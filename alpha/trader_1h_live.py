#!/usr/bin/env python3
"""
AlphaTrader 1H LIVE Trading Bot
================================

LIVE trading with the 1-hour model on HyperLiquid.
Based on trader_1h.py but with actual order execution.

Usage:
    # Live trading
    python -m alpha.trader_1h_live --mode live --loop

    # Paper trading (simulated)
    python -m alpha.trader_1h_live --mode paper --loop
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

# Import HyperLiquidTrader for LIVE trading
try:
    from hyperliquid_trader import HyperLiquidTrader
    HL_AVAILABLE = True
except ImportError:
    HL_AVAILABLE = False
    HyperLiquidTrader = None

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
    format='%(asctime)s [ALPHA-1H-LIVE] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================
# 1H MODEL CONFIGURATION
# ============================================================
def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default

CONFIG_1H = {
    'config_version': os.getenv('ALPHA_CONFIG_VERSION', 'v3_live'),
    'min_hold_minutes': _env_int('ALPHA_MIN_HOLD_MINUTES', 5),
    'max_hold_minutes': _env_int('ALPHA_MAX_HOLD_MINUTES', 30),
    'take_profit_pct': _env_float('ALPHA_TAKE_PROFIT_PCT', 1.5),
    'stop_loss_pct': _env_float('ALPHA_STOP_LOSS_PCT', 2.0),
    'trailing_activate_pct': _env_float('ALPHA_TRAILING_ACTIVATE_PCT', 0.8),
    'trailing_distance_pct': _env_float('ALPHA_TRAILING_DISTANCE_PCT', 0.5),
    'position_usd': _env_float('ALPHA_POSITION_USD', 50.0),
    'max_leverage': _env_int('ALPHA_MAX_LEVERAGE', 3),
    'loop_interval': _env_int('ALPHA_SLOW_INTERVAL', 300),
}

logger.info(f"1H LIVE Config loaded: {CONFIG_1H}")


@dataclass
class AlphaPosition1H:
    """Current position tracking for 1H model."""
    symbol: str
    direction: str
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


class AlphaTrader1HLive:
    """
    1-Hour LIVE Trading Bot using Policy Network + Value Network + MCTS.
    Executes real trades on HyperLiquid.
    """

    def __init__(self, config: AlphaConfig, live_trading: bool = False):
        self.config = config
        self.positions: Dict[str, AlphaPosition1H] = {}
        self.live_trading = live_trading

        # Paper trading balance (used when not live)
        self.paper_balance = 1000.0

        # HyperLiquid trader (only for live trading)
        self.hl_trader = None
        if live_trading:
            self._init_hyperliquid()

        # Load models
        self.policy_net = None
        self.value_net = None
        self.mcts = None
        self._load_models()

        # Load open positions from DB
        self._load_open_positions_from_db()

        logger.info(f"AlphaTrader 1H LIVE initialized")
        logger.info(f"  Mode: {'LIVE TRADING' if live_trading else 'PAPER TRADING'}")
        logger.info(f"  HyperLiquid: {'Connected' if self.hl_trader else 'Not connected'}")
        logger.info(f"  Config version: {CONFIG_1H['config_version']}")
        logger.info(f"  Symbols: {config.trading.symbols}")
        logger.info(f"  Max hold: {CONFIG_1H['max_hold_minutes']} min")
        logger.info(f"  Stop loss: {CONFIG_1H['stop_loss_pct']}%")
        logger.info(f"  Position: ${CONFIG_1H['position_usd']} x {CONFIG_1H['max_leverage']}x")
        logger.info(f"  Restored positions: {len(self.positions)}")

    def _init_hyperliquid(self):
        """Initialize HyperLiquid trader for live trading."""
        if not HL_AVAILABLE:
            logger.error("HyperLiquidTrader not available! Install hyperliquid-python-sdk")
            return

        private_key = os.getenv('PRIVATE_KEY') or os.getenv('HYPERLIQUID_PRIVATE_KEY')
        wallet_address = os.getenv('WALLET_ADDRESS') or os.getenv('HYPERLIQUID_WALLET_ADDRESS')

        if not private_key:
            logger.error("PRIVATE_KEY not set! Cannot do live trading.")
            return

        try:
            # Use mainnet for live trading
            self.hl_trader = HyperLiquidTrader(
                secret_key=private_key,
                account_address=wallet_address or "",
                testnet=False,
                skip_ws=True
            )

            # Test connection by getting account status
            status = self.hl_trader.get_account_status()
            balance = status.get('balance_usd', 0)
            logger.info(f"HyperLiquid connected! Balance: ${balance:.2f}")

        except Exception as e:
            logger.error(f"Failed to initialize HyperLiquid: {e}")
            self.hl_trader = None

    def _load_models(self):
        """Load policy and value networks for 1H model."""
        import torch

        checkpoint_path = "alpha/checkpoints/final_model_1h.pt"
        if not os.path.exists(checkpoint_path):
            checkpoint_path = "alpha/checkpoints/final_model.pt"
            logger.warning("1H model not found, using fallback")

        if os.path.exists(checkpoint_path):
            try:
                checkpoint = torch.load(checkpoint_path, map_location='cpu')
                self.policy_net = create_policy_network(self.config.network)
                self.value_net = create_value_network(self.config.network)

                if 'policy_state_dict' in checkpoint:
                    self.policy_net.load_state_dict(checkpoint['policy_state_dict'])
                if 'value_state_dict' in checkpoint:
                    self.value_net.load_state_dict(checkpoint['value_state_dict'])

                self.policy_net.eval()
                self.value_net.eval()
                self.mcts = MCTS(self.config.mcts)
                logger.info(f"Loaded model from {checkpoint_path}")

            except Exception as e:
                logger.error(f"Error loading model: {e}")
        else:
            logger.warning(f"No model checkpoint found at {checkpoint_path}")

    def _load_open_positions_from_db(self):
        """Load open positions from database on startup."""
        if not DB_AVAILABLE or not alpha_db:
            return

        try:
            open_trades = alpha_db.get_all_open_trades_1h()
            for trade in open_trades:
                symbol = trade['symbol']
                if symbol in self.positions:
                    continue

                opened_at = trade['opened_at']
                if opened_at.tzinfo is not None:
                    opened_at = opened_at.replace(tzinfo=None)

                position = AlphaPosition1H(
                    symbol=symbol,
                    direction=trade['direction'],
                    entry_price=float(trade['entry_price']),
                    size_usd=float(trade['size_usd']) if trade['size_usd'] else 50.0,
                    leverage=int(trade['leverage']) if trade['leverage'] else 3,
                    opened_at=opened_at,
                    current_price=float(trade['entry_price']),
                    trade_id=trade['id'],
                    decision_id=trade.get('decision_id')
                )
                self.positions[symbol] = position

                age_hours = (datetime.now() - opened_at).total_seconds() / 3600
                logger.info(f"Restored: {trade['direction']} {symbol} @ ${position.entry_price:.2f} ({age_hours:.1f}h)")

            if self.positions:
                logger.info(f"Restored {len(self.positions)} positions from DB")

        except Exception as e:
            logger.error(f"Error loading positions: {e}")

    def get_balance(self) -> float:
        """Get current balance (real or paper)."""
        if self.live_trading and self.hl_trader:
            try:
                status = self.hl_trader.get_account_status()
                return status.get('balance_usd', self.paper_balance)
            except:
                pass
        return self.paper_balance

    def get_market_data_1h(self, symbol: str) -> Optional[Dict]:
        """Get market data using indicators."""
        if not INDICATORS_AVAILABLE:
            return None

        try:
            _, indicators = get_hyperliquid_indicators(symbol)
            if not indicators:
                return None

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
            }
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None

    def make_decision(self, symbol: str, market_data: Dict) -> Optional[Action]:
        """Make trading decision using policy network."""
        if self.policy_net is None:
            logger.warning("No model loaded")
            return None

        try:
            import torch

            indicators_data = {
                symbol: {
                    'price': market_data.get('price', 0),
                    'ema20': market_data.get('ema20', 0),
                    'ema50': market_data.get('ema50', 0),
                    'rsi_14': market_data.get('rsi_14', 50),
                    'rsi_7': market_data.get('rsi_14', 50),
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

            sentiment_data = {'value': market_data.get('fear_greed', 50), 'classification': 'Neutral'}

            position_data = None
            if symbol in self.positions:
                pos = self.positions[symbol]
                position_data = {
                    'has_position': True,
                    'symbol': pos.symbol,
                    'direction': pos.direction,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl_pct': pos.unrealized_pnl_pct,
                    'duration_hours': (datetime.now() - pos.opened_at).total_seconds() / 3600,
                }

            balance = self.get_balance()
            state = create_state_from_data(
                indicators_data=indicators_data,
                sentiment_data=sentiment_data,
                forecast_data={},
                score_data={},
                position_data=position_data,
                account_data={'balance_usd': balance, 'equity_usd': balance}
            )

            state_tensor = torch.FloatTensor(state.to_vector(target_symbol=symbol)).unsqueeze(0)

            with torch.no_grad():
                policy_output = self.policy_net(state_tensor)
                action_probs = policy_output[0]
                value_output = self.value_net(state_tensor)
                value_estimate = value_output[0].item()

            action_idx = torch.argmax(action_probs).item()
            confidence = action_probs[0][action_idx].item()
            action_types = [ActionType.HOLD, ActionType.OPEN_LONG, ActionType.OPEN_SHORT, ActionType.CLOSE]
            action_type = action_types[min(action_idx, len(action_types) - 1)]

            action = Action(action_type=action_type, symbol=symbol, confidence=confidence)
            action.value_estimate = value_estimate
            action.mcts_approved = True
            action.mcts_win_prob = None

            return action

        except Exception as e:
            logger.error(f"Error making decision for {symbol}: {e}")
            return None

    def _open_position(self, symbol: str, direction: str, price: float, action: Action) -> bool:
        """Open a new position - LIVE or PAPER."""
        size_usd = CONFIG_1H['position_usd']
        leverage = CONFIG_1H['max_leverage']
        balance = self.get_balance()

        # Calculate portion of balance
        portion = size_usd / balance if balance > 0 else 0.05

        # LIVE TRADING - Execute on HyperLiquid
        if self.live_trading and self.hl_trader:
            try:
                order = {
                    "operation": "open",
                    "symbol": symbol,
                    "direction": direction.lower(),
                    "target_portion_of_balance": float(portion),
                    "leverage": leverage,
                    "reason": f"Alpha1H {action.action_type.name}"
                }

                logger.info(f"[LIVE] Executing order: {order}")
                result = self.hl_trader.execute_signal(order)

                if result.get('status') == 'ok' or 'statuses' in result:
                    logger.info(f"[LIVE] Order executed successfully: {result}")
                else:
                    logger.error(f"[LIVE] Order failed: {result}")
                    return False

            except Exception as e:
                logger.error(f"[LIVE] Error executing order: {e}")
                return False

        # Save to DB
        decision_id = None
        trade_id = None

        if DB_AVAILABLE and alpha_db:
            decision_id = alpha_db.save_decision_1h(
                symbol=symbol,
                policy_action=direction,
                final_action=f"OPEN_{direction}",
                policy_confidence=action.confidence,
                value_estimate=getattr(action, 'value_estimate', 0),
                win_probability=action.confidence,
                mcts_approved=True,
                mcts_win_prob=None,
                mcts_reason=None,
                price=price,
                rsi=50, macd=0, adx=25, fear_greed=50,
                market_data={},
                decision_info={'action': direction, 'interval': '1h', 'live': self.live_trading}
            )

            trade_id = alpha_db.save_trade_open_1h(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                size_usd=size_usd,
                leverage=leverage,
                decision_id=decision_id,
                policy_confidence=action.confidence,
                mcts_win_prob=None,
                is_paper=not self.live_trading
            )

        # Track position
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

        mode = "LIVE" if self.live_trading else "PAPER"
        logger.info(f"[{mode}] OPENED {direction} {symbol} @ ${price:.2f}")
        return True

    def _close_position(self, symbol: str, price: float, reason: str) -> bool:
        """Close existing position - LIVE or PAPER."""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        # Calculate P&L
        if position.direction == "LONG":
            pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
        else:
            pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage

        # LIVE TRADING - Close on HyperLiquid
        if self.live_trading and self.hl_trader:
            try:
                logger.info(f"[LIVE] Closing {symbol} position...")
                result = self.hl_trader.exchange.market_close(symbol)

                if result.get('status') == 'ok' or 'statuses' in result:
                    logger.info(f"[LIVE] Position closed: {result}")
                else:
                    logger.error(f"[LIVE] Close failed: {result}")

            except Exception as e:
                logger.error(f"[LIVE] Error closing position: {e}")

        # Update paper balance
        pnl_usd = position.size_usd * (pnl_pct / 100)
        self.paper_balance += pnl_usd

        # Save to DB
        if DB_AVAILABLE and alpha_db and position.trade_id:
            alpha_db.close_trade_1h(position.trade_id, price, reason)

        mode = "LIVE" if self.live_trading else "PAPER"
        logger.info(f"[{mode}] CLOSED {position.direction} {symbol} @ ${price:.2f} | P&L: {pnl_pct:+.2f}%")

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

                hold_minutes = (datetime.now() - position.opened_at).total_seconds() / 60

                # TIME STOP
                max_hold = CONFIG_1H['max_hold_minutes']
                if hold_minutes >= max_hold:
                    logger.info(f"TIME STOP: {symbol} held {hold_minutes:.0f}m >= {max_hold}m")
                    self._close_position(symbol, price, "TIME_STOP")
                    continue

                # STOP LOSS
                stop_loss = CONFIG_1H['stop_loss_pct']
                if pnl_pct <= -stop_loss:
                    logger.info(f"STOP LOSS: {symbol} P&L {pnl_pct:.2f}% <= -{stop_loss}%")
                    self._close_position(symbol, price, "STOP_LOSS")
                    continue

                # TRAILING STOP
                trailing_activate = CONFIG_1H['trailing_activate_pct']
                trailing_distance = CONFIG_1H['trailing_distance_pct']

                if position.max_profit_pct >= trailing_activate:
                    drop_from_max = position.max_profit_pct - pnl_pct
                    if drop_from_max >= trailing_distance:
                        logger.info(f"TRAILING STOP: {symbol} dropped {drop_from_max:.2f}% from max")
                        self._close_position(symbol, price, "TRAILING_STOP")
                        continue

                # TAKE PROFIT / SIGNAL (after min_hold)
                min_hold = CONFIG_1H['min_hold_minutes']
                if hold_minutes >= min_hold:
                    take_profit = CONFIG_1H['take_profit_pct']
                    if pnl_pct >= take_profit:
                        logger.info(f"TAKE PROFIT: {symbol} P&L {pnl_pct:.2f}% >= {take_profit}%")
                        self._close_position(symbol, price, "TAKE_PROFIT")
                        continue

                    action = self.make_decision(symbol, market_data)
                    if action and action.action_type == ActionType.CLOSE:
                        self._close_position(symbol, price, "SIGNAL")

            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")

    def run_loop(self):
        """Run continuous trading loop."""
        slow_interval = CONFIG_1H['loop_interval']
        fast_interval = 30

        logger.info(f"Starting trading loop")
        logger.info(f"  SLOW: {slow_interval}s, FAST: {fast_interval}s")

        last_slow = datetime.min

        while True:
            try:
                now = datetime.now()
                self.check_positions()

                if (now - last_slow).total_seconds() >= slow_interval:
                    logger.info(f"{'='*50}")
                    logger.info(f"SLOW loop at {now.strftime('%H:%M:%S')}")
                    last_slow = now

                    for symbol in self.config.trading.symbols:
                        try:
                            if symbol in self.positions:
                                continue
                            if len(self.positions) >= self.config.trading.max_open_positions:
                                break

                            market_data = self.get_market_data_1h(symbol)
                            if not market_data:
                                continue

                            action = self.make_decision(symbol, market_data)
                            if not action:
                                continue

                            action_name = action.action_type.name
                            logger.info(f"{symbol}: {action_name} conf={action.confidence:.1%}")

                            if action.action_type in [ActionType.OPEN_LONG, ActionType.OPEN_SHORT]:
                                direction = "LONG" if action.action_type == ActionType.OPEN_LONG else "SHORT"
                                self._open_position(symbol, direction, market_data['price'], action)

                        except Exception as e:
                            logger.error(f"Error processing {symbol}: {e}")

                    balance = self.get_balance()
                    logger.info(f"Status: {len(self.positions)} positions, Balance: ${balance:.2f}")

                time.sleep(fast_interval)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="AlphaTrader 1H LIVE Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--loop", action="store_true")

    args = parser.parse_args()

    config = get_config_1h()
    live_trading = (args.mode == "live")

    if live_trading:
        logger.warning("=" * 60)
        logger.warning("  LIVE TRADING MODE - REAL MONEY AT RISK!")
        logger.warning("=" * 60)

    trader = AlphaTrader1HLive(config, live_trading=live_trading)
    trader.run_loop()


if __name__ == "__main__":
    main()
