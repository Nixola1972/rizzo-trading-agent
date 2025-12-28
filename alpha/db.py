"""
AlphaTrader Database Module
===========================

Saves decisions and trades to PostgreSQL for:
1. Analytics and performance tracking
2. Future retraining with real data
3. Arena dashboard integration
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def sanitize_for_json(obj: Any) -> Any:
    """Convert numpy types and other non-JSON-serializable types to native Python."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, '__dict__'):
        # For dataclasses and other objects
        return sanitize_for_json(obj.__dict__)
    else:
        return obj

# Try to import psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not installed - database logging disabled")


def get_database_url() -> Optional[str]:
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL") or os.getenv("ALPHA_DATABASE_URL")


@contextmanager
def get_connection():
    """Get a database connection with context manager."""
    if not PSYCOPG2_AVAILABLE:
        yield None
        return

    db_url = get_database_url()
    if not db_url:
        logger.warning("No DATABASE_URL configured")
        yield None
        return

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        yield conn
        conn.commit()
    except Exception as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
        yield None
    finally:
        if conn:
            conn.close()


def init_tables():
    """Create AlphaTrader tables if they don't exist."""
    if not PSYCOPG2_AVAILABLE:
        return False

    with get_connection() as conn:
        if not conn:
            return False

        try:
            cur = conn.cursor()

            # Table for every decision made by AlphaTrader
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alpha_decisions (
                    id SERIAL PRIMARY KEY,

                    -- Timestamp
                    created_at TIMESTAMPTZ DEFAULT NOW(),

                    -- Symbol and Decision
                    symbol VARCHAR(10) NOT NULL,
                    policy_action VARCHAR(20) NOT NULL,
                    final_action VARCHAR(20) NOT NULL,

                    -- Confidence
                    policy_confidence DECIMAL(5,4),
                    value_estimate DECIMAL(8,6),
                    win_probability DECIMAL(5,4),

                    -- MCTS
                    mcts_approved BOOLEAN,
                    mcts_win_prob DECIMAL(5,4),
                    mcts_reason TEXT,

                    -- Market State at Decision Time
                    price DECIMAL(20,8),
                    rsi DECIMAL(6,2),
                    macd DECIMAL(12,6),
                    adx DECIMAL(6,2),
                    fear_greed INTEGER,

                    -- Full state for analysis
                    market_data JSONB,
                    decision_info JSONB,

                    -- Validation (filled later)
                    price_after_5m DECIMAL(20,8),
                    price_after_15m DECIMAL(20,8),
                    was_correct BOOLEAN,

                    -- Indexes
                    CONSTRAINT idx_alpha_decisions_symbol_time UNIQUE (symbol, created_at)
                );

                CREATE INDEX IF NOT EXISTS idx_alpha_decisions_created
                    ON alpha_decisions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_alpha_decisions_symbol
                    ON alpha_decisions(symbol);
            """)

            # Table for paper trades
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alpha_trades (
                    id SERIAL PRIMARY KEY,

                    -- Identification
                    symbol VARCHAR(10) NOT NULL,
                    direction VARCHAR(5) NOT NULL,

                    -- Timestamps
                    opened_at TIMESTAMPTZ NOT NULL,
                    closed_at TIMESTAMPTZ,
                    duration_seconds INTEGER,

                    -- Prices
                    entry_price DECIMAL(20,8) NOT NULL,
                    exit_price DECIMAL(20,8),
                    size_usd DECIMAL(10,2),
                    leverage INTEGER DEFAULT 1,

                    -- P&L
                    pnl_usd DECIMAL(10,4),
                    pnl_pct DECIMAL(8,4),

                    -- MFE/MAE
                    max_price DECIMAL(20,8),
                    min_price DECIMAL(20,8),
                    mfe_pct DECIMAL(8,4),
                    mae_pct DECIMAL(8,4),

                    -- Decision context
                    decision_id INTEGER REFERENCES alpha_decisions(id),
                    policy_confidence DECIMAL(5,4),
                    mcts_win_prob DECIMAL(5,4),

                    -- Exit info
                    exit_reason VARCHAR(30),

                    -- Status
                    status VARCHAR(10) DEFAULT 'OPEN',
                    is_paper BOOLEAN DEFAULT TRUE,

                    -- Metadata
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_alpha_trades_symbol
                    ON alpha_trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_alpha_trades_status
                    ON alpha_trades(status);
                CREATE INDEX IF NOT EXISTS idx_alpha_trades_opened
                    ON alpha_trades(opened_at DESC);
            """)

            # Table for equity curve tracking
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alpha_equity (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    equity_usd DECIMAL(12,2) NOT NULL,
                    open_positions INTEGER DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    total_pnl_usd DECIMAL(12,2) DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_alpha_equity_time
                    ON alpha_equity(timestamp DESC);
            """)

            conn.commit()
            logger.info("AlphaTrader tables created successfully")
            return True

        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            conn.rollback()
            return False


def save_decision(
    symbol: str,
    policy_action: str,
    final_action: str,
    policy_confidence: float,
    value_estimate: float,
    win_probability: float,
    mcts_approved: Optional[bool],
    mcts_win_prob: Optional[float],
    mcts_reason: Optional[str],
    price: float,
    rsi: float,
    macd: float,
    adx: float,
    fear_greed: int,
    market_data: Dict,
    decision_info: Dict
) -> Optional[int]:
    """Save a decision to the database. Returns decision ID."""

    if not PSYCOPG2_AVAILABLE:
        return None

    with get_connection() as conn:
        if not conn:
            return None

        try:
            cur = conn.cursor()
            # Sanitize data to remove numpy types before JSON conversion
            safe_market_data = sanitize_for_json(market_data)
            safe_decision_info = sanitize_for_json(decision_info)

            cur.execute("""
                INSERT INTO alpha_decisions (
                    symbol, policy_action, final_action,
                    policy_confidence, value_estimate, win_probability,
                    mcts_approved, mcts_win_prob, mcts_reason,
                    price, rsi, macd, adx, fear_greed,
                    market_data, decision_info
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
            """, (
                symbol, policy_action, final_action,
                float(policy_confidence) if policy_confidence else 0,
                float(value_estimate) if value_estimate else 0,
                float(win_probability) if win_probability else 0,
                mcts_approved,
                float(mcts_win_prob) if mcts_win_prob else None,
                mcts_reason,
                float(price) if price else 0,
                float(rsi) if rsi else 50,
                float(macd) if macd else 0,
                float(adx) if adx else 25,
                int(fear_greed) if fear_greed else 50,
                Json(safe_market_data), Json(safe_decision_info)
            ))

            result = cur.fetchone()
            decision_id = result[0] if result else None
            conn.commit()

            logger.info(f"Saved decision #{decision_id} for {symbol}: {final_action}")
            return decision_id

        except Exception as e:
            logger.error(f"Error saving decision: {e}")
            return None


def save_trade_open(
    symbol: str,
    direction: str,
    entry_price: float,
    size_usd: float,
    leverage: int,
    decision_id: Optional[int],
    policy_confidence: float,
    mcts_win_prob: Optional[float],
    is_paper: bool = True
) -> Optional[int]:
    """Save a new trade opening. Returns trade ID."""

    if not PSYCOPG2_AVAILABLE:
        return None

    with get_connection() as conn:
        if not conn:
            return None

        try:
            cur = conn.cursor()
            # Convert numpy types to native Python
            safe_entry_price = float(entry_price) if entry_price else 0
            safe_size_usd = float(size_usd) if size_usd else 0
            safe_leverage = int(leverage) if leverage else 1
            safe_confidence = float(policy_confidence) if policy_confidence else 0
            safe_mcts_prob = float(mcts_win_prob) if mcts_win_prob else None

            cur.execute("""
                INSERT INTO alpha_trades (
                    symbol, direction, opened_at,
                    entry_price, size_usd, leverage,
                    decision_id, policy_confidence, mcts_win_prob,
                    max_price, min_price, status, is_paper
                ) VALUES (
                    %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN', %s
                )
                RETURNING id
            """, (
                symbol, direction, safe_entry_price, safe_size_usd, safe_leverage,
                decision_id, safe_confidence, safe_mcts_prob,
                safe_entry_price, safe_entry_price, is_paper
            ))

            result = cur.fetchone()
            trade_id = result[0] if result else None
            conn.commit()

            logger.info(f"Saved trade #{trade_id}: {direction} {symbol} @ ${entry_price:.2f}")
            return trade_id

        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return None


def update_trade_prices(trade_id: int, current_price: float, direction: str):
    """Update max/min prices for MFE/MAE tracking."""

    if not PSYCOPG2_AVAILABLE:
        return

    with get_connection() as conn:
        if not conn:
            return

        try:
            cur = conn.cursor()
            safe_price = float(current_price) if current_price else 0
            cur.execute("""
                UPDATE alpha_trades
                SET max_price = GREATEST(max_price, %s),
                    min_price = LEAST(min_price, %s)
                WHERE id = %s
            """, (safe_price, safe_price, trade_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating trade prices: {e}")


def close_trade(
    trade_id: int,
    exit_price: float,
    exit_reason: str
):
    """Close a trade and calculate P&L."""

    if not PSYCOPG2_AVAILABLE:
        return

    with get_connection() as conn:
        if not conn:
            return

        try:
            cur = conn.cursor()

            # Get trade info
            cur.execute("""
                SELECT entry_price, direction, leverage, opened_at, max_price, min_price
                FROM alpha_trades WHERE id = %s
            """, (trade_id,))

            row = cur.fetchone()
            if not row:
                return

            entry_price, direction, leverage, opened_at, max_price, min_price = row

            # Calculate P&L
            if direction == "LONG":
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * leverage
                mfe_pct = ((max_price - entry_price) / entry_price) * 100 * leverage
                mae_pct = ((min_price - entry_price) / entry_price) * 100 * leverage
            else:
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100 * leverage
                mfe_pct = ((entry_price - min_price) / entry_price) * 100 * leverage
                mae_pct = ((entry_price - max_price) / entry_price) * 100 * leverage

            # Calculate duration
            duration = int((datetime.utcnow() - opened_at).total_seconds())

            # Update trade
            cur.execute("""
                UPDATE alpha_trades
                SET closed_at = NOW(),
                    exit_price = %s,
                    pnl_pct = %s,
                    mfe_pct = %s,
                    mae_pct = %s,
                    duration_seconds = %s,
                    exit_reason = %s,
                    status = 'CLOSED'
                WHERE id = %s
            """, (exit_price, pnl_pct, mfe_pct, mae_pct, duration, exit_reason, trade_id))

            conn.commit()
            logger.info(f"Closed trade #{trade_id}: {pnl_pct:+.2f}%")

        except Exception as e:
            logger.error(f"Error closing trade: {e}")


def get_open_trade(symbol: str) -> Optional[Dict]:
    """Get open trade for a symbol."""

    if not PSYCOPG2_AVAILABLE:
        return None

    with get_connection() as conn:
        if not conn:
            return None

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT * FROM alpha_trades
                WHERE symbol = %s AND status = 'OPEN'
                ORDER BY opened_at DESC LIMIT 1
            """, (symbol,))

            return cur.fetchone()

        except Exception as e:
            logger.error(f"Error getting open trade: {e}")
            return None


def get_stats() -> Dict:
    """Get overall AlphaTrader stats."""

    if not PSYCOPG2_AVAILABLE:
        return {}

    with get_connection() as conn:
        if not conn:
            return {}

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Trade stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as winning_trades,
                    COALESCE(SUM(pnl_pct), 0) as total_pnl_pct,
                    COALESCE(AVG(pnl_pct), 0) as avg_pnl_pct,
                    COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_trades
                FROM alpha_trades
            """)
            trade_stats = cur.fetchone()

            # Decision stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_decisions,
                    COUNT(CASE WHEN final_action != 'HOLD' THEN 1 END) as action_decisions,
                    COUNT(CASE WHEN mcts_approved = FALSE THEN 1 END) as mcts_vetoes
                FROM alpha_decisions
            """)
            decision_stats = cur.fetchone()

            return {
                'trades': dict(trade_stats) if trade_stats else {},
                'decisions': dict(decision_stats) if decision_stats else {},
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}


def save_equity_snapshot(
    equity_usd: float,
    open_positions: int,
    total_trades: int,
    winning_trades: int,
    total_pnl_usd: float
):
    """Save equity curve data point."""

    if not PSYCOPG2_AVAILABLE:
        return

    with get_connection() as conn:
        if not conn:
            return

        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO alpha_equity (
                    equity_usd, open_positions, total_trades,
                    winning_trades, total_pnl_usd
                ) VALUES (%s, %s, %s, %s, %s)
            """, (equity_usd, open_positions, total_trades, winning_trades, total_pnl_usd))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving equity: {e}")


# Initialize tables on module import
if PSYCOPG2_AVAILABLE and get_database_url():
    init_tables()
