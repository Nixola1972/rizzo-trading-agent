"""
AlphaTrader RL Trainer
======================

Training loop for the Policy and Value networks using PPO (Proximal Policy Optimization).

Training modes:
1. Historical: Train on historical price data
2. Arena: Train using the Arena simulator
3. Self-Play: Two policies compete (future)

Usage:
    python -m alpha.trainer --episodes 10000 --checkpoint-dir alpha/checkpoints
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import numpy as np

from .config import AlphaConfig, TrainingConfig, get_config
from .market_state import MarketState, Action, ActionType, create_state_from_data
from .reward import RewardCalculator, TradeResult
from .policy_network import create_policy_network, PolicyOutput
from .value_network import create_value_network, create_actor_critic

# Try importing PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """Single experience tuple for replay buffer."""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    log_prob: float
    value: float


@dataclass
class EpisodeStats:
    """Statistics for a training episode."""
    episode: int
    total_reward: float
    num_trades: int
    win_rate: float
    avg_pnl: float
    policy_loss: float = 0.0
    value_loss: float = 0.0
    entropy: float = 0.0


class ReplayBuffer:
    """Experience replay buffer for training."""

    def __init__(self, capacity: int = 100000):
        self.capacity = capacity
        self.buffer: List[Experience] = []
        self.position = 0

    def push(self, experience: Experience):
        """Add experience to buffer."""
        if len(self.buffer) < self.capacity:
            self.buffer.append(experience)
        else:
            self.buffer[self.position] = experience
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size: int) -> List[Experience]:
        """Sample random batch."""
        indices = np.random.choice(len(self.buffer), batch_size, replace=False)
        return [self.buffer[i] for i in indices]

    def __len__(self) -> int:
        return len(self.buffer)

    def clear(self):
        """Clear buffer."""
        self.buffer = []
        self.position = 0


class PPOTrainer:
    """
    Proximal Policy Optimization trainer.

    PPO is a stable, sample-efficient RL algorithm that works well for continuous action spaces.
    """

    def __init__(self, config: Optional[TrainingConfig] = None):
        self.config = config or get_config().training

        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available. Training disabled.")
            self.enabled = False
            return

        self.enabled = True

        # Create networks
        self.actor_critic = create_actor_critic()
        self.policy = self.actor_critic.policy
        self.value = self.actor_critic.value

        # Optimizers
        self.policy_optimizer = optim.Adam(
            self.policy.parameters(),
            lr=get_config().network.policy_learning_rate
        )
        self.value_optimizer = optim.Adam(
            self.value.parameters(),
            lr=get_config().network.value_learning_rate
        )

        # Reward calculator
        self.reward_calc = RewardCalculator()

        # Buffer
        self.buffer = ReplayBuffer(self.config.buffer_size)

        # Stats
        self.episode_stats: List[EpisodeStats] = []
        self.best_reward = float('-inf')

    def compute_gae(
        self,
        rewards: List[float],
        values: List[float],
        dones: List[bool],
        next_value: float,
    ) -> Tuple[List[float], List[float]]:
        """
        Compute Generalized Advantage Estimation (GAE).

        Returns:
            (advantages, returns)
        """
        advantages = []
        returns = []
        gae = 0

        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_val = next_value
                next_done = 1.0
            else:
                next_val = values[t + 1]
                next_done = 1.0 - float(dones[t + 1])

            delta = rewards[t] + self.config.gamma * next_val * next_done - values[t]
            gae = delta + self.config.gamma * self.config.gae_lambda * next_done * gae

            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])

        return advantages, returns

    def ppo_update(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        old_log_probs: torch.Tensor,
        returns: torch.Tensor,
        advantages: torch.Tensor,
    ) -> Tuple[float, float, float]:
        """
        Perform PPO update step.

        Returns:
            (policy_loss, value_loss, entropy)
        """
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        total_policy_loss = 0
        total_value_loss = 0
        total_entropy = 0

        for _ in range(self.config.ppo_epochs):
            # Get current policy output
            log_probs, entropy, _ = self.policy.evaluate_actions(states, actions)

            # Get current value estimate
            values, _ = self.value.batch_estimate(states)
            values = values.squeeze()

            # PPO ratio
            ratio = torch.exp(log_probs - old_log_probs)

            # Clipped surrogate objective
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.config.ppo_clip, 1 + self.config.ppo_clip) * advantages
            policy_loss = -torch.min(surr1, surr2).mean()

            # Value loss
            value_loss = nn.MSELoss()(values, returns)

            # Entropy bonus (encourages exploration)
            entropy_loss = -entropy.mean()

            # Total loss
            loss = (
                policy_loss +
                self.config.value_loss_coef * value_loss +
                self.config.entropy_coef * entropy_loss
            )

            # Update
            self.policy_optimizer.zero_grad()
            self.value_optimizer.zero_grad()
            loss.backward()

            # Gradient clipping
            nn.utils.clip_grad_norm_(self.policy.parameters(), get_config().network.gradient_clip)
            nn.utils.clip_grad_norm_(self.value.parameters(), get_config().network.gradient_clip)

            self.policy_optimizer.step()
            self.value_optimizer.step()

            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            total_entropy += entropy.mean().item()

        num_epochs = self.config.ppo_epochs
        return total_policy_loss / num_epochs, total_value_loss / num_epochs, total_entropy / num_epochs

    def train_episode(
        self,
        env_data: List[Dict],  # List of market states from historical data
        symbol: str = "BTC",
    ) -> EpisodeStats:
        """
        Train on a single episode (sequence of market states).

        Args:
            env_data: List of dictionaries with market data
            symbol: Symbol to trade

        Returns:
            EpisodeStats for this episode
        """
        if not self.enabled:
            return EpisodeStats(0, 0, 0, 0, 0)

        states = []
        actions = []
        rewards = []
        values = []
        log_probs = []
        dones = []

        # Reset reward calculator
        self.reward_calc.reset_episode()

        # Current position state
        position = None
        entry_idx = 0

        for i, data in enumerate(env_data):
            # Create market state
            state = create_state_from_data(
                indicators_data={symbol: data.get('indicators', {})},
                sentiment_data=data.get('sentiment', {}),
                forecast_data={symbol: data.get('forecast', {})},
                score_data={symbol: data.get('score', {})},
                position_data=position,
                account_data=data.get('account', {}),
            )

            # Get action from policy
            action, policy_output = self.policy.get_action(state, symbol)
            value_output = self.value.estimate(state, symbol)

            # Store experience
            states.append(state.to_vector(symbol))
            actions.append(action.action_type.value)
            log_probs.append(policy_output.log_prob)
            values.append(value_output.value)

            # Execute action and get reward
            reward = 0.0
            done = False

            if action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
                if position is None:
                    # Open position
                    position = {
                        'has_position': True,
                        'symbol': symbol,
                        'direction': 'LONG' if action.action_type == ActionType.OPEN_LONG else 'SHORT',
                        'entry_price': data['indicators']['price'],
                        'current_price': data['indicators']['price'],
                        'leverage': action.leverage,
                        'size_usd': 50,
                        'unrealized_pnl_pct': 0,
                        'duration_hours': 0,
                        'max_profit_pct': 0,
                        'max_loss_pct': 0,
                    }
                    entry_idx = i
                    reward = -0.005  # Small cost for opening

            elif action.action_type == ActionType.CLOSE:
                if position is not None:
                    # Close position and calculate reward
                    exit_price = data['indicators']['price']
                    entry_price = position['entry_price']
                    direction = position['direction']
                    leverage = position['leverage']

                    # Calculate P&L
                    if direction == 'LONG':
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * leverage
                    else:
                        pnl_pct = ((entry_price - exit_price) / entry_price) * 100 * leverage

                    # Create trade result
                    trade_result = TradeResult(
                        symbol=symbol,
                        direction=direction,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        size_usd=50,
                        leverage=leverage,
                        entry_time=datetime.utcnow(),
                        exit_time=datetime.utcnow(),
                        pnl_usd=pnl_pct * 0.5,  # Approximate
                        pnl_pct=pnl_pct,
                        max_profit_pct=max(position['max_profit_pct'], pnl_pct),
                        max_loss_pct=abs(min(position['max_loss_pct'], pnl_pct)),
                        exit_reason='AI',
                    )

                    # Get reward from reward calculator
                    reward_breakdown = self.reward_calc.calculate_trade_reward(trade_result)
                    reward = reward_breakdown.total_reward

                    # Clear position
                    position = None

            elif action.action_type == ActionType.HOLD:
                # Update position if we have one
                if position is not None:
                    current_price = data['indicators']['price']
                    entry_price = position['entry_price']
                    direction = position['direction']
                    leverage = position['leverage']

                    if direction == 'LONG':
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100 * leverage
                    else:
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100 * leverage

                    position['current_price'] = current_price
                    position['unrealized_pnl_pct'] = pnl_pct
                    position['duration_hours'] = (i - entry_idx) * 0.25  # Assuming 15min candles
                    position['max_profit_pct'] = max(position['max_profit_pct'], pnl_pct)
                    position['max_loss_pct'] = min(position['max_loss_pct'], pnl_pct)

                    # Small step reward
                    reward = self.reward_calc.calculate_step_reward(
                        'HOLD',
                        pnl_pct,
                        position['duration_hours'],
                        True
                    )

            rewards.append(reward)
            dones.append(i == len(env_data) - 1)

        # Compute advantages and returns
        if len(states) > 0:
            next_value = values[-1] if not dones[-1] else 0
            advantages, returns = self.compute_gae(rewards, values, dones, next_value)

            # Convert to tensors
            states_t = torch.FloatTensor(np.array(states))
            actions_t = torch.LongTensor(actions)
            old_log_probs_t = torch.FloatTensor(log_probs)
            returns_t = torch.FloatTensor(returns)
            advantages_t = torch.FloatTensor(advantages)

            # PPO update
            policy_loss, value_loss, entropy = self.ppo_update(
                states_t, actions_t, old_log_probs_t, returns_t, advantages_t
            )
        else:
            policy_loss, value_loss, entropy = 0, 0, 0

        # Get episode stats
        stats = self.reward_calc.get_stats()

        return EpisodeStats(
            episode=len(self.episode_stats),
            total_reward=sum(rewards),
            num_trades=stats.get('trades', 0),
            win_rate=stats.get('win_rate', 0),
            avg_pnl=stats.get('avg_return', 0),
            policy_loss=policy_loss,
            value_loss=value_loss,
            entropy=entropy,
        )

    def save_checkpoint(self, path: str):
        """Save model checkpoint."""
        if not self.enabled:
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)

        torch.save({
            'policy_state_dict': self.policy.state_dict(),
            'value_state_dict': self.value.state_dict(),
            'policy_optimizer': self.policy_optimizer.state_dict(),
            'value_optimizer': self.value_optimizer.state_dict(),
            'episode_stats': self.episode_stats,
            'best_reward': self.best_reward,
        }, path)

        logger.info(f"Saved checkpoint to {path}")

    def load_checkpoint(self, path: str):
        """Load model checkpoint."""
        if not self.enabled or not os.path.exists(path):
            return False

        checkpoint = torch.load(path)
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.value.load_state_dict(checkpoint['value_state_dict'])
        self.policy_optimizer.load_state_dict(checkpoint['policy_optimizer'])
        self.value_optimizer.load_state_dict(checkpoint['value_optimizer'])
        self.episode_stats = checkpoint.get('episode_stats', [])
        self.best_reward = checkpoint.get('best_reward', float('-inf'))

        logger.info(f"Loaded checkpoint from {path}")
        return True


def generate_synthetic_data(num_episodes: int = 100, episode_length: int = 100) -> List[List[Dict]]:
    """
    Generate synthetic market data for testing training loop.

    This is a placeholder - real training should use historical data from Arena DB.
    """
    episodes = []

    for _ in range(num_episodes):
        episode = []
        price = 100000 + np.random.randn() * 5000

        for _ in range(episode_length):
            # Random walk price
            price *= 1 + np.random.randn() * 0.01

            episode.append({
                'indicators': {
                    'price': price,
                    'ema20': price * (1 + np.random.randn() * 0.01),
                    'ema50': price * (1 + np.random.randn() * 0.02),
                    'rsi_14': 50 + np.random.randn() * 15,
                    'macd': np.random.randn() * 50,
                    'atr_14': price * 0.015,
                },
                'sentiment': {
                    'value': int(50 + np.random.randn() * 20),
                },
                'forecast': {
                    'change_pct': np.random.randn() * 0.5,
                },
                'score': {
                    'score_bullish': max(0, 20 + np.random.randn() * 10),
                    'score_bearish': max(0, 15 + np.random.randn() * 10),
                    'net_score': np.random.randn() * 15,
                    'direction': np.random.choice(['LONG', 'SHORT', 'HOLD']),
                    'confidence': np.random.choice(['WEAK', 'NORMAL', 'STRONG']),
                },
                'account': {
                    'balance_usd': 1000,
                    'equity_usd': 1000,
                },
            })

        episodes.append(episode)

    return episodes


def main():
    """Main training loop."""
    parser = argparse.ArgumentParser(description='AlphaTrader Trainer')
    parser.add_argument('--episodes', type=int, default=1000, help='Number of episodes')
    parser.add_argument('--checkpoint-dir', type=str, default='alpha/checkpoints')
    parser.add_argument('--resume', type=str, default=None, help='Resume from checkpoint')
    args = parser.parse_args()

    if not TORCH_AVAILABLE:
        logger.error("PyTorch is required for training. Please install: pip install torch")
        sys.exit(1)

    # Create trainer
    trainer = PPOTrainer()

    # Resume if specified
    if args.resume:
        trainer.load_checkpoint(args.resume)

    # Generate synthetic data (replace with real data in production)
    logger.info("Generating synthetic training data...")
    episodes = generate_synthetic_data(num_episodes=args.episodes, episode_length=100)

    # Training loop
    logger.info(f"Starting training for {len(episodes)} episodes...")

    for i, episode_data in enumerate(episodes):
        stats = trainer.train_episode(episode_data, symbol="BTC")
        trainer.episode_stats.append(stats)

        # Log progress
        if (i + 1) % 100 == 0:
            recent_stats = trainer.episode_stats[-100:]
            avg_reward = np.mean([s.total_reward for s in recent_stats])
            avg_win_rate = np.mean([s.win_rate for s in recent_stats])

            logger.info(
                f"Episode {i + 1}/{len(episodes)} | "
                f"Avg Reward: {avg_reward:.3f} | "
                f"Avg Win Rate: {avg_win_rate:.1%} | "
                f"Policy Loss: {stats.policy_loss:.4f}"
            )

        # Save checkpoint
        if (i + 1) % 500 == 0:
            checkpoint_path = os.path.join(args.checkpoint_dir, f"checkpoint_{i + 1}.pt")
            trainer.save_checkpoint(checkpoint_path)

    # Save final model
    final_path = os.path.join(args.checkpoint_dir, "final_model.pt")
    trainer.save_checkpoint(final_path)
    logger.info(f"Training complete. Final model saved to {final_path}")


if __name__ == "__main__":
    main()
