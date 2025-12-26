"""
AlphaTrader Module
==================

A parallel trading system inspired by AlphaGo/AlphaZero architecture.
This module is COMPLETELY INDEPENDENT from botone_v6 and can run in parallel.

Components:
-----------
- PolicyNetwork: Neural network that decides actions (OPEN/CLOSE/HOLD, direction, leverage)
- ValueNetwork: Neural network that estimates probability of profit
- MCTS: Monte Carlo Tree Search for lookahead simulation
- Trainer: Reinforcement Learning training loop
- Trader: Main execution engine (like botone_v6 but RL-powered)

Architecture:
-------------
                    ┌─────────────────┐
                    │   MarketState   │
                    │  (indicators,   │
                    │   sentiment,    │
                    │   position)     │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
    ┌─────────────────┐            ┌─────────────────┐
    │  PolicyNetwork  │            │  ValueNetwork   │
    │  (what to do)   │            │  (win prob)     │
    └────────┬────────┘            └────────┬────────┘
             │                              │
             └──────────────┬───────────────┘
                            ▼
                    ┌─────────────────┐
                    │      MCTS       │
                    │  (simulate N    │
                    │   scenarios)    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Action      │
                    │  (execute if    │
                    │   value > 60%)  │
                    └─────────────────┘

Shared Modules (from parent):
-----------------------------
- indicators.py: Technical analysis (EMA, RSI, MACD, ATR, etc.)
- forecaster.py: Prophet predictions
- signal_scorer.py: Score calculation
- hyperliquid_trader.py: Exchange execution
- sentiment.py: Fear & Greed Index

Usage:
------
    # Training mode (learn from historical data)
    python -m alpha.trainer --train --episodes 10000

    # Trading mode (live or paper)
    python -m alpha.trader --mode paper --loop
    python -m alpha.trader --mode live --loop

Author: AlphaTrader System
Version: 0.1.0
"""

from .config import AlphaConfig
from .market_state import MarketState, Action, ActionType
from .reward import RewardCalculator

__version__ = "0.1.0"
__all__ = [
    "AlphaConfig",
    "MarketState",
    "Action",
    "ActionType",
    "RewardCalculator",
]
