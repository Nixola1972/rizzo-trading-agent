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


# Test della funzione
if __name__ == "__main__":
    # Esempio di utilizzo
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
    print("\nRaw result:")
    print(result)
