#!/usr/bin/env python3
"""
Binance Historical Data Loader for AlphaTrader
===============================================

Downloads historical candlestick data from Binance's public data repository.
This provides MUCH more historical data than HyperLiquid API (years vs days).

Data source: https://data.binance.vision/

Usage:
    # Download BTC and ETH from 2020 to now
    python -m alpha.binance_data_loader --symbols BTC ETH --start-year 2020

    # Download all major coins from 2017
    python -m alpha.binance_data_loader --symbols BTC ETH SOL BNB XRP DOGE AVAX LINK --start-year 2017

    # Check available data
    python -m alpha.binance_data_loader --check
"""

import os
import sys
import io
import zipfile
import logging
import argparse
import requests
import pickle
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

# Technical analysis
try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BINANCE] %(message)s')
logger = logging.getLogger(__name__)

# Binance data URL
BINANCE_DATA_URL = "https://data.binance.vision/data"

# Map our symbols to Binance symbols
SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT",
    "AVAX": "AVAXUSDT",
    "LINK": "LINKUSDT",
    "MATIC": "MATICUSDT",
    "DOT": "DOTUSDT",
    "LTC": "LTCUSDT",
    "ATOM": "ATOMUSDT",
    "UNI": "UNIUSDT",
    "ARB": "ARBUSDT",
    "OP": "OPUSDT",
}

# Column names for Binance klines CSV
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base",
    "taker_buy_quote", "ignore"
]


class BinanceDataLoader:
    """Download and process historical data from Binance."""

    def __init__(self, output_dir: str = "alpha/data/binance"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    def get_available_months(
        self,
        symbol: str,
        interval: str = "15m",
        data_type: str = "futures/um"  # futures/um for perpetual, spot for spot
    ) -> List[str]:
        """
        Check which months are available for a symbol.

        Returns list of available month strings like ['2020-01', '2020-02', ...]
        """
        binance_symbol = SYMBOL_MAP.get(symbol, f"{symbol}USDT")

        # Try to list files (Binance doesn't have a proper API for this)
        # We'll just try common date ranges
        available = []
        current = datetime.now()

        # Check from 2017 to now
        for year in range(2017, current.year + 1):
            for month in range(1, 13):
                if year == current.year and month > current.month:
                    break

                date_str = f"{year}-{month:02d}"
                url = f"{BINANCE_DATA_URL}/{data_type}/monthly/klines/{binance_symbol}/{interval}/{binance_symbol}-{interval}-{date_str}.zip"

                try:
                    response = self.session.head(url, timeout=5)
                    if response.status_code == 200:
                        available.append(date_str)
                except:
                    pass

        return available

    def download_month(
        self,
        symbol: str,
        year: int,
        month: int,
        interval: str = "15m",
        data_type: str = "futures/um"
    ) -> Optional[pd.DataFrame]:
        """
        Download one month of kline data.

        Returns DataFrame with OHLCV data or None if not available.
        """
        binance_symbol = SYMBOL_MAP.get(symbol, f"{symbol}USDT")
        date_str = f"{year}-{month:02d}"

        url = f"{BINANCE_DATA_URL}/{data_type}/monthly/klines/{binance_symbol}/{interval}/{binance_symbol}-{interval}-{date_str}.zip"

        try:
            response = self.session.get(url, timeout=60)

            if response.status_code == 200:
                # Extract ZIP in memory
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    # Get the CSV filename inside
                    csv_name = zf.namelist()[0]
                    with zf.open(csv_name) as f:
                        # Read first line to check if it has a header
                        first_line = f.readline().decode('utf-8').strip()
                        f.seek(0)  # Reset to beginning

                        # Check if first line is a header (contains text like 'open_time')
                        has_header = 'open' in first_line.lower() or not first_line[0].isdigit()

                        if has_header:
                            # File has header row (2022-08+ format)
                            df = pd.read_csv(f)
                            # Rename columns to our standard names
                            df.columns = df.columns.str.lower().str.replace(' ', '_')
                        else:
                            # No header (pre-2022-08 format)
                            df = pd.read_csv(f, header=None, names=KLINE_COLUMNS)

                # Ensure open_time column exists (handle different column names)
                if 'open_time' not in df.columns:
                    # Try common alternatives
                    for col in ['opentime', 'open time', 'timestamp', 'time']:
                        if col in df.columns:
                            df['open_time'] = df[col]
                            break
                    else:
                        # Use first column as timestamp
                        df['open_time'] = df.iloc[:, 0]

                # Convert open_time to numeric first (handles string numbers)
                df['open_time'] = pd.to_numeric(df['open_time'], errors='coerce')

                # Convert timestamps - Binance uses milliseconds
                # Note: From 2025, SPOT uses microseconds, but futures still uses ms
                df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True, errors='coerce')

                # If that failed, try microseconds (for 2025+ spot data)
                if df["timestamp"].isna().all():
                    df["timestamp"] = pd.to_datetime(df["open_time"], unit="us", utc=True, errors='coerce')

                # Ensure we have the right columns (handle different naming)
                col_mapping = {
                    'open': ['open', 'Open'],
                    'high': ['high', 'High'],
                    'low': ['low', 'Low'],
                    'close': ['close', 'Close'],
                    'volume': ['volume', 'Volume', 'vol']
                }

                for target, sources in col_mapping.items():
                    if target not in df.columns:
                        for src in sources:
                            if src in df.columns:
                                df[target] = df[src]
                                break

                # Select and convert columns
                required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
                for col in required_cols:
                    if col not in df.columns:
                        logger.warning(f"  ! {symbol} {date_str}: Missing column {col}")
                        return None

                df = df[required_cols].copy()
                df["open"] = pd.to_numeric(df["open"], errors='coerce')
                df["high"] = pd.to_numeric(df["high"], errors='coerce')
                df["low"] = pd.to_numeric(df["low"], errors='coerce')
                df["close"] = pd.to_numeric(df["close"], errors='coerce')
                df["volume"] = pd.to_numeric(df["volume"], errors='coerce')

                # Drop any rows with NaN values
                df = df.dropna()

                if len(df) > 0:
                    logger.info(f"  ✓ {symbol} {date_str}: {len(df)} candles")
                    return df
                else:
                    logger.warning(f"  ! {symbol} {date_str}: No valid data after parsing")
                    return None

            elif response.status_code == 404:
                logger.debug(f"  - {symbol} {date_str}: not available")
                return None
            else:
                logger.warning(f"  ! {symbol} {date_str}: HTTP {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"  ✗ {symbol} {date_str}: {e}")
            return None

    def download_symbol(
        self,
        symbol: str,
        start_year: int = 2020,
        end_year: Optional[int] = None,
        interval: str = "15m",
        data_type: str = "futures/um"
    ) -> pd.DataFrame:
        """
        Download all available data for a symbol.

        Args:
            symbol: Coin symbol (BTC, ETH, etc.)
            start_year: Year to start from
            end_year: Year to end (default: current year)
            interval: Candle interval (15m, 1h, etc.)
            data_type: 'futures/um' for perpetual, 'spot' for spot

        Returns:
            DataFrame with all candles
        """
        if end_year is None:
            end_year = datetime.now().year

        logger.info(f"\n{'='*50}")
        logger.info(f"Downloading {symbol} ({start_year}-{end_year}, {interval})")
        logger.info(f"{'='*50}")

        all_dfs = []
        current = datetime.now()

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                # Don't try to download future months
                if year == current.year and month > current.month:
                    break

                df = self.download_month(symbol, year, month, interval, data_type)
                if df is not None and not df.empty:
                    all_dfs.append(df)

        if not all_dfs:
            logger.warning(f"No data found for {symbol}")
            return pd.DataFrame()

        # Combine all months
        result = pd.concat(all_dfs, ignore_index=True)
        result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        logger.info(f"✓ {symbol}: {len(result):,} total candles")
        logger.info(f"  Period: {result['timestamp'].min()} to {result['timestamp'].max()}")

        return result

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to the dataframe."""
        if df.empty:
            return df

        df = df.copy()

        # Price
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        if TA_AVAILABLE:
            # EMAs
            df["ema20"] = ta.trend.ema_indicator(close, window=20)
            df["ema50"] = ta.trend.ema_indicator(close, window=50)

            # RSI
            df["rsi_7"] = ta.momentum.rsi(close, window=7)
            df["rsi_14"] = ta.momentum.rsi(close, window=14)

            # MACD
            macd = ta.trend.MACD(close)
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()
            df["macd_histogram"] = macd.macd_diff()

            # ATR
            df["atr_14"] = ta.volatility.average_true_range(high, low, close, window=14)

            # ADX
            df["adx"] = ta.trend.adx(high, low, close, window=14)

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(close, window=20)
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_middle"] = bb.bollinger_mavg()
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_pct_b"] = bb.bollinger_pband()
            df["bb_bandwidth"] = bb.bollinger_wband()

            # OBV
            obv = ta.volume.on_balance_volume(close, volume)
            df["obv"] = obv
            df["obv_ema"] = ta.trend.ema_indicator(obv, window=20)
            df["obv_trend"] = (df["obv"] > df["obv_ema"]).astype(float) - 0.5

        else:
            # Simple fallback calculations without ta library
            df["ema20"] = close.ewm(span=20).mean()
            df["ema50"] = close.ewm(span=50).mean()

            # Simple RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df["rsi_14"] = 100 - (100 / (1 + rs))
            df["rsi_7"] = df["rsi_14"]  # Simplified

            # Simple MACD
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            df["macd"] = ema12 - ema26
            df["macd_signal"] = df["macd"].ewm(span=9).mean()
            df["macd_histogram"] = df["macd"] - df["macd_signal"]

            # Placeholders
            df["atr_14"] = (high - low).rolling(14).mean()
            df["adx"] = 25.0
            df["bb_upper"] = close.rolling(20).mean() + 2 * close.rolling(20).std()
            df["bb_middle"] = close.rolling(20).mean()
            df["bb_lower"] = close.rolling(20).mean() - 2 * close.rolling(20).std()
            df["bb_pct_b"] = 0.5
            df["bb_bandwidth"] = 0.04
            df["obv_trend"] = 0.0

        # Fill NaN values
        df = df.ffill().bfill()

        return df

    def create_training_episodes(
        self,
        df: pd.DataFrame,
        symbol: str,
        episode_length: int = 100,
        overlap: int = 20
    ) -> List[Dict]:
        """
        Split data into training episodes.

        Each episode is a sequence of candles that the RL agent will train on.
        """
        if df.empty or len(df) < episode_length:
            return []

        episodes = []
        start_idx = 0

        while start_idx + episode_length <= len(df):
            episode_df = df.iloc[start_idx:start_idx + episode_length]

            # Convert to list of dicts for training
            candles = []
            for _, row in episode_df.iterrows():
                candle = {
                    "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "price": float(row["close"]),
                    "volume": float(row["volume"]),
                    "ema20": float(row.get("ema20", row["close"])),
                    "ema50": float(row.get("ema50", row["close"])),
                    "rsi_7": float(row.get("rsi_7", 50)),
                    "rsi_14": float(row.get("rsi_14", 50)),
                    "macd": float(row.get("macd", 0)),
                    "macd_signal": float(row.get("macd_signal", 0)),
                    "macd_histogram": float(row.get("macd_histogram", 0)),
                    "atr_14": float(row.get("atr_14", 0)),
                    "adx": float(row.get("adx", 25)),
                    "bb_upper": float(row.get("bb_upper", row["close"] * 1.02)),
                    "bb_middle": float(row.get("bb_middle", row["close"])),
                    "bb_lower": float(row.get("bb_lower", row["close"] * 0.98)),
                    "bb_pct_b": float(row.get("bb_pct_b", 0.5)),
                    "bb_bandwidth": float(row.get("bb_bandwidth", 0.04)),
                    "obv_trend": float(row.get("obv_trend", 0)),
                }
                candles.append(candle)

            episode = {
                "symbol": symbol,
                "start_time": candles[0]["timestamp"],
                "end_time": candles[-1]["timestamp"],
                "candles": candles,
            }
            episodes.append(episode)

            start_idx += episode_length - overlap

        return episodes


def download_all_data(
    symbols: List[str],
    start_year: int = 2020,
    interval: str = "15m",
    output_dir: str = "alpha/data",
    data_type: str = "futures/um",
    episode_length: int = None,
    episode_overlap: int = None
) -> Dict[str, pd.DataFrame]:
    """
    Download data for multiple symbols and create training episodes.

    For 1h candles, use optimized settings:
        episode_length=72 (3 days), overlap=48 (67%) -> 3.3x more episodes
    For 15m candles, use default:
        episode_length=100, overlap=20
    """
    loader = BinanceDataLoader(output_dir=os.path.join(output_dir, "binance_raw"))

    # Optimized defaults based on interval
    if episode_length is None:
        if interval == "1h":
            episode_length = 72  # 3 days of hourly candles
        else:
            episode_length = 100  # Default for 15m

    if episode_overlap is None:
        if interval == "1h":
            episode_overlap = 48  # 67% overlap for more training data
        else:
            episode_overlap = 20  # Default 20% overlap

    logger.info(f"📊 Episode config: length={episode_length}, overlap={episode_overlap}")

    all_data = {}
    all_episodes = []

    for symbol in symbols:
        # Download
        df = loader.download_symbol(symbol, start_year=start_year, interval=interval, data_type=data_type)

        if df.empty:
            logger.warning(f"No data for {symbol}, trying spot market...")
            df = loader.download_symbol(symbol, start_year=start_year, interval=interval, data_type="spot")

        if not df.empty:
            # Add indicators
            logger.info(f"Adding indicators for {symbol}...")
            df = loader.add_indicators(df)
            all_data[symbol] = df

            # Save raw data
            parquet_path = os.path.join(output_dir, f"{symbol}_binance_candles.parquet")
            df.to_parquet(parquet_path)
            logger.info(f"Saved {symbol} to {parquet_path}")

            # Create episodes with optimized settings
            episodes = loader.create_training_episodes(
                df, symbol,
                episode_length=episode_length,
                overlap=episode_overlap
            )
            all_episodes.extend(episodes)
            logger.info(f"Created {len(episodes)} training episodes for {symbol}")

    # Save all episodes
    if all_episodes:
        episodes_path = os.path.join(output_dir, "training_episodes_binance.pkl")
        with open(episodes_path, "wb") as f:
            pickle.dump(all_episodes, f)
        logger.info(f"\n{'='*50}")
        logger.info(f"✓ Saved {len(all_episodes)} total episodes to {episodes_path}")
        logger.info(f"{'='*50}")

    # Summary
    logger.info(f"\n📊 DOWNLOAD SUMMARY:")
    logger.info(f"   Symbols: {len(all_data)}")
    total_candles = sum(len(df) for df in all_data.values())
    logger.info(f"   Total candles: {total_candles:,}")
    logger.info(f"   Total episodes: {len(all_episodes)}")

    if all_data:
        oldest = min(df["timestamp"].min() for df in all_data.values())
        newest = max(df["timestamp"].max() for df in all_data.values())
        logger.info(f"   Date range: {oldest} to {newest}")

    return all_data


def check_available_data():
    """Check what data is available on Binance."""
    loader = BinanceDataLoader()

    symbols_to_check = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK"]

    print("\n" + "=" * 60)
    print("🔍 Checking Binance Data Availability")
    print("=" * 60)

    for symbol in symbols_to_check:
        binance_sym = SYMBOL_MAP.get(symbol, f"{symbol}USDT")

        # Check first and last available month
        first_month = None
        last_month = None

        current = datetime.now()

        # Check backwards from now
        for year in range(current.year, 2016, -1):
            for month in range(12, 0, -1):
                if year == current.year and month > current.month:
                    continue

                df = loader.download_month(symbol, year, month, data_type="futures/um")
                if df is not None:
                    if last_month is None:
                        last_month = f"{year}-{month:02d}"
                    first_month = f"{year}-{month:02d}"
                elif first_month is not None:
                    # Found gap, stop
                    break

            if first_month is not None and df is None:
                break

        if first_month:
            print(f"  {symbol}: {first_month} to {last_month} (Futures)")
        else:
            print(f"  {symbol}: No futures data, checking spot...")


def main():
    parser = argparse.ArgumentParser(description="Download Binance historical data")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"],
                       help="Symbols to download")
    parser.add_argument("--start-year", type=int, default=2020,
                       help="Year to start from (default: 2020)")
    parser.add_argument("--interval", default="15m",
                       help="Candle interval (default: 15m)")
    parser.add_argument("--output-dir", default="alpha/data",
                       help="Output directory")
    parser.add_argument("--check", action="store_true",
                       help="Check available data")
    parser.add_argument("--data-type", default="futures/um",
                       choices=["futures/um", "spot"],
                       help="Data type: futures/um (perpetual) or spot")
    parser.add_argument("--episode-length", type=int, default=None,
                       help="Episode length in candles (default: 72 for 1h, 100 for 15m)")
    parser.add_argument("--episode-overlap", type=int, default=None,
                       help="Episode overlap in candles (default: 48 for 1h, 20 for 15m)")

    args = parser.parse_args()

    if args.check:
        check_available_data()
    else:
        download_all_data(
            symbols=args.symbols,
            start_year=args.start_year,
            interval=args.interval,
            output_dir=args.output_dir,
            data_type=args.data_type,
            episode_length=args.episode_length,
            episode_overlap=args.episode_overlap
        )


if __name__ == "__main__":
    main()
