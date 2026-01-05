#!/usr/bin/env python3
"""
AlphaTrader 1H Trading Bot
==========================

Paper/Live trading with the 1-hour model, completely independent from 15m model.

Features:
- Uses 1h candles from HyperLiquid
- Separate database tables (alpha_trades_1h, alpha_decisions_1h)
- Separate checkpoints (model_1h_*.pt)
- Slower loop (every 5 minutes instead of 1 minute)
- Longer minimum hold time (30 minutes instead of 5)

Usage:
    # Paper trading
    python -m alpha.trader_1h --mode paper --loop

    # Single decision (no loop)
    python -m alpha.trader_1h --mode paper --once
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass

# Set environment variable BEFORE importing config
os.environ["ALPHA_INTERVAL"] = "1h"

from dotenv import load_dotenv
load_dotenv(".env.alpha")
load_dotenv(".env.baseline", override=False)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpha.config import get_config_1h, AlphaConfig
from alpha.market_state import MarketState, Action, ActionType, create_state_from_data
from alpha.policy_network import create_policy_network
from alpha.value_network import create_value_network
from alpha.mcts import MCTS
from alpha.reward import RewardCalculator

# Import 1H database module
try:
    from alpha import db_1h as alpha_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    alpha_db = None

# Import standalone indicators
try:
    from alpha.indicators_standalone import get_hyperliquid_indicators, get_fear_greed_index
    INDICATORS_AVAILABLE = True
except ImportError:
    INDICATORS_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ALPHA-1H] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class AlphaPosition1H:
    """Current position tracking for 1H model."""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    size_usd: float
    leverage: int
    opened_at: datetime
    current_price: float = 0.0
    unrealized_pnl_pct: float = 0.0
    max_profit_pct: float = 0.0
    max_loss_pct: float = 0.0
    trade_id: Optional[int] = None
    decision_id: Optional[int] = None


class AlphaTrader1H:
    """
    1-Hour Trading Bot using Policy Network + Value Network + MCTS.
    Completely independent from 15m model.
    """

    def __init__(self, config: AlphaConfig):
        self.config = config
        self.positions: Dict[str, AlphaPosition1H] = {}

        # Paper trading balance
        self.paper_balance = 1000.0

        # Load models
        self.policy_net = None
        self.value_net = None
        self.mcts = None

        self._load_models()

        # CRITICAL: Load open positions from DB on startup
        # This prevents "zombie positions" after container restart
        self._load_open_positions_from_db()

        logger.info(f"AlphaTrader 1H initialized")
        logger.info(f"  Interval: {config.interval.interval}")
        logger.info(f"  Symbols: {config.trading.symbols}")
        logger.info(f"  Loop interval: {config.interval.loop_interval_seconds}s")
        logger.info(f"  Min hold: {config.trading.min_hold_minutes} min")
        logger.info(f"  Max hold: {getattr(config.trading, 'max_hold_minutes', 90)} min (TIME STOP)")
        logger.info(f"  Restored positions: {len(self.positions)}")

    def _load_models(self):
        """Load policy and value networks for 1H model."""
        import torch

        # Look for 1h checkpoint
        checkpoint_path = "alpha/checkpoints/final_model_1h.pt"
        if not os.path.exists(checkpoint_path):
            checkpoint_path = "alpha/checkpoints/model_1h_best.pt"
        if not os.path.exists(checkpoint_path):
            # Fall back to 15m model if 1h not available yet
            checkpoint_path = "alpha/checkpoints/final_model.pt"
            logger.warning("1H model not found, using 15m model as fallback")

        if os.path.exists(checkpoint_path):
            try:
                checkpoint = torch.load(checkpoint_path, map_location='cpu')

                # Create networks (pass NetworkConfig, not state_dim)
                self.policy_net = create_policy_network(self.config.network)
                self.value_net = create_value_network(self.config.network)

                # Load weights
                if 'policy_state_dict' in checkpoint:
                    self.policy_net.load_state_dict(checkpoint['policy_state_dict'])
                if 'value_state_dict' in checkpoint:
                    self.value_net.load_state_dict(checkpoint['value_state_dict'])

                self.policy_net.eval()
                self.value_net.eval()

                # Create MCTS (only takes config)
                self.mcts = MCTS(self.config.mcts)

                logger.info(f"Loaded model from {checkpoint_path}")

            except Exception as e:
                logger.error(f"Error loading model: {e}")
                self.policy_net = None
        else:
            logger.warning(f"No model checkpoint found at {checkpoint_path}")

    def _load_open_positions_from_db(self):
        """Load open positions from database on startup.

        This is CRITICAL for recovering state after container restart.
        Without this, the bot doesn't know about existing open positions
        and cannot close them, creating "zombie positions".
        """
        if not DB_AVAILABLE or not alpha_db:
            logger.warning("[1H] Database not available, cannot load positions")
            return

        try:
            open_trades = alpha_db.get_all_open_trades_1h()

            for trade in open_trades:
                symbol = trade['symbol']

                # Skip if we already have a position for this symbol
                # (shouldn't happen, but be safe)
                if symbol in self.positions:
                    logger.warning(f"[1H] Duplicate position for {symbol}, skipping")
                    continue

                # Convert DB row to AlphaPosition1H
                # Handle timezone-aware datetime from DB
                opened_at = trade['opened_at']
                if opened_at.tzinfo is not None:
                    # Convert to naive datetime for consistency
                    opened_at = opened_at.replace(tzinfo=None)

                position = AlphaPosition1H(
                    symbol=symbol,
                    direction=trade['direction'],
                    entry_price=float(trade['entry_price']),
                    size_usd=float(trade['size_usd']) if trade['size_usd'] else 25.0,
                    leverage=int(trade['leverage']) if trade['leverage'] else 3,
                    opened_at=opened_at,
                    current_price=float(trade['entry_price']),
                    trade_id=trade['id'],
                    decision_id=trade.get('decision_id')
                )

                self.positions[symbol] = position

                # Calculate how long position has been open
                age_hours = (datetime.now() - opened_at).total_seconds() / 3600
                logger.info(f"[1H] Restored position: {trade['direction']} {symbol} @ ${position.entry_price:.2f} (open {age_hours:.1f}h)")

            if self.positions:
                logger.info(f"[1H] ✅ Restored {len(self.positions)} positions from database")

        except Exception as e:
            logger.error(f"[1H] Error loading positions from DB: {e}")

    def get_market_data_1h(self, symbol: str) -> Optional[Dict]:
        """Get market data using 1h candles."""
        if not INDICATORS_AVAILABLE:
            logger.error("Indicators not available")
            return None

        try:
            # Get indicators (function uses default 15m candles, but that's fine for live decisions)
            # The model was trained on 1h data, but for live trading we use current market state
            # Note: get_hyperliquid_indicators returns (formatted_text, indicators_dict)
            _, indicators = get_hyperliquid_indicators(symbol)
            if not indicators:
                logger.warning(f"[1H] {symbol}: No indicators returned")
                return None

            # Get fear & greed (returns dict with 'value' key)
            fg_data = get_fear_greed_index()
            fear_greed = fg_data.get('value', 50) if fg_data else 50

            return {
                'symbol': symbol,
                'price': indicators.get('price', 0),
                'rsi_14': indicators.get('rsi_14', 50),
                'macd': indicators.get('macd', 0),
                'adx': indicators.get('adx', 25),
                'ema20': indicators.get('ema20', 0),
                'ema50': indicators.get('ema50', 0),
                'atr_14': indicators.get('atr_14', 0),
                'volume': indicators.get('volume', 0),
                'fear_greed': fear_greed,
                'interval': '1h'
            }

        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None

    def make_decision(self, symbol: str, market_data: Dict) -> Optional[Action]:
        """Make trading decision using policy network + MCTS."""
        if self.policy_net is None:
            logger.warning("No model loaded, cannot make decision")
            return None

        try:
            import torch

            # Format indicators for create_state_from_data
            indicators_data = {
                symbol: {
                    'price': market_data.get('price', 0),
                    'ema20': market_data.get('ema20', 0),
                    'ema50': market_data.get('ema50', 0),
                    'rsi_14': market_data.get('rsi_14', 50),
                    'rsi_7': market_data.get('rsi_14', 50),  # Use 14 as fallback
                    'macd': market_data.get('macd', 0),
                    'macd_signal': 0,
                    'macd_histogram': 0,
                    'atr_14': market_data.get('atr_14', 0),
                    'adx': market_data.get('adx', 25),
                    'volume_ratio': 1.0,
                    'bollinger_pct_b': 0.5,
                    'obv_trend': 0,
                }
            }

            # Format sentiment data
            sentiment_data = {
                'value': market_data.get('fear_greed', 50),
                'classification': 'Neutral'
            }

            # Position data
            position_data = None
            if symbol in self.positions:
                pos = self.positions[symbol]
                position_data = {
                    'has_position': True,
                    'symbol': pos.symbol,
                    'direction': pos.direction,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'size_usd': pos.size_usd,
                    'leverage': pos.leverage,
                    'unrealized_pnl_pct': pos.unrealized_pnl_pct,
                    'duration_hours': (datetime.now() - pos.opened_at).total_seconds() / 3600,
                    'max_profit_pct': pos.max_profit_pct,
                    'max_loss_pct': pos.max_loss_pct,
                }

            # Create market state with properly formatted data
            state = create_state_from_data(
                indicators_data=indicators_data,
                sentiment_data=sentiment_data,
                forecast_data={},
                score_data={},
                position_data=position_data,
                account_data={'balance_usd': self.paper_balance, 'equity_usd': self.paper_balance}
            )

            # Get policy prediction (pass target symbol for correct feature extraction)
            state_tensor = torch.FloatTensor(state.to_vector(target_symbol=symbol)).unsqueeze(0)

            with torch.no_grad():
                # policy_net returns: (action_probs, leverage, size_pct, confidence, entropy)
                policy_output = self.policy_net(state_tensor)
                action_probs = policy_output[0]  # First element is action_probs
                net_confidence = policy_output[3]  # Fourth element is confidence
                # value_net returns: (value, confidence)
                value_output = self.value_net(state_tensor)
                value_estimate = value_output[0].item()  # First element is value tensor

            # Get action from policy
            action_idx = torch.argmax(action_probs).item()
            confidence = action_probs[0][action_idx].item()

            # Map to action type
            action_types = [ActionType.HOLD, ActionType.OPEN_LONG, ActionType.OPEN_SHORT,
                          ActionType.CLOSE]
            action_type = action_types[min(action_idx, len(action_types) - 1)]

            # MCTS validation if enabled
            mcts_approved = True
            mcts_win_prob = None

            if self.mcts and self.config.mcts.min_win_probability > 0:
                mcts_result = self.mcts.search(state)
                mcts_win_prob = mcts_result.get('win_probability', 0)
                mcts_approved = mcts_win_prob >= self.config.mcts.min_win_probability

            # Create action with valid fields only
            action = Action(
                action_type=action_type,
                symbol=symbol,
                confidence=confidence
            )
            # Store extra info as attributes for logging
            action.value_estimate = value_estimate
            action.mcts_approved = mcts_approved
            action.mcts_win_prob = mcts_win_prob

            return action

        except Exception as e:
            logger.error(f"Error making decision for {symbol}: {e}")
            return None

    def execute_action(self, action: Action, market_data: Dict) -> bool:
        """Execute trading action (paper or live)."""
        symbol = action.symbol
        price = market_data.get('price', 0)

        if action.action_type == ActionType.HOLD:
            return True

        if action.action_type == ActionType.CLOSE:
            return self._close_position(symbol, price, "SIGNAL")

        if action.action_type in [ActionType.OPEN_LONG, ActionType.OPEN_SHORT]:
            # Check if already have position
            if symbol in self.positions:
                logger.info(f"[1H] Already have position in {symbol}, skipping")
                return False

            direction = "LONG" if action.action_type == ActionType.OPEN_LONG else "SHORT"
            return self._open_position(symbol, direction, price, action)

        return False

    def _open_position(self, symbol: str, direction: str, price: float, action: Action) -> bool:
        """Open a new position."""
        size_usd = self.config.trading.base_position_usd
        leverage = min(self.config.trading.max_leverage, 3)  # Lower leverage for 1h

        # Save to DB
        decision_id = None
        trade_id = None

        if DB_AVAILABLE and alpha_db:
            decision_id = alpha_db.save_decision_1h(
                symbol=symbol,
                policy_action=direction,
                final_action=f"OPEN_{direction}",
                policy_confidence=action.confidence,
                value_estimate=action.value_estimate,
                win_probability=action.mcts_win_prob or action.confidence,
                mcts_approved=action.mcts_approved,
                mcts_win_prob=action.mcts_win_prob,
                mcts_reason=None,
                price=price,
                rsi=50,
                macd=0,
                adx=25,
                fear_greed=50,
                market_data={},
                decision_info={'action': direction, 'interval': '1h'}
            )

            trade_id = alpha_db.save_trade_open_1h(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                size_usd=size_usd,
                leverage=leverage,
                decision_id=decision_id,
                policy_confidence=action.confidence,
                mcts_win_prob=action.mcts_win_prob,
                is_paper=self.config.trading.paper_trading
            )

        # Create position
        self.positions[symbol] = AlphaPosition1H(
            symbol=symbol,
            direction=direction,
            entry_price=price,
            size_usd=size_usd,
            leverage=leverage,
            opened_at=datetime.now(),
            current_price=price,
            trade_id=trade_id,
            decision_id=decision_id
        )

        logger.info(f"[1H] ✅ OPENED {direction} {symbol} @ ${price:.2f}")
        return True

    def _close_position(self, symbol: str, price: float, reason: str) -> bool:
        """Close existing position."""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        # Calculate P&L
        if position.direction == "LONG":
            pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
        else:
            pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage

        # Update paper balance
        pnl_usd = position.size_usd * (pnl_pct / 100)
        self.paper_balance += pnl_usd

        # Save to DB
        if DB_AVAILABLE and alpha_db and position.trade_id:
            alpha_db.close_trade_1h(position.trade_id, price, reason)

        logger.info(f"[1H] ✅ CLOSED {position.direction} {symbol} @ ${price:.2f} | P&L: {pnl_pct:+.2f}%")

        del self.positions[symbol]
        return True

    def check_positions(self):
        """Check and manage open positions."""
        for symbol, position in list(self.positions.items()):
            try:
                market_data = self.get_market_data_1h(symbol)
                if not market_data:
                    continue

                price = market_data.get('price', 0)
                position.current_price = price

                # Update P&L
                if position.direction == "LONG":
                    pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
                else:
                    pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage

                position.unrealized_pnl_pct = pnl_pct
                position.max_profit_pct = max(position.max_profit_pct, pnl_pct)
                position.max_loss_pct = min(position.max_loss_pct, pnl_pct)

                # Update DB
                if DB_AVAILABLE and alpha_db and position.trade_id:
                    alpha_db.update_trade_prices_1h(position.trade_id, price, position.direction)

                # Check hold time
                hold_minutes = (datetime.now() - position.opened_at).total_seconds() / 60

                # TIME STOP: Force close after max_hold_minutes (default 90 min)
                # Analysis shows: 30-45min = +61.52, >2h = -37.04
                # Cutoff at 90 min captures most profit, avoids death zone
                max_hold = getattr(self.config.trading, 'max_hold_minutes', 90)
                if hold_minutes >= max_hold:
                    logger.info(f"[1H] ⏰ TIME STOP: {symbol} held {hold_minutes:.0f}m > {max_hold}m limit")
                    self._close_position(symbol, price, "TIME_STOP")
                    continue

                # Check for close conditions
                if hold_minutes >= self.config.trading.min_hold_minutes:
                    # Get fresh decision
                    action = self.make_decision(symbol, market_data)
                    if action and action.action_type == ActionType.CLOSE:
                        self._close_position(symbol, price, "SIGNAL")
                    # Also check if significant profit
                    elif pnl_pct > 2.0:  # 2% profit threshold for 1h model
                        self._close_position(symbol, price, "TAKE_PROFIT")

                # Emergency stop loss
                if pnl_pct < -5.0:  # 5% stop loss
                    self._close_position(symbol, price, "STOP_LOSS")

            except Exception as e:
                logger.error(f"[1H] Error checking position {symbol}: {e}")

    def run_once(self):
        """Run one trading cycle."""
        logger.info(f"[1H] {'='*50}")
        logger.info(f"[1H] Trading cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Check existing positions first
        self.check_positions()

        # Make decisions for each symbol
        for symbol in self.config.trading.symbols:
            try:
                # Skip if already have position
                if symbol in self.positions:
                    continue

                # Check max positions
                if len(self.positions) >= self.config.trading.max_open_positions:
                    break

                # Get market data
                market_data = self.get_market_data_1h(symbol)
                if not market_data:
                    logger.warning(f"[1H] {symbol}: No market data returned")
                    continue

                # Make decision
                action = self.make_decision(symbol, market_data)
                if not action:
                    logger.warning(f"[1H] {symbol}: No action returned from make_decision")
                    continue

                # Log the decision
                action_name = action.action_type.name if action.action_type else "NONE"
                logger.info(f"[1H] {symbol}: Decision={action_name} conf={action.confidence:.1%} value={action.value_estimate:.3f}")

                if action.mcts_win_prob is not None:
                    logger.info(f"[1H] {symbol}: MCTS win_prob={action.mcts_win_prob:.1%} approved={action.mcts_approved}")

                # Execute if approved
                if action.action_type != ActionType.HOLD:
                    if action.mcts_approved or self.config.mcts.min_win_probability == 0:
                        self.execute_action(action, market_data)
                    else:
                        logger.info(f"[1H] MCTS vetoed {symbol} action")

            except Exception as e:
                logger.error(f"[1H] Error processing {symbol}: {e}")

        # Log status
        open_count = len(self.positions)
        logger.info(f"[1H] Status: {open_count} open positions, Balance: ${self.paper_balance:.2f}")

    def run_loop(self):
        """Run continuous trading loop."""
        logger.info(f"[1H] Starting trading loop (interval: {self.config.interval.loop_interval_seconds}s)")

        while True:
            try:
                self.run_once()
                time.sleep(self.config.interval.loop_interval_seconds)

            except KeyboardInterrupt:
                logger.info("[1H] Shutting down...")
                break
            except Exception as e:
                logger.error(f"[1H] Loop error: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="AlphaTrader 1H Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper",
                       help="Trading mode")
    parser.add_argument("--loop", action="store_true",
                       help="Run continuous loop")
    parser.add_argument("--once", action="store_true",
                       help="Run single cycle")

    args = parser.parse_args()

    # Get 1h config
    config = get_config_1h()
    config.trading.paper_trading = (args.mode == "paper")

    # Create trader
    trader = AlphaTrader1H(config)

    if args.once:
        trader.run_once()
    else:
        trader.run_loop()


if __name__ == "__main__":
    main()
