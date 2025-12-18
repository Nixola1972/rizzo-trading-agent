"""
Arena Dashboard - Interactive Web Interface V6

Features:
- Login system with session management
- V6 AI Battle with multiple charts per strategy family
- Toggle controls for variants and AI models
- Real-time equity curves
- API call tracking
- GO LIVE button to deploy winning model to production
- Pause/Resume simulation
"""

import os
import json
import math
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from functools import wraps
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for

from .db import ArenaDB
from .config_loader import load_variants
from .metrics import calculate_metrics, get_leaderboard
from .models import TradeDirection

# Login credentials
LOGIN_USERNAME = os.environ.get("ARENA_USERNAME", "nico")
LOGIN_PASSWORD = os.environ.get("ARENA_PASSWORD", "Trade@2025")


def sanitize_for_json(obj):
    """
    Recursively sanitize an object to ensure it's JSON-serializable.
    Replaces inf, -inf, nan with safe values.
    Handles datetime, None, and various numeric types.
    """
    if obj is None:
        return None
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, (int, bool, str)):
        return obj
    elif isinstance(obj, float):
        if math.isnan(obj):
            return 0.0
        elif math.isinf(obj):
            return 999.99 if obj > 0 else -999.99
        return obj
    else:
        # Try to convert to float for numpy types, etc.
        try:
            val = float(obj)
            if math.isnan(val):
                return 0.0
            elif math.isinf(val):
                return 999.99 if val > 0 else -999.99
            return val
        except (TypeError, ValueError):
            # Last resort: convert to string
            return str(obj)


# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("ARENA_SECRET_KEY", secrets.token_hex(32))


def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def safe_json_filter(obj):
    """Custom Jinja filter for safe JSON encoding that handles inf/nan and HTML."""
    from markupsafe import Markup
    sanitized = sanitize_for_json(obj)
    # Use ensure_ascii=True to escape all non-ASCII characters
    # Then escape HTML-unsafe characters for inline script safety
    json_str = json.dumps(sanitized, ensure_ascii=True, default=str)
    # Escape characters that could break inline <script> tags
    json_str = json_str.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return Markup(json_str)


# Register the custom filter
app.jinja_env.filters['safejson'] = safe_json_filter


# Database
db: Optional[ArenaDB] = None

# Simulation state (shared with simulator)
simulation_paused = False

# Starting capital for equity simulation
STARTING_CAPITAL = float(os.environ.get("ARENA_STARTING_CAPITAL", 100))

# Available AI models for selection (all models from V2_MULTI_AI + speciale)
AVAILABLE_AI_MODELS = [
    {"id": "deepseek/deepseek-v3.2-speciale", "name": "DeepSeek V3.2 Speciale"},
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"},
    {"id": "x-ai/grok-4.1-fast", "name": "Grok 4.1 Fast"},
    {"id": "anthropic/claude-haiku-4.5", "name": "Claude Haiku 4.5"},
    {"id": "qwen/qwen3-max", "name": "Qwen3 Max"},
    {"id": "tngtech/deepseek-r1t2-chimera:free", "name": "DeepSeek R1T2 Chimera (Free)"},
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B"},
]


def init_dashboard(database: Optional[ArenaDB] = None):
    """Initialize dashboard with database connection."""
    global db
    db = database or ArenaDB()


# ==================== HTML Templates ====================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏟️ Arena - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
            color: #cccccc;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: #1a1a3e;
            border-radius: 15px;
            padding: 40px;
            border: 1px solid #333;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h1 {
            color: #00d4ff;
            font-size: 2em;
            margin-bottom: 10px;
        }
        .login-header p {
            color: #888;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #888;
            font-size: 0.9em;
        }
        .form-group input {
            width: 100%;
            padding: 12px 15px;
            background: #0f0f23;
            border: 1px solid #333;
            border-radius: 8px;
            color: #fff;
            font-size: 1em;
            transition: border-color 0.2s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #00d4ff;
        }
        .login-btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            border: none;
            border-radius: 8px;
            color: #000;
            font-weight: 600;
            font-size: 1.1em;
            cursor: pointer;
            transition: all 0.2s;
        }
        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0, 212, 255, 0.4);
        }
        .error-message {
            background: #ff444433;
            color: #ff4444;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .version-badge {
            text-align: center;
            margin-top: 20px;
            color: #666;
            font-size: 0.85em;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>🏟️ Arena V6</h1>
            <p>AI Battle Trading System</p>
        </div>
        {% if error %}
        <div class="error-message">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="login-btn">🚀 Enter Arena</button>
        </form>
        <div class="version-badge">Arena V6 AI Battle System</div>
    </div>
</body>
</html>
"""

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

        /* Model Selector Dropdown */
        .model-selector {
            background: #1a1a3e;
            color: #00d4ff;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s;
        }
        .model-selector:hover {
            border-color: #00d4ff;
            background: #252550;
        }
        .model-selector:focus {
            outline: none;
            border-color: #00d4ff;
            box-shadow: 0 0 5px rgba(0, 212, 255, 0.3);
        }
        .model-selector option {
            background: #1a1a3e;
            color: #ccc;
        }

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
        .details-btn {
            width: 100%;
            margin-top: 10px;
            padding: 8px;
            background: #2a2a4e;
            border: 1px solid #444;
            border-radius: 4px;
            color: #aaa;
            cursor: pointer;
            font-size: 0.9em;
        }
        .details-btn:hover {
            background: #3a3a5e;
            color: #fff;
        }
        .rec-details {
            margin-top: 10px;
            padding: 10px;
            background: #1a1a3e;
            border-radius: 6px;
            border: 1px solid #333;
        }
        .details-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85em;
        }
        .details-table th {
            text-align: left;
            padding: 6px;
            color: #888;
            border-bottom: 1px solid #333;
        }
        .details-table td {
            padding: 6px;
            border-bottom: 1px solid #222;
        }
        .details-table .best-row {
            background: rgba(0, 255, 136, 0.1);
        }
        .details-table .best-row td {
            color: #00ff88;
            font-weight: 600;
        }
        .details-summary {
            margin-top: 10px;
            text-align: center;
            color: #666;
            font-size: 0.8em;
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

        /* AI Analysis Styles */
        .ai-analysis-btn {
            padding: 15px 30px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            font-size: 1.1em;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
        }
        .ai-analysis-btn:hover {
            background: linear-gradient(135deg, #8b5cf6, #a78bfa);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.4);
        }
        .ai-analysis-btn:disabled {
            background: #444;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        .ai-analysis-btn.loading {
            background: linear-gradient(135deg, #4b4b8a, #5a5a9a);
            animation: pulse-btn 1.5s infinite;
        }
        @keyframes pulse-btn {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .ai-result-card {
            background: #1e1e3f;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 3px solid #6366f1;
        }
        .ai-result-card h3 {
            color: #a78bfa;
            margin-bottom: 10px;
            font-size: 1em;
        }
        .ai-result-card ul {
            list-style: none;
            padding-left: 0;
        }
        .ai-result-card li {
            padding: 5px 0;
            border-bottom: 1px solid #333;
        }
        .ai-result-card li:last-child {
            border-bottom: none;
        }
        .ai-action-item {
            background: #252550;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .ai-action-item .action-title {
            font-weight: 600;
            color: #fff;
            margin-bottom: 5px;
        }
        .ai-action-item .action-reason {
            color: #aaa;
            font-size: 0.9em;
        }
        .ai-action-item .action-meta {
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            font-size: 0.85em;
        }
        .ai-action-item .priority-high { color: #ff4444; }
        .ai-action-item .priority-medium { color: #ffaa00; }
        .ai-action-item .priority-low { color: #00ff88; }

        /* V6 Grid Layout */
        .v6-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }
        @media (max-width: 1200px) {
            .v6-grid { grid-template-columns: 1fr; }
        }
        .v6-chart-box {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #333;
        }
        .v6-chart-box h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1em;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .v6-chart-box .interval-badge {
            font-size: 0.75em;
            padding: 4px 8px;
            background: #252550;
            border-radius: 4px;
            color: #888;
        }

        /* V6 Model Toggle Grid */
        .v6-models-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        .v6-model-toggle {
            background: #252550;
            border-radius: 6px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .v6-model-toggle .model-name {
            font-size: 0.85em;
            color: #ccc;
        }
        .v6-model-toggle .model-stats {
            font-size: 0.7em;
            color: #666;
        }

        /* GO LIVE Button */
        .go-live-container {
            background: linear-gradient(135deg, #1a3a1a, #0f0f23);
            border: 2px solid #00ff88;
            border-radius: 15px;
            padding: 25px;
            margin-top: 30px;
            text-align: center;
        }
        .go-live-container h2 {
            color: #00ff88;
            margin-bottom: 15px;
        }
        .go-live-container p {
            color: #888;
            margin-bottom: 20px;
        }
        .go-live-btn {
            padding: 20px 50px;
            background: linear-gradient(135deg, #00aa55, #00ff88);
            border: none;
            border-radius: 10px;
            color: #000;
            font-weight: 700;
            font-size: 1.3em;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 5px 25px rgba(0, 255, 136, 0.3);
        }
        .go-live-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 35px rgba(0, 255, 136, 0.5);
        }
        .go-live-btn:disabled {
            background: #444;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }
        .go-live-winner {
            background: #252550;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            display: inline-block;
        }
        .go-live-winner .winner-label {
            color: #888;
            font-size: 0.85em;
        }
        .go-live-winner .winner-name {
            color: #00ff88;
            font-size: 1.5em;
            font-weight: 600;
        }
        .go-live-winner .winner-stats {
            color: #ccc;
            margin-top: 5px;
        }

        /* Confirmation Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.active { display: flex; }
        .modal-box {
            background: #1a1a3e;
            border-radius: 15px;
            padding: 30px;
            max-width: 500px;
            border: 1px solid #333;
            text-align: center;
        }
        .modal-box h2 {
            color: #ffaa00;
            margin-bottom: 15px;
        }
        .modal-box p {
            color: #ccc;
            margin-bottom: 20px;
        }
        .modal-buttons {
            display: flex;
            gap: 15px;
            justify-content: center;
        }
        .modal-btn {
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .modal-btn-cancel {
            background: #444;
            color: #fff;
        }
        .modal-btn-confirm {
            background: linear-gradient(135deg, #ff6600, #ff8800);
            color: #fff;
        }
        .modal-btn:hover {
            transform: translateY(-2px);
        }

        /* Leaderboard highlight for best model */
        .leaderboard-best {
            background: linear-gradient(90deg, rgba(0, 255, 136, 0.1), transparent);
            border-left: 3px solid #00ff88;
        }

        /* Logout button */
        .logout-btn {
            padding: 8px 16px;
            background: transparent;
            border: 1px solid #666;
            color: #888;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .logout-btn:hover {
            border-color: #ff4444;
            color: #ff4444;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏟️ Arena V6 AI Battle</h1>
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
            <div class="header-stat">
                <button class="logout-btn" onclick="window.location.href='/logout'">🚪 Logout</button>
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
        <div class="tab active" onclick="showTab('v6-battle')">⚔️ V6 Battle</div>
        <div class="tab" onclick="showTab('ai-battle')">🤖 AI Models</div>
        <div class="tab" onclick="showTab('strategies')">📊 Strategies</div>
        <div class="tab" onclick="showTab('positions')">📍 Positions</div>
        <div class="tab" onclick="showTab('analytics')">🎯 Analytics</div>
    </div>

    <!-- GO LIVE Confirmation Modal -->
    <div id="golive-modal" class="modal-overlay">
        <div class="modal-box">
            <h2>⚠️ Conferma GO LIVE</h2>
            <p>Stai per deployare <strong id="modal-model-name"></strong> in produzione.</p>
            <p style="color: #ffaa00; font-size: 0.9em;">Questa azione modificherà la configurazione di RIZZO (produzione reale).</p>
            <div class="modal-buttons">
                <button class="modal-btn modal-btn-cancel" onclick="closeGoLiveModal()">❌ Annulla</button>
                <button class="modal-btn modal-btn-confirm" onclick="confirmGoLive()">✅ Conferma GO LIVE</button>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- V6 Battle Tab (NEW - Default) -->
        <div id="v6-battle" class="tab-content active">
            <!-- V6 Strategy Charts Grid -->
            <div class="v6-grid">
                <!-- V6 FAST (5min) Chart -->
                <div class="v6-chart-box">
                    <h3>
                        🚀 V6 Fast Strategies
                        <span class="interval-badge">5min check</span>
                    </h3>
                    <canvas id="v6FastChart" height="100"></canvas>
                </div>

                <!-- V6 MEDIUM (15min) Chart -->
                <div class="v6-chart-box">
                    <h3>
                        ⚖️ V6 Medium Strategies
                        <span class="interval-badge">15min check</span>
                    </h3>
                    <canvas id="v6MediumChart" height="100"></canvas>
                </div>

                <!-- V6 MACRO (1h) Chart -->
                <div class="v6-chart-box">
                    <h3>
                        🌍 V6 Macro Trend
                        <span class="interval-badge">1h check</span>
                    </h3>
                    <canvas id="v6MacroChart" height="100"></canvas>
                </div>

                <!-- V6 Combined Leaderboard -->
                <div class="v6-chart-box">
                    <h3>🏆 V6 AI Leaderboard (All Strategies)</h3>
                    <table>
                        <thead>
                            <tr><th>#</th><th>AI Model</th><th>Trades</th><th>Win%</th><th>W/L</th><th>P&L</th><th>API Calls</th></tr>
                        </thead>
                        <tbody>
                            {% for entry in v6_leaderboard %}
                            <tr class="{{ 'leaderboard-best' if entry.rank == 1 else '' }}">
                                <td>
                                    {% if entry.rank == 1 %}<span class="medal">🥇</span>
                                    {% elif entry.rank == 2 %}<span class="medal">🥈</span>
                                    {% elif entry.rank == 3 %}<span class="medal">🥉</span>
                                    {% else %}{{ entry.rank }}{% endif %}
                                </td>
                                <td>{{ entry.ai_model }}</td>
                                <td>{{ entry.total_trades }}</td>
                                <td>{{ "%.1f"|format(entry.win_rate) }}%</td>
                                <td><span style="color: #27ae60;">{{ entry.wins }}W</span> / <span style="color: #e74c3c;">{{ entry.losses }}L</span></td>
                                <td class="{{ 'pnl-positive' if entry.total_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(entry.total_pnl_usd) }}
                                </td>
                                <td>{{ entry.api_calls }} <span style="color: #e74c3c;">({{ entry.api_errors }} err)</span></td>
                            </tr>
                            {% endfor %}
                            {% if not v6_leaderboard %}
                            <tr><td colspan="7" style="text-align: center; color: #666;">No V6 trades yet</td></tr>
                            {% endif %}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- V6 Model Controls per Strategy -->
            <div class="section" style="margin-top: 20px;">
                <h2>⚙️ V6 AI Model Controls</h2>
                <p style="color: #888; margin-bottom: 15px;">Enable/disable AI models for each V6 strategy family.</p>

                {% for family in v6_model_controls %}
                <div style="margin-bottom: 20px;">
                    <h3 style="color: #00d4ff; font-size: 0.95em; margin-bottom: 10px;">
                        {{ family.name }}
                        <span style="color: #666; font-weight: normal;">({{ family.description }})</span>
                    </h3>
                    <div class="v6-models-grid">
                        {% for model in family.models %}
                        <div class="v6-model-toggle">
                            <div>
                                <div class="model-name">{{ model.name }}</div>
                                <div class="model-stats">{{ model.trades }} trades | {{ "%.1f"|format(model.win_rate) }}% WR</div>
                            </div>
                            <label class="toggle-switch">
                                <input type="checkbox" {{ 'checked' if model.enabled else '' }}
                                       onchange="toggleV6Model('{{ family.family }}', '{{ model.id }}', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>

            <!-- GO LIVE Section -->
            <div class="go-live-container">
                <h2>🚀 GO LIVE - Deploy to Botone Baseline</h2>
                <p>Deploy the best performing AI model + config to BOTONE (production bot).</p>

                {% if best_v6_model %}
                <div class="go-live-winner">
                    <div class="winner-label">BEST PERFORMER</div>
                    <div class="winner-name">{{ best_v6_model.name }}</div>
                    <div class="winner-stats">
                        {{ best_v6_model.trades }} trades |
                        {{ "%.1f"|format(best_v6_model.win_rate) }}% WR |
                        <span class="{{ 'pnl-positive' if best_v6_model.pnl >= 0 else 'pnl-negative' }}">
                            ${{ "%.2f"|format(best_v6_model.pnl) }}
                        </span>
                    </div>
                    {% if best_v6_model.variant_id %}
                    <div class="winner-variant" style="color: #888; font-size: 0.9em; margin-top: 5px;">
                        Variant: {{ best_v6_model.variant_id }} | Style: {{ best_v6_model.prompt_style or 'N/A' }}
                    </div>
                    {% endif %}
                </div>

                <div class="go-live-buttons" style="display: flex; gap: 15px; margin-top: 20px; flex-wrap: wrap;">
                    <button class="go-live-btn" style="background: linear-gradient(135deg, #3498db, #2980b9);"
                            onclick="copyToBaseline('{{ best_v6_model.id }}', '{{ best_v6_model.variant_id }}')"
                            {% if best_v6_model.trades < 5 %}disabled title="Need at least 5 trades"{% endif %}>
                        📋 Copy to .env.baseline
                    </button>
                    <button class="go-live-btn" style="background: linear-gradient(135deg, #27ae60, #1e8449);"
                            onclick="startBotone()">
                        🚀 Start Botone Containers
                    </button>
                    <button class="go-live-btn" style="background: linear-gradient(135deg, #e74c3c, #c0392b);"
                            onclick="stopBotone()">
                        ⏹️ Stop Botone
                    </button>
                </div>

                {% if best_v6_model.trades < 5 %}
                <p style="color: #888; margin-top: 10px; font-size: 0.85em;">
                    ⚠️ Minimum 5 trades required for Copy. Current: {{ best_v6_model.trades }}
                </p>
                {% endif %}

                <div id="go-live-status" style="margin-top: 15px; padding: 10px; border-radius: 8px; display: none;"></div>

                {% else %}
                <p style="color: #666;">No V6 trades yet. Start the simulation to collect data.</p>
                <div class="go-live-buttons" style="display: flex; gap: 15px; margin-top: 20px;">
                    <button class="go-live-btn" disabled>📋 Copy to .env.baseline</button>
                    <button class="go-live-btn" style="background: linear-gradient(135deg, #27ae60, #1e8449);"
                            onclick="startBotone()">
                        🚀 Start Botone Containers
                    </button>
                    <button class="go-live-btn" style="background: linear-gradient(135deg, #e74c3c, #c0392b);"
                            onclick="stopBotone()">
                        ⏹️ Stop Botone
                    </button>
                </div>
                {% endif %}
            </div>
        </div>

        <!-- AI Battle Tab (Legacy V2) -->
        <div id="ai-battle" class="tab-content">
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
                                📊 WR: {{ "%.1f"|format(model.win_rate) }}% ({{ model.winning_trades }}W / {{ model.losing_trades }}L) |
                                📞 API: {{ model.api_calls }} | ❌ Err: {{ model.api_errors }}
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
                            <th>AI Model</th>
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
                            <td>
                                {% if v.is_single_model %}
                                <select class="model-selector" onchange="changeVariantModel('{{ v.id }}', this.value)" style="max-width: 180px;">
                                    {% for m in available_models %}
                                    <option value="{{ m.id }}" {{ 'selected' if m.id == v.current_model else '' }}>
                                        {{ m.name }}
                                    </option>
                                    {% endfor %}
                                </select>
                                {% else %}
                                <span style="color: #888;">{{ v.ai_count }} modelli (Battle)</span>
                                {% endif %}
                            </td>
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
                        {% if rec.details and rec.details.ranges %}
                        <button class="details-btn" onclick="toggleDetails({{ loop.index0 }})">
                            📊 Mostra dettagli
                        </button>
                        <div class="rec-details" id="details-{{ loop.index0 }}" style="display: none;">
                            <table class="details-table">
                                <thead>
                                    <tr>
                                        <th>Score Range</th>
                                        <th>Trade</th>
                                        <th>Win Rate</th>
                                        <th>Avg P&L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for r in rec.details.ranges %}
                                    <tr class="{% if r.is_best %}best-row{% endif %}">
                                        <td>{{ r.range }}{% if r.is_best %} ⭐{% endif %}</td>
                                        <td>{{ r.trades }}</td>
                                        <td>{% if r.win_rate %}{{ "%.1f"|format(r.win_rate * 100) }}%{% else %}-{% endif %}</td>
                                        <td class="{% if r.avg_pnl and r.avg_pnl > 0 %}pnl-positive{% elif r.avg_pnl and r.avg_pnl < 0 %}pnl-negative{% endif %}">
                                            {% if r.avg_pnl %}${{ "%.2f"|format(r.avg_pnl) }}{% else %}-{% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                            <div class="details-summary">
                                Totale: {{ rec.details.total_trades }} trade analizzati
                            </div>
                        </div>
                        {% endif %}
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

                <!-- AI Deep Analysis Section -->
                <div class="section" style="margin-top: 30px;">
                    <h2>🤖 AI Deep Analysis</h2>
                    <p style="color: #888; margin-bottom: 15px;">
                        Analisi approfondita dei dati di trading usando LLM. Genera insight, pattern e raccomandazioni avanzate.
                    </p>

                    <div style="text-align: center; margin-bottom: 20px;">
                        <button class="ai-analysis-btn" id="run-ai-analysis" onclick="runAIAnalysis()">
                            🧠 Esegui Analisi AI
                        </button>
                        <span id="ai-analysis-status" style="margin-left: 15px; color: #888;"></span>
                    </div>

                    <div id="ai-analysis-result" style="display: none;">
                        <div class="ai-result-card">
                            <h3>📝 Riepilogo</h3>
                            <p id="ai-summary" style="color: #ccc;"></p>
                        </div>

                        <div class="ai-result-card">
                            <h3>💡 Key Insights</h3>
                            <ul id="ai-insights" style="color: #ccc;"></ul>
                        </div>

                        <div class="ai-result-card">
                            <h3>⚡ Azioni Raccomandate</h3>
                            <div id="ai-actions"></div>
                        </div>

                        <div class="ai-result-card" style="border-left: 3px solid #ff4444;">
                            <h3>⚠️ Risk Warnings</h3>
                            <ul id="ai-warnings" style="color: #ffaa00;"></ul>
                        </div>

                        <div class="ai-result-card">
                            <h3>📊 Market Observations</h3>
                            <ul id="ai-observations" style="color: #ccc;"></ul>
                        </div>

                        <div style="text-align: center; margin-top: 15px; color: #666; font-size: 0.8em;">
                            <span id="ai-meta"></span>
                        </div>
                    </div>
                </div>

                <!-- Detailed Analytics Breakdown Section -->
                <div class="section" style="margin-top: 30px; grid-column: span 2;">
                    <h2>📊 Detailed Breakdown (with Fees)</h2>
                    <p style="color: #888; margin-bottom: 15px;">
                        Analisi dettagliata per AI Model, Stile e Timeframe. Include calcolo fees (0.0432% taker).
                    </p>

                    <!-- Totals Summary -->
                    <div class="analytics-stats" style="margin-bottom: 25px;">
                        <div class="stat-box">
                            <div class="stat-label">Total Trades</div>
                            <div class="stat-value">{{ detailed_analytics.totals.trades or 0 }}</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Gross P&L</div>
                            <div class="stat-value {{ 'positive' if (detailed_analytics.totals.gross_pnl_usd or 0) >= 0 else 'negative' }}">
                                ${{ "%.2f"|format(detailed_analytics.totals.gross_pnl_usd or 0) }}
                            </div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Total Fees</div>
                            <div class="stat-value" style="color: #ff6666;">
                                -${{ "%.2f"|format(detailed_analytics.totals.total_fees_usd or 0) }}
                            </div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Net P&L</div>
                            <div class="stat-value {{ 'positive' if (detailed_analytics.totals.net_pnl_usd or 0) >= 0 else 'negative' }}">
                                ${{ "%.2f"|format(detailed_analytics.totals.net_pnl_usd or 0) }}
                            </div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Win Rate</div>
                            <div class="stat-value">{{ "%.1f"|format(detailed_analytics.totals.win_rate or 0) }}%</div>
                        </div>
                    </div>

                    <!-- By AI Model -->
                    <h3 style="color: #00d4ff; margin-bottom: 10px;">🤖 Per AI Model</h3>
                    <table style="margin-bottom: 25px;">
                        <thead>
                            <tr>
                                <th>AI Model</th>
                                <th>Trades</th>
                                <th>W/L</th>
                                <th>Win%</th>
                                <th>Gross P&L</th>
                                <th>Fees</th>
                                <th>Net P&L</th>
                                <th>Avg Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for model, stats in detailed_analytics.by_model.items() %}
                            <tr>
                                <td>{{ model }}</td>
                                <td>{{ stats.trades }}</td>
                                <td>{{ stats.wins }}/{{ stats.losses }}</td>
                                <td>{{ "%.1f"|format(stats.win_rate) }}%</td>
                                <td class="{{ 'pnl-positive' if stats.gross_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.gross_pnl_usd) }}
                                </td>
                                <td style="color: #ff6666;">-${{ "%.2f"|format(stats.total_fees_usd) }}</td>
                                <td class="{{ 'pnl-positive' if stats.net_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.net_pnl_usd) }}
                                </td>
                                <td>{{ "%.1f"|format(stats.avg_duration_min) }}m</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="8" style="text-align: center; color: #666;">Nessun trade</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>

                    <!-- By Style -->
                    <h3 style="color: #00ff88; margin-bottom: 10px;">🎯 Per Stile</h3>
                    <table style="margin-bottom: 25px;">
                        <thead>
                            <tr>
                                <th>Stile</th>
                                <th>Trades</th>
                                <th>W/L</th>
                                <th>Win%</th>
                                <th>Gross P&L</th>
                                <th>Fees</th>
                                <th>Net P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for style, stats in detailed_analytics.by_style.items() %}
                            <tr>
                                <td>
                                    {% if style == 'PRUDENT' %}🛡️{% elif style == 'MODERATE' %}⚖️{% elif style == 'AGGRESSIVE' %}🔥{% elif style == 'TREND' %}📈{% else %}❓{% endif %}
                                    {{ style }}
                                </td>
                                <td>{{ stats.trades }}</td>
                                <td>{{ stats.wins }}/{{ stats.losses }}</td>
                                <td>{{ "%.1f"|format(stats.win_rate) }}%</td>
                                <td class="{{ 'pnl-positive' if stats.gross_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.gross_pnl_usd) }}
                                </td>
                                <td style="color: #ff6666;">-${{ "%.2f"|format(stats.total_fees_usd) }}</td>
                                <td class="{{ 'pnl-positive' if stats.net_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.net_pnl_usd) }}
                                </td>
                            </tr>
                            {% else %}
                            <tr><td colspan="7" style="text-align: center; color: #666;">Nessun trade</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>

                    <!-- By Timeframe -->
                    <h3 style="color: #ffaa00; margin-bottom: 10px;">⏱️ Per Timeframe</h3>
                    <table style="margin-bottom: 25px;">
                        <thead>
                            <tr>
                                <th>Timeframe</th>
                                <th>Trades</th>
                                <th>W/L</th>
                                <th>Win%</th>
                                <th>Gross P&L</th>
                                <th>Fees</th>
                                <th>Net P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for tf, stats in detailed_analytics.by_timeframe.items() %}
                            <tr>
                                <td>
                                    {% if tf == 'FAST' %}⚡{% elif tf == 'MEDIUM' %}🕐{% elif tf == 'MACRO' %}📊{% else %}📁{% endif %}
                                    {{ tf }}
                                </td>
                                <td>{{ stats.trades }}</td>
                                <td>{{ stats.wins }}/{{ stats.losses }}</td>
                                <td>{{ "%.1f"|format(stats.win_rate) }}%</td>
                                <td class="{{ 'pnl-positive' if stats.gross_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.gross_pnl_usd) }}
                                </td>
                                <td style="color: #ff6666;">-${{ "%.2f"|format(stats.total_fees_usd) }}</td>
                                <td class="{{ 'pnl-positive' if stats.net_pnl_usd >= 0 else 'pnl-negative' }}">
                                    ${{ "%.2f"|format(stats.net_pnl_usd) }}
                                </td>
                            </tr>
                            {% else %}
                            <tr><td colspan="7" style="text-align: center; color: #666;">Nessun trade</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>

                    <!-- Matrix View: Model × Style (Collapsible) -->
                    <details style="margin-bottom: 20px;">
                        <summary style="cursor: pointer; color: #aa44ff; font-size: 1.1em; margin-bottom: 10px;">
                            🔮 Matrice AI Model × Stile (click per espandere)
                        </summary>
                        <table>
                            <thead>
                                <tr>
                                    <th>Model | Style</th>
                                    <th>Trades</th>
                                    <th>Win%</th>
                                    <th>Net P&L</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for key, stats in detailed_analytics.by_model_style.items() %}
                                {% set parts = key.split('|') %}
                                <tr>
                                    <td>{{ parts[0] }} × {{ parts[1] }}</td>
                                    <td>{{ stats.trades }}</td>
                                    <td>{{ "%.1f"|format(stats.win_rate) }}%</td>
                                    <td class="{{ 'pnl-positive' if stats.net_pnl_usd >= 0 else 'pnl-negative' }}">
                                        ${{ "%.2f"|format(stats.net_pnl_usd) }}
                                    </td>
                                </tr>
                                {% else %}
                                <tr><td colspan="4" style="text-align: center; color: #666;">Nessun trade</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </details>
                </div>
            </div>
        </div>

        <div class="refresh-info">
            Auto-refresh every 60 seconds • Last update: {{ now }}
        </div>
    </div>

    <!-- Essential UI functions - separate script to ensure they load even if charts fail -->
    <script>
        // Tab switching - preserves tab in URL hash for refresh
        function showTab(tabId) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector(`[onclick="showTab('${tabId}')"]`).classList.add('active');
            document.getElementById(tabId).classList.add('active');
            // Save current tab to URL hash for persistence across refresh
            window.location.hash = tabId;
        }

        // Restore tab from URL hash on page load
        (function() {
            const hash = window.location.hash.substring(1);
            if (hash && document.getElementById(hash)) {
                showTab(hash);
            }
        })();

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

        function changeVariantModel(variantId, modelId) {
            const select = event.target;
            select.disabled = true;
            select.style.opacity = '0.5';

            fetch(`/api/variant/${variantId}/model`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelId })
            })
            .then(r => r.json())
            .then(d => {
                select.disabled = false;
                select.style.opacity = '1';

                if (d.success) {
                    alert('✅ ' + d.message);
                    // Reload page after short delay
                    setTimeout(() => location.reload(), 1000);
                } else {
                    alert('❌ Errore: ' + d.error);
                }
            })
            .catch(e => {
                select.disabled = false;
                select.style.opacity = '1';
                alert('❌ Errore di connessione');
            });
        }

        function closePosition(positionId) {
            if (confirm('Close this position?')) {
                fetch(`/api/position/${positionId}/close`, { method: 'POST' })
                    .then(r => r.json())
                    .then(d => location.reload());
            }
        }

        // V6 Model Toggle
        function toggleV6Model(family, modelId, enabled) {
            fetch(`/api/v6/model/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ family: family, model_id: modelId, enabled: enabled })
            })
            .then(r => r.json())
            .then(d => {
                if (!d.success) {
                    alert('Error: ' + d.error);
                    location.reload();
                }
            });
        }

        // GO LIVE Modal
        let goLiveModelId = null;
        let goLiveModelName = null;

        function showGoLiveModal(modelId, modelName) {
            goLiveModelId = modelId;
            goLiveModelName = modelName;
            document.getElementById('modal-model-name').textContent = modelName;
            document.getElementById('golive-modal').classList.add('active');
        }

        function closeGoLiveModal() {
            document.getElementById('golive-modal').classList.remove('active');
            goLiveModelId = null;
            goLiveModelName = null;
        }

        function confirmGoLive() {
            if (!goLiveModelId) return;

            const btn = document.querySelector('.modal-btn-confirm');
            btn.disabled = true;
            btn.textContent = '⏳ Deploying...';

            fetch('/api/go-live', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: goLiveModelId, model_name: goLiveModelName })
            })
            .then(r => r.json())
            .then(d => {
                closeGoLiveModal();
                if (d.success) {
                    alert('✅ GO LIVE Success!\\n\\n' + d.message + '\\n\\nRizzo will use: ' + goLiveModelName);
                    location.reload();
                } else {
                    alert('❌ GO LIVE Failed:\\n\\n' + d.error);
                }
            })
            .catch(e => {
                closeGoLiveModal();
                alert('❌ Connection error');
            });
        }

        // Botone Baseline Functions
        function showStatus(message, isError = false) {
            const status = document.getElementById('go-live-status');
            status.style.display = 'block';
            status.style.background = isError ? '#c0392b' : '#27ae60';
            status.style.color = 'white';
            status.innerHTML = message;
        }

        function copyToBaseline(modelId, variantId) {
            if (!confirm('Copiare la configurazione in .env.baseline?\\n\\nModel: ' + modelId + '\\nVariant: ' + variantId)) return;

            showStatus('⏳ Copiando configurazione...');

            fetch('/api/copy-to-baseline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: modelId, variant_id: variantId })
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    showStatus('✅ ' + d.message + '<br><small>Parametri copiati: ' + d.params_copied + '</small>');
                } else {
                    showStatus('❌ Errore: ' + d.error, true);
                }
            })
            .catch(e => showStatus('❌ Errore di connessione', true));
        }

        function startBotone() {
            if (!confirm('Avviare i container Botone Baseline?\\n\\n• botone_baseline_slow\\n• botone_baseline_fast')) return;

            showStatus('⏳ Avviando containers...');

            fetch('/api/botone/start', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    showStatus('✅ ' + d.message);
                } else {
                    showStatus('❌ Errore: ' + d.error, true);
                }
            })
            .catch(e => showStatus('❌ Errore di connessione', true));
        }

        function stopBotone() {
            if (!confirm('Fermare i container Botone Baseline?')) return;

            showStatus('⏳ Fermando containers...');

            fetch('/api/botone/stop', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    showStatus('✅ ' + d.message);
                } else {
                    showStatus('❌ Errore: ' + d.error, true);
                }
            })
            .catch(e => showStatus('❌ Errore di connessione', true));
        }

        // Close modal on overlay click
        document.getElementById('golive-modal').addEventListener('click', function(e) {
            if (e.target === this) closeGoLiveModal();
        });

        function toggleDetails(index) {
            const details = document.getElementById('details-' + index);
            const btn = details.previousElementSibling;
            if (details.style.display === 'none') {
                details.style.display = 'block';
                btn.textContent = '📊 Nascondi dettagli';
            } else {
                details.style.display = 'none';
                btn.textContent = '📊 Mostra dettagli';
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
                        alert(`✅ ${d.message}\\n\\nModifiche:\\n${d.changes.join('\\n')}`);
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
                        alert(`✅ Applicate ${d.applied}/${d.total} raccomandazioni!\\n\\n` +
                              d.results.map(r => `${r.success ? '✓' : '✗'} ${r.message}`).join('\\n'));
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

        function runAIAnalysis() {
            const btn = document.getElementById('run-ai-analysis');
            const status = document.getElementById('ai-analysis-status');
            const result = document.getElementById('ai-analysis-result');

            btn.disabled = true;
            btn.classList.add('loading');
            btn.textContent = '⏳ Analizzando...';
            status.textContent = 'Chiamata API in corso...';

            fetch('/api/ai-analysis/run', { method: 'POST' })
                .then(r => r.json())
                .then(d => {
                    btn.disabled = false;
                    btn.classList.remove('loading');
                    btn.textContent = '🧠 Esegui Analisi AI';

                    if (d.success) {
                        status.textContent = `Completato in ${d.execution_time.toFixed(1)}s (${d.model_used})`;
                        result.style.display = 'block';

                        // Populate summary
                        document.getElementById('ai-summary').textContent = d.summary || 'Nessun riepilogo disponibile';

                        // Populate insights
                        const insightsList = document.getElementById('ai-insights');
                        insightsList.innerHTML = '';
                        (d.key_insights || []).forEach(insight => {
                            const li = document.createElement('li');
                            li.textContent = insight;
                            insightsList.appendChild(li);
                        });
                        if (!d.key_insights || d.key_insights.length === 0) {
                            insightsList.innerHTML = '<li style="color: #666;">Nessun insight disponibile</li>';
                        }

                        // Populate actions
                        const actionsDiv = document.getElementById('ai-actions');
                        actionsDiv.innerHTML = '';
                        (d.recommended_actions || []).forEach(action => {
                            const actionDiv = document.createElement('div');
                            actionDiv.className = 'ai-action-item';
                            actionDiv.innerHTML = `
                                <div class="action-title">${action.action || 'Azione'}</div>
                                <div class="action-reason">${action.reason || ''}</div>
                                <div class="action-meta">
                                    <span class="priority-${action.priority || 'medium'}">${(action.priority || 'medium').toUpperCase()}</span>
                                    <span>${action.expected_impact || ''}</span>
                                </div>
                            `;
                            actionsDiv.appendChild(actionDiv);
                        });
                        if (!d.recommended_actions || d.recommended_actions.length === 0) {
                            actionsDiv.innerHTML = '<p style="color: #666;">Nessuna azione raccomandata</p>';
                        }

                        // Populate warnings
                        const warningsList = document.getElementById('ai-warnings');
                        warningsList.innerHTML = '';
                        (d.risk_warnings || []).forEach(warning => {
                            const li = document.createElement('li');
                            li.textContent = warning;
                            warningsList.appendChild(li);
                        });
                        if (!d.risk_warnings || d.risk_warnings.length === 0) {
                            warningsList.innerHTML = '<li style="color: #666;">Nessun warning</li>';
                        }

                        // Populate observations
                        const obsList = document.getElementById('ai-observations');
                        obsList.innerHTML = '';
                        (d.market_observations || []).forEach(obs => {
                            const li = document.createElement('li');
                            li.textContent = obs;
                            obsList.appendChild(li);
                        });
                        if (!d.market_observations || d.market_observations.length === 0) {
                            obsList.innerHTML = '<li style="color: #666;">Nessuna osservazione</li>';
                        }

                        // Meta info
                        document.getElementById('ai-meta').textContent =
                            `Report ID: ${d.report_id} | Model: ${d.model_used}`;

                    } else {
                        status.textContent = `Errore: ${d.error}`;
                        result.style.display = 'none';
                    }
                })
                .catch(e => {
                    btn.disabled = false;
                    btn.classList.remove('loading');
                    btn.textContent = '🧠 Esegui Analisi AI';
                    status.textContent = 'Errore di connessione';
                    console.error('AI Analysis error:', e);
                });
        }

        // Check for previous AI analysis on page load
        (function loadLastAIAnalysis() {
            fetch('/api/ai-analysis/last')
                .then(r => r.json())
                .then(d => {
                    if (d.success) {
                        const status = document.getElementById('ai-analysis-status');
                        status.textContent = `Ultimo report: ${d.generated_at}`;
                    }
                });
        })();

        // Auto-refresh every 60 seconds (preserves current tab via URL hash)
        setTimeout(() => location.reload(), 60000);
    </script>

    <!-- Charts - separate script so chart errors don't break UI functions -->
    <script>
        try {
            const aiData = {{ ai_chart_data | safejson }};
            const stratData = {{ strategy_chart_data | safejson }};
            const v6FastData = {{ v6_fast_chart_data | safejson }};
            const v6MediumData = {{ v6_medium_chart_data | safejson }};
            const v6MacroData = {{ v6_macro_chart_data | safejson }};

            const chartOptions = {
                responsive: true,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { labels: { color: '#888' } } },
                scales: {
                    x: { grid: { color: '#333' }, ticks: { color: '#888' } },
                    y: { grid: { color: '#333' }, ticks: { color: '#888', callback: v => '$' + v.toFixed(2) } }
                }
            };

            const v6ChartOptions = {
                ...chartOptions,
                plugins: {
                    ...chartOptions.plugins,
                    legend: { display: true, position: 'bottom', labels: { color: '#888', boxWidth: 12, padding: 8 } }
                }
            };

            if (typeof Chart !== 'undefined') {
                // V6 Fast Chart (5min strategies)
                if (document.getElementById('v6FastChart')) {
                    new Chart(document.getElementById('v6FastChart').getContext('2d'), {
                        type: 'line',
                        data: { labels: v6FastData.labels || [], datasets: v6FastData.datasets || [] },
                        options: v6ChartOptions
                    });
                }

                // V6 Medium Chart (15min strategies)
                if (document.getElementById('v6MediumChart')) {
                    new Chart(document.getElementById('v6MediumChart').getContext('2d'), {
                        type: 'line',
                        data: { labels: v6MediumData.labels || [], datasets: v6MediumData.datasets || [] },
                        options: v6ChartOptions
                    });
                }

                // V6 Macro Chart (1h strategy)
                if (document.getElementById('v6MacroChart')) {
                    new Chart(document.getElementById('v6MacroChart').getContext('2d'), {
                        type: 'line',
                        data: { labels: v6MacroData.labels || [], datasets: v6MacroData.datasets || [] },
                        options: v6ChartOptions
                    });
                }

                // Legacy charts
                if (document.getElementById('aiBattleChart')) {
                    new Chart(document.getElementById('aiBattleChart').getContext('2d'), {
                        type: 'line',
                        data: { labels: aiData.labels || [], datasets: aiData.datasets || [] },
                        options: chartOptions
                    });
                }

                if (document.getElementById('strategiesChart')) {
                    new Chart(document.getElementById('strategiesChart').getContext('2d'), {
                        type: 'line',
                        data: { labels: stratData.labels || [], datasets: stratData.datasets || [] },
                        options: chartOptions
                    });
                }
            } else {
                console.warn('Chart.js not loaded - charts disabled');
            }
        } catch (e) {
            console.error('Chart initialization error:', e);
        }
    </script>
</body>
</html>
"""


# ==================== Routes ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_HTML, error="Invalid credentials")

    return render_template_string(LOGIN_HTML, error=None)


@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
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
    ai_chart_data = sanitize_for_json(get_ai_chart_data())
    strategy_chart_data = sanitize_for_json(get_strategy_chart_data())
    analytics = sanitize_for_json(get_analytics_data())
    detailed_analytics = sanitize_for_json(db.get_detailed_analytics())

    # V6 specific data
    v6_leaderboard = sanitize_for_json(get_v6_leaderboard())
    v6_model_controls = sanitize_for_json(get_v6_model_controls())
    best_v6_model = sanitize_for_json(get_best_v6_model())
    v6_fast_chart_data = sanitize_for_json(get_v6_chart_data('FAST'))
    v6_medium_chart_data = sanitize_for_json(get_v6_chart_data('MEDIUM'))
    v6_macro_chart_data = sanitize_for_json(get_v6_chart_data('MACRO'))

    return render_template_string(
        DASHBOARD_HTML,
        stats=sanitize_for_json(stats),
        variants=sanitize_for_json(variants),
        ai_models=sanitize_for_json(ai_models),
        ai_leaderboard=sanitize_for_json(ai_leaderboard),
        positions=sanitize_for_json(positions),
        recent_trades=sanitize_for_json(recent_trades),
        ai_chart_data=ai_chart_data,
        strategy_chart_data=strategy_chart_data,
        analytics=analytics,
        detailed_analytics=detailed_analytics,
        available_models=AVAILABLE_AI_MODELS,
        paused=simulation_paused,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # V6 data
        v6_leaderboard=v6_leaderboard,
        v6_model_controls=v6_model_controls,
        best_v6_model=best_v6_model,
        v6_fast_chart_data=v6_fast_chart_data,
        v6_medium_chart_data=v6_medium_chart_data,
        v6_macro_chart_data=v6_macro_chart_data,
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


@app.route('/api/variant/<variant_id>/model', methods=['POST'])
def api_change_variant_model(variant_id):
    """Change the AI model for a single-model variant."""
    import logging
    logger = logging.getLogger("arena.dashboard")

    data = request.get_json() or {}
    new_model = data.get('model')

    if not new_model:
        return jsonify({"success": False, "error": "Model not specified"})

    # Validate model is in available list
    valid_models = [m["id"] for m in AVAILABLE_AI_MODELS]
    if new_model not in valid_models:
        return jsonify({"success": False, "error": f"Invalid model: {new_model}"})

    try:
        # Load and update variants.json
        import os
        variants_path = os.path.join(os.path.dirname(__file__), "variants.json")

        with open(variants_path, 'r') as f:
            variants_data = json.load(f)

        # Find and update the variant
        updated = False
        for v in variants_data.get("variants", []):
            if v.get("id") == variant_id:
                # Only update single-model variants (not V2_MULTI_AI)
                if len(v.get("ai_models", [])) == 1:
                    v["ai_models"] = [new_model]
                    updated = True
                    logger.info(f"Updated {variant_id} AI model to: {new_model}")
                else:
                    return jsonify({"success": False, "error": "Cannot change model for multi-AI variants"})
                break

        if not updated:
            return jsonify({"success": False, "error": f"Variant {variant_id} not found"})

        # Save updated variants.json
        with open(variants_path, 'w') as f:
            json.dump(variants_data, f, indent=2)

        model_short = new_model.split('/')[-1]
        new_sv_id = f"{variant_id}_{model_short}"

        # Update variant's ai_models in database
        db.update_variant_ai_models(variant_id, [new_model])
        logger.info(f"Updated variant {variant_id} ai_models in DB to: {new_model}")

        # Delete old sub-variant and create new one
        db.delete_sub_variant_by_variant(variant_id)

        from .models import SubVariant
        new_sv = SubVariant(
            id=new_sv_id,
            variant_id=variant_id,
            ai_model=new_model,
            ai_model_name=model_short,
            enabled=True
        )
        db.save_sub_variant(new_sv)

        return jsonify({
            "success": True,
            "model": new_model,
            "message": f"Modello cambiato a {model_short}. Refresh page per vedere."
        })

    except Exception as e:
        logger.error(f"Error changing model: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/available-models')
def api_available_models():
    """Get list of available AI models."""
    return jsonify({"models": AVAILABLE_AI_MODELS})


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


@app.route('/api/analytics/detailed')
def api_detailed_analytics():
    """
    Get detailed analytics with breakdown by AI Model, Style, and Timeframe.

    Query params:
    - hours: Optional, filter to last N hours (default: all time)
    """
    hours = request.args.get('hours', type=int)
    data = db.get_detailed_analytics(hours=hours)
    return jsonify(sanitize_for_json(data))


# AI Analysis cache
_ai_analyzer = None
_ai_last_report = None


@app.route('/api/ai-analysis/run', methods=['POST'])
def api_run_ai_analysis():
    """Trigger AI-powered deep analysis."""
    global _ai_analyzer, _ai_last_report

    try:
        from .ai_analysis import AIAnalyzer

        if _ai_analyzer is None:
            _ai_analyzer = AIAnalyzer(db)

        report = _ai_analyzer.run_analysis(force=True)

        if report:
            _ai_last_report = report
            return jsonify({
                "success": True,
                "report_id": report.report_id,
                "model_used": report.model_used,
                "summary": report.analysis_text,
                "key_insights": report.key_insights,
                "recommended_actions": report.recommended_actions,
                "risk_warnings": report.risk_warnings,
                "market_observations": report.market_observations,
                "execution_time": report.execution_time_seconds,
            })
        else:
            return jsonify({"success": False, "error": "AI analysis failed - check API key"})

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()})


@app.route('/api/ai-analysis/last')
def api_get_last_ai_analysis():
    """Get the last AI analysis report."""
    global _ai_last_report

    if _ai_last_report:
        return jsonify({
            "success": True,
            "report_id": _ai_last_report.report_id,
            "generated_at": _ai_last_report.generated_at.isoformat(),
            "model_used": _ai_last_report.model_used,
            "summary": _ai_last_report.analysis_text,
            "key_insights": _ai_last_report.key_insights,
            "recommended_actions": _ai_last_report.recommended_actions,
            "risk_warnings": _ai_last_report.risk_warnings,
            "market_observations": _ai_last_report.market_observations,
        })
    else:
        return jsonify({"success": False, "message": "Nessuna analisi AI disponibile. Clicca 'Esegui Analisi AI' per generarne una."})


# ==================== V6 API Routes ====================

@app.route('/api/v6/model/toggle', methods=['POST'])
def api_toggle_v6_model():
    """Toggle a specific AI model on/off for a V6 variant family."""
    import logging
    logger = logging.getLogger("arena.dashboard")

    data = request.get_json() or {}
    family = data.get('family')  # FAST, MEDIUM, MACRO
    model_id = data.get('model_id')
    enabled = data.get('enabled', True)

    if not model_id:
        return jsonify({"success": False, "error": "Missing model_id"})

    try:
        # Get model name for sub_variant lookup
        model_name = model_id.split("/")[-1]

        # Define variant families
        families = {
            "FAST": ["V6_FAST_PRUDENT", "V6_FAST_MODERATE", "V6_FAST_AGGRESSIVE"],
            "MEDIUM": ["V6_MEDIUM_PRUDENT", "V6_MEDIUM_MODERATE", "V6_MEDIUM_AGGRESSIVE"],
            "MACRO": ["V6_MACRO_TREND"],
        }

        # Get variants for this family (or all if no family specified)
        if family and family in families:
            target_variants = families[family]
        else:
            # If no family, update all V6 variants
            target_variants = []
            for variants_list in families.values():
                target_variants.extend(variants_list)

        # Update all sub_variants in the database for this model
        updated_count = 0
        for variant_id in target_variants:
            sub_variant_id = f"{variant_id}_{model_name}"
            if db.toggle_sub_variant(sub_variant_id, enabled):
                updated_count += 1
                logger.info(f"V6 Model toggle: {sub_variant_id} = {enabled}")

        return jsonify({"success": True, "enabled": enabled, "updated": updated_count})

    except Exception as e:
        logger.error(f"Error toggling V6 model: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/go-live', methods=['POST'])
def api_go_live():
    """Deploy the winning AI model to production (Rizzo)."""
    import logging
    logger = logging.getLogger("arena.dashboard")

    data = request.get_json() or {}
    model_id = data.get('model_id')
    model_name = data.get('model_name')

    if not model_id:
        return jsonify({"success": False, "error": "Missing model_id"})

    try:
        # Find the production .env file
        prod_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

        if not os.path.exists(prod_env_path):
            return jsonify({"success": False, "error": f".env file not found at {prod_env_path}"})

        # Read current .env
        with open(prod_env_path, 'r') as f:
            env_content = f.read()

        # Update OPENROUTER_MODEL
        import re
        new_env = re.sub(
            r'^OPENROUTER_MODEL=.*$',
            f'OPENROUTER_MODEL={model_id}',
            env_content,
            flags=re.MULTILINE
        )

        # If OPENROUTER_MODEL doesn't exist, add it
        if 'OPENROUTER_MODEL=' not in new_env:
            new_env += f'\nOPENROUTER_MODEL={model_id}\n'

        # Write updated .env
        with open(prod_env_path, 'w') as f:
            f.write(new_env)

        logger.info(f"GO LIVE: Deployed {model_id} to production")

        return jsonify({
            "success": True,
            "message": f"Production model updated to: {model_name}",
            "model_id": model_id,
            "note": "Restart Rizzo containers to apply changes"
        })

    except Exception as e:
        logger.error(f"GO LIVE error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/copy-to-baseline', methods=['POST'])
def api_copy_to_baseline():
    """Copy winning variant config to .env.baseline for Botone."""
    import logging
    import re
    logger = logging.getLogger("arena.dashboard")

    data = request.get_json() or {}
    model_id = data.get('model_id')
    variant_id = data.get('variant_id')

    if not model_id or not variant_id:
        return jsonify({"success": False, "error": "Missing model_id or variant_id"})

    try:
        # Load variant config from variants.json
        variants_path = os.path.join(os.path.dirname(__file__), "variants.json")
        with open(variants_path, 'r') as f:
            variants_data = json.load(f)

        # Find the variant
        variant_config = None
        for v in variants_data.get("variants", []):
            if v.get("id") == variant_id:
                variant_config = v
                break

        if not variant_config:
            return jsonify({"success": False, "error": f"Variant {variant_id} not found"})

        # Get trading params
        params = variant_config.get("trading_params", {})
        prompt_style = variant_config.get("prompt_style", "moderate")

        # Build .env.baseline content
        baseline_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.baseline")

        # Read existing or create new
        if os.path.exists(baseline_path):
            with open(baseline_path, 'r') as f:
                env_content = f.read()
        else:
            env_content = "# Botone Baseline Configuration\n# Auto-generated from Arena\n\n"

        # Parameters to update
        updates = {
            "OPENROUTER_MODEL": model_id,
            "TRADING_STYLE": prompt_style.lower(),
            "LEVERAGE": str(params.get("leverage", 5)),
            "STOP_LOSS_PCT": str(params.get("stop_loss_pct", 4.0)),
            "TAKE_PROFIT_PCT": str(params.get("take_profit_pct", 8.0)),
            "TRAILING_ENABLED": str(params.get("trailing_enabled", True)).lower(),
            "TRAILING_STEPS": params.get("trailing_steps", "3.0:0.0,6.0:2.5,9.0:5.0"),
            "SMART_SL_ENABLED": str(params.get("smart_sl_enabled", False)).lower(),
            "SMART_SL_EXTENSION_PCT": str(params.get("smart_sl_extension_pct", 1.5)),
            "SMART_SL_MAX_EXTENSIONS": str(params.get("smart_sl_max_extensions", 2)),
            "POSITION_SIZE_USD": str(params.get("position_size_usd", 25)),
            "SCORE_THRESHOLD_OPEN": str(params.get("score_threshold_open", 0)),
            "DOUBLE_CHECK_AI_ENABLED": str(params.get("double_check_ai_enabled", False)).lower(),
            "ARENA_SOURCE_VARIANT": variant_id,
            "ARENA_SOURCE_MODEL": model_id,
        }

        # Update or add each parameter
        for key, value in updates.items():
            pattern = rf'^{key}=.*$'
            if re.search(pattern, env_content, re.MULTILINE):
                env_content = re.sub(pattern, f'{key}={value}', env_content, flags=re.MULTILINE)
            else:
                env_content += f'{key}={value}\n'

        # Write updated .env.baseline
        with open(baseline_path, 'w') as f:
            f.write(env_content)

        logger.info(f"COPY TO BASELINE: {model_id} from {variant_id}")

        return jsonify({
            "success": True,
            "message": f"Config copiata in .env.baseline",
            "params_copied": len(updates),
            "variant_id": variant_id,
            "model_id": model_id
        })

    except Exception as e:
        logger.error(f"Copy to baseline error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/botone/start', methods=['POST'])
def api_botone_start():
    """Start Botone Baseline containers."""
    import logging
    import subprocess
    logger = logging.getLogger("arena.dashboard")

    try:
        # Stop existing containers (ignore errors if not running)
        subprocess.run(["docker", "stop", "botone_baseline_slow", "botone_baseline_fast"],
                      capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "botone_baseline_slow", "botone_baseline_fast"],
                      capture_output=True, timeout=10)

        # Start SLOW container
        slow_result = subprocess.run([
            "docker", "run", "-d",
            "--name", "botone_baseline_slow",
            "--env-file", "/home/user/trading-bots/rizzo-trading-agent/.env.baseline",
            "-e", "PYTHONUNBUFFERED=1",
            "--network", "unified-memory-stack_memory-net",
            "--restart", "unless-stopped",
            "--entrypoint", "python",
            "botone-baseline",
            "sentinel.py", "--mode", "slow", "--loop"
        ], capture_output=True, text=True, timeout=60)

        if slow_result.returncode != 0:
            return jsonify({"success": False, "error": f"SLOW start failed: {slow_result.stderr}"})

        # Start FAST container
        fast_result = subprocess.run([
            "docker", "run", "-d",
            "--name", "botone_baseline_fast",
            "--env-file", "/home/user/trading-bots/rizzo-trading-agent/.env.baseline",
            "-e", "PYTHONUNBUFFERED=1",
            "--network", "unified-memory-stack_memory-net",
            "--restart", "unless-stopped",
            "--entrypoint", "python",
            "botone-baseline",
            "sentinel.py", "--mode", "fast", "--loop"
        ], capture_output=True, text=True, timeout=60)

        if fast_result.returncode != 0:
            return jsonify({"success": False, "error": f"FAST start failed: {fast_result.stderr}"})

        logger.info("BOTONE START: Both containers started successfully")

        return jsonify({
            "success": True,
            "message": "Botone containers avviati: slow + fast"
        })

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout starting containers"})
    except Exception as e:
        logger.error(f"Botone start error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/botone/stop', methods=['POST'])
def api_botone_stop():
    """Stop Botone Baseline containers."""
    import logging
    import subprocess
    logger = logging.getLogger("arena.dashboard")

    try:
        # Stop containers
        stop_result = subprocess.run(
            ["docker", "stop", "botone_baseline_slow", "botone_baseline_fast"],
            capture_output=True, text=True, timeout=30
        )

        # Remove containers
        subprocess.run(
            ["docker", "rm", "botone_baseline_slow", "botone_baseline_fast"],
            capture_output=True, timeout=10
        )

        logger.info("BOTONE STOP: Containers stopped")

        return jsonify({
            "success": True,
            "message": "Botone containers fermati"
        })

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout stopping containers"})
    except Exception as e:
        logger.error(f"Botone stop error: {e}")
        return jsonify({"success": False, "error": str(e)})


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

        # Check if it's a single-model variant (can change model)
        is_single_model = len(v.ai_models) == 1 and v.id != "V2_MULTI_AI"
        current_model = v.ai_models[0] if v.ai_models else None

        variants.append({
            "id": v.id,
            "name": v.name,
            "mode": mode_short,
            "ai_count": len(v.ai_models),
            "trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "pnl": metrics["total_pnl_usd"],
            "enabled": v.enabled,
            "is_single_model": is_single_model,
            "current_model": current_model,
            "current_model_name": current_model.split("/")[-1] if current_model else None,
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
                    # Get trade stats for this model
                    trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                    total_trades = len(trades)
                    winning_trades = len([t for t in trades if t.pnl_usd and t.pnl_usd > 0])
                    losing_trades = total_trades - winning_trades
                    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

                    models.append({
                        "id": sv_db.id,
                        "ai_model": sv_db.ai_model,
                        "ai_model_name": sv_db.ai_model_name,
                        "enabled": sv_db.enabled,
                        "api_calls": sv_db.api_calls,
                        "api_errors": sv_db.api_errors,
                        "total_trades": total_trades,
                        "winning_trades": winning_trades,
                        "losing_trades": losing_trades,
                        "win_rate": win_rate,
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
                        "profit_factor": r.profit_factor if r.profit_factor != float('inf') else 999.99,
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
                        "details": r.details if hasattr(r, 'details') and r.details else None,
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

    # Get all snapshots for the last 24 hours
    all_snapshots = db.get_all_equity_snapshots(hours=24)
    variants = load_variants(db)

    # FIRST PASS: Collect all unique timestamps globally and build per-variant equity maps
    global_timestamps = set()
    variant_data = {}  # variant_id -> {timestamp: equity}

    for v in variants:
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

                global_timestamps.add(ts_bucket)

                if ts_bucket not in variant_equity:
                    variant_equity[ts_bucket] = {"total_pnl": 0.0, "count": 0}
                pnl = snap["total_equity"] - STARTING_CAPITAL
                variant_equity[ts_bucket]["total_pnl"] += pnl
                variant_equity[ts_bucket]["count"] += 1

        # Convert to final equity values
        equity_map = {}
        for ts, data in variant_equity.items():
            if data["count"] > 0:
                avg_pnl = data["total_pnl"] / data["count"]
                equity_map[ts] = round(STARTING_CAPITAL + avg_pnl, 2)

        variant_data[v.id] = {
            "name": v.name,
            "equity_map": equity_map
        }

    # Sort global timestamps chronologically
    sorted_global_ts = sorted(global_timestamps)

    # Build labels from sorted global timestamps
    labels = []
    for ts in sorted_global_ts:
        try:
            dt = datetime.fromisoformat(ts)
            labels.append(dt.strftime("%H:%M"))
        except Exception:
            labels.append("")

    # SECOND PASS: Build datasets using global timestamps
    for i, v in enumerate(variants):
        vdata = variant_data.get(v.id, {})
        equity_map = vdata.get("equity_map", {})

        if equity_map:
            # Build equity curve aligned to global timestamps
            equity = []
            last_equity = STARTING_CAPITAL

            for ts in sorted_global_ts:
                if ts in equity_map:
                    last_equity = equity_map[ts]
                equity.append(last_equity)
        else:
            # Fallback to trade-based if no snapshots
            trades = db.get_trades_for_variant(v.id, limit=1000)
            trades.sort(key=lambda t: t.exit_time or datetime.min)

            equity = []
            cumulative = STARTING_CAPITAL

            # Fill with starting capital up to global length
            if sorted_global_ts:
                for _ in sorted_global_ts:
                    equity.append(STARTING_CAPITAL)
            else:
                equity = [STARTING_CAPITAL]

            # Apply trade P&L (simplified)
            for t in trades:
                cumulative += t.pnl_usd
            if equity:
                equity[-1] = cumulative  # Last point shows current state

        color = colors[i % len(colors)]
        datasets.append({
            "label": v.name[:15],
            "data": equity,
            "borderColor": color,
            "backgroundColor": "transparent",
            "tension": 0.4,
            "pointRadius": 0,
        })

    # Add "Start" label if no data
    if not labels:
        labels = ["Start"]
        # Ensure each dataset has at least one point
        for ds in datasets:
            if not ds["data"]:
                ds["data"] = [STARTING_CAPITAL]

    return {"labels": labels, "datasets": datasets}


# ==================== V6 Data Functions ====================

def get_v6_leaderboard() -> List[Dict[str, Any]]:
    """Get combined AI model leaderboard for all V6 variants."""
    # Aggregate trades by AI model across all V6 variants
    model_stats = {}  # model_id -> {trades, wins, pnl, api_calls, api_errors}

    for v in load_variants(db):
        if v.id.startswith("V6_"):
            for sv in v.sub_variants:
                trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                model_name = sv.ai_model_name

                if model_name not in model_stats:
                    model_stats[model_name] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "api_calls": 0, "api_errors": 0}

                # Get API stats from sub_variant
                sv_db = db.get_sub_variant(sv.id)
                if sv_db:
                    model_stats[model_name]["api_calls"] += sv_db.api_calls or 0
                    model_stats[model_name]["api_errors"] += sv_db.api_errors or 0

                for t in trades:
                    model_stats[model_name]["trades"] += 1
                    model_stats[model_name]["pnl"] += t.pnl_usd
                    if t.pnl_usd > 0:
                        model_stats[model_name]["wins"] += 1
                    else:
                        model_stats[model_name]["losses"] += 1

    # Convert to leaderboard format
    leaderboard = []
    for model, stats in model_stats.items():
        win_rate = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
        leaderboard.append({
            "ai_model": model,
            "total_trades": stats["trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": win_rate,
            "total_pnl_usd": stats["pnl"],
            "api_calls": stats["api_calls"],
            "api_errors": stats["api_errors"],
        })

    # Sort by P&L
    leaderboard.sort(key=lambda x: x["total_pnl_usd"], reverse=True)

    # Add ranks
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    return leaderboard


def get_v6_model_controls() -> List[Dict[str, Any]]:
    """Get model controls organized by V6 variant family."""
    controls = []

    # Define variant families
    families = {
        "FAST": {"name": "V6 Fast (5min)", "description": "High frequency trading", "variants": ["V6_FAST_PRUDENT", "V6_FAST_MODERATE", "V6_FAST_AGGRESSIVE"]},
        "MEDIUM": {"name": "V6 Medium (15min)", "description": "Balanced approach", "variants": ["V6_MEDIUM_PRUDENT", "V6_MEDIUM_MODERATE", "V6_MEDIUM_AGGRESSIVE"]},
        "MACRO": {"name": "V6 Macro (1h)", "description": "Trend following", "variants": ["V6_MACRO_TREND"]},
    }

    for family_key, family_info in families.items():
        # Aggregate model stats across all variants in this family
        model_data = {}

        for v in load_variants(db):
            if v.id in family_info["variants"]:
                for model_id in v.ai_models:
                    model_name = model_id.split("/")[-1]

                    if model_id not in model_data:
                        model_data[model_id] = {
                            "id": model_id,
                            "name": model_name,
                            "enabled": True,  # Default, will be updated from DB
                            "trades": 0,
                            "wins": 0,
                        }

                    # Get stats and enabled state from sub_variants (from DB)
                    for sv in v.sub_variants:
                        if sv.ai_model == model_id:
                            # Read enabled state from database (sv comes from DB)
                            model_data[model_id]["enabled"] = sv.enabled
                            trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                            model_data[model_id]["trades"] += len(trades)
                            model_data[model_id]["wins"] += sum(1 for t in trades if t.pnl_usd > 0)

        # Calculate win rates
        models = []
        for model_id, data in model_data.items():
            win_rate = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            models.append({
                "id": data["id"],
                "name": data["name"],
                "enabled": data["enabled"],
                "trades": data["trades"],
                "win_rate": win_rate,
            })

        # Use first variant ID for the toggle control
        variant_id = family_info["variants"][0] if family_info["variants"] else ""

        controls.append({
            "family": family_key,
            "name": family_info["name"],
            "description": family_info["description"],
            "variant_id": variant_id,
            "models": models,
        })

    return controls


def get_best_v6_model() -> Optional[Dict[str, Any]]:
    """Get the best performing AI model from V6 variants."""
    leaderboard = get_v6_leaderboard()

    if not leaderboard:
        return None

    best = leaderboard[0]

    # Find the model ID and best variant for this model
    model_id = None
    best_variant_id = None
    best_prompt_style = None

    # Load variants.json to get prompt_style
    variants_path = os.path.join(os.path.dirname(__file__), "variants.json")
    variants_json = {}
    try:
        with open(variants_path, 'r') as f:
            variants_json = json.load(f)
    except:
        pass

    # Find model_id and best performing variant for this model
    best_variant_pnl = float('-inf')

    for v in load_variants(db):
        if v.id.startswith("V6_"):
            for m in v.ai_models:
                if m.split("/")[-1] == best["ai_model"]:
                    if model_id is None:
                        model_id = m

                    # Check PnL for this model in this specific variant
                    for sv in v.sub_variants:
                        if sv.ai_model == m:
                            trades = db.get_trades_for_sub_variant(sv.id, limit=1000)
                            variant_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd)
                            if variant_pnl > best_variant_pnl:
                                best_variant_pnl = variant_pnl
                                best_variant_id = v.id
                                # Get prompt_style from JSON
                                for vj in variants_json.get("variants", []):
                                    if vj.get("id") == v.id:
                                        best_prompt_style = vj.get("prompt_style", "moderate")
                                        break
                    break

    # Fallback: if no variant found, use V6_FAST_MODERATE as default
    if best_variant_id is None:
        best_variant_id = "V6_FAST_MODERATE"
        best_prompt_style = "moderate"

    return {
        "id": model_id or best["ai_model"],
        "name": best["ai_model"],
        "trades": best["total_trades"],
        "win_rate": best["win_rate"],
        "pnl": best["total_pnl_usd"],
        "variant_id": best_variant_id,
        "prompt_style": best_prompt_style or "moderate",
    }


def get_v6_chart_data(family: str) -> Dict[str, Any]:
    """Get chart data for a specific V6 strategy family."""
    colors = ['#00d4ff', '#00ff88', '#ff4444', '#ffaa00', '#aa44ff', '#ff44aa', '#44ffff']
    datasets = []
    labels = []

    # Map family to variant patterns
    family_patterns = {
        "FAST": ["V6_FAST_PRUDENT", "V6_FAST_MODERATE", "V6_FAST_AGGRESSIVE"],
        "MEDIUM": ["V6_MEDIUM_PRUDENT", "V6_MEDIUM_MODERATE", "V6_MEDIUM_AGGRESSIVE"],
        "MACRO": ["V6_MACRO_TREND"],
    }

    variant_ids = family_patterns.get(family, [])

    # Collect data for each variant in this family
    color_idx = 0
    for v in load_variants(db):
        if v.id in variant_ids:
            # Get trades for this variant
            trades = db.get_trades_for_variant(v.id, limit=1000)
            trades.sort(key=lambda t: t.exit_time or datetime.min)

            # Build equity curve
            equity = [STARTING_CAPITAL]
            cumulative = STARTING_CAPITAL

            for t in trades:
                cumulative += t.pnl_usd
                equity.append(cumulative)
                if t.exit_time and len(labels) < len(equity):
                    labels.append(t.exit_time.strftime("%H:%M"))

            # Ensure labels match
            while len(labels) < len(equity):
                labels.append("")

            # Get style name (Prudent, Moderate, Aggressive)
            style_name = v.name.split()[-1].replace("(", "").replace(")", "")
            if "Prudente" in v.name:
                style_name = "Prudent"
            elif "Moderato" in v.name:
                style_name = "Moderate"
            elif "Aggressivo" in v.name:
                style_name = "Aggressive"
            elif "Macro" in v.name:
                style_name = "Macro Trend"

            color = colors[color_idx % len(colors)]
            datasets.append({
                "label": style_name,
                "data": equity,
                "borderColor": color,
                "backgroundColor": "transparent",
                "tension": 0.4,
                "pointRadius": 0,
            })
            color_idx += 1

    if not labels:
        labels = ["Start"]

    # Ensure all datasets have same length
    max_len = max(len(ds["data"]) for ds in datasets) if datasets else 1
    for ds in datasets:
        while len(ds["data"]) < max_len:
            ds["data"].append(ds["data"][-1] if ds["data"] else STARTING_CAPITAL)

    while len(labels) < max_len:
        labels.append("")

    return {"labels": labels, "datasets": datasets}


def is_simulation_paused() -> bool:
    """Check if simulation is paused."""
    return simulation_paused


def run_dashboard(host: str = "0.0.0.0", port: int = 5055, debug: bool = False):
    """Run the dashboard server."""
    init_dashboard()
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_dashboard()
