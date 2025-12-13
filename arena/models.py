"""
Arena Data Models

Dataclasses for variants, sub-variants, and simulated trades.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class OperationMode(str, Enum):
    """How AI is triggered for trade decisions."""
    SCORE_TRIGGERED = "SCORE_TRIGGERED"  # Standard: score must exceed threshold
    AI_INDEPENDENT = "AI_INDEPENDENT"    # AI decides freely every interval


class TradeDirection(str, Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    """Status of a simulated trade."""
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"      # Take profit hit
    CLOSED_SL = "CLOSED_SL"      # Stop loss hit
    CLOSED_SMART_SL = "CLOSED_SMART_SL"  # Smart SL extended, then hit
    CLOSED_SIGNAL = "CLOSED_SIGNAL"      # Closed by contrary signal
    CLOSED_AI = "CLOSED_AI"      # Closed by AI decision
    CLOSED_MANUAL = "CLOSED_MANUAL"      # Manually closed


@dataclass
class IndicatorConfig:
    """Configuration for technical indicators."""
    # Periods
    ema_short_period: int = 9
    ema_medium_period: int = 21
    ema_long_period: int = 50
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    adx_period: int = 14

    # Weights for scoring (V2 Smart Score)
    weight_macd: float = 25.0
    weight_rsi: float = 15.0
    weight_ema_alignment: float = 20.0
    weight_adx_trend: float = 15.0
    weight_volume: float = 10.0
    weight_whale: float = 10.0
    weight_funding: float = 5.0
    weight_double_bottom: float = 12.0
    weight_double_top: float = 12.0

    # Thresholds
    macd_threshold_strong: float = 0.20
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    adx_min_trend: float = 20.0
    adx_strong_trend: float = 25.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ema_short_period": self.ema_short_period,
            "ema_medium_period": self.ema_medium_period,
            "ema_long_period": self.ema_long_period,
            "rsi_period": self.rsi_period,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "atr_period": self.atr_period,
            "adx_period": self.adx_period,
            "weight_macd": self.weight_macd,
            "weight_rsi": self.weight_rsi,
            "weight_ema_alignment": self.weight_ema_alignment,
            "weight_adx_trend": self.weight_adx_trend,
            "weight_volume": self.weight_volume,
            "weight_whale": self.weight_whale,
            "weight_funding": self.weight_funding,
            "weight_double_bottom": self.weight_double_bottom,
            "weight_double_top": self.weight_double_top,
            "macd_threshold_strong": self.macd_threshold_strong,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "adx_min_trend": self.adx_min_trend,
            "adx_strong_trend": self.adx_strong_trend,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndicatorConfig":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class TradingParams:
    """Trading parameters for a variant."""
    # Position sizing
    position_size_usd: float = 50.0
    leverage: int = 3

    # Stop loss / Take profit
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0

    # Trailing stop
    trailing_enabled: bool = True
    trailing_steps: str = "2.5:0.0,5.0:2.0,7.5:4.0"  # "pnl:sl_level,..."

    # ATR dynamic
    atr_dynamic_enabled: bool = False
    atr_base_percent: float = 1.5
    atr_step_multiplier_min: float = 0.8
    atr_step_multiplier_max: float = 1.5

    # Scoring
    score_threshold_open: float = 15.0
    score_threshold_close: float = -10.0

    # AI settings
    double_check_ai_enabled: bool = True
    trading_style: str = "moderate"  # aggressive, moderate, conservative

    # Smart SL
    smart_sl_enabled: bool = False
    smart_sl_extension_pct: float = 1.0
    smart_sl_max_extensions: int = 2

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "position_size_usd": self.position_size_usd,
            "leverage": self.leverage,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trailing_enabled": self.trailing_enabled,
            "trailing_steps": self.trailing_steps,
            "atr_dynamic_enabled": self.atr_dynamic_enabled,
            "atr_base_percent": self.atr_base_percent,
            "atr_step_multiplier_min": self.atr_step_multiplier_min,
            "atr_step_multiplier_max": self.atr_step_multiplier_max,
            "score_threshold_open": self.score_threshold_open,
            "score_threshold_close": self.score_threshold_close,
            "double_check_ai_enabled": self.double_check_ai_enabled,
            "trading_style": self.trading_style,
            "smart_sl_enabled": self.smart_sl_enabled,
            "smart_sl_extension_pct": self.smart_sl_extension_pct,
            "smart_sl_max_extensions": self.smart_sl_max_extensions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingParams":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class SubVariant:
    """
    A sub-variant represents a specific AI model within a variant.
    Each variant can have multiple sub-variants, one per AI model.
    """
    id: str                          # e.g., "V1_deepseek"
    variant_id: str                  # Parent variant ID
    ai_model: str                    # e.g., "deepseek/deepseek-chat"
    ai_model_name: str               # e.g., "DeepSeek V3"

    # Control
    enabled: bool = True             # Can be toggled from dashboard

    # Statistics (updated after each trade)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0

    # API tracking
    api_calls: int = 0               # Number of API calls made
    api_errors: int = 0              # Number of API errors

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_trade_at: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "variant_id": self.variant_id,
            "ai_model": self.ai_model,
            "ai_model_name": self.ai_model_name,
            "enabled": self.enabled,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl_usd": self.total_pnl_usd,
            "total_pnl_pct": self.total_pnl_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "api_calls": self.api_calls,
            "api_errors": self.api_errors,
            "win_rate": self.win_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_trade_at": self.last_trade_at.isoformat() if self.last_trade_at else None,
        }


@dataclass
class Variant:
    """
    A variant represents a specific configuration to test.
    Each variant can have multiple sub-variants (one per AI model).
    """
    id: str                          # e.g., "V1_BASELINE"
    name: str                        # e.g., "Baseline Configuration"
    description: str                 # What this variant tests
    enabled: bool = True

    # Configuration
    operation_mode: OperationMode = OperationMode.SCORE_TRIGGERED
    trading_params: TradingParams = field(default_factory=TradingParams)
    indicator_config: IndicatorConfig = field(default_factory=IndicatorConfig)

    # AI models to test (creates sub-variants)
    ai_models: List[str] = field(default_factory=lambda: ["deepseek/deepseek-chat"])

    # Pattern detection settings
    pattern_detection_enabled: bool = True
    pattern_timeframe: str = "1h"
    pattern_min_confidence: float = 0.60

    # AI Independent mode settings (if operation_mode == AI_INDEPENDENT)
    ai_check_interval_minutes: int = 15
    ai_independent_timeframe: str = "4h"  # Longer timeframe for independent AI

    # Symbols to trade
    symbols: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])

    # Sub-variants (populated at runtime)
    sub_variants: List[SubVariant] = field(default_factory=list)

    # Aggregate statistics
    total_trades: int = 0
    total_pnl_usd: float = 0.0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    def get_sub_variant(self, ai_model: str) -> Optional[SubVariant]:
        """Get sub-variant for a specific AI model."""
        for sv in self.sub_variants:
            if sv.ai_model == ai_model:
                return sv
        return None

    def create_sub_variants(self) -> None:
        """Create sub-variants for each AI model."""
        self.sub_variants = []
        for model in self.ai_models:
            model_name = model.split("/")[-1] if "/" in model else model
            sv = SubVariant(
                id=f"{self.id}_{model_name}",
                variant_id=self.id,
                ai_model=model,
                ai_model_name=model_name.replace("-", " ").title(),
            )
            self.sub_variants.append(sv)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "operation_mode": self.operation_mode.value,
            "trading_params": self.trading_params.to_dict(),
            "indicator_config": self.indicator_config.to_dict(),
            "ai_models": self.ai_models,
            "pattern_detection_enabled": self.pattern_detection_enabled,
            "pattern_timeframe": self.pattern_timeframe,
            "pattern_min_confidence": self.pattern_min_confidence,
            "ai_check_interval_minutes": self.ai_check_interval_minutes,
            "ai_independent_timeframe": self.ai_independent_timeframe,
            "symbols": self.symbols,
            "sub_variants": [sv.to_dict() for sv in self.sub_variants],
            "total_trades": self.total_trades,
            "total_pnl_usd": self.total_pnl_usd,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Variant":
        """Create from dictionary."""
        # Parse nested objects
        trading_params = TradingParams.from_dict(data.get("trading_params", {}))
        indicator_config = IndicatorConfig.from_dict(data.get("indicator_config", {}))
        operation_mode = OperationMode(data.get("operation_mode", "SCORE_TRIGGERED"))

        variant = cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            operation_mode=operation_mode,
            trading_params=trading_params,
            indicator_config=indicator_config,
            ai_models=data.get("ai_models", ["deepseek/deepseek-chat"]),
            pattern_detection_enabled=data.get("pattern_detection_enabled", True),
            pattern_timeframe=data.get("pattern_timeframe", "1h"),
            pattern_min_confidence=data.get("pattern_min_confidence", 0.60),
            ai_check_interval_minutes=data.get("ai_check_interval_minutes", 15),
            ai_independent_timeframe=data.get("ai_independent_timeframe", "4h"),
            symbols=data.get("symbols", ["BTC", "ETH", "SOL"]),
        )

        # Create sub-variants
        variant.create_sub_variants()

        return variant


@dataclass
class SimulatedPosition:
    """
    An open simulated position.
    """
    id: str                          # Unique position ID
    sub_variant_id: str              # Which sub-variant this belongs to
    symbol: str                      # e.g., "BTC"
    direction: TradeDirection

    # Entry details
    entry_price: float
    entry_time: datetime
    position_size_usd: float
    leverage: int

    # Stop loss / Take profit
    stop_loss_price: float
    take_profit_price: float
    current_sl_level: float          # Current SL percentage (for trailing)

    # Smart SL tracking
    smart_sl_extensions: int = 0
    original_sl_price: float = 0.0

    # Current state
    current_price: float = 0.0
    current_pnl_pct: float = 0.0
    current_pnl_usd: float = 0.0
    peak_pnl_pct: float = 0.0

    # Score that triggered entry
    entry_score: float = 0.0
    entry_reason: str = ""           # "pattern", "score", "ai_independent"

    def update_pnl(self, current_price: float) -> None:
        """Update current P&L based on price."""
        self.current_price = current_price

        if self.direction == TradeDirection.LONG:
            self.current_pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
        else:
            self.current_pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage

        self.current_pnl_usd = (self.current_pnl_pct / 100) * self.position_size_usd

        if self.current_pnl_pct > self.peak_pnl_pct:
            self.peak_pnl_pct = self.current_pnl_pct

    def check_sl_hit(self) -> bool:
        """Check if stop loss was hit."""
        if self.direction == TradeDirection.LONG:
            return self.current_price <= self.stop_loss_price
        else:
            return self.current_price >= self.stop_loss_price

    def check_tp_hit(self) -> bool:
        """Check if take profit was hit."""
        if self.direction == TradeDirection.LONG:
            return self.current_price >= self.take_profit_price
        else:
            return self.current_price <= self.take_profit_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "sub_variant_id": self.sub_variant_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "position_size_usd": self.position_size_usd,
            "leverage": self.leverage,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "current_sl_level": self.current_sl_level,
            "smart_sl_extensions": self.smart_sl_extensions,
            "original_sl_price": self.original_sl_price,
            "current_price": self.current_price,
            "current_pnl_pct": self.current_pnl_pct,
            "current_pnl_usd": self.current_pnl_usd,
            "peak_pnl_pct": self.peak_pnl_pct,
            "entry_score": self.entry_score,
            "entry_reason": self.entry_reason,
        }


@dataclass
class SimulatedTrade:
    """
    A completed simulated trade.
    """
    id: str                          # Unique trade ID
    sub_variant_id: str              # Which sub-variant this belongs to
    variant_id: str                  # Parent variant ID
    symbol: str
    direction: TradeDirection

    # Entry
    entry_price: float
    entry_time: datetime
    position_size_usd: float
    leverage: int
    entry_score: float = 0.0
    entry_reason: str = ""

    # Exit
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    exit_reason: TradeStatus = TradeStatus.OPEN

    # Results
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    peak_pnl_pct: float = 0.0
    duration_minutes: int = 0

    # Smart SL info
    smart_sl_extensions: int = 0
    final_sl_price: float = 0.0

    # AI info
    ai_model: str = ""
    ai_confidence: float = 0.0

    def close(self, exit_price: float, exit_reason: TradeStatus) -> None:
        """Close the trade and calculate final P&L."""
        self.exit_price = exit_price
        self.exit_time = datetime.now()
        self.exit_reason = exit_reason

        if self.direction == TradeDirection.LONG:
            self.pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100 * self.leverage
        else:
            self.pnl_pct = ((self.entry_price - exit_price) / self.entry_price) * 100 * self.leverage

        self.pnl_usd = (self.pnl_pct / 100) * self.position_size_usd

        if self.entry_time and self.exit_time:
            self.duration_minutes = int((self.exit_time - self.entry_time).total_seconds() / 60)

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl_usd > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "sub_variant_id": self.sub_variant_id,
            "variant_id": self.variant_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "position_size_usd": self.position_size_usd,
            "leverage": self.leverage,
            "entry_score": self.entry_score,
            "entry_reason": self.entry_reason,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason.value,
            "pnl_pct": self.pnl_pct,
            "pnl_usd": self.pnl_usd,
            "peak_pnl_pct": self.peak_pnl_pct,
            "duration_minutes": self.duration_minutes,
            "smart_sl_extensions": self.smart_sl_extensions,
            "final_sl_price": self.final_sl_price,
            "ai_model": self.ai_model,
            "ai_confidence": self.ai_confidence,
            "is_winner": self.is_winner,
        }

    @classmethod
    def from_position(cls, position: SimulatedPosition, variant_id: str) -> "SimulatedTrade":
        """Create a trade from a position."""
        return cls(
            id=position.id,
            sub_variant_id=position.sub_variant_id,
            variant_id=variant_id,
            symbol=position.symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            entry_time=position.entry_time,
            position_size_usd=position.position_size_usd,
            leverage=position.leverage,
            entry_score=position.entry_score,
            entry_reason=position.entry_reason,
            peak_pnl_pct=position.peak_pnl_pct,
            smart_sl_extensions=position.smart_sl_extensions,
            final_sl_price=position.stop_loss_price,
        )
