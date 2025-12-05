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
| **aggressive** | MACD alone is enough (>0.15) | High frequency, volatile markets |
| **moderate** | MACD + EMA confirmation | Balanced risk/reward (RECOMMENDED) |
| **conservative** | ALL signals must align | Capital preservation, stable markets |

### Detailed Style Rules

#### AGGRESSIVE (Momentum Chaser)
```
Entry: Need ONLY ONE strong signal
- MACD > 0.15 (or < -0.15) = GO
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
- Price vs EMA20 confirms direction
Secondary:
- RSI as exhaustion filter only (< 25 or > 75 = caution)
- Whale activity: confirming is good, neutral is OK
Bias: Strong MACD + EMA confirmation = GO
```

#### CONSERVATIVE (Sniper)
```
Entry: ALL signals must align
Required:
- MACD > 0.25 (or < -0.25)
- Price must confirm vs EMA20
- RSI must not be exhausted
- No contradicting whale activity
- Score trend must be stable
Bias: When in doubt → HOLD
```

---

## Indicator Weights

The DOUBLE_CHECK prompt assigns different importance to indicators:

### Primary Indicators (High Weight)
- **MACD**: Momentum direction and strength
- **Price vs EMA20**: Trend confirmation

### Secondary Indicators (Medium Weight)
- **RSI**: Only matters at extremes (<25 or >75)
- **Whale Activity**: Confirmation signal

### Tertiary Indicators (Low Weight for short-term trades)
- **Fear & Greed Index**: Macro sentiment, less relevant for MICRO_GAIN

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

*Last updated: December 2024*
