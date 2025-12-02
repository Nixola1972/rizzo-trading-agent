#!/usr/bin/env python3
"""
Trading Bot - Main Entry Point

Supporta due modalità:
1. Single Run: Esegue un ciclo di analisi e termina (per CRON)
2. Autonomous Loop: Gira in loop continuo con intervallo configurabile

Usage:
    python main.py                          # Single run
    python main.py --loop                   # Loop autonomo
    python main.py --loop --interval 15     # Loop con intervallo custom (minuti)
    python main.py --ticker ETH             # Analizza solo ETH
    python main.py --ticker ETH --priority high  # Trigger prioritario (da sentinel)
"""

from indicators import analyze_multiple_tickers
from news_feed import fetch_latest_news
from trading_agent import previsione_trading_agent, get_last_signal_scores, get_scoring_config, SCORING_ENABLED, AI_CALL_INTERVAL_MINUTES
from whalealert import format_whale_alerts_to_string
from sentiment import get_sentiment
from forecaster import get_crypto_forecasts
from hyperliquid_trader import HyperLiquidTrader
import os
import json
import signal
import sys
import time
import argparse
import db_utils
import telegram_notifier as tg
from dotenv import load_dotenv
load_dotenv()

# Trade Journal - Import opzionale per retrocompatibilità
try:
    import trade_journal as tj
    TRADE_JOURNAL_ENABLED = True
except ImportError:
    TRADE_JOURNAL_ENABLED = False
    tj = None

# AI Context Builder - Nuovo modulo per contesto arricchito
try:
    from ai_context import build_full_ai_context, format_context_summary
    AI_CONTEXT_ENABLED = True
except ImportError:
    AI_CONTEXT_ENABLED = False
    print("[WARNING] ai_context.py non trovato, contesto AI ridotto")

# ===== MICRO-GAIN CONFIGURATION =====
MICRO_GAIN_ENABLED = os.getenv('MICRO_GAIN_ENABLED', 'false').lower() == 'true'
MICRO_GAIN_TARGET_PERCENT = float(os.getenv('MICRO_GAIN_TARGET_PERCENT', '0.15'))
MICRO_GAIN_LEVERAGE = int(os.getenv('MICRO_GAIN_LEVERAGE', '5'))
MICRO_GAIN_PORTION = float(os.getenv('MICRO_GAIN_PORTION', '0.3'))
SCORE_THRESHOLD_HOLD = float(os.getenv('SCORE_THRESHOLD_HOLD', '15'))
SCORE_THRESHOLD_NORMAL = float(os.getenv('SCORE_THRESHOLD_OPEN', '20'))  # Soglia per mode NORMAL

# ===== DOUBLE_CHECK AI CONFIGURATION =====
# Quando abilitato, le aperture automatiche (MICRO_GAIN) passano attraverso AI per validazione
DOUBLE_CHECK_AI_ENABLED = os.getenv('DOUBLE_CHECK_AI_ENABLED', 'false').lower() == 'true'
if DOUBLE_CHECK_AI_ENABLED:
    print("🔍 DOUBLE_CHECK_AI: Aperture automatiche validate da AI")

# ===== SMART EXIT CONFIGURATION =====
# Sistema di exit intelligenti basato su regole (EMA invalidation, Score decay, Time stop)
SMART_EXIT_ENABLED = os.getenv('SMART_EXIT_ENABLED', 'true').lower() == 'true'
SMART_EXIT_MODE = os.getenv('SMART_EXIT_MODE', 'warn')  # 'warn' = solo warning, 'hybrid' = warn + confirm
SMART_EXIT_EMA_CHECK = os.getenv('SMART_EXIT_EMA_CHECK', 'true').lower() == 'true'
SMART_EXIT_SCORE_DECAY_CHECK = os.getenv('SMART_EXIT_SCORE_DECAY_CHECK', 'true').lower() == 'true'
SMART_EXIT_TIME_STOP_MINUTES = int(os.getenv('SMART_EXIT_TIME_STOP_MINUTES', '60'))  # 0 = disabilitato
SMART_EXIT_CONFIRM_CYCLES = int(os.getenv('SMART_EXIT_CONFIRM_CYCLES', '2'))  # cicli per conferma in hybrid mode

if SMART_EXIT_ENABLED:
    mode_desc = "WARN-ONLY" if SMART_EXIT_MODE == 'warn' else "HYBRID (warn + confirm)"
    print(f"🚨 SMART_EXIT: {mode_desc}")
    checks = []
    if SMART_EXIT_EMA_CHECK:
        checks.append("EMA")
    if SMART_EXIT_SCORE_DECAY_CHECK:
        checks.append("ScoreDecay")
    if SMART_EXIT_TIME_STOP_MINUTES > 0:
        checks.append(f"TimeStop({SMART_EXIT_TIME_STOP_MINUTES}min)")
    print(f"   Checks attivi: {', '.join(checks)}")

# Score confirmation - richiede N cicli consecutivi sopra soglia prima di aprire
SCORE_CONFIRMATION_CYCLES = int(os.getenv('SCORE_CONFIRMATION_CYCLES', '3'))

# ===== NORMAL MODE TRAILING CONFIGURATION =====
NORMAL_STOP_LOSS_PERCENT = float(os.getenv('NORMAL_STOP_LOSS_PERCENT', '5.0'))
NORMAL_TRAILING_ACTIVATION = float(os.getenv('NORMAL_TRAILING_ACTIVATION', '2.0'))
NORMAL_TRAILING_GAP = float(os.getenv('NORMAL_TRAILING_GAP', '1.5'))

# ===== LOOP AUTONOMO CONFIGURATION =====
DEFAULT_LOOP_INTERVAL_MINUTES = int(os.getenv('AI_CALL_INTERVAL_MINUTES', '15'))
BOT_TIMEOUT_SECONDS = int(os.getenv("BOT_TIMEOUT_SECONDS", "300"))

# ===== MIN HOLD TIME - Previene chiusure premature =====
# L'AI non può chiudere posizioni prima di MIN_HOLD_MINUTES minuti
# Basato su analisi: trades 10-30 min hanno performance migliore (+0.49% avg)
MIN_HOLD_MINUTES = int(os.getenv('MIN_HOLD_MINUTES', '10'))
if MIN_HOLD_MINUTES > 0:
    print(f"⏱️  MIN_HOLD_MINUTES: {MIN_HOLD_MINUTES} min (chiusure AI bloccate prima)")

# ===== AI FREE MODE CONFIGURATION =====
# Quando abilitato, l'AI viene sempre chiamata indipendentemente dallo score
AI_FREE_MODE = os.getenv('AI_FREE_MODE', 'false').lower() == 'true'
MAX_POSITIONS_PER_SYMBOL = int(os.getenv('MAX_POSITIONS_PER_SYMBOL', '1'))
if AI_FREE_MODE:
    print("🆓 AI_FREE_MODE: AI sempre chiamata, score come suggerimento")
if MAX_POSITIONS_PER_SYMBOL > 1:
    print(f"📊 MAX_POSITIONS_PER_SYMBOL: {MAX_POSITIONS_PER_SYMBOL} posizioni per simbolo")

# Hyperliquid Config
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
VERBOSE = os.getenv("VERBOSE", "true").lower() == "true"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")


def determine_trading_mode(net_score: float) -> str:
    """
    Determina il trading mode in base allo score.

    Returns:
        'MICRO_GAIN': Score tra HOLD e NORMAL (es. 15-20)
        'NORMAL': Score >= NORMAL threshold
        'HOLD': Score < HOLD threshold (non dovrebbe arrivare qui)
    """
    if not MICRO_GAIN_ENABLED:
        return "NORMAL"

    abs_score = abs(net_score)

    if abs_score < SCORE_THRESHOLD_HOLD:
        return "HOLD"
    elif abs_score < SCORE_THRESHOLD_NORMAL:
        return "MICRO_GAIN"
    else:
        return "NORMAL"


# ===== ENRICHED AI CONTEXT FUNCTIONS (legacy, ora in ai_context.py) =====
def get_symbol_trade_stats(symbol: str, days: int = 7) -> dict:
    """
    Recupera statistiche storiche per un simbolo dal Trade Journal.
    Aiuta l'AI a capire come sta performando su quel simbolo.
    """
    if not TRADE_JOURNAL_ENABLED:
        return None

    try:
        by_symbol = tj.get_summary_by_symbol(days)
        for stat in by_symbol:
            if stat.get('symbol') == symbol:
                return {
                    "trades_count": stat.get('trades', 0),
                    "win_rate": float(stat.get('win_rate') or 0),
                    "net_pnl_usd": float(stat.get('net_pnl') or 0),
                    "avg_pnl_percent": float(stat.get('avg_net_pnl_percent') or 0),
                    "period_days": days
                }
        return {"trades_count": 0, "win_rate": 0, "net_pnl_usd": 0, "avg_pnl_percent": 0, "period_days": days}
    except Exception as e:
        print(f"[STATS] ⚠️ Errore recupero stats per {symbol}: {e}")
        return None


def get_position_context(symbol: str) -> dict:
    """
    Recupera contesto della posizione aperta: durata, score apertura, peak, etc.
    """
    try:
        tracking = db_utils.get_position_tracking(symbol)
        if not tracking:
            return None

        from datetime import datetime, timezone

        created_at = tracking.get('created_at')
        if created_at:
            # Calcola durata posizione in minuti
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            duration_minutes = int((now - created_at).total_seconds() / 60)
        else:
            duration_minutes = 0

        return {
            "duration_minutes": duration_minutes,
            "entry_price": tracking.get('entry_price'),
            "peak_price": tracking.get('peak_price'),
            "opening_score": tracking.get('opening_score'),
            "trading_mode": tracking.get('trading_mode', 'NORMAL'),
            "trailing_active": tracking.get('trailing_active', False)
        }
    except Exception as e:
        print(f"[CONTEXT] ⚠️ Errore recupero position context per {symbol}: {e}")
        return None


def get_overall_performance(days: int = 7) -> dict:
    """
    Recupera performance complessiva del bot.
    Utile per l'AI per capire se essere più conservativo o aggressivo.
    """
    if not TRADE_JOURNAL_ENABLED:
        return None

    try:
        summary = tj.get_trade_summary(days)
        if not summary:
            return None

        return {
            "total_trades": summary.get('total_trades', 0),
            "win_rate": float(summary.get('win_rate') or 0),
            "total_net_pnl": float(summary.get('total_net_pnl') or 0),
            "avg_pnl_percent": float(summary.get('avg_net_pnl_percent') or 0),
            "avg_duration_minutes": int((summary.get('avg_duration_sec') or 0) / 60),
            "period_days": days
        }
    except Exception as e:
        print(f"[STATS] ⚠️ Errore recupero overall performance: {e}")
        return None


def should_skip_ai_call(symbol: str) -> tuple:
    """
    Controlla se dovremmo saltare la chiamata AI per questo simbolo
    basandosi sull'intervallo configurato AI_CALL_INTERVAL_MINUTES.

    Returns:
        (should_skip: bool, reason: str, minutes_since_last: int)
    """
    from datetime import datetime, timezone

    try:
        # Recupera le ultime operazioni bot per questo simbolo
        recent_ops = db_utils.get_recent_bot_operations(symbol=symbol, limit=1)

        if not recent_ops:
            return (False, "Nessuna operazione precedente", 0)

        last_op = recent_ops[0]
        last_op_time = last_op.get('created_at')

        if not last_op_time:
            return (False, "Timestamp non disponibile", 0)

        # Calcola minuti dall'ultima operazione
        if last_op_time.tzinfo is None:
            last_op_time = last_op_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        minutes_since = int((now - last_op_time).total_seconds() / 60)

        if minutes_since < AI_CALL_INTERVAL_MINUTES:
            return (
                True,
                f"Ultima chiamata AI {minutes_since}min fa (minimo: {AI_CALL_INTERVAL_MINUTES}min)",
                minutes_since
            )

        return (False, f"Passati {minutes_since}min dall'ultima chiamata", minutes_since)

    except Exception as e:
        print(f"[AI_INTERVAL] ⚠️ Errore controllo intervallo per {symbol}: {e}")
        return (False, f"Errore: {e}", 0)


# ===== SMART EXIT WARNING TRACKER =====
# Traccia i warning consecutivi per ogni simbolo (per hybrid mode)
_smart_exit_warning_counts = {}  # {symbol: {warning_type: count}}


def generate_smart_exit_warnings(
    symbol: str,
    position: dict,
    position_context: dict,
    ticker_indicators: dict,
    net_score: float
) -> list:
    """
    Genera warning di Smart Exit per posizioni aperte.

    Args:
        symbol: Simbolo della posizione
        position: Dati posizione da Hyperliquid
        position_context: Contesto posizione da tracking DB
        ticker_indicators: Indicatori tecnici per questo simbolo
        net_score: Score attuale calcolato

    Returns:
        Lista di warning dict: [{"type": "EMA_INVALIDATION", "message": "...", "severity": "warning|critical"}]
    """
    global _smart_exit_warning_counts

    if not SMART_EXIT_ENABLED:
        return []

    warnings = []
    direction = position.get("side", "long").lower()

    # Inizializza tracker per questo simbolo se non esiste
    if symbol not in _smart_exit_warning_counts:
        _smart_exit_warning_counts[symbol] = {}

    # === RULE 1: EMA INVALIDATION ===
    if SMART_EXIT_EMA_CHECK and ticker_indicators:
        try:
            current_price = ticker_indicators.get("current", {}).get("price")
            ema20 = ticker_indicators.get("current", {}).get("ema20")

            if current_price and ema20:
                ema_warning = None

                if direction == "long" and current_price < ema20:
                    pct_below = ((ema20 - current_price) / ema20) * 100
                    ema_warning = {
                        "type": "EMA_INVALIDATION",
                        "message": f"LONG position: Price ${current_price:.2f} is {pct_below:.2f}% BELOW EMA20 (${ema20:.2f})",
                        "severity": "critical" if pct_below > 1.0 else "warning"
                    }
                elif direction == "short" and current_price > ema20:
                    pct_above = ((current_price - ema20) / ema20) * 100
                    ema_warning = {
                        "type": "EMA_INVALIDATION",
                        "message": f"SHORT position: Price ${current_price:.2f} is {pct_above:.2f}% ABOVE EMA20 (${ema20:.2f})",
                        "severity": "critical" if pct_above > 1.0 else "warning"
                    }

                if ema_warning:
                    warnings.append(ema_warning)
                    # Track consecutive warnings
                    _smart_exit_warning_counts[symbol]["EMA_INVALIDATION"] = \
                        _smart_exit_warning_counts[symbol].get("EMA_INVALIDATION", 0) + 1
                else:
                    # Reset counter if no warning
                    _smart_exit_warning_counts[symbol]["EMA_INVALIDATION"] = 0

        except Exception as e:
            print(f"[SMART_EXIT] EMA check error for {symbol}: {e}")

    # === RULE 2: SCORE DECAY ===
    if SMART_EXIT_SCORE_DECAY_CHECK:
        try:
            opening_score = None
            if position_context:
                opening_score = position_context.get("opening_score")

            score_warning = None

            # Score decay: score cambiato segno rispetto alla posizione
            if direction == "long" and net_score < 0:
                score_warning = {
                    "type": "SCORE_DECAY",
                    "message": f"LONG position but score turned NEGATIVE: {net_score:.1f}",
                    "severity": "critical" if net_score < -10 else "warning"
                }
            elif direction == "short" and net_score > 0:
                score_warning = {
                    "type": "SCORE_DECAY",
                    "message": f"SHORT position but score turned POSITIVE: {net_score:.1f}",
                    "severity": "critical" if net_score > 10 else "warning"
                }
            # Score decay significativo rispetto all'apertura
            elif opening_score is not None:
                if direction == "long" and opening_score > 0:
                    decay_pct = ((opening_score - net_score) / abs(opening_score)) * 100 if opening_score != 0 else 0
                    if decay_pct > 50:
                        score_warning = {
                            "type": "SCORE_DECAY",
                            "message": f"LONG: Score decayed {decay_pct:.0f}% from opening ({opening_score:.1f} → {net_score:.1f})",
                            "severity": "warning"
                        }
                elif direction == "short" and opening_score < 0:
                    decay_pct = ((abs(opening_score) - abs(net_score)) / abs(opening_score)) * 100 if opening_score != 0 else 0
                    if decay_pct > 50:
                        score_warning = {
                            "type": "SCORE_DECAY",
                            "message": f"SHORT: Score decayed {decay_pct:.0f}% from opening ({opening_score:.1f} → {net_score:.1f})",
                            "severity": "warning"
                        }

            if score_warning:
                warnings.append(score_warning)
                _smart_exit_warning_counts[symbol]["SCORE_DECAY"] = \
                    _smart_exit_warning_counts[symbol].get("SCORE_DECAY", 0) + 1
            else:
                _smart_exit_warning_counts[symbol]["SCORE_DECAY"] = 0

        except Exception as e:
            print(f"[SMART_EXIT] Score decay check error for {symbol}: {e}")

    # === RULE 3: TIME STOP ===
    if SMART_EXIT_TIME_STOP_MINUTES > 0 and position_context:
        try:
            duration_minutes = position_context.get("duration_minutes", 0)

            if duration_minutes > SMART_EXIT_TIME_STOP_MINUTES:
                # Controlla il P&L per valutare severità
                pnl_pct = position_context.get("unrealized_pnl_pct") or 0

                if pnl_pct < 1.0:  # Meno dell'1% di profitto dopo tanto tempo
                    severity = "critical" if duration_minutes > SMART_EXIT_TIME_STOP_MINUTES * 2 else "warning"
                    time_warning = {
                        "type": "TIME_STOP",
                        "message": f"Position open for {duration_minutes} minutes (limit: {SMART_EXIT_TIME_STOP_MINUTES}) with only {pnl_pct:.2f}% P&L",
                        "severity": severity
                    }
                    warnings.append(time_warning)
                    _smart_exit_warning_counts[symbol]["TIME_STOP"] = \
                        _smart_exit_warning_counts[symbol].get("TIME_STOP", 0) + 1
                else:
                    _smart_exit_warning_counts[symbol]["TIME_STOP"] = 0

        except Exception as e:
            print(f"[SMART_EXIT] Time stop check error for {symbol}: {e}")

    # === CHECK HYBRID MODE: Conferma dopo N cicli consecutivi ===
    confirmed_exits = []
    if SMART_EXIT_MODE == 'hybrid' and warnings:
        for warning in warnings:
            warning_type = warning["type"]
            consecutive_count = _smart_exit_warning_counts[symbol].get(warning_type, 0)

            if consecutive_count >= SMART_EXIT_CONFIRM_CYCLES:
                warning["confirmed"] = True
                warning["consecutive_cycles"] = consecutive_count
                confirmed_exits.append(warning)
                print(f"[SMART_EXIT] 🔴 CONFIRMED: {symbol} {warning_type} after {consecutive_count} cycles")

    return warnings


def clear_smart_exit_warnings(symbol: str):
    """Resetta i warning per un simbolo (chiamare quando posizione chiusa)."""
    global _smart_exit_warning_counts
    if symbol in _smart_exit_warning_counts:
        del _smart_exit_warning_counts[symbol]


# ===== TIMEOUT HANDLER =====
_cycle_timeout_triggered = False

def cycle_timeout_handler(signum, frame):
    """Handler per timeout del singolo ciclo (non uccide il processo in loop mode)."""
    global _cycle_timeout_triggered
    _cycle_timeout_triggered = True
    print(f"⚠️ CYCLE TIMEOUT: Analysis cycle exceeded timeout. Skipping...")
    raise TimeoutError("Analysis cycle timeout")


# ===== MAIN ANALYSIS CYCLE =====
def run_analysis_cycle(
    ticker: str = None,
    reason: str = "scheduled",
    priority: str = "normal",
    timeout_seconds: int = None,
    sentinel_score: float = None
) -> dict:
    """
    Esegue un singolo ciclo di analisi trading.

    Args:
        ticker: Simbolo specifico da analizzare (opzionale, default: tutti)
        reason: Motivo del trigger (scheduled, take_profit, manual, etc.)
        priority: Priorità esecuzione (normal, high)
        timeout_seconds: Timeout per questo ciclo (default: BOT_TIMEOUT_SECONDS)
        sentinel_score: Score già calcolato dalla sentinel (evita ricalcolo, usa prompt libero)

    Returns:
        dict con risultato del ciclo (actions_taken, errors, etc.)
    """
    global _cycle_timeout_triggered
    _cycle_timeout_triggered = False

    # Flag per determinare se usare prompt "libero" (chiamata da sentinel)
    is_sentinel_triggered = sentinel_score is not None and priority == "high"

    result = {
        "success": False,
        "actions_taken": [],
        "errors": [],
        "tickers_analyzed": [],
        "timestamp": None
    }

    from datetime import datetime, timezone
    import time as time_module
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    cycle_start_time = time_module.time()  # Per calcolare durata ciclo

    # Lista per raccogliere tutte le decisioni (per riassunto Telegram)
    all_decisions = []

    # Setup timeout per questo ciclo
    effective_timeout = timeout_seconds or BOT_TIMEOUT_SECONDS
    signal.signal(signal.SIGALRM, cycle_timeout_handler)
    signal.alarm(effective_timeout)

    try:
        if priority == "high":
            if sentinel_score is not None:
                print(f"🚀 SENTINEL TRIGGER: {reason} (score={sentinel_score:.1f})")
                print(f"   📊 Using SENTINEL score - AI will receive liberated prompt")
            else:
                print(f"🚀 PRIORITY EXECUTION: {reason}")

        # Verifica credenziali
        if not PRIVATE_KEY or not WALLET_ADDRESS:
            raise RuntimeError("PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env")

        # Connetti a Hyperliquid
        bot = HyperLiquidTrader(
            secret_key=PRIVATE_KEY,
            account_address=WALLET_ADDRESS,
            testnet=TESTNET
        )

        # Determina tickers da analizzare
        all_tickers = ['BTC', 'ETH', 'SOL']

        if ticker:
            ticker_upper = ticker.upper()
            if ticker_upper in all_tickers:
                tickers = [ticker_upper]
                print(f"🎯 Modalità singolo ticker: {ticker_upper} (reason: {reason})")
            else:
                print(f"⚠️ Ticker {ticker_upper} non supportato. Uso tutti: {all_tickers}")
                tickers = all_tickers
        else:
            tickers = all_tickers

        result["tickers_analyzed"] = tickers

        # Recupera dati di mercato
        print("[STEP 1] Recupero indicatori tecnici...")
        indicators_txt, indicators_json = analyze_multiple_tickers(tickers)

        print("[STEP 2] Recupero news e whale alerts...")
        news_txt = fetch_latest_news()
        whale_alerts_txt = format_whale_alerts_to_string()

        print("[STEP 3] Recupero sentiment e forecast...")
        sentiment_txt, sentiment_json = get_sentiment()
        forecasts_txt, forecasts_json = get_crypto_forecasts()

        # Recupera performance complessiva per contesto AI
        overall_perf = get_overall_performance(days=7)
        if overall_perf:
            print(f"[STATS] 📊 Performance 7gg: {overall_perf['total_trades']} trades, WR {overall_perf['win_rate']:.1f}%, Net P&L ${overall_perf['total_net_pnl']:.2f}")

        # Salva sentiment nella cache per il sentinel
        if sentiment_json:
            try:
                cache_id = db_utils.save_sentiment_cache(
                    value=sentiment_json.get('valore'),
                    classification=sentiment_json.get('classificazione'),
                    source_timestamp=sentiment_json.get('timestamp'),
                    raw=sentiment_json
                )
                print(f"[CACHE] Sentiment salvato in cache con id={cache_id}")
            except Exception as e:
                print(f"[CACHE] ⚠️ Errore salvataggio sentiment cache: {e}")

        # Recupera trend sentiment (confronto con valori precedenti)
        sentiment_trend = db_utils.get_sentiment_trend(hours=6)
        if sentiment_trend:
            print(f"[SENTIMENT] 📈 Trend: {sentiment_trend['trend']} (da {sentiment_trend['previous_value']} a {sentiment_trend['current_value']}, change: {sentiment_trend['change']:+d})")

        msg_info = f"""<indicatori>\n{indicators_txt}\n</indicatori>\n\n
        <news>\n{news_txt}</news>\n\n
        <whale_alerts>\n{whale_alerts_txt}</whale_alerts>\n\n
        <sentiment>\n{sentiment_txt}\n</sentiment>\n\n
        <forecast>\n{forecasts_txt}\n</forecast>\n\n"""

        account_status = bot.get_account_status()
        portfolio_data = f"{json.dumps(account_status)}"
        snapshot_id = db_utils.log_account_status(account_status)
        print(f"[db_utils] Snapshot salvato con id={snapshot_id}")

        # Estrai posizioni aperte per il sistema di trailing stop
        open_positions = account_status.get("open_positions", [])
        open_symbols = [p.get("symbol") for p in open_positions]

        print("L'agente sta decidendo le sue azioni!")

        # ===== CICLO PER OGNI SIMBOLO =====
        # Calcola gli score una volta sola
        from trading_agent import calculate_scores_for_symbols, SCORE_THRESHOLD_OPEN
        scores = calculate_scores_for_symbols(indicators_json, sentiment_json, forecasts_json)

        # Ordina i simboli per forza del segnale (più forte prima)
        symbols_by_strength = sorted(
            tickers,
            key=lambda t: abs(scores.get(t, {}).get('net_score', 0)),
            reverse=True
        )

        print(f"\n📊 Ordine valutazione (per forza segnale): {symbols_by_strength}")

        actions_taken = []

        for ticker_sym in symbols_by_strength:
            score_data = scores.get(ticker_sym, {})
            net_score = score_data.get('net_score', 0)
            direction = score_data.get('direction', 'HOLD')

            # Se sentinel trigger per questo ticker, usa sentinel_score
            if is_sentinel_triggered and ticker and ticker.upper() == ticker_sym:
                net_score = sentinel_score
                direction = "LONG" if sentinel_score > 0 else "SHORT" if sentinel_score < 0 else "HOLD"
                print(f"\n{'='*50}")
                print(f"🚀 SENTINEL: {ticker_sym} usando score sentinel={sentinel_score:.1f} invece di ricalcolato")
            else:
                print(f"\n{'='*50}")

            # Verifica se c'è già una posizione aperta su questo simbolo
            has_position = ticker_sym in open_symbols

            print(f"📈 Valutazione {ticker_sym}: score={net_score:.1f}, direction={direction}, position={'YES' if has_position else 'NO'}")

            # Se c'è già una posizione, gestiscila (HOLD o CLOSE)
            # Se NON c'è posizione e il segnale è forte, considera OPEN
            # Con MICRO_GAIN: apri anche se score è tra HOLD e OPEN threshold
            # Con AI_FREE_MODE: chiama sempre l'AI, non skip mai
            is_micro_gain_candidate = False
            if not has_position:
                min_threshold = SCORE_THRESHOLD_HOLD if MICRO_GAIN_ENABLED else SCORE_THRESHOLD_OPEN
                if abs(net_score) < min_threshold:
                    if AI_FREE_MODE:
                        # AI_FREE_MODE: non skip, passa all'AI con info che score è basso
                        print(f"   🆓 AI_FREE_MODE: {ticker_sym} score={net_score:.1f} (sotto soglia {min_threshold}) → chiamo AI comunque")
                    else:
                        print(f"   ⏭️  Skip {ticker_sym}: no position e score {net_score:.1f} sotto soglia {min_threshold}")
                        continue
                # Marca come candidato MICRO_GAIN (solo se non AI_FREE_MODE)
                if not AI_FREE_MODE and MICRO_GAIN_ENABLED and abs(net_score) < SCORE_THRESHOLD_OPEN:
                    is_micro_gain_candidate = True
                    print(f"   🎯 {ticker_sym}: score {net_score:.1f} in range MICRO_GAIN ({SCORE_THRESHOLD_HOLD}-{SCORE_THRESHOLD_OPEN})")

            # === MICRO_GAIN: Forza OPEN senza chiedere all'AI (a meno che DOUBLE_CHECK sia attivo) ===
            if is_micro_gain_candidate:
                micro_direction = "long" if net_score > 0 else "short"

                # Se DOUBLE_CHECK è attivo, passa all'AI invece di aprire direttamente
                if DOUBLE_CHECK_AI_ENABLED:
                    print(f"   🔍 DOUBLE_CHECK: {ticker_sym} MICRO_GAIN passa a AI per validazione")
                    is_micro_gain_candidate = False  # Disabilita auto-open, farà decidere AI
                    # NON fare continue, lascia proseguire all'AI call sotto

            # Esegue auto-open solo se ancora candidato (DOUBLE_CHECK non attivo)
            if is_micro_gain_candidate:
                micro_direction = "long" if net_score > 0 else "short"
                print(f"   🎯 MICRO_GAIN AUTO-OPEN: {ticker_sym} {micro_direction.upper()} (score={net_score:.1f})")

                out = {
                    "operation": "open",
                    "symbol": ticker_sym,
                    "direction": micro_direction,
                    "reason": f"MICRO_GAIN auto-open: score {net_score:.1f} in range [{SCORE_THRESHOLD_HOLD}-{SCORE_THRESHOLD_OPEN}]",
                    "target_portion_of_balance": MICRO_GAIN_PORTION,
                    "leverage": MICRO_GAIN_LEVERAGE,
                    "trading_mode": "MICRO_GAIN",
                    "opening_score": net_score,
                    "micro_gain_target": MICRO_GAIN_TARGET_PERCENT
                }

                print(f"[EXEC] MICRO_GAIN: Apertura {micro_direction.upper()} su {ticker_sym}...")
                bot.execute_signal(out)
                actions_taken.append(out)

                # Crea tracking per MICRO_GAIN
                try:
                    current_status = bot.get_account_status()
                    for pos in current_status.get("open_positions", []):
                        if pos.get("symbol") == ticker_sym:
                            db_utils.upsert_position_tracking(
                                symbol=pos["symbol"],
                                direction=pos["side"],
                                entry_price=pos["entry_price"],
                                current_price=pos["mark_price"],
                                trailing_active=False,
                                opening_score=net_score,
                                trading_mode="MICRO_GAIN"
                            )
                            print(f"[TRACKING] 🎯 MICRO_GAIN tracking creato per {ticker_sym} @ {pos['entry_price']}")

                            # Trade Journal: registra apertura
                            if TRADE_JOURNAL_ENABLED:
                                try:
                                    trade_uuid = tj.open_trade(
                                        symbol=ticker_sym,
                                        direction=pos["side"].upper(),
                                        trading_mode="MICRO_GAIN",
                                        entry_price=float(pos["entry_price"]),
                                        size=float(pos.get("size", 0)),
                                        leverage=MICRO_GAIN_LEVERAGE,
                                        score=net_score,
                                        sl_percent=float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '3.0')),
                                        tp_percent=MICRO_GAIN_TARGET_PERCENT
                                    )
                                    print(f"[JOURNAL] 📒 Trade registrato: {trade_uuid[:8]}...")
                                except Exception as je:
                                    print(f"[JOURNAL] ⚠️ Errore registrazione trade: {je}")

                            if ticker_sym not in open_symbols:
                                open_symbols.append(ticker_sym)
                            break
                except Exception as e:
                    print(f"[TRACKING] ⚠️ Errore creazione tracking MICRO_GAIN: {e}")

                # Aggiungi a decisioni per riassunto + notifica apertura
                all_decisions.append({
                    "symbol": out.get("symbol"),
                    "operation": out.get("operation"),
                    "direction": out.get("direction", ""),
                    "reason": "MICRO_GAIN auto-open",
                })
                tg.notify_trading_decision(out)  # Notifica apertura
                op_id = db_utils.log_bot_operation(
                    out,
                    system_prompt="MICRO_GAIN auto-open",
                    indicators=[ind for ind in indicators_json if ind.get('ticker') == ticker_sym],
                    news_text=news_txt,
                    sentiment=sentiment_json,
                    forecasts=forecasts_json
                )
                print(f"   💾 Operazione MICRO_GAIN {ticker_sym} salvata con id={op_id}")
                continue  # Passa al prossimo ticker

            # === CONTROLLO INTERVALLO AI ===
            # Salta la chiamata AI se non è passato abbastanza tempo dall'ultima chiamata
            # (solo se NON c'è una posizione aperta da gestire E non è prioritario)
            if not has_position and priority != "high":
                skip_ai, skip_reason, mins_since = should_skip_ai_call(ticker_sym)
                if skip_ai:
                    print(f"   ⏭️  Skip {ticker_sym}: {skip_reason}")
                    continue

            # Costruisci prompt specifico per questo simbolo
            with open('system_prompt_single.txt', 'r') as f:
                system_prompt_template = f.read()

            # Filtra indicatori per questo ticker
            ticker_indicators = [ind for ind in indicators_json if ind.get('ticker') == ticker_sym]
            ticker_forecasts = [fc for fc in forecasts_json if fc.get('Ticker') == ticker_sym or fc.get('ticker') == ticker_sym] if isinstance(forecasts_json, list) else forecasts_json

            # Trova la posizione per questo ticker (se esiste)
            ticker_position = None
            for pos in open_positions:
                if pos.get("symbol") == ticker_sym:
                    ticker_position = pos
                    break

            # === ENRICHED CONTEXT: usa il nuovo modulo ai_context ===
            # Inizializza position_context prima del blocco condizionale
            position_context = None

            if AI_CONTEXT_ENABLED:
                ticker_context = build_full_ai_context(
                    symbol=ticker_sym,
                    indicators_json=indicators_json,
                    sentiment_json=sentiment_json,
                    forecasts_json=forecasts_json,
                    account_status=account_status,
                    position=ticker_position,
                    score_data=score_data
                )
                # Estrai position_context dal ticker_context per il profit-taking
                position_context = ticker_context.get('position_context')
                # Log context summary
                print(f"   📊 {format_context_summary(ticker_context)}")
            else:
                # Fallback: costruisci contesto base
                symbol_stats = get_symbol_trade_stats(ticker_sym, days=7)
                position_context = get_position_context(ticker_sym) if has_position else None

                ticker_context = {
                    "symbol": ticker_sym,
                    "score": score_data,
                    "has_position": has_position,
                    "position": ticker_position,
                    "indicators": ticker_indicators[0] if ticker_indicators else {},
                    "sentiment": sentiment_json,
                    "forecast": ticker_forecasts,
                    "account_balance": account_status.get("balance_usd", 0),
                    "open_positions_count": len(open_positions),
                    "all_open_symbols": open_symbols,
                    "symbol_historical_stats": symbol_stats,
                    "position_context": position_context,
                    "bot_overall_performance": overall_perf,
                    "sentiment_trend": sentiment_trend
                }

            system_prompt = system_prompt_template.format(
                json.dumps(ticker_context, indent=2, default=str),
                msg_info
            )

            # === SMART EXIT WARNINGS: Genera warning per posizioni aperte ===
            smart_exit_warnings = []
            if has_position and ticker_position and SMART_EXIT_ENABLED:
                smart_exit_warnings = generate_smart_exit_warnings(
                    symbol=ticker_sym,
                    position=ticker_position,
                    position_context=position_context,
                    ticker_indicators=ticker_indicators[0] if ticker_indicators else {},
                    net_score=net_score
                )

                if smart_exit_warnings:
                    # Costruisci sezione warning per il prompt
                    warning_lines = []
                    has_critical = any(w.get("severity") == "critical" for w in smart_exit_warnings)
                    has_confirmed = any(w.get("confirmed") for w in smart_exit_warnings)

                    warning_lines.append("")
                    warning_lines.append("## ⚠️ SMART EXIT WARNINGS")
                    warning_lines.append("")

                    for w in smart_exit_warnings:
                        severity_icon = "🔴" if w.get("severity") == "critical" else "🟡"
                        confirmed_tag = " [CONFIRMED]" if w.get("confirmed") else ""
                        warning_lines.append(f"{severity_icon} **{w['type']}**{confirmed_tag}: {w['message']}")

                    warning_lines.append("")
                    warning_lines.append("### What these warnings mean:")
                    warning_lines.append("- **EMA_INVALIDATION**: Price has crossed the EMA20 against your position direction")
                    warning_lines.append("- **SCORE_DECAY**: The trading score has weakened or reversed")
                    warning_lines.append("- **TIME_STOP**: Position open too long with minimal profit")
                    warning_lines.append("")

                    if has_confirmed:
                        warning_lines.append("### ⚠️ CONFIRMED SIGNALS:")
                        warning_lines.append("Some warnings have been confirmed over multiple cycles.")
                        warning_lines.append("This increases the probability that the exit signal is valid.")
                        warning_lines.append("")

                    warning_lines.append("### Your task:")
                    warning_lines.append("Evaluate these warnings alongside other factors (P&L, trend, etc.)")
                    warning_lines.append("and decide whether to CLOSE or HOLD the position.")
                    warning_lines.append("The warnings are informational - you make the final decision.")

                    system_prompt += "\n".join(warning_lines)

                    # Log warnings
                    print(f"   ⚠️ SMART_EXIT: {len(smart_exit_warnings)} warning(s) for {ticker_sym}")
                    for w in smart_exit_warnings:
                        print(f"      - {w['type']}: {w['message'][:60]}...")

            # === AI_FREE_MODE: Aggiungi istruzioni per libertà decisionale ===
            if AI_FREE_MODE:
                free_mode_instructions = """

## 🆓 AI FREE MODE - LIBERTÀ DECISIONALE ATTIVA

IMPORTANTE: Sei in modalità FREE MODE. Le regole sullo score sono DISABILITATE.

### IGNORA QUESTE REGOLE:
- ❌ "If score is weak → do nothing" - IGNORA
- ❌ "If score > threshold → OPEN" - IGNORA
- ❌ "require stronger signals" - IGNORA

### INVECE, DECIDI BASANDOTI SU:
1. **Indicatori Tecnici**: RSI, MACD, EMA alignment, volume
2. **Sentiment di Mercato**: Fear & Greed, whale alerts
3. **Forecast**: Previsioni di prezzo a 15min e 1h
4. **Contesto BTC**: Se BTC è bearish, cautela su altcoin
5. **Risk Metrics**: Exposure attuale, posizioni aperte

### SEI LIBERO DI:
- Aprire posizioni anche con score basso se gli indicatori supportano
- Ignorare lo score se vedi pattern tecnici chiari
- Essere più aggressivo se il contesto lo permette

### LO SCORE È SOLO UN SUGGERIMENTO:
Il net_score nel context è informativo, NON vincolante. Tu decidi.
"""
                system_prompt += free_mode_instructions
                print(f"   🆓 AI_FREE_MODE: Prompt modificato per libertà decisionale")

            # === SENTINEL TRIGGER: Additional context when called by sentinel ===
            if is_sentinel_triggered:
                sentinel_direction = "LONG" if sentinel_score > 0 else "SHORT"
                sentinel_instructions = f"""

## SENTINEL TRIGGER - ADDITIONAL CONTEXT

You have been called by the SENTINEL monitoring system because it detected a potentially significant signal.

### PRE-CALCULATED DATA FROM SENTINEL:
- **Sentinel Score**: {sentinel_score:.1f}
- **Suggested Direction**: {sentinel_direction}
- **Trigger Reason**: {reason}

### CONTEXT:
This score was calculated by the sentinel using real-time market data.
It is provided as additional information for your analysis.

### YOUR TASK:
Analyze the full context (indicators, sentiment, volume, etc.) and make your own independent decision.
The sentinel score is just one data point to consider - you are free to:
- Agree with the suggested direction and OPEN
- Disagree if you see contradicting signals and HOLD
- Make any decision you believe is correct based on your analysis

### KEY QUESTIONS TO CONSIDER:
1. Do the technical indicators (RSI, MACD, EMA) support the {sentinel_direction} direction?
2. Is there any significant contradiction in the data?
3. What does the volume pattern suggest?
4. Is the risk/reward favorable?

You have full autonomy to decide. The sentinel score is informational only.
"""
                system_prompt += sentinel_instructions
                print(f"   🚀 SENTINEL MODE: Additional context provided (score={sentinel_score:.1f}, dir={sentinel_direction})")

            # === PROFIT-TAKING RULES: Aggiungi pressione per prendere profitti ===
            if has_position and ticker_position:
                # Calcola metriche profitto
                entry_price = float(ticker_position.get('entry_price', 0))
                mark_price = float(ticker_position.get('mark_price', 0))
                pnl_usd = float(ticker_position.get('pnl_usd', 0))

                # Parse leverage
                leverage_raw = ticker_position.get('leverage', 1)
                if isinstance(leverage_raw, str):
                    import re
                    match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                    leverage = float(match.group(1)) if match else 1.0
                else:
                    leverage = float(leverage_raw)

                # Calcola P&L %
                direction = ticker_position.get('side', 'long').lower()
                if entry_price > 0:
                    if direction == 'long':
                        price_change = ((mark_price - entry_price) / entry_price) * 100
                    else:
                        price_change = ((entry_price - mark_price) / entry_price) * 100
                    current_pnl_pct = price_change * leverage
                else:
                    current_pnl_pct = 0

                # Recupera max profit dal position context
                max_profit_pct = 0
                duration_minutes = 0
                if position_context:
                    max_profit_pct = position_context.get('max_profit_pct', current_pnl_pct)
                    duration_minutes = position_context.get('duration_minutes', 0)

                # Calcola profit decay
                profit_decay_pct = 0
                if max_profit_pct > 0 and current_pnl_pct < max_profit_pct:
                    profit_decay_pct = ((max_profit_pct - current_pnl_pct) / max_profit_pct) * 100

                # Costruisci warning dinamico
                # NOTA: Fees Hyperliquid ~0.25% round trip (open+close)
                # Quindi profitto netto = profitto lordo - 0.25%
                FEES_ESTIMATE = 0.25  # % stimata per round trip
                net_profit_pct = current_pnl_pct - FEES_ESTIMATE
                profit_warnings = []

                # Warning 1: Profitto SIGNIFICATIVO (>3%) - il trailing dovrebbe gestirlo ma avvisa
                if current_pnl_pct >= 5.0:
                    profit_warnings.append(f"💰 PROFITTO ALTO: +{current_pnl_pct:.1f}% (netto ~{net_profit_pct:.1f}% dopo fees) - Valuta se prendere profitto!")

                # Warning 2: Profit decay CRITICO - stai perdendo troppo dei guadagni
                # Attiva solo se avevi un buon profitto (>3%) e ora stai decadendo
                if max_profit_pct >= 3.0 and profit_decay_pct >= 40:
                    remaining_net = current_pnl_pct - FEES_ESTIMATE
                    profit_warnings.append(f"📉 PROFIT DECAY: Eri a +{max_profit_pct:.1f}%, ora +{current_pnl_pct:.1f}% (perso {profit_decay_pct:.0f}% del profitto!)")

                    # URGENTE se decay > 60% O se il profitto netto sta per andare a zero
                    if profit_decay_pct >= 60:
                        profit_warnings.append(f"⚠️ URGENTE: Hai perso oltre il 60% del profitto! Netto stimato: {remaining_net:.1f}%")
                    elif remaining_net < 0.5:
                        profit_warnings.append(f"⚠️ ATTENZIONE: Profitto netto dopo fees ~{remaining_net:.1f}% - Rischi di andare in pari!")

                # Warning 3: Posizione aperta MOLTO a lungo con profitto discreto
                # Più conservativo: solo dopo 120min e con profitto > 2%
                if duration_minutes >= 120 and current_pnl_pct >= 2.0:
                    profit_warnings.append(f"⏰ TEMPO: Posizione aperta da {duration_minutes} minuti con +{current_pnl_pct:.1f}% - Considera chiusura!")

                # Warning 4: Profitto che sta per essere mangiato dalle fees
                # Se sei tra 0.3% e 0.8%, dopo fees sei quasi a zero
                if 0.3 <= current_pnl_pct < 0.8 and duration_minutes >= 45:
                    profit_warnings.append(f"⚡ ATTENZIONE FEES: Profitto +{current_pnl_pct:.1f}%, dopo fees ~{net_profit_pct:.1f}% - Quasi break-even!")

                # Aggiungi al prompt se ci sono warning
                if profit_warnings:
                    profit_instructions = """

## 💰 PROFIT-TAKING ALERT - LEGGI ATTENTAMENTE!

""" + "\n".join(profit_warnings) + """

### CONSIDERA LE FEES (~0.25% round trip):
- Profitto lordo 0.5% → Netto ~0.25% (quasi break-even)
- Profitto lordo 1% → Netto ~0.75%
- Profitto lordo 3% → Netto ~2.75% (buono!)

### REGOLE PROFIT-TAKING:
1. **Profitto > 5%**: Valuta seriamente di chiudere - è un ottimo risultato
2. **Profit Decay > 60%**: URGENTE - stai perdendo troppo dei guadagni
3. **Profitto < 0.5% dopo tanto tempo**: Le fees mangeranno tutto
4. **Il trailing stop protegge i profitti automaticamente** - questi warning sono per situazioni critiche

### NOTA:
- Il sistema di trailing stop già protegge i profitti
- Questi warning sono per situazioni dove il decay è critico
- Non chiudere prematuramente se il trailing è attivo e il trend è ancora favorevole
"""
                    system_prompt += profit_instructions
                    print(f"   💰 PROFIT ALERT: P&L={current_pnl_pct:+.1f}%, Max={max_profit_pct:.1f}%, Decay={profit_decay_pct:.0f}%")

            # Chiama AI per questo specifico ticker
            out = previsione_trading_agent(
                system_prompt,
                indicators=ticker_indicators,
                sentiment=sentiment_json,
                forecasts=ticker_forecasts,
                open_positions=[ticker_position] if ticker_position else []
            )

            # Forza il simbolo corretto
            out['symbol'] = ticker_sym

            # === AI_FREE_MODE: Log se AI decide diversamente dallo score ===
            if AI_FREE_MODE:
                ai_operation = out.get('operation', 'hold')
                ai_direction = out.get('direction', '')
                score_direction = direction  # dalla valutazione score

                # Verifica se AI ha deciso diversamente dallo score
                if ai_operation == 'open' and score_direction == 'HOLD':
                    print(f"   🆓 FREE MODE: AI ha deciso OPEN {ai_direction} nonostante score={net_score:.1f} (HOLD)")
                elif ai_operation == 'open' and ((ai_direction == 'long' and net_score < 0) or (ai_direction == 'short' and net_score > 0)):
                    print(f"   🆓 FREE MODE: AI ha deciso {ai_direction.upper()} contro direzione score ({net_score:.1f})")
                elif ai_operation != 'hold':
                    print(f"   🆓 FREE MODE: AI decide {ai_operation} {ai_direction} (score suggeriva {score_direction})")

            print(f"   ✅ Decisione per {ticker_sym}: {out.get('operation')} {out.get('direction', '')}")

            # === MIN_HOLD_MINUTES: Blocca chiusure premature ===
            if out.get("operation") == "close" and MIN_HOLD_MINUTES > 0 and position_context:
                pos_duration = position_context.get('duration_minutes', 0)
                if pos_duration < MIN_HOLD_MINUTES:
                    print(f"   ⏱️  BLOCKED: AI vuole chiudere ma posizione aperta solo {pos_duration} min (min: {MIN_HOLD_MINUTES})")
                    print(f"   ➡️  Override: CLOSE → HOLD (attendi ancora {MIN_HOLD_MINUTES - pos_duration} min)")
                    out['operation'] = 'hold'
                    out['reason'] = f"MIN_HOLD override: {pos_duration}/{MIN_HOLD_MINUTES} min"

            # Esegui solo se non è HOLD
            if out.get("operation") != "hold":
                # Determina trading mode per nuove posizioni
                trading_mode = "NORMAL"
                if out.get("operation") == "open":
                    # === VERIFICA CONFERMA CICLI PRIMA DI APRIRE ===
                    # Usa la soglia appropriata basata sul trading mode che useremmo
                    confirmation_threshold = SCORE_THRESHOLD_NORMAL  # Default per NORMAL mode
                    if MICRO_GAIN_ENABLED and abs(net_score) < SCORE_THRESHOLD_NORMAL:
                        confirmation_threshold = SCORE_THRESHOLD_HOLD  # Più bassa per MICRO_GAIN

                    confirmation = db_utils.check_score_confirmation_db(
                        symbol=ticker_sym,
                        threshold=confirmation_threshold,
                        cycles_required=SCORE_CONFIRMATION_CYCLES
                    )

                    if not confirmation["confirmed"]:
                        print(f"   ⏳ {ticker_sym} AI OPEN: waiting confirmation - {confirmation['reason']}")
                        print(f"      Recent DB scores: {[f'{s:.1f}' for s in confirmation['scores']]}")
                        out['operation'] = 'hold'
                        out['reason'] = f"Score confirmation pending: {confirmation['reason']}"
                        continue

                    print(f"   ✅ {ticker_sym} AI OPEN: confirmed ({SCORE_CONFIRMATION_CYCLES} cycles stable)")

                    trading_mode = determine_trading_mode(net_score)
                    out['trading_mode'] = trading_mode
                    out['opening_score'] = net_score
                    if trading_mode == "MICRO_GAIN":
                        out['micro_gain_target'] = MICRO_GAIN_TARGET_PERCENT
                        print(f"   🎯 MICRO_GAIN MODE: target +{MICRO_GAIN_TARGET_PERCENT}% P&L")

                print(f"[EXEC] Esecuzione {out.get('operation')} su {ticker_sym} (mode: {trading_mode})...")
                bot.execute_signal(out)
                actions_taken.append(out)

                # Clear Smart Exit warnings quando posizione viene chiusa
                if out.get("operation") == "close":
                    clear_smart_exit_warnings(ticker_sym)

                # Trade Journal: registra chiusura PRIMA di eliminare tracking
                if out.get("operation") == "close" and TRADE_JOURNAL_ENABLED:
                    try:
                        open_trade = tj.get_open_trade(ticker_sym)
                        if open_trade:
                            # Usa mark_price catturato PRIMA della chiusura (da ticker_position)
                            # Non possiamo prenderlo da open_positions perché la posizione è già chiusa!
                            if ticker_position and 'mark_price' in ticker_position:
                                exit_price = float(ticker_position.get('mark_price', 0))
                                print(f"[JOURNAL] 📍 Exit price da ticker_position: ${exit_price:.2f}")
                            else:
                                # Fallback: prova a ottenere da tracking o entry
                                tracking = db_utils.get_position_tracking(ticker_sym)
                                if tracking and tracking.get('current_price'):
                                    exit_price = float(tracking.get('current_price'))
                                    print(f"[JOURNAL] 📍 Exit price da tracking: ${exit_price:.2f}")
                                else:
                                    exit_price = float(open_trade.get('entry_price', 0))
                                    print(f"[JOURNAL] ⚠️ Exit price fallback a entry: ${exit_price:.2f}")

                            result_close = tj.close_trade(
                                trade_uuid=open_trade['trade_uuid'],
                                exit_price=exit_price,
                                close_reason=tj.CloseReason.AI_DECISION,
                                close_score=net_score if net_score else None
                            )
                            print(f"[JOURNAL] 📒 Trade chiuso: Net P&L ${result_close['net_pnl_usd']:.2f}")
                    except Exception as je:
                        print(f"[JOURNAL] ⚠️ Errore chiusura trade: {je}")

                # Gestisci tracking
                if out.get("_delete_tracking") and out.get("symbol"):
                    try:
                        deleted = db_utils.delete_position_tracking(out["symbol"])
                        if deleted:
                            print(f"[TRACKING] ✅ Tracking eliminato per {out['symbol']}")
                    except Exception as e:
                        print(f"[TRACKING] ⚠️ Errore eliminazione tracking: {e}")

                if out.get("operation") == "open":
                    try:
                        current_status = bot.get_account_status()
                        for pos in current_status.get("open_positions", []):
                            if pos.get("symbol") == out["symbol"]:
                                db_utils.upsert_position_tracking(
                                    symbol=pos["symbol"],
                                    direction=pos["side"],
                                    entry_price=pos["entry_price"],
                                    current_price=pos["mark_price"],
                                    trailing_active=False,
                                    opening_score=net_score,
                                    trading_mode=trading_mode
                                )
                                mode_emoji = "🎯" if trading_mode == "MICRO_GAIN" else "📊"
                                print(f"[TRACKING] {mode_emoji} Tracking creato per {out['symbol']} @ {pos['entry_price']} (mode: {trading_mode}, score: {net_score:.1f})")

                                # Trade Journal: registra apertura
                                if TRADE_JOURNAL_ENABLED:
                                    try:
                                        # Parametri diversi per MICRO_GAIN vs NORMAL
                                        if trading_mode == "MICRO_GAIN":
                                            sl_pct = float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '3.0'))
                                            tp_pct = MICRO_GAIN_TARGET_PERCENT
                                            trailing_act = float(os.getenv('MICRO_GAIN_TRAILING_ACTIVATION', '0.5'))
                                            trailing_g = float(os.getenv('MICRO_GAIN_TRAILING_GAP', '0.5'))
                                        else:
                                            sl_pct = NORMAL_STOP_LOSS_PERCENT
                                            tp_pct = None
                                            trailing_act = NORMAL_TRAILING_ACTIVATION
                                            trailing_g = NORMAL_TRAILING_GAP

                                        trade_uuid = tj.open_trade(
                                            symbol=ticker_sym,
                                            direction=pos["side"].upper(),
                                            trading_mode=trading_mode,
                                            entry_price=float(pos["entry_price"]),
                                            size=float(pos.get("size", 0)),
                                            leverage=int(out.get("leverage", MICRO_GAIN_LEVERAGE if trading_mode == "MICRO_GAIN" else 1)),
                                            score=net_score,
                                            sl_percent=sl_pct,
                                            tp_percent=tp_pct,
                                            trailing_activation=trailing_act,
                                            trailing_gap=trailing_g
                                        )
                                        print(f"[JOURNAL] 📒 Trade registrato: {trade_uuid[:8]}... (mode: {trading_mode})")
                                    except Exception as je:
                                        print(f"[JOURNAL] ⚠️ Errore registrazione trade: {je}")

                                # Aggiorna open_symbols per il prossimo ciclo
                                if out["symbol"] not in open_symbols:
                                    open_symbols.append(out["symbol"])
                                break
                    except Exception as e:
                        print(f"[TRACKING] ⚠️ Errore creazione tracking: {e}")

            # Raccogli decisione per riassunto (notifica singola solo per OPEN)
            all_decisions.append({
                "symbol": out.get("symbol"),
                "operation": out.get("operation"),
                "direction": out.get("direction", ""),
                "reason": out.get("reason", "")[:100],
            })

            # Notifica singola SOLO per aperture (importanti da sapere subito)
            if out.get("operation") == "open":
                tg.notify_trading_decision(out)

            # Salva operazione nel DB
            op_id = db_utils.log_bot_operation(
                out,
                system_prompt=system_prompt,
                indicators=ticker_indicators,
                news_text=news_txt,
                sentiment=sentiment_json,
                forecasts=ticker_forecasts
            )
            print(f"   💾 Operazione {ticker_sym} salvata con id={op_id}")

        # ===== FINE CICLO =====

        print(f"\n{'='*50}")
        print(f"📊 Riepilogo: {len(actions_taken)} azioni eseguite")
        for action in actions_taken:
            print(f"   - {action.get('operation')} {action.get('symbol')} {action.get('direction', '')}")

        # Salva signal scores nel database per tracciabilità (usa gli score calcolati all'inizio)
        if SCORING_ENABLED:
            print("\n[STEP FINAL] Salvataggio signal scores...")
            weights_config = get_scoring_config()
            for symbol, score_result in scores.items():
                try:
                    score_id = db_utils.log_signal_score(
                        symbol=symbol,
                        score_result=score_result,
                        weights_config=weights_config
                    )
                    print(f"   Signal score {symbol} salvato con id={score_id}")
                except Exception as e:
                    print(f"   Errore salvataggio score {symbol}: {e}")

        result["success"] = True
        result["actions_taken"] = actions_taken

        # === NOTIFICA RIASSUNTO CICLO AI ===
        try:
            cycle_duration = time_module.time() - cycle_start_time

            # Prepara scores per il riassunto
            scores_for_summary = {}
            if SCORING_ENABLED and scores:
                for sym, score_data in scores.items():
                    scores_for_summary[sym] = {
                        "net": score_data.get("net_score", 0),
                        "bull": score_data.get("bull_score", 0),
                        "bear": score_data.get("bear_score", 0),
                    }

            # Recupera info account
            try:
                account_status = bot.get_account_status()
                balance = account_status.get("balance", 0)
                open_pos_count = len(account_status.get("open_positions", []))
            except:
                balance = None
                open_pos_count = None

            # Invia riassunto
            tg.notify_ai_cycle_summary(
                reason=reason,
                tickers_analyzed=tickers,
                decisions=all_decisions,
                scores=scores_for_summary,
                duration_seconds=cycle_duration,
                balance=balance,
                open_positions=open_pos_count,
            )
        except Exception as e:
            print(f"[TELEGRAM] ⚠️ Errore invio riassunto: {e}")

    except TimeoutError:
        result["errors"].append(f"Cycle timeout after {effective_timeout}s")
        print(f"⚠️ Ciclo terminato per timeout")

    except Exception as e:
        result["errors"].append(str(e))
        # Notifica errore su Telegram
        tg.notify_error(type(e).__name__, str(e), source="trading_agent")

        db_utils.log_error(e, context={
            "tickers": tickers if 'tickers' in dir() else [],
            "reason": reason,
            "priority": priority
        }, source="trading_agent")
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Disabilita alarm
        signal.alarm(0)

    return result


# ===== AUTONOMOUS LOOP =====
def run_autonomous_loop(interval_minutes: int = None):
    """
    Esegue il bot in loop continuo con intervallo configurabile.

    Args:
        interval_minutes: Intervallo tra i cicli in minuti (default: AI_CALL_INTERVAL_MINUTES)
    """
    interval = interval_minutes or DEFAULT_LOOP_INTERVAL_MINUTES
    interval_seconds = interval * 60

    print("=" * 60)
    print("🔄 AUTONOMOUS LOOP MODE")
    print("=" * 60)
    print(f"   Intervallo: {interval} minuti")
    print(f"   Timeout per ciclo: {BOT_TIMEOUT_SECONDS} secondi")
    print(f"   MICRO_GAIN: {'ENABLED' if MICRO_GAIN_ENABLED else 'DISABLED'}")
    print(f"   Testnet: {'YES' if TESTNET else 'NO'}")
    print("=" * 60)

    cycle_count = 0
    errors_count = 0
    max_consecutive_errors = 5

    try:
        while True:
            cycle_count += 1
            print(f"\n{'='*60}")
            print(f"🔄 CICLO #{cycle_count} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            try:
                result = run_analysis_cycle(
                    ticker=None,
                    reason="autonomous_loop",
                    priority="normal",
                    timeout_seconds=BOT_TIMEOUT_SECONDS
                )

                if result["success"]:
                    errors_count = 0  # Reset error counter on success
                    print(f"✅ Ciclo #{cycle_count} completato con successo")
                else:
                    errors_count += 1
                    print(f"⚠️ Ciclo #{cycle_count} completato con errori: {result['errors']}")

            except Exception as e:
                errors_count += 1
                print(f"❌ Errore nel ciclo #{cycle_count}: {e}")
                import traceback
                traceback.print_exc()

                # Se troppi errori consecutivi, notifica e rallenta
                if errors_count >= max_consecutive_errors:
                    print(f"🚨 {errors_count} errori consecutivi! Rallento l'esecuzione...")
                    tg.send_telegram_message(
                        f"🚨 <b>BOT ALERT</b>\n\n"
                        f"{errors_count} errori consecutivi nel loop autonomo.\n"
                        f"Ultimo errore: {str(e)[:200]}"
                    )
                    # Aspetta il doppio del tempo
                    time.sleep(interval_seconds)

            # Aspetta prima del prossimo ciclo
            print(f"💤 Prossimo ciclo tra {interval} minuti...")
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("\n\n🛑 Loop interrotto (Ctrl+C)")
        print(f"   Cicli completati: {cycle_count}")
        print(f"   Errori totali: {errors_count}")


# ===== MAIN ENTRY POINT =====
def main():
    """Entry point principale."""
    parser = argparse.ArgumentParser(
        description="Trading Bot - Analisi e trading automatico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
    python main.py                          # Single run (tutti i ticker)
    python main.py --ticker ETH             # Analizza solo ETH
    python main.py --loop                   # Loop autonomo
    python main.py --loop --interval 10     # Loop ogni 10 minuti
    python main.py --ticker BTC --priority high  # Trigger prioritario
        """
    )
    parser.add_argument("--ticker", type=str, help="Analizza solo questo ticker (es: ETH)")
    parser.add_argument("--reason", type=str, default="manual", help="Motivo trigger (es: take_profit, manual)")
    parser.add_argument("--loop", action="store_true", help="Esegui in loop autonomo continuo")
    parser.add_argument("--interval", type=int, default=None, help="Intervallo loop in minuti (default: AI_CALL_INTERVAL_MINUTES)")
    parser.add_argument("--priority", type=str, default="normal", choices=["normal", "high"], help="Priorità esecuzione")
    parser.add_argument("--sentinel-score", type=float, default=None, help="Score calcolato dalla sentinel (evita ricalcolo)")

    args = parser.parse_args()

    print("=" * 60)
    print("🤖 TRADING BOT STARTED")
    print("=" * 60)
    print(f"⏱️  AI call interval: {AI_CALL_INTERVAL_MINUTES} minutes")
    print(f"⏱️  Bot timeout: {BOT_TIMEOUT_SECONDS} seconds")
    print(f"🌐 Testnet: {'YES' if TESTNET else 'NO'}")
    print(f"📊 AI Context Module: {'ENABLED' if AI_CONTEXT_ENABLED else 'DISABLED'}")
    print("=" * 60)

    if args.loop:
        # Modalità loop autonomo
        run_autonomous_loop(interval_minutes=args.interval)
    else:
        # Modalità single run
        sentinel_score = getattr(args, 'sentinel_score', None)
        result = run_analysis_cycle(
            ticker=args.ticker,
            reason=args.reason,
            priority=args.priority,
            sentinel_score=sentinel_score
        )

        if not result["success"]:
            print(f"\n⚠️ Ciclo terminato con errori: {result['errors']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
