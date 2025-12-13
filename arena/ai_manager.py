"""
Arena AI Manager

Handles AI calls for trade decisions using OpenRouter API.
Supports multiple AI models configured per variant.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import requests

from .models import (
    Variant,
    SubVariant,
    TradeDirection,
    OperationMode,
)


# Configure logging
logger = logging.getLogger("arena.ai_manager")


class AIManager:
    """
    Manages AI calls for Arena simulation.
    Uses OpenRouter API to support multiple models.
    """

    def __init__(self):
        """Initialize AI Manager."""
        self.api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.api_base = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")

        if not self.api_key:
            logger.warning("No API key found for AI Manager. Set OPENROUTER_API_KEY.")

        # Rate limiting
        self._last_call_time: Dict[str, float] = {}
        self._min_interval = 1.0  # Minimum seconds between calls per model

        # Cache for recent decisions
        self._decision_cache: Dict[str, Tuple[datetime, Dict]] = {}
        self._cache_ttl_seconds = 60

    def validate_trade(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        direction: TradeDirection,
        market_data: Dict[str, Any],
        score_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[TradeDirection], str, float]:
        """
        Validate a trade decision using AI.

        Returns:
            Tuple of (approved, override_direction, reason, confidence)
        """
        if not self.api_key:
            return True, None, "No API key - auto-approved", 0.5

        # Rate limiting
        self._rate_limit(sub_variant.ai_model)

        # Build prompt based on operation mode
        if variant.operation_mode == OperationMode.AI_INDEPENDENT:
            prompt = self._build_independent_prompt(
                symbol, market_data, score_data, variant
            )
        else:
            prompt = self._build_validation_prompt(
                symbol, direction, market_data, score_data, variant
            )

        # Call AI
        try:
            response = self._call_ai(sub_variant.ai_model, prompt)

            if not response:
                return True, None, "AI call failed - auto-approved", 0.3

            # Parse response
            return self._parse_response(response, direction)

        except Exception as e:
            logger.error(f"AI validation error: {e}")
            return True, None, f"Error: {str(e)[:50]}", 0.3

    def get_independent_decision(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        market_data: Dict[str, Any],
        has_position: bool,
        current_position_direction: Optional[TradeDirection] = None,
    ) -> Tuple[str, Optional[TradeDirection], str, float]:
        """
        Get AI decision for independent mode.

        Returns:
            Tuple of (action, direction, reason, confidence)
            action: "open", "close", "hold"
        """
        if not self.api_key:
            return "hold", None, "No API key", 0.0

        self._rate_limit(sub_variant.ai_model)

        prompt = self._build_independent_decision_prompt(
            symbol, market_data, has_position, current_position_direction, variant
        )

        try:
            response = self._call_ai(sub_variant.ai_model, prompt)

            if not response:
                return "hold", None, "AI call failed", 0.0

            return self._parse_independent_response(response)

        except Exception as e:
            logger.error(f"AI independent decision error: {e}")
            return "hold", None, f"Error: {str(e)[:50]}", 0.0

    def check_smart_sl_extension(
        self,
        variant: Variant,
        sub_variant: SubVariant,
        symbol: str,
        direction: TradeDirection,
        current_pnl_pct: float,
        market_data: Dict[str, Any],
        extensions_used: int,
    ) -> Tuple[bool, str, float]:
        """
        Check if AI recommends extending stop loss.

        Returns:
            Tuple of (should_extend, reason, confidence)
        """
        if not self.api_key:
            return False, "No API key", 0.0

        max_extensions = variant.trading_params.smart_sl_max_extensions
        if extensions_used >= max_extensions:
            return False, f"Max extensions ({max_extensions}) reached", 0.0

        self._rate_limit(sub_variant.ai_model)

        prompt = self._build_smart_sl_prompt(
            symbol, direction, current_pnl_pct, market_data, extensions_used, max_extensions
        )

        try:
            response = self._call_ai(sub_variant.ai_model, prompt)

            if not response:
                return False, "AI call failed", 0.0

            return self._parse_smart_sl_response(response)

        except Exception as e:
            logger.error(f"Smart SL AI error: {e}")
            return False, f"Error: {str(e)[:50]}", 0.0

    def _rate_limit(self, model: str) -> None:
        """Apply rate limiting per model."""
        now = time.time()
        last_call = self._last_call_time.get(model, 0)
        elapsed = now - last_call

        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        self._last_call_time[model] = time.time()

    def _call_ai(self, model: str, prompt: str) -> Optional[Dict[str, Any]]:
        """Make API call to AI model."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/rizzo-trading",
            "X-Title": "Rizzo Arena",
        }

        system_message = """You are a cryptocurrency trading AI assistant for simulation testing.
Analyze the provided market data and make trading decisions.
Always respond with valid JSON containing your decision and reasoning.
Be concise and focus on key indicators."""

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        }

        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"AI API error {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Try to parse JSON from response
            return self._extract_json(content)

        except requests.exceptions.Timeout:
            logger.warning(f"AI call timeout for model {model}")
            return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None

    def _extract_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from AI response."""
        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in content
        import re
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Return structured response from plain text
        content_lower = content.lower()
        if "open" in content_lower or "buy" in content_lower or "long" in content_lower:
            return {"operation": "open", "reason": content[:100]}
        elif "close" in content_lower or "sell" in content_lower:
            return {"operation": "close", "reason": content[:100]}
        else:
            return {"operation": "hold", "reason": content[:100]}

    def _build_validation_prompt(
        self,
        symbol: str,
        direction: TradeDirection,
        market_data: Dict[str, Any],
        score_data: Dict[str, Any],
        variant: Variant,
    ) -> str:
        """Build prompt for trade validation."""
        style = variant.trading_params.trading_style.upper()

        return f"""ARENA SIMULATION - Trade Validation
Style: {style}

PROPOSED TRADE:
- Symbol: {symbol}
- Direction: {direction.value}
- Score: {score_data.get('net_score', 0):.1f}

MARKET DATA:
- Price: ${market_data.get('price', 0):,.2f}
- MACD: {market_data.get('macd', 0):.4f}
- RSI: {market_data.get('rsi', 50):.1f}
- ADX: {market_data.get('adx', 0):.1f}
- EMA Trend: {market_data.get('ema_trend', 'neutral')}
- Volume: {market_data.get('volume_ratio', 1.0):.2f}x avg

PATTERN:
- Double Bottom: {market_data.get('double_bottom', False)}
- Double Top: {market_data.get('double_top', False)}

Respond with JSON:
{{"operation": "open" or "hold", "direction": "LONG" or "SHORT", "confidence": 0.0-1.0, "reason": "brief reason"}}

Note: You can override direction if indicators strongly suggest opposite."""

    def _build_independent_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        score_data: Dict[str, Any],
        variant: Variant,
    ) -> str:
        """Build prompt for AI independent mode."""
        return f"""ARENA SIMULATION - AI Independent Decision
Timeframe: {variant.ai_independent_timeframe}

SYMBOL: {symbol}

MARKET DATA:
- Price: ${market_data.get('price', 0):,.2f}
- MACD: {market_data.get('macd', 0):.4f}
- RSI: {market_data.get('rsi', 50):.1f}
- ADX: {market_data.get('adx', 0):.1f}
- EMA9: ${market_data.get('ema9', 0):,.2f}
- EMA21: ${market_data.get('ema21', 0):,.2f}
- ATR: {market_data.get('atr', 0):.2f}

PATTERNS:
- Double Bottom: {market_data.get('double_bottom', False)} (conf: {market_data.get('double_bottom_conf', 0):.0%})
- Double Top: {market_data.get('double_top', False)} (conf: {market_data.get('double_top_conf', 0):.0%})

SENTIMENT:
- Fear & Greed: {market_data.get('fear_greed', 50)}
- Funding Rate: {market_data.get('funding_rate', 0):.4%}

Analyze ALL indicators and decide whether to trade.
Respond with JSON:
{{"operation": "open" or "hold", "direction": "LONG" or "SHORT", "confidence": 0.0-1.0, "reason": "your analysis"}}"""

    def _build_independent_decision_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        has_position: bool,
        current_direction: Optional[TradeDirection],
        variant: Variant,
    ) -> str:
        """Build prompt for independent decision with position context."""
        position_info = ""
        if has_position and current_direction:
            position_info = f"""
CURRENT POSITION:
- Direction: {current_direction.value}
- P&L: {market_data.get('current_pnl_pct', 0):.2f}%
"""

        return f"""ARENA SIMULATION - AI Free Decision
Interval: Every {variant.ai_check_interval_minutes} minutes
Timeframe: {variant.ai_independent_timeframe}

SYMBOL: {symbol}
{position_info}
MARKET DATA:
- Price: ${market_data.get('price', 0):,.2f}
- MACD: {market_data.get('macd', 0):.4f}
- RSI: {market_data.get('rsi', 50):.1f}
- ADX: {market_data.get('adx', 0):.1f}
- Trend: {market_data.get('trend', 'neutral')}

You have FULL CONTROL. Decide:
- "open" + direction: Open new position
- "close": Close current position (if any)
- "hold": Do nothing

Respond with JSON:
{{"action": "open/close/hold", "direction": "LONG/SHORT" (if open), "confidence": 0.0-1.0, "reason": "brief analysis"}}"""

    def _build_smart_sl_prompt(
        self,
        symbol: str,
        direction: TradeDirection,
        current_pnl_pct: float,
        market_data: Dict[str, Any],
        extensions_used: int,
        max_extensions: int,
    ) -> str:
        """Build prompt for Smart SL decision."""
        return f"""ARENA SIMULATION - Smart Stop Loss Decision

POSITION:
- Symbol: {symbol}
- Direction: {direction.value}
- Current P&L: {current_pnl_pct:.2f}%
- SL Extensions Used: {extensions_used}/{max_extensions}

MARKET DATA:
- Price: ${market_data.get('price', 0):,.2f}
- MACD: {market_data.get('macd', 0):.4f}
- RSI: {market_data.get('rsi', 50):.1f}
- ADX: {market_data.get('adx', 0):.1f}

The position is approaching stop loss. Should we EXTEND the SL to give more room?

Consider:
- Is there a potential reversal forming?
- Are indicators showing the trend might continue in our favor?
- Is extending the risk worth it?

Respond with JSON:
{{"extend": true/false, "confidence": 0.0-1.0, "reason": "brief reasoning"}}"""

    def _parse_response(
        self,
        response: Dict[str, Any],
        original_direction: TradeDirection,
    ) -> Tuple[bool, Optional[TradeDirection], str, float]:
        """Parse AI validation response."""
        operation = response.get("operation", "hold").lower()
        approved = operation == "open"

        # Check for direction override
        override_direction = None
        ai_direction = response.get("direction", "").upper()
        if ai_direction in ["LONG", "SHORT"] and ai_direction != original_direction.value:
            override_direction = TradeDirection(ai_direction)

        reason = response.get("reason", "No reason provided")
        confidence = float(response.get("confidence", 0.5))

        return approved, override_direction, reason, confidence

    def _parse_independent_response(
        self,
        response: Dict[str, Any],
    ) -> Tuple[str, Optional[TradeDirection], str, float]:
        """Parse AI independent decision response."""
        action = response.get("action", response.get("operation", "hold")).lower()

        direction = None
        if action == "open":
            dir_str = response.get("direction", "").upper()
            if dir_str in ["LONG", "SHORT"]:
                direction = TradeDirection(dir_str)
            else:
                action = "hold"  # Can't open without direction

        reason = response.get("reason", "No reason provided")
        confidence = float(response.get("confidence", 0.5))

        return action, direction, reason, confidence

    def _parse_smart_sl_response(
        self,
        response: Dict[str, Any],
    ) -> Tuple[bool, str, float]:
        """Parse Smart SL response."""
        extend = response.get("extend", False)
        reason = response.get("reason", "No reason provided")
        confidence = float(response.get("confidence", 0.5))

        return extend, reason, confidence
