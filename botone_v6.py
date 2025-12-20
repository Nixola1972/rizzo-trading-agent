#!/usr/bin/env python3
"""
Botone V6 - Production Trading Bot using Arena V6 AI_INDEPENDENT System

This entry point replicates Arena V6's AI_INDEPENDENT trading system for
REAL TRADING on HyperLiquid. It uses the same prompts and logic as Arena V6.

Configuration is fully managed via .env.baseline file.

Usage:
    # SLOW loop (AI decisions every N minutes)
    python botone_v6.py --mode slow --loop

    # FAST loop (position monitoring every 5s)
    python botone_v6.py --mode fast --loop
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

# Load environment FIRST
load_dotenv(".env.baseline")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [BOTONE-V6] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# ENUMS & DATACLASSES
# ==============================================================================

class TradeDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """Active position tracking."""
    id: str
    symbol: str
    direction: TradeDirection
    entry_price: float
    size: float
    leverage: int
    stop_loss_price: float
    take_profit_price: float
    current_sl_level: float  # Current trailing SL level
    opened_at: datetime


# ==============================================================================
# CONFIGURATION - All from .env.baseline
# ==============================================================================

class BotoneV6Config:
    """Configuration loaded from .env.baseline."""

    def __init__(self):
        # Bot identity
        self.bot_name = os.getenv("BOT_NAME", "botone-v6")

        # API Keys
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.ai_model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b-2507")

        # HyperLiquid credentials (same as sentinel.py)
        self.hl_private_key = os.getenv("PRIVATE_KEY") or os.getenv("HL_PRIVATE_KEY")
        self.hl_account_address = os.getenv("WALLET_ADDRESS") or os.getenv("HL_ACCOUNT_ADDRESS")
        self.hl_testnet = os.getenv("TESTNET", "false").lower() == "true" or os.getenv("HL_TESTNET", "false").lower() == "true"

        # Trading Parameters
        self.position_size_usd = float(os.getenv("POSITION_SIZE_USD", "25"))
        self.max_leverage = int(os.getenv("MAX_LEVERAGE", "3"))
        self.stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3.0"))
        self.take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "4.0"))
        self.min_profit_to_close = float(os.getenv("MIN_PROFIT_TO_CLOSE", "0.5"))  # Min profit % for AI to close
        self.ai_loss_threshold_pct = float(os.getenv("AI_LOSS_THRESHOLD_PCT", "50"))  # AI can close if loss > X% of SL

        # Leverage limits per style (configurable via env)
        self.leverage_prudent_max = int(os.getenv("LEVERAGE_PRUDENT_MAX", "3"))
        self.leverage_moderate_max = int(os.getenv("LEVERAGE_MODERATE_MAX", "5"))
        self.leverage_aggressive_min = int(os.getenv("LEVERAGE_AGGRESSIVE_MIN", "5"))
        self.leverage_macro_max = int(os.getenv("LEVERAGE_MACRO_MAX", "2"))

        # Trailing Stop
        self.trailing_enabled = os.getenv("TRAILING_ENABLED", "true").lower() == "true"
        self.trailing_steps = os.getenv("TRAILING_STEPS", "2.0:0.0,3.0:1.0,4.0:2.0")

        # AI Independent Mode Settings
        self.prompt_style = os.getenv("V6_PROMPT_STYLE", "PRUDENT").upper()
        self.ai_interval_minutes = int(os.getenv("V6_AI_INTERVAL_MINUTES", "5"))
        self.timeframe = os.getenv("V6_TIMEFRAME", "5min")

        # Symbols to trade
        symbols_str = os.getenv("TRADING_SYMBOLS", "BTC,ETH,SOL")
        self.symbols = [s.strip() for s in symbols_str.split(",")]

        # Loop intervals
        self.slow_loop_interval = int(os.getenv("SLOW_LOOP_INTERVAL", "60"))  # seconds
        self.fast_loop_interval = int(os.getenv("FAST_LOOP_INTERVAL", "5"))   # seconds

        # Validate required fields
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required in .env.baseline")
        if not self.hl_private_key:
            raise ValueError("PRIVATE_KEY (or HL_PRIVATE_KEY) is required in .env.baseline")
        if not self.hl_account_address:
            raise ValueError("WALLET_ADDRESS (or HL_ACCOUNT_ADDRESS) is required in .env.baseline")

        logger.info(f"=== {self.bot_name.upper()} CONFIGURATION ===")
        logger.info(f"  AI Model: {self.ai_model}")
        logger.info(f"  Prompt Style: {self.prompt_style}")
        logger.info(f"  AI Interval: {self.ai_interval_minutes} min")
        logger.info(f"  Symbols: {self.symbols}")
        logger.info(f"  Position Size: ${self.position_size_usd}")
        logger.info(f"  Max Leverage: {self.max_leverage}x")
        logger.info(f"  Style Leverage Limits: PRUDENT={self.leverage_prudent_max}x, MODERATE={self.leverage_moderate_max}x, AGGRESSIVE={self.leverage_aggressive_min}-{self.max_leverage}x, MACRO={self.leverage_macro_max}x")
        logger.info(f"  SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        logger.info(f"  Min Profit to Close: {self.min_profit_to_close}%")
        logger.info(f"  AI Loss Threshold: {self.ai_loss_threshold_pct}% of SL (={self.stop_loss_pct * self.ai_loss_threshold_pct / 100:.1f}%)")
        logger.info(f"  Trailing: {self.trailing_enabled} - {self.trailing_steps}")
        logger.info(f"  Testnet: {self.hl_testnet}")
        logger.info("=" * 50)


# ==============================================================================
# AI MANAGER - V6 Prompts
# ==============================================================================

class BotoneAIManager:
    """AI Manager for Botone V6 - uses same prompts as Arena V6."""

    def __init__(self, config: BotoneV6Config):
        self.config = config
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    def get_decision(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        has_position: bool,
        current_direction: Optional[TradeDirection],
        current_pnl_pct: float = 0.0,
    ) -> Tuple[str, Optional[TradeDirection], str, float, int]:
        """
        Get AI trading decision.

        Returns:
            Tuple of (action, direction, reason, confidence, leverage)
            action: "open", "close", or "hold"
        """
        prompt = self._build_v6_prompt(
            symbol, market_data, has_position, current_direction, current_pnl_pct
        )

        response = self._call_ai(prompt)
        if not response:
            return "hold", None, "AI call failed", 0.0, 1

        return self._parse_response(response)

    def _build_v6_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        has_position: bool,
        current_direction: Optional[TradeDirection],
        current_pnl_pct: float,
    ) -> str:
        """Build V6 prompt - same format as Arena."""

        # Position info
        position_info = ""
        if has_position and current_direction:
            position_info = f"""
CURRENT POSITION:
- Direction: {current_direction.value}
- P&L: {current_pnl_pct:+.2f}%
- Entry Price: ${market_data.get('entry_price', 0):,.2f}
"""

        max_leverage = self.config.max_leverage

        # Enhanced market data section
        bb_squeeze_text = "⚠️ SQUEEZE (breakout imminent!)" if market_data.get('bb_squeeze', False) else "no squeeze"
        market_section = f"""
PRICE DATA:
- Current: ${market_data.get('price', 0):,.2f}
- Change 1h: {market_data.get('change_1h', 0):+.2f}%
- Change 24h: {market_data.get('change_24h', 0):+.2f}%

TECHNICAL INDICATORS:
- MACD: {market_data.get('macd', 0):.4f} ({self._macd_signal(market_data.get('macd', 0))})
- RSI: {market_data.get('rsi', 50):.1f} ({self._rsi_signal(market_data.get('rsi', 50))})
- ADX: {market_data.get('adx', 0):.1f} ({self._adx_signal(market_data.get('adx', 0))})
- EMA Stack: Price vs EMA9 vs EMA21 = {market_data.get('ema_stack', 'neutral')}
- ATR (Volatility): {market_data.get('atr', 0):.2f} ({market_data.get('volatility_level', 'normal')})

BOLLINGER BANDS:
- Position: {market_data.get('bb_position', 'MIDDLE')} (ABOVE_UPPER=overbought, BELOW_LOWER=oversold)
- %B: {market_data.get('bb_percent_b', 0.5):.2f} (0=lower band, 0.5=middle, 1=upper band)
- Bandwidth: {market_data.get('bb_bandwidth', 0):.2f}% ({bb_squeeze_text})

PIVOT POINTS (Support/Resistance):
- R2 (Strong Resistance): ${market_data.get('pivot_r2', 0):,.2f}
- R1 (Resistance): ${market_data.get('pivot_r1', 0):,.2f}
- PP (Pivot): ${market_data.get('pivot_pp', 0):,.2f}
- S1 (Support): ${market_data.get('pivot_s1', 0):,.2f}
- S2 (Strong Support): ${market_data.get('pivot_s2', 0):,.2f}

VOLUME & LIQUIDITY:
- Volume 24h: ${market_data.get('volume_24h', 0):,.0f}
- Volume Ratio: {market_data.get('volume_ratio', 1.0):.2f}x average
- OBV Trend: {market_data.get('obv_trend', 'neutral')} (rising=buyers, falling=sellers)
- Open Interest: ${market_data.get('open_interest', 0):,.0f}
- OI Change 24h: {market_data.get('oi_change_24h', 0):+.2f}%

MULTI-TIMEFRAME TREND:
- 15min: {market_data.get('trend_15m', 'neutral')}
- 1h: {market_data.get('trend_1h', 'neutral')}
- 4h: {market_data.get('trend_4h', 'neutral')}
- 1D: {market_data.get('trend_1d', 'neutral')}

PATTERNS:
- Double Bottom: {market_data.get('double_bottom', False)} (conf: {market_data.get('double_bottom_conf', 0):.0%})
- Double Top: {market_data.get('double_top', False)} (conf: {market_data.get('double_top_conf', 0):.0%})

SENTIMENT:
- Fear & Greed Index: {market_data.get('fear_greed', 50)} ({self._fg_signal(market_data.get('fear_greed', 50))})
- Funding Rate: {market_data.get('funding_rate', 0):.4%} ({self._funding_signal(market_data.get('funding_rate', 0))})
- Whale Activity: {market_data.get('whale_activity', 'none')}
"""

        # Style-specific rules
        rules = self._get_style_rules()

        return f"""V6 PRODUCTION BOT - {self.config.prompt_style} Strategy
Interval: Every {self.config.ai_interval_minutes} minutes
Analysis Timeframe: {self.config.timeframe}

SYMBOL: {symbol}
{position_info}
{market_section}
{rules}

IMPORTANT: Show your CONFIDENCE BREAKDOWN - how each indicator contributed to the final score.

Respond with JSON:
{{
  "action": "open/close/hold",
  "direction": "LONG/SHORT" (required if action=open),
  "leverage": 1-{max_leverage} (required if action=open),
  "confidence": 0.0-1.0,
  "reason": "brief summary",
  "confidence_breakdown": {{
    "MACD": "+X% (reason)",
    "RSI": "+X% or -X% (reason)",
    "ADX": "+X% (reason)",
    "EMA": "+X% (reason)",
    "Bollinger": "+X% or -X% (reason)",
    "OBV": "+X% (reason)",
    "Pivot": "+X% or -X% (reason)",
    "Funding": "+X% or -X% (reason)",
    "OI": "+X% (reason)",
    "Patterns": "+X% (reason if detected)"
  }},
  "key_factors": ["top 2-3 indicators that drove this decision"],
  "warnings": ["any risks identified"]
}}

RULES for confidence_breakdown:
- Positive % = indicator supports the trade direction
- Negative % = indicator warns against the trade
- 0% = neutral, no impact
- Sum of all contributions should roughly equal final confidence"""

    def _get_style_rules(self) -> str:
        """Get rules based on prompt style."""
        max_leverage = self.config.max_leverage
        style = self.config.prompt_style

        # Get style-specific leverage limits from config
        prudent_max = self.config.leverage_prudent_max
        moderate_max = self.config.leverage_moderate_max
        aggressive_min = self.config.leverage_aggressive_min
        macro_max = self.config.leverage_macro_max

        if style == "PRUDENT":
            return f"""
TRADING STYLE: PRUDENT (Capital Preservation)
Goal: High win rate, fewer trades, protect capital

RULES YOU MUST FOLLOW:
1. ONLY open if confidence > 80%
2. Require at least 3 aligned indicators (MACD + RSI + Trend)
3. MAX leverage: {prudent_max}x
4. PREFER HOLD when uncertain - patience is key
5. AVOID trading when ADX < 20 (no clear trend)
6. AVOID trading when volatility is high (ATR above normal)
7. Take profit early (> 2%) - don't get greedy
8. If funding rate is extreme (>0.05% or <-0.05%), be extra cautious

DECISION PRIORITY: Safety > Profit
When in doubt → HOLD"""

        elif style == "AGGRESSIVE":
            return f"""
TRADING STYLE: AGGRESSIVE (Maximum Opportunities)
Goal: Capture more moves, accept higher risk for higher rewards

RULES YOU MUST FOLLOW:
1. Open if confidence > 50%
2. Use higher leverage ({aggressive_min}-{max_leverage}x) on strong signals
3. Trade even in moderate volatility
4. Hold positions longer for bigger targets
5. One strong indicator can be enough to enter
6. Volume spike = potential opportunity
7. Against-trend trades OK if reversal signals strong

DECISION PRIORITY: Opportunity capture
Be decisive - markets reward action"""

        elif style == "MACRO":
            return f"""
TRADING STYLE: MACRO TREND FOLLOWER (Big Moves Only)
Goal: Catch major trend moves on daily timeframe

RULES YOU MUST FOLLOW:
1. ONLY open if confidence > 85%
2. REQUIRE trend alignment on 4h AND 1D timeframes
3. MAX leverage: {macro_max}x (protect capital for big moves)
4. Target: 5-10% profit (let winners run)
5. IGNORE short-term noise and minor fluctuations
6. Wait for PERFECT setups - patience is critical
7. Only 1-3 trades per week expected
8. RSI extremes matter more on daily timeframe

MULTI-TIMEFRAME REQUIREMENT:
- 4h and 1D must agree on direction
- If conflict → HOLD

DECISION PRIORITY: Quality over quantity
Think like an investor, not a scalper"""

        else:  # MODERATE (default)
            return f"""
TRADING STYLE: MODERATE (Balanced)
Goal: Balance between opportunities and risk management

RULES YOU MUST FOLLOW:
1. Open if confidence > 60%
2. Need at least 2 aligned indicators
3. Leverage 1-{moderate_max}x based on confidence:
   - 60-70% confidence → 2-3x
   - 70-80% confidence → 3-{min(5, moderate_max)}x
   - 80%+ confidence → up to {moderate_max}x
4. Close position when indicators flip against you
5. Consider volume confirmation for entries
6. Respect multi-timeframe alignment

DECISION PRIORITY: Risk-adjusted returns"""

    def _call_ai(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.ai_model,
            "messages": [
                {"role": "system", "content": "You are a crypto trading AI. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            logger.info(f"AI Response: {content[:200]}...")

            return self._extract_json(content)

        except requests.exceptions.Timeout:
            logger.error("AI call timeout")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"AI call HTTP error: {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            logger.error(f"Model used: {self.config.ai_model}")
            return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None

    def _extract_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from AI response."""
        import re

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block
        json_block = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: infer from content
        content_lower = content.lower()
        reason = content[:200] if content else "No response"

        if "open" in content_lower or "buy" in content_lower:
            return {"action": "open", "reason": reason}
        elif "close" in content_lower or "sell" in content_lower:
            return {"action": "close", "reason": reason}
        else:
            return {"action": "hold", "reason": reason}

    def _parse_response(
        self,
        response: Dict[str, Any],
    ) -> Tuple[str, Optional[TradeDirection], str, float, int]:
        """Parse AI response."""
        action = response.get("action", response.get("operation", "hold")).lower()

        direction = None
        leverage = 1

        if action == "open":
            dir_str = response.get("direction", "").upper()
            if dir_str in ["LONG", "SHORT"]:
                direction = TradeDirection(dir_str)
            else:
                action = "hold"  # Can't open without direction

            # Parse leverage
            try:
                ai_leverage = int(response.get("leverage", 3))
                leverage = max(1, min(ai_leverage, self.config.max_leverage))
            except (ValueError, TypeError):
                leverage = 3

        # Build enriched reason with AI reasoning
        base_reason = response.get("reason", "No reason provided")
        key_factors = response.get("key_factors", [])
        warnings = response.get("warnings", [])
        confidence_breakdown = response.get("confidence_breakdown", {})

        # Build detailed reason string
        reason_parts = [base_reason]

        # Add confidence breakdown if available
        if confidence_breakdown:
            breakdown_str = " | ".join([f"{k}: {v}" for k, v in confidence_breakdown.items() if v and v != "0%"])
            if breakdown_str:
                reason_parts.append(f"BREAKDOWN: {breakdown_str}")

        if key_factors:
            reason_parts.append(f"KEY: {', '.join(key_factors)}")
        if warnings:
            reason_parts.append(f"⚠️ WARNINGS: {', '.join(warnings)}")

        reason = " | ".join(reason_parts)
        confidence = float(response.get("confidence", 0.5))

        return action, direction, reason, confidence, leverage

    # Helper methods for signal interpretation
    def _macd_signal(self, macd: float) -> str:
        if macd > 0.2: return "strong bullish"
        elif macd > 0: return "bullish"
        elif macd < -0.2: return "strong bearish"
        elif macd < 0: return "bearish"
        return "neutral"

    def _rsi_signal(self, rsi: float) -> str:
        if rsi > 70: return "overbought"
        elif rsi > 60: return "bullish"
        elif rsi < 30: return "oversold"
        elif rsi < 40: return "bearish"
        return "neutral"

    def _adx_signal(self, adx: float) -> str:
        if adx > 40: return "very strong trend"
        elif adx > 25: return "strong trend"
        elif adx > 20: return "trend developing"
        return "weak/no trend"

    def _fg_signal(self, fg: int) -> str:
        if fg > 75: return "extreme greed"
        elif fg > 55: return "greed"
        elif fg < 25: return "extreme fear"
        elif fg < 45: return "fear"
        return "neutral"

    def _funding_signal(self, rate: float) -> str:
        if rate > 0.01: return "longs paying - crowded long"
        elif rate < -0.01: return "shorts paying - crowded short"
        return "neutral"


# ==============================================================================
# MARKET DATA
# ==============================================================================

class MarketDataProvider:
    """Get market data from HyperLiquid using indicators module."""

    def __init__(self, config: BotoneV6Config):
        self.config = config
        self._analyzer = None

    def get_analyzer(self):
        """Lazy load analyzer."""
        if self._analyzer is None:
            from indicators import CryptoTechnicalAnalysisHL
            self._analyzer = CryptoTechnicalAnalysisHL(testnet=self.config.hl_testnet)
        return self._analyzer

    def get_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants

            base_url = constants.TESTNET_API_URL if self.config.hl_testnet else constants.MAINNET_API_URL
            info = Info(base_url)
            mids = info.all_mids()
            return float(mids.get(symbol, 0))
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0.0

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get full market data for a symbol."""
        try:
            analyzer = self.get_analyzer()
            analysis = analyzer.get_complete_analysis(symbol)
            current = analysis.get("current", {})

            # Determine EMA trend/stack (indicators uses ema20/ema50)
            ema9 = current.get("ema20", 0)  # Use ema20 as proxy for ema9
            ema21 = current.get("ema50", 0)  # Use ema50 as proxy for ema21
            price = current.get("price", 0)

            if price > ema9 > ema21:
                ema_stack = "bullish (price > EMA20 > EMA50)"
            elif price < ema9 < ema21:
                ema_stack = "bearish (price < EMA20 < EMA50)"
            else:
                ema_stack = "neutral/mixed"

            # Get ATR from longer_term section
            longer_term = analysis.get("longer_term_15m", {})
            atr = longer_term.get("atr_14_current", 0)
            atr_pct = (atr / price * 100) if price > 0 else 0
            if atr_pct > 3:
                volatility_level = "high"
            elif atr_pct > 1.5:
                volatility_level = "normal"
            else:
                volatility_level = "low"

            # Extract Bollinger Bands
            bollinger = analysis.get("bollinger", {})
            bb_position = bollinger.get("position", "MIDDLE")
            bb_bandwidth = bollinger.get("bandwidth", 0)
            bb_squeeze = bollinger.get("squeeze", False)
            bb_percent_b = bollinger.get("percent_b", 0.5)

            # Extract OBV trend
            obv_trend = longer_term.get("obv_trend", "neutral")

            # Extract Pivot Points
            pivot_points = analysis.get("pivot_points", {})

            return {
                "price": price,
                "macd": current.get("macd", 0),
                "rsi": current.get("rsi_14", 50),
                "adx": current.get("adx", 0),
                "ema9": ema9,
                "ema21": ema21,
                "ema_stack": ema_stack,
                "atr": atr,
                "volatility_level": volatility_level,

                # Bollinger Bands (NEW)
                "bb_position": bb_position,
                "bb_bandwidth": bb_bandwidth,
                "bb_squeeze": bb_squeeze,
                "bb_percent_b": bb_percent_b,

                # OBV - On Balance Volume (NEW)
                "obv_trend": obv_trend,

                # Pivot Points (NEW)
                "pivot_pp": pivot_points.get("pp", 0),
                "pivot_r1": pivot_points.get("r1", 0),
                "pivot_r2": pivot_points.get("r2", 0),
                "pivot_s1": pivot_points.get("s1", 0),
                "pivot_s2": pivot_points.get("s2", 0),

                # Volume - from longer_term (volume key is a string, not dict)
                "volume_24h": longer_term.get("volume_current", 0),
                "volume_ratio": longer_term.get("volume_current", 0) / max(longer_term.get("volume_average", 1), 1),

                # Open Interest
                "open_interest": analysis.get("derivatives", {}).get("open_interest_latest", 0),
                "oi_change_24h": analysis.get("derivatives", {}).get("oi_change_pct", 0),

                # Funding
                "funding_rate": analysis.get("derivatives", {}).get("funding_rate", 0),

                # Multi-timeframe trends (simplified)
                "trend_15m": self._get_trend(current),
                "trend_1h": self._get_trend(current),  # Would need separate analysis
                "trend_4h": self._get_trend(current),
                "trend_1d": self._get_trend(current),

                # Patterns
                "double_bottom": analysis.get("patterns", {}).get("double_bottom", {}).get("detected", False),
                "double_bottom_conf": analysis.get("patterns", {}).get("double_bottom", {}).get("confidence", 0),
                "double_top": analysis.get("patterns", {}).get("double_top", {}).get("detected", False),
                "double_top_conf": analysis.get("patterns", {}).get("double_top", {}).get("confidence", 0),

                # Fear & Greed (placeholder - would need external API)
                "fear_greed": 50,

                # Whale activity
                "whale_activity": "none",

                # Change percentages
                "change_1h": 0,  # Would need historical data
                "change_24h": 0,
            }
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return {"price": self.get_price(symbol)}

    def _get_trend(self, current: Dict) -> str:
        """Determine trend from indicators."""
        macd = current.get("macd", 0)
        rsi = current.get("rsi_14", 50)

        bullish_signals = 0
        bearish_signals = 0

        if macd > 0:
            bullish_signals += 1
        elif macd < 0:
            bearish_signals += 1

        if rsi > 55:
            bullish_signals += 1
        elif rsi < 45:
            bearish_signals += 1

        if bullish_signals >= 2:
            return "bullish"
        elif bearish_signals >= 2:
            return "bearish"
        return "neutral"


# ==============================================================================
# TRAILING STOP MANAGER
# ==============================================================================

class TrailingSLManager:
    """Manages trailing stop loss."""

    def __init__(self, config: BotoneV6Config):
        self.config = config
        self.steps = self._parse_steps(config.trailing_steps)

    def _parse_steps(self, steps_str: str) -> list:
        """Parse trailing steps from string format."""
        steps = []
        if not steps_str:
            return steps

        for step in steps_str.split(","):
            try:
                parts = step.strip().split(":")
                if len(parts) == 2:
                    threshold = float(parts[0])
                    sl_level = float(parts[1])
                    steps.append((threshold, sl_level))
            except (ValueError, IndexError):
                continue

        return sorted(steps, key=lambda x: x[0])

    def get_new_sl(
        self,
        direction: TradeDirection,
        entry_price: float,
        current_price: float,
        leverage: int,
        current_sl_level: float,
    ) -> Tuple[bool, float, float]:
        """
        Calculate new SL based on trailing steps.

        Returns:
            Tuple of (was_updated, new_sl_price, new_sl_level)
        """
        if not self.config.trailing_enabled:
            return False, 0.0, current_sl_level

        # Calculate current P&L %
        if direction == TradeDirection.LONG:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100 * leverage
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100 * leverage

        # Find applicable step
        applicable_sl_level = current_sl_level
        for threshold, sl_level in self.steps:
            if pnl_pct >= threshold and sl_level > current_sl_level:
                applicable_sl_level = sl_level

        if applicable_sl_level <= current_sl_level:
            return False, 0.0, current_sl_level

        # Calculate new SL price
        if direction == TradeDirection.LONG:
            # For LONG: SL is below entry
            sl_move = (applicable_sl_level / leverage) / 100
            new_sl_price = entry_price * (1 + sl_move)
        else:
            # For SHORT: SL is above entry
            sl_move = (applicable_sl_level / leverage) / 100
            new_sl_price = entry_price * (1 - sl_move)

        return True, new_sl_price, applicable_sl_level


# ==============================================================================
# POSITION TRACKER (In-Memory)
# ==============================================================================

class PositionTracker:
    """Track open positions in memory."""

    def __init__(self):
        self.positions: Dict[str, Position] = {}  # symbol -> Position

    def add_position(self, position: Position):
        self.positions[position.symbol] = position

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def remove_position(self, symbol: str):
        if symbol in self.positions:
            del self.positions[symbol]

    def get_all_positions(self) -> list:
        return list(self.positions.values())

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions


# ==============================================================================
# MAIN BOT CLASS
# ==============================================================================

class BotoneV6:
    """Main Botone V6 trading bot."""

    def __init__(self):
        self.config = BotoneV6Config()
        self.ai_manager = BotoneAIManager(self.config)
        self.market_data = MarketDataProvider(self.config)
        self.trailing_sl = TrailingSLManager(self.config)
        self.position_tracker = PositionTracker()

        # Initialize HyperLiquid trader
        from hyperliquid_trader import HyperLiquidTrader
        self.trader = HyperLiquidTrader(
            secret_key=self.config.hl_private_key,
            account_address=self.config.hl_account_address,
            testnet=self.config.hl_testnet,
        )

        # Last AI check times
        self._last_ai_check: Dict[str, datetime] = {}

        logger.info(f"Botone V6 initialized - AI Model: {self.config.ai_model}")

    def sync_positions_from_exchange(self):
        """Sync positions from HyperLiquid exchange."""
        try:
            status = self.trader.get_account_status()
            exchange_positions = status.get("open_positions", [])

            # Debug log
            if exchange_positions:
                logger.info(f"[SYNC] Found {len(exchange_positions)} positions on exchange")
                for pos in exchange_positions:
                    logger.debug(f"[SYNC] Raw position data: {pos}")

            # Track which symbols have positions on exchange
            exchange_symbols = set()

            for pos in exchange_positions:
                symbol = pos.get("symbol")
                if not symbol:
                    continue

                exchange_symbols.add(symbol)

                # Check if we're already tracking this
                if not self.position_tracker.has_position(symbol):
                    # Add to tracker
                    direction = TradeDirection.LONG if pos.get("side") == "long" else TradeDirection.SHORT
                    entry_price = pos.get("entry_price", 0)
                    size = pos.get("size", 0)

                    # Log warning if entry price is 0
                    if entry_price == 0:
                        logger.warning(f"[SYNC] ⚠️ {symbol}: entry_price is 0! Raw data: {pos}")
                        # Try to get current price as fallback
                        current_price = self.market_data.get_price(symbol)
                        if current_price > 0:
                            logger.warning(f"[SYNC] Using current price as fallback: ${current_price}")
                            entry_price = current_price

                    # Get actual leverage from exchange data
                    # Format can be: 3, "3", "3x", "2 (cross)", {"value": 3}, etc.
                    lev_data = pos.get("leverage", 3)
                    try:
                        if isinstance(lev_data, dict):
                            actual_leverage = int(lev_data.get("value", 3))
                        elif isinstance(lev_data, str):
                            # Extract first number from string like "2 (cross)" or "3x"
                            import re
                            match = re.search(r'(\d+)', lev_data)
                            actual_leverage = int(match.group(1)) if match else 3
                        else:
                            actual_leverage = int(lev_data) if lev_data else 3
                    except (ValueError, TypeError):
                        actual_leverage = 3
                    if actual_leverage <= 0:
                        actual_leverage = 3  # Default fallback

                    # Calculate SL/TP from config - MUST divide by leverage!
                    # SL at 10% P&L loss with 3x leverage = 3.33% price move
                    if direction == TradeDirection.LONG:
                        sl_price = entry_price * (1 - self.config.stop_loss_pct / 100 / actual_leverage)
                        tp_price = entry_price * (1 + self.config.take_profit_pct / 100 / actual_leverage)
                    else:
                        sl_price = entry_price * (1 + self.config.stop_loss_pct / 100 / actual_leverage)
                        tp_price = entry_price * (1 - self.config.take_profit_pct / 100 / actual_leverage)

                    position = Position(
                        id=f"{symbol}_{int(time.time())}",
                        symbol=symbol,
                        direction=direction,
                        entry_price=entry_price,
                        size=size,
                        leverage=actual_leverage,
                        stop_loss_price=sl_price,
                        take_profit_price=tp_price,
                        current_sl_level=-self.config.stop_loss_pct,
                        opened_at=datetime.now(),
                    )
                    self.position_tracker.add_position(position)
                    logger.info(f"Synced position from exchange: {symbol} {direction.value}")

            # Remove positions that no longer exist on exchange
            for symbol in list(self.position_tracker.positions.keys()):
                if symbol not in exchange_symbols:
                    self.position_tracker.remove_position(symbol)
                    logger.info(f"Position closed on exchange: {symbol}")

        except Exception as e:
            logger.error(f"Error syncing positions: {e}")

    def run_slow_loop(self):
        """Run slow loop - AI decisions."""
        logger.info("[SLOW] Loop iteration starting...")

        # Sync positions first
        self.sync_positions_from_exchange()

        for symbol in self.config.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"[SLOW] Error processing {symbol}: {e}")

        # Show summary with positions status
        positions = self.position_tracker.get_all_positions()
        if positions:
            logger.info("[SLOW] ═══════════════════════════════════════")
            logger.info(f"[SLOW] 📊 POSITIONS SUMMARY ({len(positions)} open):")
            for pos in positions:
                current_price = self.market_data.get_price(pos.symbol)
                if current_price > 0 and pos.entry_price > 0:
                    if pos.direction == TradeDirection.LONG:
                        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100 * pos.leverage
                    else:
                        pnl_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100 * pos.leverage
                    emoji = "🟢" if pnl_pct >= 0 else "🔴"
                    logger.info(f"[SLOW]   {emoji} {pos.symbol} {pos.direction.value}: {pnl_pct:+.2f}% @ ${current_price:,.2f}")
            logger.info("[SLOW] ═══════════════════════════════════════")

        interval = self.config.ai_interval_minutes
        logger.info(f"[SLOW] ✅ Loop complete - next AI check in {interval} minutes")
        logger.info(f"[SLOW] 💤 Waiting... (FAST loop monitors SL/TP every 5s)")

    def run_fast_loop(self):
        """Run fast loop - position monitoring."""
        # Sync positions
        self.sync_positions_from_exchange()

        positions = self.position_tracker.get_all_positions()
        if not positions:
            logger.debug("[FAST] No open positions")
            return

        # First, verify all positions have SL orders on exchange
        self._verify_all_sl_orders(positions)

        for position in positions:
            try:
                self._monitor_position(position)
            except Exception as e:
                logger.error(f"[FAST] Error monitoring {position.symbol}: {e}")

    def _verify_all_sl_orders(self, positions: list):
        """Verify all positions have SL orders on exchange, place if missing."""
        try:
            # Get all open orders from exchange - use frontend_open_orders for trigger orders
            try:
                open_orders = self.trader.exchange.info.frontend_open_orders(self.config.hl_account_address)
            except AttributeError:
                open_orders = self.trader.exchange.info.open_orders(self.config.hl_account_address)

            # Build a set of symbols that have SL orders
            symbols_with_sl = set()
            for order in open_orders:
                trigger_px = order.get("triggerPx")
                if trigger_px and trigger_px != "0.0":
                    symbols_with_sl.add(order.get("coin"))

            # Check each position
            for position in positions:
                if position.symbol not in symbols_with_sl:
                    logger.warning(f"[FAST] ⚠️ {position.symbol}: SL MANCANTE su exchange! Piazzo ora...")
                    self._place_sl_order(position)

        except Exception as e:
            logger.error(f"[FAST] Errore verifica SL orders: {e}")

    def _place_sl_order(self, position: Position):
        """Place a stop loss order on the exchange."""
        try:
            sl_is_buy = position.direction == TradeDirection.SHORT

            # Round SL price appropriately based on asset tick size
            # BTC: 0.1, ETH: 0.1, SOL: 0.01, others: 0.0001
            if position.symbol in ["BTC", "ETH"]:
                sl_price_rounded = round(position.stop_loss_price, 1)
            elif position.symbol == "SOL":
                sl_price_rounded = round(position.stop_loss_price, 2)
            else:
                sl_price_rounded = round(position.stop_loss_price, 4)

            # Get actual position size from exchange
            status = self.trader.get_account_status()
            actual_size = position.size
            for pos in status.get("open_positions", []):
                if pos.get("symbol") == position.symbol:
                    actual_size = abs(float(pos.get("size", 0)))
                    break

            if actual_size <= 0:
                logger.warning(f"[FAST] {position.symbol}: Size=0, skip SL placement")
                return

            # Get current price to validate SL
            current_price = self.market_data.get_price(position.symbol)
            sl_distance_pct = abs(sl_price_rounded - current_price) / current_price * 100
            logger.info(f"[FAST] {position.symbol}: Placing SL - size={actual_size}, price=${sl_price_rounded:.2f}, is_buy={sl_is_buy}, current=${current_price:.2f}, distance={sl_distance_pct:.1f}%")

            sl_order = self.trader.exchange.order(
                position.symbol,
                sl_is_buy,
                actual_size,
                sl_price_rounded,
                {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            # Check for errors in nested response
            if sl_order.get("status") == "ok":
                # Check for nested errors in statuses
                response_data = sl_order.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [])

                has_error = False
                for status in statuses:
                    if "error" in status:
                        logger.error(f"[FAST] {position.symbol}: ❌ SL RIFIUTATO: {status['error']}")
                        has_error = True
                        break

                if not has_error:
                    logger.info(f"[FAST] {position.symbol}: ✅ SL piazzato @ ${sl_price_rounded:.2f}")
            else:
                logger.warning(f"[FAST] {position.symbol}: ❌ Errore piazzamento SL: {sl_order}")

        except Exception as e:
            logger.error(f"[FAST] {position.symbol}: ❌ Errore _place_sl_order: {e}")

    def _process_symbol(self, symbol: str):
        """Process a symbol for potential trades."""
        # Check AI interval
        check_key = symbol
        last_check = self._last_ai_check.get(check_key, datetime.min)
        interval = timedelta(minutes=self.config.ai_interval_minutes)

        if datetime.now() - last_check < interval:
            remaining = interval - (datetime.now() - last_check)
            logger.info(f"[SLOW] {symbol}: ⏳ Skipping - next AI check in {remaining.seconds}s")
            return

        self._last_ai_check[check_key] = datetime.now()

        # Get market data
        market_data = self.market_data.get_market_data(symbol)
        if market_data.get("price", 0) == 0:
            logger.warning(f"[SLOW] {symbol}: No price data")
            return

        # Verbose logging of market data
        if os.getenv("VERBOSE_LOGGING", "false").lower() == "true":
            logger.info(f"[SLOW] {symbol}: === MARKET DATA ===")
            logger.info(f"  Price: ${market_data.get('price', 0):,.2f}")
            logger.info(f"  MACD: {market_data.get('macd', 0):.4f}")
            logger.info(f"  RSI: {market_data.get('rsi', 50):.1f}")
            logger.info(f"  ADX: {market_data.get('adx', 0):.1f}")
            logger.info(f"  EMA Stack: {market_data.get('ema_stack', 'N/A')}")
            logger.info(f"  ATR: {market_data.get('atr', 0):.4f} ({market_data.get('volatility_level', 'N/A')})")
            # Bollinger Bands (NEW)
            bb_squeeze = "SQUEEZE!" if market_data.get('bb_squeeze', False) else "no"
            logger.info(f"  Bollinger: {market_data.get('bb_position', 'N/A')} | %B={market_data.get('bb_percent_b', 0):.2f} | Squeeze={bb_squeeze}")
            # OBV (NEW)
            logger.info(f"  OBV Trend: {market_data.get('obv_trend', 'N/A')}")
            # Pivot Points (NEW)
            logger.info(f"  Pivot Points: R2=${market_data.get('pivot_r2', 0):,.0f} R1=${market_data.get('pivot_r1', 0):,.0f} PP=${market_data.get('pivot_pp', 0):,.0f} S1=${market_data.get('pivot_s1', 0):,.0f} S2=${market_data.get('pivot_s2', 0):,.0f}")
            logger.info(f"  Volume Ratio: {market_data.get('volume_ratio', 1.0):.2f}x")
            logger.info(f"  Funding Rate: {market_data.get('funding_rate', 0):.4%}")
            logger.info(f"  Open Interest: ${market_data.get('open_interest', 0):,.0f}")

        # Check if we have a position
        position = self.position_tracker.get_position(symbol)
        has_position = position is not None
        current_direction = position.direction if position else None
        current_pnl_pct = 0.0

        if position:
            price = market_data.get("price", position.entry_price)
            if position.direction == TradeDirection.LONG:
                current_pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
            else:
                current_pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage

            # Add entry_price to market_data for AI prompt
            market_data["entry_price"] = position.entry_price
            market_data["position_leverage"] = position.leverage
            market_data["stop_loss_price"] = position.stop_loss_price

        # Get AI decision
        logger.info(f"[SLOW] {symbol}: Calling AI ({self.config.prompt_style})...")

        action, direction, reason, confidence, leverage = self.ai_manager.get_decision(
            symbol=symbol,
            market_data=market_data,
            has_position=has_position,
            current_direction=current_direction,
            current_pnl_pct=current_pnl_pct,
        )

        logger.info(f"[SLOW] {symbol}: AI → {action.upper()} {direction.value if direction else ''} "
                   f"lev={leverage}x conf={confidence:.0%}")

        # Verbose logging of full AI response
        if os.getenv("VERBOSE_LOGGING", "false").lower() == "true":
            logger.info(f"[SLOW] {symbol}: === FULL AI RESPONSE ===")
            logger.info(f"  {reason}")
        else:
            logger.info(f"[SLOW] {symbol}: Reason: {reason[:100]}...")

        # Execute decision
        if action == "open" and direction and not has_position:
            self._open_position(symbol, direction, market_data.get("price", 0), leverage, reason)
        elif action == "close" and has_position:
            # Logica chiusura AI:
            # 1. Se in profitto >= MIN_PROFIT_TO_CLOSE → chiudi (profit taking)
            # 2. Se in perdita >= X% dello SL → AI può chiudere (loss cutting)
            # 3. Altrimenti → ignora, aspetta trailing/SL
            position = self.position_tracker.get_position(symbol)
            if position:
                current_price = market_data.get("price", 0)
                if position.direction == TradeDirection.LONG:
                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                else:
                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

                min_profit = self.config.min_profit_to_close
                sl_pct = self.config.stop_loss_pct
                loss_threshold = sl_pct * (self.config.ai_loss_threshold_pct / 100)  # es: 10% SL * 50% = 5%

                if pnl_pct >= min_profit:
                    # CASO 1: In profitto - permetti la chiusura
                    logger.info(f"[SLOW] {symbol}: ✅ AI chiude in profitto (P&L: {pnl_pct:+.2f}% >= {min_profit}%)")
                    self._close_position(symbol, "AI profit-take", reason)
                elif pnl_pct < 0 and abs(pnl_pct) >= loss_threshold:
                    # CASO 2: Perdita significativa (>50% di SL) - AI può tagliare
                    logger.warning(f"[SLOW] {symbol}: 🔴 AI taglia perdita (P&L: {pnl_pct:+.2f}% >= -{loss_threshold:.1f}% threshold)")
                    logger.warning(f"[SLOW] {symbol}: Chiudo prima dello SL @ ${position.stop_loss_price:.2f}")
                    self._close_position(symbol, "AI loss-cut", reason)
                else:
                    # CASO 3: Perdita piccola o profitto insufficiente - ignora
                    if pnl_pct < 0:
                        logger.info(f"[SLOW] {symbol}: ⏳ AI vuole chiudere ma perdita piccola ({pnl_pct:+.2f}% < -{loss_threshold:.1f}%)")
                        logger.info(f"[SLOW] {symbol}: Aspetto recupero o SL @ ${position.stop_loss_price:.2f}")
                    else:
                        logger.info(f"[SLOW] {symbol}: ⏳ AI vuole chiudere ma profitto basso ({pnl_pct:+.2f}% < {min_profit}%)")
                        logger.info(f"[SLOW] {symbol}: Aspetto trailing o target migliore")
            else:
                self._close_position(symbol, "AI decision", reason)

    def _get_next_trailing_step(self, current_pnl_pct: float, leverage: int) -> str:
        """Get info about the next trailing stop step."""
        try:
            steps = []
            for step in self.config.trailing_steps.split(","):
                profit_str, lock_str = step.strip().split(":")
                profit_pct = float(profit_str)
                lock_pct = float(lock_str)
                steps.append((profit_pct, lock_pct))

            # Sort by profit threshold
            steps.sort(key=lambda x: x[0])

            # Find the next step that hasn't been reached yet
            for profit_threshold, lock_at in steps:
                if current_pnl_pct < profit_threshold:
                    needed = profit_threshold - current_pnl_pct
                    return f"Next: +{profit_threshold:.1f}% → lock +{lock_at:.1f}% (need +{needed:.2f}%)"

            # All steps reached
            if steps:
                last_profit, last_lock = steps[-1]
                return f"✅ Max trailing reached (lock: +{last_lock:.1f}%)"
            return "No trailing steps"
        except Exception as e:
            return f"Trailing error: {e}"

    def _monitor_position(self, position: Position):
        """Monitor an open position for SL/TP/trailing."""
        price = self.market_data.get_price(position.symbol)
        if price <= 0:
            return

        # Calculate P&L
        if position.direction == TradeDirection.LONG:
            pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
            price_move_pct = ((price - position.entry_price) / position.entry_price) * 100
        else:
            pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage
            price_move_pct = ((position.entry_price - price) / position.entry_price) * 100

        # Find current and next trailing step
        current_level_str = f"+{position.current_sl_level:.1f}%" if position.current_sl_level >= 0 else f"{position.current_sl_level:.1f}%"
        next_step_info = self._get_next_trailing_step(pnl_pct, position.leverage)

        # Detailed log with trailing info
        logger.info(f"[FAST] {position.symbol} {position.direction.value}: "
                    f"${price:,.2f} | P&L: {pnl_pct:+.2f}% | "
                    f"SL: ${position.stop_loss_price:.2f} (lock: {current_level_str}) | "
                    f"{next_step_info}")

        # Check TP
        if position.direction == TradeDirection.LONG and price >= position.take_profit_price:
            self._close_position(position.symbol, "TP hit", f"Price ${price:.2f} >= TP ${position.take_profit_price:.2f}")
            return
        elif position.direction == TradeDirection.SHORT and price <= position.take_profit_price:
            self._close_position(position.symbol, "TP hit", f"Price ${price:.2f} <= TP ${position.take_profit_price:.2f}")
            return

        # Check SL
        if position.direction == TradeDirection.LONG and price <= position.stop_loss_price:
            self._close_position(position.symbol, "SL hit", f"Price ${price:.2f} <= SL ${position.stop_loss_price:.2f}")
            return
        elif position.direction == TradeDirection.SHORT and price >= position.stop_loss_price:
            self._close_position(position.symbol, "SL hit", f"Price ${price:.2f} >= SL ${position.stop_loss_price:.2f}")
            return

        # Apply trailing
        was_updated, new_sl, new_level = self.trailing_sl.get_new_sl(
            direction=position.direction,
            entry_price=position.entry_price,
            current_price=price,
            leverage=position.leverage,
            current_sl_level=position.current_sl_level,
        )

        if was_updated:
            position.stop_loss_price = new_sl
            position.current_sl_level = new_level
            logger.info(f"[FAST] {position.symbol}: Trailing SL → ${new_sl:.2f} (level: +{new_level:.1f}%)")

            # === AGGIORNA SL SU HYPERLIQUID ===
            try:
                # Cancel existing SL orders and place new one
                # MUST use frontend_open_orders() to see trigger orders (SL/TP)
                try:
                    open_orders = self.trader.exchange.info.frontend_open_orders(self.config.hl_account_address)
                except AttributeError:
                    open_orders = self.trader.exchange.info.open_orders(self.config.hl_account_address)

                for order in open_orders:
                    if order.get("coin") == position.symbol:
                        trigger_px = order.get("triggerPx")
                        if trigger_px and trigger_px != "0.0":
                            # Cancel old SL
                            self.trader.exchange.cancel(position.symbol, order.get("oid"))
                            logger.info(f"[FAST] {position.symbol}: Cancellato vecchio SL")

                # Place new SL
                sl_is_buy = position.direction == TradeDirection.SHORT

                # Round SL price appropriately based on asset tick size
                # BTC: 0.1, ETH: 0.1, SOL: 0.01, others: 0.0001
                if position.symbol in ["BTC", "ETH"]:
                    sl_price_rounded = round(new_sl, 1)
                elif position.symbol == "SOL":
                    sl_price_rounded = round(new_sl, 2)
                else:
                    sl_price_rounded = round(new_sl, 4)

                # Get actual position size from exchange
                status = self.trader.get_account_status()
                actual_size = position.size
                for pos in status.get("open_positions", []):
                    if pos.get("symbol") == position.symbol:
                        actual_size = abs(float(pos.get("size", 0)))
                        break

                sl_order = self.trader.exchange.order(
                    position.symbol,
                    sl_is_buy,
                    actual_size,
                    sl_price_rounded,
                    {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},  # float, not string!
                    reduce_only=True
                )

                if sl_order.get("status") == "ok":
                    logger.info(f"[FAST] {position.symbol}: 🛡️ Nuovo SL piazzato @ ${sl_price_rounded:.2f}")
                else:
                    logger.warning(f"[FAST] {position.symbol}: ⚠️ Errore aggiornamento SL: {sl_order}")

            except Exception as sl_err:
                logger.error(f"[FAST] {position.symbol}: ❌ Errore trailing SL update: {sl_err}")

    def _open_position(self, symbol: str, direction: TradeDirection, price: float, leverage: int, reason: str):
        """Open a new position."""
        logger.info(f"[TRADE] Opening {direction.value} on {symbol} @ ${price:.2f} lev={leverage}x")

        try:
            # Calculate position size
            is_buy = direction == TradeDirection.LONG

            # Calculate SL/TP prices
            if direction == TradeDirection.LONG:
                sl_price = price * (1 - self.config.stop_loss_pct / 100 / leverage)
                tp_price = price * (1 + self.config.take_profit_pct / 100 / leverage)
            else:
                sl_price = price * (1 + self.config.stop_loss_pct / 100 / leverage)
                tp_price = price * (1 - self.config.take_profit_pct / 100 / leverage)

            # Build order JSON for execute_signal
            order = {
                "operation": "open",
                "symbol": symbol,
                "direction": direction.value.lower(),
                "target_portion_of_balance": self.config.position_size_usd / 100,  # Will be adjusted by trader
                "leverage": leverage,
                "reason": reason,
            }

            # Execute via HyperLiquid trader
            result = self.trader.execute_signal(order)

            if result.get("status") == "ok" or "response" in result:
                # Track position
                position = Position(
                    id=f"{symbol}_{int(time.time())}",
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    size=self.config.position_size_usd / price,
                    leverage=leverage,
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                    current_sl_level=-self.config.stop_loss_pct,
                    opened_at=datetime.now(),
                )
                self.position_tracker.add_position(position)

                logger.info(f"[TRADE] ✅ Opened {direction.value} {symbol}")
                logger.info(f"[TRADE]    Entry: ${price:.2f} | SL: ${sl_price:.2f} | TP: ${tp_price:.2f}")

                # === PIAZZA SL SU HYPERLIQUID ===
                try:
                    # Piccolo delay per permettere alla posizione di apparire
                    time.sleep(1)

                    # Get actual position size from exchange
                    logger.info(f"[TRADE] Recupero size posizione per SL...")
                    status = self.trader.get_account_status()
                    actual_size = 0
                    for pos in status.get("open_positions", []):
                        if pos.get("symbol") == symbol:
                            actual_size = abs(float(pos.get("size", 0)))
                            logger.info(f"[TRADE] Trovata posizione {symbol}: size={actual_size}")
                            break

                    if actual_size > 0:
                        # SL direction is opposite to position
                        sl_is_buy = direction == TradeDirection.SHORT

                        # Round SL price appropriately based on asset tick size
                        # BTC: 0.1, ETH: 0.1, SOL: 0.01, others: 0.0001
                        if symbol in ["BTC", "ETH"]:
                            sl_price_rounded = round(sl_price, 1)
                        elif symbol == "SOL":
                            sl_price_rounded = round(sl_price, 2)
                        else:
                            sl_price_rounded = round(sl_price, 4)

                        logger.info(f"[TRADE] Piazzando SL: {symbol} is_buy={sl_is_buy} size={actual_size} trigger={sl_price_rounded}")

                        # Place SL trigger order - triggerPx deve essere float, non string!
                        sl_order = self.trader.exchange.order(
                            symbol,
                            sl_is_buy,
                            actual_size,
                            sl_price_rounded,  # limit price
                            {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                            reduce_only=True
                        )

                        logger.info(f"[TRADE] SL order response: {sl_order}")

                        if sl_order.get("status") == "ok":
                            response_data = sl_order.get("response", {})
                            if response_data.get("type") == "order":
                                statuses = response_data.get("data", {}).get("statuses", [])
                                if statuses and statuses[0].get("resting"):
                                    oid = statuses[0]["resting"]["oid"]
                                    logger.info(f"[TRADE] 🛡️ SL piazzato su HyperLiquid @ ${sl_price_rounded:.2f} (OID: {oid})")
                                else:
                                    logger.info(f"[TRADE] 🛡️ SL piazzato @ ${sl_price_rounded:.2f}")
                            else:
                                logger.info(f"[TRADE] 🛡️ SL piazzato @ ${sl_price_rounded:.2f}")
                        else:
                            logger.warning(f"[TRADE] ⚠️ SL non piazzato: {sl_order}")
                    else:
                        logger.warning(f"[TRADE] ⚠️ Position size non trovato dopo 1s, riprovo...")
                        # Riprova dopo altro delay
                        time.sleep(2)
                        status = self.trader.get_account_status()
                        for pos in status.get("open_positions", []):
                            if pos.get("symbol") == symbol:
                                actual_size = abs(float(pos.get("size", 0)))
                                break
                        if actual_size > 0:
                            sl_is_buy = direction == TradeDirection.SHORT
                            # Round SL price appropriately based on asset tick size
                            if symbol in ["BTC", "ETH"]:
                                sl_price_rounded = round(sl_price, 1)
                            elif symbol == "SOL":
                                sl_price_rounded = round(sl_price, 2)
                            else:
                                sl_price_rounded = round(sl_price, 4)
                            sl_order = self.trader.exchange.order(
                                symbol,
                                sl_is_buy,
                                actual_size,
                                sl_price_rounded,
                                {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                                reduce_only=True
                            )
                            if sl_order.get("status") == "ok":
                                logger.info(f"[TRADE] 🛡️ SL piazzato (retry) @ ${sl_price_rounded:.2f}")
                            else:
                                logger.error(f"[TRADE] ❌ SL fallito anche al retry: {sl_order}")
                        else:
                            logger.error(f"[TRADE] ❌ Position size ancora non trovato!")

                except Exception as sl_err:
                    logger.error(f"[TRADE] ❌ Errore piazzamento SL: {sl_err}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.error(f"[TRADE] ❌ Failed to open: {result}")

        except Exception as e:
            logger.error(f"[TRADE] ❌ Error opening position: {e}")

    def _close_position(self, symbol: str, exit_type: str, reason: str):
        """Close a position."""
        logger.info(f"[TRADE] Closing {symbol} - {exit_type}: {reason}")

        try:
            result = self.trader.exchange.market_close(symbol)

            if result.get("status") == "ok" or "response" in result:
                self.position_tracker.remove_position(symbol)
                logger.info(f"[TRADE] ✅ Closed {symbol}")
            else:
                logger.error(f"[TRADE] ❌ Failed to close: {result}")

        except Exception as e:
            logger.error(f"[TRADE] ❌ Error closing position: {e}")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Botone V6 - Production Trading Bot")
    parser.add_argument("--mode", choices=["slow", "fast"], default="slow",
                       help="Loop mode: slow (AI decisions) or fast (position monitoring)")
    parser.add_argument("--loop", action="store_true",
                       help="Run in continuous loop mode")
    parser.add_argument("--once", action="store_true",
                       help="Run once and exit")

    args = parser.parse_args()

    bot = BotoneV6()

    if args.once:
        if args.mode == "slow":
            bot.run_slow_loop()
        else:
            bot.run_fast_loop()
        return

    if args.loop:
        interval = bot.config.slow_loop_interval if args.mode == "slow" else bot.config.fast_loop_interval
        logger.info(f"Starting {args.mode.upper()} loop (interval: {interval}s)")

        while True:
            try:
                if args.mode == "slow":
                    bot.run_slow_loop()
                else:
                    bot.run_fast_loop()

                time.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(10)
    else:
        # Default: run once
        if args.mode == "slow":
            bot.run_slow_loop()
        else:
            bot.run_fast_loop()


if __name__ == "__main__":
    main()
