# ARENA - Trading Simulation System

## Technical Documentation v2.0

**Created:** 2025-12-13
**Last Updated:** 2025-12-13
**Status:** ✅ DEPLOYED AND RUNNING

---

## IMPORTANT: AI Development Context

> **Se sei un AI che deve modificare questo progetto, leggi questa sezione!**

### Quick Reference for AI Developers

```
ARENA è un sistema di SIMULAZIONE che:
- NON esegue trade reali
- Usa prezzi reali da HyperLiquid
- Testa multiple configurazioni (varianti) in parallelo
- Ogni variante può avere più modelli AI (sub-varianti)
- Dashboard web su porta 5055
- Database SQLite in data/arena.db
```

### File Principali da Modificare

| Obiettivo | File |
|-----------|------|
| Aggiungere/modificare varianti | `arena/variants.json` |
| Logica simulazione | `arena/simulator.py` |
| Chiamate AI | `arena/ai_manager.py` |
| Smart SL | `arena/smart_sl.py` |
| Dashboard web | `arena/dashboard.py` |
| Metriche/statistiche | `arena/metrics.py` |
| Database | `arena/db.py` |
| Modelli dati | `arena/models.py` |

### Dipendenze Docker

```dockerfile
# Dockerfile.arena richiede:
flask, requests, python-dotenv, hyperliquid-python-sdk, pandas, numpy, ta
```

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current Configuration](#2-current-configuration)
3. [Architecture](#3-architecture)
4. [File Structure](#4-file-structure)
5. [Variants System](#5-variants-system)
6. [AI Models Configuration](#6-ai-models-configuration)
7. [Database Schema](#7-database-schema)
8. [Dashboard](#8-dashboard)
9. [Docker Deployment](#9-docker-deployment)
10. [Environment Variables](#10-environment-variables)
11. [API Reference](#11-api-reference)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Overview

### What is Arena?

Arena è un **sistema di simulazione** che gira in parallelo al bot di trading reale. Permette di testare multiple configurazioni (varianti) simultaneamente senza rischiare soldi veri.

### Key Features

- **Zero Risk**: Simulazione pura, nessun trade reale
- **Real Data**: Usa prezzi live da HyperLiquid
- **Multi-AI**: Confronta diversi modelli AI sulla stessa strategia
- **Web Dashboard**: Visualizza equity curve, leaderboard, posizioni
- **Auto-tracking**: Database SQLite con tutti i trade simulati

### System Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ARENA FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   HyperLiquid API ──► Prezzi BTC/ETH/SOL                                │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    ARENA SIMULATOR                               │   │
│   │                                                                  │   │
│   │   Per ogni Variante:                                             │   │
│   │     Per ogni Sub-Variante (AI model):                            │   │
│   │       - Calcola score con indicatori                             │   │
│   │       - Se score > threshold → chiedi conferma AI                │   │
│   │       - Se AI approva → apri posizione simulata                  │   │
│   │       - Monitora SL/TP/Trailing                                  │   │
│   │       - Salva trade in database                                  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│         │                                                                │
│         ▼                                                                │
│   SQLite DB (data/arena.db) ──► Dashboard Web (:5055)                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Current Configuration

### Active AI Models (Competitors)

| Modello | Provider | Costo | Note |
|---------|----------|-------|------|
| `deepseek/deepseek-chat` | DeepSeek | $$ | **PRINCIPALE** - V3 |
| `x-ai/grok-code-fast-1` | xAI | $$ | Grok ottimizzato per codice |
| `anthropic/claude-haiku-4.5` | Anthropic | $ | Claude veloce |
| `openai/gpt-oss-120b` | OpenAI | $$$ | GPT grande |
| `qwen/qwen3-max` | Alibaba | $$ | Qwen top |
| `qwen/qwen3-235b-a22b:free` | Alibaba | FREE | Qwen gratuito |

### Active Variants

| ID | Nome | Modalità | AI Models | Descrizione |
|----|------|----------|-----------|-------------|
| V1_BASELINE | Baseline DeepSeek V3 | SCORE_TRIGGERED | 1 | Config produzione riferimento |
| V2_MULTI_AI | Battle: 6 AI a Confronto | SCORE_TRIGGERED | 6 | Tutti i modelli competono |
| V3_SMART_EXIT | Smart Exit con DeepSeek | SCORE_TRIGGERED | 1 | SL controllato da AI |
| V4_INDICATOR_TEST | Indicatori Ottimizzati | SCORE_TRIGGERED | 1 | Pesi/periodi diversi |
| V5_AI_FREE | AI Libero (ogni 15min) | AI_INDEPENDENT | 2 | AI decide senza filtri |

### Total Sub-Variants: 11

```
V1: 1 sub-variant (DeepSeek)
V2: 6 sub-variants (DeepSeek, Grok, Claude, GPT, Qwen-Max, Qwen-Free)
V3: 1 sub-variant (DeepSeek)
V4: 1 sub-variant (DeepSeek)
V5: 2 sub-variants (DeepSeek, Qwen-Free)
```

---

## 3. Architecture

### Components Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ARENA ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  External Services                                                       │
│  ─────────────────                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ HyperLiquid  │  │  OpenRouter  │  │   Browser    │                   │
│  │   (prices)   │  │  (AI API)    │  │  (dashboard) │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
│         │                 │                 │                            │
│         ▼                 ▼                 ▼                            │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      ARENA CONTAINER                             │    │
│  │                                                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│  │  │ main.py     │  │ simulator   │  │ dashboard   │              │    │
│  │  │ (entry)     │──│ .py         │  │ .py (Flask) │◄─── :5055    │    │
│  │  └─────────────┘  └──────┬──────┘  └──────┬──────┘              │    │
│  │                          │                │                      │    │
│  │                          ▼                ▼                      │    │
│  │                   ┌─────────────────────────────┐                │    │
│  │                   │        db.py                │                │    │
│  │                   │   (SQLite operations)       │                │    │
│  │                   └──────────┬──────────────────┘                │    │
│  │                              │                                   │    │
│  │                              ▼                                   │    │
│  │                   ┌─────────────────────────────┐                │    │
│  │                   │    data/arena.db            │                │    │
│  │                   │  - arena_variants           │                │    │
│  │                   │  - arena_sub_variants       │                │    │
│  │                   │  - arena_positions          │                │    │
│  │                   │  - arena_trades             │                │    │
│  │                   └─────────────────────────────┘                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Loop Structure

```python
# Slow Loop (ogni 60 secondi) - ENTRY CHECK
for variant in enabled_variants:
    for sub_variant in variant.sub_variants:
        if variant.mode == "SCORE_TRIGGERED":
            score = calculate_score(market_data)
            if score > threshold:
                ai_approved = call_ai(sub_variant.ai_model, market_data)
                if ai_approved:
                    open_simulated_position()
        elif variant.mode == "AI_INDEPENDENT":
            if time_since_last_check >= 15_minutes:
                decision = ask_ai_freely(sub_variant.ai_model, market_data)
                execute_decision(decision)

# Fast Loop (ogni 5 secondi) - POSITION MANAGEMENT
for position in open_positions:
    update_pnl(position, current_price)
    check_take_profit(position)
    check_stop_loss(position)
    apply_trailing_stop(position)
    if smart_sl_enabled:
        check_smart_sl_extension(position)
```

---

## 4. File Structure

```
rizzo-trading-agent/
│
├── arena/                          # ═══ ARENA PACKAGE ═══
│   │
│   ├── __init__.py                 # Package exports
│   │
│   ├── models.py                   # Data classes
│   │   ├── Variant                 # Configurazione variante
│   │   ├── SubVariant              # Sub-variante per AI model
│   │   ├── SimulatedPosition       # Posizione aperta simulata
│   │   ├── SimulatedTrade          # Trade chiuso simulato
│   │   ├── TradingParams           # Parametri trading
│   │   ├── IndicatorConfig         # Config indicatori
│   │   └── Enums (OperationMode, TradeDirection, TradeStatus)
│   │
│   ├── db.py                       # Database operations (SQLite)
│   │   ├── ArenaDB class
│   │   ├── _init_db()              # Auto-create tables
│   │   ├── save/get variants
│   │   ├── save/get positions
│   │   ├── save/get trades
│   │   └── get_leaderboard()
│   │
│   ├── config_loader.py            # Load/save variants
│   │   ├── load_variants()         # From DB or create defaults
│   │   ├── load_variants_from_file() # From variants.json
│   │   └── get_default_variants()  # 5 default variants
│   │
│   ├── simulator.py                # ═══ CORE ENGINE ═══
│   │   ├── ArenaSimulator class
│   │   ├── start() / stop()        # Control loop
│   │   ├── _slow_loop()            # Entry evaluation (60s)
│   │   ├── _fast_loop()            # Position monitor (5s)
│   │   ├── _process_variant()      # Per-variant logic
│   │   ├── _open_position()        # Create simulated position
│   │   ├── _close_position()       # Close and record trade
│   │   ├── _calculate_score()      # Score with indicator weights
│   │   ├── _get_prices()           # From HyperLiquid
│   │   └── _get_market_data()      # Full indicators
│   │
│   ├── ai_manager.py               # AI API calls
│   │   ├── AIManager class
│   │   ├── validate_trade()        # DOUBLE_CHECK style
│   │   ├── get_independent_decision() # AI_FREE mode
│   │   ├── check_smart_sl_extension() # Smart SL
│   │   ├── _call_ai()              # OpenRouter API call
│   │   └── _rate_limit()           # Per-model rate limiting
│   │
│   ├── smart_sl.py                 # Smart Stop Loss
│   │   ├── SmartSLManager class
│   │   ├── check_and_extend_sl()   # Main logic
│   │   ├── _is_near_sl()           # Proximity check
│   │   └── TrailingSLManager       # Trailing stop logic
│   │
│   ├── metrics.py                  # Performance calculations
│   │   ├── calculate_metrics()     # Win rate, Sharpe, etc.
│   │   ├── calculate_sharpe_ratio()
│   │   ├── calculate_max_drawdown()
│   │   ├── get_leaderboard()
│   │   └── compare_variants()
│   │
│   ├── reporter.py                 # Report generation
│   │   ├── ArenaReporter class
│   │   ├── print_leaderboard()
│   │   ├── print_full_report()
│   │   └── generate_json_report()
│   │
│   ├── dashboard.py                # Flask web dashboard
│   │   ├── Flask app
│   │   ├── / route (main page)
│   │   ├── /api/stats
│   │   ├── /api/equity
│   │   ├── /api/leaderboard
│   │   ├── get_equity_chart_data() # For Chart.js
│   │   └── DASHBOARD_HTML template
│   │
│   ├── main.py                     # Entry point for Docker
│   │   └── Starts simulator + dashboard together
│   │
│   ├── cli.py                      # Command line interface
│   │   ├── arena init
│   │   ├── arena status
│   │   ├── arena report
│   │   ├── arena leaderboard
│   │   └── arena variants list/enable/disable
│   │
│   ├── variants.json               # ═══ VARIANT CONFIG ═══
│   │   └── 5 varianti con modelli AI configurati
│   │
│   └── .env.arena.example          # Environment template
│
├── Dockerfile.arena                # Docker image for Arena
├── docker-compose.arena.yml        # Docker Compose config
├── run_arena.py                    # Standalone runner script
│
├── data/                           # Data directory (gitignored)
│   └── arena.db                    # SQLite database
│
└── ARENA_TECHNICAL_DOC.md          # This document
```

---

## 5. Variants System

### Variant Structure (variants.json)

```json
{
  "id": "V2_MULTI_AI",
  "name": "Battle: 6 AI a Confronto",
  "description": "DeepSeek V3 vs Grok vs Claude vs GPT vs Qwen",
  "enabled": true,
  "operation_mode": "SCORE_TRIGGERED",  // or "AI_INDEPENDENT"

  "ai_models": [
    "deepseek/deepseek-chat",
    "x-ai/grok-code-fast-1",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-oss-120b",
    "qwen/qwen3-max",
    "qwen/qwen3-235b-a22b:free"
  ],

  "trading_params": {
    "position_size_usd": 50.0,
    "leverage": 3,
    "stop_loss_pct": 3.0,
    "take_profit_pct": 6.0,
    "trailing_enabled": true,
    "trailing_steps": "2.5:0.0,5.0:2.0,7.5:4.0",
    "score_threshold_open": 15.0,
    "double_check_ai_enabled": true,
    "trading_style": "moderate",
    "smart_sl_enabled": false,
    "smart_sl_extension_pct": 1.0,
    "smart_sl_max_extensions": 2
  },

  "indicator_config": {
    "ema_short_period": 9,
    "ema_medium_period": 21,
    "weight_macd": 25.0,
    "weight_rsi": 15.0,
    "macd_threshold_strong": 0.20,
    "adx_min_trend": 20.0
  },

  "pattern_detection_enabled": true,
  "symbols": ["BTC", "ETH", "SOL"],

  // Solo per AI_INDEPENDENT mode:
  "ai_check_interval_minutes": 15,
  "ai_independent_timeframe": "4h"
}
```

### Operation Modes

| Mode | Description | When AI is Called |
|------|-------------|-------------------|
| `SCORE_TRIGGERED` | Standard - score must exceed threshold | Solo se score > threshold |
| `AI_INDEPENDENT` | AI decides freely every N minutes | Ogni 15 minuti, sempre |

### Trading Parameters Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `position_size_usd` | float | 50.0 | Size posizione in USD |
| `leverage` | int | 3 | Leva |
| `stop_loss_pct` | float | 3.0 | Stop loss % |
| `take_profit_pct` | float | 6.0 | Take profit % |
| `trailing_enabled` | bool | true | Trailing stop attivo |
| `trailing_steps` | string | "2.5:0.0,..." | Steps formato "PNL:SL_LEVEL" |
| `score_threshold_open` | float | 15.0 | Score minimo per entry |
| `double_check_ai_enabled` | bool | true | Conferma AI prima di entry |
| `trading_style` | string | "moderate" | aggressive/moderate/conservative |
| `smart_sl_enabled` | bool | false | AI può estendere SL |
| `smart_sl_extension_pct` | float | 1.0 | Estensione SL % |
| `smart_sl_max_extensions` | int | 2 | Max estensioni |

### Indicator Config Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ema_short_period` | int | 9 | EMA veloce |
| `ema_medium_period` | int | 21 | EMA media |
| `ema_long_period` | int | 50 | EMA lenta |
| `rsi_period` | int | 14 | Periodo RSI |
| `macd_fast` | int | 12 | MACD fast |
| `macd_slow` | int | 26 | MACD slow |
| `macd_signal` | int | 9 | MACD signal |
| `weight_macd` | float | 25.0 | Peso MACD nel score |
| `weight_rsi` | float | 15.0 | Peso RSI |
| `weight_ema_alignment` | float | 20.0 | Peso allineamento EMA |
| `weight_adx_trend` | float | 15.0 | Peso ADX |
| `weight_double_bottom` | float | 12.0 | Peso pattern W |
| `weight_double_top` | float | 12.0 | Peso pattern M |

---

## 6. AI Models Configuration

### OpenRouter Setup

Arena usa **OpenRouter** come gateway per tutti i modelli AI. Una sola API key per tutti.

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
```

### Available Models (OpenRouter)

```python
# Modelli configurati in variants.json
MODELS = [
    "deepseek/deepseek-chat",      # DeepSeek V3 - veloce, economico
    "x-ai/grok-code-fast-1",       # Grok - xAI
    "anthropic/claude-haiku-4.5",  # Claude Haiku - veloce
    "openai/gpt-oss-120b",         # GPT grande
    "qwen/qwen3-max",              # Qwen top tier
    "qwen/qwen3-235b-a22b:free",   # Qwen gratuito
]
```

### AI Prompts

**SCORE_TRIGGERED validation prompt:**
```
ARENA SIMULATION - Trade Validation
Style: MODERATE

PROPOSED TRADE:
- Symbol: BTC
- Direction: LONG
- Score: 18.5

MARKET DATA:
- Price: $97,500
- MACD: 0.25
- RSI: 55
- ADX: 28
- EMA Trend: bullish

Respond with JSON:
{"operation": "open" or "hold", "direction": "LONG" or "SHORT",
 "confidence": 0.0-1.0, "reason": "brief reason"}
```

**AI_INDEPENDENT prompt:**
```
ARENA SIMULATION - AI Free Decision
Timeframe: 4h

SYMBOL: BTC

MARKET DATA:
- Price: $97,500
- MACD: 0.25
- RSI: 55
- ADX: 28

You have FULL CONTROL. Decide:
{"action": "open/close/hold", "direction": "LONG/SHORT",
 "confidence": 0.0-1.0, "reason": "analysis"}
```

---

## 7. Database Schema

### Tables (SQLite - auto-created)

```sql
-- arena_variants: Configurazioni varianti
CREATE TABLE arena_variants (
    id TEXT PRIMARY KEY,              -- "V1_BASELINE"
    name TEXT NOT NULL,
    description TEXT,
    enabled INTEGER DEFAULT 1,
    operation_mode TEXT DEFAULT 'SCORE_TRIGGERED',
    trading_params TEXT,              -- JSON
    indicator_config TEXT,            -- JSON
    ai_models TEXT,                   -- JSON array
    pattern_detection_enabled INTEGER DEFAULT 1,
    symbols TEXT DEFAULT '["BTC","ETH","SOL"]',
    total_trades INTEGER DEFAULT 0,
    total_pnl_usd REAL DEFAULT 0.0,
    created_at TIMESTAMP
);

-- arena_sub_variants: Una per AI model per variant
CREATE TABLE arena_sub_variants (
    id TEXT PRIMARY KEY,              -- "V2_MULTI_AI_deepseek-chat"
    variant_id TEXT NOT NULL,
    ai_model TEXT NOT NULL,           -- "deepseek/deepseek-chat"
    ai_model_name TEXT,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_pnl_usd REAL DEFAULT 0.0,
    total_pnl_pct REAL DEFAULT 0.0,
    max_drawdown_pct REAL DEFAULT 0.0,
    sharpe_ratio REAL DEFAULT 0.0,
    last_trade_at TIMESTAMP
);

-- arena_positions: Posizioni aperte
CREATE TABLE arena_positions (
    id TEXT PRIMARY KEY,
    sub_variant_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,          -- "LONG" or "SHORT"
    entry_price REAL NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    position_size_usd REAL,
    leverage INTEGER,
    stop_loss_price REAL,
    take_profit_price REAL,
    current_sl_level REAL,
    smart_sl_extensions INTEGER DEFAULT 0,
    current_pnl_pct REAL,
    peak_pnl_pct REAL
);

-- arena_trades: Trade chiusi
CREATE TABLE arena_trades (
    id TEXT PRIMARY KEY,
    sub_variant_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL,
    exit_price REAL,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    exit_reason TEXT,                 -- "CLOSED_TP", "CLOSED_SL", etc.
    pnl_pct REAL,
    pnl_usd REAL,
    duration_minutes INTEGER,
    ai_model TEXT
);
```

---

## 8. Dashboard

### Access

```
http://YOUR-VPS-IP:5055
```

### Features

- **Stats Cards**: Equity, Return %, Trades, Win Rate, Posizioni aperte
- **Equity Chart**: Grafico equity curve con Chart.js
- **Leaderboard**: Classifica sub-varianti per P&L
- **Open Positions**: Tabella posizioni aperte
- **Variants Performance**: Confronto varianti

### Auto-refresh

La dashboard si aggiorna automaticamente ogni 30 secondi.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard HTML |
| `/api/stats` | GET | JSON statistiche |
| `/api/equity` | GET | JSON dati equity chart |
| `/api/leaderboard` | GET | JSON leaderboard |

---

## 9. Docker Deployment

### Quick Start

```bash
# Sul VPS
cd ~/trading-bots/rizzo-trading-agent

# Pull ultimo codice
git pull

# Build e avvia
docker build -t rizzo-arena -f Dockerfile.arena .

docker run -d \
  --name rizzo-arena \
  --restart unless-stopped \
  -p 5055:5055 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/arena/variants.json:/app/arena/variants.json:ro \
  -e ARENA_ENABLED=true \
  -e ARENA_STARTING_CAPITAL=100 \
  -e ARENA_DASHBOARD_PORT=5055 \
  -e OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY \
  rizzo-arena
```

### Commands Reference

```bash
# Vedere log
docker logs -f rizzo-arena

# Riavviare (dopo modifiche a variants.json)
docker restart rizzo-arena

# Fermare
docker stop rizzo-arena

# Rimuovere
docker rm -f rizzo-arena

# Rebuild completo
docker rm -f rizzo-arena && \
docker build -t rizzo-arena -f Dockerfile.arena . && \
docker run -d ... (come sopra)
```

### Dockerfile.arena

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    requests \
    python-dotenv \
    hyperliquid-python-sdk \
    pandas \
    numpy \
    ta

COPY . .

RUN mkdir -p /app/data

EXPOSE 5055

CMD ["python", "-m", "arena.main"]
```

---

## 10. Environment Variables

### Required

| Variable | Example | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | `sk-or-v1-xxx` | API key OpenRouter |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `ARENA_ENABLED` | `true` | Master switch |
| `ARENA_STARTING_CAPITAL` | `100` | Capitale iniziale simulato |
| `ARENA_DASHBOARD_ENABLED` | `true` | Abilita dashboard |
| `ARENA_DASHBOARD_PORT` | `5055` | Porta dashboard |
| `ARENA_LOOP_INTERVAL` | `60` | Slow loop (secondi) |
| `ARENA_FAST_LOOP_INTERVAL` | `5` | Fast loop (secondi) |
| `ARENA_LOG_LEVEL` | `INFO` | Log level |
| `ARENA_DISABLED_VARIANTS` | `` | Varianti da disabilitare (comma-separated) |

---

## 11. API Reference

### AIManager Methods

```python
# Validazione trade (SCORE_TRIGGERED mode)
ai_manager.validate_trade(
    variant: Variant,
    sub_variant: SubVariant,
    symbol: str,
    direction: TradeDirection,
    market_data: Dict,
    score_data: Dict
) -> Tuple[bool, Optional[TradeDirection], str, float]
# Returns: (approved, override_direction, reason, confidence)

# Decisione libera (AI_INDEPENDENT mode)
ai_manager.get_independent_decision(
    variant: Variant,
    sub_variant: SubVariant,
    symbol: str,
    market_data: Dict,
    has_position: bool,
    current_direction: Optional[TradeDirection]
) -> Tuple[str, Optional[TradeDirection], str, float]
# Returns: (action, direction, reason, confidence)
# action: "open", "close", "hold"

# Smart SL check
ai_manager.check_smart_sl_extension(
    variant: Variant,
    sub_variant: SubVariant,
    symbol: str,
    direction: TradeDirection,
    current_pnl_pct: float,
    market_data: Dict,
    extensions_used: int
) -> Tuple[bool, str, float]
# Returns: (should_extend, reason, confidence)
```

### ArenaDB Methods

```python
db = ArenaDB()

# Variants
db.save_variant(variant)
db.get_variant(variant_id) -> Optional[Variant]
db.get_all_variants(enabled_only=True) -> List[Variant]

# Sub-variants
db.save_sub_variant(sub_variant)
db.get_sub_variant(sub_variant_id) -> Optional[SubVariant]
db.update_sub_variant_stats(sub_variant_id, trade)

# Positions
db.save_position(position)
db.get_position(position_id) -> Optional[SimulatedPosition]
db.get_position_by_symbol(sub_variant_id, symbol) -> Optional[SimulatedPosition]
db.get_all_open_positions() -> List[SimulatedPosition]
db.delete_position(position_id)

# Trades
db.save_trade(trade)
db.get_trades_for_sub_variant(sub_variant_id, limit=100) -> List[SimulatedTrade]
db.get_recent_trades(hours=24, limit=100) -> List[SimulatedTrade]
db.get_trade_stats(...) -> Dict

# Leaderboard
db.get_leaderboard(limit=20) -> List[Dict]
```

---

## 12. Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `No module named 'ta'` | Missing dependency | Rebuild Docker con `ta` in pip install |
| `No module named 'pandas'` | Missing dependency | Rebuild Docker con `pandas numpy` |
| `Could not get market data` | Network/API error | Check HyperLiquid connectivity |
| `Port 5050 already allocated` | Port in use | Usa porta diversa (5055) |
| `database is locked` | Concurrent access | Riavvia container |

### Rebuild Container

```bash
docker rm -f rizzo-arena
docker build --no-cache -t rizzo-arena -f Dockerfile.arena .
docker run -d ... (come sopra)
```

### Check Logs

```bash
# Ultimi 100 log
docker logs --tail 100 rizzo-arena

# Follow in tempo reale
docker logs -f rizzo-arena
```

### Reset Database

```bash
# Rimuove tutti i dati Arena
rm data/arena.db
docker restart rizzo-arena
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-13 | 1.0 | Initial document |
| 2025-12-13 | 2.0 | Complete rewrite with deployment info, current config, AI dev context |

---

## Quick Reference Card

```
╔══════════════════════════════════════════════════════════════════╗
║                     ARENA QUICK REFERENCE                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  Dashboard:     http://YOUR-IP:5055                              ║
║  Database:      data/arena.db (SQLite)                           ║
║  Config:        arena/variants.json                              ║
║                                                                   ║
║  Start:         docker run -d --name rizzo-arena ...             ║
║  Stop:          docker stop rizzo-arena                          ║
║  Logs:          docker logs -f rizzo-arena                       ║
║  Restart:       docker restart rizzo-arena                       ║
║                                                                   ║
║  Modify AI models:    Edit arena/variants.json → restart         ║
║  Disable variant:     Set "enabled": false → restart             ║
║  Reset data:          rm data/arena.db → restart                 ║
║                                                                   ║
║  11 Sub-Variants competing:                                      ║
║  - V1: DeepSeek V3 (baseline)                                    ║
║  - V2: 6 AI models battle                                        ║
║  - V3: Smart SL with DeepSeek                                    ║
║  - V4: Optimized indicators                                      ║
║  - V5: AI Free mode (DeepSeek + Qwen)                           ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

*Document maintained by: Claude AI*
*Last updated: 2025-12-13*
