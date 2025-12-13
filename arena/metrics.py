"""
Arena Metrics Calculator

Calculates performance metrics for variants and sub-variants:
- Win rate, P&L, Sharpe ratio
- Drawdown analysis
- Comparison between variants
"""

import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .models import SimulatedTrade
from .db import ArenaDB


def calculate_metrics(
    trades: List[SimulatedTrade],
    risk_free_rate: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate comprehensive trading metrics from a list of trades.

    Args:
        trades: List of completed trades
        risk_free_rate: Annual risk-free rate for Sharpe calculation

    Returns:
        Dictionary with calculated metrics
    """
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl_usd": 0.0,
            "total_pnl_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "max_profit_pct": 0.0,
            "max_loss_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_duration_minutes": 0,
            "best_trade": None,
            "worst_trade": None,
        }

    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t.pnl_usd > 0)
    losing_trades = total_trades - winning_trades

    total_pnl_usd = sum(t.pnl_usd for t in trades)
    total_pnl_pct = sum(t.pnl_pct for t in trades)
    avg_pnl_pct = total_pnl_pct / total_trades

    # Max profit/loss
    pnl_values = [t.pnl_pct for t in trades]
    max_profit_pct = max(pnl_values) if pnl_values else 0.0
    max_loss_pct = min(pnl_values) if pnl_values else 0.0

    # Profit factor (gross profits / gross losses)
    gross_profit = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
    gross_loss = abs(sum(t.pnl_usd for t in trades if t.pnl_usd < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

    # Sharpe ratio
    sharpe_ratio = calculate_sharpe_ratio(trades, risk_free_rate)

    # Max drawdown
    max_drawdown_pct = calculate_max_drawdown(trades)

    # Average duration
    durations = [t.duration_minutes for t in trades if t.duration_minutes > 0]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Best and worst trades
    best_trade = max(trades, key=lambda t: t.pnl_pct)
    worst_trade = min(trades, key=lambda t: t.pnl_pct)

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0.0,
        "total_pnl_usd": total_pnl_usd,
        "total_pnl_pct": total_pnl_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "max_profit_pct": max_profit_pct,
        "max_loss_pct": max_loss_pct,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "avg_duration_minutes": avg_duration,
        "best_trade": {
            "symbol": best_trade.symbol,
            "direction": best_trade.direction.value,
            "pnl_pct": best_trade.pnl_pct,
            "pnl_usd": best_trade.pnl_usd,
        },
        "worst_trade": {
            "symbol": worst_trade.symbol,
            "direction": worst_trade.direction.value,
            "pnl_pct": worst_trade.pnl_pct,
            "pnl_usd": worst_trade.pnl_usd,
        },
    }


def calculate_sharpe_ratio(
    trades: List[SimulatedTrade],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 365,
) -> float:
    """
    Calculate Sharpe ratio from trades.

    Uses daily returns approximation based on trade P&L.
    """
    if len(trades) < 2:
        return 0.0

    returns = [t.pnl_pct for t in trades]
    avg_return = sum(returns) / len(returns)

    # Standard deviation
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    # Annualized Sharpe
    excess_return = avg_return - (risk_free_rate / periods_per_year)
    sharpe = (excess_return / std_dev) * math.sqrt(periods_per_year)

    return round(sharpe, 2)


def calculate_max_drawdown(trades: List[SimulatedTrade]) -> float:
    """
    Calculate maximum drawdown from trade sequence.

    Returns the largest peak-to-trough decline as a percentage.
    """
    if not trades:
        return 0.0

    # Sort by exit time
    sorted_trades = sorted(trades, key=lambda t: t.exit_time or datetime.min)

    # Calculate cumulative P&L
    cumulative_pnl = 0.0
    peak_pnl = 0.0
    max_drawdown = 0.0

    for trade in sorted_trades:
        cumulative_pnl += trade.pnl_pct

        if cumulative_pnl > peak_pnl:
            peak_pnl = cumulative_pnl

        drawdown = peak_pnl - cumulative_pnl
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return max_drawdown


def get_leaderboard(
    db: Optional[ArenaDB] = None,
    limit: int = 20,
    min_trades: int = 5,
) -> List[Dict[str, Any]]:
    """
    Get sub-variant leaderboard sorted by P&L.

    Args:
        db: Database instance
        limit: Maximum entries to return
        min_trades: Minimum trades required to be ranked

    Returns:
        List of leaderboard entries
    """
    if db is None:
        db = ArenaDB()

    leaderboard = db.get_leaderboard(limit=limit * 2)  # Get extra for filtering

    # Filter by minimum trades and re-rank
    filtered = [e for e in leaderboard if e["total_trades"] >= min_trades]

    for i, entry in enumerate(filtered[:limit]):
        entry["rank"] = i + 1

    return filtered[:limit]


def compare_variants(
    db: Optional[ArenaDB] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Compare variant performance over a time period.

    Returns comparison data for all variants.
    """
    if db is None:
        db = ArenaDB()

    variants = db.get_all_variants(enabled_only=False)
    comparison = []

    for variant in variants:
        trades = db.get_trades_for_variant(variant.id, limit=1000)

        # Filter by time if needed
        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            trades = [t for t in trades if t.exit_time and t.exit_time >= cutoff]

        metrics = calculate_metrics(trades)

        comparison.append({
            "variant_id": variant.id,
            "variant_name": variant.name,
            "enabled": variant.enabled,
            "operation_mode": variant.operation_mode.value,
            "sub_variants_count": len(variant.sub_variants),
            **metrics,
        })

    # Sort by P&L
    comparison.sort(key=lambda x: x["total_pnl_usd"], reverse=True)

    return {
        "period_hours": hours,
        "total_variants": len(variants),
        "comparison": comparison,
    }


def get_symbol_performance(
    db: Optional[ArenaDB] = None,
    hours: int = 24,
) -> Dict[str, Dict[str, Any]]:
    """
    Get performance breakdown by symbol.
    """
    if db is None:
        db = ArenaDB()

    trades = db.get_recent_trades(hours=hours, limit=10000)

    # Group by symbol
    by_symbol: Dict[str, List[SimulatedTrade]] = {}
    for trade in trades:
        if trade.symbol not in by_symbol:
            by_symbol[trade.symbol] = []
        by_symbol[trade.symbol].append(trade)

    # Calculate metrics per symbol
    performance = {}
    for symbol, symbol_trades in by_symbol.items():
        performance[symbol] = calculate_metrics(symbol_trades)

    return performance


def get_ai_model_performance(
    db: Optional[ArenaDB] = None,
    hours: int = 24,
) -> Dict[str, Dict[str, Any]]:
    """
    Get performance breakdown by AI model.
    """
    if db is None:
        db = ArenaDB()

    trades = db.get_recent_trades(hours=hours, limit=10000)

    # Group by AI model
    by_model: Dict[str, List[SimulatedTrade]] = {}
    for trade in trades:
        model = trade.ai_model or "unknown"
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(trade)

    # Calculate metrics per model
    performance = {}
    for model, model_trades in by_model.items():
        performance[model] = calculate_metrics(model_trades)

    return performance
