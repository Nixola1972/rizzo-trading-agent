"""
Monte Carlo Tree Search (MCTS) for AlphaTrader
==============================================

MCTS simulates future scenarios before making trading decisions.
This is the "lookahead" component from AlphaGo.

Before executing a trade, MCTS:
1. Simulates N possible price paths
2. For each path, simulates what would happen with different actions
3. Returns statistics on win probability

If win probability < threshold (e.g., 60%), the trade is vetoed.

Key concepts:
- Node: A market state at a point in time
- Edge: An action taken from a state
- Rollout: Simulation of future price movements
- Backprop: Update statistics up the tree
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import random

from .market_state import MarketState, Action, ActionType
from .reward import simulate_trade_outcome, TradeResult
from .config import MCTSConfig, get_config


@dataclass
class MCTSStats:
    """Statistics for a node/edge in the tree."""
    visits: int = 0
    total_value: float = 0.0
    wins: int = 0
    losses: int = 0

    @property
    def mean_value(self) -> float:
        """Average value across visits."""
        return self.total_value / self.visits if self.visits > 0 else 0.0

    @property
    def win_rate(self) -> float:
        """Win rate across simulations."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.5


@dataclass
class MCTSNode:
    """Node in the MCTS tree representing a market state."""
    state: MarketState
    action_taken: Optional[ActionType] = None  # Action that led to this state
    parent: Optional['MCTSNode'] = None
    children: Dict[ActionType, 'MCTSNode'] = field(default_factory=dict)
    stats: MCTSStats = field(default_factory=MCTSStats)
    depth: int = 0

    def is_leaf(self) -> bool:
        """Check if this is a leaf node."""
        return len(self.children) == 0

    def is_fully_expanded(self) -> bool:
        """Check if all actions have been tried."""
        return len(self.children) == len(ActionType)

    def ucb_score(self, c: float = 1.414) -> float:
        """
        Upper Confidence Bound score for selection.

        UCB = mean_value + c * sqrt(ln(parent_visits) / visits)
        """
        if self.stats.visits == 0:
            return float('inf')  # Unexplored nodes have infinite UCB

        if self.parent is None or self.parent.stats.visits == 0:
            return self.stats.mean_value

        exploitation = self.stats.mean_value
        exploration = c * math.sqrt(math.log(self.parent.stats.visits) / self.stats.visits)

        return exploitation + exploration


@dataclass
class MCTSResult:
    """Result of MCTS simulation."""
    recommended_action: ActionType
    win_probability: float
    action_stats: Dict[str, Dict]  # Stats for each action
    total_simulations: int
    should_execute: bool  # Based on min_win_probability threshold
    reasoning: str


class PriceSimulator:
    """
    Simulates future price movements for MCTS rollouts.

    Uses a combination of:
    1. Historical volatility
    2. Current trend (from EMA)
    3. Random walk component
    4. Optional Prophet forecast
    """

    def __init__(self, use_prophet: bool = False):
        self.use_prophet = use_prophet

    def simulate_path(
        self,
        current_price: float,
        volatility: float,  # ATR or historical volatility
        trend: float,  # Current trend direction (-1 to 1)
        steps: int = 12,  # Number of future candles
        interval_minutes: int = 15,
    ) -> List[float]:
        """
        Simulate a price path.

        Args:
            current_price: Starting price
            volatility: Expected volatility per step
            trend: Trend bias (-1 = bearish, 0 = neutral, 1 = bullish)
            steps: Number of future steps
            interval_minutes: Minutes per step

        Returns:
            List of prices for each step
        """
        prices = [current_price]

        # Volatility per step (scaled by time)
        vol_per_step = volatility / current_price  # Normalize to percentage

        for _ in range(steps):
            # Random component (geometric Brownian motion)
            random_return = np.random.normal(0, vol_per_step)

            # Trend component (small bias)
            trend_return = trend * vol_per_step * 0.1

            # Mean reversion component (slight pull back to mean)
            mean_price = np.mean(prices[-5:]) if len(prices) >= 5 else current_price
            reversion = (mean_price - prices[-1]) / prices[-1] * 0.05

            # Total return
            total_return = random_return + trend_return + reversion

            # New price (can't go negative)
            new_price = max(prices[-1] * (1 + total_return), prices[-1] * 0.5)
            prices.append(new_price)

        return prices[1:]  # Exclude starting price

    def simulate_multiple_paths(
        self,
        current_price: float,
        volatility: float,
        trend: float,
        num_paths: int = 100,
        steps: int = 12,
    ) -> List[List[float]]:
        """Simulate multiple price paths."""
        return [
            self.simulate_path(current_price, volatility, trend, steps)
            for _ in range(num_paths)
        ]


class MCTS:
    """
    Monte Carlo Tree Search for trading decisions.

    Before executing a trade, MCTS simulates many possible outcomes
    to estimate the probability of success.
    """

    def __init__(self, config: Optional[MCTSConfig] = None):
        self.config = config or get_config().mcts
        self.simulator = PriceSimulator(use_prophet=self.config.use_prophet_for_sim)

    def search(
        self,
        state: MarketState,
        symbol: str = "BTC",
        proposed_action: Optional[ActionType] = None,
    ) -> MCTSResult:
        """
        Run MCTS to evaluate trading actions.

        Args:
            state: Current market state
            symbol: Symbol to trade
            proposed_action: If provided, focus simulations on this action

        Returns:
            MCTSResult with win probability and recommendation
        """
        # Get current market data
        if symbol not in state.indicators:
            return MCTSResult(
                recommended_action=ActionType.HOLD,
                win_probability=0.0,
                action_stats={},
                total_simulations=0,
                should_execute=False,
                reasoning="No indicator data for symbol",
            )

        indicators = state.indicators[symbol]
        current_price = indicators.price
        volatility = indicators.atr_14 if indicators.atr_14 > 0 else current_price * 0.01

        # Calculate trend from EMA
        if indicators.ema20 > 0:
            trend = (current_price - indicators.ema20) / indicators.ema20
            trend = np.clip(trend * 10, -1, 1)  # Scale and clip
        else:
            trend = 0

        # Initialize stats for each action
        action_stats: Dict[ActionType, MCTSStats] = {
            action: MCTSStats() for action in ActionType
        }

        # Run simulations
        for _ in range(self.config.num_simulations):
            # Simulate price path
            price_path = self.simulator.simulate_path(
                current_price=current_price,
                volatility=volatility,
                trend=trend,
                steps=self.config.simulation_timesteps,
            )

            # Evaluate each action
            for action in ActionType:
                if action == ActionType.HOLD:
                    # HOLD: no P&L change
                    action_stats[action].visits += 1
                    action_stats[action].total_value += 0
                    continue

                if action == ActionType.CLOSE:
                    # CLOSE: depends on current position
                    if state.position.has_position:
                        # Calculate P&L if we close now
                        if state.position.direction == "LONG":
                            pnl_pct = (current_price - state.position.entry_price) / state.position.entry_price * 100
                        else:
                            pnl_pct = (state.position.entry_price - current_price) / state.position.entry_price * 100
                        pnl_pct *= state.position.leverage

                        action_stats[action].visits += 1
                        action_stats[action].total_value += pnl_pct / 10  # Normalize
                        if pnl_pct > 0:
                            action_stats[action].wins += 1
                        else:
                            action_stats[action].losses += 1
                    continue

                # OPEN_LONG or OPEN_SHORT
                direction = "LONG" if action == ActionType.OPEN_LONG else "SHORT"

                # Simulate trade with default SL/TP
                trade_result = simulate_trade_outcome(
                    entry_price=current_price,
                    direction=direction,
                    leverage=3,  # Default leverage
                    stop_loss_pct=3.0,
                    take_profit_pct=4.0,
                    price_path=price_path,
                )

                action_stats[action].visits += 1
                action_stats[action].total_value += trade_result.pnl_pct / 10  # Normalize
                if trade_result.pnl_pct > 0:
                    action_stats[action].wins += 1
                else:
                    action_stats[action].losses += 1

        # Find best action
        best_action = ActionType.HOLD
        best_win_rate = 0.0

        for action, stats in action_stats.items():
            if stats.win_rate > best_win_rate:
                best_win_rate = stats.win_rate
                best_action = action

        # Check if proposed action meets threshold
        if proposed_action is not None:
            proposed_win_rate = action_stats[proposed_action].win_rate
            should_execute = proposed_win_rate >= self.config.min_win_probability
        else:
            proposed_win_rate = best_win_rate
            should_execute = best_win_rate >= self.config.min_win_probability

        # Build result
        stats_dict = {
            action.name: {
                "visits": stats.visits,
                "mean_value": stats.mean_value,
                "win_rate": stats.win_rate,
                "wins": stats.wins,
                "losses": stats.losses,
            }
            for action, stats in action_stats.items()
        }

        # Build reasoning
        reasoning_parts = [
            f"MCTS ran {self.config.num_simulations} simulations.",
            f"Best action: {best_action.name} (win rate: {best_win_rate:.1%})",
        ]

        if proposed_action is not None:
            reasoning_parts.append(
                f"Proposed {proposed_action.name}: {proposed_win_rate:.1%} win rate"
            )
            if should_execute:
                reasoning_parts.append(f"APPROVED (>= {self.config.min_win_probability:.0%} threshold)")
            else:
                reasoning_parts.append(f"VETOED (< {self.config.min_win_probability:.0%} threshold)")

        return MCTSResult(
            recommended_action=best_action,
            win_probability=proposed_win_rate if proposed_action else best_win_rate,
            action_stats=stats_dict,
            total_simulations=self.config.num_simulations,
            should_execute=should_execute,
            reasoning=" | ".join(reasoning_parts),
        )

    def should_execute_trade(
        self,
        state: MarketState,
        symbol: str,
        action: ActionType,
    ) -> Tuple[bool, float, str]:
        """
        Quick check if a trade should be executed.

        Returns:
            (should_execute, win_probability, reason)
        """
        result = self.search(state, symbol, proposed_action=action)
        return result.should_execute, result.win_probability, result.reasoning


# Test
if __name__ == "__main__":
    from .market_state import MarketState, IndicatorState, PositionState

    # Create a bullish market state
    state = MarketState()
    state.indicators["BTC"] = IndicatorState(
        symbol="BTC",
        price=100000,
        ema20=98000,  # Price above EMA = bullish
        rsi_14=60,
        macd=50,
        atr_14=1500,  # ~1.5% volatility
    )
    state.balance_usd = 1000

    # Run MCTS
    mcts = MCTS()
    print("=== MCTS Simulation ===")
    print(f"Current price: $100,000")
    print(f"EMA20: $98,000 (bullish)")
    print(f"Volatility (ATR): $1,500")
    print()

    result = mcts.search(state, "BTC")
    print(f"Recommended action: {result.recommended_action.name}")
    print(f"Win probability: {result.win_probability:.1%}")
    print(f"Should execute: {result.should_execute}")
    print(f"Reasoning: {result.reasoning}")
    print()

    print("Action Statistics:")
    for action_name, stats in result.action_stats.items():
        print(f"  {action_name}: win_rate={stats['win_rate']:.1%}, "
              f"mean_value={stats['mean_value']:.3f}, visits={stats['visits']}")

    # Test with proposed LONG action
    print("\n=== Testing OPEN_LONG ===")
    should_exec, win_prob, reason = mcts.should_execute_trade(
        state, "BTC", ActionType.OPEN_LONG
    )
    print(f"Should execute LONG: {should_exec}")
    print(f"Win probability: {win_prob:.1%}")
    print(f"Reason: {reason}")

    # Test with bearish market
    print("\n=== Bearish Market Test ===")
    state.indicators["BTC"].ema20 = 102000  # Price below EMA = bearish
    result = mcts.search(state, "BTC", proposed_action=ActionType.OPEN_LONG)
    print(f"LONG in bearish market:")
    print(f"Win probability: {result.win_probability:.1%}")
    print(f"Should execute: {result.should_execute}")
