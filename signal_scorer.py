"""
Signal Scorer Module
====================
Calcola score BULLISH e BEARISH basati su indicatori tecnici e sentiment.
I pesi sono configurabili via .env per permettere tuning senza modificare il codice.

Ogni segnale contribuisce allo score in base a:
1. Il peso configurato (0-20)
2. L'intensità del segnale (quanto è estremo il valore)

Output: score_bullish, score_bearish, net_score, direction_suggestion
"""

import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


def get_weight(env_var: str, default: float) -> float:
    """Legge un peso dal file .env con fallback al default."""
    try:
        return float(os.getenv(env_var, default))
    except (ValueError, TypeError):
        return default


# ============================================
# CONFIGURAZIONE PESI (da .env)
# ============================================

# Segnali BEARISH (favoriscono SHORT)
WEIGHT_FEAR_GREED_FEAR = get_weight('WEIGHT_FEAR_GREED_FEAR', 8.0)
WEIGHT_RSI_OVERBOUGHT = get_weight('WEIGHT_RSI_OVERBOUGHT', 15.0)
WEIGHT_TREND_BEARISH = get_weight('WEIGHT_TREND_BEARISH', 10.0)
WEIGHT_FORECAST_NEGATIVE = get_weight('WEIGHT_FORECAST_NEGATIVE', 6.0)
WEIGHT_MACD_NEGATIVE = get_weight('WEIGHT_MACD_NEGATIVE', 5.0)
WEIGHT_VOLUME_BEARISH = get_weight('WEIGHT_VOLUME_BEARISH', 4.0)

# Segnali BULLISH (favoriscono LONG)
WEIGHT_FEAR_GREED_GREED = get_weight('WEIGHT_FEAR_GREED_GREED', 8.0)
WEIGHT_RSI_OVERSOLD = get_weight('WEIGHT_RSI_OVERSOLD', 15.0)
WEIGHT_TREND_BULLISH = get_weight('WEIGHT_TREND_BULLISH', 10.0)
WEIGHT_FORECAST_POSITIVE = get_weight('WEIGHT_FORECAST_POSITIVE', 6.0)
WEIGHT_MACD_POSITIVE = get_weight('WEIGHT_MACD_POSITIVE', 5.0)
WEIGHT_VOLUME_BULLISH = get_weight('WEIGHT_VOLUME_BULLISH', 4.0)

# Soglie decisionali
SCORE_THRESHOLD_OPEN = get_weight('SCORE_THRESHOLD_OPEN', 15.0)
SCORE_THRESHOLD_STRONG = get_weight('SCORE_THRESHOLD_STRONG', 25.0)
SCORE_THRESHOLD_HOLD = get_weight('SCORE_THRESHOLD_HOLD', 10.0)

# Soglie indicatori
RSI_OVERBOUGHT_THRESHOLD = get_weight('RSI_OVERBOUGHT_THRESHOLD', 70.0)
RSI_OVERSOLD_THRESHOLD = get_weight('RSI_OVERSOLD_THRESHOLD', 30.0)
FEAR_GREED_FEAR_THRESHOLD = get_weight('FEAR_GREED_FEAR_THRESHOLD', 30.0)
FEAR_GREED_GREED_THRESHOLD = get_weight('FEAR_GREED_GREED_THRESHOLD', 60.0)
FORECAST_MIN_CHANGE_PCT = get_weight('FORECAST_MIN_CHANGE_PCT', 0.3)

# Volume Smoothing (Opzione D - riduce rumore)
VOLUME_SMOOTHING_CYCLES = int(get_weight('VOLUME_SMOOTHING_CYCLES', 3))  # Media ultimi N cicli
VOLUME_RATIO_BULLISH_THRESHOLD = get_weight('VOLUME_RATIO_BULLISH_THRESHOLD', 1.5)  # Bid/Ask > 1.5
VOLUME_RATIO_BEARISH_THRESHOLD = get_weight('VOLUME_RATIO_BEARISH_THRESHOLD', 0.67)  # Bid/Ask < 0.67

# History per volume smoothing (per simbolo)
_volume_ratio_history = {}


def calculate_signal_score(
    price: float,
    ema20: float,
    rsi: float,
    macd: float,
    fear_greed: int,
    forecast_change_pct: float,
    volume_bid: float = 0,
    volume_ask: float = 0,
    symbol: str = "UNKNOWN"
) -> dict:
    """
    Calcola lo score dei segnali per una singola coin.

    Args:
        price: Prezzo attuale
        ema20: EMA a 20 periodi
        rsi: RSI (7 o 14 periodi)
        macd: Valore MACD
        fear_greed: Fear & Greed Index (0-100)
        forecast_change_pct: Previsione cambio % da Prophet
        volume_bid: Volume bid
        volume_ask: Volume ask
        symbol: Simbolo (per volume smoothing history)

    Returns:
        dict con score_bullish, score_bearish, net_score, signals, direction
    """
    global _volume_ratio_history

    score_bullish = 0.0
    score_bearish = 0.0
    signals = []

    # ============================================
    # 1. FEAR & GREED INDEX
    # ============================================
    if fear_greed < FEAR_GREED_FEAR_THRESHOLD:
        # Mercato in paura → Bearish signal
        intensity = (FEAR_GREED_FEAR_THRESHOLD - fear_greed) / FEAR_GREED_FEAR_THRESHOLD
        contribution = WEIGHT_FEAR_GREED_FEAR * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'BEARISH',
            'weight': WEIGHT_FEAR_GREED_FEAR,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'F&G={fear_greed} < {FEAR_GREED_FEAR_THRESHOLD} (Fear)'
        })
    elif fear_greed > FEAR_GREED_GREED_THRESHOLD:
        # Mercato euforico → Bullish signal (ma attenzione a extreme greed)
        intensity = (fear_greed - FEAR_GREED_GREED_THRESHOLD) / (100 - FEAR_GREED_GREED_THRESHOLD)
        contribution = WEIGHT_FEAR_GREED_GREED * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'BULLISH',
            'weight': WEIGHT_FEAR_GREED_GREED,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'F&G={fear_greed} > {FEAR_GREED_GREED_THRESHOLD} (Greed)'
        })
    else:
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'F&G={fear_greed} (Neutral zone)'
        })

    # ============================================
    # 2. RSI (Relative Strength Index)
    # ============================================
    if rsi > RSI_OVERBOUGHT_THRESHOLD:
        # Overbought → Bearish (probabile correzione)
        intensity = min((rsi - RSI_OVERBOUGHT_THRESHOLD) / (100 - RSI_OVERBOUGHT_THRESHOLD), 1.0)
        contribution = WEIGHT_RSI_OVERBOUGHT * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'RSI',
            'value': round(rsi, 2),
            'direction': 'BEARISH',
            'weight': WEIGHT_RSI_OVERBOUGHT,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'RSI={rsi:.1f} > {RSI_OVERBOUGHT_THRESHOLD} (Overbought)'
        })
    elif rsi < RSI_OVERSOLD_THRESHOLD:
        # Oversold → Bullish (probabile rimbalzo)
        intensity = min((RSI_OVERSOLD_THRESHOLD - rsi) / RSI_OVERSOLD_THRESHOLD, 1.0)
        contribution = WEIGHT_RSI_OVERSOLD * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'RSI',
            'value': round(rsi, 2),
            'direction': 'BULLISH',
            'weight': WEIGHT_RSI_OVERSOLD,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'RSI={rsi:.1f} < {RSI_OVERSOLD_THRESHOLD} (Oversold)'
        })
    else:
        signals.append({
            'indicator': 'RSI',
            'value': round(rsi, 2),
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'RSI={rsi:.1f} (Neutral zone)'
        })

    # ============================================
    # 3. TREND (Price vs EMA20 + MACD)
    # ============================================
    price_above_ema = price > ema20
    macd_positive = macd > 0

    if not price_above_ema and not macd_positive:
        # Prezzo sotto EMA20 E MACD negativo → Forte segnale bearish
        contribution = WEIGHT_TREND_BEARISH
        score_bearish += contribution
        signals.append({
            'indicator': 'Trend (EMA+MACD)',
            'value': f'Price={price:.2f}, EMA20={ema20:.2f}, MACD={macd:.4f}',
            'direction': 'BEARISH',
            'weight': WEIGHT_TREND_BEARISH,
            'intensity': 1.0,
            'contribution': contribution,
            'reason': f'Price < EMA20 AND MACD < 0 (Downtrend)'
        })
    elif price_above_ema and macd_positive:
        # Prezzo sopra EMA20 E MACD positivo → Forte segnale bullish
        contribution = WEIGHT_TREND_BULLISH
        score_bullish += contribution
        signals.append({
            'indicator': 'Trend (EMA+MACD)',
            'value': f'Price={price:.2f}, EMA20={ema20:.2f}, MACD={macd:.4f}',
            'direction': 'BULLISH',
            'weight': WEIGHT_TREND_BULLISH,
            'intensity': 1.0,
            'contribution': contribution,
            'reason': f'Price > EMA20 AND MACD > 0 (Uptrend)'
        })
    else:
        # Segnali misti → contributo parziale dal MACD
        if macd > 0:
            contribution = WEIGHT_MACD_POSITIVE * 0.5
            score_bullish += contribution
            signals.append({
                'indicator': 'MACD',
                'value': round(macd, 4),
                'direction': 'BULLISH',
                'weight': WEIGHT_MACD_POSITIVE,
                'intensity': 0.5,
                'contribution': round(contribution, 2),
                'reason': f'MACD={macd:.4f} > 0 (Bullish momentum)'
            })
        elif macd < 0:
            contribution = WEIGHT_MACD_NEGATIVE * 0.5
            score_bearish += contribution
            signals.append({
                'indicator': 'MACD',
                'value': round(macd, 4),
                'direction': 'BEARISH',
                'weight': WEIGHT_MACD_NEGATIVE,
                'intensity': 0.5,
                'contribution': round(contribution, 2),
                'reason': f'MACD={macd:.4f} < 0 (Bearish momentum)'
            })

    # ============================================
    # 4. FORECAST (Prophet Prediction)
    # ============================================
    if forecast_change_pct < -FORECAST_MIN_CHANGE_PCT:
        # Previsione ribasso
        intensity = min(abs(forecast_change_pct) / 2.0, 1.0)  # Max intensity at -2%
        contribution = WEIGHT_FORECAST_NEGATIVE * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'BEARISH',
            'weight': WEIGHT_FORECAST_NEGATIVE,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Bearish)'
        })
    elif forecast_change_pct > FORECAST_MIN_CHANGE_PCT:
        # Previsione rialzo
        intensity = min(abs(forecast_change_pct) / 2.0, 1.0)
        contribution = WEIGHT_FORECAST_POSITIVE * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'BULLISH',
            'weight': WEIGHT_FORECAST_POSITIVE,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Bullish)'
        })
    else:
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Too small)'
        })

    # ============================================
    # 5. VOLUME (Bid vs Ask) - CON SMOOTHING
    # ============================================
    # Opzione D: Media mobile del ratio per ridurre rumore
    if volume_bid > 0 and volume_ask > 0:
        current_ratio = volume_bid / volume_ask

        # Inizializza history per questo simbolo se non esiste
        if symbol not in _volume_ratio_history:
            _volume_ratio_history[symbol] = []

        # Aggiungi ratio corrente alla history
        _volume_ratio_history[symbol].append(current_ratio)

        # Mantieni solo gli ultimi N cicli
        if len(_volume_ratio_history[symbol]) > VOLUME_SMOOTHING_CYCLES:
            _volume_ratio_history[symbol] = _volume_ratio_history[symbol][-VOLUME_SMOOTHING_CYCLES:]

        # Calcola la MEDIA del ratio (smoothed)
        avg_ratio = sum(_volume_ratio_history[symbol]) / len(_volume_ratio_history[symbol])

        # Usa la media smoothed per le decisioni
        if avg_ratio > VOLUME_RATIO_BULLISH_THRESHOLD:
            # Più compratori che venditori (media confermata) → Bullish
            intensity = min((avg_ratio - 1) / 2, 1.0)
            contribution = WEIGHT_VOLUME_BULLISH * intensity
            score_bullish += contribution
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f} (smooth {len(_volume_ratio_history[symbol])} cycles)',
                'direction': 'BULLISH',
                'weight': WEIGHT_VOLUME_BULLISH,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Volume Avg Ratio={avg_ratio:.2f} > {VOLUME_RATIO_BULLISH_THRESHOLD} (Buyers dominant)'
            })
        elif avg_ratio < VOLUME_RATIO_BEARISH_THRESHOLD:
            # Più venditori che compratori (media confermata) → Bearish
            intensity = min((1 - avg_ratio) / 0.5, 1.0)
            contribution = WEIGHT_VOLUME_BEARISH * intensity
            score_bearish += contribution
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f} (smooth {len(_volume_ratio_history[symbol])} cycles)',
                'direction': 'BEARISH',
                'weight': WEIGHT_VOLUME_BEARISH,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Volume Avg Ratio={avg_ratio:.2f} < {VOLUME_RATIO_BEARISH_THRESHOLD} (Sellers dominant)'
            })
        else:
            # Zona neutra - il volume non contribuisce (rumore filtrato)
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f} (smooth {len(_volume_ratio_history[symbol])} cycles)',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'Volume Avg Ratio={avg_ratio:.2f} in neutral zone (noise filtered)'
            })

    # ============================================
    # CALCOLO FINALE
    # ============================================
    net_score = score_bullish - score_bearish

    # Determina direzione suggerita
    if net_score >= SCORE_THRESHOLD_OPEN:
        direction = 'LONG'
        confidence = 'STRONG' if net_score >= SCORE_THRESHOLD_STRONG else 'NORMAL'
    elif net_score <= -SCORE_THRESHOLD_OPEN:
        direction = 'SHORT'
        confidence = 'STRONG' if net_score <= -SCORE_THRESHOLD_STRONG else 'NORMAL'
    else:
        direction = 'HOLD'
        confidence = 'WEAK'

    return {
        'score_bullish': round(score_bullish, 2),
        'score_bearish': round(score_bearish, 2),
        'net_score': round(net_score, 2),
        'direction': direction,
        'confidence': confidence,
        'signals': signals,
        'thresholds': {
            'open': SCORE_THRESHOLD_OPEN,
            'strong': SCORE_THRESHOLD_STRONG,
            'hold': SCORE_THRESHOLD_HOLD
        },
        'timestamp': datetime.utcnow().isoformat()
    }


def format_score_for_prompt(score_result: dict) -> str:
    """
    Formatta il risultato dello scoring per includerlo nel prompt AI.
    """
    lines = [
        "=== SIGNAL SCORING ANALYSIS ===",
        f"Score BULLISH: {score_result['score_bullish']}",
        f"Score BEARISH: {score_result['score_bearish']}",
        f"NET SCORE: {score_result['net_score']}",
        f"Suggested Direction: {score_result['direction']} ({score_result['confidence']})",
        "",
        "Signal Details:"
    ]

    for signal in score_result['signals']:
        if signal['contribution'] > 0:
            lines.append(
                f"  - {signal['indicator']}: {signal['direction']} "
                f"(+{signal['contribution']} points) - {signal['reason']}"
            )

    lines.append("")
    lines.append(f"Thresholds: Open={score_result['thresholds']['open']}, "
                 f"Strong={score_result['thresholds']['strong']}")
    lines.append("================================")

    return "\n".join(lines)


def get_scoring_config() -> dict:
    """
    Restituisce la configurazione attuale dei pesi per logging/debug.
    """
    return {
        'weights_bearish': {
            'fear_greed_fear': WEIGHT_FEAR_GREED_FEAR,
            'rsi_overbought': WEIGHT_RSI_OVERBOUGHT,
            'trend_bearish': WEIGHT_TREND_BEARISH,
            'forecast_negative': WEIGHT_FORECAST_NEGATIVE,
            'macd_negative': WEIGHT_MACD_NEGATIVE,
            'volume_bearish': WEIGHT_VOLUME_BEARISH
        },
        'weights_bullish': {
            'fear_greed_greed': WEIGHT_FEAR_GREED_GREED,
            'rsi_oversold': WEIGHT_RSI_OVERSOLD,
            'trend_bullish': WEIGHT_TREND_BULLISH,
            'forecast_positive': WEIGHT_FORECAST_POSITIVE,
            'macd_positive': WEIGHT_MACD_POSITIVE,
            'volume_bullish': WEIGHT_VOLUME_BULLISH
        },
        'thresholds': {
            'score_open': SCORE_THRESHOLD_OPEN,
            'score_strong': SCORE_THRESHOLD_STRONG,
            'score_hold': SCORE_THRESHOLD_HOLD
        },
        'indicator_thresholds': {
            'rsi_overbought': RSI_OVERBOUGHT_THRESHOLD,
            'rsi_oversold': RSI_OVERSOLD_THRESHOLD,
            'fear_greed_fear': FEAR_GREED_FEAR_THRESHOLD,
            'fear_greed_greed': FEAR_GREED_GREED_THRESHOLD,
            'forecast_min_change': FORECAST_MIN_CHANGE_PCT
        }
    }


# ============================================
# SMART SCORE V2 - Logica Graduale
# ============================================
# Nuovi pesi per indicatori aggiuntivi
WEIGHT_BOLLINGER = get_weight('WEIGHT_BOLLINGER', 8.0)
WEIGHT_OBV_TREND = get_weight('WEIGHT_OBV_TREND', 6.0)
WEIGHT_MACD_HISTOGRAM = get_weight('WEIGHT_MACD_HISTOGRAM', 5.0)
WEIGHT_EMA_ALIGNMENT = get_weight('WEIGHT_EMA_ALIGNMENT', 7.0)
WEIGHT_RSI_MOMENTUM = get_weight('WEIGHT_RSI_MOMENTUM', 6.0)  # RSI in zone momentum

# ADX thresholds
ADX_WEAK_THRESHOLD = get_weight('ADX_WEAK_THRESHOLD', 20.0)  # Below = ranging market
ADX_STRONG_THRESHOLD = get_weight('ADX_STRONG_THRESHOLD', 25.0)  # Above = strong trend

# Bollinger thresholds
BB_SQUEEZE_THRESHOLD = get_weight('BB_SQUEEZE_THRESHOLD', 2.0)  # Bandwidth < 2% = squeeze


def calculate_smart_score_v2(
    price: float,
    ema20: float,
    ema50: float,
    rsi: float,
    macd: float,
    macd_signal: float,
    fear_greed: int,
    forecast_change_pct: float,
    volume_bid: float = 0,
    volume_ask: float = 0,
    symbol: str = "UNKNOWN",
    # Nuovi indicatori
    bollinger: dict = None,  # {'upper', 'lower', 'middle', 'bandwidth', 'percent_b', 'position', 'squeeze'}
    obv_trend: str = None,  # 'RISING', 'FALLING', 'FLAT'
    macd_histogram_trend: str = None,  # 'EXPANDING', 'CONTRACTING', 'FLAT'
    ema_alignment: str = None,  # 'GOLDEN_CROSS', 'DEATH_CROSS', 'NEUTRAL'
    adx: float = None,  # Trend strength (0-100)
) -> dict:
    """
    Smart Score V2 - Logica graduale invece di on/off.

    Miglioramenti:
    1. RSI graduale: zone momentum (55-70 bullish, 30-45 bearish)
    2. Bollinger Bands: position-based scoring
    3. OBV: conferma trend con volume
    4. MACD Histogram: momentum in espansione/contrazione
    5. EMA Alignment: golden/death cross
    6. ADX: filtro mercato ranging (riduce score se ADX < 20)

    Args:
        [... parametri esistenti ...]
        bollinger: Dict con dati Bollinger Bands
        obv_trend: Trend OBV ('RISING', 'FALLING', 'FLAT')
        macd_histogram_trend: Trend histogram MACD
        ema_alignment: Allineamento EMA20/EMA50
        adx: Average Directional Index (trend strength)

    Returns:
        dict con score_bullish, score_bearish, net_score, signals, direction
    """
    global _volume_ratio_history

    score_bullish = 0.0
    score_bearish = 0.0
    signals = []

    # Inizializza bollinger se non fornito
    if bollinger is None:
        bollinger = {}

    # ============================================
    # 1. RSI - LOGICA GRADUALE (NON CONTRARIAN)
    # ============================================
    # Zone:
    # - 55-70: Bullish momentum zone (contribuisce progressivamente)
    # - 30-45: Bearish momentum zone (contribuisce progressivamente)
    # - <30: Oversold (potenziale rimbalzo - bullish contrarian)
    # - >80: Strong momentum (NON penalizzato - crypto può continuare)
    # - 70-80: Cautela ma non contrarian

    if rsi >= 55 and rsi <= 70:
        # Bullish momentum zone - contributo graduale
        # RSI 55 → intensity 0.2, RSI 70 → intensity 1.0
        intensity = 0.2 + (rsi - 55) / 15 * 0.8
        contribution = WEIGHT_RSI_MOMENTUM * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'RSI Momentum',
            'value': round(rsi, 2),
            'direction': 'BULLISH',
            'weight': WEIGHT_RSI_MOMENTUM,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'RSI={rsi:.1f} in bullish momentum zone (55-70)'
        })
    elif rsi >= 30 and rsi <= 45:
        # Bearish momentum zone - contributo graduale
        # RSI 45 → intensity 0.2, RSI 30 → intensity 1.0
        intensity = 0.2 + (45 - rsi) / 15 * 0.8
        contribution = WEIGHT_RSI_MOMENTUM * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'RSI Momentum',
            'value': round(rsi, 2),
            'direction': 'BEARISH',
            'weight': WEIGHT_RSI_MOMENTUM,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'RSI={rsi:.1f} in bearish momentum zone (30-45)'
        })
    elif rsi < 30:
        # Oversold - potenziale rimbalzo (bullish contrarian)
        intensity = min((30 - rsi) / 20, 1.0)  # Max at RSI 10
        contribution = WEIGHT_RSI_OVERSOLD * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'RSI Oversold',
            'value': round(rsi, 2),
            'direction': 'BULLISH',
            'weight': WEIGHT_RSI_OVERSOLD,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'RSI={rsi:.1f} OVERSOLD - potential bounce'
        })
    elif rsi > 80:
        # RSI alto ma NON penalizzato - crypto momentum può continuare
        # Solo un piccolo segnale di cautela, non bearish
        signals.append({
            'indicator': 'RSI Strong',
            'value': round(rsi, 2),
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'RSI={rsi:.1f} strong momentum (not contrarian in crypto)'
        })
    else:
        # 45-55 o 70-80: zona neutra
        signals.append({
            'indicator': 'RSI',
            'value': round(rsi, 2),
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'RSI={rsi:.1f} in neutral zone'
        })

    # ============================================
    # 2. BOLLINGER BANDS - Position Based
    # ============================================
    if bollinger:
        bb_position = bollinger.get('position', 'NEUTRAL')
        bb_squeeze = bollinger.get('squeeze', False)
        bb_percent_b = bollinger.get('percent_b', 0.5)

        if bb_position == 'ABOVE_UPPER':
            # Prezzo sopra upper band - strong bullish breakout
            # In crypto, breakout = momentum continuation, non mean reversion
            intensity = min(bb_percent_b - 1.0, 0.5) / 0.5 if bb_percent_b > 1.0 else 0.8
            contribution = WEIGHT_BOLLINGER * intensity
            score_bullish += contribution
            signals.append({
                'indicator': 'Bollinger Breakout',
                'value': f'%B={bb_percent_b:.2f}',
                'direction': 'BULLISH',
                'weight': WEIGHT_BOLLINGER,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Price ABOVE upper band - bullish breakout (crypto momentum)'
            })
        elif bb_position == 'BELOW_LOWER':
            # Prezzo sotto lower band - potential reversal o continuation bearish
            intensity = min(abs(bb_percent_b), 0.5) / 0.5 if bb_percent_b < 0 else 0.8
            contribution = WEIGHT_BOLLINGER * intensity
            score_bearish += contribution
            signals.append({
                'indicator': 'Bollinger Breakdown',
                'value': f'%B={bb_percent_b:.2f}',
                'direction': 'BEARISH',
                'weight': WEIGHT_BOLLINGER,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Price BELOW lower band - bearish pressure'
            })
        elif bb_position == 'UPPER_HALF':
            # Prezzo nella metà superiore - lieve bullish bias
            intensity = (bb_percent_b - 0.5) * 0.6  # Max 0.3 quando %B = 1.0
            contribution = WEIGHT_BOLLINGER * intensity * 0.5
            score_bullish += contribution
            signals.append({
                'indicator': 'Bollinger Position',
                'value': f'%B={bb_percent_b:.2f}',
                'direction': 'BULLISH',
                'weight': WEIGHT_BOLLINGER,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Price in upper half of bands (mild bullish)'
            })
        elif bb_position == 'LOWER_HALF':
            # Prezzo nella metà inferiore - lieve bearish bias
            intensity = (0.5 - bb_percent_b) * 0.6  # Max 0.3 quando %B = 0
            contribution = WEIGHT_BOLLINGER * intensity * 0.5
            score_bearish += contribution
            signals.append({
                'indicator': 'Bollinger Position',
                'value': f'%B={bb_percent_b:.2f}',
                'direction': 'BEARISH',
                'weight': WEIGHT_BOLLINGER,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Price in lower half of bands (mild bearish)'
            })

        # Squeeze detection (bassa volatilità)
        if bb_squeeze:
            # Squeeze = non penalizza, ma prepara per breakout
            # Il breakout direction sarà determinato dagli altri indicatori
            signals.append({
                'indicator': 'Bollinger Squeeze',
                'value': f'BW={bollinger.get("bandwidth", 0):.2f}%',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'Low volatility squeeze - potential breakout incoming'
            })

    # ============================================
    # 3. OBV TREND - Volume Confirmation
    # ============================================
    if obv_trend:
        if obv_trend == 'RISING':
            contribution = WEIGHT_OBV_TREND
            score_bullish += contribution
            signals.append({
                'indicator': 'OBV Trend',
                'value': obv_trend,
                'direction': 'BULLISH',
                'weight': WEIGHT_OBV_TREND,
                'intensity': 1.0,
                'contribution': contribution,
                'reason': 'OBV RISING - volume confirms uptrend'
            })
        elif obv_trend == 'FALLING':
            contribution = WEIGHT_OBV_TREND
            score_bearish += contribution
            signals.append({
                'indicator': 'OBV Trend',
                'value': obv_trend,
                'direction': 'BEARISH',
                'weight': WEIGHT_OBV_TREND,
                'intensity': 1.0,
                'contribution': contribution,
                'reason': 'OBV FALLING - volume confirms downtrend'
            })
        else:
            signals.append({
                'indicator': 'OBV Trend',
                'value': obv_trend,
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': 'OBV FLAT - no volume confirmation'
            })

    # ============================================
    # 4. MACD HISTOGRAM TREND
    # ============================================
    if macd_histogram_trend:
        # Histogram EXPANDING con MACD > 0 = bullish momentum increasing
        # Histogram EXPANDING con MACD < 0 = bearish momentum increasing
        macd_direction = 'bullish' if macd > 0 else 'bearish'

        if macd_histogram_trend == 'EXPANDING':
            contribution = WEIGHT_MACD_HISTOGRAM
            if macd > 0:
                score_bullish += contribution
                signals.append({
                    'indicator': 'MACD Histogram',
                    'value': f'{macd_histogram_trend} (MACD {macd:.4f})',
                    'direction': 'BULLISH',
                    'weight': WEIGHT_MACD_HISTOGRAM,
                    'intensity': 1.0,
                    'contribution': contribution,
                    'reason': f'Histogram EXPANDING with positive MACD - bullish momentum growing'
                })
            else:
                score_bearish += contribution
                signals.append({
                    'indicator': 'MACD Histogram',
                    'value': f'{macd_histogram_trend} (MACD {macd:.4f})',
                    'direction': 'BEARISH',
                    'weight': WEIGHT_MACD_HISTOGRAM,
                    'intensity': 1.0,
                    'contribution': contribution,
                    'reason': f'Histogram EXPANDING with negative MACD - bearish momentum growing'
                })
        elif macd_histogram_trend == 'CONTRACTING':
            # Momentum sta diminuendo - potenziale inversione
            contribution = WEIGHT_MACD_HISTOGRAM * 0.5
            if macd > 0:
                # Bullish momentum diminuisce - lieve bearish
                score_bearish += contribution
                signals.append({
                    'indicator': 'MACD Histogram',
                    'value': f'{macd_histogram_trend} (MACD {macd:.4f})',
                    'direction': 'BEARISH',
                    'weight': WEIGHT_MACD_HISTOGRAM,
                    'intensity': 0.5,
                    'contribution': contribution,
                    'reason': f'Histogram CONTRACTING - bullish momentum fading'
                })
            else:
                # Bearish momentum diminuisce - lieve bullish
                score_bullish += contribution
                signals.append({
                    'indicator': 'MACD Histogram',
                    'value': f'{macd_histogram_trend} (MACD {macd:.4f})',
                    'direction': 'BULLISH',
                    'weight': WEIGHT_MACD_HISTOGRAM,
                    'intensity': 0.5,
                    'contribution': contribution,
                    'reason': f'Histogram CONTRACTING - bearish momentum fading'
                })
        else:
            signals.append({
                'indicator': 'MACD Histogram',
                'value': f'{macd_histogram_trend}',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': 'MACD Histogram FLAT'
            })

    # ============================================
    # 5. EMA ALIGNMENT (Golden/Death Cross)
    # ============================================
    if ema_alignment:
        if ema_alignment == 'GOLDEN_CROSS':
            contribution = WEIGHT_EMA_ALIGNMENT
            score_bullish += contribution
            signals.append({
                'indicator': 'EMA Alignment',
                'value': f'EMA20={ema20:.2f} > EMA50={ema50:.2f}',
                'direction': 'BULLISH',
                'weight': WEIGHT_EMA_ALIGNMENT,
                'intensity': 1.0,
                'contribution': contribution,
                'reason': 'GOLDEN CROSS - EMA20 above EMA50 (bullish trend)'
            })
        elif ema_alignment == 'DEATH_CROSS':
            contribution = WEIGHT_EMA_ALIGNMENT
            score_bearish += contribution
            signals.append({
                'indicator': 'EMA Alignment',
                'value': f'EMA20={ema20:.2f} < EMA50={ema50:.2f}',
                'direction': 'BEARISH',
                'weight': WEIGHT_EMA_ALIGNMENT,
                'intensity': 1.0,
                'contribution': contribution,
                'reason': 'DEATH CROSS - EMA20 below EMA50 (bearish trend)'
            })
        else:
            signals.append({
                'indicator': 'EMA Alignment',
                'value': 'NEUTRAL',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': 'EMA20 and EMA50 converging'
            })

    # ============================================
    # 6. TREND (Price vs EMA20 + MACD)
    # ============================================
    price_above_ema = price > ema20
    macd_positive = macd > 0

    if not price_above_ema and not macd_positive:
        # Prezzo sotto EMA20 E MACD negativo → Forte segnale bearish
        contribution = WEIGHT_TREND_BEARISH
        score_bearish += contribution
        signals.append({
            'indicator': 'Trend (EMA+MACD)',
            'value': f'Price={price:.2f}, EMA20={ema20:.2f}, MACD={macd:.4f}',
            'direction': 'BEARISH',
            'weight': WEIGHT_TREND_BEARISH,
            'intensity': 1.0,
            'contribution': contribution,
            'reason': f'Price < EMA20 AND MACD < 0 (Downtrend)'
        })
    elif price_above_ema and macd_positive:
        # Prezzo sopra EMA20 E MACD positivo → Forte segnale bullish
        contribution = WEIGHT_TREND_BULLISH
        score_bullish += contribution
        signals.append({
            'indicator': 'Trend (EMA+MACD)',
            'value': f'Price={price:.2f}, EMA20={ema20:.2f}, MACD={macd:.4f}',
            'direction': 'BULLISH',
            'weight': WEIGHT_TREND_BULLISH,
            'intensity': 1.0,
            'contribution': contribution,
            'reason': f'Price > EMA20 AND MACD > 0 (Uptrend)'
        })
    else:
        # Segnali misti → contributo parziale dal MACD
        if macd > 0:
            contribution = WEIGHT_MACD_POSITIVE * 0.5
            score_bullish += contribution
            signals.append({
                'indicator': 'MACD',
                'value': round(macd, 4),
                'direction': 'BULLISH',
                'weight': WEIGHT_MACD_POSITIVE,
                'intensity': 0.5,
                'contribution': round(contribution, 2),
                'reason': f'MACD={macd:.4f} > 0 (Bullish momentum)'
            })
        elif macd < 0:
            contribution = WEIGHT_MACD_NEGATIVE * 0.5
            score_bearish += contribution
            signals.append({
                'indicator': 'MACD',
                'value': round(macd, 4),
                'direction': 'BEARISH',
                'weight': WEIGHT_MACD_NEGATIVE,
                'intensity': 0.5,
                'contribution': round(contribution, 2),
                'reason': f'MACD={macd:.4f} < 0 (Bearish momentum)'
            })

    # ============================================
    # 7. FEAR & GREED INDEX
    # ============================================
    if fear_greed < FEAR_GREED_FEAR_THRESHOLD:
        # Mercato in paura → Bearish signal
        intensity = (FEAR_GREED_FEAR_THRESHOLD - fear_greed) / FEAR_GREED_FEAR_THRESHOLD
        contribution = WEIGHT_FEAR_GREED_FEAR * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'BEARISH',
            'weight': WEIGHT_FEAR_GREED_FEAR,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'F&G={fear_greed} < {FEAR_GREED_FEAR_THRESHOLD} (Fear)'
        })
    elif fear_greed > FEAR_GREED_GREED_THRESHOLD:
        # Mercato euforico → Bullish signal
        intensity = (fear_greed - FEAR_GREED_GREED_THRESHOLD) / (100 - FEAR_GREED_GREED_THRESHOLD)
        contribution = WEIGHT_FEAR_GREED_GREED * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'BULLISH',
            'weight': WEIGHT_FEAR_GREED_GREED,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'F&G={fear_greed} > {FEAR_GREED_GREED_THRESHOLD} (Greed)'
        })
    else:
        signals.append({
            'indicator': 'Fear & Greed',
            'value': fear_greed,
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'F&G={fear_greed} (Neutral zone)'
        })

    # ============================================
    # 8. FORECAST (Prophet Prediction)
    # ============================================
    if forecast_change_pct < -FORECAST_MIN_CHANGE_PCT:
        # Previsione ribasso
        intensity = min(abs(forecast_change_pct) / 2.0, 1.0)  # Max intensity at -2%
        contribution = WEIGHT_FORECAST_NEGATIVE * intensity
        score_bearish += contribution
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'BEARISH',
            'weight': WEIGHT_FORECAST_NEGATIVE,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Bearish)'
        })
    elif forecast_change_pct > FORECAST_MIN_CHANGE_PCT:
        # Previsione rialzo
        intensity = min(abs(forecast_change_pct) / 2.0, 1.0)
        contribution = WEIGHT_FORECAST_POSITIVE * intensity
        score_bullish += contribution
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'BULLISH',
            'weight': WEIGHT_FORECAST_POSITIVE,
            'intensity': round(intensity, 2),
            'contribution': round(contribution, 2),
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Bullish)'
        })
    else:
        signals.append({
            'indicator': 'Forecast',
            'value': f'{forecast_change_pct:+.2f}%',
            'direction': 'NEUTRAL',
            'weight': 0,
            'intensity': 0,
            'contribution': 0,
            'reason': f'Forecast {forecast_change_pct:+.2f}% (Too small)'
        })

    # ============================================
    # 9. VOLUME (Bid vs Ask) - CON SMOOTHING
    # ============================================
    if volume_bid > 0 and volume_ask > 0:
        current_ratio = volume_bid / volume_ask

        # Inizializza history per questo simbolo se non esiste
        if symbol not in _volume_ratio_history:
            _volume_ratio_history[symbol] = []

        # Aggiungi ratio corrente alla history
        _volume_ratio_history[symbol].append(current_ratio)

        # Mantieni solo gli ultimi N cicli
        if len(_volume_ratio_history[symbol]) > VOLUME_SMOOTHING_CYCLES:
            _volume_ratio_history[symbol] = _volume_ratio_history[symbol][-VOLUME_SMOOTHING_CYCLES:]

        # Calcola la MEDIA del ratio (smoothed)
        avg_ratio = sum(_volume_ratio_history[symbol]) / len(_volume_ratio_history[symbol])

        if avg_ratio > VOLUME_RATIO_BULLISH_THRESHOLD:
            intensity = min((avg_ratio - 1) / 2, 1.0)
            contribution = WEIGHT_VOLUME_BULLISH * intensity
            score_bullish += contribution
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f}',
                'direction': 'BULLISH',
                'weight': WEIGHT_VOLUME_BULLISH,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Volume Ratio={avg_ratio:.2f} > {VOLUME_RATIO_BULLISH_THRESHOLD} (Buyers)'
            })
        elif avg_ratio < VOLUME_RATIO_BEARISH_THRESHOLD:
            intensity = min((1 - avg_ratio) / 0.5, 1.0)
            contribution = WEIGHT_VOLUME_BEARISH * intensity
            score_bearish += contribution
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f}',
                'direction': 'BEARISH',
                'weight': WEIGHT_VOLUME_BEARISH,
                'intensity': round(intensity, 2),
                'contribution': round(contribution, 2),
                'reason': f'Volume Ratio={avg_ratio:.2f} < {VOLUME_RATIO_BEARISH_THRESHOLD} (Sellers)'
            })
        else:
            signals.append({
                'indicator': 'Volume',
                'value': f'Bid/Ask={avg_ratio:.2f}',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'Volume Ratio in neutral zone'
            })

    # ============================================
    # 10. ADX FILTER (Ranging Market Penalty)
    # ============================================
    adx_multiplier = 1.0
    if adx is not None:
        if adx < ADX_WEAK_THRESHOLD:
            # Mercato ranging - riduce il weight dello score totale
            # ADX 0 → multiplier 0.5, ADX 20 → multiplier 1.0
            adx_multiplier = 0.5 + (adx / ADX_WEAK_THRESHOLD) * 0.5
            signals.append({
                'indicator': 'ADX Filter',
                'value': f'ADX={adx:.1f}',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'ADX={adx:.1f} < {ADX_WEAK_THRESHOLD} - RANGING MARKET (score reduced by {(1-adx_multiplier)*100:.0f}%)'
            })
        elif adx >= ADX_STRONG_THRESHOLD:
            signals.append({
                'indicator': 'ADX Filter',
                'value': f'ADX={adx:.1f}',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'ADX={adx:.1f} >= {ADX_STRONG_THRESHOLD} - STRONG TREND confirmed'
            })
        else:
            signals.append({
                'indicator': 'ADX Filter',
                'value': f'ADX={adx:.1f}',
                'direction': 'NEUTRAL',
                'weight': 0,
                'intensity': 0,
                'contribution': 0,
                'reason': f'ADX={adx:.1f} - Moderate trend strength'
            })

    # ============================================
    # CALCOLO FINALE CON ADX MULTIPLIER
    # ============================================
    # Applica ADX multiplier per ridurre score in mercati ranging
    score_bullish_final = score_bullish * adx_multiplier
    score_bearish_final = score_bearish * adx_multiplier
    net_score = score_bullish_final - score_bearish_final

    # Determina direzione suggerita
    if net_score >= SCORE_THRESHOLD_OPEN:
        direction = 'LONG'
        confidence = 'STRONG' if net_score >= SCORE_THRESHOLD_STRONG else 'NORMAL'
    elif net_score <= -SCORE_THRESHOLD_OPEN:
        direction = 'SHORT'
        confidence = 'STRONG' if net_score <= -SCORE_THRESHOLD_STRONG else 'NORMAL'
    else:
        direction = 'HOLD'
        confidence = 'WEAK'

    return {
        'score_bullish': round(score_bullish_final, 2),
        'score_bearish': round(score_bearish_final, 2),
        'score_bullish_raw': round(score_bullish, 2),  # Pre-ADX filter
        'score_bearish_raw': round(score_bearish, 2),  # Pre-ADX filter
        'net_score': round(net_score, 2),
        'direction': direction,
        'confidence': confidence,
        'adx_multiplier': round(adx_multiplier, 2),
        'signals': signals,
        'thresholds': {
            'open': SCORE_THRESHOLD_OPEN,
            'strong': SCORE_THRESHOLD_STRONG,
            'hold': SCORE_THRESHOLD_HOLD
        },
        'timestamp': datetime.utcnow().isoformat(),
        'version': 'v2'
    }


def format_score_v2_for_prompt(score_result: dict) -> str:
    """
    Formatta il risultato dello scoring V2 per includerlo nel prompt AI.
    """
    lines = [
        "=== SMART SCORE V2 ANALYSIS ===",
        f"Score BULLISH: {score_result['score_bullish']}",
        f"Score BEARISH: {score_result['score_bearish']}",
        f"NET SCORE: {score_result['net_score']}",
        f"Suggested Direction: {score_result['direction']} ({score_result['confidence']})",
    ]

    if score_result.get('adx_multiplier', 1.0) < 1.0:
        lines.append(f"⚠️ ADX Filter: Score reduced by {(1-score_result['adx_multiplier'])*100:.0f}% (ranging market)")

    lines.append("")
    lines.append("Signal Details:")

    for signal in score_result['signals']:
        if signal['contribution'] > 0:
            icon = "🟢" if signal['direction'] == 'BULLISH' else "🔴"
            lines.append(
                f"  {icon} {signal['indicator']}: {signal['direction']} "
                f"(+{signal['contribution']:.1f} pts) - {signal['reason']}"
            )

    lines.append("")
    lines.append(f"Thresholds: Open={score_result['thresholds']['open']}, "
                 f"Strong={score_result['thresholds']['strong']}")
    lines.append("================================")

    return "\n".join(lines)


# Test della funzione
if __name__ == "__main__":
    # Test V1
    print("=== TEST V1 ===")
    result = calculate_signal_score(
        price=3300.0,
        ema20=3350.0,
        rsi=75.0,
        macd=-2.5,
        fear_greed=22,
        forecast_change_pct=-0.8,
        volume_bid=100,
        volume_ask=150
    )
    print(format_score_for_prompt(result))

    # Test V2
    print("\n\n=== TEST V2 ===")
    result_v2 = calculate_smart_score_v2(
        price=3300.0,
        ema20=3350.0,
        ema50=3400.0,
        rsi=62.0,  # In bullish momentum zone
        macd=0.15,
        macd_signal=0.10,
        fear_greed=65,
        forecast_change_pct=0.5,
        volume_bid=120,
        volume_ask=100,
        symbol="BTC",
        bollinger={'position': 'UPPER_HALF', 'squeeze': False, 'percent_b': 0.75, 'bandwidth': 3.5},
        obv_trend='RISING',
        macd_histogram_trend='EXPANDING',
        ema_alignment='GOLDEN_CROSS',
        adx=28.0
    )
    print(format_score_v2_for_prompt(result_v2))

    # Test V2 con ADX basso (ranging)
    print("\n\n=== TEST V2 CON ADX BASSO ===")
    result_v2_ranging = calculate_smart_score_v2(
        price=3300.0,
        ema20=3350.0,
        ema50=3400.0,
        rsi=62.0,
        macd=0.15,
        macd_signal=0.10,
        fear_greed=65,
        forecast_change_pct=0.5,
        volume_bid=120,
        volume_ask=100,
        symbol="BTC",
        bollinger={'position': 'UPPER_HALF', 'squeeze': True, 'percent_b': 0.75, 'bandwidth': 1.5},
        obv_trend='FLAT',
        macd_histogram_trend='FLAT',
        ema_alignment='NEUTRAL',
        adx=12.0  # Ranging market
    )
    print(format_score_v2_for_prompt(result_v2_ranging))
