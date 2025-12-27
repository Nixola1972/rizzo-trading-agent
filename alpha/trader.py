#!/usr/bin/env python3
"""
AlphaTrader - RL-Powered Trading Bot
=====================================

Main trading engine that uses Policy Network + Value Network + MCTS
to make trading decisions.

This is COMPLETELY INDEPENDENT from botone_v6 and can run in parallel.

Usage:
    # Paper trading (no real money)
    python -m alpha.trader --mode paper --loop

    # Live trading (real money - CAUTION!)
    python -m alpha.trader --mode live --loop

    # Single decision (no loop)
    python -m alpha.trader --mode paper --once
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv(".env.alpha")
load_dotenv(".env.baseline", override=False)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .config import AlphaConfig, get_config
from .market_state import MarketState, Action, ActionType, create_state_from_data
from .policy_network import create_policy_network
from .value_network import create_value_network
from .mcts import MCTS
from .reward import RewardCalculator

# Import shared modules from parent
try:
    from indicators import get_hyperliquid_indicators
    from forecaster import get_crypto_forecasts
    from sentiment import get_fear_greed_index
    from signal_scorer import calculate_signal_score, calculate_smart_score_v2
    from hyperliquid_trader import HyperLiquidTrader
    MODULES_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Could not import shared modules: {e}")
    MODULES_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ALPHA] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class AlphaPosition:
    """Current position tracking."""
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


class AlphaTrader:
    """
    AlphaTrader - The RL-powered trading bot.

    Architecture:
    1. PolicyNetwork decides what action to take
    2. ValueNetwork estimates probability of success
    3. MCTS simulates future scenarios for validation
    4. If all checks pass, execute the trade
    """

    def __init__(self, config: Optional[AlphaConfig] = None):
        self.config = config or get_config()

        # Validate config
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            if not self.config.trading.paper_trading:
                raise ValueError("Cannot start live trading with config errors")

        # Initialize networks
        logger.info("Initializing neural networks...")
        self.policy = create_policy_network(self.config.network)
        self.value = create_value_network(self.config.network)
        self.mcts = MCTS(self.config.mcts)
        self.reward_calc = RewardCalculator(self.config.reward)

        # Load checkpoint if available
        checkpoint_path = os.path.join(
            self.config.training.checkpoint_dir,
            "final_model.pt"
        )
        if os.path.exists(checkpoint_path):
            logger.info(f"Loading model from {checkpoint_path}")
            self._load_checkpoint(checkpoint_path)

        # Initialize exchange connection (for live trading)
        self.exchange: Optional[HyperLiquidTrader] = None
        if MODULES_AVAILABLE and not self.config.trading.paper_trading:
            logger.info("Connecting to HyperLiquid...")
            self.exchange = HyperLiquidTrader(
                secret_key=self.config.hl_private_key,
                account_address=self.config.hl_account_address,
                testnet=self.config.hl_testnet,
            )

        # State
        self.positions: Dict[str, AlphaPosition] = {}
        self.last_decision_time: Optional[datetime] = None
        self.total_trades = 0
        self.winning_trades = 0

    def _load_checkpoint(self, path: str):
        """Load model weights from checkpoint."""
        try:
            import torch
            # weights_only=False needed for custom classes in checkpoint
            checkpoint = torch.load(path, map_location='cpu', weights_only=False)

            if hasattr(self.policy, 'load_state_dict'):
                self.policy.load_state_dict(checkpoint['policy_state_dict'])
            if hasattr(self.value, 'load_state_dict'):
                self.value.load_state_dict(checkpoint['value_state_dict'])

            logger.info("Model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")

    def fetch_market_data(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch current market data from all sources.

        Returns:
            Dictionary with indicators, sentiment, forecasts, scores
        """
        if not MODULES_AVAILABLE:
            logger.warning("Shared modules not available, returning empty data")
            return {}

        data = {
            'indicators': {},
            'sentiment': {},
            'forecasts': {},
            'scores': {},
            'account': {},
        }

        try:
            # Get indicators for each symbol
            for symbol in symbols:
                ind_text, ind_json = get_hyperliquid_indicators(symbol.upper())
                if ind_json:
                    data['indicators'][symbol] = ind_json

            # Get sentiment
            sentiment = get_fear_greed_index()
            if sentiment:
                data['sentiment'] = sentiment

            # Get forecasts
            forecasts = get_crypto_forecasts(symbols, testnet=self.config.hl_testnet)
            if forecasts:
                for fc in forecasts:
                    symbol = fc.get('Ticker', 'BTC')
                    data['forecasts'][symbol] = {
                        'change_pct': fc.get('Variazione %', 0),
                        'prediction': fc.get('Previsione', 0),
                        'timeframe': fc.get('Timeframe', ''),
                    }

            # Calculate scores
            for symbol in symbols:
                if symbol in data['indicators']:
                    ind = data['indicators'][symbol]
                    fg_value = data['sentiment'].get('value', 50) if data['sentiment'] else 50
                    fc_change = data['forecasts'].get(symbol, {}).get('change_pct', 0)

                    score = calculate_signal_score(
                        price=ind.get('price', 0),
                        ema20=ind.get('ema20', 0),
                        rsi=ind.get('rsi_14', 50),
                        macd=ind.get('macd', 0),
                        fear_greed=fg_value,
                        forecast_change_pct=fc_change,
                        volume_bid=ind.get('volume_bid', 0),
                        volume_ask=ind.get('volume_ask', 0),
                        symbol=symbol,
                    )
                    data['scores'][symbol] = score

            # Get account status if exchange connected
            if self.exchange:
                account = self.exchange.get_account_status()
                data['account'] = {
                    'balance_usd': account.get('balance_usd', 0),
                    'equity_usd': account.get('balance_usd', 0),
                }

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")

        return data

    def create_market_state(self, data: Dict, symbol: str) -> MarketState:
        """Create MarketState from fetched data."""

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
                'duration_hours': (datetime.utcnow() - pos.opened_at).total_seconds() / 3600,
                'max_profit_pct': pos.max_profit_pct,
                'max_loss_pct': pos.max_loss_pct,
            }

        return create_state_from_data(
            indicators_data=data.get('indicators', {}),
            sentiment_data=data.get('sentiment', {}),
            forecast_data=data.get('forecasts', {}),
            score_data=data.get('scores', {}),
            position_data=position_data,
            account_data=data.get('account', {}),
        )

    def make_decision(self, symbol: str = "BTC") -> Tuple[Action, Dict]:
        """
        Make a trading decision for a symbol.

        Returns:
            (Action, decision_info)
        """
        decision_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'steps': [],
        }

        # 1. Fetch market data
        logger.info(f"Fetching market data for {symbol}...")
        data = self.fetch_market_data([symbol])
        decision_info['market_data'] = bool(data.get('indicators'))

        if symbol not in data.get('indicators', {}):
            logger.warning(f"No indicator data for {symbol}")
            return Action(ActionType.HOLD, symbol), decision_info

        # 2. Create market state
        state = self.create_market_state(data, symbol)
        decision_info['state_dim'] = state.state_dim

        # 3. Get action from policy network
        logger.info("Consulting Policy Network...")
        if hasattr(self.policy, 'get_action'):
            try:
                action, policy_output = self.policy.get_action(state, symbol)
            except:
                action = self.policy.get_action(state, symbol)
                policy_output = None
        else:
            action = self.policy.get_action(state, symbol)
            policy_output = None

        decision_info['policy_action'] = action.action_type.name
        decision_info['policy_confidence'] = action.confidence
        decision_info['steps'].append(f"Policy suggests: {action.action_type.name}")

        # 4. Get value estimate
        logger.info("Consulting Value Network...")
        value_output = self.value.estimate(state, symbol)
        decision_info['value_estimate'] = value_output.value
        decision_info['win_probability'] = value_output.win_probability
        decision_info['steps'].append(
            f"Value estimate: {value_output.value:.3f} "
            f"(win prob: {value_output.win_probability:.1%})"
        )

        # 5. MCTS validation (for open/close actions)
        if action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            logger.info("Running MCTS simulation...")
            should_execute, mcts_win_prob, mcts_reason = self.mcts.should_execute_trade(
                state, symbol, action.action_type
            )
            decision_info['mcts_approved'] = should_execute
            decision_info['mcts_win_prob'] = mcts_win_prob
            decision_info['mcts_reason'] = mcts_reason
            decision_info['steps'].append(f"MCTS: {mcts_reason}")

            if not should_execute:
                logger.info(f"MCTS VETOED {action.action_type.name}: {mcts_reason}")
                action = Action(ActionType.HOLD, symbol, confidence=0.0)
                decision_info['final_action'] = 'HOLD (MCTS veto)'
                return action, decision_info

        # 6. Value Network veto (if win probability too low)
        min_win_prob = self.config.mcts.min_win_probability
        if action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            if value_output.win_probability < min_win_prob:
                logger.info(
                    f"Value Network VETOED: "
                    f"win prob {value_output.win_probability:.1%} < {min_win_prob:.0%}"
                )
                action = Action(ActionType.HOLD, symbol, confidence=0.0)
                decision_info['final_action'] = 'HOLD (Value veto)'
                return action, decision_info

        decision_info['final_action'] = action.action_type.name
        return action, decision_info

    def execute_action(self, action: Action) -> bool:
        """
        Execute a trading action.

        Returns:
            True if executed successfully
        """
        if action.action_type == ActionType.HOLD:
            logger.info(f"HOLD {action.symbol} - no action needed")
            return True

        if self.config.trading.paper_trading:
            return self._execute_paper(action)
        else:
            return self._execute_live(action)

    def _execute_paper(self, action: Action) -> bool:
        """Execute paper trade (simulated)."""
        symbol = action.symbol

        if action.action_type == ActionType.CLOSE:
            if symbol in self.positions:
                pos = self.positions[symbol]
                logger.info(
                    f"[PAPER] CLOSE {symbol} {pos.direction} | "
                    f"P&L: {pos.unrealized_pnl_pct:.2f}%"
                )
                if pos.unrealized_pnl_pct > 0:
                    self.winning_trades += 1
                self.total_trades += 1
                del self.positions[symbol]
                return True
            return False

        elif action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            if symbol in self.positions:
                logger.warning(f"Already have position in {symbol}")
                return False

            direction = "LONG" if action.action_type == ActionType.OPEN_LONG else "SHORT"
            position_size = self.config.trading.base_position_usd * action.position_size_pct

            # Get current price (need to fetch)
            data = self.fetch_market_data([symbol])
            price = data.get('indicators', {}).get(symbol, {}).get('price', 0)

            if price == 0:
                logger.error("Could not get current price")
                return False

            self.positions[symbol] = AlphaPosition(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                size_usd=position_size,
                leverage=action.leverage,
                opened_at=datetime.utcnow(),
                current_price=price,
            )

            logger.info(
                f"[PAPER] OPEN {direction} {symbol} | "
                f"Size: ${position_size:.0f} | Leverage: {action.leverage}x | "
                f"Entry: ${price:,.2f}"
            )
            return True

        return False

    def _execute_live(self, action: Action) -> bool:
        """Execute live trade on exchange."""
        if not self.exchange:
            logger.error("Exchange not connected")
            return False

        symbol = action.symbol

        if action.action_type == ActionType.CLOSE:
            result = self.exchange.execute_signal({
                'operation': 'close',
                'symbol': symbol,
                'direction': 'long',  # Will close whatever is open
                'reason': 'AlphaTrader decision',
            })
            if result.get('success'):
                if symbol in self.positions:
                    del self.positions[symbol]
                return True
            return False

        elif action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            direction = "long" if action.action_type == ActionType.OPEN_LONG else "short"
            position_pct = (
                self.config.trading.base_position_usd *
                action.position_size_pct /
                1000  # Assume $1000 balance
            )

            result = self.exchange.execute_signal({
                'operation': 'open',
                'symbol': symbol,
                'direction': direction,
                'target_portion_of_balance': min(position_pct, 0.5),
                'leverage': action.leverage,
                'reason': f'AlphaTrader: {action.confidence:.1%} confidence',
            })

            return result.get('success', False)

        return False

    def update_positions(self):
        """Update P&L for open positions."""
        if not self.positions:
            return

        for symbol, pos in list(self.positions.items()):
            data = self.fetch_market_data([symbol])
            price = data.get('indicators', {}).get(symbol, {}).get('price', 0)

            if price > 0:
                pos.current_price = price

                if pos.direction == "LONG":
                    pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100 * pos.leverage
                else:
                    pnl_pct = ((pos.entry_price - price) / pos.entry_price) * 100 * pos.leverage

                pos.unrealized_pnl_pct = pnl_pct
                pos.max_profit_pct = max(pos.max_profit_pct, pnl_pct)
                pos.max_loss_pct = min(pos.max_loss_pct, pnl_pct)

                logger.debug(
                    f"{symbol} {pos.direction}: P&L {pnl_pct:+.2f}% | "
                    f"MFE: {pos.max_profit_pct:.2f}% | MAE: {pos.max_loss_pct:.2f}%"
                )

    def run_loop(self):
        """Main trading loop."""
        logger.info("=" * 60)
        logger.info("AlphaTrader Starting")
        logger.info(f"Mode: {'PAPER' if self.config.trading.paper_trading else 'LIVE'}")
        logger.info(f"Symbols: {self.config.trading.symbols}")
        logger.info(f"MCTS min win prob: {self.config.mcts.min_win_probability:.0%}")
        logger.info("=" * 60)

        slow_interval = self.config.trading.slow_loop_interval
        fast_interval = self.config.trading.fast_loop_interval
        last_slow = datetime.min

        while True:
            try:
                now = datetime.utcnow()

                # Fast loop: update positions
                self.update_positions()

                # Slow loop: make decisions
                if (now - last_slow).total_seconds() >= slow_interval:
                    last_slow = now

                    for symbol in self.config.trading.symbols:
                        logger.info(f"\n{'='*40}")
                        logger.info(f"Evaluating {symbol}...")

                        action, info = self.make_decision(symbol)

                        logger.info(f"Decision: {action.action_type.name}")
                        for step in info.get('steps', []):
                            logger.info(f"  -> {step}")

                        if action.action_type != ActionType.HOLD:
                            success = self.execute_action(action)
                            logger.info(f"Execution: {'SUCCESS' if success else 'FAILED'}")

                        time.sleep(1)  # Small delay between symbols

                time.sleep(fast_interval)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(30)

    def run_once(self):
        """Make a single decision for each symbol."""
        for symbol in self.config.trading.symbols:
            logger.info(f"\n{'='*40}")
            logger.info(f"Evaluating {symbol}...")

            action, info = self.make_decision(symbol)

            logger.info(f"Decision: {action.action_type.name}")
            logger.info(f"Confidence: {action.confidence:.1%}")
            logger.info(f"Value estimate: {info.get('value_estimate', 0):.3f}")
            logger.info(f"Win probability: {info.get('win_probability', 0):.1%}")

            for step in info.get('steps', []):
                logger.info(f"  -> {step}")

            print(json.dumps(info, indent=2, default=str))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='AlphaTrader')
    parser.add_argument(
        '--mode',
        choices=['paper', 'live'],
        default='paper',
        help='Trading mode'
    )
    parser.add_argument(
        '--loop',
        action='store_true',
        help='Run in continuous loop mode'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Make single decision and exit'
    )
    parser.add_argument(
        '--symbols',
        nargs='+',
        default=['BTC', 'ETH', 'SOL'],
        help='Symbols to trade'
    )
    args = parser.parse_args()

    # Configure
    config = get_config()
    config.trading.paper_trading = (args.mode == 'paper')
    config.trading.symbols = args.symbols

    # Create trader
    trader = AlphaTrader(config)

    if args.once:
        trader.run_once()
    elif args.loop:
        trader.run_loop()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
