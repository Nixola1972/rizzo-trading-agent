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
import argparse
import db_utils
import telegram_notifier as tg
from dotenv import load_dotenv
load_dotenv()

# Trade Journal - Import opzionale per retrocompatibilità
try:
    import trade_journal as tj
    TRADE_JOURNAL_ENABLED = True
except ImportError:
    TRADE_JOURNAL_ENABLED = False
    tj = None

# ===== MICRO-GAIN CONFIGURATION =====
MICRO_GAIN_ENABLED = os.getenv('MICRO_GAIN_ENABLED', 'false').lower() == 'true'
MICRO_GAIN_TARGET_PERCENT = float(os.getenv('MICRO_GAIN_TARGET_PERCENT', '0.15'))
MICRO_GAIN_LEVERAGE = int(os.getenv('MICRO_GAIN_LEVERAGE', '5'))
MICRO_GAIN_PORTION = float(os.getenv('MICRO_GAIN_PORTION', '0.3'))
SCORE_THRESHOLD_HOLD = float(os.getenv('SCORE_THRESHOLD_HOLD', '15'))
SCORE_THRESHOLD_NORMAL = float(os.getenv('SCORE_THRESHOLD_OPEN', '20'))  # Soglia per mode NORMAL

def determine_trading_mode(net_score: float) -> str:
    """
    Determina il trading mode in base allo score.

    Returns:
        'MICRO_GAIN': Score tra HOLD e NORMAL (es. 15-20)
        'NORMAL': Score >= NORMAL threshold
        'HOLD': Score < HOLD threshold (non dovrebbe arrivare qui)
    """
    if not MICRO_GAIN_ENABLED:
        return "NORMAL"

    abs_score = abs(net_score)

    if abs_score < SCORE_THRESHOLD_HOLD:
        return "HOLD"
    elif abs_score < SCORE_THRESHOLD_NORMAL:
        return "MICRO_GAIN"
    else:
        return "NORMAL"

# Parse arguments
parser = argparse.ArgumentParser(description="Trading Bot")
parser.add_argument("--ticker", type=str, help="Analizza solo questo ticker (es: ETH)")
parser.add_argument("--reason", type=str, default="manual", help="Motivo trigger (es: take_profit)")
args = parser.parse_args()

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
    all_tickers = ['BTC', 'ETH', 'SOL']

    # Se specificato --ticker, analizza solo quello
    if args.ticker:
        ticker_upper = args.ticker.upper()
        if ticker_upper in all_tickers:
            tickers = [ticker_upper]
            print(f"🎯 Modalità singolo ticker: {ticker_upper} (reason: {args.reason})")
        else:
            print(f"⚠️ Ticker {ticker_upper} non supportato. Uso tutti: {all_tickers}")
            tickers = all_tickers
    else:
        tickers = all_tickers

    indicators_txt, indicators_json  = analyze_multiple_tickers(tickers)
    news_txt = fetch_latest_news()
    # whale_alerts_txt = format_whale_alerts_to_string()
    sentiment_txt, sentiment_json  = get_sentiment()
    forecasts_txt, forecasts_json = get_crypto_forecasts()

    # Salva sentiment nella cache per il sentinel
    if sentiment_json:
        try:
            cache_id = db_utils.save_sentiment_cache(
                value=sentiment_json.get('valore'),
                classification=sentiment_json.get('classificazione'),
                source_timestamp=sentiment_json.get('timestamp'),
                raw=sentiment_json
            )
            print(f"[CACHE] Sentiment salvato in cache con id={cache_id}")
        except Exception as e:
            print(f"[CACHE] ⚠️ Errore salvataggio sentiment cache: {e}")

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
        # Con MICRO_GAIN: apri anche se score è tra HOLD e OPEN threshold
        is_micro_gain_candidate = False
        if not has_position:
            min_threshold = SCORE_THRESHOLD_HOLD if MICRO_GAIN_ENABLED else SCORE_THRESHOLD_OPEN
            if abs(net_score) < min_threshold:
                print(f"   ⏭️  Skip {ticker}: no position e score {net_score:.1f} sotto soglia {min_threshold}")
                continue
            # Marca come candidato MICRO_GAIN
            if MICRO_GAIN_ENABLED and abs(net_score) < SCORE_THRESHOLD_OPEN:
                is_micro_gain_candidate = True
                print(f"   🎯 {ticker}: score {net_score:.1f} in range MICRO_GAIN ({SCORE_THRESHOLD_HOLD}-{SCORE_THRESHOLD_OPEN})")

        # === MICRO_GAIN: Forza OPEN senza chiedere all'AI ===
        if is_micro_gain_candidate:
            micro_direction = "long" if net_score > 0 else "short"
            print(f"   🎯 MICRO_GAIN AUTO-OPEN: {ticker} {micro_direction.upper()} (score={net_score:.1f})")

            out = {
                "operation": "open",
                "symbol": ticker,
                "direction": micro_direction,
                "reason": f"MICRO_GAIN auto-open: score {net_score:.1f} in range [{SCORE_THRESHOLD_HOLD}-{SCORE_THRESHOLD_OPEN}]",
                "target_portion_of_balance": MICRO_GAIN_PORTION,  # From .env MICRO_GAIN_PORTION
                "leverage": MICRO_GAIN_LEVERAGE,  # From .env MICRO_GAIN_LEVERAGE
                "trading_mode": "MICRO_GAIN",
                "opening_score": net_score,
                "micro_gain_target": MICRO_GAIN_TARGET_PERCENT
            }

            print(f"[EXEC] MICRO_GAIN: Apertura {micro_direction.upper()} su {ticker}...")
            bot.execute_signal(out)
            actions_taken.append(out)

            # Crea tracking per MICRO_GAIN
            try:
                current_status = bot.get_account_status()
                for pos in current_status.get("open_positions", []):
                    if pos.get("symbol") == ticker:
                        db_utils.upsert_position_tracking(
                            symbol=pos["symbol"],
                            direction=pos["side"],
                            entry_price=pos["entry_price"],
                            current_price=pos["mark_price"],
                            trailing_active=False,
                            opening_score=net_score,
                            trading_mode="MICRO_GAIN"
                        )
                        print(f"[TRACKING] 🎯 MICRO_GAIN tracking creato per {ticker} @ {pos['entry_price']}")

                        # Trade Journal: registra apertura
                        if TRADE_JOURNAL_ENABLED:
                            try:
                                trade_uuid = tj.open_trade(
                                    symbol=ticker,
                                    direction=pos["side"].upper(),
                                    trading_mode="MICRO_GAIN",
                                    entry_price=float(pos["entry_price"]),
                                    size=float(pos.get("size", 0)),
                                    leverage=MICRO_GAIN_LEVERAGE,
                                    score=net_score,
                                    sl_percent=float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '3.0')),
                                    tp_percent=MICRO_GAIN_TARGET_PERCENT
                                )
                                print(f"[JOURNAL] 📒 Trade registrato: {trade_uuid[:8]}...")
                            except Exception as je:
                                print(f"[JOURNAL] ⚠️ Errore registrazione trade: {je}")

                        if ticker not in open_symbols:
                            open_symbols.append(ticker)
                        break
            except Exception as e:
                print(f"[TRACKING] ⚠️ Errore creazione tracking MICRO_GAIN: {e}")

            # Notifica e salva
            tg.notify_trading_decision(out)
            op_id = db_utils.log_bot_operation(
                out,
                system_prompt="MICRO_GAIN auto-open",
                indicators=[ind for ind in indicators_json if ind.get('ticker') == ticker],
                news_text=news_txt,
                sentiment=sentiment_json,
                forecasts=forecasts_json
            )
            print(f"   💾 Operazione MICRO_GAIN {ticker} salvata con id={op_id}")
            continue  # Passa al prossimo ticker

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
            # Determina trading mode per nuove posizioni
            trading_mode = "NORMAL"
            if out.get("operation") == "open":
                trading_mode = determine_trading_mode(net_score)
                out['trading_mode'] = trading_mode
                out['opening_score'] = net_score
                if trading_mode == "MICRO_GAIN":
                    out['micro_gain_target'] = MICRO_GAIN_TARGET_PERCENT
                    print(f"   🎯 MICRO_GAIN MODE: target +{MICRO_GAIN_TARGET_PERCENT}% P&L")

            print(f"[EXEC] Esecuzione {out.get('operation')} su {ticker} (mode: {trading_mode})...")
            bot.execute_signal(out)
            actions_taken.append(out)

            # Trade Journal: registra chiusura PRIMA di eliminare tracking
            if out.get("operation") == "close" and TRADE_JOURNAL_ENABLED:
                try:
                    open_trade = tj.get_open_trade(ticker)
                    if open_trade:
                        # Ottieni prezzo di chiusura
                        current_status = bot.get_account_status()
                        exit_price = 0
                        for pos in current_status.get("open_positions", []):
                            if pos.get("symbol") == ticker:
                                exit_price = float(pos.get("mark_price", 0))
                                break
                        if exit_price == 0:
                            # Posizione già chiusa, usa ultimo prezzo noto
                            exit_price = float(open_trade.get('entry_price', 0))

                        result = tj.close_trade(
                            trade_uuid=open_trade['trade_uuid'],
                            exit_price=exit_price,
                            close_reason=tj.CloseReason.AI_DECISION,
                            close_score=net_score if net_score else None
                        )
                        print(f"[JOURNAL] 📒 Trade chiuso: Net P&L ${result['net_pnl_usd']:.2f}")
                except Exception as je:
                    print(f"[JOURNAL] ⚠️ Errore chiusura trade: {je}")

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
                                trailing_active=False,
                                opening_score=net_score,
                                trading_mode=trading_mode
                            )
                            mode_emoji = "🎯" if trading_mode == "MICRO_GAIN" else "📊"
                            print(f"[TRACKING] {mode_emoji} Tracking creato per {out['symbol']} @ {pos['entry_price']} (mode: {trading_mode}, score: {net_score:.1f})")

                            # Trade Journal: registra apertura
                            if TRADE_JOURNAL_ENABLED:
                                try:
                                    sl_pct = float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '3.0')) if trading_mode == "MICRO_GAIN" else float(os.getenv('NORMAL_STOP_LOSS_PERCENT', '5.0'))
                                    tp_pct = MICRO_GAIN_TARGET_PERCENT if trading_mode == "MICRO_GAIN" else None
                                    trade_uuid = tj.open_trade(
                                        symbol=ticker,
                                        direction=pos["side"].upper(),
                                        trading_mode=trading_mode,
                                        entry_price=float(pos["entry_price"]),
                                        size=float(pos.get("size", 0)),
                                        leverage=int(out.get("leverage", MICRO_GAIN_LEVERAGE if trading_mode == "MICRO_GAIN" else 1)),
                                        score=net_score,
                                        sl_percent=sl_pct,
                                        tp_percent=tp_pct
                                    )
                                    print(f"[JOURNAL] 📒 Trade registrato: {trade_uuid[:8]}...")
                                except Exception as je:
                                    print(f"[JOURNAL] ⚠️ Errore registrazione trade: {je}")

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

    # Salva signal scores nel database per tracciabilità (usa gli score calcolati all'inizio)
    if SCORING_ENABLED:
        print("\n[STEP FINAL] Salvataggio signal scores...")
        weights_config = get_scoring_config()
        # Usa 'scores' calcolato all'inizio, non get_last_signal_scores()
        for symbol, score_result in scores.items():
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
