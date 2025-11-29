#!/usr/bin/env python3
"""
Sentinel - Monitoraggio continuo trailing stop e stop loss.

Script leggero che gira frequentemente (ogni 1-2 minuti) per:
1. Controllare i prezzi correnti delle posizioni aperte
2. Aggiornare il peak_price nel database
3. Chiudere posizioni se trailing stop o stop loss viene triggerato

NON fa:
- Chiamate AI
- Calcolo indicatori
- Analisi di mercato

Uso:
    python sentinel.py              # Esegue un singolo controllo
    python sentinel.py --loop       # Esegue in loop continuo
    python sentinel.py --interval 60  # Loop con intervallo personalizzato
"""

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Trade Journal - Import opzionale per retrocompatibilità
try:
    import trade_journal as tj
    TRADE_JOURNAL_ENABLED = True
except ImportError:
    TRADE_JOURNAL_ENABLED = False
    tj = None

# Database Utils - Import opzionale
try:
    import db_utils
    DB_UTILS_ENABLED = True
except ImportError:
    DB_UTILS_ENABLED = False
    db_utils = None

# Configurazione
SENTINEL_ENABLED = os.getenv('SENTINEL_ENABLED', 'true').lower() == 'true'
SENTINEL_INTERVAL = int(os.getenv('SENTINEL_INTERVAL_SECONDS', '60'))
SENTINEL_TELEGRAM_NOTIFY = os.getenv('SENTINEL_TELEGRAM_NOTIFY', 'true').lower() == 'true'

# Trailing Stop Config
TRAILING_STOP_ENABLED = os.getenv('TRAILING_STOP_ENABLED', 'true').lower() == 'true'
TRAILING_STOP_PERCENT = float(os.getenv('TRAILING_STOP_PERCENT', '7'))
TRAILING_STOP_ACTIVATION_PERCENT = float(os.getenv('TRAILING_STOP_ACTIVATION_PERCENT', '3'))
INITIAL_STOP_LOSS_PERCENT = float(os.getenv('INITIAL_STOP_LOSS_PERCENT', '10'))

# Take Profit Config
TAKE_PROFIT_ENABLED = os.getenv('TAKE_PROFIT_ENABLED', 'true').lower() == 'true'
TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '5'))
TAKE_PROFIT_TRIGGER_BOT = os.getenv('TAKE_PROFIT_TRIGGER_BOT', 'true').lower() == 'true'

# Hyperliquid Config
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

# MICRO_GAIN Config
MICRO_GAIN_ENABLED = os.getenv('MICRO_GAIN_ENABLED', 'false').lower() == 'true'
MICRO_GAIN_REVERSAL_SCORE = float(os.getenv('MICRO_GAIN_REVERSAL_SCORE', '5'))

# MICRO_GAIN Auto-Open Config (Sentinel gestisce apertura)
MICRO_GAIN_AUTO_OPEN = os.getenv('MICRO_GAIN_AUTO_OPEN', 'false').lower() == 'true'
MICRO_GAIN_TARGET_PERCENT = float(os.getenv('MICRO_GAIN_TARGET_PERCENT', '3.0'))  # TP: chiudi quando guadagni questo %
MICRO_GAIN_STOP_LOSS_PERCENT = float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '3.0'))  # SL iniziale: perdi max questo %
MICRO_GAIN_TRAILING_GAP = float(os.getenv('MICRO_GAIN_TRAILING_GAP', '0.5'))  # SL segue P&L con questo gap
MICRO_GAIN_TRAILING_ACTIVATION = float(os.getenv('MICRO_GAIN_TRAILING_ACTIVATION', '0.5'))  # Trailing parte quando P&L >= questo
MICRO_GAIN_COOLDOWN_SECONDS = int(os.getenv('MICRO_GAIN_COOLDOWN_SECONDS', '300'))  # Attesa dopo chiusura
MICRO_GAIN_MAX_POSITIONS = int(os.getenv('MICRO_GAIN_MAX_POSITIONS', '3'))  # Max posizioni contemporanee
SCORE_THRESHOLD_HOLD = float(os.getenv('SCORE_THRESHOLD_HOLD', '10'))
SCORE_THRESHOLD_OPEN = float(os.getenv('SCORE_THRESHOLD_OPEN', '20'))
MICRO_GAIN_LEVERAGE = int(os.getenv('MICRO_GAIN_LEVERAGE', '5'))
MICRO_GAIN_PORTION = float(os.getenv('MICRO_GAIN_PORTION', '0.3'))  # % balance per posizione

# MICRO_GAIN Trailing Mode Config
# Modalità: "continuous" (classico), "steps" (gradini), "disable" (disabilitato)
MICRO_GAIN_TRAILING_MODE = os.getenv('MICRO_GAIN_TRAILING_MODE', 'continuous')
MICRO_GAIN_TRAILING_STEPS_STR = os.getenv('MICRO_GAIN_TRAILING_STEPS', '1:0,2:1,3:2')

# ===== MICRO_PAY CONFIG =====
# Modalità ultra-micro per score deboli (5-15) - molti trade piccoli
# Se disabilitato, HOLD si estende fino a SCORE_THRESHOLD_HOLD
MICRO_PAY_ENABLED = os.getenv('MICRO_PAY_ENABLED', 'false').lower() == 'true'
MICRO_PAY_THRESHOLD = float(os.getenv('MICRO_PAY_THRESHOLD', '5'))  # Score minimo per MICRO_PAY
MICRO_PAY_TARGET_PERCENT = float(os.getenv('MICRO_PAY_TARGET_PERCENT', '1.2'))  # TP: +1.2% P&L
MICRO_PAY_STOP_LOSS_PERCENT = float(os.getenv('MICRO_PAY_STOP_LOSS_PERCENT', '1.2'))  # SL: -1.2% P&L
MICRO_PAY_LEVERAGE = int(os.getenv('MICRO_PAY_LEVERAGE', '3'))
MICRO_PAY_PORTION = float(os.getenv('MICRO_PAY_PORTION', '0.15'))  # 15% del balance
MICRO_PAY_COOLDOWN_SECONDS = int(os.getenv('MICRO_PAY_COOLDOWN_SECONDS', '120'))  # 2 min cooldown
MICRO_PAY_TRAILING_MODE = os.getenv('MICRO_PAY_TRAILING_MODE', 'disable')  # No trailing, TP/SL fissi

# NORMAL Mode Trailing Config (gestito dal sentinel come MICRO_GAIN)
# Stesso meccanismo ma con parametri più ampi
NORMAL_TRAILING_ENABLED = os.getenv('NORMAL_TRAILING_ENABLED', 'true').lower() == 'true'
NORMAL_STOP_LOSS_PERCENT = float(os.getenv('NORMAL_STOP_LOSS_PERCENT', '5.0'))  # SL iniziale (P&L %)
NORMAL_TRAILING_ACTIVATION = float(os.getenv('NORMAL_TRAILING_ACTIVATION', '2.0'))  # Trailing parte a +2% P&L
NORMAL_TRAILING_GAP = float(os.getenv('NORMAL_TRAILING_GAP', '1.5'))  # SL segue P&L con gap 1.5%

# NORMAL Mode Trailing a Gradini (più conservativo per score alti)
# Formato: "pnl1:sl1,pnl2:sl2,..." es. "3:0,5:2,8:5,12:8"
# Significa: a +3% P&L -> SL=0%, a +5% P&L -> SL=+2%, etc.
# Modalità: "continuous" (classico), "steps" (gradini), "disable" (disabilitato)
NORMAL_TRAILING_MODE = os.getenv('NORMAL_TRAILING_MODE', 'steps')
NORMAL_TRAILING_STEPS_STR = os.getenv('NORMAL_TRAILING_STEPS', '3:0,5:2,8:5,12:8,15:10')

def parse_trailing_steps(steps_str: str, default_steps: list = None) -> list:
    """Parse trailing steps from string format 'pnl:sl,pnl:sl,...' to list of tuples."""
    if default_steps is None:
        default_steps = [(3.0, 0.0), (5.0, 2.0), (8.0, 5.0), (12.0, 8.0), (15.0, 10.0)]

    steps = []
    try:
        for step in steps_str.split(','):
            pnl, sl = step.strip().split(':')
            steps.append((float(pnl), float(sl)))
        # Ordina per P&L crescente
        steps.sort(key=lambda x: x[0])
    except Exception as e:
        print(f"[SENTINEL] Errore parsing trailing steps '{steps_str}': {e}")
        steps = default_steps
    return steps

# Parse steps per entrambe le modalità
MICRO_GAIN_TRAILING_STEPS = parse_trailing_steps(
    MICRO_GAIN_TRAILING_STEPS_STR,
    default_steps=[(1.0, 0.0), (2.0, 1.0), (3.0, 2.0)]
)
NORMAL_TRAILING_STEPS = parse_trailing_steps(
    NORMAL_TRAILING_STEPS_STR,
    default_steps=[(3.0, 0.0), (5.0, 2.0), (8.0, 5.0), (12.0, 8.0), (15.0, 10.0)]
)

# Tracking SL corrente per ogni simbolo (in-memory)
_current_sl_level = {}  # symbol -> current SL % level

# Cooldown tracking (in-memory)
_last_close_time = {}  # symbol -> timestamp

# Score smoothing (in-memory) - tiene traccia degli ultimi N scores
SCORE_SMOOTHING_SAMPLES = int(os.getenv('SCORE_SMOOTHING_SAMPLES', '3'))  # Media ultimi 3 scores
_score_history = {}  # symbol -> list of recent scores


# ===== SMART SENTINEL CONFIGURATION =====
# Wake AI Agent su tutte le chiusure (non solo TP)
SENTINEL_WAKE_ON_ALL_CLOSES = os.getenv('SENTINEL_WAKE_ON_ALL_CLOSES', 'true').lower() == 'true'

# Volatility Monitoring
SENTINEL_VOLATILITY_CHECK = os.getenv('SENTINEL_VOLATILITY_CHECK', 'false').lower() == 'true'
SENTINEL_VOLATILITY_THRESHOLD_PCT = float(os.getenv('SENTINEL_VOLATILITY_THRESHOLD_PCT', '2.0'))
SENTINEL_VOLATILITY_WINDOW_SEC = int(os.getenv('SENTINEL_VOLATILITY_WINDOW_SEC', '300'))
SENTINEL_VOLATILITY_COOLDOWN_SEC = int(os.getenv('SENTINEL_VOLATILITY_COOLDOWN_SEC', '600'))  # 10 min cooldown

# Passive SL Verification
SENTINEL_SL_VERIFICATION = os.getenv('SENTINEL_SL_VERIFICATION', 'true').lower() == 'true'
SENTINEL_SL_VERIFICATION_INTERVAL = int(os.getenv('SENTINEL_SL_VERIFICATION_INTERVAL', '300'))  # 5 min

# Log file configuration
LOG_FILE_ENABLED = os.getenv('LOG_FILE_ENABLED', 'true').lower() == 'true'
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', '/app/logs/sentinel.log')
LOG_FILE_MAX_SIZE_MB = int(os.getenv('LOG_FILE_MAX_SIZE_MB', '10'))

def ensure_log_dir():
    """Crea la directory dei log se non esiste."""
    log_dir = os.path.dirname(LOG_FILE_PATH)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

def rotate_log_if_needed():
    """Ruota il file di log se supera la dimensione massima."""
    if os.path.exists(LOG_FILE_PATH):
        size_mb = os.path.getsize(LOG_FILE_PATH) / (1024 * 1024)
        if size_mb > LOG_FILE_MAX_SIZE_MB:
            # Rinomina il vecchio log
            backup_path = LOG_FILE_PATH + '.old'
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(LOG_FILE_PATH, backup_path)

def log(msg: str):
    """Log con timestamp - scrive su console e file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

    # Scrivi anche su file
    if LOG_FILE_ENABLED:
        try:
            ensure_log_dir()
            rotate_log_if_needed()
            with open(LOG_FILE_PATH, 'a') as f:
                f.write(f"[{full_timestamp}] {msg}\n")
        except Exception as e:
            print(f"[{timestamp}] ⚠️ Errore scrittura log file: {e}")


# ============================================================================
# SMART SENTINEL: WAKE AI AGENT
# ============================================================================

def wake_ai_agent(symbol: str, reason: str):
    """
    Sveglia l'AI agent per rivalutare un simbolo.

    Lancia main.py in background (fire and forget) con priorità alta.

    Args:
        symbol: Simbolo da analizzare (BTC, ETH, SOL)
        reason: Motivo del trigger (stop_loss, trailing_stop, volatility_spike, etc.)
    """
    import telegram_notifier as tg

    log(f"🚀 Triggering AI agent per {symbol} (reason: {reason})...")

    try:
        # Prepara il comando
        log_file = f"/tmp/ai_wake_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        with open(log_file, 'w') as f_out:
            process = subprocess.Popen(
                [sys.executable, "main.py", "--ticker", symbol, "--reason", reason, "--priority", "high"],
                stdout=f_out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )

        log(f"   ✅ AI agent avviato per {symbol} (PID: {process.pid})")

        # Notifica Telegram (opzionale)
        if SENTINEL_TELEGRAM_NOTIFY:
            try:
                emoji_map = {
                    "stop_loss": "🛑",
                    "trailing_stop": "📉",
                    "take_profit": "💰",
                    "volatility_spike": "⚡",
                    "reversal": "🔄",
                    "sl_mismatch": "⚠️",
                }
                emoji = emoji_map.get(reason, "🤖")
                tg.send_telegram_message(
                    f"{emoji} <b>AI Wake Trigger</b>\n\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>PID:</b> {process.pid}"
                )
            except Exception:
                pass

        return {"success": True, "pid": process.pid}

    except Exception as e:
        log(f"   ❌ Errore wake_ai_agent: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ============================================================================
# SMART SENTINEL: VOLATILITY MONITOR
# ============================================================================

class VolatilityMonitor:
    """
    Monitora la volatilità dei prezzi per rilevare movimenti bruschi.

    Mantiene una coda di prezzi con timestamp per ogni simbolo.
    Se la variazione (max-min)/min supera la soglia, triggera un alert.
    """

    def __init__(self):
        from collections import deque
        # symbol -> deque of (timestamp, price)
        self._price_history = {}
        # symbol -> last alert timestamp (per cooldown)
        self._last_alert = {}

    def add_price(self, symbol: str, price: float, timestamp: float = None):
        """
        Aggiunge un prezzo alla history.

        Args:
            symbol: Simbolo
            price: Prezzo corrente
            timestamp: Timestamp Unix (default: now)
        """
        if timestamp is None:
            timestamp = time.time()

        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=1000)

        self._price_history[symbol].append((timestamp, price))

        # Pulisci prezzi vecchi
        self._cleanup_old_prices(symbol)

    def _cleanup_old_prices(self, symbol: str):
        """Rimuove prezzi più vecchi della finestra."""
        if symbol not in self._price_history:
            return

        cutoff = time.time() - SENTINEL_VOLATILITY_WINDOW_SEC
        while self._price_history[symbol] and self._price_history[symbol][0][0] < cutoff:
            self._price_history[symbol].popleft()

    def check_volatility(self, symbol: str) -> dict:
        """
        Controlla se la volatilità supera la soglia.

        Returns:
            dict con:
                - triggered: bool
                - volatility_pct: float
                - min_price: float
                - max_price: float
                - reason: str
        """
        result = {
            "triggered": False,
            "volatility_pct": 0.0,
            "min_price": 0,
            "max_price": 0,
            "reason": ""
        }

        if not SENTINEL_VOLATILITY_CHECK:
            return result

        if symbol not in self._price_history or len(self._price_history[symbol]) < 2:
            return result

        # Ottieni prezzi nella finestra
        prices = [p[1] for p in self._price_history[symbol]]

        if not prices:
            return result

        min_price = min(prices)
        max_price = max(prices)

        if min_price <= 0:
            return result

        # Calcola volatilità
        volatility_pct = ((max_price - min_price) / min_price) * 100

        result["volatility_pct"] = round(volatility_pct, 2)
        result["min_price"] = min_price
        result["max_price"] = max_price

        # Controlla soglia
        if volatility_pct >= SENTINEL_VOLATILITY_THRESHOLD_PCT:
            # Controlla cooldown
            if self._is_in_cooldown(symbol):
                result["reason"] = f"Volatility {volatility_pct:.2f}% (in cooldown)"
                return result

            result["triggered"] = True
            result["reason"] = f"Volatility spike: {volatility_pct:.2f}% in {SENTINEL_VOLATILITY_WINDOW_SEC}s"

            # Imposta cooldown
            self._last_alert[symbol] = time.time()

        return result

    def _is_in_cooldown(self, symbol: str) -> bool:
        """Verifica se il simbolo è in cooldown dopo un alert."""
        if symbol not in self._last_alert:
            return False

        elapsed = time.time() - self._last_alert[symbol]
        return elapsed < SENTINEL_VOLATILITY_COOLDOWN_SEC

    def get_stats(self, symbol: str) -> dict:
        """Ottieni statistiche per un simbolo."""
        if symbol not in self._price_history:
            return {"count": 0, "oldest": None, "newest": None}

        history = self._price_history[symbol]
        if not history:
            return {"count": 0, "oldest": None, "newest": None}

        return {
            "count": len(history),
            "oldest": history[0][0] if history else None,
            "newest": history[-1][0] if history else None,
            "window_sec": SENTINEL_VOLATILITY_WINDOW_SEC
        }


# Istanza globale del volatility monitor
_volatility_monitor = VolatilityMonitor()


# ============================================================================
# SMART SENTINEL: PASSIVE SL VERIFICATION
# ============================================================================

_last_sl_verification_time = 0


def should_run_sl_verification() -> bool:
    """Controlla se è tempo di eseguire la verifica SL passiva."""
    global _last_sl_verification_time

    if not SENTINEL_SL_VERIFICATION:
        return False

    elapsed = time.time() - _last_sl_verification_time
    return elapsed >= SENTINEL_SL_VERIFICATION_INTERVAL


def run_passive_sl_verification(bot, positions: list):
    """
    Verifica passiva che gli ordini SL siano corretti.

    Confronta SL nel DB/memoria con ordini su Hyperliquid.
    Se c'è mismatch, tenta di correggere.

    Args:
        bot: HyperLiquidTrader instance
        positions: Lista posizioni aperte
    """
    global _last_sl_verification_time

    if not SENTINEL_SL_VERIFICATION:
        return

    if not should_run_sl_verification():
        return

    _last_sl_verification_time = time.time()

    log("🔍 Verifica SL passiva...")

    import db_utils
    import telegram_notifier as tg

    issues_found = []

    try:
        # Ottieni ordini aperti da Hyperliquid
        try:
            open_orders = bot.info.frontend_open_orders(bot.account_address)
        except AttributeError:
            open_orders = bot.info.open_orders(bot.account_address)

        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("side", "long").lower()
            entry_price = float(pos.get("entry_price", 0))
            size = float(pos.get("size", 0))

            # Cerca tracking nel DB
            tracking = db_utils.get_position_tracking(symbol)
            if not tracking:
                continue

            trading_mode = tracking.get("trading_mode", "NORMAL")

            # Determina SL atteso
            if trading_mode == "MICRO_GAIN":
                expected_sl_pct = MICRO_GAIN_STOP_LOSS_PERCENT
                leverage = MICRO_GAIN_LEVERAGE
            elif trading_mode == "MICRO_PAY":
                expected_sl_pct = MICRO_PAY_STOP_LOSS_PERCENT
                leverage = MICRO_PAY_LEVERAGE
            else:
                expected_sl_pct = NORMAL_STOP_LOSS_PERCENT
                # Parse leverage dalla posizione
                leverage_raw = pos.get("leverage", 1)
                if isinstance(leverage_raw, str):
                    import re
                    match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                    leverage = float(match.group(1)) if match else 1.0
                else:
                    leverage = float(leverage_raw)

            # Calcola prezzo SL atteso
            price_change_pct = expected_sl_pct / leverage
            if direction == "long":
                expected_sl_price = entry_price * (1 - price_change_pct / 100)
                expected_side = "A"  # Ask (sell)
            else:
                expected_sl_price = entry_price * (1 + price_change_pct / 100)
                expected_side = "B"  # Bid (buy)

            # Cerca ordine SL per questo simbolo
            sl_order = None
            for order in open_orders:
                if order.get("coin") == symbol and order.get("side") == expected_side:
                    trigger_px = order.get("triggerPx")
                    if trigger_px and trigger_px != "0.0":
                        sl_order = order
                        break

            # Verifica
            if not sl_order:
                issues_found.append({
                    "symbol": symbol,
                    "issue": "SL_MISSING",
                    "trading_mode": trading_mode
                })
                log(f"   ⚠️ {symbol}: SL mancante! Mode={trading_mode}")

                # Tenta di piazzare SL
                log(f"   🔧 Tentativo piazzamento SL per {symbol}...")
                if trading_mode == "MICRO_GAIN":
                    place_micro_gain_sl_order(bot, symbol, direction, entry_price, size)
                elif trading_mode == "MICRO_PAY":
                    place_micro_pay_sl_order(bot, symbol, direction, entry_price, size)
                else:
                    place_normal_initial_sl(bot, symbol, direction, entry_price, size, leverage)

            else:
                # Verifica prezzo SL
                actual_sl_price = float(sl_order.get("triggerPx", 0))
                price_diff_pct = abs(actual_sl_price - expected_sl_price) / expected_sl_price * 100

                if price_diff_pct > 1.0:  # Tolleranza 1%
                    issues_found.append({
                        "symbol": symbol,
                        "issue": "SL_PRICE_MISMATCH",
                        "expected": expected_sl_price,
                        "actual": actual_sl_price,
                        "diff_pct": price_diff_pct
                    })
                    log(f"   ⚠️ {symbol}: SL price mismatch - expected ${expected_sl_price:.2f}, actual ${actual_sl_price:.2f}")

        # Report finale
        if issues_found:
            log(f"   📋 Trovati {len(issues_found)} problemi SL")

            # Notifica Telegram se ci sono problemi critici
            missing_sl = [i for i in issues_found if i["issue"] == "SL_MISSING"]
            if missing_sl and SENTINEL_TELEGRAM_NOTIFY:
                try:
                    symbols_list = ", ".join([i["symbol"] for i in missing_sl])
                    tg.send_telegram_message(
                        f"⚠️ <b>SL VERIFICATION ALERT</b>\n\n"
                        f"Simboli senza SL: {symbols_list}\n"
                        f"Tentativo correzione automatica in corso."
                    )
                except Exception:
                    pass
        else:
            log(f"   ✅ Tutti gli SL verificati OK")

    except Exception as e:
        log(f"   ❌ Errore verifica SL passiva: {e}")
        import traceback
        traceback.print_exc()


def get_smoothed_score(symbol: str, raw_score: float) -> float:
    """
    Calcola uno score mediato sugli ultimi N campioni.
    Riduce la volatilità causata da indicatori binari (MACD, EMA).

    Args:
        symbol: Simbolo
        raw_score: Score appena calcolato

    Returns:
        float: Score mediato
    """
    global _score_history

    if symbol not in _score_history:
        _score_history[symbol] = []

    # Aggiungi nuovo score alla history
    _score_history[symbol].append(raw_score)

    # Mantieni solo gli ultimi N campioni
    if len(_score_history[symbol]) > SCORE_SMOOTHING_SAMPLES:
        _score_history[symbol] = _score_history[symbol][-SCORE_SMOOTHING_SAMPLES:]

    # Calcola media
    if len(_score_history[symbol]) == 0:
        return raw_score

    avg_score = sum(_score_history[symbol]) / len(_score_history[symbol])

    # Log per debug
    if len(_score_history[symbol]) > 1:
        log(f"      📊 {symbol} scores: {[f'{s:.0f}' for s in _score_history[symbol]]} → avg={avg_score:.1f}")

    return avg_score


def calculate_quick_score(symbol: str, verbose: bool = True) -> float:
    """
    Calcola lo score COMPLETO usando signal_scorer.py + sentiment cache.

    Usa gli stessi pesi e logica di main.py per garantire coerenza:
    - RSI: peso 15 (overbought/oversold)
    - Trend (EMA+MACD): peso 10
    - MACD solo: peso 5
    - Fear & Greed: peso 8 (da cache DB)
    - Volume: peso 4
    - Forecast: skip (non disponibile nel sentinel)

    Args:
        symbol: Simbolo da analizzare
        verbose: Se True, logga tutti i dettagli del calcolo

    Returns:
        float: Score positivo = bullish, negativo = bearish
               Range tipico: -40 a +40 (con F&G incluso)
    """
    try:
        from indicators import CryptoTechnicalAnalysisHL
        from signal_scorer import calculate_signal_score
        import db_utils

        analyzer = CryptoTechnicalAnalysisHL(testnet=TESTNET)
        data = analyzer.get_complete_analysis(symbol)

        if not data:
            if verbose:
                log(f"      ❌ {symbol}: Nessun dato ricevuto")
            return 0.0

        # Estrai dati dalla struttura corretta (intraday contiene gli array)
        intraday = data.get('intraday', {})

        # Prendi l'ultimo valore degli array (più recente)
        rsi_array = intraday.get('rsi_14', [50])
        rsi = rsi_array[-1] if rsi_array else 50

        macd_array = intraday.get('macd', [0])
        macd = macd_array[-1] if macd_array else 0

        ema_array = intraday.get('ema_20', [0])
        ema20 = ema_array[-1] if ema_array else 0

        prices_array = intraday.get('mid_prices', [0])
        price = prices_array[-1] if prices_array else 0

        # Estrai volume dal data structure
        volume_str = data.get('volume', '')
        volume_bid = 0.0
        volume_ask = 0.0
        if isinstance(volume_str, str) and "Bid Vol" in volume_str:
            try:
                parts = volume_str.replace("Bid Vol:", "").split("Ask Vol:")
                bid_str = parts[0].strip().strip(",")
                ask_str = parts[1].strip()
                volume_bid = float(bid_str)
                volume_ask = float(ask_str)
            except Exception:
                pass

        # Leggi Fear & Greed dalla cache (aggiornata da main.py ogni 15 min)
        fear_greed = 50  # Default neutral
        fg_source = "default"
        try:
            # Prima prova con dati freschi (ultimi 60 min)
            cached_sentiment = db_utils.get_cached_sentiment(max_age_minutes=60)
            if cached_sentiment and cached_sentiment.get('valore') is not None:
                fear_greed = cached_sentiment['valore']
                fg_source = f"cache ({cached_sentiment.get('classificazione', 'N/A')})"
            else:
                # Fallback: usa dati anche se vecchi (fino a 24 ore)
                cached_sentiment = db_utils.get_cached_sentiment(max_age_minutes=1440)
                if cached_sentiment and cached_sentiment.get('valore') is not None:
                    fear_greed = cached_sentiment['valore']
                    fg_source = f"STALE cache ({cached_sentiment.get('classificazione', 'N/A')})"
                    if verbose:
                        log(f"      ⚠️ {symbol} Usando F&G stale (>60 min) - AI non aggiornata?")
        except Exception as e:
            if verbose:
                log(f"      ⚠️ Errore lettura sentiment cache: {e}")

        if verbose:
            log(f"      📈 {symbol} Indicatori: RSI={rsi:.1f}, MACD={macd:.4f}, Price=${price:.2f}, EMA20=${ema20:.2f}")
            log(f"      📈 {symbol} F&G={fear_greed} ({fg_source}), Vol Bid={volume_bid:.1f}, Ask={volume_ask:.1f}")

        # Usa calculate_signal_score per calcolo COMPLETO
        # Forecast = 0 perché Prophet non è disponibile nel sentinel
        score_result = calculate_signal_score(
            price=price,
            ema20=ema20,
            rsi=rsi,
            macd=macd,
            fear_greed=fear_greed,
            forecast_change_pct=0.0,  # Skip forecast nel sentinel
            volume_bid=volume_bid,
            volume_ask=volume_ask
        )

        net_score = score_result.get('net_score', 0.0)

        if verbose:
            # Log dettagliato dei segnali che hanno contribuito
            active_signals = [s for s in score_result.get('signals', []) if s.get('contribution', 0) > 0]
            signal_details = []
            for s in active_signals:
                dir_sign = "+" if s.get('direction') == 'BULLISH' else "-"
                signal_details.append(f"{s.get('indicator')}={dir_sign}{s.get('contribution'):.1f}")

            log(f"      📊 {symbol} Score: bull={score_result.get('score_bullish'):.1f} bear={score_result.get('score_bearish'):.1f}")
            if signal_details:
                log(f"      📊 {symbol} Signals: {' | '.join(signal_details)}")
            log(f"      📊 {symbol} Net Score (raw): {net_score:+.1f} → {score_result.get('direction')}")

        # Applica smoothing per ridurre volatilità
        smoothed_score = get_smoothed_score(symbol, net_score)
        return smoothed_score

    except Exception as e:
        log(f"⚠️ Errore calcolo quick_score per {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return 0.0


def check_micro_gain_reversal(position: dict, tracking_data: dict) -> dict:
    """
    Controlla se una posizione MICRO_GAIN deve essere chiusa per inversione.

    Args:
        position: Dati posizione da Hyperliquid
        tracking_data: Dati tracking dal DB (include trading_mode, opening_score)

    Returns:
        dict con triggered, reason, quick_score
    """
    result = {
        "triggered": False,
        "reason": "",
        "quick_score": 0.0
    }

    if not MICRO_GAIN_ENABLED:
        return result

    trading_mode = tracking_data.get("trading_mode", "NORMAL")
    if trading_mode != "MICRO_GAIN":
        return result

    symbol = position.get("symbol", "")
    direction = position.get("side", "long").lower()

    # Calcola quick score
    quick_score = calculate_quick_score(symbol)
    result["quick_score"] = quick_score

    # Verifica inversione
    # Per LONG: se quick_score è molto negativo = inversione
    # Per SHORT: se quick_score è molto positivo = inversione
    if direction == "long" and quick_score < -MICRO_GAIN_REVERSAL_SCORE:
        result["triggered"] = True
        result["reason"] = f"MICRO_GAIN REVERSAL: Score {quick_score:.1f} (soglia -{MICRO_GAIN_REVERSAL_SCORE})"
    elif direction == "short" and quick_score > MICRO_GAIN_REVERSAL_SCORE:
        result["triggered"] = True
        result["reason"] = f"MICRO_GAIN REVERSAL: Score {quick_score:.1f} (soglia +{MICRO_GAIN_REVERSAL_SCORE})"

    return result


def is_in_cooldown(symbol: str) -> bool:
    """Verifica se il simbolo è in cooldown dopo una chiusura recente."""
    global _last_close_time
    if symbol not in _last_close_time:
        return False

    elapsed = time.time() - _last_close_time[symbol]
    return elapsed < MICRO_GAIN_COOLDOWN_SECONDS


def set_cooldown(symbol: str):
    """Imposta il cooldown per un simbolo."""
    global _last_close_time
    _last_close_time[symbol] = time.time()
    log(f"   ⏱️ Cooldown attivato per {symbol} ({MICRO_GAIN_COOLDOWN_SECONDS}s)")


def open_micro_gain_position(bot, symbol: str, direction: str, score: float):
    """
    Apre una posizione MICRO_GAIN con TP e SL orders su Hyperliquid.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        score: Score che ha generato il segnale

    Returns:
        dict con risultato operazione
    """
    import db_utils
    import telegram_notifier as tg

    log(f"🎯 MICRO_GAIN AUTO-OPEN: {symbol} {direction.upper()} (score={score:.1f})")

    try:
        # Prepara ordine
        order_json = {
            "operation": "open",
            "symbol": symbol,
            "direction": direction,
            "reason": f"MICRO_GAIN sentinel auto-open: score {score:.1f}",
            "target_portion_of_balance": MICRO_GAIN_PORTION,
            "leverage": MICRO_GAIN_LEVERAGE,
            "trading_mode": "MICRO_GAIN",
            "opening_score": score,
            "micro_gain_target": MICRO_GAIN_TARGET_PERCENT
        }

        # Esegui ordine
        result = bot.execute_signal(order_json)

        # Hyperliquid ritorna status:"ok" quando l'ordine va a buon fine
        order_success = (
            result.get("success") or
            result.get("status") == "ok" or
            result.get("status") == "executed"
        )

        if order_success:
            # Ottieni entry price dalla posizione
            account_status = bot.get_account_status()
            entry_price = 0
            position_size = 0

            for pos in account_status.get("open_positions", []):
                if pos.get("symbol") == symbol:
                    entry_price = float(pos.get("entry_price", 0))
                    position_size = float(pos.get("size", 0))
                    break

            if entry_price > 0:
                # Crea tracking
                db_utils.upsert_position_tracking(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=entry_price,
                    trailing_active=False,
                    opening_score=score,
                    trading_mode="MICRO_GAIN"
                )

                # Trade Journal: registra apertura trade
                trade_uuid = None
                if TRADE_JOURNAL_ENABLED:
                    try:
                        trade_uuid = tj.open_trade(
                            symbol=symbol,
                            direction=direction.upper(),
                            trading_mode="MICRO_GAIN",
                            entry_price=entry_price,
                            size=position_size,
                            leverage=MICRO_GAIN_LEVERAGE,
                            score=score,
                            sl_percent=MICRO_GAIN_STOP_LOSS_PERCENT,
                            tp_percent=MICRO_GAIN_TARGET_PERCENT,
                            trailing_activation=MICRO_GAIN_TRAILING_ACTIVATION,
                            trailing_gap=MICRO_GAIN_TRAILING_GAP
                        )
                        log(f"   📒 Trade Journal: registrato trade {trade_uuid[:8]}...")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal error: {e}")

                # Piazza SL order su Hyperliquid
                sl_price = place_micro_gain_sl_order(bot, symbol, direction, entry_price, position_size)

                # VERIFICA IMMEDIATA: controlla che l'ordine SL sia stato piazzato correttamente
                time.sleep(0.5)  # Piccola pausa per sincronizzazione
                sl_verification = verify_and_fix_sl_order(
                    bot, symbol, direction, entry_price, position_size,
                    MICRO_GAIN_LEVERAGE, "MICRO_GAIN", max_retries=2
                )
                if not sl_verification["verified"]:
                    log(f"   🚨 CRITICO: Impossibile verificare SL per {symbol}!")
                elif sl_verification["fixed"]:
                    log(f"   🔧 SL corretto automaticamente per {symbol}")

                # Trade Journal: registra SL placement
                if TRADE_JOURNAL_ENABLED and trade_uuid and sl_price:
                    try:
                        tj.log_sl_placed(trade_uuid, sl_price, "STOP_TRIGGER", entry_price)
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal SL log error: {e}")

                # Inizializza SL level per trailing
                _current_sl_level[symbol] = -MICRO_GAIN_STOP_LOSS_PERCENT

                # Notifica Telegram
                if SENTINEL_TELEGRAM_NOTIFY:
                    try:
                        tg.send_telegram_message(
                            f"🎯 <b>MICRO_GAIN OPEN</b>\n\n"
                            f"<b>Symbol:</b> {symbol}\n"
                            f"<b>Direction:</b> {direction.upper()}\n"
                            f"<b>Entry:</b> ${entry_price:.2f}\n"
                            f"<b>Score:</b> {score:.1f}\n"
                            f"<b>TP Target:</b> +{MICRO_GAIN_TARGET_PERCENT}%\n"
                            f"<b>SL:</b> -{MICRO_GAIN_STOP_LOSS_PERCENT}%"
                        )
                    except Exception as e:
                        log(f"   ⚠️ Errore Telegram: {e}")

                log(f"   ✅ Posizione MICRO_GAIN aperta: {symbol} {direction.upper()} @ ${entry_price:.2f}")
                return {"success": True, "entry_price": entry_price}
            else:
                log(f"   ⚠️ Posizione aperta ma entry price non trovato")
                return {"success": False, "error": "Entry price not found"}
        else:
            log(f"   ⚠️ Errore apertura: {result}")
            return {"success": False, "error": str(result)}

    except Exception as e:
        log(f"   ❌ Errore apertura MICRO_GAIN: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def place_micro_gain_sl_order(bot, symbol: str, direction: str, entry_price: float, size: float):
    """
    Piazza un ordine STOP LOSS trigger su Hyperliquid per MICRO_GAIN.

    Usa ordine STOP (trigger) invece di LIMIT per evitare esecuzione immediata.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size della posizione
    """
    try:
        # Calcola prezzo SL trigger
        price_change_pct = MICRO_GAIN_STOP_LOSS_PERCENT / MICRO_GAIN_LEVERAGE

        if direction == "long":
            # LONG: SL sotto il prezzo di entrata
            sl_trigger = entry_price * (1 - price_change_pct / 100)
        else:
            # SHORT: SL sopra il prezzo di entrata
            sl_trigger = entry_price * (1 + price_change_pct / 100)

        # Arrotonda al tick size
        sl_trigger = bot._round_to_tick(sl_trigger, symbol)

        log(f"   🛡️ Piazzo SL STOP @ ${sl_trigger:.2f} (trigger, loss: -{MICRO_GAIN_STOP_LOSS_PERCENT}%)")

        # Piazza ordine STOP (trigger) - direzione opposta per chiudere
        is_buy = direction == "short"  # Se short, compra per chiudere

        # Usa trigger order invece di limit order
        sl_order = bot.exchange.order(
            symbol,
            is_buy,
            size,
            sl_trigger,  # Prezzo limite (uguale al trigger per market-like execution)
            {"trigger": {"triggerPx": sl_trigger, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True
        )

        if sl_order.get("status") == "ok":
            response_data = sl_order.get("response", {})
            if response_data.get("type") == "order":
                statuses = response_data.get("data", {}).get("statuses", [])
                if statuses and statuses[0].get("resting"):
                    log(f"   ✅ SL STOP piazzato: OID={statuses[0]['resting']['oid']}")
                    return sl_trigger  # Ritorna il prezzo SL per il journal

        log(f"   ⚠️ SL order response: {sl_order}")
        return None

    except Exception as e:
        log(f"   ❌ Errore piazzamento SL: {e}")
        return None


# ===== MICRO_PAY FUNCTIONS =====

def open_micro_pay_position(bot, symbol: str, direction: str, score: float):
    """
    Apre una posizione MICRO_PAY con TP e SL orders su Hyperliquid.

    MICRO_PAY è per score deboli (5-15): trade veloci con piccoli guadagni.
    Trailing disabilitato, solo TP/SL fissi.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        score: Score che ha generato il segnale

    Returns:
        dict con risultato operazione
    """
    import db_utils
    import telegram_notifier as tg

    log(f"💵 MICRO_PAY AUTO-OPEN: {symbol} {direction.upper()} (score={score:.1f})")

    try:
        # Prepara ordine
        order_json = {
            "operation": "open",
            "symbol": symbol,
            "direction": direction,
            "reason": f"MICRO_PAY sentinel auto-open: score {score:.1f}",
            "target_portion_of_balance": MICRO_PAY_PORTION,
            "leverage": MICRO_PAY_LEVERAGE,
            "trading_mode": "MICRO_PAY",
            "opening_score": score,
            "micro_gain_target": MICRO_PAY_TARGET_PERCENT  # Usa lo stesso campo per compatibilità
        }

        # Esegui ordine
        result = bot.execute_signal(order_json)

        # Hyperliquid ritorna status:"ok" quando l'ordine va a buon fine
        order_success = (
            result.get("success") or
            result.get("status") == "ok" or
            result.get("status") == "executed"
        )

        if order_success:
            # Ottieni entry price dalla posizione
            account_status = bot.get_account_status()
            entry_price = 0
            position_size = 0

            for pos in account_status.get("open_positions", []):
                if pos.get("symbol") == symbol:
                    entry_price = float(pos.get("entry_price", 0))
                    position_size = float(pos.get("size", 0))
                    break

            if entry_price > 0:
                # Crea tracking
                db_utils.upsert_position_tracking(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=entry_price,
                    trailing_active=False,
                    opening_score=score,
                    trading_mode="MICRO_PAY"
                )

                # Trade Journal: registra apertura trade
                trade_uuid = None
                if TRADE_JOURNAL_ENABLED:
                    try:
                        trade_uuid = tj.open_trade(
                            symbol=symbol,
                            direction=direction.upper(),
                            trading_mode="MICRO_PAY",
                            entry_price=entry_price,
                            size=position_size,
                            leverage=MICRO_PAY_LEVERAGE,
                            score=score,
                            sl_percent=MICRO_PAY_STOP_LOSS_PERCENT,
                            tp_percent=MICRO_PAY_TARGET_PERCENT,
                            trailing_activation=0,  # No trailing per MICRO_PAY
                            trailing_gap=0
                        )
                        log(f"   📒 Trade Journal: registrato trade MICRO_PAY {trade_uuid[:8]}...")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal error: {e}")

                # Piazza SL order su Hyperliquid
                sl_price = place_micro_pay_sl_order(bot, symbol, direction, entry_price, position_size)

                # VERIFICA IMMEDIATA: controlla che l'ordine SL sia stato piazzato correttamente
                time.sleep(0.5)  # Piccola pausa per sincronizzazione
                sl_verification = verify_and_fix_sl_order(
                    bot, symbol, direction, entry_price, position_size,
                    MICRO_PAY_LEVERAGE, "MICRO_PAY", max_retries=2
                )
                if not sl_verification["verified"]:
                    log(f"   🚨 CRITICO: Impossibile verificare SL per {symbol}!")
                elif sl_verification["fixed"]:
                    log(f"   🔧 SL corretto automaticamente per {symbol}")

                # Trade Journal: registra SL placement
                if TRADE_JOURNAL_ENABLED and trade_uuid and sl_price:
                    try:
                        tj.log_sl_placed(trade_uuid, sl_price, "STOP_TRIGGER", entry_price)
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal SL log error: {e}")

                # Inizializza SL level (no trailing per MICRO_PAY)
                _current_sl_level[f"{symbol}_MICROPAY"] = -MICRO_PAY_STOP_LOSS_PERCENT

                # Notifica Telegram
                if SENTINEL_TELEGRAM_NOTIFY:
                    try:
                        tg.send_telegram_message(
                            f"💵 <b>MICRO_PAY OPEN</b>\n\n"
                            f"<b>Symbol:</b> {symbol}\n"
                            f"<b>Direction:</b> {direction.upper()}\n"
                            f"<b>Entry:</b> ${entry_price:.2f}\n"
                            f"<b>Score:</b> {score:.1f}\n"
                            f"<b>TP Target:</b> +{MICRO_PAY_TARGET_PERCENT}%\n"
                            f"<b>SL:</b> -{MICRO_PAY_STOP_LOSS_PERCENT}%\n"
                            f"<i>Quick trade mode - no trailing</i>"
                        )
                    except Exception as e:
                        log(f"   ⚠️ Errore Telegram: {e}")

                log(f"   ✅ Posizione MICRO_PAY aperta: {symbol} {direction.upper()} @ ${entry_price:.2f}")
                return {"success": True, "entry_price": entry_price}
            else:
                log(f"   ⚠️ Posizione aperta ma entry price non trovato")
                return {"success": False, "error": "Entry price not found"}
        else:
            log(f"   ⚠️ Errore apertura: {result}")
            return {"success": False, "error": str(result)}

    except Exception as e:
        log(f"   ❌ Errore apertura MICRO_PAY: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def place_micro_pay_sl_order(bot, symbol: str, direction: str, entry_price: float, size: float):
    """
    Piazza un ordine STOP LOSS trigger su Hyperliquid per MICRO_PAY.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size della posizione
    """
    try:
        # Calcola prezzo SL trigger
        price_change_pct = MICRO_PAY_STOP_LOSS_PERCENT / MICRO_PAY_LEVERAGE

        if direction == "long":
            sl_trigger = entry_price * (1 - price_change_pct / 100)
        else:
            sl_trigger = entry_price * (1 + price_change_pct / 100)

        sl_trigger = bot._round_to_tick(sl_trigger, symbol)

        log(f"   🛡️ Piazzo MICRO_PAY SL STOP @ ${sl_trigger:.2f} (loss: -{MICRO_PAY_STOP_LOSS_PERCENT}%)")

        is_buy = direction == "short"

        sl_order = bot.exchange.order(
            symbol,
            is_buy,
            size,
            sl_trigger,
            {"trigger": {"triggerPx": sl_trigger, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True
        )

        if sl_order.get("status") == "ok":
            response_data = sl_order.get("response", {})
            if response_data.get("type") == "order":
                statuses = response_data.get("data", {}).get("statuses", [])
                if statuses and statuses[0].get("resting"):
                    log(f"   ✅ MICRO_PAY SL piazzato: OID={statuses[0]['resting']['oid']}")
                    return sl_trigger

        log(f"   ⚠️ SL order response: {sl_order}")
        return None

    except Exception as e:
        log(f"   ❌ Errore piazzamento MICRO_PAY SL: {e}")
        return None


# ===== DETECT EXTERNALLY CLOSED POSITIONS =====

def detect_externally_closed_positions(bot, existing_symbols: list):
    """
    Rileva posizioni tracciate che sono state chiuse esternamente (TP/SL su Hyperliquid).
    Registra la chiusura nel Trade Journal.

    Args:
        bot: HyperLiquidTrader instance
        existing_symbols: Lista dei simboli con posizioni attualmente aperte
    """
    if not TRADE_JOURNAL_ENABLED:
        return

    try:
        import trade_journal as tj
        import db_utils

        # Ottieni tutti i tracking attivi dal DB
        all_trackings = db_utils.get_all_position_trackings()

        for tracking in all_trackings:
            symbol = tracking.get("symbol")

            # Se il simbolo è ancora aperto, skip
            if symbol in existing_symbols:
                continue

            # Posizione era tracciata ma non esiste più → chiusa esternamente!
            log(f"📋 {symbol}: Posizione chiusa esternamente (TP/SL)")

            # Cerca trade aperto nel journal
            open_trade = tj.get_open_trade(symbol)
            if not open_trade:
                log(f"   ⚠️ {symbol}: Nessun trade aperto nel journal, cleanup tracking")
                db_utils.delete_position_tracking(symbol)
                continue

            # Ottieni ultimo fill da Hyperliquid per il prezzo di chiusura
            exit_price = None
            close_reason = tj.CloseReason.MANUAL  # Default

            try:
                # Usa user_fills per ottenere gli ultimi trade
                fills = bot.info.user_fills(bot.account_address)

                # Cerca l'ultimo fill per questo simbolo
                symbol_fills = [f for f in fills if f.get("coin") == symbol]
                if symbol_fills:
                    # Ordina per tempo (più recente prima)
                    symbol_fills.sort(key=lambda x: x.get("time", 0), reverse=True)
                    last_fill = symbol_fills[0]
                    exit_price = float(last_fill.get("px", 0))

                    # Determina reason dal tipo di ordine
                    # Se il fill è da un ordine trigger, è TP o SL
                    order_type = last_fill.get("orderType", "")
                    if "Trigger" in str(order_type) or last_fill.get("cloid", "").startswith("sl"):
                        close_reason = tj.CloseReason.SL_HIT
                    elif last_fill.get("cloid", "").startswith("tp"):
                        close_reason = tj.CloseReason.TP_HIT
                    else:
                        # Controlla direzione per capire se era TP o SL
                        entry_price = float(open_trade.get("entry_price", 0))
                        direction = open_trade.get("direction", "").lower()

                        if direction == "long":
                            # Long: se exit > entry, probabilmente TP
                            if exit_price > entry_price:
                                close_reason = tj.CloseReason.TP_HIT
                            else:
                                close_reason = tj.CloseReason.SL_HIT
                        else:
                            # Short: se exit < entry, probabilmente TP
                            if exit_price < entry_price:
                                close_reason = tj.CloseReason.TP_HIT
                            else:
                                close_reason = tj.CloseReason.SL_HIT

                    log(f"   📍 Exit price: ${exit_price:.2f}, reason: {close_reason.value}")
            except Exception as e:
                log(f"   ⚠️ Errore lettura fills: {e}")
                # Usa ultimo prezzo tracciato come fallback
                exit_price = tracking.get("last_checked_price") or tracking.get("entry_price")

            if not exit_price:
                exit_price = tracking.get("entry_price", 0)
                log(f"   ⚠️ Exit price non trovato, uso entry: ${exit_price:.2f}")

            # Chiudi trade nel journal
            try:
                result_close = tj.close_trade(
                    trade_uuid=open_trade['trade_uuid'],
                    exit_price=exit_price,
                    close_reason=close_reason
                )
                log(f"   📒 Trade Journal: chiuso trade - Net P&L: ${result_close['net_pnl_usd']:.2f}")
            except Exception as e:
                log(f"   ⚠️ Errore chiusura trade journal: {e}")

            # Cleanup tracking
            db_utils.delete_position_tracking(symbol)

            # Reset SL level
            sl_key_micro = symbol
            sl_key_normal = f"{symbol}_NORMAL"
            sl_key_micropay = f"{symbol}_MICROPAY"
            for key in [sl_key_micro, sl_key_normal, sl_key_micropay]:
                if key in _current_sl_level:
                    del _current_sl_level[key]

    except Exception as e:
        log(f"⚠️ Errore detect_externally_closed_positions: {e}")


def update_micro_gain_sl_order(bot, symbol: str, direction: str, entry_price: float,
                                current_price: float, size: float):
    """
    Aggiorna l'ordine SL per MICRO_GAIN.

    Supporta tre modalità (configurabile via MICRO_GAIN_TRAILING_MODE):

    1. "continuous" - Trailing continuo classico:
       - Se P&L >= TRAILING_ACTIVATION, inizia il trailing
       - SL segue il P&L mantenendo un gap di TRAILING_GAP
       - SL non scende mai, solo sale

    2. "steps" - Trailing a gradini:
       - SL si alza solo a livelli predefiniti
       - Meno sensibile alle oscillazioni

    3. "disable" - Trailing disabilitato:
       - SL resta fisso al valore iniziale
       - Nessun trailing

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        current_price: Prezzo corrente
        size: Size della posizione

    Returns:
        bool: True se SL è stato aggiornato
    """
    global _current_sl_level

    # Se trailing disabilitato, esci subito
    if MICRO_GAIN_TRAILING_MODE == "disable":
        return False

    try:
        # Calcola P&L corrente
        if direction == "long":
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            price_change_pct = ((entry_price - current_price) / entry_price) * 100

        pnl_pct = price_change_pct * MICRO_GAIN_LEVERAGE

        # SL corrente (iniziale = -STOP_LOSS_PERCENT)
        current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT)

        # Log stato trailing con indicazione modalità
        mode_str = MICRO_GAIN_TRAILING_MODE.upper()
        log(f"   📊 {symbol} MICRO_GAIN ({mode_str}): P&L={pnl_pct:+.2f}% | SL={current_sl:+.2f}%")

        # Calcola nuovo SL in base alla modalità
        new_sl_level = None

        if MICRO_GAIN_TRAILING_MODE == "steps":
            # === MODALITÀ GRADINI ===
            step_sl = get_step_sl_level(pnl_pct, current_sl, MICRO_GAIN_TRAILING_STEPS)

            if step_sl > current_sl:
                new_sl_level = step_sl
                # Trova quale gradino è stato raggiunto
                step_reached = None
                for pnl_threshold, sl_level in MICRO_GAIN_TRAILING_STEPS:
                    if sl_level == step_sl:
                        step_reached = pnl_threshold
                        break
                log(f"   📶 STEP RAGGIUNTO! P&L >= +{step_reached}% → SL sale a {new_sl_level:+.2f}%")
        else:
            # === MODALITÀ CONTINUA (classica) ===
            if pnl_pct >= MICRO_GAIN_TRAILING_ACTIVATION:
                continuous_sl = pnl_pct - MICRO_GAIN_TRAILING_GAP
                if continuous_sl > current_sl:
                    new_sl_level = continuous_sl
                    log(f"   📈 TRAILING CONTINUO: P&L={pnl_pct:+.2f}% | SL: {current_sl:+.2f}% → {new_sl_level:+.2f}%")

        # Se c'è un nuovo SL da impostare
        if new_sl_level is not None and new_sl_level > current_sl:
            # Calcola prezzo SL
            sl_price_change = new_sl_level / MICRO_GAIN_LEVERAGE

            if direction == "long":
                new_sl_price = entry_price * (1 + sl_price_change / 100)
            else:
                new_sl_price = entry_price * (1 - sl_price_change / 100)

            new_sl_price = bot._round_to_tick(new_sl_price, symbol)

            # Cancella ordini SL esistenti
            try:
                open_orders = bot.info.open_orders(bot.account_address)
                for order in open_orders:
                    if order.get("coin") == symbol:
                        # Cancella solo ordini SL (lato opposto alla posizione)
                        expected_side = "B" if direction == "short" else "A"
                        if order.get("side") == expected_side:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            log(f"   🗑️ Cancellato SL precedente")
            except Exception as e:
                log(f"   ⚠️ Errore cancellazione: {e}")

            # Piazza nuovo SL STOP (trigger order)
            is_buy = direction == "short"

            sl_order = bot.exchange.order(
                symbol,
                is_buy,
                size,
                new_sl_price,
                {"trigger": {"triggerPx": new_sl_price, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") == "ok":
                old_sl = current_sl
                _current_sl_level[symbol] = new_sl_level
                log(f"   🔒 MICRO_GAIN SL STOP @ ${new_sl_price:.2f} ({new_sl_level:+.2f}%)")

                # Trade Journal: log SL modification
                if TRADE_JOURNAL_ENABLED:
                    try:
                        open_trade = tj.get_open_trade(symbol)
                        if open_trade:
                            # Log trailing activation se è il primo trailing update
                            if old_sl <= -MICRO_GAIN_STOP_LOSS_PERCENT + 0.1:
                                activation_pct = MICRO_GAIN_TRAILING_STEPS[0][0] if MICRO_GAIN_TRAILING_MODE == "steps" else MICRO_GAIN_TRAILING_ACTIVATION
                                tj.log_trailing_activated(
                                    open_trade['trade_uuid'],
                                    current_price, pnl_pct,
                                    activation_pct
                                )
                                log(f"   📒 Trade Journal: trailing MICRO_GAIN attivato ({mode_str})")
                            # Log SL update
                            tj.log_trailing_updated(
                                open_trade['trade_uuid'],
                                old_sl, new_sl_level,
                                current_price, current_price, pnl_pct
                            )
                            # Update peak
                            tj.update_trade_peak(open_trade['trade_uuid'], current_price, pnl_pct)
                            log(f"   📒 Trade Journal: SL MICRO_GAIN {old_sl:+.2f}% → {new_sl_level:+.2f}%")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal error: {e}")

                return True
            else:
                log(f"   ⚠️ Errore SL: {sl_order}")

        return False

    except Exception as e:
        log(f"   ❌ Errore update MICRO_GAIN SL: {e}")
        return False


def get_step_sl_level(pnl_pct: float, current_sl: float, steps: list) -> float:
    """
    Calcola il livello SL basato sui gradini configurati.

    Args:
        pnl_pct: P&L corrente in percentuale
        current_sl: SL corrente in percentuale
        steps: Lista di tuple (pnl_threshold, sl_level)

    Returns:
        Nuovo livello SL (o current_sl se non cambia)
    """
    new_sl = current_sl

    # Trova il gradino più alto raggiunto
    for pnl_threshold, sl_level in steps:
        if pnl_pct >= pnl_threshold and sl_level > new_sl:
            new_sl = sl_level

    return new_sl


def update_normal_sl_order(bot, symbol: str, direction: str, entry_price: float,
                           current_price: float, size: float, leverage: float):
    """
    Aggiorna l'ordine SL per posizioni NORMAL.

    Supporta due modalità (configurabile via NORMAL_TRAILING_MODE):

    1. "continuous" - Trailing continuo classico:
       - Se P&L >= NORMAL_TRAILING_ACTIVATION, inizia il trailing
       - SL segue il P&L mantenendo un gap di NORMAL_TRAILING_GAP
       - SL non scende mai, solo sale

    2. "steps" - Trailing a gradini (più conservativo):
       - SL si alza solo a livelli predefiniti
       - Esempio: a +3% P&L -> SL=0%, a +5% -> SL=+2%, etc.
       - Meno sensibile alle oscillazioni di mercato

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        current_price: Prezzo corrente
        size: Size della posizione
        leverage: Leva usata

    Returns:
        bool: True se SL è stato aggiornato
    """
    global _current_sl_level

    if not NORMAL_TRAILING_ENABLED:
        return False

    # Se trailing disabilitato, esci subito
    if NORMAL_TRAILING_MODE == "disable":
        return False

    try:
        # Calcola P&L corrente
        if direction == "long":
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            price_change_pct = ((entry_price - current_price) / entry_price) * 100

        pnl_pct = price_change_pct * leverage

        # SL corrente (iniziale = -NORMAL_STOP_LOSS_PERCENT)
        sl_key = f"{symbol}_NORMAL"
        current_sl = _current_sl_level.get(sl_key, -NORMAL_STOP_LOSS_PERCENT)

        # Log stato trailing con indicazione modalità
        mode_str = NORMAL_TRAILING_MODE.upper()
        log(f"   📊 {symbol} NORMAL ({mode_str}): P&L={pnl_pct:+.2f}% | SL={current_sl:+.2f}%")

        # Calcola nuovo SL in base alla modalità
        new_sl_level = None

        if NORMAL_TRAILING_MODE == "steps":
            # === MODALITÀ GRADINI ===
            # SL si alza solo quando si raggiunge un nuovo gradino
            step_sl = get_step_sl_level(pnl_pct, current_sl, NORMAL_TRAILING_STEPS)

            if step_sl > current_sl:
                new_sl_level = step_sl
                # Trova quale gradino è stato raggiunto per il log
                step_reached = None
                for pnl_threshold, sl_level in NORMAL_TRAILING_STEPS:
                    if sl_level == step_sl:
                        step_reached = pnl_threshold
                        break
                log(f"   📶 STEP RAGGIUNTO! P&L >= +{step_reached}% → SL sale a {new_sl_level:+.2f}%")
        else:
            # === MODALITÀ CONTINUA (classica) ===
            if pnl_pct >= NORMAL_TRAILING_ACTIVATION:
                continuous_sl = pnl_pct - NORMAL_TRAILING_GAP
                if continuous_sl > current_sl:
                    new_sl_level = continuous_sl
                    log(f"   📈 TRAILING CONTINUO: P&L={pnl_pct:+.2f}% | SL: {current_sl:+.2f}% → {new_sl_level:+.2f}%")

        # Se c'è un nuovo SL da impostare
        if new_sl_level is not None and new_sl_level > current_sl:
            # Calcola prezzo SL
            sl_price_change = new_sl_level / leverage

            if direction == "long":
                new_sl_price = entry_price * (1 + sl_price_change / 100)
            else:
                new_sl_price = entry_price * (1 - sl_price_change / 100)

            new_sl_price = bot._round_to_tick(new_sl_price, symbol)

            # Cancella ordini SL esistenti
            try:
                open_orders = bot.info.open_orders(bot.account_address)
                for order in open_orders:
                    if order.get("coin") == symbol:
                        # Cancella solo ordini SL (lato opposto alla posizione)
                        expected_side = "B" if direction == "short" else "A"
                        if order.get("side") == expected_side:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            log(f"   🗑️ Cancellato SL precedente")
            except Exception as e:
                log(f"   ⚠️ Errore cancellazione: {e}")

            # Piazza nuovo SL STOP (trigger order)
            is_buy = direction == "short"

            sl_order = bot.exchange.order(
                symbol,
                is_buy,
                size,
                new_sl_price,
                {"trigger": {"triggerPx": new_sl_price, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") == "ok":
                old_sl = current_sl
                _current_sl_level[sl_key] = new_sl_level
                log(f"   🔒 NORMAL SL STOP @ ${new_sl_price:.2f} ({new_sl_level:+.2f}%)")

                # Trade Journal: log trailing per NORMAL mode
                if TRADE_JOURNAL_ENABLED:
                    try:
                        open_trade = tj.get_open_trade(symbol)
                        if open_trade:
                            # Log trailing activation se è il primo trailing update
                            if old_sl <= -NORMAL_STOP_LOSS_PERCENT + 0.1:
                                # Per steps, usa il primo gradino come activation
                                activation_pct = NORMAL_TRAILING_STEPS[0][0] if NORMAL_TRAILING_MODE == "steps" else NORMAL_TRAILING_ACTIVATION
                                tj.log_trailing_activated(
                                    open_trade['trade_uuid'],
                                    current_price, pnl_pct,
                                    activation_pct
                                )
                                log(f"   📒 Trade Journal: trailing NORMAL attivato ({mode_str})")
                            # Log SL update
                            tj.log_trailing_updated(
                                open_trade['trade_uuid'],
                                old_sl, new_sl_level,
                                current_price, current_price, pnl_pct
                            )
                            # Update peak
                            tj.update_trade_peak(open_trade['trade_uuid'], current_price, pnl_pct)
                            log(f"   📒 Trade Journal: SL NORMAL {old_sl:+.2f}% → {new_sl_level:+.2f}%")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal NORMAL error: {e}")

                return True
            else:
                log(f"   ⚠️ Errore SL: {sl_order}")

        return False

    except Exception as e:
        log(f"   ❌ Errore update NORMAL SL: {e}")
        return False


def place_normal_initial_sl(bot, symbol: str, direction: str, entry_price: float, size: float, leverage: float):
    """
    Piazza l'ordine SL iniziale per posizioni NORMAL se non esiste.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size della posizione
        leverage: Leva usata
    """
    if not NORMAL_TRAILING_ENABLED:
        return False

    sl_key = f"{symbol}_NORMAL"

    # Se già esiste SL level in memoria, non ricreare
    if sl_key in _current_sl_level:
        return False

    try:
        # IMPORTANTE: Controlla se esiste già un ordine SL su Hyperliquid
        # Questo previene duplicati quando il container viene riavviato
        expected_side = "B" if direction == "short" else "A"
        try:
            open_orders = bot.info.frontend_open_orders(bot.account_address)
            for order in open_orders:
                if order.get("coin") == symbol and order.get("side") == expected_side:
                    trigger_px = order.get("triggerPx")
                    if trigger_px and trigger_px != "0.0":
                        # SL già esiste su Hyperliquid - CALCOLA il livello reale dal prezzo
                        trigger_price = float(trigger_px)

                        # Calcola la percentuale SL reale basata sul prezzo trigger
                        if direction == "long":
                            # Long: SL sotto entry = negativo, sopra entry = positivo
                            price_diff_pct = ((trigger_price - entry_price) / entry_price) * 100
                        else:
                            # Short: SL sopra entry = negativo, sotto entry = positivo
                            price_diff_pct = ((entry_price - trigger_price) / entry_price) * 100

                        # Moltiplica per leva per ottenere il livello SL in %
                        calculated_sl_level = price_diff_pct * leverage

                        _current_sl_level[sl_key] = calculated_sl_level
                        log(f"   ✅ {symbol} SL già esistente su HL (trigger=${trigger_px}), livello calcolato: {calculated_sl_level:+.2f}%")
                        return False
        except Exception as e:
            log(f"   ⚠️ Errore check ordini esistenti: {e}")

        # Calcola prezzo SL iniziale
        price_change_pct = NORMAL_STOP_LOSS_PERCENT / leverage

        if direction == "long":
            sl_price = entry_price * (1 - price_change_pct / 100)
        else:
            sl_price = entry_price * (1 + price_change_pct / 100)

        sl_price = bot._round_to_tick(sl_price, symbol)

        log(f"   🛡️ Piazzo NORMAL SL STOP @ ${sl_price:.2f} (trigger, loss: -{NORMAL_STOP_LOSS_PERCENT}%)")

        is_buy = direction == "short"

        # Usa trigger order invece di limit order
        sl_order = bot.exchange.order(
            symbol,
            is_buy,
            size,
            sl_price,
            {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True
        )

        if sl_order.get("status") == "ok":
            _current_sl_level[sl_key] = -NORMAL_STOP_LOSS_PERCENT
            log(f"   ✅ NORMAL SL order piazzato")

            # Trade Journal: registra SL placement per NORMAL mode
            if TRADE_JOURNAL_ENABLED:
                try:
                    open_trade = tj.get_open_trade(symbol)
                    if open_trade:
                        tj.log_sl_placed(open_trade['trade_uuid'], sl_price, "STOP_TRIGGER", entry_price)
                        log(f"   📒 Trade Journal: SL NORMAL registrato @ ${sl_price:.2f}")
                except Exception as e:
                    log(f"   ⚠️ Trade Journal NORMAL SL log error: {e}")

            return True

        log(f"   ⚠️ NORMAL SL response: {sl_order}")
        return False

    except Exception as e:
        log(f"   ❌ Errore piazzamento NORMAL SL: {e}")
        return False


# ============================================================================
# ORDER VERIFICATION SYSTEM - Controllo automatico ordini SL
# ============================================================================

# Tolleranza per confronto prezzi (0.5% - per gestire arrotondamenti)
PRICE_TOLERANCE_PERCENT = 0.5
# Tolleranza per confronto size (1% - per gestire arrotondamenti)
SIZE_TOLERANCE_PERCENT = 1.0


def calculate_expected_sl_price(entry_price: float, direction: str, leverage: float,
                                  trading_mode: str, current_sl_level: float = None) -> float:
    """
    Calcola il prezzo SL atteso per una posizione.

    IMPORTANTE: Se current_sl_level è fornito, usa quello invece del valore iniziale.
    Questo permette di verificare correttamente lo SL dopo che il trailing l'ha spostato.

    Args:
        entry_price: Prezzo di entrata
        direction: 'long' o 'short'
        leverage: Leva della posizione
        trading_mode: 'MICRO_GAIN', 'MICRO_PAY' o 'NORMAL'
        current_sl_level: Livello SL corrente in % (es. -5.0 o +0.6). Se None, usa il default.
    """
    # Determina la leva da usare
    if trading_mode == "MICRO_GAIN":
        lev = MICRO_GAIN_LEVERAGE
        default_sl_pct = MICRO_GAIN_STOP_LOSS_PERCENT
    elif trading_mode == "MICRO_PAY":
        lev = MICRO_PAY_LEVERAGE
        default_sl_pct = MICRO_PAY_STOP_LOSS_PERCENT
    else:
        lev = leverage
        default_sl_pct = NORMAL_STOP_LOSS_PERCENT

    # Usa current_sl_level se fornito, altrimenti il default
    # current_sl_level è in termini di P&L% (es. -5.0 per perdita 5%, +0.6 per profit 0.6%)
    if current_sl_level is not None:
        sl_pct = current_sl_level
    else:
        sl_pct = -default_sl_pct  # Negativo perché è una perdita

    # Converti da P&L% a movimento prezzo%
    # P&L% = price_change% * leverage
    # price_change% = P&L% / leverage
    price_change_pct = sl_pct / lev

    # Calcola prezzo SL
    if direction == "long":
        # Per LONG: SL negativo = prezzo sotto entry, SL positivo = prezzo sopra entry
        return entry_price * (1 + price_change_pct / 100)
    else:
        # Per SHORT: SL negativo = prezzo sopra entry, SL positivo = prezzo sotto entry
        return entry_price * (1 - price_change_pct / 100)


def verify_sl_order_complete(bot, symbol: str, direction: str, entry_price: float,
                              size: float, leverage: float, trading_mode: str = "NORMAL",
                              current_sl_level: float = None) -> dict:
    """
    Verifica COMPLETA di un ordine SL: esistenza, tipo, prezzo, size, direzione.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo della posizione
        direction: Direzione della posizione ('long' o 'short')
        entry_price: Prezzo di entrata
        size: Size della posizione
        leverage: Leva usata
        trading_mode: 'MICRO_GAIN' o 'NORMAL'
        current_sl_level: Livello SL corrente in % (da _current_sl_level). Se None, usa default.

    Returns:
        dict con:
            - exists: bool - se esiste un ordine SL
            - is_trigger: bool - se è di tipo STOP trigger
            - is_correct_price: bool - se il prezzo è corretto
            - is_correct_size: bool - se la size è corretta
            - is_correct_side: bool - se la direzione è corretta
            - all_valid: bool - se tutto è corretto
            - order: dict - dati ordine se esiste
            - issues: list - lista problemi rilevati
            - error: str - messaggio errore se c'è problema
    """
    result = {
        "exists": False,
        "is_trigger": False,
        "is_correct_price": False,
        "is_correct_size": False,
        "is_correct_side": False,
        "all_valid": False,
        "order": None,
        "issues": [],
        "expected_price": 0,
        "actual_price": 0,
        "expected_size": size,
        "actual_size": 0,
        "error": None
    }

    try:
        # Lato ordine SL: opposto alla posizione
        expected_side = "B" if direction == "short" else "A"

        # Calcola prezzo SL atteso (usando current_sl_level se disponibile)
        expected_sl_price = calculate_expected_sl_price(entry_price, direction, leverage, trading_mode, current_sl_level)
        result["expected_price"] = expected_sl_price

        # Usa frontend_open_orders per avere tutti i dettagli (incluso triggerPx)
        # open_orders() NON ritorna triggerPx, solo: coin, limitPx, oid, side, sz, timestamp
        try:
            open_orders = bot.info.frontend_open_orders(bot.account_address)
        except AttributeError:
            # Fallback per versioni SDK senza frontend_open_orders
            log(f"   ⚠️ SDK senza frontend_open_orders, uso open_orders (verifica tipo non disponibile)")
            open_orders = bot.info.open_orders(bot.account_address)

        for order in open_orders:
            if order.get("coin") == symbol and order.get("side") == expected_side:
                result["exists"] = True
                result["order"] = order

                # 1. Verifica tipo (STOP trigger)
                # frontend_open_orders ritorna triggerPx come stringa (es. "92270.0" o "0.0")
                trigger_px = order.get("triggerPx")
                # Un ordine è TRIGGER se triggerPx esiste E NON è "0.0" o vuoto
                is_trigger = trigger_px is not None and trigger_px != "" and trigger_px != "0.0"
                result["is_trigger"] = is_trigger
                if not is_trigger:
                    result["issues"].append("TIPO: ordine LIMIT invece di STOP TRIGGER")

                # 2. Verifica prezzo trigger
                if trigger_px:
                    actual_price = float(trigger_px)
                    result["actual_price"] = actual_price

                    # Tolleranza sul prezzo
                    price_diff_pct = abs(actual_price - expected_sl_price) / expected_sl_price * 100
                    result["is_correct_price"] = price_diff_pct <= PRICE_TOLERANCE_PERCENT

                    if not result["is_correct_price"]:
                        result["issues"].append(
                            f"PREZZO: trigger ${actual_price:.4f} vs atteso ${expected_sl_price:.4f} "
                            f"(diff: {price_diff_pct:.2f}%)"
                        )
                else:
                    result["issues"].append("PREZZO: nessun trigger price impostato")

                # 3. Verifica size
                order_size = float(order.get("sz", 0))
                result["actual_size"] = order_size

                size_diff_pct = abs(order_size - size) / size * 100 if size > 0 else 100
                result["is_correct_size"] = size_diff_pct <= SIZE_TOLERANCE_PERCENT

                if not result["is_correct_size"]:
                    result["issues"].append(
                        f"SIZE: {order_size:.6f} vs attesa {size:.6f} (diff: {size_diff_pct:.2f}%)"
                    )

                # 4. Verifica side (già verificato nel filtro, ma double-check)
                actual_side = order.get("side")
                result["is_correct_side"] = actual_side == expected_side

                if not result["is_correct_side"]:
                    result["issues"].append(
                        f"SIDE: {actual_side} vs atteso {expected_side}"
                    )

                # Tutto valido?
                result["all_valid"] = (
                    result["is_trigger"] and
                    result["is_correct_price"] and
                    result["is_correct_size"] and
                    result["is_correct_side"]
                )

                return result

        # Nessun ordine trovato
        result["issues"].append(f"Nessun ordine SL trovato per {symbol}")
        return result

    except Exception as e:
        result["error"] = str(e)
        result["issues"].append(f"Errore verifica: {e}")
        return result


def verify_and_fix_sl_order(bot, symbol: str, direction: str, entry_price: float,
                             size: float, leverage: float, trading_mode: str = "NORMAL",
                             max_retries: int = 2, current_sl_level: float = None) -> dict:
    """
    Verifica COMPLETA che l'ordine SL esista e sia corretto (tipo, prezzo, size, direzione).
    Se manca o è sbagliato, tenta di correggerlo automaticamente.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size posizione
        leverage: Leva usata
        trading_mode: 'MICRO_GAIN' o 'NORMAL'
        max_retries: Numero massimo tentativi
        current_sl_level: Livello SL corrente in % (da _current_sl_level). Se None, usa default.

    Returns:
        dict con status della verifica/fix
    """
    import telegram_notifier as tg

    result = {
        "verified": False,
        "was_missing": False,
        "was_wrong_type": False,
        "was_wrong_values": False,
        "fixed": False,
        "attempts": 0,
        "issues": [],
        "error": None
    }

    for attempt in range(max_retries + 1):
        result["attempts"] = attempt + 1

        # Verifica COMPLETA ordine esistente (con current_sl_level per trailing)
        check = verify_sl_order_complete(
            bot, symbol, direction, entry_price, size, leverage, trading_mode, current_sl_level
        )

        if check["all_valid"]:
            # Ordine esiste ed è completamente corretto
            result["verified"] = True
            if attempt > 0:
                result["fixed"] = True
                log(f"   ✅ {symbol} SL STOP TRIGGER verificato (corretto al tentativo {attempt + 1})")
            else:
                log(f"   ✅ {symbol} SL STOP TRIGGER OK: trigger=${check['actual_price']:.4f}, size={check['actual_size']:.6f}")
            return result

        # Se l'ordine esiste ma ha problemi
        if check["exists"]:
            result["issues"] = check["issues"]

            if not check["is_trigger"]:
                result["was_wrong_type"] = True
                log(f"   ⚠️ {symbol} SL è LIMIT invece di STOP TRIGGER")
            else:
                result["was_wrong_values"] = True
                for issue in check["issues"]:
                    log(f"   ⚠️ {symbol} {issue}")

            # Cancella ordine sbagliato
            log(f"   🗑️ Cancello ordine errato per {symbol}...")
            try:
                bot.exchange.cancel(symbol, check["order"].get("oid"))
                log(f"   ✅ Ordine cancellato")
                time.sleep(0.5)
            except Exception as e:
                log(f"   ❌ Errore cancellazione: {e}")
        else:
            result["was_missing"] = True
            log(f"   ⚠️ {symbol} SL mancante")

        # Piazza nuovo ordine SL corretto
        log(f"   🔄 Piazzo nuovo SL per {symbol} (tentativo {attempt + 1}/{max_retries + 1})...")

        sl_price = None
        if trading_mode == "MICRO_GAIN":
            sl_price = place_micro_gain_sl_order(bot, symbol, direction, entry_price, size)
        else:
            # Per NORMAL mode - usa current_sl_level se disponibile (trailing attivo)
            if current_sl_level is not None:
                # current_sl_level è già in % rispetto all'entry (es. +0.60% o -5.0%)
                sl_pct = current_sl_level
                log(f"   📊 Usando current_sl_level: {sl_pct:+.2f}%")
            else:
                # Fallback al valore iniziale
                sl_pct = -NORMAL_STOP_LOSS_PERCENT
                log(f"   📊 Usando SL iniziale: {sl_pct:.2f}%")

            # Calcola prezzo SL basato sulla percentuale
            price_change_pct = abs(sl_pct) / leverage
            if direction == "long":
                if sl_pct >= 0:
                    # Trailing attivo: SL sopra entry (in profitto)
                    sl_price = entry_price * (1 + price_change_pct / 100)
                else:
                    # SL sotto entry (in perdita)
                    sl_price = entry_price * (1 - price_change_pct / 100)
            else:  # short
                if sl_pct >= 0:
                    # Trailing attivo: SL sotto entry (in profitto per short)
                    sl_price = entry_price * (1 - price_change_pct / 100)
                else:
                    # SL sopra entry (in perdita per short)
                    sl_price = entry_price * (1 + price_change_pct / 100)
            sl_price = bot._round_to_tick(sl_price, symbol)

            is_buy = direction == "short"
            sl_order = bot.exchange.order(
                symbol,
                is_buy,
                size,
                sl_price,
                {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") != "ok":
                log(f"   ❌ Errore API: {sl_order}")
                sl_price = None

        if sl_price:
            log(f"   ✅ Nuovo SL piazzato @ ${sl_price:.4f}")
            time.sleep(0.5)  # Pausa per sincronizzazione
        else:
            log(f"   ❌ Fallito piazzamento SL")

    # Se arriviamo qui, tutti i tentativi sono falliti
    issues_str = ", ".join(result["issues"]) if result["issues"] else "ordine mancante"
    result["error"] = f"Impossibile correggere SL per {symbol} dopo {max_retries + 1} tentativi: {issues_str}"

    # ALERT CRITICO - notifica immediata
    log(f"   🚨 ALERT CRITICO: {result['error']}")

    if SENTINEL_TELEGRAM_NOTIFY:
        try:
            issues_list = "\n".join([f"• {i}" for i in result["issues"]]) if result["issues"] else "• Ordine mancante"
            tg.send_telegram_message(
                f"🚨 <b>ALERT CRITICO - SL NON VALIDO</b>\n\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Direction:</b> {direction.upper()}\n"
                f"<b>Entry:</b> ${entry_price:.2f}\n"
                f"<b>Size:</b> {size:.6f}\n"
                f"<b>Mode:</b> {trading_mode}\n\n"
                f"<b>Problemi rilevati:</b>\n{issues_list}\n\n"
                f"⚠️ <b>POSIZIONE CON SL NON VALIDO!</b>\n"
                f"Tentativi falliti: {result['attempts']}\n\n"
                f"<b>Azione richiesta:</b> verifica manuale immediata"
            )
        except Exception as e:
            log(f"   ⚠️ Errore invio alert Telegram: {e}")

    return result


def run_order_verification(bot, positions: list) -> dict:
    """
    Esegue verifica ordini per tutte le posizioni aperte.

    Args:
        bot: HyperLiquidTrader instance
        positions: Lista posizioni aperte

    Returns:
        dict con summary della verifica
    """
    import db_utils

    summary = {
        "total_positions": len(positions),
        "verified_ok": 0,
        "fixed": 0,
        "failed": 0,
        "details": []
    }

    log(f"🔍 Verifica ordini SL per {len(positions)} posizioni...")

    for pos in positions:
        symbol = pos.get("symbol", "")
        direction = pos.get("side", "long").lower()
        entry_price = float(pos.get("entry_price", 0))
        size = float(pos.get("size", 0))

        # Parse leverage
        leverage_raw = pos.get("leverage", 1)
        if isinstance(leverage_raw, str):
            import re
            match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
            leverage = float(match.group(1)) if match else 1.0
        else:
            leverage = float(leverage_raw)

        # Determina trading mode
        tracking_data = db_utils.get_position_tracking(symbol)
        trading_mode = tracking_data.get("trading_mode", "NORMAL") if tracking_data else "NORMAL"

        # Recupera current_sl_level dalla memoria (aggiornato dal trailing)
        # La chiave dipende dal trading_mode:
        # - MICRO_GAIN: symbol (es. "SOL")
        # - NORMAL: symbol_NORMAL (es. "SOL_NORMAL")
        if trading_mode == "MICRO_GAIN":
            sl_key = symbol
        else:
            sl_key = f"{symbol}_NORMAL"
        current_sl_level = _current_sl_level.get(sl_key)

        # Verifica e correggi se necessario (passa current_sl_level per trailing)
        result = verify_and_fix_sl_order(
            bot, symbol, direction, entry_price, size, leverage, trading_mode,
            current_sl_level=current_sl_level
        )

        detail = {
            "symbol": symbol,
            "trading_mode": trading_mode,
            "verified": result["verified"],
            "was_missing": result["was_missing"],
            "was_wrong_type": result.get("was_wrong_type", False),
            "was_wrong_values": result.get("was_wrong_values", False),
            "fixed": result["fixed"],
            "issues": result.get("issues", []),
            "error": result["error"]
        }
        summary["details"].append(detail)

        if result["verified"]:
            if result["fixed"]:
                summary["fixed"] += 1
                # Log già fatto in verify_and_fix_sl_order
            else:
                summary["verified_ok"] += 1
        else:
            summary["failed"] += 1
            # Log già fatto in verify_and_fix_sl_order

    # Log summary
    log(f"📋 Verifica completata: {summary['verified_ok']} OK, {summary['fixed']} corretti, {summary['failed']} FALLITI")

    return summary


def check_and_open_micro_gain(bot, existing_symbols: list):
    """
    Controlla se aprire nuove posizioni MICRO_GAIN o MICRO_PAY.

    Schema soglie:
    - HOLD: score < MICRO_PAY_THRESHOLD (se MICRO_PAY abilitato) o < SCORE_THRESHOLD_HOLD
    - MICRO_PAY: MICRO_PAY_THRESHOLD <= score < SCORE_THRESHOLD_HOLD (se abilitato)
    - MICRO_GAIN: SCORE_THRESHOLD_HOLD <= score < SCORE_THRESHOLD_OPEN
    - NORMAL: score >= SCORE_THRESHOLD_OPEN (gestito da main.py AI)

    Args:
        bot: HyperLiquidTrader instance
        existing_symbols: Lista simboli con posizioni già aperte
    """
    if not MICRO_GAIN_AUTO_OPEN:
        return

    symbols_to_check = ['BTC', 'ETH', 'SOL']

    # Conta posizioni esistenti
    position_count = len(existing_symbols)

    for symbol in symbols_to_check:
        # Skip se già abbiamo posizione
        if symbol in existing_symbols:
            continue

        # Skip se in cooldown (usa il cooldown appropriato)
        if is_in_cooldown(symbol):
            # Calcola remaining basato sul cooldown più lungo tra MICRO_GAIN e MICRO_PAY
            cooldown_used = max(MICRO_GAIN_COOLDOWN_SECONDS, MICRO_PAY_COOLDOWN_SECONDS if MICRO_PAY_ENABLED else 0)
            remaining = cooldown_used - (time.time() - _last_close_time.get(symbol, 0))
            if remaining > 0:
                log(f"   ⏱️ {symbol} in cooldown ({remaining:.0f}s rimanenti)")
                continue

        # Skip se abbiamo raggiunto max posizioni
        if position_count >= MICRO_GAIN_MAX_POSITIONS:
            log(f"   ⚠️ Max posizioni raggiunte ({MICRO_GAIN_MAX_POSITIONS})")
            break

        # Calcola score
        score = calculate_quick_score(symbol)
        abs_score = abs(score)

        log(f"   📊 {symbol} quick_score: {score:.1f}")

        direction = "long" if score > 0 else "short"

        # Determina quale modalità usare basata sullo score
        # Priority: MICRO_GAIN > MICRO_PAY (score più alto = più sicuro)

        if SCORE_THRESHOLD_HOLD <= abs_score < SCORE_THRESHOLD_OPEN:
            # === MICRO_GAIN RANGE (15-20) ===
            result = open_micro_gain_position(bot, symbol, direction, score)

            if result.get("success"):
                position_count += 1
                existing_symbols.append(symbol)

        elif MICRO_PAY_ENABLED and MICRO_PAY_THRESHOLD <= abs_score < SCORE_THRESHOLD_HOLD:
            # === MICRO_PAY RANGE (5-15) ===
            log(f"   💵 {symbol} in range MICRO_PAY ({MICRO_PAY_THRESHOLD}-{SCORE_THRESHOLD_HOLD})")

            result = open_micro_pay_position(bot, symbol, direction, score)

            if result.get("success"):
                position_count += 1
                existing_symbols.append(symbol)


def check_take_profit(position: dict) -> dict:
    """
    Controlla se take profit è triggerato.

    Calcola il P&L reale considerando la leva.

    Returns:
        dict con triggered, reason, pnl_pct
    """
    if not TAKE_PROFIT_ENABLED:
        return {"triggered": False, "reason": "Disabled", "pnl_pct": 0}

    direction = position.get("side", "long").lower()
    entry_price = float(position.get("entry_price", 0))
    current_price = float(position.get("mark_price", 0))

    # Parse leverage (può essere "3x (cross)" o numero)
    leverage_raw = position.get("leverage", 1)
    if isinstance(leverage_raw, str):
        # Estrai il numero da stringhe tipo "3x (cross)"
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        leverage = float(match.group(1)) if match else 1.0
    else:
        leverage = float(leverage_raw)

    if entry_price == 0 or current_price == 0:
        return {"triggered": False, "reason": "No price", "pnl_pct": 0}

    # Calcola movimento prezzo
    if direction == "long":
        price_change_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        price_change_pct = ((entry_price - current_price) / entry_price) * 100

    # P&L reale = movimento prezzo * leva
    pnl_pct = price_change_pct * leverage

    result = {
        "triggered": False,
        "reason": "",
        "pnl_pct": pnl_pct,
        "price_change_pct": price_change_pct,
        "leverage": leverage
    }

    # Check take profit
    if pnl_pct >= TAKE_PROFIT_PERCENT:
        result["triggered"] = True
        result["reason"] = f"TAKE PROFIT: +{pnl_pct:.2f}% P&L (soglia +{TAKE_PROFIT_PERCENT}%, leva {leverage}x)"

    return result


def check_trailing_stop(position: dict, tracking_data: dict = None) -> dict:
    """
    Controlla se trailing stop o stop loss è triggerato.

    Calcola P&L reale considerando la leva.

    Returns:
        dict con triggered, reason, trailing_active, new_peak
    """
    if not TRAILING_STOP_ENABLED:
        return {"triggered": False, "reason": "Disabled", "trailing_active": False}

    direction = position.get("side", "long").lower()
    entry_price = float(position.get("entry_price", 0))
    current_price = float(position.get("mark_price", 0))

    # Parse leverage (può essere "3x (cross)" o numero)
    leverage_raw = position.get("leverage", 1)
    if isinstance(leverage_raw, str):
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        leverage = float(match.group(1)) if match else 1.0
    else:
        leverage = float(leverage_raw)

    if entry_price == 0 or current_price == 0:
        return {"triggered": False, "reason": "No price", "trailing_active": False}

    # Calcola movimento prezzo (senza leva)
    if direction == "long":
        price_change_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        price_change_pct = ((entry_price - current_price) / entry_price) * 100

    # P&L reale = movimento prezzo * leva
    pnl_pct = price_change_pct * leverage

    # Peak price dal tracking
    if tracking_data:
        peak_price = tracking_data.get("peak_price", current_price)
        trailing_active = tracking_data.get("trailing_active", False)
    else:
        peak_price = current_price
        trailing_active = False

    # Aggiorna peak
    if direction == "long":
        new_peak = max(peak_price, current_price)
    else:
        new_peak = min(peak_price, current_price)

    # Calcola distanza dal peak (movimento prezzo)
    if direction == "long":
        price_change_from_peak_pct = ((current_price - new_peak) / new_peak) * 100
    else:
        price_change_from_peak_pct = ((new_peak - current_price) / new_peak) * 100

    # P&L dal peak = movimento dal peak * leva
    pnl_from_peak_pct = price_change_from_peak_pct * leverage

    # Attiva trailing se P&L reale >= soglia (soglia interpretata come P&L reale)
    if pnl_pct >= TRAILING_STOP_ACTIVATION_PERCENT:
        trailing_active = True

    result = {
        "triggered": False,
        "reason": "",
        "trailing_active": trailing_active,
        "new_peak": new_peak,
        "profit_pct": price_change_pct,  # Movimento prezzo (per compatibilità log)
        "profit_from_peak_pct": price_change_from_peak_pct,  # Per compatibilità log
        "pnl_pct": pnl_pct,  # P&L reale
        "pnl_from_peak_pct": pnl_from_peak_pct,  # P&L reale dal peak
        "leverage": leverage
    }

    # Check stop loss iniziale (usa P&L reale)
    if not trailing_active and pnl_pct <= -INITIAL_STOP_LOSS_PERCENT:
        result["triggered"] = True
        result["reason"] = f"STOP LOSS: {pnl_pct:.2f}% P&L (soglia -{INITIAL_STOP_LOSS_PERCENT}%, leva {leverage}x)"
        return result

    # Check trailing stop (usa P&L reale dal peak)
    if trailing_active and pnl_from_peak_pct <= -TRAILING_STOP_PERCENT:
        result["triggered"] = True
        result["reason"] = f"TRAILING STOP: {-pnl_from_peak_pct:.2f}% P&L dal peak (soglia {TRAILING_STOP_PERCENT}%, leva {leverage}x)"
        return result

    return result


def run_sentinel_check():
    """Esegue un singolo controllo di tutte le posizioni."""

    if not SENTINEL_ENABLED:
        log("Sentinel disabilitato (SENTINEL_ENABLED=false)")
        return

    if not TRAILING_STOP_ENABLED:
        log("Trailing stop disabilitato (TRAILING_STOP_ENABLED=false)")
        return

    if not PRIVATE_KEY or not WALLET_ADDRESS:
        log("PRIVATE_KEY o WALLET_ADDRESS mancanti")
        return

    # Import qui per evitare errori se mancano dipendenze
    try:
        from hyperliquid_trader import HyperLiquidTrader
        import db_utils
        import telegram_notifier as tg
    except ImportError as e:
        log(f"Errore import: {e}")
        return

    try:
        # Connetti a Hyperliquid
        bot = HyperLiquidTrader(
            secret_key=PRIVATE_KEY,
            account_address=WALLET_ADDRESS,
            testnet=TESTNET
        )

        # Ottieni posizioni aperte
        account_status = bot.get_account_status()
        positions = account_status.get("open_positions", [])

        # Lista simboli con posizioni aperte
        existing_symbols = [p.get("symbol") for p in positions]

        # === DETECT EXTERNALLY CLOSED POSITIONS ===
        # Controlla se ci sono posizioni tracciate che non esistono più
        # (chiuse da TP/SL su Hyperliquid)
        detect_externally_closed_positions(bot, existing_symbols)

        if not positions:
            log("Nessuna posizione aperta")
            # === CHECK MICRO_GAIN AUTO-OPEN ===
            if MICRO_GAIN_AUTO_OPEN:
                log("🔍 Controllo opportunità MICRO_GAIN...")
                check_and_open_micro_gain(bot, existing_symbols)
            return

        log(f"Controllo {len(positions)} posizioni...")

        # === CHECK MICRO_GAIN AUTO-OPEN (se abbiamo meno di MAX posizioni) ===
        if MICRO_GAIN_AUTO_OPEN and len(positions) < MICRO_GAIN_MAX_POSITIONS:
            log(f"🔍 Controllo opportunità MICRO_GAIN ({len(positions)}/{MICRO_GAIN_MAX_POSITIONS} posizioni)...")
            check_and_open_micro_gain(bot, existing_symbols)

        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("side", "")
            entry_price = pos.get("entry_price", 0)
            mark_price = pos.get("mark_price", 0)
            pnl = pos.get("pnl_usd", 0)

            leverage = pos.get("leverage", 1)

            # Ottieni tracking dal DB
            tracking_data = db_utils.get_position_tracking(symbol)

            # Ottieni trading_mode dal tracking
            trading_mode = tracking_data.get("trading_mode", "NORMAL") if tracking_data else "NORMAL"

            # === CHECK TAKE PROFIT (prima del trailing stop) ===
            tp_result = check_take_profit(pos)
            tp_triggered = tp_result.get("triggered", False)
            pnl_pct = tp_result.get("pnl_pct", 0)

            # === CHECK MICRO_GAIN REVERSAL ===
            micro_gain_result = {"triggered": False, "reason": "", "quick_score": 0.0}
            position_size = float(pos.get("size", 0))

            # Parse leverage
            leverage_raw = pos.get("leverage", 1)
            if isinstance(leverage_raw, str):
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                pos_leverage = float(match.group(1)) if match else 1.0
            else:
                pos_leverage = float(leverage_raw)

            if trading_mode == "MICRO_GAIN" and tracking_data:
                micro_gain_result = check_micro_gain_reversal(pos, tracking_data)

                # === UPDATE MICRO_GAIN TRAILING SL (lock-in profit) ===
                if position_size > 0:
                    update_micro_gain_sl_order(
                        bot, symbol, direction, entry_price, mark_price, position_size
                    )

            elif trading_mode == "NORMAL" and NORMAL_TRAILING_ENABLED:
                # === UPDATE NORMAL TRAILING SL (same mechanism, different params) ===
                if position_size > 0:
                    # Prima piazza SL iniziale se non esiste
                    place_normal_initial_sl(
                        bot, symbol, direction, entry_price, position_size, pos_leverage
                    )
                    # Poi aggiorna se in profitto
                    update_normal_sl_order(
                        bot, symbol, direction, entry_price, mark_price, position_size, pos_leverage
                    )

            # === CHECK TRAILING STOP (solo per NORMAL mode) ===
            result = check_trailing_stop(pos, tracking_data)

            # Aggiorna tracking nel DB
            db_utils.upsert_position_tracking(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                current_price=mark_price,
                trailing_active=result.get("trailing_active", False)
            )

            profit_pct = result.get("profit_pct", 0)
            profit_from_peak_pct = result.get("profit_from_peak_pct", 0)
            new_peak = result.get("new_peak", mark_price)
            trailing_status = "ACTIVE" if result.get("trailing_active") else "inactive"

            # Determina azione
            action_taken = None
            action_reason = None
            should_close = False
            close_reason = ""
            bot_triggered = False  # Traccia se il bot viene triggerato

            # MICRO_GAIN reversal ha priorità per posizioni MICRO_GAIN
            if micro_gain_result.get("triggered"):
                should_close = True
                close_reason = micro_gain_result['reason']
                action_taken = "CLOSE_MICRO_GAIN_REVERSAL"
                action_reason = close_reason
            # Take profit ha priorità
            elif tp_triggered:
                should_close = True
                close_reason = tp_result['reason']
                action_taken = "CLOSE_TAKE_PROFIT"
                action_reason = close_reason
            elif result.get("triggered") and trading_mode != "MICRO_GAIN":
                # Trailing stop solo per NORMAL mode
                should_close = True
                close_reason = result['reason']
                if "STOP LOSS" in close_reason:
                    action_taken = "CLOSE_STOP_LOSS"
                else:
                    action_taken = "CLOSE_TRAILING_STOP"
                action_reason = close_reason

            if should_close:
                # CHIUDI POSIZIONE
                log(f"🛑 {symbol}: {close_reason}")
                log(f"   Chiusura posizione {direction.upper()}...")

                try:
                    close_result = bot.exchange.market_close(symbol)
                    log(f"   ✅ Posizione chiusa: {close_result}")

                    # Trade Journal: registra chiusura trade
                    if TRADE_JOURNAL_ENABLED:
                        try:
                            open_trade = tj.get_open_trade(symbol)
                            if open_trade:
                                # Mappa action_taken a close_reason del journal
                                journal_close_reason = {
                                    "CLOSE_TAKE_PROFIT": tj.CloseReason.TP_HIT,
                                    "CLOSE_STOP_LOSS": tj.CloseReason.SL_HIT,
                                    "CLOSE_TRAILING_STOP": tj.CloseReason.TRAILING_SL,
                                    "CLOSE_MICRO_GAIN_REVERSAL": tj.CloseReason.REVERSAL
                                }.get(action_taken, tj.CloseReason.MANUAL)

                                result_close = tj.close_trade(
                                    trade_uuid=open_trade['trade_uuid'],
                                    exit_price=mark_price,
                                    close_reason=journal_close_reason,
                                    close_score=micro_gain_result.get('quick_score')
                                )
                                log(f"   📒 Trade Journal: chiuso trade - Net P&L: ${result_close['net_pnl_usd']:.2f}")
                        except Exception as e:
                            log(f"   ⚠️ Trade Journal close error: {e}")

                    # Elimina tracking
                    db_utils.delete_position_tracking(symbol)

                    # Attiva cooldown per MICRO_GAIN auto-open
                    if MICRO_GAIN_AUTO_OPEN:
                        set_cooldown(symbol)

                    # Reset SL level per questo simbolo (both MICRO_GAIN and NORMAL keys)
                    if symbol in _current_sl_level:
                        del _current_sl_level[symbol]
                    sl_key_normal = f"{symbol}_NORMAL"
                    if sl_key_normal in _current_sl_level:
                        del _current_sl_level[sl_key_normal]

                    # Cancella ordini TP/SL rimasti per questo simbolo
                    try:
                        open_orders = bot.info.open_orders(bot.account_address)
                        for order in open_orders:
                            if order.get("coin") == symbol:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                log(f"   🗑️ Cancellato ordine residuo OID={order.get('oid')}")
                    except Exception as e:
                        log(f"   ⚠️ Errore cancellazione ordini residui: {e}")

                    # Notifica Telegram
                    if SENTINEL_TELEGRAM_NOTIFY:
                        emoji = "💰" if action_taken == "CLOSE_TAKE_PROFIT" else "🛑"
                        try:
                            tg.send_telegram_message(
                                f"{emoji} <b>SENTINEL CLOSE</b>\n\n"
                                f"<b>Symbol:</b> {symbol}\n"
                                f"<b>Direction:</b> {direction.upper()}\n"
                                f"<b>Reason:</b> {close_reason}\n"
                                f"<b>Entry:</b> ${entry_price:.2f}\n"
                                f"<b>Exit:</b> ${mark_price:.2f}\n"
                                f"<b>PnL:</b> ${pnl:.2f} ({pnl_pct:+.2f}%)"
                            )
                        except Exception as e:
                            log(f"   ⚠️ Errore Telegram: {e}")

                    # === SMART SENTINEL: Wake AI Agent su chiusure ===
                    # Mappa action_taken -> reason per wake_ai_agent
                    wake_reason_map = {
                        "CLOSE_TAKE_PROFIT": "take_profit",
                        "CLOSE_STOP_LOSS": "stop_loss",
                        "CLOSE_TRAILING_STOP": "trailing_stop",
                        "CLOSE_MICRO_GAIN_REVERSAL": "reversal",
                    }

                    # Determina se svegliare l'AI
                    should_wake_ai = False
                    wake_reason = wake_reason_map.get(action_taken, "position_closed")

                    if action_taken == "CLOSE_TAKE_PROFIT" and TAKE_PROFIT_TRIGGER_BOT:
                        should_wake_ai = True
                    elif SENTINEL_WAKE_ON_ALL_CLOSES and action_taken in wake_reason_map:
                        should_wake_ai = True

                    if should_wake_ai:
                        log(f"   🚀 Wake AI Agent per {symbol} (reason: {wake_reason})...")
                        wake_result = wake_ai_agent(symbol, wake_reason)
                        if wake_result.get("success"):
                            bot_triggered = True
                            log(f"   ✅ AI Agent avviato (PID: {wake_result.get('pid')})")
                        else:
                            log(f"   ⚠️ Fallito wake AI: {wake_result.get('error')}")

                except Exception as e:
                    log(f"   ❌ Errore chiusura: {e}")
            else:
                # Log stato
                peak_info = ""
                if result.get("trailing_active"):
                    peak_info = f", peak_dist={profit_from_peak_pct:.2f}%"
                tp_info = f", P&L={pnl_pct:+.2f}%" if TAKE_PROFIT_ENABLED else ""
                mode_info = f" [MICRO_GAIN]" if trading_mode == "MICRO_GAIN" else ""
                quick_score_info = f", qscore={micro_gain_result.get('quick_score', 0):.1f}" if trading_mode == "MICRO_GAIN" else ""
                log(f"   {symbol}: {direction.upper()}{mode_info} price_chg={profit_pct:.2f}% trailing={trailing_status}{peak_info}{tp_info}{quick_score_info}")

            # Log nel database per dashboard
            try:
                db_utils.log_sentinel_check(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=mark_price,
                    peak_price=new_peak,
                    profit_pct=profit_pct,
                    profit_from_peak_pct=profit_from_peak_pct,
                    trailing_active=result.get("trailing_active", False),
                    action_taken=action_taken,
                    action_reason=action_reason,
                    bot_triggered=bot_triggered,
                )
            except Exception as e:
                log(f"   ⚠️ Errore log DB: {e}")

        # === VERIFICA ORDINI SL ===
        # Alla fine di ogni ciclo, verifica che tutti gli ordini SL siano corretti
        # Se mancano o sono di tipo sbagliato, tenta di correggerli automaticamente
        log("")
        verification_result = run_order_verification(bot, positions)

        # Se ci sono fallimenti, log aggiuntivo
        if verification_result["failed"] > 0:
            log(f"⚠️ ATTENZIONE: {verification_result['failed']} posizioni senza SL verificato!")

        # === SMART SENTINEL: VERIFICA SL PASSIVA PERIODICA ===
        run_passive_sl_verification(bot, positions)

        # === SMART SENTINEL: VOLATILITY MONITORING ===
        if SENTINEL_VOLATILITY_CHECK:
            log("\n⚡ Controllo volatilità...")
            for pos in positions:
                symbol = pos.get("symbol", "")
                mark_price = float(pos.get("mark_price", 0))

                # Aggiungi prezzo alla history
                _volatility_monitor.add_price(symbol, mark_price)

                # Controlla volatilità
                vol_result = _volatility_monitor.check_volatility(symbol)

                if vol_result.get("triggered"):
                    log(f"   ⚡ {symbol}: VOLATILITY SPIKE! {vol_result['reason']}")

                    # Notifica Telegram
                    if SENTINEL_TELEGRAM_NOTIFY:
                        try:
                            tg.send_telegram_message(
                                f"⚡ <b>VOLATILITY WARNING</b>\n\n"
                                f"<b>Symbol:</b> {symbol}\n"
                                f"<b>Volatility:</b> {vol_result['volatility_pct']:.2f}%\n"
                                f"<b>Window:</b> {SENTINEL_VOLATILITY_WINDOW_SEC}s\n"
                                f"<b>Range:</b> ${vol_result['min_price']:.2f} - ${vol_result['max_price']:.2f}"
                            )
                        except Exception:
                            pass

                    # Wake AI Agent per rivalutare
                    wake_ai_agent(symbol, "volatility_spike")

    except Exception as e:
        log(f"❌ Errore sentinel: {e}")
        import traceback
        traceback.print_exc()


def run_loop(interval: int = None):
    """Esegue il sentinel in loop continuo."""

    interval = interval or SENTINEL_INTERVAL

    log(f"🔄 Sentinel avviato in loop (intervallo: {interval}s)")
    log(f"   Trailing legacy: {TRAILING_STOP_PERCENT}%, Activation: {TRAILING_STOP_ACTIVATION_PERCENT}%, Stop Loss: {INITIAL_STOP_LOSS_PERCENT}%")
    if NORMAL_TRAILING_ENABLED:
        log(f"   📊 NORMAL Trailing: enabled")
        log(f"      SL iniziale: -{NORMAL_STOP_LOSS_PERCENT}%")
        log(f"      Trailing: attivazione={NORMAL_TRAILING_ACTIVATION}%, gap={NORMAL_TRAILING_GAP}%")
    if MICRO_GAIN_ENABLED:
        log(f"   🎯 MICRO_GAIN: enabled, reversal_score: {MICRO_GAIN_REVERSAL_SCORE}")
    if MICRO_GAIN_AUTO_OPEN:
        log(f"   🚀 MICRO_GAIN AUTO-OPEN: enabled")
        log(f"      TP: +{MICRO_GAIN_TARGET_PERCENT}%, SL iniziale: -{MICRO_GAIN_STOP_LOSS_PERCENT}%")
        log(f"      Trailing: attivazione={MICRO_GAIN_TRAILING_ACTIVATION}%, gap={MICRO_GAIN_TRAILING_GAP}%")
        log(f"      Cooldown: {MICRO_GAIN_COOLDOWN_SECONDS}s, Max positions: {MICRO_GAIN_MAX_POSITIONS}")
        log(f"      Score smoothing: {SCORE_SMOOTHING_SAMPLES} samples, Leverage: {MICRO_GAIN_LEVERAGE}x")
        log(f"      Score range: {SCORE_THRESHOLD_HOLD} - {SCORE_THRESHOLD_OPEN}")
    if MICRO_PAY_ENABLED:
        log(f"   💵 MICRO_PAY: enabled")
        log(f"      TP: +{MICRO_PAY_TARGET_PERCENT}%, SL: -{MICRO_PAY_STOP_LOSS_PERCENT}%")
        log(f"      Leverage: {MICRO_PAY_LEVERAGE}x, Portion: {MICRO_PAY_PORTION*100}%")
        log(f"      Cooldown: {MICRO_PAY_COOLDOWN_SECONDS}s, Trailing: {MICRO_PAY_TRAILING_MODE}")
        log(f"      Score range: {MICRO_PAY_THRESHOLD} - {SCORE_THRESHOLD_HOLD}")
    else:
        log(f"   💵 MICRO_PAY: disabled (HOLD extends to score {SCORE_THRESHOLD_HOLD})")
    if TAKE_PROFIT_ENABLED:
        log(f"   Take Profit: {TAKE_PROFIT_PERCENT}% P&L")

    # === SMART SENTINEL CONFIGURATION ===
    log(f"\n🧠 SMART SENTINEL:")
    log(f"   Wake on all closes: {'ENABLED' if SENTINEL_WAKE_ON_ALL_CLOSES else 'DISABLED'}")
    log(f"   Volatility check: {'ENABLED' if SENTINEL_VOLATILITY_CHECK else 'DISABLED'}")
    if SENTINEL_VOLATILITY_CHECK:
        log(f"      Threshold: {SENTINEL_VOLATILITY_THRESHOLD_PCT}%, Window: {SENTINEL_VOLATILITY_WINDOW_SEC}s")
        log(f"      Cooldown: {SENTINEL_VOLATILITY_COOLDOWN_SEC}s")
    log(f"   SL Verification: {'ENABLED' if SENTINEL_SL_VERIFICATION else 'DISABLED'}")
    if SENTINEL_SL_VERIFICATION:
        log(f"      Interval: {SENTINEL_SL_VERIFICATION_INTERVAL}s")

    try:
        while True:
            run_sentinel_check()
            log(f"💤 Prossimo check tra {interval}s...")
            time.sleep(interval)
    except KeyboardInterrupt:
        log("Sentinel interrotto (Ctrl+C)")


def main():
    parser = argparse.ArgumentParser(description="Sentinel - Monitoraggio trailing stop")
    parser.add_argument("--loop", action="store_true", help="Esegui in loop continuo")
    parser.add_argument("--interval", type=int, default=None, help="Intervallo in secondi (default: da .env)")
    args = parser.parse_args()

    print("=" * 50)
    print("🛡️  SENTINEL - Trailing Stop Monitor")
    print("=" * 50)

    if args.loop:
        run_loop(args.interval)
    else:
        run_sentinel_check()


if __name__ == "__main__":
    main()
