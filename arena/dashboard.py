"""
Arena Dashboard - Interactive Web Interface

Features:
- 3 Tabs: AI Battle, Strategies, Live Positions
- Toggle controls for variants and AI models
- Real-time equity curves
- API call tracking
- Pause/Resume simulation
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Flask, render_template_string, jsonify, request

from .db import ArenaDB
from .config_loader import load_variants
from .metrics import calculate_metrics, get_leaderboard
from .models import TradeDirection


# Flask app
app = Flask(__name__)

# Database
db: Optional[ArenaDB] = None

# Simulation state (shared with simulator)
simulation_paused = False

# Starting capital for equity simulation
STARTING_CAPITAL = float(os.environ.get("ARENA_STARTING_CAPITAL", 100))


def init_dashboard(database: Optional[ArenaDB] = None):
    """Initialize dashboard with database connection."""
    global db
    db = database or ArenaDB()


# ==================== HTML Template ====================

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
            padding: 15px 20px;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { color: #00d4ff; font-size: 1.5em; }
        .header-stats {
            display: flex;
            gap: 30px;
        }
        .header-stat {
            text-align: center;
        }
        .header-stat .value {
            font-size: 1.4em;
            font-weight: bold;
        }
        .header-stat .value.positive { color: #00ff88; }
        .header-stat .value.negative { color: #ff4444; }
        .header-stat .label { color: #888; font-size: 0.8em; }

        .control-bar {
            background: #1a1a3e;
            padding: 10px 20px;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .sim-status {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #00ff88;
            animation: pulse 2s infinite;
        }
        .status-dot.paused { background: #ffaa00; animation: none; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }
        .btn-primary { background: #00d4ff; color: #000; }
        .btn-warning { background: #ffaa00; color: #000; }
        .btn-danger { background: #ff4444; color: #fff; }
        .btn:hover { opacity: 0.8; transform: translateY(-1px); }

        .tabs {
            display: flex;
            background: #1a1a3e;
            border-bottom: 1px solid #333;
        }
        .tab {
            padding: 15px 30px;
            cursor: pointer;
            color: #888;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        .tab:hover { color: #ccc; }
        .tab.active {
            color: #00d4ff;
            border-bottom-color: #00d4ff;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .chart-container {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }
        .chart-container h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.1em;
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
            font-size: 1.1em;
            border-bottom: 1px solid #333;
            padding-bottom: 10px;
        }

        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
        th { color: #00d4ff; font-weight: 600; }
        tr:hover { background: #252550; }

        .toggle-switch {
            position: relative;
            width: 50px;
            height: 26px;
            cursor: pointer;
        }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .toggle-slider {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: #333;
            border-radius: 26px;
            transition: 0.3s;
        }
        .toggle-slider:before {
            content: "";
            position: absolute;
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background: #888;
            border-radius: 50%;
            transition: 0.3s;
        }
        .toggle-switch input:checked + .toggle-slider { background: #00d4ff33; }
        .toggle-switch input:checked + .toggle-slider:before {
            transform: translateX(24px);
            background: #00d4ff;
        }

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
        .medal { font-size: 1.3em; }

        .model-card {
            background: #252550;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .model-info { flex: 1; }
        .model-name { font-weight: 600; color: #fff; }
        .model-stats { color: #888; font-size: 0.9em; margin-top: 5px; }
        .model-controls { display: flex; align-items: center; gap: 15px; }

        .two-columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 1000px) {
            .two-columns { grid-template-columns: 1fr; }
        }

        .refresh-info {
            text-align: center;
            color: #666;
            font-size: 0.85em;
            margin-top: 20px;
        }

        /* Analytics Tab Styles */
        .rec-card {
            background: #1e1e3f;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #333;
        }
        .rec-card.rec-high { border-left-color: #ff4444; }
        .rec-card.rec-medium { border-left-color: #ffaa00; }
        .rec-card.rec-low { border-left-color: #00ff88; }

        .rec-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .rec-badge {
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 600;
        }
        .rec-badge-high { background: #ff444433; color: #ff4444; }
        .rec-badge-medium { background: #ffaa0033; color: #ffaa00; }
        .rec-badge-low { background: #00ff8833; color: #00ff88; }
        .rec-type { color: #888; font-size: 0.85em; text-transform: uppercase; }

        .rec-card h3 { color: #fff; margin-bottom: 8px; font-size: 1.1em; }
        .rec-card p { color: #aaa; font-size: 0.95em; line-height: 1.4; }

        .rec-change {
            background: #0f0f23;
            padding: 10px;
            border-radius: 5px;
            margin: 12px 0;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .rec-old { color: #ff4444; text-decoration: line-through; }
        .rec-arrow { color: #666; }
        .rec-new { color: #00ff88; font-weight: 600; }

        .rec-footer {
            display: flex;
            justify-content: space-between;
            color: #666;
            font-size: 0.85em;
            margin-top: 10px;
        }
        .apply-btn {
            width: 100%;
            margin-top: 12px;
            padding: 10px;
            background: linear-gradient(135deg, #00aa55, #00cc66);
            border: none;
            border-radius: 6px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .apply-btn:hover {
            background: linear-gradient(135deg, #00cc66, #00ee77);
            transform: translateY(-1px);
        }
        .apply-btn:disabled {
            background: #444;
            cursor: not-allowed;
            transform: none;
        }
        .apply-btn.applied {
            background: #333;
            color: #888;
        }
        .apply-all-btn {
            padding: 15px 30px;
            background: linear-gradient(135deg, #ff6600, #ff8800);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            font-size: 1.1em;
            cursor: pointer;
            transition: all 0.2s;
        }
        .apply-all-btn:hover {
            background: linear-gradient(135deg, #ff8800, #ffaa00);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(255, 136, 0, 0.4);
        }

        .analytics-stats {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-box {
            background: #1e1e3f;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-label { color: #888; font-size: 0.85em; margin-bottom: 5px; }
        .stat-value { font-size: 1.3em; font-weight: 600; color: #fff; }
        .stat-value.positive { color: #00ff88; }
        .stat-value.negative { color: #ff4444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏟️ Arena Trading Simulation</h1>
        <div class="header-stats">
            <div class="header-stat">
                <div class="value {{ 'positive' if stats.total_pnl >= 0 else 'negative' }}">${{ "%.2f"|format(stats.current_equity) }}</div>
                <div class="label">Equity</div>
            </div>
            <div class="header-stat">
                <div class="value {{ 'positive' if stats.total_pnl >= 0 else 'negative' }}">{{ "%.2f"|format(stats.total_pnl_pct) }}%</div>
                <div class="label">Return</div>
            </div>
            <div class="header-stat">
                <div class="value">{{ stats.total_trades }}</div>
                <div class="label">Trades</div>
            </div>
            <div class="header-stat">
                <div class="value">{{ "%.1f"|format(stats.win_rate) }}%</div>
                <div class="label">Win Rate</div>
            </div>
        </div>
    </div>

    <div class="control-bar">
        <div class="sim-status">
            <div class="status-dot {{ 'paused' if paused else '' }}"></div>
            <span>{{ 'PAUSED' if paused else 'RUNNING' }}</span>
        </div>
        <div>
            <button class="btn {{ 'btn-primary' if paused else 'btn-warning' }}" onclick="toggleSimulation()">
                {{ '▶️ Resume' if paused else '⏸️ Pause' }}
            </button>
        </div>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="showTab('ai-battle')">🤖 AI Battle</div>
        <div class="tab" onclick="showTab('strategies')">📊 Strategies</div>
        <div class="tab" onclick="showTab('positions')">📍 Positions</div>
        <div class="tab" onclick="showTab('analytics')">🎯 Analytics</div>
    </div>

    <div class="container">
        <!-- AI Battle Tab -->
        <div id="ai-battle" class="tab-content active">
            <div class="chart-container">
                <h2>📈 AI Models Equity Curve (V2 Battle)</h2>
                <canvas id="aiBattleChart" height="80"></canvas>
            </div>

            <div class="two-columns">
                <div class="section">
                    <h2>🏆 AI Leaderboard</h2>
                    <table>
                        <thead>
                            <tr><th>#</th><th>AI Model</th><th>Trades</th><th>Win%</th><th>P&L</th></tr>
                        </thead>
                        <tbody>
                            {% for entry in ai_leaderboard %}
                            <tr>
                                <td>
                                    {% if entry.rank == 1 %}<span class="medal">🥇</span>
                                    {% elif entry.rank == 2 %}<span class="medal">🥈</span>
                                    {% elif entry.rank == 3 %}<span class="medal">🥉</span>
                                    {% else %}{{ entry.rank }}{% endif %}
                                </td>
                                <td>{{ entry.ai_model }}</td>
                                <td>{{ entry.total_trades }}</td>
                                <td>{{ "%.1f"|format(entry.win_rate) }}%</td>
                                <td class="{{ 'pnl-positive' if entry.total_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(entry.total_pnl_usd) }}
                                </td>
                            </tr>
                            {% endfor %}
                            {% if not ai_leaderboard %}
                            <tr><td colspan="5" style="text-align: center; color: #666;">No trades yet</td></tr>
                            {% endif %}
                        </tbody>
                    </table>
                </div>

                <div class="section">
                    <h2>⚙️ AI Model Controls</h2>
                    {% for model in ai_models %}
                    <div class="model-card">
                        <div class="model-info">
                            <div class="model-name">{{ model.ai_model_name }}</div>
                            <div class="model-stats">
                                API Calls: {{ model.api_calls }} | Errors: {{ model.api_errors }}
                            </div>
                        </div>
                        <div class="model-controls">
                            <label class="toggle-switch">
                                <input type="checkbox" {{ 'checked' if model.enabled else '' }}
                                       onchange="toggleModel('{{ model.id }}', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        <!-- Strategies Tab -->
        <div id="strategies" class="tab-content">
            <div class="chart-container">
                <h2>📈 Strategies Comparison</h2>
                <canvas id="strategiesChart" height="80"></canvas>
            </div>

            <div class="section">
                <h2>🎯 Strategy Performance</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>Mode</th>
                            <th>AI Models</th>
                            <th>Trades</th>
                            <th>Win%</th>
                            <th>P&L</th>
                            <th>Enabled</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for v in variants %}
                        <tr>
                            <td>{{ v.name }}</td>
                            <td>{{ v.mode }}</td>
                            <td>{{ v.ai_count }}</td>
                            <td>{{ v.trades }}</td>
                            <td>{{ "%.1f"|format(v.win_rate) }}%</td>
                            <td class="{{ 'pnl-positive' if v.pnl >= 0 else 'pnl-negative' }}">
                                ${{ "%.2f"|format(v.pnl) }}
                            </td>
                            <td>
                                <label class="toggle-switch">
                                    <input type="checkbox" {{ 'checked' if v.enabled else '' }}
                                           onchange="toggleVariant('{{ v.id }}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Positions Tab -->
        <div id="positions" class="tab-content">
            <div class="section">
                <h2>📍 Open Positions ({{ positions|length }})</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>Symbol</th>
                            <th>AI Model</th>
                            <th>Direction</th>
                            <th>Leva</th>
                            <th>Entry</th>
                            <th>Current</th>
                            <th>P&L %</th>
                            <th>P&L $</th>
                            <th>Duration</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for pos in positions %}
                        <tr>
                            <td><small>{{ pos.variant }}</small></td>
                            <td><strong>{{ pos.symbol }}</strong></td>
                            <td>{{ pos.ai_model }}</td>
                            <td>
                                <span class="badge {{ 'badge-long' if pos.direction == 'LONG' else 'badge-short' }}">
                                    {{ pos.direction }}
                                </span>
                            </td>
                            <td>{{ pos.leverage }}x</td>
                            <td>${{ "%.2f"|format(pos.entry_price) }}</td>
                            <td>${{ "%.2f"|format(pos.current_price) }}</td>
                            <td class="{{ 'pnl-positive' if pos.pnl_pct >= 0 else 'pnl-negative' }}">
                                {{ "%.2f"|format(pos.pnl_pct) }}%
                            </td>
                            <td class="{{ 'pnl-positive' if pos.pnl_usd >= 0 else 'pnl-negative' }}">
                                ${{ "%.2f"|format(pos.pnl_usd) }}
                            </td>
                            <td>{{ pos.duration }}</td>
                            <td>
                                <button class="btn btn-danger" onclick="closePosition('{{ pos.id }}')">Close</button>
                            </td>
                        </tr>
                        {% endfor %}
                        {% if not positions %}
                        <tr><td colspan="11" style="text-align: center; color: #666;">No open positions</td></tr>
                        {% endif %}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h2>📜 Recent Trades</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Symbol</th>
                            <th>AI Model</th>
                            <th>Direction</th>
                            <th>Exit Reason</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for trade in recent_trades %}
                        <tr>
                            <td>{{ trade.exit_time }}</td>
                            <td>{{ trade.symbol }}</td>
                            <td>{{ trade.ai_model }}</td>
                            <td>
                                <span class="badge {{ 'badge-long' if trade.direction == 'LONG' else 'badge-short' }}">
                                    {{ trade.direction }}
                                </span>
                            </td>
                            <td>{{ trade.exit_reason }}</td>
                            <td class="{{ 'pnl-positive' if trade.pnl_usd >= 0 else 'pnl-negative' }}">
                                ${{ "%.2f"|format(trade.pnl_usd) }}
                            </td>
                        </tr>
                        {% endfor %}
                        {% if not recent_trades %}
                        <tr><td colspan="6" style="text-align: center; color: #666;">No recent trades</td></tr>
                        {% endif %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Analytics Tab -->
        <div id="analytics" class="tab-content">
            <div class="two-columns">
                <div class="section">
                    <h2>🎯 Recommendations for Production</h2>
                    <p style="color: #888; margin-bottom: 15px;">
                        These recommendations are based on {{ analytics.total_trades or 0 }} trades
                        analyzed in the last 24 hours.
                    </p>
                    {% if analytics.recommendations %}
                    {% for rec in analytics.recommendations %}
                    <div class="rec-card rec-{{ rec.priority }}" id="rec-{{ loop.index0 }}">
                        <div class="rec-header">
                            <span class="rec-badge rec-badge-{{ rec.priority }}">
                                {% if rec.priority == 'high' %}🔴 HIGH
                                {% elif rec.priority == 'medium' %}🟡 MEDIUM
                                {% else %}🟢 LOW{% endif %}
                            </span>
                            <span class="rec-type">{{ rec.type }}</span>
                        </div>
                        <h3>{{ rec.title }}</h3>
                        <p>{{ rec.description }}</p>
                        <div class="rec-change">
                            <span class="rec-old">{{ rec.current_value }}</span>
                            <span class="rec-arrow">→</span>
                            <span class="rec-new">{{ rec.recommended_value }}</span>
                        </div>
                        <div class="rec-footer">
                            <span>Confidence: {{ "%.0f"|format(rec.confidence * 100) }}%</span>
                            <span>{{ rec.expected_improvement }}</span>
                        </div>
                        <button class="apply-btn" onclick="applyRecommendation({{ loop.index0 }})">
                            ✅ Applica
                        </button>
                    </div>
                    {% endfor %}
                    {% if analytics.recommendations %}
                    <div style="margin-top: 20px; text-align: center;">
                        <button class="apply-all-btn" onclick="applyAllRecommendations()">
                            🚀 Applica Tutte le HIGH Priority
                        </button>
                    </div>
                    {% endif %}
                    {% else %}
                    <div style="text-align: center; color: #666; padding: 40px;">
                        <p>📊 Waiting for enough data...</p>
                        <p style="font-size: 0.9em;">Recommendations will appear after at least 10 trades.</p>
                    </div>
                    {% endif %}
                </div>

                <div class="section">
                    <h2>📊 Performance Summary</h2>
                    <div class="analytics-stats">
                        <div class="stat-box">
                            <div class="stat-label">Total P&L (24h)</div>
                            <div class="stat-value {{ 'positive' if (analytics.total_pnl or 0) >= 0 else 'negative' }}">
                                ${{ "%.2f"|format(analytics.total_pnl or 0) }}
                            </div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Avg Win Rate</div>
                            <div class="stat-value">{{ "%.1f"|format((analytics.avg_win_rate or 0) * 100) }}%</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Best AI Model</div>
                            <div class="stat-value">{{ analytics.best_ai or 'N/A' }}</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Best Strategy</div>
                            <div class="stat-value">{{ analytics.best_variant or 'N/A' }}</div>
                        </div>
                    </div>

                    <h2 style="margin-top: 30px;">🏆 AI Model Rankings</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>AI Model</th>
                                <th>Trades</th>
                                <th>Win%</th>
                                <th>Profit Factor</th>
                                <th>P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for ai in analytics.ai_rankings %}
                            <tr>
                                <td>{{ loop.index }}</td>
                                <td>{{ ai.model_name }}</td>
                                <td>{{ ai.total_trades }}</td>
                                <td>{{ "%.1f"|format(ai.win_rate * 100) }}%</td>
                                <td>{{ "%.2f"|format(ai.profit_factor) if ai.profit_factor < 100 else '∞' }}</td>
                                <td class="{{ 'pnl-positive' if ai.total_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(ai.total_pnl_usd) }}
                                </td>
                            </tr>
                            {% endfor %}
                            {% if not analytics.ai_rankings %}
                            <tr><td colspan="6" style="text-align: center; color: #666;">No data yet</td></tr>
                            {% endif %}
                        </tbody>
                    </table>

                    <div style="margin-top: 20px; text-align: center; color: #666; font-size: 0.9em;">
                        Last analysis: {{ analytics.last_update or 'Never' }}
                    </div>
                </div>
            </div>
        </div>

        <div class="refresh-info">
            Auto-refresh every 30 seconds • Last update: {{ now }}
        </div>
    </div>

    <script>
        // Tab switching
        function showTab(tabId) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector(`[onclick="showTab('${tabId}')"]`).classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }

        // Toggle functions
        function toggleSimulation() {
            fetch('/api/simulation/toggle', { method: 'POST' })
                .then(r => r.json())
                .then(d => location.reload());
        }

        function toggleVariant(variantId, enabled) {
            fetch(`/api/variant/${variantId}/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            }).then(r => r.json());
        }

        function toggleModel(subVariantId, enabled) {
            fetch(`/api/model/${subVariantId}/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            }).then(r => r.json());
        }

        function closePosition(positionId) {
            if (confirm('Close this position?')) {
                fetch(`/api/position/${positionId}/close`, { method: 'POST' })
                    .then(r => r.json())
                    .then(d => location.reload());
            }
        }

        function applyRecommendation(index) {
            const btn = document.querySelector(`#rec-${index} .apply-btn`);
            btn.disabled = true;
            btn.textContent = '⏳ Applicando...';

            fetch(`/api/analytics/apply/${index}`, { method: 'POST' })
                .then(r => r.json())
                .then(d => {
                    if (d.success) {
                        btn.textContent = '✓ Applicato!';
                        btn.classList.add('applied');
                        alert(`✅ ${d.message}\n\nModifiche:\n${d.changes.join('\n')}`);
                    } else {
                        btn.textContent = '❌ Errore';
                        btn.disabled = false;
                        alert(`Errore: ${d.message || d.error}`);
                    }
                })
                .catch(e => {
                    btn.textContent = '❌ Errore';
                    btn.disabled = false;
                    alert('Errore di connessione');
                });
        }

        function applyAllRecommendations() {
            if (!confirm('Applicare TUTTE le raccomandazioni HIGH priority?')) return;

            const btn = document.querySelector('.apply-all-btn');
            btn.disabled = true;
            btn.textContent = '⏳ Applicando...';

            fetch('/api/analytics/apply-all', { method: 'POST' })
                .then(r => r.json())
                .then(d => {
                    if (d.success) {
                        alert(`✅ Applicate ${d.applied}/${d.total} raccomandazioni!\n\n` +
                              d.results.map(r => `${r.success ? '✓' : '✗'} ${r.message}`).join('\n'));
                        location.reload();
                    } else {
                        btn.textContent = '❌ Errore';
                        btn.disabled = false;
                        alert(`Errore: ${d.error}`);
                    }
                })
                .catch(e => {
                    btn.textContent = '❌ Errore';
                    btn.disabled = false;
                    alert('Errore di connessione');
                });
        }

        // Charts
        const aiData = {{ ai_chart_data | tojson }};
        const stratData = {{ strategy_chart_data | tojson }};

        const chartOptions = {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: '#888' } } },
            scales: {
                x: { grid: { color: '#333' }, ticks: { color: '#888' } },
                y: { grid: { color: '#333' }, ticks: { color: '#888', callback: v => '$' + v.toFixed(2) } }
            }
        };

        new Chart(document.getElementById('aiBattleChart').getContext('2d'), {
            type: 'line',
            data: { labels: aiData.labels, datasets: aiData.datasets },
            options: chartOptions
        });

        new Chart(document.getElementById('strategiesChart').getContext('2d'), {
            type: 'line',
            data: { labels: stratData.labels, datasets: stratData.datasets },
            options: chartOptions
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
    global db, simulation_paused
    if db is None:
        init_dashboard()

    stats = get_dashboard_stats()
    variants = get_variants_data()
    ai_models = get_ai_models_data()
    ai_leaderboard = get_ai_leaderboard()
    positions = get_positions_data()
    recent_trades = get_recent_trades_data()
    ai_chart_data = get_ai_chart_data()
    strategy_chart_data = get_strategy_chart_data()
    analytics = get_analytics_data()

    return render_template_string(
        DASHBOARD_HTML,
        stats=stats,
        variants=variants,
        ai_models=ai_models,
        ai_leaderboard=ai_leaderboard,
        positions=positions,
        recent_trades=recent_trades,
        ai_chart_data=ai_chart_data,
        strategy_chart_data=strategy_chart_data,
        analytics=analytics,
        paused=simulation_paused,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route('/api/simulation/toggle', methods=['POST'])
def api_toggle_simulation():
    """Toggle simulation pause state."""
    global simulation_paused
    simulation_paused = not simulation_paused
    return jsonify({"paused": simulation_paused})


@app.route('/api/variant/<variant_id>/toggle', methods=['POST'])
def api_toggle_variant(variant_id):
    """Toggle variant enabled status."""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    success = db.toggle_variant(variant_id, enabled)
    return jsonify({"success": success, "enabled": enabled})


@app.route('/api/model/<sub_variant_id>/toggle', methods=['POST'])
def api_toggle_model(sub_variant_id):
    """Toggle AI model enabled status."""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    success = db.toggle_sub_variant(sub_variant_id, enabled)
    return jsonify({"success": success, "enabled": enabled})


@app.route('/api/position/<position_id>/close', methods=['POST'])
def api_close_position(position_id):
    """Manually close a position."""
    from .models import TradeStatus, SimulatedTrade

    position = db.get_position(position_id)
    if not position:
        return jsonify({"success": False, "error": "Position not found"})

    # Get variant info
    sub_variant = db.get_sub_variant(position.sub_variant_id)
    if not sub_variant:
        return jsonify({"success": False, "error": "Sub-variant not found"})

    # Create trade record
    trade = SimulatedTrade.from_position(position, sub_variant.variant_id)
    trade.close(position.current_price, TradeStatus.CLOSED_MANUAL)
    trade.ai_model = sub_variant.ai_model

    # Save trade and update stats
    db.save_trade(trade)
    db.update_sub_variant_stats(position.sub_variant_id, trade)
    db.delete_position(position_id)

    return jsonify({"success": True, "pnl_usd": trade.pnl_usd})


@app.route('/api/stats')
def api_stats():
    """API endpoint for stats."""
    return jsonify(get_dashboard_stats())


@app.route('/api/leaderboard')
def api_leaderboard():
    """API endpoint for leaderboard."""
    return jsonify(get_ai_leaderboard())


@app.route('/api/costs')
def api_costs():
    """API endpoint for API call costs."""
    return jsonify(db.get_api_stats())


@app.route('/api/analytics')
def api_analytics():
    """API endpoint for analytics data."""
    return jsonify(get_analytics_data())


@app.route('/api/analytics/run', methods=['POST'])
def api_run_analytics():
    """Force run analytics and return results."""
    try:
        from .analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        report = analytics.run_analysis(force=True)

        if report:
            return jsonify({
                "success": True,
                "report_id": report.report_id,
                "recommendations_count": len(report.recommendations),
            })
        return jsonify({"success": False, "error": "Not enough data"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/analytics/apply/<int:index>', methods=['POST'])
def api_apply_recommendation(index: int):
    """Apply a specific recommendation by index."""
    try:
        from .analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)

        # Get latest report
        report = analytics.get_latest_report()
        if not report:
            # Try to run analysis first
            report = analytics.run_analysis(force=True)

        if not report or not report.recommendations:
            return jsonify({"success": False, "error": "Nessuna raccomandazione disponibile"})

        if index < 0 or index >= len(report.recommendations):
            return jsonify({"success": False, "error": f"Indice {index} non valido. Range: 0-{len(report.recommendations)-1}"})

        recommendation = report.recommendations[index]
        result = analytics.apply_recommendation(recommendation)

        return jsonify({
            "success": result["success"],
            "recommendation": recommendation.title,
            "message": result["message"],
            "changes": result["changes"],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/analytics/apply-all', methods=['POST'])
def api_apply_all_recommendations():
    """Apply all HIGH priority recommendations automatically."""
    try:
        from .analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)

        # Ensure we have a recent report
        report = analytics.get_latest_report()
        if not report:
            report = analytics.run_analysis(force=True)

        if not report:
            return jsonify({"success": False, "error": "Impossibile generare report analytics"})

        results = analytics.apply_all_high_priority()

        applied_count = sum(1 for r in results if r.get("success"))
        total = len(results)

        return jsonify({
            "success": applied_count > 0,
            "applied": applied_count,
            "total": total,
            "results": results,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/analytics/recommendations')
def api_get_recommendations():
    """Get all current recommendations with details."""
    try:
        from .analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)

        report = analytics.get_latest_report()
        if not report:
            report = analytics.run_analysis(force=True)

        if not report:
            return jsonify({"success": False, "recommendations": []})

        recs = []
        for i, rec in enumerate(report.recommendations):
            recs.append({
                "index": i,
                "type": rec.type.value,
                "priority": rec.priority.value,
                "title": rec.title,
                "description": rec.description,
                "current_value": str(rec.current_value),
                "recommended_value": str(rec.recommended_value),
                "expected_improvement": rec.expected_improvement,
                "confidence": rec.confidence,
                "evidence": rec.evidence,
            })

        return jsonify({
            "success": True,
            "report_id": report.report_id,
            "generated_at": report.generated_at.isoformat(),
            "recommendations": recs,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "recommendations": []})


# ==================== Data Functions ====================

def get_dashboard_stats() -> Dict[str, Any]:
    """Get dashboard statistics."""
    global db

    trades = db.get_recent_trades(hours=24*365, limit=10000)
    metrics = calculate_metrics(trades)

    total_pnl = metrics["total_pnl_usd"]
    current_equity = STARTING_CAPITAL + total_pnl
    total_pnl_pct = (total_pnl / STARTING_CAPITAL) * 100 if STARTING_CAPITAL > 0 else 0

    positions = db.get_all_open_positions()
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


def get_variants_data() -> List[Dict[str, Any]]:
    """Get variants with performance data."""
    variants = []
    for v in load_variants(db):
        trades = db.get_trades_for_variant(v.id, limit=1000)
        metrics = calculate_metrics(trades)

        mode_short = "SCORE" if v.operation_mode.value == "SCORE_TRIGGERED" else "AI_FREE"

        variants.append({
            "id": v.id,
            "name": v.name,
            "mode": mode_short,
            "ai_count": len(v.ai_models),
            "trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "pnl": metrics["total_pnl_usd"],
            "enabled": v.enabled,
        })
    return variants


def get_ai_models_data() -> List[Dict[str, Any]]:
    """Get AI models from V2_MULTI_AI battle."""
    models = []
    for v in load_variants(db):
        if v.id == "V2_MULTI_AI":
            for sv in v.sub_variants:
                sv_db = db.get_sub_variant(sv.id)
                if sv_db:
                    models.append({
                        "id": sv_db.id,
                        "ai_model": sv_db.ai_model,
                        "ai_model_name": sv_db.ai_model_name,
                        "enabled": sv_db.enabled,
                        "api_calls": sv_db.api_calls,
                        "api_errors": sv_db.api_errors,
                    })
    return models


def get_ai_leaderboard() -> List[Dict[str, Any]]:
    """Get AI model leaderboard for V2 battle."""
    leaderboard = []
    rank = 1

    for v in load_variants(db):
        if v.id == "V2_MULTI_AI":
            sv_data = []
            for sv in v.sub_variants:
                trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                metrics = calculate_metrics(trades)
                sv_data.append({
                    "ai_model": sv.ai_model_name,
                    "total_trades": metrics["total_trades"],
                    "win_rate": metrics["win_rate"],
                    "total_pnl_usd": metrics["total_pnl_usd"],
                })

            # Sort by P&L
            sv_data.sort(key=lambda x: x["total_pnl_usd"], reverse=True)

            for entry in sv_data:
                entry["rank"] = rank
                leaderboard.append(entry)
                rank += 1

    return leaderboard


def get_positions_data() -> List[Dict[str, Any]]:
    """Get open positions with details."""
    positions = []
    for p in db.get_all_open_positions():
        sv = db.get_sub_variant(p.sub_variant_id)
        ai_model = sv.ai_model_name if sv else "Unknown"

        # Get variant name from sub_variant_id (format: VARIANT_ID_ai-model)
        variant_id = sv.variant_id if sv else p.sub_variant_id.split("_")[0]
        variant = db.get_variant(variant_id)
        variant_name = variant.name if variant else variant_id

        duration_mins = int((datetime.now() - p.entry_time).total_seconds() / 60)
        if duration_mins < 60:
            duration = f"{duration_mins}m"
        else:
            duration = f"{duration_mins // 60}h {duration_mins % 60}m"

        positions.append({
            "id": p.id,
            "symbol": p.symbol,
            "variant": variant_name,
            "ai_model": ai_model,
            "direction": p.direction.value,
            "leverage": p.leverage,
            "entry_price": p.entry_price,
            "current_price": p.current_price,
            "pnl_pct": p.current_pnl_pct,
            "pnl_usd": p.current_pnl_usd,
            "duration": duration,
        })
    return positions


def get_recent_trades_data() -> List[Dict[str, Any]]:
    """Get recent closed trades."""
    trades = db.get_recent_trades(hours=48, limit=20)
    result = []

    for t in trades:
        result.append({
            "exit_time": t.exit_time.strftime("%m/%d %H:%M") if t.exit_time else "",
            "symbol": t.symbol,
            "ai_model": t.ai_model or "Unknown",
            "direction": t.direction.value,
            "exit_reason": t.exit_reason.value if t.exit_reason else "",
            "pnl_usd": t.pnl_usd,
        })
    return result


def get_analytics_data() -> Dict[str, Any]:
    """Get analytics data for the analytics tab."""
    try:
        from .analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)

        # Try to get or generate report
        report = analytics.run_analysis(force=False)

        if report:
            return {
                "total_trades": report.total_trades_analyzed,
                "total_pnl": report.total_pnl_usd,
                "avg_win_rate": report.avg_win_rate,
                "best_ai": report.best_ai_model.split("/")[-1] if report.best_ai_model else None,
                "best_variant": report.best_performing_variant,
                "ai_rankings": [
                    {
                        "model_name": r.model_name,
                        "total_trades": r.total_trades,
                        "win_rate": r.win_rate,
                        "profit_factor": r.profit_factor,
                        "total_pnl_usd": r.total_pnl_usd,
                    }
                    for r in report.ai_rankings
                ],
                "recommendations": [
                    {
                        "type": r.type.value,
                        "priority": r.priority.value,
                        "title": r.title,
                        "description": r.description,
                        "current_value": str(r.current_value),
                        "recommended_value": str(r.recommended_value),
                        "expected_improvement": r.expected_improvement,
                        "confidence": r.confidence,
                    }
                    for r in report.recommendations
                ],
                "last_update": report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
    except Exception as e:
        import logging
        logging.getLogger("arena.dashboard").warning(f"Analytics error: {e}")

    # Return empty data if no report
    return {
        "total_trades": 0,
        "total_pnl": 0.0,
        "avg_win_rate": 0.0,
        "best_ai": None,
        "best_variant": None,
        "ai_rankings": [],
        "recommendations": [],
        "last_update": None,
    }


def get_ai_chart_data() -> Dict[str, Any]:
    """Get chart data for AI battle using equity snapshots (5-min intervals)."""
    colors = ['#00d4ff', '#00ff88', '#ff4444', '#ffaa00', '#aa44ff', '#44ffaa']
    datasets = []
    labels = []

    # Get all snapshots for the last 24 hours
    all_snapshots = db.get_all_equity_snapshots(hours=24)

    for v in load_variants(db):
        if v.id == "V2_MULTI_AI":
            for i, sv in enumerate(v.sub_variants):
                snapshots = all_snapshots.get(sv.id, [])

                if snapshots:
                    # Use snapshot history for chart
                    equity = []
                    for snap in snapshots:
                        equity.append(snap["total_equity"])
                        # Build labels from timestamps
                        if len(labels) < len(equity):
                            try:
                                ts = datetime.fromisoformat(snap["timestamp"])
                                labels.append(ts.strftime("%H:%M"))
                            except Exception:
                                labels.append("")
                else:
                    # Fallback to trade-based if no snapshots yet
                    trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                    trades.sort(key=lambda t: t.exit_time or datetime.min)

                    equity = [STARTING_CAPITAL]
                    cumulative = STARTING_CAPITAL

                    for t in trades:
                        cumulative += t.pnl_usd
                        equity.append(cumulative)
                        if t.exit_time and len(labels) < len(equity):
                            labels.append(t.exit_time.strftime("%H:%M"))

                    # Add current unrealized P&L
                    open_positions = db.get_positions_for_sub_variant(sv.id)
                    unrealized_pnl = sum(p.current_pnl_usd for p in open_positions)
                    if unrealized_pnl != 0 or open_positions:
                        equity.append(cumulative + unrealized_pnl)
                        if len(labels) < len(equity):
                            labels.append("Now")

                # Ensure labels list is long enough
                while len(labels) < len(equity):
                    labels.append("")

                color = colors[i % len(colors)]
                datasets.append({
                    "label": sv.ai_model_name[:15],
                    "data": equity,
                    "borderColor": color,
                    "backgroundColor": "transparent",
                    "tension": 0.4,
                    "pointRadius": 0,  # Hide points for cleaner look
                })

    # Add "Start" label if no data
    if not labels:
        labels = ["Start"]

    return {"labels": labels, "datasets": datasets}


def get_strategy_chart_data() -> Dict[str, Any]:
    """Get chart data for strategy comparison using equity snapshots."""
    colors = ['#00d4ff', '#00ff88', '#ff4444', '#ffaa00', '#aa44ff']
    datasets = []
    labels = []

    # Get all snapshots for the last 24 hours
    all_snapshots = db.get_all_equity_snapshots(hours=24)

    variants = load_variants(db)

    for i, v in enumerate(variants):
        # Aggregate snapshots for all sub-variants in this variant
        # FIX: Use AVERAGE instead of SUM for fair comparison between variants
        # FIX2: Bucket timestamps to minute to group snapshots from different sub-variants
        variant_equity = {}  # timestamp_bucket -> {"total_pnl": float, "count": int}

        for sv in v.sub_variants:
            snapshots = all_snapshots.get(sv.id, [])
            for snap in snapshots:
                ts = snap["timestamp"]
                # Bucket timestamp to minute (remove seconds/milliseconds)
                try:
                    dt = datetime.fromisoformat(ts)
                    ts_bucket = dt.strftime("%Y-%m-%dT%H:%M:00")
                except Exception:
                    ts_bucket = ts[:16] + ":00"  # Fallback: truncate to minute

                if ts_bucket not in variant_equity:
                    variant_equity[ts_bucket] = {"total_pnl": 0.0, "count": 0}
                # Track P&L and count for averaging
                pnl = snap["total_equity"] - STARTING_CAPITAL
                variant_equity[ts_bucket]["total_pnl"] += pnl
                variant_equity[ts_bucket]["count"] += 1

        if variant_equity:
            # Sort by timestamp and build equity curve
            sorted_ts = sorted(variant_equity.keys())
            equity = []
            for ts in sorted_ts:
                # Calculate AVERAGE equity across sub-variants
                data = variant_equity[ts]
                if data["count"] > 0:
                    avg_pnl = data["total_pnl"] / data["count"]
                    avg_equity = STARTING_CAPITAL + avg_pnl
                else:
                    avg_equity = STARTING_CAPITAL
                equity.append(round(avg_equity, 2))
                if len(labels) < len(equity):
                    try:
                        dt = datetime.fromisoformat(ts)
                        labels.append(dt.strftime("%H:%M"))
                    except Exception:
                        labels.append("")
        else:
            # Fallback to trade-based if no snapshots yet
            trades = db.get_trades_for_variant(v.id, limit=1000)
            trades.sort(key=lambda t: t.exit_time or datetime.min)

            equity = [STARTING_CAPITAL]
            cumulative = STARTING_CAPITAL

            for t in trades:
                cumulative += t.pnl_usd
                equity.append(cumulative)
                if t.exit_time and len(labels) < len(equity):
                    labels.append(t.exit_time.strftime("%H:%M"))

            # Add unrealized P&L from open positions
            open_positions = db.get_positions_for_variant(v.id)
            unrealized_pnl = sum(p.current_pnl_usd for p in open_positions)
            if unrealized_pnl != 0 or open_positions:
                equity.append(cumulative + unrealized_pnl)
                if len(labels) < len(equity):
                    labels.append("Now")

        while len(labels) < len(equity):
            labels.append("")

        color = colors[i % len(colors)]
        datasets.append({
            "label": v.name[:15],
            "data": equity,
            "borderColor": color,
            "backgroundColor": "transparent",
            "tension": 0.4,
            "pointRadius": 0,  # Hide points for cleaner look
        })

    # Add "Start" label if no data
    if not labels:
        labels = ["Start"]

    return {"labels": labels, "datasets": datasets}


def is_simulation_paused() -> bool:
    """Check if simulation is paused."""
    return simulation_paused


def run_dashboard(host: str = "0.0.0.0", port: int = 5050, debug: bool = False):
    """Run the dashboard server."""
    init_dashboard()
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_dashboard()
