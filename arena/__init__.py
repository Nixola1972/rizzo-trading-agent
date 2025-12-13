"""
Arena - Trading Simulation System

A simulation framework for testing trading strategies without risking real money.
Runs multiple variants simultaneously to find optimal configurations.
"""

__version__ = "1.0.0"

from .models import Variant, SubVariant, SimulatedTrade, SimulatedPosition
from .db import ArenaDB
from .config_loader import load_variants, get_variant
from .simulator import ArenaSimulator
from .ai_manager import AIManager
from .smart_sl import SmartSLManager
from .metrics import calculate_metrics, get_leaderboard
from .reporter import ArenaReporter

__all__ = [
    "Variant",
    "SubVariant",
    "SimulatedTrade",
    "SimulatedPosition",
    "ArenaDB",
    "load_variants",
    "get_variant",
    "ArenaSimulator",
    "AIManager",
    "SmartSLManager",
    "calculate_metrics",
    "get_leaderboard",
    "ArenaReporter",
]
