#!/usr/bin/env python3
"""
Arena Runner Script

Simple script to start Arena simulation.
Can be run standalone or imported.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if Arena is enabled
ARENA_ENABLED = os.environ.get("ARENA_ENABLED", "false").lower() == "true"

if not ARENA_ENABLED:
    print("⚠️  Arena is disabled. Set ARENA_ENABLED=true in .env to enable.")
    sys.exit(0)

# Configure logging
log_level = os.environ.get("ARENA_LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s [ARENA] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("arena")


def main():
    """Main entry point."""
    from arena.simulator import ArenaSimulator
    from arena.reporter import ArenaReporter
    import signal

    logger.info("🏟️  Arena Trading Simulation Starting...")

    # Initialize
    simulator = ArenaSimulator()

    # Show status
    status = simulator.get_status()
    logger.info(f"Loaded {status['variants_loaded']} variants ({status['variants_enabled']} enabled)")

    # Signal handlers
    def shutdown(signum, frame):
        logger.info("Shutting down Arena...")
        simulator.stop()

        # Print final report
        reporter = ArenaReporter(simulator.db)
        reporter.print_leaderboard(limit=5)

        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start simulation (blocking)
    logger.info("Starting simulation loop...")
    simulator.start(blocking=True)


if __name__ == "__main__":
    main()
