"""
Reward Function for AlphaTrader RL
==================================

This module defines how the agent is rewarded/penalized for its actions.
The reward function is CRITICAL for learning good trading behavior.

Key principles:
1. Reward profitable trades (P&L > 0)
2. Penalize losses, but not too harshly (learning from losses)
3. Time penalty to avoid stagnant positions
4. Drawdown penalty to encourage risk management
5. Bonus for consistency (Sharpe/Sortino ratio)
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from .config import RewardConfig, get_config


@dataclass
class TradeResult:
    """Result of a completed trade."""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    size_usd: float
    leverage: int
    entry_time: datetime
    exit_time: datetime
    pnl_usd: float
    pnl_pct: float
    max_profit_pct: float  # MFE
    max_loss_pct: float  # MAE
    exit_reason: str  # "TP", "SL", "AI", "TIMEOUT", etc.


@dataclass
class RewardBreakdown:
    """Detailed breakdown of reward components."""
    base_pnl_reward: float = 0.0
    time_penalty: float = 0.0
    drawdown_penalty: float = 0.0
    win_bonus: float = 0.0
    consistency_bonus: float = 0.0
    holding_cost: float = 0.0
    risk_adjusted_bonus: float = 0.0
    total_reward: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "base_pnl_reward": self.base_pnl_reward,
            "time_penalty": self.time_penalty,
            "drawdown_penalty": self.drawdown_penalty,
            "win_bonus": self.win_bonus,
            "consistency_bonus": self.consistency_bonus,
            "holding_cost": self.holding_cost,
            "risk_adjusted_bonus": self.risk_adjusted_bonus,
            "total_reward": self.total_reward,
        }


class RewardCalculator:
    """
    Calculates rewards for the RL agent.

    The reward is designed to encourage:
    1. Profitable trades
    2. Quick execution (time efficiency)
    3. Risk management (small drawdowns)
    4. Consistency (stable returns)
    """

    def __init__(self, config: Optional[RewardConfig] = None):
        self.config = config or get_config().reward
        self.trade_history: List[TradeResult] = []
        self.episode_returns: List[float] = []

    def calculate_trade_reward(self, trade: TradeResult) -> RewardBreakdown:
        """
        Calculate reward for a completed trade.

        Args:
            trade: The completed trade result

        Returns:
            RewardBreakdown with all components
        """
        breakdown = RewardBreakdown()

        # 1. Base P&L Reward
        # Scale P&L to reasonable range for RL (roughly -1 to +1 for typical trades)
        breakdown.base_pnl_reward = trade.pnl_pct * self.config.pnl_multiplier / 10.0

        # 2. Time Penalty
        duration_hours = (trade.exit_time - trade.entry_time).total_seconds() / 3600
        if duration_hours > self.config.time_decay_start_hours:
            excess_hours = duration_hours - self.config.time_decay_start_hours
            breakdown.time_penalty = -min(
                excess_hours * self.config.time_decay_rate,
                self.config.max_time_penalty
            )

        # 3. Drawdown Penalty
        # Penalize trades that had large unrealized losses even if they ended up profitable
        if trade.max_loss_pct > self.config.drawdown_penalty_threshold * 100:
            drawdown_excess = (trade.max_loss_pct / 100) - self.config.drawdown_penalty_threshold
            breakdown.drawdown_penalty = -drawdown_excess * self.config.drawdown_penalty_rate

        # 4. Win Bonus
        if trade.pnl_pct > 0:
            breakdown.win_bonus = self.config.win_bonus

        # 5. Holding Cost (opportunity cost)
        breakdown.holding_cost = -duration_hours * self.config.holding_cost_per_hour

        # 6. Risk-Adjusted Bonus (Calmar-like ratio)
        # Reward high return relative to drawdown
        if trade.max_loss_pct > 0:
            risk_adjusted = trade.pnl_pct / trade.max_loss_pct
            if risk_adjusted > 1.5:  # Good risk/reward
                breakdown.risk_adjusted_bonus = min(risk_adjusted - 1.0, 0.5) * 0.1

        # Calculate total
        breakdown.total_reward = (
            breakdown.base_pnl_reward +
            breakdown.time_penalty +
            breakdown.drawdown_penalty +
            breakdown.win_bonus +
            breakdown.holding_cost +
            breakdown.risk_adjusted_bonus
        )

        # Store trade for consistency calculation
        self.trade_history.append(trade)
        self.episode_returns.append(trade.pnl_pct)

        return breakdown

    def calculate_step_reward(
        self,
        action_taken: str,  # "HOLD", "OPEN_LONG", "OPEN_SHORT", "CLOSE"
        unrealized_pnl_pct: float = 0.0,
        position_duration_hours: float = 0.0,
        position_open: bool = False,
    ) -> float:
        """
        Calculate immediate step reward (for training between trade completions).

        This is a smaller reward used during training to provide more frequent
        feedback to the agent.
        """
        reward = 0.0

        if action_taken == "HOLD":
            if position_open:
                # Small reward/penalty based on unrealized P&L
                reward = unrealized_pnl_pct / 100.0 * 0.01

                # Time penalty for holding too long
                if position_duration_hours > self.config.time_decay_start_hours:
                    reward -= 0.001
            else:
                # Neutral for holding without position
                reward = 0.0

        elif action_taken in ("OPEN_LONG", "OPEN_SHORT"):
            # Small negative for opening (encourage selectivity)
            reward = -0.005

        elif action_taken == "CLOSE":
            # This will be handled by calculate_trade_reward
            reward = 0.0

        return reward

    def calculate_episode_bonus(self) -> float:
        """
        Calculate end-of-episode bonus based on overall performance.

        This rewards consistency and good Sharpe/Sortino ratios.
        """
        if len(self.episode_returns) < 2:
            return 0.0

        returns = np.array(self.episode_returns)
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        # Sharpe-like ratio
        if std_return > 0:
            sharpe = mean_return / std_return
        else:
            sharpe = mean_return if mean_return > 0 else 0

        bonus = 0.0

        # Sharpe bonus
        if sharpe > self.config.sharpe_bonus_threshold:
            bonus += self.config.sharpe_bonus

        # Win rate bonus
        win_rate = np.mean(returns > 0)
        if win_rate > 0.6:  # >60% win rate
            bonus += 0.05

        # Total return bonus
        total_return = np.sum(returns)
        if total_return > 5:  # >5% total return
            bonus += total_return / 100.0 * 0.1

        return bonus

    def get_sortino_ratio(self) -> float:
        """Calculate Sortino ratio (only considers downside volatility)."""
        if len(self.episode_returns) < 2:
            return 0.0

        returns = np.array(self.episode_returns)
        mean_return = np.mean(returns)

        # Downside returns only
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns)
            if downside_std > 0:
                return mean_return / downside_std

        return mean_return if mean_return > 0 else 0.0

    def get_stats(self) -> Dict:
        """Get statistics for logging."""
        if len(self.trade_history) == 0:
            return {"trades": 0}

        returns = np.array(self.episode_returns)
        wins = returns > 0
        losses = returns < 0

        return {
            "trades": len(self.trade_history),
            "win_rate": float(np.mean(wins)) if len(wins) > 0 else 0,
            "avg_return": float(np.mean(returns)),
            "total_return": float(np.sum(returns)),
            "sharpe": float(np.mean(returns) / np.std(returns)) if np.std(returns) > 0 else 0,
            "sortino": self.get_sortino_ratio(),
            "max_drawdown": float(np.min(returns)) if len(returns) > 0 else 0,
            "avg_win": float(np.mean(returns[wins])) if np.any(wins) else 0,
            "avg_loss": float(np.mean(returns[losses])) if np.any(losses) else 0,
        }

    def reset_episode(self):
        """Reset for new episode."""
        self.trade_history = []
        self.episode_returns = []


def calculate_pnl(
    entry_price: float,
    exit_price: float,
    direction: str,
    leverage: int = 1,
) -> Tuple[float, float]:
    """
    Calculate P&L for a trade.

    Returns:
        (pnl_pct, pnl_multiplier)
    """
    if direction == "LONG":
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * leverage
    else:  # SHORT
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100 * leverage

    return pnl_pct, pnl_pct / 100.0


def simulate_trade_outcome(
    entry_price: float,
    direction: str,
    leverage: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    price_path: List[float],
) -> TradeResult:
    """
    Simulate a trade outcome given a price path.

    Used for MCTS simulations and backtesting.
    """
    exit_price = entry_price
    exit_reason = "END"
    max_price = entry_price
    min_price = entry_price

    for i, price in enumerate(price_path):
        max_price = max(max_price, price)
        min_price = min(min_price, price)

        # Calculate current P&L
        if direction == "LONG":
            current_pnl_pct = ((price - entry_price) / entry_price) * 100 * leverage
        else:
            current_pnl_pct = ((entry_price - price) / entry_price) * 100 * leverage

        # Check SL
        if current_pnl_pct <= -stop_loss_pct:
            exit_price = price
            exit_reason = "SL"
            break

        # Check TP
        if current_pnl_pct >= take_profit_pct:
            exit_price = price
            exit_reason = "TP"
            break

        exit_price = price

    # Calculate final P&L
    pnl_pct, _ = calculate_pnl(entry_price, exit_price, direction, leverage)

    # Calculate MFE/MAE
    if direction == "LONG":
        mfe = ((max_price - entry_price) / entry_price) * 100 * leverage
        mae = ((entry_price - min_price) / entry_price) * 100 * leverage
    else:
        mfe = ((entry_price - min_price) / entry_price) * 100 * leverage
        mae = ((max_price - entry_price) / entry_price) * 100 * leverage

    return TradeResult(
        symbol="SIM",
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        size_usd=0,
        leverage=leverage,
        entry_time=datetime.utcnow(),
        exit_time=datetime.utcnow(),
        pnl_usd=0,
        pnl_pct=pnl_pct,
        max_profit_pct=max(mfe, 0),
        max_loss_pct=max(mae, 0),
        exit_reason=exit_reason,
    )


# Test
if __name__ == "__main__":
    calc = RewardCalculator()

    # Simulate a winning trade
    trade1 = TradeResult(
        symbol="BTC",
        direction="LONG",
        entry_price=100000,
        exit_price=102000,
        size_usd=50,
        leverage=3,
        entry_time=datetime.utcnow() - timedelta(hours=2),
        exit_time=datetime.utcnow(),
        pnl_usd=3.0,
        pnl_pct=6.0,  # 2% * 3x leverage
        max_profit_pct=7.0,
        max_loss_pct=1.5,
        exit_reason="TP",
    )

    reward1 = calc.calculate_trade_reward(trade1)
    print("=== Winning Trade ===")
    print(f"P&L: {trade1.pnl_pct}%")
    print(f"Reward breakdown: {reward1.to_dict()}")
    print(f"Total reward: {reward1.total_reward:.4f}")

    # Simulate a losing trade
    trade2 = TradeResult(
        symbol="ETH",
        direction="SHORT",
        entry_price=3500,
        exit_price=3600,
        size_usd=50,
        leverage=2,
        entry_time=datetime.utcnow() - timedelta(hours=8),
        exit_time=datetime.utcnow(),
        pnl_usd=-2.86,
        pnl_pct=-5.71,  # -2.86% * 2x leverage
        max_profit_pct=1.0,
        max_loss_pct=6.0,
        exit_reason="SL",
    )

    reward2 = calc.calculate_trade_reward(trade2)
    print("\n=== Losing Trade ===")
    print(f"P&L: {trade2.pnl_pct}%")
    print(f"Reward breakdown: {reward2.to_dict()}")
    print(f"Total reward: {reward2.total_reward:.4f}")

    # Episode stats
    print("\n=== Episode Stats ===")
    print(calc.get_stats())
