#!/usr/bin/env python3
"""
Script per confrontare i dati del Database con i dati reali di Hyperliquid.
Estrae i fills (trade) da Hyperliquid e li confronta con la tabella `trades`.

Uso:
    python verify_trades_vs_hyperliquid.py
    python verify_trades_vs_hyperliquid.py --export    # Esporta anche CSV
    python verify_trades_vs_hyperliquid.py --import    # Importa fills mancanti nel DB

Autore: Trading Bot Analysis
Data: 2025-12-04
"""

import os
import sys
import json
import csv
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# Hyperliquid
try:
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    HYPERLIQUID_AVAILABLE = True
except ImportError:
    print("⚠️ hyperliquid SDK non installato. Installa con: pip install hyperliquid-python-sdk")
    HYPERLIQUID_AVAILABLE = False

# Database
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    print("⚠️ psycopg2 non installato. Installa con: pip install psycopg2-binary")
    PSYCOPG2_AVAILABLE = False

# Configurazione
TESTNET = os.getenv("TESTNET", "false").lower() == "true"
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
DATABASE_URL = os.getenv("DATABASE_URL")


def get_hyperliquid_fills():
    """Estrae tutti i fills da Hyperliquid."""
    if not HYPERLIQUID_AVAILABLE:
        return []

    base_url = constants.TESTNET_API_URL if TESTNET else constants.MAINNET_API_URL
    info = Info(base_url, skip_ws=True)

    print(f"📡 Connessione a Hyperliquid ({'TESTNET' if TESTNET else 'MAINNET'})...")
    print(f"📍 Wallet: {WALLET_ADDRESS}")

    # Ottieni tutti i fills
    fills = info.user_fills(WALLET_ADDRESS)

    print(f"✅ Trovati {len(fills)} fills su Hyperliquid")
    return fills


def get_db_trades():
    """Estrae tutti i trade dal database."""
    if not PSYCOPG2_AVAILABLE or not DATABASE_URL:
        return []

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            trade_uuid,
            created_at,
            symbol,
            direction,
            status,
            entry_price,
            exit_price,
            size,
            pnl_usd,
            fee_total,
            net_pnl_usd,
            close_reason,
            trading_mode,
            open_score
        FROM trades
        ORDER BY created_at DESC
    """)

    trades = cur.fetchall()
    cur.close()
    conn.close()

    print(f"✅ Trovati {len(trades)} trade nel Database")
    return trades


def analyze_fills(fills):
    """Analizza i fills di Hyperliquid."""

    # Raggruppa per giorno
    by_day = {}
    by_symbol = {}
    total_pnl = Decimal('0')
    total_fee = Decimal('0')

    for fill in fills:
        # Parse timestamp
        ts = fill.get('time', 0)
        if ts > 0:
            dt = datetime.fromtimestamp(ts / 1000)
            day = dt.strftime('%Y-%m-%d')
        else:
            day = 'unknown'

        # Inizializza giorno
        if day not in by_day:
            by_day[day] = {
                'count': 0,
                'pnl': Decimal('0'),
                'fee': Decimal('0'),
                'buys': 0,
                'sells': 0
            }

        # Inizializza symbol
        coin = fill.get('coin', 'UNKNOWN')
        if coin not in by_symbol:
            by_symbol[coin] = {
                'count': 0,
                'pnl': Decimal('0'),
                'fee': Decimal('0')
            }

        by_day[day]['count'] += 1
        by_symbol[coin]['count'] += 1

        # P&L chiuso
        closed_pnl = Decimal(str(fill.get('closedPnl', '0')))
        total_pnl += closed_pnl
        by_day[day]['pnl'] += closed_pnl
        by_symbol[coin]['pnl'] += closed_pnl

        # Fee
        fee = Decimal(str(fill.get('fee', '0')))
        total_fee += fee
        by_day[day]['fee'] += fee
        by_symbol[coin]['fee'] += fee

        # Direzione
        side = fill.get('side', '')
        if side == 'B':
            by_day[day]['buys'] += 1
        else:
            by_day[day]['sells'] += 1

    return {
        'by_day': by_day,
        'by_symbol': by_symbol,
        'total_pnl': total_pnl,
        'total_fee': total_fee,
        'total_fills': len(fills)
    }


def compare_data(hl_analysis, db_trades):
    """Confronta i dati Hyperliquid vs Database."""

    print("\n" + "="*70)
    print("📊 CONFRONTO HYPERLIQUID vs DATABASE")
    print("="*70)

    # Totali Hyperliquid
    print(f"\n🔷 HYPERLIQUID (dati reali):")
    print(f"   Total Fills:    {hl_analysis['total_fills']}")
    print(f"   Total P&L:      {hl_analysis['total_pnl']:.4f} USDC")
    print(f"   Total Fee:      {hl_analysis['total_fee']:.4f} USDC")
    net_hl = hl_analysis['total_pnl'] - hl_analysis['total_fee']
    print(f"   Net P&L:        {net_hl:.4f} USDC")

    # Totali Database
    if db_trades:
        db_total_pnl = sum(Decimal(str(t['pnl_usd'] or 0)) for t in db_trades)
        db_total_fee = sum(Decimal(str(t['fee_total'] or 0)) for t in db_trades)
        db_total_net = sum(Decimal(str(t['net_pnl_usd'] or 0)) for t in db_trades)

        print(f"\n🔶 DATABASE:")
        print(f"   Total Trades:   {len(db_trades)}")
        print(f"   Total P&L:      {db_total_pnl:.4f} USDC")
        print(f"   Total Fee:      {db_total_fee:.4f} USDC")
        print(f"   Net P&L:        {db_total_net:.4f} USDC")

        # Differenze
        print(f"\n⚠️  DIFFERENZE:")
        fill_diff = hl_analysis['total_fills'] - len(db_trades)
        print(f"   Fills vs Trades:  {hl_analysis['total_fills']} vs {len(db_trades)} ({fill_diff:+d})")
        pnl_diff = hl_analysis['total_pnl'] - db_total_pnl
        print(f"   P&L Diff:         {pnl_diff:+.4f} USDC")
        fee_diff = hl_analysis['total_fee'] - db_total_fee
        print(f"   Fee Diff:         {fee_diff:+.4f} USDC")
        net_diff = net_hl - db_total_net
        print(f"   Net P&L Diff:     {net_diff:+.4f} USDC")

    # Per Symbol
    print(f"\n📈 DETTAGLIO PER SYMBOL (Hyperliquid):")
    print("-"*60)
    print(f"{'Symbol':<10} {'Fills':>8} {'P&L':>15} {'Fee':>12} {'Net':>15}")
    print("-"*60)

    for symbol in sorted(hl_analysis['by_symbol'].keys()):
        data = hl_analysis['by_symbol'][symbol]
        net = data['pnl'] - data['fee']
        print(f"{symbol:<10} {data['count']:>8} {data['pnl']:>15.4f} {data['fee']:>12.4f} {net:>15.4f}")

    # Per giorno
    print(f"\n📅 DETTAGLIO PER GIORNO (Hyperliquid):")
    print("-"*70)
    print(f"{'Giorno':<12} {'Fills':>8} {'P&L':>15} {'Fee':>12} {'Net':>15}")
    print("-"*70)

    for day in sorted(hl_analysis['by_day'].keys(), reverse=True)[:15]:
        data = hl_analysis['by_day'][day]
        net = data['pnl'] - data['fee']
        print(f"{day:<12} {data['count']:>8} {data['pnl']:>15.4f} {data['fee']:>12.4f} {net:>15.4f}")

    print("-"*70)
    total_net = hl_analysis['total_pnl'] - hl_analysis['total_fee']
    print(f"{'TOTALE':<12} {hl_analysis['total_fills']:>8} {hl_analysis['total_pnl']:>15.4f} {hl_analysis['total_fee']:>12.4f} {total_net:>15.4f}")

    return {
        'hl_net': net_hl,
        'db_net': db_total_net if db_trades else Decimal('0'),
        'difference': net_diff if db_trades else net_hl
    }


def export_fills_csv(fills, filename=None):
    """Esporta i fills in CSV."""
    if not filename:
        filename = f"hyperliquid_fills_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'timestamp', 'date', 'coin', 'side', 'direction',
            'price', 'size', 'closedPnl', 'fee', 'net_pnl',
            'hash', 'oid'
        ])

        for fill in fills:
            ts = fill.get('time', 0)
            dt = datetime.fromtimestamp(ts / 1000) if ts > 0 else None

            closed_pnl = Decimal(str(fill.get('closedPnl', '0')))
            fee = Decimal(str(fill.get('fee', '0')))
            net_pnl = closed_pnl - fee

            # Direzione leggibile
            dir_raw = fill.get('dir', '')
            side = fill.get('side', '')

            writer.writerow([
                ts,
                dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '',
                fill.get('coin', ''),
                side,
                dir_raw,
                fill.get('px', ''),
                fill.get('sz', ''),
                str(closed_pnl),
                str(fee),
                str(net_pnl),
                fill.get('hash', ''),
                fill.get('oid', '')
            ])

    print(f"💾 CSV esportato: {filename}")
    return filename


def export_fills_json(fills, filename=None):
    """Esporta i fills in JSON."""
    if not filename:
        filename = f"hyperliquid_fills_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(filename, 'w') as f:
        json.dump(fills, f, indent=2, default=str)

    print(f"💾 JSON esportato: {filename}")
    return filename


def main():
    print("🔍 Verifica Trade: Hyperliquid vs Database")
    print("="*70)

    # Argomenti
    export_csv = '--export' in sys.argv or '-e' in sys.argv
    do_import = '--import' in sys.argv or '-i' in sys.argv

    if not WALLET_ADDRESS:
        print("❌ WALLET_ADDRESS non configurato nel .env!")
        return

    if not HYPERLIQUID_AVAILABLE:
        print("❌ SDK Hyperliquid non disponibile!")
        return

    # Estrai dati da Hyperliquid
    fills = get_hyperliquid_fills()

    if not fills:
        print("⚠️ Nessun fill trovato su Hyperliquid")
        return

    # Estrai dati da DB (se disponibile)
    db_trades = []
    if DATABASE_URL and PSYCOPG2_AVAILABLE:
        db_trades = get_db_trades()
    else:
        print("⚠️ Database non configurato, confronto solo dati Hyperliquid")

    # Analizza fills
    hl_analysis = analyze_fills(fills)

    # Confronta
    result = compare_data(hl_analysis, db_trades)

    # Export
    if export_csv:
        export_fills_csv(fills)

    # Sempre salva JSON per riferimento
    export_fills_json(fills)

    # Summary finale
    print("\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)
    print(f"   Hyperliquid Net P&L: {result['hl_net']:.4f} USDC")
    if db_trades:
        print(f"   Database Net P&L:    {result['db_net']:.4f} USDC")
        print(f"   DIFFERENZA:          {result['difference']:.4f} USDC")

        if abs(result['difference']) > 1:
            print("\n   ⚠️  ATTENZIONE: Differenza significativa tra DB e Hyperliquid!")
            print("       Potrebbero esserci trade mancanti nel database.")

    if do_import:
        print("\n⚠️ Funzione import non ancora implementata.")
        print("   Per importare i fills mancanti, usa i dati dal JSON esportato.")


if __name__ == "__main__":
    main()
