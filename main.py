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

    # Estrai posizioni aperte per il sistema di trailing stop
    open_positions = account_status.get("open_positions", [])
    open_symbols = [p.get("symbol") for p in open_positions]

    print("L'agente sta decidendo le sue azioni!")

    # ===== CICLO PER OGNI SIMBOLO =====
    # Calcola gli score una volta sola
    from trading_agent import calculate_scores_for_symbols, SCORE_THRESHOLD_OPEN
    scores = calculate_scores_for_symbols(indicators_json, sentiment_json, forecasts_json)

    # Ordina i simboli per forza del segnale (più forte prima)
    symbols_by_strength = sorted(
        tickers,
        key=lambda t: abs(scores.get(t, {}).get('net_score', 0)),
        reverse=True
    )

    print(f"\n📊 Ordine valutazione (per forza segnale): {symbols_by_strength}")

    actions_taken = []

    for ticker in symbols_by_strength:
        score_data = scores.get(ticker, {})
        net_score = score_data.get('net_score', 0)
        direction = score_data.get('direction', 'HOLD')

        # Verifica se c'è già una posizione aperta su questo simbolo
        has_position = ticker in open_symbols

        print(f"\n{'='*50}")
        print(f"📈 Valutazione {ticker}: score={net_score:.1f}, direction={direction}, position={'YES' if has_position else 'NO'}")

        # Se c'è già una posizione, gestiscila (HOLD o CLOSE)
        # Se NON c'è posizione e il segnale è forte, considera OPEN
        if not has_position and abs(net_score) < SCORE_THRESHOLD_OPEN:
            print(f"   ⏭️  Skip {ticker}: no position e score {net_score:.1f} sotto soglia {SCORE_THRESHOLD_OPEN}")
            continue

        # Costruisci prompt specifico per questo simbolo
        with open('system_prompt_single.txt', 'r') as f:
            system_prompt_template = f.read()

        # Filtra indicatori per questo ticker
        ticker_indicators = [ind for ind in indicators_json if ind.get('ticker') == ticker]
        ticker_forecasts = [fc for fc in forecasts_json if fc.get('Ticker') == ticker or fc.get('ticker') == ticker] if isinstance(forecasts_json, list) else forecasts_json

        # Trova la posizione per questo ticker (se esiste)
        ticker_position = None
        for pos in open_positions:
            if pos.get("symbol") == ticker:
                ticker_position = pos
                break

        # Costruisci il contesto per questo singolo ticker
        ticker_context = {
            "symbol": ticker,
            "score": score_data,
            "has_position": has_position,
            "position": ticker_position,
            "indicators": ticker_indicators[0] if ticker_indicators else {},
            "sentiment": sentiment_json,
            "forecast": ticker_forecasts,
            "account_balance": account_status.get("balance_usd", 0),
            "open_positions_count": len(open_positions),
            "all_open_symbols": open_symbols
        }

        system_prompt = system_prompt_template.format(
            json.dumps(ticker_context, indent=2, default=str),
            msg_info
        )

        # Chiama AI per questo specifico ticker
        out = previsione_trading_agent(
            system_prompt,
            indicators=ticker_indicators,
            sentiment=sentiment_json,
            forecasts=ticker_forecasts,
            open_positions=[ticker_position] if ticker_position else []
        )

        # Forza il simbolo corretto
        out['symbol'] = ticker

        print(f"   ✅ Decisione per {ticker}: {out.get('operation')} {out.get('direction', '')}")

        # Esegui solo se non è HOLD
        if out.get("operation") != "hold":
            print(f"[EXEC] Esecuzione {out.get('operation')} su {ticker}...")
            bot.execute_signal(out)
            actions_taken.append(out)

            # Gestisci tracking
            if out.get("_delete_tracking") and out.get("symbol"):
                try:
                    deleted = db_utils.delete_position_tracking(out["symbol"])
                    if deleted:
                        print(f"[TRACKING] ✅ Tracking eliminato per {out['symbol']}")
                except Exception as e:
                    print(f"[TRACKING] ⚠️ Errore eliminazione tracking: {e}")

            if out.get("operation") == "open":
                try:
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
                            # Aggiorna open_symbols per il prossimo ciclo
                            if out["symbol"] not in open_symbols:
                                open_symbols.append(out["symbol"])
                            break
                except Exception as e:
                    print(f"[TRACKING] ⚠️ Errore creazione tracking: {e}")

        # Notifica Telegram
        tg.notify_trading_decision(out)

        # Salva operazione nel DB
        op_id = db_utils.log_bot_operation(
            out,
            system_prompt=system_prompt,
            indicators=ticker_indicators,
            news_text=news_txt,
            sentiment=sentiment_json,
            forecasts=ticker_forecasts
        )
        print(f"   💾 Operazione {ticker} salvata con id={op_id}")

    # ===== FINE CICLO =====

    print(f"\n{'='*50}")
    print(f"📊 Riepilogo: {len(actions_taken)} azioni eseguite")
    for action in actions_taken:
        print(f"   - {action.get('operation')} {action.get('symbol')} {action.get('direction', '')}")

    # Salva signal scores nel database per tracciabilità
    if SCORING_ENABLED:
        print("\n[STEP FINAL] Salvataggio signal scores...")
        signal_scores = get_last_signal_scores()
        weights_config = get_scoring_config()
        for symbol, score_result in signal_scores.items():
            try:
                score_id = db_utils.log_signal_score(
                    symbol=symbol,
                    score_result=score_result,
                    weights_config=weights_config
                )
                print(f"   Signal score {symbol} salvato con id={score_id}")
            except Exception as e:
                print(f"   Errore salvataggio score {symbol}: {e}")

except Exception as e:
    # Notifica errore su Telegram
    tg.notify_error(type(e).__name__, str(e), source="trading_agent")

    db_utils.log_error(e, context={"prompt": system_prompt if 'system_prompt' in dir() else "",
                                    "tickers": tickers if 'tickers' in dir() else [],
                                    "indicators":indicators_json if 'indicators_json' in dir() else None,
                                    "news":news_txt if 'news_txt' in dir() else "",
                                    "sentiment":sentiment_json if 'sentiment_json' in dir() else None,
                                    "forecasts":forecasts_json if 'forecasts_json' in dir() else None,
                                    "balance":account_status if 'account_status' in dir() else None
                                    }, source="trading_agent")
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
