#!/usr/bin/env python3
"""
Trade Journal - Sistema completo di tracking trades, eventi e analisi profittabilità.

Funzionalità:
1. Registra ogni trade completo (apertura → chiusura)
2. Traccia OGNI evento/modifica sulla posizione (SL changes, trailing, etc.)
3. Calcola P&L netto includendo fees
4. Fornisce analytics per ottimizzare i parametri

Tabelle PostgreSQL:
- trades: Un record per ogni trade completo
- trade_events: Ogni singola azione/modifica su un trade
- position_snapshots: Foto della posizione ogni 30 secondi
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import json

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Hyperliquid fee structure (taker fees for market orders)
TAKER_FEE_RATE = Decimal("0.00035")  # 0.035% per side
MAKER_FEE_RATE = Decimal("0.0001")   # 0.01% per side (for limit orders)


# =====================
# Database Schema
# =====================

TRADE_JOURNAL_SCHEMA = """
-- Tabella principale trades: un record per ogni trade completo
CREATE TABLE IF NOT EXISTS trades (
    id                      BIGSERIAL PRIMARY KEY,
    trade_uuid              UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Identificazione
    symbol                  TEXT NOT NULL,
    direction               TEXT NOT NULL,  -- LONG / SHORT
    trading_mode            TEXT NOT NULL,  -- MICRO_GAIN / NORMAL
    status                  TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN / CLOSED

    -- Timestamps
    opened_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at               TIMESTAMPTZ,
    duration_seconds        INTEGER,

    -- Prezzi e Size
    entry_price             NUMERIC(30, 10) NOT NULL,
    exit_price              NUMERIC(30, 10),
    size                    NUMERIC(30, 10) NOT NULL,
    leverage                INTEGER NOT NULL DEFAULT 1,
    notional_value          NUMERIC(30, 10),  -- size * entry_price
    margin_used             NUMERIC(30, 10),  -- notional / leverage

    -- P&L Lordo
    pnl_percent             NUMERIC(10, 4),
    pnl_usd                 NUMERIC(20, 8),

    -- Fees
    fee_open                NUMERIC(20, 8) DEFAULT 0,
    fee_close               NUMERIC(20, 8) DEFAULT 0,
    fee_funding             NUMERIC(20, 8) DEFAULT 0,
    fee_total               NUMERIC(20, 8) DEFAULT 0,

    -- P&L Netto (quello che conta!)
    net_pnl_usd             NUMERIC(20, 8),
    net_pnl_percent         NUMERIC(10, 4),  -- % sul margine usato
    profitable              BOOLEAN,

    -- Chiusura
    close_reason            TEXT,  -- TP_HIT, SL_HIT, TRAILING_SL, AI_DECISION, MANUAL, LIQUIDATION

    -- Indicatori all'apertura
    open_score              NUMERIC(10, 2),
    open_rsi                NUMERIC(10, 4),
    open_macd               NUMERIC(20, 8),
    open_fg                 INTEGER,  -- Fear & Greed
    open_volume_ratio       NUMERIC(10, 4),  -- bid/ask ratio
    -- Nuovi campi per Smart Exit analysis
    open_price_vs_ema20     NUMERIC(10, 4),  -- % distance from EMA20 at open
    open_ema_alignment      TEXT,            -- bullish/bearish/neutral at open
    open_trend_direction    TEXT,            -- UP/DOWN/SIDEWAYS at open
    open_atr                NUMERIC(20, 8),  -- ATR at open time

    -- Indicatori alla chiusura
    close_score             NUMERIC(10, 2),
    close_rsi               NUMERIC(10, 4),
    close_price_vs_ema20    NUMERIC(10, 4),  -- % distance from EMA20 at close

    -- Smart Exit tracking
    exit_warnings           JSONB,           -- warnings active at close time
    cycles_open             INTEGER,         -- number of analysis cycles position was open

    -- Parametri usati
    sl_percent_config       NUMERIC(10, 4),  -- SL configurato
    tp_percent_config       NUMERIC(10, 4),  -- TP configurato
    trailing_activation     NUMERIC(10, 4),  -- Soglia attivazione trailing
    trailing_gap            NUMERIC(10, 4),  -- Gap trailing

    -- Peak tracking
    peak_price              NUMERIC(30, 10),
    peak_pnl_percent        NUMERIC(10, 4),

    -- Metadata
    metadata                JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_trading_mode ON trades(trading_mode);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at);
CREATE INDEX IF NOT EXISTS idx_trades_profitable ON trades(profitable);

-- Tabella eventi: OGNI azione/modifica su un trade
CREATE TABLE IF NOT EXISTS trade_events (
    id                      BIGSERIAL PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trade_uuid              UUID NOT NULL,

    -- Tipo evento
    event_type              TEXT NOT NULL,
    description             TEXT,

    -- Valori prima/dopo (per tracciare cambiamenti)
    old_value               JSONB,
    new_value               JSONB,

    -- Contesto al momento dell'evento
    current_price           NUMERIC(30, 10),
    current_pnl_percent     NUMERIC(10, 4),
    current_score           NUMERIC(10, 2),

    -- Chi ha triggerato
    triggered_by            TEXT DEFAULT 'SYSTEM',  -- SYSTEM / MANUAL / AI

    -- Metadata
    metadata                JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_trade_events_trade_uuid ON trade_events(trade_uuid);
CREATE INDEX IF NOT EXISTS idx_trade_events_event_type ON trade_events(event_type);
CREATE INDEX IF NOT EXISTS idx_trade_events_created_at ON trade_events(created_at);

-- Tabella snapshots: foto della posizione ogni N secondi
CREATE TABLE IF NOT EXISTS trade_snapshots (
    id                      BIGSERIAL PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trade_uuid              UUID NOT NULL,

    -- Stato posizione
    current_price           NUMERIC(30, 10) NOT NULL,
    pnl_percent             NUMERIC(10, 4),
    pnl_usd                 NUMERIC(20, 8),

    -- Indicatori
    score                   NUMERIC(10, 2),
    rsi                     NUMERIC(10, 4),
    macd                    NUMERIC(20, 8),

    -- Trailing state
    trailing_active         BOOLEAN DEFAULT FALSE,
    current_sl_level        NUMERIC(30, 10),
    distance_to_sl_percent  NUMERIC(10, 4)
);

CREATE INDEX IF NOT EXISTS idx_trade_snapshots_trade_uuid ON trade_snapshots(trade_uuid);
CREATE INDEX IF NOT EXISTS idx_trade_snapshots_created_at ON trade_snapshots(created_at);

-- View per analisi rapida
CREATE OR REPLACE VIEW v_trade_summary AS
SELECT
    t.symbol,
    t.trading_mode,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE t.profitable = true) as winning_trades,
    COUNT(*) FILTER (WHERE t.profitable = false) as losing_trades,
    ROUND(100.0 * COUNT(*) FILTER (WHERE t.profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(AVG(t.pnl_percent)::numeric, 4) as avg_pnl_percent,
    ROUND(SUM(t.pnl_usd)::numeric, 2) as total_pnl_usd,
    ROUND(SUM(t.fee_total)::numeric, 2) as total_fees,
    ROUND(SUM(t.net_pnl_usd)::numeric, 2) as total_net_pnl,
    ROUND(AVG(t.duration_seconds)::numeric, 0) as avg_duration_sec
FROM trades t
WHERE t.status = 'CLOSED'
GROUP BY t.symbol, t.trading_mode;

-- View per analisi profittabilità
CREATE OR REPLACE VIEW v_profitability_analysis AS
SELECT
    DATE_TRUNC('day', closed_at) as trade_date,
    trading_mode,
    COUNT(*) as trades,
    ROUND(SUM(pnl_usd)::numeric, 2) as gross_pnl,
    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
    ROUND(100.0 * SUM(fee_total) / NULLIF(ABS(SUM(pnl_usd)), 0), 2) as fees_percent_of_pnl,
    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable) / NULLIF(COUNT(*), 0), 2) as win_rate
FROM trades
WHERE status = 'CLOSED' AND closed_at IS NOT NULL
GROUP BY DATE_TRUNC('day', closed_at), trading_mode
ORDER BY trade_date DESC;
"""


# =====================
# Event Types
# =====================

class EventType:
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    SL_PLACED = "SL_PLACED"
    SL_MODIFIED = "SL_MODIFIED"
    SL_TRIGGERED = "SL_TRIGGERED"
    TP_PLACED = "TP_PLACED"
    TP_MODIFIED = "TP_MODIFIED"
    TP_TRIGGERED = "TP_TRIGGERED"
    TRAILING_ACTIVATED = "TRAILING_ACTIVATED"
    TRAILING_UPDATED = "TRAILING_UPDATED"
    MODE_CHANGED = "MODE_CHANGED"
    SIZE_MODIFIED = "SIZE_MODIFIED"
    SCORE_CHANGED = "SCORE_CHANGED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    CONTROLLER_CHECK = "CONTROLLER_CHECK"


class CloseReason:
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    TRAILING_SL = "TRAILING_SL"
    AI_DECISION = "AI_DECISION"
    MANUAL = "MANUAL"
    LIQUIDATION = "LIQUIDATION"
    REVERSAL = "REVERSAL"


# =====================
# Database Connection
# =====================

@contextmanager
def get_journal_connection():
    """Get database connection for trade journal."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")

    conn = psycopg2.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def init_trade_journal_schema():
    """Initialize trade journal tables."""
    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(TRADE_JOURNAL_SCHEMA)
        conn.commit()
    print("[TradeJournal] Schema initialized")


# =====================
# Trade Management
# =====================

def calculate_fees(notional_value: Decimal, is_taker: bool = True) -> Decimal:
    """Calculate trading fees for one side of the trade."""
    rate = TAKER_FEE_RATE if is_taker else MAKER_FEE_RATE
    return notional_value * rate


def open_trade(
    symbol: str,
    direction: str,
    trading_mode: str,
    entry_price: float,
    size: float,
    leverage: int = 1,
    score: float = None,
    rsi: float = None,
    macd: float = None,
    fg: int = None,
    volume_ratio: float = None,
    sl_percent: float = None,
    tp_percent: float = None,
    trailing_activation: float = None,
    trailing_gap: float = None,
    # Nuovi parametri per Smart Exit analysis
    price_vs_ema20: float = None,
    ema_alignment: str = None,
    trend_direction: str = None,
    atr: float = None,
    metadata: dict = None
) -> str:
    """
    Open a new trade and record it in the journal.
    Returns the trade_uuid.
    """
    trade_uuid = str(uuid.uuid4())

    entry_price_dec = Decimal(str(entry_price))
    size_dec = Decimal(str(size))
    notional = size_dec * entry_price_dec
    margin = notional / Decimal(leverage)
    fee_open = calculate_fees(notional)

    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trades (
                    trade_uuid, symbol, direction, trading_mode, status,
                    entry_price, size, leverage, notional_value, margin_used,
                    fee_open, fee_total,
                    open_score, open_rsi, open_macd, open_fg, open_volume_ratio,
                    open_price_vs_ema20, open_ema_alignment, open_trend_direction, open_atr,
                    sl_percent_config, tp_percent_config, trailing_activation, trailing_gap,
                    peak_price, metadata
                ) VALUES (
                    %s, %s, %s, %s, 'OPEN',
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
            """, (
                trade_uuid, symbol, direction, trading_mode,
                entry_price_dec, size_dec, leverage, notional, margin,
                fee_open, fee_open,
                score, rsi, macd, fg, volume_ratio,
                price_vs_ema20, ema_alignment, trend_direction, atr,
                sl_percent, tp_percent, trailing_activation, trailing_gap,
                entry_price_dec,  # peak starts at entry
                Json(metadata or {})
            ))
        conn.commit()

    # Log opening event
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.POSITION_OPENED,
        description=f"Opened {direction} {symbol} @ {entry_price}",
        current_price=entry_price,
        current_score=score,
        new_value={
            "symbol": symbol,
            "direction": direction,
            "trading_mode": trading_mode,
            "entry_price": entry_price,
            "size": size,
            "leverage": leverage,
            "score": score
        }
    )

    return trade_uuid


def close_trade(
    trade_uuid: str,
    exit_price: float,
    close_reason: str,
    close_score: float = None,
    close_rsi: float = None,
    funding_fees: float = 0,
    # Nuovi parametri per Smart Exit analysis
    close_price_vs_ema20: float = None,
    exit_warnings: list = None,
    cycles_open: int = None
) -> dict:
    """
    Close a trade and calculate final P&L.
    Returns trade summary.
    """
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get trade details
            cur.execute("""
                SELECT * FROM trades WHERE trade_uuid = %s
            """, (trade_uuid,))
            trade = cur.fetchone()

            if not trade:
                raise ValueError(f"Trade {trade_uuid} not found")

            if trade['status'] == 'CLOSED':
                raise ValueError(f"Trade {trade_uuid} already closed")

            # Calculate P&L
            entry_price = Decimal(str(trade['entry_price']))
            exit_price_dec = Decimal(str(exit_price))
            size = Decimal(str(trade['size']))
            direction = trade['direction']
            notional = Decimal(str(trade['notional_value']))
            margin = Decimal(str(trade['margin_used']))

            # P&L calculation
            if direction == 'LONG':
                pnl_usd = (exit_price_dec - entry_price) * size
            else:  # SHORT
                pnl_usd = (entry_price - exit_price_dec) * size

            pnl_percent = (pnl_usd / margin) * 100 if margin else Decimal(0)

            # Fees
            fee_open = Decimal(str(trade['fee_open']))
            fee_close = calculate_fees(size * exit_price_dec)
            fee_funding = Decimal(str(funding_fees))
            fee_total = fee_open + fee_close + fee_funding

            # Net P&L
            net_pnl_usd = pnl_usd - fee_total
            net_pnl_percent = (net_pnl_usd / margin) * 100 if margin else Decimal(0)
            profitable = net_pnl_usd > 0

            # Duration
            opened_at = trade['opened_at']
            closed_at = datetime.now(timezone.utc)
            duration = int((closed_at - opened_at).total_seconds())

            # Update trade
            cur.execute("""
                UPDATE trades SET
                    status = 'CLOSED',
                    exit_price = %s,
                    closed_at = %s,
                    duration_seconds = %s,
                    pnl_percent = %s,
                    pnl_usd = %s,
                    fee_close = %s,
                    fee_funding = %s,
                    fee_total = %s,
                    net_pnl_usd = %s,
                    net_pnl_percent = %s,
                    profitable = %s,
                    close_reason = %s,
                    close_score = %s,
                    close_rsi = %s,
                    close_price_vs_ema20 = %s,
                    exit_warnings = %s,
                    cycles_open = %s
                WHERE trade_uuid = %s
            """, (
                exit_price_dec, closed_at, duration,
                pnl_percent, pnl_usd,
                fee_close, fee_funding, fee_total,
                net_pnl_usd, net_pnl_percent, profitable,
                close_reason, close_score, close_rsi,
                close_price_vs_ema20,
                Json(exit_warnings) if exit_warnings else None,
                cycles_open,
                trade_uuid
            ))
        conn.commit()

    # Log closing event
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.POSITION_CLOSED,
        description=f"Closed @ {exit_price} - {close_reason}",
        current_price=exit_price,
        current_pnl=float(pnl_percent),
        current_score=close_score,
        new_value={
            "exit_price": exit_price,
            "pnl_usd": float(pnl_usd),
            "pnl_percent": float(pnl_percent),
            "fee_total": float(fee_total),
            "net_pnl_usd": float(net_pnl_usd),
            "close_reason": close_reason,
            "duration_seconds": duration
        }
    )

    return {
        "trade_uuid": trade_uuid,
        "symbol": trade['symbol'],
        "direction": direction,
        "pnl_usd": float(pnl_usd),
        "pnl_percent": float(pnl_percent),
        "fee_total": float(fee_total),
        "net_pnl_usd": float(net_pnl_usd),
        "net_pnl_percent": float(net_pnl_percent),
        "profitable": profitable,
        "close_reason": close_reason,
        "duration_seconds": duration
    }


def get_open_trade(symbol: str) -> Optional[dict]:
    """Get open trade for a symbol."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM trades
                WHERE symbol = %s AND status = 'OPEN'
                ORDER BY opened_at DESC
                LIMIT 1
            """, (symbol,))
            return cur.fetchone()


def get_trade_by_uuid(trade_uuid: str) -> Optional[dict]:
    """Get trade by UUID."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM trades WHERE trade_uuid = %s", (trade_uuid,))
            return cur.fetchone()


def update_trade_peak(trade_uuid: str, peak_price: float, peak_pnl_percent: float):
    """Update peak price and P&L for trailing calculation."""
    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE trades SET
                    peak_price = %s,
                    peak_pnl_percent = %s
                WHERE trade_uuid = %s
            """, (peak_price, peak_pnl_percent, trade_uuid))
        conn.commit()


# =====================
# Event Logging
# =====================

def log_event(
    trade_uuid: str,
    event_type: str,
    description: str = None,
    old_value: dict = None,
    new_value: dict = None,
    current_price: float = None,
    current_pnl: float = None,
    current_score: float = None,
    triggered_by: str = "SYSTEM",
    metadata: dict = None
):
    """Log an event for a trade."""
    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_events (
                    trade_uuid, event_type, description,
                    old_value, new_value,
                    current_price, current_pnl_percent, current_score,
                    triggered_by, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade_uuid, event_type, description,
                Json(old_value) if old_value else None,
                Json(new_value) if new_value else None,
                current_price, current_pnl, current_score,
                triggered_by, Json(metadata or {})
            ))
        conn.commit()


def log_sl_placed(trade_uuid: str, sl_price: float, sl_type: str, current_price: float):
    """Log SL order placed."""
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.SL_PLACED,
        description=f"SL placed @ {sl_price} ({sl_type})",
        current_price=current_price,
        new_value={"sl_price": sl_price, "sl_type": sl_type}
    )


def log_sl_modified(trade_uuid: str, old_sl: float, new_sl: float, reason: str, current_price: float, current_pnl: float = None):
    """Log SL modification (trailing, manual, etc.)."""
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.SL_MODIFIED,
        description=f"SL modified: {old_sl} → {new_sl} ({reason})",
        old_value={"sl_price": old_sl},
        new_value={"sl_price": new_sl, "reason": reason},
        current_price=current_price,
        current_pnl=current_pnl
    )


def log_trailing_activated(trade_uuid: str, current_price: float, current_pnl: float, activation_threshold: float):
    """Log trailing SL activation."""
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.TRAILING_ACTIVATED,
        description=f"Trailing activated at P&L {current_pnl:.2f}% (threshold: {activation_threshold}%)",
        current_price=current_price,
        current_pnl=current_pnl,
        new_value={"activation_pnl": current_pnl, "threshold": activation_threshold}
    )


def log_trailing_updated(trade_uuid: str, old_sl: float, new_sl: float, peak_price: float, current_price: float, current_pnl: float):
    """Log trailing SL update."""
    log_event(
        trade_uuid=trade_uuid,
        event_type=EventType.TRAILING_UPDATED,
        description=f"Trailing SL updated: {old_sl} → {new_sl}",
        old_value={"sl_price": old_sl},
        new_value={"sl_price": new_sl, "peak_price": peak_price},
        current_price=current_price,
        current_pnl=current_pnl
    )


def get_trade_events(trade_uuid: str) -> List[dict]:
    """Get all events for a trade."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM trade_events
                WHERE trade_uuid = %s
                ORDER BY created_at ASC
            """, (trade_uuid,))
            return cur.fetchall()


# =====================
# Snapshots
# =====================

def save_snapshot(
    trade_uuid: str,
    current_price: float,
    pnl_percent: float,
    pnl_usd: float = None,
    score: float = None,
    rsi: float = None,
    macd: float = None,
    trailing_active: bool = False,
    current_sl_level: float = None,
    distance_to_sl_percent: float = None
):
    """Save a position snapshot."""
    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_snapshots (
                    trade_uuid, current_price, pnl_percent, pnl_usd,
                    score, rsi, macd,
                    trailing_active, current_sl_level, distance_to_sl_percent
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade_uuid, current_price, pnl_percent, pnl_usd,
                score, rsi, macd,
                trailing_active, current_sl_level, distance_to_sl_percent
            ))
        conn.commit()


# =====================
# Analytics Queries
# =====================

def get_trade_summary(days: int = 30) -> dict:
    """Get trade summary for the last N days."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE profitable = true) as winning_trades,
                    COUNT(*) FILTER (WHERE profitable = false) as losing_trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(pnl_usd)::numeric, 2) as total_gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    ROUND(AVG(pnl_percent)::numeric, 4) as avg_pnl_percent,
                    ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent,
                    ROUND(AVG(duration_seconds)::numeric, 0) as avg_duration_sec
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            return cur.fetchone()


def get_summary_by_mode(days: int = 30) -> List[dict]:
    """Get summary grouped by trading mode."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    trading_mode,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(pnl_usd)::numeric, 2) as gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                    ROUND(AVG(duration_seconds)::numeric, 0) as avg_duration
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY trading_mode
            """, (days,))
            return cur.fetchall()


def get_summary_by_symbol(days: int = 30) -> List[dict]:
    """Get summary grouped by symbol."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                    ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY symbol
            """, (days,))
            return cur.fetchall()


def get_summary_by_score_range(days: int = 30) -> List[dict]:
    """Get summary grouped by score range."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    CASE
                        WHEN ABS(open_score) BETWEEN 15 AND 18 THEN '15-18'
                        WHEN ABS(open_score) BETWEEN 18 AND 22 THEN '18-22'
                        WHEN ABS(open_score) > 22 THEN '22+'
                        ELSE '<15'
                    END as score_range,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND open_score IS NOT NULL
                GROUP BY score_range
                ORDER BY score_range
            """, (days,))
            return cur.fetchall()


def get_fee_analysis(days: int = 30) -> dict:
    """Analyze fee impact."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    ROUND(SUM(pnl_usd)::numeric, 2) as gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                    ROUND(100.0 * SUM(fee_total) / NULLIF(ABS(SUM(pnl_usd)), 0), 2) as fees_percent_of_gross,
                    COUNT(*) FILTER (WHERE pnl_usd > 0 AND net_pnl_usd <= 0) as trades_profitable_before_fees_only,
                    ROUND(AVG(fee_total)::numeric, 4) as avg_fee_per_trade,
                    ROUND(AVG(margin_used)::numeric, 2) as avg_margin,
                    ROUND(100.0 * AVG(fee_total / NULLIF(margin_used, 0)), 4) as avg_fee_percent_of_margin
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            return cur.fetchone()


def get_unprofitable_due_to_fees(days: int = 30) -> List[dict]:
    """Get trades that were profitable before fees but not after."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    trade_uuid, symbol, direction, trading_mode,
                    pnl_usd as gross_pnl,
                    fee_total as fees,
                    net_pnl_usd as net_pnl,
                    margin_used,
                    leverage,
                    duration_seconds
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND pnl_usd > 0
                  AND net_pnl_usd <= 0
                ORDER BY closed_at DESC
            """, (days,))
            return cur.fetchall()


def get_closed_trades(symbol: str = None, days: int = 30) -> List[dict]:
    """
    Get closed trades, optionally filtered by symbol.

    Args:
        symbol: Filter by symbol (optional)
        days: Number of days to look back

    Returns:
        List of closed trade dicts
    """
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if symbol:
                cur.execute("""
                    SELECT * FROM trades
                    WHERE status = 'CLOSED'
                      AND symbol = %s
                      AND closed_at >= NOW() - INTERVAL '%s days'
                    ORDER BY closed_at DESC
                """, (symbol, days))
            else:
                cur.execute("""
                    SELECT * FROM trades
                    WHERE status = 'CLOSED'
                      AND closed_at >= NOW() - INTERVAL '%s days'
                    ORDER BY closed_at DESC
                """, (days,))
            return cur.fetchall()


def get_equity_history(days: int = 7) -> List[dict]:
    """
    Get equity history based on cumulative P&L.

    Returns list of {date, equity, pnl} dicts.
    """
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    DATE_TRUNC('day', closed_at) as trade_date,
                    SUM(net_pnl_usd) as daily_pnl,
                    SUM(SUM(net_pnl_usd)) OVER (ORDER BY DATE_TRUNC('day', closed_at)) as cumulative_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY DATE_TRUNC('day', closed_at)
                ORDER BY trade_date
            """, (days,))
            rows = cur.fetchall()

            # Convert to equity (starting from 100)
            result = []
            base_equity = 100  # Starting equity reference
            for row in rows:
                result.append({
                    "date": row["trade_date"],
                    "daily_pnl": float(row["daily_pnl"] or 0),
                    "equity": base_equity + float(row["cumulative_pnl"] or 0)
                })
            return result


def get_trade_summary_extended(days: int = 30) -> dict:
    """
    Extended trade summary with more metrics for AI context.
    """
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE profitable = true) as winning_trades,
                    COUNT(*) FILTER (WHERE profitable = false) as losing_trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(pnl_usd)::numeric, 2) as total_gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    ROUND(AVG(pnl_percent)::numeric, 4) as avg_pnl_percent,
                    ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent,
                    ROUND(AVG(duration_seconds)::numeric, 0) as avg_duration_sec,
                    -- Additional metrics
                    ROUND(SUM(CASE WHEN profitable THEN net_pnl_usd ELSE 0 END)::numeric, 2) as total_profit,
                    ROUND(SUM(CASE WHEN NOT profitable THEN net_pnl_usd ELSE 0 END)::numeric, 2) as total_loss,
                    ROUND(AVG(CASE WHEN profitable THEN net_pnl_usd END)::numeric, 2) as avg_win,
                    ROUND(AVG(CASE WHEN NOT profitable THEN net_pnl_usd END)::numeric, 2) as avg_loss,
                    ROUND(MAX(net_pnl_usd)::numeric, 2) as max_win,
                    ROUND(MIN(net_pnl_usd)::numeric, 2) as max_loss
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            return cur.fetchone()


def get_summary_by_direction(symbol: str = None, days: int = 30) -> List[dict]:
    """Get summary grouped by direction (LONG/SHORT)."""
    with get_journal_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if symbol:
                cur.execute("""
                    SELECT
                        direction,
                        COUNT(*) as trades,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                        ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                        ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent
                    FROM trades
                    WHERE status = 'CLOSED'
                      AND symbol = %s
                      AND closed_at >= NOW() - INTERVAL '%s days'
                    GROUP BY direction
                """, (symbol, days))
            else:
                cur.execute("""
                    SELECT
                        direction,
                        COUNT(*) as trades,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                        ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                        ROUND(AVG(net_pnl_percent)::numeric, 4) as avg_net_pnl_percent
                    FROM trades
                    WHERE status = 'CLOSED'
                      AND closed_at >= NOW() - INTERVAL '%s days'
                    GROUP BY direction
                """, (days,))
            return cur.fetchall()


def get_suggestions() -> List[str]:
    """Generate optimization suggestions based on data."""
    suggestions = []

    # Get recent data
    summary = get_trade_summary(30)
    by_mode = get_summary_by_mode(30)
    by_score = get_summary_by_score_range(30)
    fee_analysis = get_fee_analysis(30)

    if not summary or summary['total_trades'] == 0:
        return ["Dati insufficienti per generare suggerimenti. Servono più trades."]

    # Fee impact suggestion
    if fee_analysis and fee_analysis['fees_percent_of_gross']:
        fee_pct = float(fee_analysis['fees_percent_of_gross'])
        if fee_pct > 30:
            suggestions.append(f"⚠️ Le fees rappresentano il {fee_pct:.1f}% del P&L lordo. Considera di aumentare il size delle posizioni o ridurre la frequenza dei trades.")

    # Trades unprofitable due to fees
    if fee_analysis and fee_analysis['trades_profitable_before_fees_only']:
        unprofitable_count = fee_analysis['trades_profitable_before_fees_only']
        if unprofitable_count > 0:
            suggestions.append(f"⚠️ {unprofitable_count} trades erano profittevoli prima delle fees ma in perdita dopo. Alza il target profit minimo.")

    # Win rate by score
    for row in by_score or []:
        if row['win_rate'] and float(row['win_rate']) < 50:
            suggestions.append(f"📊 Score range {row['score_range']} ha win rate {row['win_rate']}%. Considera di alzare la soglia minima.")

    # Mode comparison
    mode_data = {m['trading_mode']: m for m in (by_mode or [])}
    if 'MICRO_GAIN' in mode_data and 'NORMAL' in mode_data:
        mg = mode_data['MICRO_GAIN']
        nm = mode_data['NORMAL']
        if mg.get('net_pnl') and nm.get('net_pnl'):
            if float(mg['net_pnl']) > float(nm['net_pnl']) * 1.5:
                suggestions.append("💡 MICRO_GAIN sta performando meglio di NORMAL. Considera di abbassare la soglia NORMAL.")
            elif float(nm['net_pnl']) > float(mg['net_pnl']) * 1.5:
                suggestions.append("💡 NORMAL sta performando meglio di MICRO_GAIN. Considera di alzare la soglia MICRO_GAIN.")

    if not suggestions:
        suggestions.append("✅ Il sistema sta performando nella norma. Continua a monitorare.")

    return suggestions


# =====================
# Database Migration
# =====================

MIGRATION_V2_SMART_EXIT = """
-- Migration V2: Add Smart Exit tracking columns
-- Run this only once to upgrade existing databases

-- Add new columns to trades table (only if they don't exist)
DO $$
BEGIN
    -- Open indicators columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='open_price_vs_ema20') THEN
        ALTER TABLE trades ADD COLUMN open_price_vs_ema20 NUMERIC(10, 4);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='open_ema_alignment') THEN
        ALTER TABLE trades ADD COLUMN open_ema_alignment TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='open_trend_direction') THEN
        ALTER TABLE trades ADD COLUMN open_trend_direction TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='open_atr') THEN
        ALTER TABLE trades ADD COLUMN open_atr NUMERIC(20, 8);
    END IF;

    -- Close indicators columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='close_price_vs_ema20') THEN
        ALTER TABLE trades ADD COLUMN close_price_vs_ema20 NUMERIC(10, 4);
    END IF;

    -- Smart Exit tracking columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='exit_warnings') THEN
        ALTER TABLE trades ADD COLUMN exit_warnings JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='cycles_open') THEN
        ALTER TABLE trades ADD COLUMN cycles_open INTEGER;
    END IF;
END $$;
"""


def run_migration_v2():
    """
    Run migration V2 to add Smart Exit tracking columns.
    Safe to run multiple times - columns won't be added if they already exist.
    """
    with get_journal_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_V2_SMART_EXIT)
        conn.commit()
    print("[TradeJournal] Migration V2 (Smart Exit) completed")


def check_and_run_migrations():
    """
    Check for pending migrations and run them.
    Call this at startup to ensure database schema is up to date.
    """
    try:
        run_migration_v2()
    except Exception as e:
        print(f"[TradeJournal] Migration error: {e}")


# =====================
# Main / Test
# =====================

if __name__ == "__main__":
    print("Initializing Trade Journal schema...")
    init_trade_journal_schema()
    print("Done!")

    print("\nRunning migrations...")
    check_and_run_migrations()
    print("Done!")

    # Test summary
    print("\nTrade Summary (last 30 days):")
    summary = get_trade_summary(30)
    if summary:
        for k, v in summary.items():
            print(f"  {k}: {v}")
