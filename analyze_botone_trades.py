#!/usr/bin/env python3
"""
Analisi Trade Botone V6 - Legge dalla tabella botone_trades

Esegui sul server con: python analyze_botone_trades.py
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(".env.baseline")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set in .env.baseline")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def analyze():
    conn = psycopg2.connect(DATABASE_URL)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ========================================
        # 1. OVERVIEW
        # ========================================
        print("\n" + "=" * 100)
        print("📊 ANALISI BOTONE V6 TRADES")
        print("=" * 100)

        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN closed_at IS NOT NULL THEN 1 END) as closed,
                COUNT(CASE WHEN closed_at IS NULL THEN 1 END) as open
            FROM botone_trades
        """)
        overview = cur.fetchone()
        print(f"\n📈 Trade Totali: {overview['total']} ({overview['closed']} chiusi, {overview['open']} aperti)")

        if overview['closed'] == 0:
            print("❌ Nessun trade chiuso trovato")
            return

        # Stats dei chiusi
        cur.execute("""
            SELECT
                COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN pnl_usd <= 0 THEN 1 END) as losses,
                ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
                ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl,
                ROUND(AVG(pnl_usd)::numeric, 4) as avg_pnl,
                ROUND(AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END)::numeric, 4) as avg_win,
                ROUND(AVG(CASE WHEN pnl_usd <= 0 THEN pnl_usd END)::numeric, 4) as avg_loss,
                ROUND(AVG(duration_seconds/60.0)::numeric, 1) as avg_duration_min
            FROM botone_trades
            WHERE closed_at IS NOT NULL
        """)
        stats = cur.fetchone()
        print(f"   Wins/Losses: {stats['wins']}/{stats['losses']} (Win Rate: {stats['win_rate']}%)")
        print(f"   P&L Totale: ${stats['total_pnl']}")
        print(f"   Avg Win: ${stats['avg_win']} | Avg Loss: ${stats['avg_loss']}")
        if stats['avg_win'] and stats['avg_loss']:
            rr = abs(float(stats['avg_win']) / float(stats['avg_loss']))
            print(f"   R/R Ratio: {rr:.2f}")
        print(f"   Durata Media: {stats['avg_duration_min']} min")

        # ========================================
        # 2. DETTAGLIO ULTIMI TRADE (più recenti)
        # ========================================
        print("\n" + "=" * 100)
        print("📋 ULTIMI 15 TRADE CHIUSI (più recenti prima)")
        print("=" * 100)

        cur.execute("""
            SELECT * FROM botone_trades
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 15
        """)
        trades = cur.fetchall()

        for t in trades:
            pnl = float(t['pnl_usd'] or 0)
            pnl_pct = float(t['pnl_pct'] or 0)
            mfe = float(t['mfe_pct'] or 0)
            mae = float(t['mae_pct'] or 0)
            duration_min = (t['duration_seconds'] or 0) / 60
            emoji = "✅" if pnl > 0 else "❌"

            print(f"\n{emoji} #{t['id']} {t['symbol']} {t['direction']}")
            print(f"   📅 {t['opened_at'].strftime('%m/%d %H:%M')} → {t['closed_at'].strftime('%H:%M')} ({duration_min:.0f} min)")
            print(f"   💰 Entry ${float(t['entry_price']):,.2f} → Exit ${float(t['exit_price'] or 0):,.2f}")
            print(f"   📊 P&L: ${pnl:.2f} ({pnl_pct:+.2f}%) | Size ${t['size_usd']} @ {t['leverage']}x")
            print(f"   📈 MFE: {mfe:+.2f}% | 📉 MAE: {mae:+.2f}%")

            # Problemi rilevati
            if pnl < 0 and mfe > 1.0:
                print(f"   ⚠️ PROFITTO PERSO: era a +{mfe:.2f}% poi chiuso in perdita!")
            if pnl < 0 and mae < -2.0:
                print(f"   ⚠️ DRAWDOWN ECCESSIVO: {mae:.2f}% prima della chiusura")

            # Entry indicators
            print(f"   🔬 Entry: MACD={t['entry_macd']:.4f} RSI={t['entry_rsi']:.1f} ADX={t['entry_adx']:.1f}")
            print(f"      EMA={t['entry_ema_stack']} Vol={t['entry_volume_ratio']:.2f}x BB={t['entry_bb_position']}")
            print(f"      OBV={t['entry_obv_trend']} Funding={float(t['entry_funding_rate'] or 0):.4%}")

            # AI Decision
            print(f"   🤖 AI: Tier={t['conviction_tier']} Conf={float(t['ai_confidence'] or 0):.0%} Style={t['prompt_style']}")
            if t['ai_reasoning']:
                reasoning = t['ai_reasoning'][:150] + "..." if len(t['ai_reasoning']) > 150 else t['ai_reasoning']
                print(f"      {reasoning}")

            # Exit
            print(f"   🚪 Exit: {t['exit_reason']} | SL=${float(t['sl_price'] or 0):,.2f} | Trailing={t['trailing_level_pct']}%")

        # ========================================
        # 3. ANALISI PER EXIT REASON
        # ========================================
        print("\n" + "=" * 100)
        print("📉 ANALISI PER EXIT REASON")
        print("=" * 100)

        cur.execute("""
            SELECT
                exit_reason,
                COUNT(*) as count,
                COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) as wins,
                ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
                ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl,
                ROUND(AVG(pnl_usd)::numeric, 4) as avg_pnl,
                ROUND(AVG(mfe_pct)::numeric, 2) as avg_mfe
            FROM botone_trades
            WHERE closed_at IS NOT NULL
            GROUP BY exit_reason
            ORDER BY count DESC
        """)
        print(f"\n{'Reason':<20} {'Count':>6} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'Avg P&L':>10} {'Avg MFE':>8}")
        print("-" * 80)
        for row in cur.fetchall():
            print(f"{row['exit_reason'] or 'N/A':<20} {row['count']:>6} {row['wins']:>6} {row['win_rate']:>6} ${row['total_pnl']:>9} ${row['avg_pnl']:>9} {row['avg_mfe']:>7}%")

        # ========================================
        # 4. PROFITTI SPRECATI (MFE alto ma chiuso in perdita)
        # ========================================
        print("\n" + "=" * 100)
        print("⚠️ PROFITTI SPRECATI (MFE > 1% ma chiuso in perdita)")
        print("=" * 100)

        cur.execute("""
            SELECT
                id, symbol, direction,
                opened_at, closed_at,
                ROUND(mfe_pct::numeric, 2) as mfe,
                ROUND(pnl_pct::numeric, 2) as exit_pnl,
                ROUND(pnl_usd::numeric, 2) as pnl_usd,
                exit_reason,
                trailing_level_pct
            FROM botone_trades
            WHERE closed_at IS NOT NULL
              AND pnl_usd <= 0
              AND mfe_pct > 1.0
            ORDER BY mfe_pct DESC
            LIMIT 10
        """)
        wasted = cur.fetchall()

        if wasted:
            print(f"\n{'ID':>5} {'Symbol':<6} {'Dir':<6} {'MFE':>7} {'Exit':>7} {'P&L$':>8} {'Trail':>6} {'Reason':<15}")
            print("-" * 75)
            for row in wasted:
                print(f"{row['id']:>5} {row['symbol']:<6} {row['direction']:<6} +{row['mfe']:>5.2f}% {row['exit_pnl']:>6.2f}% ${row['pnl_usd']:>7.2f} {row['trailing_level_pct'] or 0:>5}% {row['exit_reason'] or 'N/A':<15}")
            print(f"\n💡 Questi trade erano in profitto ma hanno chiuso in perdita.")
            print("   Possibili cause: trailing troppo lento, reversal improvviso, SL troppo largo")
        else:
            print("   ✅ Nessun trade con profitto sprecato significativo")

        # ========================================
        # 5. ANALISI QUALITA' ENTRY
        # ========================================
        print("\n" + "=" * 100)
        print("🔬 QUALITA' DEGLI ENTRY")
        print("=" * 100)

        cur.execute("""
            SELECT
                COUNT(CASE WHEN entry_adx < 20 THEN 1 END) as low_adx,
                COUNT(CASE WHEN entry_volume_ratio < 0.5 THEN 1 END) as low_vol,
                COUNT(CASE WHEN entry_ema_stack LIKE '%neutral%' OR entry_ema_stack LIKE '%mixed%' THEN 1 END) as neutral_ema,
                COUNT(CASE WHEN entry_rsi > 70 OR entry_rsi < 30 THEN 1 END) as extreme_rsi,
                COUNT(*) as total
            FROM botone_trades
            WHERE closed_at IS NOT NULL
        """)
        quality = cur.fetchone()
        total = quality['total']

        print(f"\n📊 Su {total} trade chiusi:")
        if quality['low_adx']:
            pct = 100 * quality['low_adx'] / total
            print(f"   ⚠️ {quality['low_adx']} ({pct:.1f}%) con ADX < 20 (mercato senza trend)")
        if quality['low_vol']:
            pct = 100 * quality['low_vol'] / total
            print(f"   ⚠️ {quality['low_vol']} ({pct:.1f}%) con Volume < 0.5x (basso volume)")
        if quality['neutral_ema']:
            pct = 100 * quality['neutral_ema'] / total
            print(f"   ⚠️ {quality['neutral_ema']} ({pct:.1f}%) con EMA neutral/mixed (senza direzione)")
        if quality['extreme_rsi']:
            pct = 100 * quality['extreme_rsi'] / total
            print(f"   ⚠️ {quality['extreme_rsi']} ({pct:.1f}%) con RSI estremo (<30 o >70)")

        # Win rate per ADX
        cur.execute("""
            SELECT
                CASE
                    WHEN entry_adx < 15 THEN 'ADX < 15'
                    WHEN entry_adx < 20 THEN 'ADX 15-20'
                    WHEN entry_adx < 25 THEN 'ADX 20-25'
                    WHEN entry_adx < 30 THEN 'ADX 25-30'
                    ELSE 'ADX 30+'
                END as adx_range,
                COUNT(*) as count,
                ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
                ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl
            FROM botone_trades
            WHERE closed_at IS NOT NULL AND entry_adx IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        """)
        print(f"\n📊 Performance per ADX:")
        print(f"{'ADX Range':<12} {'Count':>6} {'WR%':>6} {'Tot P&L':>10}")
        print("-" * 40)
        for row in cur.fetchall():
            print(f"{row['adx_range']:<12} {row['count']:>6} {row['win_rate']:>6} ${row['total_pnl']:>9}")

        # ========================================
        # 6. POSIZIONI APERTE
        # ========================================
        cur.execute("""
            SELECT * FROM botone_trades
            WHERE closed_at IS NULL
            ORDER BY opened_at DESC
        """)
        open_positions = cur.fetchall()

        if open_positions:
            print("\n" + "=" * 100)
            print(f"📂 POSIZIONI APERTE ({len(open_positions)})")
            print("=" * 100)

            for p in open_positions:
                hours_open = (datetime.now() - p['opened_at']).total_seconds() / 3600
                print(f"\n   {p['symbol']} {p['direction']} @ ${float(p['entry_price']):,.2f}")
                print(f"   Opened: {p['opened_at'].strftime('%m/%d %H:%M')} ({hours_open:.1f}h ago)")
                print(f"   SL: ${float(p['sl_price'] or 0):,.2f} | Size: ${p['size_usd']} @ {p['leverage']}x")
                print(f"   AI: Tier={p['conviction_tier']} Conf={float(p['ai_confidence'] or 0):.0%}")

        # ========================================
        # 7. RACCOMANDAZIONI
        # ========================================
        print("\n" + "=" * 100)
        print("💡 RACCOMANDAZIONI")
        print("=" * 100)

        # Check win rate vs R/R
        if stats['avg_win'] and stats['avg_loss']:
            rr = abs(float(stats['avg_win']) / float(stats['avg_loss']))
            breakeven_wr = 100 / (1 + rr)
            actual_wr = float(stats['win_rate'])

            print(f"\n📐 Risk/Reward:")
            print(f"   R/R Ratio: {rr:.2f}")
            print(f"   Breakeven WR: {breakeven_wr:.1f}%")
            print(f"   Actual WR: {actual_wr:.1f}%")

            if actual_wr < breakeven_wr:
                gap = breakeven_wr - actual_wr
                print(f"\n   ❌ SOTTO breakeven di {gap:.1f}%!")
                print("   Opzioni: entry più selettivi, o SL più stretto, o TP più conservativo")
            else:
                print(f"\n   ✅ SOPRA breakeven - sistema teoricamente profittevole")

        # Check wasted profits
        if wasted:
            print(f"\n⚠️ Hai {len(wasted)} trade con profitto sprecato (MFE>1% ma chiuso in perdita)")
            print("   Considera trailing stop più aggressivo o take profit anticipato")

        print("\n" + "=" * 100)

    conn.close()


if __name__ == "__main__":
    analyze()
