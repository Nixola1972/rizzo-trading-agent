#!/usr/bin/env python3
"""
Script per testare tutte le connessioni necessarie al bot
"""
import os
import sys
from dotenv import load_dotenv
import psycopg2

# Carica variabili d'ambiente
load_dotenv()

def test_env_vars():
    """Verifica che tutte le variabili d'ambiente siano presenti"""
    print("🔍 Test 1: Variabili d'ambiente")
    print("-" * 50)

    required_vars = [
        'PRIVATE_KEY',
        'WALLET_ADDRESS',
        'OPENAI_API_KEY',
        'CMC_PRO_API_KEY',
        'DATABASE_URL'
    ]

    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            print(f"  ❌ {var}: MANCANTE")
            missing.append(var)
        else:
            # Mostra solo primi/ultimi caratteri per sicurezza
            if len(value) > 10:
                masked = f"{value[:4]}...{value[-4:]}"
            else:
                masked = "***"
            print(f"  ✅ {var}: {masked}")

    print()
    if missing:
        print(f"❌ Variabili mancanti: {', '.join(missing)}")
        return False

    print("✅ Tutte le variabili d'ambiente presenti")
    return True


def test_database():
    """Testa la connessione al database PostgreSQL"""
    print("🔍 Test 2: Database PostgreSQL")
    print("-" * 50)

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("  ❌ DATABASE_URL non configurato")
        return False

    try:
        # Prova connessione
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"  ✅ Connessione OK")
        print(f"  📊 PostgreSQL version: {version[0].split(',')[0]}")

        # Verifica se le tabelle esistono
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        tables = cursor.fetchall()

        if tables:
            print(f"  📋 Tabelle esistenti: {len(tables)}")
            for table in tables:
                print(f"     - {table[0]}")
        else:
            print("  ⚠️  Nessuna tabella trovata (verranno create al primo avvio)")

        cursor.close()
        conn.close()
        print()
        print("✅ Database PostgreSQL OK")
        return True

    except Exception as e:
        print(f"  ❌ Errore connessione database: {e}")
        print()
        return False


def test_openai():
    """Testa la connessione a OpenAI API"""
    print("🔍 Test 3: OpenAI API")
    print("-" * 50)

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("  ❌ OPENAI_API_KEY non configurato")
        return False

    try:
        import openai
        openai.api_key = api_key

        # Test semplice
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # Prova con una richiesta minima
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )

        print("  ✅ Connessione OpenAI OK")
        print(f"  📊 Model: {response.model}")
        print()
        print("✅ OpenAI API OK")
        return True

    except Exception as e:
        print(f"  ❌ Errore OpenAI API: {e}")
        print()
        return False


def test_coinmarketcap():
    """Testa la connessione a CoinMarketCap API"""
    print("🔍 Test 4: CoinMarketCap API")
    print("-" * 50)

    api_key = os.getenv('CMC_PRO_API_KEY')
    if not api_key:
        print("  ❌ CMC_PRO_API_KEY non configurato")
        return False

    try:
        import requests

        url = 'https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest'
        headers = {
            'X-CMC_PRO_API_KEY': api_key,
        }
        params = {
            'symbol': 'BTC',
            'convert': 'USD'
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            btc_price = data['data']['BTC'][0]['quote']['USD']['price']
            print("  ✅ Connessione CoinMarketCap OK")
            print(f"  💰 BTC Price: ${btc_price:,.2f}")
            print()
            print("✅ CoinMarketCap API OK")
            return True
        else:
            print(f"  ❌ Errore API: Status {response.status_code}")
            print(f"     {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Errore CoinMarketCap API: {e}")
        print()
        return False


def test_hyperliquid():
    """Testa la connessione a HyperLiquid"""
    print("🔍 Test 5: HyperLiquid Exchange")
    print("-" * 50)

    private_key = os.getenv('PRIVATE_KEY')
    wallet_address = os.getenv('WALLET_ADDRESS')

    if not private_key or not wallet_address:
        print("  ❌ PRIVATE_KEY o WALLET_ADDRESS non configurati")
        return False

    try:
        from hyperliquid_trader import HyperLiquidTrader

        # Test con testnet
        bot = HyperLiquidTrader(
            secret_key=private_key,
            account_address=wallet_address,
            testnet=True  # Usa sempre testnet per i test
        )

        # Prova a ottenere lo stato dell'account
        status = bot.get_account_status()

        print("  ✅ Connessione HyperLiquid OK")
        print(f"  📊 Testnet: True")
        print(f"  💰 Balance: ${status['account_value']}")
        print(f"  📍 Posizioni aperte: {len(status['open_positions'])}")
        print()
        print("✅ HyperLiquid Exchange OK")
        return True

    except Exception as e:
        print(f"  ❌ Errore HyperLiquid: {e}")
        print()
        return False


def main():
    """Esegue tutti i test"""
    print("=" * 50)
    print("🤖 TEST CONNESSIONI RIZZO TRADING AGENT")
    print("=" * 50)
    print()

    # Installa openai se mancante
    try:
        import openai
    except ImportError:
        print("📦 Installazione openai...")
        os.system("pip3 install openai")
        print()

    results = {
        'env_vars': test_env_vars(),
        'database': test_database(),
        'openai': test_openai(),
        'coinmarketcap': test_coinmarketcap(),
        'hyperliquid': test_hyperliquid()
    }

    print()
    print("=" * 50)
    print("📊 RIEPILOGO TEST")
    print("=" * 50)

    for test_name, result in results.items():
        status = "✅ OK" if result else "❌ FALLITO"
        print(f"  {test_name.upper()}: {status}")

    print()

    all_passed = all(results.values())
    if all_passed:
        print("🎉 TUTTI I TEST SUPERATI!")
        print("Il bot è pronto per essere avviato.")
        return 0
    else:
        print("⚠️  ALCUNI TEST FALLITI")
        print("Controlla la configurazione nel file .env")
        return 1


if __name__ == "__main__":
    sys.exit(main())
