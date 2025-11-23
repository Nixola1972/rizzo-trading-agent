from indicators import analyze_multiple_tickers
from news_feed import fetch_latest_news
from trading_agent import previsione_trading_agent, get_last_signal_scores, get_scoring_config, SCORING_ENABLED
from whalealert import format_whale_alerts_to_string
from sentiment import get_sentiment
from forecaster import get_crypto_forecasts
from hyperliquid_trader import HyperLiquidTrader
import os
import json
import signal
import sys
import db_utils
import telegram_notifier as tg
from dotenv import load_dotenv
load_dotenv()

# Timeout globale configurabile da .env (default 5 minuti)
GLOBAL_TIMEOUT = int(os.getenv("BOT_TIMEOUT_SECONDS", "300"))

def timeout_handler(signum, frame):
    print(f"❌ TIMEOUT: Script exceeded {GLOBAL_TIMEOUT} seconds. Exiting...")
    # Notifica timeout su Telegram
    tg.notify_timeout(GLOBAL_TIMEOUT)
    sys.exit(1)

# Imposta il timeout globale
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(GLOBAL_TIMEOUT)
print(f"⏱️ Global timeout set: {GLOBAL_TIMEOUT} seconds (BOT_TIMEOUT_SECONDS)")

# Collegamento ad Hyperliquid
TESTNET = os.getenv("TESTNET", "true").lower() == "true"  # Legge da .env
VERBOSE = os.getenv("VERBOSE", "true").lower() == "true"  # Legge da .env
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

if not PRIVATE_KEY or not WALLET_ADDRESS:
    raise RuntimeError("PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env")
try:
    bot = HyperLiquidTrader(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        testnet=TESTNET
    )

    # Calcolo delle informazioni in input per Ticker
    tickers = ['BTC', 'ETH', 'SOL']
    indicators_txt, indicators_json  = analyze_multiple_tickers(tickers)
    news_txt = fetch_latest_news()
    # whale_alerts_txt = format_whale_alerts_to_string()
    sentiment_txt, sentiment_json  = get_sentiment()
    forecasts_txt, forecasts_json = get_crypto_forecasts()


    msg_info=f"""<indicatori>\n{indicators_txt}\n</indicatori>\n\n
    <news>\n{news_txt}</news>\n\n
    <sentiment>\n{sentiment_txt}\n</sentiment>\n\n
    <forecast>\n{forecasts_txt}\n</forecast>\n\n"""

    account_status = bot.get_account_status()
    portfolio_data = f"{json.dumps(account_status)}"
    snapshot_id = db_utils.log_account_status(account_status)
    print(f"[db_utils] Operazione inserita con id={snapshot_id}")


    # Creating System prompt
    with open('system_prompt.txt', 'r') as f:
        system_prompt = f.read()
    system_prompt = system_prompt.format(portfolio_data, msg_info)
        
    print("L'agente sta decidendo la sua azione!")
    # Estrai posizioni aperte per il sistema di trailing stop
    open_positions = account_status.get("open_positions", [])

    # Passa indicatori, sentiment, forecast e posizioni aperte
    out = previsione_trading_agent(
        system_prompt,
        indicators=indicators_json,
        sentiment=sentiment_json,
        forecasts=forecasts_json,
        open_positions=open_positions
    )

    print(f"[DEBUG] Tipo risposta AI: {type(out)}")
    print(f"[DEBUG] Contenuto risposta: {out}")

    print("[STEP 1] Esecuzione segnale su Hyperliquid...")
    bot.execute_signal(out)
    print("[STEP 1] ✅ Completato")

    # Se la posizione è stata chiusa, elimina il tracking
    if out.get("_delete_tracking") and out.get("symbol"):
        try:
            deleted = db_utils.delete_position_tracking(out["symbol"])
            if deleted:
                print(f"[TRACKING] ✅ Tracking eliminato per {out['symbol']}")
        except Exception as e:
            print(f"[TRACKING] ⚠️ Errore eliminazione tracking: {e}")

    # Se è stata aperta una nuova posizione, crea il tracking
    if out.get("operation") == "open" and out.get("symbol"):
        try:
            # Ottieni il prezzo corrente per inizializzare il tracking
            current_status = bot.get_account_status()
            for pos in current_status.get("open_positions", []):
                if pos.get("symbol") == out["symbol"]:
                    db_utils.upsert_position_tracking(
                        symbol=pos["symbol"],
                        direction=pos["side"],
                        entry_price=pos["entry_price"],
                        current_price=pos["mark_price"],
                        trailing_active=False
                    )
                    print(f"[TRACKING] ✅ Tracking creato per {out['symbol']} @ {pos['entry_price']}")
                    break
        except Exception as e:
            print(f"[TRACKING] ⚠️ Errore creazione tracking: {e}")

    # Notifica Telegram della decisione
    print("[STEP 2] Invio notifica Telegram...")
    tg.notify_trading_decision(out)
    print("[STEP 2] ✅ Completato")

    print("[STEP 3] Salvataggio operazione nel DB...")
    print(f"[DEBUG] indicators_json type: {type(indicators_json)}")
    print(f"[DEBUG] sentiment_json type: {type(sentiment_json)}")
    print(f"[DEBUG] forecasts_json type: {type(forecasts_json)}")
    op_id = db_utils.log_bot_operation(out, system_prompt=system_prompt, indicators=indicators_json, news_text=news_txt, sentiment=sentiment_json, forecasts=forecasts_json)
    print(f"[STEP 3] ✅ Operazione inserita con id={op_id}")

    # Salva signal scores nel database per tracciabilità
    if SCORING_ENABLED:
        print("[STEP 4] Salvataggio signal scores...")
        signal_scores = get_last_signal_scores()
        print(f"[DEBUG] signal_scores type: {type(signal_scores)}, keys: {signal_scores.keys() if isinstance(signal_scores, dict) else 'N/A'}")
        weights_config = get_scoring_config()
        for symbol, score_result in signal_scores.items():
            print(f"[DEBUG] {symbol} score_result type: {type(score_result)}")
            try:
                score_id = db_utils.log_signal_score(
                    symbol=symbol,
                    score_result=score_result,
                    weights_config=weights_config
                )
                print(f"[STEP 4] Signal score {symbol} salvato con id={score_id}")
            except Exception as e:
                print(f"[STEP 4] Errore salvataggio score {symbol}: {e}")

except Exception as e:
    # Notifica errore su Telegram
    tg.notify_error(type(e).__name__, str(e), source="trading_agent")

    db_utils.log_error(e, context={"prompt": system_prompt, "tickers": tickers,
                                    "indicators":indicators_json, "news":news_txt,
                                    "sentiment":sentiment_json, "forecasts":forecasts_json,
                                    "balance":account_status
                                    }, source="trading_agent")
    print(f"An error occurred: {e}")