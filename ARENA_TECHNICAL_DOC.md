# ARENA - Trading Simulation System

## Technical Documentation v1.0

**Created:** 2025-12-13
**Last Updated:** 2025-12-13
**Status:** In Development

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Variants System](#3-variants-system)
4. [Sub-Variants (AI Models)](#4-sub-variants-ai-models)
5. [Parameters Reference](#5-parameters-reference)
6. [Indicator Configuration](#6-indicator-configuration)
7. [Pattern Detection](#7-pattern-detection)
8. [AI Independent Mode](#8-ai-independent-mode)
9. [Smart SL System](#9-smart-sl-system)
10. [Database Schema](#10-database-schema)
11. [File Structure](#11-file-structure)
12. [Configuration Examples](#12-configuration-examples)
13. [API & Models](#13-api--models)
14. [Metrics & Leaderboard](#14-metrics--leaderboard)
15. [Deployment](#15-deployment)

---

## 1. Overview

### What is Arena?

Arena is a **simulation system** that runs in parallel with the real trading bot. It allows testing multiple configurations (variants) simultaneously without risking real money.

### Key Concepts

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ARENA CONCEPT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PRODUCTION (Real Money)              ARENA (Simulation)                   │
│   ───────────────────────              ──────────────────                   │
│                                                                             │
│   ┌─────────────────────┐              ┌─────────────────────┐              │
│   │   Current Bot       │              │   Variant 1 + AI A  │              │
│   │   (sentinel.py)     │              │   Variant 1 + AI B  │              │
│   │                     │              │   Variant 2 + AI A  │              │
│   │   Real trades       │              │   Variant 3 + AI A  │              │
│   │   Real P&L          │              │   ...               │              │
│   └─────────────────────┘              └─────────────────────┘              │
│            │                                      │                         │
│            │                                      ▼                         │
│            │                           ┌─────────────────────┐              │
│            │                           │   LEADERBOARD       │              │
│            │                           │   Compare all       │              │
│            │                           │   Find winners      │              │
│            │                           └─────────────────────┘              │
│            │                                      │                         │
│            │◄─────── PROMOTE WINNER ──────────────┘                         │
│                     (manual decision)                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Benefits

| Aspect | Benefit |
|--------|---------|
| **Zero Risk** | Simulation doesn't use real money |
| **Real Data** | Uses live prices, not historical backtest |
| **Fair Comparison** | All variants see the same data |
| **No Overfitting** | Tests on FUTURE data, not past |
| **You Decide** | Promotion to production requires your approval |

---

## 2. Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  HyperLiquid│     │  Indicators │     │  OpenRouter │                   │
│  │  (prices)   │     │  (MACD,RSI) │     │  (AI API)   │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                          │
│         └───────────────────┼───────────────────┘                          │
│                             │                                               │
│                             ▼                                               │
│              ┌──────────────────────────────┐                              │
│              │       ARENA SIMULATOR        │                              │
│              │  ┌────────────────────────┐  │                              │
│              │  │   Market Data Feed     │  │                              │
│              │  └───────────┬────────────┘  │                              │
│              │              │               │                              │
│              │              ▼               │                              │
│              │  ┌────────────────────────┐  │                              │
│              │  │   For each SubVariant: │  │                              │
│              │  │   - Evaluate entry     │  │                              │
│              │  │   - Manage positions   │  │                              │
│              │  │   - Calculate P&L      │  │                              │
│              │  │   - Apply trailing     │  │                              │
│              │  │   - Call AI if needed  │  │                              │
│              │  └───────────┬────────────┘  │                              │
│              │              │               │                              │
│              │              ▼               │                              │
│              │  ┌────────────────────────┐  │                              │
│              │  │   Save to Database     │  │                              │
│              │  └────────────────────────┘  │                              │
│              └──────────────────────────────┘                              │
│                             │                                               │
│                             ▼                                               │
│              ┌──────────────────────────────┐                              │
│              │         PostgreSQL           │                              │
│              │  - arena_variants            │                              │
│              │  - arena_sub_variants        │                              │
│              │  - simulated_positions       │                              │
│              │  - simulated_trades          │                              │
│              └──────────────────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Every 30 seconds (SCORE_TRIGGERED mode):
1. Fetch prices for BTC, ETH, SOL
2. Calculate indicators (MACD, RSI, EMA, etc.)
3. Calculate score using configured weights
4. For each sub-variant:
   a. Has open position? → Manage (trailing, SL check, close if hit)
   b. No position? → Evaluate entry based on variant's parameters
5. Save all changes to database
6. Every hour: generate leaderboard report

Every 15 minutes (AI_INDEPENDENT mode):
1. Fetch all market data
2. Pass everything to AI without score filtering
3. AI decides freely: OPEN/HOLD
4. Execute AI decision in simulation
```

---

## 3. Variants System

### What is a Variant?

A **Variant** is a configuration set that defines:
- Trading parameters (SL, TP, trailing, thresholds)
- Indicator configuration (periods, weights, thresholds)
- Operating mode (SCORE_TRIGGERED or AI_INDEPENDENT)
- List of AI models to use (creates sub-variants)

### Variant Structure

```python
Variant:
├── id: int
├── name: str                    # "Conservative", "Aggressive", etc.
├── description: str
├── mode: str                    # "SCORE_TRIGGERED" | "AI_INDEPENDENT"
├── interval_minutes: int        # For AI_INDEPENDENT mode (default: 15)
│
├── parameters: {                # Trading parameters
│   ├── MICRO_GAIN_STOP_LOSS_PERCENT
│   ├── MICRO_GAIN_TRAILING_STEPS
│   ├── SCORE_THRESHOLD_HOLD
│   ├── ... (see section 5)
│   }
│
├── indicator_config: {          # Indicator configuration
│   ├── periods: { RSI, MACD_FAST, MACD_SLOW, ... }
│   ├── weights: { WEIGHT_MACD, WEIGHT_RSI, ... }
│   ├── thresholds: { ADX_WEAK, RSI_OVERSOLD, ... }
│   }
│
├── smart_sl_config: {           # Smart SL configuration
│   ├── enabled: bool
│   ├── trigger_zone: float
│   ├── max_sl_extension: float
│   └── require_ai_confirmation: bool
│   }
│
└── ai_models: [                 # List of AI models (creates sub-variants)
    "deepseek/deepseek-chat",
    "openai/gpt-4-turbo",
    ...
    ]
```

### The 5 Initial Variants

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           5 INITIAL VARIANTS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. BASELINE                                                                │
│     ├─ Mode: SCORE_TRIGGERED                                               │
│     ├─ Parameters: From current .env                                       │
│     ├─ Indicators: Current configuration                                   │
│     ├─ Smart SL: NO                                                        │
│     ├─ AI Models: [DeepSeek]                                               │
│     └─ Purpose: Reference to beat                                          │
│                                                                             │
│  2. MULTI_AI                                                                │
│     ├─ Mode: SCORE_TRIGGERED                                               │
│     ├─ Parameters: Same as Baseline                                        │
│     ├─ Indicators: Same as Baseline                                        │
│     ├─ Smart SL: NO                                                        │
│     ├─ AI Models: [DeepSeek, GPT-4, Claude, Qwen]                          │
│     └─ Purpose: Compare AI models with same parameters                     │
│                                                                             │
│  3. SMART_EXIT                                                              │
│     ├─ Mode: SCORE_TRIGGERED                                               │
│     ├─ Parameters: AI decides SL dynamically                               │
│     ├─ Indicators: Standard                                                │
│     ├─ Smart SL: YES (AI can extend SL if sees reversal)                  │
│     ├─ AI Models: [DeepSeek, GPT-4]                                        │
│     └─ Purpose: Test intelligent stop loss management                      │
│                                                                             │
│  4. INDICATOR_TEST                                                          │
│     ├─ Mode: SCORE_TRIGGERED                                               │
│     ├─ Parameters: Variable (SL, trailing also tested)                     │
│     ├─ Indicators: Different periods and weights                           │
│     │   ├─ Version A: Fast (RSI 7, MACD 8/17/9)                            │
│     │   ├─ Version B: Standard (RSI 14, MACD 12/26/9)                      │
│     │   └─ Version C: Slow (RSI 21, MACD 12/26/9)                          │
│     ├─ Smart SL: NO                                                        │
│     ├─ AI Models: [DeepSeek]                                               │
│     └─ Purpose: Find optimal indicator configuration                       │
│                                                                             │
│  5. AI_FREE                                                                 │
│     ├─ Mode: AI_INDEPENDENT (no score threshold!)                          │
│     ├─ Interval: 15 minutes                                                │
│     ├─ Parameters: SL=4% (only for position management)                    │
│     ├─ Indicators: All passed to AI without filtering                      │
│     ├─ Smart SL: YES                                                       │
│     ├─ AI Models: [DeepSeek, GPT-4]                                        │
│     ├─ Timeframe: LONGER (4h candles for trend context)                    │
│     └─ Purpose: Let AI decide everything freely                            │
│                                                                             │
│  TOTAL SUB-VARIANTS: 1 + 4 + 2 + 3 + 2 = 12                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Sub-Variants (AI Models)

### What is a Sub-Variant?

When a Variant has multiple AI models configured, it creates **Sub-Variants**:

```
Variant "MULTI_AI" with ai_models: [DeepSeek, GPT-4, Claude]
    │
    ├─ Sub-Variant: MULTI_AI_DeepSeek
    │   └─ Uses DeepSeek for all AI decisions
    │
    ├─ Sub-Variant: MULTI_AI_GPT4
    │   └─ Uses GPT-4 for all AI decisions
    │
    └─ Sub-Variant: MULTI_AI_Claude
        └─ Uses Claude for all AI decisions

Each sub-variant:
- Has SAME parameters (from parent Variant)
- Has SAME indicator config (from parent Variant)
- Has DIFFERENT AI model
- Has SEPARATE tracking (trades, P&L, metrics, API cost)
```

### Sub-Variant Structure

```python
SubVariant:
├── id: int
├── variant_id: int              # FK to parent Variant
├── ai_model: str                # "deepseek/deepseek-chat"
├── full_name: str               # "MULTI_AI_DeepSeek"
│
├── # Tracking (separate per sub-variant)
├── total_trades: int
├── total_pnl_usd: float
├── win_rate: float
├── sharpe_ratio: float
├── max_drawdown_usd: float
├── api_calls_count: int
└── api_cost_usd: float
```

---

## 5. Parameters Reference

### Trading Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `MICRO_GAIN_STOP_LOSS_PERCENT` | float | 3.5 | Initial stop loss % |
| `MICRO_GAIN_TARGET_PERCENT` | float | 4.0 | Take profit % |
| `MICRO_GAIN_TRAILING_STEPS` | string | "0.5:-5.0,1.0:-4.0,..." | Trailing SL steps |
| `MICRO_GAIN_LEVERAGE` | float | 5 | Position leverage |
| `MICRO_GAIN_COOLDOWN_SECONDS` | int | 300 | Cooldown after close |
| `SCORE_THRESHOLD_HOLD` | float | 15 | Min score for MICRO_GAIN |
| `SCORE_THRESHOLD_OPEN` | float | 20 | Min score for NORMAL mode |
| `SCORE_CONFIRMATION_CYCLES` | int | 3 | Cycles to confirm score |

### Trailing Steps Format

```
Format: "PNL_THRESHOLD:SL_LEVEL,PNL_THRESHOLD:SL_LEVEL,..."

Example: "0.5:-5.0,1.0:-4.0,1.5:-2.5,2.0:-1.0,2.5:0.0,3.0:0.5,4.0:1.5"

Meaning:
- At +0.5% P&L → SL moves to -5.0%
- At +1.0% P&L → SL moves to -4.0%
- At +1.5% P&L → SL moves to -2.5%
- At +2.0% P&L → SL moves to -1.0%
- At +2.5% P&L → SL moves to 0.0% (breakeven)
- At +3.0% P&L → SL moves to +0.5%
- At +4.0% P&L → SL moves to +1.5%
```

### ATR Dynamic Steps

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ATR_DYNAMIC_STEPS_ENABLED` | bool | true | Scale steps based on ATR |
| `ATR_BASE_PERCENT` | float | 1.5 | Base ATR for scaling |
| `ATR_STEP_MULTIPLIER_MIN` | float | 0.5 | Min multiplier (0.8 recommended) |
| `ATR_STEP_MULTIPLIER_MAX` | float | 2.5 | Max multiplier |

---

## 6. Indicator Configuration

### Indicator Periods

| Parameter | Default | Description | Test Values |
|-----------|---------|-------------|-------------|
| `RSI_PERIOD` | 14 | RSI calculation period | 7, 14, 21 |
| `MACD_FAST` | 12 | MACD fast EMA | 8, 12 |
| `MACD_SLOW` | 26 | MACD slow EMA | 17, 26 |
| `MACD_SIGNAL` | 9 | MACD signal line | 5, 9 |
| `EMA_SHORT` | 9 | Short EMA period | 5, 9 |
| `EMA_MEDIUM` | 20 | Medium EMA period | 12, 20 |
| `EMA_LONG` | 50 | Long EMA period | 26, 50 |
| `ADX_PERIOD` | 14 | ADX period | 14 |
| `ATR_PERIOD` | 14 | ATR period | 14 |
| `BB_PERIOD` | 20 | Bollinger Bands period | 20 |
| `BB_STD` | 2.0 | Bollinger Bands std dev | 2.0 |

### Score Weights (V1 - Legacy)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WEIGHT_RSI_OVERBOUGHT` | 15.0 | Weight for overbought RSI |
| `WEIGHT_RSI_OVERSOLD` | 15.0 | Weight for oversold RSI |
| `WEIGHT_TREND_BULLISH` | 10.0 | Weight for bullish trend |
| `WEIGHT_TREND_BEARISH` | 10.0 | Weight for bearish trend |
| `WEIGHT_MACD_POSITIVE` | 5.0 | Weight for positive MACD |
| `WEIGHT_MACD_NEGATIVE` | 5.0 | Weight for negative MACD |
| `WEIGHT_VOLUME_BULLISH` | 4.0 | Weight for bullish volume |
| `WEIGHT_VOLUME_BEARISH` | 4.0 | Weight for bearish volume |
| `WEIGHT_FEAR_GREED_GREED` | 8.0 | Weight for greed sentiment |
| `WEIGHT_FEAR_GREED_FEAR` | 8.0 | Weight for fear sentiment |
| `WEIGHT_FORECAST_POSITIVE` | 6.0 | Weight for positive forecast |
| `WEIGHT_FORECAST_NEGATIVE` | 6.0 | Weight for negative forecast |

### Score Weights (V2 - Smart Score)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WEIGHT_BOLLINGER` | 8.0 | Weight for Bollinger Bands position |
| `WEIGHT_OBV_TREND` | 6.0 | Weight for OBV trend |
| `WEIGHT_MACD_HISTOGRAM` | 5.0 | Weight for MACD histogram |
| `WEIGHT_EMA_ALIGNMENT` | 7.0 | Weight for EMA alignment |
| `WEIGHT_RSI_MOMENTUM` | 6.0 | Weight for RSI momentum zones |
| `WEIGHT_DOUBLE_BOTTOM` | 10.0 | Weight for Double Bottom pattern |
| `WEIGHT_DOUBLE_TOP` | 10.0 | Weight for Double Top pattern |

### Indicator Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RSI_OVERBOUGHT_THRESHOLD` | 70 | RSI overbought level |
| `RSI_OVERSOLD_THRESHOLD` | 30 | RSI oversold level |
| `ADX_WEAK_THRESHOLD` | 20 | ADX below = ranging market |
| `ADX_STRONG_THRESHOLD` | 25 | ADX above = strong trend |
| `BB_SQUEEZE_THRESHOLD` | 2.0 | Bandwidth < 2% = squeeze |
| `FEAR_GREED_FEAR_THRESHOLD` | 30 | Below = fear sentiment |
| `FEAR_GREED_GREED_THRESHOLD` | 60 | Above = greed sentiment |
| `VOLUME_RATIO_BULLISH_THRESHOLD` | 1.5 | Bid/Ask > 1.5 = bullish |
| `VOLUME_RATIO_BEARISH_THRESHOLD` | 0.67 | Bid/Ask < 0.67 = bearish |

---

## 7. Pattern Detection

### Double Bottom / Double Top Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PATTERN_DETECTION_ENABLED` | true | Enable pattern detection |
| `PATTERN_DETECTION_TIMEFRAME` | 1h | Candle timeframe |
| `PATTERN_LOOKBACK_CANDLES` | 100 | Candles to analyze |
| `PATTERN_CACHE_SECONDS` | 300 | Cache duration |
| `PATTERN_PRICE_TOLERANCE_PCT` | 2.0 | Price tolerance between lows/highs |
| `PATTERN_MIN_DISTANCE_CANDLES` | 10 | Min distance between pivots |
| `PATTERN_RSI_DIVERGENCE_MIN` | 5 | Min RSI divergence |
| `PATTERN_MIN_CONFIDENCE` | 0.60 | Min confidence to consider |

### Pattern Entry System

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PATTERN_ENTRY_SYSTEM` | FAST_LOOP | IMMEDIATE or FAST_LOOP |
| `PATTERN_ENTRY_EXPIRY_MINUTES` | 120 | Pending entry expiration |
| `PATTERN_ENTRY_CONFIRM_VOLUME` | true | Require volume confirmation |
| `PATTERN_ENTRY_VOLUME_MULTIPLIER` | 1.5 | Volume > 1.5x average |

### Contrary Pattern Action

| Parameter | Default | Options |
|-----------|---------|---------|
| `PATTERN_CONTRA_ACTION` | ACCELERATE | CLOSE, ACCELERATE, REDUCE_50, ALERT_ONLY |
| `PATTERN_CONTRA_MIN_CONFIDENCE` | 0.70 | Min confidence to trigger |

---

## 8. AI Independent Mode

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI INDEPENDENT MODE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DIFFERENCE FROM SCORE_TRIGGERED:                                           │
│                                                                             │
│  SCORE_TRIGGERED (standard):                                                │
│  ───────────────────────────                                                │
│  1. Calculate score with indicators                                         │
│  2. Score > threshold? → Call AI for confirmation                          │
│  3. AI confirms → Open trade                                                │
│                                                                             │
│  AI sees opportunities ONLY if score is high enough.                       │
│                                                                             │
│                                                                             │
│  AI_INDEPENDENT (free):                                                     │
│  ──────────────────────                                                     │
│  1. Every 15 minutes, ALWAYS                                               │
│  2. Collect ALL data (price, indicators, sentiment, patterns)              │
│  3. Pass EVERYTHING to AI without filters                                  │
│  4. AI decides freely: OPEN/HOLD/CLOSE                                     │
│                                                                             │
│  AI sees EVERYTHING and decides without constraints.                       │
│  Can find opportunities that score doesn't capture.                        │
│                                                                             │
│  LONGER TIMEFRAME:                                                          │
│  Because it runs every 15 min, AI_FREE uses:                               │
│  - 4h candles for trend context (not just 15m)                             │
│  - Longer-term patterns                                                     │
│  - Multi-timeframe analysis                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### AI Independent Prompt Template

```
You are a fully autonomous trading AI.
Analyze this data and decide if you want to open a position.

MARKET DATA (Current):
- BTC: $97,500 | MACD: +0.15 | RSI: 58 | ADX: 32
- ETH: $3,200 | MACD: -0.08 | RSI: 45 | ADX: 22
- SOL: $132 | MACD: +0.25 | RSI: 62 | ADX: 38

LONGER TERM CONTEXT (4h candles):
- BTC trend: BULLISH (above EMA50)
- ETH trend: NEUTRAL (consolidating)
- SOL trend: BULLISH (strong momentum)

PATTERNS DETECTED:
- SOL: Double Bottom (85% confidence)

SENTIMENT:
- Fear & Greed: 42 (Fear)
- Funding Rate BTC: +0.01%
- Whale Activity: neutral

CURRENT POSITIONS: None

DECIDE:
- Do you want to open a position?
- Which asset? Long or Short?
- If no, why?

Respond in JSON:
{"action": "OPEN|HOLD", "symbol": "BTC|ETH|SOL", "direction": "long|short",
 "confidence": 0-100, "reason": "..."}
```

---

## 9. Smart SL System

### How Smart SL Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SMART SL SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SCENARIO:                                                                  │
│  ─────────                                                                  │
│  Position: LONG BTC @ $97,000                                              │
│  Current SL: -3% ($94,090)                                                 │
│  Price drops to $94,200 (almost SL)                                        │
│                                                                             │
│  CLASSIC SYSTEM:                                                            │
│  "SL almost hit, prepare to close"                                         │
│                                                                             │
│  SMART SL SYSTEM:                                                           │
│  1. Detect we're in "danger zone" (P&L close to SL)                        │
│  2. Analyze current indicators:                                             │
│     - MACD turning positive                                                │
│     - RSI was oversold, now bouncing                                       │
│     - Volume increasing                                                     │
│  3. Ask AI: "Should I close or hold?"                                      │
│  4. AI: "I see imminent reversal, HOLD"                                    │
│  5. DECISION:                                                               │
│     - Extend SL temporarily (e.g., -3% → -4.5%)                            │
│     - Continue monitoring                                                   │
│     - If price recovers: SL saved us from premature exit                   │
│     - If price drops more: Close at extended SL                            │
│                                                                             │
│  SAFETY LIMITS:                                                             │
│  - SL cannot go beyond max (e.g., -6%)                                     │
│  - Can "save" position only 1-2 times                                      │
│  - If AI doesn't respond in 5s → close anyway                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Smart SL Configuration

```python
smart_sl_config: {
    "enabled": True,
    "trigger_zone": 1.0,           # Activate when P&L < SL + 1%
    "max_sl_extension": 2.0,       # Max SL extension (e.g., -3% → -5%)
    "max_saves": 2,                # Max times can "save"
    "require_ai_confirmation": True,
    "ai_timeout_seconds": 10,      # If AI slow → close
    "min_indicators_for_hold": 2,  # Min bullish indicators to hold
}
```

---

## 10. Database Schema

### Tables

```sql
-- Main variants table
CREATE TABLE arena_variants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    mode VARCHAR(20) NOT NULL DEFAULT 'SCORE_TRIGGERED',  -- SCORE_TRIGGERED | AI_INDEPENDENT
    interval_minutes INTEGER DEFAULT 15,                   -- For AI_INDEPENDENT

    parameters JSONB NOT NULL,           -- Trading params (SL, TP, trailing, etc.)
    indicator_config JSONB,              -- Indicator periods, weights, thresholds
    smart_sl_config JSONB,               -- Smart SL configuration
    ai_models JSONB NOT NULL,            -- Array of AI model names

    is_active BOOLEAN DEFAULT true,
    is_baseline BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Sub-variants (one per AI model per variant)
CREATE TABLE arena_sub_variants (
    id SERIAL PRIMARY KEY,
    variant_id INTEGER REFERENCES arena_variants(id),
    ai_model VARCHAR(100) NOT NULL,      -- "deepseek/deepseek-chat"
    full_name VARCHAR(150) NOT NULL,     -- "MULTI_AI_DeepSeek"

    -- Tracking
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    total_pnl_usd DECIMAL(12,4) DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0,
    sharpe_ratio DECIMAL(6,4) DEFAULT 0,
    max_drawdown_usd DECIMAL(12,4) DEFAULT 0,
    profit_factor DECIMAL(6,4) DEFAULT 0,

    -- API tracking
    api_calls_count INTEGER DEFAULT 0,
    api_cost_usd DECIMAL(10,4) DEFAULT 0,

    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(variant_id, ai_model)
);

-- Open simulated positions
CREATE TABLE simulated_positions (
    id SERIAL PRIMARY KEY,
    sub_variant_id INTEGER REFERENCES arena_sub_variants(id),
    symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,

    entry_price DECIMAL(20,8) NOT NULL,
    entry_score DECIMAL(10,4),
    current_sl_percent DECIMAL(6,4) NOT NULL,
    peak_pnl_percent DECIMAL(10,4) DEFAULT 0,
    sl_saves_used INTEGER DEFAULT 0,      -- For Smart SL

    opened_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(sub_variant_id, symbol)
);

-- Closed simulated trades
CREATE TABLE simulated_trades (
    id SERIAL PRIMARY KEY,
    sub_variant_id INTEGER REFERENCES arena_sub_variants(id),

    symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,

    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8) NOT NULL,
    entry_score DECIMAL(10,4),

    pnl_percent DECIMAL(10,4) NOT NULL,
    pnl_usd DECIMAL(12,4) NOT NULL,
    peak_pnl_percent DECIMAL(10,4),

    close_reason VARCHAR(50) NOT NULL,    -- SL_HIT, TP_HIT, TRAILING, AI_DECISION, SMART_SL

    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP DEFAULT NOW(),
    duration_seconds INTEGER,

    profitable BOOLEAN NOT NULL,

    -- For analysis
    indicator_snapshot JSONB,             -- Indicators at entry
    ai_reasoning TEXT                     -- AI's reasoning (if applicable)
);

-- Indexes for performance
CREATE INDEX idx_simulated_trades_sub_variant ON simulated_trades(sub_variant_id);
CREATE INDEX idx_simulated_trades_closed_at ON simulated_trades(closed_at);
CREATE INDEX idx_simulated_positions_sub_variant ON simulated_positions(sub_variant_id);
```

---

## 11. File Structure

```
rizzo-trading-agent/
│
├── sentinel.py                    # Production bot (unchanged)
├── indicators.py                  # Indicators (shared)
├── signal_scorer.py               # Score calculation (shared)
├── db_utils.py                    # Existing DB utils (extend)
│
├── arena/                         # ═══ NEW: Arena package ═══
│   │
│   ├── __init__.py
│   │
│   ├── config.py                  # Arena configuration
│   │   └─ Intervals, limits, defaults
│   │
│   ├── models.py                  # Data classes
│   │   ├─ Variant
│   │   ├─ SubVariant
│   │   ├─ SimulatedPosition
│   │   ├─ SimulatedTrade
│   │   └─ VariantMetrics
│   │
│   ├── db.py                      # Arena database operations
│   │   ├─ create_tables()
│   │   ├─ CRUD for variants/sub-variants
│   │   ├─ CRUD for positions/trades
│   │   └─ Metrics aggregation queries
│   │
│   ├── variant_manager.py         # Variant management
│   │   ├─ create_variant()
│   │   ├─ create_sub_variants()
│   │   ├─ create_baseline_from_env()
│   │   └─ activate/deactivate variants
│   │
│   ├── indicator_calculator.py    # Custom indicator calculation
│   │   └─ calculate_with_config()  # Uses variant's indicator_config
│   │
│   ├── score_calculator.py        # Custom score calculation
│   │   └─ calculate_with_weights() # Uses variant's weights
│   │
│   ├── simulator.py               # ═══ CORE: Simulation engine ═══
│   │   ├─ class ArenaSimulator
│   │   │   ├─ run_cycle()
│   │   │   ├─ process_score_triggered()
│   │   │   ├─ process_ai_independent()
│   │   │   ├─ evaluate_entry()
│   │   │   ├─ manage_position()
│   │   │   ├─ calculate_trailing()
│   │   │   ├─ check_smart_sl()
│   │   │   └─ close_position()
│   │
│   ├── ai_manager.py              # AI model management
│   │   ├─ call_ai()               # Call specific model
│   │   ├─ rate_limit()            # Respect limits
│   │   └─ track_cost()            # Track API costs
│   │
│   ├── smart_sl.py                # Smart SL logic
│   │   ├─ should_extend_sl()
│   │   ├─ get_ai_decision()
│   │   └─ calculate_new_sl()
│   │
│   ├── metrics.py                 # Metrics calculation
│   │   ├─ calculate_win_rate()
│   │   ├─ calculate_sharpe_ratio()
│   │   ├─ calculate_profit_factor()
│   │   └─ calculate_max_drawdown()
│   │
│   └── report.py                  # Reporting
│       ├─ generate_leaderboard()
│       ├─ compare_ai_models()
│       ├─ compare_indicators()
│       └─ send_telegram_report()
│
├── arena_main.py                  # Arena entry point
│   └─ Main loop, argument parsing
│
├── arena_cli.py                   # CLI commands
│   ├─ arena setup                 # Initial setup
│   ├─ arena create-variant        # Create variant
│   ├─ arena list                  # List variants
│   ├─ arena report                # Generate report
│   └─ arena promote               # Promote winner
│
├── ARENA_TECHNICAL_DOC.md         # This document
│
└── docker-compose.arena.yml       # Docker for Arena
```

---

## 12. Configuration Examples

### Variant: BASELINE

```json
{
  "name": "BASELINE",
  "description": "Current production configuration",
  "mode": "SCORE_TRIGGERED",
  "parameters": {
    "MICRO_GAIN_STOP_LOSS_PERCENT": 3.5,
    "MICRO_GAIN_TARGET_PERCENT": 4.0,
    "MICRO_GAIN_TRAILING_STEPS": "0.5:-5.0,1.0:-4.0,1.5:-2.5,2.0:-1.0,2.5:0.0,3.0:0.5",
    "MICRO_GAIN_LEVERAGE": 5,
    "SCORE_THRESHOLD_HOLD": 15
  },
  "indicator_config": {
    "periods": {
      "RSI": 14,
      "MACD_FAST": 12,
      "MACD_SLOW": 26,
      "MACD_SIGNAL": 9
    },
    "weights": {
      "WEIGHT_MACD_POSITIVE": 5.0,
      "WEIGHT_RSI_OVERSOLD": 15.0,
      "WEIGHT_BOLLINGER": 8.0,
      "WEIGHT_OBV_TREND": 6.0,
      "WEIGHT_DOUBLE_BOTTOM": 10.0
    },
    "thresholds": {
      "ADX_WEAK_THRESHOLD": 20.0,
      "RSI_OVERSOLD_THRESHOLD": 30.0
    }
  },
  "smart_sl_config": {
    "enabled": false
  },
  "ai_models": ["deepseek/deepseek-chat"]
}
```

### Variant: AI_FREE

```json
{
  "name": "AI_FREE",
  "description": "AI decides everything, no score threshold",
  "mode": "AI_INDEPENDENT",
  "interval_minutes": 15,
  "parameters": {
    "MICRO_GAIN_STOP_LOSS_PERCENT": 4.0,
    "MICRO_GAIN_LEVERAGE": 5
  },
  "indicator_config": {
    "periods": {
      "RSI": 14,
      "MACD_FAST": 12,
      "MACD_SLOW": 26
    },
    "longer_timeframe": "4h"
  },
  "smart_sl_config": {
    "enabled": true,
    "trigger_zone": 1.0,
    "max_sl_extension": 2.0,
    "max_saves": 2,
    "require_ai_confirmation": true
  },
  "ai_models": ["deepseek/deepseek-chat", "openai/gpt-4-turbo"]
}
```

---

## 13. API & Models

### OpenRouter Configuration

All AI models are accessed through **OpenRouter** with a single API key.

```env
# .env configuration
OPENROUTER_API_KEY=sk-or-v1-xxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Available models (configure per variant)
ARENA_AI_MODELS=deepseek/deepseek-chat,openai/gpt-4-turbo,anthropic/claude-3-sonnet,qwen/qwen-72b-chat

# AI_FREE specific model (if you want different)
AI_FREE_MODEL=openai/gpt-4-turbo
```

### Model Comparison

| Model | Cost/1K tokens | Speed | Quality | Best For |
|-------|---------------|-------|---------|----------|
| deepseek/deepseek-chat | $0.001 | Fast | Good | High volume |
| openai/gpt-4-turbo | $0.01 | Medium | Excellent | Complex decisions |
| anthropic/claude-3-sonnet | $0.003 | Fast | Very Good | Balanced |
| qwen/qwen-72b-chat | $0.0008 | Fast | Good | Budget testing |

### API Cost Management

```python
# Rate limiting per sub-variant
MAX_API_CALLS_PER_HOUR = 20

# Cost tracking
# Each AI call logs: model, tokens_used, cost_usd
# Aggregated per sub-variant for comparison
```

---

## 14. Metrics & Leaderboard

### Metrics Calculated

| Metric | Formula | Meaning |
|--------|---------|---------|
| **Win Rate** | wins / total_trades × 100 | % profitable trades |
| **Profit Factor** | sum(wins) / sum(losses) | Profitability ratio |
| **Sharpe Ratio** | (avg_return - risk_free) / std_dev | Risk-adjusted return |
| **Max Drawdown** | max peak-to-trough decline | Worst losing streak |
| **Avg Trade P&L** | total_pnl / total_trades | Average per trade |
| **Profit Left on Table** | avg(peak - exit) | How much left behind |
| **P&L per API Cost** | total_pnl / api_cost | Cost efficiency |

### Leaderboard Example

```
╔════════════════════════════════════════════════════════════════════════════════╗
║                              ARENA LEADERBOARD                                 ║
╠════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  BY SUB-VARIANT (Performance):                                                 ║
║  ──────────────────────────────────────────────────────────────────────────── ║
║  #  │ Sub-Variant          │ Mode     │ Trades │ WR   │ P&L     │ Sharpe     ║
║  ───┼──────────────────────┼──────────┼────────┼──────┼─────────┼──────────  ║
║  1  │ AI_FREE_GPT4         │ AI_INDEP │   45   │ 52%  │ +$24.50 │ 1.82       ║
║  2  │ SMART_EXIT_GPT4      │ SCORE    │   38   │ 50%  │ +$19.20 │ 1.68       ║
║  3  │ MULTI_AI_GPT4        │ SCORE    │   58   │ 48%  │ +$15.80 │ 1.48       ║
║  4  │ BASELINE_DeepSeek    │ SCORE    │   62   │ 42%  │ +$8.60  │ 1.22       ║
║                                                                                ║
║  BY AI MODEL (Aggregated):                                                     ║
║  ──────────────────────────────────────────────────────────────────────────── ║
║  Model      │ Sub-Var │ Trades │ Avg WR │ Total P&L │ API Cost │ P&L/Cost    ║
║  ───────────┼─────────┼────────┼────────┼───────────┼──────────┼───────────  ║
║  GPT-4      │    4    │  180   │  51%   │  +$62.50  │  $38.00  │  1.64       ║
║  DeepSeek   │    4    │  195   │  43%   │  +$35.20  │  $6.00   │  5.87 ⭐    ║
║                                                                                ║
║  BY INDICATOR CONFIG:                                                          ║
║  ──────────────────────────────────────────────────────────────────────────── ║
║  Config          │ RSI  │ MACD     │ Avg WR │ Sharpe │ Note                   ║
║  ────────────────┼──────┼──────────┼────────┼────────┼──────────────────────  ║
║  Fast            │  7   │ 8/17/9   │  44%   │  1.28  │ More trades            ║
║  Standard        │ 14   │ 12/26/9  │  45%   │  1.35  │ Balanced               ║
║  Conservative    │ 21   │ 12/26/9  │  52%   │  1.55  │ Fewer but precise      ║
║                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════╝
```

---

## 15. Deployment

### Docker Configuration

```yaml
# docker-compose.arena.yml
version: '3.8'

services:
  rizzo_arena:
    build: .
    image: rizzo-arena:latest
    container_name: rizzo_arena
    entrypoint: python arena_main.py --loop
    env_file:
      - .env
    environment:
      - ARENA_MODE=true
      - PYTHONUNBUFFERED=1
    networks:
      - unified-memory-stack_memory-net
    restart: unless-stopped
    depends_on:
      - memory_postgres
```

### Commands

```bash
# Setup Arena (first time)
python arena_cli.py setup

# Create baseline from current config
python arena_cli.py create-baseline

# Create a new variant
python arena_cli.py create-variant \
  --name "CONSERVATIVE" \
  --param MICRO_GAIN_STOP_LOSS_PERCENT=5.0 \
  --param SCORE_THRESHOLD_HOLD=20 \
  --ai-model deepseek/deepseek-chat \
  --ai-model openai/gpt-4-turbo

# List all variants
python arena_cli.py list

# Run Arena
docker run -d --name rizzo_arena ...
# or
python arena_main.py --loop

# Generate report
python arena_cli.py report

# Promote winner to production
python arena_cli.py promote --sub-variant-id 5
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-13 | 1.0 | Initial document creation |

---

## Next Steps

1. [ ] Create arena/ package structure
2. [ ] Implement database schema
3. [ ] Implement models.py
4. [ ] Implement db.py
5. [ ] Implement simulator.py (core)
6. [ ] Implement AI manager
7. [ ] Implement Smart SL
8. [ ] Implement metrics and reporting
9. [ ] Create CLI
10. [ ] Docker configuration
11. [ ] Testing
12. [ ] Deployment

---

*Document maintained by: Claude AI*
*Last updated: 2025-12-13*
