"""
Smart Exit Optimizer - Massimizza profitti considerando fees e trend.

Questo modulo calcola:
1. P&L netto reale (incluse fees apertura, chiusura, funding)
2. Trend della posizione vs trend di mercato
3. Raccomandazione smart per exit ottimale
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import deque
from decimal import Decimal
import numpy as np

# Fee structure Hyperliquid
TAKER_FEE_RATE = 0.00035  # 0.035% per side
MAKER_FEE_RATE = 0.0001   # 0.01% per side

# Price history settings
PRICE_HISTORY_SIZE = int(os.getenv('SMART_EXIT_HISTORY_SIZE', '20'))  # Ultimi 20 prezzi
TREND_WINDOW = int(os.getenv('SMART_EXIT_TREND_WINDOW', '10'))  # Finestra per calcolo trend

# Smart exit thresholds (configurabili)
SMART_EXIT_ENABLED = os.getenv('SMART_EXIT_ENABLED', 'false').lower() == 'true'
MIN_PROFIT_TO_EXIT = float(os.getenv('SMART_EXIT_MIN_PROFIT', '0.3'))  # % minimo netto per uscita anticipata
TREND_MISALIGN_EXIT = float(os.getenv('SMART_EXIT_TREND_MISALIGN', '-0.5'))  # Soglia disallineamento per exit


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
    trend_strength: float = 0.0      # Forza del trend (0-1)

    # Break-even analysis
    breakeven_price: float = 0.0     # Prezzo per uscire a zero dopo fees
    distance_to_breakeven_pct: float = 0.0  # % dal breakeven

    # Time analysis
    time_in_position_sec: int = 0    # Secondi in posizione

    # Smart recommendation
    action: str = "HOLD"             # "HOLD", "TAKE_PROFIT", "CUT_LOSS", "TRAIL_TIGHT", "TRAIL_WIDE"
    confidence: float = 0.0          # 0-100%
    reason: str = ""                 # Spiegazione


# Storage per price history per simbolo (persiste tra cicli FAST)
_price_histories: Dict[str, deque] = {}


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


def calculate_trend_slope(prices: List[float]) -> Tuple[float, float]:
    """
    Calcola la pendenza del trend usando regressione lineare.

    Returns:
        (slope, r_squared): slope normalizzato (-1 to +1), forza del trend (0-1)
    """
    if len(prices) < 3:
        return 0.0, 0.0

    try:
        # Normalizza i prezzi per evitare problemi numerici
        prices_arr = np.array(prices)
        mean_price = np.mean(prices_arr)
        if mean_price == 0:
            return 0.0, 0.0

        # Regressione lineare semplice
        x = np.arange(len(prices_arr))

        # Calcola slope
        x_mean = np.mean(x)
        y_mean = np.mean(prices_arr)

        numerator = np.sum((x - x_mean) * (prices_arr - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return 0.0, 0.0

        slope = numerator / denominator

        # Normalizza slope in percentuale per periodo
        slope_pct = (slope / mean_price) * 100  # % change per step

        # Calcola R-squared per la forza del trend
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = np.sum((prices_arr - y_pred) ** 2)
        ss_tot = np.sum((prices_arr - y_mean) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        r_squared = max(0, min(1, r_squared))  # Clamp 0-1

        # Normalizza slope a range -1 to +1 (assumendo max 0.5% per step)
        normalized_slope = max(-1, min(1, slope_pct / 0.5))

        return normalized_slope, r_squared

    except Exception:
        return 0.0, 0.0


def calculate_fees(notional: float, is_taker: bool = True) -> float:
    """Calcola le fees per un lato del trade."""
    rate = TAKER_FEE_RATE if is_taker else MAKER_FEE_RATE
    return notional * rate


def calculate_breakeven_price(entry_price: float, direction: str,
                               leverage: float, total_fees_pct: float) -> float:
    """
    Calcola il prezzo di breakeven considerando le fees.

    total_fees_pct: fees totali come % del notional (es. 0.07 per 0.07%)
    """
    # Fee come % del movimento prezzo necessario
    fee_price_impact = total_fees_pct / leverage

    if direction == "long":
        # Long: prezzo deve salire abbastanza da coprire fees
        return entry_price * (1 + fee_price_impact / 100)
    else:
        # Short: prezzo deve scendere abbastanza da coprire fees
        return entry_price * (1 - fee_price_impact / 100)


def calculate_position_metrics(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    position_size: float,
    leverage: float,
    entry_time: float,
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
        market_indicators: Dict con EMA, MACD, etc. dal mercato
        funding_rate: Funding rate corrente (% per 8h)

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

    # Funding ogni 8h, proporzionale al tempo
    if funding_rate != 0:
        funding_periods = hours_held / 8
        # Funding positivo = long paga, negativo = short paga
        if direction == "long":
            metrics.funding_paid_usd = metrics.notional_current * (funding_rate / 100) * funding_periods
        else:
            metrics.funding_paid_usd = -metrics.notional_current * (funding_rate / 100) * funding_periods

    # === NET P&L ===
    total_fees_usd = metrics.fee_open_usd + metrics.fee_close_usd + abs(metrics.funding_paid_usd)
    metrics.net_pnl_usd = metrics.gross_pnl_usd - total_fees_usd

    # Net P&L come percentuale del margin
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
        metrics.price_history = prices[-TREND_WINDOW:]
        metrics.pos_trend_slope, metrics.trend_strength = calculate_trend_slope(prices[-TREND_WINDOW:])

    # === MARKET TREND (se disponibile) ===
    if market_indicators:
        # Usa MACD come proxy per trend di mercato
        macd = market_indicators.get('macd', 0)
        ema_diff = market_indicators.get('price_vs_ema20', 0)  # % sopra/sotto EMA20

        # Combina MACD e EMA per trend score
        if macd > 0.2 and ema_diff > 0:
            metrics.mkt_trend_slope = min(1.0, (macd + ema_diff/10) / 2)
        elif macd < -0.2 and ema_diff < 0:
            metrics.mkt_trend_slope = max(-1.0, (macd + ema_diff/10) / 2)
        else:
            metrics.mkt_trend_slope = macd / 2  # Trend debole

    # === TREND ALIGNMENT ===
    # Allineato se entrambi positivi o entrambi negativi
    if direction == "long":
        # Long vuole trend positivo
        metrics.trend_aligned = (metrics.pos_trend_slope > 0 and metrics.mkt_trend_slope > 0)
    else:
        # Short vuole trend negativo
        metrics.trend_aligned = (metrics.pos_trend_slope < 0 and metrics.mkt_trend_slope < 0)

    # === SMART RECOMMENDATION ===
    metrics.action, metrics.confidence, metrics.reason = _calculate_smart_action(metrics)

    return metrics


def _calculate_smart_action(m: PositionMetrics) -> Tuple[str, float, str]:
    """
    Calcola l'azione raccomandata basata sulle metriche.

    Returns:
        (action, confidence, reason)
    """
    net = m.net_pnl_pct
    aligned = m.trend_aligned
    trend = m.pos_trend_slope
    strength = m.trend_strength
    time_sec = m.time_in_position_sec

    # === REGOLE DI DECISIONE ===

    # 1. LOSS SIGNIFICATIVA - esci
    if net < -3.0:
        return "CUT_LOSS", 90, f"Perdita netta {net:.1f}% supera soglia"

    # 2. LOSS MODERATA + TREND CONTRARIO - esci presto
    if net < -1.0 and not aligned and strength > 0.5:
        return "CUT_LOSS", 75, f"Perdita {net:.1f}% con trend contrario (slope={trend:.2f})"

    # 3. LOSS LEGGERA + TREND A FAVORE - aspetta
    if -1.0 <= net < 0 and aligned:
        return "HOLD", 60, f"In perdita {net:.1f}% ma trend allineato, attendo recupero"

    # 4. LOSS LEGGERA + TREND CONTRARIO - esci
    if -1.0 <= net < 0 and not aligned and time_sec > 120:
        return "CUT_LOSS", 65, f"Perdita {net:.1f}% con trend contrario dopo {time_sec}s"

    # 5. BREAKEVEN ZONE - decisione basata su trend
    if 0 <= net < 0.5:
        if aligned and strength > 0.3:
            return "HOLD", 55, f"Zona breakeven ma trend favorevole (slope={trend:.2f})"
        elif not aligned:
            return "TAKE_PROFIT", 60, f"Zona breakeven con trend contrario, prendi {net:.1f}%"
        else:
            return "HOLD", 50, "Zona breakeven, trend neutro"

    # 6. PICCOLO PROFITTO (0.5-1.5%) - valuta trend
    if 0.5 <= net < 1.5:
        if not aligned and strength > 0.4:
            return "TAKE_PROFIT", 70, f"Profitto {net:.1f}% con trend contrario, esci"
        elif aligned and strength > 0.5:
            return "TRAIL_TIGHT", 65, f"Profitto {net:.1f}% con trend favorevole, trailing stretto"
        else:
            return "HOLD", 55, f"Profitto {net:.1f}%, trend neutro"

    # 7. BUON PROFITTO (1.5-3%) - proteggi
    if 1.5 <= net < 3.0:
        if aligned and strength > 0.6:
            return "TRAIL_WIDE", 75, f"Profitto {net:.1f}% con trend forte, lascia correre"
        elif not aligned:
            return "TAKE_PROFIT", 80, f"Profitto {net:.1f}% ma trend gira, prendi profitto"
        else:
            return "TRAIL_TIGHT", 70, f"Profitto {net:.1f}%, trailing per proteggere"

    # 8. OTTIMO PROFITTO (>3%) - quasi sempre proteggi
    if net >= 3.0:
        if aligned and strength > 0.7:
            return "TRAIL_WIDE", 80, f"Ottimo profitto {net:.1f}% con trend forte"
        else:
            return "TAKE_PROFIT", 85, f"Ottimo profitto {net:.1f}%, prendi e ringrazia"

    # Default
    return "HOLD", 50, "Situazione standard"


def get_smart_exit_recommendation(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    position_size: float,
    leverage: float,
    entry_time: float,
    market_indicators: dict = None,
    funding_rate: float = 0.0
) -> dict:
    """
    API principale per ottenere raccomandazione smart exit.

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
        market_indicators=market_indicators,
        funding_rate=funding_rate
    )

    return {
        "enabled": True,
        "action": metrics.action,
        "confidence": metrics.confidence,
        "reason": metrics.reason,
        "metrics": {
            "gross_pnl_pct": round(metrics.gross_pnl_pct, 2),
            "net_pnl_pct": round(metrics.net_pnl_pct, 2),
            "net_pnl_usd": round(metrics.net_pnl_usd, 2),
            "fees_total_usd": round(metrics.fee_open_usd + metrics.fee_close_usd + abs(metrics.funding_paid_usd), 2),
            "breakeven_price": round(metrics.breakeven_price, 2),
            "distance_to_breakeven_pct": round(metrics.distance_to_breakeven_pct, 2),
            "pos_trend_slope": round(metrics.pos_trend_slope, 3),
            "mkt_trend_slope": round(metrics.mkt_trend_slope, 3),
            "trend_aligned": metrics.trend_aligned,
            "trend_strength": round(metrics.trend_strength, 2),
            "time_in_position_sec": metrics.time_in_position_sec
        }
    }


def format_smart_exit_log(recommendation: dict, symbol: str) -> str:
    """Formatta il log per la raccomandazione smart exit."""
    if not recommendation.get("enabled"):
        return ""

    m = recommendation.get("metrics", {})
    action = recommendation.get("action", "HOLD")
    confidence = recommendation.get("confidence", 0)
    reason = recommendation.get("reason", "")

    # Emoji per action
    action_emoji = {
        "HOLD": "⏸️",
        "TAKE_PROFIT": "💰",
        "CUT_LOSS": "🛑",
        "TRAIL_TIGHT": "🎯",
        "TRAIL_WIDE": "🚀"
    }.get(action, "❓")

    # Colore per net P&L
    net_pnl = m.get("net_pnl_pct", 0)
    pnl_indicator = "🟢" if net_pnl > 0.5 else "🟡" if net_pnl > 0 else "🔴"

    trend_indicator = "✅" if m.get("trend_aligned") else "⚠️"

    return (
        f"   [SMART] {symbol}: {action_emoji} {action} ({confidence}%)\n"
        f"           {pnl_indicator} Net P&L: {net_pnl:+.2f}% (${m.get('net_pnl_usd', 0):+.2f})\n"
        f"           💸 Fees: ${m.get('fees_total_usd', 0):.2f} | BE: ${m.get('breakeven_price', 0):.2f}\n"
        f"           {trend_indicator} Trend: pos={m.get('pos_trend_slope', 0):+.2f} mkt={m.get('mkt_trend_slope', 0):+.2f}\n"
        f"           💡 {reason}"
    )
