import pandas as pd
import ta
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

from hyperliquid.info import Info
from hyperliquid.utils import constants


INTERVAL_TO_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


class CryptoTechnicalAnalysisHL:
    """
    Analisi tecnica usando l'API Info di Hyperliquid.
    Tutti gli indicatori principali sono centrati sul timeframe 15 minuti.
    """

    def __init__(self, testnet: bool = True):
        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.info = Info(base_url, skip_ws=True)

    # ==============================
    #       FETCH OHLCV (HL)
    # ==============================

    def get_orderbook_volume(self, ticker: str) -> str:
        """
        Restituisce una stringa con i volumi totali di bid e ask per un ticker (es. 'btc-usd').
        Usa Info.l2_snapshot() dal wrapper ufficiale Hyperliquid.
        """
        coin = ticker.split('-')[0].upper()  # es. "BTC" da "btc-usd"

        try:
            orderbook = self.info.l2_snapshot(coin)
        except Exception as e:
            return f"Errore recuperando orderbook: {e}"

        if not orderbook or "levels" not in orderbook:
            return f"Nessun dato disponibile per {coin}"

        bids = orderbook["levels"][0]
        asks = orderbook["levels"][1]

        bid_volume = sum(float(level["sz"]) for level in bids)
        ask_volume = sum(float(level["sz"]) for level in asks)

        return f"Bid Vol: {bid_volume}, Ask Vol: {ask_volume}"

    def fetch_ohlcv(self, coin: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """
        Recupera i dati OHLCV da Hyperliquid tramite Info.candles_snapshot.

        Args:
            coin: asset Hyperliquid (es. 'BTC', 'ETH')
            interval: es. '15m', '1d'
            limit: numero massimo di candele circa (usato per la finestra temporale)

        Returns:
            DataFrame con colonne: timestamp, open, high, low, close, volume
        """
        if interval not in INTERVAL_TO_MS:
            raise ValueError(f"Interval '{interval}' non supportato in INTERVAL_TO_MS")

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        step_ms = INTERVAL_TO_MS[interval]
        start_ms = now_ms - limit * step_ms

        # ⚠️ Metodo corretto: candles_snapshot (non candle_snapshot)
        ohlcv_data = self.info.candles_snapshot(
            name=coin,
            interval=interval,
            startTime=start_ms,
            endTime=now_ms,
        )

        if not ohlcv_data:
            raise RuntimeError(f"Nessuna candela ricevuta per {coin} ({interval})")

        df = pd.DataFrame(ohlcv_data)

        # df ha colonne tipo: t, T, o, h, l, c, v, n, s, i
        df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True)

        # tieni solo quello che ci serve
        df = df[["timestamp", "o", "h", "l", "c", "v"]].copy()
        df.rename(
            columns={
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
            },
            inplace=True,
        )

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    # ==============================
    #       INDICATORI TECNICI
    # ==============================
    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        return ta.trend.EMAIndicator(data, window=period).ema_indicator()

    def calculate_macd(self, data: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        macd = ta.trend.MACD(data)
        return macd.macd(), macd.macd_signal(), macd.macd_diff()

    def calculate_rsi(self, data: pd.Series, period: int) -> pd.Series:
        return ta.momentum.RSIIndicator(data, window=period).rsi()

    def calculate_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> pd.Series:
        return ta.volatility.AverageTrueRange(
            high, low, close, window=period
        ).average_true_range()

    def calculate_pivot_points(
        self, high: float, low: float, close: float
    ) -> Dict[str, float]:
        pp = (high + low + close) / 3.0
        s1 = (2 * pp) - high
        s2 = pp - (high - low)
        r1 = (2 * pp) - low
        r2 = pp + (high - low)
        return {"pp": pp, "s1": s1, "s2": s2, "r1": r1, "r2": r2}

    # ==============================
    #   FUNDING / OI (from Hyperliquid API)
    # ==============================
    def _get_asset_contexts(self) -> Dict[str, Dict]:
        """
        Fetch metaAndAssetCtxs from Hyperliquid API.
        Returns dict mapping coin name to its context (OI, funding, etc.)
        Cached for 60 seconds to avoid excessive API calls.
        """
        cache_key = '_asset_contexts_cache'
        cache_time_key = '_asset_contexts_time'

        # Check cache (60 second TTL)
        now = datetime.now()
        if hasattr(self, cache_key) and hasattr(self, cache_time_key):
            cache_age = (now - getattr(self, cache_time_key)).total_seconds()
            if cache_age < 60:
                return getattr(self, cache_key)

        try:
            # Determine API URL
            base_url = getattr(self, 'base_url', 'https://api.hyperliquid.xyz')
            if 'testnet' in base_url:
                api_url = "https://api.hyperliquid-testnet.xyz/info"
            else:
                api_url = "https://api.hyperliquid.xyz/info"

            response = requests.post(
                api_url,
                json={"type": "metaAndAssetCtxs"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # data = [meta, assetCtxs]
            # meta contains universe (list of assets)
            # assetCtxs contains funding, openInterest, etc.
            if len(data) >= 2:
                meta = data[0]
                asset_ctxs = data[1]

                # Build mapping: coin name -> context
                result = {}
                universe = meta.get('universe', [])

                for i, asset in enumerate(universe):
                    coin_name = asset.get('name', '')
                    if i < len(asset_ctxs):
                        ctx = asset_ctxs[i]
                        # Safe float conversion with None handling
                        def safe_float(val, default=0.0):
                            if val is None:
                                return default
                            try:
                                return float(val)
                            except (ValueError, TypeError):
                                return default

                        result[coin_name] = {
                            'funding': safe_float(ctx.get('funding')),
                            'open_interest': safe_float(ctx.get('openInterest')),
                            'mark_price': safe_float(ctx.get('markPx')),
                            'oracle_price': safe_float(ctx.get('oraclePx')),
                            'premium': safe_float(ctx.get('premium')),
                        }

                # Cache result
                setattr(self, cache_key, result)
                setattr(self, cache_time_key, now)
                return result

            return {}
        except Exception as e:
            print(f"[INDICATORS] Warning: Failed to fetch asset contexts: {e}")
            return {}

    def get_funding_rate(self, coin: str) -> float:
        """
        Get current funding rate for a coin from Hyperliquid.
        Funding rate is expressed as hourly rate (multiply by 24 for daily, by 8760 for annual).
        """
        try:
            contexts = self._get_asset_contexts()
            coin_upper = coin.upper()

            if coin_upper in contexts:
                funding = contexts[coin_upper].get('funding', 0)
                return funding
            return 0.0
        except Exception as e:
            print(f"[INDICATORS] Error getting funding rate for {coin}: {e}")
            return 0.0

    def get_open_interest(self, coin: str) -> Dict[str, float]:
        """
        Get open interest for a coin from Hyperliquid.
        Returns OI in USD notional value.
        """
        try:
            contexts = self._get_asset_contexts()
            coin_upper = coin.upper()

            if coin_upper in contexts:
                oi = contexts[coin_upper].get('open_interest', 0)
                # For average, we'd need historical data - for now return same as latest
                return {"latest": oi, "average": oi}
            return {"latest": 0.0, "average": 0.0}
        except Exception as e:
            print(f"[INDICATORS] Error getting open interest for {coin}: {e}")
            return {"latest": 0.0, "average": 0.0}

    # ==============================
    #   CORRELATION (BTC/ETH/SOL)
    # ==============================
    def calculate_correlations(self, coins: List[str] = None, window: int = 20) -> Dict[str, float]:
        """
        Calculate price return correlations between coins.
        Uses 15m timeframe returns over specified window.
        Cached for 5 minutes to reduce API calls.

        Args:
            coins: List of coins to analyze (default: BTC, ETH, SOL)
            window: Number of periods for correlation calculation (default: 20)

        Returns:
            Dict with correlation pairs, e.g.:
            {"BTC_ETH": 0.85, "BTC_SOL": 0.72, "ETH_SOL": 0.78}
        """
        # Check cache (5 min TTL - correlations don't change fast)
        cache_key = '_correlations_cache'
        cache_time_key = '_correlations_time'
        now = datetime.now()

        if hasattr(self, cache_key) and hasattr(self, cache_time_key):
            cache_age = (now - getattr(self, cache_time_key)).total_seconds()
            if cache_age < 300:  # 5 minutes
                return getattr(self, cache_key)

        if coins is None:
            coins = ["BTC", "ETH", "SOL"]

        try:
            import time

            # Fetch price data for all coins with delay to avoid rate limiting
            price_data = {}
            for idx, coin in enumerate(coins):
                try:
                    # Small delay between API calls to avoid 429
                    if idx > 0:
                        time.sleep(0.3)

                    df = self.fetch_ohlcv(coin.upper(), "15m", limit=window + 10)
                    if len(df) >= window:
                        # Calculate returns
                        df['returns'] = df['close'].pct_change()
                        price_data[coin.upper()] = df['returns'].tail(window).values
                except Exception as e:
                    print(f"[INDICATORS] Warning: Could not fetch data for {coin}: {e}")
                    continue

            if len(price_data) < 2:
                return {}

            # Build DataFrame of returns
            returns_df = pd.DataFrame(price_data)

            # Calculate correlation matrix
            corr_matrix = returns_df.corr()

            # Extract correlation pairs
            result = {}
            coins_list = list(price_data.keys())
            for i, coin1 in enumerate(coins_list):
                for coin2 in coins_list[i+1:]:
                    pair_key = f"{coin1}_{coin2}"
                    corr_value = corr_matrix.loc[coin1, coin2]
                    if pd.notna(corr_value):
                        result[pair_key] = round(corr_value, 4)

            # Cache result
            setattr(self, cache_key, result)
            setattr(self, cache_time_key, now)

            return result
        except Exception as e:
            print(f"[INDICATORS] Error calculating correlations: {e}")
            return {}

    # ==============================
    #   ANALISI COMPLETA A 15m
    # ==============================
    def get_complete_analysis(self, ticker: str) -> Dict:
        coin = ticker.upper()

        # 1) DATI 15 MINUTI (intraday principale)
        df_15m = self.fetch_ohlcv(coin, "15m", limit=200)

        df_15m["ema_20"] = self.calculate_ema(df_15m["close"], 20)
        macd_line, signal_line, macd_diff = self.calculate_macd(df_15m["close"])
        df_15m["macd"] = macd_diff
        df_15m["rsi_7"] = self.calculate_rsi(df_15m["close"], 7)
        df_15m["rsi_14"] = self.calculate_rsi(df_15m["close"], 14)

        last_10_15m = df_15m.tail(10)

        # 2) CONTESTO "longer term" sempre a 15m ma su finestra più lunga
        longer_term = df_15m.tail(50).copy()
        longer_term["ema_20"] = self.calculate_ema(longer_term["close"], 20)
        longer_term["ema_50"] = self.calculate_ema(longer_term["close"], 50)
        longer_term["atr_3"] = self.calculate_atr(
            longer_term["high"], longer_term["low"], longer_term["close"], 3
        )
        longer_term["atr_14"] = self.calculate_atr(
            longer_term["high"], longer_term["low"], longer_term["close"], 14
        )
        macd_15m_long, _, macd_diff_15m_long = self.calculate_macd(
            longer_term["close"]
        )
        longer_term["macd"] = macd_diff_15m_long
        longer_term["rsi_14"] = self.calculate_rsi(longer_term["close"], 14)

        avg_volume = longer_term["volume"].tail(20).mean()
        last_10_longer = longer_term.tail(10)

        # 3) PIVOT POINTS daily
        df_daily = self.fetch_ohlcv(coin, "1d", limit=2)
        if len(df_daily) >= 2:
            prev_day = df_daily.iloc[-2]
            pivot_points = self.calculate_pivot_points(
                prev_day["high"], prev_day["low"], prev_day["close"]
            )
        else:
            last = df_15m.iloc[-1]
            pivot_points = self.calculate_pivot_points(
                last["high"], last["low"], last["close"]
            )

        oi_data = self.get_open_interest(coin)
        funding_rate = self.get_funding_rate(coin)
        correlations = self.calculate_correlations()

        current_15m = df_15m.iloc[-1]
        current_longer = longer_term.iloc[-1]

        result = {
            "ticker": ticker,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            
            "current": {
                "price": current_15m["close"],
                "ema20": current_15m["ema_20"],
                "macd": current_15m["macd"],
                "rsi_7": current_15m["rsi_7"],
            },
            "volume": self.get_orderbook_volume(ticker),
            "pivot_points": pivot_points,

            "derivatives": {
                "open_interest_latest": oi_data["latest"],
                "open_interest_average": oi_data["average"],
                "funding_rate": funding_rate,
                "correlations": correlations,
            },

            "intraday": {
                "mid_prices": last_10_15m["close"].tolist(),
                "ema_20": last_10_15m["ema_20"].tolist(),
                "macd": last_10_15m["macd"].tolist(),
                "rsi_7": last_10_15m["rsi_7"].tolist(),
                "rsi_14": last_10_15m["rsi_14"].tolist(),
            },

            "longer_term_15m": {
                "ema_20_current": current_longer["ema_20"],
                "ema_50_current": current_longer["ema_50"],
                "atr_3_current": current_longer["atr_3"],
                "atr_14_current": current_longer["atr_14"],
                "volume_current": current_longer["volume"],
                "volume_average": avg_volume,
                "macd_series": last_10_longer["macd"].tolist(),
                "rsi_14_series": last_10_longer["rsi_14"].tolist(),
            },
        }
        return result

    def format_output(self, data: Dict) -> str:
        output = f"\n<{data['ticker']}_data>\n"
        output += f"Timestamp: {data['timestamp']} (UTC) (Hyperliquid, 15m)\n"
        output += f"\n"

        curr = data["current"]
        output += (
            f"current_price = {curr['price']:.1f}, "
            f"current_ema20 = {curr['ema20']:.3f}, "
            f"current_macd = {curr['macd']:.3f}, "
            f"current_rsi (7 period) = {curr['rsi_7']:.3f}\n\n"
        )
        output += f"Volume: {data['volume']}\n\n"

        pivot = data["pivot_points"]
        output += "Pivot Points (based on previous day):\n"
        output += (
            f"R2 = {pivot['r2']:.2f}, R1 = {pivot['r1']:.2f}, "
            f"PP = {pivot['pp']:.2f}, "
            f"S1 = {pivot['s1']:.2f}, S2 = {pivot['s2']:.2f}\n\n"
        )

        deriv = data["derivatives"]
        output += (
            f"In addition, here is the latest {data['ticker']} derivatives data from Hyperliquid:\n"
        )
        output += (
            f"Open Interest: ${deriv['open_interest_latest']:,.0f} USD\n"
        )
        output += f"Funding Rate: {deriv['funding_rate']:.6f} (hourly, positive = longs pay shorts)\n"
        if deriv.get('correlations'):
            corr_str = ", ".join([f"{k}: {v:.2f}" for k, v in deriv['correlations'].items()])
            output += f"Correlations (20-period returns): {corr_str}\n"
        output += "\n"

        intra = data["intraday"]
        output += "Intraday series (15m, oldest → latest):\n"
        output += (
            f"Mid prices: {[round(x, 1) for x in intra['mid_prices']]}\n"
            f"EMA indicators (20-period): {[round(x, 3) for x in intra['ema_20']]}\n"
            f"MACD indicators: {[round(x, 3) for x in intra['macd']]}\n"
            f"RSI indicators (7-Period): {[round(x, 3) for x in intra['rsi_7']]}\n"
            f"RSI indicators (14-Period): {[round(x, 3) for x in intra['rsi_14']]}\n\n"
        )

        lt = data["longer_term_15m"]
        output += "Longer-term context (still 15-minute timeframe, wider window):\n"
        output += (
            f"20-Period EMA: {lt['ema_20_current']:.3f} vs. "
            f"50-Period EMA: {lt['ema_50_current']:.3f}\n"
            f"3-Period ATR: {lt['atr_3_current']:.3f} vs. "
            f"14-Period ATR: {lt['atr_14_current']:.3f}\n"
            f"Current Volume: {lt['volume_current']:.3f} vs. "
            f"Average Volume: {lt['volume_average']:.3f}\n"
            f"MACD indicators: {[round(x, 3) for x in lt['macd_series']]}\n"
            f"RSI indicators (14-Period): {[round(x, 3) for x in lt['rsi_14_series']]}\n"
        )
        output += f"<{data['ticker']}_data>\n"
        return output


def analyze_multiple_tickers(tickers: List[str], testnet: bool = True) -> str:
    analyzer = CryptoTechnicalAnalysisHL(testnet=testnet)
    full_output = ""
    datas = []
    data = None
    for ticker in tickers:
        try:
            data = analyzer.get_complete_analysis(ticker)
            datas.append(data)
            full_output += analyzer.format_output(data)
        except Exception as e:
            print(f"Errore durante l'analisi di {ticker}: {e}")
    return full_output, datas


# if __name__ == "__main__":
#     tickers = ["BTC", "ETH", "BNB"]
#     result = analyze_multiple_tickers(tickers, testnet=True)
#     print(result)
