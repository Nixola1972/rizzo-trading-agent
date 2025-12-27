# CLAUDE.md - AI Prompt Architecture

---

## 🗂️ Project Structure & Branches

### Two Separate Deployments

Questo repository contiene **due sistemi di trading indipendenti** che girano su cartelle separate sul VPS:

| Progetto | Cartella VPS | Branch | Descrizione |
|----------|--------------|--------|-------------|
| **Rizzo/Botone** | `~/rizzo-trading-agent` | `main` | Bot di produzione con AI LLM (DeepSeek) |
| **AlphaTrader** | `~/alphatrader` | `claude/continue-latest-branch-Wvo2L` | Sistema RL ispirato ad AlphaGo |

### Rizzo/Botone (Production)

```
Cartella: ~/rizzo-trading-agent
Branch: main (o branch stabile di produzione)

Containers:
├─ rizzo_sentinel_slow   (entry logic)
├─ rizzo_sentinel_fast   (SL/TP monitoring)
├─ botone_v6_slow        (AI decisions)
├─ botone_v6_fast        (position monitoring)
└─ rizzo-arena           (simulazione)

Database: rizzo_trading, botone_baseline
Decisioni: AI LLM (DeepSeek via OpenRouter)
```

### AlphaTrader (Experimental)

```
Cartella: ~/alphatrader
Branch: claude/continue-latest-branch-Wvo2L

Containers:
├─ alpha_training        (training RL)
└─ alpha_trader          (paper/live trading)

Database: Nessuno (usa file pickle locali)
Decisioni: Neural Network + MCTS (locale, no API)
```

### Differenze Chiave

| Aspetto | Rizzo/Botone | AlphaTrader |
|---------|--------------|-------------|
| **Decisioni** | AI LLM (DeepSeek) | Neural Network |
| **Costo API** | $$ (chiamate OpenRouter) | $0 (tutto locale) |
| **Latenza** | 2-5 secondi | <100ms |
| **Apprendimento** | Nessuno (prompt fissi) | PPO Reinforcement Learning |
| **Validazione** | DOUBLE_CHECK AI | MCTS (Monte Carlo Tree Search) |
| **Maturità** | Produzione | Sperimentale |

### Setup Iniziale VPS

```bash
# 1. Rizzo/Botone (già esistente)
cd ~/rizzo-trading-agent
git checkout main
# ... già configurato

# 2. AlphaTrader (nuovo, separato)
cd ~
git clone -b claude/continue-latest-branch-Wvo2L \
  https://github.com/Nixola1972/rizzo-trading-agent.git alphatrader
cd ~/alphatrader
mkdir -p alpha/data alpha/checkpoints
docker build -t alphatrader -f Dockerfile.alpha .
```

### Aggiornamenti

```bash
# Aggiornare Rizzo/Botone
cd ~/rizzo-trading-agent
git pull origin main
docker-compose up -d --build

# Aggiornare AlphaTrader
cd ~/alphatrader
git pull origin claude/continue-latest-branch-Wvo2L
docker build --no-cache -t alphatrader -f Dockerfile.alpha .
```

---

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

# --- ACCELERATE Control ---
ACCELERATE_COOLDOWN_SECONDS=300         # Cooldown between ACCELERATE triggers (0=disabled)
ACCELERATE_MIN_PROFIT=0.0               # Min P&L% to trigger ACCELERATE (0=always, 1.5=only in profit)

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

### Modelli AI Configurati (V2_MULTI_AI Battle - Legacy)

| AI Model | Provider | Note |
|----------|----------|------|
| `deepseek/deepseek-v3.2-speciale` | DeepSeek | Principale |
| `x-ai/grok-code-fast-1` | xAI | Grok veloce |
| `anthropic/claude-haiku-4.5` | Anthropic | Claude economico |
| `openai/gpt-oss-120b` | OpenAI | GPT open source |
| `qwen/qwen3-max` | Alibaba | Qwen premium |
| `qwen/qwen3-235b-a22b:free` | Alibaba | Qwen gratuito |

### V6 AI Battle System (Attivo)

Il sistema V6 è la nuova architettura per testare AI models su diverse strategie e timeframe.

#### Varianti V6

| Variant | Timeframe | Stile | Descrizione |
|---------|-----------|-------|-------------|
| `V6_FAST_PRUDENT` | 5min | Prudente | Alta frequenza, basso rischio |
| `V6_FAST_MODERATE` | 5min | Moderato | Bilanciato |
| `V6_FAST_AGGRESSIVE` | 5min | Aggressivo | Alto rischio/rendimento |
| `V6_MEDIUM_PRUDENT` | 15min | Prudente | Medio termine, conservativo |
| `V6_MEDIUM_MODERATE` | 15min | Moderato | Approccio bilanciato |
| `V6_MEDIUM_AGGRESSIVE` | 15min | Aggressivo | Trend following aggressivo |
| `V6_MACRO_TREND` | 1h | Trend | Macro trend following |

#### Modelli AI V6 (8 per variante)

| AI Model | Provider | Note |
|----------|----------|------|
| `deepseek/deepseek-v3.2-exp` | DeepSeek | Principale, experimental |
| `tngtech/deepseek-r1t2-chimera:free` | DeepSeek | Gratuito |
| `z-ai/glm-4.6:exacto` | Z-AI | GLM Exacto |
| `deepseek/deepseek-chat` | DeepSeek | Chat model |
| `openai/gpt-oss-120b` | OpenAI | GPT open source |
| `qwen/qwen3-235b-a22b-2507` | Alibaba | Qwen premium 2507 |
| `x-ai/grok-4.1-fast` | xAI | Grok veloce |
| `moonshotai/kimi-k2-0905` | Moonshot | Kimi K2 |

#### Configurazione Default

- **Tutte le varianti disabilitate di default** - Attivazione manuale dalla dashboard
- **Toggle persistente nel database** - Le modifiche sopravvivono ai restart
- **Dashboard mostra**: Win Rate (W/L), API Calls, Errori per ogni modello

### Threading Architecture

Il simulator usa **thread separati e indipendenti** per FAST e SLOW loop:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DUAL-THREAD ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────┐   ┌─────────────────────────────┐        │
│   │     SLOW LOOP THREAD        │   │     FAST LOOP THREAD        │        │
│   ├─────────────────────────────┤   ├─────────────────────────────┤        │
│   │ • Ogni 60 secondi           │   │ • Ogni 5 secondi            │        │
│   │ • Calcola score             │   │ • Aggiorna prezzi           │        │
│   │ • Chiama AI (può bloccare   │   │ • Calcola P&L real-time     │        │
│   │   per 20-30s)               │   │ • Check SL/TP               │        │
│   │ • Apre nuove posizioni      │   │ • Trailing stop             │        │
│   │ • Analytics                 │   │ • Equity snapshots          │        │
│   └─────────────────────────────┘   └─────────────────────────────┘        │
│              │                                   │                          │
│              └───────────────┬───────────────────┘                          │
│                              │                                              │
│                   INDIPENDENTI (no blocking)                                │
│                                                                             │
│   Problema risolto:                                                         │
│   Prima: SLOW bloccava FAST → posizioni mostravano $0.00                    │
│   Ora: Thread separati → prezzi sempre aggiornati                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Implementazione (simulator.py)

```python
def start(self, blocking: bool = True) -> None:
    """Start simulation with separate threads for fast/slow loops."""
    if not blocking:
        # Non-blocking: start both loops in separate threads
        self._fast_thread = threading.Thread(target=self._run_fast_loop, daemon=True)
        self._slow_thread = threading.Thread(target=self._run_slow_loop, daemon=True)
        self._fast_thread.start()
        self._slow_thread.start()
```

### Toggle State Persistence

I toggle dei modelli AI ora **salvano nel database SQLite**, non nel file JSON:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOGGLE PERSISTENCE FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. Utente clicca toggle nella dashboard                                   │
│      └─ POST /api/v6/model/toggle { family: "FAST", model_id: "...", ... }  │
│                                                                             │
│   2. API chiama db.toggle_sub_variant(sub_variant_id, enabled)              │
│      └─ UPDATE arena_sub_variants SET enabled = ? WHERE id = ?              │
│                                                                             │
│   3. Al refresh pagina, get_v6_model_controls() legge dal DB                │
│      └─ SELECT enabled FROM arena_sub_variants WHERE id = ?                 │
│                                                                             │
│   Risultato: Toggle persistente anche dopo restart container                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dashboard V6 Features

La dashboard V6 mostra statistiche dettagliate per ogni modello AI:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🤖 V6 AI Model Controls                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  V6 Fast (5min) - High frequency trading                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  deepseek-v3.2-speciale    [ON]                                      │   │
│  │  25 trades | 68.0% WR                                                │   │
│  │  📊 WR: 68.0% (17W / 8L) | 📞 API: 142 | ❌ Err: 2                    │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  claude-haiku-4.5          [OFF]                                     │   │
│  │  18 trades | 55.5% WR                                                │   │
│  │  📊 WR: 55.5% (10W / 8L) | 📞 API: 98 | ❌ Err: 0                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  V6 Leaderboard                                                             │
│  ┌───────┬──────────────────────┬────────┬────────┬─────────┬───────────┐   │
│  │ Rank  │ AI Model             │ Trades │ W/L    │ P&L     │ API Calls │   │
│  ├───────┼──────────────────────┼────────┼────────┼─────────┼───────────┤   │
│  │ 🥇 1  │ deepseek-v3.2        │ 25     │ 17/8   │ +$15.42 │ 142       │   │
│  │ 🥈 2  │ qwen3-max            │ 22     │ 14/8   │ +$8.75  │ 120       │   │
│  │ 🥉 3  │ grok-4.1-fast        │ 20     │ 11/9   │ +$3.20  │ 105       │   │
│  └───────┴──────────────────────┴────────┴────────┴─────────┴───────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

### Detailed Analytics (Fee Tracking)

Il sistema calcola automaticamente le trading fees e fornisce breakdown dettagliati per analisi.

#### Calcolo Fees

```
Fee = Volume × 0.000432 (0.0432% taker fee)
Volume = Position Size × Leverage × 2 (open + close)

Esempio:
- Position: $25 USD
- Leverage: 5x
- Volume: $25 × 5 × 2 = $250
- Fee: $250 × 0.000432 = $0.108

Per ogni trade il sistema salva:
- fee_usd: Trading fees (USD)
- net_pnl_usd: P&L netto dopo fees
- duration_seconds: Durata del trade
```

#### API Endpoint

```
GET /api/analytics/detailed?hours=24
```

Restituisce breakdown per:
- **by_model**: Aggregato per AI Model
- **by_style**: Per stile trading (PRUDENT, MODERATE, AGGRESSIVE)
- **by_timeframe**: Per timeframe (FAST, MEDIUM, MACRO)
- **by_model_style**: Matrice Model × Style
- **by_model_style_timeframe**: Matrice completa Model × Style × Timeframe
- **totals**: Totali globali

Ogni breakdown include:
- trades, wins, losses
- gross_pnl_usd, total_fees_usd, net_pnl_usd
- win_rate, avg_pnl_pct, avg_duration_min

#### Dashboard Section

Nella tab "🎯 Analytics" è stata aggiunta la sezione "📊 Detailed Breakdown (with Fees)" che mostra:

1. **Summary**: Totali con Gross P&L, Fees, Net P&L
2. **Per AI Model**: Tabella con tutte le metriche per modello
3. **Per Stile**: PRUDENT 🛡️, MODERATE ⚖️, AGGRESSIVE 🔥
4. **Per Timeframe**: FAST ⚡, MEDIUM 🕐, MACRO 📊
5. **Matrice Model × Stile**: Espandibile con click

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

## Infrastructure & Database Configuration

### PostgreSQL Database

Il sistema usa PostgreSQL per la persistenza dei dati. Il database gira in un container Docker.

#### Container Info

```
Container Name: memory_postgres
Image: postgres:16-alpine
Port: 5433:5432 (host:container)
Network: unified-memory-stack_memory-net
```

#### Users & Permissions

| User | Role | Permissions |
|------|------|-------------|
| `memory_user` | Superuser | CREATE DB, Replication, Bypass RLS |
| `tradingbot` | Application user | Standard access |

#### Databases

| Database | Owner | Purpose |
|----------|-------|---------|
| `rizzo_trading` | tradingbot | Bot di produzione (Rizzo) |
| `botone_baseline` | tradingbot | Bot baseline (Botone) |
| `unified_memory` | memory_user | Sistema memoria AI |

#### Comandi Utili

```bash
# Connetti al database
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading

# Lista database
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "\l"

# Lista utenti/ruoli
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "\du"

# Crea nuovo database (usa superuser)
docker exec -it memory_postgres psql -U memory_user -d postgres -c "CREATE DATABASE nome_db OWNER tradingbot;"
```

---

## Database Schema & Trade Tracking

### Tabelle Principali per Trade

Ci sono **due sistemi** di tracking trade separati:

| Tabella | Bot | File | Scopo |
|---------|-----|------|-------|
| `trades` | Rizzo | `trade_journal.py` | Trade tracking completo per Rizzo |
| `botone_trades` | Botone V6 | `botone_v6_db.py` | Trade tracking per Botone V6 |

### Schema `botone_trades` (Botone V6)

```sql
CREATE TABLE botone_trades (
    id SERIAL PRIMARY KEY,

    -- Basic Info
    symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(5) NOT NULL,           -- LONG / SHORT
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Prices
    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8),
    size_usd DECIMAL(10,2),
    leverage INTEGER,

    -- P&L
    pnl_usd DECIMAL(10,4),
    pnl_pct DECIMAL(8,4),

    -- MFE/MAE (Max Favorable/Adverse Excursion)
    max_price DECIMAL(20,8),                 -- Updated by FAST loop
    min_price DECIMAL(20,8),                 -- Updated by FAST loop
    mfe_pct DECIMAL(8,4),                    -- Calculated at close
    mae_pct DECIMAL(8,4),                    -- Calculated at close

    -- AI Decision at Entry
    conviction_tier INTEGER,                 -- 1=Speculativo, 2=Standard, 3=High
    ai_confidence DECIMAL(5,4),              -- 0.0 - 1.0
    ai_reasoning TEXT,                       -- Full AI explanation
    prompt_style VARCHAR(20),                -- PRUDENT/MODERATE/AGGRESSIVE

    -- Indicators at Entry (saved by SLOW loop)
    entry_macd DECIMAL(12,6),
    entry_rsi DECIMAL(6,2),
    entry_adx DECIMAL(6,2),
    entry_ema_stack VARCHAR(20),             -- bullish/bearish/neutral
    entry_volume_ratio DECIMAL(6,3),
    entry_bb_position VARCHAR(20),           -- UPPER/MIDDLE/LOWER
    entry_bb_squeeze BOOLEAN,
    entry_obv_trend VARCHAR(10),             -- RISING/FALLING/FLAT
    entry_funding_rate DECIMAL(12,8),
    entry_open_interest DECIMAL(20,2),
    entry_fear_greed INTEGER,
    entry_price_vs_pivot VARCHAR(30),

    -- Pattern Detection at Entry
    entry_double_bottom BOOLEAN DEFAULT FALSE,
    entry_double_top BOOLEAN DEFAULT FALSE,
    entry_pattern_confidence DECIMAL(5,4),

    -- Exit Info
    exit_reason VARCHAR(30),                 -- SL_HIT, TP_HIT, TRAILING_SL, AI_CLOSE, etc.
    trailing_level_pct DECIMAL(6,3),
    sl_price DECIMAL(20,8),
    tp_price DECIMAL(20,8),

    -- Metadata
    bot_name VARCHAR(50) DEFAULT 'botone-v6',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Chi Salva Cosa

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE WRITE FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   SLOW LOOP (ogni N minuti)                                                 │
│   ├─ save_trade_entry()                                                     │
│   │   └─ Salva: symbol, direction, entry_price, size, leverage,             │
│   │            conviction_tier, ai_confidence, ai_reasoning,                │
│   │            TUTTI gli indicatori (MACD, RSI, ADX, EMA, BB, OBV...)       │
│   │                                                                         │
│   └─ Può chiamare close_trade() se AI decide di chiudere                    │
│                                                                             │
│   FAST LOOP (ogni 5 secondi)                                                │
│   ├─ update_mfe_mae()                                                       │
│   │   └─ Aggiorna: max_price, min_price (per MFE/MAE tracking)              │
│   │                                                                         │
│   └─ close_trade()                                                          │
│       └─ Salva: closed_at, exit_price, pnl_usd, pnl_pct,                    │
│                mfe_pct, mae_pct, exit_reason, trailing_level_pct,           │
│                duration_seconds                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MFE/MAE Tracking

**MFE** (Max Favorable Excursion) = Massimo profitto raggiunto durante il trade
**MAE** (Max Adverse Excursion) = Massima perdita raggiunta durante il trade

```
Esempio LONG:
- Entry: $100
- Durante il trade: min=$98, max=$105
- MFE = +5% (quanto potevi guadagnare)
- MAE = -2% (quanto hai rischiato)

Esempio SHORT:
- Entry: $100
- Durante il trade: min=$95, max=$102
- MFE = +5% (profitto se chiuso al minimo)
- MAE = -2% (perdita se chiuso al massimo)
```

### Exit Reasons

| Reason | Descrizione | Chi lo trigga |
|--------|-------------|---------------|
| `SL_HIT` | Stop Loss raggiunto | FAST loop |
| `TP_HIT` | Take Profit raggiunto | FAST loop |
| `TRAILING_SL` | Trailing Stop Loss attivato | FAST loop |
| `AI_CLOSE` | AI ha deciso di chiudere | SLOW loop |
| `TIMEOUT` | Posizione aperta troppo a lungo | FAST loop |
| `HEALTH_EXIT` | Health Check ha forzato uscita | FAST loop |
| `BTC_WATCHDOG` | BTC Watchdog ha protetto | FAST loop |
| `MANUAL` | Chiusura manuale | Dashboard/API |

### Schema `trades` (Rizzo)

```sql
CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    trade_uuid UUID NOT NULL UNIQUE,

    -- Identification
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    trading_mode TEXT NOT NULL,              -- MICRO_GAIN / NORMAL
    status TEXT NOT NULL DEFAULT 'OPEN',

    -- Timestamps
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    duration_seconds INTEGER,

    -- Prices & Size
    entry_price NUMERIC(30,10) NOT NULL,
    exit_price NUMERIC(30,10),
    size NUMERIC(30,10) NOT NULL,
    leverage INTEGER DEFAULT 1,
    notional_value NUMERIC(30,10),
    margin_used NUMERIC(30,10),

    -- P&L
    pnl_percent NUMERIC(10,4),
    pnl_usd NUMERIC(20,8),
    net_pnl_usd NUMERIC(20,8),               -- After fees
    net_pnl_percent NUMERIC(10,4),
    profitable BOOLEAN,

    -- Fees
    fee_open NUMERIC(20,8),
    fee_close NUMERIC(20,8),
    fee_funding NUMERIC(20,8),
    fee_total NUMERIC(20,8),

    -- Source
    open_source TEXT,                        -- MICRO_GAIN_AUTO, AI_DECISION, MANUAL
    close_reason TEXT,                       -- TP_HIT, SL_HIT, TRAILING_SL, etc.

    -- Indicators at open
    open_score NUMERIC(10,2),
    open_rsi NUMERIC(10,4),
    open_macd NUMERIC(20,8),
    open_fg INTEGER,                         -- Fear & Greed
    open_volume_ratio NUMERIC(10,4),

    -- Peak tracking
    peak_price NUMERIC(30,10),
    peak_pnl_percent NUMERIC(10,4),

    -- Config used
    sl_percent_config NUMERIC(10,4),
    tp_percent_config NUMERIC(10,4),
    trailing_activation NUMERIC(10,4),
    trailing_gap NUMERIC(10,4),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);
```

### Altre Tabelle Utili

| Tabella | Scopo |
|---------|-------|
| `signal_scores` | Storico score calcolati per ogni symbol |
| `sentinel_logs` | Log delle azioni del Sentinel |
| `position_tracking` | Stato attuale delle posizioni (usato per coordinare SLOW/FAST) |
| `ai_prompt_logs` | Log completo prompt/risposta AI per debug |
| `trade_events` | Ogni singola modifica su un trade (cambio SL, trailing, etc.) |
| `errors` | Log errori per debugging |

### Query Utili per Analisi

```bash
# Ultimi 10 trade chiusi con P&L
docker exec -it memory_postgres psql -U tradingbot -d botone_baseline -c "
SELECT id, symbol, direction,
       ROUND(pnl_pct::numeric, 2) as pnl_pct,
       ROUND(mfe_pct::numeric, 2) as mfe_pct,
       ROUND(mae_pct::numeric, 2) as mae_pct,
       exit_reason
FROM botone_trades
WHERE closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 10;"

# Win rate per symbol
docker exec -it memory_postgres psql -U tradingbot -d botone_baseline -c "
SELECT symbol,
       COUNT(*) as trades,
       COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) as wins,
       ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
       ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY symbol
ORDER BY total_pnl DESC;"

# Profitti sprecati (MFE alto ma chiuso in perdita)
docker exec -it memory_postgres psql -U tradingbot -d botone_baseline -c "
SELECT id, symbol, direction,
       ROUND(mfe_pct::numeric, 2) as max_profit,
       ROUND(pnl_pct::numeric, 2) as actual_pnl,
       exit_reason
FROM botone_trades
WHERE closed_at IS NOT NULL
  AND pnl_usd < 0
  AND mfe_pct > 1.0
ORDER BY mfe_pct DESC;"

# Performance per exit_reason
docker exec -it memory_postgres psql -U tradingbot -d botone_baseline -c "
SELECT exit_reason,
       COUNT(*) as count,
       ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
       ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY exit_reason
ORDER BY count DESC;"
```

### Script di Analisi

```bash
# Analisi completa Botone V6 trades
python3 analyze_botone_trades.py

# Analisi Rizzo trades (usa tabella `trades`)
python3 analyze_trades.py

# Nota: eseguire dallo host con DATABASE_URL modificato
DATABASE_URL='postgresql://tradingbot:BotoneDB2025@localhost:5433/botone_baseline' python3 analyze_botone_trades.py
```

---

## Production Bots

### Rizzo (Production Bot)

Bot principale in produzione con configurazione ottimizzata.

```
Containers:
├─ rizzo_sentinel_slow  (entry logic, ogni 60s)
├─ rizzo_sentinel_fast  (monitoring SL/TP, ogni 5s)
├─ rizzo_main           (main.py loop)
├─ rizzo_dashboard      (Streamlit UI, porta 8501)
└─ rizzo-arena          (Simulazione, porta 5055)

Database: rizzo_trading
HyperLiquid: Account principale
```

### Botone-Baseline (Baseline Bot)

Bot separato che replica la strategia V1_BASELINE dell'Arena per test in produzione reale.

```
Containers:
├─ botone_baseline_slow  (entry logic)
└─ botone_baseline_fast  (monitoring)

Database: botone_baseline
HyperLiquid: Sub-account dedicato (separato da Rizzo)
```

#### Configurazione Botone (.env.baseline)

```bash
# ═══════════════════════════════════════════════════════════════════════════
# BOTONE-BASELINE CONFIGURATION
# Replica la strategia V1_BASELINE dell'Arena
# ═══════════════════════════════════════════════════════════════════════════

# --- Bot Identity ---
BOT_NAME=botone-baseline

# --- API Keys ---
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_MODEL=deepseek/deepseek-v3.2-speciale

# --- HyperLiquid (SUB-ACCOUNT DEDICATO) ---
HL_PRIVATE_KEY=0xYourSubAccountPrivateKey
HL_ACCOUNT_ADDRESS=0xYourSubAccountAddress

# --- Database (SEPARATO da Rizzo) ---
DATABASE_URL=postgresql://tradingbot:TradingBot2025!Secure@memory_postgres:5432/botone_baseline

# --- Trading Parameters (V1_BASELINE) ---
SCORE_THRESHOLD_OPEN=15
TRADING_STYLE=moderate
DOUBLE_CHECK_AI_ENABLED=true

# --- Trailing Stop Esteso (fino al 40%) ---
TRAILING_STEPS=2.5:0.0,3.5:1.0,4.5:1.5,5.0:2.0,6.0:3.0,7.5:4.5,8.5:5.5,10.0:7.0,12.5:9.5,15.0:12.0,17.5:14.0,20.0:16.0,25.0:21.0,30.0:26.0,35.0:31.0,40.0:36.0
TAKE_PROFIT_ENABLED=false

# --- Position Sizing ---
POSITION_SIZE_USD=10
LEVERAGE=5
```

#### Trailing Stop Steps Spiegazione

```
Formato: PROFIT%:LOCK%

2.5:0.0   → A +2.5% profit, SL a breakeven (0%)
3.5:1.0   → A +3.5% profit, lock +1.0%
4.5:1.5   → A +4.5% profit, lock +1.5%
5.0:2.0   → A +5.0% profit, lock +2.0%
6.0:3.0   → A +6.0% profit, lock +3.0%
7.5:4.5   → A +7.5% profit, lock +4.5%
8.5:5.5   → A +8.5% profit, lock +5.5%
10.0:7.0  → A +10% profit, lock +7.0%
12.5:9.5  → A +12.5% profit, lock +9.5%
15.0:12.0 → A +15% profit, lock +12%
17.5:14.0 → A +17.5% profit, lock +14%
20.0:16.0 → A +20% profit, lock +16%
25.0:21.0 → A +25% profit, lock +21%
30.0:26.0 → A +30% profit, lock +26%
35.0:31.0 → A +35% profit, lock +31%
40.0:36.0 → A +40% profit, lock +36%
```

#### Setup Botone-Baseline

```bash
# 1. Crea database
docker exec -it memory_postgres psql -U memory_user -d postgres -c "CREATE DATABASE botone_baseline OWNER tradingbot;"

# 2. Pull codice
cd ~/trading-bots/rizzo-trading-agent
git pull origin claude/project-expansion-discussion-e6H5a

# 3. Crea e configura .env.baseline
cp .env.baseline.template .env.baseline
nano .env.baseline  # Inserisci le tue credenziali

# 4. Build immagine
docker build -t botone-baseline -f Dockerfile .

# 5. Avvia SLOW container
docker run -d \
  --name botone_baseline_slow \
  --env-file .env.baseline \
  -e PYTHONUNBUFFERED=1 \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  --entrypoint python \
  botone-baseline \
  sentinel.py --mode slow --loop

# 6. Avvia FAST container
docker run -d \
  --name botone_baseline_fast \
  --env-file .env.baseline \
  -e PYTHONUNBUFFERED=1 \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  --entrypoint python \
  botone-baseline \
  sentinel.py --mode fast --loop

# 7. Verifica
docker ps | grep botone
docker logs -f botone_baseline_slow --tail 50
```

#### Architettura SLOW + FAST

```
┌─────────────────────────────────────────────────────────────────┐
│                 BOTONE-BASELINE ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────┐     ┌─────────────────────┐           │
│   │  botone_baseline_   │     │  botone_baseline_   │           │
│   │       SLOW          │     │       FAST          │           │
│   ├─────────────────────┤     ├─────────────────────┤           │
│   │ • Ogni 60 secondi   │     │ • Ogni 5 secondi    │           │
│   │ • Calcola score     │     │ • Legge posizioni   │           │
│   │ • Chiama AI         │     │ • Check SL/TP       │           │
│   │ • APRE posizioni    │     │ • Trailing stop     │           │
│   │                     │     │ • CHIUDE posizioni  │           │
│   └──────────┬──────────┘     └──────────┬──────────┘           │
│              │                           │                       │
│              └─────────────┬─────────────┘                       │
│                            │                                     │
│                            ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              SHARED RESOURCES                            │   │
│   │  ├─ PostgreSQL: botone_baseline                         │   │
│   │  └─ HyperLiquid: Sub-account dedicato                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   I due container si COORDINANO attraverso il database:          │
│   • SLOW scrive nuove posizioni → FAST le monitora               │
│   • Non si ostacolano perché leggono/scrivono dati diversi       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Differenze Rizzo vs Botone

| Aspetto | Rizzo (Produzione) | Botone (Baseline) |
|---------|-------------------|-------------------|
| Score Threshold | 45 | 15 |
| Trading Style | Varia | moderate |
| Trailing Steps | Standard | Esteso (fino 40%) |
| Take Profit | Configurabile | Disabilitato |
| Database | rizzo_trading | botone_baseline |
| HL Account | Principale | Sub-account |

---

### Botone V6 (Production Bot)

Bot di produzione che usa l'architettura V6 con AI decision-making avanzato e set completo di indicatori.

```
Containers:
├─ botone_v6_slow  (AI decisions, ogni N minuti)
└─ botone_v6_fast  (position monitoring, ogni 5s)

Script: botone_v6.py
Image: botone-v6:latest
Database: botone_baseline (condiviso)
HyperLiquid: Sub-account dedicato
```

#### Indicatori Passati all'AI

Botone V6 passa ALL indicatori disponibili all'AI per massimizzare il contesto:

| Categoria | Indicatori |
|-----------|------------|
| **Momentum** | MACD (valore + segnale), RSI (14 periodi) |
| **Trend** | ADX (forza trend), EMA Stack (EMA20 vs EMA50 vs Price) |
| **Volatilità** | ATR (14 periodi), Bollinger Bands (position, %B, bandwidth, squeeze) |
| **Volume** | OBV Trend (rising/falling), Volume Ratio (vs average) |
| **Support/Resistance** | Pivot Points (R2, R1, PP, S1, S2) |
| **Derivatives** | Funding Rate, Open Interest (+ change 24h) |
| **Patterns** | Double Bottom, Double Top (con confidence) |
| **Sentiment** | Fear & Greed Index |

#### Confidence Breakdown

L'AI deve spiegare COME ha calcolato la confidence, indicando il contributo di ogni indicatore:

```json
{
  "action": "open",
  "direction": "LONG",
  "leverage": 3,
  "confidence": 0.82,
  "reason": "Strong bullish momentum with volume confirmation",
  "confidence_breakdown": {
    "MACD": "+15% (0.25 strong bullish)",
    "EMA": "+12% (price above both EMAs)",
    "OBV": "+10% (rising, confirms buyers)",
    "ADX": "+8% (28 = strong trend)",
    "Pivot": "+5% (above PP, heading to R1)",
    "Patterns": "+0% (none detected)",
    "RSI": "-5% (62 = approaching overbought)",
    "Bollinger": "-3% (near upper band)",
    "Funding": "-2% (slightly crowded long)",
    "OI": "+2% (rising with price)"
  },
  "key_factors": ["MACD", "EMA", "OBV"],
  "warnings": ["RSI approaching overbought zone"]
}
```

Questo permette di:
- Capire quali indicatori l'AI pesa di più
- Identificare pattern nelle decisioni
- Debug di trade sbagliati
- Ottimizzazione futura dei pesi

#### Configurazione Botone V6 (.env.baseline)

```bash
# ═══════════════════════════════════════════════════════════════════════════
# BOTONE V6 CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# --- Bot Identity ---
BOT_NAME=botone-v6

# --- API Keys ---
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_MODEL=deepseek/deepseek-chat

# --- HyperLiquid (SUB-ACCOUNT DEDICATO) ---
HL_PRIVATE_KEY=0xYourSubAccountPrivateKey
HL_ACCOUNT_ADDRESS=0xYourSubAccountAddress

# --- Database ---
DATABASE_URL=postgresql://tradingbot:TradingBot2025!Secure@memory_postgres:5432/botone_baseline

# --- V6 Prompt Style ---
V6_PROMPT_STYLE=MODERATE          # PRUDENT, MODERATE, AGGRESSIVE, MACRO

# --- AI Settings ---
AI_INTERVAL_MINUTES=5             # Frequenza chiamate AI
MIN_PROFIT_TO_CLOSE=1.5           # Min profit % per chiusura AI
AI_LOSS_THRESHOLD_PCT=50          # AI può chiudere se loss > X% dello SL

# --- Leverage per Style ---
MAX_LEVERAGE=5
LEVERAGE_PRUDENT_MAX=3
LEVERAGE_MODERATE_MAX=5
LEVERAGE_AGGRESSIVE_MIN=5
LEVERAGE_MACRO_MAX=2

# --- Position Sizing ---
POSITION_SIZE_USD=25
STOP_LOSS_PCT=10

# --- Trailing Stop ---
TRAILING_STEPS=2.0:0.0,3.0:1.0,4.0:2.0,5.0:3.0,7.0:5.0,10.0:7.0,15.0:12.0,20.0:16.0

# --- Symbols ---
SYMBOLS=BTC,ETH,SOL

# --- Logging ---
VERBOSE_LOGGING=true              # Mostra tutti gli indicatori nei log
```

#### Deploy Botone V6

```bash
# 1. Pull delle modifiche
cd /root/trading-bots/rizzo-trading-agent
git pull origin claude/project-expansion-discussion-e6H5a

# 2. Stop e rimuovi containers esistenti
docker stop botone_v6_slow botone_v6_fast
docker rm botone_v6_slow botone_v6_fast

# 3. Rebuild immagine
docker build -t botone-v6 -f Dockerfile .

# 4. Avvia FAST (monitoring)
docker run -d \
  --name botone_v6_fast \
  --env-file /root/trading-bots/rizzo-trading-agent/.env.baseline \
  -e PYTHONUNBUFFERED=1 \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  --entrypoint python \
  botone-v6:latest \
  botone_v6.py --mode fast --loop

# 5. Avvia SLOW (AI decisions)
docker run -d \
  --name botone_v6_slow \
  --env-file /root/trading-bots/rizzo-trading-agent/.env.baseline \
  -e PYTHONUNBUFFERED=1 \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  --entrypoint python \
  botone-v6:latest \
  botone_v6.py --mode slow --loop

# 6. Verifica
docker ps | grep botone_v6
docker logs -f botone_v6_slow --tail 50
```

#### Architettura Botone V6

```
┌─────────────────────────────────────────────────────────────────┐
│                     BOTONE V6 ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────┐     ┌─────────────────────┐           │
│   │   botone_v6_slow    │     │   botone_v6_fast    │           │
│   ├─────────────────────┤     ├─────────────────────┤           │
│   │ • Ogni N minuti     │     │ • Ogni 5 secondi    │           │
│   │ • Fetch indicatori  │     │ • Update prezzi     │           │
│   │ • Chiama AI         │     │ • Check SL/TP       │           │
│   │ • APRE posizioni    │     │ • Trailing stop     │           │
│   │ • Può CHIUDERE      │     │ • CHIUDE posizioni  │           │
│   │   (profit/loss-cut) │     │                     │           │
│   └──────────┬──────────┘     └──────────┬──────────┘           │
│              │                           │                       │
│              │    THREAD INDIPENDENTI    │                       │
│              │    (non si bloccano)      │                       │
│              └─────────────┬─────────────┘                       │
│                            │                                     │
│                            ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              INDICATORI PASSATI ALL'AI                   │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │  MACD, RSI, ADX, EMA Stack, ATR                         │   │
│   │  Bollinger Bands (position, %B, bandwidth, squeeze)      │   │
│   │  OBV Trend, Volume Ratio                                 │   │
│   │  Pivot Points (R2, R1, PP, S1, S2)                       │   │
│   │  Funding Rate, Open Interest                             │   │
│   │  Double Bottom/Top Patterns                              │   │
│   │  Fear & Greed Index                                      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              AI OUTPUT con BREAKDOWN                     │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │  {                                                       │   │
│   │    "action": "open",                                     │   │
│   │    "confidence": 0.82,                                   │   │
│   │    "confidence_breakdown": {                             │   │
│   │      "MACD": "+15%",                                     │   │
│   │      "RSI": "-5%",                                       │   │
│   │      ...                                                 │   │
│   │    }                                                     │   │
│   │  }                                                       │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### AI Close Logic

L'AI in SLOW loop può chiudere posizioni in due casi:

1. **Profit Taking**: P&L >= MIN_PROFIT_TO_CLOSE (default 1.5%)
2. **Loss Cutting**: Perdita >= AI_LOSS_THRESHOLD_PCT% dello SL (default 50%)

Esempio con SL=10% e AI_LOSS_THRESHOLD_PCT=50:
- AI può chiudere se loss >= 5% (50% di 10%)
- Permette all'AI di tagliare perdite "intelligentemente" prima dello SL

#### Log Output Esempio

```
[SLOW] BTC: === MARKET DATA ===
  Price: $97,500.00
  MACD: 0.1850
  RSI: 58.0
  ADX: 28.5
  EMA Stack: bullish (price > EMA20 > EMA50)
  ATR: 850.00 (normal)
  Bollinger: UPPER_HALF | %B=0.72 | Squeeze=no
  OBV Trend: rising
  Pivot Points: R2=$99,500 R1=$98,200 PP=$97,000 S1=$95,800 S2=$94,500
  Volume Ratio: 1.25x
  Funding Rate: 0.0080%
  Open Interest: $1,250,000,000

[SLOW] BTC: Calling AI (MODERATE)...
[SLOW] BTC: AI Decision: OPEN LONG | Conf: 82% | Lev: 3x
  Strong bullish momentum | BREAKDOWN: MACD: +15% | EMA: +12% | OBV: +10% | ADX: +8% | RSI: -5% | Bollinger: -3%
  KEY: MACD, EMA, OBV
  ⚠️ WARNINGS: Approaching R1 resistance

[TRADE] Opening LONG on BTC @ $97,500.00 lev=3x
[TRADE] ✅ Position opened successfully
[TRADE] 📍 Setting SL at $94,575.00 (3.0% below entry)
```

---

## HEALTH Check System (Smart Exit)

### Overview

Il sistema HEALTH Check monitora continuamente le posizioni aperte e prende azioni protettive basate su uno **score di salute** calcolato dagli indicatori di mercato.

### Architettura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HEALTH CHECK FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   FAST LOOP (ogni 5-30 secondi)                                             │
│   │                                                                         │
│   ├─→ Per ogni posizione aperta:                                            │
│   │   │                                                                     │
│   │   ├─→ 1. GRACE PERIOD CHECK                                             │
│   │   │   └─ Se posizione < HEALTH_GRACE_PERIOD_MINUTES → SKIP              │
│   │   │                                                                     │
│   │   ├─→ 2. CALCOLA SCORE da indicatori                                    │
│   │   │   ├─ EMA Stack: favorevole/contrario                                │
│   │   │   ├─ RSI: favorevole/contrario                                      │
│   │   │   ├─ MACD: favorevole/contrario                                     │
│   │   │   ├─ Volume: buono/basso                                            │
│   │   │   ├─ Bollinger: favorevole/squeeze                                  │
│   │   │   ├─ OBV: allineato/contrario                                       │
│   │   │   └─ Time Decay: penalità se in perdita da ore                      │
│   │   │                                                                     │
│   │   └─→ 3. AZIONE basata su score                                         │
│   │       ├─ HEALTHY (>= 2): Nessuna azione                                 │
│   │       ├─ CAUTION (0-1): Stringi SL se in profitto                       │
│   │       ├─ DANGER (-3 a -1): SL a breakeven                               │
│   │       └─ EMERGENCY (< -4): Chiudi se in profitto                        │
│   │                                                                         │
│   └─→ Log: [HEALTH] BTC: Score 3 ✅ HEALTHY | EMA:+2 | RSI:0 | MACD:+1...   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Grace Period

**Problema risolto**: L'AI apriva una posizione e HEALTH la chiudeva immediatamente perché gli indicatori davano score basso.

**Soluzione**: `HEALTH_GRACE_PERIOD_MINUTES` (default: 5 minuti) impedisce a HEALTH di intervenire su posizioni troppo nuove, dando tempo alla decisione AI di "giocarsi".

```python
# Se posizione ha meno di 5 minuti, HEALTH non interviene
if position_age_minutes < config.health_grace_period_minutes:
    logger.info(f"[HEALTH] {symbol}: ⏳ Grace period - skipping")
    continue
```

### Score Calculation (Pesi Configurabili)

Ogni indicatore contribuisce allo score con pesi configurabili via `.env`:

| Indicatore | Favorevole | Neutro | Contrario | Env Variable |
|------------|------------|--------|-----------|--------------|
| **EMA Stack** | +2 | 0 | -2 | `HEALTH_WEIGHT_EMA_POS/NEG` |
| **RSI** | +1 | 0 | -1 | `HEALTH_WEIGHT_RSI_POS/NEG` |
| **MACD** | +1 | 0 | -1 | `HEALTH_WEIGHT_MACD_POS/NEG` |
| **Volume** | +1 | 0 | -1 | `HEALTH_WEIGHT_VOL_POS/NEG` |
| **Bollinger** | +1 | 0 | -1 | `HEALTH_WEIGHT_BB_POS/NEG` |
| **BB Squeeze** | - | - | -1 | `HEALTH_WEIGHT_BB_SQUEEZE` |
| **OBV** | +1 | 0 | -1 | `HEALTH_WEIGHT_OBV_POS/NEG` |
| **Time (loss)** | - | 0 | -1/-2/-3 | `HEALTH_WEIGHT_TIME_*` |
| **Resilience** | +1 | - | - | `HEALTH_WEIGHT_RESILIENCE` |

**Range Score**: da **-9** (tutto contro) a **+9** (tutto favorevole)

### Condizioni Indicatori

| Indicatore | Favorevole (LONG) | Contrario (LONG) |
|------------|-------------------|------------------|
| EMA Stack | "bullish" | "bearish" |
| RSI | > 50 | < 40 |
| MACD | > +0.1 | < -0.1 |
| Volume | > 0.8x | < 0.3x |
| Bollinger | UPPER zone | LOWER zone |
| OBV | RISING | FALLING |

*Per SHORT, le condizioni sono invertite.*

### Time Decay

Penalità progressiva per posizioni in **perdita** da troppo tempo:

| Ore Aperta | Penalità | Env Variable |
|------------|----------|--------------|
| >= 4h | -1 | `HEALTH_TIME_DECAY_START` |
| >= 8h | -2 | `HEALTH_TIME_DECAY_MEDIUM` |
| >= 12h | -3 | `HEALTH_TIME_DECAY_SEVERE` |

**Nota**: Il time decay si applica SOLO se P&L <= 0. Se in profitto, nessuna penalità (anzi, bonus resilienza +1 se profit > 2%).

### Thresholds e Azioni

| Score | Status | Azione | Condizione |
|-------|--------|--------|------------|
| >= 2 | ✅ HEALTHY | Nessuna | - |
| 0-1 | ⚠️ CAUTION | Stringi SL | P&L >= 0.5% |
| -3 a -1 | 🔶 DANGER | SL a breakeven | P&L >= 0% |
| < -4 | 🔴 EMERGENCY | Chiudi posizione | P&L >= 0.5% |

### Configurazione Completa (.env)

```bash
# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK SYSTEM - Smart Exit
# ═══════════════════════════════════════════════════════════════════════════

# --- Master Switch ---
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_INTERVAL=30              # Secondi tra check

# --- Grace Period (IMPORTANTE!) ---
HEALTH_GRACE_PERIOD_MINUTES=5         # Minuti prima che HEALTH possa intervenire

# --- Score Thresholds ---
HEALTH_SCORE_HEALTHY=2                # >= questo = tutto ok
HEALTH_SCORE_CAUTION=0                # >= questo = stringi SL
HEALTH_SCORE_DANGER=-3                # >= questo = SL a breakeven
HEALTH_SCORE_EMERGENCY=-4             # < questo = chiudi

# --- Profit Thresholds per Azioni ---
HEALTH_MIN_PROFIT_CAUTION=0.5         # Min P&L% per azione CAUTION
HEALTH_MIN_PROFIT_DANGER=0.0          # Min P&L% per azione DANGER
HEALTH_MIN_PROFIT_EMERGENCY=0.5       # Min P&L% per azione EMERGENCY

# --- Time Decay (ore) ---
HEALTH_TIME_DECAY_START=4             # Ore prima di penalità -1
HEALTH_TIME_DECAY_MEDIUM=8            # Ore per penalità -2
HEALTH_TIME_DECAY_SEVERE=12           # Ore per penalità -3

# --- Pesi Indicatori (tutti configurabili) ---
HEALTH_WEIGHT_EMA_POS=2
HEALTH_WEIGHT_EMA_NEG=-2
HEALTH_WEIGHT_RSI_POS=1
HEALTH_WEIGHT_RSI_NEG=-1
HEALTH_WEIGHT_MACD_POS=1
HEALTH_WEIGHT_MACD_NEG=-1
HEALTH_WEIGHT_VOL_POS=1
HEALTH_WEIGHT_VOL_NEG=-1
HEALTH_WEIGHT_BB_POS=1
HEALTH_WEIGHT_BB_NEG=-1
HEALTH_WEIGHT_BB_SQUEEZE=-1
HEALTH_WEIGHT_OBV_POS=1
HEALTH_WEIGHT_OBV_NEG=-1
HEALTH_WEIGHT_TIME_LIGHT=-1
HEALTH_WEIGHT_TIME_MEDIUM=-2
HEALTH_WEIGHT_TIME_SEVERE=-3
HEALTH_WEIGHT_RESILIENCE=1
```

### Esempio Log

```
[HEALTH] BTC: ⏳ Grace period (2.3m < 5.0m) - skipping
[HEALTH] ETH: Score 4 ✅ HEALTHY | EMA:+2 | RSI:+1 | MACD:+1 | VOL:0 | BB:0 | OBV:0 | TIME:0(0.5h)
[HEALTH] SOL: Score 1 ⚠️ CAUTION | EMA:+2 | RSI:-1 | MACD:0 | VOL:0 | BB:0 | OBV:0 | TIME:0(1.2h)
[HEALTH] SOL: Tightening SL (P&L: +1.25%)
[HEALTH] BTC: Score -2 🔶 DANGER | EMA:-2 | RSI:-1 | MACD:-1 | VOL:+1 | BB:0 | OBV:+1 | TIME:0(3.5h)
[HEALTH] BTC: Setting SL to breakeven (P&L: +0.35%)
```

### Bilanciamento Pesi (Storico)

**Problema originale**: I pesi erano asimmetrici e penalizzavano troppo:
- MACD contrario: -2 (ma favorevole solo +1)
- Bollinger squeeze: -2
- Threshold HEALTHY: 4 (quasi irraggiungibile)

**Soluzione applicata** (Dicembre 2025):
- Tutti i pesi resi simmetrici (+1/-1)
- EMA rimane +2/-2 (indicatore principale)
- Threshold HEALTHY abbassato da 4 a 2
- Tutti i pesi configurabili via `.env`

**Range score dopo fix**:
- Max positivo: +9 (era +8)
- Max negativo: -9 (era -12)
- Sistema bilanciato

### File Reference

| File | Funzione |
|------|----------|
| `botone_v6.py` | `_check_position_health()` - Loop principale |
| `botone_v6.py` | `_calculate_position_health()` - Calcolo score |
| `botone_v6.py` | `BotoneV6Config` (linee 150-186) - Configurazione |

---

*Last updated: December 2025*

---

# AlphaTrader Module (NEW - Parallel System)

## Overview

AlphaTrader is a **completely independent** trading system that runs in parallel with botone_v6. It's inspired by AlphaGo/AlphaZero architecture, using:

1. **Policy Network**: Neural network that decides actions (OPEN/CLOSE/HOLD)
2. **Value Network**: Neural network that estimates win probability
3. **MCTS**: Monte Carlo Tree Search for scenario simulation
4. **PPO Trainer**: Reinforcement Learning training loop

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ALPHATRADER ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐   │
│  │ MarketState │────▶│   Policy    │────▶│ Proposed Action     │   │
│  │ (64 features)│    │   Network   │     │ (LONG/SHORT/HOLD)   │   │
│  └─────────────┘     └─────────────┘     └──────────┬──────────┘   │
│                                                      │              │
│                      ┌─────────────┐                 │              │
│                      │    Value    │                 │              │
│                      │   Network   │                 │              │
│                      └──────┬──────┘                 │              │
│                             │                        │              │
│                      Win Probability                 │              │
│                             │                        │              │
│                             ▼                        ▼              │
│                      ┌───────────────────────────────────┐         │
│                      │              MCTS                  │         │
│                      │  (Simulate 100 future scenarios)  │         │
│                      └──────────────┬────────────────────┘         │
│                                     │                               │
│                             Win Rate > 60%?                         │
│                                     │                               │
│                          ┌──────────┴──────────┐                   │
│                          ▼                      ▼                   │
│                    ✅ EXECUTE              ❌ VETO                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## File Structure

```
alpha/
├── __init__.py           # Module initialization
├── config.py             # Configuration (AlphaConfig)
├── market_state.py       # State representation for RL
├── reward.py             # Reward function for training
├── policy_network.py     # Policy Network (PyTorch/Numpy)
├── value_network.py      # Value Network (PyTorch/Numpy)
├── mcts.py               # Monte Carlo Tree Search
├── trainer.py            # PPO training loop
├── trader.py             # Main trading bot
├── data_loader.py        # HyperLiquid historical data fetcher
├── data/                 # Training data storage
│   ├── BTC_candles.parquet
│   ├── ETH_candles.parquet
│   ├── SOL_candles.parquet
│   └── training_episodes.pkl
└── checkpoints/          # Model weights
```

## Components

### 1. MarketState (`market_state.py`)

Converts market data into a 64-feature vector for neural networks:

| Feature Group | Dimensions | Description |
|---------------|------------|-------------|
| Position | 7 | Has position, direction, P&L, duration, leverage |
| Target Indicators | 10 | Price/EMA, RSI, MACD, ADX, Bollinger |
| BTC Indicators | 10 | Cross-asset correlation |
| Sentiment | 4 | Fear/Greed, Forecast, BTC RSI |
| Score | 5 | Bullish/Bearish scores from signal_scorer |
| Account | 2 | Balance, equity |
| Price History | 5 | Mean return, volatility, trend |

### 2. Policy Network (`policy_network.py`)

Neural network that outputs:
- **Action probabilities** (HOLD, OPEN_LONG, OPEN_SHORT, CLOSE)
- **Leverage** (1-10)
- **Position size** (0.5x - 2.0x base)
- **Confidence** (0-1)

### 3. Value Network (`value_network.py`)

Estimates the "value" of a market state:
- Output range: [-1, 1]
- +1.0 = Very high win probability
- 0.0 = Neutral
- -1.0 = Very high loss probability

### 4. MCTS (`mcts.py`)

Before executing a trade:
1. Simulates 100 price paths (configurable)
2. For each path, simulates trade outcome (SL/TP)
3. Calculates win rate for proposed action
4. **VETO** if win rate < 60% threshold

### 5. Reward Function (`reward.py`)

| Component | Effect | Purpose |
|-----------|--------|---------|
| P&L Reward | +/- based on trade result | Core learning signal |
| Time Penalty | -0.01/hour after 4h | Avoid stagnant trades |
| Drawdown Penalty | -0.5x excess DD | Risk management |
| Win Bonus | +0.1 for winning | Encourage wins |
| Holding Cost | -0.001/hour | Opportunity cost |

## Usage

### Data Pipeline (HyperLiquid Historical Data)

Before training, download historical data from HyperLiquid:

```bash
# Download 60 days of 15-minute candles for BTC, ETH, SOL
python -m alpha.data_loader --symbols BTC ETH SOL --days 60 --interval 15m

# Check what data is available
python -m alpha.data_loader --check

# Download more data for comprehensive training
python -m alpha.data_loader --symbols BTC ETH SOL --days 180 --interval 15m

# Download 1-hour candles for longer-term patterns
python -m alpha.data_loader --symbols BTC ETH --days 365 --interval 1h
```

The data loader:
1. Fetches OHLCV candles from HyperLiquid API
2. Downloads funding rate history
3. Calculates technical indicators (EMA, RSI, MACD, ATR, ADX, Bollinger, OBV)
4. Creates training episodes (100 candles each with 20-candle overlap)
5. Saves to `alpha/data/` as parquet/pickle files

### Training

```bash
# Train on HyperLiquid historical data (RECOMMENDED)
python -m alpha.trainer --data-source hyperliquid --episodes 1000

# Train on synthetic data (for testing the pipeline)
python -m alpha.trainer --data-source synthetic --episodes 100

# Resume from checkpoint
python -m alpha.trainer --data-source hyperliquid --resume alpha/checkpoints/best_model.pt

# Specify data path and symbol
python -m alpha.trainer --data-source hyperliquid --data-path alpha/data/training_episodes.pkl --symbol BTC
```

### Trading

```bash
# Paper trading (SAFE - no real money)
python -m alpha.trader --mode paper --loop

# Single decision (debug)
python -m alpha.trader --mode paper --once

# Live trading (CAUTION!)
python -m alpha.trader --mode live --loop
```

## Configuration

Create `.env.alpha` for AlphaTrader-specific settings:

```env
# MCTS Settings
ALPHA_MCTS_SIMS=100            # Number of simulations
ALPHA_MIN_WIN_PROB=0.60        # Minimum win probability to execute

# Network Settings
ALPHA_POLICY_LR=0.0003         # Policy learning rate
ALPHA_VALUE_LR=0.0003          # Value learning rate

# Training
ALPHA_EPISODES=10000           # Training episodes
ALPHA_BATCH_SIZE=64

# Trading
ALPHA_PAPER=true               # Paper trading mode
ALPHA_POSITION_USD=25          # Base position size
ALPHA_MAX_LEVERAGE=5           # Maximum leverage
```

## Decision Flow

1. **Fetch Data**: Get indicators, sentiment, forecasts from existing modules
2. **Create State**: Convert to 64-feature MarketState vector
3. **Policy Network**: Get action recommendation
4. **Value Network**: Estimate win probability
5. **MCTS Validation**: Simulate 100 scenarios
6. **Execute or Veto**: Only execute if all checks pass

## Comparison with Botone V6

| Aspect | Botone V6 | AlphaTrader |
|--------|-----------|-------------|
| Decision | AI LLM (DeepSeek) | Neural Network |
| Validation | DOUBLE_CHECK AI | MCTS + Value Network |
| Learning | None (static prompts) | PPO Reinforcement Learning |
| Lookahead | None | 12-step price simulation |
| Cost | API calls ($) | Local computation |
| Latency | 2-5 seconds | <100ms |

## Integration with Existing Modules

AlphaTrader **reuses** existing modules without modification:
- `indicators.py` → Technical indicators
- `forecaster.py` → Prophet predictions
- `sentiment.py` → Fear & Greed Index
- `signal_scorer.py` → Score calculation
- `hyperliquid_trader.py` → Exchange execution

## Future Improvements

1. **Self-Play**: Two AlphaTrader agents compete
2. **Continuous Learning**: Update networks from live trades
3. **Multi-Asset**: Portfolio optimization across symbols
4. **Improved MCTS**: Use Prophet forecasts in simulations

---

## Docker Deployment

AlphaTrader includes a Docker container with all dependencies pre-installed.

### Build Container

```bash
docker build -t alphatrader -f Dockerfile.alpha .
```

### Commands

| Command | Description |
|---------|-------------|
| `download-api` | Download data via REST API |
| `download-s3` | Download data via S3 (recommended, more data) |
| `train` | Start training |
| `trade-paper` | Paper trading (no real money) |
| `trade-live` | Live trading (CAUTION!) |
| `check` | Check data sources |
| `status` | Check training progress |

### Training with Docker

```bash
# Step 1: Download historical data
docker run -d --name alpha_download \
  -v $(pwd)/alpha/data:/app/alpha/data \
  alphatrader download-s3

# Step 2: Start training (runs in background)
docker run -d --name alpha_training \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  -e EPISODES=1000 \
  alphatrader train

# Step 3: Check progress
docker exec alpha_training cat alpha/checkpoints/training_status.json

# Or view logs
docker logs -f alpha_training
```

### Training Status JSON

During training, a `training_status.json` file is updated with:

```json
{
  "status": "training",
  "episode": 450,
  "total_episodes": 1000,
  "progress_pct": 45.0,
  "avg_reward": 0.0234,
  "win_rate": 52.3,
  "best_reward": 0.0456,
  "elapsed_seconds": 3600,
  "eta_seconds": 4400,
  "eta_human": "1h 13m",
  "last_update": "2025-12-27T10:30:00Z"
}
```

### Paper Trading with Docker

```bash
docker run -d --name alpha_trader \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env \
  alphatrader trade-paper
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DAYS` | 60 | Days of data to download |
| `EPISODES` | 1000 | Training episodes |

### Volume Mounts

| Container Path | Purpose |
|---------------|---------|
| `/app/alpha/data` | Training data (candles, episodes) |
| `/app/alpha/checkpoints` | Model weights, training status |

---

## 🇮🇹 Guida Semplificata (per chi non è tecnico)

### Cos'è AlphaTrader?

È un "cervello artificiale" che **impara a fare trading** studiando i dati storici. Come un trader che guarda migliaia di grafici per capire quando comprare e vendere.

### Che dati scarica?

Ci sono **DUE METODI** per scaricare dati:

#### Metodo 1: S3 Bulk Download (CONSIGLIATO - più dati)

| Dato | Descrizione |
|------|-------------|
| **Tick-by-tick trades** | OGNI singolo trade eseguito |
| **Order Book L2** | Profondità del mercato |
| **Asset Contexts** | Mark price, funding, open interest |

Scarica **milioni di punti dati** invece di migliaia!

#### Metodo 2: REST API (più semplice)

| Dato | Descrizione |
|------|-------------|
| **Candele** | Prezzo ogni 15 minuti |
| **Volume** | Quanto è stato scambiato |
| **Funding Rate** | Costo posizioni |

### Confronto metodi

| Aspetto | REST API | S3 Bulk |
|---------|----------|---------|
| Dati/giorno | ~96 candele | ~100.000+ trade |
| Setup | Facile | Richiede AWS CLI |
| Qualità | Buona | **Ottima** |

### Quanti dati servono?

| Periodo | REST API | S3 Bulk | Qualità |
|---------|----------|---------|---------|
| 30 giorni | ~2.800 | ~3 milioni | ⚠️ Minimo |
| **60 giorni** | ~5.700 | ~6 milioni | ✅ **Consigliato** |
| 180 giorni | ~17.000 | ~18 milioni | ✅✅ Ottimo |

### Rischio blocco API?

**NO.**
- REST API: limite 1200/min, noi usiamo ~20/min
- S3: nessun limite (file pubblici Amazon)

### Come si usa? (CON DOCKER - CONSIGLIATO)

```bash
# PASSO 1: Costruisci il container (una volta sola)
docker build -t alphatrader -f Dockerfile.alpha .

# PASSO 2: Scarica dati storici
docker run -v $(pwd)/alpha/data:/app/alpha/data alphatrader download-s3

# PASSO 3: Addestra il modello (in background)
docker run -d --name alpha_training \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  -e EPISODES=1000 \
  alphatrader train

# PASSO 4: Controlla il progresso
docker exec alpha_training cat alpha/checkpoints/training_status.json
# oppure: docker logs -f alpha_training
```

### Come si usa? (SENZA DOCKER)

```bash
# PASSO 1: Installa dipendenze
pip install torch pandas numpy requests python-dotenv ta lz4

# PASSO 2: Scarica dati storici
python -m alpha.data_loader --source s3 --symbols BTC ETH --days 60

# PASSO 3: Addestra il modello
python -m alpha.trainer --data-source hyperliquid --episodes 1000
```

### Dopo il training?

```bash
# Con Docker:
docker run -d --name alpha_trader \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env \
  alphatrader trade-paper

# Senza Docker:
python -m alpha.trader --mode paper --loop

# Quando sei sicuro, passa a soldi VERI
# docker run ... alphatrader trade-live
# oppure: python -m alpha.trader --mode live --loop
```

### Come controllo il progresso del training?

Durante il training, viene creato un file `training_status.json`:

```bash
# Vedere lo stato
docker exec alpha_training cat alpha/checkpoints/training_status.json

# Esempio output:
# {
#   "progress_pct": 45.0,      <- 45% completato
#   "win_rate": 52.3,          <- 52% trade vincenti
#   "eta_human": "1h 13m"      <- tempo rimanente stimato
# }
```

### ⚠️ Avvertenze importanti

1. **Il training richiede tempo** - ore o giorni, non minuti
2. **Inizia SEMPRE in paper mode** - mai soldi veri subito
3. **Più dati = risultati migliori** - consigliati 180+ giorni
4. **È un sistema parallelo** - non interferisce con botone_v6

---

## 📊 AlphaTrader Status & Debug Info

### Current Training Status (December 2025) - AGGIORNATO

| Aspetto | Valore |
|---------|--------|
| **Training completato** | ✅ Sì |
| **Data Source** | **Binance** (data.binance.vision) - 2017-2025 |
| **Episodi** | ~25,000 (da 11 simboli × anni di dati) |
| **Simboli trainati** | BTC, ETH, SOL, DOGE, XRP, BNB, SUI, ARB, AVAX, LINK, ADA |
| **Win Rate** | **54.7%** ✅ (era 50.7%) |
| **Avg P&L** | **+1.08%** ✅ (era +0.02%) |
| **Best Reward** | 2.349 |
| **Checkpoint** | `alpha/checkpoints/final_model.pt` (~1.3MB) |
| **Paper Trading** | ✅ Funzionante |
| **MCTS Validation** | ✅ Attivo (60% threshold) |

### Miglioramenti Dicembre 2025

#### 1. Binance Data Source (NUOVO)
HyperLiquid API ha limite di 5000 candele (~52 giorni). Implementato download da Binance:
```bash
# Scarica anni di dati storici
python -m alpha.binance_data_loader --symbols BTC ETH SOL --days 365
```
**File**: `alpha/binance_data_loader.py`

#### 2. Mode Collapse Fix
Il modello dava sempre 99.99% OPEN_SHORT (mode collapse).
**Causa**: `entropy_coef` troppo basso (0.01)
**Fix**: Aumentato a 0.05 per più esplorazione
```bash
python -m alpha.trainer --data-source binance --entropy-coef 0.05
```

#### 3. Binance CSV Format Change (Agosto 2022)
Binance ha aggiunto header row ai CSV dal 2022-08.
**Fix**: Rilevamento automatico header in `binance_data_loader.py`

#### 4. Output Buffering Fix
Il trader loop non stampava output.
**Fix**: Sostituito `logger.info()` con `print(flush=True)`

### Paper Trading - Come Funziona

```
┌─────────────────────────────────────────────────────────────────┐
│  FAST LOOP (ogni 5s)                                            │
│  └─ Monitora posizioni aperte (P&L, SL, TP)                    │
│                                                                 │
│  SLOW LOOP (ogni 5min = 300s)                                   │
│  └─ 1. Policy Network → suggerisce azione                      │
│  └─ 2. Value Network → stima win probability                   │
│  └─ 3. MCTS → simula 100 scenari futuri                        │
│  └─ 4. Se win rate >= 60% → ESEGUE trade                       │
│  └─ 5. Altrimenti → VETO, resta in HOLD                        │
└─────────────────────────────────────────────────────────────────┘
```

### Esempio Output Paper Trading

```
============================================================
AlphaTrader Starting
Mode: PAPER
Symbols: ['BTC', 'ETH', 'SOL']
MCTS min win prob: 60%
Slow loop interval: 300s
============================================================

========================================
[22:57:13] Evaluating BTC...
Decision: HOLD (conf: 48.6%)
  -> Policy suggests: HOLD
  -> Value estimate: 0.996 (win prob: 99.8%)

========================================
[22:57:13] Evaluating ETH...
Decision: HOLD (conf: 0.0%)
  -> Policy suggests: OPEN_LONG
  -> Value estimate: 0.549 (win prob: 77.5%)
  -> MCTS: 100 sims | OPEN_LONG: 48.0% win rate | VETOED (< 60%)

========================================
[22:57:13] Evaluating SOL...
Decision: HOLD (conf: 0.0%)
  -> Policy suggests: OPEN_LONG
  -> Value estimate: 0.464 (win prob: 73.2%)
  -> MCTS: 100 sims | OPEN_LONG: 50.0% win rate | VETOED (< 60%)
```

### Comandi Utili VPS

```bash
# === PAPER TRADING ===

# Avvia paper trading (background)
cd ~/alphatrader
docker run -d --name alpha_trader \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env \
  --restart unless-stopped \
  --entrypoint python \
  alphatrader -m alpha.trader --mode paper --loop

# Visualizza logs
docker logs -f alpha_trader

# Stop
docker stop alpha_trader && docker rm alpha_trader

# === DEBUG ===

# Test singola decisione
docker run -it --rm \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env \
  --entrypoint python \
  alphatrader -m alpha.trader --mode paper --once

# Debug model
docker run -it --rm \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  alphatrader python -m alpha.debug_model

# === RETRAINING ===

# Scarica nuovi dati Binance
docker run -v $(pwd)/alpha/data:/app/alpha/data \
  alphatrader python -m alpha.binance_data_loader --days 180

# Retrain con nuovi dati
docker run -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  alphatrader python -m alpha.trainer --data-source binance --episodes 10000
```

### Files Chiave AlphaTrader

| File | Descrizione |
|------|-------------|
| `alpha/trainer.py` | Loop di training PPO |
| `alpha/trader.py` | Bot di paper/live trading |
| `alpha/policy_network.py` | Rete neurale per decisioni |
| `alpha/value_network.py` | Rete per stima win probability |
| `alpha/mcts.py` | Monte Carlo Tree Search validation |
| `alpha/market_state.py` | Vettore stato (43 features) |
| `alpha/indicators_standalone.py` | Fetch indicatori HyperLiquid (con retry) |
| `alpha/binance_data_loader.py` | Download dati storici Binance |
| `alpha/debug_model.py` | Script di debug |
| `alpha/config.py` | Configurazione (state_dim=43) |

### Prossimi Passi Consigliati

1. **Fase 1** (Ora): Lasciare paper trading attivo per 1-2 settimane
2. **Fase 2**: Analizzare risultati e retrainare se necessario
3. **Fase 3**: Integrare come segnale aggiuntivo per Botone V6

### Note Tecniche

- **Non auto-apprende**: Usa pesi fissi dal training. Per aggiornare, serve retraining.
- **MCTS conservativo**: Blocca trade con win rate < 60%
- **Dati Binance**: Illimitati (dal 2017), molto più completi di HyperLiquid

---

*AlphaTrader v0.2.0 - December 2025*
