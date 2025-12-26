"""
Policy Network for AlphaTrader
==============================

Neural network that decides what action to take given the market state.

Architecture:
- Input: Market state vector (from MarketState.to_vector())
- Hidden: 3 fully connected layers with ReLU/LayerNorm
- Output: Action probabilities (softmax over action types) + continuous values

Actions:
- HOLD (0)
- OPEN_LONG (1)
- OPEN_SHORT (2)
- CLOSE (3)

Plus continuous outputs:
- leverage (1-10)
- position_size_pct (0.5-2.0)
- confidence (0-1)
"""

import numpy as np
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass

from .market_state import MarketState, Action, ActionType
from .config import NetworkConfig, get_config

# Try to import PyTorch, fall back to numpy if not available
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.distributions import Categorical
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None


@dataclass
class PolicyOutput:
    """Output from the policy network."""
    action_type: ActionType
    action_probs: np.ndarray  # Probabilities for each action
    leverage: int
    position_size_pct: float
    confidence: float
    log_prob: float  # Log probability of selected action (for training)
    entropy: float  # Entropy of action distribution


class PolicyNetworkNumpy:
    """
    Simple numpy-based policy network for when PyTorch is not available.
    Uses fixed weights (no training) - mainly for testing.
    """

    def __init__(self, state_dim: int = 64, num_actions: int = 4):
        self.state_dim = state_dim
        self.num_actions = num_actions

        # Initialize random weights
        np.random.seed(42)
        self.w1 = np.random.randn(state_dim, 128) * 0.1
        self.b1 = np.zeros(128)
        self.w2 = np.random.randn(128, 64) * 0.1
        self.b2 = np.zeros(64)
        self.w_action = np.random.randn(64, num_actions) * 0.1
        self.b_action = np.zeros(num_actions)
        self.w_leverage = np.random.randn(64, 1) * 0.1
        self.w_size = np.random.randn(64, 1) * 0.1

    def forward(self, state: np.ndarray) -> PolicyOutput:
        """Forward pass."""
        # Hidden layers
        h1 = np.maximum(0, state @ self.w1 + self.b1)  # ReLU
        h2 = np.maximum(0, h1 @ self.w2 + self.b2)  # ReLU

        # Action logits
        action_logits = h2 @ self.w_action + self.b_action
        action_probs = np.exp(action_logits - np.max(action_logits))
        action_probs = action_probs / np.sum(action_probs)

        # Sample action
        action_idx = np.random.choice(self.num_actions, p=action_probs)

        # Continuous outputs
        leverage_raw = float(h2 @ self.w_leverage)
        leverage = int(np.clip(1 + 9 * (1 / (1 + np.exp(-leverage_raw))), 1, 10))

        size_raw = float(h2 @ self.w_size)
        size_pct = float(np.clip(0.5 + 1.5 * (1 / (1 + np.exp(-size_raw))), 0.5, 2.0))

        return PolicyOutput(
            action_type=ActionType(action_idx),
            action_probs=action_probs,
            leverage=leverage,
            position_size_pct=size_pct,
            confidence=float(action_probs[action_idx]),
            log_prob=float(np.log(action_probs[action_idx] + 1e-8)),
            entropy=float(-np.sum(action_probs * np.log(action_probs + 1e-8))),
        )

    def get_action(self, state: MarketState, symbol: str = "BTC") -> Action:
        """Get action from market state."""
        state_vec = state.to_vector(symbol)
        output = self.forward(state_vec)

        return Action(
            action_type=output.action_type,
            symbol=symbol,
            leverage=output.leverage,
            position_size_pct=output.position_size_pct,
            confidence=output.confidence,
        )


if TORCH_AVAILABLE:
    class PolicyNetworkTorch(nn.Module):
        """
        PyTorch-based policy network for training.

        Architecture:
        - Input layer: state_dim -> hidden[0]
        - Hidden layers with LayerNorm and Dropout
        - Action head: softmax over action types
        - Leverage head: sigmoid scaled to [1, 10]
        - Size head: sigmoid scaled to [0.5, 2.0]
        - Confidence head: sigmoid [0, 1]
        """

        def __init__(self, config: Optional[NetworkConfig] = None):
            super().__init__()

            self.config = config or get_config().network
            state_dim = self.config.state_dim
            hidden_layers = self.config.policy_hidden_layers
            dropout = self.config.policy_dropout

            # Build hidden layers
            layers = []
            prev_dim = state_dim
            for hidden_dim in hidden_layers:
                layers.append(nn.Linear(prev_dim, hidden_dim))
                if self.config.batch_norm:
                    layers.append(nn.LayerNorm(hidden_dim))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(dropout))
                prev_dim = hidden_dim

            self.hidden = nn.Sequential(*layers)

            # Output heads
            final_dim = hidden_layers[-1] if hidden_layers else state_dim

            # Action head (4 actions)
            self.action_head = nn.Linear(final_dim, 4)

            # Leverage head (continuous, mapped to 1-10)
            self.leverage_head = nn.Linear(final_dim, 1)

            # Position size head (continuous, mapped to 0.5-2.0)
            self.size_head = nn.Linear(final_dim, 1)

            # Confidence head (how confident is the network in its decision)
            self.confidence_head = nn.Linear(final_dim, 1)

        def forward(
            self,
            state: torch.Tensor,
            deterministic: bool = False
        ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
            """
            Forward pass.

            Args:
                state: (batch_size, state_dim) tensor
                deterministic: If True, take argmax action instead of sampling

            Returns:
                action_probs: (batch_size, 4) action probabilities
                leverage: (batch_size, 1) leverage values [1-10]
                size_pct: (batch_size, 1) position size [0.5-2.0]
                confidence: (batch_size, 1) confidence [0-1]
                entropy: (batch_size,) entropy of action distribution
            """
            # Hidden layers
            features = self.hidden(state)

            # Action probabilities
            action_logits = self.action_head(features)
            action_probs = F.softmax(action_logits, dim=-1)

            # Continuous outputs
            leverage = 1 + 9 * torch.sigmoid(self.leverage_head(features))  # [1, 10]
            size_pct = 0.5 + 1.5 * torch.sigmoid(self.size_head(features))  # [0.5, 2.0]
            confidence = torch.sigmoid(self.confidence_head(features))  # [0, 1]

            # Entropy
            entropy = -torch.sum(action_probs * torch.log(action_probs + 1e-8), dim=-1)

            return action_probs, leverage, size_pct, confidence, entropy

        def get_action(
            self,
            state: MarketState,
            symbol: str = "BTC",
            deterministic: bool = False
        ) -> Tuple[Action, PolicyOutput]:
            """
            Get action from market state.

            Returns:
                (Action, PolicyOutput) tuple
            """
            # Convert state to tensor
            state_vec = state.to_vector(symbol)
            state_tensor = torch.FloatTensor(state_vec).unsqueeze(0)

            with torch.no_grad():
                action_probs, leverage, size_pct, confidence, entropy = self.forward(
                    state_tensor, deterministic
                )

            # Convert to numpy
            probs = action_probs.squeeze().numpy()

            # Sample or argmax action
            if deterministic:
                action_idx = np.argmax(probs)
            else:
                dist = Categorical(action_probs)
                action_idx = dist.sample().item()

            log_prob = np.log(probs[action_idx] + 1e-8)

            output = PolicyOutput(
                action_type=ActionType(action_idx),
                action_probs=probs,
                leverage=int(round(leverage.item())),
                position_size_pct=float(size_pct.item()),
                confidence=float(confidence.item()),
                log_prob=float(log_prob),
                entropy=float(entropy.item()),
            )

            action = Action(
                action_type=output.action_type,
                symbol=symbol,
                leverage=output.leverage,
                position_size_pct=output.position_size_pct,
                confidence=output.confidence,
            )

            return action, output

        def evaluate_actions(
            self,
            states: torch.Tensor,
            actions: torch.Tensor
        ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            """
            Evaluate log probabilities of given actions (for PPO training).

            Args:
                states: (batch_size, state_dim)
                actions: (batch_size,) action indices

            Returns:
                log_probs: (batch_size,) log probabilities
                entropy: (batch_size,) entropy
                values: (batch_size,) (placeholder, should come from value network)
            """
            action_probs, _, _, _, entropy = self.forward(states)

            # Get log probs for selected actions
            dist = Categorical(action_probs)
            log_probs = dist.log_prob(actions)

            return log_probs, entropy, torch.zeros_like(log_probs)


# Factory function
def create_policy_network(config: Optional[NetworkConfig] = None) -> PolicyNetworkNumpy:
    """Create a policy network (PyTorch if available, else numpy)."""
    if TORCH_AVAILABLE:
        return PolicyNetworkTorch(config)
    else:
        state_dim = config.state_dim if config else 64
        return PolicyNetworkNumpy(state_dim)


# Test
if __name__ == "__main__":
    print(f"PyTorch available: {TORCH_AVAILABLE}")

    # Create dummy state
    from .market_state import MarketState, IndicatorState, SentimentState, ScoreState

    state = MarketState()
    state.indicators["BTC"] = IndicatorState(
        symbol="BTC",
        price=100000,
        ema20=99000,
        rsi_14=65,
        macd=50,
    )
    state.sentiment = SentimentState(fear_greed_index=60)
    state.scores["BTC"] = ScoreState(
        score_bullish=25,
        score_bearish=10,
        net_score=15,
        direction="LONG",
        confidence="NORMAL",
    )
    state.balance_usd = 1000

    # Create network and get action
    network = create_policy_network()
    action = network.get_action(state, "BTC")

    print(f"\nAction: {action.action_type.name}")
    print(f"Leverage: {action.leverage}")
    print(f"Size: {action.position_size_pct:.2f}x")
    print(f"Confidence: {action.confidence:.2f}")
