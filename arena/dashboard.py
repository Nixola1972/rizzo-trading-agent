"""
Arena Dashboard - Web interface for monitoring simulations

Features:
- Real-time equity curve chart
- Leaderboard visualization
- Open positions monitor
- Variant performance comparison
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Flask, render_template_string, jsonify

from .db import ArenaDB
from .config_loader import load_variants
from .metrics import calculate_metrics, get_leaderboard
from .reporter import ArenaReporter


# Flask app
app = Flask(__name__)

# Database
db: Optional[ArenaDB] = None

# Starting capital for equity simulation
STARTING_CAPITAL = float(os.environ.get("ARENA_STARTING_CAPITAL", 100))


def init_dashboard(database: Optional[ArenaDB] = None):
    """Initialize dashboard with database connection."""
    global db
    db = database or ArenaDB()


# ==================== HTML Templates ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏟️ Arena Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #cccccc;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1a3e 0%, #0f0f23 100%);
            padding: 20px;
            border-bottom: 1px solid #333;
            text-align: center;
        }
        .header h1 { color: #00d4ff; font-size: 2em; }
        .header .subtitle { color: #888; margin-top: 5px; }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid #333;
        }
        .stat-card .value {
            font-size: 2em;
            font-weight: bold;
            color: #00d4ff;
        }
        .stat-card .value.positive { color: #00ff88; }
        .stat-card .value.negative { color: #ff4444; }
        .stat-card .label { color: #888; margin-top: 5px; }

        .chart-container {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 30px;
            border: 1px solid #333;
        }
        .chart-container h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.2em;
        }

        .section {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }
        .section h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.2em;
            border-bottom: 1px solid #333;
            padding-bottom: 10px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #333;
        }
        th { color: #00d4ff; font-weight: 600; }
        tr:hover { background: #252550; }

        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .badge-long { background: #00ff8833; color: #00ff88; }
        .badge-short { background: #ff444433; color: #ff4444; }
        .badge-enabled { background: #00ff8833; color: #00ff88; }
        .badge-disabled { background: #88888833; color: #888; }

        .pnl-positive { color: #00ff88; }
        .pnl-negative { color: #ff4444; }

        .medal { font-size: 1.5em; }

        .refresh-info {
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-top: 20px;
        }

        .two-columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) {
            .two-columns { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏟️ Arena Trading Simulation</h1>
        <div class="subtitle">Real-time performance monitoring • Starting Capital: ${{ starting_capital }}</div>
    </div>

    <div class="container">
        <!-- Stats Cards -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value {{ 'positive' if stats.total_pnl >= 0 else 'negative' }}">
                    ${{ "%.2f"|format(stats.current_equity) }}
                </div>
                <div class="label">Current Equity</div>
            </div>
            <div class="stat-card">
                <div class="value {{ 'positive' if stats.total_pnl >= 0 else 'negative' }}">
                    {{ "%.2f"|format(stats.total_pnl_pct) }}%
                </div>
                <div class="label">Total Return</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ stats.total_trades }}</div>
                <div class="label">Total Trades</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ "%.1f"|format(stats.win_rate) }}%</div>
                <div class="label">Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ stats.open_positions }}</div>
                <div class="label">Open Positions</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ stats.active_variants }}</div>
                <div class="label">Active Variants</div>
            </div>
        </div>

        <!-- Equity Chart -->
        <div class="chart-container">
            <h2>📈 Equity Curve (All Sub-Variants)</h2>
            <canvas id="equityChart" height="100"></canvas>
        </div>

        <div class="two-columns">
            <!-- Leaderboard -->
            <div class="section">
                <h2>🏆 Leaderboard</h2>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Sub-Variant</th>
                            <th>Trades</th>
                            <th>Win%</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for entry in leaderboard %}
                        <tr>
                            <td>
                                {% if entry.rank == 1 %}<span class="medal">🥇</span>
                                {% elif entry.rank == 2 %}<span class="medal">🥈</span>
                                {% elif entry.rank == 3 %}<span class="medal">🥉</span>
                                {% else %}{{ entry.rank }}{% endif %}
                            </td>
                            <td>{{ entry.sub_variant_id[:20] }}</td>
                            <td>{{ entry.total_trades }}</td>
                            <td>{{ "%.1f"|format(entry.win_rate) }}%</td>
                            <td class="{{ 'pnl-positive' if entry.total_pnl_usd >= 0 else 'pnl-negative' }}">
                                ${{ "%.2f"|format(entry.total_pnl_usd) }}
                            </td>
                        </tr>
                        {% endfor %}
                        {% if not leaderboard %}
                        <tr><td colspan="5" style="text-align: center; color: #666;">No trades yet</td></tr>
                        {% endif %}
                    </tbody>
                </table>
            </div>

            <!-- Open Positions -->
            <div class="section">
                <h2>📍 Open Positions</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Dir</th>
                            <th>Entry</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for pos in positions %}
                        <tr>
                            <td>{{ pos.symbol }}</td>
                            <td>
                                <span class="badge {{ 'badge-long' if pos.direction == 'LONG' else 'badge-short' }}">
                                    {{ pos.direction }}
                                </span>
                            </td>
                            <td>${{ "%.2f"|format(pos.entry_price) }}</td>
                            <td class="{{ 'pnl-positive' if pos.pnl_pct >= 0 else 'pnl-negative' }}">
                                {{ "%.2f"|format(pos.pnl_pct) }}%
                            </td>
                        </tr>
                        {% endfor %}
                        {% if not positions %}
                        <tr><td colspan="4" style="text-align: center; color: #666;">No open positions</td></tr>
                        {% endif %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Variants -->
        <div class="section">
            <h2>🎯 Variants Performance</h2>
            <table>
                <thead>
                    <tr>
                        <th>Variant</th>
                        <th>Mode</th>
                        <th>AI Models</th>
                        <th>Trades</th>
                        <th>Win%</th>
                        <th>P&L</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for v in variants %}
                    <tr>
                        <td>{{ v.name }}</td>
                        <td>{{ v.mode[:10] }}</td>
                        <td>{{ v.ai_count }}</td>
                        <td>{{ v.trades }}</td>
                        <td>{{ "%.1f"|format(v.win_rate) }}%</td>
                        <td class="{{ 'pnl-positive' if v.pnl >= 0 else 'pnl-negative' }}">
                            ${{ "%.2f"|format(v.pnl) }}
                        </td>
                        <td>
                            <span class="badge {{ 'badge-enabled' if v.enabled else 'badge-disabled' }}">
                                {{ 'ON' if v.enabled else 'OFF' }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="refresh-info">
            Auto-refresh every 30 seconds • Last update: <span id="lastUpdate">{{ now }}</span>
        </div>
    </div>

    <script>
        // Equity chart data from server
        const equityData = {{ equity_data | tojson }};

        // Create chart
        const ctx = document.getElementById('equityChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: equityData.labels,
                datasets: equityData.datasets
            },
            options: {
                responsive: true,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        labels: { color: '#888' }
                    }
                },
                scales: {
                    x: {
                        grid: { color: '#333' },
                        ticks: { color: '#888' }
                    },
                    y: {
                        grid: { color: '#333' },
                        ticks: {
                            color: '#888',
                            callback: function(value) { return '$' + value.toFixed(2); }
                        }
                    }
                }
            }
        });

        // Auto-refresh
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
"""


# ==================== Routes ====================

@app.route('/')
def dashboard():
    """Main dashboard page."""
    global db
    if db is None:
        init_dashboard()

    # Get stats
    stats = get_dashboard_stats()

    # Get leaderboard
    leaderboard = get_leaderboard(db, limit=10, min_trades=1)

    # Get positions
    positions = []
    for p in db.get_all_open_positions():
        positions.append({
            "symbol": p.symbol,
            "direction": p.direction.value,
            "entry_price": p.entry_price,
            "pnl_pct": p.current_pnl_pct,
        })

    # Get variants
    variants = []
    for v in load_variants(db):
        # Calculate variant stats
        trades = db.get_trades_for_variant(v.id, limit=1000)
        metrics = calculate_metrics(trades)

        variants.append({
            "name": v.name,
            "mode": v.operation_mode.value,
            "ai_count": len(v.ai_models),
            "trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "pnl": metrics["total_pnl_usd"],
            "enabled": v.enabled,
        })

    # Get equity data for chart
    equity_data = get_equity_chart_data()

    return render_template_string(
        DASHBOARD_HTML,
        stats=stats,
        leaderboard=leaderboard,
        positions=positions,
        variants=variants,
        equity_data=equity_data,
        starting_capital=STARTING_CAPITAL,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route('/api/stats')
def api_stats():
    """API endpoint for stats."""
    return jsonify(get_dashboard_stats())


@app.route('/api/equity')
def api_equity():
    """API endpoint for equity data."""
    return jsonify(get_equity_chart_data())


@app.route('/api/leaderboard')
def api_leaderboard():
    """API endpoint for leaderboard."""
    return jsonify(get_leaderboard(db, limit=20, min_trades=1))


# ==================== Data Functions ====================

def get_dashboard_stats() -> Dict[str, Any]:
    """Get dashboard statistics."""
    global db

    # Get all trades
    trades = db.get_recent_trades(hours=24*365, limit=10000)
    metrics = calculate_metrics(trades)

    # Calculate current equity
    total_pnl = metrics["total_pnl_usd"]
    current_equity = STARTING_CAPITAL + total_pnl
    total_pnl_pct = (total_pnl / STARTING_CAPITAL) * 100 if STARTING_CAPITAL > 0 else 0

    # Get open positions
    positions = db.get_all_open_positions()

    # Get active variants
    variants = load_variants(db)
    active = len([v for v in variants if v.enabled])

    return {
        "current_equity": current_equity,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "total_trades": metrics["total_trades"],
        "win_rate": metrics["win_rate"],
        "open_positions": len(positions),
        "active_variants": active,
    }


def get_equity_chart_data() -> Dict[str, Any]:
    """Get equity curve data for chart."""
    global db

    # Get all trades sorted by time
    trades = db.get_recent_trades(hours=24*365, limit=10000)
    trades.sort(key=lambda t: t.exit_time or datetime.min)

    # Group trades by sub-variant
    by_subvariant: Dict[str, List] = {}
    for trade in trades:
        sv_id = trade.sub_variant_id
        if sv_id not in by_subvariant:
            by_subvariant[sv_id] = []
        by_subvariant[sv_id].append(trade)

    # Build datasets
    datasets = []
    colors = [
        '#00d4ff', '#00ff88', '#ff4444', '#ffaa00',
        '#aa44ff', '#44ffaa', '#ff44aa', '#44aaff'
    ]

    # Combined equity curve
    combined_labels = []
    combined_equity = [STARTING_CAPITAL]
    cumulative = STARTING_CAPITAL

    for trade in trades:
        cumulative += trade.pnl_usd
        combined_equity.append(cumulative)
        if trade.exit_time:
            combined_labels.append(trade.exit_time.strftime("%m/%d %H:%M"))
        else:
            combined_labels.append("")

    # Add starting point
    combined_labels.insert(0, "Start")

    datasets.append({
        "label": "Combined Equity",
        "data": combined_equity,
        "borderColor": "#00d4ff",
        "backgroundColor": "rgba(0, 212, 255, 0.1)",
        "fill": True,
        "tension": 0.4,
    })

    # Individual sub-variant curves (top 5)
    sorted_svs = sorted(
        by_subvariant.items(),
        key=lambda x: sum(t.pnl_usd for t in x[1]),
        reverse=True
    )[:5]

    for i, (sv_id, sv_trades) in enumerate(sorted_svs):
        equity = [STARTING_CAPITAL]
        cumulative = STARTING_CAPITAL

        for trade in sv_trades:
            cumulative += trade.pnl_usd
            equity.append(cumulative)

        # Pad with last value to match length
        while len(equity) < len(combined_equity):
            equity.append(equity[-1] if equity else STARTING_CAPITAL)

        color = colors[i % len(colors)]
        datasets.append({
            "label": sv_id[:15],
            "data": equity[:len(combined_labels)],
            "borderColor": color,
            "backgroundColor": "transparent",
            "borderDash": [5, 5],
            "tension": 0.4,
        })

    return {
        "labels": combined_labels,
        "datasets": datasets,
    }


def run_dashboard(host: str = "0.0.0.0", port: int = 5050, debug: bool = False):
    """Run the dashboard server."""
    init_dashboard()
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_dashboard()
