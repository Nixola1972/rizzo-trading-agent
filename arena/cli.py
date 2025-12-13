#!/usr/bin/env python3
"""
Arena CLI - Command Line Interface

Run Arena simulation from command line or integrate with main bot.
"""

import os
import sys
import argparse
import logging
import signal
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arena.db import ArenaDB
from arena.config_loader import load_variants, reload_variants_from_file, enable_variant
from arena.simulator import ArenaSimulator
from arena.reporter import ArenaReporter
from arena.metrics import get_leaderboard


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arena.cli")


def cmd_start(args):
    """Start Arena simulation."""
    print("🏟️  Starting Arena Simulation...")

    simulator = ArenaSimulator()

    # Handle signals for graceful shutdown
    def signal_handler(signum, frame):
        print("\n🛑 Shutting down Arena...")
        simulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start blocking (main thread)
    simulator.start(blocking=True)


def cmd_status(args):
    """Show Arena status."""
    db = ArenaDB()
    reporter = ArenaReporter(db)

    # Load variants
    variants = load_variants(db)

    print("\n🏟️  ARENA STATUS")
    print("=" * 60)
    print(f"Total Variants: {len(variants)}")
    print(f"Enabled Variants: {len([v for v in variants if v.enabled])}")

    print("\nVariants:")
    for v in variants:
        status = "✅" if v.enabled else "❌"
        mode = v.operation_mode.value
        models = len(v.ai_models)
        print(f"  {status} {v.id}: {v.name} ({mode}, {models} AI models)")

    # Open positions
    positions = db.get_all_open_positions()
    print(f"\nOpen Positions: {len(positions)}")

    if positions:
        reporter.print_open_positions()


def cmd_report(args):
    """Generate Arena report."""
    db = ArenaDB()
    reporter = ArenaReporter(db)

    hours = args.hours if hasattr(args, 'hours') else 24

    if args.format == "json":
        import json
        report = reporter.generate_json_report(hours=hours)
        print(json.dumps(report, indent=2, default=str))
    else:
        reporter.print_full_report(hours=hours)


def cmd_leaderboard(args):
    """Show leaderboard."""
    db = ArenaDB()
    reporter = ArenaReporter(db)

    limit = args.limit if hasattr(args, 'limit') else 10
    reporter.print_leaderboard(limit=limit)


def cmd_variants(args):
    """List or manage variants."""
    db = ArenaDB()

    if args.action == "list":
        variants = load_variants(db)
        print("\n📋 VARIANTS")
        print("=" * 70)
        for v in variants:
            status = "✅ ENABLED" if v.enabled else "❌ DISABLED"
            print(f"\n{v.id}: {v.name}")
            print(f"  Status: {status}")
            print(f"  Mode: {v.operation_mode.value}")
            print(f"  AI Models: {', '.join(v.ai_models)}")
            print(f"  Symbols: {', '.join(v.symbols)}")
            print(f"  Description: {v.description}")

    elif args.action == "enable":
        if not args.variant_id:
            print("Error: --variant-id required")
            return
        if enable_variant(args.variant_id, True, db):
            print(f"✅ Variant {args.variant_id} enabled")
        else:
            print(f"❌ Variant {args.variant_id} not found")

    elif args.action == "disable":
        if not args.variant_id:
            print("Error: --variant-id required")
            return
        if enable_variant(args.variant_id, False, db):
            print(f"❌ Variant {args.variant_id} disabled")
        else:
            print(f"❌ Variant {args.variant_id} not found")

    elif args.action == "reload":
        variants = reload_variants_from_file(db)
        print(f"🔄 Reloaded {len(variants)} variants from config file")


def cmd_reset(args):
    """Reset Arena data."""
    if not args.confirm:
        print("⚠️  This will DELETE all Arena data!")
        print("Use --confirm to proceed")
        return

    db = ArenaDB()
    db.reset_all_data()
    print("🗑️  All Arena data has been reset")


def cmd_init(args):
    """Initialize Arena (create database and default variants)."""
    print("🔧 Initializing Arena...")

    # Create data directory
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)

    # Initialize database (creates tables)
    db = ArenaDB()

    # Load variants (creates defaults if needed)
    variants = load_variants(db)

    print(f"✅ Arena initialized with {len(variants)} variants")
    print(f"📁 Database: {db.db_path}")

    # Show variants
    for v in variants:
        print(f"  - {v.id}: {v.name}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Arena - Trading Simulation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  arena init                    Initialize Arena
  arena start                   Start simulation
  arena status                  Show current status
  arena report                  Generate full report
  arena leaderboard             Show leaderboard
  arena variants list           List all variants
  arena variants enable --variant-id V1_BASELINE
  arena variants disable --variant-id V5_AI_FREE
  arena reset --confirm         Reset all data
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    parser_init = subparsers.add_parser("init", help="Initialize Arena")
    parser_init.set_defaults(func=cmd_init)

    # start
    parser_start = subparsers.add_parser("start", help="Start simulation")
    parser_start.set_defaults(func=cmd_start)

    # status
    parser_status = subparsers.add_parser("status", help="Show status")
    parser_status.set_defaults(func=cmd_status)

    # report
    parser_report = subparsers.add_parser("report", help="Generate report")
    parser_report.add_argument("--hours", type=int, default=24, help="Hours to include")
    parser_report.add_argument("--format", choices=["text", "json"], default="text")
    parser_report.set_defaults(func=cmd_report)

    # leaderboard
    parser_lb = subparsers.add_parser("leaderboard", help="Show leaderboard")
    parser_lb.add_argument("--limit", type=int, default=10, help="Number of entries")
    parser_lb.set_defaults(func=cmd_leaderboard)

    # variants
    parser_variants = subparsers.add_parser("variants", help="Manage variants")
    parser_variants.add_argument("action", choices=["list", "enable", "disable", "reload"])
    parser_variants.add_argument("--variant-id", help="Variant ID for enable/disable")
    parser_variants.set_defaults(func=cmd_variants)

    # reset
    parser_reset = subparsers.add_parser("reset", help="Reset all data")
    parser_reset.add_argument("--confirm", action="store_true", help="Confirm reset")
    parser_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
