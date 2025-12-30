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

# Import database module for logging
try:
    from . import db as alpha_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    alpha_db = None

# Import HyperLiquidTrader SEPARATELY (required for live trading)
HyperLiquidTrader = None
try:
    from hyperliquid_trader import HyperLiquidTrader
    logging.info("HyperLiquidTrader imported successfully")
except ImportError as e:
    logging.warning(f"HyperLiquidTrader not available: {e}")
    HyperLiquidTrader = None

# Import shared modules from parent OR use standalone
try:
    from indicators import get_hyperliquid_indicators
    from forecaster import get_crypto_forecasts
    from sentiment import get_fear_greed_index
    from signal_scorer import calculate_signal_score, calculate_smart_score_v2
    MODULES_AVAILABLE = True
except ImportError as e:
    logging.info(f"Shared modules not found, using standalone indicators: {e}")
    # Use standalone indicators from alpha module
    try:
        from .indicators_standalone import get_hyperliquid_indicators, get_fear_greed_index
        # Create dummy functions for missing modules
        def get_crypto_forecasts(*args, **kwargs): return []
        def calculate_signal_score(*args, **kwargs): return {'bull': 0, 'bear': 0, 'net': 0}
        def calculate_smart_score_v2(*args, **kwargs): return {'bull': 0, 'bear': 0, 'net': 0}
        MODULES_AVAILABLE = True
        logging.info("Standalone indicators loaded successfully")
    except ImportError as e2:
        logging.warning(f"Could not import standalone modules: {e2}")
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
    stop_loss_price: float = 0.0  # Stop loss trigger price
    sl_order_id: Optional[int] = None  # HyperLiquid SL order ID
    size_coins: float = 0.0  # Position size in coins (for SL order)
    trade_id: Optional[int] = None  # Database trade ID
    decision_id: Optional[int] = None  # Database decision ID


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
        self.exchange = None
        if not self.config.trading.paper_trading:
            if HyperLiquidTrader is None:
                raise RuntimeError(
                    "LIVE mode requires HyperLiquidTrader but it failed to import! "
                    "Check that hyperliquid-python-sdk and eth-account are installed."
                )
            logger.info("Connecting to HyperLiquid...")
            self.exchange = HyperLiquidTrader(
                secret_key=self.config.hl_private_key,
                account_address=self.config.hl_account_address,
                testnet=self.config.hl_testnet,
            )
            logger.info("✅ Connected to HyperLiquid LIVE!")

        # State
        self.positions: Dict[str, AlphaPosition] = {}
        self.last_decision_time: Optional[datetime] = None
        self.total_trades = 0
        self.winning_trades = 0

        # Cooldown tracking: {symbol: last_close_time}
        self.cooldowns: Dict[str, datetime] = {}

        # Sync positions from exchange at startup (LIVE mode only)
        if self.exchange and not self.config.trading.paper_trading:
            self._sync_positions_from_exchange()

    def _sync_positions_from_exchange(self):
        """Sync open positions from HyperLiquid at startup."""
        try:
            status = self.exchange.get_account_status()
            open_positions = status.get("open_positions", [])

            for pos in open_positions:
                symbol = pos.get("symbol", "")
                if symbol not in self.config.trading.symbols:
                    continue

                direction = "LONG" if pos.get("side") == "long" else "SHORT"
                entry_price = pos.get("entry_price", 0)
                size = pos.get("size", 0)

                # Create position tracking object
                self.positions[symbol] = AlphaPosition(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    size_usd=size * entry_price,
                    leverage=5,  # Default, we don't have exact leverage info
                    opened_at=datetime.now(),  # Approximate
                    current_price=pos.get("mark_price", entry_price),
                )
                print(f"📍 Synced existing position: {direction} {symbol} @ ${entry_price:.4f}", flush=True)

            if open_positions:
                print(f"✅ Synced {len(self.positions)} existing positions from HyperLiquid", flush=True)
            else:
                print("✅ No existing positions on HyperLiquid", flush=True)

        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")
            print(f"⚠️ Could not sync positions from exchange: {e}", flush=True)

    def _sync_and_cleanup_positions(self):
        """Check if local positions still exist on exchange, remove if not."""
        try:
            # Get actual positions from exchange
            status = self.exchange.get_account_status()
            exchange_positions = {pos.get("symbol"): pos for pos in status.get("open_positions", [])}

            # Check each local position
            for symbol in list(self.positions.keys()):
                if symbol not in exchange_positions:
                    pos = self.positions[symbol]
                    print(f"🔄 Position {symbol} no longer on exchange - cleaning up", flush=True)

                    # Close in database if needed
                    if DB_AVAILABLE and alpha_db and pos.trade_id:
                        # Try to get a reasonable exit price
                        data = self.fetch_market_data([symbol])
                        exit_price = data.get('indicators', {}).get(symbol, {}).get('price', pos.current_price)

                        alpha_db.close_trade(
                            trade_id=pos.trade_id,
                            exit_price=exit_price,
                            exit_reason="MANUAL_CLOSE"
                        )
                        print(f"💾 Trade #{pos.trade_id} marked as MANUAL_CLOSE", flush=True)

                    # Remove from local tracking
                    del self.positions[symbol]
                    # Set cooldown
                    self.cooldowns[symbol] = datetime.now()

            # Also check for positions on exchange that we don't know about
            for symbol, pos_data in exchange_positions.items():
                if symbol in self.config.trading.symbols and symbol not in self.positions:
                    print(f"⚠️ Found untracked position on exchange: {symbol}", flush=True)
                    # Optionally add it to local tracking
                    # For now just warn - don't auto-add as we don't have decision context

        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            print(f"⚠️ Position sync error: {e}", flush=True)

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

    def _save_decision_to_db(self, symbol: str, data: Dict, decision_info: Dict) -> Optional[int]:
        """Save decision to PostgreSQL database."""
        if not DB_AVAILABLE or not alpha_db:
            return None

        try:
            indicators = data.get('indicators', {}).get(symbol, {})
            sentiment = data.get('sentiment', {})

            decision_id = alpha_db.save_decision(
                symbol=symbol,
                policy_action=decision_info.get('policy_action', 'UNKNOWN'),
                final_action=decision_info.get('final_action', 'UNKNOWN'),
                policy_confidence=decision_info.get('policy_confidence', 0),
                value_estimate=decision_info.get('value_estimate', 0),
                win_probability=decision_info.get('win_probability', 0),
                mcts_approved=decision_info.get('mcts_approved'),
                mcts_win_prob=decision_info.get('mcts_win_prob'),
                mcts_reason=decision_info.get('mcts_reason'),
                price=indicators.get('price', 0),
                rsi=indicators.get('rsi_14', 50),
                macd=indicators.get('macd', 0),
                adx=indicators.get('adx', 25),
                fear_greed=sentiment.get('value', 50),
                market_data=data,
                decision_info=decision_info
            )
            return decision_id
        except Exception as e:
            logger.error(f"Error saving decision to DB: {e}")
            return None

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
        self._last_market_data = {}  # Store for DB save

        # 1. Fetch market data
        logger.info(f"Fetching market data for {symbol}...")
        data = self.fetch_market_data([symbol])
        self._last_market_data = data  # Store for DB save
        decision_info['market_data'] = bool(data.get('indicators'))

        if symbol not in data.get('indicators', {}):
            logger.warning(f"No indicator data for {symbol}")
            decision_info['final_action'] = 'HOLD (no data)'
            self._save_decision_to_db(symbol, data, decision_info)
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

        # 3.5. Filter CLOSE when no position exists
        if action.action_type == ActionType.CLOSE and symbol not in self.positions:
            print(f"[FILTER] CLOSE ignored: no position in {symbol}", flush=True)
            action = Action(ActionType.HOLD, symbol, confidence=0.0)
            decision_info['final_action'] = 'HOLD (no position)'
            decision_info['steps'].append("Filtered: CLOSE without position → HOLD")
            self._save_decision_to_db(symbol, data, decision_info)
            return action, decision_info

        # 3.6. Filter CLOSE if position not held long enough (min_hold_minutes)
        if action.action_type == ActionType.CLOSE and symbol in self.positions:
            pos = self.positions[symbol]
            min_hold = timedelta(minutes=self.config.trading.min_hold_minutes)
            time_held = datetime.now() - pos.opened_at
            if time_held < min_hold:
                minutes_left = (min_hold - time_held).total_seconds() / 60
                print(f"[FILTER] CLOSE ignored: {symbol} held {time_held.total_seconds()/60:.1f}min < {self.config.trading.min_hold_minutes}min (wait {minutes_left:.1f}min)", flush=True)
                action = Action(ActionType.HOLD, symbol, confidence=0.0)
                decision_info['final_action'] = f'HOLD (min hold: {minutes_left:.1f}min left)'
                decision_info['steps'].append(f"Filtered: CLOSE before min_hold ({self.config.trading.min_hold_minutes}min) → HOLD")
                self._save_decision_to_db(symbol, data, decision_info)
                return action, decision_info

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
                self._save_decision_to_db(symbol, data, decision_info)
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
                self._save_decision_to_db(symbol, data, decision_info)
                return action, decision_info

        decision_info['final_action'] = action.action_type.name

        # Save decision to database and store ID for trade linking
        decision_id = self._save_decision_to_db(symbol, data, decision_info)
        decision_info['decision_id'] = decision_id

        return action, decision_info

    def execute_action(self, action: Action, decision_info: Optional[Dict] = None) -> bool:
        """
        Execute a trading action.

        Returns:
            True if executed successfully
        """
        if action.action_type == ActionType.HOLD:
            logger.info(f"HOLD {action.symbol} - no action needed")
            return True

        if self.config.trading.paper_trading:
            return self._execute_paper(action, decision_info)
        else:
            return self._execute_live(action, decision_info)

    def _execute_paper(self, action: Action, decision_info: Optional[Dict] = None) -> bool:
        """Execute paper trade (simulated)."""
        symbol = action.symbol

        if action.action_type == ActionType.CLOSE:
            if symbol in self.positions:
                pos = self.positions[symbol]
                print(
                    f"[PAPER] CLOSE {symbol} {pos.direction} | "
                    f"P&L: {pos.unrealized_pnl_pct:.2f}%", flush=True
                )

                # Save trade close to database
                if DB_AVAILABLE and alpha_db and pos.trade_id:
                    alpha_db.close_trade(
                        trade_id=pos.trade_id,
                        exit_price=pos.current_price,
                        exit_reason="AI_CLOSE"
                    )

                if pos.unrealized_pnl_pct > 0:
                    self.winning_trades += 1
                self.total_trades += 1
                del self.positions[symbol]
                return True
            else:
                print(f"[EXECUTE] ❌ CLOSE failed: No position in {symbol}", flush=True)
            return False

        elif action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            if symbol in self.positions:
                print(f"[EXECUTE] ❌ Already have position in {symbol}", flush=True)
                return False

            direction = "LONG" if action.action_type == ActionType.OPEN_LONG else "SHORT"
            position_size = self.config.trading.base_position_usd * action.position_size_pct

            # Get current price (need to fetch)
            data = self.fetch_market_data([symbol])
            indicators = data.get('indicators', {}).get(symbol, {})
            price = indicators.get('price', 0)

            print(f"[EXECUTE] Fetched price for {symbol}: ${price}", flush=True)

            if price == 0:
                print(f"[EXECUTE] ❌ Could not get price! Data keys: {data.get('indicators', {}).keys()}", flush=True)
                return False

            # Get decision ID for linking
            decision_id = decision_info.get('decision_id') if decision_info else None
            mcts_win_prob = decision_info.get('mcts_win_prob') if decision_info else None

            # Save trade to database
            trade_id = None
            if DB_AVAILABLE and alpha_db:
                trade_id = alpha_db.save_trade_open(
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    size_usd=position_size,
                    leverage=action.leverage,
                    decision_id=decision_id,
                    policy_confidence=action.confidence,
                    mcts_win_prob=mcts_win_prob,
                    is_paper=True
                )

            self.positions[symbol] = AlphaPosition(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                size_usd=position_size,
                leverage=action.leverage,
                opened_at=datetime.utcnow(),
                current_price=price,
                trade_id=trade_id,
                decision_id=decision_id,
            )

            logger.info(
                f"[PAPER] OPEN {direction} {symbol} | "
                f"Size: ${position_size:.0f} | Leverage: {action.leverage}x | "
                f"Entry: ${price:,.2f} | DB: #{trade_id}"
            )
            return True

        return False

    def _execute_live(self, action: Action, decision_info: Optional[Dict] = None) -> bool:
        """Execute live trade on exchange."""
        if not self.exchange:
            logger.error("Exchange not connected")
            return False

        symbol = action.symbol

        if action.action_type == ActionType.CLOSE:
            # Get position info before closing (for DB and SL cancellation)
            pos = self.positions.get(symbol)
            trade_id = pos.trade_id if pos else None
            sl_order_id = pos.sl_order_id if pos else None

            # Cancel SL order first (if exists)
            if sl_order_id and self.exchange:
                print(f"🗑️ Cancelling SL order {sl_order_id} for {symbol}...", flush=True)
                cancel_result = self.exchange.cancel_order(symbol, sl_order_id)
                if cancel_result.get('status') == 'ok':
                    print(f"✅ SL order cancelled", flush=True)
                else:
                    print(f"⚠️ SL cancel result: {cancel_result}", flush=True)

            result = self.exchange.execute_signal({
                'operation': 'close',
                'symbol': symbol,
                'direction': 'long',  # Will close whatever is open
                'reason': 'AlphaTrader decision',
            })
            # Check for success - API returns 'status': 'ok' not 'success'
            success = result.get('status') == 'ok' or result.get('success', False)
            if success:
                print(f"✅ Position closed: {symbol}", flush=True)

                # Get exit price for DB
                exit_price = self._get_entry_price_from_result(result, symbol) or (pos.current_price if pos else 0)

                # Get exit reason from action reasoning or default
                exit_reason = getattr(action, 'reasoning', None) or 'AI_CLOSE'

                # Save to database
                if DB_AVAILABLE and alpha_db and trade_id:
                    alpha_db.close_trade(
                        trade_id=trade_id,
                        exit_price=exit_price,
                        exit_reason=exit_reason
                    )
                    print(f"💾 Trade #{trade_id} saved to DB: {exit_reason}", flush=True)

                if symbol in self.positions:
                    del self.positions[symbol]
                # Set cooldown for this symbol
                self.cooldowns[symbol] = datetime.now()
                print(f"⏱️ Cooldown set for {symbol} ({self.config.trading.trade_cooldown_minutes}min)", flush=True)
                return True
            else:
                print(f"❌ Failed to close: {result}", flush=True)
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

            # Check for success - API returns 'status': 'ok' not 'success'
            success = result.get('status') == 'ok' or result.get('success', False)
            if success:
                print(f"✅ Position opened: {direction.upper()} {symbol}", flush=True)

                # Get entry price from result or fetch current price
                entry_price = self._get_entry_price_from_result(result, symbol)

                # Get size in coins from result or fetch from exchange
                size_coins = self._get_size_coins_from_result(result)
                if size_coins == 0:
                    # Fallback: fetch from exchange after a short delay
                    import time
                    time.sleep(0.5)
                    size_coins = self._get_position_size_from_exchange(symbol)
                print(f"📊 Position size: {size_coins} {symbol}", flush=True)

                # Get decision ID for linking
                decision_id = decision_info.get('decision_id') if decision_info else None
                mcts_win_prob = decision_info.get('mcts_win_prob') if decision_info else None

                # Save trade to database (LIVE)
                trade_id = None
                if DB_AVAILABLE and alpha_db:
                    trade_id = alpha_db.save_trade_open(
                        symbol=symbol,
                        direction=direction.upper(),
                        entry_price=entry_price,
                        size_usd=self.config.trading.base_position_usd,
                        leverage=action.leverage,
                        decision_id=decision_id,
                        policy_confidence=action.confidence,
                        mcts_win_prob=mcts_win_prob,
                        is_paper=False  # LIVE trade!
                    )
                    print(f"💾 Trade #{trade_id} saved to DB (LIVE)", flush=True)

                # Track position locally
                self.positions[symbol] = AlphaPosition(
                    symbol=symbol,
                    direction=direction.upper(),
                    entry_price=entry_price,
                    size_usd=self.config.trading.base_position_usd,
                    leverage=action.leverage,
                    opened_at=datetime.now(),
                    current_price=entry_price,
                    size_coins=size_coins,  # Store size in coins for SL order
                    trade_id=trade_id,
                    decision_id=decision_id,
                )

                # Set Stop Loss on exchange
                self._set_stop_loss(symbol, direction, entry_price, action.leverage)

            else:
                print(f"❌ Failed to open: {result}", flush=True)
            return success

        return False

    def _get_entry_price_from_result(self, result: Dict, symbol: str) -> float:
        """Extract entry price from order result or fetch current price."""
        try:
            # Try to get from result
            response = result.get('response', {})
            if isinstance(response, dict):
                data = response.get('data', {})
                statuses = data.get('statuses', [])
                if statuses and isinstance(statuses[0], dict):
                    filled = statuses[0].get('filled', {})
                    if filled:
                        return float(filled.get('avgPx', 0))

            # Fallback: fetch current price
            data = self.fetch_market_data([symbol])
            return data.get('indicators', {}).get(symbol, {}).get('price', 0)
        except Exception as e:
            logger.error(f"Error getting entry price: {e}")
            return 0

    def _get_size_coins_from_result(self, result: Dict) -> float:
        """Extract filled size in coins from order result."""
        try:
            response = result.get('response', {})
            if isinstance(response, dict):
                data = response.get('data', {})
                statuses = data.get('statuses', [])
                if statuses and isinstance(statuses[0], dict):
                    filled = statuses[0].get('filled', {})
                    if filled:
                        return float(filled.get('totalSz', 0))
            return 0
        except Exception as e:
            logger.error(f"Error getting size from result: {e}")
            return 0

    def _get_position_size_from_exchange(self, symbol: str) -> float:
        """Get current position size in coins from exchange."""
        try:
            if not self.exchange:
                return 0
            status = self.exchange.get_account_status()
            for pos in status.get("open_positions", []):
                if pos.get("symbol") == symbol:
                    return abs(pos.get("size", 0))
            return 0
        except Exception as e:
            logger.error(f"Error getting position size: {e}")
            return 0

    def _set_stop_loss(self, symbol: str, direction: str, entry_price: float, leverage: int):
        """Set stop loss order on HyperLiquid (native exchange order)."""
        try:
            sl_pct = self.config.trading.stop_loss_pct

            # Calculate SL price based on direction
            if direction == "long":
                sl_price = entry_price * (1 - sl_pct / 100)
            else:
                sl_price = entry_price * (1 + sl_pct / 100)

            print(f"🛡️ Setting Stop Loss for {symbol}: {sl_pct}% -> ${sl_price:.4f}", flush=True)

            # Store SL price locally for tracking
            if symbol in self.positions:
                self.positions[symbol].stop_loss_price = sl_price

            # Place REAL SL order on HyperLiquid (LIVE mode only)
            if self.exchange and not self.config.trading.paper_trading:
                pos = self.positions.get(symbol)
                if pos and pos.size_coins > 0:
                    result = self.exchange.place_stop_loss(
                        symbol=symbol,
                        direction=direction,
                        size=pos.size_coins,
                        trigger_price=sl_price
                    )

                    if result.get('status') == 'ok':
                        sl_order_id = result.get('sl_order_id')
                        if sl_order_id:
                            self.positions[symbol].sl_order_id = sl_order_id
                            print(f"✅ SL order placed on exchange (ID: {sl_order_id})", flush=True)
                        else:
                            print(f"✅ SL order placed on exchange", flush=True)
                    else:
                        print(f"⚠️ SL order may have failed: {result}", flush=True)
                        # Keep local tracking as backup
                else:
                    print(f"⚠️ Cannot place SL: position size unknown", flush=True)
            else:
                # Paper trading: just track locally
                print(f"✅ Stop Loss tracked locally at ${sl_price:.4f} ({sl_pct}% from entry)", flush=True)

        except Exception as e:
            logger.error(f"Error setting stop loss: {e}")
            print(f"⚠️ Failed to set stop loss: {e}", flush=True)

    def update_positions(self):
        """Update P&L for open positions and check stop losses."""
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

                # Update MFE/MAE in database
                if DB_AVAILABLE and alpha_db and pos.trade_id:
                    alpha_db.update_trade_prices(pos.trade_id, price, pos.direction)

                logger.debug(
                    f"{symbol} {pos.direction}: P&L {pnl_pct:+.2f}% | "
                    f"MFE: {pos.max_profit_pct:.2f}% | MAE: {pos.max_loss_pct:.2f}%"
                )

                # LIVE MODE: Check if exchange SL triggered (position no longer exists)
                if self.exchange and pos.sl_order_id:
                    # Periodically verify position still exists on exchange
                    exchange_size = self._get_position_size_from_exchange(symbol)
                    if exchange_size == 0:
                        # Position was closed by exchange (SL triggered!)
                        print(f"\n🛑 SL TRIGGERED ON EXCHANGE for {symbol}!", flush=True)
                        print(f"   P&L when closed: ~{pnl_pct:+.2f}%", flush=True)

                        # Save to database
                        if DB_AVAILABLE and alpha_db and pos.trade_id:
                            alpha_db.close_trade(
                                trade_id=pos.trade_id,
                                exit_price=pos.stop_loss_price,
                                exit_reason="SL_HIT_EXCHANGE"
                            )
                            print(f"💾 Trade #{pos.trade_id} saved to DB: SL_HIT_EXCHANGE", flush=True)

                        # Remove from local tracking
                        del self.positions[symbol]
                        # Set cooldown
                        self.cooldowns[symbol] = datetime.now()
                        print(f"⏱️ Cooldown set for {symbol}", flush=True)
                        continue  # Skip rest of loop for this symbol

                # PAPER MODE: Check stop loss locally
                elif self.config.trading.paper_trading and pos.stop_loss_price > 0:
                    sl_hit = False
                    if pos.direction == "LONG" and price <= pos.stop_loss_price:
                        sl_hit = True
                    elif pos.direction == "SHORT" and price >= pos.stop_loss_price:
                        sl_hit = True

                    if sl_hit:
                        print(f"\n🛑 STOP LOSS HIT for {symbol}!", flush=True)
                        print(f"   Direction: {pos.direction}", flush=True)
                        print(f"   Entry: ${pos.entry_price:.4f}", flush=True)
                        print(f"   SL Price: ${pos.stop_loss_price:.4f}", flush=True)
                        print(f"   Current: ${price:.4f}", flush=True)
                        print(f"   P&L: {pnl_pct:+.2f}%", flush=True)

                        # Close position (paper)
                        close_action = Action(ActionType.CLOSE, symbol, confidence=1.0)
                        close_action.reasoning = f"Stop Loss hit at ${price:.4f}"
                        success = self.execute_action(close_action, {'steps': ['Stop Loss triggered']})
                        print(f"🛑 SL Close: {'SUCCESS' if success else 'FAILED'}", flush=True)

    def run_loop(self):
        """Main trading loop."""
        # Use print for immediate output (logger may buffer)
        print("=" * 60, flush=True)
        print("AlphaTrader Starting", flush=True)
        print(f"Mode: {'PAPER' if self.config.trading.paper_trading else '🔴 LIVE 🔴'}", flush=True)
        print(f"Symbols: {self.config.trading.symbols}", flush=True)
        print(f"MCTS min win prob: {self.config.mcts.min_win_probability:.0%}", flush=True)
        print(f"Min hold time: {self.config.trading.min_hold_minutes} min", flush=True)
        print(f"Max hold time: {self.config.trading.max_hold_minutes} min (force close)", flush=True)
        print(f"Stop Loss: {self.config.trading.stop_loss_pct}%", flush=True)
        print(f"Trade cooldown: {self.config.trading.trade_cooldown_minutes} min", flush=True)
        print(f"Slow loop interval: {self.config.trading.slow_loop_interval}s", flush=True)
        if DB_AVAILABLE and alpha_db:
            print(f"Database: ✅ Connected (PostgreSQL)", flush=True)
        else:
            print(f"Database: ❌ Not connected (decisions not saved)", flush=True)
        print("=" * 60, flush=True)

        slow_interval = self.config.trading.slow_loop_interval
        fast_interval = self.config.trading.fast_loop_interval
        last_slow = datetime.min

        print(f"Entering main loop... slow={slow_interval}s, fast={fast_interval}s", flush=True)
        loop_count = 0

        while True:
            try:
                loop_count += 1
                now = datetime.utcnow()

                if loop_count <= 3 or loop_count % 10 == 0:
                    print(f"[Loop {loop_count}] {now.strftime('%H:%M:%S')}", flush=True)

                # Fast loop: update positions
                self.update_positions()

                # Slow loop: make decisions
                seconds_since_last = (now - last_slow).total_seconds()
                if seconds_since_last >= slow_interval:
                    print(f"[Slow loop triggered] {seconds_since_last:.0f}s since last", flush=True)
                    last_slow = now

                    # SYNC POSITIONS: Detect manually closed positions (LIVE mode)
                    if self.exchange and not self.config.trading.paper_trading:
                        self._sync_and_cleanup_positions()

                    # CHECK MAX HOLD: Force close positions held too long
                    max_hold = self.config.trading.max_hold_minutes
                    for sym, pos in list(self.positions.items()):
                        time_held = (datetime.now() - pos.opened_at).total_seconds() / 60
                        if time_held >= max_hold:
                            print(f"\n⏰ [MAX_HOLD] {sym} held {time_held:.1f}min >= {max_hold}min - FORCE CLOSING!", flush=True)
                            # Force close this position
                            close_action = Action(ActionType.CLOSE, sym, confidence=1.0)
                            close_action.reasoning = f"Max hold time exceeded ({time_held:.1f}min >= {max_hold}min)"
                            success = self.execute_action(close_action, {'steps': ['Max hold exceeded']})
                            print(f"⏰ [MAX_HOLD] Force close {sym}: {'SUCCESS' if success else 'FAILED'}", flush=True)

                    for symbol in self.config.trading.symbols:
                        print(f"\n{'='*40}", flush=True)
                        print(f"[{now.strftime('%H:%M:%S')}] Evaluating {symbol}...", flush=True)

                        # CHECK 1: Already have position on this symbol?
                        if symbol in self.positions:
                            pos = self.positions[symbol]
                            print(f"  ⏭️ SKIP: Already have {pos.direction} position on {symbol}", flush=True)
                            continue

                        # CHECK 2: Cooldown active for this symbol?
                        if symbol in self.cooldowns:
                            cooldown_end = self.cooldowns[symbol] + timedelta(minutes=self.config.trading.trade_cooldown_minutes)
                            if now < cooldown_end:
                                remaining = (cooldown_end - now).total_seconds() / 60
                                print(f"  ⏭️ SKIP: Cooldown active for {symbol} ({remaining:.1f}min remaining)", flush=True)
                                continue
                            else:
                                # Cooldown expired, remove it
                                del self.cooldowns[symbol]

                        action, info = self.make_decision(symbol)

                        print(f"Decision: {action.action_type.name} (conf: {action.confidence:.1%})", flush=True)
                        for step in info.get('steps', []):
                            print(f"  -> {step}", flush=True)

                        if action.action_type != ActionType.HOLD:
                            success = self.execute_action(action, info)
                            print(f"Execution: {'SUCCESS' if success else 'FAILED'}", flush=True)

                        time.sleep(1)  # Small delay between symbols

                time.sleep(fast_interval)

            except KeyboardInterrupt:
                print("\nShutting down...", flush=True)
                break
            except Exception as e:
                print(f"Error in main loop: {e}", flush=True)
                import traceback
                traceback.print_exc()
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
        default=None,  # Use config default if not specified
        help='Symbols to trade (default: from config)'
    )
    args = parser.parse_args()

    # Configure
    config = get_config()
    config.trading.paper_trading = (args.mode == 'paper')
    # Only override symbols if explicitly passed on command line
    if args.symbols:
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
