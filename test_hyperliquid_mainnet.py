#!/usr/bin/env python3
"""
🧪 TEST SEMPLICE HYPERLIQUID MAINNET
Script minimale per verificare connessione e balance senza il bot completo
"""
import os
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.utils import constants
import json

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

if not PRIVATE_KEY or not WALLET_ADDRESS:
    print("❌ ERRORE: PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env!")
    exit(1)

print("=" * 80)
print("🧪 TEST HYPERLIQUID MAINNET - VERIFICA WALLET")
print("=" * 80)
print()
print(f"👛 Wallet: {WALLET_ADDRESS}")
print(f"🌐 Ambiente: MAINNET (api.hyperliquid.xyz)")
print()

# ============================================================================
# TEST 1: Connessione API
# ============================================================================
print("=" * 80)
print("TEST 1: Connessione API HyperLiquid")
print("=" * 80)
print()

try:
    # Crea connessione a MAINNET
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    print("✅ Connessione API stabilita")
    print(f"   Endpoint: {constants.MAINNET_API_URL}")
    print()
except Exception as e:
    print(f"❌ ERRORE nella connessione API: {e}")
    exit(1)

# ============================================================================
# TEST 2: Recupera user_state (balance e posizioni)
# ============================================================================
print("=" * 80)
print("TEST 2: Recupera dati wallet (user_state)")
print("=" * 80)
print()

try:
    user_state = info.user_state(WALLET_ADDRESS)

    print("✅ Dati ricevuti dall'API")
    print()
    print("📊 STRUTTURA COMPLETA user_state:")
    print("=" * 80)
    print(json.dumps(user_state, indent=2))
    print("=" * 80)
    print()

except Exception as e:
    print(f"❌ ERRORE nel recupero user_state: {e}")
    print()
    print("🔍 Possibili cause:")
    print("   1. Wallet non attivato su mainnet (serve almeno 1 deposito)")
    print("   2. Problemi di rete/connessione")
    print("   3. API HyperLiquid temporaneamente non disponibile")
    print()
    exit(1)

# ============================================================================
# TEST 3: Estrai balance
# ============================================================================
print("=" * 80)
print("TEST 3: Analisi balance")
print("=" * 80)
print()

margin_summary = user_state.get('marginSummary', {})
cross_margin_summary = user_state.get('crossMarginSummary', {})
withdrawable = user_state.get('withdrawable', '0.0')

balance_margin = float(margin_summary.get('accountValue', '0'))
balance_cross = float(cross_margin_summary.get('accountValue', '0'))
balance_withdrawable = float(withdrawable)

print(f"💰 marginSummary.accountValue:      {balance_margin} USDC")
print(f"💰 crossMarginSummary.accountValue: {balance_cross} USDC")
print(f"💰 withdrawable:                     {balance_withdrawable} USDC")
print()

# ============================================================================
# TEST 4: Verifica posizioni aperte
# ============================================================================
print("=" * 80)
print("TEST 4: Posizioni aperte")
print("=" * 80)
print()

asset_positions = user_state.get('assetPositions', [])

if asset_positions:
    print(f"📍 Trovate {len(asset_positions)} posizioni aperte:")
    for i, pos in enumerate(asset_positions, 1):
        position_data = pos.get('position', {})
        coin = position_data.get('coin', 'N/A')
        size = position_data.get('szi', '0')
        print(f"   {i}. {coin}: size={size}")
else:
    print("❌ Nessuna posizione aperta")

print()

# ============================================================================
# DIAGNOSI FINALE
# ============================================================================
print("=" * 80)
print("📊 DIAGNOSI FINALE")
print("=" * 80)
print()

total_balance = max(balance_margin, balance_cross, balance_withdrawable)

if total_balance == 0:
    print("❌ PROBLEMA: Balance = 0.0 USDC su MAINNET")
    print()
    print("🎯 CAUSA PROBABILE:")
    print("   Il wallet NON è stato ancora ATTIVATO su HyperLiquid mainnet.")
    print("   Per attivare un wallet serve fare almeno 1 DEPOSITO.")
    print()
    print("✅ SOLUZIONE:")
    print()
    print("   PASSO 1 - Vai sull'interfaccia web HyperLiquid:")
    print("   🌐 https://app.hyperliquid.xyz")
    print()
    print("   PASSO 2 - Connetti il wallet:")
    print(f"   👛 {WALLET_ADDRESS}")
    print()
    print("   PASSO 3 - Fai un deposito:")
    print("   💵 Clicca 'Deposit' in alto a destra")
    print("   💵 Trasferisci USDC da un exchange (Binance, Coinbase, etc.)")
    print("   💵 Importo minimo: 20-50 USDC (raccomandato per trading)")
    print("   💵 Network: Arbitrum One (layer 2 di Ethereum)")
    print()
    print("   PASSO 4 - Attendi conferma (1-2 minuti)")
    print()
    print("   PASSO 5 - Ri-esegui questo test:")
    print("   python3 test_hyperliquid_mainnet.py")
    print()
    print("   ✅ Dopo il deposito, il wallet sarà ATTIVO e il bot potrà operare!")
    print()
    print("⚠️  IMPORTANTE:")
    print("   - TESTNET è offline (come hai detto)")
    print("   - I 15 USD che vedevi prima erano probabilmente su testnet")
    print("   - Per trading REALE serve MAINNET con fondi veri")
    print("   - Serve depositare USDC veri per attivare il wallet")

elif total_balance > 0:
    print(f"✅ PERFETTO! Balance trovato: {total_balance} USDC")
    print()
    print("🎉 Il wallet è ATTIVO e ha fondi!")
    print()
    print("✅ Prossimi passi:")
    print("   1. Verifica che .env abbia: TESTNET=false")
    print("   2. Esegui il bot: python3 trading_agent.py")
    print("   3. Il bot può iniziare a operare!")

else:
    print("⚠️  Situazione anomala - verifica i dati sopra")

print()
print("=" * 80)
print("🔗 LINK UTILI")
print("=" * 80)
print()
print("🌐 HyperLiquid MAINNET: https://app.hyperliquid.xyz")
print(f"👛 Il tuo wallet:       {WALLET_ADDRESS}")
print("📚 Come depositare:     https://hyperliquid.gitbook.io/hyperliquid-docs/for-traders/depositing-and-withdrawing")
print()
print("=" * 80)
