"""
Smart Exit Optimizer - Accelera trailing step quando il trend gira.

IMPORTANTE: Questo modulo NON chiude posizioni direttamente.
Lavora IN SINERGIA con il sistema di trailing stop esistente.

Funzionalità:
1. Calcola P&L netto reale (fees apertura, chiusura, funding)
2. Analizza trend posizione vs trend mercato
3. Suggerisce ACCELERATE (anticipa prossimo step) quando trend gira
4. Il trailing stop esistente rimane INTATTO
"""

import os
import time
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import deque
import numpy as np

# =============================================================================
# FEE STRUCTURE HYPERLIQUID (Tier 0: ≤ $5M volume)
# =============================================================================
# Perps Taker: 0.0450%
# Perps Maker: 0.0150%
# Queste sono le fee REALI di Hyperliquid
TAKER_FEE_RATE = 0.00045  # 0.045% per side
MAKER_FEE_RATE = 0.00015  # 0.015% per side

# =============================================================================
# CONFIGURAZIONE (da .env)
# =============================================================================
SMART_EXIT_ENABLED = os.getenv('SMART_EXIT_ENABLED', 'false').lower() == 'true'
PRICE_HISTORY_SIZE = int(os.getenv('SMART_EXIT_HISTORY_SIZE', '100'))  # 100 letture default
TREND_WINDOW = int(os.getenv('SMART_EXIT_TREND_WINDOW', '30'))  # Finestra per calcolo trend

# Soglie per decisione ACCELERATE
ACCELERATE_CONFIDENCE_THRESHOLD = int(os.getenv('SMART_EXIT_ACCELERATE_CONFIDENCE', '75'))
MIN_PROFIT_FOR_ACCELERATE = float(os.getenv('SMART_EXIT_MIN_PROFIT', '0.3'))  # % minimo netto

# AI Decision
SMART_EXIT_AI_ENABLED = os.getenv('SMART_EXIT_AI_ENABLED', 'false').lower() == 'true'


@dataclass
class PositionMetrics:
    """Metriche calcolate in tempo reale per ogni posizione."""

    symbol: str
    direction: str  # 'long' o 'short'
    entry_price: float
    current_price: float
    position_size: float
    leverage: float
    entry_time: float  # timestamp

    # P&L breakdown
    gross_pnl_pct: float = 0.0       # P&L lordo %
    gross_pnl_usd: float = 0.0       # P&L lordo $
    fee_open_usd: float = 0.0        # Fee apertura $
    fee_close_usd: float = 0.0       # Fee chiusura stimata $
    funding_paid_usd: float = 0.0    # Funding pagato $
    net_pnl_pct: float = 0.0         # P&L NETTO %
    net_pnl_usd: float = 0.0         # P&L NETTO $

    # Notional values
    notional_entry: float = 0.0      # Valore posizione all'apertura
    notional_current: float = 0.0    # Valore posizione attuale

    # Trend analysis
    price_history: List[float] = field(default_factory=list)
    pos_trend_slope: float = 0.0     # Pendenza trend posizione (-1 to +1)
    mkt_trend_slope: float = 0.0     # Pendenza trend mercato
    trend_aligned: bool = True       # Trend posizione = trend mercato?
    trend_strength: float = 0.0      # Forza del trend (R², 0-1)

    # Break-even analysis
    breakeven_price: float = 0.0     # Prezzo per uscire a zero dopo fees
    distance_to_breakeven_pct: float = 0.0  # % dal breakeven

    # Time analysis
    time_in_position_sec: int = 0    # Secondi in posizione

    # Trailing step info
    current_sl_pct: float = 0.0      # SL attuale (% P&L)
    next_step_trigger: float = 0.0   # P&L per prossimo step
    next_step_sl: float = 0.0        # SL del prossimo step

    # Smart recommendation
    action: str = "HOLD"             # "HOLD" o "ACCELERATE"
    confidence: float = 0.0          # 0-100%
    reason: str = ""                 # Spiegazione


# =============================================================================
# STORAGE GLOBALE
# =============================================================================
# Price history per simbolo (persiste tra cicli FAST)
_price_histories: Dict[str, deque] = {}

# Cache funding rate (aggiornato periodicamente)
_funding_rates: Dict[str, dict] = {}
_funding_rates_last_update: float = 0
FUNDING_RATE_CACHE_SECONDS = 300  # Aggiorna ogni 5 minuti


# =============================================================================
# PRICE HISTORY FUNCTIONS
# =============================================================================

def get_price_history(symbol: str) -> deque:
    """Ottiene o crea la price history per un simbolo."""
    if symbol not in _price_histories:
        _price_histories[symbol] = deque(maxlen=PRICE_HISTORY_SIZE)
    return _price_histories[symbol]


def add_price_to_history(symbol: str, price: float, timestamp: float = None):
    """Aggiunge un prezzo alla history."""
    history = get_price_history(symbol)
    history.append({
        'price': price,
        'timestamp': timestamp or time.time()
    })


def clear_price_history(symbol: str):
    """Pulisce la history quando la posizione viene chiusa."""
    if symbol in _price_histories:
        _price_histories[symbol].clear()


def get_history_duration_seconds(symbol: str) -> float:
    """Ritorna la durata in secondi della price history raccolta."""
    history = get_price_history(symbol)
    if len(history) < 2:
        return 0
    return history[-1]['timestamp'] - history[0]['timestamp']


# =============================================================================
# FUNDING RATE FUNCTIONS
# =============================================================================

def fetch_funding_rate(bot, symbol: str) -> float:
    """
    Fetch funding rate reale da Hyperliquid API.

    Args:
        bot: HyperLiquidTrader instance
        symbol: Simbolo (BTC, ETH, SOL)

    Returns:
        Funding rate in % (es. 0.01 = 0.01%)
    """
    global _funding_rates, _funding_rates_last_update

    current_time = time.time()

    # Usa cache se recente
    if (current_time - _funding_rates_last_update) < FUNDING_RATE_CACHE_SECONDS:
        if symbol in _funding_rates:
            return _funding_rates[symbol].get('rate', 0.0)

    try:
        # Hyperliquid API per funding rates
        meta = bot.info.meta()

        if meta and 'universe' in meta:
            for asset_info in meta['universe']:
                if asset_info.get('name') == symbol:
                    funding = asset_info.get('funding', 0)
                    _funding_rates[symbol] = {
                        'rate': float(funding) * 100,  # Converti in %
                        'timestamp': current_time
                    }
                    _funding_rates_last_update = current_time
                    return _funding_rates[symbol]['rate']

        return 0.0

    except Exception as e:
        # In caso di errore, ritorna 0 (meglio sottostimare che bloccare)
        return 0.0


# =============================================================================
# TRAILING STEPS PARSER
# =============================================================================

def parse_trailing_steps(steps_str: str) -> List[Tuple[float, float]]:
    """
    Parsa la stringa degli step di trailing.

    Args:
        steps_str: Formato "pnl1:sl1,pnl2:sl2,..." es. "0.8:-2.0,1.4:0.3,2.2:1.0"

    Returns:
        Lista di tuple (trigger_pnl, sl_level) ordinate per trigger_pnl
    """
    if not steps_str:
        return []

    steps = []
    try:
        for pair in steps_str.split(','):
            trigger, sl = pair.split(':')
            steps.append((float(trigger.strip()), float(sl.strip())))
        # Ordina per trigger P&L crescente
        steps.sort(key=lambda x: x[0])
        return steps
    except Exception:
        return []


def find_current_and_next_step(current_pnl: float, steps: List[Tuple[float, float]]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Trova lo step corrente e il prossimo step basato sul P&L attuale.

    Args:
        current_pnl: P&L attuale in %
        steps: Lista di (trigger_pnl, sl_level)

    Returns:
        (current_step, next_step) - tuple (trigger, sl) per ognuno
        next_step è None se siamo all'ultimo step
    """
    if not steps:
        return (None, None), (None, None)

    current_step = (0, steps[0][1])  # Default: primo SL
    next_step = None

    for i, (trigger, sl) in enumerate(steps):
        if current_pnl >= trigger:
            current_step = (trigger, sl)
            # Prossimo step se esiste
            if i + 1 < len(steps):
                next_step = steps[i + 1]
        else:
            # Non abbiamo ancora raggiunto questo step
            next_step = (trigger, sl)
            break

    return current_step, next_step


# =============================================================================
# FEE CALCULATIONS
# =============================================================================

def calculate_fees(notional: float, is_taker: bool = True) -> float:
    """Calcola le fees per un lato del trade (apertura o chiusura)."""
    rate = TAKER_FEE_RATE if is_taker else MAKER_FEE_RATE
    return notional * rate


def calculate_breakeven_price(entry_price: float, direction: str,
                               leverage: float, total_fees_pct: float) -> float:
    """
    Calcola il prezzo di breakeven considerando le fees.

    Args:
        entry_price: Prezzo di entrata
        direction: 'long' o 'short'
        leverage: Leva usata
        total_fees_pct: fees totali come % del notional (es. 0.09 per 0.09%)

    Returns:
        Prezzo breakeven
    """
    # Fee come % del movimento prezzo necessario
    fee_price_impact = total_fees_pct / leverage

    if direction == "long":
        # Long: prezzo deve salire abbastanza da coprire fees
        return entry_price * (1 + fee_price_impact / 100)
    else:
        # Short: prezzo deve scendere abbastanza da coprire fees
        return entry_price * (1 - fee_price_impact / 100)


# =============================================================================
# TREND ANALYSIS
# =============================================================================

def calculate_trend_slope(prices: List[float]) -> Tuple[float, float]:
    """
    Calcola la pendenza del trend usando regressione lineare.

    Args:
        prices: Lista di prezzi

    Returns:
        (slope, r_squared): slope normalizzato (-1 to +1), forza del trend (0-1)
    """
    if len(prices) < 3:
        return 0.0, 0.0

    try:
        prices_arr = np.array(prices)
        mean_price = np.mean(prices_arr)
        if mean_price == 0:
            return 0.0, 0.0

        # Regressione lineare
        x = np.arange(len(prices_arr))
        x_mean = np.mean(x)
        y_mean = np.mean(prices_arr)

        numerator = np.sum((x - x_mean) * (prices_arr - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return 0.0, 0.0

        slope = numerator / denominator

        # Normalizza slope in percentuale per periodo
        slope_pct = (slope / mean_price) * 100

        # R-squared per forza del trend
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = np.sum((prices_arr - y_pred) ** 2)
        ss_tot = np.sum((prices_arr - y_mean) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        r_squared = max(0, min(1, r_squared))

        # Normalizza slope a range -1 to +1
        normalized_slope = max(-1, min(1, slope_pct / 0.3))

        return normalized_slope, r_squared

    except Exception:
        return 0.0, 0.0


# =============================================================================
# MAIN METRICS CALCULATION
# =============================================================================

def calculate_position_metrics(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    position_size: float,
    leverage: float,
    entry_time: float,
    current_sl_pct: float = None,
    trailing_steps: str = None,
    market_indicators: dict = None,
    funding_rate: float = 0.0
) -> PositionMetrics:
    """
    Calcola tutte le metriche per una posizione.

    Args:
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        current_price: Prezzo corrente
        position_size: Size in coin
        leverage: Leva usata
        entry_time: Timestamp apertura
        current_sl_pct: SL attuale in % (dal trailing stop)
        trailing_steps: Stringa degli step (es. "0.8:-2.0,1.4:0.3,...")
        market_indicators: Dict con EMA, MACD, etc.
        funding_rate: Funding rate in % (se 0, verrà stimato)

    Returns:
        PositionMetrics con tutti i calcoli
    """
    metrics = PositionMetrics(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        position_size=position_size,
        leverage=leverage,
        entry_time=entry_time
    )

    # === NOTIONAL VALUES ===
    metrics.notional_entry = position_size * entry_price
    metrics.notional_current = position_size * current_price

    # === GROSS P&L ===
    if direction == "long":
        price_change_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        price_change_pct = ((entry_price - current_price) / entry_price) * 100

    metrics.gross_pnl_pct = price_change_pct * leverage
    metrics.gross_pnl_usd = (metrics.notional_current - metrics.notional_entry) * (1 if direction == "long" else -1)

    # === FEES ===
    metrics.fee_open_usd = calculate_fees(metrics.notional_entry)
    metrics.fee_close_usd = calculate_fees(metrics.notional_current)

    # === FUNDING ===
    metrics.time_in_position_sec = int(time.time() - entry_time)
    hours_held = metrics.time_in_position_sec / 3600

    if funding_rate != 0:
        funding_periods = hours_held / 8  # Funding ogni 8h
        if direction == "long":
            metrics.funding_paid_usd = metrics.notional_current * (funding_rate / 100) * funding_periods
        else:
            metrics.funding_paid_usd = -metrics.notional_current * (funding_rate / 100) * funding_periods

    # === NET P&L ===
    total_fees_usd = metrics.fee_open_usd + metrics.fee_close_usd + abs(metrics.funding_paid_usd)
    metrics.net_pnl_usd = metrics.gross_pnl_usd - total_fees_usd

    margin_used = metrics.notional_entry / leverage
    if margin_used > 0:
        metrics.net_pnl_pct = (metrics.net_pnl_usd / margin_used) * 100

    # === BREAKEVEN ===
    total_fees_pct = ((metrics.fee_open_usd + metrics.fee_close_usd) / metrics.notional_entry) * 100
    metrics.breakeven_price = calculate_breakeven_price(
        entry_price, direction, leverage, total_fees_pct
    )

    if direction == "long":
        metrics.distance_to_breakeven_pct = ((current_price - metrics.breakeven_price) / metrics.breakeven_price) * 100
    else:
        metrics.distance_to_breakeven_pct = ((metrics.breakeven_price - current_price) / metrics.breakeven_price) * 100

    # === PRICE HISTORY & TREND ===
    add_price_to_history(symbol, current_price)
    history = get_price_history(symbol)

    if len(history) >= 3:
        prices = [h['price'] for h in history]
        window = min(TREND_WINDOW, len(prices))
        metrics.price_history = prices[-window:]
        metrics.pos_trend_slope, metrics.trend_strength = calculate_trend_slope(prices[-window:])

    # === MARKET TREND ===
    if market_indicators:
        macd = market_indicators.get('macd', 0)
        ema_diff = market_indicators.get('price_vs_ema20', 0)

        if macd > 0.2 and ema_diff > 0:
            metrics.mkt_trend_slope = min(1.0, (macd + ema_diff/10) / 2)
        elif macd < -0.2 and ema_diff < 0:
            metrics.mkt_trend_slope = max(-1.0, (macd + ema_diff/10) / 2)
        else:
            metrics.mkt_trend_slope = macd / 2

    # === TREND ALIGNMENT ===
    if direction == "long":
        metrics.trend_aligned = (metrics.pos_trend_slope > 0)
    else:
        metrics.trend_aligned = (metrics.pos_trend_slope < 0)

    # === TRAILING STEPS INFO ===
    if current_sl_pct is not None:
        metrics.current_sl_pct = current_sl_pct

    if trailing_steps:
        steps = parse_trailing_steps(trailing_steps)
        current_step, next_step = find_current_and_next_step(metrics.gross_pnl_pct, steps)

        if next_step:
            metrics.next_step_trigger = next_step[0]
            metrics.next_step_sl = next_step[1]

    # === SMART RECOMMENDATION ===
    metrics.action, metrics.confidence, metrics.reason = _calculate_smart_action(metrics)

    return metrics


# =============================================================================
# DECISION LOGIC - HOLD vs ACCELERATE
# =============================================================================

def _calculate_smart_action(m: PositionMetrics) -> Tuple[str, float, str]:
    """
    Calcola se suggerire ACCELERATE (anticipa prossimo step) o HOLD.

    IMPORTANTE: Non suggerisce MAI di chiudere la posizione.
    Il trailing stop esistente gestisce le chiusure.

    Returns:
        (action, confidence, reason)
    """
    net = m.net_pnl_pct
    gross = m.gross_pnl_pct
    aligned = m.trend_aligned
    trend = m.pos_trend_slope
    strength = m.trend_strength

    # Se non c'è prossimo step, non possiamo accelerare
    if m.next_step_trigger == 0:
        return "HOLD", 50, "Nessun prossimo step disponibile"

    # Quanto manca al prossimo step?
    distance_to_next = m.next_step_trigger - gross

    # Quanto guadagneremmo di protezione accelerando?
    sl_improvement = m.next_step_sl - m.current_sl_pct

    # === REGOLA CRITICA: MAI ABBASSARE UN PROFIT LOCK ===
    # Se current_sl è positivo (profit lock), ACCELERATE solo se next_step_sl è MIGLIORE
    # Esempio: current_sl = +0.27%, next_step_sl = -2% → sl_improvement = -2.27 → NO ACCELERATE!
    if sl_improvement <= 0:
        # Il prossimo step peggiorerebbe lo SL - non accelerare MAI
        if m.current_sl_pct > 0:
            return "HOLD", 90, f"Profit lock attivo ({m.current_sl_pct:+.1f}%), prossimo step peggiorerebbe SL"
        # Anche se SL è negativo, non peggiorare
        return "HOLD", 60, f"Prossimo step non migliora SL ({m.current_sl_pct:+.1f}% → {m.next_step_sl:+.1f}%)"

    # === REGOLE DI DECISIONE (solo se sl_improvement > 0) ===

    # 1. Siamo in profitto E il trend è chiaramente contrario
    if net > MIN_PROFIT_FOR_ACCELERATE and not aligned and strength > 0.4:
        # Trend sta girando forte
        if abs(trend) > 0.5:
            return "ACCELERATE", 85, f"Trend invertito (slope={trend:.2f}), anticipa step per proteggere +{net:.1f}%"
        else:
            return "ACCELERATE", 70, f"Trend in inversione, proteggi profitto +{net:.1f}%"

    # 2. Siamo vicini al prossimo step MA trend gira
    if distance_to_next < 0.5 and not aligned:
        return "ACCELERATE", 75, f"Vicino a step (manca {distance_to_next:.1f}%) ma trend gira, anticipa"

    # 3. Abbiamo buon profitto (>2%) e trend neutro/debole
    if net > 2.0 and strength < 0.3:
        return "ACCELERATE", 65, f"Profitto {net:.1f}% con trend debole, meglio proteggere"

    # 4. Trend fortemente contrario anche con profitto basso
    if not aligned and abs(trend) > 0.7 and strength > 0.5:
        if net > 0:
            return "ACCELERATE", 80, f"Trend fortemente contrario (slope={trend:.2f}), proteggi ora"

    # 5. Tutto ok, trend allineato - lascia correre
    if aligned and strength > 0.3:
        return "HOLD", 70, f"Trend allineato (slope={trend:.2f}), lascia correre"

    # Default: HOLD
    return "HOLD", 50, "Situazione normale, step esistenti sufficienti"


# =============================================================================
# AI PROMPT FOR DECISION (optional)
# =============================================================================

def get_ai_decision_prompt(metrics: PositionMetrics) -> str:
    """
    Genera il prompt per far decidere all'AI se ACCELERARE.

    Returns:
        Prompt string per l'AI
    """
    return f"""You are analyzing a trading position that already has trailing stop protection.
Your job is NOT to close the position, but to decide if we should ACCELERATE
the trailing stop to the next step to lock more profit.

POSITION DATA:
- Symbol: {metrics.symbol}
- Direction: {metrics.direction.upper()}
- Entry: ${metrics.entry_price:.2f}
- Current: ${metrics.current_price:.2f}
- Leverage: {metrics.leverage}x

P&L ANALYSIS:
- Gross P&L: {metrics.gross_pnl_pct:+.2f}%
- Net P&L (after fees): {metrics.net_pnl_pct:+.2f}% (${metrics.net_pnl_usd:+.2f})
- Total Fees: ${metrics.fee_open_usd + metrics.fee_close_usd:.2f}
- Breakeven price: ${metrics.breakeven_price:.2f}

CURRENT TRAILING STOP:
- Current SL level: {metrics.current_sl_pct:+.1f}%
- Next step triggers at: {metrics.next_step_trigger:+.1f}% P&L
- Next step would set SL to: {metrics.next_step_sl:+.1f}%

TREND ANALYSIS (based on last {len(metrics.price_history)} prices):
- Position trend slope: {metrics.pos_trend_slope:+.2f} (range: -1 to +1)
- Trend strength (R²): {metrics.trend_strength:.2f}
- Trend aligned with position: {"YES" if metrics.trend_aligned else "NO"}

TIME IN POSITION: {metrics.time_in_position_sec} seconds

DECISION OPTIONS:
1. HOLD - Keep current SL, let the normal trailing steps work
2. ACCELERATE - Move SL to next step level NOW (before reaching trigger)

Respond in JSON only:
{{
  "decision": "HOLD" or "ACCELERATE",
  "confidence": 0-100,
  "reason": "brief explanation (max 50 words)"
}}

GUIDELINES:
- ACCELERATE only when trend is clearly reversing against the position
- If trend is aligned and strong, always HOLD to capture more profit
- When in doubt, prefer HOLD (let the normal trailing work)
- ACCELERATE is about locking profit early, not cutting losses (SL handles that)
"""


# =============================================================================
# PUBLIC API
# =============================================================================

def get_smart_exit_recommendation(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    position_size: float,
    leverage: float,
    entry_time: float,
    current_sl_pct: float = None,
    trailing_steps: str = None,
    market_indicators: dict = None,
    funding_rate: float = 0.0
) -> dict:
    """
    API principale per ottenere raccomandazione smart exit.

    Args:
        symbol: Simbolo (BTC, ETH, SOL)
        direction: 'long' o 'short'
        entry_price: Prezzo di entrata
        current_price: Prezzo corrente
        position_size: Size in coin
        leverage: Leva usata
        entry_time: Timestamp apertura
        current_sl_pct: SL attuale (% P&L)
        trailing_steps: Stringa step trailing (es. "0.8:-2.0,1.4:0.3,...")
        market_indicators: Dict con indicatori mercato
        funding_rate: Funding rate in %

    Returns:
        dict con action, confidence, reason e metriche dettagliate
    """
    if not SMART_EXIT_ENABLED:
        return {
            "enabled": False,
            "action": "HOLD",
            "confidence": 0,
            "reason": "Smart Exit disabilitato"
        }

    metrics = calculate_position_metrics(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        position_size=position_size,
        leverage=leverage,
        entry_time=entry_time,
        current_sl_pct=current_sl_pct,
        trailing_steps=trailing_steps,
        market_indicators=market_indicators,
        funding_rate=funding_rate
    )

    result = {
        "enabled": True,
        "action": metrics.action,
        "confidence": metrics.confidence,
        "reason": metrics.reason,
        "should_accelerate": metrics.action == "ACCELERATE" and metrics.confidence >= ACCELERATE_CONFIDENCE_THRESHOLD,
        "next_step_sl": metrics.next_step_sl if metrics.action == "ACCELERATE" else None,
        "metrics": {
            "gross_pnl_pct": round(metrics.gross_pnl_pct, 2),
            "net_pnl_pct": round(metrics.net_pnl_pct, 2),
            "net_pnl_usd": round(metrics.net_pnl_usd, 2),
            "fees_total_usd": round(metrics.fee_open_usd + metrics.fee_close_usd + abs(metrics.funding_paid_usd), 2),
            "breakeven_price": round(metrics.breakeven_price, 2),
            "current_sl_pct": round(metrics.current_sl_pct, 2),
            "next_step_trigger": round(metrics.next_step_trigger, 2),
            "next_step_sl": round(metrics.next_step_sl, 2),
            "pos_trend_slope": round(metrics.pos_trend_slope, 3),
            "trend_strength": round(metrics.trend_strength, 2),
            "trend_aligned": metrics.trend_aligned,
            "time_in_position_sec": metrics.time_in_position_sec,
            "price_history_size": len(metrics.price_history)
        }
    }

    # Se AI enabled e decisione incerta, genera prompt
    if SMART_EXIT_AI_ENABLED and 40 < metrics.confidence < 80:
        result["ai_prompt"] = get_ai_decision_prompt(metrics)

    return result


def format_smart_exit_log(recommendation: dict, symbol: str, verbose: bool = True) -> str:
    """
    Formatta il log per la raccomandazione smart exit.

    Args:
        recommendation: Dict con metriche e raccomandazione
        symbol: Simbolo
        verbose: Se True, mostra tutti i calcoli dettagliati
    """
    if not recommendation.get("enabled"):
        return ""

    m = recommendation.get("metrics", {})
    action = recommendation.get("action", "HOLD")
    confidence = recommendation.get("confidence", 0)
    reason = recommendation.get("reason", "")
    should_accelerate = recommendation.get("should_accelerate", False)

    # Emoji per action
    if should_accelerate:
        action_emoji = "⚡"  # Accelerate attivo
    elif action == "ACCELERATE":
        action_emoji = "🔶"  # Accelerate suggerito ma sotto soglia
    else:
        action_emoji = "✅"  # Hold

    # Colore per net P&L
    net_pnl = m.get("net_pnl_pct", 0)
    gross_pnl = m.get("gross_pnl_pct", 0)
    pnl_indicator = "🟢" if net_pnl > 0.5 else "🟡" if net_pnl > 0 else "🔴"

    trend_indicator = "📈" if m.get("trend_aligned") else "📉"

    log_lines = [
        f"   [SMART] {symbol}: {action_emoji} {action} ({confidence}%)",
    ]

    if verbose:
        # Linea 1: P&L dettagliato
        fees = m.get("fees_total_usd", 0)
        net_usd = m.get("net_pnl_usd", 0)
        log_lines.append(
            f"           {pnl_indicator} P&L: Gross {gross_pnl:+.2f}% → Net {net_pnl:+.2f}% (${net_usd:+.2f}) | Fees: ${fees:.2f}"
        )

        # Linea 2: Breakeven e tempo
        be_price = m.get("breakeven_price", 0)
        time_sec = m.get("time_in_position_sec", 0)
        time_min = time_sec // 60
        time_sec_rem = time_sec % 60
        log_lines.append(
            f"           💰 Breakeven: ${be_price:.2f} | ⏱️ In posizione: {time_min}m {time_sec_rem}s"
        )

        # Linea 3: Trend analysis
        slope = m.get("pos_trend_slope", 0)
        strength = m.get("trend_strength", 0)
        history_size = m.get("price_history_size", 0)
        aligned = "ALIGNED" if m.get("trend_aligned") else "AGAINST"
        log_lines.append(
            f"           {trend_indicator} Trend: slope={slope:+.3f} R²={strength:.2f} ({history_size} samples) [{aligned}]"
        )

        # Linea 4: Step info
        current_sl = m.get("current_sl_pct", 0)
        next_trigger = m.get("next_step_trigger", 0)
        next_sl = m.get("next_step_sl", 0)
        if next_trigger > 0:
            log_lines.append(
                f"           📊 SL attuale: {current_sl:+.1f}% | Prossimo step: @{next_trigger}% → SL {next_sl:+.1f}%"
            )
    else:
        # Versione compatta
        step_info = ""
        if m.get("next_step_trigger", 0) > 0:
            step_info = f" | Next@{m.get('next_step_trigger')}%→SL {m.get('next_step_sl')}%"
        log_lines.append(
            f"           {pnl_indicator} Net: {net_pnl:+.2f}% | Gross: {gross_pnl:+.2f}% | Fees: ${m.get('fees_total_usd', 0):.2f}"
        )
        log_lines.append(
            f"           {trend_indicator} Trend: {m.get('pos_trend_slope', 0):+.2f} (R²={m.get('trend_strength', 0):.2f}){step_info}"
        )

    # Azione ACCELERATE
    if should_accelerate:
        log_lines.append(f"           ⚡ ESEGUO ACCELERATE → SL da {m.get('current_sl_pct', 0):+.1f}% a {recommendation.get('next_step_sl')}%")

    # Reason
    log_lines.append(f"           💡 {reason}")

    return "\n".join(log_lines)
