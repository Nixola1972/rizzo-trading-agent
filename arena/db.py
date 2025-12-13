"""
Arena Database Operations

SQLite database for storing Arena simulation data:
- Variants and their configurations
- Sub-variants (per AI model)
- Simulated trades
- Open positions
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from .models import (
    Variant,
    SubVariant,
    SimulatedTrade,
    SimulatedPosition,
    TradeDirection,
    TradeStatus,
    OperationMode,
    TradingParams,
    IndicatorConfig,
)


# Default database path
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "arena.db")


class ArenaDB:
    """Database manager for Arena simulation system."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        self.db_path = db_path or os.environ.get("ARENA_DB_PATH", DEFAULT_DB_PATH)

        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get a database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Variants table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS arena_variants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    enabled INTEGER DEFAULT 1,
                    operation_mode TEXT DEFAULT 'SCORE_TRIGGERED',
                    trading_params TEXT,
                    indicator_config TEXT,
                    ai_models TEXT,
                    pattern_detection_enabled INTEGER DEFAULT 1,
                    pattern_timeframe TEXT DEFAULT '1h',
                    pattern_min_confidence REAL DEFAULT 0.60,
                    ai_check_interval_minutes INTEGER DEFAULT 15,
                    ai_independent_timeframe TEXT DEFAULT '4h',
                    symbols TEXT DEFAULT '["BTC","ETH","SOL"]',
                    total_trades INTEGER DEFAULT 0,
                    total_pnl_usd REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Sub-variants table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS arena_sub_variants (
                    id TEXT PRIMARY KEY,
                    variant_id TEXT NOT NULL,
                    ai_model TEXT NOT NULL,
                    ai_model_name TEXT,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl_usd REAL DEFAULT 0.0,
                    total_pnl_pct REAL DEFAULT 0.0,
                    max_drawdown_pct REAL DEFAULT 0.0,
                    sharpe_ratio REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_trade_at TIMESTAMP,
                    FOREIGN KEY (variant_id) REFERENCES arena_variants(id)
                )
            """)

            # Open positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS arena_positions (
                    id TEXT PRIMARY KEY,
                    sub_variant_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    position_size_usd REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    stop_loss_price REAL NOT NULL,
                    take_profit_price REAL NOT NULL,
                    current_sl_level REAL DEFAULT 0.0,
                    smart_sl_extensions INTEGER DEFAULT 0,
                    original_sl_price REAL DEFAULT 0.0,
                    current_price REAL DEFAULT 0.0,
                    current_pnl_pct REAL DEFAULT 0.0,
                    current_pnl_usd REAL DEFAULT 0.0,
                    peak_pnl_pct REAL DEFAULT 0.0,
                    entry_score REAL DEFAULT 0.0,
                    entry_reason TEXT,
                    FOREIGN KEY (sub_variant_id) REFERENCES arena_sub_variants(id)
                )
            """)

            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS arena_trades (
                    id TEXT PRIMARY KEY,
                    sub_variant_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    position_size_usd REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    entry_score REAL DEFAULT 0.0,
                    entry_reason TEXT,
                    exit_price REAL,
                    exit_time TIMESTAMP,
                    exit_reason TEXT,
                    pnl_pct REAL DEFAULT 0.0,
                    pnl_usd REAL DEFAULT 0.0,
                    peak_pnl_pct REAL DEFAULT 0.0,
                    duration_minutes INTEGER DEFAULT 0,
                    smart_sl_extensions INTEGER DEFAULT 0,
                    final_sl_price REAL DEFAULT 0.0,
                    ai_model TEXT,
                    ai_confidence REAL DEFAULT 0.0,
                    FOREIGN KEY (sub_variant_id) REFERENCES arena_sub_variants(id),
                    FOREIGN KEY (variant_id) REFERENCES arena_variants(id)
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_sub_variant
                ON arena_trades(sub_variant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_variant
                ON arena_trades(variant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON arena_trades(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_exit_time
                ON arena_trades(exit_time)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_sub_variant
                ON arena_positions(sub_variant_id)
            """)

            conn.commit()

    # ==================== Variant Operations ====================

    def save_variant(self, variant: Variant) -> bool:
        """Save or update a variant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO arena_variants (
                    id, name, description, enabled, operation_mode,
                    trading_params, indicator_config, ai_models,
                    pattern_detection_enabled, pattern_timeframe, pattern_min_confidence,
                    ai_check_interval_minutes, ai_independent_timeframe, symbols,
                    total_trades, total_pnl_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                variant.id,
                variant.name,
                variant.description,
                1 if variant.enabled else 0,
                variant.operation_mode.value,
                json.dumps(variant.trading_params.to_dict()),
                json.dumps(variant.indicator_config.to_dict()),
                json.dumps(variant.ai_models),
                1 if variant.pattern_detection_enabled else 0,
                variant.pattern_timeframe,
                variant.pattern_min_confidence,
                variant.ai_check_interval_minutes,
                variant.ai_independent_timeframe,
                json.dumps(variant.symbols),
                variant.total_trades,
                variant.total_pnl_usd,
                variant.created_at.isoformat() if variant.created_at else datetime.now().isoformat(),
            ))

            # Save sub-variants in same transaction
            for sv in variant.sub_variants:
                self._save_sub_variant_with_conn(cursor, sv)

            conn.commit()
            return True

    def _save_sub_variant_with_conn(self, cursor, sub_variant: SubVariant) -> None:
        """Save sub-variant using existing cursor (for transactions)."""
        cursor.execute("""
            INSERT OR REPLACE INTO arena_sub_variants (
                id, variant_id, ai_model, ai_model_name,
                total_trades, winning_trades, losing_trades,
                total_pnl_usd, total_pnl_pct, max_drawdown_pct, sharpe_ratio,
                created_at, last_trade_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sub_variant.id,
            sub_variant.variant_id,
            sub_variant.ai_model,
            sub_variant.ai_model_name,
            sub_variant.total_trades,
            sub_variant.winning_trades,
            sub_variant.losing_trades,
            sub_variant.total_pnl_usd,
            sub_variant.total_pnl_pct,
            sub_variant.max_drawdown_pct,
            sub_variant.sharpe_ratio,
            sub_variant.created_at.isoformat() if sub_variant.created_at else datetime.now().isoformat(),
            sub_variant.last_trade_at.isoformat() if sub_variant.last_trade_at else None,
        ))

    def get_variant(self, variant_id: str) -> Optional[Variant]:
        """Get a variant by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM arena_variants WHERE id = ?", (variant_id,))
            row = cursor.fetchone()

            if not row:
                return None

            variant = self._row_to_variant(row)

            # Load sub-variants
            cursor.execute(
                "SELECT * FROM arena_sub_variants WHERE variant_id = ?",
                (variant_id,)
            )
            for sv_row in cursor.fetchall():
                variant.sub_variants.append(self._row_to_sub_variant(sv_row))

            return variant

    def get_all_variants(self, enabled_only: bool = True) -> List[Variant]:
        """Get all variants."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if enabled_only:
                cursor.execute("SELECT * FROM arena_variants WHERE enabled = 1")
            else:
                cursor.execute("SELECT * FROM arena_variants")

            variants = []
            for row in cursor.fetchall():
                variant = self._row_to_variant(row)

                # Load sub-variants
                cursor.execute(
                    "SELECT * FROM arena_sub_variants WHERE variant_id = ?",
                    (variant.id,)
                )
                for sv_row in cursor.fetchall():
                    variant.sub_variants.append(self._row_to_sub_variant(sv_row))

                variants.append(variant)

            return variants

    def delete_variant(self, variant_id: str) -> bool:
        """Delete a variant and all related data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete positions
            cursor.execute("""
                DELETE FROM arena_positions
                WHERE sub_variant_id IN (
                    SELECT id FROM arena_sub_variants WHERE variant_id = ?
                )
            """, (variant_id,))

            # Delete trades
            cursor.execute("DELETE FROM arena_trades WHERE variant_id = ?", (variant_id,))

            # Delete sub-variants
            cursor.execute("DELETE FROM arena_sub_variants WHERE variant_id = ?", (variant_id,))

            # Delete variant
            cursor.execute("DELETE FROM arena_variants WHERE id = ?", (variant_id,))

            conn.commit()
            return cursor.rowcount > 0

    def _row_to_variant(self, row: sqlite3.Row) -> Variant:
        """Convert database row to Variant object."""
        trading_params = TradingParams.from_dict(json.loads(row["trading_params"] or "{}"))
        indicator_config = IndicatorConfig.from_dict(json.loads(row["indicator_config"] or "{}"))

        return Variant(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            enabled=bool(row["enabled"]),
            operation_mode=OperationMode(row["operation_mode"]),
            trading_params=trading_params,
            indicator_config=indicator_config,
            ai_models=json.loads(row["ai_models"] or '["deepseek/deepseek-chat"]'),
            pattern_detection_enabled=bool(row["pattern_detection_enabled"]),
            pattern_timeframe=row["pattern_timeframe"] or "1h",
            pattern_min_confidence=row["pattern_min_confidence"] or 0.60,
            ai_check_interval_minutes=row["ai_check_interval_minutes"] or 15,
            ai_independent_timeframe=row["ai_independent_timeframe"] or "4h",
            symbols=json.loads(row["symbols"] or '["BTC","ETH","SOL"]'),
            total_trades=row["total_trades"] or 0,
            total_pnl_usd=row["total_pnl_usd"] or 0.0,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    # ==================== Sub-Variant Operations ====================

    def save_sub_variant(self, sub_variant: SubVariant) -> bool:
        """Save or update a sub-variant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO arena_sub_variants (
                    id, variant_id, ai_model, ai_model_name,
                    total_trades, winning_trades, losing_trades,
                    total_pnl_usd, total_pnl_pct, max_drawdown_pct, sharpe_ratio,
                    created_at, last_trade_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sub_variant.id,
                sub_variant.variant_id,
                sub_variant.ai_model,
                sub_variant.ai_model_name,
                sub_variant.total_trades,
                sub_variant.winning_trades,
                sub_variant.losing_trades,
                sub_variant.total_pnl_usd,
                sub_variant.total_pnl_pct,
                sub_variant.max_drawdown_pct,
                sub_variant.sharpe_ratio,
                sub_variant.created_at.isoformat() if sub_variant.created_at else datetime.now().isoformat(),
                sub_variant.last_trade_at.isoformat() if sub_variant.last_trade_at else None,
            ))

            conn.commit()
            return True

    def get_sub_variant(self, sub_variant_id: str) -> Optional[SubVariant]:
        """Get a sub-variant by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM arena_sub_variants WHERE id = ?", (sub_variant_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_sub_variant(row)

    def update_sub_variant_stats(
        self,
        sub_variant_id: str,
        trade: SimulatedTrade
    ) -> bool:
        """Update sub-variant statistics after a trade."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get current stats
            cursor.execute("SELECT * FROM arena_sub_variants WHERE id = ?", (sub_variant_id,))
            row = cursor.fetchone()

            if not row:
                return False

            total_trades = (row["total_trades"] or 0) + 1
            winning_trades = (row["winning_trades"] or 0) + (1 if trade.is_winner else 0)
            losing_trades = (row["losing_trades"] or 0) + (0 if trade.is_winner else 1)
            total_pnl_usd = (row["total_pnl_usd"] or 0.0) + trade.pnl_usd
            total_pnl_pct = (row["total_pnl_pct"] or 0.0) + trade.pnl_pct

            # Update max drawdown if this trade had a larger loss
            max_drawdown = row["max_drawdown_pct"] or 0.0
            if trade.pnl_pct < 0 and abs(trade.pnl_pct) > max_drawdown:
                max_drawdown = abs(trade.pnl_pct)

            cursor.execute("""
                UPDATE arena_sub_variants SET
                    total_trades = ?,
                    winning_trades = ?,
                    losing_trades = ?,
                    total_pnl_usd = ?,
                    total_pnl_pct = ?,
                    max_drawdown_pct = ?,
                    last_trade_at = ?
                WHERE id = ?
            """, (
                total_trades,
                winning_trades,
                losing_trades,
                total_pnl_usd,
                total_pnl_pct,
                max_drawdown,
                datetime.now().isoformat(),
                sub_variant_id,
            ))

            conn.commit()
            return True

    def _row_to_sub_variant(self, row: sqlite3.Row) -> SubVariant:
        """Convert database row to SubVariant object."""
        return SubVariant(
            id=row["id"],
            variant_id=row["variant_id"],
            ai_model=row["ai_model"],
            ai_model_name=row["ai_model_name"] or "",
            total_trades=row["total_trades"] or 0,
            winning_trades=row["winning_trades"] or 0,
            losing_trades=row["losing_trades"] or 0,
            total_pnl_usd=row["total_pnl_usd"] or 0.0,
            total_pnl_pct=row["total_pnl_pct"] or 0.0,
            max_drawdown_pct=row["max_drawdown_pct"] or 0.0,
            sharpe_ratio=row["sharpe_ratio"] or 0.0,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            last_trade_at=datetime.fromisoformat(row["last_trade_at"]) if row["last_trade_at"] else None,
        )

    # ==================== Position Operations ====================

    def save_position(self, position: SimulatedPosition) -> bool:
        """Save or update an open position."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO arena_positions (
                    id, sub_variant_id, symbol, direction,
                    entry_price, entry_time, position_size_usd, leverage,
                    stop_loss_price, take_profit_price, current_sl_level,
                    smart_sl_extensions, original_sl_price,
                    current_price, current_pnl_pct, current_pnl_usd, peak_pnl_pct,
                    entry_score, entry_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id,
                position.sub_variant_id,
                position.symbol,
                position.direction.value,
                position.entry_price,
                position.entry_time.isoformat(),
                position.position_size_usd,
                position.leverage,
                position.stop_loss_price,
                position.take_profit_price,
                position.current_sl_level,
                position.smart_sl_extensions,
                position.original_sl_price,
                position.current_price,
                position.current_pnl_pct,
                position.current_pnl_usd,
                position.peak_pnl_pct,
                position.entry_score,
                position.entry_reason,
            ))

            conn.commit()
            return True

    def get_positions_for_sub_variant(self, sub_variant_id: str) -> List[SimulatedPosition]:
        """Get all open positions for a sub-variant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM arena_positions WHERE sub_variant_id = ?",
                (sub_variant_id,)
            )

            positions = []
            for row in cursor.fetchall():
                positions.append(self._row_to_position(row))

            return positions

    def get_position(self, position_id: str) -> Optional[SimulatedPosition]:
        """Get a position by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM arena_positions WHERE id = ?", (position_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_position(row)

    def get_position_by_symbol(
        self,
        sub_variant_id: str,
        symbol: str
    ) -> Optional[SimulatedPosition]:
        """Get open position for a symbol in a sub-variant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM arena_positions WHERE sub_variant_id = ? AND symbol = ?",
                (sub_variant_id, symbol)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_position(row)

    def delete_position(self, position_id: str) -> bool:
        """Delete a position (when closed)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM arena_positions WHERE id = ?", (position_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_open_positions(self) -> List[SimulatedPosition]:
        """Get all open positions across all sub-variants."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM arena_positions")

            positions = []
            for row in cursor.fetchall():
                positions.append(self._row_to_position(row))

            return positions

    def _row_to_position(self, row: sqlite3.Row) -> SimulatedPosition:
        """Convert database row to SimulatedPosition object."""
        return SimulatedPosition(
            id=row["id"],
            sub_variant_id=row["sub_variant_id"],
            symbol=row["symbol"],
            direction=TradeDirection(row["direction"]),
            entry_price=row["entry_price"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            position_size_usd=row["position_size_usd"],
            leverage=row["leverage"],
            stop_loss_price=row["stop_loss_price"],
            take_profit_price=row["take_profit_price"],
            current_sl_level=row["current_sl_level"] or 0.0,
            smart_sl_extensions=row["smart_sl_extensions"] or 0,
            original_sl_price=row["original_sl_price"] or 0.0,
            current_price=row["current_price"] or 0.0,
            current_pnl_pct=row["current_pnl_pct"] or 0.0,
            current_pnl_usd=row["current_pnl_usd"] or 0.0,
            peak_pnl_pct=row["peak_pnl_pct"] or 0.0,
            entry_score=row["entry_score"] or 0.0,
            entry_reason=row["entry_reason"] or "",
        )

    # ==================== Trade Operations ====================

    def save_trade(self, trade: SimulatedTrade) -> bool:
        """Save a completed trade."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO arena_trades (
                    id, sub_variant_id, variant_id, symbol, direction,
                    entry_price, entry_time, position_size_usd, leverage,
                    entry_score, entry_reason,
                    exit_price, exit_time, exit_reason,
                    pnl_pct, pnl_usd, peak_pnl_pct, duration_minutes,
                    smart_sl_extensions, final_sl_price,
                    ai_model, ai_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id,
                trade.sub_variant_id,
                trade.variant_id,
                trade.symbol,
                trade.direction.value,
                trade.entry_price,
                trade.entry_time.isoformat() if trade.entry_time else None,
                trade.position_size_usd,
                trade.leverage,
                trade.entry_score,
                trade.entry_reason,
                trade.exit_price,
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.exit_reason.value if trade.exit_reason else None,
                trade.pnl_pct,
                trade.pnl_usd,
                trade.peak_pnl_pct,
                trade.duration_minutes,
                trade.smart_sl_extensions,
                trade.final_sl_price,
                trade.ai_model,
                trade.ai_confidence,
            ))

            conn.commit()
            return True

    def get_trades_for_sub_variant(
        self,
        sub_variant_id: str,
        limit: int = 100
    ) -> List[SimulatedTrade]:
        """Get trades for a sub-variant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM arena_trades
                WHERE sub_variant_id = ?
                ORDER BY exit_time DESC
                LIMIT ?
            """, (sub_variant_id, limit))

            trades = []
            for row in cursor.fetchall():
                trades.append(self._row_to_trade(row))

            return trades

    def get_trades_for_variant(
        self,
        variant_id: str,
        limit: int = 100
    ) -> List[SimulatedTrade]:
        """Get trades for a variant (all sub-variants)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM arena_trades
                WHERE variant_id = ?
                ORDER BY exit_time DESC
                LIMIT ?
            """, (variant_id, limit))

            trades = []
            for row in cursor.fetchall():
                trades.append(self._row_to_trade(row))

            return trades

    def get_recent_trades(self, hours: int = 24, limit: int = 100) -> List[SimulatedTrade]:
        """Get recent trades across all variants."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM arena_trades
                WHERE exit_time >= datetime('now', ? || ' hours')
                ORDER BY exit_time DESC
                LIMIT ?
            """, (f"-{hours}", limit))

            trades = []
            for row in cursor.fetchall():
                trades.append(self._row_to_trade(row))

            return trades

    def get_trade_stats(
        self,
        sub_variant_id: Optional[str] = None,
        variant_id: Optional[str] = None,
        symbol: Optional[str] = None,
        hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get aggregated trade statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if sub_variant_id:
                conditions.append("sub_variant_id = ?")
                params.append(sub_variant_id)
            if variant_id:
                conditions.append("variant_id = ?")
                params.append(variant_id)
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if hours:
                conditions.append(f"exit_time >= datetime('now', '-{hours} hours')")

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(pnl_usd) as total_pnl_usd,
                    AVG(pnl_pct) as avg_pnl_pct,
                    MAX(pnl_pct) as max_pnl_pct,
                    MIN(pnl_pct) as min_pnl_pct,
                    AVG(duration_minutes) as avg_duration
                FROM arena_trades
                WHERE {where_clause}
            """, params)

            row = cursor.fetchone()

            total_trades = row["total_trades"] or 0
            winning_trades = row["winning_trades"] or 0

            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": row["losing_trades"] or 0,
                "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                "total_pnl_usd": row["total_pnl_usd"] or 0.0,
                "avg_pnl_pct": row["avg_pnl_pct"] or 0.0,
                "max_pnl_pct": row["max_pnl_pct"] or 0.0,
                "min_pnl_pct": row["min_pnl_pct"] or 0.0,
                "avg_duration_minutes": row["avg_duration"] or 0,
            }

    def _row_to_trade(self, row: sqlite3.Row) -> SimulatedTrade:
        """Convert database row to SimulatedTrade object."""
        return SimulatedTrade(
            id=row["id"],
            sub_variant_id=row["sub_variant_id"],
            variant_id=row["variant_id"],
            symbol=row["symbol"],
            direction=TradeDirection(row["direction"]),
            entry_price=row["entry_price"],
            entry_time=datetime.fromisoformat(row["entry_time"]) if row["entry_time"] else datetime.now(),
            position_size_usd=row["position_size_usd"],
            leverage=row["leverage"],
            entry_score=row["entry_score"] or 0.0,
            entry_reason=row["entry_reason"] or "",
            exit_price=row["exit_price"] or 0.0,
            exit_time=datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None,
            exit_reason=TradeStatus(row["exit_reason"]) if row["exit_reason"] else TradeStatus.OPEN,
            pnl_pct=row["pnl_pct"] or 0.0,
            pnl_usd=row["pnl_usd"] or 0.0,
            peak_pnl_pct=row["peak_pnl_pct"] or 0.0,
            duration_minutes=row["duration_minutes"] or 0,
            smart_sl_extensions=row["smart_sl_extensions"] or 0,
            final_sl_price=row["final_sl_price"] or 0.0,
            ai_model=row["ai_model"] or "",
            ai_confidence=row["ai_confidence"] or 0.0,
        )

    # ==================== Leaderboard ====================

    def get_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get sub-variant leaderboard sorted by P&L."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    sv.id,
                    sv.variant_id,
                    sv.ai_model_name,
                    sv.total_trades,
                    sv.winning_trades,
                    sv.losing_trades,
                    sv.total_pnl_usd,
                    sv.total_pnl_pct,
                    sv.max_drawdown_pct,
                    sv.sharpe_ratio,
                    v.name as variant_name
                FROM arena_sub_variants sv
                JOIN arena_variants v ON sv.variant_id = v.id
                WHERE sv.total_trades > 0
                ORDER BY sv.total_pnl_usd DESC
                LIMIT ?
            """, (limit,))

            leaderboard = []
            rank = 1
            for row in cursor.fetchall():
                total_trades = row["total_trades"] or 0
                winning_trades = row["winning_trades"] or 0

                leaderboard.append({
                    "rank": rank,
                    "sub_variant_id": row["id"],
                    "variant_id": row["variant_id"],
                    "variant_name": row["variant_name"],
                    "ai_model": row["ai_model_name"],
                    "total_trades": total_trades,
                    "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                    "total_pnl_usd": row["total_pnl_usd"] or 0.0,
                    "total_pnl_pct": row["total_pnl_pct"] or 0.0,
                    "max_drawdown_pct": row["max_drawdown_pct"] or 0.0,
                    "sharpe_ratio": row["sharpe_ratio"] or 0.0,
                })
                rank += 1

            return leaderboard

    # ==================== Cleanup ====================

    def reset_all_data(self) -> bool:
        """Reset all arena data (use with caution!)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM arena_trades")
            cursor.execute("DELETE FROM arena_positions")
            cursor.execute("DELETE FROM arena_sub_variants")
            cursor.execute("DELETE FROM arena_variants")
            conn.commit()
            return True
