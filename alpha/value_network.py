"""
Value Network for AlphaTrader
=============================

Neural network that estimates the expected value (probability of profit)
of a given market state.

This is the "Value Network" from AlphaGo - it tells us how "good" a state is
before we take any action.

Architecture:
- Input: Market state vector (same as PolicyNetwork)
- Hidden: 3 fully connected layers
- Output: Single value in [-1, 1] representing expected outcome

Interpretation:
- +1.0: Very high probability of profit
- 0.0: Neutral / uncertain
- -1.0: Very high probability of loss
"""

import numpy as np
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

from .market_state import MarketState
from .config import NetworkConfig, get_config

# Try to import PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None


@dataclass
class ValueOutput:
    """Output from the value network."""
    value: float  # Expected value [-1, 1]
    win_probability: float  # Estimated probability of winning [0, 1]
    confidence: float  # Network's confidence in its estimate [0, 1]


class ValueNetworkNumpy:
    """
    Simple numpy-based value network (no training, for testing).
    """

    def __init__(self, state_dim: int = 64):
        self.state_dim = state_dim

        # Initialize random weights
        np.random.seed(43)
        self.w1 = np.random.randn(state_dim, 128) * 0.1
        self.b1 = np.zeros(128)
        self.w2 = np.random.randn(128, 64) * 0.1
        self.b2 = np.zeros(64)
        self.w_value = np.random.randn(64, 1) * 0.1
        self.w_conf = np.random.randn(64, 1) * 0.1

    def forward(self, state: np.ndarray) -> ValueOutput:
        """Forward pass."""
        # Hidden layers
        h1 = np.maximum(0, state @ self.w1 + self.b1)
        h2 = np.maximum(0, h1 @ self.w2 + self.b2)

        # Value output (tanh for [-1, 1])
        value_raw = float(h2 @ self.w_value)
        value = float(np.tanh(value_raw))

        # Confidence
        conf_raw = float(h2 @ self.w_conf)
        confidence = float(1 / (1 + np.exp(-conf_raw)))

        # Win probability from value
        win_prob = (value + 1) / 2  # Map [-1, 1] to [0, 1]

        return ValueOutput(
            value=value,
            win_probability=win_prob,
            confidence=confidence,
        )

    def estimate(self, state: MarketState, symbol: str = "BTC") -> ValueOutput:
        """Estimate value of market state."""
        state_vec = state.to_vector(symbol)
        return self.forward(state_vec)


if TORCH_AVAILABLE:
    class ValueNetworkTorch(nn.Module):
        """
        PyTorch-based value network for training.

        Architecture:
        - Input layer: state_dim -> hidden[0]
        - Hidden layers with LayerNorm and Dropout
        - Value head: tanh output [-1, 1]
        - Confidence head: sigmoid [0, 1]
        """

        def __init__(self, config: Optional[NetworkConfig] = None):
            super().__init__()

            self.config = config or get_config().network
            state_dim = self.config.state_dim
            hidden_layers = self.config.value_hidden_layers
            dropout = self.config.value_dropout

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

            # Value head (single output, tanh activation)
            self.value_head = nn.Sequential(
                nn.Linear(final_dim, 1),
                nn.Tanh()
            )

            # Confidence head (how sure is the network)
            self.confidence_head = nn.Sequential(
                nn.Linear(final_dim, 1),
                nn.Sigmoid()
            )

        def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Forward pass.

            Args:
                state: (batch_size, state_dim) tensor

            Returns:
                value: (batch_size, 1) values in [-1, 1]
                confidence: (batch_size, 1) confidence in [0, 1]
            """
            features = self.hidden(state)
            value = self.value_head(features)
            confidence = self.confidence_head(features)
            return value, confidence

        def estimate(self, state: MarketState, symbol: str = "BTC") -> ValueOutput:
            """Estimate value of market state."""
            state_vec = state.to_vector(symbol)
            state_tensor = torch.FloatTensor(state_vec).unsqueeze(0)

            with torch.no_grad():
                value, confidence = self.forward(state_tensor)

            value_scalar = float(value.item())
            conf_scalar = float(confidence.item())
            win_prob = (value_scalar + 1) / 2

            return ValueOutput(
                value=value_scalar,
                win_probability=win_prob,
                confidence=conf_scalar,
            )

        def batch_estimate(self, states: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Estimate values for a batch of states.

            Args:
                states: (batch_size, state_dim)

            Returns:
                values: (batch_size, 1)
                confidences: (batch_size, 1)
            """
            return self.forward(states)


class CombinedActorCritic:
    """
    Combined Actor-Critic network (Policy + Value sharing some layers).

    This is more efficient for training as both networks share features.
    """

    def __init__(self, config: Optional[NetworkConfig] = None):
        self.config = config or get_config().network

        if TORCH_AVAILABLE:
            self._init_torch()
        else:
            self._init_numpy()

    def _init_numpy(self):
        """Initialize numpy versions."""
        from .policy_network import PolicyNetworkNumpy
        self.policy = PolicyNetworkNumpy(self.config.state_dim)
        self.value = ValueNetworkNumpy(self.config.state_dim)
        self.is_torch = False

    def _init_torch(self):
        """Initialize PyTorch version with shared backbone."""
        from .policy_network import PolicyNetworkTorch
        self.policy = PolicyNetworkTorch(self.config)
        self.value = ValueNetworkTorch(self.config)
        self.is_torch = True

    def get_action_and_value(
        self,
        state: MarketState,
        symbol: str = "BTC",
        deterministic: bool = False
    ) -> Tuple:
        """
        Get both action and value estimate for a state.

        Returns:
            (action, policy_output, value_output)
        """
        from .policy_network import PolicyOutput

        if self.is_torch:
            action, policy_output = self.policy.get_action(state, symbol, deterministic)
        else:
            action = self.policy.get_action(state, symbol)
            policy_output = PolicyOutput(
                action_type=action.action_type,
                action_probs=np.array([0.25, 0.25, 0.25, 0.25]),
                leverage=action.leverage,
                position_size_pct=action.position_size_pct,
                confidence=action.confidence,
                log_prob=0.0,
                entropy=0.0,
            )

        value_output = self.value.estimate(state, symbol)

        return action, policy_output, value_output


# Factory function
def create_value_network(config: Optional[NetworkConfig] = None) -> ValueNetworkNumpy:
    """Create a value network (PyTorch if available, else numpy)."""
    if TORCH_AVAILABLE:
        return ValueNetworkTorch(config)
    else:
        state_dim = config.state_dim if config else 64
        return ValueNetworkNumpy(state_dim)


def create_actor_critic(config: Optional[NetworkConfig] = None) -> CombinedActorCritic:
    """Create combined actor-critic network."""
    return CombinedActorCritic(config)


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

    # Create network and estimate value
    network = create_value_network()
    output = network.estimate(state, "BTC")

    print(f"\nValue: {output.value:.3f}")
    print(f"Win probability: {output.win_probability:.1%}")
    print(f"Confidence: {output.confidence:.1%}")

    # Test actor-critic
    print("\n=== Actor-Critic ===")
    ac = create_actor_critic()
    action, policy_out, value_out = ac.get_action_and_value(state, "BTC")

    print(f"Action: {action.action_type.name}")
    print(f"Value: {value_out.value:.3f}")
    print(f"Win prob: {value_out.win_probability:.1%}")
