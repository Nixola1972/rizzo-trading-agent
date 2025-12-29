#!/usr/bin/env python3
"""
AlphaTrader 1H Trainer
======================

Wrapper for training the 1-hour model, completely independent from 15m model.

Usage:
    # Download 1h data from Binance
    python -m alpha.binance_data_loader --symbols BTC ETH SOL DOGE XRP BNB ADA AVAX LINK ARB SUI \
        --interval 1h --start-year 2017 --output-dir alpha/data/hourly

    # Train 1h model
    python -m alpha.trainer_1h --episodes 10000

    # Resume training
    python -m alpha.trainer_1h --resume alpha/checkpoints/best_model_1h.pt --episodes 5000
"""

import os
import sys
import argparse
import logging
import numpy as np
from datetime import datetime
from typing import List, Dict

# Set environment variable BEFORE importing config
os.environ["ALPHA_INTERVAL"] = "1h"

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [TRAINER-1H] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Train AlphaTrader 1H Model")
    parser.add_argument("--episodes", type=int, default=10000,
                       help="Number of training episodes")
    parser.add_argument("--resume", type=str, default=None,
                       help="Resume from checkpoint")
    parser.add_argument("--entropy-coef", type=float, default=0.05,
                       help="Entropy coefficient for exploration")
    parser.add_argument("--learning-rate", type=float, default=0.0003,
                       help="Learning rate")
    parser.add_argument("--data-dir", type=str, default="alpha/data/hourly",
                       help="Directory with 1h training data")
    parser.add_argument("--checkpoint-dir", type=str, default="alpha/checkpoints",
                       help="Directory for saving checkpoints")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AlphaTrader 1H Training")
    logger.info("=" * 60)
    logger.info(f"Data directory: {args.data_dir}")
    logger.info(f"Episodes: {args.episodes}")
    logger.info(f"Entropy coefficient: {args.entropy_coef}")
    logger.info(f"Checkpoint dir: {args.checkpoint_dir}")
    logger.info("=" * 60)

    # Check if data exists
    data_file = os.path.join(args.data_dir, "training_episodes_binance.pkl")
    if not os.path.exists(data_file):
        # Try alternative path
        data_file = os.path.join(args.data_dir, "training_episodes_1h.pkl")

    if not os.path.exists(data_file):
        logger.error(f"Training data not found at {args.data_dir}")
        logger.error("Please download 1h data first:")
        logger.error("  python -m alpha.binance_data_loader --interval 1h --output-dir alpha/data/hourly")
        sys.exit(1)

    logger.info(f"Found training data: {data_file}")

    # Import trainer components
    from alpha.trainer import PPOTrainer, load_hyperliquid_data
    from alpha.config import get_config_1h

    # Get 1h config
    config = get_config_1h()
    logger.info(f"Interval: {config.interval.interval}")
    logger.info(f"Hours per candle: {config.interval.hours_per_candle}")

    # Load data using the proper loader that converts to trainer format
    logger.info("Loading training episodes...")
    episodes = load_hyperliquid_data(data_file, max_episodes=args.episodes * 2)

    if not episodes:
        logger.error("No valid episodes loaded!")
        sys.exit(1)

    logger.info(f"Loaded {len(episodes)} episodes for training")

    # Create trainer with TrainingConfig (not AlphaConfig)
    trainer = PPOTrainer(config=config.training)

    # Resume if specified
    if args.resume and os.path.exists(args.resume):
        logger.info(f"Resuming from {args.resume}")
        trainer.load_checkpoint(args.resume)

    # Create checkpoint directory
    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # Training loop
    total_training_episodes = args.episodes
    log_interval = min(100, max(10, total_training_episodes // 50))
    best_avg_reward = float('-inf')

    logger.info(f"Starting training for {total_training_episodes} episodes...")
    logger.info(f"Log interval: every {log_interval} episodes")

    global_step = 0
    num_epochs = (total_training_episodes // len(episodes)) + 1

    for epoch in range(num_epochs):
        # Shuffle episodes each epoch
        np.random.shuffle(episodes)

        for episode_data in episodes:
            if global_step >= total_training_episodes:
                break

            global_step += 1

            # Train on this episode
            stats = trainer.train_episode(episode_data)

            # Log progress
            if global_step % log_interval == 0 or global_step == total_training_episodes:
                recent_stats = trainer.episode_stats[-log_interval:]
                avg_reward = np.mean([s.total_reward for s in recent_stats])
                avg_win_rate = np.mean([s.win_rate for s in recent_stats])
                avg_trades = np.mean([s.num_trades for s in recent_stats])
                avg_pnl = np.mean([s.avg_pnl for s in recent_stats])

                progress_pct = (global_step / total_training_episodes) * 100

                logger.info(
                    f"Step {global_step}/{total_training_episodes} ({progress_pct:.1f}%) | "
                    f"Reward: {avg_reward:.3f} | "
                    f"Win Rate: {avg_win_rate:.1%} | "
                    f"Trades: {avg_trades:.1f} | "
                    f"Avg P&L: {avg_pnl:.2f}%"
                )

                # Save status file
                status = {
                    "status": "training",
                    "model": "1h",
                    "step": global_step,
                    "total_steps": total_training_episodes,
                    "progress_pct": round(progress_pct, 1),
                    "avg_reward": round(avg_reward, 4),
                    "win_rate": round(avg_win_rate * 100, 1),
                    "avg_trades": round(avg_trades, 1),
                    "avg_pnl": round(avg_pnl, 2),
                    "best_reward": round(best_avg_reward, 4),
                    "last_update": datetime.utcnow().isoformat(),
                }

                import json
                status_path = os.path.join(args.checkpoint_dir, "training_status_1h.json")
                with open(status_path, "w") as f:
                    json.dump(status, f, indent=2)

                # Track best model
                if avg_reward > best_avg_reward:
                    best_avg_reward = avg_reward
                    best_path = os.path.join(args.checkpoint_dir, "best_model_1h.pt")
                    trainer.save_checkpoint(best_path)
                    logger.info(f"New best 1H model saved (reward: {avg_reward:.3f})")

            # Regular checkpoint every 500 steps
            if global_step % 500 == 0:
                checkpoint_path = os.path.join(args.checkpoint_dir, f"checkpoint_1h_{global_step}.pt")
                trainer.save_checkpoint(checkpoint_path)

        if global_step >= total_training_episodes:
            break

    # Save final model
    final_path = os.path.join(args.checkpoint_dir, "final_model_1h.pt")
    trainer.save_checkpoint(final_path)

    # Final summary
    if trainer.episode_stats:
        final_stats = trainer.episode_stats[-100:] if len(trainer.episode_stats) >= 100 else trainer.episode_stats
        final_reward = np.mean([s.total_reward for s in final_stats])
        final_win_rate = np.mean([s.win_rate for s in final_stats])
        final_pnl = np.mean([s.avg_pnl for s in final_stats])

        logger.info("")
        logger.info("=" * 60)
        logger.info("1H TRAINING COMPLETE!")
        logger.info("=" * 60)
        logger.info(f"Total episodes: {len(trainer.episode_stats)}")
        logger.info(f"Final Avg Reward: {final_reward:.3f}")
        logger.info(f"Final Win Rate: {final_win_rate:.1%}")
        logger.info(f"Final Avg P&L: {final_pnl:.2f}%")
        logger.info(f"Best model: {os.path.join(args.checkpoint_dir, 'best_model_1h.pt')}")
        logger.info(f"Final model: {final_path}")
        logger.info("=" * 60)

        # Update status
        import json
        status = {
            "status": "complete",
            "model": "1h",
            "total_episodes": len(trainer.episode_stats),
            "progress_pct": 100.0,
            "avg_reward": round(final_reward, 4),
            "win_rate": round(final_win_rate * 100, 1),
            "avg_pnl": round(final_pnl, 2),
            "best_reward": round(best_avg_reward, 4),
            "best_model": os.path.join(args.checkpoint_dir, "best_model_1h.pt"),
            "final_model": final_path,
            "completed_at": datetime.utcnow().isoformat(),
        }
        status_path = os.path.join(args.checkpoint_dir, "training_status_1h.json")
        with open(status_path, "w") as f:
            json.dump(status, f, indent=2)


if __name__ == "__main__":
    main()
