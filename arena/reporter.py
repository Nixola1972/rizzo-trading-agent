"""
Arena Reporter

Generates reports and leaderboards for Arena simulation results.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .db import ArenaDB
from .models import Variant, SubVariant
from .metrics import (
    calculate_metrics,
    get_leaderboard,
    compare_variants,
    get_symbol_performance,
    get_ai_model_performance,
)


class ArenaReporter:
    """Generates reports for Arena simulation results."""

    def __init__(self, db: Optional[ArenaDB] = None):
        """Initialize reporter."""
        self.db = db or ArenaDB()

    def print_leaderboard(self, limit: int = 10, min_trades: int = 3) -> None:
        """Print formatted leaderboard to console."""
        leaderboard = get_leaderboard(self.db, limit=limit, min_trades=min_trades)

        print("\n" + "=" * 80)
        print("                           🏆 ARENA LEADERBOARD 🏆")
        print("=" * 80)

        if not leaderboard:
            print("  No sub-variants with enough trades yet.")
            print("=" * 80)
            return

        # Header
        print(f"{'Rank':<5} {'Sub-Variant':<25} {'Trades':<8} {'Win%':<8} {'P&L $':<12} {'P&L %':<10}")
        print("-" * 80)

        for entry in leaderboard:
            rank = entry["rank"]
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."

            pnl_color = "+" if entry["total_pnl_usd"] >= 0 else ""
            pnl_usd = f"{pnl_color}{entry['total_pnl_usd']:.2f}"
            pnl_pct = f"{pnl_color}{entry['total_pnl_pct']:.1f}%"

            print(
                f"{medal:<5} {entry['sub_variant_id'][:24]:<25} "
                f"{entry['total_trades']:<8} {entry['win_rate']:.1f}%{'':<4} "
                f"${pnl_usd:<11} {pnl_pct:<10}"
            )

        print("=" * 80)

    def print_variant_comparison(self, hours: int = 24) -> None:
        """Print variant comparison report."""
        comparison = compare_variants(self.db, hours=hours)

        print("\n" + "=" * 90)
        print(f"                    📊 VARIANT COMPARISON (Last {hours}h)")
        print("=" * 90)

        if not comparison["comparison"]:
            print("  No data available.")
            return

        # Header
        print(f"{'Variant':<20} {'Mode':<12} {'Trades':<8} {'Win%':<8} {'P&L $':<12} {'Sharpe':<8} {'MaxDD%':<8}")
        print("-" * 90)

        for v in comparison["comparison"]:
            status = "✓" if v["enabled"] else "✗"
            mode = v["operation_mode"][:10]
            pnl = f"${v['total_pnl_usd']:+.2f}"

            print(
                f"{status} {v['variant_name'][:18]:<18} {mode:<12} "
                f"{v['total_trades']:<8} {v['win_rate']:.1f}%{'':<4} "
                f"{pnl:<12} {v['sharpe_ratio']:.2f}{'':<5} {v['max_drawdown_pct']:.1f}%"
            )

        print("=" * 90)

    def print_symbol_performance(self, hours: int = 24) -> None:
        """Print performance by symbol."""
        performance = get_symbol_performance(self.db, hours=hours)

        print("\n" + "=" * 70)
        print(f"                    📈 SYMBOL PERFORMANCE (Last {hours}h)")
        print("=" * 70)

        if not performance:
            print("  No data available.")
            return

        print(f"{'Symbol':<10} {'Trades':<8} {'Win%':<8} {'P&L $':<12} {'Avg P&L%':<10} {'Best%':<10}")
        print("-" * 70)

        for symbol, metrics in sorted(performance.items()):
            pnl = f"${metrics['total_pnl_usd']:+.2f}"
            print(
                f"{symbol:<10} {metrics['total_trades']:<8} "
                f"{metrics['win_rate']:.1f}%{'':<4} {pnl:<12} "
                f"{metrics['avg_pnl_pct']:+.2f}%{'':<5} {metrics['max_profit_pct']:+.2f}%"
            )

        print("=" * 70)

    def print_ai_model_performance(self, hours: int = 24) -> None:
        """Print performance by AI model."""
        performance = get_ai_model_performance(self.db, hours=hours)

        print("\n" + "=" * 80)
        print(f"                    🤖 AI MODEL PERFORMANCE (Last {hours}h)")
        print("=" * 80)

        if not performance:
            print("  No data available.")
            return

        print(f"{'Model':<30} {'Trades':<8} {'Win%':<8} {'P&L $':<12} {'Sharpe':<8}")
        print("-" * 80)

        sorted_models = sorted(
            performance.items(),
            key=lambda x: x[1]["total_pnl_usd"],
            reverse=True
        )

        for model, metrics in sorted_models:
            model_short = model.split("/")[-1] if "/" in model else model
            pnl = f"${metrics['total_pnl_usd']:+.2f}"
            print(
                f"{model_short[:28]:<30} {metrics['total_trades']:<8} "
                f"{metrics['win_rate']:.1f}%{'':<4} {pnl:<12} {metrics['sharpe_ratio']:.2f}"
            )

        print("=" * 80)

    def print_open_positions(self) -> None:
        """Print current open positions."""
        positions = self.db.get_all_open_positions()

        print("\n" + "=" * 90)
        print("                         📍 OPEN POSITIONS")
        print("=" * 90)

        if not positions:
            print("  No open positions.")
            print("=" * 90)
            return

        print(f"{'Sub-Variant':<25} {'Symbol':<8} {'Dir':<6} {'Entry $':<12} {'P&L%':<10} {'P&L$':<10}")
        print("-" * 90)

        for p in positions:
            pnl_emoji = "🟢" if p.current_pnl_pct >= 0 else "🔴"
            print(
                f"{p.sub_variant_id[:24]:<25} {p.symbol:<8} {p.direction.value:<6} "
                f"${p.entry_price:,.2f}{'':<4} {pnl_emoji} {p.current_pnl_pct:+.2f}%{'':<4} "
                f"${p.current_pnl_usd:+.2f}"
            )

        print("=" * 90)

    def print_full_report(self, hours: int = 24) -> None:
        """Print complete Arena report."""
        print("\n")
        print("╔" + "═" * 88 + "╗")
        print("║" + " " * 30 + "🏟️  ARENA REPORT  🏟️" + " " * 30 + "║")
        print("║" + f"{'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^88}" + "║")
        print("╚" + "═" * 88 + "╝")

        self.print_leaderboard(limit=10)
        self.print_variant_comparison(hours=hours)
        self.print_symbol_performance(hours=hours)
        self.print_ai_model_performance(hours=hours)
        self.print_open_positions()

        # Summary stats
        trades = self.db.get_recent_trades(hours=hours)
        metrics = calculate_metrics(trades)

        print("\n" + "=" * 60)
        print(f"              📊 OVERALL STATS (Last {hours}h)")
        print("=" * 60)
        print(f"  Total Trades: {metrics['total_trades']}")
        print(f"  Win Rate: {metrics['win_rate']:.1f}%")
        print(f"  Total P&L: ${metrics['total_pnl_usd']:+.2f}")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.1f}%")
        print(f"  Avg Trade Duration: {metrics['avg_duration_minutes']:.0f} min")
        print("=" * 60)

    def generate_json_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate report as JSON-serializable dictionary."""
        trades = self.db.get_recent_trades(hours=hours)
        metrics = calculate_metrics(trades)

        positions = self.db.get_all_open_positions()
        leaderboard = get_leaderboard(self.db)
        comparison = compare_variants(self.db, hours=hours)
        symbol_perf = get_symbol_performance(self.db, hours=hours)
        ai_perf = get_ai_model_performance(self.db, hours=hours)

        return {
            "generated_at": datetime.now().isoformat(),
            "period_hours": hours,
            "overall_metrics": metrics,
            "open_positions": [p.to_dict() for p in positions],
            "leaderboard": leaderboard,
            "variant_comparison": comparison,
            "symbol_performance": symbol_perf,
            "ai_model_performance": ai_perf,
        }
