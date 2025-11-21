#!/usr/bin/env python3
"""
🔍 INVESTIGAZIONE COMPLETA WALLET HYPERLIQUID
Controlla sia TESTNET che MAINNET per localizzare i fondi
"""
import os
from dotenv import load_dotenv
from hyperliquid_trader import HyperLiquidTrader
import json

load_dotenv()

print("=" * 80)
print("🔍 INVESTIGAZIONE COMPLETA WALLET HYPERLIQUID")
print("=" * 80)
print()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

if not PRIVATE_KEY or not WALLET_ADDRESS:
    print("❌ ERRORE: PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env!")
    exit(1)

print(f"📋 Wallet da investigare: {WALLET_ADDRESS}")
print()

# ============================================================================
# STEP 1: VERIFICA TESTNET
# ============================================================================
print("=" * 80)
print("🧪 STEP 1: CONTROLLO TESTNET")
print("=" * 80)
print()

try:
    print("🔌 Connessione a HyperLiquid TESTNET...")
    bot_testnet = HyperLiquidTrader(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        testnet=True
    )

    print("✅ Connesso a TESTNET")
    print()

    account_status_testnet = bot_testnet.get_account_status()

    # Estrai balance testnet
    margin_summary_testnet = account_status_testnet.get('marginSummary', {})
    balance_testnet = float(margin_summary_testnet.get('accountValue', '0'))

    print(f"💰 TESTNET Balance: {balance_testnet} USDC")

    if balance_testnet > 0:
        print("✅ TROVATI FONDI SU TESTNET!")
        print()
        print("📊 Dettagli TESTNET:")
        print(json.dumps(margin_summary_testnet, indent=2))

        # Posizioni testnet
        positions_testnet = account_status_testnet.get('assetPositions', [])
        if positions_testnet:
            print()
            print(f"📍 Posizioni aperte su TESTNET: {len(positions_testnet)}")
            for pos in positions_testnet:
                position_data = pos.get('position', {})
                print(f"   - {position_data.get('coin', 'N/A')}: {position_data.get('szi', '0')}")
    else:
        print("❌ Nessun fondo su TESTNET")

except Exception as e:
    print(f"❌ ERRORE durante controllo TESTNET: {e}")
    balance_testnet = 0

print()

# ============================================================================
# STEP 2: VERIFICA MAINNET
# ============================================================================
print("=" * 80)
print("🌐 STEP 2: CONTROLLO MAINNET")
print("=" * 80)
print()

try:
    print("🔌 Connessione a HyperLiquid MAINNET...")
    bot_mainnet = HyperLiquidTrader(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        testnet=False
    )

    print("✅ Connesso a MAINNET")
    print()

    account_status_mainnet = bot_mainnet.get_account_status()

    # Estrai balance mainnet
    margin_summary_mainnet = account_status_mainnet.get('marginSummary', {})
    balance_mainnet = float(margin_summary_mainnet.get('accountValue', '0'))

    print(f"💰 MAINNET Balance: {balance_mainnet} USDC")

    if balance_mainnet > 0:
        print("✅ TROVATI FONDI SU MAINNET!")
        print()
        print("📊 Dettagli MAINNET:")
        print(json.dumps(margin_summary_mainnet, indent=2))

        # Posizioni mainnet
        positions_mainnet = account_status_mainnet.get('assetPositions', [])
        if positions_mainnet:
            print()
            print(f"📍 Posizioni aperte su MAINNET: {len(positions_mainnet)}")
            for pos in positions_mainnet:
                position_data = pos.get('position', {})
                print(f"   - {position_data.get('coin', 'N/A')}: {position_data.get('szi', '0')}")
    else:
        print("❌ Nessun fondo su MAINNET")

except Exception as e:
    print(f"❌ ERRORE durante controllo MAINNET: {e}")
    balance_mainnet = 0

print()

# ============================================================================
# STEP 3: ANALISI E RACCOMANDAZIONI
# ============================================================================
print("=" * 80)
print("📊 RIEPILOGO E PROSSIMI PASSI")
print("=" * 80)
print()

print(f"💰 TESTNET Balance:  {balance_testnet} USDC")
print(f"💰 MAINNET Balance:  {balance_mainnet} USDC")
print(f"💰 TOTALE:           {balance_testnet + balance_mainnet} USDC")
print()

if balance_testnet > 0 and balance_mainnet == 0:
    print("=" * 80)
    print("🎯 SITUAZIONE: I tuoi 15 USD sono su TESTNET, non su MAINNET")
    print("=" * 80)
    print()
    print("📋 COSA SIGNIFICA:")
    print("   - TESTNET = ambiente di test, fondi finti per sperimentare")
    print("   - MAINNET = ambiente reale, fondi veri per trading reale")
    print("   - I fondi NON si possono trasferire da testnet a mainnet")
    print()
    print("🎯 COME PROCEDERE PER ATTIVARE MAINNET:")
    print()
    print("OPZIONE 1 - Depositare fondi VERI su MAINNET (raccomandato):")
    print("   1. Vai su: https://app.hyperliquid.xyz")
    print(f"   2. Connetti il wallet: {WALLET_ADDRESS}")
    print("   3. Clicca 'Deposit' in alto a destra")
    print("   4. Trasferisci USDC da un exchange (Binance, Coinbase, etc.) o da un altro wallet")
    print("   5. Importo minimo consigliato: 20-50 USDC per trading reale")
    print("   6. Attendi la conferma (1-2 minuti)")
    print("   7. Il wallet sarà ATTIVO e il bot potrà operare su mainnet!")
    print()
    print("OPZIONE 2 - Continuare su TESTNET per testare:")
    print("   1. Cambia .env: TESTNET=true")
    print("   2. Rebuild: docker compose -f docker-compose.existing-postgres.yml build")
    print("   3. Il bot userà i fondi testnet (ma sono finti!)")
    print()
    print("⚠️  RACCOMANDAZIONE:")
    print("   Per trading VERO devi usare MAINNET con fondi veri.")
    print("   Il TESTNET è solo per sperimentare senza rischi.")

elif balance_mainnet > 0:
    print("=" * 80)
    print("✅ PERFETTO! Hai fondi su MAINNET")
    print("=" * 80)
    print()
    print(f"💰 Balance MAINNET: {balance_mainnet} USDC")
    print()
    print("🎯 IL BOT È PRONTO PER OPERARE!")
    print()
    print("✅ Prossimi passi:")
    print("   1. Assicurati che .env abbia: TESTNET=false")
    print("   2. Rebuild: docker compose -f docker-compose.existing-postgres.yml build")
    print("   3. Test: docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot")
    print("   4. Se funziona, il cron lo eseguirà automaticamente ogni 15 min")

elif balance_testnet == 0 and balance_mainnet == 0:
    print("=" * 80)
    print("❌ NESSUN FONDO TROVATO né su TESTNET né su MAINNET")
    print("=" * 80)
    print()
    print("🎯 POSSIBILI CAUSE:")
    print("   1. I fondi sono su un WALLET DIVERSO")
    print("   2. Non hai ancora fatto deposit su HyperLiquid")
    print("   3. C'è un problema con la configurazione")
    print()
    print("🔍 VERIFICA MANUALE:")
    print("   1. TESTNET - Vai su: https://app.hyperliquid-testnet.xyz")
    print(f"      Connetti wallet: {WALLET_ADDRESS}")
    print("      Controlla se vedi fondi")
    print()
    print("   2. MAINNET - Vai su: https://app.hyperliquid.xyz")
    print(f"      Connetti wallet: {WALLET_ADDRESS}")
    print("      Controlla se vedi fondi")
    print()
    print("🎯 COME OTTENERE FONDI:")
    print()
    print("   PER TESTNET (fondi finti per test):")
    print("   1. Vai su: https://app.hyperliquid-testnet.xyz")
    print("   2. Connetti wallet")
    print("   3. Cerca 'Faucet' o chiedi fondi testnet nella community")
    print()
    print("   PER MAINNET (fondi veri):")
    print("   1. Vai su: https://app.hyperliquid.xyz")
    print("   2. Connetti wallet")
    print("   3. Clicca 'Deposit'")
    print("   4. Trasferisci USDC da exchange o altro wallet")
    print("   5. Minimo consigliato: 20-50 USDC")

else:
    print("=" * 80)
    print("🎯 HAI FONDI SU ENTRAMBI GLI AMBIENTI")
    print("=" * 80)
    print()
    print(f"💰 TESTNET:  {balance_testnet} USDC (fondi finti)")
    print(f"💰 MAINNET:  {balance_mainnet} USDC (fondi veri)")
    print()
    print("⚠️  IMPORTANTE: Scegli su quale ambiente vuoi operare:")
    print("   - TESTNET = test senza rischi, fondi finti")
    print("   - MAINNET = trading reale, fondi veri")
    print()
    print("📝 Configura .env:")
    print("   Per TESTNET: TESTNET=true")
    print("   Per MAINNET: TESTNET=false")

print()
print("=" * 80)
print("🔗 LINK UTILI:")
print("=" * 80)
print()
print("🌐 HyperLiquid MAINNET:  https://app.hyperliquid.xyz")
print("🧪 HyperLiquid TESTNET:  https://app.hyperliquid-testnet.xyz")
print(f"👛 Il tuo wallet:        {WALLET_ADDRESS}")
print()
print("📚 Documentazione:")
print("   https://hyperliquid.gitbook.io/hyperliquid-docs")
print()
print("=" * 80)
