#!/usr/bin/env python3
"""
Analisi Approfondita Trade per Ottimizzazione Parametri

Esegui con: python analyze_trades.py

Questo script analizza tutti i dati disponibili nel database per trovare
i parametri ottimali e identificare i pattern di perdita/guadagno.
"""

import sys
sys.path.insert(0, '.')

import db_utils
from datetime import datetime, timedelta
from decimal import Decimal


def analyze_trades():
    """Analisi completa dei trade per ottimizzazione."""

    print("=" * 80)
    print("📊 ANALISI COMPLETA TRADE PER OTTIMIZZAZIONE")
    print("=" * 80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:

            # ========================================
            # 1. OVERVIEW GENERALE
            # ========================================
            print("\n" + "=" * 80)
            print("1️⃣  OVERVIEW GENERALE")
            print("=" * 80)

            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) as closed,
                    COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    COUNT(CASE WHEN profitable = false THEN 1 END) as losses,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(CASE WHEN status = 'CLOSED' THEN 1 END), 0), 2) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(CASE WHEN profitable = true THEN net_pnl_usd END)::numeric, 4) as avg_win,
                    ROUND(AVG(CASE WHEN profitable = false THEN net_pnl_usd END)::numeric, 4) as avg_loss,
                    ROUND(AVG(duration_seconds/60.0)::numeric, 1) as avg_duration_min
                FROM trades
            """)
            row = cur.fetchone()
            print(f"Trade Totali: {row[0]} ({row[1]} chiusi, {row[2]} aperti)")
            print(f"Win/Loss: {row[3]} / {row[4]} (Win Rate: {row[5]}%)")
            print(f"P&L Totale: ${row[6]}")
            print(f"Media Win: ${row[7]} | Media Loss: ${row[8]}")
            if row[7] and row[8]:
                rr = abs(float(row[7]) / float(row[8])) if row[8] != 0 else 0
                print(f"R/R Ratio: {rr:.2f}")
            print(f"Durata Media: {row[9]} minuti")

            # ========================================
            # 2. ANALISI PER CLOSE REASON
            # ========================================
            print("\n" + "=" * 80)
            print("2️⃣  ANALISI PER CLOSE REASON (dove perdi/guadagni)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    close_reason,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(net_pnl_usd)::numeric, 4) as avg_pnl,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak_pnl
                FROM trades
                WHERE status = 'CLOSED'
                GROUP BY close_reason
                ORDER BY count DESC
            """)
            print(f"\n{'Reason':<20} {'Count':>6} {'%':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg P&L':>10} {'Avg Peak':>8}")
            print("-" * 80)
            for row in cur.fetchall():
                reason = row[0] or 'UNKNOWN'
                print(f"{reason:<20} {row[1]:>6} {row[2]:>6} {row[3]:>6} {row[4]:>6} ${row[5]:>9} ${row[6]:>9} {row[7]:>7}%")

            # ========================================
            # 3. ANALISI PEAK P&L (quanto profit lasci sul tavolo)
            # ========================================
            print("\n" + "=" * 80)
            print("3️⃣  ANALISI PEAK P&L (profit lasciato sul tavolo)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    CASE
                        WHEN peak_pnl_percent < 0.5 THEN '< 0.5%'
                        WHEN peak_pnl_percent < 1.0 THEN '0.5-1%'
                        WHEN peak_pnl_percent < 1.5 THEN '1-1.5%'
                        WHEN peak_pnl_percent < 2.0 THEN '1.5-2%'
                        WHEN peak_pnl_percent < 3.0 THEN '2-3%'
                        WHEN peak_pnl_percent < 4.0 THEN '3-4%'
                        ELSE '4%+'
                    END as peak_range,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit_pnl,
                    ROUND(AVG(peak_pnl_percent - COALESCE(pnl_percent, 0))::numeric, 2) as avg_left_on_table,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins
                FROM trades
                WHERE status = 'CLOSED' AND peak_pnl_percent IS NOT NULL
                GROUP BY
                    CASE
                        WHEN peak_pnl_percent < 0.5 THEN '< 0.5%'
                        WHEN peak_pnl_percent < 1.0 THEN '0.5-1%'
                        WHEN peak_pnl_percent < 1.5 THEN '1-1.5%'
                        WHEN peak_pnl_percent < 2.0 THEN '1.5-2%'
                        WHEN peak_pnl_percent < 3.0 THEN '2-3%'
                        WHEN peak_pnl_percent < 4.0 THEN '3-4%'
                        ELSE '4%+'
                    END,
                    CASE
                        WHEN peak_pnl_percent < 0.5 THEN 1
                        WHEN peak_pnl_percent < 1.0 THEN 2
                        WHEN peak_pnl_percent < 1.5 THEN 3
                        WHEN peak_pnl_percent < 2.0 THEN 4
                        WHEN peak_pnl_percent < 3.0 THEN 5
                        WHEN peak_pnl_percent < 4.0 THEN 6
                        ELSE 7
                    END
                ORDER BY
                    CASE
                        WHEN peak_pnl_percent < 0.5 THEN 1
                        WHEN peak_pnl_percent < 1.0 THEN 2
                        WHEN peak_pnl_percent < 1.5 THEN 3
                        WHEN peak_pnl_percent < 2.0 THEN 4
                        WHEN peak_pnl_percent < 3.0 THEN 5
                        WHEN peak_pnl_percent < 4.0 THEN 6
                        ELSE 7
                    END
            """)
            print(f"\n{'Peak Range':<12} {'Count':>6} {'%':>6} {'Exit P&L':>10} {'Left on Table':>14} {'Wins':>6}")
            print("-" * 60)
            for row in cur.fetchall():
                print(f"{row[0]:<12} {row[1]:>6} {row[2]:>6} {row[3]:>9}% {row[4]:>13}% {row[5]:>6}")

            # ========================================
            # 4. ANALISI PER SYMBOL
            # ========================================
            print("\n" + "=" * 80)
            print("4️⃣  ANALISI PER SYMBOL")
            print("=" * 80)

            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as count,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(CASE WHEN profitable = true THEN net_pnl_usd END)::numeric, 4) as avg_win,
                    ROUND(AVG(CASE WHEN profitable = false THEN net_pnl_usd END)::numeric, 4) as avg_loss
                FROM trades
                WHERE status = 'CLOSED'
                GROUP BY symbol
                ORDER BY total_pnl DESC
            """)
            print(f"\n{'Symbol':<8} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg Win':>10} {'Avg Loss':>10}")
            print("-" * 70)
            for row in cur.fetchall():
                print(f"{row[0]:<8} {row[1]:>6} {row[2]:>6} {row[3]:>6} ${row[4]:>9} ${row[5]:>9} ${row[6]:>9}")

            # ========================================
            # 5. ANALISI PER DIRECTION (LONG vs SHORT)
            # ========================================
            print("\n" + "=" * 80)
            print("5️⃣  ANALISI PER DIRECTION (LONG vs SHORT)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    direction,
                    COUNT(*) as count,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(net_pnl_usd)::numeric, 4) as avg_pnl
                FROM trades
                WHERE status = 'CLOSED'
                GROUP BY direction
                ORDER BY direction
            """)
            print(f"\n{'Direction':<8} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg P&L':>10}")
            print("-" * 50)
            for row in cur.fetchall():
                print(f"{row[0]:<8} {row[1]:>6} {row[2]:>6} {row[3]:>6} ${row[4]:>9} ${row[5]:>9}")

            # ========================================
            # 6. ANALISI PER ORA DEL GIORNO
            # ========================================
            print("\n" + "=" * 80)
            print("6️⃣  ANALISI PER ORA DEL GIORNO (UTC)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    EXTRACT(HOUR FROM opened_at) as hour,
                    COUNT(*) as count,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                GROUP BY EXTRACT(HOUR FROM opened_at)
                ORDER BY hour
            """)
            print(f"\n{'Ora':<6} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10}")
            print("-" * 40)
            for row in cur.fetchall():
                hour = int(row[0])
                print(f"{hour:02d}:00  {row[1]:>6} {row[2]:>6} {row[3]:>6} ${row[4]:>9}")

            # ========================================
            # 7. ANALISI DURATA TRADE
            # ========================================
            print("\n" + "=" * 80)
            print("7️⃣  ANALISI DURATA TRADE")
            print("=" * 80)

            cur.execute("""
                SELECT
                    CASE
                        WHEN duration_seconds < 300 THEN '< 5 min'
                        WHEN duration_seconds < 900 THEN '5-15 min'
                        WHEN duration_seconds < 1800 THEN '15-30 min'
                        WHEN duration_seconds < 3600 THEN '30-60 min'
                        WHEN duration_seconds < 7200 THEN '1-2 ore'
                        ELSE '2+ ore'
                    END as duration_range,
                    COUNT(*) as count,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak
                FROM trades
                WHERE status = 'CLOSED' AND duration_seconds IS NOT NULL
                GROUP BY
                    CASE
                        WHEN duration_seconds < 300 THEN '< 5 min'
                        WHEN duration_seconds < 900 THEN '5-15 min'
                        WHEN duration_seconds < 1800 THEN '15-30 min'
                        WHEN duration_seconds < 3600 THEN '30-60 min'
                        WHEN duration_seconds < 7200 THEN '1-2 ore'
                        ELSE '2+ ore'
                    END,
                    CASE
                        WHEN duration_seconds < 300 THEN 1
                        WHEN duration_seconds < 900 THEN 2
                        WHEN duration_seconds < 1800 THEN 3
                        WHEN duration_seconds < 3600 THEN 4
                        WHEN duration_seconds < 7200 THEN 5
                        ELSE 6
                    END
                ORDER BY
                    CASE
                        WHEN duration_seconds < 300 THEN 1
                        WHEN duration_seconds < 900 THEN 2
                        WHEN duration_seconds < 1800 THEN 3
                        WHEN duration_seconds < 3600 THEN 4
                        WHEN duration_seconds < 7200 THEN 5
                        ELSE 6
                    END
            """)
            print(f"\n{'Durata':<12} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg Peak':>10}")
            print("-" * 55)
            for row in cur.fetchall():
                print(f"{row[0]:<12} {row[1]:>6} {row[2]:>6} {row[3]:>6} ${row[4]:>9} {row[5]:>9}%")

            # ========================================
            # 8. TRAILING STOP ANALYSIS
            # ========================================
            print("\n" + "=" * 80)
            print("8️⃣  TRAILING STOP ANALYSIS")
            print("=" * 80)

            cur.execute("""
                SELECT
                    close_reason,
                    COUNT(*) as count,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit,
                    ROUND(AVG(peak_pnl_percent - COALESCE(pnl_percent, 0))::numeric, 2) as avg_slippage,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND close_reason IN ('TP_HIT', 'TRAILING_SL', 'SL_HIT')
                GROUP BY close_reason
                ORDER BY close_reason
            """)
            print(f"\n{'Reason':<15} {'Count':>6} {'Avg Peak':>10} {'Avg Exit':>10} {'Slippage':>10} {'Tot P&L':>10}")
            print("-" * 65)
            for row in cur.fetchall():
                print(f"{row[0]:<15} {row[1]:>6} {row[2]:>9}% {row[3]:>9}% {row[4]:>9}% ${row[5]:>9}")

            # ========================================
            # 9. SCORE ANALYSIS (a che score entri meglio?)
            # ========================================
            print("\n" + "=" * 80)
            print("9️⃣  SCORE ANALYSIS (a che score entri meglio?)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    CASE
                        WHEN open_score < 10 THEN '< 10'
                        WHEN open_score < 15 THEN '10-15'
                        WHEN open_score < 20 THEN '15-20'
                        WHEN open_score < 25 THEN '20-25'
                        WHEN open_score < 30 THEN '25-30'
                        ELSE '30+'
                    END as score_range,
                    COUNT(*) as count,
                    COUNT(CASE WHEN profitable = true THEN 1 END) as wins,
                    ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) /
                          NULLIF(COUNT(*), 0), 1) as win_rate,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_pnl,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak
                FROM trades
                WHERE status = 'CLOSED' AND open_score IS NOT NULL
                GROUP BY
                    CASE
                        WHEN open_score < 10 THEN '< 10'
                        WHEN open_score < 15 THEN '10-15'
                        WHEN open_score < 20 THEN '15-20'
                        WHEN open_score < 25 THEN '20-25'
                        WHEN open_score < 30 THEN '25-30'
                        ELSE '30+'
                    END,
                    CASE
                        WHEN open_score < 10 THEN 1
                        WHEN open_score < 15 THEN 2
                        WHEN open_score < 20 THEN 3
                        WHEN open_score < 25 THEN 4
                        WHEN open_score < 30 THEN 5
                        ELSE 6
                    END
                ORDER BY
                    CASE
                        WHEN open_score < 10 THEN 1
                        WHEN open_score < 15 THEN 2
                        WHEN open_score < 20 THEN 3
                        WHEN open_score < 25 THEN 4
                        WHEN open_score < 30 THEN 5
                        ELSE 6
                    END
            """)
            print(f"\n{'Score':<10} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg Peak':>10}")
            print("-" * 55)
            for row in cur.fetchall():
                print(f"{row[0]:<10} {row[1]:>6} {row[2]:>6} {row[3]:>6} ${row[4]:>9} {row[5]:>9}%")

            # ========================================
            # 10. WORST TRADES (per capire dove si perde di più)
            # ========================================
            print("\n" + "=" * 80)
            print("🔟 WORST TRADES (ultimi 20)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    symbol,
                    direction,
                    opened_at,
                    ROUND(duration_seconds/60.0) as duration_min,
                    ROUND(open_score::numeric, 1) as score,
                    ROUND(peak_pnl_percent::numeric, 2) as peak_pnl,
                    ROUND(pnl_percent::numeric, 2) as exit_pnl,
                    ROUND(net_pnl_usd::numeric, 2) as net_pnl,
                    close_reason
                FROM trades
                WHERE status = 'CLOSED'
                ORDER BY net_pnl_usd ASC
                LIMIT 20
            """)
            print(f"\n{'Symbol':<6} {'Dir':<6} {'When':<12} {'Min':>5} {'Score':>6} {'Peak':>7} {'Exit':>7} {'Net$':>8} {'Reason':<15}")
            print("-" * 85)
            for row in cur.fetchall():
                when = row[2].strftime("%m/%d %H:%M") if row[2] else "?"
                print(f"{row[0]:<6} {row[1]:<6} {when:<12} {row[3] or 0:>5.0f} {row[4] or 0:>6.1f} {row[5] or 0:>6.2f}% {row[6] or 0:>6.2f}% ${row[7] or 0:>7.2f} {row[8] or 'N/A':<15}")

            # ========================================
            # 11. BEST TRADES
            # ========================================
            print("\n" + "=" * 80)
            print("1️⃣1️⃣ BEST TRADES (ultimi 20)")
            print("=" * 80)

            cur.execute("""
                SELECT
                    symbol,
                    direction,
                    opened_at,
                    ROUND(duration_seconds/60.0) as duration_min,
                    ROUND(open_score::numeric, 1) as score,
                    ROUND(peak_pnl_percent::numeric, 2) as peak_pnl,
                    ROUND(pnl_percent::numeric, 2) as exit_pnl,
                    ROUND(net_pnl_usd::numeric, 2) as net_pnl,
                    close_reason
                FROM trades
                WHERE status = 'CLOSED'
                ORDER BY net_pnl_usd DESC
                LIMIT 20
            """)
            print(f"\n{'Symbol':<6} {'Dir':<6} {'When':<12} {'Min':>5} {'Score':>6} {'Peak':>7} {'Exit':>7} {'Net$':>8} {'Reason':<15}")
            print("-" * 85)
            for row in cur.fetchall():
                when = row[2].strftime("%m/%d %H:%M") if row[2] else "?"
                print(f"{row[0]:<6} {row[1]:<6} {when:<12} {row[3] or 0:>5.0f} {row[4] or 0:>6.1f} {row[5] or 0:>6.2f}% {row[6] or 0:>6.2f}% ${row[7] or 0:>7.2f} {row[8] or 'N/A':<15}")

            # ========================================
            # 12. RACCOMANDAZIONI
            # ========================================
            print("\n" + "=" * 80)
            print("💡 RACCOMANDAZIONI BASATE SUI DATI")
            print("=" * 80)

            # Calcola alcune metriche chiave
            cur.execute("""
                SELECT
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY peak_pnl_percent)::numeric, 2) as median_peak,
                    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY peak_pnl_percent)::numeric, 2) as p75_peak,
                    ROUND(AVG(CASE WHEN close_reason = 'SL_HIT' THEN pnl_percent END)::numeric, 2) as avg_sl_exit,
                    ROUND(AVG(CASE WHEN close_reason = 'TP_HIT' THEN pnl_percent END)::numeric, 2) as avg_tp_exit
                FROM trades
                WHERE status = 'CLOSED' AND peak_pnl_percent IS NOT NULL
            """)
            metrics = cur.fetchone()

            print(f"""
📈 Analisi Peak P&L:
   - Media Peak: {metrics[0]}%
   - Mediana Peak: {metrics[1]}%
   - 75° Percentile Peak: {metrics[2]}%

📉 Uscite attuali:
   - Media uscita SL: {metrics[3]}%
   - Media uscita TP: {metrics[4]}%

💡 SUGGERIMENTI:
""")

            if metrics[1] and float(metrics[1]) < 1.5:
                print("   ⚠️ La MEDIANA del peak è bassa (<1.5%). Considera:")
                print("      - Ridurre MICRO_GAIN_TARGET_PERCENT a 1.0-1.5%")
                print("      - I trade non raggiungono spesso il target attuale")

            if metrics[0] and metrics[2]:
                suggested_tp = float(metrics[1]) * 0.8  # 80% della mediana
                print(f"\n   📊 TP Suggerito basato sui dati: {suggested_tp:.1f}%")
                print(f"      (80% della mediana peak = più trade in profitto)")

            # Controlla R/R ratio
            cur.execute("""
                SELECT
                    ROUND(AVG(CASE WHEN profitable = true THEN net_pnl_usd END)::numeric, 4) as avg_win,
                    ROUND(AVG(CASE WHEN profitable = false THEN net_pnl_usd END)::numeric, 4) as avg_loss
                FROM trades WHERE status = 'CLOSED'
            """)
            rr_row = cur.fetchone()
            if rr_row[0] and rr_row[1]:
                rr = abs(float(rr_row[0]) / float(rr_row[1]))
                breakeven_wr = 100 / (1 + rr)
                cur.execute("SELECT ROUND(100.0 * COUNT(CASE WHEN profitable = true THEN 1 END) / COUNT(*)::numeric, 1) FROM trades WHERE status = 'CLOSED'")
                actual_wr = float(cur.fetchone()[0])

                print(f"\n   📐 Risk/Reward Analysis:")
                print(f"      - R/R Ratio attuale: {rr:.2f}")
                print(f"      - Win Rate necessario per breakeven: {breakeven_wr:.1f}%")
                print(f"      - Win Rate attuale: {actual_wr:.1f}%")

                if actual_wr < breakeven_wr:
                    gap = breakeven_wr - actual_wr
                    print(f"\n   ❌ Sei SOTTO il breakeven di {gap:.1f}%!")
                    print("      Opzioni:")
                    print("      1. Aumentare Win Rate (entry più selettivi)")
                    print("      2. Aumentare R/R (TP più alto o SL più stretto)")
                else:
                    print(f"\n   ✅ Sei SOPRA il breakeven - sistema teoricamente profittevole")

            print("\n" + "=" * 80)
            print("Fine Analisi")
            print("=" * 80)


if __name__ == "__main__":
    analyze_trades()
