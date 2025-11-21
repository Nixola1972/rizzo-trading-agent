#!/usr/bin/env python3
"""
Verifica che PRIVATE_KEY e WALLET_ADDRESS corrispondano
"""
import os
from dotenv import load_dotenv
import eth_account

load_dotenv()

print("=" * 60)
print("🔐 VERIFICA WALLET & PRIVATE KEY")
print("=" * 60)
print()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

if not PRIVATE_KEY or not WALLET_ADDRESS:
    print("❌ ERRORE: PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env!")
    exit(1)

print(f"📋 Configurazione da .env:")
print(f"   WALLET_ADDRESS: {WALLET_ADDRESS}")
print(f"   PRIVATE_KEY: {PRIVATE_KEY[:10]}...{PRIVATE_KEY[-4:]}")
print()

# Genera address dalla private key
try:
    account = eth_account.Account.from_key(PRIVATE_KEY)
    derived_address = account.address

    print(f"🔑 Address derivato dalla PRIVATE_KEY:")
    print(f"   {derived_address}")
    print()

    if derived_address.lower() == WALLET_ADDRESS.lower():
        print("✅ PERFETTO! PRIVATE_KEY e WALLET_ADDRESS corrispondono!")
        print()
        print("Il problema NON è la configurazione delle chiavi.")
        print()
        print("🔍 Possibili cause:")
        print("1. L'account non ha mai fatto deposit su HyperLiquid")
        print("2. I fondi sono su un wallet diverso")
        print("3. C'è un problema con l'API HyperLiquid")
        print()
        print("✅ PROSSIMO PASSO:")
        print("   Vai su https://app.hyperliquid.xyz")
        print(f"   Connetti wallet {WALLET_ADDRESS}")
        print("   Verifica se vedi i 15 USD")
        print("   Se NO: i fondi sono altrove")
        print("   Se SÌ: fai un piccolo deposit/withdraw per 'attivare' l'account")
    else:
        print("❌ ERRORE! PRIVATE_KEY e WALLET_ADDRESS NON CORRISPONDONO!")
        print()
        print(f"   WALLET_ADDRESS nel .env: {WALLET_ADDRESS}")
        print(f"   Address dalla PRIVATE_KEY:  {derived_address}")
        print()
        print("🔧 FIX:")
        print("   Opzione 1: Usa la PRIVATE_KEY corretta per questo WALLET_ADDRESS")
        print(f"   Opzione 2: Cambia WALLET_ADDRESS a {derived_address}")
        print()

except Exception as e:
    print(f"❌ ERRORE durante verifica: {e}")
    print()
    print("La PRIVATE_KEY potrebbe essere malformata.")

print("=" * 60)
