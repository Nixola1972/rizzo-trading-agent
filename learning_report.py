#!/usr/bin/env python3
"""
TRADE LEARNING REPORT
=====================

Analizza automaticamente i trade e genera raccomandazioni concrete
per migliorare i parametri del sistema.

Esegui con: python learning_report.py [giorni]
Esempio: python learning_report.py 7

Opzioni:
  --telegram    Invia report anche su Telegram
  --json        Output in formato JSON
  --ai          Includi analisi AI (costa token)
"""

import sys
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

sys.path.insert(0, '.')

import db_utils
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Recommendation:
    """Una raccomandazione di modifica parametro."""
    parameter: str
    current_value: str
    suggested_value: str
    reason: str
    confidence: int  # 0-100
    impact: str  # "high", "medium", "low"
    category: str  # "entry", "exit", "risk", "filter"


@dataclass
class Pattern:
    """Un pattern identificato nei dati."""
    name: str
    description: str
    evidence: str
    severity: str  # "critical", "warning", "info"


@dataclass
class LearningReport:
    """Report completo di analisi."""
    generated_at: str
    period_days: int

    # Summary
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_trade_pnl: float

    # Comparisons
    prev_period_win_rate: Optional[float]
    win_rate_change: Optional[float]

    # Patterns
    patterns: List[Pattern]

    # Recommendations
    recommendations: List[Recommendation]

    # Raw insights
    insights: List[str]


# ============================================================================
# DATABASE QUERIES
# ============================================================================

def get_basic_stats(days: int) -> Dict:
    """Statistiche base del periodo."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    COUNT(CASE WHEN profitable = false THEN 1 END) as losses,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(net_pnl_usd)::numeric, 4) as avg_pnl,
                    ROUND(AVG(CASE WHEN profitable = true THEN net_pnl_usd END)::numeric, 4) as avg_win,
                    ROUND(AVG(CASE WHEN profitable = false THEN net_pnl_usd END)::numeric, 4) as avg_loss,
                    ROUND(AVG(duration_seconds/60.0)::numeric, 1) as avg_duration_min
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            row = cur.fetchone()
            return {
                "total": row[0] or 0,
                "wins": row[1] or 0,
                "losses": row[2] or 0,
                "win_rate": float(row[3] or 0),
                "total_pnl": float(row[4] or 0),
                "avg_pnl": float(row[5] or 0),
                "avg_win": float(row[6] or 0),
                "avg_loss": float(row[7] or 0),
                "avg_duration_min": float(row[8] or 0)
            }


def get_previous_period_stats(days: int) -> Dict:
    """Statistiche del periodo precedente per confronto."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND closed_at < NOW() - INTERVAL '%s days'
            """, (days * 2, days))
            row = cur.fetchone()
            return {
                "total": row[0] or 0,
                "win_rate": float(row[1] or 0),
                "total_pnl": float(row[2] or 0)
            }


def get_score_performance(days: int) -> List[Dict]:
    """Performance per range di score."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    CASE
                        WHEN ABS(open_score) < 15 THEN '10-15'
                        WHEN ABS(open_score) < 18 THEN '15-18'
                        WHEN ABS(open_score) < 20 THEN '18-20'
                        WHEN ABS(open_score) < 22 THEN '20-22'
                        WHEN ABS(open_score) < 25 THEN '22-25'
                        ELSE '25+'
                    END as score_range,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(ABS(open_score))::numeric, 1) as avg_score
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND open_score IS NOT NULL
                GROUP BY score_range
                ORDER BY avg_score
            """, (days,))
            return [{"range": r[0], "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0), "avg_score": float(r[4] or 0)}
                   for r in cur.fetchall()]


def get_peak_analysis(days: int) -> Dict:
    """Analisi dei peak P&L - quanto profitto lasciamo sul tavolo."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            # Trade persi che erano in profitto
            cur.execute("""
                SELECT
                    COUNT(*) as total_losses,
                    COUNT(CASE WHEN peak_pnl_percent > 0 THEN 1 END) as had_profit,
                    COUNT(CASE WHEN peak_pnl_percent >= 0.5 THEN 1 END) as reached_05,
                    COUNT(CASE WHEN peak_pnl_percent >= 1.0 THEN 1 END) as reached_1,
                    COUNT(CASE WHEN peak_pnl_percent >= 1.5 THEN 1 END) as reached_15,
                    COUNT(CASE WHEN peak_pnl_percent >= 2.0 THEN 1 END) as reached_2,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit
                FROM trades
                WHERE status = 'CLOSED'
                  AND profitable = false
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            row = cur.fetchone()

            total_losses = row[0] or 0
            return {
                "total_losses": total_losses,
                "had_profit": row[1] or 0,
                "had_profit_pct": round(100 * (row[1] or 0) / max(total_losses, 1), 1),
                "reached_05": row[2] or 0,
                "reached_1": row[3] or 0,
                "reached_15": row[4] or 0,
                "reached_2": row[5] or 0,
                "avg_peak": float(row[6] or 0),
                "avg_exit": float(row[7] or 0)
            }


def get_duration_performance(days: int) -> List[Dict]:
    """Performance per durata del trade."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    CASE
                        WHEN duration_seconds < 300 THEN '< 5 min'
                        WHEN duration_seconds < 900 THEN '5-15 min'
                        WHEN duration_seconds < 1800 THEN '15-30 min'
                        WHEN duration_seconds < 3600 THEN '30-60 min'
                        ELSE '60+ min'
                    END as duration_range,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND duration_seconds IS NOT NULL
                GROUP BY duration_range
                ORDER BY MIN(duration_seconds)
            """, (days,))
            return [{"range": r[0], "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0)} for r in cur.fetchall()]


def get_symbol_performance(days: int) -> List[Dict]:
    """Performance per symbol."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(net_pnl_usd)::numeric, 4) as avg_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY symbol
                ORDER BY total_pnl DESC
            """, (days,))
            return [{"symbol": r[0], "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0), "avg_pnl": float(r[4] or 0)}
                   for r in cur.fetchall()]


def get_direction_performance(days: int) -> List[Dict]:
    """Performance LONG vs SHORT."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    direction,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY direction
            """, (days,))
            return [{"direction": r[0], "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0)} for r in cur.fetchall()]


def get_close_reason_stats(days: int) -> List[Dict]:
    """Performance per close reason."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    close_reason,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY close_reason
                ORDER BY trades DESC
            """, (days,))
            return [{"reason": r[0], "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0), "avg_peak": float(r[4] or 0),
                    "avg_exit": float(r[5] or 0)} for r in cur.fetchall()]


def get_hourly_performance(days: int) -> List[Dict]:
    """Performance per ora del giorno."""
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    EXTRACT(HOUR FROM opened_at) as hour,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY hour
                HAVING COUNT(*) >= 3
                ORDER BY hour
            """, (days,))
            return [{"hour": int(r[0]), "trades": r[1], "win_rate": float(r[2] or 0),
                    "total_pnl": float(r[3] or 0)} for r in cur.fetchall()]


def get_current_env_params() -> Dict:
    """Legge i parametri attuali dal .env."""
    return {
        "SCORE_THRESHOLD_OPEN": os.getenv("SCORE_THRESHOLD_OPEN", "15"),
        "MICRO_GAIN_STOP_LOSS_PERCENT": os.getenv("MICRO_GAIN_STOP_LOSS_PERCENT", "1.0"),
        "MICRO_GAIN_TARGET_PERCENT": os.getenv("MICRO_GAIN_TARGET_PERCENT", "4.0"),
        "MICRO_GAIN_TRAILING_STEPS": os.getenv("MICRO_GAIN_TRAILING_STEPS", ""),
        "MICRO_GAIN_LEVERAGE": os.getenv("MICRO_GAIN_LEVERAGE", "5"),
        "TRADING_STYLE": os.getenv("TRADING_STYLE", "moderate"),
        "ENABLED_SYMBOLS": os.getenv("ENABLED_SYMBOLS", "BTC,ETH,SOL"),
    }


# ============================================================================
# PATTERN DETECTION
# ============================================================================

def detect_patterns(
    stats: Dict,
    score_perf: List[Dict],
    peak_analysis: Dict,
    duration_perf: List[Dict],
    symbol_perf: List[Dict],
    direction_perf: List[Dict],
    close_reasons: List[Dict],
    hourly_perf: List[Dict]
) -> List[Pattern]:
    """Identifica pattern nei dati."""
    patterns = []

    # 1. Score threshold troppo basso
    low_score_wr = None
    high_score_wr = None
    for s in score_perf:
        if s["range"] in ["10-15", "15-18"]:
            if s["trades"] >= 5:
                low_score_wr = s["win_rate"]
        elif s["range"] in ["20-22", "22-25", "25+"]:
            if s["trades"] >= 3:
                high_score_wr = max(high_score_wr or 0, s["win_rate"])

    if low_score_wr and high_score_wr and high_score_wr - low_score_wr > 15:
        patterns.append(Pattern(
            name="SCORE_THRESHOLD_LOW",
            description="Score basso ha win rate molto peggiore di score alto",
            evidence=f"Score basso: {low_score_wr}% WR | Score alto: {high_score_wr}% WR | Gap: {high_score_wr - low_score_wr}%",
            severity="critical"
        ))

    # 2. Profitto lasciato sul tavolo
    if peak_analysis["had_profit_pct"] > 50:
        patterns.append(Pattern(
            name="PROFIT_LEFT_ON_TABLE",
            description=f"{peak_analysis['had_profit_pct']}% dei trade persi erano in profitto prima",
            evidence=f"Peak medio: {peak_analysis['avg_peak']}% | Exit medio: {peak_analysis['avg_exit']}%",
            severity="critical"
        ))
    elif peak_analysis["had_profit_pct"] > 30:
        patterns.append(Pattern(
            name="PROFIT_LEFT_ON_TABLE",
            description=f"{peak_analysis['had_profit_pct']}% dei trade persi erano in profitto prima",
            evidence=f"Peak medio: {peak_analysis['avg_peak']}% | Exit medio: {peak_analysis['avg_exit']}%",
            severity="warning"
        ))

    # 3. Trade troppo corti perdono
    short_trades = next((d for d in duration_perf if d["range"] == "< 5 min"), None)
    if short_trades and short_trades["trades"] >= 5 and short_trades["win_rate"] < 40:
        patterns.append(Pattern(
            name="SHORT_DURATION_LOSES",
            description="Trade sotto 5 minuti hanno win rate basso",
            evidence=f"{short_trades['trades']} trade | Win Rate: {short_trades['win_rate']}%",
            severity="warning"
        ))

    # 4. Un symbol underperforma
    if len(symbol_perf) >= 2:
        best = max(symbol_perf, key=lambda x: x["win_rate"])
        worst = min(symbol_perf, key=lambda x: x["win_rate"])
        if worst["trades"] >= 5 and best["win_rate"] - worst["win_rate"] > 20:
            patterns.append(Pattern(
                name="SYMBOL_UNDERPERFORM",
                description=f"{worst['symbol']} ha win rate molto peggiore di {best['symbol']}",
                evidence=f"{worst['symbol']}: {worst['win_rate']}% | {best['symbol']}: {best['win_rate']}%",
                severity="warning"
            ))

    # 5. LONG vs SHORT sbilanciato
    long_perf = next((d for d in direction_perf if d["direction"] and d["direction"].upper() == "LONG"), None)
    short_perf = next((d for d in direction_perf if d["direction"] and d["direction"].upper() == "SHORT"), None)
    if long_perf and short_perf:
        if long_perf["trades"] >= 5 and short_perf["trades"] >= 5:
            diff = abs(long_perf["win_rate"] - short_perf["win_rate"])
            if diff > 20:
                worse = "SHORT" if short_perf["win_rate"] < long_perf["win_rate"] else "LONG"
                patterns.append(Pattern(
                    name="DIRECTION_IMBALANCE",
                    description=f"{worse} performa significativamente peggio",
                    evidence=f"LONG: {long_perf['win_rate']}% | SHORT: {short_perf['win_rate']}%",
                    severity="warning"
                ))

    # 6. SL hit rate alto
    sl_stats = next((c for c in close_reasons if c["reason"] == "SL_HIT"), None)
    if sl_stats and stats["total"] > 0:
        sl_rate = 100 * sl_stats["trades"] / stats["total"]
        if sl_rate > 40:
            patterns.append(Pattern(
                name="HIGH_SL_RATE",
                description=f"SL triggerato nel {sl_rate:.0f}% dei trade",
                evidence=f"{sl_stats['trades']} SL hits su {stats['total']} trade totali",
                severity="critical" if sl_rate > 50 else "warning"
            ))

    # 7. Win rate generale basso
    if stats["win_rate"] < 45 and stats["total"] >= 10:
        patterns.append(Pattern(
            name="LOW_WIN_RATE",
            description=f"Win rate generale sotto 45%: {stats['win_rate']}%",
            evidence=f"{stats['wins']} wins su {stats['total']} trade",
            severity="critical"
        ))

    # 8. R/R ratio sbilanciato
    if stats["avg_win"] and stats["avg_loss"] and stats["avg_loss"] != 0:
        rr = abs(stats["avg_win"] / stats["avg_loss"])
        if rr < 0.8:
            patterns.append(Pattern(
                name="BAD_RR_RATIO",
                description=f"Risk/Reward ratio basso: {rr:.2f}",
                evidence=f"Avg Win: ${stats['avg_win']:.2f} | Avg Loss: ${stats['avg_loss']:.2f}",
                severity="warning"
            ))

    return patterns


# ============================================================================
# RECOMMENDATION ENGINE
# ============================================================================

def generate_recommendations(
    patterns: List[Pattern],
    stats: Dict,
    score_perf: List[Dict],
    peak_analysis: Dict,
    duration_perf: List[Dict],
    symbol_perf: List[Dict],
    current_params: Dict
) -> List[Recommendation]:
    """Genera raccomandazioni basate sui pattern."""
    recommendations = []

    for pattern in patterns:
        if pattern.name == "SCORE_THRESHOLD_LOW":
            # Trova lo score ottimale
            best_score_range = max(
                [s for s in score_perf if s["trades"] >= 3],
                key=lambda x: x["win_rate"],
                default=None
            )
            if best_score_range:
                suggested = best_score_range["range"].split("-")[0]
                recommendations.append(Recommendation(
                    parameter="SCORE_THRESHOLD_OPEN",
                    current_value=current_params.get("SCORE_THRESHOLD_OPEN", "15"),
                    suggested_value=suggested,
                    reason=f"Score {best_score_range['range']} ha win rate {best_score_range['win_rate']}%",
                    confidence=85,
                    impact="high",
                    category="entry"
                ))

        elif pattern.name == "PROFIT_LEFT_ON_TABLE":
            # Suggerisci trailing più aggressivo
            if peak_analysis["reached_1"] > peak_analysis["total_losses"] * 0.3:
                recommendations.append(Recommendation(
                    parameter="MICRO_GAIN_TARGET_PERCENT",
                    current_value=current_params.get("MICRO_GAIN_TARGET_PERCENT", "4.0"),
                    suggested_value="1.5",
                    reason=f"{peak_analysis['reached_1']} trade persi avevano raggiunto +1%",
                    confidence=78,
                    impact="high",
                    category="exit"
                ))

            # Suggerisci trailing breakeven anticipato
            recommendations.append(Recommendation(
                parameter="MICRO_GAIN_TRAILING_STEPS",
                current_value=current_params.get("MICRO_GAIN_TRAILING_STEPS", "N/A")[:50],
                suggested_value="0.5:-5.0,1.0:-3.0,1.5:-1.0,2.0:0.0,2.5:0.5,3.0:1.0",
                reason=f"Breakeven a +2% per proteggere profitti (peak medio era {peak_analysis['avg_peak']}%)",
                confidence=75,
                impact="high",
                category="exit"
            ))

        elif pattern.name == "HIGH_SL_RATE":
            current_sl = float(current_params.get("MICRO_GAIN_STOP_LOSS_PERCENT", "1.0"))
            suggested_sl = min(current_sl * 1.5, 5.0)
            recommendations.append(Recommendation(
                parameter="MICRO_GAIN_STOP_LOSS_PERCENT",
                current_value=str(current_sl),
                suggested_value=f"{suggested_sl:.1f}",
                reason="SL troppo stretto, considera allargarlo",
                confidence=70,
                impact="medium",
                category="risk"
            ))

        elif pattern.name == "SYMBOL_UNDERPERFORM":
            # Trova il symbol peggiore
            worst = min(symbol_perf, key=lambda x: x["win_rate"])
            if worst["win_rate"] < 40 and worst["trades"] >= 5:
                current_symbols = current_params.get("ENABLED_SYMBOLS", "BTC,ETH,SOL")
                suggested_symbols = ",".join([s for s in current_symbols.split(",")
                                             if s != worst["symbol"]])
                recommendations.append(Recommendation(
                    parameter="ENABLED_SYMBOLS",
                    current_value=current_symbols,
                    suggested_value=suggested_symbols,
                    reason=f"{worst['symbol']} ha solo {worst['win_rate']}% win rate",
                    confidence=65,
                    impact="medium",
                    category="filter"
                ))

        elif pattern.name == "SHORT_DURATION_LOSES":
            recommendations.append(Recommendation(
                parameter="MIN_POSITION_AGE_SECONDS",
                current_value=os.getenv("MIN_POSITION_AGE_SECONDS", "0"),
                suggested_value="300",
                reason="Trade troppo corti perdono, aspetta almeno 5 minuti prima di chiudere",
                confidence=60,
                impact="low",
                category="exit"
            ))

        elif pattern.name == "LOW_WIN_RATE":
            # Suggerisci stile più conservativo
            current_style = current_params.get("TRADING_STYLE", "moderate")
            if current_style != "conservative":
                recommendations.append(Recommendation(
                    parameter="TRADING_STYLE",
                    current_value=current_style,
                    suggested_value="conservative",
                    reason=f"Win rate basso ({stats['win_rate']}%), usa filtri più stretti",
                    confidence=70,
                    impact="high",
                    category="entry"
                ))

    # Ordina per confidence
    recommendations.sort(key=lambda x: x.confidence, reverse=True)

    return recommendations


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_report(days: int = 7) -> LearningReport:
    """Genera il report completo."""

    # Raccogli dati
    stats = get_basic_stats(days)
    prev_stats = get_previous_period_stats(days)
    score_perf = get_score_performance(days)
    peak_analysis = get_peak_analysis(days)
    duration_perf = get_duration_performance(days)
    symbol_perf = get_symbol_performance(days)
    direction_perf = get_direction_performance(days)
    close_reasons = get_close_reason_stats(days)
    hourly_perf = get_hourly_performance(days)
    current_params = get_current_env_params()

    # Detect patterns
    patterns = detect_patterns(
        stats, score_perf, peak_analysis, duration_perf,
        symbol_perf, direction_perf, close_reasons, hourly_perf
    )

    # Generate recommendations
    recommendations = generate_recommendations(
        patterns, stats, score_perf, peak_analysis,
        duration_perf, symbol_perf, current_params
    )

    # Build insights
    insights = []

    # Win rate change
    if prev_stats["total"] > 0:
        wr_change = stats["win_rate"] - prev_stats["win_rate"]
        if wr_change > 5:
            insights.append(f"Win Rate migliorato: +{wr_change:.1f}% vs periodo precedente")
        elif wr_change < -5:
            insights.append(f"Win Rate peggiorato: {wr_change:.1f}% vs periodo precedente")

    # Best/worst hours
    if hourly_perf:
        best_hour = max(hourly_perf, key=lambda x: x["win_rate"])
        worst_hour = min(hourly_perf, key=lambda x: x["win_rate"])
        if best_hour["win_rate"] - worst_hour["win_rate"] > 20:
            insights.append(f"Ore migliori: {best_hour['hour']}:00 ({best_hour['win_rate']}% WR)")
            insights.append(f"Ore peggiori: {worst_hour['hour']}:00 ({worst_hour['win_rate']}% WR)")

    # R/R ratio
    if stats["avg_win"] and stats["avg_loss"] and stats["avg_loss"] != 0:
        rr = abs(stats["avg_win"] / stats["avg_loss"])
        breakeven_wr = 100 / (1 + rr)
        insights.append(f"R/R Ratio: {rr:.2f} (breakeven a {breakeven_wr:.1f}% WR)")

    return LearningReport(
        generated_at=datetime.now().isoformat(),
        period_days=days,
        total_trades=stats["total"],
        winning_trades=stats["wins"],
        losing_trades=stats["losses"],
        win_rate=stats["win_rate"],
        total_pnl=stats["total_pnl"],
        avg_trade_pnl=stats["avg_pnl"],
        prev_period_win_rate=prev_stats["win_rate"] if prev_stats["total"] > 0 else None,
        win_rate_change=stats["win_rate"] - prev_stats["win_rate"] if prev_stats["total"] > 0 else None,
        patterns=patterns,
        recommendations=recommendations,
        insights=insights
    )


def print_report(report: LearningReport):
    """Stampa il report in formato leggibile."""
    print()
    print("=" * 70)
    print(f"   TRADE LEARNING REPORT - Ultimi {report.period_days} giorni")
    print(f"   Generato: {report.generated_at[:19]}")
    print("=" * 70)

    # Summary
    print(f"""
   PERFORMANCE SUMMARY
   {"─" * 50}
   Trade Totali:  {report.total_trades}
   Vincenti:      {report.winning_trades} ({report.win_rate}%)
   Perdenti:      {report.losing_trades}
   P&L Totale:    ${report.total_pnl:.2f}
   P&L Medio:     ${report.avg_trade_pnl:.4f}
""")

    if report.prev_period_win_rate is not None:
        change_emoji = "" if report.win_rate_change >= 0 else ""
        print(f"   vs Periodo Precedente: {change_emoji} {report.win_rate_change:+.1f}% WR")

    # Patterns
    if report.patterns:
        print(f"""
   PATTERN IDENTIFICATI
   {"─" * 50}""")
        for p in report.patterns:
            severity_emoji = {"critical": "", "warning": "", "info": ""}[p.severity]
            print(f"\n   {severity_emoji} {p.name}")
            print(f"      {p.description}")
            print(f"      Evidenza: {p.evidence}")

    # Recommendations
    if report.recommendations:
        print(f"""

   RACCOMANDAZIONI
   {"─" * 50}""")
        for i, r in enumerate(report.recommendations, 1):
            impact_emoji = {"high": "", "medium": "", "low": ""}[r.impact]
            print(f"""
   {i}. {r.parameter} {impact_emoji}
      Attuale:    {r.current_value}
      Suggerito:  {r.suggested_value}
      Motivo:     {r.reason}
      Confidence: {r.confidence}%""")

    # Insights
    if report.insights:
        print(f"""

   INSIGHTS
   {"─" * 50}""")
        for insight in report.insights:
            print(f"    {insight}")

    # Footer
    print(f"""

{"=" * 70}
   Per applicare le modifiche, aggiorna il file .env sul VPS
{"=" * 70}
""")


def send_to_telegram(report: LearningReport):
    """Invia il report su Telegram."""
    try:
        from telegram_notifier import send_telegram_message

        # Costruisci messaggio compatto
        msg = f"""*TRADE LEARNING REPORT*
Ultimi {report.period_days} giorni

*Performance*
Trade: {report.total_trades} | WR: {report.win_rate}%
P&L: ${report.total_pnl:.2f}
"""

        if report.win_rate_change is not None:
            emoji = "" if report.win_rate_change >= 0 else ""
            msg += f"vs Precedente: {emoji} {report.win_rate_change:+.1f}%\n"

        if report.patterns:
            msg += "\n*Pattern:*\n"
            for p in report.patterns[:3]:  # Max 3
                emoji = {"critical": "", "warning": "", "info": ""}[p.severity]
                msg += f"{emoji} {p.name}\n"

        if report.recommendations:
            msg += "\n*Top Raccomandazioni:*\n"
            for r in report.recommendations[:3]:  # Max 3
                msg += f" {r.parameter}: {r.suggested_value}\n"

        send_telegram_message(msg)
        print("   Report inviato su Telegram")
    except Exception as e:
        print(f"   Errore Telegram: {e}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trade Learning Report")
    parser.add_argument("days", nargs="?", type=int, default=7, help="Giorni da analizzare (default: 7)")
    parser.add_argument("--telegram", action="store_true", help="Invia su Telegram")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        report = generate_report(args.days)

        if args.json:
            # Output JSON
            output = {
                "generated_at": report.generated_at,
                "period_days": report.period_days,
                "summary": {
                    "total_trades": report.total_trades,
                    "win_rate": report.win_rate,
                    "total_pnl": report.total_pnl
                },
                "patterns": [asdict(p) for p in report.patterns],
                "recommendations": [asdict(r) for r in report.recommendations],
                "insights": report.insights
            }
            print(json.dumps(output, indent=2))
        else:
            print_report(report)

        if args.telegram:
            send_to_telegram(report)

    except Exception as e:
        print(f" Errore: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
