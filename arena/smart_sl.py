"""
Arena Smart Stop Loss Manager

Implements AI-controlled stop loss extension system.
When price approaches SL, AI can decide to extend it based on market conditions.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from .models import (
    Variant,
    SubVariant,
    SimulatedPosition,
    TradeDirection,
)
from .ai_manager import AIManager


logger = logging.getLogger("arena.smart_sl")


class SmartSLManager:
    """
    Manages Smart Stop Loss functionality.

    When a position approaches its stop loss, this manager:
    1. Checks if Smart SL is enabled for the variant
    2. Consults AI to decide if SL should be extended
    3. Applies the extension if approved

    This allows the AI to "save" positions that might recover.
    """

    def __init__(self, ai_manager: Optional[AIManager] = None):
        """Initialize Smart SL Manager."""
        self.ai_manager = ai_manager or AIManager()

        # Track extension history per position
        self._extension_history: Dict[str, list] = {}

        # SL proximity threshold (% of SL distance)
        self._proximity_threshold = 0.3  # Check when within 30% of SL

    def check_and_extend_sl(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        position: SimulatedPosition,
        current_price: float,
        market_data: Dict[str, Any],
    ) -> Tuple[bool, float, str]:
        """
        Check if SL should be extended and apply if approved.

        Args:
            variant: The variant configuration
            sub_variant: The sub-variant (for AI model)
            position: The current position
            current_price: Current market price
            market_data: Current market indicators

        Returns:
            Tuple of (was_extended, new_sl_price, reason)
        """
        if not variant.trading_params.smart_sl_enabled:
            return False, position.stop_loss_price, "Smart SL disabled"

        max_extensions = variant.trading_params.smart_sl_max_extensions
        if position.smart_sl_extensions >= max_extensions:
            return False, position.stop_loss_price, f"Max extensions ({max_extensions}) reached"

        # Check if price is near SL
        if not self._is_near_sl(position, current_price):
            return False, position.stop_loss_price, "Not near SL"

        # Calculate current P&L
        if position.direction == TradeDirection.LONG:
            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
        else:
            pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

        # Ask AI
        should_extend, reason, confidence = self.ai_manager.check_smart_sl_extension(
            variant=variant,
            sub_variant=sub_variant,
            symbol=position.symbol,
            direction=position.direction,
            current_pnl_pct=pnl_pct,
            market_data=market_data,
            extensions_used=position.smart_sl_extensions,
        )

        if not should_extend:
            return False, position.stop_loss_price, reason

        # Calculate new SL
        extension_pct = variant.trading_params.smart_sl_extension_pct
        new_sl_price = self._calculate_new_sl(position, extension_pct)

        # Log extension
        logger.info(
            f"Smart SL extended for {position.symbol}: "
            f"${position.stop_loss_price:.2f} -> ${new_sl_price:.2f} "
            f"(extension #{position.smart_sl_extensions + 1}, conf: {confidence:.0%})"
        )

        # Track extension history
        self._record_extension(
            position.id,
            position.stop_loss_price,
            new_sl_price,
            reason,
            confidence,
        )

        return True, new_sl_price, reason

    def _is_near_sl(self, position: SimulatedPosition, current_price: float) -> bool:
        """Check if current price is near stop loss."""
        entry = position.entry_price
        sl = position.stop_loss_price

        # Calculate distance from entry to SL
        sl_distance = abs(entry - sl)

        # Calculate current distance to SL
        current_distance = abs(current_price - sl)

        # Check if within threshold
        proximity = current_distance / sl_distance if sl_distance > 0 else 1.0

        return proximity <= self._proximity_threshold

    def _calculate_new_sl(
        self,
        position: SimulatedPosition,
        extension_pct: float,
    ) -> float:
        """Calculate new stop loss price after extension."""
        current_sl = position.stop_loss_price
        entry = position.entry_price

        # Extension amount based on entry price
        extension_amount = entry * (extension_pct / 100)

        if position.direction == TradeDirection.LONG:
            # For LONG, move SL lower (give more room)
            new_sl = current_sl - extension_amount
        else:
            # For SHORT, move SL higher (give more room)
            new_sl = current_sl + extension_amount

        return new_sl

    def _record_extension(
        self,
        position_id: str,
        old_sl: float,
        new_sl: float,
        reason: str,
        confidence: float,
    ) -> None:
        """Record extension in history."""
        if position_id not in self._extension_history:
            self._extension_history[position_id] = []

        self._extension_history[position_id].append({
            "timestamp": datetime.now().isoformat(),
            "old_sl": old_sl,
            "new_sl": new_sl,
            "reason": reason,
            "confidence": confidence,
        })

    def get_extension_history(self, position_id: str) -> list:
        """Get extension history for a position."""
        return self._extension_history.get(position_id, [])

    def clear_history(self, position_id: str) -> None:
        """Clear extension history for a closed position."""
        if position_id in self._extension_history:
            del self._extension_history[position_id]


class TrailingSLManager:
    """
    Manages trailing stop loss for Arena positions.
    Applies trailing steps based on P&L thresholds.
    """

    def __init__(self):
        """Initialize Trailing SL Manager."""
        pass

    def apply_trailing(
        self,
        position: SimulatedPosition,
        trading_params: Dict[str, Any],
        current_price: float,
    ) -> Tuple[bool, float, float]:
        """
        Apply trailing stop loss logic.

        Args:
            position: Current position
            trading_params: Trading parameters with trailing config
            current_price: Current market price

        Returns:
            Tuple of (was_updated, new_sl_price, new_sl_level_pct)
        """
        if not trading_params.get("trailing_enabled", True):
            return False, position.stop_loss_price, position.current_sl_level

        # Calculate current P&L
        if position.direction == TradeDirection.LONG:
            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
        else:
            pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

        # Parse trailing steps
        steps = self._parse_trailing_steps(trading_params.get("trailing_steps", ""))

        # Find applicable step
        applicable_sl_level = position.current_sl_level
        for threshold, sl_level in sorted(steps, reverse=True):
            if pnl_pct >= threshold and sl_level > position.current_sl_level:
                applicable_sl_level = sl_level
                break

        if applicable_sl_level <= position.current_sl_level:
            return False, position.stop_loss_price, position.current_sl_level

        # Calculate new SL price
        new_sl_price = self._calculate_sl_price(
            position.entry_price,
            position.direction,
            applicable_sl_level,
            position.leverage,
        )

        return True, new_sl_price, applicable_sl_level

    def _parse_trailing_steps(self, steps_str: str) -> list:
        """Parse trailing steps from string format."""
        steps = []
        if not steps_str:
            return steps

        for step in steps_str.split(","):
            try:
                parts = step.strip().split(":")
                if len(parts) == 2:
                    threshold = float(parts[0])
                    sl_level = float(parts[1])
                    steps.append((threshold, sl_level))
            except ValueError:
                continue

        return steps

    def _calculate_sl_price(
        self,
        entry_price: float,
        direction: TradeDirection,
        sl_level_pct: float,
        leverage: int,
    ) -> float:
        """Calculate SL price from percentage level."""
        # SL level is the P&L percentage at which SL is set
        # e.g., sl_level=2.0 means SL locks in 2% profit

        # Account for leverage in calculation
        price_move_pct = sl_level_pct / leverage

        if direction == TradeDirection.LONG:
            return entry_price * (1 + price_move_pct / 100)
        else:
            return entry_price * (1 - price_move_pct / 100)
