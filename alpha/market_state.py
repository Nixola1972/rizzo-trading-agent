"""
Market State Representation
===========================

Defines the state representation for the RL agent.
This is the "observation" that the agent sees at each timestep.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime


class ActionType(Enum):
    """Possible actions the agent can take."""
    HOLD = 0
    OPEN_LONG = 1
    OPEN_SHORT = 2
    CLOSE = 3


@dataclass
class Action:
    """Action chosen by the agent."""
    action_type: ActionType
    symbol: str = "BTC"
    leverage: int = 1
    position_size_pct: float = 1.0  # Percentage of base position
    confidence: float = 0.0  # Agent's confidence in this action
    reasoning: str = ""  # Optional reasoning

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "action_type": self.action_type.name,
            "symbol": self.symbol,
            "leverage": self.leverage,
            "position_size_pct": self.position_size_pct,
            "confidence": self.confidence,
            "reasoning": self.reasoning
        }


@dataclass
class PositionState:
    """Current position state (if any)."""
    has_position: bool = False
    symbol: str = ""
    direction: str = ""  # "LONG" or "SHORT"
    entry_price: float = 0.0
    current_price: float = 0.0
    size_usd: float = 0.0
    leverage: int = 1
    unrealized_pnl_pct: float = 0.0
    duration_hours: float = 0.0
    max_profit_pct: float = 0.0  # MFE
    max_loss_pct: float = 0.0  # MAE

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector for neural network input."""
        return np.array([
            1.0 if self.has_position else 0.0,
            1.0 if self.direction == "LONG" else (-1.0 if self.direction == "SHORT" else 0.0),
            self.unrealized_pnl_pct / 10.0,  # Normalize to ~[-1, 1]
            min(self.duration_hours / 24.0, 1.0),  # Normalize to [0, 1]
            self.leverage / 10.0,  # Normalize to [0, 1]
            self.max_profit_pct / 10.0,
            self.max_loss_pct / 10.0,
        ], dtype=np.float32)


@dataclass
class IndicatorState:
    """Technical indicator state for a single symbol."""
    symbol: str = ""
    price: float = 0.0
    ema20: float = 0.0
    ema50: float = 0.0
    rsi_7: float = 50.0
    rsi_14: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    atr_14: float = 0.0
    volume_ratio: float = 1.0  # bid/ask ratio
    adx: float = 25.0
    bollinger_pct_b: float = 0.5
    obv_trend: float = 0.0  # -1 falling, 0 flat, 1 rising

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector for neural network input."""
        # Normalize all values to roughly [-1, 1] or [0, 1]
        price_vs_ema20 = (self.price - self.ema20) / self.ema20 if self.ema20 > 0 else 0
        price_vs_ema50 = (self.price - self.ema50) / self.ema50 if self.ema50 > 0 else 0

        return np.array([
            np.clip(price_vs_ema20 * 10, -1, 1),  # Price relative to EMA20
            np.clip(price_vs_ema50 * 10, -1, 1),  # Price relative to EMA50
            (self.rsi_7 - 50) / 50,  # RSI7 normalized
            (self.rsi_14 - 50) / 50,  # RSI14 normalized
            np.clip(self.macd / 100, -1, 1),  # MACD normalized
            np.clip(self.macd_histogram / 50, -1, 1),  # Histogram
            (self.adx - 25) / 25,  # ADX centered at 25
            self.bollinger_pct_b * 2 - 1,  # Bollinger %B to [-1, 1]
            np.clip(self.volume_ratio - 1, -1, 1),  # Volume ratio
            self.obv_trend,  # Already -1 to 1
        ], dtype=np.float32)


@dataclass
class SentimentState:
    """Market sentiment state."""
    fear_greed_index: int = 50  # 0-100
    forecast_15m_pct: float = 0.0  # Prophet forecast
    forecast_1h_pct: float = 0.0
    btc_rsi: float = 50.0  # BTC RSI for cross-asset correlation

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector."""
        return np.array([
            (self.fear_greed_index - 50) / 50,  # Normalize to [-1, 1]
            np.clip(self.forecast_15m_pct / 2, -1, 1),  # Forecast
            np.clip(self.forecast_1h_pct / 2, -1, 1),
            (self.btc_rsi - 50) / 50,  # BTC RSI
        ], dtype=np.float32)


@dataclass
class ScoreState:
    """Signal scorer state (from signal_scorer.py)."""
    score_bullish: float = 0.0
    score_bearish: float = 0.0
    net_score: float = 0.0
    direction: str = "HOLD"  # LONG, SHORT, HOLD
    confidence: str = "WEAK"  # WEAK, NORMAL, STRONG

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector."""
        dir_val = 1.0 if self.direction == "LONG" else (-1.0 if self.direction == "SHORT" else 0.0)
        conf_val = 0.33 if self.confidence == "WEAK" else (0.66 if self.confidence == "NORMAL" else 1.0)

        return np.array([
            self.score_bullish / 50,  # Normalize
            self.score_bearish / 50,
            self.net_score / 50,
            dir_val,
            conf_val,
        ], dtype=np.float32)


@dataclass
class MarketState:
    """
    Complete market state observation for the RL agent.

    This combines:
    - Position state (if any)
    - Technical indicators for each symbol
    - Sentiment/macro data
    - Signal scores

    Total state dimension: ~64 features
    """
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Position
    position: PositionState = field(default_factory=PositionState)

    # Per-symbol indicators
    indicators: Dict[str, IndicatorState] = field(default_factory=dict)

    # Sentiment
    sentiment: SentimentState = field(default_factory=SentimentState)

    # Signal scores per symbol
    scores: Dict[str, ScoreState] = field(default_factory=dict)

    # Account state
    balance_usd: float = 0.0
    equity_usd: float = 0.0

    # Historical context (last N candles summary)
    price_history: List[float] = field(default_factory=list)  # Last 10 prices

    def to_vector(self, target_symbol: str = "BTC") -> np.ndarray:
        """
        Convert entire state to numpy vector for neural network.

        Args:
            target_symbol: The symbol we're considering trading

        Returns:
            numpy array of shape (state_dim,)
        """
        vectors = []

        # 1. Position state (7 features)
        vectors.append(self.position.to_vector())

        # 2. Target symbol indicators (10 features)
        if target_symbol in self.indicators:
            vectors.append(self.indicators[target_symbol].to_vector())
        else:
            vectors.append(np.zeros(10, dtype=np.float32))

        # 3. BTC indicators if not target (for correlation) (10 features)
        if target_symbol != "BTC" and "BTC" in self.indicators:
            vectors.append(self.indicators["BTC"].to_vector())
        else:
            vectors.append(np.zeros(10, dtype=np.float32))

        # 4. Sentiment (4 features)
        vectors.append(self.sentiment.to_vector())

        # 5. Target symbol score (5 features)
        if target_symbol in self.scores:
            vectors.append(self.scores[target_symbol].to_vector())
        else:
            vectors.append(np.zeros(5, dtype=np.float32))

        # 6. Account state (2 features)
        vectors.append(np.array([
            np.log1p(self.balance_usd) / 10,  # Log-normalized balance
            (self.equity_usd - self.balance_usd) / max(self.balance_usd, 1) if self.balance_usd > 0 else 0,
        ], dtype=np.float32))

        # 7. Price history features (5 features)
        if len(self.price_history) >= 2:
            prices = np.array(self.price_history[-10:])
            returns = np.diff(prices) / prices[:-1] if len(prices) > 1 else np.array([0])
            vectors.append(np.array([
                np.mean(returns) * 100,  # Mean return
                np.std(returns) * 100 if len(returns) > 1 else 0,  # Volatility
                returns[-1] * 100 if len(returns) > 0 else 0,  # Last return
                (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] > 0 else 0,  # Total change
                len(prices) / 10,  # History length
            ], dtype=np.float32))
        else:
            vectors.append(np.zeros(5, dtype=np.float32))

        # Concatenate all vectors
        state_vector = np.concatenate(vectors)

        # Clip to prevent extreme values
        state_vector = np.clip(state_vector, -10, 10)

        return state_vector

    @property
    def state_dim(self) -> int:
        """Get the dimension of the state vector."""
        return len(self.to_vector())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "position": {
                "has_position": self.position.has_position,
                "symbol": self.position.symbol,
                "direction": self.position.direction,
                "unrealized_pnl_pct": self.position.unrealized_pnl_pct,
            },
            "balance_usd": self.balance_usd,
            "equity_usd": self.equity_usd,
            "indicators": {
                k: {"price": v.price, "rsi_14": v.rsi_14, "macd": v.macd}
                for k, v in self.indicators.items()
            },
            "sentiment": {
                "fear_greed": self.sentiment.fear_greed_index,
                "forecast_15m": self.sentiment.forecast_15m_pct,
            },
            "scores": {
                k: {"net_score": v.net_score, "direction": v.direction}
                for k, v in self.scores.items()
            }
        }


def create_state_from_data(
    indicators_data: Dict[str, Any],
    sentiment_data: Dict[str, Any],
    forecast_data: Dict[str, Any],
    score_data: Dict[str, Any],
    position_data: Optional[Dict[str, Any]] = None,
    account_data: Optional[Dict[str, Any]] = None,
) -> MarketState:
    """
    Factory function to create MarketState from raw data.

    This bridges the gap between existing data sources and the RL state.
    """
    state = MarketState()

    # Parse indicators
    for symbol, ind in indicators_data.items():
        state.indicators[symbol] = IndicatorState(
            symbol=symbol,
            price=ind.get("price", 0),
            ema20=ind.get("ema20", 0),
            ema50=ind.get("ema50", 0),
            rsi_7=ind.get("rsi_7", 50),
            rsi_14=ind.get("rsi_14", 50),
            macd=ind.get("macd", 0),
            macd_signal=ind.get("macd_signal", 0),
            macd_histogram=ind.get("macd_histogram", 0),
            atr_14=ind.get("atr_14", 0),
            volume_ratio=ind.get("volume_ratio", 1),
            adx=ind.get("adx", 25),
            bollinger_pct_b=ind.get("bollinger_pct_b", 0.5),
            obv_trend=ind.get("obv_trend", 0),
        )

    # Parse sentiment
    state.sentiment = SentimentState(
        fear_greed_index=sentiment_data.get("value", 50),
        btc_rsi=indicators_data.get("BTC", {}).get("rsi_14", 50),
    )

    # Parse forecasts
    for symbol, fc in forecast_data.items():
        if "15m" in str(fc.get("timeframe", "")).lower():
            state.sentiment.forecast_15m_pct = fc.get("change_pct", 0)
        elif "1h" in str(fc.get("timeframe", "")).lower():
            state.sentiment.forecast_1h_pct = fc.get("change_pct", 0)

    # Parse scores
    for symbol, sc in score_data.items():
        state.scores[symbol] = ScoreState(
            score_bullish=sc.get("score_bullish", 0),
            score_bearish=sc.get("score_bearish", 0),
            net_score=sc.get("net_score", 0),
            direction=sc.get("direction", "HOLD"),
            confidence=sc.get("confidence", "WEAK"),
        )

    # Parse position
    if position_data and position_data.get("has_position"):
        state.position = PositionState(
            has_position=True,
            symbol=position_data.get("symbol", ""),
            direction=position_data.get("direction", ""),
            entry_price=position_data.get("entry_price", 0),
            current_price=position_data.get("current_price", 0),
            size_usd=position_data.get("size_usd", 0),
            leverage=position_data.get("leverage", 1),
            unrealized_pnl_pct=position_data.get("unrealized_pnl_pct", 0),
            duration_hours=position_data.get("duration_hours", 0),
            max_profit_pct=position_data.get("max_profit_pct", 0),
            max_loss_pct=position_data.get("max_loss_pct", 0),
        )

    # Parse account
    if account_data:
        state.balance_usd = account_data.get("balance_usd", 0)
        state.equity_usd = account_data.get("equity_usd", state.balance_usd)

    return state
