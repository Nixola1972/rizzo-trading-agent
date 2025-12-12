#!/usr/bin/env python3
"""
Trade Analyzer - Analisi intelligente dei trades con AI.

Raccoglie metriche complete dal Trade Journal e le invia all'AI per:
1. Identificare pattern problematici
2. Analizzare correlazione score/risultati
3. Suggerire modifiche parametri specifiche

Usa la stessa configurazione AI presente nel .env
"""

import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# AI Configuration (stessa del trading_agent.py)
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai').lower()

if AI_PROVIDER == 'openai':
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
elif AI_PROVIDER == 'openrouter':
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv('OPENROUTER_API_KEY')
    )
    MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
else:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')


def get_db_connection():
    """Get database connection."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(dsn)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder for Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# =====================
# Metrics Collection
# =====================

def get_trades_summary(days: int = 30) -> dict:
    """Get overall trades summary."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE profitable = true) as winning_trades,
                    COUNT(*) FILTER (WHERE profitable = false) as losing_trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(SUM(pnl_usd)::numeric, 2) as gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_pnl_percent,
                    ROUND(AVG(duration_seconds / 60.0)::numeric, 1) as avg_duration_min
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            return dict(cur.fetchone() or {})


def get_close_reason_analysis(days: int = 30) -> List[dict]:
    """Analyze performance by close reason."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    close_reason,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_pnl_percent,
                    ROUND(AVG(net_pnl_usd)::numeric, 2) as avg_net_pnl,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    ROUND(AVG(duration_seconds / 60.0)::numeric, 1) as avg_duration_min
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY close_reason
                ORDER BY count DESC
            """, (days,))
            return [dict(row) for row in cur.fetchall()]


def get_symbol_analysis(days: int = 30) -> List[dict]:
    """Analyze performance by symbol."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as total_trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(AVG(net_pnl_percent)::numeric, 2) as avg_net_pnl_percent,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    -- Close reason breakdown
                    COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') as sl_hit_count,
                    COUNT(*) FILTER (WHERE close_reason = 'TP_HIT') as tp_hit_count,
                    COUNT(*) FILTER (WHERE close_reason = 'TRAILING_SL') as trailing_count,
                    COUNT(*) FILTER (WHERE close_reason = 'REVERSAL') as reversal_count,
                    -- Percentages
                    ROUND(100.0 * COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') / NULLIF(COUNT(*), 0), 1) as sl_hit_pct
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY symbol
                ORDER BY total_trades DESC
            """, (days,))
            return [dict(row) for row in cur.fetchall()]


def get_trading_mode_analysis(days: int = 30) -> List[dict]:
    """Analyze performance by trading mode."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    trading_mode,
                    COUNT(*) as total_trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_pnl_percent,
                    ROUND(AVG(net_pnl_percent)::numeric, 2) as avg_net_pnl_percent,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    ROUND(AVG(duration_seconds / 60.0)::numeric, 1) as avg_duration_min,
                    ROUND(AVG(fee_total)::numeric, 2) as avg_fee
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY trading_mode
            """, (days,))
            return [dict(row) for row in cur.fetchall()]


def get_score_correlation_analysis(days: int = 30) -> dict:
    """
    Analizza la correlazione tra score di apertura e risultati.
    Risponde alla domanda: score più alto = risultati migliori?
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Analisi per range di score
            cur.execute("""
                SELECT
                    CASE
                        WHEN ABS(open_score) < 15 THEN '< 15 (debole)'
                        WHEN ABS(open_score) BETWEEN 15 AND 17.99 THEN '15-18 (medio)'
                        WHEN ABS(open_score) BETWEEN 18 AND 21.99 THEN '18-22 (buono)'
                        WHEN ABS(open_score) >= 22 THEN '22+ (forte)'
                    END as score_range,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(AVG(net_pnl_percent)::numeric, 2) as avg_net_pnl_percent,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_net_pnl,
                    ROUND(AVG(ABS(open_score))::numeric, 1) as avg_score
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND open_score IS NOT NULL
                GROUP BY score_range
                ORDER BY avg_score
            """, (days,))
            by_score_range = [dict(row) for row in cur.fetchall()]

            # Correlazione per trading mode
            cur.execute("""
                SELECT
                    trading_mode,
                    CASE
                        WHEN ABS(open_score) < 18 THEN 'basso (< 18)'
                        WHEN ABS(open_score) >= 18 AND ABS(open_score) < 22 THEN 'medio (18-22)'
                        ELSE 'alto (22+)'
                    END as score_level,
                    COUNT(*) as trades,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE profitable = true) / NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(AVG(net_pnl_percent)::numeric, 2) as avg_net_pnl_percent
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND open_score IS NOT NULL
                GROUP BY trading_mode, score_level
                ORDER BY trading_mode, avg_net_pnl_percent DESC
            """, (days,))
            by_mode_and_score = [dict(row) for row in cur.fetchall()]

            # Statistiche correlazione
            cur.execute("""
                SELECT
                    CORR(ABS(open_score), net_pnl_percent) as score_pnl_correlation,
                    CORR(ABS(open_score), CASE WHEN profitable THEN 1 ELSE 0 END) as score_win_correlation
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                  AND open_score IS NOT NULL
            """, (days,))
            correlation_stats = dict(cur.fetchone() or {})

            return {
                "by_score_range": by_score_range,
                "by_mode_and_score": by_mode_and_score,
                "correlation": {
                    "score_vs_pnl": round(float(correlation_stats.get('score_pnl_correlation') or 0), 3),
                    "score_vs_win": round(float(correlation_stats.get('score_win_correlation') or 0), 3),
                    "interpretation": interpret_correlation(correlation_stats.get('score_pnl_correlation'))
                }
            }


def interpret_correlation(corr) -> str:
    """Interpreta il valore di correlazione."""
    if corr is None:
        return "Dati insufficienti"
    corr = float(corr)
    if corr > 0.7:
        return "Forte correlazione positiva: score alto = risultati migliori"
    elif corr > 0.4:
        return "Moderata correlazione positiva: score aiuta ma non determina tutto"
    elif corr > 0.1:
        return "Debole correlazione: score ha impatto limitato"
    elif corr > -0.1:
        return "Nessuna correlazione: score non predice i risultati"
    elif corr > -0.4:
        return "Debole correlazione negativa: score alto tende a risultati peggiori (!)"
    else:
        return "Correlazione negativa: c'è un problema con il calcolo dello score"


def get_fee_impact_analysis(days: int = 30) -> dict:
    """Analyze fee impact on profitability."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    ROUND(SUM(pnl_usd)::numeric, 2) as gross_pnl,
                    ROUND(SUM(fee_total)::numeric, 2) as total_fees,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl,
                    ROUND(100.0 * SUM(fee_total) / NULLIF(ABS(SUM(pnl_usd)), 0), 1) as fees_pct_of_gross,
                    COUNT(*) FILTER (WHERE pnl_usd > 0 AND net_pnl_usd <= 0) as profitable_before_fees_only,
                    ROUND(AVG(fee_total)::numeric, 4) as avg_fee_per_trade,
                    ROUND(AVG(margin_used)::numeric, 2) as avg_margin,
                    ROUND(100.0 * AVG(fee_total / NULLIF(margin_used, 0)), 3) as avg_fee_pct_of_margin
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            return dict(cur.fetchone() or {})


def get_recent_trades_detail(days: int = 30, limit: int = 20) -> List[dict]:
    """Get recent trades with full details for AI analysis."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    symbol,
                    direction,
                    trading_mode,
                    opened_at,
                    closed_at,
                    duration_seconds / 60.0 as duration_min,
                    entry_price,
                    exit_price,
                    leverage,
                    open_score,
                    close_score,
                    pnl_percent,
                    net_pnl_usd,
                    fee_total,
                    close_reason,
                    profitable
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                ORDER BY closed_at DESC
                LIMIT %s
            """, (days, limit))
            return [dict(row) for row in cur.fetchall()]


def get_sl_analysis(days: int = 30) -> dict:
    """Analyze SL hit patterns."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # SL hits by symbol
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') as sl_hits,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') / NULLIF(COUNT(*), 0), 1) as sl_hit_rate,
                    ROUND(AVG(CASE WHEN close_reason = 'SL_HIT' THEN net_pnl_usd END)::numeric, 2) as avg_sl_loss,
                    ROUND(AVG(CASE WHEN close_reason = 'SL_HIT' THEN duration_seconds / 60.0 END)::numeric, 1) as avg_sl_duration_min
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY symbol
                HAVING COUNT(*) >= 3
            """, (days,))
            by_symbol = [dict(row) for row in cur.fetchall()]

            # SL hits by trading mode
            cur.execute("""
                SELECT
                    trading_mode,
                    sl_percent_config,
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') as sl_hits,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE close_reason = 'SL_HIT') / NULLIF(COUNT(*), 0), 1) as sl_hit_rate
                FROM trades
                WHERE status = 'CLOSED'
                  AND closed_at >= NOW() - INTERVAL '%s days'
                GROUP BY trading_mode, sl_percent_config
            """, (days,))
            by_mode = [dict(row) for row in cur.fetchall()]

            return {
                "by_symbol": by_symbol,
                "by_mode": by_mode
            }


# =====================
# AI Analysis
# =====================

def collect_all_metrics(days: int = 30) -> dict:
    """Collect all metrics for AI analysis."""
    return {
        "period_days": days,
        "collected_at": datetime.now().isoformat(),
        "summary": get_trades_summary(days),
        "by_close_reason": get_close_reason_analysis(days),
        "by_symbol": get_symbol_analysis(days),
        "by_trading_mode": get_trading_mode_analysis(days),
        "score_correlation": get_score_correlation_analysis(days),
        "fee_impact": get_fee_impact_analysis(days),
        "sl_analysis": get_sl_analysis(days),
        "recent_trades": get_recent_trades_detail(days, limit=15)
    }


def analyze_with_ai(days: int = 30) -> str:
    """
    Collect metrics and send to AI for analysis.
    Returns AI analysis as text.
    """
    # Collect all metrics
    metrics = collect_all_metrics(days)

    # Check if we have enough data
    if not metrics["summary"] or metrics["summary"].get("total_trades", 0) == 0:
        return "❌ Dati insufficienti per l'analisi. Servono trade chiusi nel periodo selezionato."

    # Prepare prompt
    metrics_json = json.dumps(metrics, cls=DecimalEncoder, indent=2)

    prompt = f"""Sei un analista esperto di trading algoritmico. Analizza questi dati di trading degli ultimi {days} giorni e fornisci insights actionable.

DATI TRADING:
{metrics_json}

ANALISI RICHIESTA:

1. **OVERVIEW GENERALE**
   - Riassumi la performance complessiva
   - Identifica i punti di forza e debolezza

2. **ANALISI CORRELAZIONE SCORE**
   - Lo score di apertura predice effettivamente i risultati?
   - Score più alto porta a trade migliori? Quantifica.
   - Suggerisci se le soglie attuali sono corrette

3. **ANALISI PER CLOSE REASON**
   - Quale metodo di chiusura funziona meglio?
   - I REVERSAL chiudono troppo presto o al momento giusto?
   - Gli SL sono troppo stretti o corretti?

4. **ANALISI PER SYMBOL**
   - Quale asset performa meglio/peggio?
   - Ci sono asset che richiedono parametri diversi?

5. **ANALISI TRADING MODE**
   - MICRO_GAIN vs NORMAL: quale funziona meglio?
   - I parametri attuali sono ottimali?

6. **IMPATTO FEES**
   - Le fees stanno mangiando i profitti?
   - Suggerimenti per ridurre l'impatto

7. **SUGGERIMENTI SPECIFICI**
   Per ogni problema identificato, suggerisci:
   - Quale parametro modificare (nome esatto)
   - Valore attuale vs valore suggerito
   - Impatto stimato

Usa emoji per evidenziare i punti chiave. Sii specifico con i numeri.
Non fare assunzioni - basa tutto sui dati forniti."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un analista di trading quantitativo. Fornisci analisi dettagliate e suggerimenti specifici basati sui dati."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=4000,
            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"❌ Errore chiamata AI: {str(e)}"


def get_quick_insights(days: int = 30) -> List[str]:
    """
    Generate quick insights without AI (rule-based).
    For dashboard display.
    """
    insights = []

    try:
        summary = get_trades_summary(days)
        if not summary or summary.get("total_trades", 0) == 0:
            return ["Dati insufficienti per generare insights"]

        # Win rate check
        win_rate = summary.get("win_rate")
        if win_rate and float(win_rate) < 50:
            insights.append(f"⚠️ Win rate basso: {win_rate}% - Sotto il 50%")
        elif win_rate and float(win_rate) > 65:
            insights.append(f"✅ Win rate buono: {win_rate}%")

        # Fee impact
        fee_analysis = get_fee_impact_analysis(days)
        if fee_analysis:
            fees_pct = fee_analysis.get("fees_pct_of_gross")
            if fees_pct and float(fees_pct) > 30:
                insights.append(f"⚠️ Fees elevate: {fees_pct}% del P&L lordo")

            eaten = fee_analysis.get("profitable_before_fees_only", 0)
            if eaten and int(eaten) > 0:
                insights.append(f"⚠️ {eaten} trade erano profit ma fees li hanno azzerati")

        # Score correlation
        score_analysis = get_score_correlation_analysis(days)
        if score_analysis and score_analysis.get("correlation"):
            corr = score_analysis["correlation"].get("score_vs_pnl", 0)
            if corr < 0.1:
                insights.append("⚠️ Score non correla con i risultati - verificare calcolo")
            elif corr > 0.5:
                insights.append(f"✅ Buona correlazione score/risultati: {corr:.2f}")

        # SL analysis
        sl_analysis = get_sl_analysis(days)
        if sl_analysis and sl_analysis.get("by_symbol"):
            for row in sl_analysis["by_symbol"]:
                if row.get("sl_hit_rate") and float(row["sl_hit_rate"]) > 35:
                    insights.append(f"⚠️ {row['symbol']}: SL hit rate alto ({row['sl_hit_rate']}%) - considera allargare SL")

        # Close reason analysis
        close_analysis = get_close_reason_analysis(days)
        for row in close_analysis:
            if row.get("close_reason") == "REVERSAL":
                if row.get("win_rate") and float(row["win_rate"]) < 45:
                    insights.append(f"⚠️ REVERSAL win rate basso ({row['win_rate']}%) - score threshold troppo basso?")

        if not insights:
            insights.append("✅ Sistema nella norma, nessun problema evidente")

    except Exception as e:
        insights.append(f"Errore generazione insights: {str(e)}")

    return insights


# =====================
# Main
# =====================

if __name__ == "__main__":
    import sys

    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except:
            pass

    print(f"🔍 Raccolta metriche ultimi {days} giorni...")
    print()

    # Quick insights
    print("=" * 60)
    print("📊 QUICK INSIGHTS (rule-based)")
    print("=" * 60)
    for insight in get_quick_insights(days):
        print(f"  {insight}")
    print()

    # Ask if user wants full AI analysis
    print("Vuoi l'analisi completa con AI? (s/n): ", end="")
    try:
        answer = input().strip().lower()
        if answer in ['s', 'si', 'yes', 'y']:
            print()
            print("=" * 60)
            print("🤖 ANALISI AI")
            print("=" * 60)
            print()
            analysis = analyze_with_ai(days)
            print(analysis)
    except:
        pass
