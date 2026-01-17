"""
Database module for Botone V6 trade tracking.
Stores trades with MFE/MAE, indicators at entry, and AI decision context.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger("BOTONE-V6")


def _to_python_type(value):
    """
    Convert numpy types to Python native types for database compatibility.
    psycopg2 cannot handle numpy.float64, numpy.int64, numpy.bool_, etc.
    """
    if value is None:
        return None

    # Check for numpy types by checking the type name
    # This avoids importing numpy just to check types
    type_name = type(value).__name__

    if type_name in ('float64', 'float32', 'float16'):
        return float(value)
    elif type_name in ('int64', 'int32', 'int16', 'int8', 'uint64', 'uint32', 'uint16', 'uint8'):
        return int(value)
    elif type_name in ('bool_', 'bool8'):
        return bool(value)
    elif type_name == 'ndarray':
        # Convert array to list, then take first element if single value
        arr = value.tolist()
        return arr[0] if len(arr) == 1 else arr

    # Already a Python native type
    return value

# Try to import psycopg2, fallback gracefully if not available
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not installed - database tracking disabled")


class TradeDatabase:
    """Database handler for trade tracking."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.conn = None
        self.enabled = False

        if not PSYCOPG2_AVAILABLE:
            logger.warning("Database tracking disabled - psycopg2 not available")
            return

        if not self.database_url:
            logger.warning("Database tracking disabled - DATABASE_URL not set")
            return

        try:
            self._connect()
            self._create_tables()
            self.enabled = True
            logger.info("✅ Database tracking enabled")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            self.enabled = False

    def _connect(self):
        """Establish database connection."""
        self.conn = psycopg2.connect(self.database_url)
        self.conn.autocommit = True

    def _create_tables(self):
        """Create tables if they don't exist."""
        with self.conn.cursor() as cur:
            # Main trades table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS botone_trades (
                    id SERIAL PRIMARY KEY,

                    -- Basic Info
                    symbol VARCHAR(10) NOT NULL,
                    direction VARCHAR(5) NOT NULL,
                    opened_at TIMESTAMP NOT NULL,
                    closed_at TIMESTAMP,
                    duration_seconds INTEGER,

                    -- Prices
                    entry_price DECIMAL(20,8) NOT NULL,
                    exit_price DECIMAL(20,8),
                    size_usd DECIMAL(10,2),
                    leverage INTEGER,

                    -- P&L
                    pnl_usd DECIMAL(10,4),
                    pnl_pct DECIMAL(8,4),

                    -- MFE/MAE (Max Favorable/Adverse Excursion)
                    max_price DECIMAL(20,8),
                    min_price DECIMAL(20,8),
                    mfe_pct DECIMAL(8,4),
                    mae_pct DECIMAL(8,4),

                    -- AI Decision at Entry
                    conviction_tier INTEGER,
                    ai_confidence DECIMAL(5,4),
                    ai_reasoning TEXT,
                    prompt_style VARCHAR(20),

                    -- Indicators at Entry
                    entry_macd DECIMAL(12,6),
                    entry_rsi DECIMAL(6,2),
                    entry_adx DECIMAL(6,2),
                    entry_ema_stack VARCHAR(20),
                    entry_volume_ratio DECIMAL(6,3),
                    entry_bb_position VARCHAR(20),
                    entry_bb_squeeze BOOLEAN,
                    entry_obv_trend VARCHAR(10),
                    entry_funding_rate DECIMAL(12,8),
                    entry_open_interest DECIMAL(20,2),
                    entry_fear_greed INTEGER,
                    entry_price_vs_pivot VARCHAR(30),

                    -- Pattern Detection at Entry
                    entry_double_bottom BOOLEAN DEFAULT FALSE,
                    entry_double_top BOOLEAN DEFAULT FALSE,
                    entry_pattern_confidence DECIMAL(5,4),

                    -- Exit Info
                    exit_reason VARCHAR(30),
                    trailing_level_pct DECIMAL(6,3),
                    sl_price DECIMAL(20,8),
                    tp_price DECIMAL(20,8),

                    -- Metadata
                    bot_name VARCHAR(50) DEFAULT 'botone-v6',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Index for common queries
                CREATE INDEX IF NOT EXISTS idx_botone_trades_symbol ON botone_trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_botone_trades_opened_at ON botone_trades(opened_at);
                CREATE INDEX IF NOT EXISTS idx_botone_trades_closed_at ON botone_trades(closed_at);
            """)

            # AI decision logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_prompt_logs (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    symbol TEXT,
                    full_prompt TEXT,
                    ai_raw_response TEXT,
                    parsed_decision JSONB,
                    model_used TEXT,
                    duration_ms INTEGER
                );

                -- Index for common queries
                CREATE INDEX IF NOT EXISTS idx_ai_prompt_logs_symbol ON ai_prompt_logs(symbol);
                CREATE INDEX IF NOT EXISTS idx_ai_prompt_logs_created_at ON ai_prompt_logs(created_at);
                CREATE INDEX IF NOT EXISTS idx_ai_prompt_logs_model ON ai_prompt_logs(model_used);
            """)
            logger.info("Database tables created/verified")

    def save_trade_entry(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        size_usd: float,
        leverage: int,
        sl_price: float,
        tp_price: float,
        conviction_tier: int,
        ai_confidence: float,
        ai_reasoning: str,
        prompt_style: str,
        indicators: Dict[str, Any],
    ) -> Optional[int]:
        """
        Save a new trade entry to the database.
        Returns the trade ID for later updates.
        """
        if not self.enabled:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO botone_trades (
                        symbol, direction, opened_at, entry_price, size_usd, leverage,
                        max_price, min_price,
                        sl_price, tp_price,
                        conviction_tier, ai_confidence, ai_reasoning, prompt_style,
                        entry_macd, entry_rsi, entry_adx, entry_ema_stack,
                        entry_volume_ratio, entry_bb_position, entry_bb_squeeze,
                        entry_obv_trend, entry_funding_rate, entry_open_interest,
                        entry_fear_greed, entry_price_vs_pivot,
                        entry_double_bottom, entry_double_top, entry_pattern_confidence
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s
                    ) RETURNING id
                """, (
                    symbol,
                    direction,
                    datetime.now(),
                    _to_python_type(entry_price),
                    _to_python_type(size_usd),
                    _to_python_type(leverage),
                    _to_python_type(entry_price),  # Initial max_price = entry
                    _to_python_type(entry_price),  # Initial min_price = entry
                    _to_python_type(sl_price),
                    _to_python_type(tp_price),
                    _to_python_type(conviction_tier),
                    _to_python_type(ai_confidence),
                    ai_reasoning[:2000] if ai_reasoning else None,  # Truncate long reasoning
                    prompt_style,
                    _to_python_type(indicators.get("macd")),
                    _to_python_type(indicators.get("rsi")),
                    _to_python_type(indicators.get("adx")),
                    indicators.get("ema_stack"),  # string, no conversion needed
                    _to_python_type(indicators.get("volume_ratio")),
                    indicators.get("bb_position"),  # string, no conversion needed
                    bool(indicators.get("bb_squeeze", False)),  # Convert to Python bool
                    indicators.get("obv_trend"),  # string, no conversion needed
                    _to_python_type(indicators.get("funding_rate")),
                    _to_python_type(indicators.get("open_interest")),
                    _to_python_type(indicators.get("fear_greed")),
                    indicators.get("price_vs_pivot"),  # string, no conversion needed
                    bool(indicators.get("double_bottom", False)),  # Convert to Python bool
                    bool(indicators.get("double_top", False)),  # Convert to Python bool
                    _to_python_type(indicators.get("pattern_confidence")),
                ))
                trade_id = cur.fetchone()[0]
                logger.info(f"[DB] Trade #{trade_id} saved: {direction} {symbol} @ ${entry_price}")
                return trade_id

        except Exception as e:
            logger.error(f"[DB] Error saving trade entry: {e}")
            return None

    def update_mfe_mae(self, trade_id: int, max_price: float, min_price: float):
        """Update the max/min prices for MFE/MAE tracking."""
        if not self.enabled or not trade_id:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE botone_trades
                    SET max_price = GREATEST(max_price, %s),
                        min_price = LEAST(min_price, %s)
                    WHERE id = %s
                """, (_to_python_type(max_price), _to_python_type(min_price), trade_id))
        except Exception as e:
            logger.error(f"[DB] Error updating MFE/MAE: {e}")

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl_usd: float,
        pnl_pct: float,
        exit_reason: str,
        trailing_level_pct: Optional[float] = None,
    ):
        """Close a trade and calculate final MFE/MAE percentages."""
        if not self.enabled or not trade_id:
            return

        try:
            with self.conn.cursor() as cur:
                # Get entry price and direction for MFE/MAE calculation
                cur.execute("""
                    SELECT entry_price, direction, max_price, min_price, leverage, opened_at
                    FROM botone_trades WHERE id = %s
                """, (trade_id,))
                row = cur.fetchone()

                if not row:
                    logger.warning(f"[DB] Trade #{trade_id} not found for closing")
                    return

                entry_price, direction, max_price, min_price, leverage, opened_at = row
                entry_price = float(entry_price)
                max_price = float(max_price)
                min_price = float(min_price)
                leverage = leverage or 1

                # Calculate MFE/MAE based on direction
                if direction == "LONG":
                    # For LONG: MFE = how high it went, MAE = how low it went
                    mfe_pct = ((max_price - entry_price) / entry_price) * 100 * leverage
                    mae_pct = ((entry_price - min_price) / entry_price) * 100 * leverage
                else:
                    # For SHORT: MFE = how low it went, MAE = how high it went
                    mfe_pct = ((entry_price - min_price) / entry_price) * 100 * leverage
                    mae_pct = ((max_price - entry_price) / entry_price) * 100 * leverage

                # Calculate duration
                duration_seconds = int((datetime.now() - opened_at).total_seconds())

                cur.execute("""
                    UPDATE botone_trades
                    SET closed_at = %s,
                        exit_price = %s,
                        pnl_usd = %s,
                        pnl_pct = %s,
                        mfe_pct = %s,
                        mae_pct = %s,
                        exit_reason = %s,
                        trailing_level_pct = %s,
                        duration_seconds = %s
                    WHERE id = %s
                """, (
                    datetime.now(),
                    _to_python_type(exit_price),
                    _to_python_type(pnl_usd),
                    _to_python_type(pnl_pct),
                    _to_python_type(mfe_pct),
                    _to_python_type(mae_pct),
                    exit_reason,
                    _to_python_type(trailing_level_pct),
                    duration_seconds,
                    trade_id,
                ))

                logger.info(f"[DB] Trade #{trade_id} closed: {exit_reason} | P&L: {pnl_pct:+.2f}% | MFE: {mfe_pct:+.2f}% | MAE: {mae_pct:+.2f}%")

        except Exception as e:
            logger.error(f"[DB] Error closing trade: {e}")

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get trading statistics for the last N days."""
        if not self.enabled:
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as winning_trades,
                        COUNT(CASE WHEN pnl_pct <= 0 THEN 1 END) as losing_trades,
                        COALESCE(SUM(pnl_usd), 0) as total_pnl_usd,
                        COALESCE(AVG(pnl_pct), 0) as avg_pnl_pct,
                        COALESCE(AVG(mfe_pct), 0) as avg_mfe_pct,
                        COALESCE(AVG(mae_pct), 0) as avg_mae_pct,
                        COALESCE(AVG(duration_seconds), 0) as avg_duration_sec,
                        COALESCE(AVG(CASE WHEN pnl_pct > 0 THEN pnl_pct END), 0) as avg_win_pct,
                        COALESCE(AVG(CASE WHEN pnl_pct <= 0 THEN pnl_pct END), 0) as avg_loss_pct
                    FROM botone_trades
                    WHERE closed_at IS NOT NULL
                      AND closed_at >= NOW() - INTERVAL '%s days'
                """, (days,))

                stats = dict(cur.fetchone())

                # Calculate win rate
                total = stats['total_trades']
                if total > 0:
                    stats['win_rate'] = (stats['winning_trades'] / total) * 100
                    # Profit factor
                    if stats['avg_loss_pct'] != 0:
                        stats['profit_factor'] = abs(stats['avg_win_pct'] / stats['avg_loss_pct'])
                    else:
                        stats['profit_factor'] = float('inf') if stats['avg_win_pct'] > 0 else 0
                else:
                    stats['win_rate'] = 0
                    stats['profit_factor'] = 0

                return stats

        except Exception as e:
            logger.error(f"[DB] Error getting statistics: {e}")
            return {}

    def get_trade_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the most recent open trade for a symbol."""
        if not self.enabled:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM botone_trades
                    WHERE symbol = %s AND closed_at IS NULL
                    ORDER BY opened_at DESC
                    LIMIT 1
                """, (symbol,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[DB] Error getting trade: {e}")
            return None

    def save_ai_decision(
        self,
        symbol: str,
        full_prompt: str,
        ai_raw_response: str,
        parsed_decision: dict,
        model_used: str,
        duration_ms: int,
    ) -> Optional[int]:
        """Save AI decision to ai_prompt_logs for debugging."""
        if not self.enabled:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ai_prompt_logs (
                        symbol, full_prompt, ai_raw_response,
                        parsed_decision, model_used, duration_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    symbol,
                    full_prompt,
                    ai_raw_response,
                    json.dumps(parsed_decision) if parsed_decision else '{}',
                    model_used,
                    duration_ms,
                ))
                log_id = cur.fetchone()[0]
                self.conn.commit()
                logger.debug(f"[DB] AI decision saved for {symbol} (log_id={log_id})")
                return log_id
        except Exception as e:
            logger.error(f"[DB] Error saving AI decision: {e}")
            return None

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("[DB] Database connection closed")
