#!/usr/bin/env python3
"""
Sentinel - Monitoraggio continuo trailing stop e stop loss.

Script leggero che gira frequentemente (ogni 1-2 minuti) per:
1. Controllare i prezzi correnti delle posizioni aperte
2. Aggiornare il peak_price nel database
3. Chiudere posizioni se trailing stop o stop loss viene triggerato

NON fa:
- Chiamate AI
- Calcolo indicatori
- Analisi di mercato

Uso:
    python sentinel.py              # Esegue un singolo controllo
    python sentinel.py --loop       # Esegue in loop continuo
    python sentinel.py --interval 60  # Loop con intervallo personalizzato
"""

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurazione
SENTINEL_ENABLED = os.getenv('SENTINEL_ENABLED', 'true').lower() == 'true'
SENTINEL_INTERVAL = int(os.getenv('SENTINEL_INTERVAL_SECONDS', '60'))
SENTINEL_TELEGRAM_NOTIFY = os.getenv('SENTINEL_TELEGRAM_NOTIFY', 'true').lower() == 'true'

# Trailing Stop Config
TRAILING_STOP_ENABLED = os.getenv('TRAILING_STOP_ENABLED', 'true').lower() == 'true'
TRAILING_STOP_PERCENT = float(os.getenv('TRAILING_STOP_PERCENT', '7'))
TRAILING_STOP_ACTIVATION_PERCENT = float(os.getenv('TRAILING_STOP_ACTIVATION_PERCENT', '3'))
INITIAL_STOP_LOSS_PERCENT = float(os.getenv('INITIAL_STOP_LOSS_PERCENT', '10'))

# Take Profit Config
TAKE_PROFIT_ENABLED = os.getenv('TAKE_PROFIT_ENABLED', 'true').lower() == 'true'
TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '5'))
TAKE_PROFIT_TRIGGER_BOT = os.getenv('TAKE_PROFIT_TRIGGER_BOT', 'true').lower() == 'true'

# Hyperliquid Config
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")


def log(msg: str):
    """Log con timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")


def check_take_profit(position: dict) -> dict:
    """
    Controlla se take profit è triggerato.

    Calcola il P&L reale considerando la leva.

    Returns:
        dict con triggered, reason, pnl_pct
    """
    if not TAKE_PROFIT_ENABLED:
        return {"triggered": False, "reason": "Disabled", "pnl_pct": 0}

    direction = position.get("side", "long").lower()
    entry_price = float(position.get("entry_price", 0))
    current_price = float(position.get("mark_price", 0))

    # Parse leverage (può essere "3x (cross)" o numero)
    leverage_raw = position.get("leverage", 1)
    if isinstance(leverage_raw, str):
        # Estrai il numero da stringhe tipo "3x (cross)"
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        leverage = float(match.group(1)) if match else 1.0
    else:
        leverage = float(leverage_raw)

    if entry_price == 0 or current_price == 0:
        return {"triggered": False, "reason": "No price", "pnl_pct": 0}

    # Calcola movimento prezzo
    if direction == "long":
        price_change_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        price_change_pct = ((entry_price - current_price) / entry_price) * 100

    # P&L reale = movimento prezzo * leva
    pnl_pct = price_change_pct * leverage

    result = {
        "triggered": False,
        "reason": "",
        "pnl_pct": pnl_pct,
        "price_change_pct": price_change_pct,
        "leverage": leverage
    }

    # Check take profit
    if pnl_pct >= TAKE_PROFIT_PERCENT:
        result["triggered"] = True
        result["reason"] = f"TAKE PROFIT: +{pnl_pct:.2f}% P&L (soglia +{TAKE_PROFIT_PERCENT}%, leva {leverage}x)"

    return result


def check_trailing_stop(position: dict, tracking_data: dict = None) -> dict:
    """
    Controlla se trailing stop o stop loss è triggerato.

    Calcola P&L reale considerando la leva.

    Returns:
        dict con triggered, reason, trailing_active, new_peak
    """
    if not TRAILING_STOP_ENABLED:
        return {"triggered": False, "reason": "Disabled", "trailing_active": False}

    direction = position.get("side", "long").lower()
    entry_price = float(position.get("entry_price", 0))
    current_price = float(position.get("mark_price", 0))

    # Parse leverage (può essere "3x (cross)" o numero)
    leverage_raw = position.get("leverage", 1)
    if isinstance(leverage_raw, str):
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
        leverage = float(match.group(1)) if match else 1.0
    else:
        leverage = float(leverage_raw)

    if entry_price == 0 or current_price == 0:
        return {"triggered": False, "reason": "No price", "trailing_active": False}

    # Calcola movimento prezzo (senza leva)
    if direction == "long":
        price_change_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        price_change_pct = ((entry_price - current_price) / entry_price) * 100

    # P&L reale = movimento prezzo * leva
    pnl_pct = price_change_pct * leverage

    # Peak price dal tracking
    if tracking_data:
        peak_price = tracking_data.get("peak_price", current_price)
        trailing_active = tracking_data.get("trailing_active", False)
    else:
        peak_price = current_price
        trailing_active = False

    # Aggiorna peak
    if direction == "long":
        new_peak = max(peak_price, current_price)
    else:
        new_peak = min(peak_price, current_price)

    # Calcola distanza dal peak (movimento prezzo)
    if direction == "long":
        price_change_from_peak_pct = ((current_price - new_peak) / new_peak) * 100
    else:
        price_change_from_peak_pct = ((new_peak - current_price) / new_peak) * 100

    # P&L dal peak = movimento dal peak * leva
    pnl_from_peak_pct = price_change_from_peak_pct * leverage

    # Attiva trailing se P&L reale >= soglia (soglia interpretata come P&L reale)
    if pnl_pct >= TRAILING_STOP_ACTIVATION_PERCENT:
        trailing_active = True

    result = {
        "triggered": False,
        "reason": "",
        "trailing_active": trailing_active,
        "new_peak": new_peak,
        "profit_pct": price_change_pct,  # Movimento prezzo (per compatibilità log)
        "profit_from_peak_pct": price_change_from_peak_pct,  # Per compatibilità log
        "pnl_pct": pnl_pct,  # P&L reale
        "pnl_from_peak_pct": pnl_from_peak_pct,  # P&L reale dal peak
        "leverage": leverage
    }

    # Check stop loss iniziale (usa P&L reale)
    if not trailing_active and pnl_pct <= -INITIAL_STOP_LOSS_PERCENT:
        result["triggered"] = True
        result["reason"] = f"STOP LOSS: {pnl_pct:.2f}% P&L (soglia -{INITIAL_STOP_LOSS_PERCENT}%, leva {leverage}x)"
        return result

    # Check trailing stop (usa P&L reale dal peak)
    if trailing_active and pnl_from_peak_pct <= -TRAILING_STOP_PERCENT:
        result["triggered"] = True
        result["reason"] = f"TRAILING STOP: {-pnl_from_peak_pct:.2f}% P&L dal peak (soglia {TRAILING_STOP_PERCENT}%, leva {leverage}x)"
        return result

    return result


def run_sentinel_check():
    """Esegue un singolo controllo di tutte le posizioni."""

    if not SENTINEL_ENABLED:
        log("Sentinel disabilitato (SENTINEL_ENABLED=false)")
        return

    if not TRAILING_STOP_ENABLED:
        log("Trailing stop disabilitato (TRAILING_STOP_ENABLED=false)")
        return

    if not PRIVATE_KEY or not WALLET_ADDRESS:
        log("PRIVATE_KEY o WALLET_ADDRESS mancanti")
        return

    # Import qui per evitare errori se mancano dipendenze
    try:
        from hyperliquid_trader import HyperLiquidTrader
        import db_utils
        import telegram_notifier as tg
    except ImportError as e:
        log(f"Errore import: {e}")
        return

    try:
        # Connetti a Hyperliquid
        bot = HyperLiquidTrader(
            secret_key=PRIVATE_KEY,
            account_address=WALLET_ADDRESS,
            testnet=TESTNET
        )

        # Ottieni posizioni aperte
        account_status = bot.get_account_status()
        positions = account_status.get("open_positions", [])

        if not positions:
            log("Nessuna posizione aperta")
            return

        log(f"Controllo {len(positions)} posizioni...")

        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("side", "")
            entry_price = pos.get("entry_price", 0)
            mark_price = pos.get("mark_price", 0)
            pnl = pos.get("pnl_usd", 0)

            leverage = pos.get("leverage", 1)

            # Ottieni tracking dal DB
            tracking_data = db_utils.get_position_tracking(symbol)

            # === CHECK TAKE PROFIT (prima del trailing stop) ===
            tp_result = check_take_profit(pos)
            tp_triggered = tp_result.get("triggered", False)
            pnl_pct = tp_result.get("pnl_pct", 0)

            # === CHECK TRAILING STOP ===
            result = check_trailing_stop(pos, tracking_data)

            # Aggiorna tracking nel DB
            db_utils.upsert_position_tracking(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                current_price=mark_price,
                trailing_active=result.get("trailing_active", False)
            )

            profit_pct = result.get("profit_pct", 0)
            profit_from_peak_pct = result.get("profit_from_peak_pct", 0)
            new_peak = result.get("new_peak", mark_price)
            trailing_status = "ACTIVE" if result.get("trailing_active") else "inactive"

            # Determina azione
            action_taken = None
            action_reason = None
            should_close = False
            close_reason = ""

            # Take profit ha priorità
            if tp_triggered:
                should_close = True
                close_reason = tp_result['reason']
                action_taken = "CLOSE_TAKE_PROFIT"
                action_reason = close_reason
            elif result.get("triggered"):
                should_close = True
                close_reason = result['reason']
                if "STOP LOSS" in close_reason:
                    action_taken = "CLOSE_STOP_LOSS"
                else:
                    action_taken = "CLOSE_TRAILING_STOP"
                action_reason = close_reason

            if should_close:
                # CHIUDI POSIZIONE
                log(f"🛑 {symbol}: {close_reason}")
                log(f"   Chiusura posizione {direction.upper()}...")

                try:
                    close_result = bot.exchange.market_close(symbol)
                    log(f"   ✅ Posizione chiusa: {close_result}")

                    # Elimina tracking
                    db_utils.delete_position_tracking(symbol)

                    # Notifica Telegram
                    if SENTINEL_TELEGRAM_NOTIFY:
                        emoji = "💰" if action_taken == "CLOSE_TAKE_PROFIT" else "🛑"
                        try:
                            tg.send_telegram_message(
                                f"{emoji} <b>SENTINEL CLOSE</b>\n\n"
                                f"<b>Symbol:</b> {symbol}\n"
                                f"<b>Direction:</b> {direction.upper()}\n"
                                f"<b>Reason:</b> {close_reason}\n"
                                f"<b>Entry:</b> ${entry_price:.2f}\n"
                                f"<b>Exit:</b> ${mark_price:.2f}\n"
                                f"<b>PnL:</b> ${pnl:.2f} ({pnl_pct:+.2f}%)"
                            )
                        except Exception as e:
                            log(f"   ⚠️ Errore Telegram: {e}")

                    # Trigger bot dopo take profit per rivalutare
                    if action_taken == "CLOSE_TAKE_PROFIT" and TAKE_PROFIT_TRIGGER_BOT:
                        log(f"   🚀 Triggering bot per rivalutare {symbol}...")
                        try:
                            # Lancia main.py in background per questo ticker
                            subprocess.Popen(
                                ["python", "main.py", "--ticker", symbol, "--reason", "take_profit"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True
                            )
                            log(f"   ✅ Bot triggerato per {symbol}")
                        except Exception as e:
                            log(f"   ⚠️ Errore trigger bot: {e}")

                except Exception as e:
                    log(f"   ❌ Errore chiusura: {e}")
            else:
                # Log stato
                peak_info = ""
                if result.get("trailing_active"):
                    peak_info = f", peak_dist={profit_from_peak_pct:.2f}%"
                tp_info = f", P&L={pnl_pct:+.2f}%" if TAKE_PROFIT_ENABLED else ""
                log(f"   {symbol}: {direction.upper()} price_chg={profit_pct:.2f}% trailing={trailing_status}{peak_info}{tp_info}")

            # Log nel database per dashboard
            try:
                db_utils.log_sentinel_check(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    current_price=mark_price,
                    peak_price=new_peak,
                    profit_pct=profit_pct,
                    profit_from_peak_pct=profit_from_peak_pct,
                    trailing_active=result.get("trailing_active", False),
                    action_taken=action_taken,
                    action_reason=action_reason,
                )
            except Exception as e:
                log(f"   ⚠️ Errore log DB: {e}")

    except Exception as e:
        log(f"❌ Errore sentinel: {e}")
        import traceback
        traceback.print_exc()


def run_loop(interval: int = None):
    """Esegue il sentinel in loop continuo."""

    interval = interval or SENTINEL_INTERVAL

    log(f"🔄 Sentinel avviato in loop (intervallo: {interval}s)")
    log(f"   Trailing: {TRAILING_STOP_PERCENT}%, Activation: {TRAILING_STOP_ACTIVATION_PERCENT}%, Stop Loss: {INITIAL_STOP_LOSS_PERCENT}%")
    if TAKE_PROFIT_ENABLED:
        log(f"   Take Profit: {TAKE_PROFIT_PERCENT}% P&L")

    try:
        while True:
            run_sentinel_check()
            log(f"💤 Prossimo check tra {interval}s...")
            time.sleep(interval)
    except KeyboardInterrupt:
        log("Sentinel interrotto (Ctrl+C)")


def main():
    parser = argparse.ArgumentParser(description="Sentinel - Monitoraggio trailing stop")
    parser.add_argument("--loop", action="store_true", help="Esegui in loop continuo")
    parser.add_argument("--interval", type=int, default=None, help="Intervallo in secondi (default: da .env)")
    args = parser.parse_args()

    print("=" * 50)
    print("🛡️  SENTINEL - Trailing Stop Monitor")
    print("=" * 50)

    if args.loop:
        run_loop(args.interval)
    else:
        run_sentinel_check()


if __name__ == "__main__":
    main()
