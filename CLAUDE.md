# CLAUDE.md - AI Prompt Architecture

This document describes how AI prompts work in the Rizzo Trading Agent.

## Overview

The trading agent uses AI (via OpenRouter/DeepSeek) for two distinct purposes:
1. **Main Trading Decisions** - Full analysis and trade execution
2. **DOUBLE_CHECK Validation** - Confirmation before opening positions

## Prompt Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API CALL STRUCTURE                          │
├─────────────────────────────────────────────────────────────────────┤
│  SYSTEM MESSAGE (fixed, English):                                   │
│  "You are a cryptocurrency trading AI.                              │
│   Always respond with valid JSON..."                                │
│  → Defined in: trading_agent.py (call_ai_api function)              │
├─────────────────────────────────────────────────────────────────────┤
│  USER MESSAGE (variable):                                           │
│  → Content depends on the calling context (see below)               │
└─────────────────────────────────────────────────────────────────────┘
```

## Prompt Types

### 1. Main Trading Prompt (main.py)

**File**: `system_prompt_single.txt`
**Language**: English
**Called by**: `main.py` → `previsione_trading_agent()`

**Purpose**: Full trading decision (OPEN/CLOSE/HOLD) with comprehensive market analysis.

**Content includes**:
- Portfolio context
- Market data (indicators, forecasts)
- Historical stats
- Position context
- Whale alerts
- Fear & Greed sentiment

**When called**:
- Every trading cycle (configurable interval)
- For each enabled symbol (BTC, ETH, SOL)

---

### 2. DOUBLE_CHECK Prompt (sentinel.py)

**File**: Inline in `sentinel.py` (`validate_double_check_ai` function)
**Language**: English
**Called by**: `sentinel.py` → `validate_double_check_ai()`

**Purpose**: Validate a proposed trade BEFORE execution. Acts as a confirmation layer.

**When called**:
- After Sentinel score exceeds threshold
- Before opening any MICRO_GAIN or MICRO_PAY position
- Only if `DOUBLE_CHECK_AI_ENABLED=true`

---

## TRADING_STYLE Configuration

The DOUBLE_CHECK prompt behavior is controlled by the `TRADING_STYLE` environment variable.

### Environment Variable

```env
TRADING_STYLE=moderate  # Options: aggressive | moderate | conservative
```

### Trading Styles Explained

| Style | Entry Requirements | Best For |
|-------|-------------------|----------|
| **aggressive** | MACD >0.15 + ADX >15 | High frequency, volatile markets |
| **moderate** | MACD >0.20 + EMA + ADX >20 | Balanced risk/reward (RECOMMENDED) |
| **conservative** | ALL signals + ADX >25 | Capital preservation, stable markets |

### Detailed Style Rules

#### AGGRESSIVE (Momentum Chaser)
```
Entry: Need ONLY ONE strong signal
- MACD > 0.15 (or < -0.15) = GO
- ADX > 15 = OK (lower bar for ranging filter)
- Ignore RSI in 20-80 range
- EMA is secondary confirmation
- Whale activity: nice to have, not required
Bias: When in doubt with strong momentum → OPEN
```

#### MODERATE (Trend Follower) - DEFAULT
```
Entry: PRIMARY signals + no major contradiction
Primary:
- MACD > 0.20 (or < -0.20) = strong signal
- ADX > 20 = REQUIRED (avoid ranging markets)
- Price vs EMA20 confirms direction
Secondary:
- RSI as exhaustion filter only (< 25 or > 75 = caution)
- Whale activity: confirming is good, neutral is OK
- Funding rate: check for squeeze risk
Bias: Strong MACD + EMA + ADX > 20 = GO
```

#### CONSERVATIVE (Sniper)
```
Entry: ALL signals must align
Required:
- MACD > 0.25 (or < -0.25)
- ADX > 25 = REQUIRED (need confirmed trend)
- Price must confirm vs EMA20
- RSI must not be exhausted
- No contradicting whale activity
- No extreme funding rate
- Score trend must be stable
Bias: When in doubt → HOLD
```

---

## Direction Override Feature

The AI can override the direction proposed by Sentinel if indicators strongly suggest the opposite.

### How it works:
1. Sentinel calculates score +15 → proposes LONG
2. AI analyzes indicators → sees MACD is strongly negative (-0.30)
3. AI responds: `{"operation": "open", "direction": "short"}`
4. System opens SHORT instead of LONG

### Log output when override happens:
```
🔍 DOUBLE_CHECK [MODERATE]: Validating BTC LONG...
   ✅ AI APPROVED with DIRECTION OVERRIDE: LONG → SHORT
      Reason: MACD -0.30 strongly bearish, overrides positive score
```

### When AI should override:
- Only with HIGH CONFIDENCE in the opposite direction
- When primary indicators (MACD, EMA) strongly contradict the score
- Example: Score is positive but MACD is very negative

---

## Indicator Weights

The DOUBLE_CHECK prompt assigns different importance to indicators:

### Primary Indicators (High Weight)
- **MACD**: Momentum direction and strength
- **Price vs EMA20**: Trend confirmation
- **ADX**: Trend strength filter (CRITICAL for avoiding ranging markets)

### Secondary Indicators (Medium Weight)
- **RSI**: Only matters at extremes (<25 or >75)
- **Whale Activity**: Confirmation signal
- **Open Interest**: Trend health indicator
- **Funding Rate**: Squeeze risk detector

### Tertiary Indicators (Low Weight for short-term trades)
- **Fear & Greed Index**: Macro sentiment, less relevant for MICRO_GAIN

---

## ADX (Average Directional Index)

ADX is a **trend strength** indicator, NOT a direction indicator. It measures HOW STRONG the current trend is, regardless of whether it's bullish or bearish.

### Why ADX is Critical

**Problem**: Trading in ranging/sideways markets causes losses due to whipsaws and false signals.

**Solution**: ADX filters out ranging markets before opening positions.

### ADX Thresholds

| ADX Value | Interpretation | Trading Action |
|-----------|---------------|----------------|
| < 20 | **WEAK/NO TREND** (ranging) | **DO NOT TRADE** - high risk of whipsaw |
| 20-25 | Emerging trend | OK with strong confirmation |
| 25-50 | Strong trend | Good for trend-following trades |
| > 50 | Very strong trend | Trend may be exhausting, watch for reversal |

### ADX in Trading Styles

- **Aggressive**: ADX > 15 (lower bar)
- **Moderate**: ADX > 20 (avoid ranging)
- **Conservative**: ADX > 25 (confirmed trend only)

### Data Source

ADX is calculated in `indicators.py` using a 14-period lookback on 15-minute candles.

---

## Open Interest & Funding Rate

### Open Interest (OI)
- Total value of open derivative positions
- Rising OI + Rising Price = Healthy bullish trend
- Rising OI + Falling Price = Healthy bearish trend
- Falling OI = Positions closing, trend weakening

### Funding Rate
- Cost of holding leveraged positions
- Positive funding = Longs pay shorts (bullish bias in market)
- Negative funding = Shorts pay longs (bearish bias in market)
- **Extreme negative** (< -0.01%): Short squeeze risk
- **Extreme positive** (> +0.01%): Long squeeze risk

---

## Numeric Thresholds

| Indicator | Threshold | Meaning |
|-----------|-----------|---------|
| MACD | > 0.15 | Bullish momentum |
| MACD | < -0.15 | Bearish momentum |
| MACD | > 0.20 | Strong bullish (moderate mode) |
| MACD | < -0.20 | Strong bearish (moderate mode) |
| MACD | > 0.25 | Very strong (conservative mode) |
| RSI | < 25 | Oversold exhaustion warning |
| RSI | > 75 | Overbought exhaustion warning |
| RSI | 30-70 | Neutral (does not block trades) |
| **ADX** | < 20 | **RANGING MARKET - AVOID TRADING** |
| ADX | 20-25 | Emerging trend - OK with confirmation |
| ADX | 25-50 | Strong trend - Good for trading |
| ADX | > 50 | Very strong trend - Watch exhaustion |
| Funding | < -0.01% | Short squeeze risk (caution on shorts) |
| Funding | > +0.01% | Long squeeze risk (caution on longs) |

---

## Call Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      SENTINEL LOOP                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. Calculate Score for each symbol (BTC, ETH, SOL)              │
│     └─→ signal_scorer.py                                          │
│                                                                   │
│  2. Check if score exceeds SCORE_THRESHOLD_OPEN                  │
│     └─→ If NO: HOLD (no action)                                   │
│     └─→ If YES: Continue to step 3                                │
│                                                                   │
│  3. DOUBLE_CHECK_AI_ENABLED?                                      │
│     └─→ If NO: Open position directly                             │
│     └─→ If YES: Call validate_double_check_ai()                   │
│                                                                   │
│  4. DOUBLE_CHECK Validation                                       │
│     ├─→ Gather: indicators, whale, sentiment                      │
│     ├─→ Select prompt based on TRADING_STYLE                      │
│     ├─→ Call AI (DeepSeek)                                        │
│     └─→ AI responds: "open" or "hold"                             │
│                                                                   │
│  5. Execute Decision                                              │
│     └─→ If "open": Place trade on HyperLiquid                    │
│     └─→ If "hold": Skip this signal                               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `system_prompt_single.txt` | Main trading prompt template |
| `sentinel.py` | Contains DOUBLE_CHECK prompt and trading styles |
| `trading_agent.py` | AI call wrapper (`previsione_trading_agent`) |
| `.env` | Configuration including TRADING_STYLE |

---

## Example Log Output

```
[12:34:56] 📊 BTC Score: BULL=0.0 BEAR=18.5 NET=-18.5 → SHORT
[12:34:56]    🔍 DOUBLE_CHECK [MODERATE]: Validating BTC SHORT...
[12:34:56]       Calling AI...
[12:34:58]       ✅ AI APPROVED: MACD -0.25 strong bearish, price below EMA20 confirms
[12:34:58]    ✅ Opening MICRO_GAIN SHORT on BTC
```

---

## Updating Prompts

To modify trading behavior:

1. **Change strictness**: Set `TRADING_STYLE` in `.env`
2. **Modify thresholds**: Edit `_get_trading_style_prompt()` in `sentinel.py`
3. **Add new indicators**: Update `validate_double_check_ai()` prompt construction

---

## Double Bottom / Double Top Pattern Detection

### Overview

The system can detect **reversal patterns** (Double Bottom "W" and Double Top "M") to:
1. **ENTRY**: Add points to score when pattern detected (potential entry signal)
2. **EXIT**: Trigger protective action when contrary pattern appears during open position

### Pattern Types

```
DOUBLE BOTTOM (W) - Bullish Reversal
═════════════════════════════════════

   Price
     ▲
     │                 ╱── NECKLINE (resistance)
     │    ╲           ╱
     │     ╲    ╱╲   ╱
     │      ╲  ╱  ╲ ╱
     │       ╲╱    ╲╱
     │       LOW1  LOW2   ← Two similar lows
     │      (RSI:28)(RSI:35) ← RSI DIVERGENCE (bullish)
     └──────────────────────▶

   RSI makes HIGHER low while price makes similar low = BULLISH signal


DOUBLE TOP (M) - Bearish Reversal
═════════════════════════════════

   Price
     ▲       HIGH1  HIGH2   ← Two similar highs
     │       ╱╲    ╱╲
     │      ╱  ╲  ╱  ╲      (RSI:72)(RSI:65) ← RSI DIVERGENCE (bearish)
     │     ╱    ╲╱    ╲
     │    ╱            ╲
     │                  ╲── NECKLINE (support)
     └──────────────────────▶

   RSI makes LOWER high while price makes similar high = BEARISH signal
```

### Detection Logic

Pattern detection runs on **1-hour candles** (configurable) with caching to minimize API calls.

```
Detection Parameters:
├─ Timeframe: 1h (reliable patterns)
├─ Lookback: 100 candles (~4 days)
├─ Price tolerance: ±2% between lows/highs
├─ Min distance: 10 candles between first and second low/high
├─ RSI divergence: min 5 points difference
└─ Confidence: calculated based on pattern quality (0-100%)
```

### Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PATTERN DETECTION FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   HyperLiquid API                                                           │
│        │                                                                    │
│        ├─── 15m candles (200) ─── Standard indicators (EMA, RSI, MACD)      │
│        │                                                                    │
│        └─── 1h candles (100) ─── Pattern detection (cached 5 min)           │
│                    │                                                        │
│                    ▼                                                        │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  indicators.py                                                      │    │
│   │  ├─ detect_double_bottom(candles) → {detected, confidence, ...}     │    │
│   │  └─ detect_double_top(candles) → {detected, confidence, ...}        │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                    │                                                        │
│                    ▼                                                        │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  signal_scorer.py                                                   │    │
│   │  └─ calculate_smart_score_v2() now includes:                        │    │
│   │     if double_bottom.detected:                                      │    │
│   │         score_bullish += WEIGHT_DOUBLE_BOTTOM * confidence          │    │
│   │     if double_top.detected:                                         │    │
│   │         score_bearish += WEIGHT_DOUBLE_TOP * confidence             │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                    │                                                        │
│                    ▼                                                        │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  sentinel.py                                                        │    │
│   │                                                                     │    │
│   │  SLOW LOOP:                                                         │    │
│   │  ├─ Pattern info included in DOUBLE_CHECK AI prompt                 │    │
│   │  ├─ If AI approves → creates PENDING_ENTRY (not immediate entry)    │    │
│   │  └─ Contrary pattern check → triggers ACCELERATE if detected        │    │
│   │                                                                     │    │
│   │  FAST LOOP:                                                         │    │
│   │  └─ Monitors PENDING_ENTRIES for:                                   │    │
│   │     ├─ Entry condition (price breakout + volume)                    │    │
│   │     ├─ Invalidation (pattern broken)                                │    │
│   │     └─ Expiration (time limit)                                      │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Entry System: FAST_LOOP Monitoring

Instead of entering immediately when pattern detected, the system uses a **pending entry** approach:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PENDING ENTRY SYSTEM                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. SLOW LOOP detects pattern + AI approves                                │
│      → Creates PENDING_ENTRY:                                               │
│        {                                                                    │
│          "symbol": "BTC",                                                   │
│          "direction": "LONG",                                               │
│          "entry_price": 98000,        # neckline                            │
│          "invalidation_price": 94800, # below first low = pattern broken    │
│          "stop_loss": 93500,          # ATR-based                           │
│          "expires_at": now + 2h                                             │
│        }                                                                    │
│                                                                             │
│   2. FAST LOOP monitors every 3-5s:                                         │
│                                                                             │
│      ┌─────────────────────────────────────────────────────────────────┐    │
│      │  CHECK 1: Expired?                                              │    │
│      │  └─ Yes → Remove pending entry, log "⏰ SCADUTO"                 │    │
│      │                                                                 │    │
│      │  CHECK 2: Pattern invalidated? (price < invalidation_price)     │    │
│      │  └─ Yes → Remove pending entry, log "❌ INVALIDATO"              │    │
│      │                                                                 │    │
│      │  CHECK 3: Already in position?                                  │    │
│      │  └─ Yes → Remove pending entry                                  │    │
│      │                                                                 │    │
│      │  CHECK 4: Entry condition met? (price > entry_price)            │    │
│      │  └─ Yes + Volume OK → OPEN POSITION, log "✅ BREAKOUT!"          │    │
│      └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   Benefits:                                                                 │
│   ✓ Avoids false breakouts (waits for confirmation)                         │
│   ✓ Can add volume/momentum confirmation                                    │
│   ✓ Easy to cancel (just delete from memory)                                │
│   ✓ No orders sitting on exchange                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Exit System: Contrary Pattern Protection

When a contrary pattern appears during an open position, the system protects profits:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONTRARY PATTERN → ACCELERATE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Scenario: You are SHORT on BTC, in profit                                 │
│                                                                             │
│   SLOW LOOP detects DOUBLE BOTTOM (bullish reversal)                        │
│   → This is CONTRARY to your SHORT position!                                │
│   → Risk: trend may reverse against you                                     │
│                                                                             │
│   Action: ACCELERATE                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Tighten stop loss to protect profits                            │   │
│   │  2. Position stays open (don't close immediately)                   │   │
│   │  3. If price reverses up → SL hit, profit locked                    │   │
│   │  4. If price continues down → you stay in the trade                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Configuration options (PATTERN_CONTRA_ACTION):                            │
│   ├─ ACCELERATE: Tighten SL (recommended)                                   │
│   ├─ CLOSE: Close position immediately                                      │
│   ├─ REDUCE_50: Close 50% of position                                       │
│   └─ ALERT_ONLY: Just log warning, no action                                │
│                                                                             │
│   Example log:                                                              │
│   [14:30:02] ⚠️ DOUBLE BOTTOM detected while SHORT BTC                       │
│   [14:30:02] 🔄 ACCELERATE: SL tightened $101,500 → $96,500                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pattern Usage Matrix

| Your Position | Pattern Detected | Action |
|---------------|------------------|--------|
| None | Double Bottom | → Score +12 bullish, potential LONG entry |
| None | Double Top | → Score +12 bearish, potential SHORT entry |
| LONG | Double Bottom | → Confirmation (pattern supports your position) |
| LONG | Double Top | → ⚠️ CONTRARY! Trigger ACCELERATE |
| SHORT | Double Top | → Confirmation (pattern supports your position) |
| SHORT | Double Bottom | → ⚠️ CONTRARY! Trigger ACCELERATE |

### API Impact

Pattern detection is **cached** to minimize API calls:

| Without Pattern | With Pattern (cached) | HyperLiquid Limit |
|-----------------|----------------------|-------------------|
| ~24 calls/min | ~25 calls/min | 1200/min |
| 2% of limit | 2.5% of limit | - |

Cache refresh: every 5 minutes (patterns form slowly on 1h timeframe).

### Environment Variables

```bash
# ═══════════════════════════════════════════════════════════════════════════
# PATTERN DETECTION - Double Bottom / Double Top
# ═══════════════════════════════════════════════════════════════════════════

# --- Enable/Disable ---
PATTERN_DETECTION_ENABLED=true

# --- Detection Settings ---
PATTERN_DETECTION_TIMEFRAME=1h          # 15m, 1h, 4h
PATTERN_LOOKBACK_CANDLES=100            # Candles to analyze
PATTERN_CACHE_SECONDS=300               # Cache refresh (5 min)

# --- Pattern Parameters ---
PATTERN_PRICE_TOLERANCE_PCT=2.0         # Tolerance between lows/highs (%)
PATTERN_MIN_DISTANCE_CANDLES=10         # Min candles between low1/low2
PATTERN_RSI_DIVERGENCE_MIN=5            # Min RSI difference for divergence
PATTERN_MIN_CONFIDENCE=0.60             # Min confidence to consider valid

# --- Score Weights ---
WEIGHT_DOUBLE_BOTTOM=12.0               # Points added to bullish score
WEIGHT_DOUBLE_TOP=12.0                  # Points added to bearish score

# --- Entry System ---
PATTERN_ENTRY_SYSTEM=FAST_LOOP          # IMMEDIATE or FAST_LOOP
PATTERN_ENTRY_EXPIRY_MINUTES=120        # Pending entry expiration
PATTERN_ENTRY_CONFIRM_VOLUME=true       # Require volume confirmation
PATTERN_ENTRY_VOLUME_MULTIPLIER=1.5     # Volume > 1.5x average

# --- Exit System (Contrary Pattern) ---
PATTERN_CONTRA_ACTION=ACCELERATE        # CLOSE, ACCELERATE, REDUCE_50, ALERT_ONLY
PATTERN_CONTRA_MIN_CONFIDENCE=0.70      # Min confidence to trigger action

# --- Stop Loss ---
PATTERN_SL_USE_ATR=true                 # Use ATR for dynamic SL
PATTERN_SL_ATR_MULTIPLIER=1.5           # SL = entry - (1.5 × ATR)
```

### Example: Complete Flow

```
═══════════════════════════════════════════════════════════════════════════════
                    EXAMPLE: BTC Double Bottom Entry
═══════════════════════════════════════════════════════════════════════════════

14:30:00 [SLOW] Fetching 1h candles for pattern detection...
14:30:01 [SLOW] 🔷 DOUBLE BOTTOM DETECTED on BTC
         ├─ Confidence: 85%
         ├─ First low: $94,800 (RSI: 28)
         ├─ Second low: $95,000 (RSI: 35)
         ├─ RSI Divergence: BULLISH (+7)
         ├─ Neckline: $98,000
         └─ Suggested SL: $93,500 (1.5 × ATR)

14:30:02 [SLOW] Score calculation:
         ├─ Standard indicators: +16.5 bullish
         ├─ Double Bottom: +10.2 bullish (12 × 0.85)
         └─ NET SCORE: +26.7 → LONG (STRONG)

14:30:03 [SLOW] 🔍 DOUBLE_CHECK AI validation...
         └─ AI APPROVED: "Strong W pattern with RSI divergence"

14:30:04 [SLOW] ⏳ Created PENDING_ENTRY:
         ├─ Entry: wait for price > $98,000 (neckline breakout)
         ├─ Invalidation: price < $94,800 (pattern broken)
         ├─ Stop Loss: $93,500
         └─ Expires: 16:30:00 (2 hours)

14:30:07 [FAST] 👀 BTC @ $96,500 - Below neckline, waiting...
14:35:12 [FAST] 👀 BTC @ $97,200 - Below neckline, waiting...
14:42:33 [FAST] 👀 BTC @ $97,900 - Almost there...
14:45:18 [FAST] 👀 BTC @ $98,100 - ABOVE NECKLINE!
14:45:18 [FAST] 📊 Checking volume... 2.1x average ✓
14:45:19 [FAST] ✅ BREAKOUT CONFIRMED!

14:45:20 [FAST] 🚀 OPEN LONG BTC @ $98,100
         ├─ Stop Loss: $93,500 (ATR-based)
         └─ Source: Double Bottom pattern

═══════════════════════════════════════════════════════════════════════════════
```

### Files Modified

| File | Changes |
|------|---------|
| `indicators.py` | Added `detect_double_bottom()`, `detect_double_top()` |
| `signal_scorer.py` | Added `WEIGHT_DOUBLE_BOTTOM`, `WEIGHT_DOUBLE_TOP`, pattern scoring |
| `sentinel.py` | Added pending entries system, contrary pattern detection, AI prompt update |
| `.env` | Added all `PATTERN_*` variables |

---

## Arena Trading Simulation System

### Overview

Arena è un sistema di simulazione che permette di testare diverse strategie e modelli AI **senza rischiare capitale reale**. Usa dati di mercato reali da HyperLiquid ma esegue trade solo in simulazione.

### Architettura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ARENA SYSTEM ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                  │
│   │   Variant   │     │   Variant   │     │   Variant   │                  │
│   │ V1_BASELINE │     │ V2_MULTI_AI │     │  V5_AI_FREE │                  │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                  │
│          │                   │                   │                          │
│          │           ┌───────┴───────┐           │                          │
│          │           │ Sub-Variants  │           │                          │
│          │           │ (one per AI)  │           │                          │
│          │           ├───────────────┤           │                          │
│          │           │ DeepSeek V3   │           │                          │
│          │           │ Grok          │           │                          │
│          │           │ Claude Haiku  │           │                          │
│          │           │ GPT-oss-120b  │           │                          │
│          │           │ Qwen3-Max     │           │                          │
│          │           │ Qwen3-Free    │           │                          │
│          │           └───────────────┘           │                          │
│          │                   │                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      SIMULATOR ENGINE                                │   │
│   │  ├─ SLOW LOOP (60s): Check entry signals                            │   │
│   │  └─ FAST LOOP (5s): Monitor positions, SL/TP                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      WEB DASHBOARD                                   │   │
│   │  ├─ Tab 1: AI Battle (equity curves, leaderboard)                   │   │
│   │  ├─ Tab 2: Strategies (variant comparison)                          │   │
│   │  └─ Tab 3: Positions (live P&L, manual close)                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interactive Dashboard Features

La dashboard web (porta 5050/5055) offre controlli interattivi in tempo reale:

#### Tab 1: AI Battle
- **Equity Curve**: Grafico comparativo delle performance di ogni AI model
- **Leaderboard**: Classifica AI per P&L totale
- **Toggle AI Models**: Attiva/disattiva singoli modelli AI dalla dashboard

#### Tab 2: Strategies
- **Strategy Comparison**: Grafico delle equity curve per variant
- **Performance Table**: Trades, Win Rate, P&L per ogni strategia
- **Toggle Variants**: Attiva/disattiva intere strategie

#### Tab 3: Positions
- **Live Positions**: Tutte le posizioni aperte con P&L real-time
- **Close Button**: Chiudi manualmente qualsiasi posizione
- **Recent Trades**: Storico delle ultime operazioni chiuse

#### Control Bar
- **Pause/Resume**: Ferma o riprendi la simulazione
- **Status Indicator**: LED che mostra stato (verde=running, giallo=paused)

### API Endpoints

```
POST /api/simulation/toggle     # Pause/Resume simulazione
POST /api/variant/<id>/toggle   # Toggle variant on/off
POST /api/model/<id>/toggle     # Toggle AI model on/off
POST /api/position/<id>/close   # Chiudi posizione manualmente
GET  /api/stats                 # Statistiche generali
GET  /api/leaderboard           # Classifica AI
GET  /api/costs                 # Statistiche chiamate API
```

### API Call Tracking

Il sistema traccia automaticamente:
- **api_calls**: Numero totale chiamate API per ogni AI model
- **api_errors**: Numero errori API (timeout, rate limit, etc.)

Visibile nella dashboard sotto ogni AI model card.

### Database Schema (arena/db.py)

```sql
-- Sub-variants with controls and tracking
CREATE TABLE arena_sub_variants (
    id TEXT PRIMARY KEY,
    variant_id TEXT NOT NULL,
    ai_model TEXT NOT NULL,
    ai_model_name TEXT,
    enabled INTEGER DEFAULT 1,        -- Toggle from dashboard
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    total_pnl_usd REAL DEFAULT 0.0,
    api_calls INTEGER DEFAULT 0,      -- API call tracking
    api_errors INTEGER DEFAULT 0,     -- Error tracking
    ...
);
```

### Modelli AI Configurati (V2_MULTI_AI Battle)

| AI Model | Provider | Note |
|----------|----------|------|
| `deepseek/deepseek-v3.2-speciale` | DeepSeek | Principale |
| `x-ai/grok-code-fast-1` | xAI | Grok veloce |
| `anthropic/claude-haiku-4.5` | Anthropic | Claude economico |
| `openai/gpt-oss-120b` | OpenAI | GPT open source |
| `qwen/qwen3-max` | Alibaba | Qwen premium |
| `qwen/qwen3-235b-a22b:free` | Alibaba | Qwen gratuito |

### Environment Variables (.env)

```bash
# ═══════════════════════════════════════════════════════════════════════════
# ARENA - Trading Simulation System
# ═══════════════════════════════════════════════════════════════════════════

# Master switch
ARENA_ENABLED=true

# Starting capital for equity tracking
ARENA_STARTING_CAPITAL=100

# Dashboard
ARENA_DASHBOARD_ENABLED=true
ARENA_DASHBOARD_PORT=5050

# Simulation intervals
ARENA_LOOP_INTERVAL=60        # Slow loop (entry signals)
ARENA_FAST_LOOP_INTERVAL=5    # Fast loop (position monitoring)

# AI API
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxx

# Optional: disable specific variants
# ARENA_DISABLED_VARIANTS=V5_AI_FREE,V4_INDICATOR_TEST
```

### Docker Deployment

```bash
# Build
docker build -t rizzo-arena -f Dockerfile.arena .

# Run
docker run -d \
  --name rizzo-arena \
  --env-file .env \
  -p 5055:5055 \
  rizzo-arena

# View logs
docker logs -f rizzo-arena

# Rebuild after updates
docker stop rizzo-arena && docker rm rizzo-arena
docker build -t rizzo-arena -f Dockerfile.arena .
docker run -d --name rizzo-arena --env-file .env -p 5055:5055 rizzo-arena
```

### Analytics Engine

Il sistema Arena include un motore di analisi automatico che:

1. **Analizza i dati ogni ora** (configurabile via `ARENA_ANALYTICS_INTERVAL`)
2. **Genera raccomandazioni** per migliorare il modello di produzione
3. **Mostra i risultati** nella tab "🎯 Analytics" della dashboard

#### Come funziona

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ANALYTICS ENGINE FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Every 1 hour (ARENA_ANALYTICS_INTERVAL):                                  │
│                                                                             │
│   1. COLLECT: Get all trades from last 24h                                  │
│   2. ANALYZE: Calculate per-AI-model statistics                             │
│   3. OPTIMIZE: Find optimal parameters (SL, leverage, etc.)                 │
│   4. RECOMMEND: Generate actionable recommendations                         │
│   5. DISPLAY: Show in dashboard "Analytics" tab                             │
│                                                                             │
│   Recommendations Types:                                                    │
│   ├─ 🔴 HIGH: Immediate action (disable losing AI, change SL)               │
│   ├─ 🟡 MEDIUM: Consider applying (parameter tweaks)                        │
│   └─ 🟢 LOW: Nice to have (minor optimizations)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Cosa analizza

| Metric | Descrizione |
|--------|-------------|
| **AI Rankings** | Classifica AI per P&L, win rate, profit factor |
| **Stop Loss** | Trova lo SL% ottimale basato sui trade storici |
| **Leverage** | Analizza quale leva produce i migliori risultati |
| **Best Variant** | Identifica la strategia più performante |

#### API Endpoints

```
GET  /api/analytics        # Ottieni analytics correnti
POST /api/analytics/run    # Forza esecuzione analisi
```

#### Environment Variables

```bash
# Analytics settings
ARENA_ANALYTICS_INTERVAL=3600    # Secondi tra analisi (default: 1 ora)
```

#### Esempio Output nei Log

```
📊 Running Arena Analytics...
============================================================
🎯 ARENA ANALYTICS - HIGH PRIORITY RECOMMENDATIONS
============================================================
  📌 Usa deepseek-v3.2-speciale come modello principale
     deepseek-v3.2-speciale ha il miglior P&L ($15.42)
     con win rate 68.0% su 25 trade.
     ➡️  Cambia: deepseek/deepseek-v3.2-speciale → deepseek/deepseek-v3.2-speciale

  📌 Disabilita gpt-oss-120b
     gpt-oss-120b sta perdendo $12.35 con win rate 35.0%.
     ➡️  Cambia: enabled → disabled

============================================================
📊 Analytics Report: AR_20251213_143000
   Trades analyzed: 87
   Total P&L: $24.50
   Best AI: deepseek/deepseek-v3.2-speciale
   Recommendations: 3
```

### Files Reference (Arena)

| File | Purpose |
|------|---------|
| `arena/main.py` | Entry point, avvia simulator e dashboard |
| `arena/simulator.py` | Engine simulazione (loop, trading logic) |
| `arena/dashboard.py` | Web dashboard Flask con controlli interattivi |
| `arena/db.py` | Database SQLite per trades, positions, stats |
| `arena/models.py` | Dataclass: Variant, SubVariant, Position, Trade |
| `arena/ai_manager.py` | Wrapper OpenRouter API con tracking |
| `arena/analytics.py` | Analytics engine per raccomandazioni |
| `arena/config_loader.py` | Carica variants da JSON |
| `arena/variants.json` | Configurazione varianti e AI models |
| `Dockerfile.arena` | Docker image per deployment |

---

*Last updated: December 2025*
