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
    python -m alpha.trainer_1h --resume alpha/checkpoints/model_1h_best.pt --episodes 5000
"""

import os
import sys
import argparse
import logging

# Set environment variable BEFORE importing config
os.environ["ALPHA_INTERVAL"] = "1h"

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpha.config import get_config_1h, IntervalConfig

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

    # Get 1h config
    config = get_config_1h()

    logger.info("=" * 60)
    logger.info("AlphaTrader 1H Training")
    logger.info("=" * 60)
    logger.info(f"Interval: {config.interval.interval}")
    logger.info(f"Hours per candle: {config.interval.hours_per_candle}")
    logger.info(f"Data directory: {args.data_dir}")
    logger.info(f"Episodes: {args.episodes}")
    logger.info(f"Entropy coefficient: {args.entropy_coef}")
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

    # Import trainer and run
    # We need to modify the trainer to accept hours_per_candle parameter
    from alpha.trainer import AlphaTrainer, load_training_data

    # Load data
    logger.info("Loading training episodes...")
    episodes = load_training_data(data_file)
    logger.info(f"Loaded {len(episodes)} episodes")

    # Create trainer with 1h config
    trainer = AlphaTrainer(
        config=config,
        hours_per_candle=config.interval.hours_per_candle,  # 1.0 for 1h
        checkpoint_suffix="_1h"
    )

    # Resume if specified
    if args.resume and os.path.exists(args.resume):
        logger.info(f"Resuming from {args.resume}")
        trainer.load_checkpoint(args.resume)

    # Train
    logger.info("Starting training...")
    trainer.train(
        episodes=episodes,
        total_episodes=args.episodes,
        entropy_coef=args.entropy_coef,
        learning_rate=args.learning_rate,
        checkpoint_dir=args.checkpoint_dir
    )

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
