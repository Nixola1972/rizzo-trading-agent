"""
AlphaTrader Data Loader
=======================

Downloads historical data from HyperLiquid for RL training.

Data sources (in order of richness):

1. **S3 BULK DATA** (RECOMMENDED - Most complete)
   - hyperliquid-archive: L2 order book, asset contexts
   - hl-mainnet-node-data: All trades tick-by-tick
   - Format: LZ4 compressed

2. **REST API** (Simpler but limited)
   - OHLCV Candles (1m, 5m, 15m, 1h, 4h, 1d)
   - Funding Rate History
   - Open Interest

Usage:
    # Method 1: S3 Bulk Download (BEST - tick level data)
    python -m alpha.data_loader --source s3 --symbols BTC ETH --days 30

    # Method 2: REST API (simpler, candlestick data)
    python -m alpha.data_loader --source api --symbols BTC ETH SOL --days 60 --interval 15m

    # Check available data
    python -m alpha.data_loader --check
"""

import os
import sys
import json
import time
import pickle
import logging
import argparse
import subprocess
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

# S3 Buckets (public, no auth needed)
S3_ARCHIVE_BUCKET = "hyperliquid-archive"
S3_NODE_DATA_BUCKET = "hl-mainnet-node-data"
S3_ARTEMIS_BUCKET = "artemis-hyperliquid-data"

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
            # Save as pickle (no extra dependencies needed)
            pickle_path = os.path.join(output_dir, f"{symbol}_candles.pkl")
            df.to_pickle(pickle_path)
            logger.info(f"Saved {symbol} data to {pickle_path}")

            # Also save as CSV for inspection
            csv_path = os.path.join(output_dir, f"{symbol}_candles.csv")
            df.to_csv(csv_path, index=False)

    def save_episodes(
        self,
        episodes: List[TrainingEpisode],
        output_path: str = "alpha/data/training_episodes.pkl",
    ):
        """Save training episodes to disk as dicts (avoids pickle class issues)."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Convert TrainingEpisode objects to dicts for pickle compatibility
        episodes_as_dicts = []
        for ep in episodes:
            ep_dict = {
                'symbol': ep.symbol,
                'start_time': ep.start_time,
                'end_time': ep.end_time,
                'candles': ep.candles,
                'funding_rates': ep.funding_rates,
            }
            episodes_as_dicts.append(ep_dict)

        with open(output_path, "wb") as f:
            pickle.dump(episodes_as_dicts, f)

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


# =============================================================================
# S3 BULK DATA LOADER (Tick-by-tick, Order Book, All Fills)
# =============================================================================

class S3DataLoader:
    """
    Downloads bulk historical data from HyperLiquid S3 buckets.

    Available buckets:
    - hyperliquid-archive: L2 order book snapshots, asset contexts
    - hl-mainnet-node-data: All trade fills tick-by-tick

    Format: LZ4 compressed files

    Requirements:
    - AWS CLI installed: pip install awscli
    - LZ4: pip install lz4
    """

    def __init__(self, output_dir: str = "alpha/data/s3"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Check if AWS CLI is available
        self.aws_available = self._check_aws_cli()

    def _check_aws_cli(self) -> bool:
        """Check if AWS CLI is installed."""
        try:
            result = subprocess.run(
                ["aws", "--version"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.warning("AWS CLI not found. Install with: pip install awscli")
            return False

    def _decompress_lz4(self, lz4_path: str, output_path: str) -> bool:
        """Decompress LZ4 file."""
        try:
            import lz4.frame
            with open(lz4_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    f_out.write(lz4.frame.decompress(f_in.read()))
            return True
        except ImportError:
            logger.error("LZ4 not installed. Run: pip install lz4")
            return False
        except Exception as e:
            logger.error(f"Failed to decompress {lz4_path}: {e}")
            return False

    def list_available_dates(self, bucket: str = S3_ARCHIVE_BUCKET) -> List[str]:
        """List available dates in S3 bucket."""
        if not self.aws_available:
            return []

        try:
            result = subprocess.run(
                ["aws", "s3", "ls", f"s3://{bucket}/market_data/", "--no-sign-request"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Failed to list S3: {result.stderr}")
                return []

            # Parse output: "PRE 2024-01-15/"
            dates = []
            for line in result.stdout.strip().split('\n'):
                if 'PRE' in line:
                    date = line.split('PRE')[-1].strip().rstrip('/')
                    dates.append(date)

            return sorted(dates)
        except Exception as e:
            logger.error(f"Error listing S3: {e}")
            return []

    def download_market_data(
        self,
        symbol: str,
        date: str,
        data_type: str = "l2Book",  # l2Book, trades, etc.
    ) -> Optional[pd.DataFrame]:
        """
        Download market data for a specific date and symbol.

        Path format: s3://hyperliquid-archive/market_data/{date}/{hour}/{datatype}/{coin}.lz4
        """
        if not self.aws_available:
            logger.error("AWS CLI required for S3 download")
            return None

        local_dir = os.path.join(self.output_dir, date, symbol)
        os.makedirs(local_dir, exist_ok=True)

        all_data = []

        # Download all hours for the date
        for hour in range(24):
            hour_str = f"{hour:02d}"
            s3_path = f"s3://{S3_ARCHIVE_BUCKET}/market_data/{date}/{hour_str}/{data_type}/{symbol}.lz4"
            local_lz4 = os.path.join(local_dir, f"{hour_str}_{data_type}.lz4")
            local_csv = os.path.join(local_dir, f"{hour_str}_{data_type}.csv")

            # Download
            result = subprocess.run(
                ["aws", "s3", "cp", s3_path, local_lz4, "--no-sign-request"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                continue  # File might not exist for this hour

            # Decompress
            if self._decompress_lz4(local_lz4, local_csv):
                try:
                    df = pd.read_csv(local_csv)
                    all_data.append(df)
                except Exception as e:
                    logger.warning(f"Failed to parse {local_csv}: {e}")

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return None

    def download_node_fills(
        self,
        start_date: str,
        end_date: str,
        symbol: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Download all trade fills from node data.

        Path: s3://hl-mainnet-node-data/node_fills_by_block/

        This contains EVERY trade that happened on HyperLiquid.
        """
        if not self.aws_available:
            logger.error("AWS CLI required for S3 download")
            return pd.DataFrame()

        local_dir = os.path.join(self.output_dir, "node_fills")
        os.makedirs(local_dir, exist_ok=True)

        # Sync the date range
        logger.info(f"Downloading node fills from {start_date} to {end_date}...")

        # List and download files
        result = subprocess.run(
            [
                "aws", "s3", "sync",
                f"s3://{S3_NODE_DATA_BUCKET}/node_fills_by_block/",
                local_dir,
                "--no-sign-request",
                "--exclude", "*",
                "--include", f"*{start_date}*",
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.warning(f"S3 sync warning: {result.stderr}")

        # Read all downloaded files
        all_fills = []
        for f in Path(local_dir).glob("*.lz4"):
            csv_path = str(f).replace('.lz4', '.csv')
            if self._decompress_lz4(str(f), csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    if symbol and 'coin' in df.columns:
                        df = df[df['coin'] == symbol]
                    all_fills.append(df)
                except Exception as e:
                    logger.warning(f"Failed to parse {csv_path}: {e}")

        if all_fills:
            result_df = pd.concat(all_fills, ignore_index=True)
            logger.info(f"Downloaded {len(result_df)} fills")
            return result_df

        return pd.DataFrame()

    def download_asset_contexts(self, date: str) -> pd.DataFrame:
        """
        Download asset contexts (mark price, funding, OI) for a date.

        Path: s3://hyperliquid-archive/asset_ctxs/{date}.csv.lz4
        """
        if not self.aws_available:
            return pd.DataFrame()

        local_lz4 = os.path.join(self.output_dir, f"asset_ctxs_{date}.lz4")
        local_csv = os.path.join(self.output_dir, f"asset_ctxs_{date}.csv")

        s3_path = f"s3://{S3_ARCHIVE_BUCKET}/asset_ctxs/{date}.csv.lz4"

        result = subprocess.run(
            ["aws", "s3", "cp", s3_path, local_lz4, "--no-sign-request"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Failed to download asset contexts: {result.stderr}")
            return pd.DataFrame()

        if self._decompress_lz4(local_lz4, local_csv):
            return pd.read_csv(local_csv)

        return pd.DataFrame()

    def fills_to_candles(
        self,
        fills_df: pd.DataFrame,
        interval: str = "15m",
    ) -> pd.DataFrame:
        """
        Convert tick-by-tick fills to OHLCV candles.

        This gives you MUCH more accurate candles than the REST API
        because it's built from actual trade data.
        """
        if fills_df.empty:
            return pd.DataFrame()

        # Ensure timestamp column
        if 'time' in fills_df.columns:
            fills_df['timestamp'] = pd.to_datetime(fills_df['time'], unit='ms')
        elif 'timestamp' not in fills_df.columns:
            logger.error("No timestamp column in fills data")
            return pd.DataFrame()

        # Set timestamp as index
        df = fills_df.set_index('timestamp')

        # Get price column
        price_col = 'px' if 'px' in df.columns else 'price'
        size_col = 'sz' if 'sz' in df.columns else 'size'

        # Resample to candles
        candles = df.resample(interval).agg({
            price_col: ['first', 'max', 'min', 'last'],
            size_col: 'sum'
        })

        candles.columns = ['open', 'high', 'low', 'close', 'volume']
        candles = candles.dropna()
        candles = candles.reset_index()

        logger.info(f"Created {len(candles)} candles from {len(fills_df)} fills")
        return candles


def download_s3_data(
    symbols: List[str] = ["BTC", "ETH"],
    days: int = 30,
    output_dir: str = "alpha/data",
) -> Dict[str, pd.DataFrame]:
    """
    Download historical data from S3 and process for training.

    This provides MUCH richer data than the REST API:
    - Tick-by-tick trade data
    - Order book snapshots
    - All fills
    """
    loader = S3DataLoader(output_dir=os.path.join(output_dir, "s3_raw"))
    api_loader = HyperLiquidDataLoader()

    # Get date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    # Check what dates are available
    available_dates = loader.list_available_dates()

    if not available_dates:
        logger.warning("Could not list S3 dates. Falling back to REST API.")
        return download_training_data(symbols, days, "15m", output_dir)

    logger.info(f"S3 data available from {available_dates[0]} to {available_dates[-1]}")

    # Filter to requested range
    dates_to_download = [
        d for d in available_dates
        if start_date <= datetime.strptime(d, "%Y-%m-%d").date() <= end_date
    ]

    logger.info(f"Will download {len(dates_to_download)} days of data")

    all_data = {}
    all_episodes = []

    for symbol in symbols:
        logger.info(f"\n{'='*50}")
        logger.info(f"Processing {symbol} from S3...")
        logger.info(f"{'='*50}")

        symbol_fills = []

        for date in dates_to_download:
            # Try to get fills for this date
            try:
                fills = loader.download_node_fills(date, date, symbol)
                if not fills.empty:
                    symbol_fills.append(fills)
            except Exception as e:
                logger.warning(f"Failed to get fills for {date}: {e}")

        if symbol_fills:
            # Combine all fills
            all_fills = pd.concat(symbol_fills, ignore_index=True)
            logger.info(f"Total fills for {symbol}: {len(all_fills)}")

            # Convert to candles
            df = loader.fills_to_candles(all_fills, "15m")

            if not df.empty:
                # Process with indicators
                df = api_loader.process_candles(df)
                all_data[symbol] = df

                # Create episodes
                episodes = api_loader.create_training_episodes(df, symbol)
                all_episodes.extend(episodes)
        else:
            logger.warning(f"No S3 data for {symbol}, trying REST API...")
            df = api_loader.get_all_candles(symbol, "15m", days)
            if not df.empty:
                df = api_loader.process_candles(df)
                all_data[symbol] = df
                episodes = api_loader.create_training_episodes(df, symbol)
                all_episodes.extend(episodes)

    # Save data
    api_loader.save_data(all_data, output_dir)
    api_loader.save_episodes(all_episodes, os.path.join(output_dir, "training_episodes.pkl"))

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("S3 DOWNLOAD COMPLETE")
    logger.info(f"{'='*50}")

    for symbol, df in all_data.items():
        logger.info(f"{symbol}: {len(df)} candles")

    logger.info(f"Total training episodes: {len(all_episodes)}")

    return all_data


def main():
    parser = argparse.ArgumentParser(
        description="AlphaTrader Data Loader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # S3 Bulk Download (RECOMMENDED - tick level data)
  python -m alpha.data_loader --source s3 --symbols BTC ETH --days 30

  # REST API (simpler, candlestick data)
  python -m alpha.data_loader --source api --symbols BTC ETH SOL --days 60 --interval 15m

  # Check available data
  python -m alpha.data_loader --check

Data Sources:
  s3   - HyperLiquid S3 buckets (tick-by-tick, order book, all fills)
         Requires: pip install awscli lz4
  api  - REST API (OHLCV candles, funding rates)
         No additional dependencies
        """
    )
    parser.add_argument("--source", type=str, default="api",
                       choices=["api", "s3"],
                       help="Data source: 'api' (REST) or 's3' (bulk download)")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"],
                       help="Symbols to download")
    parser.add_argument("--days", type=int, default=60,
                       help="Days of historical data")
    parser.add_argument("--interval", type=str, default="15m",
                       choices=["1m", "5m", "15m", "1h", "4h", "1d"],
                       help="Candle interval (only for API source)")
    parser.add_argument("--output", type=str, default="alpha/data",
                       help="Output directory")
    parser.add_argument("--testnet", action="store_true",
                       help="Use testnet API")
    parser.add_argument("--check", action="store_true",
                       help="Just check available data without downloading")

    args = parser.parse_args()

    if args.check:
        logger.info("=" * 60)
        logger.info("CHECKING AVAILABLE DATA SOURCES")
        logger.info("=" * 60)

        # Check REST API
        logger.info("\n📡 REST API:")
        api_loader = HyperLiquidDataLoader(testnet=args.testnet)
        ctx = api_loader.get_perpetuals_context()
        if ctx:
            logger.info(f"   ✅ Available - {len(ctx)} assets")
            logger.info(f"   Assets: {list(ctx.keys())[:5]}...")
        else:
            logger.info("   ❌ Not reachable")

        # Check S3
        logger.info("\n📦 S3 Buckets:")
        s3_loader = S3DataLoader(output_dir=args.output)
        if s3_loader.aws_available:
            dates = s3_loader.list_available_dates()
            if dates:
                logger.info(f"   ✅ Available - {len(dates)} days")
                logger.info(f"   Range: {dates[0]} to {dates[-1]}")
            else:
                logger.info("   ⚠️ AWS CLI ok but no dates listed (may be network issue)")
        else:
            logger.info("   ❌ AWS CLI not installed")
            logger.info("   Install with: pip install awscli lz4")

        logger.info("\n" + "=" * 60)
        logger.info("RECOMMENDATION:")
        if s3_loader.aws_available:
            logger.info("Use --source s3 for tick-by-tick data (best for training)")
        else:
            logger.info("Use --source api for candlestick data")
        logger.info("=" * 60)

    else:
        if args.source == "s3":
            logger.info("📦 Using S3 Bulk Download (tick-by-tick data)")
            download_s3_data(
                symbols=args.symbols,
                days=args.days,
                output_dir=args.output,
            )
        else:
            logger.info("📡 Using REST API (candlestick data)")
            download_training_data(
                symbols=args.symbols,
                days=args.days,
                interval=args.interval,
                output_dir=args.output,
                testnet=args.testnet,
            )


if __name__ == "__main__":
    main()
