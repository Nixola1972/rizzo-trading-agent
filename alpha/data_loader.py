"""
AlphaTrader Data Loader
=======================

Downloads historical data from HyperLiquid for RL training.

Data sources:
1. OHLCV Candles (1m, 5m, 15m, 1h, 4h, 1d)
2. Funding Rate History
3. Open Interest
4. Order Book Snapshots

The data is processed and formatted for the AlphaTrader training loop.

Usage:
    # Download and prepare training data
    python -m alpha.data_loader --symbols BTC ETH SOL --days 60 --interval 15m

    # Just check what data is available
    python -m alpha.data_loader --check
"""

import os
import sys
import json
import time
import pickle
import logging
import argparse
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HyperLiquid API endpoints
HL_MAINNET_API = "https://api.hyperliquid.xyz/info"
HL_TESTNET_API = "https://api.hyperliquid-testnet.xyz/info"

# Interval to milliseconds
INTERVAL_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


@dataclass
class CandleData:
    """Single candle data point."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Calculated indicators (filled by process_candles)
    ema20: float = 0.0
    ema50: float = 0.0
    rsi_7: float = 50.0
    rsi_14: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    atr_14: float = 0.0
    adx: float = 25.0

    # Bollinger Bands
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_pct_b: float = 0.5
    bb_bandwidth: float = 0.0

    # OBV
    obv: float = 0.0
    obv_trend: float = 0.0  # -1, 0, 1

    # Derivatives data (if available)
    funding_rate: float = 0.0
    open_interest: float = 0.0


@dataclass
class TrainingEpisode:
    """A sequence of candles forming one training episode."""
    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    candles: List[Dict]  # List of CandleData as dicts

    def __len__(self):
        return len(self.candles)


class HyperLiquidDataLoader:
    """
    Downloads and processes historical data from HyperLiquid.
    """

    def __init__(self, testnet: bool = False):
        self.api_url = HL_TESTNET_API if testnet else HL_MAINNET_API
        self.testnet = testnet
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

    def _rate_limit(self):
        """Simple rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _post(self, payload: Dict) -> Any:
        """Make POST request to HyperLiquid API."""
        self._rate_limit()

        try:
            response = self.session.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None

    # =========================================================================
    # CANDLE DATA
    # =========================================================================

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 5000,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles from HyperLiquid.

        Args:
            symbol: Asset symbol (BTC, ETH, SOL, etc.)
            interval: Candle interval (1m, 5m, 15m, 1h, 4h, 1d)
            start_time: Start datetime
            end_time: End datetime (default: now)
            limit: Max candles to fetch (HyperLiquid limit is ~5000)

        Returns:
            DataFrame with OHLCV data
        """
        if interval not in INTERVAL_MS:
            raise ValueError(f"Invalid interval: {interval}. Use one of {list(INTERVAL_MS.keys())}")

        if end_time is None:
            end_time = datetime.now(timezone.utc)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        logger.info(f"Fetching {symbol} {interval} candles from {start_time} to {end_time}")

        # HyperLiquid uses POST with specific payload
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            }
        }

        data = self._post(payload)

        if not data:
            logger.warning(f"No candle data received for {symbol}")
            return pd.DataFrame()

        # Parse response
        # Format: [[timestamp, open, high, low, close, volume], ...]
        # Or dict format with 't', 'o', 'h', 'l', 'c', 'v' keys

        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                # Dict format
                df = pd.DataFrame(data)
                df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True)
                df = df.rename(columns={
                    "o": "open", "h": "high", "l": "low",
                    "c": "close", "v": "volume"
                })
            else:
                # List format
                df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        else:
            logger.warning(f"Unexpected data format: {type(data)}")
            return pd.DataFrame()

        # Convert to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(f"Fetched {len(df)} candles for {symbol}")
        return df

    def get_all_candles(
        self,
        symbol: str,
        interval: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """
        Fetch all candles for a period, handling pagination.

        HyperLiquid has a limit of ~5000 candles per request.
        For longer periods, we need to make multiple requests.
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        interval_ms = INTERVAL_MS[interval]
        max_candles_per_request = 5000

        # Calculate how many requests we need
        total_ms = int((end_time - start_time).total_seconds() * 1000)
        total_candles = total_ms // interval_ms

        if total_candles <= max_candles_per_request:
            return self.get_candles(symbol, interval, start_time, end_time)

        # Multiple requests needed
        all_dfs = []
        current_start = start_time

        while current_start < end_time:
            chunk_end = min(
                current_start + timedelta(milliseconds=max_candles_per_request * interval_ms),
                end_time
            )

            df = self.get_candles(symbol, interval, current_start, chunk_end)
            if not df.empty:
                all_dfs.append(df)

            current_start = chunk_end
            time.sleep(0.2)  # Be nice to the API

        if not all_dfs:
            return pd.DataFrame()

        result = pd.concat(all_dfs, ignore_index=True)
        result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        logger.info(f"Total candles fetched for {symbol}: {len(result)}")
        return result

    # =========================================================================
    # FUNDING RATE HISTORY
    # =========================================================================

    def get_funding_history(
        self,
        symbol: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical funding rates.

        Funding is paid hourly on HyperLiquid.
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        logger.info(f"Fetching funding history for {symbol}")

        payload = {
            "type": "fundingHistory",
            "coin": symbol,
            "startTime": start_ms,
        }

        data = self._post(payload)

        if not data:
            logger.warning(f"No funding data for {symbol}")
            return pd.DataFrame()

        # Parse funding history
        # Format: [{"coin": "BTC", "fundingRate": "0.0001", "premium": "0.0002", "time": 1234567890000}, ...]

        df = pd.DataFrame(data)
        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["funding_rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        df["premium"] = pd.to_numeric(df.get("premium", 0), errors="coerce")

        df = df[df["timestamp"] <= end_time]
        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(f"Fetched {len(df)} funding rate entries for {symbol}")
        return df

    # =========================================================================
    # PERPETUALS CONTEXT (Open Interest, Mark Price, etc.)
    # =========================================================================

    def get_perpetuals_context(self) -> Dict[str, Dict]:
        """
        Get current context for all perpetuals.

        Returns dict with mark price, funding, open interest per asset.
        """
        payload = {"type": "metaAndAssetCtxs"}

        data = self._post(payload)

        if not data or len(data) < 2:
            logger.warning("Could not fetch perpetuals context")
            return {}

        # data[0] is meta (universe info), data[1] is asset contexts
        meta = data[0]
        asset_ctxs = data[1]

        result = {}
        for i, asset in enumerate(meta.get("universe", [])):
            name = asset.get("name", f"ASSET_{i}")
            if i < len(asset_ctxs):
                ctx = asset_ctxs[i]
                result[name] = {
                    "mark_price": float(ctx.get("markPx", 0)),
                    "funding_rate": float(ctx.get("funding", 0)),
                    "open_interest": float(ctx.get("openInterest", 0)),
                    "premium": float(ctx.get("premium", 0)),
                    "oracle_price": float(ctx.get("oraclePx", 0)),
                }

        return result

    # =========================================================================
    # PROCESS CANDLES (Add Indicators)
    # =========================================================================

    def process_candles(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators for candle data.
        """
        if df.empty or len(df) < 50:
            logger.warning("Not enough data to calculate indicators")
            return df

        try:
            import ta
        except ImportError:
            logger.error("ta library not installed. Run: pip install ta")
            return df

        df = df.copy()

        # EMA
        df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
        df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

        # RSI
        df["rsi_7"] = ta.momentum.RSIIndicator(df["close"], window=7).rsi()
        df["rsi_14"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

        # MACD
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_histogram"] = macd.macd_diff()

        # ATR
        df["atr_14"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        ).average_true_range()

        # ADX
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"] = adx.adx()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_pct_b"] = bb.bollinger_pband()
        df["bb_bandwidth"] = bb.bollinger_wband()

        # OBV
        df["obv"] = ta.volume.OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()

        # OBV Trend (5-period slope)
        obv_slope = df["obv"].diff(5) / 5
        df["obv_trend"] = np.where(obv_slope > 0, 1, np.where(obv_slope < 0, -1, 0))

        # Fill NaN with reasonable defaults
        df = df.fillna(method="ffill").fillna(method="bfill")

        # Ensure no infinities
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)

        logger.info(f"Processed {len(df)} candles with indicators")
        return df

    # =========================================================================
    # CREATE TRAINING EPISODES
    # =========================================================================

    def create_training_episodes(
        self,
        df: pd.DataFrame,
        symbol: str,
        episode_length: int = 100,
        overlap: int = 20,
    ) -> List[TrainingEpisode]:
        """
        Split processed candle data into training episodes.

        Args:
            df: Processed candle DataFrame
            symbol: Asset symbol
            episode_length: Number of candles per episode
            overlap: Overlap between episodes for data augmentation

        Returns:
            List of TrainingEpisode objects
        """
        if len(df) < episode_length:
            logger.warning(f"Not enough data for episodes. Need {episode_length}, have {len(df)}")
            return []

        episodes = []
        step = episode_length - overlap

        for start_idx in range(0, len(df) - episode_length + 1, step):
            end_idx = start_idx + episode_length
            episode_df = df.iloc[start_idx:end_idx]

            # Convert to list of dicts
            candles = episode_df.to_dict("records")

            episodes.append(TrainingEpisode(
                symbol=symbol,
                interval="15m",  # TODO: make configurable
                start_time=episode_df.iloc[0]["timestamp"],
                end_time=episode_df.iloc[-1]["timestamp"],
                candles=candles,
            ))

        logger.info(f"Created {len(episodes)} training episodes for {symbol}")
        return episodes

    # =========================================================================
    # SAVE/LOAD DATA
    # =========================================================================

    def save_data(
        self,
        data: Dict[str, pd.DataFrame],
        output_dir: str = "alpha/data",
    ):
        """Save processed data to disk."""
        os.makedirs(output_dir, exist_ok=True)

        for symbol, df in data.items():
            # Save as parquet (efficient)
            parquet_path = os.path.join(output_dir, f"{symbol}_candles.parquet")
            df.to_parquet(parquet_path)
            logger.info(f"Saved {symbol} data to {parquet_path}")

            # Also save as CSV for inspection
            csv_path = os.path.join(output_dir, f"{symbol}_candles.csv")
            df.to_csv(csv_path, index=False)

    def save_episodes(
        self,
        episodes: List[TrainingEpisode],
        output_path: str = "alpha/data/training_episodes.pkl",
    ):
        """Save training episodes to disk."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as f:
            pickle.dump(episodes, f)

        logger.info(f"Saved {len(episodes)} episodes to {output_path}")

    def load_episodes(
        self,
        input_path: str = "alpha/data/training_episodes.pkl",
    ) -> List[TrainingEpisode]:
        """Load training episodes from disk."""
        with open(input_path, "rb") as f:
            episodes = pickle.load(f)

        logger.info(f"Loaded {len(episodes)} episodes from {input_path}")
        return episodes


def download_training_data(
    symbols: List[str] = ["BTC", "ETH", "SOL"],
    days: int = 60,
    interval: str = "15m",
    output_dir: str = "alpha/data",
    testnet: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    Download and process training data for multiple symbols.
    """
    loader = HyperLiquidDataLoader(testnet=testnet)

    all_data = {}
    all_episodes = []

    for symbol in symbols:
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing {symbol}...")
        logger.info(f"{'='*50}")

        # Download candles
        df = loader.get_all_candles(symbol, interval, days)

        if df.empty:
            logger.error(f"No data for {symbol}, skipping")
            continue

        # Process with indicators
        df = loader.process_candles(df)

        # Try to get funding history and merge
        try:
            funding_df = loader.get_funding_history(
                symbol,
                start_time=df["timestamp"].min(),
                end_time=df["timestamp"].max(),
            )

            if not funding_df.empty:
                # Merge funding data (forward fill to candle timestamps)
                funding_df = funding_df.set_index("timestamp")
                funding_df = funding_df.resample(interval).last().ffill()
                funding_df = funding_df.reset_index()

                df = pd.merge_asof(
                    df.sort_values("timestamp"),
                    funding_df[["timestamp", "funding_rate"]].sort_values("timestamp"),
                    on="timestamp",
                    direction="backward",
                )
        except Exception as e:
            logger.warning(f"Could not fetch funding data: {e}")

        all_data[symbol] = df

        # Create episodes
        episodes = loader.create_training_episodes(df, symbol)
        all_episodes.extend(episodes)

        time.sleep(1)  # Be nice to API

    # Save data
    loader.save_data(all_data, output_dir)
    loader.save_episodes(all_episodes, os.path.join(output_dir, "training_episodes.pkl"))

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("DOWNLOAD COMPLETE")
    logger.info(f"{'='*50}")

    for symbol, df in all_data.items():
        logger.info(f"{symbol}: {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")

    logger.info(f"Total training episodes: {len(all_episodes)}")

    return all_data


def main():
    parser = argparse.ArgumentParser(description="AlphaTrader Data Loader")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"],
                       help="Symbols to download")
    parser.add_argument("--days", type=int, default=60,
                       help="Days of historical data")
    parser.add_argument("--interval", type=str, default="15m",
                       choices=["1m", "5m", "15m", "1h", "4h", "1d"],
                       help="Candle interval")
    parser.add_argument("--output", type=str, default="alpha/data",
                       help="Output directory")
    parser.add_argument("--testnet", action="store_true",
                       help="Use testnet API")
    parser.add_argument("--check", action="store_true",
                       help="Just check available data without downloading")

    args = parser.parse_args()

    if args.check:
        loader = HyperLiquidDataLoader(testnet=args.testnet)

        logger.info("Checking HyperLiquid API...")

        # Check perpetuals context
        ctx = loader.get_perpetuals_context()
        logger.info(f"Available assets: {list(ctx.keys())[:10]}... ({len(ctx)} total)")

        # Show sample for BTC
        if "BTC" in ctx:
            logger.info(f"BTC context: {ctx['BTC']}")

        # Try to get some candles
        df = loader.get_candles(
            "BTC", "15m",
            datetime.now(timezone.utc) - timedelta(hours=1),
            datetime.now(timezone.utc),
        )
        logger.info(f"Sample BTC candles: {len(df)}")
        if not df.empty:
            logger.info(f"Latest candle: {df.iloc[-1].to_dict()}")

    else:
        download_training_data(
            symbols=args.symbols,
            days=args.days,
            interval=args.interval,
            output_dir=args.output,
            testnet=args.testnet,
        )


if __name__ == "__main__":
    main()
