#!/usr/bin/env python3
"""
Arena Main - Run simulator and dashboard together

This is the main entry point for Arena in Docker.
Starts both the simulation loop and the web dashboard.
"""

import os
import sys
import signal
import logging
import threading
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
log_level = os.environ.get("ARENA_LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s [ARENA] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arena.main")


def main():
    """Main entry point."""

    # Check if enabled
    arena_enabled = os.environ.get("ARENA_ENABLED", "true").lower() == "true"
    if not arena_enabled:
        logger.warning("Arena is disabled. Set ARENA_ENABLED=true to enable.")
        sys.exit(0)

    logger.info("=" * 60)
    logger.info("🏟️  ARENA TRADING SIMULATION")
    logger.info("=" * 60)

    # Initialize components
    from arena.db import ArenaDB
    from arena.config_loader import load_variants
    from arena.simulator import ArenaSimulator
    from arena.dashboard import run_dashboard, init_dashboard

    # Initialize database
    db = ArenaDB()
    logger.info(f"Database: {db.db_path}")

    # Load variants
    variants = load_variants(db)
    enabled = [v for v in variants if v.enabled]
    logger.info(f"Loaded {len(variants)} variants ({len(enabled)} enabled)")

    for v in variants:
        status = "✅" if v.enabled else "❌"
        logger.info(f"  {status} {v.id}: {v.name} ({len(v.sub_variants)} sub-variants)")

    # Initialize simulator
    simulator = ArenaSimulator(db=db)

    # Initialize dashboard
    init_dashboard(db)

    # Signal handlers
    def shutdown(signum, frame):
        logger.info("Shutting down Arena...")
        simulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Check if dashboard enabled
    dashboard_enabled = os.environ.get("ARENA_DASHBOARD_ENABLED", "true").lower() == "true"
    dashboard_port = int(os.environ.get("ARENA_DASHBOARD_PORT", 5050))

    if dashboard_enabled:
        # Start simulator with separate fast/slow threads (non-blocking)
        simulator.start(blocking=False)
        logger.info("Simulator started in background")

        # Run dashboard in main thread (blocking)
        logger.info(f"Starting dashboard on port {dashboard_port}...")
        logger.info(f"📊 Open http://localhost:{dashboard_port} to view dashboard")

        from arena.dashboard import app
        app.run(host="0.0.0.0", port=dashboard_port, debug=False, threaded=True)
    else:
        # Run simulator only (blocking)
        logger.info("Dashboard disabled, running simulator only")
        simulator.start(blocking=True)


if __name__ == "__main__":
    main()
