#!/usr/bin/env python3
"""
Script di verifica configurazione completa del Rizzo Trading Bot
Testa tutte le connessioni e la configurazione prima dell'avvio
"""
import os
import sys
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()

def print_header(text):
    """Stampa un header colorato"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text):
    """Stampa messaggio di successo"""
    print(f"✅ {text}")

def print_error(text):
    """Stampa messaggio di errore"""
    print(f"❌ {text}")

def print_warning(text):
    """Stampa messaggio di warning"""
    print(f"⚠️  {text}")

def print_info(text):
    """Stampa messaggio informativo"""
    print(f"ℹ️  {text}")


# ===========================================
# TEST 1: Variabili d'ambiente
# ===========================================
def test_env_vars():
    print_header("TEST 1: Variabili d'Ambiente")

    all_ok = True

    # AI Provider
    ai_provider = os.getenv('AI_PROVIDER', 'openai').lower()
    print_info(f"AI Provider configurato: {ai_provider}")

    required_vars = {
        'PRIVATE_KEY': 'Chiave privata wallet Ethereum',
        'WALLET_ADDRESS': 'Indirizzo wallet Ethereum',
        'CMC_PRO_API_KEY': 'API key CoinMarketCap',
        'DATABASE_URL': 'URL database PostgreSQL',
        'POSTGRES_NETWORK': 'Network Docker PostgreSQL',
    }

    # Aggiungi API key AI richiesta
    if ai_provider == 'openrouter':
        required_vars['OPENROUTER_API_KEY'] = 'API key OpenRouter'
        required_vars['OPENROUTER_MODEL'] = 'Modello OpenRouter'
    else:
        required_vars['OPENAI_API_KEY'] = 'API key OpenAI'

    print("\nVariabili richieste:")
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            print_error(f"{var}: MANCANTE ({description})")
            all_ok = False
        else:
            # Mostra solo primi/ultimi caratteri per sicurezza
            if len(value) > 10:
                masked = f"{value[:6]}...{value[-4:]}"
            else:
                masked = "***"
            print_success(f"{var}: {masked}")

    # Variabili opzionali
    testnet = os.getenv('TESTNET', 'true')
    verbose = os.getenv('VERBOSE', 'true')
    print(f"\nConfigurazioni:")
    print_info(f"TESTNET: {testnet}")
    print_info(f"VERBOSE: {verbose}")

    if testnet.lower() != 'true':
        print_warning("TESTNET=false - Stai usando MAINNET (soldi veri)!")

    return all_ok


# ===========================================
# TEST 2: Database PostgreSQL
# ===========================================
def test_database():
    print_header("TEST 2: Database PostgreSQL")

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print_error("DATABASE_URL non configurato")
        return False

    try:
        import psycopg2
        print_info("Tentativo connessione al database...")

        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Verifica versione PostgreSQL
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print_success(f"Connessione OK")
        print_info(f"PostgreSQL: {version[0].split(',')[0]}")

        # Verifica database
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print_info(f"Database: {db_name}")

        # Verifica tabelle
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        if tables:
            print_success(f"Tabelle esistenti ({len(tables)}):")
            for table in tables:
                print(f"    - {table[0]}")
        else:
            print_warning("Nessuna tabella trovata (verranno create al primo avvio)")

        # Test permessi
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS _test_permissions (id SERIAL PRIMARY KEY);")
            cursor.execute("DROP TABLE _test_permissions;")
            conn.commit()
            print_success("Permessi scrittura OK")
        except Exception as e:
            print_error(f"Permessi scrittura limitati: {e}")

        cursor.close()
        conn.close()
        return True

    except ImportError:
        print_error("Libreria psycopg2 non installata")
        print_info("Installa con: pip install psycopg2-binary")
        return False
    except Exception as e:
        print_error(f"Errore connessione database: {e}")
        return False


# ===========================================
# TEST 3: AI Provider (OpenAI o OpenRouter)
# ===========================================
def test_ai_provider():
    print_header("TEST 3: AI Provider")

    ai_provider = os.getenv('AI_PROVIDER', 'openai').lower()

    try:
        from openai import OpenAI

        if ai_provider == 'openrouter':
            api_key = os.getenv('OPENROUTER_API_KEY')
            model = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')

            if not api_key:
                print_error("OPENROUTER_API_KEY mancante")
                return False

            print_info(f"Testing OpenRouter con modello: {model}")
            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )

        else:
            api_key = os.getenv('OPENAI_API_KEY')
            model = "gpt-4-turbo"

            if not api_key:
                print_error("OPENAI_API_KEY mancante")
                return False

            print_info(f"Testing OpenAI con modello: {model}")
            client = OpenAI(api_key=api_key)

        # Test chiamata semplice
        print_info("Invio richiesta di test...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'OK' if you can read this"}
            ],
            max_tokens=10
        )

        result = response.choices[0].message.content
        print_success("Connessione AI OK")
        print_info(f"Risposta: {result}")
        print_info(f"Modello usato: {response.model}")

        return True

    except ImportError:
        print_error("Libreria openai non installata")
        print_info("Installa con: pip install openai")
        return False
    except Exception as e:
        print_error(f"Errore AI Provider: {e}")
        return False


# ===========================================
# TEST 4: CoinMarketCap API
# ===========================================
def test_coinmarketcap():
    print_header("TEST 4: CoinMarketCap API")

    api_key = os.getenv('CMC_PRO_API_KEY')
    if not api_key:
        print_error("CMC_PRO_API_KEY mancante")
        return False

    try:
        import requests

        url = 'https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest'
        headers = {'X-CMC_PRO_API_KEY': api_key}
        params = {'symbol': 'BTC', 'convert': 'USD'}

        print_info("Fetching BTC price...")
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            btc_price = data['data']['BTC'][0]['quote']['USD']['price']
            print_success("CoinMarketCap API OK")
            print_info(f"BTC Price: ${btc_price:,.2f}")
            return True
        else:
            print_error(f"Errore API: Status {response.status_code}")
            print_info(f"Response: {response.text}")
            return False

    except ImportError:
        print_error("Libreria requests non installata")
        print_info("Installa con: pip install requests")
        return False
    except Exception as e:
        print_error(f"Errore CoinMarketCap: {e}")
        return False


# ===========================================
# TEST 5: HyperLiquid Connection
# ===========================================
def test_hyperliquid():
    print_header("TEST 5: HyperLiquid Exchange")

    private_key = os.getenv('PRIVATE_KEY')
    wallet_address = os.getenv('WALLET_ADDRESS')
    testnet = os.getenv('TESTNET', 'true').lower() == 'true'

    if not private_key or not wallet_address:
        print_error("PRIVATE_KEY o WALLET_ADDRESS mancanti")
        return False

    try:
        from hyperliquid_trader import HyperLiquidTrader

        print_info(f"Modalità: {'TESTNET' if testnet else 'MAINNET'}")
        print_info("Connessione a HyperLiquid...")

        bot = HyperLiquidTrader(
            secret_key=private_key,
            account_address=wallet_address,
            testnet=testnet
        )

        # Ottieni stato account
        status = bot.get_account_status()

        print_success("Connessione HyperLiquid OK")
        print_info(f"Account Value: ${status.get('account_value', 0)}")
        print_info(f"Withdrawable: ${status.get('withdrawable', 0)}")
        print_info(f"Posizioni aperte: {len(status.get('open_positions', []))}")

        if status.get('open_positions'):
            print("\nPosizioni aperte:")
            for pos in status['open_positions']:
                print(f"  - {pos.get('coin')}: {pos.get('szi')} @ ${pos.get('entryPx')}")

        return True

    except ImportError as e:
        print_error(f"Import error: {e}")
        print_info("Assicurati che hyperliquid-python-sdk sia installato")
        return False
    except Exception as e:
        print_error(f"Errore HyperLiquid: {e}")
        return False


# ===========================================
# TEST 6: Moduli Trading Agent
# ===========================================
def test_trading_modules():
    print_header("TEST 6: Moduli Trading Agent")

    modules = {
        'indicators': 'Indicatori tecnici',
        'news_feed': 'Feed notizie',
        'sentiment': 'Sentiment analysis',
        'forecaster': 'Price forecasting',
        'trading_agent': 'AI trading agent',
        'hyperliquid_trader': 'HyperLiquid trader',
        'db_utils': 'Database utilities'
    }

    all_ok = True
    for module, description in modules.items():
        try:
            __import__(module)
            print_success(f"{module}.py - {description}")
        except Exception as e:
            print_error(f"{module}.py - {description}: {e}")
            all_ok = False

    return all_ok


# ===========================================
# MAIN
# ===========================================
def main():
    print("\n" + "🤖 " * 20)
    print("  RIZZO TRADING BOT - VERIFICA CONFIGURAZIONE")
    print("🤖 " * 20)

    results = {
        'Variabili d\'ambiente': test_env_vars(),
        'Database PostgreSQL': test_database(),
        'AI Provider': test_ai_provider(),
        'CoinMarketCap API': test_coinmarketcap(),
        'HyperLiquid Exchange': test_hyperliquid(),
        'Moduli Python': test_trading_modules()
    }

    # Riepilogo
    print_header("RIEPILOGO VERIFICHE")

    all_passed = True
    for test_name, result in results.items():
        if result:
            print_success(f"{test_name}: OK")
        else:
            print_error(f"{test_name}: FALLITO")
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print_success("TUTTI I TEST SUPERATI!")
        print_info("\n🚀 Il bot è pronto per essere avviato:")
        print("   docker compose -f docker-compose.existing-postgres.yml up -d")
        print("\n   Per vedere i log:")
        print("   docker compose -f docker-compose.existing-postgres.yml logs -f trading-bot")
        return 0
    else:
        print_error("ALCUNI TEST FALLITI")
        print_info("\nCorreggi gli errori sopra prima di avviare il bot.")
        print_info("Controlla il file .env e verifica le API keys.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
