#!/usr/bin/env python3
"""Script per verificare lo stato del bot nel database."""

import db_utils
from datetime import datetime, timezone, timedelta

def check_recent_operations():
    """Mostra le ultime operazioni del bot."""
    print("\n" + "="*80)
    print("ULTIME OPERAZIONI DEL BOT (ultime 50)")
    print("="*80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    created_at,
                    operation,
                    symbol,
                    direction,
                    target_portion_of_balance,
                    leverage,
                    raw_payload->>'reason' as reason
                FROM bot_operations
                ORDER BY created_at DESC
                LIMIT 50;
            """)
            rows = cur.fetchall()

            if not rows:
                print("Nessuna operazione trovata!")
                return

            for row in rows:
                id_, created_at, op, symbol, direction, portion, leverage, reason = row
                print(f"\n[{id_}] {created_at}")
                print(f"    Operation: {op} | Symbol: {symbol} | Direction: {direction}")
                print(f"    Portion: {portion} | Leverage: {leverage}")
                if reason:
                    print(f"    Reason: {reason[:150]}...")

def check_operation_stats():
    """Statistiche sulle operazioni nelle ultime 24 ore."""
    print("\n" + "="*80)
    print("STATISTICHE OPERAZIONI (ultime 24 ore)")
    print("="*80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    operation,
                    COUNT(*) as count
                FROM bot_operations
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY operation
                ORDER BY count DESC;
            """)
            rows = cur.fetchall()

            if not rows:
                print("Nessuna operazione nelle ultime 24 ore!")
                return

            total = sum(r[1] for r in rows)
            print(f"Totale operazioni: {total}")
            for op, count in rows:
                pct = (count / total) * 100
                print(f"  {op}: {count} ({pct:.1f}%)")

def check_recent_errors():
    """Mostra gli errori recenti."""
    print("\n" + "="*80)
    print("ERRORI RECENTI (ultime 24 ore)")
    print("="*80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    created_at,
                    error_type,
                    error_message,
                    source
                FROM errors
                WHERE created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 20;
            """)
            rows = cur.fetchall()

            if not rows:
                print("Nessun errore nelle ultime 24 ore!")
                return

            for row in rows:
                id_, created_at, err_type, err_msg, source = row
                print(f"\n[{id_}] {created_at} - {source}")
                print(f"    Type: {err_type}")
                print(f"    Message: {err_msg[:200] if err_msg else 'N/A'}...")

def check_account_snapshots():
    """Mostra gli ultimi snapshot dell'account."""
    print("\n" + "="*80)
    print("ULTIMI SNAPSHOT ACCOUNT")
    print("="*80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    created_at,
                    balance_usd
                FROM account_snapshots
                ORDER BY created_at DESC
                LIMIT 10;
            """)
            rows = cur.fetchall()

            if not rows:
                print("Nessun snapshot trovato!")
                return

            for row in rows:
                id_, created_at, balance = row
                print(f"[{id_}] {created_at} - Balance: ${balance:.2f}")

def check_last_run_time():
    """Verifica quando è stata l'ultima esecuzione del bot."""
    print("\n" + "="*80)
    print("ULTIMA ESECUZIONE DEL BOT")
    print("="*80)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(created_at) as last_run
                FROM bot_operations;
            """)
            row = cur.fetchone()

            if row and row[0]:
                last_run = row[0]
                now = datetime.now(timezone.utc)
                diff = now - last_run
                hours = diff.total_seconds() / 3600
                print(f"Ultima operazione: {last_run}")
                print(f"Tempo trascorso: {hours:.1f} ore fa")
            else:
                print("Nessuna operazione trovata!")

if __name__ == "__main__":
    print("Verifica stato del trading bot...")
    print(f"Ora corrente (UTC): {datetime.now(timezone.utc)}")

    check_last_run_time()
    check_operation_stats()
    check_recent_operations()
    check_recent_errors()
    check_account_snapshots()
