"""
Sentinel Lock - Database-based semaphore for FAST/SLOW coordination.

Prevents conflicts between SENTINEL-FAST and SENTINEL-SLOW processes.

Usage:
    from sentinel_lock import SentinelLock

    with SentinelLock("BTC", "sl_update") as lock:
        if lock.acquired:
            # Safe to update SL
            update_sl_order(...)
        else:
            # Another process has the lock, skip
            pass
"""

import time
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional
import psycopg2
from psycopg2 import sql
import os

logger = logging.getLogger(__name__)

# Lock types and their max hold times (seconds)
LOCK_TYPES = {
    "sl_update": 5,        # Updating SL order
    "position_open": 10,   # Opening a position
    "position_close": 10,  # Closing a position
    "score_calc": 15,      # Calculating score
    "ai_validation": 30,   # AI DOUBLE_CHECK
}

# Database connection string
DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_db_connection():
    """Get a fresh database connection."""
    return psycopg2.connect(DATABASE_URL)


def ensure_lock_table_exists():
    """Create the sentinel_locks table if it doesn't exist."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS sentinel_locks (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        lock_type VARCHAR(50) NOT NULL,
        process_id VARCHAR(20) NOT NULL,
        acquired_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP NOT NULL,
        UNIQUE(symbol, lock_type)
    );

    CREATE INDEX IF NOT EXISTS idx_sentinel_locks_expires
    ON sentinel_locks(expires_at);
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
            conn.commit()
        logger.debug("sentinel_locks table ready")
    except Exception as e:
        logger.error(f"Error creating sentinel_locks table: {e}")


def ensure_state_table_exists():
    """Create the sentinel_state table for shared state between FAST/SLOW."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS sentinel_state (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        key VARCHAR(100) NOT NULL,
        value TEXT,
        value_numeric DECIMAL(20, 8),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(symbol, key)
    );

    CREATE INDEX IF NOT EXISTS idx_sentinel_state_symbol_key
    ON sentinel_state(symbol, key);
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
            conn.commit()
        logger.debug("sentinel_state table ready")
    except Exception as e:
        logger.error(f"Error creating sentinel_state table: {e}")


class SentinelLock:
    """
    Database-based lock for coordinating SENTINEL-FAST and SENTINEL-SLOW.

    Uses PostgreSQL advisory locks with automatic expiration.
    """

    def __init__(self, symbol: str, lock_type: str, process_id: str = "unknown"):
        """
        Initialize a sentinel lock.

        Args:
            symbol: The trading symbol (BTC, ETH, SOL)
            lock_type: Type of operation (sl_update, position_open, etc.)
            process_id: Identifier for this process (FAST or SLOW)
        """
        self.symbol = symbol.upper()
        self.lock_type = lock_type
        self.process_id = process_id
        self.acquired = False
        self.max_hold_time = LOCK_TYPES.get(lock_type, 10)

    def __enter__(self):
        """Try to acquire the lock."""
        self.acquired = self._try_acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock if we acquired it."""
        if self.acquired:
            self._release()
        return False  # Don't suppress exceptions

    def _try_acquire(self) -> bool:
        """
        Try to acquire the lock using INSERT with ON CONFLICT.

        Returns True if lock acquired, False if already held by another process.
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # First, clean up expired locks
                    cur.execute("""
                        DELETE FROM sentinel_locks
                        WHERE expires_at < NOW()
                    """)

                    # Try to insert our lock
                    expires_at = datetime.now() + timedelta(seconds=self.max_hold_time)

                    cur.execute("""
                        INSERT INTO sentinel_locks (symbol, lock_type, process_id, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (symbol, lock_type) DO UPDATE
                        SET process_id = EXCLUDED.process_id,
                            acquired_at = NOW(),
                            expires_at = EXCLUDED.expires_at
                        WHERE sentinel_locks.expires_at < NOW()
                        RETURNING id
                    """, (self.symbol, self.lock_type, self.process_id, expires_at))

                    result = cur.fetchone()
                    conn.commit()

                    if result:
                        logger.debug(f"🔒 Lock acquired: {self.symbol}/{self.lock_type} by {self.process_id}")
                        return True
                    else:
                        # Lock exists and hasn't expired, check who has it
                        cur.execute("""
                            SELECT process_id, expires_at
                            FROM sentinel_locks
                            WHERE symbol = %s AND lock_type = %s
                        """, (self.symbol, self.lock_type))
                        row = cur.fetchone()
                        if row:
                            logger.debug(f"🔒 Lock busy: {self.symbol}/{self.lock_type} held by {row[0]} until {row[1]}")
                        return False

        except Exception as e:
            logger.error(f"Error acquiring lock {self.symbol}/{self.lock_type}: {e}")
            return False

    def _release(self):
        """Release the lock."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM sentinel_locks
                        WHERE symbol = %s AND lock_type = %s AND process_id = %s
                    """, (self.symbol, self.lock_type, self.process_id))
                conn.commit()
            logger.debug(f"🔓 Lock released: {self.symbol}/{self.lock_type} by {self.process_id}")
        except Exception as e:
            logger.error(f"Error releasing lock {self.symbol}/{self.lock_type}: {e}")


class SentinelState:
    """
    Shared state manager for SENTINEL-FAST and SENTINEL-SLOW.

    Stores values like current_sl_level, last_close_time, etc. in database
    so both processes can access them.
    """

    @staticmethod
    def set(symbol: str, key: str, value: str = None, value_numeric: float = None):
        """Set a state value."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO sentinel_state (symbol, key, value, value_numeric, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (symbol, key) DO UPDATE
                        SET value = EXCLUDED.value,
                            value_numeric = EXCLUDED.value_numeric,
                            updated_at = NOW()
                    """, (symbol.upper(), key, value, value_numeric))
                conn.commit()
        except Exception as e:
            logger.error(f"Error setting state {symbol}/{key}: {e}")

    @staticmethod
    def get(symbol: str, key: str, default=None):
        """Get a state value."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT value, value_numeric
                        FROM sentinel_state
                        WHERE symbol = %s AND key = %s
                    """, (symbol.upper(), key))
                    row = cur.fetchone()
                    if row:
                        # Return numeric if available, otherwise string
                        return row[1] if row[1] is not None else row[0]
                    return default
        except Exception as e:
            logger.error(f"Error getting state {symbol}/{key}: {e}")
            return default

    @staticmethod
    def get_numeric(symbol: str, key: str, default: float = None) -> Optional[float]:
        """Get a numeric state value."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT value_numeric
                        FROM sentinel_state
                        WHERE symbol = %s AND key = %s
                    """, (symbol.upper(), key))
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        return float(row[0])
                    return default
        except Exception as e:
            logger.error(f"Error getting numeric state {symbol}/{key}: {e}")
            return default

    @staticmethod
    def delete(symbol: str, key: str):
        """Delete a state value."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM sentinel_state
                        WHERE symbol = %s AND key = %s
                    """, (symbol.upper(), key))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting state {symbol}/{key}: {e}")

    @staticmethod
    def get_all(symbol: str) -> dict:
        """Get all state values for a symbol."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT key, value, value_numeric
                        FROM sentinel_state
                        WHERE symbol = %s
                    """, (symbol.upper(),))
                    rows = cur.fetchall()
                    result = {}
                    for key, value, value_numeric in rows:
                        result[key] = value_numeric if value_numeric is not None else value
                    return result
        except Exception as e:
            logger.error(f"Error getting all state for {symbol}: {e}")
            return {}


# Initialize tables on import
def init_sentinel_tables():
    """Initialize all sentinel tables."""
    ensure_lock_table_exists()
    ensure_state_table_exists()


# Convenience function for checking if another process is working on a symbol
def is_symbol_busy(symbol: str, lock_types: list = None) -> bool:
    """
    Check if a symbol has any active locks.

    Args:
        symbol: The trading symbol
        lock_types: Optional list of lock types to check (default: all)

    Returns:
        True if any lock is held, False otherwise
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if lock_types:
                    cur.execute("""
                        SELECT COUNT(*) FROM sentinel_locks
                        WHERE symbol = %s AND lock_type = ANY(%s) AND expires_at > NOW()
                    """, (symbol.upper(), lock_types))
                else:
                    cur.execute("""
                        SELECT COUNT(*) FROM sentinel_locks
                        WHERE symbol = %s AND expires_at > NOW()
                    """, (symbol.upper(),))
                count = cur.fetchone()[0]
                return count > 0
    except Exception as e:
        logger.error(f"Error checking if {symbol} is busy: {e}")
        return False


# Signal that SLOW is currently calculating for a symbol (FAST should skip heavy operations)
def signal_slow_active(symbol: str, active: bool = True):
    """Signal that SLOW process is actively working on a symbol."""
    if active:
        SentinelState.set(symbol, "slow_active", "true")
    else:
        SentinelState.delete(symbol, "slow_active")


def is_slow_active(symbol: str) -> bool:
    """Check if SLOW process is actively working on a symbol."""
    return SentinelState.get(symbol, "slow_active") == "true"
