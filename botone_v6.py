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

# Import database module (optional - gracefully handles missing psycopg2)
try:
    from botone_v6_db import TradeDatabase
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    TradeDatabase = None

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
    # MFE/MAE tracking
    max_price: float = 0.0  # Highest price seen (for MFE)
    min_price: float = 0.0  # Lowest price seen (for MAE)
    # Database tracking
    trade_id: Optional[int] = None  # Database ID for this trade
    # Entry context (stored for DB)
    conviction_tier: int = 2
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    entry_indicators: Optional[Dict[str, Any]] = None


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

        # Reasoning Tokens (for models that support it: DeepSeek R1, o1, o3, Grok, Gemini Thinking)
        self.reasoning_enabled = os.getenv("REASONING_ENABLED", "false").strip().lower() == "true"
        self.reasoning_effort = os.getenv("REASONING_EFFORT", "medium").strip()  # high, medium, low
        self.reasoning_max_tokens = int(os.getenv("REASONING_MAX_TOKENS", "2000").strip())

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

        # AI Conviction Sizing - Dynamic position sizing based on AI tier
        self.conviction_sizing_enabled = os.getenv("CONVICTION_SIZING_ENABLED", "false").lower() == "true"
        self.tier1_size_usd = float(os.getenv("TIER1_SIZE_USD", "25"))  # Speculativo
        self.tier2_size_usd = float(os.getenv("TIER2_SIZE_USD", "35"))  # Standard
        self.tier3_size_usd = float(os.getenv("TIER3_SIZE_USD", "50"))  # High Conviction
        self.force_tier = int(os.getenv("FORCE_TIER", "0"))  # 0=disabled, 1/2/3=force tier
        # TIER 3 safety requirements
        self.tier3_min_adx = float(os.getenv("TIER3_MIN_ADX", "25"))
        self.tier3_min_volume_ratio = float(os.getenv("TIER3_MIN_VOLUME_RATIO", "1.2"))
        self.tier3_min_score_margin = float(os.getenv("TIER3_MIN_SCORE_MARGIN", "15"))

        # BTC Watchdog - Protezione correlazione cross-asset
        self.btc_watchdog_enabled = os.getenv("BTC_WATCHDOG_ENABLED", "true").lower() == "true"
        self.btc_rsi_extreme = float(os.getenv("BTC_RSI_EXTREME", "70"))  # RSI >= 70 → azione immediata
        self.btc_rsi_danger = float(os.getenv("BTC_RSI_DANGER", "65"))    # RSI >= 65 → stringi se in profitto
        self.btc_rsi_oversold = float(os.getenv("BTC_RSI_OVERSOLD", "30")) # RSI <= 30 → proteggi LONG
        # SL tightening amounts (% from entry price)
        self.btc_watchdog_extreme_sl_pct = float(os.getenv("BTC_WATCHDOG_EXTREME_SL_PCT", "0.5"))  # SL a breakeven + X%
        self.btc_watchdog_danger_sl_pct = float(os.getenv("BTC_WATCHDOG_DANGER_SL_PCT", "1.0"))    # SL a profit - X%
        # Entry VETO based on BTC RSI - block new entries in extreme zones
        self.btc_entry_veto_enabled = os.getenv("BTC_ENTRY_VETO_ENABLED", "true").lower() == "true"
        self.btc_entry_veto_long_rsi = float(os.getenv("BTC_ENTRY_VETO_LONG_RSI", "70"))   # Block LONG if BTC RSI >= this
        self.btc_entry_veto_short_rsi = float(os.getenv("BTC_ENTRY_VETO_SHORT_RSI", "30")) # Block SHORT if BTC RSI <= this

        # === RSI ENTRY FILTER (per-symbol RSI check) ===
        # Block LONG entries when symbol's own RSI is too high (overbought)
        # Block SHORT entries when symbol's own RSI is too low (oversold)
        self.rsi_entry_filter_enabled = os.getenv("RSI_ENTRY_FILTER_ENABLED", "true").lower() == "true"
        self.long_max_rsi = float(os.getenv("LONG_MAX_RSI", "65"))      # Block LONG if symbol RSI >= this
        self.short_min_rsi = float(os.getenv("SHORT_MIN_RSI", "35"))    # Block SHORT if symbol RSI <= this

        # === EMA TREND FILTER ===
        # Block trades against the trend: no SHORT in uptrend, no LONG in downtrend
        self.ema_trend_filter_enabled = os.getenv("EMA_TREND_FILTER_ENABLED", "true").lower() == "true"

        # === ADX FILTER ===
        # Block trades when ADX is too high (trend too strong = entering too late)
        # Data shows: ADX >40 has negative avg P&L (-1.17%), ADX <20 has +3.79%!
        self.adx_filter_enabled = os.getenv("ADX_FILTER_ENABLED", "true").lower() == "true"
        self.adx_max = float(os.getenv("ADX_MAX", "40"))  # Block new trades when ADX >= this

        # === EARLY EXIT FOR BAD ENTRY ===
        # Close trade early if it goes against us without ever going in our favor
        # Data shows: trades with MAE > MFE have only 8% win rate!
        self.early_exit_enabled = os.getenv("EARLY_EXIT_ENABLED", "true").lower() == "true"
        self.early_exit_minutes = int(os.getenv("EARLY_EXIT_MINUTES", "5"))  # Check after X minutes
        self.early_exit_mae_threshold = float(os.getenv("EARLY_EXIT_MAE", "1.5"))  # Close if MAE >= this
        self.early_exit_mfe_threshold = float(os.getenv("EARLY_EXIT_MFE", "0.5"))  # AND MFE < this

        # === TIME STOP ===
        # Close ALL trades after X minutes regardless of P&L
        # Data shows: trades > 30min have significantly lower win rate (80% → 15%)
        self.time_stop_enabled = os.getenv("TIME_STOP_ENABLED", "true").lower() == "true"
        self.time_stop_minutes = int(os.getenv("TIME_STOP_MINUTES", "30"))  # Close after 30 min

        # === MULTI-TIMEFRAME ANALYSIS ===
        # Pass candle data from multiple timeframes to AI for broader context
        self.multi_timeframe_enabled = os.getenv("MULTI_TIMEFRAME_ENABLED", "false").lower() == "true"
        self.mtf_candles_1m = int(os.getenv("MTF_CANDLES_1M", "30"))    # Last 30 min (entry timing)
        self.mtf_candles_15m = int(os.getenv("MTF_CANDLES_15M", "12"))  # Last 3 hours (intraday trend)
        self.mtf_candles_4h = int(os.getenv("MTF_CANDLES_4H", "6"))     # Last 24 hours (daily trend)
        self.mtf_candles_1d = int(os.getenv("MTF_CANDLES_1D", "7"))     # Last week (macro trend)

        # === SYMBOL COOLDOWN ===
        # Minimum minutes between trades on same symbol (prevent overtrading)
        self.symbol_cooldown_enabled = os.getenv("SYMBOL_COOLDOWN_ENABLED", "true").lower() == "true"
        self.symbol_cooldown_minutes = int(os.getenv("SYMBOL_COOLDOWN_MINUTES", "30"))
        self.symbol_last_trade_time: Dict[str, datetime] = {}  # Track last trade time per symbol

        # Timeout Exit - Chiudi trade stagnanti
        self.timeout_enabled = os.getenv("TIMEOUT_ENABLED", "true").lower() == "true"
        self.timeout_hours = float(os.getenv("TIMEOUT_HOURS", "12"))
        self.timeout_loss_threshold = float(os.getenv("TIMEOUT_LOSS_THRESHOLD", "-3"))  # Chiudi se P&L < -3%
        self.timeout_stale_max = float(os.getenv("TIMEOUT_STALE_MAX", "1"))  # Chiudi se P&L < +1% (stagnante)

        # Smart Exit System - Health Check per posizioni
        self.health_check_enabled = os.getenv("HEALTH_CHECK_ENABLED", "true").lower() == "true"
        self.health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))  # Secondi tra check
        self.health_grace_period_minutes = float(os.getenv("HEALTH_GRACE_PERIOD_MINUTES", "5"))  # Minuti prima che HEALTH possa intervenire
        # Score thresholds
        self.health_score_healthy = int(os.getenv("HEALTH_SCORE_HEALTHY", "2"))      # >= questo = tutto ok (era 4, troppo severo)
        self.health_score_caution = int(os.getenv("HEALTH_SCORE_CAUTION", "0"))      # >= questo = stringi SL
        self.health_score_danger = int(os.getenv("HEALTH_SCORE_DANGER", "-3"))       # >= questo = SL a breakeven
        self.health_score_emergency = int(os.getenv("HEALTH_SCORE_EMERGENCY", "-4")) # < questo = chiudi
        # Profit thresholds per azioni
        self.health_min_profit_caution = float(os.getenv("HEALTH_MIN_PROFIT_CAUTION", "0.5"))
        self.health_min_profit_danger = float(os.getenv("HEALTH_MIN_PROFIT_DANGER", "0.0"))
        self.health_min_profit_emergency = float(os.getenv("HEALTH_MIN_PROFIT_EMERGENCY", "0.5"))
        # Time decay settings
        self.health_time_decay_start = float(os.getenv("HEALTH_TIME_DECAY_START", "4"))   # Ore prima di penalità
        self.health_time_decay_medium = float(os.getenv("HEALTH_TIME_DECAY_MEDIUM", "8")) # Ore per penalità media
        self.health_time_decay_severe = float(os.getenv("HEALTH_TIME_DECAY_SEVERE", "12")) # Ore per penalità grave

        # Health Score Weights (configurable via env)
        # Positive = when indicator favors position, Negative = when against
        self.health_weight_ema_pos = int(os.getenv("HEALTH_WEIGHT_EMA_POS", "2"))
        self.health_weight_ema_neg = int(os.getenv("HEALTH_WEIGHT_EMA_NEG", "-2"))
        self.health_weight_rsi_pos = int(os.getenv("HEALTH_WEIGHT_RSI_POS", "1"))
        self.health_weight_rsi_neg = int(os.getenv("HEALTH_WEIGHT_RSI_NEG", "-1"))
        self.health_weight_macd_pos = int(os.getenv("HEALTH_WEIGHT_MACD_POS", "1"))
        self.health_weight_macd_neg = int(os.getenv("HEALTH_WEIGHT_MACD_NEG", "-1"))  # Era -2, ora simmetrico
        self.health_weight_vol_pos = int(os.getenv("HEALTH_WEIGHT_VOL_POS", "1"))
        self.health_weight_vol_neg = int(os.getenv("HEALTH_WEIGHT_VOL_NEG", "-1"))
        self.health_weight_bb_pos = int(os.getenv("HEALTH_WEIGHT_BB_POS", "1"))
        self.health_weight_bb_neg = int(os.getenv("HEALTH_WEIGHT_BB_NEG", "-1"))  # Era -2, ora simmetrico
        self.health_weight_bb_squeeze = int(os.getenv("HEALTH_WEIGHT_BB_SQUEEZE", "-1"))  # Era -2
        self.health_weight_obv_pos = int(os.getenv("HEALTH_WEIGHT_OBV_POS", "1"))
        self.health_weight_obv_neg = int(os.getenv("HEALTH_WEIGHT_OBV_NEG", "-1"))
        self.health_weight_time_light = int(os.getenv("HEALTH_WEIGHT_TIME_LIGHT", "-1"))
        self.health_weight_time_medium = int(os.getenv("HEALTH_WEIGHT_TIME_MEDIUM", "-2"))
        self.health_weight_time_severe = int(os.getenv("HEALTH_WEIGHT_TIME_SEVERE", "-3"))
        self.health_weight_resilience = int(os.getenv("HEALTH_WEIGHT_RESILIENCE", "1"))

        # Leverage limits per style (configurable via env) - both MIN and MAX
        # MIN = minimum for trailing stops to work, MAX = maximum allowed
        self.leverage_prudent_min = int(os.getenv("LEVERAGE_PRUDENT_MIN", "2"))
        self.leverage_prudent_max = int(os.getenv("LEVERAGE_PRUDENT_MAX", "3"))
        self.leverage_moderate_min = int(os.getenv("LEVERAGE_MODERATE_MIN", "3"))
        self.leverage_moderate_max = int(os.getenv("LEVERAGE_MODERATE_MAX", "5"))
        self.leverage_aggressive_min = int(os.getenv("LEVERAGE_AGGRESSIVE_MIN", "5"))
        self.leverage_aggressive_max = int(os.getenv("LEVERAGE_AGGRESSIVE_MAX", "10"))
        self.leverage_macro_min = int(os.getenv("LEVERAGE_MACRO_MIN", "2"))
        self.leverage_macro_max = int(os.getenv("LEVERAGE_MACRO_MAX", "3"))

        # Trailing Stop
        self.trailing_enabled = os.getenv("TRAILING_ENABLED", "true").lower() == "true"
        self.trailing_steps = os.getenv("TRAILING_STEPS", "2.0:0.0,3.0:1.0,4.0:2.0")

        # AI Independent Mode Settings
        self.prompt_style = os.getenv("V6_PROMPT_STYLE", "PRUDENT").upper()
        self.ai_interval_minutes = int(os.getenv("V6_AI_INTERVAL_MINUTES", "5"))
        self.timeframe = os.getenv("V6_TIMEFRAME", "5min")

        # RESEARCH MODE - Advanced weighted scoring system
        self.research_mode = os.getenv("RESEARCH_MODE", "false").lower() == "true"
        self.research_min_volume_ratio = float(os.getenv("RESEARCH_MIN_VOLUME_RATIO", "0.5"))

        # HYBRID VOLUME CHECK - Real-time volume detection
        # Baseline: 15m candle for stable reference
        # Current: 1m candles for real-time activity detection
        self.volume_baseline_timeframe = os.getenv("VOLUME_BASELINE_TIMEFRAME", "15m")
        self.volume_baseline_candles = int(os.getenv("VOLUME_BASELINE_CANDLES", "1"))
        self.volume_check_timeframe = os.getenv("VOLUME_CHECK_TIMEFRAME", "1m")
        self.volume_check_candles = int(os.getenv("VOLUME_CHECK_CANDLES", "2"))
        # Minimum volume ratio per tier (current_volume / baseline_volume)
        self.volume_min_tier1 = float(os.getenv("VOLUME_MIN_TIER1", "0.3"))  # BTC, ETH
        self.volume_min_tier2 = float(os.getenv("VOLUME_MIN_TIER2", "0.5"))  # SOL, XRP, etc
        self.volume_min_tier3 = float(os.getenv("VOLUME_MIN_TIER3", "0.7"))  # DOGE, AVAX
        # Action when volume is low: VETO (block), WARN (log only)
        self.volume_low_action = os.getenv("VOLUME_LOW_ACTION", "VETO").upper()

        # OBV VETO - Configurable OBV divergence check
        self.obv_veto_enabled = os.getenv("OBV_VETO_ENABLED", "true").lower() == "true"
        self.obv_veto_min_change = float(os.getenv("OBV_VETO_MIN_PRICE_CHANGE", "0.5"))  # Min price change % to trigger VETO

        # Symbols to trade (all available cryptos)
        symbols_str = os.getenv("TRADING_SYMBOLS", "BTC,ETH,SOL")
        self.symbols = [s.strip() for s in symbols_str.split(",")]

        # === CRYPTO TIER CONFIGURATION (for RESEARCH_MODE) ===
        # Configurable thresholds and multipliers per tier
        self.tier1_threshold = float(os.getenv("CRYPTO_TIER1_THRESHOLD", "60"))
        self.tier1_multiplier = float(os.getenv("CRYPTO_TIER1_MULTIPLIER", "1.0"))
        self.tier2_threshold = float(os.getenv("CRYPTO_TIER2_THRESHOLD", "70"))
        self.tier2_multiplier = float(os.getenv("CRYPTO_TIER2_MULTIPLIER", "0.95"))
        self.tier3_threshold = float(os.getenv("CRYPTO_TIER3_THRESHOLD", "75"))  # Fixed: was 107-114 (impossible!)
        self.tier3_multiplier = float(os.getenv("CRYPTO_TIER3_MULTIPLIER", "0.85"))

        # Default tier for unknown cryptos
        self.default_crypto_tier = int(os.getenv("DEFAULT_CRYPTO_TIER", "2"))

        # Tier overrides: format "SYMBOL:TIER,SYMBOL:TIER" e.g. "PEPE:3,WIF:3,BONK:3"
        self.tier_overrides_str = os.getenv("CRYPTO_TIER_OVERRIDES", "")
        self.tier_overrides = {}
        if self.tier_overrides_str:
            for item in self.tier_overrides_str.split(","):
                if ":" in item:
                    symbol, tier = item.strip().split(":")
                    self.tier_overrides[symbol.upper()] = int(tier)

        # Build crypto_tiers dictionary using configurable values
        self.crypto_tiers = self._build_crypto_tiers()

        # Loop intervals
        self.slow_loop_interval = int(os.getenv("SLOW_LOOP_INTERVAL", "60"))  # seconds
        self.fast_loop_interval = int(os.getenv("FAST_LOOP_INTERVAL", "5"))   # seconds

        # Validate and log configuration
        self._validate_and_log()

    def _build_crypto_tiers(self) -> Dict[str, Dict]:
        """Build crypto_tiers dictionary using configurable ENV values."""
        # Base configuration for known cryptos
        base_tiers = {
            # Tier 1 - Low risk (high liquidity)
            "BTC": 1,
            "ETH": 1,
            # Tier 2 - Medium risk
            "SOL": 2,
            "XRP": 2,
            "BNB": 2,
            "LINK": 2,
            "ADA": 2,
            "SUI": 2,
            "ARB": 2,
            # Tier 3 - High risk (meme coins, low liquidity)
            "DOGE": 3,
            "AVAX": 3,
        }

        # Apply tier overrides from ENV
        for symbol, tier in self.tier_overrides.items():
            base_tiers[symbol] = tier

        # Build final dictionary with configurable thresholds/multipliers
        crypto_tiers = {}
        for symbol, tier in base_tiers.items():
            if tier == 1:
                crypto_tiers[symbol] = {
                    "tier": 1,
                    "multiplier": self.tier1_multiplier,
                    "threshold": self.tier1_threshold,
                    "min_volume": self.volume_min_tier1
                }
            elif tier == 2:
                crypto_tiers[symbol] = {
                    "tier": 2,
                    "multiplier": self.tier2_multiplier,
                    "threshold": self.tier2_threshold,
                    "min_volume": self.volume_min_tier2
                }
            else:  # tier == 3
                crypto_tiers[symbol] = {
                    "tier": 3,
                    "multiplier": self.tier3_multiplier,
                    "threshold": self.tier3_threshold,
                    "min_volume": self.volume_min_tier3
                }

        return crypto_tiers

    def get_tier_for_symbol(self, symbol: str) -> Dict:
        """Get tier info for a symbol, with fallback to default tier."""
        if symbol in self.crypto_tiers:
            return self.crypto_tiers[symbol]

        # Unknown symbol - use default tier
        default_tier = self.default_crypto_tier
        if default_tier == 1:
            return {
                "tier": 1,
                "multiplier": self.tier1_multiplier,
                "threshold": self.tier1_threshold,
                "min_volume": self.volume_min_tier1
            }
        elif default_tier == 2:
            return {
                "tier": 2,
                "multiplier": self.tier2_multiplier,
                "threshold": self.tier2_threshold,
                "min_volume": self.volume_min_tier2
            }
        else:
            return {
                "tier": 3,
                "multiplier": self.tier3_multiplier,
                "threshold": self.tier3_threshold,
                "min_volume": self.volume_min_tier3
            }

    def _validate_and_log(self):
        """Validate required fields and log configuration."""
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required in .env.baseline")
        if not self.hl_private_key:
            raise ValueError("PRIVATE_KEY (or HL_PRIVATE_KEY) is required in .env.baseline")
        if not self.hl_account_address:
            raise ValueError("WALLET_ADDRESS (or HL_ACCOUNT_ADDRESS) is required in .env.baseline")

        logger.info(f"=== {self.bot_name.upper()} CONFIGURATION ===")
        logger.info(f"  AI Model: {self.ai_model}")
        if self.reasoning_enabled:
            logger.info(f"  🧠 Reasoning: ENABLED (effort={self.reasoning_effort}, max_tokens={self.reasoning_max_tokens})")
        else:
            logger.info(f"  🧠 Reasoning: disabled")
        logger.info(f"  Prompt Style: {self.prompt_style}")
        logger.info(f"  🔬 RESEARCH_MODE: {self.research_mode}")
        if self.research_mode:
            logger.info(f"  📊 Research Min Volume: {self.research_min_volume_ratio}x")
            logger.info(f"  📊 Crypto Tiers (Threshold/Multiplier):")
            logger.info(f"     TIER 1: threshold={self.tier1_threshold}, mult={self.tier1_multiplier}")
            logger.info(f"     TIER 2: threshold={self.tier2_threshold}, mult={self.tier2_multiplier}")
            logger.info(f"     TIER 3: threshold={self.tier3_threshold}, mult={self.tier3_multiplier}")
            logger.info(f"     Default Tier: {self.default_crypto_tier}")
            if self.tier_overrides:
                logger.info(f"     Overrides: {self.tier_overrides}")
        logger.info(f"  AI Interval: {self.ai_interval_minutes} min")
        logger.info(f"  Symbols: {self.symbols}")
        logger.info(f"  Position Size: ${self.position_size_usd}")
        if self.conviction_sizing_enabled:
            logger.info(f"  💰 Conviction Sizing: ENABLED")
            logger.info(f"     TIER 1: ${self.tier1_size_usd} (Speculativo)")
            logger.info(f"     TIER 2: ${self.tier2_size_usd} (Standard)")
            logger.info(f"     TIER 3: ${self.tier3_size_usd} (High Conviction)")
            if self.force_tier > 0:
                logger.info(f"     ⚠️ FORCE_TIER: {self.force_tier} (override attivo!)")
            logger.info(f"     TIER3 Safety: ADX>{self.tier3_min_adx}, Vol>{self.tier3_min_volume_ratio}x")
        else:
            logger.info(f"  💰 Conviction Sizing: disabled (fixed ${self.position_size_usd})")
        logger.info(f"  Max Leverage: {self.max_leverage}x")
        logger.info(f"  Style Leverage: PRUDENT={self.leverage_prudent_min}-{self.leverage_prudent_max}x, MODERATE={self.leverage_moderate_min}-{self.leverage_moderate_max}x, AGGRESSIVE={self.leverage_aggressive_min}-{self.leverage_aggressive_max}x, MACRO={self.leverage_macro_min}-{self.leverage_macro_max}x")
        logger.info(f"  SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        logger.info(f"  Min Profit to Close: {self.min_profit_to_close}%")
        logger.info(f"  AI Loss Threshold: {self.ai_loss_threshold_pct}% of SL (={self.stop_loss_pct * self.ai_loss_threshold_pct / 100:.1f}%)")
        logger.info(f"  Trailing: {self.trailing_enabled} - {self.trailing_steps}")
        # BTC Watchdog logging
        if self.btc_watchdog_enabled:
            logger.info(f"  🐕 BTC Watchdog: ENABLED")
            logger.info(f"     RSI Extreme: >={self.btc_rsi_extreme} → SL +{self.btc_watchdog_extreme_sl_pct}%")
            logger.info(f"     RSI Danger: >={self.btc_rsi_danger} → SL profit-{self.btc_watchdog_danger_sl_pct}%")
            logger.info(f"     RSI Oversold: <={self.btc_rsi_oversold} → proteggi LONG")
        else:
            logger.info(f"  🐕 BTC Watchdog: disabled")
        # BTC Entry Veto logging
        if self.btc_entry_veto_enabled:
            logger.info(f"  🚫 BTC Entry Veto: ENABLED")
            logger.info(f"     Block LONG if BTC RSI >= {self.btc_entry_veto_long_rsi}")
            logger.info(f"     Block SHORT if BTC RSI <= {self.btc_entry_veto_short_rsi}")
        else:
            logger.info(f"  🚫 BTC Entry Veto: disabled")
        # RSI Entry Filter logging
        if self.rsi_entry_filter_enabled:
            logger.info(f"  📈 RSI Entry Filter: ENABLED")
            logger.info(f"     Block LONG if symbol RSI >= {self.long_max_rsi}")
            logger.info(f"     Block SHORT if symbol RSI <= {self.short_min_rsi}")
        else:
            logger.info(f"  📈 RSI Entry Filter: disabled")
        # EMA Trend Filter logging
        if self.ema_trend_filter_enabled:
            logger.info(f"  📊 EMA Trend Filter: ENABLED")
            logger.info(f"     Block SHORT if EMA stack = bullish (uptrend)")
            logger.info(f"     Block LONG if EMA stack = bearish (downtrend)")
        else:
            logger.info(f"  📊 EMA Trend Filter: disabled")
        # ADX Filter logging
        if self.adx_filter_enabled:
            logger.info(f"  📈 ADX Filter: ENABLED (max={self.adx_max})")
            logger.info(f"     Block trades when ADX >= {self.adx_max} (trend too strong)")
        else:
            logger.info(f"  📈 ADX Filter: disabled")
        # Early Exit logging
        if self.early_exit_enabled:
            logger.info(f"  🚨 Early Exit: ENABLED (after {self.early_exit_minutes} min)")
            logger.info(f"     Close if MAE >= {self.early_exit_mae_threshold}% AND MFE < {self.early_exit_mfe_threshold}%")
        else:
            logger.info(f"  🚨 Early Exit: disabled")
        # Time Stop logging
        if self.time_stop_enabled:
            logger.info(f"  ⏰ Time Stop: ENABLED (close ALL after {self.time_stop_minutes} min)")
        else:
            logger.info(f"  ⏰ Time Stop: disabled")
        # Multi-Timeframe logging
        if self.multi_timeframe_enabled:
            logger.info(f"  📊 Multi-Timeframe: ENABLED")
            logger.info(f"     1m: {self.mtf_candles_1m} candles | 15m: {self.mtf_candles_15m} candles")
            logger.info(f"     4h: {self.mtf_candles_4h} candles | 1d: {self.mtf_candles_1d} candles")
        else:
            logger.info(f"  📊 Multi-Timeframe: disabled")
        # Symbol Cooldown logging (now PRE-AI to save tokens)
        if self.symbol_cooldown_enabled:
            logger.info(f"  ⏱️ Symbol Cooldown: ENABLED ({self.symbol_cooldown_minutes} min)")
        else:
            logger.info(f"  ⏱️ Symbol Cooldown: disabled")
        # Timeout logging
        if self.timeout_enabled:
            logger.info(f"  ⏰ Timeout Exit: ENABLED ({self.timeout_hours}h)")
            logger.info(f"     Close if P&L < {self.timeout_loss_threshold}% or stagnante < {self.timeout_stale_max}%")
        else:
            logger.info(f"  ⏰ Timeout Exit: disabled")
        # Health Check logging
        if self.health_check_enabled:
            logger.info(f"  🏥 Health Check: ENABLED (every {self.health_check_interval}s)")
            logger.info(f"     Scores: HEALTHY>={self.health_score_healthy}, CAUTION>={self.health_score_caution}, DANGER>={self.health_score_danger}, EMERGENCY<{self.health_score_emergency}")
            logger.info(f"     Time Decay: {self.health_time_decay_start}h/-1, {self.health_time_decay_medium}h/-2, {self.health_time_decay_severe}h/-3")
        else:
            logger.info(f"  🏥 Health Check: disabled")
        # Volume Check logging
        logger.info(f"  📊 Volume Check: Hybrid ({self.volume_check_timeframe}x{self.volume_check_candles} / {self.volume_baseline_timeframe}x{self.volume_baseline_candles})")
        logger.info(f"     Min Volume: T1={self.volume_min_tier1}x, T2={self.volume_min_tier2}x, T3={self.volume_min_tier3}x | Action={self.volume_low_action}")
        logger.info(f"  📊 OBV VETO: {'ENABLED' if self.obv_veto_enabled else 'DISABLED'} (min_change={self.obv_veto_min_change}%)")
        logger.info(f"  Testnet: {self.hl_testnet}")
        logger.info("=" * 50)


# ==============================================================================
# AI MANAGER - V6 Prompts
# ==============================================================================

class BotoneAIManager:
    """AI Manager for Botone V6 - uses same prompts as Arena V6."""

    def __init__(self, config: BotoneV6Config, db=None):
        self.config = config
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.db = db  # Database per logging decisioni AI
        self._last_prompt = ""  # Per logging
        self._last_raw_response = ""  # Per logging
        self._last_duration_ms = 0  # Per logging

    def get_decision(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        has_position: bool,
        current_direction: Optional[TradeDirection],
        current_pnl_pct: float = 0.0,
    ) -> Tuple[str, Optional[TradeDirection], str, float, int, int, str]:
        """
        Get AI trading decision.

        Returns:
            Tuple of (action, direction, reason, confidence, leverage, conviction_tier, tier_reasoning)
            action: "open", "close", or "hold"
        """
        # RESEARCH MODE: Use weighted scoring with veto checks
        if self.config.research_mode:
            # Get tier info for this symbol (uses configurable defaults for unknown symbols)
            tier_info = self.config.get_tier_for_symbol(symbol)

            # === HARD VETO CHECKS (before calling AI) ===
            volume_ratio = market_data.get('volume_ratio', 0)
            min_volume = tier_info.get("min_volume", 0.5)
            obv_trend = market_data.get('obv_trend', 'neutral')

            # VETO 1: Volume too low (hybrid check: 2m vs 15m)
            if volume_ratio < min_volume and not has_position:
                vol_current = market_data.get('volume_current', 0)
                vol_baseline = market_data.get('volume_baseline', 0)
                reason = f"Volume {volume_ratio:.2f}x < {min_volume}x min for Tier-{tier_info['tier']} (2m={vol_current:.0f}/15m={vol_baseline:.0f})"

                if self.config.volume_low_action == "VETO":
                    logger.info(f"[RESEARCH] {symbol}: 🚫 VETO: {reason}")
                    # Salva VETO nel database per analisi
                    self._save_veto_log(symbol, "VOLUME_VETO", reason, market_data)
                    return "hold", None, f"VETO: {reason}", 0.0, 1, 2, "VETO - no tier applicable"
                else:  # WARN mode
                    logger.warning(f"[RESEARCH] {symbol}: ⚠️ WARN: {reason} (continuing anyway)")

            # VETO 2: OBV divergence (only check for new entries)
            # Now configurable via OBV_VETO_ENABLED and OBV_VETO_MIN_PRICE_CHANGE
            if not has_position and self.config.obv_veto_enabled:
                change_1h = market_data.get('change_1h', 0)
                price_trend = "up" if change_1h > 0 else "down"
                obv_opposite = (price_trend == "up" and obv_trend == "FALLING") or \
                               (price_trend == "down" and obv_trend == "RISING")
                # Only VETO if price change is significant (above min threshold)
                if obv_opposite and abs(change_1h) > self.config.obv_veto_min_change:
                    reason = f"VETO: OBV divergence - price {price_trend} ({change_1h:+.2f}%) but OBV {obv_trend} (whale distribution risk)"
                    logger.info(f"[RESEARCH] {symbol}: 🚫 {reason}")
                    # Salva VETO nel database per analisi
                    self._save_veto_log(symbol, "OBV_VETO", reason, market_data)
                    return "hold", None, reason, 0.0, 1, 2, "VETO - no tier applicable"
                elif obv_opposite:
                    # Small price change, just warn but don't VETO
                    logger.debug(f"[RESEARCH] {symbol}: ⚠️ OBV divergence detected but price change {change_1h:+.2f}% < {self.config.obv_veto_min_change}% threshold, continuing")

            # VETO 3: Symbol Cooldown (prevent overtrading same symbol)
            # Moved here BEFORE AI call to save tokens
            if not has_position and self.config.symbol_cooldown_enabled:
                last_trade_time = self.config.symbol_last_trade_time.get(symbol)
                if last_trade_time:
                    elapsed_minutes = (datetime.now() - last_trade_time).total_seconds() / 60
                    if elapsed_minutes < self.config.symbol_cooldown_minutes:
                        remaining = self.config.symbol_cooldown_minutes - elapsed_minutes
                        reason = f"Cooldown active - last trade {elapsed_minutes:.0f}min ago, need {remaining:.0f}min more"
                        logger.info(f"[RESEARCH] {symbol}: ⏳ VETO: {reason}")
                        self._save_veto_log(symbol, "COOLDOWN_VETO", reason, market_data)
                        return "hold", None, f"VETO: {reason}", 0.0, 1, 2, "VETO - cooldown active"

            # VETO 4: ADX too high (trend too strong = entering too late)
            # Data shows ADX >40 has -1.17% avg P&L, while ADX <20 has +3.79%!
            if not has_position and self.config.adx_filter_enabled:
                adx = market_data.get('adx', 0)
                if adx and adx >= self.config.adx_max:
                    reason = f"ADX {adx:.1f} >= {self.config.adx_max} (trend too strong, entering too late)"
                    logger.info(f"[RESEARCH] {symbol}: 📊 VETO: {reason}")
                    self._save_veto_log(symbol, "ADX_VETO", reason, market_data)
                    return "hold", None, f"VETO: {reason}", 0.0, 1, 2, "VETO - ADX too high"

            # Build research prompt with tier info
            prompt = self._build_research_prompt(
                symbol, market_data, tier_info, has_position, current_direction, current_pnl_pct
            )
        else:
            # Standard V6 prompt
            prompt = self._build_v6_prompt(
                symbol, market_data, has_position, current_direction, current_pnl_pct
            )

        response = self._call_ai(prompt)
        if not response:
            # Salva anche i fallimenti nel DB per debug
            self._save_decision_log(symbol, response)
            return "hold", None, "AI call failed", 0.0, 1, 2, "AI call failed - default tier"

        # Salva la decisione nel database per analisi
        self._save_decision_log(symbol, response)

        return self._parse_response(response)

    def _save_decision_log(self, symbol: str, parsed_response: Optional[Dict]) -> None:
        """Save AI decision to database for debugging."""
        if not self.db or not hasattr(self.db, 'save_ai_decision'):
            return
        try:
            self.db.save_ai_decision(
                symbol=symbol,
                full_prompt=self._last_prompt[:10000] if self._last_prompt else "",  # Limita lunghezza
                ai_raw_response=self._last_raw_response[:5000] if self._last_raw_response else "",
                parsed_decision=parsed_response or {},
                model_used=self.config.ai_model,
                duration_ms=self._last_duration_ms,
            )
        except Exception as e:
            logger.warning(f"[AI] Failed to save decision log: {e}")

    def _save_veto_log(self, symbol: str, veto_type: str, reason: str, market_data: Dict) -> None:
        """Save VETO decision to database for debugging (before AI is called)."""
        if not self.db or not hasattr(self.db, 'save_ai_decision'):
            return
        try:
            # Salva il VETO come se fosse una decisione AI con info speciali
            veto_decision = {
                "action": "hold",
                "veto_type": veto_type,
                "reason": reason,
                "market_snapshot": {
                    "price": market_data.get("price"),
                    "macd": market_data.get("macd"),
                    "rsi": market_data.get("rsi"),
                    "adx": market_data.get("adx"),
                    "volume_ratio": market_data.get("volume_ratio"),
                    "obv_trend": market_data.get("obv_trend"),
                }
            }
            self.db.save_ai_decision(
                symbol=symbol,
                full_prompt=f"[VETO - AI NOT CALLED] {veto_type}: {reason}",
                ai_raw_response=f"BLOCKED BY {veto_type}",
                parsed_decision=veto_decision,
                model_used="VETO_SYSTEM",
                duration_ms=0,
            )
            logger.debug(f"[AI] Saved {veto_type} for {symbol}")
        except Exception as e:
            logger.warning(f"[AI] Failed to save veto log: {e}")

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

    def _build_research_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        tier_info: Dict[str, Any],
        has_position: bool,
        current_direction: Optional[TradeDirection],
        current_pnl_pct: float,
    ) -> str:
        """
        Build RESEARCH MODE prompt with weighted scoring system.
        Based on academic research on crypto technical indicators.
        """
        tier = tier_info.get("tier", 2)
        multiplier = tier_info.get("multiplier", 1.0)
        threshold = tier_info.get("threshold", 70)

        position_info = ""
        if has_position and current_direction:
            position_info = f"""
CURRENT POSITION:
- Direction: {current_direction.value}
- P&L: {current_pnl_pct:+.2f}%
- Entry Price: ${market_data.get('entry_price', 0):,.2f}
"""

        # Extract stochastic data
        stoch_k = market_data.get('stoch_k', 50)
        stoch_d = market_data.get('stoch_d', 50)
        stoch_signal = market_data.get('stoch_signal', 'NEUTRAL')
        stoch_zone = market_data.get('stoch_zone', 'NEUTRAL')

        bb_squeeze_text = "⚠️ SQUEEZE DETECTED - wait for breakout" if market_data.get('bb_squeeze', False) else "no squeeze"

        # Build multi-timeframe section if data available
        mtf_section = ""
        mtf_data = market_data.get("mtf_data", {})
        if mtf_data:
            # Use MarketDataProvider's format method via self reference
            # Since we don't have direct access, build inline
            mtf_lines = ["", "═══════════════════════════════════════════════════════════════════════",
                        "                    MULTI-TIMEFRAME ANALYSIS",
                        "═══════════════════════════════════════════════════════════════════════"]

            for label, data in mtf_data.items():
                summary = data.get("summary", {})
                trend = summary.get("trend", "?")
                change = summary.get("change_pct", 0)
                high = summary.get("high", 0)
                low = summary.get("low", 0)
                range_pct = summary.get("range_pct", 0)

                mtf_lines.append(f"\n{label.upper()} ({data.get('count', 0)} candles):")
                mtf_lines.append(f"  Trend: {trend} ({change:+.2f}%)")
                mtf_lines.append(f"  Range: ${low:.4f} - ${high:.4f} ({range_pct:.2f}%)")

                # Add last 5 candles as compact OHLC
                candles = data.get("candles", [])[-5:]
                if candles:
                    mtf_lines.append(f"  Last {len(candles)} candles (O/H/L/C):")
                    for c in candles:
                        change_c = ((c['c'] - c['o']) / c['o'] * 100) if c['o'] > 0 else 0
                        direction = "▲" if change_c > 0 else "▼" if change_c < 0 else "─"
                        mtf_lines.append(f"    {direction} {c['o']:.4f}/{c['h']:.4f}/{c['l']:.4f}/{c['c']:.4f}")

            mtf_lines.append("")
            mtf_lines.append("═══════════════════════════════════════════════════════════════════════")
            mtf_lines.append("                MTF HIERARCHY RULES (STRICT!)")
            mtf_lines.append("═══════════════════════════════════════════════════════════════════════")
            mtf_lines.append("")
            mtf_lines.append("1. 1D TREND IS KING - Defines allowed direction:")
            mtf_lines.append("   • 1D UP (>+5%) → Only LONG allowed, SHORT forbidden")
            mtf_lines.append("   • 1D DOWN (<-5%) → Only SHORT allowed, LONG forbidden")
            mtf_lines.append("   • 1D FLAT (-5% to +5%) → Both directions allowed")
            mtf_lines.append("")
            mtf_lines.append("2. 4H CONFIRMS OR SHOWS PULLBACK:")
            mtf_lines.append("   • 1D UP + 4H UP → STRONG LONG (+10 bonus)")
            mtf_lines.append("   • 1D DOWN + 4H DOWN → STRONG SHORT (+10 bonus)")
            mtf_lines.append("   • 1D UP + 4H DOWN → PULLBACK! Look for LONG entry (Tier 1-2)")
            mtf_lines.append("   • 1D DOWN + 4H UP → PULLBACK! Look for SHORT entry (Tier 1-2)")
            mtf_lines.append("")
            mtf_lines.append("3. PULLBACK ENTRY CONDITIONS (when 1D vs 4H conflict):")
            mtf_lines.append("   • RSI oversold (<35) for LONG pullback = GOOD entry")
            mtf_lines.append("   • RSI overbought (>65) for SHORT pullback = GOOD entry")
            mtf_lines.append("   • Price near support (S1/S2) for LONG = GOOD entry")
            mtf_lines.append("   • Price near resistance (R1/R2) for SHORT = GOOD entry")
            mtf_lines.append("   • Stochastic showing reversal signal = confirmation")
            mtf_lines.append("")
            mtf_lines.append("4. 15M/1M ARE FOR TIMING ONLY:")
            mtf_lines.append("   • Use lower timeframes to find precise entry point")
            mtf_lines.append("   • Do NOT use them to determine direction")
            mtf_lines.append("")
            mtf_lines.append("5. ALIGNMENT BONUSES:")
            mtf_lines.append("   • All 4 timeframes aligned → +10 bonus points")
            mtf_lines.append("   • Pullback setup with reversal signal → OK to trade (Tier 1-2)")
            mtf_lines.append("")

            mtf_section = "\n".join(mtf_lines)

        return f"""🔬 RESEARCH MODE - WEIGHTED SCORING SYSTEM
Symbol: {symbol}
Tier: {tier} (multiplier: {multiplier:.2f}x, threshold: {threshold})
{position_info}

═══════════════════════════════════════════════════════════════════════
                    PRICE & INDICATOR DATA
═══════════════════════════════════════════════════════════════════════

PRICE:
- Current: ${market_data.get('price', 0):,.2f}
- Change 1h: {market_data.get('change_1h', 0):+.2f}%
- Change 24h: {market_data.get('change_24h', 0):+.2f}%

CATEGORY A - TREND CONFIRMATION (40 points max):
- EMA Stack: {market_data.get('ema_stack', 'neutral')} (aligned=15 pts, partial=8 pts, not aligned=0 pts)
- ADX: {market_data.get('adx', 0):.1f} (>30=15 pts, 25-30=10 pts, <25=0 pts)
- MACD: {market_data.get('macd', 0):.4f} (>0 AND above signal=10 pts)
- MACD Line vs Signal: {market_data.get('macd_line', 0):.4f} vs {market_data.get('macd_signal', 0):.4f}

CATEGORY B - MOMENTUM (30 points max):
- RSI(9): {market_data.get('rsi', 50):.1f} (>50 for bullish=10 pts, <50 for bearish=10 pts)
- Stochastic %K: {stoch_k:.1f} | %D: {stoch_d:.1f} | Signal: {stoch_signal} | Zone: {stoch_zone}
  (crossover in oversold/overbought=15 pts, in neutral=8 pts)
- MACD Histogram: {market_data.get('macd_hist_trend', 'neutral')} (growing=5 pts)

CATEGORY C - VOLUME CONFIRMATION (30 points max):
- Volume Ratio: {market_data.get('volume_ratio', 1.0):.2f}x (>1.5x=15 pts, 1.0-1.5x=10 pts, 0.5-1.0x=5 pts)
- OBV Trend: {market_data.get('obv_trend', 'neutral')} (aligned with price=10 pts, divergence bonus=5 pts)
- Open Interest: ${market_data.get('open_interest', 0):,.0f}

BOLLINGER BANDS:
- Position: {market_data.get('bb_position', 'MIDDLE')}
- %B: {market_data.get('bb_percent_b', 0.5):.2f}
- Status: {bb_squeeze_text}

PIVOT POINTS:
- R2: ${market_data.get('pivot_r2', 0):,.2f} | R1: ${market_data.get('pivot_r1', 0):,.2f}
- PP: ${market_data.get('pivot_pp', 0):,.2f}
- S1: ${market_data.get('pivot_s1', 0):,.2f} | S2: ${market_data.get('pivot_s2', 0):,.2f}

SENTIMENT:
- Funding Rate: {market_data.get('funding_rate', 0):.4%}
- Fear & Greed: {market_data.get('fear_greed', 50)}

═══════════════════════════════════════════════════════════════════════
                    SCORING INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════

STEP 0: DETERMINE SETUP DIRECTION FIRST (CRITICAL!)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEFORE scoring, you MUST identify the setup direction:

1. Check EMA Stack + Price position:
   - Price > EMA20 AND EMA Stack bullish → LONG setup
   - Price < EMA20 AND EMA Stack bearish → SHORT setup

2. Confirm with 4H/1D trend (if MTF data available):
   - 1D UP + 4H UP → confirms LONG
   - 1D DOWN + 4H DOWN → confirms SHORT
   - Conflicting timeframes → NEUTRAL (likely NO_TRADE)

3. IMPORTANT: Once direction is determined:
   - Score ONLY indicators that support THAT direction
   - RSI >50 gives points ONLY for LONG setups
   - RSI <50 gives points ONLY for SHORT setups
   - Do NOT mix bullish and bearish points together!

STEP 1: CALCULATE RAW SCORE (0-100 points)
Score ONLY indicators aligned with your chosen direction:
- Category A (Trend): up to 40 points
- Category B (Momentum): up to 30 points
- Category C (Volume): up to 30 points

STEP 2: APPLY CRYPTO MULTIPLIER
- Adjusted Score = Raw Score × {multiplier:.2f}

STEP 3: COMPARE TO THRESHOLD
- Required: {threshold} points for Tier-{tier}
- If Adjusted Score < {threshold} → NO_TRADE

STEP 4: CONVERT TO REALISTIC WIN RATE
- 100 pts = 65% win rate (not 100%!)
- 80 pts = 59% win rate
- 60 pts = 53% win rate

═══════════════════════════════════════════════════════════════════════
                    SPECIAL RULES
═══════════════════════════════════════════════════════════════════════

RSI RULE (crypto-specific):
- DO NOT use traditional 30/70 overbought/oversold
- USE: RSI >50 = bullish momentum (+10 pts)
- USE: RSI <50 = bearish momentum (+10 pts for short)
- RSI divergence with price = +5 bonus

STOCHASTIC RULE:
- More important than RSI alone (15 pts vs 10 pts)
- Crossover in oversold (<30) = STRONG BUY
- Crossover in overbought (>70) = STRONG SELL

BOLLINGER SQUEEZE RULE (BALANCED):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- If squeeze detected → CAUTION, prefer waiting for breakout
- SQUEEZE + CAN TRADE CONDITIONS (Tier 1 only):
  1. Volume > 1.0x (not dead market)
  2. ADX > 20 (some trend present)
  3. MTF aligned (1D and 4H same direction)
  4. If all 3 met → Tier 1 OK, reduce confidence by 0.2
- SQUEEZE + NO TRADE CONDITIONS:
  1. Volume < 0.8x (dead market)
  2. ADX < 20 (no trend)
  3. MTF conflicting
  → If any of these, skip trade
- BREAKOUT CONFIRMATION (for Tier 2-3 during squeeze):
  1. Candle CLOSES outside Bollinger Band
  2. Volume > 1.5x average

ADX RULE (balanced for crypto):
- ADX <20: SKIP trade (strongly ranging market)
- ADX 20-25: OK but Tier 1 only (weak trend)
- ADX 25-30: OK, Tier 2 allowed
- ADX >30: Strong trend, Tier 3 allowed

WARNING SIGNALS (reduce position or SKIP):
- OBV opposite to price = whale distribution (DANGER)
- Volume >3x suddenly without news = potential pump & dump
- Funding rate >0.05% or <-0.05% = squeeze risk
- Bollinger squeeze + low volume = likely fake breakout

═══════════════════════════════════════════════════════════════════════
                    CONVICTION TIER (OBBLIGATORIO)
═══════════════════════════════════════════════════════════════════════

Valuta la QUALITÀ COMPLESSIVA del setup e assegna un tier per il sizing:

TIER 1 - SPECULATIVO ($25):
- Segnale presente ma debole
- ADX 20-25 (trend debole ma presente)
- Volume 0.8x - 1.0x (partecipazione bassa)
- Score appena sopra threshold (< 10 punti)
- Pullback setup (1D UP + 4H DOWN con segnale reversal)
- Squeeze con condizioni OK (Volume >1x, ADX >20, MTF aligned)

TIER 2 - STANDARD ($35):
- Indicatori allineati
- Trend definito (ADX 20-30)
- Volume normale (0.8x - 1.2x)
- Setup classico, no red flags

TIER 3 - HIGH CONVICTION ($50):
RICHIEDE TUTTI questi criteri:
- ADX > 25 (trend forte)
- Volume > 1.2x (conferma)
- NO Bollinger squeeze
- NO divergenze OBV
- Score almeno 15 punti sopra threshold
- Pattern tecnico chiaro (breakout, double bottom, etc.)
{mtf_section}
═══════════════════════════════════════════════════════════════════════

OUTPUT FORMAT (JSON):
{{
  "raw_score": 0-100,
  "score_breakdown": {{
    "trend": X/40,
    "momentum": X/30,
    "volume": X/30
  }},
  "adjusted_score": raw_score × {multiplier:.2f},
  "threshold": {threshold},
  "decision": "BUY/SELL/NO_TRADE",
  "action": "open/close/hold",
  "direction": "LONG/SHORT" (if action=open),
  "leverage": 1-{self.config.max_leverage},
  "confidence": 0.0-1.0,
  "conviction_tier": 1/2/3,
  "tier_reasoning": "Motivo breve della scelta del tier",
  "win_rate_expected": "XX%",
  "reason": "brief explanation",
  "warnings": ["list any warning signals detected"],
  "key_factors": ["top 2-3 factors driving decision"]
}}"""

    def _call_ai(self, prompt: str, retry_without_reasoning: bool = True) -> Optional[Dict[str, Any]]:
        """Call OpenRouter API."""
        import time as time_module
        start_time = time_module.time()

        # Salva prompt per logging
        self._last_prompt = prompt
        self._last_raw_response = ""
        self._last_duration_ms = 0

        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        use_reasoning = self.config.reasoning_enabled and retry_without_reasoning

        # When reasoning enabled, use REASONING_MAX_TOKENS from env
        # Reasoning tokens count against max_tokens limit
        max_tokens = self.config.reasoning_max_tokens if use_reasoning else 500

        payload = {
            "model": self.config.ai_model,
            "messages": [
                {"role": "system", "content": "You are a crypto trading AI. After your reasoning, you MUST output a valid JSON response."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }

        # Add reasoning parameters if enabled
        # DeepSeek V3.2-Exp only supports "enabled: true" (not effort/max_tokens)
        # Other models (OpenAI o1/o3, Anthropic) support effort/max_tokens
        if use_reasoning:
            # Simple format that works with DeepSeek V3.2-Exp
            payload["reasoning"] = {"enabled": True}
            # Increase max_tokens to leave room for reasoning + response
            payload["max_tokens"] = self.config.reasoning_max_tokens
            logger.debug(f"Reasoning enabled, max_tokens: {payload['max_tokens']}")

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60 if use_reasoning else 30
            )
            response.raise_for_status()

            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning", "")

            # Log reasoning if present
            if reasoning:
                logger.info(f"AI Reasoning: {reasoning[:300]}...")

            # Log content
            if content:
                logger.info(f"AI Response: {content[:200]}...")
            else:
                logger.debug("AI Response content is empty (reasoning model may put JSON elsewhere)")

            # Try to extract JSON from content first, then from reasoning if content is empty/invalid
            result = self._extract_json(content) if content else None
            if result is None and reasoning:
                logger.debug("Trying to extract JSON from reasoning field...")
                result = self._extract_json(reasoning)

            # Salva dati per logging
            self._last_raw_response = content or reasoning or ""
            self._last_duration_ms = int((time_module.time() - start_time) * 1000)

            return result

        except requests.exceptions.Timeout:
            logger.error("AI call timeout")
            return None
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            response_text = ""
            try:
                response_text = e.response.text if e.response is not None else ""
            except:
                pass

            # If 400 error and reasoning was enabled, retry without reasoning
            if status_code == 400 and use_reasoning and retry_without_reasoning:
                logger.warning(f"⚠️ Model {self.config.ai_model} doesn't support reasoning (400), retrying without...")
                return self._call_ai(prompt, retry_without_reasoning=False)

            logger.error(f"AI call HTTP error {status_code}: {e}")
            logger.error(f"Response body: {response_text[:500] if response_text else 'empty'}")
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
    ) -> Tuple[str, Optional[TradeDirection], str, float, int, int, str]:
        """Parse AI response.

        Returns:
            Tuple of (action, direction, reason, confidence, leverage, conviction_tier, tier_reasoning)
        """
        action = response.get("action", response.get("operation", "hold")).lower()

        direction = None
        leverage = 1

        if action == "open":
            dir_str = response.get("direction", "").upper()
            if dir_str in ["LONG", "SHORT"]:
                direction = TradeDirection(dir_str)
            else:
                action = "hold"  # Can't open without direction

            # Parse leverage - enforce min/max based on style
            try:
                ai_leverage = int(response.get("leverage", 3))
                min_leverage = self._get_min_leverage_for_style()
                max_leverage = self._get_max_leverage_for_style()
                leverage = max(min_leverage, min(ai_leverage, max_leverage))

                if ai_leverage < min_leverage:
                    logger.info(f"[AI] Leverage {ai_leverage}x → enforced minimum {min_leverage}x for {self.config.prompt_style} style")
                elif ai_leverage > max_leverage:
                    logger.info(f"[AI] Leverage {ai_leverage}x → capped to max {max_leverage}x for {self.config.prompt_style} style")
            except (ValueError, TypeError):
                leverage = self._get_min_leverage_for_style()  # Default to min for style

        # Parse conviction tier (default to TIER 2 if not provided)
        try:
            conviction_tier = int(response.get("conviction_tier", 2))
            if conviction_tier not in [1, 2, 3]:
                conviction_tier = 2  # Default to standard
        except (ValueError, TypeError):
            conviction_tier = 2

        tier_reasoning = response.get("tier_reasoning", "No tier reasoning provided")

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

        return action, direction, reason, confidence, leverage, conviction_tier, tier_reasoning

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

    def _get_min_leverage_for_style(self) -> int:
        """
        Get minimum leverage based on trading style from config.
        This ensures trailing stops can realistically trigger.
        """
        style = self.config.prompt_style

        if style == "PRUDENT":
            return self.config.leverage_prudent_min
        elif style == "AGGRESSIVE":
            return self.config.leverage_aggressive_min
        elif style == "MACRO":
            return self.config.leverage_macro_min
        else:  # MODERATE
            return self.config.leverage_moderate_min

    def _get_max_leverage_for_style(self) -> int:
        """
        Get maximum leverage based on trading style from config.
        """
        style = self.config.prompt_style

        if style == "PRUDENT":
            return self.config.leverage_prudent_max
        elif style == "AGGRESSIVE":
            return self.config.leverage_aggressive_max
        elif style == "MACRO":
            return self.config.leverage_macro_max
        else:  # MODERATE
            return self.config.leverage_moderate_max

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
        self._info = None  # Cached Info object to avoid creating new connections
        # Cache for hybrid volume ratio (refresh every 60s to avoid FAST loop API spam)
        self._volume_cache: Dict[str, Tuple[float, float, float, datetime]] = {}  # symbol -> (ratio, current, baseline, timestamp)
        self._volume_cache_ttl = 60  # seconds

    def _get_info(self):
        """Lazy load Info object - reuse to avoid 100 connection limit."""
        if self._info is None:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            base_url = constants.TESTNET_API_URL if self.config.hl_testnet else constants.MAINNET_API_URL
            self._info = Info(base_url, skip_ws=True)  # skip_ws=True avoids websocket!
            logger.info("[MARKET] Created cached Info object (skip_ws=True)")
        return self._info

    def get_analyzer(self):
        """Lazy load analyzer."""
        if self._analyzer is None:
            from indicators import CryptoTechnicalAnalysisHL
            self._analyzer = CryptoTechnicalAnalysisHL(testnet=self.config.hl_testnet)
        return self._analyzer

    def get_price(self, symbol: str) -> float:
        """Get current price for symbol using cached Info object."""
        try:
            info = self._get_info()
            mids = info.all_mids()
            return float(mids.get(symbol, 0))
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0.0

    def get_hybrid_volume_ratio(self, symbol: str, force_refresh: bool = False) -> Tuple[float, float, float]:
        """
        Get hybrid volume ratio using 1m candles for current activity
        and 15m candle for baseline. CACHED for 60s to avoid FAST loop API spam.

        Args:
            symbol: Trading symbol
            force_refresh: If True, bypass cache and fetch fresh data (use in SLOW loop)

        Returns:
            Tuple of (ratio, current_volume, baseline_volume)
            ratio = sum(last N 1m candles) / sum(baseline 15m candles normalized)
        """
        # Check cache first (unless force_refresh)
        if not force_refresh and symbol in self._volume_cache:
            cached_ratio, cached_current, cached_baseline, cached_time = self._volume_cache[symbol]
            age_seconds = (datetime.now() - cached_time).total_seconds()
            if age_seconds < self._volume_cache_ttl:
                return (cached_ratio, cached_current, cached_baseline)

        try:
            analyzer = self.get_analyzer()

            # Get 1m candles for current activity (last 2 candles by default)
            check_tf = self.config.volume_check_timeframe  # "1m"
            check_candles = self.config.volume_check_candles  # 2

            # Get baseline candles (15m by default)
            baseline_tf = self.config.volume_baseline_timeframe  # "15m"
            baseline_candles = self.config.volume_baseline_candles  # 1

            # Fetch candles using the analyzer's fetch_ohlcv method
            # Need a bit more candles to ensure we have enough data
            df_check = analyzer.fetch_ohlcv(symbol, check_tf, limit=check_candles + 5)
            df_baseline = analyzer.fetch_ohlcv(symbol, baseline_tf, limit=baseline_candles + 5)

            if df_check.empty or df_baseline.empty:
                logger.warning(f"[VOLUME] Empty candles for {symbol}")
                return (1.0, 0, 0)  # Default ratio = 1.0 (neutral)

            # Get the last N candles for each
            recent_check = df_check.tail(check_candles)
            recent_baseline = df_baseline.tail(baseline_candles)

            # Sum volumes
            current_volume = float(recent_check['volume'].sum())
            baseline_volume = float(recent_baseline['volume'].sum())

            # Normalize baseline to same time window
            # If checking 2 x 1m = 2 minutes, baseline 1 x 15m = 15 minutes
            # Normalize: baseline_per_minute = baseline_volume / 15
            # Then compare: current (2 min) vs expected (2 min at baseline rate)
            check_minutes = check_candles  # 1m candles
            baseline_minutes = baseline_candles * 15  # 15m candles

            if baseline_minutes > 0 and baseline_volume > 0:
                baseline_per_minute = baseline_volume / baseline_minutes
                expected_volume = baseline_per_minute * check_minutes
                ratio = current_volume / expected_volume if expected_volume > 0 else 1.0
            else:
                ratio = 1.0

            # Update cache
            self._volume_cache[symbol] = (ratio, current_volume, baseline_volume, datetime.now())

            return (ratio, current_volume, baseline_volume)

        except Exception as e:
            logger.error(f"[VOLUME] Error calculating hybrid volume for {symbol}: {e}")
            return (1.0, 0, 0)  # Default ratio = 1.0 (neutral)

    def get_multi_timeframe_candles(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch candles from multiple timeframes for broader market context.
        Returns formatted candle data for AI prompt.

        Args:
            symbol: Trading symbol

        Returns:
            Dict with candle data per timeframe, formatted for AI consumption
        """
        if not self.config.multi_timeframe_enabled:
            return {}

        result = {}

        try:
            analyzer = self.get_analyzer()

            # Define timeframes to fetch
            timeframes = [
                ("1m", self.config.mtf_candles_1m, "1min"),
                ("15m", self.config.mtf_candles_15m, "15min"),
                ("4h", self.config.mtf_candles_4h, "4hour"),
                ("1d", self.config.mtf_candles_1d, "1day"),
            ]

            for tf, count, label in timeframes:
                if count <= 0:
                    continue

                try:
                    df = analyzer.fetch_ohlcv(symbol, tf, limit=count + 2)

                    if df.empty:
                        continue

                    # Get last N candles
                    candles = df.tail(count)

                    # Format candles compactly for AI
                    candle_data = []
                    for idx, row in candles.iterrows():
                        candle_data.append({
                            "o": round(float(row.get('open', 0)), 4),
                            "h": round(float(row.get('high', 0)), 4),
                            "l": round(float(row.get('low', 0)), 4),
                            "c": round(float(row.get('close', 0)), 4),
                            "v": int(float(row.get('volume', 0))),
                        })

                    # Calculate summary stats for this timeframe
                    if len(candle_data) > 0:
                        closes = [c['c'] for c in candle_data]
                        highs = [c['h'] for c in candle_data]
                        lows = [c['l'] for c in candle_data]

                        first_close = closes[0] if closes else 0
                        last_close = closes[-1] if closes else 0
                        change_pct = ((last_close - first_close) / first_close * 100) if first_close > 0 else 0

                        result[label] = {
                            "count": len(candle_data),
                            "candles": candle_data,
                            "summary": {
                                "trend": "UP" if change_pct > 0.5 else "DOWN" if change_pct < -0.5 else "FLAT",
                                "change_pct": round(change_pct, 2),
                                "high": max(highs) if highs else 0,
                                "low": min(lows) if lows else 0,
                                "range_pct": round((max(highs) - min(lows)) / min(lows) * 100, 2) if min(lows) > 0 else 0,
                            }
                        }

                except Exception as e:
                    logger.warning(f"[MTF] Error fetching {tf} candles for {symbol}: {e}")
                    continue

            return result

        except Exception as e:
            logger.error(f"[MTF] Error getting multi-timeframe data for {symbol}: {e}")
            return {}

    def format_mtf_for_prompt(self, mtf_data: Dict[str, Any]) -> str:
        """
        Format multi-timeframe data as a compact string for AI prompt.
        """
        if not mtf_data:
            return ""

        lines = ["", "═══════════════════════════════════════════════════════════════════════",
                 "                    MULTI-TIMEFRAME ANALYSIS",
                 "═══════════════════════════════════════════════════════════════════════"]

        for label, data in mtf_data.items():
            summary = data.get("summary", {})
            trend = summary.get("trend", "?")
            change = summary.get("change_pct", 0)
            high = summary.get("high", 0)
            low = summary.get("low", 0)
            range_pct = summary.get("range_pct", 0)

            lines.append(f"\n{label.upper()} ({data.get('count', 0)} candles):")
            lines.append(f"  Trend: {trend} ({change:+.2f}%)")
            lines.append(f"  Range: ${low:.4f} - ${high:.4f} ({range_pct:.2f}%)")

            # Add last 5 candles as compact OHLC
            candles = data.get("candles", [])[-5:]  # Last 5 only to save tokens
            if candles:
                lines.append(f"  Last {len(candles)} candles (O/H/L/C):")
                for i, c in enumerate(candles):
                    change_c = ((c['c'] - c['o']) / c['o'] * 100) if c['o'] > 0 else 0
                    direction = "▲" if change_c > 0 else "▼" if change_c < 0 else "─"
                    lines.append(f"    {direction} {c['o']:.4f}/{c['h']:.4f}/{c['l']:.4f}/{c['c']:.4f}")

        lines.append("")
        lines.append("MULTI-TIMEFRAME INTERPRETATION:")
        lines.append("- If ALL timeframes show same trend → STRONG signal")
        lines.append("- If 1m/15m UP but 4h/1d DOWN → possible reversal, CAUTION")
        lines.append("- If short-term opposite to long-term → wait for alignment")
        lines.append("")

        return "\n".join(lines)

    def get_market_data(self, symbol: str, force_refresh_volume: bool = False) -> Dict[str, Any]:
        """Get full market data for a symbol.

        Args:
            symbol: Trading symbol
            force_refresh_volume: If True, bypass volume cache (use in SLOW loop for VETO check)
        """
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
            obv_data = analysis.get("obv", {})
            obv_trend = obv_data.get("trend", "FLAT")

            # Extract Pivot Points
            pivot_points = analysis.get("pivot_points", {})

            # Extract Stochastic (NEW)
            stochastic = analysis.get("stochastic", {})
            stoch_k = stochastic.get("k", 50)
            stoch_d = stochastic.get("d", 50)
            stoch_signal = stochastic.get("signal", "NEUTRAL")
            stoch_zone = stochastic.get("zone", "NEUTRAL")

            # MACD analysis
            macd_analysis = analysis.get("macd_analysis", {})
            macd_hist_trend = macd_analysis.get("histogram_trend", "neutral")

            # HYBRID VOLUME CHECK - use 1m candles for real-time detection
            # force_refresh_volume=True in SLOW loop for accurate VETO check
            hybrid_vol_ratio, hybrid_current_vol, hybrid_baseline_vol = self.get_hybrid_volume_ratio(symbol, force_refresh=force_refresh_volume)

            return {
                "price": price,
                "macd": current.get("macd", 0),
                "macd_line": current.get("macd_line", 0),
                "macd_signal": current.get("macd_signal", 0),
                "macd_hist_trend": macd_hist_trend,
                "rsi": current.get("rsi_9", current.get("rsi_14", 50)),  # Prefer RSI 9
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

                # Stochastic Oscillator (NEW for RESEARCH_MODE)
                "stoch_k": stoch_k,
                "stoch_d": stoch_d,
                "stoch_signal": stoch_signal,
                "stoch_zone": stoch_zone,

                # Pivot Points (NEW)
                "pivot_pp": pivot_points.get("pp", 0),
                "pivot_r1": pivot_points.get("r1", 0),
                "pivot_r2": pivot_points.get("r2", 0),
                "pivot_s1": pivot_points.get("s1", 0),
                "pivot_s2": pivot_points.get("s2", 0),

                # Volume - HYBRID: 1m candles for current, 15m for baseline
                "volume_24h": longer_term.get("volume_current", 0),  # Kept for reference
                "volume_ratio": hybrid_vol_ratio,  # NEW: real-time hybrid check
                "volume_current": hybrid_current_vol,  # Sum of last 2x 1m candles
                "volume_baseline": hybrid_baseline_vol,  # Sum of last 1x 15m candle

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

        # Initialize database FIRST (needed by ai_manager for logging)
        self.db = None
        if DB_AVAILABLE:
            try:
                self.db = TradeDatabase()
                if self.db.enabled:
                    logger.info("📊 Database trade tracking: ENABLED")
                else:
                    logger.info("📊 Database trade tracking: DISABLED (connection failed)")
            except Exception as e:
                logger.warning(f"📊 Database trade tracking: DISABLED ({e})")

        # Now initialize ai_manager WITH database reference for decision logging
        self.ai_manager = BotoneAIManager(self.config, db=self.db)
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

        # Health check timing
        self._last_health_check: datetime = datetime.min

        logger.info(f"Botone V6 initialized - AI Model: {self.config.ai_model}")

    def _calculate_position_size(
        self,
        ai_tier: int,
        tier_reasoning: str,
        market_data: Dict[str, Any],
    ) -> Tuple[float, int, str]:
        """
        Calculate position size based on AI conviction tier with safety validation.

        Args:
            ai_tier: AI's suggested tier (1, 2, or 3)
            tier_reasoning: AI's reasoning for the tier choice
            market_data: Market data for safety checks

        Returns:
            Tuple of (position_size_usd, final_tier, log_message)
        """
        # If conviction sizing is disabled, use fixed size
        if not self.config.conviction_sizing_enabled:
            return self.config.position_size_usd, 0, "Conviction sizing disabled - using fixed size"

        # Check FORCE_TIER override
        if self.config.force_tier in [1, 2, 3]:
            forced_tier = self.config.force_tier
            tier_sizes = {
                1: self.config.tier1_size_usd,
                2: self.config.tier2_size_usd,
                3: self.config.tier3_size_usd,
            }
            size = tier_sizes[forced_tier]
            return size, forced_tier, f"FORCE_TIER={forced_tier} override active"

        # Validate AI tier
        if ai_tier not in [1, 2, 3]:
            ai_tier = 2  # Default to standard

        # TIER 1 and TIER 2: Accept as-is
        if ai_tier in [1, 2]:
            tier_sizes = {
                1: self.config.tier1_size_usd,
                2: self.config.tier2_size_usd,
            }
            size = tier_sizes[ai_tier]
            tier_names = {1: "SPECULATIVO", 2: "STANDARD"}
            return size, ai_tier, f"TIER {ai_tier} ({tier_names[ai_tier]}): {tier_reasoning}"

        # TIER 3: Requires safety validation
        adx = market_data.get("adx", 0)
        volume_ratio = market_data.get("volume_ratio", 0)
        # Score margin would need to be passed - for now we'll trust TIER 3 if ADX/Volume pass

        safety_failures = []

        # Check ADX (trend strength)
        if adx < self.config.tier3_min_adx:
            safety_failures.append(f"ADX {adx:.1f} < {self.config.tier3_min_adx}")

        # Check Volume Ratio
        if volume_ratio < self.config.tier3_min_volume_ratio:
            safety_failures.append(f"Volume {volume_ratio:.2f}x < {self.config.tier3_min_volume_ratio}x")

        # Check for Bollinger squeeze (indicates uncertainty)
        bb_squeeze = market_data.get("bb_squeeze", False)
        if bb_squeeze:
            safety_failures.append("Bollinger squeeze active")

        # If any safety check fails, downgrade to TIER 2
        if safety_failures:
            downgrade_reason = " | ".join(safety_failures)
            size = self.config.tier2_size_usd
            return size, 2, f"TIER 3 → 2 DOWNGRADE: {downgrade_reason} | AI wanted: {tier_reasoning}"

        # TIER 3 approved
        size = self.config.tier3_size_usd
        return size, 3, f"TIER 3 (HIGH CONVICTION) ✓: {tier_reasoning}"

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

                    # === RECUPERA trade_id DAL DATABASE ===
                    # Questo è critico per poter chiudere correttamente il trade nel DB
                    trade_id = None
                    max_price = entry_price
                    min_price = entry_price
                    opened_at = datetime.now()

                    if self.db and self.db.enabled:
                        db_trade = self.db.get_trade_by_symbol(symbol)
                        if db_trade:
                            trade_id = db_trade.get('id')
                            max_price = float(db_trade.get('max_price', entry_price) or entry_price)
                            min_price = float(db_trade.get('min_price', entry_price) or entry_price)
                            opened_at = db_trade.get('opened_at', datetime.now())
                            logger.info(f"[SYNC] ✅ {symbol}: Recuperato trade_id={trade_id} dal DB (MFE/MAE: max={max_price:.2f}, min={min_price:.2f})")
                        else:
                            logger.warning(f"[SYNC] ⚠️ {symbol}: Nessun trade aperto trovato nel DB - il trade non sarà tracciato correttamente!")

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
                        opened_at=opened_at,
                        trade_id=trade_id,  # Recuperato dal DB!
                        max_price=max_price,  # Recuperato dal DB per MFE
                        min_price=min_price,  # Recuperato dal DB per MAE
                    )
                    self.position_tracker.add_position(position)
                    logger.info(f"Synced position from exchange: {symbol} {direction.value} (trade_id={trade_id})")

            # Remove positions that no longer exist on exchange
            # E CHIUDI IL TRADE NEL DATABASE!
            for symbol in list(self.position_tracker.positions.keys()):
                if symbol not in exchange_symbols:
                    # === CHIUDI IL TRADE NEL DATABASE ===
                    position = self.position_tracker.get_position(symbol)
                    if position and position.trade_id and self.db and self.db.enabled:
                        try:
                            # Recupera ultimo prezzo per calcolo P&L
                            current_price = self.market_data.get_price(symbol)

                            # Calcola P&L
                            if position.direction == TradeDirection.LONG:
                                pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                            else:
                                pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage
                            pnl_usd = (position.size * position.entry_price) * (pnl_pct / 100)

                            self.db.close_trade(
                                trade_id=position.trade_id,
                                exit_price=current_price,
                                pnl_usd=pnl_usd,
                                pnl_pct=pnl_pct,
                                exit_reason="SYNC_CLOSED",  # Chiuso fuori dal bot (manualmente o altro)
                                trailing_level_pct=None,
                            )
                            logger.info(f"[SYNC] ✅ Trade DB chiuso per {symbol} (trade_id={position.trade_id}): P&L {pnl_pct:+.2f}%")
                        except Exception as e:
                            logger.error(f"[SYNC] ❌ Errore chiusura trade DB per {symbol}: {e}")
                    elif position and not position.trade_id:
                        logger.warning(f"[SYNC] ⚠️ {symbol}: Posizione chiusa ma senza trade_id, DB non aggiornato")

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
        """Run fast loop - position monitoring (SL/TP/trailing)."""
        # Sync positions
        self.sync_positions_from_exchange()

        positions = self.position_tracker.get_all_positions()
        if not positions:
            logger.info("[FAST] 📭 No open positions")
            return

        logger.info(f"[FAST] 💓 Monitoring {len(positions)} positions...")

        # First, verify all positions have SL orders on exchange
        self._verify_all_sl_orders(positions)

        # BTC Watchdog - Check BTC RSI for cross-asset protection
        if self.config.btc_watchdog_enabled:
            self._check_btc_watchdog(positions)

        # Timeout Exit - Check for stale positions
        if self.config.timeout_enabled:
            self._check_timeout_exit(positions)

        # Smart Exit - Health Check (with interval control)
        if self.config.health_check_enabled:
            now = datetime.now()
            seconds_since_last = (now - self._last_health_check).total_seconds()
            if seconds_since_last >= self.config.health_check_interval:
                self._last_health_check = now
                self._check_position_health(positions)

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

            # Get tick size for debugging
            tick_size = self.trader._get_tick_size(position.symbol)

            # Use trader's _round_to_tick method (same as sentinel.py)
            sl_price_rounded = self.trader._round_to_tick(position.stop_loss_price, position.symbol)

            logger.debug(f"[FAST] {position.symbol}: SL Debug - raw={position.stop_loss_price:.6f}, tick={tick_size}, rounded={sl_price_rounded}")

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

            # Skip SL if position value is too small (HyperLiquid minimum ~$10)
            position_value_usd = actual_size * current_price
            if position_value_usd < 10.0:
                logger.warning(f"[FAST] {position.symbol}: Position too small (${position_value_usd:.2f} < $10), skip SL")
                return

            # Validate SL is on correct side
            if position.direction == TradeDirection.LONG:
                if sl_price_rounded >= current_price:
                    logger.error(f"[FAST] {position.symbol}: ❌ SL ${sl_price_rounded:.4f} >= current ${current_price:.4f} for LONG - INVALID!")
                    return
            else:  # SHORT
                if sl_price_rounded <= current_price:
                    logger.error(f"[FAST] {position.symbol}: ❌ SL ${sl_price_rounded:.4f} <= current ${current_price:.4f} for SHORT - INVALID!")
                    return

            sl_distance_pct = abs(sl_price_rounded - current_price) / current_price * 100
            logger.info(f"[FAST] {position.symbol}: Placing SL - size={actual_size}, price=${sl_price_rounded}, is_buy={sl_is_buy}, current=${current_price:.2f}, distance={sl_distance_pct:.1f}%, tick={tick_size}")

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

    def _check_btc_watchdog(self, positions: list):
        """
        BTC Watchdog - Cross-asset protection based on BTC RSI.

        When BTC shows extreme RSI readings, it often precedes market-wide moves.
        This protects altcoin positions by tightening SL when BTC shows warning signs.

        Logic:
        - BTC RSI >= 70 (EXTREME): Tighten SHORT SL to breakeven + X%
        - BTC RSI >= 65 (DANGER): Tighten SHORT SL if in profit
        - BTC RSI <= 30 (OVERSOLD): Tighten LONG SL to protect from BTC bounce
        """
        try:
            # Get BTC RSI
            btc_data = self.market_data.get_market_data("BTC")
            btc_rsi = btc_data.get("rsi", 50)

            if btc_rsi is None:
                return

            # Determine BTC zone for logging
            if btc_rsi >= self.config.btc_rsi_extreme:
                zone = "🔴 EXTREME"
            elif btc_rsi >= self.config.btc_rsi_danger:
                zone = "🟠 DANGER"
            elif btc_rsi <= self.config.btc_rsi_oversold:
                zone = "🔵 OVERSOLD"
            else:
                zone = "🟢 NORMAL"

            logger.info(f"[WATCHDOG] 🐕 BTC RSI: {btc_rsi:.1f} | Zone: {zone}")

            # Check for extreme conditions
            for position in positions:
                # Skip BTC itself
                if position.symbol == "BTC":
                    continue

                current_price = self.market_data.get_price(position.symbol)
                if current_price <= 0:
                    continue

                # Calculate current P&L
                if position.direction == TradeDirection.LONG:
                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                else:
                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

                new_sl = None
                trigger_reason = None

                # === BTC EXTREME OVERBOUGHT (RSI >= 70) ===
                # BTC molto alto → probabile correzione → SHORT altcoin a rischio
                if btc_rsi >= self.config.btc_rsi_extreme and position.direction == TradeDirection.SHORT:
                    # Stringi SL a breakeven + configured %
                    if position.direction == TradeDirection.SHORT:
                        # For SHORT: SL is ABOVE entry, so tightening means lowering it
                        # Breakeven = entry price, then add configured %
                        potential_sl = position.entry_price * (1 + self.config.btc_watchdog_extreme_sl_pct / 100)
                        # Only tighten if new SL is better (lower for SHORT)
                        if potential_sl < position.stop_loss_price:
                            new_sl = potential_sl
                            trigger_reason = f"BTC RSI {btc_rsi:.0f} EXTREME → SL a BE+{self.config.btc_watchdog_extreme_sl_pct}%"

                # === BTC DANGER ZONE (RSI >= 65) ===
                # BTC alto → cautela → stringi SL se in profitto
                elif btc_rsi >= self.config.btc_rsi_danger and position.direction == TradeDirection.SHORT:
                    # Only act if in profit
                    if pnl_pct > 0:
                        # Tighten SL to lock some profit
                        # For SHORT: lock profit means lowering the SL
                        lock_pct = max(0, pnl_pct - self.config.btc_watchdog_danger_sl_pct)
                        potential_sl = position.entry_price * (1 + (lock_pct / position.leverage) / 100)
                        if potential_sl < position.stop_loss_price:
                            new_sl = potential_sl
                            trigger_reason = f"BTC RSI {btc_rsi:.0f} DANGER → lock +{lock_pct:.1f}%"

                # === BTC OVERSOLD (RSI <= 30) ===
                # BTC molto basso → probabile bounce → LONG altcoin a rischio
                elif btc_rsi <= self.config.btc_rsi_oversold and position.direction == TradeDirection.LONG:
                    # BTC bounce could drag altcoins up quickly
                    # For LONG positions, tighten SL to protect from sudden dump before BTC bounce
                    if pnl_pct > 0:
                        # Lock some profit
                        lock_pct = max(0, pnl_pct - self.config.btc_watchdog_danger_sl_pct)
                        potential_sl = position.entry_price * (1 - (lock_pct / position.leverage) / 100)
                        if potential_sl > position.stop_loss_price:
                            new_sl = potential_sl
                            trigger_reason = f"BTC RSI {btc_rsi:.0f} OVERSOLD → lock +{lock_pct:.1f}%"

                # Apply new SL if needed
                if new_sl is not None:
                    logger.warning(f"[WATCHDOG] 🐕 {position.symbol}: {trigger_reason}")
                    logger.warning(f"[WATCHDOG] 🐕 {position.symbol}: SL ${position.stop_loss_price:.2f} → ${new_sl:.2f}")

                    # Update position
                    old_sl = position.stop_loss_price
                    position.stop_loss_price = new_sl

                    # Update on exchange
                    self._update_sl_on_exchange(position, old_sl, new_sl)

        except Exception as e:
            logger.error(f"[WATCHDOG] Error in BTC watchdog: {e}")

    def _check_timeout_exit(self, positions: list):
        """
        Timeout Exit - Close stale positions that are not moving.

        Logic:
        - Position open > TIMEOUT_HOURS (default 12h)
        - If P&L < TIMEOUT_LOSS_THRESHOLD (-3%): Close (cut loss)
        - If P&L between TIMEOUT_LOSS_THRESHOLD and TIMEOUT_STALE_MAX (+1%): Close (stale)
        - If P&L > TIMEOUT_STALE_MAX: Keep open (in profit, let trailing work)
        """
        try:
            timeout_delta = timedelta(hours=self.config.timeout_hours)
            now = datetime.now()

            # Log position ages
            ages = []
            for p in positions:
                age_h = (now - p.opened_at).total_seconds() / 3600
                ages.append(f"{p.symbol}:{age_h:.1f}h")
            logger.info(f"[TIMEOUT] ⏰ Position ages: {', '.join(ages)} | Threshold: {self.config.timeout_hours}h")

            for position in positions:
                # Calculate position age
                duration = now - position.opened_at
                duration_hours = duration.total_seconds() / 3600

                # Skip if not old enough
                if duration < timeout_delta:
                    continue

                # Calculate current P&L
                current_price = self.market_data.get_price(position.symbol)
                if current_price <= 0:
                    continue

                if position.direction == TradeDirection.LONG:
                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                else:
                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

                # Check timeout conditions
                if pnl_pct < self.config.timeout_loss_threshold:
                    # CASE 1: Losing and old → cut loss
                    logger.warning(f"[TIMEOUT] ⏰ {position.symbol}: {duration_hours:.1f}h con P&L {pnl_pct:+.2f}% < {self.config.timeout_loss_threshold}%")
                    logger.warning(f"[TIMEOUT] ⏰ {position.symbol}: CHIUDO per timeout + perdita")
                    self._close_position(position.symbol, "TIMEOUT_LOSS",
                                        f"Position > {self.config.timeout_hours}h with P&L {pnl_pct:+.2f}%")

                elif pnl_pct < self.config.timeout_stale_max:
                    # CASE 2: Stale (not losing much but not profiting) → close
                    logger.warning(f"[TIMEOUT] ⏰ {position.symbol}: {duration_hours:.1f}h con P&L {pnl_pct:+.2f}% (stagnante)")
                    logger.warning(f"[TIMEOUT] ⏰ {position.symbol}: CHIUDO per timeout + stagnazione")
                    self._close_position(position.symbol, "TIMEOUT_STALE",
                                        f"Position > {self.config.timeout_hours}h with P&L {pnl_pct:+.2f}%")
                else:
                    # CASE 3: In profit → keep open, let trailing work
                    logger.info(f"[TIMEOUT] {position.symbol}: {duration_hours:.1f}h ma P&L {pnl_pct:+.2f}% → mantengo (trailing)")

        except Exception as e:
            logger.error(f"[TIMEOUT] Error in timeout check: {e}")

    def _calculate_position_health(self, position: Position, market_data: Dict[str, Any], pnl_pct: float) -> Tuple[int, str]:
        """
        Calculate health score for a position.

        Components:
        - EMA Stack: bullish=+2, neutral=0, bearish=-2
        - RSI: favorable=+1, neutral=0, unfavorable=-1
        - MACD: strong favorable=+1, weak=0, against=-2
        - Volume: good=+1, low=0, very low=-1
        - Bollinger: favorable=+1, neutral=0, dangerous=-2
        - OBV: aligned=+1, neutral=0, against=-1
        - Time Decay: penalties based on hours without profit
        - Resilience Bonus: +1 if profitable despite time

        Returns:
            Tuple of (score, breakdown_string)
        """
        score = 0
        breakdown = []
        is_long = position.direction == TradeDirection.LONG
        cfg = self.config  # Shorthand

        # 1. EMA Stack (configurable weights)
        ema_stack = market_data.get('ema_stack', '')
        if 'bullish' in ema_stack.lower():
            if is_long:
                score += cfg.health_weight_ema_pos
                breakdown.append(f"EMA:{cfg.health_weight_ema_pos:+d}")
            else:
                score += cfg.health_weight_ema_neg
                breakdown.append(f"EMA:{cfg.health_weight_ema_neg:+d}")
        elif 'bearish' in ema_stack.lower():
            if is_long:
                score += cfg.health_weight_ema_neg
                breakdown.append(f"EMA:{cfg.health_weight_ema_neg:+d}")
            else:
                score += cfg.health_weight_ema_pos
                breakdown.append(f"EMA:{cfg.health_weight_ema_pos:+d}")
        else:
            breakdown.append("EMA:0")

        # 2. RSI (configurable weights)
        rsi = market_data.get('rsi', 50)
        if is_long:
            if rsi > 50:
                score += cfg.health_weight_rsi_pos
                breakdown.append(f"RSI:{cfg.health_weight_rsi_pos:+d}")
            elif rsi < 40:
                score += cfg.health_weight_rsi_neg
                breakdown.append(f"RSI:{cfg.health_weight_rsi_neg:+d}")
            else:
                breakdown.append("RSI:0")
        else:  # SHORT
            if rsi < 50:
                score += cfg.health_weight_rsi_pos
                breakdown.append(f"RSI:{cfg.health_weight_rsi_pos:+d}")
            elif rsi > 60:
                score += cfg.health_weight_rsi_neg
                breakdown.append(f"RSI:{cfg.health_weight_rsi_neg:+d}")
            else:
                breakdown.append("RSI:0")

        # 3. MACD (configurable weights - now symmetric by default)
        macd = market_data.get('macd', 0)
        if is_long:
            if macd > 0.1:
                score += cfg.health_weight_macd_pos
                breakdown.append(f"MACD:{cfg.health_weight_macd_pos:+d}")
            elif macd < -0.1:
                score += cfg.health_weight_macd_neg
                breakdown.append(f"MACD:{cfg.health_weight_macd_neg:+d}")
            else:
                breakdown.append("MACD:0")
        else:  # SHORT
            if macd < -0.1:
                score += cfg.health_weight_macd_pos
                breakdown.append(f"MACD:{cfg.health_weight_macd_pos:+d}")
            elif macd > 0.1:
                score += cfg.health_weight_macd_neg
                breakdown.append(f"MACD:{cfg.health_weight_macd_neg:+d}")
            else:
                breakdown.append("MACD:0")

        # 4. Volume Ratio (configurable weights)
        vol_ratio = market_data.get('volume_ratio', 1.0)
        if vol_ratio > 0.8:
            score += cfg.health_weight_vol_pos
            breakdown.append(f"VOL:{cfg.health_weight_vol_pos:+d}")
        elif vol_ratio < 0.3:
            score += cfg.health_weight_vol_neg
            breakdown.append(f"VOL:{cfg.health_weight_vol_neg:+d}")
        else:
            breakdown.append("VOL:0")

        # 5. Bollinger Bands (configurable weights)
        bb_pos = market_data.get('bb_position', 'MIDDLE')
        bb_squeeze = market_data.get('bb_squeeze', False)
        if is_long:
            if 'UPPER' in bb_pos:
                score += cfg.health_weight_bb_pos
                breakdown.append(f"BB:{cfg.health_weight_bb_pos:+d}")
            elif 'LOWER' in bb_pos and bb_squeeze:
                score += cfg.health_weight_bb_squeeze
                breakdown.append(f"BB:{cfg.health_weight_bb_squeeze:+d}(sq)")
            elif 'LOWER' in bb_pos:
                score += cfg.health_weight_bb_neg
                breakdown.append(f"BB:{cfg.health_weight_bb_neg:+d}")
            else:
                breakdown.append("BB:0")
        else:  # SHORT
            if 'LOWER' in bb_pos:
                score += cfg.health_weight_bb_pos
                breakdown.append(f"BB:{cfg.health_weight_bb_pos:+d}")
            elif 'UPPER' in bb_pos and bb_squeeze:
                score += cfg.health_weight_bb_squeeze
                breakdown.append(f"BB:{cfg.health_weight_bb_squeeze:+d}(sq)")
            elif 'UPPER' in bb_pos:
                score += cfg.health_weight_bb_neg
                breakdown.append(f"BB:{cfg.health_weight_bb_neg:+d}")
            else:
                breakdown.append("BB:0")

        # 6. OBV Trend (configurable weights)
        obv = market_data.get('obv_trend', 'FLAT')
        if isinstance(obv, str):
            obv = obv.upper()
        if is_long:
            if obv == 'RISING':
                score += cfg.health_weight_obv_pos
                breakdown.append(f"OBV:{cfg.health_weight_obv_pos:+d}")
            elif obv == 'FALLING':
                score += cfg.health_weight_obv_neg
                breakdown.append(f"OBV:{cfg.health_weight_obv_neg:+d}")
            else:
                breakdown.append("OBV:0")
        else:  # SHORT
            if obv == 'FALLING':
                score += cfg.health_weight_obv_pos
                breakdown.append(f"OBV:{cfg.health_weight_obv_pos:+d}")
            elif obv == 'RISING':
                score += cfg.health_weight_obv_neg
                breakdown.append(f"OBV:{cfg.health_weight_obv_neg:+d}")
            else:
                breakdown.append("OBV:0")

        # 7. Time Decay (only if NOT in profit, configurable weights)
        hours_open = (datetime.now() - position.opened_at).total_seconds() / 3600
        if pnl_pct <= 0:
            if hours_open >= cfg.health_time_decay_severe:
                score += cfg.health_weight_time_severe
                breakdown.append(f"TIME:{cfg.health_weight_time_severe:+d}({hours_open:.1f}h)")
            elif hours_open >= cfg.health_time_decay_medium:
                score += cfg.health_weight_time_medium
                breakdown.append(f"TIME:{cfg.health_weight_time_medium:+d}({hours_open:.1f}h)")
            elif hours_open >= cfg.health_time_decay_start:
                score += cfg.health_weight_time_light
                breakdown.append(f"TIME:{cfg.health_weight_time_light:+d}({hours_open:.1f}h)")
            else:
                breakdown.append(f"TIME:0({hours_open:.1f}h)")
        else:
            # 8. Resilience Bonus (in profit despite time)
            if pnl_pct > 2 and hours_open > cfg.health_time_decay_start:
                score += cfg.health_weight_resilience
                breakdown.append(f"RESILIENT:{cfg.health_weight_resilience:+d}")
            else:
                breakdown.append(f"TIME:0({hours_open:.1f}h)")

        return score, " | ".join(breakdown)

    def _check_position_health(self, positions: list):
        """
        Check health of all positions and take action based on score.

        Actions:
        - HEALTHY (score >= 4): Normal trailing, no action
        - CAUTION (score 0-3): Tighten SL one step if in profit
        - DANGER (score -3 to -1): Set SL to breakeven if any profit
        - EMERGENCY (score < -4): Close immediately if in profit
        """
        try:
            for position in positions:
                # === GRACE PERIOD CHECK ===
                # Skip positions that are too new - give AI decision time to prove itself
                position_age_minutes = (datetime.now() - position.opened_at).total_seconds() / 60
                if position_age_minutes < self.config.health_grace_period_minutes:
                    logger.info(f"[HEALTH] {position.symbol}: ⏳ Grace period ({position_age_minutes:.1f}m < {self.config.health_grace_period_minutes}m) - skipping")
                    continue

                # Get LIVE price for accurate P&L
                current_price = self.market_data.get_price(position.symbol)
                if current_price <= 0:
                    continue

                # Calculate P&L on LIVE price
                if position.direction == TradeDirection.LONG:
                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                else:
                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

                # Get market data (from Slow Loop cache - acceptable for trends)
                market_data = self.market_data.get_market_data(position.symbol)

                # Calculate health score
                score, breakdown = self._calculate_position_health(position, market_data, pnl_pct)

                # Determine action based on score
                if score >= self.config.health_score_healthy:
                    # HEALTHY - Normal operation
                    logger.info(f"[HEALTH] {position.symbol}: Score {score} ✅ HEALTHY | {breakdown}")

                elif score >= self.config.health_score_caution:
                    # CAUTION - Tighten SL if in profit
                    logger.warning(f"[HEALTH] {position.symbol}: Score {score} ⚠️ CAUTION | {breakdown}")
                    if pnl_pct >= self.config.health_min_profit_caution:
                        logger.warning(f"[HEALTH] {position.symbol}: Tightening SL (P&L: {pnl_pct:+.2f}%)")
                        self._health_tighten_sl_one_step(position, current_price)

                elif score >= self.config.health_score_danger:
                    # DANGER - Set SL to breakeven + small profit
                    logger.warning(f"[HEALTH] {position.symbol}: Score {score} 🔶 DANGER | {breakdown}")
                    if pnl_pct >= self.config.health_min_profit_danger:
                        logger.warning(f"[HEALTH] {position.symbol}: Setting SL to breakeven (P&L: {pnl_pct:+.2f}%)")
                        self._health_set_breakeven_sl(position, current_price, lock_pct=0.3)

                else:
                    # EMERGENCY - Close if in profit
                    logger.error(f"[HEALTH] {position.symbol}: Score {score} 🔴 EMERGENCY | {breakdown}")
                    if pnl_pct >= self.config.health_min_profit_emergency:
                        logger.error(f"[HEALTH] {position.symbol}: CLOSING - Score critical, locking profit {pnl_pct:+.2f}%")
                        self._close_position(position.symbol, "HEALTH_EMERGENCY",
                                           f"Health score {score} critical, P&L {pnl_pct:+.2f}%")
                    else:
                        logger.error(f"[HEALTH] {position.symbol}: Score critical but P&L {pnl_pct:+.2f}% < min {self.config.health_min_profit_emergency}%")
                        # Still try to protect by tightening SL
                        self._health_set_breakeven_sl(position, current_price, lock_pct=0.0)

        except Exception as e:
            logger.error(f"[HEALTH] Error in health check: {e}")

    def _health_tighten_sl_one_step(self, position: Position, current_price: float):
        """Tighten SL by one trailing step."""
        try:
            # Get current P&L
            if position.direction == TradeDirection.LONG:
                pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
            else:
                pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

            # Use trailing manager to get next step
            was_updated, new_sl, new_level = self.trailing_sl.get_new_sl(
                direction=position.direction,
                entry_price=position.entry_price,
                current_price=current_price,
                leverage=position.leverage,
                current_sl_level=position.current_sl_level,
            )

            if was_updated and new_sl != position.stop_loss_price:
                logger.info(f"[HEALTH] {position.symbol}: Trailing SL tightened ${position.stop_loss_price:.2f} → ${new_sl:.2f}")
                old_sl = position.stop_loss_price
                position.stop_loss_price = new_sl
                position.current_sl_level = new_level
                self._update_sl_on_exchange(position, old_sl, new_sl)
            else:
                logger.info(f"[HEALTH] {position.symbol}: No tighter SL step available yet")

        except Exception as e:
            logger.error(f"[HEALTH] Error tightening SL: {e}")

    def _health_set_breakeven_sl(self, position: Position, current_price: float, lock_pct: float = 0.0):
        """Set SL to breakeven + lock_pct profit."""
        try:
            # Calculate breakeven + lock price
            if position.direction == TradeDirection.LONG:
                # For LONG: SL should be above entry by lock_pct
                new_sl = position.entry_price * (1 + (lock_pct / position.leverage) / 100)
                # Only update if new SL is higher (better) than current
                if new_sl > position.stop_loss_price:
                    logger.info(f"[HEALTH] {position.symbol}: SL to breakeven+{lock_pct}%: ${position.stop_loss_price:.2f} → ${new_sl:.2f}")
                    old_sl = position.stop_loss_price
                    position.stop_loss_price = new_sl
                    position.current_sl_level = lock_pct
                    self._update_sl_on_exchange(position, old_sl, new_sl)
                else:
                    logger.info(f"[HEALTH] {position.symbol}: SL already better than breakeven (${position.stop_loss_price:.2f})")
            else:
                # For SHORT: SL should be below entry by lock_pct
                new_sl = position.entry_price * (1 - (lock_pct / position.leverage) / 100)
                # Only update if new SL is lower (better) than current
                if new_sl < position.stop_loss_price:
                    logger.info(f"[HEALTH] {position.symbol}: SL to breakeven+{lock_pct}%: ${position.stop_loss_price:.2f} → ${new_sl:.2f}")
                    old_sl = position.stop_loss_price
                    position.stop_loss_price = new_sl
                    position.current_sl_level = lock_pct
                    self._update_sl_on_exchange(position, old_sl, new_sl)
                else:
                    logger.info(f"[HEALTH] {position.symbol}: SL already better than breakeven (${position.stop_loss_price:.2f})")

        except Exception as e:
            logger.error(f"[HEALTH] Error setting breakeven SL: {e}")

    def _update_sl_on_exchange(self, position: Position, old_sl: float, new_sl: float):
        """Update stop loss on exchange (cancel old, place new)."""
        try:
            # 1. Find old SL orders
            old_sl_oids = []
            try:
                open_orders = self.trader.exchange.info.frontend_open_orders(self.config.hl_account_address)
            except AttributeError:
                open_orders = self.trader.exchange.info.open_orders(self.config.hl_account_address)

            for order in open_orders:
                if order.get("coin") == position.symbol:
                    trigger_px = order.get("triggerPx")
                    if trigger_px and trigger_px != "0.0":
                        old_sl_oids.append(order.get("oid"))

            # 2. Place new SL first (so we're always protected)
            sl_is_buy = position.direction == TradeDirection.SHORT

            # Round SL price appropriately
            sl_price_rounded = self.trader._round_to_tick(new_sl, position.symbol)

            # Get actual position size
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
                {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") == "ok":
                # Check for nested errors
                response_data = sl_order.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [])

                has_error = False
                for status in statuses:
                    if "error" in status:
                        logger.error(f"[WATCHDOG] {position.symbol}: ❌ SL RIFIUTATO: {status['error']}")
                        has_error = True
                        break

                if not has_error:
                    logger.info(f"[WATCHDOG] {position.symbol}: ✅ Nuovo SL @ ${sl_price_rounded:.2f}")

                    # 3. Cancel old SL orders
                    for oid in old_sl_oids:
                        try:
                            self.trader.exchange.cancel(position.symbol, oid)
                            logger.info(f"[WATCHDOG] {position.symbol}: Cancellato vecchio SL (oid: {oid})")
                        except Exception as cancel_err:
                            logger.warning(f"[WATCHDOG] {position.symbol}: Errore cancellazione: {cancel_err}")
            else:
                logger.warning(f"[WATCHDOG] {position.symbol}: ⚠️ Errore piazzamento SL: {sl_order}")

        except Exception as e:
            logger.error(f"[WATCHDOG] {position.symbol}: ❌ Errore update SL: {e}")

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

        # Get market data (force_refresh_volume=True for accurate VETO check in SLOW loop)
        market_data = self.market_data.get_market_data(symbol, force_refresh_volume=True)
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
            # Stochastic (NEW)
            logger.info(f"  Stochastic: %K={market_data.get('stoch_k', 50):.1f} %D={market_data.get('stoch_d', 50):.1f} | Signal={market_data.get('stoch_signal', 'N/A')} | Zone={market_data.get('stoch_zone', 'N/A')}")
            # Pivot Points (NEW)
            logger.info(f"  Pivot Points: R2=${market_data.get('pivot_r2', 0):,.4f} R1=${market_data.get('pivot_r1', 0):,.4f} PP=${market_data.get('pivot_pp', 0):,.4f} S1=${market_data.get('pivot_s1', 0):,.4f} S2=${market_data.get('pivot_s2', 0):,.4f}")
            logger.info(f"  Volume Ratio: {market_data.get('volume_ratio', 1.0):.2f}x (2m={market_data.get('volume_current', 0):.0f} / 15m={market_data.get('volume_baseline', 0):.0f})")
            logger.info(f"  Funding Rate: {market_data.get('funding_rate', 0):.4%}")
            logger.info(f"  Open Interest: ${market_data.get('open_interest', 0):,.0f}")
        else:
            # Always show volume ratio even without verbose logging
            logger.info(f"[SLOW] {symbol}: 📊 Volume {market_data.get('volume_ratio', 1.0):.2f}x (2m={market_data.get('volume_current', 0):.0f} / 15m={market_data.get('volume_baseline', 0):.0f})")

        # === MULTI-TIMEFRAME DATA ===
        # Fetch candles from multiple timeframes if enabled
        if self.config.multi_timeframe_enabled:
            mtf_data = self.market_data.get_multi_timeframe_candles(symbol)
            if mtf_data:
                market_data["mtf_data"] = mtf_data
                logger.info(f"[SLOW] {symbol}: 📈 MTF data loaded ({len(mtf_data)} timeframes)")

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

            # === OTTIMIZZAZIONE: Skip AI se P&L in "dead zone" ===
            # Dead zone = AI non può fare nulla di utile
            # - Non abbastanza profitto per chiudere (< min_profit)
            # - Non abbastanza perdita per loss-cut (< loss_threshold)
            min_profit = self.config.min_profit_to_close
            loss_threshold = self.config.stop_loss_pct * (self.config.ai_loss_threshold_pct / 100)

            if current_pnl_pct < min_profit and current_pnl_pct > -loss_threshold:
                logger.info(f"[SLOW] {symbol}: ⏭️ Skip AI - P&L {current_pnl_pct:+.2f}% in dead zone "
                           f"(need >{min_profit:+.1f}% or <-{loss_threshold:.1f}%)")
                return

        # Get AI decision
        logger.info(f"[SLOW] {symbol}: Calling AI ({self.config.prompt_style})...")

        action, direction, reason, confidence, leverage, conviction_tier, tier_reasoning = self.ai_manager.get_decision(
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
            # === BTC ENTRY VETO CHECK ===
            # Block new entries when BTC is in extreme zones (cross-asset correlation risk)
            if self.config.btc_entry_veto_enabled and symbol != "BTC":
                try:
                    btc_data = self.market_data.get_market_data("BTC")
                    btc_rsi = btc_data.get("rsi", 50)

                    if btc_rsi is not None:
                        # Block LONG if BTC RSI is overbought (may correct, dragging altcoins down)
                        if direction == TradeDirection.LONG and btc_rsi >= self.config.btc_entry_veto_long_rsi:
                            logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED LONG entry - BTC RSI {btc_rsi:.1f} >= {self.config.btc_entry_veto_long_rsi}")
                            logger.warning(f"[VETO] 🚫 {symbol}: BTC overbought may correct → altcoins at risk")
                            return

                        # Block SHORT if BTC RSI is oversold (may bounce, dragging altcoins up)
                        if direction == TradeDirection.SHORT and btc_rsi <= self.config.btc_entry_veto_short_rsi:
                            logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED SHORT entry - BTC RSI {btc_rsi:.1f} <= {self.config.btc_entry_veto_short_rsi}")
                            logger.warning(f"[VETO] 🚫 {symbol}: BTC oversold may bounce → altcoins at risk")
                            return
                except Exception as e:
                    logger.warning(f"[VETO] Could not check BTC RSI: {e}")

            # === SYMBOL RSI ENTRY FILTER ===
            # Block LONG entries when symbol RSI is overbought (likely to reverse down)
            # Block SHORT entries when symbol RSI is oversold (likely to bounce up)
            if self.config.rsi_entry_filter_enabled:
                symbol_rsi = market_data.get("rsi", 50)
                if symbol_rsi is not None:
                    # Block LONG if RSI too high (overbought)
                    if direction == TradeDirection.LONG and symbol_rsi >= self.config.long_max_rsi:
                        logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED LONG entry - RSI {symbol_rsi:.1f} >= {self.config.long_max_rsi}")
                        logger.warning(f"[VETO] 🚫 {symbol}: Overbought conditions - high reversal risk")
                        return

                    # Block SHORT if RSI too low (oversold)
                    if direction == TradeDirection.SHORT and symbol_rsi <= self.config.short_min_rsi:
                        logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED SHORT entry - RSI {symbol_rsi:.1f} <= {self.config.short_min_rsi}")
                        logger.warning(f"[VETO] 🚫 {symbol}: Oversold conditions - high bounce risk")
                        return

            # === EMA TREND FILTER ===
            # Block trades against the trend: no SHORT in uptrend, no LONG in downtrend
            if self.config.ema_trend_filter_enabled:
                ema_stack = market_data.get("ema_stack", "")

                # Block SHORT in uptrend (bullish EMA stack)
                if direction == TradeDirection.SHORT and "bullish" in ema_stack.lower():
                    logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED SHORT - EMA stack bullish (trend UP)")
                    logger.warning(f"[VETO] 🚫 {symbol}: Don't short an uptrend! EMA: {ema_stack}")
                    return

                # Block LONG in downtrend (bearish EMA stack)
                if direction == TradeDirection.LONG and "bearish" in ema_stack.lower():
                    logger.warning(f"[VETO] 🚫 {symbol}: BLOCKED LONG - EMA stack bearish (trend DOWN)")
                    logger.warning(f"[VETO] 🚫 {symbol}: Don't long a downtrend! EMA: {ema_stack}")
                    return

            # Calculate position size based on conviction tier
            position_size_usd, final_tier, tier_log = self._calculate_position_size(
                ai_tier=conviction_tier,
                tier_reasoning=tier_reasoning,
                market_data=market_data,
            )

            # Log tier decision
            tier_emoji = {0: "📊", 1: "🎲", 2: "📈", 3: "🎯"}
            logger.info(f"[SLOW] {symbol}: {tier_emoji.get(final_tier, '📊')} SIZE: ${position_size_usd:.0f} | {tier_log}")

            self._open_position(
                symbol=symbol,
                direction=direction,
                price=market_data.get("price", 0),
                leverage=leverage,
                reason=reason,
                position_size_usd=position_size_usd,
                conviction_tier=final_tier,
                ai_confidence=confidence,
                market_data=market_data,
            )
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

        # === MFE/MAE TRACKING ===
        # Initialize if needed
        if position.max_price == 0:
            position.max_price = position.entry_price
        if position.min_price == 0:
            position.min_price = position.entry_price

        # Update max/min prices
        if price > position.max_price:
            position.max_price = price
        if price < position.min_price:
            position.min_price = price

        # Update database periodically (every update would be too frequent)
        if self.db and self.db.enabled and position.trade_id:
            self.db.update_mfe_mae(position.trade_id, position.max_price, position.min_price)

        # Calculate P&L
        if position.direction == TradeDirection.LONG:
            pnl_pct = ((price - position.entry_price) / position.entry_price) * 100 * position.leverage
            price_move_pct = ((price - position.entry_price) / position.entry_price) * 100
            # MFE = max profit seen, MAE = max loss seen
            mfe_pct = ((position.max_price - position.entry_price) / position.entry_price) * 100 * position.leverage
            mae_pct = ((position.entry_price - position.min_price) / position.entry_price) * 100 * position.leverage
        else:
            pnl_pct = ((position.entry_price - price) / position.entry_price) * 100 * position.leverage
            price_move_pct = ((position.entry_price - price) / position.entry_price) * 100
            # MFE = max profit seen (price went down), MAE = max loss seen (price went up)
            mfe_pct = ((position.entry_price - position.min_price) / position.entry_price) * 100 * position.leverage
            mae_pct = ((position.max_price - position.entry_price) / position.entry_price) * 100 * position.leverage

        # === EARLY EXIT FOR BAD ENTRY ===
        # If trade has been open for X minutes and MAE > threshold while MFE < threshold, close it
        # Data shows: trades with MAE > MFE have only 8% win rate!
        if self.config.early_exit_enabled and position.opened_at:
            elapsed_minutes = (datetime.now() - position.opened_at).total_seconds() / 60
            if elapsed_minutes >= self.config.early_exit_minutes:
                if mae_pct >= self.config.early_exit_mae_threshold and mfe_pct < self.config.early_exit_mfe_threshold:
                    logger.warning(f"[EARLY EXIT] 🚨 {position.symbol}: BAD ENTRY detected!")
                    logger.warning(f"[EARLY EXIT] 🚨 {position.symbol}: MAE {mae_pct:.2f}% >= {self.config.early_exit_mae_threshold}%, MFE {mfe_pct:.2f}% < {self.config.early_exit_mfe_threshold}%")
                    logger.warning(f"[EARLY EXIT] 🚨 {position.symbol}: Closing after {elapsed_minutes:.0f} min to prevent further loss")
                    self._close_position(position.symbol, "EARLY_EXIT", f"Bad entry: MAE {mae_pct:.1f}% > MFE {mfe_pct:.1f}% after {elapsed_minutes:.0f}min")
                    return

        # === TIME STOP ===
        # Close ALL trades after X minutes - data shows win rate drops from 80% to 15% after 30 min
        if self.config.time_stop_enabled and position.opened_at:
            elapsed_minutes = (datetime.now() - position.opened_at).total_seconds() / 60
            if elapsed_minutes >= self.config.time_stop_minutes:
                logger.warning(f"[TIME STOP] ⏰ {position.symbol}: Trade open {elapsed_minutes:.0f} min >= {self.config.time_stop_minutes} min limit")
                logger.warning(f"[TIME STOP] ⏰ {position.symbol}: P&L: {pnl_pct:+.2f}% | MFE: {mfe_pct:.2f}% | MAE: {mae_pct:.2f}%")
                self._close_position(position.symbol, "TIME_STOP", f"Time limit: {elapsed_minutes:.0f}min >= {self.config.time_stop_minutes}min | P&L: {pnl_pct:+.2f}%")
                return

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
            # ORDINE IMPORTANTE: prima piazza nuovo SL, poi cancella vecchio
            # Così non sei mai scoperto durante l'aggiornamento
            try:
                # 1. Trova vecchi SL orders (per cancellarli DOPO)
                old_sl_oids = []
                try:
                    open_orders = self.trader.exchange.info.frontend_open_orders(self.config.hl_account_address)
                except AttributeError:
                    open_orders = self.trader.exchange.info.open_orders(self.config.hl_account_address)

                for order in open_orders:
                    if order.get("coin") == position.symbol:
                        trigger_px = order.get("triggerPx")
                        if trigger_px and trigger_px != "0.0":
                            old_sl_oids.append(order.get("oid"))

                # 2. PRIMA piazza nuovo SL (sei protetto)
                sl_is_buy = position.direction == TradeDirection.SHORT

                # Round SL price appropriately based on asset tick size
                # BTC: 0.1, ETH: 0.1, SOL: 0.01, others: 0.0001
                # Use string formatting to ensure exact decimal precision (avoids float issues)
                if position.symbol in ["BTC", "ETH"]:
                    sl_price_rounded = float(f"{new_sl:.1f}")
                elif position.symbol == "SOL":
                    sl_price_rounded = float(f"{new_sl:.2f}")
                else:
                    sl_price_rounded = float(f"{new_sl:.4f}")

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
                    {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                    reduce_only=True
                )

                if sl_order.get("status") == "ok":
                    logger.info(f"[FAST] {position.symbol}: 🛡️ Nuovo SL piazzato @ ${sl_price_rounded:.1f}")

                    # 3. POI cancella vecchi SL (ora sei coperto dal nuovo)
                    for oid in old_sl_oids:
                        try:
                            self.trader.exchange.cancel(position.symbol, oid)
                            logger.info(f"[FAST] {position.symbol}: Cancellato vecchio SL (oid: {oid})")
                        except Exception as cancel_err:
                            logger.warning(f"[FAST] {position.symbol}: Errore cancellazione vecchio SL: {cancel_err}")
                else:
                    logger.warning(f"[FAST] {position.symbol}: ⚠️ Errore aggiornamento SL: {sl_order}")

            except Exception as sl_err:
                logger.error(f"[FAST] {position.symbol}: ❌ Errore trailing SL update: {sl_err}")

    def _open_position(
        self,
        symbol: str,
        direction: TradeDirection,
        price: float,
        leverage: int,
        reason: str,
        position_size_usd: Optional[float] = None,
        conviction_tier: int = 2,
        ai_confidence: float = 0.5,
        market_data: Optional[Dict[str, Any]] = None,
    ):
        """Open a new position.

        Args:
            symbol: Trading symbol (BTC, ETH, SOL)
            direction: LONG or SHORT
            price: Entry price
            leverage: Leverage multiplier
            reason: AI reasoning for the trade
            position_size_usd: Position size in USD (optional, uses config default if not provided)
            conviction_tier: AI conviction tier (1/2/3)
            ai_confidence: AI confidence (0-1)
            market_data: Market indicators at entry time
        """
        # Use provided size or fall back to config default
        size_usd = position_size_usd if position_size_usd is not None else self.config.position_size_usd

        logger.info(f"[TRADE] Opening {direction.value} on {symbol} @ ${price:.2f} lev={leverage}x size=${size_usd:.0f}")

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
                "target_portion_of_balance": size_usd / 100,  # Will be adjusted by trader
                "leverage": leverage,
                "reason": reason,
            }

            # Execute via HyperLiquid trader
            result = self.trader.execute_signal(order)

            if result.get("status") == "ok" or "response" in result:
                # Extract indicators for database
                indicators = {}
                if market_data:
                    indicators = {
                        "macd": market_data.get("macd"),
                        "rsi": market_data.get("rsi"),
                        "adx": market_data.get("adx"),
                        "ema_stack": market_data.get("ema_stack"),
                        "volume_ratio": market_data.get("volume_ratio"),
                        "bb_position": market_data.get("bb_position"),
                        "bb_squeeze": market_data.get("bb_squeeze"),
                        "obv_trend": market_data.get("obv_trend"),
                        "funding_rate": market_data.get("funding_rate"),
                        "open_interest": market_data.get("open_interest"),
                        "fear_greed": market_data.get("fear_greed"),
                        "price_vs_pivot": market_data.get("price_vs_pivot"),
                        "double_bottom": market_data.get("double_bottom", {}).get("detected", False) if isinstance(market_data.get("double_bottom"), dict) else False,
                        "double_top": market_data.get("double_top", {}).get("detected", False) if isinstance(market_data.get("double_top"), dict) else False,
                        "pattern_confidence": market_data.get("pattern_confidence"),
                    }

                # Save to database
                trade_id = None
                if self.db and self.db.enabled:
                    trade_id = self.db.save_trade_entry(
                        symbol=symbol,
                        direction=direction.value,
                        entry_price=price,
                        size_usd=size_usd,
                        leverage=leverage,
                        sl_price=sl_price,
                        tp_price=tp_price,
                        conviction_tier=conviction_tier,
                        ai_confidence=ai_confidence,
                        ai_reasoning=reason,
                        prompt_style=self.config.prompt_style,
                        indicators=indicators,
                    )
                    if trade_id:
                        logger.info(f"[DB] ✅ Trade salvato con trade_id={trade_id}")
                    else:
                        logger.error(f"[DB] ❌ save_trade_entry ha restituito None! Il trade non sarà tracciato nel DB")

                # Track position
                position = Position(
                    id=f"{symbol}_{int(time.time())}",
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    size=size_usd / price,
                    leverage=leverage,
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                    current_sl_level=-self.config.stop_loss_pct,
                    opened_at=datetime.now(),
                    max_price=price,
                    min_price=price,
                    trade_id=trade_id,
                    conviction_tier=conviction_tier,
                    ai_confidence=ai_confidence,
                    ai_reasoning=reason,
                    entry_indicators=indicators,
                )
                self.position_tracker.add_position(position)

                logger.info(f"[TRADE] ✅ Opened {direction.value} {symbol} | Size: ${size_usd:.0f}")
                logger.info(f"[TRADE]    Entry: ${price:.2f} | SL: ${sl_price:.2f} | TP: ${tp_price:.2f}")

                # Update cooldown timestamp for this symbol
                if self.config.symbol_cooldown_enabled:
                    self.config.symbol_last_trade_time[symbol] = datetime.now()
                    logger.debug(f"[COOLDOWN] Updated last trade time for {symbol}")

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
                        # Use string formatting to ensure exact decimal precision (avoids float issues)
                        if symbol in ["BTC", "ETH"]:
                            sl_price_rounded = float(f"{sl_price:.1f}")
                        elif symbol == "SOL":
                            sl_price_rounded = float(f"{sl_price:.2f}")
                        else:
                            sl_price_rounded = float(f"{sl_price:.4f}")

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
                            # Use string formatting to ensure exact decimal precision
                            if symbol in ["BTC", "ETH"]:
                                sl_price_rounded = float(f"{sl_price:.1f}")
                            elif symbol == "SOL":
                                sl_price_rounded = float(f"{sl_price:.2f}")
                            else:
                                sl_price_rounded = float(f"{sl_price:.4f}")
                            sl_order = self.trader.exchange.order(
                                symbol,
                                sl_is_buy,
                                actual_size,
                                sl_price_rounded,
                                {"trigger": {"triggerPx": sl_price_rounded, "isMarket": True, "tpsl": "sl"}},
                                reduce_only=True
                            )
                            if sl_order.get("status") == "ok":
                                logger.info(f"[TRADE] 🛡️ SL piazzato (retry) @ ${sl_price_rounded:.1f}")
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

        # Get position before closing (for database save)
        position = self.position_tracker.get_position(symbol)

        try:
            # Get current price for P&L calculation
            current_price = self.market_data.get_price(symbol)

            result = self.trader.exchange.market_close(symbol)

            # Gestisce il caso in cui market_close restituisce None
            if result is None:
                logger.error(f"[TRADE] ❌ market_close returned None for {symbol}")
                return

            if result.get("status") == "ok" or "response" in result:
                # Calculate P&L
                pnl_usd = 0.0
                pnl_pct = 0.0
                trailing_level = None

                if position:
                    if position.direction == TradeDirection.LONG:
                        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100 * position.leverage
                    else:
                        pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100 * position.leverage

                    pnl_usd = (position.size * position.entry_price) * (pnl_pct / 100)
                    trailing_level = position.current_sl_level if position.current_sl_level >= 0 else None

                    # Save to database
                    if self.db and self.db.enabled and position.trade_id:
                        self.db.close_trade(
                            trade_id=position.trade_id,
                            exit_price=current_price,
                            pnl_usd=pnl_usd,
                            pnl_pct=pnl_pct,
                            exit_reason=exit_type,
                            trailing_level_pct=trailing_level,
                        )

                self.position_tracker.remove_position(symbol)
                logger.info(f"[TRADE] ✅ Closed {symbol} | P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")
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

                # Countdown with periodic log
                if args.mode == "slow":
                    # SLOW: countdown ogni 60 secondi
                    remaining = interval
                    while remaining > 0:
                        sleep_chunk = min(60, remaining)
                        time.sleep(sleep_chunk)
                        remaining -= sleep_chunk
                        if remaining > 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            if mins > 0:
                                logger.info(f"[SLOW] ⏳ Next cycle in {int(mins)}m {int(secs)}s...")
                            else:
                                logger.info(f"[SLOW] ⏳ Next cycle in {int(secs)}s...")
                else:
                    # FAST: semplice sleep con heartbeat
                    logger.debug(f"[FAST] 💓 Sleeping {interval}s...")
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
