"""
Arena Simulator - Core Simulation Engine

The main simulation loop that:
1. Processes market data for each variant/sub-variant
2. Makes trading decisions based on variant configuration
3. Manages simulated positions
4. Tracks performance metrics
"""

import os
import uuid
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from threading import Thread, Event

from .models import (
    Variant,
    SubVariant,
    SimulatedPosition,
    SimulatedTrade,
    TradeDirection,
    TradeStatus,
    OperationMode,
)
from .db import ArenaDB
from .config_loader import load_variants, get_enabled_variants
from .ai_manager import AIManager
from .smart_sl import SmartSLManager, TrailingSLManager


logger = logging.getLogger("arena.simulator")


class ArenaSimulator:
    """
    Core Arena simulation engine.

    Runs simulations for all enabled variants and their sub-variants,
    processing real market data without executing real trades.
    """

    def __init__(
        self,
        db: Optional[ArenaDB] = None,
        ai_manager: Optional[AIManager] = None,
    ):
        """Initialize Arena Simulator."""
        self.db = db or ArenaDB()
        self.ai_manager = ai_manager or AIManager(db=self.db)

        # Set DB reference for API tracking
        self.ai_manager.set_db(self.db)

        self.smart_sl = SmartSLManager(self.ai_manager)
        self.trailing_sl = TrailingSLManager()

        # Load variants
        self.variants: List[Variant] = []
        self._load_variants()

        # Runtime state
        self._running = False
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

        # Simulation settings
        self.loop_interval = int(os.environ.get("ARENA_LOOP_INTERVAL", 60))  # seconds
        self.fast_loop_interval = int(os.environ.get("ARENA_FAST_LOOP_INTERVAL", 5))

        # Price cache
        self._price_cache: Dict[str, Tuple[float, datetime]] = {}
        self._price_cache_ttl = 5  # seconds

        # Last AI check times (for AI_INDEPENDENT mode)
        self._last_ai_check: Dict[str, datetime] = {}

        # Equity snapshot settings
        self.snapshot_interval = int(os.environ.get("ARENA_SNAPSHOT_INTERVAL", 300))  # 5 min default
        self._last_snapshot_time = datetime.min
        self.starting_capital = float(os.environ.get("ARENA_STARTING_CAPITAL", 100))

    def _load_variants(self) -> None:
        """Load variants from database."""
        self.variants = load_variants(self.db)
        logger.info(f"Loaded {len(self.variants)} variants")

        for v in self.variants:
            logger.info(f"  - {v.id}: {v.name} ({len(v.sub_variants)} sub-variants)")

    def reload_variants(self) -> None:
        """Reload variants from database."""
        self._load_variants()

    def start(self, blocking: bool = False) -> None:
        """
        Start the simulation loop.

        Args:
            blocking: If True, run in current thread. If False, run in background.
        """
        if self._running:
            logger.warning("Simulator already running")
            return

        self._running = True
        self._stop_event.clear()

        logger.info("Starting Arena Simulator...")

        if blocking:
            self._run_loop()
        else:
            self._thread = Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the simulation loop."""
        if not self._running:
            return

        logger.info("Stopping Arena Simulator...")
        self._stop_event.set()
        self._running = False

        if self._thread:
            self._thread.join(timeout=10)

    def _run_loop(self) -> None:
        """Main simulation loop."""
        logger.info("Arena simulation loop started")

        last_slow_loop = datetime.min
        slow_loop_interval = timedelta(seconds=self.loop_interval)

        while not self._stop_event.is_set():
            try:
                # Check if simulation is paused via dashboard
                try:
                    from .dashboard import is_simulation_paused
                    if is_simulation_paused():
                        logger.debug("Simulation paused via dashboard")
                        self._stop_event.wait(self.fast_loop_interval)
                        continue
                except ImportError:
                    pass  # Dashboard not running

                now = datetime.now()

                # Fast loop - check open positions
                self._fast_loop()

                # Slow loop - check for new entries
                if now - last_slow_loop >= slow_loop_interval:
                    self._slow_loop()
                    last_slow_loop = now

                # Equity snapshots - record every snapshot_interval
                snapshot_interval_td = timedelta(seconds=self.snapshot_interval)
                if now - self._last_snapshot_time >= snapshot_interval_td:
                    self._record_equity_snapshots()
                    self._last_snapshot_time = now

                # Sleep until next fast loop
                self._stop_event.wait(self.fast_loop_interval)

            except Exception as e:
                logger.error(f"Simulation loop error: {e}", exc_info=True)
                time.sleep(5)

        logger.info("Arena simulation loop stopped")

    def _fast_loop(self) -> None:
        """
        Fast loop - runs every few seconds.
        - Updates position P&L
        - Checks SL/TP hits
        - Applies trailing stops
        - Checks Smart SL
        """
        # Get all open positions
        positions = self.db.get_all_open_positions()

        if not positions:
            return

        # Group by symbol for efficient price fetching
        symbols = set(p.symbol for p in positions)
        prices = self._get_prices(list(symbols))

        for position in positions:
            try:
                price = prices.get(position.symbol)
                if not price:
                    continue

                self._process_position(position, price)

            except Exception as e:
                logger.error(f"Error processing position {position.id}: {e}")

    def _slow_loop(self) -> None:
        """
        Slow loop - runs every loop_interval seconds.
        - Evaluates entry signals for each variant
        - AI Independent mode checks
        """
        # Get enabled variants (check DB for real-time toggle)
        enabled_variants = []
        for v in self.variants:
            v_db = self.db.get_variant(v.id)
            if v_db and v_db.enabled:
                enabled_variants.append(v)

        if not enabled_variants:
            return

        # Get market data for all symbols
        all_symbols = set()
        for v in enabled_variants:
            all_symbols.update(v.symbols)

        market_data = self._get_market_data(list(all_symbols))

        for variant in enabled_variants:
            for sub_variant in variant.sub_variants:
                try:
                    # Check if sub-variant is enabled (reload from DB for real-time toggle)
                    sv_db = self.db.get_sub_variant(sub_variant.id)
                    if sv_db and not sv_db.enabled:
                        logger.debug(f"Skipping disabled sub-variant: {sub_variant.id}")
                        continue

                    self._process_variant(variant, sub_variant, market_data)
                except Exception as e:
                    logger.error(f"Error processing {sub_variant.id}: {e}")

    def _process_position(self, position: SimulatedPosition, current_price: float) -> None:
        """Process an open position - check SL/TP, trailing, Smart SL."""
        # Update P&L
        position.update_pnl(current_price)

        # Save updated position to DB (for dashboard to show current price/P&L)
        self.db.save_position(position)

        # Get variant for this position
        sub_variant = self.db.get_sub_variant(position.sub_variant_id)
        if not sub_variant:
            return

        variant = self.db.get_variant(sub_variant.variant_id)
        if not variant:
            return

        # Check TP hit
        if position.check_tp_hit():
            self._close_position(position, variant, TradeStatus.CLOSED_TP)
            return

        # Check SL hit
        if position.check_sl_hit():
            # Before closing, check Smart SL
            if variant.trading_params.smart_sl_enabled:
                market_data = self._get_market_data([position.symbol])
                was_extended, new_sl, reason = self.smart_sl.check_and_extend_sl(
                    variant, sub_variant, position, current_price,
                    market_data.get(position.symbol, {}),
                )

                if was_extended:
                    position.stop_loss_price = new_sl
                    position.smart_sl_extensions += 1
                    self.db.save_position(position)
                    logger.info(f"[ARENA] {position.symbol} Smart SL extended: ${new_sl:.2f}")
                    return

            # Close on SL
            status = TradeStatus.CLOSED_SMART_SL if position.smart_sl_extensions > 0 else TradeStatus.CLOSED_SL
            self._close_position(position, variant, status)
            return

        # Apply trailing stop
        was_updated, new_sl, new_level = self.trailing_sl.apply_trailing(
            position, variant.trading_params.to_dict(), current_price
        )

        if was_updated:
            position.stop_loss_price = new_sl
            position.current_sl_level = new_level
            self.db.save_position(position)
            logger.info(f"[ARENA] {position.symbol} Trailing SL: ${new_sl:.2f} (level: +{new_level:.1f}%)")

    def _process_variant(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        market_data: Dict[str, Dict],
    ) -> None:
        """Process a variant/sub-variant for potential entries."""

        for symbol in variant.symbols:
            data = market_data.get(symbol)
            if not data:
                continue

            # Check if already has position
            existing = self.db.get_position_by_symbol(sub_variant.id, symbol)

            if variant.operation_mode == OperationMode.AI_INDEPENDENT:
                # AI Independent mode - let AI decide everything
                self._process_ai_independent(variant, sub_variant, symbol, data, existing)
            else:
                # Score-triggered mode
                if not existing:
                    self._process_score_triggered(variant, sub_variant, symbol, data)

    def _process_score_triggered(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        market_data: Dict[str, Any],
    ) -> None:
        """Process score-triggered entry logic."""
        # Calculate score using variant's indicator config
        score_data = self._calculate_score(market_data, variant.indicator_config)

        net_score = score_data.get("net_score", 0)
        threshold = variant.trading_params.score_threshold_open

        if abs(net_score) < threshold:
            return  # Score not high enough

        # Determine direction from score
        direction = TradeDirection.LONG if net_score > 0 else TradeDirection.SHORT

        # Double check with AI if enabled
        if variant.trading_params.double_check_ai_enabled:
            approved, override_dir, reason, confidence = self.ai_manager.validate_trade(
                variant, sub_variant, symbol, direction, market_data, score_data
            )

            if not approved:
                logger.debug(f"[ARENA] {sub_variant.id} {symbol}: AI rejected - {reason}")
                return

            if override_dir:
                logger.info(f"[ARENA] {sub_variant.id} {symbol}: AI override {direction.value} -> {override_dir.value}")
                direction = override_dir

        # Open position
        self._open_position(
            variant, sub_variant, symbol, direction,
            market_data.get("price", 0),
            score_data.get("net_score", 0),
            "score_triggered",
        )

    def _process_ai_independent(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        market_data: Dict[str, Any],
        existing_position: Optional[SimulatedPosition],
    ) -> None:
        """Process AI Independent mode."""
        # Check interval
        check_key = f"{sub_variant.id}_{symbol}"
        last_check = self._last_ai_check.get(check_key, datetime.min)
        interval = timedelta(minutes=variant.ai_check_interval_minutes)

        if datetime.now() - last_check < interval:
            return

        self._last_ai_check[check_key] = datetime.now()

        # Get AI decision
        has_position = existing_position is not None
        current_direction = existing_position.direction if existing_position else None

        action, direction, reason, confidence = self.ai_manager.get_independent_decision(
            variant, sub_variant, symbol, market_data, has_position, current_direction
        )

        logger.info(f"[ARENA] {sub_variant.id} {symbol}: AI decision = {action} ({reason[:50]})")

        if action == "open" and direction and not has_position:
            self._open_position(
                variant, sub_variant, symbol, direction,
                market_data.get("price", 0),
                0.0,  # No score in AI Independent mode
                "ai_independent",
            )
        elif action == "close" and has_position:
            self._close_position(existing_position, variant, TradeStatus.CLOSED_AI)

    def _open_position(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        direction: TradeDirection,
        price: float,
        score: float,
        reason: str,
    ) -> None:
        """Open a new simulated position."""
        params = variant.trading_params

        # Calculate SL/TP prices
        if direction == TradeDirection.LONG:
            sl_price = price * (1 - params.stop_loss_pct / 100 / params.leverage)
            tp_price = price * (1 + params.take_profit_pct / 100 / params.leverage)
        else:
            sl_price = price * (1 + params.stop_loss_pct / 100 / params.leverage)
            tp_price = price * (1 - params.take_profit_pct / 100 / params.leverage)

        position = SimulatedPosition(
            id=str(uuid.uuid4()),
            sub_variant_id=sub_variant.id,
            symbol=symbol,
            direction=direction,
            entry_price=price,
            entry_time=datetime.now(),
            position_size_usd=params.position_size_usd,
            leverage=params.leverage,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            current_sl_level=0.0,
            original_sl_price=sl_price,
            entry_score=score,
            entry_reason=reason,
        )

        self.db.save_position(position)

        logger.info(
            f"[ARENA] OPEN {sub_variant.id} {symbol} {direction.value} @ ${price:.2f} "
            f"(SL: ${sl_price:.2f}, TP: ${tp_price:.2f})"
        )

    def _close_position(
        self,
        position: SimulatedPosition,
        variant: Variant,
        status: TradeStatus,
    ) -> None:
        """Close a simulated position."""
        # Create trade record
        trade = SimulatedTrade.from_position(position, variant.id)
        trade.close(position.current_price, status)
        trade.ai_model = self.db.get_sub_variant(position.sub_variant_id).ai_model

        # Save trade
        self.db.save_trade(trade)

        # Update sub-variant stats
        self.db.update_sub_variant_stats(position.sub_variant_id, trade)

        # Delete position
        self.db.delete_position(position.id)

        # Clear Smart SL history
        self.smart_sl.clear_history(position.id)

        emoji = "✅" if trade.is_winner else "❌"
        logger.info(
            f"[ARENA] {emoji} CLOSE {position.sub_variant_id} {position.symbol} "
            f"P&L: {trade.pnl_pct:+.2f}% (${trade.pnl_usd:+.2f}) - {status.value}"
        )

    def _calculate_score(
        self,
        market_data: Dict[str, Any],
        indicator_config: Any,
    ) -> Dict[str, Any]:
        """Calculate trading score based on indicators."""
        # Simplified score calculation for simulation
        # In production, this would use the full signal_scorer logic

        score_bull = 0.0
        score_bear = 0.0

        # MACD
        macd = market_data.get("macd", 0)
        weight_macd = indicator_config.weight_macd if hasattr(indicator_config, 'weight_macd') else 25.0
        if macd > 0.15:
            score_bull += weight_macd * min(macd / 0.30, 1.0)
        elif macd < -0.15:
            score_bear += weight_macd * min(abs(macd) / 0.30, 1.0)

        # RSI
        rsi = market_data.get("rsi", 50)
        weight_rsi = indicator_config.weight_rsi if hasattr(indicator_config, 'weight_rsi') else 15.0
        if rsi < 30:
            score_bull += weight_rsi * (30 - rsi) / 30
        elif rsi > 70:
            score_bear += weight_rsi * (rsi - 70) / 30

        # EMA trend
        ema_trend = market_data.get("ema_trend", "neutral")
        weight_ema = indicator_config.weight_ema_alignment if hasattr(indicator_config, 'weight_ema_alignment') else 20.0
        if ema_trend == "bullish":
            score_bull += weight_ema
        elif ema_trend == "bearish":
            score_bear += weight_ema

        # ADX
        adx = market_data.get("adx", 0)
        weight_adx = indicator_config.weight_adx_trend if hasattr(indicator_config, 'weight_adx_trend') else 15.0
        if adx > 25:
            # Strong trend - amplify existing signal
            if score_bull > score_bear:
                score_bull += weight_adx * 0.5
            else:
                score_bear += weight_adx * 0.5

        # Patterns
        if market_data.get("double_bottom"):
            weight_db = indicator_config.weight_double_bottom if hasattr(indicator_config, 'weight_double_bottom') else 12.0
            conf = market_data.get("double_bottom_conf", 0.7)
            score_bull += weight_db * conf

        if market_data.get("double_top"):
            weight_dt = indicator_config.weight_double_top if hasattr(indicator_config, 'weight_double_top') else 12.0
            conf = market_data.get("double_top_conf", 0.7)
            score_bear += weight_dt * conf

        return {
            "score_bull": score_bull,
            "score_bear": score_bear,
            "net_score": score_bull - score_bear,
        }

    def _get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices for symbols."""
        # This would connect to HyperLiquid API in production
        # For now, we'll use a placeholder that the integration will provide

        try:
            # Try to import from existing system
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

            from hyperliquid.info import Info
            from hyperliquid.utils import constants

            info = Info(constants.MAINNET_API_URL)
            all_mids = info.all_mids()

            prices = {}
            for symbol in symbols:
                if symbol in all_mids:
                    prices[symbol] = float(all_mids[symbol])

            return prices

        except Exception as e:
            logger.warning(f"Could not get prices: {e}")
            return {}

    def _get_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get full market data for symbols using CryptoTechnicalAnalysisHL."""
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

            from indicators import CryptoTechnicalAnalysisHL

            # Use mainnet for real prices
            analyzer = CryptoTechnicalAnalysisHL(testnet=False)

            market_data = {}
            for symbol in symbols:
                try:
                    # Get complete analysis from indicators module
                    analysis = analyzer.get_complete_analysis(symbol)
                    current = analysis.get("current", {})

                    # Determine EMA trend
                    ema_trend = "neutral"
                    ema_alignment = analysis.get("ema_alignment", "NEUTRAL")
                    if ema_alignment == "GOLDEN_CROSS":
                        ema_trend = "bullish"
                    elif ema_alignment == "DEATH_CROSS":
                        ema_trend = "bearish"

                    market_data[symbol] = {
                        "price": current.get("price", 0),
                        "macd": current.get("macd", 0),
                        "rsi": current.get("rsi_14", 50),
                        "adx": current.get("adx", 0),
                        "ema20": current.get("ema20", 0),
                        "ema50": current.get("ema50", 0),
                        "ema_trend": ema_trend,
                        "funding_rate": analysis.get("derivatives", {}).get("funding_rate", 0),
                        "open_interest": analysis.get("derivatives", {}).get("open_interest_latest", 0),
                        # Bollinger
                        "bb_position": analysis.get("bollinger", {}).get("position", "MIDDLE"),
                        "bb_squeeze": analysis.get("bollinger", {}).get("squeeze", False),
                        # OBV
                        "obv_trend": analysis.get("obv", {}).get("trend", "neutral"),
                        # Pattern detection (placeholder)
                        "double_bottom": False,
                        "double_bottom_conf": 0,
                        "double_top": False,
                        "double_top_conf": 0,
                    }

                except Exception as e:
                    logger.warning(f"Could not get data for {symbol}: {e}")
                    market_data[symbol] = {"price": 0}

            return market_data

        except Exception as e:
            logger.warning(f"Could not get market data: {e}")
            return {}

    # ==================== Status Methods ====================

    def get_status(self) -> Dict[str, Any]:
        """Get simulator status."""
        positions = self.db.get_all_open_positions()

        return {
            "running": self._running,
            "variants_loaded": len(self.variants),
            "variants_enabled": len([v for v in self.variants if v.enabled]),
            "open_positions": len(positions),
            "loop_interval": self.loop_interval,
            "fast_loop_interval": self.fast_loop_interval,
        }

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all open positions."""
        positions = self.db.get_all_open_positions()

        return [
            {
                "id": p.id,
                "sub_variant": p.sub_variant_id,
                "symbol": p.symbol,
                "direction": p.direction.value,
                "entry_price": p.entry_price,
                "current_pnl_pct": p.current_pnl_pct,
                "current_pnl_usd": p.current_pnl_usd,
            }
            for p in positions
        ]

    def _record_equity_snapshots(self) -> None:
        """Record equity snapshots for all sub-variants."""
        try:
            # Get all sub-variants from all variants
            for variant in self.variants:
                for sub_variant in variant.sub_variants:
                    try:
                        # Get realized P&L from closed trades
                        sv_db = self.db.get_sub_variant(sub_variant.id)
                        realized_pnl = sv_db.total_pnl_usd if sv_db else 0.0

                        # Get unrealized P&L from open positions
                        positions = self.db.get_positions_for_sub_variant(sub_variant.id)
                        unrealized_pnl = sum(p.current_pnl_usd for p in positions)
                        open_positions = len(positions)

                        # Save snapshot
                        self.db.save_equity_snapshot(
                            sub_variant_id=sub_variant.id,
                            realized_pnl_usd=realized_pnl,
                            unrealized_pnl_usd=unrealized_pnl,
                            open_positions=open_positions,
                            starting_capital=self.starting_capital,
                        )

                    except Exception as e:
                        logger.warning(f"Error recording snapshot for {sub_variant.id}: {e}")

            logger.debug("Equity snapshots recorded")

            # Cleanup old snapshots periodically (every 24h worth of snapshots)
            # 288 snapshots per day at 5-min intervals
            if hasattr(self, '_snapshot_count'):
                self._snapshot_count += 1
                if self._snapshot_count >= 288:
                    deleted = self.db.cleanup_old_snapshots(days=7)
                    if deleted > 0:
                        logger.info(f"Cleaned up {deleted} old equity snapshots")
                    self._snapshot_count = 0
            else:
                self._snapshot_count = 0

        except Exception as e:
            logger.error(f"Error recording equity snapshots: {e}")
