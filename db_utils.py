from __future__ import annotations
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import traceback
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# Import opzionale di numpy per gestire tipi np.float64 / np.int64, ecc.
try:  # pragma: no cover - se numpy non è installato non è un problema
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

load_dotenv()



@dataclass
class DBConfig:
    dsn: str


def get_db_config() -> DBConfig:
    """Recupera la configurazione del DB dalla variabile d'ambiente DATABASE_URL.

    Esempio:
    export DATABASE_URL="postgresql://user:password@localhost:5432/trading_db"
    """

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL non impostata. Imposta la variabile d'ambiente, "
            "ad esempio: postgresql://user:password@localhost:5432/trading_db"
        )
    return DBConfig(dsn=dsn)


@contextmanager
def get_connection():
    """Context manager che restituisce una connessione PostgreSQL.

    Usa il DSN in DATABASE_URL.
    Timeout configurabili da .env:
    - DB_CONNECT_TIMEOUT: timeout connessione in secondi (default 30)
    - DB_QUERY_TIMEOUT: timeout query in millisecondi (default 60000 = 60s)
    """

    config = get_db_config()
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "30"))
    query_timeout = int(os.getenv("DB_QUERY_TIMEOUT", "60000"))

    conn = psycopg2.connect(
        config.dsn,
        connect_timeout=connect_timeout,
        options=f'-c statement_timeout={query_timeout}'
    )
    try:
        yield conn
    finally:
        conn.close()


# =====================
# Creazione schema
# =====================


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance_usd     NUMERIC(20, 8) NOT NULL,
    raw_payload     JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS open_positions (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES account_snapshots(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    side                TEXT NOT NULL,
    size                NUMERIC(30, 10) NOT NULL,
    entry_price         NUMERIC(30, 10),
    mark_price          NUMERIC(30, 10),
    pnl_usd             NUMERIC(30, 10),
    leverage            TEXT,
    raw_payload         JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_open_positions_snapshot_id
    ON open_positions(snapshot_id);


CREATE TABLE IF NOT EXISTS ai_contexts (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_prompt   TEXT
);

CREATE TABLE IF NOT EXISTS indicators_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    ticker                  TEXT NOT NULL,
    ts                      TIMESTAMPTZ,
    price                   NUMERIC(20, 8),
    ema20                   NUMERIC(20, 8),
    macd                    NUMERIC(20, 8),
    rsi_7                   NUMERIC(20, 8),
    volume_bid              NUMERIC(20, 8),
    volume_ask              NUMERIC(20, 8),
    pp                      NUMERIC(20, 8),
    s1                      NUMERIC(20, 8),
    s2                      NUMERIC(20, 8),
    r1                      NUMERIC(20, 8),
    r2                      NUMERIC(20, 8),
    open_interest_latest    NUMERIC(30, 10),
    open_interest_average   NUMERIC(30, 10),
    funding_rate            NUMERIC(20, 8),
    ema20_15m               NUMERIC(20, 8),
    ema50_15m               NUMERIC(20, 8),
    atr3_15m                NUMERIC(20, 8),
    atr14_15m               NUMERIC(20, 8),
    volume_15m_current      NUMERIC(30, 10),
    volume_15m_average      NUMERIC(30, 10),
    intraday_mid_prices     JSONB,
    intraday_ema20_series   JSONB,
    intraday_macd_series    JSONB,
    intraday_rsi7_series    JSONB,
    intraday_rsi14_series   JSONB,
    lt15m_macd_series       JSONB,
    lt15m_rsi14_series      JSONB
);

CREATE TABLE IF NOT EXISTS news_contexts (
    id              BIGSERIAL PRIMARY KEY,
    context_id      BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    news_text       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    value                   INTEGER,
    classification          TEXT,
    sentiment_timestamp     BIGINT,
    raw                     JSONB
);

CREATE TABLE IF NOT EXISTS forecasts_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT NOT NULL REFERENCES ai_contexts(id) ON DELETE CASCADE,
    ticker                  TEXT NOT NULL,
    timeframe               TEXT NOT NULL,
    last_price              NUMERIC(30, 10),
    prediction              NUMERIC(30, 10),
    lower_bound             NUMERIC(30, 10),
    upper_bound             NUMERIC(30, 10),
    change_pct              NUMERIC(10, 4),
    forecast_timestamp      BIGINT,
    raw                     JSONB
);

CREATE TABLE IF NOT EXISTS bot_operations (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id          BIGINT REFERENCES ai_contexts(id) ON DELETE CASCADE,
    operation           TEXT NOT NULL,
    symbol              TEXT,
    direction           TEXT,
    target_portion_of_balance NUMERIC(10, 4),
    leverage            NUMERIC(10, 4),
    raw_payload         JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bot_operations_created_at
    ON bot_operations(created_at);

CREATE TABLE IF NOT EXISTS errors (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_type      TEXT NOT NULL,
    error_message   TEXT,
    traceback       TEXT,
    context         JSONB,
    source          TEXT
);

CREATE INDEX IF NOT EXISTS idx_errors_created_at
    ON errors(created_at);

CREATE TABLE IF NOT EXISTS signal_scores (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id          BIGINT REFERENCES ai_contexts(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    score_bullish       NUMERIC(10, 2) NOT NULL,
    score_bearish       NUMERIC(10, 2) NOT NULL,
    net_score           NUMERIC(10, 2) NOT NULL,
    direction           TEXT NOT NULL,
    confidence          TEXT,
    signals             JSONB NOT NULL,
    thresholds          JSONB,
    weights_config      JSONB
);

CREATE INDEX IF NOT EXISTS idx_signal_scores_created_at
    ON signal_scores(created_at);
CREATE INDEX IF NOT EXISTS idx_signal_scores_symbol
    ON signal_scores(symbol);

CREATE TABLE IF NOT EXISTS position_tracking (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol              TEXT NOT NULL UNIQUE,
    direction           TEXT NOT NULL,
    entry_price         NUMERIC(30, 10) NOT NULL,
    peak_price          NUMERIC(30, 10) NOT NULL,
    trailing_active     BOOLEAN DEFAULT FALSE,
    last_checked_price  NUMERIC(30, 10)
);

CREATE INDEX IF NOT EXISTS idx_position_tracking_symbol
    ON position_tracking(symbol);

CREATE TABLE IF NOT EXISTS sentinel_logs (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol              TEXT NOT NULL,
    direction           TEXT NOT NULL,
    entry_price         NUMERIC(30, 10) NOT NULL,
    current_price       NUMERIC(30, 10) NOT NULL,
    peak_price          NUMERIC(30, 10) NOT NULL,
    profit_pct          NUMERIC(10, 4),
    profit_from_peak_pct NUMERIC(10, 4),
    trailing_active     BOOLEAN DEFAULT FALSE,
    action_taken        TEXT,
    action_reason       TEXT,
    bot_triggered       BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sentinel_logs_created_at
    ON sentinel_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_sentinel_logs_symbol
    ON sentinel_logs(symbol);
"""


MIGRATION_SQL = """
ALTER TABLE bot_operations
    ADD COLUMN IF NOT EXISTS context_id BIGINT;

ALTER TABLE indicators_contexts
    ADD COLUMN IF NOT EXISTS ticker TEXT,
    ADD COLUMN IF NOT EXISTS ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS price NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema20 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS macd NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS rsi_7 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_bid NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_ask NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS pp NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS s1 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS s2 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS r1 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS r2 NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS open_interest_latest NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS open_interest_average NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS funding_rate NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema20_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS ema50_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS atr3_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS atr14_15m NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS volume_15m_current NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS volume_15m_average NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS intraday_mid_prices JSONB,
    ADD COLUMN IF NOT EXISTS intraday_ema20_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_macd_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_rsi7_series JSONB,
    ADD COLUMN IF NOT EXISTS intraday_rsi14_series JSONB,
    ADD COLUMN IF NOT EXISTS lt15m_macd_series JSONB,
    ADD COLUMN IF NOT EXISTS lt15m_rsi14_series JSONB;

ALTER TABLE sentiment_contexts
    ADD COLUMN IF NOT EXISTS value INTEGER,
    ADD COLUMN IF NOT EXISTS classification TEXT,
    ADD COLUMN IF NOT EXISTS sentiment_timestamp BIGINT,
    ADD COLUMN IF NOT EXISTS raw JSONB;

ALTER TABLE forecasts_contexts
    ADD COLUMN IF NOT EXISTS ticker TEXT,
    ADD COLUMN IF NOT EXISTS timeframe TEXT,
    ADD COLUMN IF NOT EXISTS last_price NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS prediction NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS lower_bound NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS upper_bound NUMERIC(30, 10),
    ADD COLUMN IF NOT EXISTS change_pct NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS forecast_timestamp BIGINT,
    ADD COLUMN IF NOT EXISTS raw JSONB;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'indicators_contexts'
          AND column_name = 'indicators'
    ) THEN
        ALTER TABLE indicators_contexts
        ALTER COLUMN indicators DROP NOT NULL;
    END IF;
END$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'sentiment_contexts'
          AND column_name = 'sentiment'
    ) THEN
        ALTER TABLE sentiment_contexts
        ALTER COLUMN sentiment DROP NOT NULL;
    END IF;
END$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'forecasts_contexts'
          AND column_name = 'forecasts'
    ) THEN
        ALTER TABLE forecasts_contexts
        ALTER COLUMN forecasts DROP NOT NULL;
    END IF;
END$$;

-- Migration for sentinel_logs bot_triggered column
ALTER TABLE sentinel_logs
    ADD COLUMN IF NOT EXISTS bot_triggered BOOLEAN DEFAULT FALSE;
"""



def init_db() -> None:
    """Crea le tabelle necessarie nel database se non esistono.

    Da chiamare una volta all'avvio dell'applicazione.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Crea le tabelle base
            cur.execute(SCHEMA_SQL)
            # Applica eventuali migrazioni (aggiunta colonne per input del modello)
            cur.execute(MIGRATION_SQL)
        conn.commit()


# =====================
# Funzioni di logging
# =====================


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_json_arg(value: Any) -> Any:
    """Normalizza un argomento che può essere dict/list oppure stringa JSON.

    - Se è una stringa, prova a fare json.loads; in caso di errore, la incapsula in {"raw": value}
    - Altrimenti la restituisce così com'è.
    """

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {"raw": value}
    return value


def _to_plain_number(value: Any) -> Optional[float]:
    """Converte numeri (inclusi numpy scalars) in float Python.

    Restituisce None se non convertibile.
    """

    if value is None:
        return None

    # Gestione numpy scalars se numpy è disponibile
    if np is not None:  # type: ignore[name-defined]
        try:
            if isinstance(value, np.generic):  # type: ignore[attr-defined]
                return float(value)  # type: ignore[arg-type]
        except Exception:
            pass

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except Exception:
        return None


def _normalize_for_json(value: Any) -> Any:
    """Converte strutture (dict/list) sostituendo eventuali numpy scalars con tipi Python.

    Utile prima di passare a Json(...).
    """

    if isinstance(value, dict):
        return {k: _normalize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_for_json(v) for v in value]

    num = _to_plain_number(value)
    if num is not None:
        return num

    return value


def log_error(
    exc: BaseException,
    *,
    context: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
) -> None:
    """Salva un'eccezione nella tabella `errors`.

    Parametri:
    - exc: eccezione catturata (es. nell'`except Exception as e:`)
    - context: dizionario opzionale con informazioni aggiuntive (verrà salvato come JSONB)
    - source: stringa opzionale per indicare la sorgente (es. "main_loop", "news_feed", ...)

    Uso tipico::

        try:
            ...
        except Exception as e:
            log_error(e, context={"phase": "main_loop"}, source="trading_agent")
            raise
    """

    error_type = type(exc).__name__
    error_message = str(exc)
    tb_str = traceback.format_exc()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO errors (
                    error_type,
                    error_message,
                    traceback,
                    context,
                    source
                )
                VALUES (%s, %s, %s, %s, %s);
                """,
                (
                    error_type,
                    error_message,
                    tb_str,
                    Json(context) if context is not None else None,
                    source,
                ),
            )
        conn.commit()



def log_signal_score(
    symbol: str,
    score_result: Dict[str, Any],
    *,
    context_id: Optional[int] = None,
    weights_config: Optional[Dict[str, Any]] = None,
) -> int:
    """Salva il risultato dello scoring dei segnali nella tabella `signal_scores`.

    Parametri:
    - symbol: simbolo della criptovaluta (BTC, ETH, SOL)
    - score_result: dizionario con i risultati dello scoring da signal_scorer.py
        {
            'score_bullish': float,
            'score_bearish': float,
            'net_score': float,
            'direction': str (LONG/SHORT/HOLD),
            'confidence': str (STRONG/NORMAL/WEAK),
            'signals': list of dicts con dettagli per ogni indicatore,
            'thresholds': dict con le soglie usate
        }
    - context_id: ID del contesto AI (opzionale, per collegare all'operazione)
    - weights_config: configurazione dei pesi usati (opzionale, per tracciabilità)

    Restituisce l'ID del record creato.
    """

    score_bullish = score_result.get('score_bullish', 0)
    score_bearish = score_result.get('score_bearish', 0)
    net_score = score_result.get('net_score', 0)
    direction = score_result.get('direction', 'HOLD')
    confidence = score_result.get('confidence', 'WEAK')
    signals = score_result.get('signals', [])
    thresholds = score_result.get('thresholds', {})

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signal_scores (
                    context_id,
                    symbol,
                    score_bullish,
                    score_bearish,
                    net_score,
                    direction,
                    confidence,
                    signals,
                    thresholds,
                    weights_config
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    context_id,
                    symbol,
                    score_bullish,
                    score_bearish,
                    net_score,
                    direction,
                    confidence,
                    Json(_normalize_for_json(signals)),
                    Json(thresholds) if thresholds else None,
                    Json(weights_config) if weights_config else None,
                ),
            )
            score_id = cur.fetchone()[0]
        conn.commit()

    return score_id


def log_account_status(account_status: Dict[str, Any]) -> int:
    """Logga lo stato dell'account e le posizioni aperte.

    `account_status` è atteso in un formato del tipo:
    {
        "balance_usd": 996.818505,
        "open_positions": [
            {
                "symbol": "BNB",
                "side": "long",
                "size": 0.106,
                "entry_price": 932.54,
                "mark_price": 932.745,
                "pnl_usd": 0.0217,
                "leverage": "2x (cross)",
            },
            ...
        ],
    }

    Restituisce l'ID dello snapshot creato.
    """

    balance = account_status.get("balance_usd")
    if balance is None:
        raise ValueError("account_status deve contenere 'balance_usd'")

    open_positions_data = account_status.get("open_positions") or []

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Inserisci lo snapshot dell'account
            cur.execute(
                """
                INSERT INTO account_snapshots (balance_usd, raw_payload)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (balance, Json(account_status)),
            )
            snapshot_id = cur.fetchone()[0]

            # Inserisci una riga per ciascuna posizione aperta
            for pos in open_positions_data:
                symbol = pos.get("symbol")
                side = pos.get("side")
                size = pos.get("size")
                entry_price = pos.get("entry_price")
                mark_price = pos.get("mark_price")
                pnl_usd = pos.get("pnl_usd")
                leverage = pos.get("leverage")

                cur.execute(
                    """
                    INSERT INTO open_positions (
                        snapshot_id,
                        symbol,
                        side,
                        size,
                        entry_price,
                        mark_price,
                        pnl_usd,
                        leverage,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        snapshot_id,
                        symbol,
                        side,
                        size,
                        entry_price,
                        mark_price,
                        pnl_usd,
                        leverage,
                        Json(pos),
                    ),
                )

        conn.commit()

    return snapshot_id


def log_bot_operation(
    operation_payload: Dict[str, Any],
    *,
    system_prompt: Optional[str] = None,
    indicators: Optional[Any] = None,
    news_text: Optional[str] = None,
    sentiment: Optional[Any] = None,
    forecasts: Optional[Any] = None,
) -> int:
    """Logga un'operazione del bot e tutti gli input associati.

    Modello dati:
    - Crea un record in `ai_contexts` (sempre, anche se alcuni campi sono None)
    - Se presenti, crea record nelle tabelle:
        - `indicators_contexts` (indicators)
        - `news_contexts` (news_text)
        - `sentiment_contexts` (sentiment)
        - `forecasts_contexts` (forecasts)
    - Crea una riga in `bot_operations` collegata via `context_id`.

    Parametri:
    - operation_payload: dict con i campi principali dell'operazione, es:
        {
            "operation": "open",
            "symbol": "BTC",
            "direction": "long",
            "target_portion_of_balance": 0.3,
            "leverage": 3,
            "reason": "...",
            ...
        }
    - system_prompt: stringa con il prompt di sistema completo usato dall'agente
    - indicators: dict/list (o stringa JSON) con gli indici per ticker
    - news_text: testo con le news rilevanti
    - sentiment: dict (o stringa JSON), es: {"valore": 16, "classificazione": "Extreme fear", ...}
    - forecasts: lista/dict (o stringa JSON) con i forecast per ticker/timeframe

    Restituisce l'ID dell'operazione creata.
    """

    operation = operation_payload.get("operation")
    if operation is None:
        raise ValueError("operation_payload deve contenere 'operation'")

    symbol = operation_payload.get("symbol")
    direction = operation_payload.get("direction")
    target_portion_of_balance = operation_payload.get("target_portion_of_balance")
    leverage = operation_payload.get("leverage")

    # indicators_norm = _normalize_json_arg(indicators) if indicators is not None else None
    sentiment_norm = _normalize_json_arg(sentiment) if sentiment is not None else None
    forecasts_norm = _normalize_json_arg(forecasts) if forecasts is not None else None

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1) Crea il contesto generale
            cur.execute(
                """
                INSERT INTO ai_contexts (system_prompt)
                VALUES (%s)
                RETURNING id;
                """,
                (system_prompt,),
            )
            context_id = cur.fetchone()[0]
            if indicators is not None:
                for indicator in indicators:
                    # Skip se indicator non è un dizionario
                    if not isinstance(indicator, dict):
                        print(f"[db_utils] Skipping non-dict indicator: {type(indicator)}")
                        continue
                    indicators_norm = _normalize_json_arg(indicator) if indicator is not None else None

                    # 2) Dettagli per tipo di input, se presenti
                    if indicators_norm is not None:
                        # indicators_norm può essere:
                        # - un dict con chiave "ticker" (un solo ticker)
                        # - un dict {ticker: {...}}
                        # - una lista di dict
                        indicator_items: List[Dict[str, Any]] = []

                        if isinstance(indicators_norm, dict):
                            if "ticker" in indicators_norm:
                                indicator_items = [indicators_norm]
                            else:
                                for tkr, data in indicators_norm.items():
                                    if isinstance(data, dict):
                                        item = {"ticker": tkr}
                                        item.update(data)
                                        indicator_items.append(item)
                        elif isinstance(indicators_norm, list):
                            indicator_items = [x for x in indicators_norm if isinstance(x, dict)]

                        for item in indicator_items:
                            ticker = item.get("ticker")
                            if not ticker:
                                continue

                            ts = None
                            ts_raw = item.get("timestamp")
                            if isinstance(ts_raw, str):
                                try:
                                    ts = datetime.fromisoformat(ts_raw)
                                except Exception:
                                    ts = None

                            current = item.get("current") or {}
                            pivot = item.get("pivot_points") or {}
                            derivatives = item.get("derivatives") or {}
                            intraday = item.get("intraday") or {}
                            lt15 = item.get("longer_term_15m") or {}

                            # Volume: "Bid Vol: 1018.14, Ask Vol: 350.96"
                            volume_str = item.get("volume") or ""
                            volume_bid = None
                            volume_ask = None
                            if isinstance(volume_str, str) and "Bid Vol" in volume_str:
                                try:
                                    parts = volume_str.replace("Bid Vol:", "").split("Ask Vol:")
                                    bid_str = parts[0].strip().strip(",")
                                    ask_str = parts[1].strip()
                                    volume_bid = float(bid_str)
                                    volume_ask = float(ask_str)
                                except Exception:
                                    volume_bid = None
                                    volume_ask = None

                            # CORREZIONE: Query con 30 placeholder correttamente formattati
                            cur.execute(
                                """
                                INSERT INTO indicators_contexts (
                                    context_id,
                                    ticker,
                                    ts,
                                    price,
                                    ema20,
                                    macd,
                                    rsi_7,
                                    volume_bid,
                                    volume_ask,
                                    pp,
                                    s1,
                                    s2,
                                    r1,
                                    r2,
                                    open_interest_latest,
                                    open_interest_average,
                                    funding_rate,
                                    ema20_15m,
                                    ema50_15m,
                                    atr3_15m,
                                    atr14_15m,
                                    volume_15m_current,
                                    volume_15m_average,
                                    intraday_mid_prices,
                                    intraday_ema20_series,
                                    intraday_macd_series,
                                    intraday_rsi7_series,
                                    intraday_rsi14_series,
                                    lt15m_macd_series,
                                    lt15m_rsi14_series
                                )
                                VALUES (
                                    %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s,
                                    %s, %s, %s, %s, %s,
                                    %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s
                                );
                                """,
                                (
                                    context_id,
                                    ticker,
                                    ts,
                                    _to_plain_number(current.get("price")),
                                    _to_plain_number(current.get("ema20")),
                                    _to_plain_number(current.get("macd")),
                                    _to_plain_number(current.get("rsi_7")),
                                    _to_plain_number(volume_bid),
                                    _to_plain_number(volume_ask),
                                    _to_plain_number(pivot.get("pp")),
                                    _to_plain_number(pivot.get("s1")),
                                    _to_plain_number(pivot.get("s2")),
                                    _to_plain_number(pivot.get("r1")),
                                    _to_plain_number(pivot.get("r2")),
                                    _to_plain_number(derivatives.get("open_interest_latest")),
                                    _to_plain_number(derivatives.get("open_interest_average")),
                                    _to_plain_number(derivatives.get("funding_rate")),
                                    _to_plain_number(lt15.get("ema_20_current")),
                                    _to_plain_number(lt15.get("ema_50_current")),
                                    _to_plain_number(lt15.get("atr_3_current")),
                                    _to_plain_number(lt15.get("atr_14_current")),
                                    _to_plain_number(lt15.get("volume_current")),
                                    _to_plain_number(lt15.get("volume_average")),
                                    Json(_normalize_for_json(intraday.get("mid_prices"))) if intraday.get("mid_prices") is not None else None,
                                    Json(_normalize_for_json(intraday.get("ema_20"))) if intraday.get("ema_20") is not None else None,
                                    Json(_normalize_for_json(intraday.get("macd"))) if intraday.get("macd") is not None else None,
                                    Json(_normalize_for_json(intraday.get("rsi_7"))) if intraday.get("rsi_7") is not None else None,
                                    Json(_normalize_for_json(intraday.get("rsi_14"))) if intraday.get("rsi_14") is not None else None,
                                    Json(_normalize_for_json(lt15.get("macd_series"))) if lt15.get("macd_series") is not None else None,
                                    Json(_normalize_for_json(lt15.get("rsi_14_series"))) if lt15.get("rsi_14_series") is not None else None,
                                ),
                            )



            if news_text:
                cur.execute(
                    """
                    INSERT INTO news_contexts (context_id, news_text)
                    VALUES (%s, %s);
                    """,
                    (context_id, news_text),
                )

            if sentiment_norm is not None:
                value = sentiment_norm.get("valore")
                classification = sentiment_norm.get("classificazione")
                ts_raw = sentiment_norm.get("timestamp")
                try:
                    ts_val = int(ts_raw) if ts_raw is not None else None
                except Exception:
                    ts_val = None

                cur.execute(
                    """
                    INSERT INTO sentiment_contexts (context_id, value, classification, sentiment_timestamp, raw)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (context_id, value, classification, ts_val, Json(sentiment_norm)),
                )


            if forecasts_norm is not None:
                forecast_items: List[Dict[str, Any]] = []
                if isinstance(forecasts_norm, list):
                    forecast_items = [x for x in forecasts_norm if isinstance(x, dict)]
                elif isinstance(forecasts_norm, dict):
                    forecast_items = [forecasts_norm]

                for f in forecast_items:
                    ticker = f.get("Ticker") or f.get("ticker")
                    timeframe = f.get("Timeframe") or f.get("timeframe")
                    last_price = f.get("Ultimo Prezzo") or f.get("last_price")
                    prediction = f.get("Previsione") or f.get("prediction")
                    lower = f.get("Limite Inferiore") or f.get("lower_bound")
                    upper = f.get("Limite Superiore") or f.get("upper_bound")
                    change_pct = f.get("Variazione %") or f.get("change_pct")
                    ts_raw = f.get("Timestamp Previsione") or f.get("forecast_timestamp")
                    try:
                        ts_val = int(ts_raw) if ts_raw is not None else None
                    except Exception:
                        ts_val = None

                    if not ticker or not timeframe:
                        continue

                    cur.execute(
                        """
                        INSERT INTO forecasts_contexts (
                            context_id,
                            ticker,
                            timeframe,
                            last_price,
                            prediction,
                            lower_bound,
                            upper_bound,
                            change_pct,
                            forecast_timestamp,
                            raw
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            context_id,
                            ticker,
                            timeframe,
                            _to_plain_number(last_price),
                            _to_plain_number(prediction),
                            _to_plain_number(lower),
                            _to_plain_number(upper),
                            _to_plain_number(change_pct),
                            ts_val,
                            Json(_normalize_for_json(f)),
                        ),
                    )


            # 3) Operazione del bot collegata al contesto
            cur.execute(
                """
                INSERT INTO bot_operations (
                    context_id,
                    operation,
                    symbol,
                    direction,
                    target_portion_of_balance,
                    leverage,
                    raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    context_id,
                    operation,
                    symbol,
                    direction,
                    target_portion_of_balance,
                    leverage,
                    Json(operation_payload),
                ),
            )
            op_id = cur.fetchone()[0]

        conn.commit()

    return op_id




# =====================
# Funzioni di lettura (facoltative ma utili)
# =====================


def get_latest_account_snapshot() -> Optional[Dict[str, Any]]:
    """Restituisce l'ultimo snapshot dell'account (raw_payload) oppure None."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM account_snapshots
                ORDER BY created_at DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0]



def get_recent_bot_operations(limit: int = 50) -> List[Dict[str, Any]]:
    """Restituisce le ultime N operazioni del bot (raw_payload)."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM bot_operations
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [r[0] for r in rows]


# =====================
# Position Tracking per Trailing Stop
# =====================


def get_position_tracking(symbol: str) -> Optional[Dict[str, Any]]:
    """Restituisce il tracking di una posizione per symbol, oppure None se non esiste."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, direction, entry_price, peak_price, trailing_active, last_checked_price, updated_at
                FROM position_tracking
                WHERE symbol = %s;
                """,
                (symbol,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "symbol": row[0],
                "direction": row[1],
                "entry_price": float(row[2]),
                "peak_price": float(row[3]),
                "trailing_active": row[4],
                "last_checked_price": float(row[5]) if row[5] else None,
                "updated_at": row[6],
            }


def upsert_position_tracking(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    trailing_active: bool = False,
) -> Dict[str, Any]:
    """
    Crea o aggiorna il tracking di una posizione.
    Aggiorna peak_price se il prezzo corrente è migliore (più alto per LONG, più basso per SHORT).

    Returns: dict con i dati aggiornati del tracking
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Controlla se esiste già
            cur.execute(
                "SELECT peak_price, direction FROM position_tracking WHERE symbol = %s",
                (symbol,),
            )
            existing = cur.fetchone()

            if existing:
                old_peak = float(existing[0])
                old_direction = existing[1]

                # Calcola nuovo peak_price
                if direction.lower() == 'long':
                    # Per LONG, peak è il massimo
                    new_peak = max(old_peak, current_price)
                else:
                    # Per SHORT, peak è il minimo
                    new_peak = min(old_peak, current_price)

                # Update
                cur.execute(
                    """
                    UPDATE position_tracking
                    SET peak_price = %s,
                        trailing_active = %s,
                        last_checked_price = %s,
                        updated_at = NOW(),
                        direction = %s
                    WHERE symbol = %s
                    RETURNING symbol, direction, entry_price, peak_price, trailing_active;
                    """,
                    (new_peak, trailing_active, current_price, direction, symbol),
                )
            else:
                # Insert nuovo
                cur.execute(
                    """
                    INSERT INTO position_tracking (symbol, direction, entry_price, peak_price, trailing_active, last_checked_price)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING symbol, direction, entry_price, peak_price, trailing_active;
                    """,
                    (symbol, direction, entry_price, current_price, trailing_active, current_price),
                )

            row = cur.fetchone()
        conn.commit()

    return {
        "symbol": row[0],
        "direction": row[1],
        "entry_price": float(row[2]),
        "peak_price": float(row[3]),
        "trailing_active": row[4],
    }


def delete_position_tracking(symbol: str) -> bool:
    """Elimina il tracking di una posizione (da chiamare quando si chiude la posizione)."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM position_tracking WHERE symbol = %s RETURNING id;",
                (symbol,),
            )
            deleted = cur.fetchone()
        conn.commit()

    return deleted is not None


def get_all_position_trackings() -> List[Dict[str, Any]]:
    """Restituisce tutti i tracking attivi."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, direction, entry_price, peak_price, trailing_active, last_checked_price, updated_at
                FROM position_tracking;
                """
            )
            rows = cur.fetchall()

    return [
        {
            "symbol": row[0],
            "direction": row[1],
            "entry_price": float(row[2]),
            "peak_price": float(row[3]),
            "trailing_active": row[4],
            "last_checked_price": float(row[5]) if row[5] else None,
            "updated_at": row[6],
        }
        for row in rows
    ]


# ==================== SENTINEL LOGS ====================

def log_sentinel_check(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    peak_price: float,
    profit_pct: float = None,
    profit_from_peak_pct: float = None,
    trailing_active: bool = False,
    action_taken: str = None,
    action_reason: str = None,
    bot_triggered: bool = False,
) -> int:
    """Logga un controllo sentinel nel database.

    Parametri:
    - symbol: simbolo (BTC, ETH, SOL)
    - direction: direzione posizione (long/short)
    - entry_price: prezzo di entrata
    - current_price: prezzo corrente
    - peak_price: prezzo massimo raggiunto
    - profit_pct: percentuale di profitto dall'entry
    - profit_from_peak_pct: percentuale dal peak (negativo = sceso dal peak)
    - trailing_active: se il trailing stop è attivo
    - action_taken: azione intrapresa (CLOSE_STOP_LOSS, CLOSE_TRAILING_STOP, CLOSE_TAKE_PROFIT, None)
    - action_reason: motivo dell'azione
    - bot_triggered: se il bot principale è stato triggerato per rivalutare

    Restituisce l'ID del record creato.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sentinel_logs (
                    symbol, direction, entry_price, current_price, peak_price,
                    profit_pct, profit_from_peak_pct, trailing_active,
                    action_taken, action_reason, bot_triggered
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    symbol,
                    direction,
                    entry_price,
                    current_price,
                    peak_price,
                    profit_pct,
                    profit_from_peak_pct,
                    trailing_active,
                    action_taken,
                    action_reason,
                    bot_triggered,
                ),
            )
            log_id = cur.fetchone()[0]
        conn.commit()

    return log_id


def get_sentinel_logs(symbol: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Restituisce gli ultimi log sentinel.

    Parametri:
    - symbol: filtra per simbolo (opzionale)
    - limit: numero massimo di record da restituire (default 50)
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            if symbol:
                cur.execute(
                    """
                    SELECT id, created_at, symbol, direction, entry_price, current_price,
                           peak_price, profit_pct, profit_from_peak_pct, trailing_active,
                           action_taken, action_reason, COALESCE(bot_triggered, FALSE)
                    FROM sentinel_logs
                    WHERE symbol = %s
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (symbol, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, created_at, symbol, direction, entry_price, current_price,
                           peak_price, profit_pct, profit_from_peak_pct, trailing_active,
                           action_taken, action_reason, COALESCE(bot_triggered, FALSE)
                    FROM sentinel_logs
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "created_at": row[1],
            "symbol": row[2],
            "direction": row[3],
            "entry_price": float(row[4]),
            "current_price": float(row[5]),
            "peak_price": float(row[6]),
            "profit_pct": float(row[7]) if row[7] else None,
            "profit_from_peak_pct": float(row[8]) if row[8] else None,
            "trailing_active": row[9],
            "action_taken": row[10],
            "action_reason": row[11],
            "bot_triggered": row[12],
        }
        for row in rows
    ]


def get_sentinel_status() -> Dict[str, Any]:
    """Restituisce lo stato del sentinel con statistiche."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Ultimo check
            cur.execute(
                """
                SELECT created_at FROM sentinel_logs
                ORDER BY created_at DESC LIMIT 1;
                """
            )
            last_check_row = cur.fetchone()

            # Conteggio azioni
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_checks,
                    COUNT(action_taken) as total_actions,
                    COUNT(CASE WHEN action_taken = 'CLOSE_STOP_LOSS' THEN 1 END) as stop_loss_count,
                    COUNT(CASE WHEN action_taken = 'CLOSE_TRAILING_STOP' THEN 1 END) as trailing_stop_count,
                    COUNT(CASE WHEN action_taken = 'CLOSE_TAKE_PROFIT' THEN 1 END) as take_profit_count,
                    COUNT(CASE WHEN bot_triggered = TRUE THEN 1 END) as bot_triggered_count
                FROM sentinel_logs
                WHERE created_at > NOW() - INTERVAL '24 hours';
                """
            )
            stats_row = cur.fetchone()

    return {
        "last_check": last_check_row[0] if last_check_row else None,
        "checks_24h": stats_row[0] if stats_row else 0,
        "actions_24h": stats_row[1] if stats_row else 0,
        "stop_loss_24h": stats_row[2] if stats_row else 0,
        "trailing_stop_24h": stats_row[3] if stats_row else 0,
        "take_profit_24h": stats_row[4] if stats_row else 0,
        "bot_triggered_24h": stats_row[5] if stats_row else 0,
    }


if __name__ == "__main__":
    init_db()

    # snapshot_id = log_account_status(example_account_status)
    # print(f"[db_utils] Operazione inserita con id={snapshot_id}")
    # operation
    # op_id = log_bot_operation(
    #     example_operation,
    #     system_prompt=example_system_prompt,
    #     indicators=example_indicators,
    #     news_text=example_news_text,
    #     sentiment=example_sentiment,
    #     forecasts=example_forecasts,
    # )
    # print(f"[db_utils] Operazione inserita con id={op_id}")
