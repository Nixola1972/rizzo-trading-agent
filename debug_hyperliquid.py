#!/usr/bin/env python3
"""
Script di debug per verificare connessione HyperLiquid
"""
import os
from dotenv import load_dotenv
from hyperliquid_trader import HyperLiquidTrader

load_dotenv()

print("=" * 60)
print("🔍 DEBUG HYPERLIQUID CONNECTION")
print("=" * 60)
print()

# Leggi configurazione da .env
TESTNET = os.getenv("TESTNET", "true").lower() in ("true", "1", "yes")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

print("📋 CONFIGURAZIONE DA .ENV:")
print(f"   TESTNET: {TESTNET}")
print(f"   WALLET_ADDRESS: {WALLET_ADDRESS}")
print(f"   PRIVATE_KEY: {PRIVATE_KEY[:10]}...{PRIVATE_KEY[-4:] if PRIVATE_KEY else 'NOT SET'}")
print()

if not PRIVATE_KEY or not WALLET_ADDRESS:
    print("❌ ERRORE: PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env!")
    exit(1)

print("🔌 Connessione a HyperLiquid...")
print(f"   Ambiente: {'TESTNET' if TESTNET else 'MAINNET'}")
print()

try:
    bot = HyperLiquidTrader(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        testnet=TESTNET
    )

    print("✅ Connessione stabilita!")
    print()

    print("💰 RECUPERO ACCOUNT STATUS...")
    account_status = bot.get_account_status()

    print()
    print("📊 ACCOUNT STATUS COMPLETO:")
    print("-" * 60)
    import json
    print(json.dumps(account_status, indent=2))
    print("-" * 60)
    print()

    # Estrai dati principali
    margin_summary = account_status.get('marginSummary', {})
    account_value = margin_summary.get('accountValue', '0')
    total_margin_used = margin_summary.get('totalMarginUsed', '0')
    total_raw_usd = margin_summary.get('totalRawUsd', '0')

    print("📈 RIEPILOGO:")
    print(f"   Account Value: {account_value} USDC")
    print(f"   Total Margin Used: {total_margin_used} USDC")
    print(f"   Total Raw USD: {total_raw_usd} USDC")
    print()

    # Posizioni aperte
    positions = account_status.get('assetPositions', [])
    print(f"📍 POSIZIONI APERTE: {len(positions)}")

    if positions:
        for pos in positions:
            position_data = pos.get('position', {})
            coin = position_data.get('coin', 'N/A')
            szi = position_data.get('szi', '0')
            entry_px = position_data.get('entryPx', '0')
            leverage = position_data.get('leverage', {}).get('value', '1')

            print(f"   - {coin}: Size={szi}, Entry={entry_px}, Leverage={leverage}x")
    else:
        print("   Nessuna posizione aperta")

    print()
    print("=" * 60)

    if float(account_value) == 0:
        print("⚠️  PROBLEMA RILEVATO: Account value = 0")
        print()
        print("Possibili cause:")
        print("1. Il wallet non ha fondi su HyperLiquid", "TESTNET" if TESTNET else "MAINNET")
        print("2. Il wallet address non è corretto")
        print("3. Devi fare deposit su HyperLiquid")
        print()
        print(f"✅ VERIFICA SU WEB: https://app.hyperliquid{'-testnet' if TESTNET else ''}.xyz")
        print(f"   Connetti wallet: {WALLET_ADDRESS}")
        print(f"   Controlla se c'è balance")
    else:
        print("✅ Account attivo con fondi!")
        print(f"   Balance: {account_value} USDC")
        print()
        print("Il bot dovrebbe funzionare correttamente!")

    print("=" * 60)

except Exception as e:
    print(f"❌ ERRORE: {e}")
    import traceback
    traceback.print_exc()
