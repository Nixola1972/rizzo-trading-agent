"""
Backtester Module
=================
Sistema di backtesting per testare diverse configurazioni di pesi sui dati storici.

Permette di:
1. Scaricare dati storici (candele) da yfinance
2. Calcolare indicatori tecnici per ogni candela
3. Applicare signal scoring con pesi configurabili
4. Simulare trade e calcolare performance

Uso:
    from backtester import Backtester

    bt = Backtester(symbols=['BTC', 'ETH', 'SOL'], days=90)
    results = bt.run(weights_config)
    bt.compare_configs([config1, config2, config3])
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None
    print("Warning: yfinance not installed. Install with: pip install yfinance")


@dataclass
class WeightsConfig:
    """Configurazione dei pesi per il backtesting."""
    name: str = "default"

    # Pesi BEARISH
    weight_fear_greed_fear: float = 8.0
    weight_rsi_overbought: float = 15.0
    weight_trend_bearish: float = 10.0
    weight_forecast_negative: float = 6.0
    weight_macd_negative: float = 5.0
    weight_volume_bearish: float = 4.0

    # Pesi BULLISH
    weight_fear_greed_greed: float = 8.0
    weight_rsi_oversold: float = 15.0
    weight_trend_bullish: float = 10.0
    weight_forecast_positive: float = 6.0
    weight_macd_positive: float = 5.0
    weight_volume_bullish: float = 4.0

    # Soglie decisionali
    score_threshold_open: float = 15.0
    score_threshold_strong: float = 25.0
    score_threshold_hold: float = 10.0

    # Soglie indicatori
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    fear_greed_fear: float = 30.0
    fear_greed_greed: float = 60.0
    forecast_min_change: float = 0.3

    # Trading parameters
    leverage: float = 3.0
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 10.0
    trailing_stop_pct: float = 7.0
    trailing_activation_pct: float = 3.0

    def to_dict(self) -> dict:
        """Converte in dizionario per serializzazione."""
        return {
            'name': self.name,
            'weights_bearish': {
                'fear_greed_fear': self.weight_fear_greed_fear,
                'rsi_overbought': self.weight_rsi_overbought,
                'trend_bearish': self.weight_trend_bearish,
                'forecast_negative': self.weight_forecast_negative,
                'macd_negative': self.weight_macd_negative,
                'volume_bearish': self.weight_volume_bearish,
            },
            'weights_bullish': {
                'fear_greed_greed': self.weight_fear_greed_greed,
                'rsi_oversold': self.weight_rsi_oversold,
                'trend_bullish': self.weight_trend_bullish,
                'forecast_positive': self.weight_forecast_positive,
                'macd_positive': self.weight_macd_positive,
                'volume_bullish': self.weight_volume_bullish,
            },
            'thresholds': {
                'score_open': self.score_threshold_open,
                'score_strong': self.score_threshold_strong,
                'score_hold': self.score_threshold_hold,
            },
            'trading': {
                'leverage': self.leverage,
                'take_profit_pct': self.take_profit_pct,
                'stop_loss_pct': self.stop_loss_pct,
                'trailing_stop_pct': self.trailing_stop_pct,
                'trailing_activation_pct': self.trailing_activation_pct,
            }
        }

    @classmethod
    def from_env(cls, name: str = "from_env") -> 'WeightsConfig':
        """Crea config dai valori .env attuali."""
        from dotenv import load_dotenv
        load_dotenv()

        def get(key, default):
            try:
                return float(os.getenv(key, default))
            except:
                return default

        return cls(
            name=name,
            weight_fear_greed_fear=get('WEIGHT_FEAR_GREED_FEAR', 8.0),
            weight_rsi_overbought=get('WEIGHT_RSI_OVERBOUGHT', 15.0),
            weight_trend_bearish=get('WEIGHT_TREND_BEARISH', 10.0),
            weight_forecast_negative=get('WEIGHT_FORECAST_NEGATIVE', 6.0),
            weight_macd_negative=get('WEIGHT_MACD_NEGATIVE', 5.0),
            weight_volume_bearish=get('WEIGHT_VOLUME_BEARISH', 4.0),
            weight_fear_greed_greed=get('WEIGHT_FEAR_GREED_GREED', 8.0),
            weight_rsi_oversold=get('WEIGHT_RSI_OVERSOLD', 15.0),
            weight_trend_bullish=get('WEIGHT_TREND_BULLISH', 10.0),
            weight_forecast_positive=get('WEIGHT_FORECAST_POSITIVE', 6.0),
            weight_macd_positive=get('WEIGHT_MACD_POSITIVE', 5.0),
            weight_volume_bullish=get('WEIGHT_VOLUME_BULLISH', 4.0),
            score_threshold_open=get('SCORE_THRESHOLD_OPEN', 15.0),
            score_threshold_strong=get('SCORE_THRESHOLD_STRONG', 25.0),
            score_threshold_hold=get('SCORE_THRESHOLD_HOLD', 10.0),
            rsi_overbought=get('RSI_OVERBOUGHT_THRESHOLD', 70.0),
            rsi_oversold=get('RSI_OVERSOLD_THRESHOLD', 30.0),
            fear_greed_fear=get('FEAR_GREED_FEAR_THRESHOLD', 30.0),
            fear_greed_greed=get('FEAR_GREED_GREED_THRESHOLD', 60.0),
            forecast_min_change=get('FORECAST_MIN_CHANGE_PCT', 0.3),
            leverage=get('LEVERAGE', 3.0),
            take_profit_pct=get('TAKE_PROFIT_PERCENT', 5.0),
            stop_loss_pct=get('INITIAL_STOP_LOSS_PERCENT', 10.0),
            trailing_stop_pct=get('TRAILING_STOP_PERCENT', 7.0),
            trailing_activation_pct=get('TRAILING_STOP_ACTIVATION_PERCENT', 3.0),
        )


@dataclass
class Trade:
    """Rappresenta un singolo trade nel backtest."""
    symbol: str
    direction: str  # LONG or SHORT
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # take_profit, stop_loss, trailing_stop, signal_reversal
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    leverage: float = 1.0
    peak_price: float = 0.0
    score_at_entry: float = 0.0

    @property
    def duration_minutes(self) -> float:
        if self.exit_time and self.entry_time:
            return (self.exit_time - self.entry_time).total_seconds() / 60
        return 0


@dataclass
class BacktestResult:
    """Risultato di un backtest."""
    config: WeightsConfig
    trades: List[Trade] = field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return len([t for t in self.trades if t.pnl_pct > 0])

    @property
    def losing_trades(self) -> int:
        return len([t for t in self.trades if t.pnl_pct <= 0])

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def total_pnl_pct(self) -> float:
        return sum(t.pnl_pct for t in self.trades)

    @property
    def avg_win_pct(self) -> float:
        wins = [t.pnl_pct for t in self.trades if t.pnl_pct > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss_pct(self) -> float:
        losses = [t.pnl_pct for t in self.trades if t.pnl_pct <= 0]
        return sum(losses) / len(losses) if losses else 0.0

    @property
    def max_win_pct(self) -> float:
        wins = [t.pnl_pct for t in self.trades if t.pnl_pct > 0]
        return max(wins) if wins else 0.0

    @property
    def max_loss_pct(self) -> float:
        losses = [t.pnl_pct for t in self.trades if t.pnl_pct <= 0]
        return min(losses) if losses else 0.0

    @property
    def profit_factor(self) -> float:
        total_wins = sum(t.pnl_pct for t in self.trades if t.pnl_pct > 0)
        total_losses = abs(sum(t.pnl_pct for t in self.trades if t.pnl_pct <= 0))
        if total_losses == 0:
            return float('inf') if total_wins > 0 else 0.0
        return total_wins / total_losses

    @property
    def avg_duration_minutes(self) -> float:
        durations = [t.duration_minutes for t in self.trades if t.duration_minutes > 0]
        return sum(durations) / len(durations) if durations else 0.0

    @property
    def exit_reasons(self) -> Dict[str, int]:
        reasons = {}
        for t in self.trades:
            r = t.exit_reason or 'unknown'
            reasons[r] = reasons.get(r, 0) + 1
        return reasons

    def to_dict(self) -> dict:
        return {
            'config_name': self.config.name,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate * 100, 2),
            'total_pnl_pct': round(self.total_pnl_pct, 2),
            'avg_win_pct': round(self.avg_win_pct, 2),
            'avg_loss_pct': round(self.avg_loss_pct, 2),
            'max_win_pct': round(self.max_win_pct, 2),
            'max_loss_pct': round(self.max_loss_pct, 2),
            'profit_factor': round(self.profit_factor, 2),
            'avg_duration_minutes': round(self.avg_duration_minutes, 1),
            'exit_reasons': self.exit_reasons,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
        }


class Backtester:
    """
    Motore di backtesting per testare configurazioni di pesi.
    """

    SYMBOL_MAP = {
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD',
        'SOL': 'SOL-USD',
    }

    def __init__(self, symbols: List[str] = None, days: int = 90, interval: str = '15m'):
        """
        Inizializza il backtester.

        Args:
            symbols: Lista di simboli da testare (default: BTC, ETH, SOL)
            days: Giorni di dati storici da scaricare
            interval: Intervallo candele (1m, 5m, 15m, 1h, 1d)
        """
        self.symbols = symbols or ['BTC', 'ETH', 'SOL']
        self.days = days
        self.interval = interval
        self.data: Dict[str, pd.DataFrame] = {}
        self._fear_greed_cache: Dict[str, int] = {}

    def download_data(self, verbose: bool = True) -> bool:
        """
        Scarica i dati storici da yfinance.

        Returns:
            True se download ok, False altrimenti
        """
        if yf is None:
            print("ERROR: yfinance not installed")
            return False

        # yfinance limita i dati a 15m a 60 giorni
        actual_days = min(self.days, 60) if self.interval in ['1m', '5m', '15m'] else self.days

        end_date = datetime.now()
        start_date = end_date - timedelta(days=actual_days)

        if verbose:
            print(f"Downloading {actual_days} days of {self.interval} data...")

        for symbol in self.symbols:
            yf_symbol = self.SYMBOL_MAP.get(symbol, f"{symbol}-USD")

            try:
                if verbose:
                    print(f"  Downloading {symbol} ({yf_symbol})...")

                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(start=start_date, end=end_date, interval=self.interval)

                if df.empty:
                    print(f"  WARNING: No data for {symbol}")
                    continue

                # Calcola indicatori
                df = self._calculate_indicators(df)
                self.data[symbol] = df

                if verbose:
                    print(f"    Got {len(df)} candles")

            except Exception as e:
                print(f"  ERROR downloading {symbol}: {e}")
                continue

        return len(self.data) > 0

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcola indicatori tecnici per il dataframe."""

        # EMA 20
        df['ema20'] = df['Close'].ewm(span=20, adjust=False).mean()

        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # ATR (per trailing stop)
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()

        # Volume ratio (simulato come random per backtest se non disponibile)
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            df['volume_ratio'] = df['Volume'].rolling(5).mean() / df['Volume'].rolling(20).mean()
        else:
            df['volume_ratio'] = 1.0

        # Rimuovi NaN
        df = df.dropna()

        return df

    def _calculate_score(
        self,
        price: float,
        ema20: float,
        rsi: float,
        macd: float,
        fear_greed: int,
        forecast_change_pct: float,
        volume_ratio: float,
        config: WeightsConfig
    ) -> Tuple[float, str]:
        """
        Calcola lo score con la configurazione specificata.

        Returns:
            Tuple di (net_score, direction)
        """
        score_bullish = 0.0
        score_bearish = 0.0

        # Fear & Greed
        if fear_greed < config.fear_greed_fear:
            intensity = (config.fear_greed_fear - fear_greed) / config.fear_greed_fear
            score_bearish += config.weight_fear_greed_fear * intensity
        elif fear_greed > config.fear_greed_greed:
            intensity = (fear_greed - config.fear_greed_greed) / (100 - config.fear_greed_greed)
            score_bullish += config.weight_fear_greed_greed * intensity

        # RSI
        if rsi > config.rsi_overbought:
            intensity = min((rsi - config.rsi_overbought) / (100 - config.rsi_overbought), 1.0)
            score_bearish += config.weight_rsi_overbought * intensity
        elif rsi < config.rsi_oversold:
            intensity = min((config.rsi_oversold - rsi) / config.rsi_oversold, 1.0)
            score_bullish += config.weight_rsi_oversold * intensity

        # Trend (Price vs EMA + MACD)
        price_above_ema = price > ema20
        macd_positive = macd > 0

        if not price_above_ema and not macd_positive:
            score_bearish += config.weight_trend_bearish
        elif price_above_ema and macd_positive:
            score_bullish += config.weight_trend_bullish
        else:
            # Segnali misti
            if macd > 0:
                score_bullish += config.weight_macd_positive * 0.5
            elif macd < 0:
                score_bearish += config.weight_macd_negative * 0.5

        # Forecast (simulato come momentum price)
        if forecast_change_pct < -config.forecast_min_change:
            intensity = min(abs(forecast_change_pct) / 2.0, 1.0)
            score_bearish += config.weight_forecast_negative * intensity
        elif forecast_change_pct > config.forecast_min_change:
            intensity = min(abs(forecast_change_pct) / 2.0, 1.0)
            score_bullish += config.weight_forecast_positive * intensity

        # Volume
        if volume_ratio > 1.5:
            intensity = min((volume_ratio - 1) / 2, 1.0)
            score_bullish += config.weight_volume_bullish * intensity
        elif volume_ratio < 0.67:
            intensity = min((1 - volume_ratio) / 0.5, 1.0)
            score_bearish += config.weight_volume_bearish * intensity

        net_score = score_bullish - score_bearish

        if net_score >= config.score_threshold_open:
            direction = 'LONG'
        elif net_score <= -config.score_threshold_open:
            direction = 'SHORT'
        else:
            direction = 'HOLD'

        return net_score, direction

    def _simulate_fear_greed(self, timestamp: datetime, rsi: float) -> int:
        """
        Simula Fear & Greed index basandosi su RSI e data.
        In un backtest reale, dovresti usare dati storici reali.
        """
        # Usa cache per consistenza
        date_key = timestamp.strftime('%Y-%m-%d')
        if date_key in self._fear_greed_cache:
            return self._fear_greed_cache[date_key]

        # Simula basandosi su RSI con rumore
        np.random.seed(int(timestamp.timestamp()) % 10000)
        base = rsi * 0.7 + np.random.uniform(-10, 10)
        fg = int(max(0, min(100, base)))

        self._fear_greed_cache[date_key] = fg
        return fg

    def run(self, config: WeightsConfig, verbose: bool = False) -> BacktestResult:
        """
        Esegue il backtest con la configurazione specificata.

        Args:
            config: Configurazione dei pesi
            verbose: Se stampare log dettagliati

        Returns:
            BacktestResult con tutti i trade simulati
        """
        if not self.data:
            print("No data loaded. Call download_data() first.")
            return BacktestResult(config=config)

        result = BacktestResult(config=config)

        for symbol, df in self.data.items():
            if verbose:
                print(f"\nBacktesting {symbol}...")

            trades = self._backtest_symbol(symbol, df, config, verbose)
            result.trades.extend(trades)

        if result.trades:
            result.start_date = min(t.entry_time for t in result.trades)
            result.end_date = max(t.exit_time for t in result.trades if t.exit_time)

        return result

    def _backtest_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        config: WeightsConfig,
        verbose: bool
    ) -> List[Trade]:
        """Esegue backtest su un singolo simbolo."""
        trades = []
        current_trade: Optional[Trade] = None

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            timestamp = row.name.to_pydatetime() if hasattr(row.name, 'to_pydatetime') else row.name

            price = row['Close']
            ema20 = row['ema20']
            rsi = row['rsi']
            macd = row['macd']
            volume_ratio = row.get('volume_ratio', 1.0)

            # Simula forecast come momentum recente
            price_change_pct = ((price - prev_row['Close']) / prev_row['Close']) * 100
            forecast_change = price_change_pct * 0.5  # Simula forecast

            # Simula fear & greed
            fear_greed = self._simulate_fear_greed(timestamp, rsi)

            # Calcola score
            net_score, direction = self._calculate_score(
                price, ema20, rsi, macd, fear_greed, forecast_change, volume_ratio, config
            )

            # Gestisci posizione aperta
            if current_trade:
                # Aggiorna peak price
                if current_trade.direction == 'LONG':
                    current_trade.peak_price = max(current_trade.peak_price, price)
                    pnl_from_entry = ((price - current_trade.entry_price) / current_trade.entry_price) * 100
                    pnl_from_peak = ((price - current_trade.peak_price) / current_trade.peak_price) * 100
                else:  # SHORT
                    current_trade.peak_price = min(current_trade.peak_price, price)
                    pnl_from_entry = ((current_trade.entry_price - price) / current_trade.entry_price) * 100
                    pnl_from_peak = ((current_trade.peak_price - price) / current_trade.peak_price) * 100

                pnl_real = pnl_from_entry * config.leverage
                pnl_from_peak_real = pnl_from_peak * config.leverage

                # Determina se attivare trailing
                trailing_active = pnl_real >= config.trailing_activation_pct

                should_close = False
                exit_reason = None

                # Check Take Profit
                if pnl_real >= config.take_profit_pct:
                    should_close = True
                    exit_reason = 'take_profit'

                # Check Stop Loss (prima del trailing)
                elif not trailing_active and pnl_real <= -config.stop_loss_pct:
                    should_close = True
                    exit_reason = 'stop_loss'

                # Check Trailing Stop
                elif trailing_active and pnl_from_peak_real <= -config.trailing_stop_pct:
                    should_close = True
                    exit_reason = 'trailing_stop'

                # Check Signal Reversal
                elif (current_trade.direction == 'LONG' and direction == 'SHORT') or \
                     (current_trade.direction == 'SHORT' and direction == 'LONG'):
                    should_close = True
                    exit_reason = 'signal_reversal'

                if should_close:
                    current_trade.exit_time = timestamp
                    current_trade.exit_price = price
                    current_trade.exit_reason = exit_reason
                    current_trade.pnl_pct = pnl_real
                    trades.append(current_trade)

                    if verbose:
                        emoji = "✅" if current_trade.pnl_pct > 0 else "❌"
                        print(f"  {emoji} Close {current_trade.direction} @ {price:.2f} "
                              f"({exit_reason}) P&L: {current_trade.pnl_pct:+.2f}%")

                    current_trade = None

            # Apri nuova posizione se non ce n'è una
            if current_trade is None and direction in ['LONG', 'SHORT']:
                current_trade = Trade(
                    symbol=symbol,
                    direction=direction,
                    entry_time=timestamp,
                    entry_price=price,
                    peak_price=price,
                    leverage=config.leverage,
                    score_at_entry=net_score
                )

                if verbose:
                    print(f"  📈 Open {direction} @ {price:.2f} (score: {net_score:.1f})")

        # Chiudi eventuale trade aperto alla fine
        if current_trade:
            last_row = df.iloc[-1]
            price = last_row['Close']
            timestamp = last_row.name.to_pydatetime() if hasattr(last_row.name, 'to_pydatetime') else last_row.name

            if current_trade.direction == 'LONG':
                pnl = ((price - current_trade.entry_price) / current_trade.entry_price) * 100
            else:
                pnl = ((current_trade.entry_price - price) / current_trade.entry_price) * 100

            current_trade.exit_time = timestamp
            current_trade.exit_price = price
            current_trade.exit_reason = 'end_of_data'
            current_trade.pnl_pct = pnl * config.leverage
            trades.append(current_trade)

        return trades

    def compare_configs(
        self,
        configs: List[WeightsConfig],
        verbose: bool = False
    ) -> List[BacktestResult]:
        """
        Confronta multiple configurazioni.

        Args:
            configs: Lista di configurazioni da testare
            verbose: Se stampare log dettagliati

        Returns:
            Lista di BacktestResult ordinati per performance
        """
        results = []

        print(f"\nComparing {len(configs)} configurations...")
        print("=" * 60)

        for i, config in enumerate(configs):
            print(f"\n[{i+1}/{len(configs)}] Testing: {config.name}")
            result = self.run(config, verbose=verbose)
            results.append(result)

            print(f"  Trades: {result.total_trades}, "
                  f"Win Rate: {result.win_rate*100:.1f}%, "
                  f"Profit Factor: {result.profit_factor:.2f}, "
                  f"Total P&L: {result.total_pnl_pct:+.2f}%")

        # Ordina per profit factor
        results.sort(key=lambda r: r.profit_factor, reverse=True)

        print("\n" + "=" * 60)
        print("RANKING (by Profit Factor):")
        print("-" * 60)

        for i, result in enumerate(results):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
            print(f"{medal} {i+1}. {result.config.name:20s} | "
                  f"PF: {result.profit_factor:6.2f} | "
                  f"WR: {result.win_rate*100:5.1f}% | "
                  f"P&L: {result.total_pnl_pct:+7.2f}%")

        return results

    def generate_report(self, results: List[BacktestResult]) -> str:
        """Genera un report markdown dei risultati."""

        lines = [
            "# Backtest Results Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\nSymbols: {', '.join(self.symbols)}",
            f"Period: {self.days} days",
            f"Interval: {self.interval}",
            "\n## Summary",
            "\n| Config | Trades | Win Rate | Profit Factor | Total P&L |",
            "|--------|--------|----------|---------------|-----------|",
        ]

        for r in results:
            lines.append(
                f"| {r.config.name} | {r.total_trades} | "
                f"{r.win_rate*100:.1f}% | {r.profit_factor:.2f} | "
                f"{r.total_pnl_pct:+.2f}% |"
            )

        if results:
            best = results[0]
            lines.extend([
                "\n## Best Configuration",
                f"\n**{best.config.name}**",
                f"\n- Profit Factor: {best.profit_factor:.2f}",
                f"- Win Rate: {best.win_rate*100:.1f}%",
                f"- Total P&L: {best.total_pnl_pct:+.2f}%",
                f"- Avg Win: {best.avg_win_pct:+.2f}%",
                f"- Avg Loss: {best.avg_loss_pct:.2f}%",
                f"- Max Win: {best.max_win_pct:+.2f}%",
                f"- Max Loss: {best.max_loss_pct:.2f}%",
                "\n### Exit Reasons",
            ])

            for reason, count in best.exit_reasons.items():
                lines.append(f"- {reason}: {count}")

            lines.extend([
                "\n### Weights Configuration",
                "```json",
                json.dumps(best.config.to_dict(), indent=2),
                "```",
            ])

        return "\n".join(lines)


# Esempio di utilizzo
if __name__ == "__main__":
    # Crea configurazioni da testare
    configs = [
        WeightsConfig(name="Current (.env)", **WeightsConfig.from_env().__dict__),
        WeightsConfig(name="RSI=12", weight_rsi_overbought=12.0, weight_rsi_oversold=12.0),
        WeightsConfig(name="RSI=18", weight_rsi_overbought=18.0, weight_rsi_oversold=18.0),
        WeightsConfig(name="Threshold=12", score_threshold_open=12.0),
        WeightsConfig(name="Threshold=18", score_threshold_open=18.0),
        WeightsConfig(name="Aggressive",
                      score_threshold_open=10.0,
                      take_profit_pct=3.0,
                      leverage=5.0),
    ]

    # Inizializza backtester
    bt = Backtester(symbols=['BTC', 'ETH'], days=30, interval='1h')

    # Scarica dati
    if bt.download_data():
        # Confronta configurazioni
        results = bt.compare_configs(configs)

        # Genera report
        report = bt.generate_report(results)

        # Salva report
        with open('backtest_report.md', 'w') as f:
            f.write(report)

        print(f"\nReport saved to backtest_report.md")
