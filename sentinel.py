#!/usr/bin/env python3
"""
Sentinel - Monitoraggio continuo trailing stop e stop loss.

ARCHITETTURA FAST/SLOW:
- FAST (2-5s): Price checks, SL updates, TP checks, trailing stop
- SLOW (30-60s): Score calculations, AI validation, position opening
- BOTH: Legacy mode, runs everything together (default)

Script leggero che gira frequentemente (ogni 1-2 minuti) per:
1. Controllare i prezzi correnti delle posizioni aperte
2. Aggiornare il peak_price nel database
3. Chiudere posizioni se trailing stop o stop loss viene triggerato

Uso:
    python sentinel.py                      # Singolo check (mode=both)
    python sentinel.py --loop               # Loop continuo (mode=both)
    python sentinel.py --mode fast --loop   # Solo FAST in loop (2-5s)
    python sentinel.py --mode slow --loop   # Solo SLOW in loop (30-60s)
    python sentinel.py --interval 60        # Loop con intervallo personalizzato
"""

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime, timedelta
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

# Risk Config - ENABLED_SYMBOLS e MAX_TRADES_PER_DAY
try:
    import risk_config as rc
    RISK_CONFIG_ENABLED = True
    ENABLED_SYMBOLS = rc.ENABLED_SYMBOLS
    MAX_TRADES_PER_DAY = rc.DAILY_LIMITS.MAX_TRADES_PER_DAY
    print(f"[SENTINEL] ✅ risk_config: Symbols={ENABLED_SYMBOLS}, MaxTrades={MAX_TRADES_PER_DAY}")
except ImportError:
    RISK_CONFIG_ENABLED = False
    # Strip whitespace da ogni simbolo
    ENABLED_SYMBOLS = [s.strip() for s in os.getenv('ENABLED_SYMBOLS', 'BTC,ETH,SOL').split(',')]
    MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '30'))
    print(f"[SENTINEL] ⚠️ risk_config non trovato, uso env: Symbols={ENABLED_SYMBOLS}")

# Smart Exit Optimizer - Import opzionale
try:
    import smart_exit
    SMART_EXIT_AVAILABLE = True
    print(f"[SENTINEL] ✅ smart_exit: Enabled={smart_exit.SMART_EXIT_ENABLED}, AI_HOLD_CHECK={smart_exit.AI_HOLD_CHECK_ENABLED}")
except ImportError:
    SMART_EXIT_AVAILABLE = False
    smart_exit = None
    print("[SENTINEL] ⚠️ smart_exit non disponibile")

# Configurazione
SENTINEL_ENABLED = os.getenv('SENTINEL_ENABLED', 'true').lower() == 'true'
SENTINEL_INTERVAL = int(os.getenv('SENTINEL_INTERVAL_SECONDS', '60'))
SENTINEL_TELEGRAM_NOTIFY = os.getenv('SENTINEL_TELEGRAM_NOTIFY', 'true').lower() == 'true'

# FAST/SLOW Mode Configuration
SENTINEL_FAST_INTERVAL = int(os.getenv('SENTINEL_FAST_INTERVAL', '3'))  # 3 seconds for price checks
SENTINEL_SLOW_INTERVAL = int(os.getenv('SENTINEL_SLOW_INTERVAL', '30'))  # 30 seconds for score/AI

# Sentinel Lock for FAST/SLOW coordination
try:
    from sentinel_lock import SentinelLock, SentinelState, init_sentinel_tables, is_symbol_busy, signal_slow_active, is_slow_active
    SENTINEL_LOCK_ENABLED = True
    # Initialize tables on first import
    init_sentinel_tables()
    print("[SENTINEL] ✅ sentinel_lock initialized")
except ImportError:
    SENTINEL_LOCK_ENABLED = False
    SentinelLock = None
    SentinelState = None
    print("[SENTINEL] ⚠️ sentinel_lock not available, running in legacy mode")

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
POSITION_AGE_PROTECTION_SECONDS = int(os.getenv('POSITION_AGE_PROTECTION_SECONDS', '15'))  # Protezione SL per posizioni nuove
MICRO_GAIN_MAX_POSITIONS = int(os.getenv('MICRO_GAIN_MAX_POSITIONS', '3'))  # Max posizioni contemporanee
SCORE_THRESHOLD_HOLD = float(os.getenv('SCORE_THRESHOLD_HOLD', '10'))
SCORE_THRESHOLD_OPEN = float(os.getenv('SCORE_THRESHOLD_OPEN', '20'))

# AI_FREE_MODE: se true, AI decide liberamente (score come suggerimento)
AI_FREE_MODE = os.getenv('AI_FREE_MODE', 'false').lower() == 'true'

# DOUBLE_CHECK_AI: se true, aperture MICRO_GAIN passano attraverso AI per validazione
DOUBLE_CHECK_AI_ENABLED = os.getenv('DOUBLE_CHECK_AI_ENABLED', 'false').lower() == 'true'

# TRADING_STYLE: aggressive | moderate | conservative
# Controls how strict the DOUBLE_CHECK validation is
TRADING_STYLE = os.getenv('TRADING_STYLE', 'moderate').lower()

# MAX_LEVERAGE: Maximum leverage AI can choose (1x to MAX_LEVERAGE)
MAX_LEVERAGE = int(os.getenv('MAX_LEVERAGE', '10'))

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

# ===== LEVERAGE SCALING CONFIG =====
# Strategia che aumenta la leva quando la posizione è in profitto protetto
LEVERAGE_SCALING_ENABLED = os.getenv('LEVERAGE_SCALING_ENABLED', 'false').lower() == 'true'
LEVERAGE_SCALING_MIN_PROTECTED_PROFIT = float(os.getenv('LEVERAGE_SCALING_MIN_PROTECTED_PROFIT', '0.5'))  # SL deve proteggere almeno questo %
LEVERAGE_SCALING_STEP = int(os.getenv('LEVERAGE_SCALING_STEP', '2'))  # +2x ogni scaling
LEVERAGE_SCALING_MAX = int(os.getenv('LEVERAGE_SCALING_MAX', '15'))  # Leva massima
LEVERAGE_SCALING_COOLDOWN_CYCLES = int(os.getenv('LEVERAGE_SCALING_COOLDOWN_CYCLES', '2'))  # Cicli di attesa tra scaling

# ===== ATR DYNAMIC STEPS CONFIG =====
# Scala automaticamente gli step del trailing in base alla volatilità (ATR)
# Se enabled, gli step vengono moltiplicati per (ATR_current / ATR_BASE)
ATR_DYNAMIC_STEPS_ENABLED = os.getenv('ATR_DYNAMIC_STEPS_ENABLED', 'false').lower() == 'true'
ATR_BASE_PERCENT = float(os.getenv('ATR_BASE_PERCENT', '1.5'))  # ATR% per cui sono tarati gli step
ATR_STEP_MULTIPLIER_MIN = float(os.getenv('ATR_STEP_MULTIPLIER_MIN', '0.5'))  # Non scalare sotto 0.5x
ATR_STEP_MULTIPLIER_MAX = float(os.getenv('ATR_STEP_MULTIPLIER_MAX', '2.5'))  # Non scalare sopra 2.5x

# ===== BTC CORRELATION FILTER =====
# Blocca trade su ALT (ETH, SOL) se BTC va nella direzione opposta
BTC_CORRELATION_FILTER_ENABLED = os.getenv('BTC_CORRELATION_FILTER_ENABLED', 'false').lower() == 'true'
BTC_CORRELATION_MACD_THRESHOLD = float(os.getenv('BTC_CORRELATION_MACD_THRESHOLD', '0.15'))  # MACD threshold per determinare trend BTC

# ===== AUTO TAKE PROFIT CONFIG =====
# Piazza automaticamente un ordine LIMIT TP dopo X minuti dall'apertura
# Questo garantisce un profitto minimo e previene chiusure AI a 0%
AUTO_TP_ENABLED = os.getenv('AUTO_TP_ENABLED', 'false').lower() == 'true'
AUTO_TP_PERCENT = float(os.getenv('AUTO_TP_PERCENT', '0.4'))  # Target profit % P&L
AUTO_TP_DELAY_MINUTES = int(os.getenv('AUTO_TP_DELAY_MINUTES', '15'))  # Piazza TP dopo X minuti

# ===== PATTERN DETECTION CONFIG (Double Bottom / Double Top) =====
# Detects reversal patterns for better entry timing and exit protection
PATTERN_DETECTION_ENABLED = os.getenv('PATTERN_DETECTION_ENABLED', 'true').lower() == 'true'
PATTERN_DETECTION_TIMEFRAME = os.getenv('PATTERN_DETECTION_TIMEFRAME', '1h')  # 15m, 1h, 4h
PATTERN_LOOKBACK_CANDLES = int(os.getenv('PATTERN_LOOKBACK_CANDLES', '100'))
PATTERN_CACHE_SECONDS = int(os.getenv('PATTERN_CACHE_SECONDS', '300'))  # 5 min cache

# Pattern parameters
PATTERN_PRICE_TOLERANCE_PCT = float(os.getenv('PATTERN_PRICE_TOLERANCE_PCT', '2.0'))
PATTERN_MIN_DISTANCE_CANDLES = int(os.getenv('PATTERN_MIN_DISTANCE_CANDLES', '10'))
PATTERN_RSI_DIVERGENCE_MIN = float(os.getenv('PATTERN_RSI_DIVERGENCE_MIN', '5'))
PATTERN_MIN_CONFIDENCE = float(os.getenv('PATTERN_MIN_CONFIDENCE', '0.60'))

# Entry system: IMMEDIATE (enter now) or FAST_LOOP (wait for breakout)
PATTERN_ENTRY_SYSTEM = os.getenv('PATTERN_ENTRY_SYSTEM', 'FAST_LOOP').upper()
PATTERN_ENTRY_EXPIRY_MINUTES = int(os.getenv('PATTERN_ENTRY_EXPIRY_MINUTES', '120'))
PATTERN_ENTRY_CONFIRM_VOLUME = os.getenv('PATTERN_ENTRY_CONFIRM_VOLUME', 'true').lower() == 'true'
PATTERN_ENTRY_VOLUME_MULTIPLIER = float(os.getenv('PATTERN_ENTRY_VOLUME_MULTIPLIER', '1.5'))

# Exit system: action on contrary pattern
# Options: CLOSE, ACCELERATE, REDUCE_50, ALERT_ONLY
PATTERN_CONTRA_ACTION = os.getenv('PATTERN_CONTRA_ACTION', 'ACCELERATE').upper()
PATTERN_CONTRA_MIN_CONFIDENCE = float(os.getenv('PATTERN_CONTRA_MIN_CONFIDENCE', '0.70'))

# Stop Loss from pattern
PATTERN_SL_USE_ATR = os.getenv('PATTERN_SL_USE_ATR', 'true').lower() == 'true'
PATTERN_SL_ATR_MULTIPLIER = float(os.getenv('PATTERN_SL_ATR_MULTIPLIER', '1.5'))

# Tracking interno per cooldown leverage scaling (symbol -> cicli rimanenti)
_leverage_scaling_cooldown = {}

# Tracking interno per AUTO_TP (symbol -> order_id se già piazzato)
_auto_tp_orders = {}

# Pattern cache (symbol -> {'last_fetch': datetime, 'double_bottom': {}, 'double_top': {}})
_pattern_cache = {}

# Pending entries for FAST_LOOP system (symbol -> entry_data)
_pending_entries = {}

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

# ===== ATR DYNAMIC FUNCTIONS =====
# Cache for ATR values (symbol -> (atr_percent, timestamp))
_atr_cache = {}
_atr_cache_ttl = 60  # Cache TTL in seconds


def get_atr_percent(symbol: str) -> float:
    """
    Get current ATR as percentage of price for a symbol.
    Uses 14-period ATR on 15-minute candles.
    Returns ATR_BASE_PERCENT if unable to calculate.
    """
    import time
    from indicators import analyze_multiple_tickers

    # Check cache
    now = time.time()
    if symbol in _atr_cache:
        cached_atr, cached_time = _atr_cache[symbol]
        if now - cached_time < _atr_cache_ttl:
            return cached_atr

    try:
        _, indicators_list = analyze_multiple_tickers([symbol])
        if indicators_list:
            data = indicators_list[0]
            price = data.get('current', {}).get('price', 0)
            atr_raw = data.get('longer_term_15m', {}).get('atr_14_current', 0)

            if price > 0 and atr_raw > 0:
                atr_pct = (atr_raw / price) * 100
                _atr_cache[symbol] = (atr_pct, now)
                return atr_pct
    except Exception as e:
        log(f"   ⚠️ Error getting ATR for {symbol}: {e}")

    return ATR_BASE_PERCENT  # Fallback


def get_dynamic_trailing_steps(symbol: str, base_steps: list) -> list:
    """
    Scale trailing steps based on current ATR volatility.

    If ATR_DYNAMIC_STEPS_ENABLED:
      multiplier = ATR_current / ATR_BASE
      Each step threshold and SL level gets multiplied.

    Args:
        symbol: Symbol to get ATR for
        base_steps: Original steps list [(pnl_threshold, sl_level), ...]

    Returns:
        Scaled steps list
    """
    if not ATR_DYNAMIC_STEPS_ENABLED:
        return base_steps

    atr_pct = get_atr_percent(symbol)
    multiplier = atr_pct / ATR_BASE_PERCENT

    # Clamp multiplier to min/max
    multiplier = max(ATR_STEP_MULTIPLIER_MIN, min(multiplier, ATR_STEP_MULTIPLIER_MAX))

    # Scale steps
    dynamic_steps = []
    for pnl_threshold, sl_level in base_steps:
        dynamic_steps.append((
            round(pnl_threshold * multiplier, 2),
            round(sl_level * multiplier, 2)
        ))

    return dynamic_steps


def get_btc_trend() -> str:
    """
    Get BTC trend based on MACD.
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    from indicators import analyze_multiple_tickers

    try:
        _, indicators_list = analyze_multiple_tickers(['BTC'])
        if indicators_list:
            data = indicators_list[0]
            macd = data.get('current', {}).get('macd', 0) or 0

            if macd > BTC_CORRELATION_MACD_THRESHOLD:
                return 'bullish'
            elif macd < -BTC_CORRELATION_MACD_THRESHOLD:
                return 'bearish'
    except Exception as e:
        log(f"   ⚠️ Error getting BTC trend: {e}")

    return 'neutral'


# ===== PATTERN DETECTION FUNCTIONS =====

def get_patterns_for_symbol(symbol: str) -> tuple:
    """
    Get Double Bottom and Double Top patterns for a symbol.
    Uses cache to minimize API calls (patterns change slowly on 1h timeframe).

    Returns:
        Tuple of (double_bottom_result, double_top_result)
    """
    global _pattern_cache

    if not PATTERN_DETECTION_ENABLED:
        return None, None

    now = datetime.now()

    # Check cache
    if symbol in _pattern_cache:
        cache = _pattern_cache[symbol]
        cache_age = (now - cache['last_fetch']).total_seconds()
        if cache_age < PATTERN_CACHE_SECONDS:
            return cache.get('double_bottom'), cache.get('double_top')

    try:
        from indicators import CryptoTechnicalAnalysisHL

        analyzer = CryptoTechnicalAnalysisHL(testnet=TESTNET)

        # Fetch candles for pattern detection timeframe
        df = analyzer.fetch_ohlcv(symbol, PATTERN_DETECTION_TIMEFRAME, limit=PATTERN_LOOKBACK_CANDLES + 20)

        if len(df) < 30:
            log(f"   ⚠️ Not enough candles for pattern detection on {symbol}")
            return None, None

        # Detect patterns
        double_bottom = analyzer.detect_double_bottom(
            df,
            price_tolerance_pct=PATTERN_PRICE_TOLERANCE_PCT,
            min_distance_candles=PATTERN_MIN_DISTANCE_CANDLES,
            rsi_divergence_min=PATTERN_RSI_DIVERGENCE_MIN,
            lookback=PATTERN_LOOKBACK_CANDLES
        )

        double_top = analyzer.detect_double_top(
            df,
            price_tolerance_pct=PATTERN_PRICE_TOLERANCE_PCT,
            min_distance_candles=PATTERN_MIN_DISTANCE_CANDLES,
            rsi_divergence_min=PATTERN_RSI_DIVERGENCE_MIN,
            lookback=PATTERN_LOOKBACK_CANDLES
        )

        # Update cache
        _pattern_cache[symbol] = {
            'last_fetch': now,
            'double_bottom': double_bottom,
            'double_top': double_top
        }

        # Log if pattern detected
        if double_bottom and double_bottom.get('detected'):
            conf = double_bottom.get('confidence', 0) * 100
            log(f"   🔷 {symbol}: DOUBLE BOTTOM detected (confidence: {conf:.0f}%)")

        if double_top and double_top.get('detected'):
            conf = double_top.get('confidence', 0) * 100
            log(f"   🔶 {symbol}: DOUBLE TOP detected (confidence: {conf:.0f}%)")

        return double_bottom, double_top

    except Exception as e:
        log(f"   ⚠️ Error detecting patterns for {symbol}: {e}")
        return None, None


def create_pending_entry(
    symbol: str,
    direction: str,
    pattern_data: dict,
    trading_mode: str = "MICRO_GAIN"
) -> bool:
    """
    Create a pending entry that FAST loop will monitor.
    Saves to DATABASE for sharing between SLOW and FAST containers.

    Args:
        symbol: Trading symbol
        direction: LONG or SHORT
        pattern_data: Pattern detection result with neckline, suggested_sl, etc.
        trading_mode: MICRO_GAIN or MICRO_PAY

    Returns:
        True if pending entry created, False otherwise
    """
    import db_utils

    if not pattern_data:
        return False

    # Get entry price (neckline for breakout)
    neckline = pattern_data.get('neckline')
    if not neckline or neckline <= 0:
        log(f"   ⚠️ Cannot create pending entry for {symbol}: invalid neckline ({neckline})")
        return False

    # Get invalidation price (below first low for Double Bottom, above first high for Double Top)
    if direction == "LONG":
        first_low = pattern_data.get('first_low', {})
        invalidation_price = first_low.get('price', 0) * 0.99  # 1% below first low
    else:
        first_high = pattern_data.get('first_high', {})
        invalidation_price = first_high.get('price', 0) * 1.01  # 1% above first high

    if invalidation_price <= 0:
        log(f"   ⚠️ Cannot create pending entry for {symbol}: invalid invalidation price")
        return False

    # BUGFIX: Check if current price is already past invalidation
    # If so, pattern is already broken - don't create pending entry
    current_price = pattern_data.get('current_price', 0)
    if current_price > 0:
        if direction == "LONG" and current_price < invalidation_price:
            log(f"   ⚠️ Cannot create pending entry for {symbol}: price ${current_price:.2f} already below invalidation ${invalidation_price:.2f}")
            return False
        elif direction == "SHORT" and current_price > invalidation_price:
            log(f"   ⚠️ Cannot create pending entry for {symbol}: price ${current_price:.2f} already above invalidation ${invalidation_price:.2f}")
            return False

    # Get suggested SL from pattern
    suggested_sl = pattern_data.get('suggested_sl') or 0
    confidence = pattern_data.get('confidence', 0.5)
    pattern_name = pattern_data.get('pattern', 'UNKNOWN')

    # Calculate expiry
    expires_at = datetime.now() + timedelta(minutes=PATTERN_ENTRY_EXPIRY_MINUTES)

    # Save to database (shared between containers)
    success = db_utils.save_pending_entry(
        symbol=symbol,
        direction=direction,
        entry_price=neckline,
        invalidation_price=invalidation_price,
        stop_loss=suggested_sl,
        expires_at=expires_at.isoformat(),
        trading_mode=trading_mode,
        pattern=pattern_name,
        confidence=confidence
    )

    if success:
        log(f"   ⏳ PENDING ENTRY created for {symbol} {direction}")
        log(f"      Entry: ${neckline:.6f} (neckline breakout)")
        log(f"      Invalidation: ${invalidation_price:.6f}")
        log(f"      Stop Loss: ${suggested_sl:.6f}" if suggested_sl else "      Stop Loss: default")
        log(f"      Expires: {expires_at.strftime('%H:%M:%S')}")
    else:
        log(f"   ⚠️ Failed to save pending entry for {symbol} to database")

    return success


def remove_pending_entry(symbol: str, reason: str, apply_cooldown: bool = False):
    """Remove a pending entry from database and log the reason.

    Args:
        symbol: Symbol to remove
        reason: Reason for removal (logged)
        apply_cooldown: If True, apply cooldown to prevent immediate re-entry
    """
    import db_utils

    if db_utils.delete_pending_entry(symbol):
        log(f"   🗑️ {symbol}: Pending entry removed - {reason}")

        # Apply cooldown if pattern was broken/invalidated to avoid immediate re-analysis
        if apply_cooldown:
            set_cooldown(symbol)
            log(f"   ⏳ Cooldown impostato per {symbol} (evita ri-analisi immediata)")


def check_pending_entries(exchange, info, existing_symbols: list = None) -> list:
    """
    Check pending entries and trigger if conditions met.
    Called from FAST loop. Reads from DATABASE (shared with SLOW).

    Args:
        exchange: HyperLiquid exchange instance
        info: HyperLiquid info instance
        existing_symbols: List of symbols with open positions

    Returns:
        List of triggered entries (symbol, direction, sl)
    """
    import db_utils
    from datetime import datetime as dt

    triggered = []
    now = dt.now()

    symbols_to_remove = []

    # Get all pending entries from database
    pending_entries = db_utils.get_all_pending_entries()

    for entry in pending_entries:
        symbol = entry['symbol']
        try:
            # 1. Check expiration
            expires_at = entry['expires_at']
            if isinstance(expires_at, str):
                expires_at = dt.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))

            # Remove timezone info for comparison (make naive)
            if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
                expires_at = expires_at.replace(tzinfo=None)

            time_remaining = expires_at - now
            minutes_remaining = time_remaining.total_seconds() / 60

            if now > expires_at:
                symbols_to_remove.append((symbol, "⏰ EXPIRED"))
                continue

            # 2. Get current price
            try:
                current_price = float(info.all_mids()[symbol])
            except Exception as e:
                log(f"   ⚠️ {symbol}: Impossibile ottenere prezzo corrente: {e}")
                continue

            # 3. Check invalidation (pattern broken)
            direction = entry['direction'].upper()
            entry_price = entry['entry_price']
            invalidation_price = entry['invalidation_price']

            if direction == "LONG":
                if current_price < invalidation_price:
                    symbols_to_remove.append((symbol, f"❌ Pattern broken (price ${current_price:.2f} < invalidation ${invalidation_price:.2f})"))
                    continue
                # Calculate distance to entry
                distance_pct = ((entry_price - current_price) / current_price) * 100
                distance_sign = "↑" if distance_pct > 0 else "↓"
            else:  # SHORT
                if current_price > invalidation_price:
                    symbols_to_remove.append((symbol, f"❌ Pattern broken (price ${current_price:.2f} > invalidation ${invalidation_price:.2f})"))
                    continue
                # Calculate distance to entry
                distance_pct = ((current_price - entry_price) / current_price) * 100
                distance_sign = "↓" if distance_pct > 0 else "↑"

            # Log pending entry status
            log(f"   ⏳ {symbol} {direction} PENDING:")
            log(f"      💰 Prezzo attuale: ${current_price:.4f}")
            log(f"      🎯 Neckline (entry): ${entry_price:.4f} ({distance_sign}{abs(distance_pct):.2f}% di distanza)")
            log(f"      🛑 Invalidation: ${invalidation_price:.4f}")
            log(f"      ⏱️ Scade tra: {minutes_remaining:.0f} minuti")

            # 4. Check if already in position
            if existing_symbols and symbol in existing_symbols:
                symbols_to_remove.append((symbol, "📍 Already in position"))
                continue

            # 5. Check entry condition (breakout)
            entry_triggered = False

            if direction == "LONG":
                if current_price > entry_price:
                    entry_triggered = True
                    log(f"      ✅ BREAKOUT! Prezzo ${current_price:.4f} > Neckline ${entry_price:.4f}")
            else:  # SHORT
                if current_price < entry_price:
                    entry_triggered = True
                    log(f"      ✅ BREAKOUT! Prezzo ${current_price:.4f} < Neckline ${entry_price:.4f}")

            if entry_triggered:
                # Optional: Check volume confirmation
                if PATTERN_ENTRY_CONFIRM_VOLUME:
                    # For now, skip volume check - can be added later
                    pass

                log(f"   ✅ BREAKOUT for {symbol}! Price ${current_price:.6f} crossed ${entry_price:.6f}")
                triggered.append({
                    'symbol': symbol,
                    'direction': direction,
                    'stop_loss': entry['stop_loss'],
                    'trading_mode': entry['trading_mode'],
                    'confidence': entry['confidence'],
                    'pattern': entry['pattern']
                })
                symbols_to_remove.append((symbol, "✅ TRIGGERED"))
            else:
                if direction == "LONG":
                    log(f"      ⏸️ In attesa: prezzo deve salire sopra ${entry_price:.4f}")
                else:
                    log(f"      ⏸️ In attesa: prezzo deve scendere sotto ${entry_price:.4f}")

        except Exception as e:
            log(f"   ⚠️ Error checking pending entry {symbol}: {e}")

    # Remove processed entries from database
    for symbol, reason in symbols_to_remove:
        # Apply cooldown when pattern is broken to avoid immediate re-analysis
        should_cooldown = "Pattern broken" in reason or "EXPIRED" in reason
        remove_pending_entry(symbol, reason, apply_cooldown=should_cooldown)

    return triggered


def handle_contrary_pattern(
    symbol: str,
    position_direction: str,
    pattern_type: str,
    pattern_confidence: float,
    exchange,
    info
) -> bool:
    """
    Handle detection of a contrary pattern (e.g., Double Bottom while SHORT).

    Args:
        symbol: Trading symbol
        position_direction: Current position direction (LONG or SHORT)
        pattern_type: DOUBLE_BOTTOM or DOUBLE_TOP
        pattern_confidence: Pattern confidence (0-1)
        exchange: HyperLiquid exchange instance
        info: HyperLiquid info instance

    Returns:
        True if action was taken, False otherwise
    """
    # Check if pattern is contrary to position
    is_contrary = False
    if position_direction == "LONG" and pattern_type == "DOUBLE_TOP":
        is_contrary = True
    elif position_direction == "SHORT" and pattern_type == "DOUBLE_BOTTOM":
        is_contrary = True

    if not is_contrary:
        return False

    # Check minimum confidence
    if pattern_confidence < PATTERN_CONTRA_MIN_CONFIDENCE:
        log(f"   ⚠️ {symbol}: Contrary pattern detected but confidence too low ({pattern_confidence*100:.0f}% < {PATTERN_CONTRA_MIN_CONFIDENCE*100:.0f}%)")
        return False

    log(f"   ⚠️ {symbol}: CONTRARY PATTERN! {pattern_type} detected while {position_direction} (conf: {pattern_confidence*100:.0f}%)")

    # Take action based on configuration
    if PATTERN_CONTRA_ACTION == "ALERT_ONLY":
        log(f"   📢 {symbol}: Alert only mode - no action taken")
        return False

    elif PATTERN_CONTRA_ACTION == "ACCELERATE":
        # Trigger ACCELERATE to tighten stop loss
        log(f"   🔄 {symbol}: Triggering ACCELERATE to protect position")
        # ACCELERATE is handled by smart_exit, we just need to signal it
        # Return True to indicate action was signaled
        return True

    elif PATTERN_CONTRA_ACTION == "CLOSE":
        log(f"   🚪 {symbol}: Closing position due to contrary pattern")
        try:
            # Close using market order
            position_size = 0
            for pos in info.user_state(exchange.wallet.address).get("assetPositions", []):
                if pos.get("position", {}).get("coin") == symbol:
                    position_size = abs(float(pos.get("position", {}).get("szi", 0)))
                    break
            if position_size > 0:
                # Determine side (opposite of position direction)
                close_side = "B" if position_direction == "SHORT" else "A"
                exchange.market_close(symbol)
                log(f"   ✅ {symbol}: Position closed")
            return True
        except Exception as e:
            log(f"   ❌ {symbol}: Error closing position: {e}")
            return False

    elif PATTERN_CONTRA_ACTION == "REDUCE_50":
        log(f"   ➗ {symbol}: Reducing position by 50%")
        # This would require implementing partial close
        # For now, just log
        return False

    return False


# Tracking SL corrente per ogni simbolo (in-memory)
_current_sl_level = {}  # symbol -> current SL % level

# Cooldown tracking (in-memory)
_last_close_time = {}  # symbol -> timestamp

# Score smoothing (in-memory) - tiene traccia degli ultimi N scores
SCORE_SMOOTHING_SAMPLES = int(os.getenv('SCORE_SMOOTHING_SAMPLES', '3'))  # Media ultimi 3 scores
_score_history = {}  # symbol -> list of recent scores

# Score confirmation - richiede N cicli consecutivi sopra soglia prima di aprire
SCORE_CONFIRMATION_CYCLES = int(os.getenv('SCORE_CONFIRMATION_CYCLES', '3'))  # Cicli di conferma


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

def wake_ai_agent(symbol: str, reason: str, sentinel_score: float = None):
    """
    Sveglia l'AI agent per rivalutare un simbolo.

    Lancia main.py in background (fire and forget) con priorità alta.

    Args:
        symbol: Simbolo da analizzare (BTC, ETH, SOL)
        reason: Motivo del trigger (stop_loss, trailing_stop, volatility_spike, etc.)
        sentinel_score: Score calcolato dalla sentinel (passato all'AI per evitare ricalcolo)
    """
    import telegram_notifier as tg

    score_info = f", score={sentinel_score:.1f}" if sentinel_score is not None else ""
    log(f"🚀 Triggering AI agent per {symbol} (reason: {reason}{score_info})...")

    try:
        # Prepara il comando
        log_file = f"/tmp/ai_wake_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Costruisci comando con score opzionale
        cmd = [sys.executable, "main.py", "--ticker", symbol, "--reason", reason, "--priority", "high"]
        if sentinel_score is not None:
            cmd.extend(["--sentinel-score", str(sentinel_score)])

        with open(log_file, 'w') as f_out:
            process = subprocess.Popen(
                cmd,
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
                    "score_signal": "📊",
                }
                emoji = emoji_map.get(reason, "🤖")
                score_msg = f"\n<b>Score:</b> {sentinel_score:.1f}" if sentinel_score is not None else ""
                tg.send_telegram_message(
                    f"{emoji} <b>AI Wake Trigger</b>\n\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Reason:</b> {reason}{score_msg}\n"
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
# DOUBLE_CHECK AI: VALIDAZIONE SINCRONA IMMEDIATA
# ============================================================================

def _get_trading_style_prompt(direction: str, style: str = "moderate") -> str:
    """
    Returns the trading style specific instructions for the DOUBLE_CHECK prompt.

    Args:
        direction: "long" or "short"
        style: "aggressive", "moderate", "conservative", or "free"

    Returns:
        String with style-specific trading rules
    """

    if style == "free":
        # AI FREE MODE - No hard constraints, AI decides based on all data
        return f"""## TRADING STYLE: FREE (AI Full Discretion)

You have COMPLETE FREEDOM to analyze all indicators and make your own decision.
There are NO mandatory thresholds or blocking rules.

### INDICATOR REFERENCE (informational, not rules):
- **MACD**: Momentum direction and strength. Positive = bullish, Negative = bearish
- **RSI**: Momentum/exhaustion. 30-70 is normal, <30 oversold, >70 overbought
- **ADX**: Trend strength. <20 = ranging/choppy, 20-25 = emerging, >25 = strong trend
- **Bollinger Bands**: Price position relative to volatility bands
- **OBV**: Volume trend confirmation
- **EMA Alignment**: Trend structure (Golden Cross = bullish, Death Cross = bearish)

### YOUR TASK:
1. Analyze ALL indicators holistically
2. Consider the proposed direction ({direction.upper()})
3. Weigh pros and cons of entering now
4. Decide: Is this a good trade opportunity?

### CONSIDERATIONS:
- Low ADX (ranging market) = higher risk but NOT automatically blocked
- Strong MACD momentum can work even in ranging markets
- Look for confluence: multiple indicators agreeing
- Consider risk/reward: Is the potential gain worth the risk?

### YOUR DECISION:
- "open" = You believe this is a good trade based on your analysis
- "hold" = You see too much risk or conflicting signals

You are the expert. Trust your judgment based on the complete picture."""

    elif style == "aggressive":
        return f"""## TRADING STYLE: AGGRESSIVE (Momentum Chaser)

### ENTRY CRITERIA (you need ONLY ONE strong signal):
- **MACD alone is enough**: If |MACD| > 0.15, this is a GO signal
- **EMA is secondary**: You can enter even if price is slightly against EMA20, if MACD momentum is strong
- **RSI**: Ignore RSI warnings in the 20-80 range. Only pause if RSI < 15 or RSI > 85
- **ADX**: Informational only - low ADX is caution, not a block

### DECISION THRESHOLDS for {direction.upper()}:
{"- MACD < -0.15 = STRONG SHORT signal ✓" if direction == "short" else "- MACD > +0.15 = STRONG LONG signal ✓"}
{"- MACD < -0.25 = VERY STRONG, enter immediately" if direction == "short" else "- MACD > +0.25 = VERY STRONG, enter immediately"}
- RSI between 20-80 = IGNORE (neutral zone)
- ADX is informational - consider it but it doesn't block
- Whale activity: Nice to have confirmation, but not required

### YOUR BIAS:
Be aggressive. A strong MACD signal beats neutral secondary indicators.
When in doubt with strong momentum → OPEN"""

    elif style == "conservative":
        return f"""## TRADING STYLE: CONSERVATIVE (Sniper)

### ENTRY CRITERIA (prefer multiple signals aligned):
1. **MACD should be strong**: |MACD| > 0.25 preferred
2. **Price vs EMA20 confirmation**: {"Price below EMA20 supports SHORT" if direction == "short" else "Price above EMA20 supports LONG"}
3. **RSI not exhausted**: {"RSI > 30 preferred (avoid catching falling knife)" if direction == "short" else "RSI < 70 preferred (avoid buying top)"}
4. **ADX shows trend**: ADX > 25 adds confidence (but not mandatory blocker)
5. **Whale activity**: Look for confirmation, contradicting is a warning

### DECISION GUIDANCE for {direction.upper()}:
{"- MACD < -0.25 + Price < EMA20 = High confidence SHORT" if direction == "short" else "- MACD > +0.25 + Price > EMA20 = High confidence LONG"}
- Multiple indicators aligned = OPEN with confidence
- Mixed signals = prefer HOLD

### YOUR BIAS:
Be patient. Prefer high-quality setups with multiple confirmations.
When in doubt → HOLD. Missing a trade is better than losing money."""

    else:  # moderate (default)
        return f"""## TRADING STYLE: MODERATE (Balanced)

### ENTRY GUIDANCE (look for confluence):

**BULLISH signals for LONG:**
- MACD > 0 (positive momentum)
- Price > EMA20 (uptrend)
- OBV RISING (volume confirms)
- Golden Cross (EMA20 > EMA50)

**BEARISH signals for SHORT:**
- MACD < 0 (negative momentum)
- Price < EMA20 (downtrend)
- OBV FALLING (volume confirms)
- Death Cross (EMA20 < EMA50)

**CONTEXT indicators (informational):**
- ADX: Higher = stronger trend (more confidence), Lower = ranging (more caution, but not blocking)
- RSI: Extreme values (<25 or >75) suggest caution
- Bollinger: Breakouts can indicate continuation

### DECISION GUIDANCE for {direction.upper()}:
- Strong MACD + EMA confirmation = High confidence → OPEN
- Strong MACD alone = Medium confidence → Consider OPEN
- Weak/mixed signals = Low confidence → HOLD

### YOUR BIAS:
Balance risk and opportunity. Look for 2-3 confirming indicators.
ADX is context, NOT a blocker - use your judgment.
When signals are clearly mixed → prefer HOLD."""


def validate_double_check_ai(symbol: str, direction: str, score: float, trading_mode: str = "MICRO_GAIN") -> dict:
    """
    Validates a trading signal using AI before opening a position.
    Uses TRADING_STYLE (aggressive/moderate/conservative) to determine strictness.

    Args:
        symbol: Symbol to validate (BTC, ETH, SOL)
        direction: Proposed direction ("long" or "short")
        score: Score that generated the signal
        trading_mode: Trading mode (MICRO_GAIN, MICRO_PAY)

    Returns:
        dict with:
        - approved: True if AI confirms, False if rejected
        - operation: "open" or "hold"
        - reason: AI decision rationale
    """
    log(f"   🔍 DOUBLE_CHECK [{TRADING_STYLE.upper()}]: Validating {symbol} {direction.upper()}...")

    try:
        from trading_agent import previsione_trading_agent
        from indicators import analyze_multiple_tickers
        from sentiment import get_sentiment
        from whalealert import get_whale_alerts_json

        # === 1. GATHER CONTEXT ===
        score_history = _get_recent_scores(symbol, limit=5)
        score_trend = _analyze_score_trend(score_history)

        try:
            _, indicators_list = analyze_multiple_tickers([symbol])
            indicators_data = indicators_list[0] if indicators_list else {}
        except:
            indicators_data = {}

        try:
            _, sentiment_data = get_sentiment()
        except:
            sentiment_data = {}

        try:
            whale_data = get_whale_alerts_json()
            whale_sentiment = whale_data.get("summary", {}).get("net_sentiment", "neutral")
            whale_symbol = whale_data.get("by_symbol", {}).get(symbol.upper(), {})
        except:
            whale_sentiment = "unavailable"
            whale_symbol = {}

        # === 1.5 PATTERN DETECTION (cached) with WINNER-TAKES-ALL ===
        double_bottom, double_top = get_patterns_for_symbol(symbol)
        pattern_info = ""
        pattern_data_for_entry = None  # Will be used for pending entry creation

        # Get detection flags and confidence
        bottom_detected = double_bottom and double_bottom.get('detected', False)
        top_detected = double_top and double_top.get('detected', False)
        bottom_conf = double_bottom.get('confidence', 0) if bottom_detected else 0
        top_conf = double_top.get('confidence', 0) if top_detected else 0

        # Winner-takes-all logic: only include pattern if it's the clear winner
        MIN_PATTERN_CONF_DIFF = 0.15  # 15% minimum difference
        use_bottom = False
        use_top = False

        if bottom_detected and top_detected:
            # Both detected: only use winner if confidence diff >= 15%
            conf_diff = abs(bottom_conf - top_conf)
            if conf_diff >= MIN_PATTERN_CONF_DIFF:
                if bottom_conf > top_conf:
                    use_bottom = True
                    log(f"      📊 Pattern: Double Bottom WINS ({bottom_conf*100:.0f}% vs {top_conf*100:.0f}%)")
                else:
                    use_top = True
                    log(f"      📊 Pattern: Double Top WINS ({top_conf*100:.0f}% vs {bottom_conf*100:.0f}%)")
            else:
                # Too close - don't include any pattern in AI prompt
                log(f"      📊 Patterns too close ({bottom_conf*100:.0f}% vs {top_conf*100:.0f}%), ignoring both in AI prompt")
        elif bottom_detected:
            use_bottom = True
        elif top_detected:
            use_top = True

        # Build pattern info only for the winner
        if use_bottom:
            conf = bottom_conf * 100
            first_low = double_bottom.get('first_low', {})
            second_low = double_bottom.get('second_low', {})
            neckline = double_bottom.get('neckline', 0)
            rsi_div = double_bottom.get('rsi_divergence', False)
            suggested_sl = double_bottom.get('suggested_sl', 0)

            pattern_info = f"""
### PATTERN DETECTED: DOUBLE BOTTOM (W) 🔷
- **Confidence**: {conf:.0f}%
- **First Low**: ${first_low.get('price', 0):,.2f} (RSI: {first_low.get('rsi', 0):.1f})
- **Second Low**: ${second_low.get('price', 0):,.2f} (RSI: {second_low.get('rsi', 0):.1f})
- **RSI Divergence**: {'BULLISH ✓ (RSI higher at second low)' if rsi_div else 'No divergence'}
- **Neckline (breakout level)**: ${neckline:,.2f}
- **Suggested Stop Loss**: ${suggested_sl:,.2f} (ATR-based)
- **Interpretation**: Double Bottom is a BULLISH reversal pattern. {"✓ CONFIRMS proposed LONG" if direction.lower() == "long" else "⚠ CONTRADICTS proposed SHORT"}
"""
            if direction.lower() == "long":
                pattern_data_for_entry = double_bottom

        elif use_top:
            conf = top_conf * 100
            first_high = double_top.get('first_high', {})
            second_high = double_top.get('second_high', {})
            neckline = double_top.get('neckline', 0)
            rsi_div = double_top.get('rsi_divergence', False)
            suggested_sl = double_top.get('suggested_sl', 0)

            pattern_info = f"""
### PATTERN DETECTED: DOUBLE TOP (M) 🔶
- **Confidence**: {conf:.0f}%
- **First High**: ${first_high.get('price', 0):,.2f} (RSI: {first_high.get('rsi', 0):.1f})
- **Second High**: ${second_high.get('price', 0):,.2f} (RSI: {second_high.get('rsi', 0):.1f})
- **RSI Divergence**: {'BEARISH ✓ (RSI lower at second high)' if rsi_div else 'No divergence'}
- **Neckline (breakdown level)**: ${neckline:,.2f}
- **Suggested Stop Loss**: ${suggested_sl:,.2f} (ATR-based)
- **Interpretation**: Double Top is a BEARISH reversal pattern. {"✓ CONFIRMS proposed SHORT" if direction.lower() == "short" else "⚠ CONTRADICTS proposed LONG"}
"""
            if direction.lower() == "short":
                pattern_data_for_entry = double_top

        # === 2. EXTRACT INDICATOR VALUES FOR PROMPT ===
        # Data is nested under 'current' key
        current_data = indicators_data.get('current', {})
        macd_val = current_data.get('macd', 0) or 0
        rsi_val = current_data.get('rsi_7', 50) or 50  # Use rsi_7 not rsi
        ema20_val = current_data.get('ema20', 0) or 0  # Key is 'ema20' not 'ema_20'
        price_val = current_data.get('price', 0) or 0
        adx_val = current_data.get('adx', 0) or 0  # ADX for trend strength
        price_vs_ema = "ABOVE" if price_val > ema20_val else "BELOW" if price_val < ema20_val else "AT"

        # ADX interpretation
        if adx_val < 20:
            adx_interpretation = "WEAK/RANGING ⚠️"
        elif adx_val < 25:
            adx_interpretation = "EMERGING TREND"
        elif adx_val < 50:
            adx_interpretation = "STRONG TREND ✓"
        else:
            adx_interpretation = "VERY STRONG TREND ✓✓"

        # === NEW V2 INDICATORS ===
        # Bollinger Bands
        bollinger_data = indicators_data.get('bollinger', {})
        bb_position = bollinger_data.get('position', 'UNKNOWN')
        bb_bandwidth = bollinger_data.get('bandwidth', 0) or 0
        bb_squeeze = bollinger_data.get('squeeze', False)
        bb_percent_b = bollinger_data.get('percent_b', 0.5) or 0.5

        # OBV Trend
        obv_data = indicators_data.get('obv', {})
        obv_trend = obv_data.get('trend', 'UNKNOWN')

        # MACD Histogram Trend
        macd_analysis = indicators_data.get('macd_analysis', {})
        macd_hist_trend = macd_analysis.get('histogram_trend', 'UNKNOWN')

        # EMA Alignment
        ema_alignment = indicators_data.get('ema_alignment', 'NEUTRAL')

        # Extract derivatives data (OI, Funding)
        derivatives_data = indicators_data.get('derivatives', {})
        oi_val = derivatives_data.get('open_interest_latest', 0) or 0
        funding_val = derivatives_data.get('funding_rate', 0) or 0
        funding_pct = funding_val * 100  # Convert to percentage

        # Log indicator values for visibility
        log(f"      📊 MACD: {macd_val:.4f} | RSI: {rsi_val:.1f} | ADX: {adx_val:.1f} ({adx_interpretation})")
        log(f"      💰 Price: ${price_val:,.2f} {price_vs_ema} EMA20 | Funding: {funding_pct:.4f}%")
        log(f"      📊 BB: {bb_position} | OBV: {obv_trend} | MACD Hist: {macd_hist_trend} | EMA: {ema_alignment}")

        # === 2.5 BTC CORRELATION FILTER ===
        # Block trades on ALT coins if BTC is trending opposite direction
        btc_trend_info = ""
        if BTC_CORRELATION_FILTER_ENABLED and symbol.upper() != "BTC":
            btc_trend = get_btc_trend()
            btc_trend_info = f"\n- **BTC Trend**: {btc_trend.upper()}"

            # Check for conflict
            if btc_trend == "bearish" and direction.lower() == "long":
                log(f"      🚫 BTC CORRELATION FILTER: BTC bearish, blocking LONG on {symbol}")
                return {
                    "approved": False,
                    "operation": "hold",
                    "reason": f"BTC bearish (MACD < -{BTC_CORRELATION_MACD_THRESHOLD}), avoid LONG on {symbol}",
                    "confidence": "n/a",
                    "direction": direction,
                    "direction_overridden": False,
                    "leverage": MICRO_GAIN_LEVERAGE
                }
            elif btc_trend == "bullish" and direction.lower() == "short":
                log(f"      🚫 BTC CORRELATION FILTER: BTC bullish, blocking SHORT on {symbol}")
                return {
                    "approved": False,
                    "operation": "hold",
                    "reason": f"BTC bullish (MACD > +{BTC_CORRELATION_MACD_THRESHOLD}), avoid SHORT on {symbol}",
                    "confidence": "n/a",
                    "direction": direction,
                    "direction_overridden": False,
                    "leverage": MICRO_GAIN_LEVERAGE
                }
            else:
                log(f"      ✅ BTC Correlation: {btc_trend.upper()} - OK for {direction.upper()}")

        # === 3. BUILD FOCUSED PROMPT ===
        style_instructions = _get_trading_style_prompt(direction, TRADING_STYLE)

        prompt = f"""## DOUBLE_CHECK VALIDATION - TRADE CONFIRMATION

You are validating a proposed trade. Analyze the REAL DATA and decide if this trade makes sense.

### PROPOSED TRADE:
- Symbol: {symbol}
- Direction: {direction.upper()}
- Sentinel Score: {score:.1f} (informational only)
- Mode: {trading_mode}

### CURRENT INDICATOR VALUES:
- **MACD**: {macd_val:.4f} {"(BEARISH)" if macd_val < 0 else "(BULLISH)" if macd_val > 0 else "(NEUTRAL)"}
- **MACD Histogram**: {macd_hist_trend} {"(momentum growing)" if macd_hist_trend == "EXPANDING" else "(momentum fading)" if macd_hist_trend == "CONTRACTING" else ""}
- **RSI**: {rsi_val:.1f} {"(OVERSOLD)" if rsi_val < 30 else "(OVERBOUGHT)" if rsi_val > 70 else "(BULLISH zone 55-70)" if 55 <= rsi_val <= 70 else "(BEARISH zone 30-45)" if 30 <= rsi_val <= 45 else "(NEUTRAL)"}
- **ADX**: {adx_val:.1f} ({adx_interpretation})
- **Price**: ${price_val:,.2f}
- **EMA20**: ${ema20_val:,.2f}
- **Price vs EMA20**: {price_vs_ema} {"✓ confirms SHORT" if price_vs_ema == "BELOW" and direction == "short" else "✓ confirms LONG" if price_vs_ema == "ABOVE" and direction == "long" else "⚠ does not confirm"}
- **EMA Alignment**: {ema_alignment} {"✓ bullish structure" if ema_alignment == "GOLDEN_CROSS" else "✓ bearish structure" if ema_alignment == "DEATH_CROSS" else ""}

### BOLLINGER BANDS & VOLUME:
- **BB Position**: {bb_position} (%B={bb_percent_b:.2f}) {"✓ bullish breakout" if bb_position == "ABOVE_UPPER" else "⚠ bearish breakdown" if bb_position == "BELOW_LOWER" else "mild bullish" if bb_position == "UPPER_HALF" else "mild bearish" if bb_position == "LOWER_HALF" else ""}
- **BB Bandwidth**: {bb_bandwidth:.2f}% {"⚠ SQUEEZE (low volatility → breakout expected)" if bb_squeeze else "(normal volatility)"}
- **OBV Trend**: {obv_trend} {"✓ volume confirms uptrend" if obv_trend == "RISING" else "⚠ volume confirms downtrend" if obv_trend == "FALLING" else "(no volume confirmation)"}

### MARKET STRUCTURE:
- **Open Interest**: ${oi_val:,.0f}
- **Funding Rate**: {funding_pct:.4f}% {"(shorts paying → squeeze risk)" if funding_val < 0 else "(longs paying)" if funding_val > 0 else "(neutral)"}

### SCORE HISTORY (last 5):
{_format_score_history(score_history)}
- Trend: {score_trend}

### WHALE ACTIVITY:
- Market: {whale_sentiment}
- {symbol}: {whale_symbol.get('net_sentiment', 'no data')} ({whale_symbol.get('count', 0)} movements)

### SENTIMENT:
- Fear & Greed: {sentiment_data.get('value', 'N/A')} ({sentiment_data.get('sentiment', 'N/A')})
{pattern_info}
{style_instructions}

### YOUR DECISION:
Based on the trading style rules above, decide:
- "open" = Indicators support the trade according to the style rules
- "hold" = Signals don't meet the style requirements

**DIRECTION OVERRIDE**: If indicators STRONGLY suggest the OPPOSITE direction, you can change it.
Example: Sentinel proposes LONG but MACD is strongly negative → You can respond with direction: "short"
Only override if you have HIGH CONFIDENCE in the opposite direction.

**LEVERAGE SELECTION** (1x to {MAX_LEVERAGE}x):
Choose leverage based on your confidence and signal strength:
- HIGH confidence + strong signals → higher leverage ({MAX_LEVERAGE}x or close)
- MEDIUM confidence → moderate leverage ({MAX_LEVERAGE // 2}x to {(MAX_LEVERAGE * 2) // 3}x)
- LOW confidence but still opening → minimal leverage (1x to 2x)
- If "hold" → leverage is ignored

Respond with JSON only:
{{"operation": "open|hold", "symbol": "{symbol}", "direction": "long|short", "leverage": 1-{MAX_LEVERAGE}, "reason": "Brief analysis (max 50 words)", "confidence": "high|medium|low"}}
"""

        log(f"      Calling AI...")
        ai_response = previsione_trading_agent(prompt, indicators=[indicators_data] if indicators_data else None, sentiment=sentiment_data)

        operation = ai_response.get("operation", "hold").lower()
        ai_reason = ai_response.get("reason", "No reason")[:80]
        approved = operation == "open"

        ai_direction = ai_response.get("direction", direction).lower()
        direction_overridden = ai_direction != direction.lower()

        # Parse leverage (default to MICRO_GAIN_LEVERAGE, clamp to 1-MAX_LEVERAGE)
        ai_leverage_raw = ai_response.get("leverage", MICRO_GAIN_LEVERAGE)
        try:
            ai_leverage = int(ai_leverage_raw)
        except (ValueError, TypeError):
            ai_leverage = MICRO_GAIN_LEVERAGE
        ai_leverage = max(1, min(ai_leverage, MAX_LEVERAGE))  # Clamp to valid range

        confidence = ai_response.get("confidence", "medium")

        if approved:
            if direction_overridden:
                log(f"      ✅ AI APPROVED with DIRECTION OVERRIDE: {direction.upper()} → {ai_direction.upper()}")
                log(f"         Leverage: {ai_leverage}x | Confidence: {confidence}")
                log(f"         Reason: {ai_reason}")
            else:
                log(f"      ✅ AI APPROVED: {ai_reason}")
                log(f"         Leverage: {ai_leverage}x | Confidence: {confidence}")
        else:
            log(f"      ❌ AI REJECTED: {ai_reason}")

        return {
            "approved": approved,
            "operation": operation,
            "reason": ai_reason,
            "confidence": confidence,
            "direction": ai_direction,
            "direction_overridden": direction_overridden,
            "leverage": ai_leverage
        }

    except Exception as e:
        log(f"      ⚠️ Validation error: {e}")
        return {"approved": False, "operation": "hold", "reason": f"Error: {str(e)}", "error": str(e), "leverage": MICRO_GAIN_LEVERAGE}


def _get_recent_scores(symbol: str, limit: int = 5) -> list:
    """Recupera ultimi N score dal database."""
    try:
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT net_score, created_at FROM score_history
                    WHERE symbol = %s ORDER BY created_at DESC LIMIT %s
                """, (symbol, limit))
                return [{"score": float(r[0]), "time": r[1]} for r in cur.fetchall()]
    except:
        return []


def _analyze_score_trend(score_history: list) -> str:
    """Analizza trend degli ultimi score."""
    if len(score_history) < 2:
        return "insufficient_data"
    scores = [s["score"] for s in score_history]
    changes = [scores[i] - scores[i+1] for i in range(len(scores)-1)]
    avg_change = sum(changes) / len(changes) if changes else 0
    all_positive = all(s > 0 for s in scores)
    all_negative = all(s < 0 for s in scores)
    trend = "strengthening" if avg_change > 2 else "weakening" if avg_change < -2 else "stable"
    if all_positive:
        return f"{trend}_bullish"
    elif all_negative:
        return f"{trend}_bearish"
    return f"{trend}_mixed"


def _format_score_history(score_history: list) -> str:
    """Formatta score history per prompt."""
    if not score_history:
        return "- No history"
    lines = []
    for s in score_history:
        time_str = s["time"].strftime("%H:%M") if hasattr(s["time"], "strftime") else str(s["time"])
        dir_str = "bull" if s["score"] > 0 else "bear" if s["score"] < 0 else "neutral"
        lines.append(f"  {time_str}: {s['score']:.1f} ({dir_str})")
    return "\n".join(lines)


def _format_quick_indicators(indicators: dict) -> str:
    """Formatta indicatori per prompt."""
    if not indicators:
        return "- No data"
    lines = []
    current = indicators.get("current", {})
    intraday = indicators.get("intraday", {})
    price, ema20 = current.get("price"), current.get("ema20")
    if price and ema20:
        vs_ema = ((price - ema20) / ema20) * 100
        lines.append(f"- Price: ${price:.2f} ({vs_ema:+.1f}% vs EMA20)")
    rsi = intraday.get("rsi_14", [])
    if rsi:
        zone = "OB" if rsi[-1] > 70 else "OS" if rsi[-1] < 30 else "N"
        lines.append(f"- RSI: {rsi[-1]:.0f} ({zone})")
    macd = intraday.get("macd", [])
    if macd:
        lines.append(f"- MACD: {macd[-1]:.4f}")
    return "\n".join(lines) if lines else "- Limited data"


def should_wake_ai_for_symbol(symbol: str, score: float, existing_positions: list) -> dict:
    """
    Decide se svegliare l'AI per un simbolo in base a AI_FREE_MODE e condizioni.

    LOGICA:
    - AI_FREE_MODE=true: NON svegliare per score (AI gira su schedule, sveglia solo su eventi)
    - AI_FREE_MODE=false:
        * Se NO posizione + score >= SCORE_THRESHOLD_OPEN (confermato) → Sveglia
        * Se posizione in direzione OPPOSTA allo score → Sveglia
        * Se posizione in STESSA direzione → NON svegliare
        * Se score sotto soglia → NON svegliare

    Args:
        symbol: Simbolo da verificare (BTC, ETH, SOL)
        score: Score attuale (positivo=bullish, negativo=bearish)
        existing_positions: Lista di posizioni aperte [{symbol, side}, ...]

    Returns:
        dict con:
        - should_wake: True/False
        - reason: Motivo della decisione
    """
    result = {
        "should_wake": False,
        "reason": ""
    }

    # AI_FREE_MODE: AI gira su schedule, non svegliare per score
    if AI_FREE_MODE:
        result["reason"] = "AI_FREE_MODE: AI runs on schedule, no proactive wake"
        return result

    # Trova posizione per questo simbolo
    position = None
    for pos in existing_positions:
        if pos.get("symbol") == symbol:
            position = pos
            break

    abs_score = abs(score)
    score_direction = "long" if score > 0 else "short"

    # CASO 1: Nessuna posizione aperta
    if position is None:
        # Verifica conferma cicli
        confirmation = check_score_confirmation(symbol, SCORE_THRESHOLD_OPEN)

        if not confirmation["confirmed"]:
            result["reason"] = f"No position, score not confirmed: {confirmation['reason']}"
            return result

        if abs_score >= SCORE_THRESHOLD_OPEN:
            result["should_wake"] = True
            result["reason"] = f"No position, score {score:.1f} >= {SCORE_THRESHOLD_OPEN} (confirmed)"
            return result
        else:
            result["reason"] = f"No position, score {score:.1f} < {SCORE_THRESHOLD_OPEN}"
            return result

    # CASO 2: Posizione aperta
    position_direction = position.get("side", "").lower()

    # Posizione in direzione OPPOSTA allo score
    if (position_direction == "long" and score < 0) or (position_direction == "short" and score > 0):
        # Verifica che lo score sia abbastanza forte per considerare reverse
        if abs_score >= SCORE_THRESHOLD_HOLD:
            result["should_wake"] = True
            result["reason"] = f"Position {position_direction}, score {score:.1f} suggests opposite → potential close/reverse"
            return result
        else:
            result["reason"] = f"Position {position_direction}, opposite score {score:.1f} too weak"
            return result

    # Posizione in STESSA direzione dello score
    result["reason"] = f"Position {position_direction} aligned with score {score:.1f} → no action needed"
    return result


def should_wake_ai_for_event(event_type: str) -> bool:
    """
    Decide se svegliare l'AI per un evento specifico.

    Sveglia sempre per:
    - Chiusure (SL, TP, trailing)
    - Volatility spike

    Args:
        event_type: Tipo di evento (stop_loss, take_profit, trailing_stop, volatility_spike, etc.)

    Returns:
        True se deve svegliare AI
    """
    # Eventi che svegliano sempre l'AI (indipendentemente da AI_FREE_MODE)
    wake_events = {
        "stop_loss",
        "trailing_stop",
        "take_profit",
        "volatility_spike",
        "reversal",
        "sl_mismatch"
    }

    return event_type in wake_events


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

            # === PROTEZIONE RACE CONDITION: Skip per posizioni appena aperte ===
            # Se la posizione è stata aperta da meno di 60 secondi, skip verifica passiva
            # Questo evita che la verifica passiva interferisca con il piazzamento SL iniziale
            created_at = tracking.get("created_at") or tracking.get("entry_time")
            if created_at:
                try:
                    from datetime import datetime as dt_passive
                    if isinstance(created_at, str):
                        created_dt = dt_passive.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                    else:
                        created_dt = created_at
                    if hasattr(created_dt, 'tzinfo') and created_dt.tzinfo is not None:
                        created_dt = created_dt.replace(tzinfo=None)
                    age_seconds = (dt_passive.now() - created_dt).total_seconds()
                    if age_seconds < POSITION_AGE_PROTECTION_SECONDS:
                        log(f"   ⏳ {symbol}: Posizione aperta da {age_seconds:.0f}s, skip verifica passiva (< {POSITION_AGE_PROTECTION_SECONDS}s)")
                        continue
                except Exception as e:
                    # CRITICO: Se c'è errore nel parsing data, skip per sicurezza (non modificare SL!)
                    log(f"   ⚠️ {symbol}: Errore calcolo età (passivo): {e} - SKIP per sicurezza")
                    continue
            else:
                # Se manca created_at, la posizione potrebbe essere in fase di apertura - SKIP
                log(f"   ⏳ {symbol}: created_at mancante, skip verifica passiva per sicurezza")
                continue

            trading_mode = tracking.get("trading_mode", "NORMAL")

            # IMPORTANTE: Parse leverage REALE dalla posizione (può cambiare con leverage scaling)
            leverage_raw = pos.get("leverage", 1)
            if isinstance(leverage_raw, str):
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                leverage = float(match.group(1)) if match else 1.0
            else:
                leverage = float(leverage_raw)

            # Determina SL atteso - USA current_sl_level se disponibile (trailing attivo)
            if trading_mode == "MICRO_GAIN":
                # Usa leva reale, fallback al default solo se 0
                if leverage <= 0:
                    leverage = MICRO_GAIN_LEVERAGE
                # Usa current_sl_level se disponibile (trailing potrebbe averlo modificato)
                sl_key = symbol
                current_sl_level = _current_sl_level.get(sl_key)
                if current_sl_level is not None:
                    sl_pct = current_sl_level
                else:
                    sl_pct = -MICRO_GAIN_STOP_LOSS_PERCENT
            elif trading_mode == "MICRO_PAY":
                # Usa leva reale, fallback al default solo se 0
                if leverage <= 0:
                    leverage = MICRO_PAY_LEVERAGE
                sl_pct = -MICRO_PAY_STOP_LOSS_PERCENT
            else:
                # Per NORMAL, leverage già parsato sopra
                # Usa current_sl_level se disponibile
                sl_key = f"{symbol}_NORMAL"
                current_sl_level = _current_sl_level.get(sl_key)
                if current_sl_level is not None:
                    sl_pct = current_sl_level
                else:
                    sl_pct = -NORMAL_STOP_LOSS_PERCENT

            # Calcola prezzo SL atteso basato su sl_pct (può essere positivo per trailing)
            price_change_pct = sl_pct / leverage
            if direction == "long":
                # Long: SL positivo = sopra entry (profit lock), negativo = sotto entry (loss)
                expected_sl_price = entry_price * (1 + price_change_pct / 100)
                expected_side = "A"  # Ask (sell)
            else:
                # Short: SL positivo = sotto entry (profit lock), negativo = sopra entry (loss)
                expected_sl_price = entry_price * (1 - price_change_pct / 100)
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

                # Tenta di piazzare SL usando sl_pct già calcolato (include trailing)
                log(f"   🔧 Tentativo piazzamento SL per {symbol} (mode={trading_mode}, sl={sl_pct:+.2f}%)...")

                # IMPORTANTE: Prima cancella eventuali ordini SL esistenti per evitare duplicati
                # (la ricerca potrebbe non averli trovati per latenza API)
                try:
                    try:
                        all_orders = bot.info.frontend_open_orders(bot.account_address)
                    except AttributeError:
                        all_orders = bot.info.open_orders(bot.account_address)

                    cancelled_count = 0
                    for order in all_orders:
                        if order.get("coin") == symbol and order.get("side") == expected_side:
                            try:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                cancelled_count += 1
                                log(f"   🗑️ Cancellato ordine SL orfano OID={order.get('oid')}")
                                time.sleep(0.1)
                            except Exception as cancel_err:
                                log(f"   ⚠️ Errore cancellazione ordine {order.get('oid')}: {cancel_err}")
                    if cancelled_count > 0:
                        time.sleep(0.3)  # Attendi sync API
                except Exception as e:
                    log(f"   ⚠️ Errore pulizia ordini esistenti: {e}")

                # Usa expected_sl_price già calcolato sopra
                sl_price = bot._round_to_tick(expected_sl_price, symbol)
                is_buy = direction == "short"

                sl_order_result = bot.exchange.order(
                    symbol,
                    is_buy,
                    size,
                    sl_price,
                    {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
                    reduce_only=True
                )

                if sl_order_result.get("status") == "ok":
                    log(f"   ✅ SL piazzato @ ${sl_price:.2f} ({sl_pct:+.1f}%)")
                else:
                    log(f"   ❌ Errore piazzamento SL: {sl_order_result}")

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


def check_score_confirmation(symbol: str, threshold: float) -> dict:
    """
    Verifica se lo score è stato stabile sopra la soglia per N cicli consecutivi.

    Questo filtro evita aperture su spike momentanei di score che poi
    rientrano rapidamente sotto soglia.

    Args:
        symbol: Simbolo da verificare
        threshold: Soglia minima (es. SCORE_THRESHOLD_HOLD)

    Returns:
        dict con:
        - confirmed: True se tutti i cicli sono sopra soglia e stessa direzione
        - reason: Motivo se non confermato
        - cycles_above: Quanti cicli consecutivi sono sopra soglia
        - direction: "long" o "short" basato sulla direzione consistente
    """
    global _score_history

    result = {
        "confirmed": False,
        "reason": "",
        "cycles_above": 0,
        "direction": None,
        "scores": []
    }

    if symbol not in _score_history or len(_score_history[symbol]) == 0:
        result["reason"] = "No history"
        return result

    scores = _score_history[symbol]
    result["scores"] = scores.copy()

    # Verifica se abbiamo abbastanza campioni
    if len(scores) < SCORE_CONFIRMATION_CYCLES:
        result["reason"] = f"Need {SCORE_CONFIRMATION_CYCLES} cycles, have {len(scores)}"
        result["cycles_above"] = len(scores)
        return result

    # Prendi gli ultimi N cicli
    recent_scores = scores[-SCORE_CONFIRMATION_CYCLES:]

    # NUOVA LOGICA: Usa la MEDIA invece di controllare ogni singolo score
    avg_score = sum(recent_scores) / len(recent_scores)
    abs_avg = abs(avg_score)

    # Verifica che la MEDIA sia sopra la soglia minima
    if abs_avg < threshold:
        result["reason"] = f"Avg score {avg_score:.1f} below threshold {threshold}"
        result["cycles_above"] = 0
        return result

    # Verifica direzione consistente (maggioranza nella stessa direzione)
    positive_count = sum(1 for s in recent_scores if s > 0)
    negative_count = sum(1 for s in recent_scores if s < 0)

    # Almeno 2/3 devono essere nella stessa direzione
    min_same_direction = max(2, SCORE_CONFIRMATION_CYCLES * 2 // 3)

    if positive_count < min_same_direction and negative_count < min_same_direction:
        result["reason"] = f"Direction not consistent: {positive_count} long, {negative_count} short (need {min_same_direction})"
        return result

    # Confermato! Usa la direzione della media
    result["confirmed"] = True
    result["direction"] = "long" if avg_score > 0 else "short"
    result["cycles_above"] = SCORE_CONFIRMATION_CYCLES
    result["avg_score"] = avg_score

    return result


def calculate_quick_score(symbol: str, verbose: bool = True, double_bottom: dict = None, double_top: dict = None) -> float:
    """
    Calcola lo score usando signal_scorer.py (V1 o V2) + sentiment cache.

    V1: Logica binaria on/off
    V2: Logica graduale con indicatori aggiuntivi (Bollinger, OBV, MACD Histogram, EMA Alignment)
        + Pattern Detection (Double Bottom / Double Top)

    Seleziona V1 o V2 tramite USE_SMART_SCORE_V2 in .env

    Args:
        symbol: Simbolo da analizzare
        verbose: Se True, logga tutti i dettagli del calcolo
        double_bottom: Pattern detection result (optional)
        double_top: Pattern detection result (optional)

    Returns:
        float: Score positivo = bullish, negativo = bearish
               Range tipico: -50 a +50 (con indicatori V2)
    """
    try:
        from indicators import CryptoTechnicalAnalysisHL
        from signal_scorer import calculate_signal_score, calculate_smart_score_v2
        import db_utils

        # Check if V2 scoring is enabled
        use_v2 = os.getenv("USE_SMART_SCORE_V2", "false").lower() == "true"

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

        macd_signal_array = intraday.get('macd_signal', [0])
        macd_signal = macd_signal_array[-1] if macd_signal_array else 0

        ema_array = intraday.get('ema_20', [0])
        ema20 = ema_array[-1] if ema_array else 0

        # EMA50 per V2
        ema50_array = intraday.get('ema_50', [0])
        ema50 = ema50_array[-1] if ema50_array else 0

        prices_array = intraday.get('mid_prices', [0])
        price = prices_array[-1] if prices_array else 0

        # ADX per V2 filtering
        adx_array = intraday.get('adx', [25])
        adx = adx_array[-1] if adx_array else 25

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

        # === NUOVI INDICATORI V2 ===
        bollinger_data = data.get('bollinger', {})
        obv_data = data.get('obv', {})
        macd_analysis = data.get('macd_analysis', {})
        ema_alignment = data.get('ema_alignment', 'NEUTRAL')

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
            if use_v2:
                bb_pos = bollinger_data.get('position', 'N/A')
                obv_trend = obv_data.get('trend', 'N/A')
                log(f"      📈 {symbol} V2: ADX={adx:.1f}, BB={bb_pos}, OBV={obv_trend}, EMA={ema_alignment}")

        # Seleziona scorer V1 o V2
        if use_v2:
            score_result = calculate_smart_score_v2(
                price=price,
                ema20=ema20,
                ema50=ema50,
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                fear_greed=fear_greed,
                forecast_change_pct=0.0,  # Skip forecast nel sentinel
                volume_bid=volume_bid,
                volume_ask=volume_ask,
                symbol=symbol,
                # Nuovi indicatori V2
                bollinger=bollinger_data,
                obv_trend=obv_data.get('trend'),
                macd_histogram_trend=macd_analysis.get('histogram_trend'),
                ema_alignment=ema_alignment,
                adx=adx,
                # Pattern detection
                double_bottom=double_bottom,
                double_top=double_top
            )
        else:
            # V1: Logica originale
            score_result = calculate_signal_score(
                price=price,
                ema20=ema20,
                rsi=rsi,
                macd=macd,
                fear_greed=fear_greed,
                forecast_change_pct=0.0,
                volume_bid=volume_bid,
                volume_ask=volume_ask,
                symbol=symbol
            )

        net_score = score_result.get('net_score', 0.0)

        if verbose:
            # Log dettagliato dei segnali che hanno contribuito
            active_signals = [s for s in score_result.get('signals', []) if s.get('contribution', 0) > 0]
            signal_details = []
            for s in active_signals:
                dir_sign = "+" if s.get('direction') == 'BULLISH' else "-"
                signal_details.append(f"{s.get('indicator')}={dir_sign}{s.get('contribution'):.1f}")

            version_tag = "V2" if use_v2 else "V1"
            adx_mult = score_result.get('adx_multiplier', 1.0)
            adx_note = f" (ADX mult={adx_mult:.2f})" if use_v2 and adx_mult < 1.0 else ""

            log(f"      📊 {symbol} [{version_tag}] Score: bull={score_result.get('score_bullish'):.1f} bear={score_result.get('score_bearish'):.1f}{adx_note}")
            if signal_details:
                log(f"      📊 {symbol} Signals: {' | '.join(signal_details)}")

            # Highlight pattern detection separately for visibility
            if score_result.get('double_bottom'):
                db = score_result['double_bottom']
                neckline = db.get('neckline', 0)
                neckline_fmt = f"${neckline:,.0f}" if neckline > 10 else f"${neckline:.4f}"
                log(f"      🔷 {symbol} DOUBLE BOTTOM: conf={db.get('confidence', 0)*100:.0f}% | neckline={neckline_fmt}")
            if score_result.get('double_top'):
                dt = score_result['double_top']
                neckline = dt.get('neckline', 0)
                neckline_fmt = f"${neckline:,.0f}" if neckline > 10 else f"${neckline:.4f}"
                log(f"      🔻 {symbol} DOUBLE TOP: conf={dt.get('confidence', 0)*100:.0f}% | neckline={neckline_fmt}")

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


def get_daily_trade_count() -> int:
    """Conta i trade aperti oggi per limitare MAX_TRADES_PER_DAY."""
    if not DB_UTILS_ENABLED:
        return 0
    try:
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                # Usa opened_at invece di created_at per evitare di contare trade importati
                cur.execute("SELECT COUNT(*) FROM trades WHERE DATE(opened_at) = CURRENT_DATE")
                result = cur.fetchone()
                return result[0] if result else 0
    except Exception as e:
        log(f"⚠️ Errore conteggio trade: {e}")
        return 0


def open_micro_gain_position(bot, symbol: str, direction: str, score: float, leverage: int = None):
    """
    Apre una posizione MICRO_GAIN con SL order su Hyperliquid.

    NOTA: Il TP LIMIT è stato disabilitato per evitare chiusure premature.
    La sentinel gestisce il trailing stop.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        score: Score che ha generato il segnale
        leverage: Leva da usare (se None, usa MICRO_GAIN_LEVERAGE)

    Returns:
        dict con risultato operazione
    """
    import db_utils
    import telegram_notifier as tg

    # Use AI-suggested leverage or default
    actual_leverage = leverage if leverage is not None else MICRO_GAIN_LEVERAGE

    log(f"🎯 MICRO_GAIN AUTO-OPEN: {symbol} {direction.upper()} (score={score:.1f}, leverage={actual_leverage}x)")

    try:
        # === CLEANUP: Cancella tutti gli ordini esistenti per questo simbolo ===
        # Evita che ordini LIMIT/TRIGGER residui da trade precedenti causino problemi
        # IMPORTANTE: Retry se cancellazione fallisce per evitare SL orfani
        import time
        max_cleanup_attempts = 3
        for cleanup_attempt in range(max_cleanup_attempts):
            try:
                try:
                    existing_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    existing_orders = bot.info.open_orders(bot.account_address)

                symbol_orders = [o for o in existing_orders if o.get("coin") == symbol]
                if not symbol_orders:
                    if cleanup_attempt > 0:
                        log(f"   ✅ Tutti gli ordini residui per {symbol} cancellati (dopo {cleanup_attempt} tentativi)")
                    break

                cancelled_count = 0
                failed_count = 0
                for order in symbol_orders:
                    try:
                        bot.exchange.cancel(symbol, order.get("oid"))
                        cancelled_count += 1
                        log(f"   🗑️ Cancellato ordine residuo OID={order.get('oid')}")
                        time.sleep(0.1)  # Piccola pausa tra cancellazioni
                    except Exception as cancel_err:
                        failed_count += 1
                        log(f"   ⚠️ Errore cancellazione ordine OID={order.get('oid')}: {cancel_err}")

                if cancelled_count > 0:
                    log(f"   ✅ Cancellati {cancelled_count} ordini residui per {symbol}")
                    time.sleep(0.5)  # Attendi sync API prima di verificare

                if failed_count > 0 and cleanup_attempt < max_cleanup_attempts - 1:
                    log(f"   🔄 {failed_count} cancellazioni fallite, retry {cleanup_attempt + 2}/{max_cleanup_attempts}...")
                    time.sleep(0.5)
                elif failed_count > 0:
                    log(f"   ⚠️ ATTENZIONE: {failed_count} ordini residui per {symbol} NON cancellati!")
                else:
                    break

            except Exception as cleanup_err:
                log(f"   ⚠️ Errore cleanup ordini pre-apertura (tentativo {cleanup_attempt + 1}): {cleanup_err}")
                if cleanup_attempt < max_cleanup_attempts - 1:
                    time.sleep(0.5)

        # === RESET SL LEVEL: Evita che il FAST loop usi valori vecchi ===
        # Deve essere fatto PRIMA di aprire la posizione
        if symbol in _current_sl_level:
            log(f"   🔄 Reset _current_sl_level[{symbol}] (era: {_current_sl_level[symbol]:+.2f}%)")
            del _current_sl_level[symbol]

        # Prepara ordine
        order_json = {
            "operation": "open",
            "symbol": symbol,
            "direction": direction,
            "reason": f"MICRO_GAIN sentinel auto-open: score {score:.1f}",
            "target_portion_of_balance": MICRO_GAIN_PORTION,
            "leverage": actual_leverage,
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
            # === IMPORTANTE: Delay per permettere a HyperLiquid di processare il fill ===
            # Senza delay, l'API può restituire entry_price sbagliato/stale
            import time
            time.sleep(1.0)  # 1 secondo di attesa per il fill

            # Ottieni entry price dalla posizione (con retry per sicurezza)
            entry_price = 0
            position_size = 0

            for retry in range(3):
                account_status = bot.get_account_status()
                for pos in account_status.get("open_positions", []):
                    if pos.get("symbol") == symbol:
                        entry_price = float(pos.get("entry_price", 0))
                        position_size = float(pos.get("size", 0))
                        break

                if entry_price > 0:
                    log(f"   📊 [MICRO_GAIN] Entry price da HL: ${entry_price:.4f} (dopo {retry+1} tentativi)")
                    break

                log(f"   ⏳ [MICRO_GAIN] Entry price non disponibile, retry {retry+1}/3...")
                time.sleep(0.5)

            if entry_price > 0:
                # Crea tracking (IMPORTANTE: salva la leva per calcoli SL consistenti)
                db_utils.upsert_position_tracking(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=entry_price,
                    trailing_active=False,
                    opening_score=score,
                    trading_mode="MICRO_GAIN",
                    leverage=actual_leverage  # CRITICO: salva la leva decisa dall'AI
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
                            leverage=actual_leverage,
                            score=score,
                            sl_percent=MICRO_GAIN_STOP_LOSS_PERCENT,
                            tp_percent=MICRO_GAIN_TARGET_PERCENT,
                            trailing_activation=MICRO_GAIN_TRAILING_ACTIVATION,
                            trailing_gap=MICRO_GAIN_TRAILING_GAP
                        )
                        log(f"   📒 Trade Journal: registrato trade {trade_uuid[:8]}...")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal error: {e}")

                # Piazza SL order su Hyperliquid (passa actual_leverage per calcolo SL corretto)
                sl_price = place_micro_gain_sl_order(bot, symbol, direction, entry_price, position_size, leverage=actual_leverage)

                # IMPORTANTE: Inizializza SL level PRIMA di qualsiasi verifica
                # per evitare che verifiche successive usino valori stale
                _current_sl_level[symbol] = -MICRO_GAIN_STOP_LOSS_PERCENT
                log(f"   📊 SL level inizializzato a {-MICRO_GAIN_STOP_LOSS_PERCENT:+.2f}%")

                # NOTA: Verifica immediata DISABILITATA per evitare race condition
                # La verifica periodica (con protezione età > 60s) catturerà eventuali problemi
                # La verifica immediata poteva "correggere" lo SL con valori sbagliati
                # perché _current_sl_level poteva contenere valori stale da trade precedenti

                # Trade Journal: registra SL placement
                if TRADE_JOURNAL_ENABLED and trade_uuid and sl_price:
                    try:
                        tj.log_sl_placed(trade_uuid, sl_price, "STOP_TRIGGER", entry_price)
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal SL log error: {e}")

                # Notifica Telegram
                if SENTINEL_TELEGRAM_NOTIFY:
                    try:
                        # Calcoli per messaggio dettagliato
                        value_usd = position_size * entry_price
                        margin = value_usd / actual_leverage
                        # P&L è sul valore posizione, NON moltiplicato per leverage!
                        target_profit = value_usd * (MICRO_GAIN_TARGET_PERCENT / 100)
                        sl_loss = value_usd * (MICRO_GAIN_STOP_LOSS_PERCENT / 100)
                        # ROI% sul margine = target_pct * leverage
                        target_roi_pct = MICRO_GAIN_TARGET_PERCENT * actual_leverage
                        sl_roi_pct = MICRO_GAIN_STOP_LOSS_PERCENT * actual_leverage
                        fees_estimate = value_usd * 0.0007  # ~0.07% open+close

                        tg.send_telegram_message(
                            f"🎯 <b>MICRO_GAIN OPEN</b>\n\n"
                            f"<b>Symbol:</b> {symbol}\n"
                            f"<b>Direction:</b> {direction.upper()}\n"
                            f"<b>Entry:</b> ${entry_price:.2f}\n"
                            f"<b>Size:</b> {position_size:.6f} {symbol}\n"
                            f"<b>Valore:</b> ${value_usd:.2f}\n"
                            f"<b>Margine:</b> ${margin:.2f} ({actual_leverage}x)\n"
                            f"<b>Score:</b> {score:.1f}\n\n"
                            f"📊 <b>Target:</b> +{MICRO_GAIN_TARGET_PERCENT}% → ${target_profit:.2f} (ROI {target_roi_pct:.0f}%)\n"
                            f"🛑 <b>Stop Loss:</b> -{MICRO_GAIN_STOP_LOSS_PERCENT}% → ${sl_loss:.2f} (ROI -{sl_roi_pct:.0f}%)\n"
                            f"💸 <b>Fees stimate:</b> ~${fees_estimate:.2f}"
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


def place_micro_gain_sl_order(bot, symbol: str, direction: str, entry_price: float, size: float, leverage: int = None):
    """
    Piazza un ordine STOP LOSS trigger su Hyperliquid per MICRO_GAIN.

    Usa ordine STOP (trigger) invece di LIMIT per evitare esecuzione immediata.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size della posizione
        leverage: Leva effettiva della posizione (se None usa MICRO_GAIN_LEVERAGE)
    """
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

    try:
        # Usa la leva passata o il default
        actual_leverage = leverage if leverage is not None else MICRO_GAIN_LEVERAGE

        # Calcola prezzo SL trigger
        price_change_pct = MICRO_GAIN_STOP_LOSS_PERCENT / actual_leverage

        if direction == "long":
            # LONG: SL sotto il prezzo di entrata
            sl_trigger = entry_price * (1 - price_change_pct / 100)
        else:
            # SHORT: SL sopra il prezzo di entrata
            sl_trigger = entry_price * (1 + price_change_pct / 100)

        # Arrotonda al tick size
        sl_trigger = bot._round_to_tick(sl_trigger, symbol)

        log(f"   🛡️ Piazzo SL STOP @ ${sl_trigger:.2f} (trigger, loss: -{MICRO_GAIN_STOP_LOSS_PERCENT}%, leva: {actual_leverage}x, price_move: {price_change_pct:.2f}%)")

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


def initialize_micro_gain_sl_level(bot, symbol: str, direction: str, entry_price: float, leverage: int = None):
    """
    Inizializza _current_sl_level per MICRO_GAIN da ordine SL esistente su Hyperliquid.

    Questa funzione risolve il problema del riavvio container: quando la sentinel
    si riavvia, _current_sl_level è vuoto ma potrebbero esserci ordini SL già piazzati.
    Calcola il livello SL corrente dall'ordine esistente.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        leverage: Leva usata per la posizione (se None, usa MICRO_GAIN_LEVERAGE default)

    Returns:
        bool: True se il livello è stato inizializzato/trovato
    """
    global _current_sl_level

    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

    # Usa leva reale se passata, altrimenti default
    actual_leverage = leverage if leverage is not None else MICRO_GAIN_LEVERAGE

    # Se già esiste, non fare nulla
    if symbol in _current_sl_level:
        return True

    try:
        # Cerca ordini SL esistenti
        try:
            open_orders = bot.info.frontend_open_orders(bot.account_address)
        except AttributeError:
            open_orders = bot.info.open_orders(bot.account_address)

        expected_side = "B" if direction == "short" else "A"

        for order in open_orders:
            if order.get("coin") == symbol and order.get("side") == expected_side:
                trigger_px = order.get("triggerPx")
                if trigger_px and trigger_px != "0.0":
                    # SL già esiste - calcola il livello reale dal prezzo trigger
                    trigger_price = float(trigger_px)

                    # Calcola la percentuale SL reale basata sul prezzo trigger
                    if direction == "long":
                        # Long: SL sotto entry = negativo, sopra entry = positivo
                        price_diff_pct = ((trigger_price - entry_price) / entry_price) * 100
                    else:
                        # Short: SL sopra entry = negativo, sotto entry = positivo
                        price_diff_pct = ((entry_price - trigger_price) / entry_price) * 100

                    # Moltiplica per leva per ottenere il livello SL in %
                    calculated_sl_level = price_diff_pct * actual_leverage

                    # === VALIDAZIONE: Verifica che SL sia ragionevole per posizione corrente ===
                    # Se SL calcolato è molto più negativo di quanto configurato, è probabilmente
                    # un ordine residuo da una posizione precedente con entry_price diverso
                    max_reasonable_sl = -MICRO_GAIN_STOP_LOSS_PERCENT * 2.5  # es. -2.5% se SL=1%
                    if calculated_sl_level < max_reasonable_sl:
                        log(f"   ⚠️ {symbol}: SL trovato su HL sembra di posizione VECCHIA!")
                        log(f"      trigger=${trigger_px}, entry=${entry_price:.2f}")
                        log(f"      sl_level calcolato={calculated_sl_level:+.2f}% (< {max_reasonable_sl:+.2f}%)")
                        log(f"      🗑️ Cancello ordine SL obsoleto OID={order.get('oid')}...")
                        try:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            log(f"      ✅ Ordine SL obsoleto cancellato")
                            time.sleep(0.2)
                        except Exception as cancel_err:
                            log(f"      ⚠️ Errore cancellazione SL obsoleto: {cancel_err}")
                        # NON usare questo SL, continua a cercare altri ordini o usa default
                        continue

                    _current_sl_level[symbol] = calculated_sl_level
                    log(f"   ✅ {symbol} MICRO_GAIN SL recuperato da HL:")
                    log(f"      trigger=${trigger_px}, entry=${entry_price:.2f}, leva={actual_leverage}x")
                    log(f"      price_diff={price_diff_pct:.4f}%, sl_level={calculated_sl_level:+.2f}%")
                    return True

        # Nessun ordine SL trovato - inizializza al default
        _current_sl_level[symbol] = -MICRO_GAIN_STOP_LOSS_PERCENT
        log(f"   ℹ️ {symbol} MICRO_GAIN SL level inizializzato a default: {-MICRO_GAIN_STOP_LOSS_PERCENT:+.2f}%")
        return True

    except Exception as e:
        log(f"   ⚠️ Errore recupero SL level per {symbol}: {e}")
        # In caso di errore, usa il default
        _current_sl_level[symbol] = -MICRO_GAIN_STOP_LOSS_PERCENT
        return True


# ===== MICRO_PAY FUNCTIONS =====

def open_micro_pay_position(bot, symbol: str, direction: str, score: float, leverage: int = None):
    """
    Apre una posizione MICRO_PAY con TP e SL orders su Hyperliquid.

    MICRO_PAY è per score deboli (5-15): trade veloci con piccoli guadagni.
    Trailing disabilitato, solo TP/SL fissi.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        score: Score che ha generato il segnale
        leverage: Leva da usare (se None, usa MICRO_PAY_LEVERAGE)

    Returns:
        dict con risultato operazione
    """
    import db_utils
    import telegram_notifier as tg

    # Use AI-suggested leverage or default
    actual_leverage = leverage if leverage is not None else MICRO_PAY_LEVERAGE

    log(f"💵 MICRO_PAY AUTO-OPEN: {symbol} {direction.upper()} (score={score:.1f}, leverage={actual_leverage}x)")

    try:
        # === CLEANUP: Cancella tutti gli ordini esistenti per questo simbolo ===
        # Evita che ordini LIMIT/TRIGGER residui da trade precedenti causino problemi
        # IMPORTANTE: Retry se cancellazione fallisce per evitare SL orfani
        import time
        max_cleanup_attempts = 3
        for cleanup_attempt in range(max_cleanup_attempts):
            try:
                try:
                    existing_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    existing_orders = bot.info.open_orders(bot.account_address)

                symbol_orders = [o for o in existing_orders if o.get("coin") == symbol]
                if not symbol_orders:
                    if cleanup_attempt > 0:
                        log(f"   ✅ Tutti gli ordini residui per {symbol} cancellati (dopo {cleanup_attempt} tentativi)")
                    break

                cancelled_count = 0
                failed_count = 0
                for order in symbol_orders:
                    try:
                        bot.exchange.cancel(symbol, order.get("oid"))
                        cancelled_count += 1
                        log(f"   🗑️ Cancellato ordine residuo OID={order.get('oid')}")
                        time.sleep(0.1)
                    except Exception as cancel_err:
                        failed_count += 1
                        log(f"   ⚠️ Errore cancellazione ordine OID={order.get('oid')}: {cancel_err}")

                if cancelled_count > 0:
                    log(f"   ✅ Cancellati {cancelled_count} ordini residui per {symbol}")
                    time.sleep(0.5)

                if failed_count > 0 and cleanup_attempt < max_cleanup_attempts - 1:
                    log(f"   🔄 {failed_count} cancellazioni fallite, retry {cleanup_attempt + 2}/{max_cleanup_attempts}...")
                    time.sleep(0.5)
                elif failed_count > 0:
                    log(f"   ⚠️ ATTENZIONE: {failed_count} ordini residui per {symbol} NON cancellati!")
                else:
                    break

            except Exception as cleanup_err:
                log(f"   ⚠️ Errore cleanup ordini pre-apertura (tentativo {cleanup_attempt + 1}): {cleanup_err}")
                if cleanup_attempt < max_cleanup_attempts - 1:
                    time.sleep(0.5)

        # === RESET SL LEVEL: Evita che il FAST loop usi valori vecchi ===
        sl_key = f"{symbol}_MICROPAY"
        if sl_key in _current_sl_level:
            log(f"   🔄 Reset _current_sl_level[{sl_key}] (era: {_current_sl_level[sl_key]:+.2f}%)")
            del _current_sl_level[sl_key]

        # Prepara ordine
        order_json = {
            "operation": "open",
            "symbol": symbol,
            "direction": direction,
            "reason": f"MICRO_PAY sentinel auto-open: score {score:.1f}",
            "target_portion_of_balance": MICRO_PAY_PORTION,
            "leverage": actual_leverage,
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
            # === IMPORTANTE: Delay per permettere a HyperLiquid di processare il fill ===
            # Senza delay, l'API può restituire entry_price sbagliato/stale
            import time
            time.sleep(1.0)  # 1 secondo di attesa per il fill

            # Ottieni entry price dalla posizione (con retry per sicurezza)
            entry_price = 0
            position_size = 0

            for retry in range(3):
                account_status = bot.get_account_status()
                for pos in account_status.get("open_positions", []):
                    if pos.get("symbol") == symbol:
                        entry_price = float(pos.get("entry_price", 0))
                        position_size = float(pos.get("size", 0))
                        break

                if entry_price > 0:
                    log(f"   📊 [MICRO_PAY] Entry price da HL: ${entry_price:.4f} (dopo {retry+1} tentativi)")
                    break

                log(f"   ⏳ [MICRO_PAY] Entry price non disponibile, retry {retry+1}/3...")
                time.sleep(0.5)

            if entry_price > 0:
                # Crea tracking (IMPORTANTE: salva la leva per calcoli SL consistenti)
                db_utils.upsert_position_tracking(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=entry_price,
                    trailing_active=False,
                    opening_score=score,
                    trading_mode="MICRO_PAY",
                    leverage=actual_leverage  # CRITICO: salva la leva decisa dall'AI
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
                            leverage=actual_leverage,
                            score=score,
                            sl_percent=MICRO_PAY_STOP_LOSS_PERCENT,
                            tp_percent=MICRO_PAY_TARGET_PERCENT,
                            trailing_activation=0,  # No trailing per MICRO_PAY
                            trailing_gap=0
                        )
                        log(f"   📒 Trade Journal: registrato trade MICRO_PAY {trade_uuid[:8]}...")
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal error: {e}")

                # Piazza SL order su Hyperliquid (passa actual_leverage per calcolo SL corretto)
                sl_price = place_micro_pay_sl_order(bot, symbol, direction, entry_price, position_size, leverage=actual_leverage)

                # IMPORTANTE: Inizializza SL level PRIMA di qualsiasi verifica
                # per evitare che verifiche successive usino valori stale
                _current_sl_level[f"{symbol}_MICROPAY"] = -MICRO_PAY_STOP_LOSS_PERCENT
                log(f"   📊 MICRO_PAY SL level inizializzato a {-MICRO_PAY_STOP_LOSS_PERCENT:+.2f}%")

                # NOTA: Verifica immediata DISABILITATA per evitare race condition
                # La verifica periodica (con protezione età > 60s) catturerà eventuali problemi

                # Trade Journal: registra SL placement
                if TRADE_JOURNAL_ENABLED and trade_uuid and sl_price:
                    try:
                        tj.log_sl_placed(trade_uuid, sl_price, "STOP_TRIGGER", entry_price)
                    except Exception as e:
                        log(f"   ⚠️ Trade Journal SL log error: {e}")

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


def place_micro_pay_sl_order(bot, symbol: str, direction: str, entry_price: float, size: float, leverage: int = None):
    """
    Piazza un ordine STOP LOSS trigger su Hyperliquid per MICRO_PAY.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        size: Size della posizione
        leverage: Leva effettiva della posizione (se None usa MICRO_PAY_LEVERAGE)
    """
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

    try:
        # Usa la leva passata o il default
        actual_leverage = leverage if leverage is not None else MICRO_PAY_LEVERAGE

        # Calcola prezzo SL trigger
        price_change_pct = MICRO_PAY_STOP_LOSS_PERCENT / actual_leverage

        if direction == "long":
            sl_trigger = entry_price * (1 - price_change_pct / 100)
        else:
            sl_trigger = entry_price * (1 + price_change_pct / 100)

        sl_trigger = bot._round_to_tick(sl_trigger, symbol)

        log(f"   🛡️ Piazzo MICRO_PAY SL STOP @ ${sl_trigger:.2f} (loss: -{MICRO_PAY_STOP_LOSS_PERCENT}%, leva: {actual_leverage}x, price_move: {price_change_pct:.2f}%)")

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

                    log(f"   📍 Exit price: ${exit_price:.2f}, reason: {close_reason}")
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

                # === TELEGRAM NOTIFICATION ===
                try:
                    import telegram_notifier as tg

                    # Get current balance
                    account_status = bot.get_account_status()
                    balance = account_status.get("balance", 0)

                    # Get P&L stats
                    pnl_today = 0.0
                    pnl_week = 0.0
                    try:
                        daily_stats = tj.get_daily_stats()
                        if daily_stats:
                            pnl_today = daily_stats.get("net_pnl_usd", 0)
                        weekly_stats = tj.get_weekly_stats()
                        if weekly_stats:
                            pnl_week = weekly_stats.get("net_pnl_usd", 0)
                    except:
                        pass

                    # Extract trade data
                    direction = open_trade.get("direction", "long")
                    entry_price = float(open_trade.get("entry_price", 0))
                    # entry_time potrebbe essere in "entry_time" o "created_at"
                    entry_time = open_trade.get("entry_time") or open_trade.get("created_at")
                    if entry_time is None:
                        # Fallback: usa now - 5 minuti se entry_time non disponibile
                        entry_time = datetime.now() - timedelta(minutes=5)
                    elif hasattr(entry_time, 'replace') and entry_time.tzinfo is not None:
                        # Rimuovi timezone per evitare "can't subtract offset-naive and offset-aware"
                        entry_time = entry_time.replace(tzinfo=None)
                    leverage = int(open_trade.get("leverage", 1))
                    size = float(open_trade.get("size", 0))
                    margin = float(open_trade.get("margin", 0))
                    value_usd = size * entry_price if size else margin * leverage
                    score_open = open_trade.get("opening_score", 0)

                    # Calculate P&L
                    pnl_usd = result_close.get("net_pnl_usd", 0)
                    pnl_pct = result_close.get("pnl_pct", 0)

                    # Map close reason to string
                    reason_map = {
                        tj.CloseReason.TP_HIT: "TP_HIT",
                        tj.CloseReason.SL_HIT: "SL_HIT",
                        tj.CloseReason.MANUAL: "EXTERNAL_CLOSE"
                    }
                    close_reason_str = reason_map.get(close_reason, str(close_reason))

                    from datetime import datetime
                    exit_time = datetime.now()

                    tg.notify_trade_summary(
                        symbol=symbol,
                        direction=direction,
                        leverage=leverage,
                        entry_price=entry_price,
                        entry_time=entry_time,
                        size=size,
                        value_usd=value_usd,
                        margin=margin,
                        exit_price=exit_price,
                        exit_time=exit_time,
                        close_reason=close_reason_str,
                        pnl_usd=pnl_usd,
                        pnl_pct=pnl_pct,
                        score_open=score_open,
                        score_close=0,  # No score at external close
                        balance=balance,
                        pnl_today=pnl_today,
                        pnl_week=pnl_week,
                    )
                    log(f"   📱 Telegram: notifica inviata per chiusura esterna {close_reason_str}")
                except Exception as e:
                    log(f"   ⚠️ Errore notifica Telegram: {e}")

            except Exception as e:
                log(f"   ⚠️ Errore chiusura trade journal: {e}")

            # Cleanup tracking
            db_utils.delete_position_tracking(symbol)

            # SET COOLDOWN per evitare riapertura immediata
            if MICRO_GAIN_AUTO_OPEN:
                set_cooldown(symbol)
                log(f"   ⏳ Cooldown impostato per {symbol}")

            # Cancella ordini TP/SL rimasti su Hyperliquid
            try:
                try:
                    open_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    open_orders = bot.info.open_orders(bot.account_address)
                cancelled_count = 0
                for order in open_orders:
                    if order.get("coin") == symbol:
                        bot.exchange.cancel(symbol, order.get("oid"))
                        cancelled_count += 1
                if cancelled_count > 0:
                    log(f"   🗑️ Cancellati {cancelled_count} ordini residui per {symbol}")
            except Exception as e:
                log(f"   ⚠️ Errore cancellazione ordini residui: {e}")

            # Reset SL level
            sl_key_micro = symbol
            sl_key_normal = f"{symbol}_NORMAL"
            sl_key_micropay = f"{symbol}_MICROPAY"
            for key in [sl_key_micro, sl_key_normal, sl_key_micropay]:
                if key in _current_sl_level:
                    del _current_sl_level[key]

            # Pulisci Smart Exit price history
            if SMART_EXIT_AVAILABLE:
                smart_exit.clear_price_history(symbol)

    except Exception as e:
        log(f"⚠️ Errore detect_externally_closed_positions: {e}")


def update_micro_gain_sl_order(bot, symbol: str, direction: str, entry_price: float,
                                current_price: float, size: float, leverage: int = None):
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

    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

    # Se trailing disabilitato, esci subito
    if MICRO_GAIN_TRAILING_MODE == "disable":
        return False

    try:
        # Calcola P&L corrente (usa leva reale se passata, altrimenti default)
        actual_leverage = leverage if leverage is not None else MICRO_GAIN_LEVERAGE

        if direction == "long":
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            price_change_pct = ((entry_price - current_price) / entry_price) * 100

        pnl_pct = price_change_pct * actual_leverage

        # SL corrente (iniziale = -STOP_LOSS_PERCENT)
        current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT)

        # Log stato trailing con indicazione modalità e dati economici
        mode_str = MICRO_GAIN_TRAILING_MODE.upper()

        # Calcoli economici
        notional_value = size * current_price
        margin = notional_value / actual_leverage
        pnl_usd = (pnl_pct / 100) * margin
        fee_estimate = notional_value * 0.00045 * 2  # 0.045% per side (open+close)
        net_pnl_usd = pnl_usd - fee_estimate

        # Log arricchito con dati economici
        log(f"   📊 {symbol} MICRO_GAIN ({mode_str}): P&L={pnl_pct:+.2f}% (${pnl_usd:+.2f}) | SL={current_sl:+.2f}%")
        log(f"      💰 Entry=${entry_price:.2f} | Now=${current_price:.2f} | Size={size:.4f}")
        log(f"      📈 Margin=${margin:.2f} ({actual_leverage}x) | Net≈${net_pnl_usd:+.2f} (fees≈${fee_estimate:.2f})")

        # Calcola nuovo SL in base alla modalità
        new_sl_level = None

        if MICRO_GAIN_TRAILING_MODE == "steps":
            # === MODALITÀ GRADINI ===
            # Get dynamic steps based on ATR volatility
            dynamic_steps = get_dynamic_trailing_steps(symbol, MICRO_GAIN_TRAILING_STEPS)
            step_sl = get_step_sl_level(pnl_pct, current_sl, dynamic_steps)

            if step_sl > current_sl:
                new_sl_level = step_sl
                # Trova quale gradino è stato raggiunto
                step_reached = None
                for pnl_threshold, sl_level in dynamic_steps:
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
            # Calcola prezzo SL (usa leva reale, non default)
            sl_price_change = new_sl_level / actual_leverage

            if direction == "long":
                new_sl_price = entry_price * (1 + sl_price_change / 100)
            else:
                new_sl_price = entry_price * (1 - sl_price_change / 100)

            new_sl_price = bot._round_to_tick(new_sl_price, symbol)

            # Cancella TUTTI gli ordini SL esistenti (usa frontend_open_orders per vedere trigger orders!)
            try:
                try:
                    open_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    open_orders = bot.info.open_orders(bot.account_address)

                expected_side = "B" if direction == "short" else "A"
                cancelled_count = 0
                for order in open_orders:
                    if order.get("coin") == symbol and order.get("side") == expected_side:
                        try:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            cancelled_count += 1
                            time.sleep(0.1)  # Piccolo delay tra cancellazioni
                        except Exception as cancel_err:
                            log(f"   ⚠️ Errore cancellazione OID={order.get('oid')}: {cancel_err}")
                if cancelled_count > 0:
                    log(f"   🗑️ Cancellati {cancelled_count} ordini SL precedenti")
                    time.sleep(0.5)  # Attendi sync (aumentato)

                    # Verifica che cancellazione sia effettiva
                    try:
                        verify_orders = bot.info.frontend_open_orders(bot.account_address)
                    except AttributeError:
                        verify_orders = bot.info.open_orders(bot.account_address)

                    remaining = [o for o in verify_orders if o.get("coin") == symbol and o.get("side") == expected_side]
                    if remaining:
                        log(f"   ⚠️ {len(remaining)} ordini ancora presenti, riprovo cancellazione...")
                        for order in remaining:
                            try:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                log(f"   🗑️ Ri-cancellato OID={order.get('oid')}")
                                time.sleep(0.2)
                            except:
                                pass
                        time.sleep(0.5)
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
                                # Get dynamic activation from ATR-scaled steps
                                if MICRO_GAIN_TRAILING_MODE == "steps":
                                    dyn_steps = get_dynamic_trailing_steps(symbol, MICRO_GAIN_TRAILING_STEPS)
                                    activation_pct = dyn_steps[0][0] if dyn_steps else MICRO_GAIN_TRAILING_ACTIVATION
                                else:
                                    activation_pct = MICRO_GAIN_TRAILING_ACTIVATION
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

    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

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

        # Log stato trailing con indicazione modalità e dati economici
        mode_str = NORMAL_TRAILING_MODE.upper()

        # Calcoli economici
        notional_value = size * current_price
        margin = notional_value / actual_leverage
        pnl_usd = (pnl_pct / 100) * margin
        fee_estimate = notional_value * 0.00045 * 2  # 0.045% per side (open+close)
        net_pnl_usd = pnl_usd - fee_estimate

        # Log arricchito con dati economici
        log(f"   📊 {symbol} NORMAL ({mode_str}): P&L={pnl_pct:+.2f}% (${pnl_usd:+.2f}) | SL={current_sl:+.2f}%")
        log(f"      💰 Entry=${entry_price:.2f} | Now=${current_price:.2f} | Size={size:.4f}")
        log(f"      📈 Margin=${margin:.2f} ({actual_leverage}x) | Net≈${net_pnl_usd:+.2f} (fees≈${fee_estimate:.2f})")

        # Calcola nuovo SL in base alla modalità
        new_sl_level = None

        if NORMAL_TRAILING_MODE == "steps":
            # === MODALITÀ GRADINI ===
            # Get dynamic steps based on ATR volatility
            dynamic_steps = get_dynamic_trailing_steps(symbol, NORMAL_TRAILING_STEPS)
            # SL si alza solo quando si raggiunge un nuovo gradino
            step_sl = get_step_sl_level(pnl_pct, current_sl, dynamic_steps)

            if step_sl > current_sl:
                new_sl_level = step_sl
                # Trova quale gradino è stato raggiunto per il log
                step_reached = None
                for pnl_threshold, sl_level in dynamic_steps:
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

            # Cancella TUTTI gli ordini SL esistenti (usa frontend_open_orders per vedere trigger orders!)
            try:
                try:
                    open_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    open_orders = bot.info.open_orders(bot.account_address)

                expected_side = "B" if direction == "short" else "A"
                cancelled_count = 0
                for order in open_orders:
                    if order.get("coin") == symbol and order.get("side") == expected_side:
                        try:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            cancelled_count += 1
                            time.sleep(0.1)  # Piccolo delay tra cancellazioni
                        except Exception as cancel_err:
                            log(f"   ⚠️ Errore cancellazione OID={order.get('oid')}: {cancel_err}")
                if cancelled_count > 0:
                    log(f"   🗑️ Cancellati {cancelled_count} ordini SL precedenti")
                    time.sleep(0.5)  # Attendi sync (aumentato)

                    # Verifica che cancellazione sia effettiva
                    try:
                        verify_orders = bot.info.frontend_open_orders(bot.account_address)
                    except AttributeError:
                        verify_orders = bot.info.open_orders(bot.account_address)

                    remaining = [o for o in verify_orders if o.get("coin") == symbol and o.get("side") == expected_side]
                    if remaining:
                        log(f"   ⚠️ {len(remaining)} ordini ancora presenti, riprovo cancellazione...")
                        for order in remaining:
                            try:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                log(f"   🗑️ Ri-cancellato OID={order.get('oid')}")
                                time.sleep(0.2)
                            except:
                                pass
                        time.sleep(0.5)
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
                                # Get dynamic activation from ATR-scaled steps
                                if NORMAL_TRAILING_MODE == "steps":
                                    dyn_steps = get_dynamic_trailing_steps(symbol, NORMAL_TRAILING_STEPS)
                                    activation_pct = dyn_steps[0][0] if dyn_steps else NORMAL_TRAILING_ACTIVATION
                                else:
                                    activation_pct = NORMAL_TRAILING_ACTIVATION
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
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

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

                        # === VALIDAZIONE: Verifica che SL sia ragionevole per posizione corrente ===
                        max_reasonable_sl = -NORMAL_STOP_LOSS_PERCENT * 2.5
                        if calculated_sl_level < max_reasonable_sl:
                            log(f"   ⚠️ {symbol}: SL NORMAL trovato su HL sembra di posizione VECCHIA!")
                            log(f"      trigger=${trigger_px}, entry=${entry_price:.2f}")
                            log(f"      sl_level={calculated_sl_level:+.2f}% (< {max_reasonable_sl:+.2f}%)")
                            log(f"      🗑️ Cancello ordine SL obsoleto...")
                            try:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                log(f"      ✅ Ordine SL obsoleto cancellato")
                                time.sleep(0.2)
                            except Exception as cancel_err:
                                log(f"      ⚠️ Errore cancellazione: {cancel_err}")
                            # NON usare questo SL, continua
                            continue

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
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

    # Determina la leva da usare
    # IMPORTANTE: Usa SEMPRE la leva reale passata come parametro
    # perché il leverage scaling può cambiarla durante la posizione
    if trading_mode == "MICRO_GAIN":
        lev = leverage if leverage > 0 else MICRO_GAIN_LEVERAGE
        default_sl_pct = MICRO_GAIN_STOP_LOSS_PERCENT
    elif trading_mode == "MICRO_PAY":
        lev = leverage if leverage > 0 else MICRO_PAY_LEVERAGE
        default_sl_pct = MICRO_PAY_STOP_LOSS_PERCENT
    else:
        lev = leverage if leverage > 0 else 1.0  # Fallback a 1x se leverage non specificato
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
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

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

        # IMPORTANTE: Cerca PRIMA ordini TRIGGER, poi LIMIT
        # Questo evita di scambiare un ordine TP LIMIT per l'SL
        trigger_orders = []
        limit_orders = []

        for order in open_orders:
            if order.get("coin") == symbol and order.get("side") == expected_side:
                trigger_px = order.get("triggerPx")
                is_trigger = trigger_px is not None and trigger_px != "" and trigger_px != "0.0"
                if is_trigger:
                    trigger_orders.append(order)
                else:
                    limit_orders.append(order)

        # Priorità: usa ordine TRIGGER se esiste, altrimenti LIMIT
        if trigger_orders:
            # Se ci sono multipli trigger orders, seleziona quello con prezzo più vicino all'atteso
            # e cancella gli altri (potrebbero essere ordini duplicati o vecchi)
            if len(trigger_orders) > 1:
                log(f"   ⚠️ {symbol}: Trovati {len(trigger_orders)} ordini TRIGGER - seleziono il più vicino all'atteso")
                # Ordina per distanza dal prezzo atteso
                def get_price_diff(o):
                    try:
                        trigger_px = float(o.get("triggerPx", 0))
                        return abs(trigger_px - expected_sl_price)
                    except:
                        return float('inf')

                trigger_orders_sorted = sorted(trigger_orders, key=get_price_diff)
                order = trigger_orders_sorted[0]  # Usa quello più vicino

                # Cancella gli altri trigger orders (duplicati/vecchi)
                for dup_order in trigger_orders_sorted[1:]:
                    try:
                        dup_oid = dup_order.get("oid")
                        dup_price = dup_order.get("triggerPx", "?")
                        bot.exchange.cancel(symbol, dup_oid)
                        log(f"   🗑️ Cancellato ordine TRIGGER duplicato: OID={dup_oid}, trigger={dup_price}")
                        time.sleep(0.2)
                    except Exception as cancel_err:
                        log(f"   ⚠️ Errore cancellazione duplicato: {cancel_err}")
            else:
                order = trigger_orders[0]
            is_trigger = True

            # CRITICO: Se ci sono ordini LIMIT oltre al TRIGGER, sono spuri e vanno cancellati!
            # Questi potrebbero essere residui che causano chiusure inaspettate
            if limit_orders:
                log(f"   ⚠️ {symbol}: Trovati {len(limit_orders)} ordini LIMIT spuri oltre al TRIGGER - CANCELLO!")
                for spurious_order in limit_orders:
                    try:
                        spurious_oid = spurious_order.get("oid")
                        spurious_price = spurious_order.get("limitPx", "?")
                        bot.exchange.cancel(symbol, spurious_oid)
                        log(f"   🗑️ Cancellato ordine LIMIT spurio: OID={spurious_oid}, price={spurious_price}")
                        time.sleep(0.2)
                    except Exception as cancel_err:
                        log(f"   ⚠️ Errore cancellazione ordine spurio OID={spurious_order.get('oid')}: {cancel_err}")
        elif limit_orders:
            order = limit_orders[0]  # Fallback a LIMIT se non ci sono TRIGGER
            is_trigger = False
        else:
            order = None
            is_trigger = False

        if order:
            result["exists"] = True
            result["order"] = order

            trigger_px = order.get("triggerPx")
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
    # IMPORTANTE: Normalizza direction a lowercase per confronti corretti
    direction = direction.lower()

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

            # Cancella TUTTI gli ordini SL esistenti per questo simbolo (previene duplicati!)
            log(f"   🗑️ Cancello ordine errato per {symbol}...")
            try:
                # Prima cancella quello trovato
                bot.exchange.cancel(symbol, check["order"].get("oid"))
                log(f"   ✅ Ordine cancellato")
                time.sleep(0.3)

                # Poi cancella eventuali altri ordini SL duplicati
                try:
                    all_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    all_orders = bot.info.open_orders(bot.account_address)

                expected_side = "B" if direction == "short" else "A"
                for order in all_orders:
                    if order.get("coin") == symbol and order.get("side") == expected_side:
                        try:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            log(f"   🗑️ Cancellato ordine SL duplicato OID={order.get('oid')}")
                            time.sleep(0.2)
                        except Exception as cancel_err:
                            log(f"   ⚠️ Errore cancellazione duplicato OID={order.get('oid')}: {cancel_err}")
            except Exception as e:
                log(f"   ❌ Errore cancellazione: {e}")
        else:
            result["was_missing"] = True
            log(f"   ⚠️ {symbol} SL mancante")

            # Anche se mancante, cancella eventuali ordini SL duplicati/orfani
            try:
                try:
                    all_orders = bot.info.frontend_open_orders(bot.account_address)
                except AttributeError:
                    all_orders = bot.info.open_orders(bot.account_address)

                expected_side = "B" if direction == "short" else "A"
                for order in all_orders:
                    if order.get("coin") == symbol and order.get("side") == expected_side:
                        try:
                            bot.exchange.cancel(symbol, order.get("oid"))
                            log(f"   🗑️ Cancellato ordine SL orfano OID={order.get('oid')}")
                            time.sleep(0.2)
                        except Exception as cancel_err:
                            log(f"   ⚠️ Errore cancellazione orfano OID={order.get('oid')}: {cancel_err}")
            except Exception as e:
                log(f"   ⚠️ Errore pulizia ordini orfani: {e}")

        # IMPORTANTE: Verifica che tutti gli ordini siano stati effettivamente cancellati
        # Aspetta e ricontrolla per evitare race condition con API
        time.sleep(0.5)
        try:
            try:
                verify_orders = bot.info.frontend_open_orders(bot.account_address)
            except AttributeError:
                verify_orders = bot.info.open_orders(bot.account_address)

            expected_side = "B" if direction == "short" else "A"
            remaining_orders = [o for o in verify_orders if o.get("coin") == symbol and o.get("side") == expected_side]

            if remaining_orders:
                log(f"   ⚠️ Trovati {len(remaining_orders)} ordini SL ancora presenti, riprovo cancellazione...")
                for order in remaining_orders:
                    try:
                        bot.exchange.cancel(symbol, order.get("oid"))
                        log(f"   🗑️ Ri-cancellato OID={order.get('oid')}")
                        time.sleep(0.2)
                    except Exception as cancel_err:
                        log(f"   ⚠️ Errore ri-cancellazione: {cancel_err}")
                time.sleep(0.5)  # Aspetta ancora dopo la ri-cancellazione
        except Exception as e:
            log(f"   ⚠️ Errore verifica cancellazione: {e}")

        # Piazza nuovo ordine SL corretto
        log(f"   🔄 Piazzo nuovo SL per {symbol} (tentativo {attempt + 1}/{max_retries + 1})...")

        sl_price = None
        if trading_mode == "MICRO_GAIN":
            # Per MICRO_GAIN - usa current_sl_level se disponibile (trailing attivo)
            if current_sl_level is not None:
                # current_sl_level è già in % rispetto all'entry (es. +0.60% o -3.0%)
                sl_pct = current_sl_level
                log(f"   📊 Usando current_sl_level: {sl_pct:+.2f}%")
            else:
                # Fallback al valore iniziale
                sl_pct = -MICRO_GAIN_STOP_LOSS_PERCENT
                log(f"   📊 Usando SL iniziale: {sl_pct:.2f}%")

            # Calcola prezzo SL basato sulla percentuale (usa leva reale)
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

            log(f"   🛡️ Piazzo SL STOP @ ${sl_price:.2f} (trigger, {sl_pct:+.1f}%)")

            is_buy = direction == "short"
            sl_order = bot.exchange.order(
                symbol,
                is_buy,
                size,
                sl_price,
                {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") == "ok":
                response_data = sl_order.get("response", {})
                if response_data.get("type") == "order":
                    statuses = response_data.get("data", {}).get("statuses", [])
                    if statuses and statuses[0].get("resting"):
                        log(f"   ✅ SL STOP piazzato: OID={statuses[0]['resting']['oid']}")
            else:
                log(f"   ❌ Errore API: {sl_order}")
                sl_price = None
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


# ===== LEVERAGE SCALING FUNCTIONS =====

def check_leverage_scaling_conditions(
    symbol: str,
    direction: str,
    current_leverage: float,
    current_sl_level: float,
    trading_mode: str
) -> dict:
    """
    Verifica se le condizioni per il leverage scaling sono soddisfatte.

    Returns:
        dict con:
        - can_scale: bool
        - reason: str (motivo se non può scalare)
        - new_leverage: int (nuova leva se può scalare)
    """
    result = {
        "can_scale": False,
        "reason": "",
        "new_leverage": 0
    }

    # 1. Scaling abilitato?
    if not LEVERAGE_SCALING_ENABLED:
        result["reason"] = "Leverage scaling disabilitato"
        return result

    # 2. Solo per NORMAL mode (non MICRO_GAIN)
    if trading_mode != "NORMAL":
        result["reason"] = f"Solo per NORMAL mode (attuale: {trading_mode})"
        return result

    # 3. Cooldown attivo?
    if symbol in _leverage_scaling_cooldown and _leverage_scaling_cooldown[symbol] > 0:
        cycles_left = _leverage_scaling_cooldown[symbol]
        result["reason"] = f"Cooldown attivo ({cycles_left} cicli rimanenti)"
        return result

    # 4. Leva già al massimo?
    if current_leverage >= LEVERAGE_SCALING_MAX:
        result["reason"] = f"Leva già al massimo ({current_leverage}x >= {LEVERAGE_SCALING_MAX}x)"
        return result

    # 5. SL protegge profitto minimo?
    if current_sl_level is None:
        result["reason"] = "SL level non disponibile"
        return result

    if current_sl_level < LEVERAGE_SCALING_MIN_PROTECTED_PROFIT:
        result["reason"] = f"SL protegge {current_sl_level:+.2f}% < minimo {LEVERAGE_SCALING_MIN_PROTECTED_PROFIT}%"
        return result

    # Tutte le condizioni soddisfatte!
    new_leverage = min(int(current_leverage) + LEVERAGE_SCALING_STEP, LEVERAGE_SCALING_MAX)
    result["can_scale"] = True
    result["new_leverage"] = new_leverage
    result["reason"] = f"OK: SL protegge {current_sl_level:+.2f}% >= {LEVERAGE_SCALING_MIN_PROTECTED_PROFIT}%"

    return result


def execute_leverage_scaling(
    bot,
    symbol: str,
    direction: str,
    entry_price: float,
    mark_price: float,
    size: float,
    current_leverage: float,
    new_leverage: int,
    current_sl_level: float
) -> dict:
    """
    Esegue il leverage scaling con ordine di protezione.

    Procedura:
    1. Piazza ordine LIMIT di protezione al prezzo SL attuale
    2. Aumenta la leva
    3. Ricalcola e piazza nuovo SL
    4. Cancella ordine protezione

    Returns:
        dict con status e dettagli
    """
    import telegram_notifier as tg

    result = {
        "success": False,
        "old_leverage": current_leverage,
        "new_leverage": new_leverage,
        "protection_order_id": None,
        "error": None
    }

    log(f"   🚀 LEVERAGE SCALING: {symbol} {current_leverage}x → {new_leverage}x")

    try:
        # === STEP 1: Calcola prezzo protezione (dove lo SL chiuderebbe) ===
        # Il current_sl_level è in % P&L, dobbiamo convertirlo in prezzo
        sl_price_change_pct = abs(current_sl_level) / current_leverage

        if direction == "long":
            if current_sl_level >= 0:
                protection_price = entry_price * (1 + sl_price_change_pct / 100)
            else:
                protection_price = entry_price * (1 - sl_price_change_pct / 100)
        else:  # short
            if current_sl_level >= 0:
                protection_price = entry_price * (1 - sl_price_change_pct / 100)
            else:
                protection_price = entry_price * (1 + sl_price_change_pct / 100)

        # Arrotonda al tick size
        protection_price = bot._round_to_tick(protection_price, symbol)

        # === VERIFICA: Non piazzare protezione se prezzo è già migliore ===
        # Per LONG: se mark_price > protection_price, il LIMIT SELL verrebbe eseguito subito!
        # Per SHORT: se mark_price < protection_price, il LIMIT BUY verrebbe eseguito subito!
        skip_protection = False
        if direction == "long" and mark_price > protection_price:
            log(f"   ⚠️ Skip protezione: mark ${mark_price:.2f} > protection ${protection_price:.2f} (già in profitto)")
            skip_protection = True
        elif direction == "short" and mark_price < protection_price:
            log(f"   ⚠️ Skip protezione: mark ${mark_price:.2f} < protection ${protection_price:.2f} (già in profitto)")
            skip_protection = True

        if not skip_protection:
            log(f"   📋 Step 1: Piazzo ordine protezione LIMIT @ ${protection_price:.4f}")

            # === STEP 2: Piazza ordine LIMIT di protezione ===
            is_buy = direction == "short"  # Opposto per chiudere

            protection_order = bot.exchange.order(
                symbol,
                is_buy,
                size,
                protection_price,
                {"limit": {"tif": "Gtc"}},
                reduce_only=True
            )

            if protection_order.get("status") != "ok":
                result["error"] = f"Errore piazzamento ordine protezione: {protection_order}"
                log(f"   ❌ {result['error']}")
                return result

            # Estrai order ID
            response_data = protection_order.get("response", {})
            if response_data.get("type") == "order":
                order_data = response_data.get("data", {})
                statuses = order_data.get("statuses", [])
                if statuses and statuses[0].get("resting"):
                    result["protection_order_id"] = statuses[0]["resting"]["oid"]
                    log(f"   ✅ Ordine protezione piazzato: OID={result['protection_order_id']}")
                elif statuses and statuses[0].get("filled"):
                    # L'ordine è stato riempito immediatamente - ABORT!
                    result["error"] = f"ABORT: Ordine protezione riempito subito! Posizione potrebbe essere chiusa."
                    log(f"   🚨 {result['error']}")
                    return result
                else:
                    result["error"] = f"Ordine protezione non resting: {statuses}"
                    log(f"   ❌ {result['error']}")
                    return result
            else:
                result["error"] = f"Risposta ordine protezione inattesa: {response_data}"
                log(f"   ❌ {result['error']}")
                return result

            time.sleep(0.3)
        else:
            log(f"   📋 Step 1: SKIP protezione (prezzo già favorevole)")

        # === STEP 3: Aumenta la leva ===
        log(f"   📋 Step 2: Aumento leva {current_leverage}x → {new_leverage}x")

        leverage_result = bot.set_leverage_for_symbol(
            symbol=symbol,
            leverage=new_leverage,
            is_cross=True
        )

        if leverage_result.get("status") != "ok":
            log(f"   ⚠️ Warning leva: {leverage_result}")
            # Continua comunque, potrebbe essere solo un warning

        time.sleep(0.5)

        # === STEP 4: Ricalcola e piazza nuovo SL ===
        log(f"   📋 Step 3: Ricalcolo SL per nuova leva")

        # Ricalcola il prezzo SL per la nuova leva (mantieni stesso livello %)
        new_sl_price_change_pct = abs(current_sl_level) / new_leverage

        if direction == "long":
            if current_sl_level >= 0:
                new_sl_price = entry_price * (1 + new_sl_price_change_pct / 100)
            else:
                new_sl_price = entry_price * (1 - new_sl_price_change_pct / 100)
        else:  # short
            if current_sl_level >= 0:
                new_sl_price = entry_price * (1 - new_sl_price_change_pct / 100)
            else:
                new_sl_price = entry_price * (1 + new_sl_price_change_pct / 100)

        new_sl_price = bot._round_to_tick(new_sl_price, symbol)

        # Prima cancella vecchio SL (se esiste)
        try:
            open_orders = bot.exchange.open_orders()
            for order in open_orders:
                if order.get("symbol") == symbol and order.get("orderType") == "trigger":
                    log(f"   🗑️ Cancello vecchio SL OID={order.get('oid')}")
                    bot.exchange.cancel(symbol, order.get("oid"))
                    time.sleep(0.2)
        except Exception as e:
            log(f"   ⚠️ Errore cancellazione vecchio SL: {e}")

        # Piazza nuovo SL
        log(f"   📋 Step 4: Piazzo nuovo SL @ ${new_sl_price:.4f} (protegge {current_sl_level:+.2f}% P&L)")

        is_buy_sl = direction == "short"
        sl_order = bot.exchange.order(
            symbol,
            is_buy_sl,
            size,
            new_sl_price,
            {"trigger": {"triggerPx": new_sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True
        )

        if sl_order.get("status") != "ok":
            log(f"   ⚠️ Warning nuovo SL: {sl_order}")
        else:
            log(f"   ✅ Nuovo SL piazzato")

        time.sleep(0.3)

        # === STEP 5: Cancella ordine protezione (se piazzato) ===
        if result["protection_order_id"]:
            log(f"   📋 Step 5: Cancello ordine protezione")
            try:
                bot.exchange.cancel(symbol, result["protection_order_id"])
                log(f"   ✅ Ordine protezione cancellato")
            except Exception as e:
                log(f"   ⚠️ Errore cancellazione protezione (potrebbe essere già eseguito): {e}")
        else:
            log(f"   📋 Step 5: SKIP (nessun ordine protezione da cancellare)")

        # === STEP 6: Imposta cooldown ===
        _leverage_scaling_cooldown[symbol] = LEVERAGE_SCALING_COOLDOWN_CYCLES
        log(f"   ⏱️ Cooldown impostato: {LEVERAGE_SCALING_COOLDOWN_CYCLES} cicli")

        result["success"] = True

        # Notifica Telegram
        if SENTINEL_TELEGRAM_NOTIFY:
            try:
                # Calcola P&L corrente e potenziale
                if direction == "long":
                    price_change_pct = ((mark_price - entry_price) / entry_price) * 100
                else:
                    price_change_pct = ((entry_price - mark_price) / entry_price) * 100
                current_pnl_pct = price_change_pct * new_leverage  # Con nuova leva

                value_usd = size * entry_price

                tg.send_telegram_message(
                    f"🚀 <b>LEVERAGE SCALING</b>\n\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Direction:</b> {direction.upper()}\n"
                    f"<b>Entry:</b> ${entry_price:.2f}\n"
                    f"<b>Mark:</b> ${mark_price:.2f}\n"
                    f"<b>Size:</b> {size:.6f} {symbol} (${value_usd:.2f})\n\n"
                    f"📈 <b>Leva:</b> {int(current_leverage)}x → {int(new_leverage)}x\n"
                    f"🛡️ <b>SL protegge:</b> {current_sl_level:+.2f}%\n"
                    f"📍 <b>Nuovo SL @:</b> ${new_sl_price:.4f}\n\n"
                    f"✅ Scaling completato!"
                )
            except Exception as e:
                log(f"   ⚠️ Errore notifica Telegram: {e}")

        log(f"   ✅ LEVERAGE SCALING completato: {symbol} ora a {new_leverage}x")

    except Exception as e:
        result["error"] = str(e)
        log(f"   ❌ Errore leverage scaling: {e}")

        # Se abbiamo piazzato ordine protezione, prova a cancellarlo
        if result["protection_order_id"]:
            try:
                bot.exchange.cancel(symbol, result["protection_order_id"])
                log(f"   🧹 Cleanup: ordine protezione cancellato")
            except:
                pass

    return result


def process_leverage_scaling(bot, pos: dict, tracking_data: dict, current_sl_level: float):
    """
    Processa leverage scaling per una posizione.
    Chiamato dal loop principale del sentinel.
    """
    symbol = pos.get("symbol", "")
    direction = pos.get("side", "long").lower()
    entry_price = float(pos.get("entry_price", 0))
    mark_price = float(pos.get("mark_price", 0))
    size = float(pos.get("size", 0))

    # Parse leverage
    leverage_raw = pos.get("leverage", 1)
    if isinstance(leverage_raw, str):
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        current_leverage = float(match.group(1)) if match else 1.0
    else:
        current_leverage = float(leverage_raw)

    trading_mode = tracking_data.get("trading_mode", "NORMAL") if tracking_data else "NORMAL"

    # Decrementa cooldown se attivo
    if symbol in _leverage_scaling_cooldown and _leverage_scaling_cooldown[symbol] > 0:
        _leverage_scaling_cooldown[symbol] -= 1
        if _leverage_scaling_cooldown[symbol] > 0:
            log(f"   ⏱️ {symbol} scaling cooldown: {_leverage_scaling_cooldown[symbol]} cicli rimanenti")

    # Verifica condizioni
    check_result = check_leverage_scaling_conditions(
        symbol=symbol,
        direction=direction,
        current_leverage=current_leverage,
        current_sl_level=current_sl_level,
        trading_mode=trading_mode
    )

    if not check_result["can_scale"]:
        # Solo log se scaling è abilitato (evita spam)
        if LEVERAGE_SCALING_ENABLED and trading_mode == "NORMAL":
            log(f"   📊 {symbol} scaling: {check_result['reason']}")
        return None

    # Esegui scaling
    return execute_leverage_scaling(
        bot=bot,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        mark_price=mark_price,
        size=size,
        current_leverage=current_leverage,
        new_leverage=check_result["new_leverage"],
        current_sl_level=current_sl_level
    )


# ===== AUTO TAKE PROFIT FUNCTIONS =====

def check_and_place_auto_tp(bot, pos: dict, tracking_data: dict):
    """
    Verifica se piazzare un ordine LIMIT TP automatico.

    Condizioni:
    1. AUTO_TP_ENABLED = true
    2. Posizione aperta da >= AUTO_TP_DELAY_MINUTES
    3. Non esiste già un ordine TP per questo simbolo
    4. Trading mode = NORMAL (non MICRO_GAIN che ha già TP)

    Args:
        bot: HyperLiquidTrader instance
        pos: Dati posizione
        tracking_data: Dati tracking dal DB
    """
    import telegram_notifier as tg

    if not AUTO_TP_ENABLED:
        return None

    symbol = pos.get("symbol", "")
    direction = pos.get("side", "long").lower()
    entry_price = float(pos.get("entry_price", 0))
    size = float(pos.get("size", 0))

    # Solo per NORMAL mode
    trading_mode = tracking_data.get("trading_mode", "NORMAL") if tracking_data else "NORMAL"
    if trading_mode != "NORMAL":
        return None

    # Già piazzato?
    if symbol in _auto_tp_orders and _auto_tp_orders[symbol]:
        return None

    # Verifica tempo dall'apertura
    if not tracking_data:
        return None

    created_at = tracking_data.get('created_at')
    if not created_at:
        return None

    from datetime import datetime, timezone
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    duration_minutes = (now - created_at).total_seconds() / 60

    if duration_minutes < AUTO_TP_DELAY_MINUTES:
        remaining = AUTO_TP_DELAY_MINUTES - duration_minutes
        log(f"   ⏳ {symbol} AUTO_TP: aspetta ancora {remaining:.0f} min")
        return None

    # Parse leverage
    leverage_raw = pos.get("leverage", 1)
    if isinstance(leverage_raw, str):
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        leverage = float(match.group(1)) if match else 1.0
    else:
        leverage = float(leverage_raw)

    # Calcola prezzo TP basato su P&L %
    # P&L % = (price_change / entry) * leverage * 100
    # price_change = (target_pnl / 100) * entry / leverage
    price_change_pct = AUTO_TP_PERCENT / leverage

    if direction == "long":
        tp_price = entry_price * (1 + price_change_pct / 100)
    else:  # short
        tp_price = entry_price * (1 - price_change_pct / 100)

    tp_price = bot._round_to_tick(tp_price, symbol)

    log(f"   🎯 AUTO_TP: Piazzo LIMIT @ ${tp_price:.4f} per {symbol} (target +{AUTO_TP_PERCENT}% P&L)")

    try:
        # Piazza ordine LIMIT
        is_buy = direction == "short"  # Opposto per chiudere

        tp_order = bot.exchange.order(
            symbol,
            is_buy,
            size,
            tp_price,
            {"limit": {"tif": "Gtc"}},
            reduce_only=True
        )

        if tp_order.get("status") == "ok":
            response_data = tp_order.get("response", {})
            if response_data.get("type") == "order":
                order_data = response_data.get("data", {})
                statuses = order_data.get("statuses", [])
                if statuses and statuses[0].get("resting"):
                    order_id = statuses[0]["resting"]["oid"]
                    _auto_tp_orders[symbol] = order_id
                    log(f"   ✅ AUTO_TP piazzato: OID={order_id}")

                    # Notifica Telegram
                    if SENTINEL_TELEGRAM_NOTIFY:
                        try:
                            # Calcoli per messaggio dettagliato
                            value_usd = size * entry_price
                            target_profit = value_usd * (AUTO_TP_PERCENT / 100) * leverage
                            fees_estimate = value_usd * 0.0007 * leverage  # ~0.07%
                            net_profit_estimate = target_profit - fees_estimate

                            tg.send_telegram_message(
                                f"🎯 <b>AUTO TAKE PROFIT PIAZZATO</b>\n\n"
                                f"<b>Symbol:</b> {symbol}\n"
                                f"<b>Direction:</b> {direction.upper()}\n"
                                f"<b>Entry:</b> ${entry_price:.2f}\n"
                                f"<b>Size:</b> {size:.6f} {symbol} (${value_usd:.2f})\n"
                                f"<b>Leverage:</b> {int(leverage)}x\n\n"
                                f"🎯 <b>TP Price:</b> ${tp_price:.4f}\n"
                                f"📊 <b>Target P&L:</b> +{AUTO_TP_PERCENT}% (${target_profit:.2f})\n"
                                f"💸 <b>Fees stimate:</b> ~${fees_estimate:.2f}\n"
                                f"✅ <b>Net stimato:</b> ~${net_profit_estimate:.2f}\n\n"
                                f"⏱️ Ordine LIMIT piazzato dopo {duration_minutes:.0f} min"
                            )
                        except Exception as e:
                            log(f"   ⚠️ Errore Telegram: {e}")

                    return {"success": True, "order_id": order_id, "tp_price": tp_price}

        log(f"   ⚠️ AUTO_TP risposta inattesa: {tp_order}")
        return {"success": False, "error": str(tp_order)}

    except Exception as e:
        log(f"   ❌ AUTO_TP errore: {e}")
        return {"success": False, "error": str(e)}


def cleanup_auto_tp_on_close(symbol: str):
    """Rimuove tracking AUTO_TP quando posizione viene chiusa."""
    if symbol in _auto_tp_orders:
        del _auto_tp_orders[symbol]
        log(f"   🧹 AUTO_TP tracking rimosso per {symbol}")


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

        # IMPORTANTE: se non esiste tracking, la posizione è ancora in fase di apertura
        # NON verificare/correggere SL per evitare race condition con MICRO_GAIN
        if not tracking_data:
            log(f"   ⏳ {symbol}: Tracking non trovato, skip verifica (apertura in corso?)")
            continue

        trading_mode = tracking_data.get("trading_mode", "NORMAL")

        # === PROTEZIONE RACE CONDITION: Skip verifiche per posizioni appena aperte ===
        # Se la posizione è stata aperta da meno di 60 secondi, NON verificare/correggere SL
        # Questo evita che valori stale in _current_sl_level sovrascrivano SL corretti
        created_at = tracking_data.get("created_at") or tracking_data.get("entry_time")
        if created_at:
            try:
                from datetime import datetime as dt_check
                if isinstance(created_at, str):
                    created_dt = dt_check.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                else:
                    created_dt = created_at
                if hasattr(created_dt, 'tzinfo') and created_dt.tzinfo is not None:
                    created_dt = created_dt.replace(tzinfo=None)
                age_seconds = (dt_check.now() - created_dt).total_seconds()
                if age_seconds < POSITION_AGE_PROTECTION_SECONDS:
                    log(f"   ⏳ {symbol}: Posizione aperta da {age_seconds:.0f}s, skip verifica SL (< {POSITION_AGE_PROTECTION_SECONDS}s)")
                    continue
            except Exception as e:
                # CRITICO: Se c'è errore nel parsing data, skip per sicurezza (non modificare SL!)
                log(f"   ⚠️ {symbol}: Errore calcolo età posizione: {e} - SKIP per sicurezza")
                continue
        else:
            # Se manca created_at, la posizione potrebbe essere in fase di apertura - SKIP
            log(f"   ⏳ {symbol}: created_at mancante, skip verifica SL per sicurezza")
            continue

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

    # Usa ENABLED_SYMBOLS da risk_config o env
    symbols_to_check = ENABLED_SYMBOLS

    # === CHECK LIMITE GIORNALIERO ===
    daily_trades = get_daily_trade_count()
    if daily_trades >= MAX_TRADES_PER_DAY:
        log(f"   ⛔ LIMITE GIORNALIERO: {daily_trades}/{MAX_TRADES_PER_DAY} - NO nuovi trade")
        return

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

        # Get pattern data (cached)
        double_bottom, double_top = get_patterns_for_symbol(symbol)

        # Calcola score (now includes pattern contribution)
        score = calculate_quick_score(symbol, double_bottom=double_bottom, double_top=double_top)
        abs_score = abs(score)

        log(f"   📊 {symbol} quick_score: {score:.1f}")

        direction = "long" if score > 0 else "short"

        # Determine which pattern is active for this direction
        active_pattern = None
        if direction == "long" and double_bottom and double_bottom.get('detected'):
            active_pattern = double_bottom
        elif direction == "short" and double_top and double_top.get('detected'):
            active_pattern = double_top

        # Determina quale modalità usare basata sullo score
        # Priority: MICRO_GAIN > MICRO_PAY (score più alto = più sicuro)

        if SCORE_THRESHOLD_HOLD <= abs_score < SCORE_THRESHOLD_OPEN:
            # === MICRO_GAIN RANGE ===
            # Verifica conferma cicli prima di aprire
            confirmation = check_score_confirmation(symbol, SCORE_THRESHOLD_HOLD)

            if not confirmation["confirmed"]:
                log(f"   ⏳ {symbol} MICRO_GAIN: waiting confirmation - {confirmation['reason']}")
                log(f"      Recent scores: {[f'{s:.1f}' for s in confirmation['scores']]}")
                continue

            log(f"   ✅ {symbol} MICRO_GAIN: confirmed ({SCORE_CONFIRMATION_CYCLES} cycles stable)")

            # === DOUBLE_CHECK_AI: Validazione AI immediata prima di aprire ===
            ai_leverage = None  # Default: use MICRO_GAIN_LEVERAGE
            if DOUBLE_CHECK_AI_ENABLED:
                validation = validate_double_check_ai(symbol, direction, score, "MICRO_GAIN")

                if not validation.get("approved"):
                    log(f"   ❌ DOUBLE_CHECK RIFIUTATO: {validation.get('reason', 'AI declined')}")
                    continue  # AI ha rifiutato, non aprire

                log(f"   ✅ DOUBLE_CHECK APPROVATO: confidence={validation.get('confidence', 'N/A')}")
                # AI potrebbe suggerire direzione diversa
                ai_direction = validation.get("direction", direction)
                if ai_direction and ai_direction.lower() != direction.lower():
                    log(f"      ⚠️ AI suggerisce {ai_direction.upper()} invece di {direction.upper()}")
                    direction = ai_direction
                # AI-suggested leverage
                ai_leverage = validation.get("leverage")

            # Check if we should use pending entry system (FAST_LOOP)
            if active_pattern and PATTERN_ENTRY_SYSTEM == "FAST_LOOP":
                # Add current price to pattern data for invalidation check
                try:
                    current_price = float(bot.info.all_mids()[symbol])
                    active_pattern['current_price'] = current_price
                except Exception as e:
                    log(f"   ⚠️ {symbol}: Cannot get current price for pending entry: {e}")

                # Create pending entry instead of opening immediately
                if create_pending_entry(symbol, direction.upper(), active_pattern, "MICRO_GAIN"):
                    log(f"   ⏳ {symbol}: Using FAST_LOOP pending entry system (waiting for breakout)")
                    continue  # Don't open now, FAST loop will handle it
                else:
                    log(f"   ⚠️ {symbol}: Failed to create pending entry, opening immediately")

            result = open_micro_gain_position(bot, symbol, direction, score, leverage=ai_leverage)

            if result.get("success"):
                position_count += 1
                existing_symbols.append(symbol)

        elif MICRO_PAY_ENABLED and MICRO_PAY_THRESHOLD <= abs_score < SCORE_THRESHOLD_HOLD:
            # === MICRO_PAY RANGE ===
            # Verifica conferma cicli prima di aprire
            confirmation = check_score_confirmation(symbol, MICRO_PAY_THRESHOLD)

            if not confirmation["confirmed"]:
                log(f"   ⏳ {symbol} MICRO_PAY: waiting confirmation - {confirmation['reason']}")
                log(f"      Recent scores: {[f'{s:.1f}' for s in confirmation['scores']]}")
                continue

            log(f"   ✅ {symbol} MICRO_PAY: confirmed ({SCORE_CONFIRMATION_CYCLES} cycles stable)")

            # === DOUBLE_CHECK_AI: Validazione AI immediata prima di aprire ===
            ai_leverage = None  # Default: use MICRO_PAY_LEVERAGE
            if DOUBLE_CHECK_AI_ENABLED:
                validation = validate_double_check_ai(symbol, direction, score, "MICRO_PAY")

                if not validation.get("approved"):
                    log(f"   ❌ DOUBLE_CHECK RIFIUTATO: {validation.get('reason', 'AI declined')}")
                    continue

                log(f"   ✅ DOUBLE_CHECK APPROVATO: confidence={validation.get('confidence', 'N/A')}")
                ai_direction = validation.get("direction", direction)
                if ai_direction and ai_direction.lower() != direction.lower():
                    log(f"      ⚠️ AI suggerisce {ai_direction.upper()} invece di {direction.upper()}")
                    direction = ai_direction
                # AI-suggested leverage
                ai_leverage = validation.get("leverage")

            # Check if we should use pending entry system (FAST_LOOP)
            if active_pattern and PATTERN_ENTRY_SYSTEM == "FAST_LOOP":
                # Add current price to pattern data for invalidation check
                try:
                    current_price = float(bot.info.all_mids()[symbol])
                    active_pattern['current_price'] = current_price
                except Exception as e:
                    log(f"   ⚠️ {symbol}: Cannot get current price for pending entry: {e}")

                # Create pending entry instead of opening immediately
                if create_pending_entry(symbol, direction.upper(), active_pattern, "MICRO_PAY"):
                    log(f"   ⏳ {symbol}: Using FAST_LOOP pending entry system (waiting for breakout)")
                    continue  # Don't open now, FAST loop will handle it
                else:
                    log(f"   ⚠️ {symbol}: Failed to create pending entry, opening immediately")

            result = open_micro_pay_position(bot, symbol, direction, score, leverage=ai_leverage)

            if result.get("success"):
                position_count += 1
                existing_symbols.append(symbol)


def check_and_wake_ai_for_normal(bot, existing_positions: list):
    """
    Controlla se svegliare l'AI per score in range NORMAL (>= SCORE_THRESHOLD_OPEN).

    Con AI_FREE_MODE=false:
    - Se score >= SCORE_THRESHOLD_OPEN (confermato) e no posizione → Sveglia AI
    - Se score in direzione opposta alla posizione → Sveglia AI

    Con AI_FREE_MODE=true:
    - NON sveglia per score (AI gira su suo schedule)

    Args:
        bot: HyperLiquidTrader instance
        existing_positions: Lista posizioni aperte
    """
    # Se AI_FREE_MODE, non fare wake proattivi per score
    if AI_FREE_MODE:
        return

    # Usa ENABLED_SYMBOLS da risk_config o env
    symbols_to_check = ENABLED_SYMBOLS
    existing_symbols = [p.get("symbol") for p in existing_positions]

    for symbol in symbols_to_check:
        # Calcola score (già calcolato in check_and_open_micro_gain, ma serve qui)
        # Usiamo lo score già in _score_history se disponibile
        if symbol in _score_history and len(_score_history[symbol]) > 0:
            score = _score_history[symbol][-1]  # Ultimo score raw
        else:
            # Score non disponibile, skip
            continue

        abs_score = abs(score)

        # Solo range NORMAL (>= SCORE_THRESHOLD_OPEN)
        if abs_score < SCORE_THRESHOLD_OPEN:
            continue

        # Verifica se dovremmo svegliare AI
        wake_check = should_wake_ai_for_symbol(symbol, score, existing_positions)

        if wake_check["should_wake"]:
            log(f"   🤖 {symbol} NORMAL range: {wake_check['reason']}")
            log(f"      → Waking AI for potential trade (score={score:.1f})")
            wake_result = wake_ai_agent(symbol, "score_signal", sentinel_score=score)
            if wake_result.get("success"):
                log(f"   ✅ AI Agent avviato (PID: {wake_result.get('pid')})")
            else:
                log(f"   ⚠️ Fallito wake AI: {wake_result.get('error')}")
        else:
            # Log solo se score è alto ma non svegliamo
            if abs_score >= SCORE_THRESHOLD_OPEN:
                log(f"   🔇 {symbol} score={score:.1f}: {wake_check['reason']}")


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
            # === CHECK AI WAKE FOR NORMAL RANGE (score >= SCORE_THRESHOLD_OPEN) ===
            log("🤖 Controllo wake AI per range NORMAL...")
            check_and_wake_ai_for_normal(bot, [])  # No positions
            return

        log(f"Controllo {len(positions)} posizioni...")

        # === CHECK MICRO_GAIN AUTO-OPEN (se abbiamo meno di MAX posizioni) ===
        if MICRO_GAIN_AUTO_OPEN and len(positions) < MICRO_GAIN_MAX_POSITIONS:
            log(f"🔍 Controllo opportunità MICRO_GAIN ({len(positions)}/{MICRO_GAIN_MAX_POSITIONS} posizioni)...")
            check_and_open_micro_gain(bot, existing_symbols)

        # === CHECK AI WAKE FOR NORMAL RANGE (score in opposite direction) ===
        check_and_wake_ai_for_normal(bot, positions)

        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("side", "").lower()  # IMPORTANTE: lowercase per confronti
            entry_price = pos.get("entry_price", 0)
            mark_price = pos.get("mark_price", 0)
            pnl = pos.get("pnl_usd", 0)

            leverage = pos.get("leverage", 1)

            # Ottieni tracking dal DB
            tracking_data = db_utils.get_position_tracking(symbol)

            # Ottieni trading_mode dal tracking
            # IMPORTANTE: se non esiste tracking, la posizione è ancora in fase di apertura
            # NON piazzare SL automaticamente per evitare race condition con MICRO_GAIN
            if not tracking_data:
                # Skip questa posizione - il processo di apertura deve ancora completare
                log(f"   ⏳ {symbol}: Tracking non trovato, skip (apertura in corso?)")
                continue

            trading_mode = tracking_data.get("trading_mode", "NORMAL")

            # === DEBUG: confronta entry_price da HL API vs DB tracking ===
            tracked_entry_price = tracking_data.get("entry_price")
            if tracked_entry_price and abs(entry_price - tracked_entry_price) > 0.01:
                price_diff = entry_price - tracked_entry_price
                price_diff_pct = (price_diff / tracked_entry_price) * 100
                log(f"   ⚠️ [SLOW] {symbol}: ENTRY PRICE MISMATCH!")
                log(f"      HL API entry:  ${entry_price:.4f}")
                log(f"      DB tracking:   ${tracked_entry_price:.4f}")
                log(f"      Differenza:    ${price_diff:+.4f} ({price_diff_pct:+.2f}%)")
                # USA L'ENTRY PRICE DAL TRACKING (quello salvato all'apertura è più affidabile)
                entry_price = tracked_entry_price
                log(f"      → Usando entry_price da tracking: ${entry_price:.4f}")

            # === CHECK TAKE PROFIT (prima del trailing stop) ===
            tp_result = check_take_profit(pos)
            tp_triggered = tp_result.get("triggered", False)
            pnl_pct = tp_result.get("pnl_pct", 0)

            # === CHECK MICRO_GAIN REVERSAL ===
            micro_gain_result = {"triggered": False, "reason": "", "quick_score": 0.0}
            position_size = float(pos.get("size", 0))

            # === LEVERAGE: usa la leva SALVATA nel DB (decisa dall'AI all'apertura) ===
            # CRITICO: evita mismatch tra leva usata per aprire e leva usata per SL
            stored_leverage = tracking_data.get("leverage")

            if stored_leverage:
                # Usa la leva salvata nel DB (fonte autorevole)
                pos_leverage = stored_leverage
            else:
                # Fallback: parse leverage da HyperLiquid (per posizioni vecchie senza leva salvata)
                leverage_raw = pos.get("leverage", 1)
                if isinstance(leverage_raw, str):
                    import re
                    match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                    pos_leverage = float(match.group(1)) if match else MICRO_GAIN_LEVERAGE
                else:
                    pos_leverage = float(leverage_raw) if leverage_raw else MICRO_GAIN_LEVERAGE
                log(f"   [SLOW] ⚠️ {symbol}: Leva non salvata in DB, usando fallback: {pos_leverage}x")

            # === PROTEZIONE RACE CONDITION SLOW LOOP ===
            # Skip SL update per posizioni appena aperte (stesso check del FAST loop)
            slow_position_age_ok = True
            created_at_slow = tracking_data.get("created_at") or tracking_data.get("entry_time")
            if created_at_slow:
                try:
                    from datetime import datetime as dt_slow
                    if isinstance(created_at_slow, str):
                        created_dt_slow = dt_slow.fromisoformat(created_at_slow.replace('Z', '+00:00').replace('+00:00', ''))
                    else:
                        created_dt_slow = created_at_slow
                    if hasattr(created_dt_slow, 'tzinfo') and created_dt_slow.tzinfo is not None:
                        created_dt_slow = created_dt_slow.replace(tzinfo=None)
                    age_seconds_slow = (dt_slow.now() - created_dt_slow).total_seconds()
                    if age_seconds_slow < POSITION_AGE_PROTECTION_SECONDS:
                        log(f"   [SLOW] ⏳ {symbol}: Posizione aperta da {age_seconds_slow:.0f}s, skip SL update (< {POSITION_AGE_PROTECTION_SECONDS}s)")
                        slow_position_age_ok = False
                except Exception as e:
                    log(f"   [SLOW] ⚠️ {symbol}: Errore calcolo età: {e} - SKIP SL update per sicurezza")
                    slow_position_age_ok = False
            else:
                log(f"   [SLOW] ⏳ {symbol}: created_at mancante, skip SL update per sicurezza")
                slow_position_age_ok = False

            if trading_mode == "MICRO_GAIN" and tracking_data:
                micro_gain_result = check_micro_gain_reversal(pos, tracking_data)

                # === INITIALIZE MICRO_GAIN SL LEVEL (recupera da ordine esistente) ===
                # Solo se posizione abbastanza vecchia
                if position_size > 0 and slow_position_age_ok:
                    initialize_micro_gain_sl_level(bot, symbol, direction, entry_price, leverage=int(pos_leverage))

                # === UPDATE MICRO_GAIN TRAILING SL (lock-in profit) ===
                # Solo se posizione abbastanza vecchia
                if position_size > 0 and slow_position_age_ok:
                    update_micro_gain_sl_order(
                        bot, symbol, direction, entry_price, mark_price, position_size,
                        leverage=int(pos_leverage)
                    )

            elif trading_mode == "NORMAL" and NORMAL_TRAILING_ENABLED:
                # === UPDATE NORMAL TRAILING SL (same mechanism, different params) ===
                # Solo se posizione abbastanza vecchia
                if position_size > 0 and slow_position_age_ok:
                    # Prima piazza SL iniziale se non esiste
                    place_normal_initial_sl(
                        bot, symbol, direction, entry_price, position_size, pos_leverage
                    )
                    # Poi aggiorna se in profitto
                    update_normal_sl_order(
                        bot, symbol, direction, entry_price, mark_price, position_size, pos_leverage
                    )

                    # === LEVERAGE SCALING (dopo trailing, quando SL protegge profitto) ===
                    if LEVERAGE_SCALING_ENABLED:
                        sl_key = f"{symbol}_NORMAL"
                        current_sl_level = _current_sl_level.get(sl_key)
                        if current_sl_level is not None:
                            process_leverage_scaling(bot, pos, tracking_data, current_sl_level)

                    # === AUTO TAKE PROFIT (piazza LIMIT dopo X minuti) ===
                    if AUTO_TP_ENABLED:
                        check_and_place_auto_tp(bot, pos, tracking_data)

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

                    # Reset AUTO_TP tracking
                    cleanup_auto_tp_on_close(symbol)

                    # Cancella ordini TP/SL rimasti per questo simbolo (usa frontend_open_orders per trigger!)
                    try:
                        try:
                            open_orders = bot.info.frontend_open_orders(bot.account_address)
                        except AttributeError:
                            open_orders = bot.info.open_orders(bot.account_address)
                        for order in open_orders:
                            if order.get("coin") == symbol:
                                bot.exchange.cancel(symbol, order.get("oid"))
                                log(f"   🗑️ Cancellato ordine residuo OID={order.get('oid')}")
                    except Exception as e:
                        log(f"   ⚠️ Errore cancellazione ordini residui: {e}")

                    # Notifica Telegram con riassunto completo
                    if SENTINEL_TELEGRAM_NOTIFY:
                        try:
                            from datetime import datetime as dt

                            # Calcoli per messaggio dettagliato
                            value_usd = position_size * entry_price
                            margin = value_usd / pos_leverage
                            fees_estimate = value_usd * 0.0007 * pos_leverage  # ~0.07% open+close
                            net_pnl = pnl - fees_estimate
                            net_pnl_pct = pnl_pct - 0.07  # Sottrai fees %

                            # Entry time da tracking
                            entry_time = dt.now()
                            if tracking_data and tracking_data.get("created_at"):
                                try:
                                    created = tracking_data["created_at"]
                                    if isinstance(created, str):
                                        entry_time = dt.fromisoformat(created.replace('Z', '+00:00').replace('+00:00', ''))
                                    else:
                                        entry_time = created.replace(tzinfo=None) if hasattr(created, 'replace') else created
                                except:
                                    pass

                            exit_time = dt.now()

                            # Motivo chiusura
                            close_reason_map = {
                                "CLOSE_TAKE_PROFIT": "Take Profit",
                                "CLOSE_STOP_LOSS": "Stop Loss",
                                "CLOSE_TRAILING_STOP": f"Trailing Stop",
                                "CLOSE_MICRO_GAIN_REVERSAL": "Reversal Score",
                            }
                            close_reason = close_reason_map.get(action_taken, "Chiusura Manuale")

                            # Aggiungi livello SL se trailing
                            if action_taken == "CLOSE_TRAILING_STOP":
                                sl_key = symbol if trading_mode == "MICRO_GAIN" else f"{symbol}_NORMAL"
                                current_sl = _current_sl_level.get(sl_key, 0)
                                if current_sl != 0:
                                    close_reason = f"Trailing Stop {current_sl:+.1f}%"

                            # Recupera balance e stats
                            balance = None
                            pnl_today = None
                            pnl_week = None
                            try:
                                account_state = bot.info.user_state(bot.account_address)
                                balance = float(account_state.get("marginSummary", {}).get("accountValue", 0))

                                # P&L oggi/settimana dal database
                                stats = db_utils.get_performance_stats(hours=168)  # 7 giorni
                                if stats:
                                    pnl_week = stats.get("net_pnl_usd", 0)
                                stats_today = db_utils.get_performance_stats(hours=24)
                                if stats_today:
                                    pnl_today = stats_today.get("net_pnl_usd", 0)
                            except:
                                pass

                            # Score di apertura/chiusura
                            score_open = None
                            score_close = None
                            try:
                                if tracking_data:
                                    score_open = tracking_data.get("open_score")
                                # Score corrente come score chiusura
                                score_close = micro_gain_result.get("quick_score") if trading_mode == "MICRO_GAIN" else None
                            except:
                                pass

                            # Invia riassunto
                            tg.notify_trade_summary(
                                symbol=symbol,
                                direction=direction,
                                leverage=int(pos_leverage),
                                entry_price=entry_price,
                                entry_time=entry_time,
                                size=position_size,
                                value_usd=value_usd,
                                margin=margin,
                                exit_price=mark_price,
                                exit_time=exit_time,
                                close_reason=close_reason,
                                pnl_usd=net_pnl,
                                pnl_pct=net_pnl_pct,
                                score_open=score_open,
                                score_close=score_close,
                                balance=balance,
                                pnl_today=pnl_today,
                                pnl_week=pnl_week,
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

                    wake_reason = wake_reason_map.get(action_taken, "position_closed")

                    # Usa should_wake_ai_for_event per decidere
                    # Eventi (chiusure) svegliano sempre, indipendentemente da AI_FREE_MODE
                    if should_wake_ai_for_event(wake_reason) and SENTINEL_WAKE_ON_ALL_CLOSES:
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

                    # Wake AI Agent per rivalutare (volatility è sempre un evento valido)
                    if should_wake_ai_for_event("volatility_spike"):
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
        if DOUBLE_CHECK_AI_ENABLED:
            log(f"      🔍 DOUBLE_CHECK_AI: enabled with TRADING_STYLE={TRADING_STYLE.upper()}")
            if TRADING_STYLE == "aggressive":
                log(f"         → Aggressive: MACD alone is enough, ignores neutral RSI")
            elif TRADING_STYLE == "conservative":
                log(f"         → Conservative: Requires ALL signals aligned")
            else:
                log(f"         → Moderate: Requires MACD + EMA confirmation")
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

    # === LEVERAGE SCALING CONFIGURATION ===
    if LEVERAGE_SCALING_ENABLED:
        log(f"\n🚀 LEVERAGE SCALING: ENABLED")
        log(f"   Min protected profit: +{LEVERAGE_SCALING_MIN_PROTECTED_PROFIT}%")
        log(f"   Step: +{LEVERAGE_SCALING_STEP}x per scaling")
        log(f"   Max leverage: {LEVERAGE_SCALING_MAX}x")
        log(f"   Cooldown: {LEVERAGE_SCALING_COOLDOWN_CYCLES} cicli tra scaling")
    else:
        log(f"\n🚀 LEVERAGE SCALING: disabled")

    # === AUTO TAKE PROFIT CONFIGURATION ===
    if AUTO_TP_ENABLED:
        log(f"\n🎯 AUTO TAKE PROFIT: ENABLED")
        log(f"   Target: +{AUTO_TP_PERCENT}% P&L")
        log(f"   Delay: {AUTO_TP_DELAY_MINUTES} min dopo apertura")
    else:
        log(f"\n🎯 AUTO TAKE PROFIT: disabled")

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


# =============================================================================
# SENTINEL FAST - Price checks, SL updates, TP checks (every 2-5 seconds)
# =============================================================================

def run_sentinel_fast():
    """
    SENTINEL-FAST: Operazioni leggere e veloci.

    Esegue SOLO:
    - Check prezzi correnti
    - Aggiornamento trailing stop
    - Verifica/correzione ordini SL
    - Check Take Profit
    - Detect posizioni chiuse esternamente

    NON esegue:
    - Calcolo score
    - Validazione AI
    - Apertura posizioni
    """
    if not SENTINEL_ENABLED:
        return

    if not PRIVATE_KEY or not WALLET_ADDRESS:
        log("[FAST] PRIVATE_KEY o WALLET_ADDRESS mancanti")
        return

    try:
        from hyperliquid_trader import HyperLiquidTrader
        import db_utils
        import telegram_notifier as tg
    except ImportError as e:
        log(f"[FAST] Errore import: {e}")
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
        existing_symbols = [p.get("symbol") for p in positions]

        log(f"[FAST] Controllo {len(positions)} posizioni...")
        if PATTERN_DETECTION_ENABLED and PATTERN_ENTRY_SYSTEM == "FAST_LOOP":
            pending_entries_db = db_utils.get_all_pending_entries()
            pending_count = len(pending_entries_db)
            log(f"[FAST] 🔷 Pending Entries: {pending_count} | Contra Action: {PATTERN_CONTRA_ACTION}")

        # === DETECT EXTERNALLY CLOSED POSITIONS ===
        detect_externally_closed_positions(bot, existing_symbols)

        # === CHECK PENDING ENTRIES (Pattern-based entry system) ===
        if PATTERN_DETECTION_ENABLED and PATTERN_ENTRY_SYSTEM == "FAST_LOOP":
            if pending_count > 0:  # FIX: usa pending_count dal DB, non _pending_entries in memoria
                log(f"[FAST] 👀 Checking {pending_count} pending entries from database...")
                triggered = check_pending_entries(bot.exchange, bot.info, existing_symbols)

                for entry_data in triggered:
                    symbol = entry_data['symbol']
                    direction = entry_data['direction'].lower()
                    trading_mode = entry_data['trading_mode']
                    pattern_sl = entry_data.get('stop_loss')

                    log(f"   🚀 {symbol}: BREAKOUT TRIGGERED! Opening {trading_mode} {direction.upper()}")

                    # Open position based on trading mode
                    if trading_mode == "MICRO_GAIN":
                        result = open_micro_gain_position(bot, symbol, direction, 20, leverage=None)  # Score 20 as placeholder
                    elif trading_mode == "MICRO_PAY":
                        result = open_micro_pay_position(bot, symbol, direction, 10, leverage=None)

                    if result and result.get("success"):
                        log(f"   ✅ {symbol}: Position opened successfully from pattern breakout")
                        existing_symbols.append(symbol)
                        # Update positions list
                        account_status = bot.get_account_status()
                        positions = account_status.get("open_positions", [])

        if not positions:
            # Nessuna posizione, niente da fare per FAST
            return

        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("side", "").lower()  # IMPORTANTE: lowercase per confronti
            entry_price = float(pos.get("entry_price", 0))
            mark_price = float(pos.get("mark_price", 0))
            position_size = float(pos.get("size", 0))

            # Ottieni tracking dal DB PRIMA di usare leverage
            tracking_data = db_utils.get_position_tracking(symbol)

            # IMPORTANTE: se non esiste tracking, la posizione è ancora in fase di apertura
            # NON piazzare/modificare SL per evitare race condition con MICRO_GAIN
            if not tracking_data:
                log(f"   ⏳ [FAST] {symbol}: Tracking non trovato, skip (apertura in corso?)")
                continue

            trading_mode = tracking_data.get("trading_mode", "NORMAL")

            # === DEBUG: confronta entry_price da HL API vs DB tracking ===
            tracked_entry_price = tracking_data.get("entry_price")
            if tracked_entry_price and abs(entry_price - tracked_entry_price) > 0.01:
                price_diff = entry_price - tracked_entry_price
                price_diff_pct = (price_diff / tracked_entry_price) * 100
                log(f"   ⚠️ [FAST] {symbol}: ENTRY PRICE MISMATCH!")
                log(f"      HL API entry:  ${entry_price:.4f}")
                log(f"      DB tracking:   ${tracked_entry_price:.4f}")
                log(f"      Differenza:    ${price_diff:+.4f} ({price_diff_pct:+.2f}%)")
                # USA L'ENTRY PRICE DAL TRACKING (quello salvato all'apertura è più affidabile)
                entry_price = tracked_entry_price
                log(f"      → Usando entry_price da tracking: ${entry_price:.4f}")

            # === LEVERAGE: usa la leva SALVATA nel DB (decisa dall'AI all'apertura) ===
            # CRITICO: evita mismatch tra leva usata per aprire e leva usata per SL
            stored_leverage = tracking_data.get("leverage")

            if stored_leverage:
                # Usa la leva salvata nel DB (fonte autorevole)
                pos_leverage = stored_leverage
                log(f"   🔧 {symbol}: Usando leva da DB: {pos_leverage}x")
            else:
                # Fallback: parse leverage da HyperLiquid (per posizioni vecchie senza leva salvata)
                leverage_raw = pos.get("leverage", 1)
                if isinstance(leverage_raw, str):
                    import re
                    match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                    pos_leverage = float(match.group(1)) if match else MICRO_GAIN_LEVERAGE
                else:
                    pos_leverage = float(leverage_raw) if leverage_raw else MICRO_GAIN_LEVERAGE
                log(f"   ⚠️ {symbol}: Leva non salvata in DB, usando fallback da HL: {pos_leverage}x")

            # === PROTEZIONE RACE CONDITION: Skip SL update per posizioni appena aperte ===
            # Se la posizione è stata aperta da meno di 90 secondi, NON aggiornare SL
            # Questo evita che initialize_micro_gain_sl_level usi valori stale
            position_age_ok = True
            created_at = tracking_data.get("created_at") or tracking_data.get("entry_time")
            if created_at:
                try:
                    from datetime import datetime as dt_fast
                    if isinstance(created_at, str):
                        created_dt = dt_fast.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                    else:
                        created_dt = created_at
                    if hasattr(created_dt, 'tzinfo') and created_dt.tzinfo is not None:
                        created_dt = created_dt.replace(tzinfo=None)
                    age_seconds = (dt_fast.now() - created_dt).total_seconds()
                    if age_seconds < POSITION_AGE_PROTECTION_SECONDS:
                        log(f"   [FAST] ⏳ {symbol}: Posizione aperta da {age_seconds:.0f}s, skip SL update (< {POSITION_AGE_PROTECTION_SECONDS}s)")
                        position_age_ok = False
                except Exception as e:
                    # CRITICO: Se c'è errore nel parsing data, skip per sicurezza (non modificare SL!)
                    log(f"   [FAST] ⚠️ {symbol}: Errore calcolo età: {e} - SKIP SL update per sicurezza")
                    position_age_ok = False
            else:
                # Se manca created_at, la posizione potrebbe essere in fase di apertura - SKIP
                log(f"   [FAST] ⏳ {symbol}: created_at mancante, skip SL update per sicurezza")
                position_age_ok = False

            # === CHECK TAKE PROFIT ===
            tp_result = check_take_profit(pos)
            pnl_pct = tp_result.get("pnl_pct", 0)

            # === CHECK/UPDATE SL (con lock per evitare conflitti con SLOW) ===
            if position_age_ok:  # Skip se posizione troppo recente
                if SENTINEL_LOCK_ENABLED:
                    with SentinelLock(symbol, "sl_update", "FAST") as lock:
                        if lock.acquired:
                            _update_sl_for_position(bot, pos, tracking_data, trading_mode, entry_price, mark_price, position_size, pos_leverage)
                        else:
                            log(f"   [FAST] {symbol}: SL update skipped (SLOW has lock)")
                else:
                    _update_sl_for_position(bot, pos, tracking_data, trading_mode, entry_price, mark_price, position_size, pos_leverage)

            # === CHECK TRAILING STOP TRIGGER ===
            result = check_trailing_stop(pos, tracking_data)

            # Log stato sintetico con dati economici
            trailing_status = "ACTIVE" if result.get("trailing_active") else "inactive"

            # Calcoli economici per log FAST
            notional_value = position_size * mark_price
            margin = notional_value / pos_leverage if pos_leverage > 0 else notional_value
            pnl_usd = (pnl_pct / 100) * margin
            fee_estimate = notional_value * 0.00045 * 2  # 0.045% per side
            net_pnl_usd = pnl_usd - fee_estimate
            current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT) if trading_mode == "MICRO_GAIN" else _current_sl_level.get(f"{symbol}_NORMAL", -NORMAL_STOP_LOSS_PERCENT)

            log(f"   [FAST] {symbol}: {direction.upper()} P&L={pnl_pct:+.2f}% (${pnl_usd:+.2f}) | SL={current_sl:+.1f}% | trailing={trailing_status}")
            log(f"      💰 ${mark_price:.2f} | Margin=${margin:.2f} | Net≈${net_pnl_usd:+.2f}")

            # === CHECK FORCE_ACCELERATE (from contrary pattern detection in SLOW) ===
            if tracking_data.get('force_accelerate'):
                log(f"   [FAST] ⚡ {symbol}: FORCE_ACCELERATE rilevato (contrary pattern)")
                # Get current SL and calculate next step
                if trading_mode == "MICRO_GAIN":
                    current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT)
                    # Parse trailing steps to find next level
                    steps = MICRO_GAIN_TRAILING_STEPS_STR.split(",") if MICRO_GAIN_TRAILING_STEPS_STR else []
                    next_sl = current_sl
                    for step in steps:
                        parts = step.strip().split(":")
                        if len(parts) == 2:
                            try:
                                step_sl = float(parts[1])
                                if step_sl > current_sl:
                                    next_sl = step_sl
                                    break
                            except ValueError:
                                continue
                    # SICUREZZA: next_sl deve essere SOTTO il P&L corrente, altrimenti SL trigger immediato!
                    if next_sl > current_sl:
                        if next_sl < pnl_pct:
                            log(f"   [FAST] ⚡ {symbol}: Forzando SL da {current_sl:+.1f}% a {next_sl:+.1f}% (contrary pattern)")
                            _current_sl_level[symbol] = next_sl
                        else:
                            log(f"   [FAST] ⚠️ {symbol}: ACCELERATE bloccato! next_sl ({next_sl:+.1f}%) >= P&L ({pnl_pct:+.2f}%)")
                    else:
                        log(f"   [FAST] ⚡ {symbol}: SL già al massimo ({current_sl:+.1f}%), no accelerate possibile")
                elif trading_mode == "NORMAL":
                    current_sl = _current_sl_level.get(f"{symbol}_NORMAL", -NORMAL_STOP_LOSS_PERCENT)
                    steps = NORMAL_TRAILING_STEPS_STR.split(",") if NORMAL_TRAILING_STEPS_STR else []
                    next_sl = current_sl
                    for step in steps:
                        parts = step.strip().split(":")
                        if len(parts) == 2:
                            try:
                                step_sl = float(parts[1])
                                if step_sl > current_sl:
                                    next_sl = step_sl
                                    break
                            except ValueError:
                                continue
                    # SICUREZZA: next_sl deve essere SOTTO il P&L corrente
                    if next_sl > current_sl:
                        if next_sl < pnl_pct:
                            log(f"   [FAST] ⚡ {symbol}: Forzando SL da {current_sl:+.1f}% a {next_sl:+.1f}% (contrary pattern)")
                            _current_sl_level[f"{symbol}_NORMAL"] = next_sl
                        else:
                            log(f"   [FAST] ⚠️ {symbol}: ACCELERATE bloccato! next_sl ({next_sl:+.1f}%) >= P&L ({pnl_pct:+.2f}%)")

                # Reset force_accelerate flag nel DB
                db_utils.update_position_tracking(symbol, {'force_accelerate': False})
                log(f"   [FAST] ✅ {symbol}: force_accelerate reset")

            # === SMART EXIT ANALYSIS ===
            if SMART_EXIT_AVAILABLE and smart_exit.SMART_EXIT_ENABLED:
                try:
                    # Ottieni entry_time dal tracking (campo è created_at)
                    entry_time = tracking_data.get("created_at") or tracking_data.get("entry_time")
                    entry_timestamp = None
                    if entry_time:
                        try:
                            if isinstance(entry_time, datetime):
                                entry_timestamp = entry_time.timestamp()
                            elif isinstance(entry_time, str):
                                # Parse ISO format string
                                from datetime import datetime as dt_parse
                                entry_dt = dt_parse.fromisoformat(entry_time.replace('Z', '+00:00').replace('+00:00', ''))
                                entry_timestamp = entry_dt.timestamp()
                            else:
                                entry_timestamp = float(entry_time)
                        except Exception:
                            entry_timestamp = None

                    if entry_timestamp is None:
                        entry_timestamp = time.time() - 300  # Default: 5 min fa

                    # Ottieni current SL level
                    if trading_mode == "MICRO_GAIN":
                        current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT)
                        trailing_steps = MICRO_GAIN_TRAILING_STEPS_STR
                    elif trading_mode == "MICRO_PAY":
                        current_sl = _current_sl_level.get(f"{symbol}_MICROPAY", -MICRO_PAY_STOP_LOSS_PERCENT)
                        trailing_steps = ""  # MICRO_PAY non ha trailing steps
                    else:
                        current_sl = _current_sl_level.get(f"{symbol}_NORMAL", -NORMAL_STOP_LOSS_PERCENT)
                        trailing_steps = NORMAL_TRAILING_STEPS_STR if NORMAL_TRAILING_MODE == "steps" else ""

                    # Fetch funding rate (con cache)
                    funding_rate = smart_exit.fetch_funding_rate(bot, symbol)

                    # Chiama Smart Exit Optimizer
                    smart_rec = smart_exit.get_smart_exit_recommendation(
                        symbol=symbol,
                        direction=direction,
                        entry_price=entry_price,
                        current_price=mark_price,
                        position_size=position_size,
                        leverage=pos_leverage,
                        entry_time=entry_timestamp,
                        current_sl_pct=current_sl,
                        trailing_steps=trailing_steps,
                        market_indicators=None,  # TODO: passare indicatori dal SLOW loop
                        funding_rate=funding_rate
                    )

                    # Log raccomandazione
                    if smart_rec.get("enabled"):
                        smart_log = smart_exit.format_smart_exit_log(smart_rec, symbol)
                        if smart_log:
                            log(smart_log)

                        # Se should_accelerate è True, anticipa lo step
                        if smart_rec.get("should_accelerate") and smart_rec.get("next_step_sl") is not None:
                            next_sl = smart_rec.get("next_step_sl")

                            # SICUREZZA: MAI abbassare lo SL, specialmente profit lock!
                            if next_sl < current_sl:
                                log(f"   [SMART] ⛔ BLOCCATO: next_sl ({next_sl:+.1f}%) < current_sl ({current_sl:+.1f}%)")
                            else:
                                log(f"   [SMART] ⚡ Accelerando SL da {current_sl:+.1f}% a {next_sl:+.1f}%")
                                if trading_mode == "MICRO_GAIN":
                                    _current_sl_level[symbol] = next_sl
                                elif trading_mode == "NORMAL":
                                    _current_sl_level[f"{symbol}_NORMAL"] = next_sl

                except Exception as e:
                    log(f"   [SMART] ⚠️ Errore: {e}")

            # Se trailing/SL triggered, gestisci chiusura
            if result.get("triggered"):
                should_close_trailing = True  # Default: chiudi

                # === AI HOLD CHECK ===
                # Prima di chiudere, controlla se l'AI dice di tenere la posizione
                if SMART_EXIT_AVAILABLE and smart_exit.AI_HOLD_CHECK_ENABLED:
                    try:
                        # Calcola P&L per check
                        if direction == "long":
                            pnl_pct = ((mark_price - entry_price) / entry_price) * 100 * pos_leverage
                        else:
                            pnl_pct = ((entry_price - mark_price) / entry_price) * 100 * pos_leverage

                        # Ottieni quick score per direzione
                        quick_score = calculate_quick_score(symbol, verbose=False)
                        score_direction = "long" if quick_score > 0 else "short"

                        # Ottieni current SL level
                        if trading_mode == "MICRO_GAIN":
                            current_sl = _current_sl_level.get(symbol, -MICRO_GAIN_STOP_LOSS_PERCENT)
                        else:
                            current_sl = _current_sl_level.get(f"{symbol}_NORMAL", -NORMAL_STOP_LOSS_PERCENT)

                        # Fetch indicatori per AI (leggeri)
                        indicators = {}
                        try:
                            from indicators import analyze_multiple_tickers
                            _, indicators_list = analyze_multiple_tickers([symbol])
                            if indicators_list:
                                ind_data = indicators_list[0].get('current', {})
                                indicators = {
                                    'macd': ind_data.get('macd', 0),
                                    'rsi': ind_data.get('rsi', 50),
                                    'adx': ind_data.get('adx', 0),
                                    'price_vs_ema20': ind_data.get('price_vs_ema20_pct', 0)
                                }
                        except Exception:
                            pass  # Usa indicatori vuoti se errore

                        # Funzione per chiamare AI
                        def call_ai_for_hold_check(prompt):
                            try:
                                from trading_agent import previsione_trading_agent
                                return previsione_trading_agent(prompt)
                            except Exception:
                                return None

                        # Chiedi all'AI
                        hold_result = smart_exit.get_ai_hold_check_recommendation(
                            symbol=symbol,
                            direction=direction,
                            entry_price=entry_price,
                            current_price=mark_price,
                            pnl_percent=pnl_pct,
                            current_sl_pct=current_sl,
                            score_direction=score_direction,
                            score_value=abs(quick_score),
                            indicators=indicators,
                            call_ai_func=call_ai_for_hold_check
                        )

                        # Log risultato
                        log(smart_exit.format_hold_check_log(hold_result, symbol))

                        # Se AI dice HOLD, aggiorna SL a breakeven e non chiudere
                        if hold_result.get("should_hold"):
                            new_sl = hold_result.get("new_sl_pct", 0.0)
                            log(f"   [HOLD_CHECK] 🔒 AI dice HOLD! SL → {new_sl:+.1f}% (breakeven)")

                            # Aggiorna SL level
                            if trading_mode == "MICRO_GAIN":
                                _current_sl_level[symbol] = new_sl
                            else:
                                _current_sl_level[f"{symbol}_NORMAL"] = new_sl

                            should_close_trailing = False  # Non chiudere!

                    except Exception as e:
                        log(f"   [HOLD_CHECK] ⚠️ Errore: {e}")

                # Chiudi solo se AI non ha detto HOLD
                if should_close_trailing:
                    _handle_position_close(bot, pos, tracking_data, "CLOSE_TRAILING_STOP", result.get("reason", "Trailing Stop"))

            # Se TP triggered
            if tp_result.get("triggered"):
                _handle_position_close(bot, pos, tracking_data, "CLOSE_TAKE_PROFIT", tp_result.get("reason", "Take Profit"))

        # === VERIFICA ORDINI SL ===
        verification_result = run_order_verification(bot, positions)

        # === PASSIVE SL VERIFICATION ===
        # Skip se run_order_verification ha appena corretto degli SL (evita duplicati)
        if verification_result.get("fixed", 0) == 0:
            run_passive_sl_verification(bot, positions)
        else:
            log("🔍 Verifica SL passiva... (skip - SL appena corretti)")
            log("   ✅ Tutti gli SL verificati OK")

    except Exception as e:
        log(f"[FAST] ❌ Errore: {e}")
        import traceback
        traceback.print_exc()


def _update_sl_for_position(bot, pos, tracking_data, trading_mode, entry_price, mark_price, position_size, pos_leverage):
    """Helper per aggiornare SL di una posizione."""
    symbol = pos.get("symbol", "")
    direction = pos.get("side", "").lower()  # IMPORTANTE: lowercase per confronti

    if trading_mode == "MICRO_GAIN" and tracking_data:
        # Initialize MICRO_GAIN SL level
        if position_size > 0:
            initialize_micro_gain_sl_level(bot, symbol, direction, entry_price, leverage=int(pos_leverage))
            update_micro_gain_sl_order(bot, symbol, direction, entry_price, mark_price, position_size,
                                       leverage=int(pos_leverage))

    elif trading_mode == "NORMAL" and NORMAL_TRAILING_ENABLED:
        if position_size > 0:
            place_normal_initial_sl(bot, symbol, direction, entry_price, position_size, pos_leverage)
            update_normal_sl_order(bot, symbol, direction, entry_price, mark_price, position_size, pos_leverage)


def _handle_position_close(bot, pos, tracking_data, action_taken, reason):
    """Helper per gestire la chiusura di una posizione."""
    symbol = pos.get("symbol", "")
    direction = pos.get("side", "").lower()  # IMPORTANTE: lowercase
    position_size = float(pos.get("size", 0))

    try:
        log(f"   [FAST] 🔻 {symbol}: Chiusura per {action_taken}")

        # Pulisci Smart Exit price history e AI Hold Check state
        if SMART_EXIT_AVAILABLE:
            smart_exit.clear_price_history(symbol)
            smart_exit.reset_hold_check_state(symbol)

        # La chiusura effettiva viene gestita dall'ordine SL su exchange
        # Qui aggiorniamo solo tracking se necessario
    except Exception as e:
        log(f"   [FAST] ❌ Errore chiusura {symbol}: {e}")


def run_loop_fast(interval: int = None):
    """Esegue SENTINEL-FAST in loop continuo."""
    interval = interval or SENTINEL_FAST_INTERVAL

    log(f"🚀 SENTINEL-FAST avviato (intervallo: {interval}s)")
    log(f"   Funzioni: Price check, SL update, TP check, Trailing stop")
    log(f"   Lock: {'ENABLED' if SENTINEL_LOCK_ENABLED else 'DISABLED (legacy mode)'}")

    try:
        while True:
            run_sentinel_fast()
            time.sleep(interval)
    except KeyboardInterrupt:
        log("SENTINEL-FAST interrotto (Ctrl+C)")


# =============================================================================
# SENTINEL SLOW - Score calculations, AI validation, position opening (every 30-60s)
# =============================================================================

def run_sentinel_slow():
    """
    SENTINEL-SLOW: Operazioni pesanti e infrequenti.

    Esegue SOLO:
    - Calcolo score (indicatori, signal_scorer)
    - Validazione AI (DOUBLE_CHECK)
    - Apertura posizioni (MICRO_GAIN, MICRO_PAY)
    - Check reversal
    - Wake AI per NORMAL range

    NON esegue:
    - Check prezzi continui (lo fa FAST)
    - Aggiornamento SL (lo fa FAST)
    """
    if not SENTINEL_ENABLED:
        return

    if not MICRO_GAIN_AUTO_OPEN:
        log("[SLOW] MICRO_GAIN_AUTO_OPEN disabled, nothing to do")
        return

    if not PRIVATE_KEY or not WALLET_ADDRESS:
        log("[SLOW] PRIVATE_KEY o WALLET_ADDRESS mancanti")
        return

    try:
        from hyperliquid_trader import HyperLiquidTrader
        import db_utils
    except ImportError as e:
        log(f"[SLOW] Errore import: {e}")
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
        existing_symbols = [p.get("symbol") for p in positions]

        log(f"[SLOW] Posizioni aperte: {len(positions)}/{MICRO_GAIN_MAX_POSITIONS}")
        if PATTERN_DETECTION_ENABLED:
            log(f"[SLOW] 🔷 Pattern Detection: ON ({PATTERN_DETECTION_TIMEFRAME}, {PATTERN_ENTRY_SYSTEM})")

        # === CHECK MICRO_GAIN AUTO-OPEN ===
        if len(positions) < MICRO_GAIN_MAX_POSITIONS:
            log(f"[SLOW] 🔍 Calcolo score e check opportunità...")

            # Segnala a FAST che SLOW è attivo (evita conflitti)
            if SENTINEL_LOCK_ENABLED:
                for symbol in ENABLED_SYMBOLS:
                    signal_slow_active(symbol, True)

            try:
                check_and_open_micro_gain(bot, existing_symbols)
            finally:
                # Rilascia segnale SLOW attivo
                if SENTINEL_LOCK_ENABLED:
                    for symbol in ENABLED_SYMBOLS:
                        signal_slow_active(symbol, False)

        # === CHECK MICRO_GAIN REVERSAL (per posizioni esistenti) ===
        for pos in positions:
            symbol = pos.get("symbol", "")
            tracking_data = db_utils.get_position_tracking(symbol)
            trading_mode = tracking_data.get("trading_mode", "NORMAL") if tracking_data else "NORMAL"

            if trading_mode == "MICRO_GAIN" and tracking_data:
                micro_gain_result = check_micro_gain_reversal(pos, tracking_data)
                if micro_gain_result.get("triggered"):
                    log(f"[SLOW] ⚠️ {symbol}: Reversal detected (score={micro_gain_result.get('quick_score', 0):.1f})")

            # === CHECK CONTRARY PATTERN (Pattern-based exit protection) ===
            if PATTERN_DETECTION_ENABLED and PATTERN_CONTRA_ACTION != "ALERT_ONLY":
                position_direction = pos.get("side", "").upper()
                double_bottom, double_top = get_patterns_for_symbol(symbol)

                # Check Double Bottom against SHORT position
                if position_direction == "SHORT" and double_bottom and double_bottom.get('detected'):
                    conf = double_bottom.get('confidence', 0)
                    if handle_contrary_pattern(symbol, position_direction, "DOUBLE_BOTTOM", conf, bot.exchange, bot.info):
                        if PATTERN_CONTRA_ACTION == "ACCELERATE" and SMART_EXIT_AVAILABLE:
                            # Force ACCELERATE through smart_exit
                            log(f"[SLOW] 🔄 {symbol}: Forcing ACCELERATE due to contrary pattern")
                            # Set flag for smart_exit to use
                            tracking_data['force_accelerate'] = True
                            db_utils.update_position_tracking(symbol, tracking_data)

                # Check Double Top against LONG position
                elif position_direction == "LONG" and double_top and double_top.get('detected'):
                    conf = double_top.get('confidence', 0)
                    if handle_contrary_pattern(symbol, position_direction, "DOUBLE_TOP", conf, bot.exchange, bot.info):
                        if PATTERN_CONTRA_ACTION == "ACCELERATE" and SMART_EXIT_AVAILABLE:
                            # Force ACCELERATE through smart_exit
                            log(f"[SLOW] 🔄 {symbol}: Forcing ACCELERATE due to contrary pattern")
                            # Set flag for smart_exit to use
                            tracking_data['force_accelerate'] = True
                            db_utils.update_position_tracking(symbol, tracking_data)

        # === CHECK AI WAKE FOR NORMAL RANGE ===
        log("[SLOW] 🤖 Check wake AI per range NORMAL...")
        check_and_wake_ai_for_normal(bot, positions)

    except Exception as e:
        log(f"[SLOW] ❌ Errore: {e}")
        import traceback
        traceback.print_exc()


def run_loop_slow(interval: int = None):
    """Esegue SENTINEL-SLOW in loop continuo."""
    interval = interval or SENTINEL_SLOW_INTERVAL

    log(f"🧠 SENTINEL-SLOW avviato (intervallo: {interval}s)")
    log(f"   Funzioni: Score calculation, AI validation, Position opening")
    log(f"   Lock: {'ENABLED' if SENTINEL_LOCK_ENABLED else 'DISABLED (legacy mode)'}")
    if DOUBLE_CHECK_AI_ENABLED:
        log(f"   🔍 DOUBLE_CHECK_AI: enabled with TRADING_STYLE={TRADING_STYLE.upper()}")

    try:
        while True:
            run_sentinel_slow()
            log(f"[SLOW] 💤 Prossimo check tra {interval}s...")
            time.sleep(interval)
    except KeyboardInterrupt:
        log("SENTINEL-SLOW interrotto (Ctrl+C)")


def main():
    parser = argparse.ArgumentParser(description="Sentinel - Monitoraggio trailing stop")
    parser.add_argument("--loop", action="store_true", help="Esegui in loop continuo")
    parser.add_argument("--interval", type=int, default=None, help="Intervallo in secondi (default: da .env)")
    parser.add_argument("--mode", type=str, default="both", choices=["fast", "slow", "both"],
                        help="Modalità: fast (price/SL), slow (score/AI), both (legacy)")
    args = parser.parse_args()

    print("=" * 50)
    print("🛡️  SENTINEL - Trailing Stop Monitor")
    print(f"   Mode: {args.mode.upper()}")
    print("=" * 50)

    # Log configuration status
    if args.mode in ["slow", "both"]:
        print(f"   📊 Pattern Detection: {'ENABLED' if PATTERN_DETECTION_ENABLED else 'DISABLED'}")
        if PATTERN_DETECTION_ENABLED:
            print(f"      Timeframe: {PATTERN_DETECTION_TIMEFRAME}")
            print(f"      Entry System: {PATTERN_ENTRY_SYSTEM}")
            print(f"      Contra Action: {PATTERN_CONTRA_ACTION}")
            print(f"      Min Confidence: {PATTERN_MIN_CONFIDENCE*100:.0f}%")
        print("=" * 50)

    if args.loop:
        if args.mode == "fast":
            run_loop_fast(args.interval)
        elif args.mode == "slow":
            run_loop_slow(args.interval)
        else:
            run_loop(args.interval)
    else:
        if args.mode == "fast":
            run_sentinel_fast()
        elif args.mode == "slow":
            run_sentinel_slow()
        else:
            run_sentinel_check()


if __name__ == "__main__":
    main()
