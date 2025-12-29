"""
AlphaTrader Configuration
=========================

All configuration for the AlphaTrader system, loaded from environment variables.
Completely separate from botone_v6 configuration.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Load environment
load_dotenv(".env.alpha")  # Separate config file for AlphaTrader
load_dotenv(".env.baseline", override=False)  # Fallback to baseline


def _env_float(key: str, default: float) -> float:
    """Load float from environment."""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    """Load int from environment."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    """Load bool from environment."""
    val = os.getenv(key, str(default)).lower().strip()
    return val in ("true", "1", "yes", "on")


@dataclass
class NetworkConfig:
    """Neural network architecture configuration."""

    # Input dimensions (calculated from MarketState)
    # 7 (position) + 10 (target) + 10 (BTC) + 4 (sentiment) + 5 (score) + 2 (account) + 5 (history) = 43
    state_dim: int = 43

    # Policy Network
    policy_hidden_layers: List[int] = field(default_factory=lambda: [256, 128, 64])
    policy_learning_rate: float = 0.0003
    policy_dropout: float = 0.1

    # Value Network
    value_hidden_layers: List[int] = field(default_factory=lambda: [256, 128, 64])
    value_learning_rate: float = 0.0003
    value_dropout: float = 0.1

    # Shared settings
    activation: str = "relu"  # relu, tanh, leaky_relu
    batch_norm: bool = True
    gradient_clip: float = 1.0


@dataclass
class MCTSConfig:
    """Monte Carlo Tree Search configuration."""

    # Simulation parameters
    num_simulations: int = 100  # Simulations per decision
    max_depth: int = 10  # Max tree depth

    # UCB exploration constant
    c_puct: float = 1.414  # sqrt(2) - classic UCB

    # Threshold for execution (0 = calculate MCTS but never veto, for data collection)
    min_win_probability: float = 0.0  # 0% = MCTS calculates but never blocks trades

    # Simulation settings
    simulation_timesteps: int = 12  # Simulate 12 candles ahead (3h @ 15m)
    use_prophet_for_sim: bool = True  # Use Prophet for price simulation

    # Performance
    parallel_sims: int = 4  # Parallel simulation threads


@dataclass
class RewardConfig:
    """Reward function configuration."""

    # P&L Reward
    pnl_multiplier: float = 1.0  # Base multiplier for P&L

    # Time penalties (encourage faster trades)
    time_decay_start_hours: float = 4.0  # Start penalizing after 4h
    time_decay_rate: float = 0.01  # Penalty per hour
    max_time_penalty: float = 0.3  # Max 30% penalty

    # Drawdown penalties
    drawdown_penalty_threshold: float = 0.02  # Penalize if DD > 2%
    drawdown_penalty_rate: float = 0.5  # Penalty multiplier

    # Win bonus (encourage winning trades)
    win_bonus: float = 0.1  # +10% for winning trades

    # Sharpe ratio bonus (encourage consistent returns)
    sharpe_bonus_threshold: float = 1.5  # Bonus if Sharpe > 1.5
    sharpe_bonus: float = 0.05

    # Risk-adjusted metrics
    use_sortino: bool = True  # Prefer Sortino over Sharpe

    # Holding cost (small penalty for holding)
    holding_cost_per_hour: float = 0.001  # 0.1% per hour


@dataclass
class TrainingConfig:
    """RL Training configuration."""

    # Algorithm
    algorithm: str = "PPO"  # PPO, A2C, or DQN

    # Training parameters
    total_episodes: int = 10000
    batch_size: int = 64
    gamma: float = 0.99  # Discount factor
    gae_lambda: float = 0.95  # GAE lambda

    # PPO specific
    ppo_epochs: int = 4
    ppo_clip: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5

    # Experience replay
    buffer_size: int = 100000
    min_buffer_size: int = 1000  # Start training after this many steps

    # Evaluation
    eval_episodes: int = 100
    eval_frequency: int = 500  # Evaluate every N episodes

    # Checkpointing
    checkpoint_frequency: int = 1000
    checkpoint_dir: str = "alpha/checkpoints"

    # Early stopping
    early_stop_patience: int = 50  # Stop if no improvement for N evals
    early_stop_min_delta: float = 0.01


@dataclass
class TradingConfig:
    """Live/Paper trading configuration."""

    # Mode
    paper_trading: bool = True  # True = paper, False = live

    # Position sizing
    base_position_usd: float = 25.0
    max_position_usd: float = 100.0
    max_leverage: int = 5

    # Risk management
    max_drawdown_pct: float = 10.0  # Stop trading if DD > 10%
    max_daily_loss_pct: float = 5.0  # Stop trading if daily loss > 5%
    max_open_positions: int = 3

    # Execution
    slippage_pct: float = 0.05  # Assume 0.05% slippage
    min_profit_to_close: float = 0.5  # Min profit % to consider closing
    min_hold_minutes: int = 5  # Minimum time to hold before closing (from analysis: 5-15 min best)

    # Loops
    slow_loop_interval: int = 60  # 1 minute (AI decision) - no API cost!
    fast_loop_interval: int = 5  # 5 seconds (monitoring)

    # Symbols - all 11 trading pairs
    symbols: List[str] = field(default_factory=lambda: [
        "BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "SUI", "ARB", "AVAX", "LINK", "ADA"
    ])


@dataclass
class AlphaConfig:
    """Master configuration for AlphaTrader."""

    # Sub-configurations
    network: NetworkConfig = field(default_factory=NetworkConfig)
    mcts: MCTSConfig = field(default_factory=MCTSConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)

    # API Keys (shared with botone)
    openrouter_api_key: Optional[str] = None
    hl_private_key: Optional[str] = None
    hl_account_address: Optional[str] = None
    hl_testnet: bool = True

    # Database
    database_url: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    tensorboard_dir: str = "alpha/runs"

    @classmethod
    def from_env(cls) -> "AlphaConfig":
        """Load configuration from environment variables."""

        config = cls()

        # API Keys
        config.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        config.hl_private_key = os.getenv("PRIVATE_KEY") or os.getenv("HL_PRIVATE_KEY")
        config.hl_account_address = os.getenv("WALLET_ADDRESS") or os.getenv("HL_ACCOUNT_ADDRESS")
        config.hl_testnet = _env_bool("TESTNET", True) or _env_bool("HL_TESTNET", True)

        # Database
        config.database_url = os.getenv("DATABASE_URL")

        # Network config
        config.network.policy_learning_rate = _env_float("ALPHA_POLICY_LR", 0.0003)
        config.network.value_learning_rate = _env_float("ALPHA_VALUE_LR", 0.0003)

        # MCTS config
        config.mcts.num_simulations = _env_int("ALPHA_MCTS_SIMS", 100)
        config.mcts.min_win_probability = _env_float("ALPHA_MIN_WIN_PROB", 0.0)  # 0 = no veto, just collect data

        # Reward config
        config.reward.pnl_multiplier = _env_float("ALPHA_PNL_MULT", 1.0)
        config.reward.time_decay_rate = _env_float("ALPHA_TIME_DECAY", 0.01)

        # Training config
        config.training.total_episodes = _env_int("ALPHA_EPISODES", 10000)
        config.training.batch_size = _env_int("ALPHA_BATCH_SIZE", 64)

        # Trading config
        config.trading.paper_trading = _env_bool("ALPHA_PAPER", True)
        config.trading.base_position_usd = _env_float("ALPHA_POSITION_USD", 25.0)
        config.trading.max_leverage = _env_int("ALPHA_MAX_LEVERAGE", 5)
        config.trading.min_hold_minutes = _env_int("ALPHA_MIN_HOLD_MINUTES", 5)

        # Symbols - hardcode all 11, only override if TRADING_SYMBOLS explicitly set
        # NOTE: Ignore SYMBOLS env var (may be set by old .env files in container)
        trading_symbols = os.getenv("TRADING_SYMBOLS", "")
        if trading_symbols:
            config.trading.symbols = [s.strip().upper() for s in trading_symbols.split(",") if s.strip()]
        else:
            # Default: all 11 symbols
            config.trading.symbols = ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "SUI", "ARB", "AVAX", "LINK", "ADA"]

        # Loop intervals
        config.trading.slow_loop_interval = _env_int("ALPHA_SLOW_INTERVAL", 60)
        config.trading.fast_loop_interval = _env_int("ALPHA_FAST_INTERVAL", 5)

        return config

    def validate(self) -> List[str]:
        """Validate configuration, return list of errors."""
        errors = []

        if not self.hl_private_key:
            errors.append("Missing PRIVATE_KEY / HL_PRIVATE_KEY")

        if not self.hl_account_address:
            errors.append("Missing WALLET_ADDRESS / HL_ACCOUNT_ADDRESS")

        if self.trading.max_leverage > 10:
            errors.append("max_leverage > 10 is dangerous")

        # Note: min_win_probability = 0 is valid for data collection phase
        # (MCTS calculates but never vetoes)

        return errors


# Global config instance
_config: Optional[AlphaConfig] = None


def get_config() -> AlphaConfig:
    """Get or create global config."""
    global _config
    if _config is None:
        _config = AlphaConfig.from_env()
    return _config
