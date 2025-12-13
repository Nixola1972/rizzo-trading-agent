"""
Arena Configuration Loader

Loads variant configurations from JSON file or environment variables.
Supports auto-creation of default variants on first run.
"""

import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from .models import (
    Variant,
    SubVariant,
    TradingParams,
    IndicatorConfig,
    OperationMode,
)
from .db import ArenaDB


# Default configuration file path
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "variants.json")


def get_default_variants() -> List[Dict[str, Any]]:
    """
    Return default variant configurations.
    These are created on first run if no config file exists.
    """
    return [
        {
            "id": "V1_BASELINE",
            "name": "Baseline",
            "description": "Current production configuration for comparison",
            "enabled": True,
            "operation_mode": "SCORE_TRIGGERED",
            "ai_models": ["deepseek/deepseek-chat"],
            "trading_params": {
                "position_size_usd": 50.0,
                "leverage": 3,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 6.0,
                "trailing_enabled": True,
                "trailing_steps": "2.5:0.0,5.0:2.0,7.5:4.0",
                "score_threshold_open": 15.0,
                "double_check_ai_enabled": True,
                "trading_style": "moderate",
                "smart_sl_enabled": False,
            },
            "indicator_config": {
                "weight_macd": 25.0,
                "weight_rsi": 15.0,
                "weight_ema_alignment": 20.0,
                "weight_adx_trend": 15.0,
                "weight_double_bottom": 12.0,
                "weight_double_top": 12.0,
            },
            "pattern_detection_enabled": True,
            "symbols": ["BTC", "ETH", "SOL"],
        },
        {
            "id": "V2_MULTI_AI",
            "name": "Multi-AI Battle",
            "description": "Same config, different AI models compete",
            "enabled": True,
            "operation_mode": "SCORE_TRIGGERED",
            "ai_models": [
                "deepseek/deepseek-chat",
                "openai/gpt-4o-mini",
                "anthropic/claude-3-haiku",
                "qwen/qwen-2.5-72b-instruct",
            ],
            "trading_params": {
                "position_size_usd": 50.0,
                "leverage": 3,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 6.0,
                "trailing_enabled": True,
                "trailing_steps": "2.5:0.0,5.0:2.0,7.5:4.0",
                "score_threshold_open": 15.0,
                "double_check_ai_enabled": True,
                "trading_style": "moderate",
                "smart_sl_enabled": False,
            },
            "indicator_config": {},
            "pattern_detection_enabled": True,
            "symbols": ["BTC", "ETH", "SOL"],
        },
        {
            "id": "V3_SMART_EXIT",
            "name": "Smart Exit",
            "description": "AI-controlled stop loss with extension capability",
            "enabled": True,
            "operation_mode": "SCORE_TRIGGERED",
            "ai_models": ["deepseek/deepseek-chat"],
            "trading_params": {
                "position_size_usd": 50.0,
                "leverage": 3,
                "stop_loss_pct": 3.5,
                "take_profit_pct": 7.0,
                "trailing_enabled": True,
                "trailing_steps": "3.0:0.0,6.0:2.5,9.0:5.0",
                "score_threshold_open": 15.0,
                "double_check_ai_enabled": True,
                "trading_style": "moderate",
                "smart_sl_enabled": True,
                "smart_sl_extension_pct": 1.0,
                "smart_sl_max_extensions": 2,
            },
            "indicator_config": {},
            "pattern_detection_enabled": True,
            "symbols": ["BTC", "ETH", "SOL"],
        },
        {
            "id": "V4_INDICATOR_TEST",
            "name": "Indicator Optimization",
            "description": "Testing different indicator weights and periods",
            "enabled": True,
            "operation_mode": "SCORE_TRIGGERED",
            "ai_models": ["deepseek/deepseek-chat"],
            "trading_params": {
                "position_size_usd": 50.0,
                "leverage": 3,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 6.0,
                "trailing_enabled": True,
                "trailing_steps": "2.5:0.0,5.0:2.0,7.5:4.0",
                "score_threshold_open": 12.0,
                "double_check_ai_enabled": True,
                "trading_style": "moderate",
                "smart_sl_enabled": False,
            },
            "indicator_config": {
                "ema_short_period": 7,
                "ema_medium_period": 14,
                "rsi_period": 10,
                "macd_fast": 8,
                "macd_slow": 21,
                "weight_macd": 30.0,
                "weight_rsi": 10.0,
                "weight_ema_alignment": 25.0,
                "weight_adx_trend": 20.0,
                "weight_double_bottom": 15.0,
                "weight_double_top": 15.0,
                "macd_threshold_strong": 0.15,
                "adx_min_trend": 18.0,
            },
            "pattern_detection_enabled": True,
            "symbols": ["BTC", "ETH", "SOL"],
        },
        {
            "id": "V5_AI_FREE",
            "name": "AI Independent",
            "description": "AI decides every 15 min without score filter",
            "enabled": True,
            "operation_mode": "AI_INDEPENDENT",
            "ai_models": [
                "deepseek/deepseek-chat",
                "openai/gpt-4o-mini",
            ],
            "trading_params": {
                "position_size_usd": 50.0,
                "leverage": 3,
                "stop_loss_pct": 4.0,
                "take_profit_pct": 8.0,
                "trailing_enabled": True,
                "trailing_steps": "3.0:0.0,6.0:2.5,9.0:5.0",
                "score_threshold_open": 0.0,
                "double_check_ai_enabled": False,
                "trading_style": "moderate",
                "smart_sl_enabled": True,
                "smart_sl_extension_pct": 1.5,
                "smart_sl_max_extensions": 3,
            },
            "indicator_config": {},
            "ai_check_interval_minutes": 15,
            "ai_independent_timeframe": "4h",
            "pattern_detection_enabled": True,
            "symbols": ["BTC", "ETH", "SOL"],
        },
    ]


def load_variants_from_file(config_path: Optional[str] = None) -> List[Variant]:
    """
    Load variants from JSON configuration file.
    Creates default file if it doesn't exist.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    # Create default config if not exists
    if not os.path.exists(path):
        create_default_config(path)

    with open(path, "r") as f:
        config = json.load(f)

    variants = []
    for v_data in config.get("variants", []):
        variant = Variant.from_dict(v_data)
        variant.create_sub_variants()
        variants.append(variant)

    return variants


def create_default_config(path: str) -> None:
    """Create default configuration file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    config = {
        "version": "1.0",
        "description": "Arena variant configurations",
        "variants": get_default_variants(),
    }

    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def load_variants(db: Optional[ArenaDB] = None) -> List[Variant]:
    """
    Load variants from database or create from defaults.
    This is the main entry point for loading variants.
    """
    if db is None:
        db = ArenaDB()

    # Try to load from database first
    variants = db.get_all_variants(enabled_only=False)

    if not variants:
        # No variants in DB, load from file and save
        variants = load_variants_from_file()

        for variant in variants:
            db.save_variant(variant)

    return variants


def get_variant(variant_id: str, db: Optional[ArenaDB] = None) -> Optional[Variant]:
    """Get a specific variant by ID."""
    if db is None:
        db = ArenaDB()

    return db.get_variant(variant_id)


def save_variant(variant: Variant, db: Optional[ArenaDB] = None) -> bool:
    """Save a variant to database."""
    if db is None:
        db = ArenaDB()

    return db.save_variant(variant)


def enable_variant(variant_id: str, enabled: bool = True, db: Optional[ArenaDB] = None) -> bool:
    """Enable or disable a variant."""
    if db is None:
        db = ArenaDB()

    variant = db.get_variant(variant_id)
    if not variant:
        return False

    variant.enabled = enabled
    return db.save_variant(variant)


def get_enabled_variants(db: Optional[ArenaDB] = None) -> List[Variant]:
    """Get only enabled variants."""
    if db is None:
        db = ArenaDB()

    return db.get_all_variants(enabled_only=True)


def reload_variants_from_file(db: Optional[ArenaDB] = None) -> List[Variant]:
    """
    Reload variants from config file, updating database.
    Preserves statistics from existing variants.
    """
    if db is None:
        db = ArenaDB()

    # Load fresh from file
    file_variants = load_variants_from_file()

    # Get existing variants for stats preservation
    existing = {v.id: v for v in db.get_all_variants(enabled_only=False)}

    for variant in file_variants:
        # Preserve stats if variant existed
        if variant.id in existing:
            old = existing[variant.id]
            variant.total_trades = old.total_trades
            variant.total_pnl_usd = old.total_pnl_usd

            # Preserve sub-variant stats
            for sv in variant.sub_variants:
                old_sv = old.get_sub_variant(sv.ai_model)
                if old_sv:
                    sv.total_trades = old_sv.total_trades
                    sv.winning_trades = old_sv.winning_trades
                    sv.losing_trades = old_sv.losing_trades
                    sv.total_pnl_usd = old_sv.total_pnl_usd
                    sv.total_pnl_pct = old_sv.total_pnl_pct
                    sv.max_drawdown_pct = old_sv.max_drawdown_pct

        db.save_variant(variant)

    return file_variants
