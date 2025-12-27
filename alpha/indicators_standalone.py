"""
Standalone indicator fetching for AlphaTrader.
Does not depend on parent module indicators.py
"""

import requests
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

HL_MAINNET_API = "https://api.hyperliquid.xyz"


def fetch_candles(symbol: str, interval: str = "15m", limit: int = 100) -> list:
    """Fetch recent candles from HyperLiquid."""
    try:
        response = requests.post(
            f"{HL_MAINNET_API}/info",
            json={
                "type": "candleSnapshot",
                "coin": symbol.upper(),
                "interval": interval,
                "startTime": int((datetime.utcnow().timestamp() - 86400 * 7) * 1000),
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data[-limit:] if len(data) > limit else data
    except Exception as e:
        logger.error(f"Error fetching candles for {symbol}: {e}")
    return []


def calculate_indicators(candles: list) -> Dict:
    """Calculate indicators from candles."""
    if not candles or len(candles) < 20:
        return {}

    closes = np.array([float(c['c']) for c in candles])
    highs = np.array([float(c['h']) for c in candles])
    lows = np.array([float(c['l']) for c in candles])
    volumes = np.array([float(c['v']) for c in candles])

    price = closes[-1]

    # EMA 20
    ema20 = calculate_ema(closes, 20)

    # EMA 50
    ema50 = calculate_ema(closes, 50) if len(closes) >= 50 else ema20

    # RSI 14
    rsi = calculate_rsi(closes, 14)

    # MACD
    macd, macd_signal, macd_hist = calculate_macd(closes)

    # ATR 14
    atr = calculate_atr(highs, lows, closes, 14)

    # ADX
    adx = calculate_adx(highs, lows, closes, 14)

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = calculate_bollinger(closes, 20, 2)

    # Volume ratio
    avg_volume = np.mean(volumes[-20:])
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0

    return {
        'price': price,
        'ema20': ema20,
        'ema50': ema50,
        'rsi_14': rsi,
        'macd': macd,
        'macd_signal': macd_signal,
        'macd_histogram': macd_hist,
        'atr_14': atr,
        'adx': adx,
        'bb_upper': bb_upper,
        'bb_middle': bb_middle,
        'bb_lower': bb_lower,
        'volume_ratio': volume_ratio,
    }


def calculate_ema(prices: np.ndarray, period: int) -> float:
    """Calculate EMA."""
    if len(prices) < period:
        return prices[-1]
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate RSI."""
    if len(prices) < period + 1:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices: np.ndarray) -> Tuple[float, float, float]:
    """Calculate MACD."""
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd = ema12 - ema26
    signal = calculate_ema(np.array([macd]), 9)  # Simplified
    histogram = macd - signal
    return macd, signal, histogram


def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Calculate ATR."""
    if len(closes) < period + 1:
        return highs[-1] - lows[-1]

    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

    return np.mean(tr_list[-period:])


def calculate_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Calculate ADX (simplified)."""
    if len(closes) < period + 1:
        return 25.0

    # Simplified ADX calculation
    tr_list = []
    dm_plus_list = []
    dm_minus_list = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

        dm_plus = highs[i] - highs[i-1] if highs[i] - highs[i-1] > 0 else 0
        dm_minus = lows[i-1] - lows[i] if lows[i-1] - lows[i] > 0 else 0

        if dm_plus > dm_minus:
            dm_minus = 0
        else:
            dm_plus = 0

        dm_plus_list.append(dm_plus)
        dm_minus_list.append(dm_minus)

    atr = np.mean(tr_list[-period:])
    di_plus = 100 * np.mean(dm_plus_list[-period:]) / atr if atr > 0 else 0
    di_minus = 100 * np.mean(dm_minus_list[-period:]) / atr if atr > 0 else 0

    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) > 0 else 0

    return dx


def calculate_bollinger(prices: np.ndarray, period: int = 20, std_dev: float = 2) -> Tuple[float, float, float]:
    """Calculate Bollinger Bands."""
    if len(prices) < period:
        return prices[-1] * 1.02, prices[-1], prices[-1] * 0.98

    middle = np.mean(prices[-period:])
    std = np.std(prices[-period:])
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return upper, middle, lower


def get_hyperliquid_indicators(symbol: str) -> Tuple[str, Dict]:
    """
    Get indicators for a symbol from HyperLiquid.

    Returns:
        Tuple of (formatted_text, indicator_dict)
    """
    candles = fetch_candles(symbol)
    if not candles:
        return "", {}

    indicators = calculate_indicators(candles)

    # Format text
    text = f"""
{symbol} Indicators:
Price: ${indicators.get('price', 0):.2f}
EMA20: ${indicators.get('ema20', 0):.2f}
EMA50: ${indicators.get('ema50', 0):.2f}
RSI: {indicators.get('rsi_14', 50):.1f}
MACD: {indicators.get('macd', 0):.4f}
ADX: {indicators.get('adx', 25):.1f}
ATR: ${indicators.get('atr_14', 0):.2f}
"""

    return text, indicators


def get_fear_greed_index() -> Dict:
    """Fetch Fear & Greed index from alternative.me API."""
    try:
        response = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                fg = data['data'][0]
                return {
                    'value': int(fg.get('value', 50)),
                    'classification': fg.get('value_classification', 'Neutral'),
                }
    except Exception as e:
        logger.error(f"Error fetching Fear & Greed: {e}")

    return {'value': 50, 'classification': 'Neutral'}
