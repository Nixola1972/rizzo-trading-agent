#!/usr/bin/env python3
"""
Analisi Performance Botone V6
Esegui con: python analyze_performance.py
Oppure: docker exec -it botone_v6_fast python /app/analyze_performance.py
"""

import os
import json
from datetime import datetime, timedelta
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://tradingbot:BotoneDB2025@memory_postgres:5432/botone_baseline"
)


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def analyze():
    conn = get_connection()
    cur = conn.cursor()

    # 1. Panoramica generale
    print_section("1. PANORAMICA GENERALE (ultimi 7 giorni)")

    cur.execute("""
        SELECT
            COUNT(*) as total_ops,
            COUNT(*) FILTER (WHERE operation = 'open') as opens,
            COUNT(*) FILTER (WHERE operation = 'close') as closes,
            COUNT(*) FILTER (WHERE operation = 'hold') as holds
        FROM bot_operations
        WHERE created_at > NOW() - INTERVAL '7 days'
    """)
    row = cur.fetchone()
    print(f"  Totale operazioni: {row['total_ops']}")
    print(f"  - Open:  {row['opens']}")
    print(f"  - Close: {row['closes']}")
    print(f"  - Hold:  {row['holds']}")

    if row['total_ops'] > 0:
        hold_pct = row['holds'] / row['total_ops'] * 100
        print(f"\n  Hold ratio: {hold_pct:.1f}%")
        if hold_pct > 90:
            print("  ⚠️  PROBLEMA: Il bot sta holdando troppo (>90%)!")

    # 2. Bilancio
    print_section("2. ANDAMENTO BILANCIO")

    cur.execute("""
        SELECT
            (SELECT balance_usd FROM account_snapshots ORDER BY created_at ASC LIMIT 1) as first_balance,
            (SELECT balance_usd FROM account_snapshots ORDER BY created_at DESC LIMIT 1) as last_balance,
            (SELECT created_at FROM account_snapshots ORDER BY created_at ASC LIMIT 1) as first_date,
            (SELECT created_at FROM account_snapshots ORDER BY created_at DESC LIMIT 1) as last_date
    """)
    row = cur.fetchone()

    if row['first_balance'] and row['last_balance']:
        first_bal = float(row['first_balance'])
        last_bal = float(row['last_balance'])
        pnl = last_bal - first_bal
        pnl_pct = (pnl / first_bal) * 100 if first_bal > 0 else 0

        print(f"  Bilancio iniziale: ${first_bal:.2f}")
        print(f"  Bilancio attuale:  ${last_bal:.2f}")
        print(f"  P&L:               ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        print(f"  Periodo:           {row['first_date']} → {row['last_date']}")

        if pnl < 0:
            print("\n  ⚠️  PROBLEMA: Il bot sta perdendo soldi!")
        elif pnl_pct < 1:
            print("\n  ⚠️  ATTENZIONE: Performance molto bassa")

    # 3. Posizioni aperte
    print_section("3. POSIZIONI APERTE ATTUALI")

    cur.execute("""
        SELECT
            op.symbol,
            op.side,
            op.size,
            op.entry_price,
            op.mark_price,
            op.pnl_usd,
            op.leverage
        FROM open_positions op
        JOIN account_snapshots s ON op.snapshot_id = s.id
        WHERE s.id = (SELECT MAX(id) FROM account_snapshots)
    """)
    positions = cur.fetchall()

    if positions:
        for pos in positions:
            pnl = float(pos['pnl_usd']) if pos['pnl_usd'] else 0
            emoji = "🟢" if pnl >= 0 else "🔴"
            print(f"  {emoji} {pos['symbol']} {pos['side'].upper()}")
            print(f"     Entry: ${float(pos['entry_price']):.2f}")
            print(f"     Mark:  ${float(pos['mark_price']):.2f}")
            print(f"     P&L:   ${pnl:+.2f}")
            print(f"     Leva:  {pos['leverage']}")
            print()
    else:
        print("  Nessuna posizione aperta")

    # 4. Analisi trade recenti
    print_section("4. TRADE RECENTI (Open/Close)")

    cur.execute("""
        SELECT
            created_at,
            operation,
            symbol,
            direction,
            leverage,
            target_portion_of_balance,
            raw_payload->>'reason' as reason
        FROM bot_operations
        WHERE operation IN ('open', 'close')
        ORDER BY created_at DESC
        LIMIT 20
    """)
    trades = cur.fetchall()

    if trades:
        for t in trades:
            emoji = "📈" if t['operation'] == 'open' else "📉"
            dir_emoji = "🟢" if t['direction'] == 'long' else "🔴"
            portion = float(t['target_portion_of_balance'] or 0) * 100
            print(f"  {emoji} {t['created_at'].strftime('%Y-%m-%d %H:%M')} | {t['operation'].upper()}")
            print(f"     {dir_emoji} {t['symbol']} {t['direction']} | Leva: {t['leverage']}x | Portion: {portion:.0f}%")
            if t['reason']:
                reason = t['reason'][:100] + "..." if len(t['reason']) > 100 else t['reason']
                print(f"     Reason: {reason}")
            print()
    else:
        print("  ⚠️  Nessun trade negli ultimi 7 giorni!")
        print("  Il bot sta solo holdando - questo è un problema.")

    # 5. Frequenza decisioni
    print_section("5. FREQUENZA DECISIONI")

    cur.execute("""
        SELECT
            operation,
            COUNT(*) as count
        FROM bot_operations
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY operation
    """)
    freq = cur.fetchall()

    for f in freq:
        print(f"  {f['operation']}: {f['count']} nelle ultime 24h")

    # 6. Sentiment analysis
    print_section("6. CORRELAZIONE SENTIMENT vs OPERAZIONI")

    cur.execute("""
        SELECT
            sc.classification,
            bo.operation,
            COUNT(*) as count
        FROM bot_operations bo
        JOIN ai_contexts ac ON bo.context_id = ac.id
        JOIN sentiment_contexts sc ON sc.context_id = ac.id
        WHERE bo.created_at > NOW() - INTERVAL '7 days'
        GROUP BY sc.classification, bo.operation
        ORDER BY count DESC
    """)
    sent = cur.fetchall()

    sentiment_ops = defaultdict(lambda: defaultdict(int))
    for s in sent:
        sentiment_ops[s['classification']][s['operation']] = s['count']

    for classification, ops in sentiment_ops.items():
        print(f"\n  {classification}:")
        for op, count in ops.items():
            print(f"    - {op}: {count}")

    # 7. Errori
    print_section("7. ERRORI RECENTI")

    cur.execute("""
        SELECT error_type, error_message, source, created_at
        FROM errors
        WHERE created_at > NOW() - INTERVAL '7 days'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    errors = cur.fetchall()

    if errors:
        for e in errors:
            print(f"  ❌ {e['created_at'].strftime('%Y-%m-%d %H:%M')}")
            print(f"     Type: {e['error_type']}")
            print(f"     Msg:  {e['error_message'][:80]}...")
            print()
    else:
        print("  ✅ Nessun errore negli ultimi 7 giorni")

    # 8. Diagnosi problemi
    print_section("8. DIAGNOSI PROBLEMI")

    # Check 1: Troppi hold?
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE operation = 'hold') as holds,
            COUNT(*) as total
        FROM bot_operations
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """)
    row = cur.fetchone()
    if row['total'] > 0:
        hold_ratio = row['holds'] / row['total']
        if hold_ratio > 0.95:
            print("  ❌ PROBLEMA 1: Hold ratio > 95%")
            print("     Il bot non sta tradando quasi mai.")
            print("     Possibili cause:")
            print("     - Threshold troppo alto nel prompt")
            print("     - AI troppo conservativa")
            print("     - Indicatori non favorevoli")
        else:
            print(f"  ✅ Hold ratio: {hold_ratio*100:.1f}% (OK)")

    # Check 2: Bilancio in calo?
    cur.execute("""
        SELECT
            balance_usd,
            created_at
        FROM account_snapshots
        ORDER BY created_at DESC
        LIMIT 10
    """)
    snapshots = cur.fetchall()
    if len(snapshots) >= 2:
        latest = float(snapshots[0]['balance_usd'])
        oldest = float(snapshots[-1]['balance_usd'])
        if latest < oldest * 0.98:  # -2% o più
            print(f"  ❌ PROBLEMA 2: Bilancio in calo")
            print(f"     Da ${oldest:.2f} a ${latest:.2f}")
        else:
            print(f"  ✅ Bilancio stabile o in crescita")

    # Check 3: Trade con loss?
    cur.execute("""
        SELECT
            op.pnl_usd
        FROM open_positions op
        JOIN account_snapshots s ON op.snapshot_id = s.id
        WHERE s.created_at > NOW() - INTERVAL '7 days'
    """)
    all_pnl = cur.fetchall()
    losses = [float(p['pnl_usd']) for p in all_pnl if p['pnl_usd'] and float(p['pnl_usd']) < 0]
    wins = [float(p['pnl_usd']) for p in all_pnl if p['pnl_usd'] and float(p['pnl_usd']) > 0]

    if losses or wins:
        total_loss = sum(losses)
        total_win = sum(wins)
        print(f"\n  Snapshot P&L:")
        print(f"    Wins:   {len(wins)} trade, totale ${total_win:+.2f}")
        print(f"    Losses: {len(losses)} trade, totale ${total_loss:+.2f}")

    print_section("RACCOMANDAZIONI")

    if row['total'] > 0 and row['holds'] / row['total'] > 0.9:
        print("""
  1. RIDUCI LA CONSERVATIVITÀ
     - Abbassa le soglie nel prompt di trading
     - Considera TRADING_STYLE=aggressive o moderate

  2. VERIFICA IL PROMPT
     - Il prompt potrebbe essere troppo restrittivo
     - L'AI potrebbe non avere abbastanza "coraggio"

  3. ANALIZZA I FORECAST
     - Se le previsioni sono sempre incerte, l'AI non traderà
     - Potrebbe servire una finestra temporale diversa
""")
    else:
        print("""
  Il bot sta tradando. Analizza:
  1. Win rate - quanti trade vincenti vs perdenti?
  2. Average gain vs average loss
  3. Timing - sta entrando/uscendo nei momenti giusti?
""")

    conn.close()


if __name__ == "__main__":
    try:
        analyze()
    except Exception as e:
        print(f"\n❌ Errore connessione database: {e}")
        print("\nAssicurati che:")
        print("1. Il container memory_postgres sia attivo")
        print("2. La DATABASE_URL sia corretta")
        print("3. Sei nella stessa rete Docker")
