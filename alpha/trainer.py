"""
AlphaTrader RL Trainer
======================

Training loop for the Policy and Value networks using PPO (Proximal Policy Optimization).

Training modes:
1. Historical: Train on historical price data from HyperLiquid
2. Arena: Train using the Arena simulator
3. Self-Play: Two policies compete (future)

Usage:
    # Train on HyperLiquid historical data
    python -m alpha.trainer --data-source hyperliquid --episodes 1000

    # First download data, then train
    python -m alpha.data_loader --symbols BTC ETH SOL --days 60 --interval 15m
    python -m alpha.trainer --data-source hyperliquid --episodes 1000

    # Train on synthetic data (for testing)
    python -m alpha.trainer --data-source synthetic --episodes 100
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

        # Only save model weights (not episode_stats to avoid class serialization issues)
        torch.save({
            'policy_state_dict': self.policy.state_dict(),
            'value_state_dict': self.value.state_dict(),
            'policy_optimizer': self.policy_optimizer.state_dict(),
            'value_optimizer': self.value_optimizer.state_dict(),
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

    This is a placeholder - real training should use historical data.
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


def load_hyperliquid_data(
    data_path: str = "alpha/data/training_episodes.pkl",
    max_episodes: Optional[int] = None,
) -> List[List[Dict]]:
    """
    Load training episodes from HyperLiquid historical data.

    The data should be downloaded first using:
        python -m alpha.data_loader --symbols BTC ETH SOL --days 60

    Args:
        data_path: Path to the training episodes pickle file
        max_episodes: Maximum number of episodes to load (None = all)

    Returns:
        List of episodes, each episode is a list of market state dicts
    """
    import pickle
    # Episodes are saved as dicts, no class import needed

    if not os.path.exists(data_path):
        logger.error(f"Data file not found: {data_path}")
        logger.error("Please download data first:")
        logger.error("  python -m alpha.data_loader --symbols BTC ETH SOL --days 60")
        return []

    # Load episodes from pickle (saved as list of dicts)
    with open(data_path, "rb") as f:
        raw_episodes = pickle.load(f)

    logger.info(f"Loaded {len(raw_episodes)} episodes from {data_path}")

    if max_episodes:
        raw_episodes = raw_episodes[:max_episodes]

    # Convert episode dicts to train_episode format
    episodes = []

    for ep in raw_episodes:
        episode = []

        # Access candles from dict (not object attribute)
        candles = ep['candles'] if isinstance(ep, dict) else ep.candles
        for candle in candles:
            # Extract price and indicators from candle
            price = candle.get('close', candle.get('price', 0))
            ema20 = candle.get('ema20', price)
            ema50 = candle.get('ema50', price)
            rsi_14 = candle.get('rsi_14', 50)
            rsi_7 = candle.get('rsi_7', 50)
            macd = candle.get('macd', 0)
            macd_signal = candle.get('macd_signal', 0)
            macd_histogram = candle.get('macd_histogram', 0)
            atr_14 = candle.get('atr_14', price * 0.01)
            adx = candle.get('adx', 25)

            # Bollinger bands
            bb_upper = candle.get('bb_upper', price * 1.02)
            bb_middle = candle.get('bb_middle', price)
            bb_lower = candle.get('bb_lower', price * 0.98)
            bb_pct_b = candle.get('bb_pct_b', 0.5)
            bb_bandwidth = candle.get('bb_bandwidth', 0.04)

            # OBV
            obv_trend = candle.get('obv_trend', 0)

            # Funding rate (if available)
            funding_rate = candle.get('funding_rate', 0)

            # Calculate basic score from indicators
            # This mimics what signal_scorer.py does
            score_bullish = 0
            score_bearish = 0

            # EMA stack contribution
            if price > ema20 > ema50:
                score_bullish += 8  # Bullish EMA stack
            elif price < ema20 < ema50:
                score_bearish += 8  # Bearish EMA stack

            # MACD contribution
            if macd > 0:
                score_bullish += min(5, macd * 20)
            else:
                score_bearish += min(5, abs(macd) * 20)

            # RSI contribution
            if rsi_14 < 30:
                score_bullish += 3  # Oversold
            elif rsi_14 > 70:
                score_bearish += 3  # Overbought

            # ADX contribution (trend strength)
            if adx > 25:
                # Strong trend - boost the dominant direction
                if score_bullish > score_bearish:
                    score_bullish += 2
                else:
                    score_bearish += 2

            # OBV trend
            if obv_trend > 0:
                score_bullish += 2
            elif obv_trend < 0:
                score_bearish += 2

            net_score = score_bullish - score_bearish

            # Determine direction
            if net_score >= 5:
                direction = 'LONG'
                confidence = 'STRONG' if net_score >= 15 else 'NORMAL' if net_score >= 10 else 'WEAK'
            elif net_score <= -5:
                direction = 'SHORT'
                confidence = 'STRONG' if net_score <= -15 else 'NORMAL' if net_score <= -10 else 'WEAK'
            else:
                direction = 'HOLD'
                confidence = 'WEAK'

            # Calculate forecast from price momentum
            # Use EMA difference as a simple trend indicator
            if ema20 > 0:
                forecast_change = ((price / ema20) - 1) * 100
            else:
                forecast_change = 0

            episode.append({
                'indicators': {
                    'price': price,
                    'open': candle.get('open', price),
                    'high': candle.get('high', price),
                    'low': candle.get('low', price),
                    'close': price,
                    'volume': candle.get('volume', 0),
                    'ema20': ema20,
                    'ema50': ema50,
                    'rsi_14': rsi_14,
                    'rsi_7': rsi_7,
                    'macd': macd,
                    'macd_signal': macd_signal,
                    'macd_histogram': macd_histogram,
                    'atr_14': atr_14,
                    'adx': adx,
                    'bb_upper': bb_upper,
                    'bb_middle': bb_middle,
                    'bb_lower': bb_lower,
                    'bb_pct_b': bb_pct_b,
                    'bb_bandwidth': bb_bandwidth,
                    'obv_trend': obv_trend,
                    'funding_rate': funding_rate,
                },
                'sentiment': {
                    # Use RSI as a proxy for sentiment (neutral default)
                    'value': int(50 + (50 - rsi_14) * 0.5),  # Inverse correlation
                },
                'forecast': {
                    'change_pct': forecast_change,
                },
                'score': {
                    'score_bullish': score_bullish,
                    'score_bearish': score_bearish,
                    'net_score': net_score,
                    'direction': direction,
                    'confidence': confidence,
                },
                'account': {
                    'balance_usd': 1000,
                    'equity_usd': 1000,
                },
                'timestamp': candle.get('timestamp'),
            })

        if len(episode) > 0:
            episodes.append(episode)

    logger.info(f"Converted {len(episodes)} episodes to training format")

    # Log sample statistics
    if episodes:
        sample_ep = episodes[0]
        logger.info(f"Sample episode length: {len(sample_ep)} candles")
        # raw_episodes are now dicts, use dict access
        sample_symbol = raw_episodes[0]['symbol'] if raw_episodes else 'unknown'
        logger.info(f"Sample episode symbol: {sample_symbol}")
        if sample_ep:
            logger.info(f"Sample price range: ${sample_ep[0]['indicators']['price']:.2f} - ${sample_ep[-1]['indicators']['price']:.2f}")

    return episodes


def main():
    """Main training loop."""
    parser = argparse.ArgumentParser(description='AlphaTrader Trainer')
    parser.add_argument('--episodes', type=int, default=1000, help='Target total episodes (epochs × data)')
    parser.add_argument('--epochs', type=int, default=None, help='Number of epochs (passes through data)')
    parser.add_argument('--checkpoint-dir', type=str, default='alpha/checkpoints')
    parser.add_argument('--resume', type=str, default=None, help='Resume from checkpoint')
    parser.add_argument('--data-source', type=str, default='synthetic',
                       choices=['synthetic', 'hyperliquid'],
                       help='Data source for training')
    parser.add_argument('--data-path', type=str, default='alpha/data/training_episodes.pkl',
                       help='Path to HyperLiquid training data')
    parser.add_argument('--symbol', type=str, default='BTC',
                       help='Symbol to train on (for filtering)')
    args = parser.parse_args()

    if not TORCH_AVAILABLE:
        logger.error("PyTorch is required for training. Please install: pip install torch")
        sys.exit(1)

    # Create trainer
    trainer = PPOTrainer()

    # Resume if specified
    if args.resume:
        trainer.load_checkpoint(args.resume)

    # Load data based on source
    if args.data_source == 'hyperliquid':
        logger.info("Loading HyperLiquid historical data...")
        episodes = load_hyperliquid_data(
            data_path=args.data_path,
            max_episodes=args.episodes if args.episodes > 0 else None
        )

        if not episodes:
            logger.error("No data loaded. Please download data first:")
            logger.error("  python -m alpha.data_loader --symbols BTC ETH SOL --days 60")
            sys.exit(1)

    else:
        logger.info("Generating synthetic training data...")
        episodes = generate_synthetic_data(num_episodes=args.episodes, episode_length=100)

    # Calculate epochs - repeat data multiple times for more training
    num_data_episodes = len(episodes)
    if args.epochs:
        num_epochs = args.epochs
    else:
        # Calculate epochs needed to reach target episodes
        num_epochs = max(1, args.episodes // num_data_episodes)

    total_training_episodes = num_epochs * num_data_episodes

    logger.info(f"Data episodes: {num_data_episodes}")
    logger.info(f"Epochs: {num_epochs}")
    logger.info(f"Total training iterations: {total_training_episodes}")
    logger.info(f"Data source: {args.data_source}")

    best_avg_reward = float('-inf')
    log_interval = min(100, max(10, total_training_episodes // 50))  # Log ~50 times
    global_step = 0

    for epoch in range(num_epochs):
        # Shuffle episodes each epoch for better generalization
        np.random.shuffle(episodes)

        for i, episode_data in enumerate(episodes):
            global_step += 1
            # Extract symbol from episode if available
            symbol = args.symbol

            stats = trainer.train_episode(episode_data, symbol=symbol)
            trainer.episode_stats.append(stats)

            # Log progress
            if global_step % log_interval == 0 or global_step == total_training_episodes:
                recent_stats = trainer.episode_stats[-log_interval:]
                avg_reward = np.mean([s.total_reward for s in recent_stats])
                avg_win_rate = np.mean([s.win_rate for s in recent_stats])
                avg_trades = np.mean([s.num_trades for s in recent_stats])
                avg_pnl = np.mean([s.avg_pnl for s in recent_stats])

                logger.info(
                    f"Epoch {epoch + 1}/{num_epochs} | Step {global_step}/{total_training_episodes} | "
                    f"Reward: {avg_reward:.3f} | "
                    f"Win Rate: {avg_win_rate:.1%} | "
                    f"Trades: {avg_trades:.1f} | "
                    f"Avg P&L: {avg_pnl:.2f}% | "
                    f"Policy Loss: {stats.policy_loss:.4f}"
                )

                # Save progress status to JSON (for monitoring)
                progress_pct = (global_step / total_training_episodes) * 100
                status = {
                    "status": "training",
                    "epoch": epoch + 1,
                    "total_epochs": num_epochs,
                    "step": global_step,
                    "total_steps": total_training_episodes,
                    "progress_pct": round(progress_pct, 1),
                    "avg_reward": round(avg_reward, 4),
                    "win_rate": round(avg_win_rate * 100, 1),
                    "avg_trades": round(avg_trades, 1),
                    "avg_pnl": round(avg_pnl, 2),
                    "policy_loss": round(stats.policy_loss, 6),
                    "best_reward": round(best_avg_reward, 4),
                    "last_update": datetime.utcnow().isoformat(),
                }
                status_path = os.path.join(args.checkpoint_dir, "training_status.json")
                os.makedirs(args.checkpoint_dir, exist_ok=True)
                with open(status_path, "w") as f:
                    json.dump(status, f, indent=2)

                # Track best model
                if avg_reward > best_avg_reward:
                    best_avg_reward = avg_reward
                    best_path = os.path.join(args.checkpoint_dir, "best_model.pt")
                    trainer.save_checkpoint(best_path)
                    logger.info(f"New best model saved (reward: {avg_reward:.3f})")

            # Regular checkpoint every 500 steps
            if global_step % 500 == 0:
                checkpoint_path = os.path.join(args.checkpoint_dir, f"checkpoint_{global_step}.pt")
                trainer.save_checkpoint(checkpoint_path)

    # Save final model
    final_path = os.path.join(args.checkpoint_dir, "final_model.pt")
    trainer.save_checkpoint(final_path)

    # Final summary
    if trainer.episode_stats:
        final_stats = trainer.episode_stats[-100:] if len(trainer.episode_stats) >= 100 else trainer.episode_stats
        final_reward = np.mean([s.total_reward for s in final_stats])
        final_win_rate = np.mean([s.win_rate for s in final_stats])
        final_pnl = np.mean([s.avg_pnl for s in final_stats])

        logger.info("=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total episodes: {len(trainer.episode_stats)}")
        logger.info(f"Final Avg Reward: {final_reward:.3f}")
        logger.info(f"Final Win Rate: {final_win_rate:.1%}")
        logger.info(f"Final Avg P&L: {final_pnl:.2f}%")
        logger.info(f"Best model saved to: {os.path.join(args.checkpoint_dir, 'best_model.pt')}")
        logger.info(f"Final model saved to: {final_path}")

        # Save final status
        final_status = {
            "status": "completed",
            "episode": len(trainer.episode_stats),
            "total_episodes": len(episodes),
            "progress_pct": 100.0,
            "avg_reward": round(final_reward, 4),
            "win_rate": round(final_win_rate * 100, 1),
            "avg_pnl": round(final_pnl, 2),
            "best_reward": round(best_avg_reward, 4),
            "best_model": os.path.join(args.checkpoint_dir, "best_model.pt"),
            "final_model": final_path,
            "completed_at": datetime.utcnow().isoformat(),
        }
        status_path = os.path.join(args.checkpoint_dir, "training_status.json")
        with open(status_path, "w") as f:
            json.dump(final_status, f, indent=2)


if __name__ == "__main__":
    main()
