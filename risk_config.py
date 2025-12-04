#!/usr/bin/env python3
"""
Risk Configuration - Configurazione centralizzata per risk management.

Tutti i parametri di risk management sono qui per facile modifica.
Basato sull'analisi del DATABASE_SUMMARY.md (4 Dic 2025).

FINDINGS CHIAVE:
- Score 13-16 è OTTIMALE (60% win rate, +9.40 USD)
- Score >20 performa PEGGIO (24% win rate)
- AI_DECISION ha 0% win rate - disabilitato
- Max 25-30 trades/giorno per profittabilità
- MICRO_GAIN è l'unico mode profittevole
"""

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List, Tuple

load_dotenv()

# =============================================================================
#                           HELPER FUNCTIONS
# =============================================================================

def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    return os.getenv(key, str(default)).lower() == 'true'

def get_env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    return float(os.getenv(key, str(default)))

def get_env_int(key: str, default: int) -> int:
    """Get int from environment variable."""
    return int(os.getenv(key, str(default)))

def parse_trailing_steps(steps_str: str) -> List[Tuple[float, float]]:
    """Parse trailing steps from string 'pnl:sl,pnl:sl,...' to list of tuples."""
    steps = []
    try:
        for step in steps_str.split(','):
            pnl, sl = step.strip().split(':')
            steps.append((float(pnl), float(sl)))
        steps.sort(key=lambda x: x[0])
    except Exception as e:
        print(f"[RISK_CONFIG] Error parsing trailing steps '{steps_str}': {e}")
        steps = [(0.4, 0.1), (0.8, 0.3), (1.2, 0.6), (1.6, 1.0)]  # Default R/R 1.6
    return steps


# =============================================================================
#                           TRADING SYMBOLS
# =============================================================================

# Simboli abilitati al trading (da DATABASE: BTC ha win rate migliore)
ENABLED_SYMBOLS = os.getenv('ENABLED_SYMBOLS', 'BTC').split(',')
# ENABLED_SYMBOLS = ['BTC', 'ETH', 'SOL']  # Per riabilitare tutti


# =============================================================================
#                           SCORE THRESHOLDS
# =============================================================================
# FINDING: Score 13-16 è OTTIMALE (60% win rate)
# Score >20 performa PEGGIO (24% win rate)

@dataclass
class ScoreConfig:
    """Configurazione soglie score per decisioni di trading."""

    # Sotto HOLD_THRESHOLD: non fare nulla
    HOLD_THRESHOLD: float = get_env_float('SCORE_THRESHOLD_HOLD', 13.0)

    # Tra HOLD e OPEN: modalità MICRO_GAIN (la più profittevole)
    # Score 13-16 = MICRO_GAIN

    # Sopra OPEN_THRESHOLD: modalità NORMAL (meno profittevole!)
    OPEN_THRESHOLD: float = get_env_float('SCORE_THRESHOLD_OPEN', 16.0)

    # Score troppo alto (>20) performa peggio - potremmo skipparli
    MAX_SCORE_OVERRIDE: float = get_env_float('SCORE_MAX_OVERRIDE', 25.0)

    # Cicli di conferma score prima di aprire
    CONFIRMATION_CYCLES: int = get_env_int('SCORE_CONFIRMATION_CYCLES', 2)

    # Smoothing: media degli ultimi N scores
    SMOOTHING_SAMPLES: int = get_env_int('SCORE_SMOOTHING_SAMPLES', 3)

SCORE = ScoreConfig()


# =============================================================================
#                           DAILY LIMITS
# =============================================================================
# FINDING: 28-30 trades/giorno sono profittevoli
# 55+ trades/giorno generano perdite

@dataclass
class DailyLimitsConfig:
    """Limiti giornalieri per evitare overtrading."""

    # Massimo trades per giorno (per simbolo)
    MAX_TRADES_PER_DAY: int = get_env_int('MAX_TRADES_PER_DAY', 25)

    # Massimo trades totali (tutti i simboli)
    MAX_TOTAL_TRADES_PER_DAY: int = get_env_int('MAX_TOTAL_TRADES_PER_DAY', 30)

    # Minuti minimo tra un trade e l'altro (stesso simbolo)
    MIN_MINUTES_BETWEEN_TRADES: int = get_env_int('MIN_MINUTES_BETWEEN_TRADES', 30)

    # Cooldown dopo perdita (minuti)
    COOLDOWN_AFTER_LOSS_MINUTES: int = get_env_int('COOLDOWN_AFTER_LOSS_MINUTES', 45)

    # Ore di trading attivo (UTC)
    TRADING_START_HOUR_UTC: int = get_env_int('TRADING_START_HOUR', 0)
    TRADING_END_HOUR_UTC: int = get_env_int('TRADING_END_HOUR', 24)

DAILY_LIMITS = DailyLimitsConfig()


# =============================================================================
#                           MICRO_GAIN MODE (PROFITTEVOLE)
# =============================================================================
# FINDING: MICRO_GAIN è l'UNICO mode profittevole
# Win rate: BTC 58%, ETH 59%, SOL 62%

@dataclass
class MicroGainConfig:
    """Configurazione MICRO_GAIN - la modalità più profittevole."""

    ENABLED: bool = get_env_bool('MICRO_GAIN_ENABLED', True)

    # Position sizing
    LEVERAGE: int = get_env_int('MICRO_GAIN_LEVERAGE', 5)
    PORTION_OF_BALANCE: float = get_env_float('MICRO_GAIN_PORTION', 0.30)  # 30% balance

    # Take Profit: target +0.40 USD (o equivalente in %)
    # Con 5x leva su 30% balance ($30 margin = $150 notional)
    # +0.40 USD = circa +0.27% movimento prezzo = +1.33% P&L
    TARGET_PERCENT: float = get_env_float('MICRO_GAIN_TARGET_PERCENT', 1.5)

    # Stop Loss: max -0.25 USD (R/R 1.6x)
    # -0.25 USD = circa -0.17% movimento prezzo = -0.83% P&L
    STOP_LOSS_PERCENT: float = get_env_float('MICRO_GAIN_STOP_LOSS_PERCENT', 1.0)

    # Trailing Stop Mode: 'continuous', 'steps', 'disable'
    TRAILING_MODE: str = os.getenv('MICRO_GAIN_TRAILING_MODE', 'steps')

    # Trailing attivazione: parte quando P&L >= questo %
    TRAILING_ACTIVATION: float = get_env_float('MICRO_GAIN_TRAILING_ACTIVATION', 0.5)

    # Trailing gap (per mode 'continuous')
    TRAILING_GAP: float = get_env_float('MICRO_GAIN_TRAILING_GAP', 0.3)

    # Trailing steps (per mode 'steps')
    # Formato: "pnl_percent:sl_percent,..."
    # Significa: quando P&L raggiunge X%, imposta SL a Y%
    # OTTIMIZZATO per R/R 1.6x
    TRAILING_STEPS_STR: str = os.getenv(
        'MICRO_GAIN_TRAILING_STEPS',
        '0.4:0.1,0.6:0.2,0.8:0.35,1.0:0.5,1.2:0.7,1.5:1.0'
    )

    # Cooldown tra trades (secondi)
    COOLDOWN_SECONDS: int = get_env_int('MICRO_GAIN_COOLDOWN_SECONDS', 300)

    # Max posizioni contemporanee
    MAX_POSITIONS: int = get_env_int('MICRO_GAIN_MAX_POSITIONS', 1)  # 1 per sicurezza

    @property
    def TRAILING_STEPS(self) -> List[Tuple[float, float]]:
        return parse_trailing_steps(self.TRAILING_STEPS_STR)

MICRO_GAIN = MicroGainConfig()


# =============================================================================
#                           NORMAL MODE (MENO PROFITTEVOLE)
# =============================================================================
# FINDING: NORMAL mode ha win rate 0-37% - molto meno profittevole
# Usare con cautela, solo su segnali MOLTO forti (che però performano peggio...)

@dataclass
class NormalModeConfig:
    """Configurazione NORMAL mode - usare con cautela."""

    ENABLED: bool = get_env_bool('NORMAL_MODE_ENABLED', False)  # DISABILITATO default

    # Position sizing (più conservativo)
    LEVERAGE: int = get_env_int('NORMAL_LEVERAGE', 3)
    PORTION_OF_BALANCE: float = get_env_float('NORMAL_PORTION', 0.25)

    # Take Profit più ampio
    TARGET_PERCENT: float = get_env_float('NORMAL_TARGET_PERCENT', 3.0)

    # Stop Loss
    STOP_LOSS_PERCENT: float = get_env_float('NORMAL_STOP_LOSS_PERCENT', 2.0)

    # Trailing
    TRAILING_ENABLED: bool = get_env_bool('NORMAL_TRAILING_ENABLED', True)
    TRAILING_MODE: str = os.getenv('NORMAL_TRAILING_MODE', 'steps')
    TRAILING_ACTIVATION: float = get_env_float('NORMAL_TRAILING_ACTIVATION', 1.0)
    TRAILING_GAP: float = get_env_float('NORMAL_TRAILING_GAP', 0.8)

    TRAILING_STEPS_STR: str = os.getenv(
        'NORMAL_TRAILING_STEPS',
        '1.0:0.0,1.5:0.5,2.0:1.0,2.5:1.5,3.0:2.0'
    )

    @property
    def TRAILING_STEPS(self) -> List[Tuple[float, float]]:
        return parse_trailing_steps(self.TRAILING_STEPS_STR)

NORMAL = NormalModeConfig()


# =============================================================================
#                           AI DECISION (DISABILITATO)
# =============================================================================
# FINDING: AI_DECISION ha 0% win rate - 46 trades TUTTI in perdita

@dataclass
class AIDecisionConfig:
    """Configurazione chiusure AI - DISABILITATO causa 0% win rate."""

    # DISABILITATO: l'AI non può chiudere posizioni autonomamente
    # Chiusure gestite SOLO da TP/SL/Trailing
    ENABLED: bool = get_env_bool('AI_DECISION_ENABLED', False)

    # Se abilitato, richiede conferma di X cicli prima di chiudere
    CONFIRMATION_CYCLES: int = get_env_int('AI_CLOSE_CONFIRMATION', 5)

    # Profit minimo per permettere chiusura AI (%)
    MIN_PROFIT_FOR_CLOSE: float = get_env_float('AI_MIN_PROFIT_FOR_CLOSE', 0.5)

AI_DECISION = AIDecisionConfig()


# =============================================================================
#                           SENTINEL CONFIGURATION
# =============================================================================

@dataclass
class SentinelConfig:
    """Configurazione Sentinel - monitoraggio continuo posizioni."""

    ENABLED: bool = get_env_bool('SENTINEL_ENABLED', True)
    INTERVAL_SECONDS: int = get_env_int('SENTINEL_INTERVAL_SECONDS', 30)

    # Telegram notifications
    TELEGRAM_NOTIFY: bool = get_env_bool('SENTINEL_TELEGRAM_NOTIFY', True)

    # Wake AI dopo chiusure
    WAKE_ON_TP_HIT: bool = get_env_bool('SENTINEL_WAKE_ON_TP', True)
    WAKE_ON_SL_HIT: bool = get_env_bool('SENTINEL_WAKE_ON_SL', False)
    WAKE_ON_TRAILING: bool = get_env_bool('SENTINEL_WAKE_ON_TRAILING', True)

    # Log file
    LOG_FILE_PATH: str = os.getenv('LOG_FILE_PATH', '/app/logs/sentinel.log')

SENTINEL = SentinelConfig()


# =============================================================================
#                           HYPERLIQUID CONNECTION
# =============================================================================

@dataclass
class HyperliquidConfig:
    """Configurazione connessione Hyperliquid."""

    TESTNET: bool = get_env_bool('TESTNET', False)  # MAINNET default
    PRIVATE_KEY: str = os.getenv('PRIVATE_KEY', '')
    WALLET_ADDRESS: str = os.getenv('WALLET_ADDRESS', '')

HYPERLIQUID = HyperliquidConfig()


# =============================================================================
#                           RISK SUMMARY
# =============================================================================

def print_risk_config():
    """Stampa configurazione risk management attuale."""
    print("\n" + "="*60)
    print("        RISK CONFIGURATION SUMMARY")
    print("="*60)

    print(f"\n[SYMBOLS] Trading abilitato per: {ENABLED_SYMBOLS}")

    print(f"\n[SCORE THRESHOLDS]")
    print(f"  HOLD (no trade):    < {SCORE.HOLD_THRESHOLD}")
    print(f"  MICRO_GAIN:         {SCORE.HOLD_THRESHOLD} - {SCORE.OPEN_THRESHOLD}")
    print(f"  NORMAL:             > {SCORE.OPEN_THRESHOLD}")

    print(f"\n[DAILY LIMITS]")
    print(f"  Max trades/day:     {DAILY_LIMITS.MAX_TRADES_PER_DAY}")
    print(f"  Min minutes between: {DAILY_LIMITS.MIN_MINUTES_BETWEEN_TRADES}")

    print(f"\n[MICRO_GAIN MODE] {'ENABLED' if MICRO_GAIN.ENABLED else 'DISABLED'}")
    print(f"  Leverage:           {MICRO_GAIN.LEVERAGE}x")
    print(f"  Portion:            {MICRO_GAIN.PORTION_OF_BALANCE*100:.0f}%")
    print(f"  Take Profit:        +{MICRO_GAIN.TARGET_PERCENT}% P&L")
    print(f"  Stop Loss:          -{MICRO_GAIN.STOP_LOSS_PERCENT}% P&L")
    print(f"  Trailing Mode:      {MICRO_GAIN.TRAILING_MODE}")
    print(f"  R/R Ratio:          {MICRO_GAIN.TARGET_PERCENT/MICRO_GAIN.STOP_LOSS_PERCENT:.2f}x")

    print(f"\n[NORMAL MODE] {'ENABLED' if NORMAL.ENABLED else 'DISABLED'}")

    print(f"\n[AI DECISION] {'ENABLED' if AI_DECISION.ENABLED else 'DISABLED (0% win rate)'}")

    print(f"\n[SENTINEL] {'ENABLED' if SENTINEL.ENABLED else 'DISABLED'}")
    print(f"  Interval:           {SENTINEL.INTERVAL_SECONDS}s")

    print("="*60 + "\n")


if __name__ == '__main__':
    print_risk_config()
