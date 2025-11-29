"""
Telegram Notifier per Trading Bot
Invia notifiche su Telegram per trades, errori e report giornalieri.

Configurazione .env:
    TELEGRAM_BOT_TOKEN=123456:ABC-DEF...  # Token da @BotFather
    TELEGRAM_CHAT_ID=123456789            # Il tuo Chat ID
    TELEGRAM_ENABLED=true                 # Abilita/disabilita notifiche
"""

import os
import requests
import html
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Configurazione
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

# Timeout per le richieste HTTP (in secondi)
TELEGRAM_TIMEOUT = int(os.getenv("TELEGRAM_TIMEOUT", "10"))


def is_telegram_configured() -> bool:
    """Verifica se Telegram è configurato correttamente."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and TELEGRAM_ENABLED)


def send_telegram_message(message: str, parse_mode: str = "HTML") -> bool:
    """
    Invia un messaggio su Telegram.

    Args:
        message: Il testo del messaggio (supporta HTML)
        parse_mode: "HTML" o "Markdown"

    Returns:
        True se inviato con successo, False altrimenti
    """
    if not is_telegram_configured():
        print("⚠️ Telegram non configurato o disabilitato")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
        if response.status_code == 200:
            print(f"✅ Telegram: messaggio inviato")
            return True
        else:
            print(f"❌ Telegram error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False


# ============================================
# MESSAGGI PRE-FORMATTATI
# ============================================

def notify_trade_open(symbol: str, direction: str, leverage: float,
                      target_pct: float, reason: str) -> bool:
    """Notifica apertura posizione."""
    # Escape HTML characters in reason to prevent parsing errors
    safe_reason = html.escape(reason[:500])
    message = f"""🟢 <b>TRADE APERTO</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}
<b>Leverage:</b> {leverage}x
<b>Size:</b> {target_pct * 100:.1f}% del balance

<b>Motivo AI:</b>
<i>{safe_reason}</i>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_trade_close(symbol: str, direction: str, reason: str,
                       pnl_usd: Optional[float] = None,
                       pnl_pct: Optional[float] = None) -> bool:
    """Notifica chiusura posizione."""
    # Escape HTML characters in reason to prevent parsing errors
    safe_reason = html.escape(reason[:500])
    pnl_text = ""
    if pnl_usd is not None:
        pnl_emoji = "📈" if pnl_usd >= 0 else "📉"
        pnl_text = f"\n<b>P&L:</b> {pnl_emoji} ${pnl_usd:+.2f}"
        if pnl_pct is not None:
            pnl_text += f" ({pnl_pct:+.2f}%)"

    message = f"""🔴 <b>TRADE CHIUSO</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}{pnl_text}

<b>Motivo AI:</b>
<i>{safe_reason}</i>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_hold(symbol: str, reason: str) -> bool:
    """Notifica decisione HOLD (opzionale, può essere disabilitata)."""
    # Di default non notifichiamo gli HOLD per non spammare
    notify_holds = os.getenv("TELEGRAM_NOTIFY_HOLDS", "false").lower() == "true"
    if not notify_holds:
        return True

    # Escape HTML characters in reason to prevent parsing errors
    safe_reason = html.escape(reason[:300])
    message = f"""⚪ <b>HOLD</b>

<b>Symbol:</b> {symbol}

<b>Motivo AI:</b>
<i>{safe_reason}</i>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_error(error_type: str, error_message: str,
                 source: Optional[str] = None) -> bool:
    """Notifica errore."""
    # Escape HTML characters to prevent parsing errors
    safe_error_type = html.escape(error_type)
    safe_error_message = html.escape(error_message[:500])
    source_text = f"\n<b>Source:</b> {html.escape(source)}" if source else ""

    message = f"""⚠️ <b>ERRORE BOT</b>

<b>Tipo:</b> {safe_error_type}{source_text}

<b>Messaggio:</b>
<code>{safe_error_message}</code>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_bot_started(balance: float, open_positions: int) -> bool:
    """Notifica avvio bot."""
    message = f"""🤖 <b>BOT AVVIATO</b>

<b>Balance:</b> ${balance:,.2f}
<b>Posizioni aperte:</b> {open_positions}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_daily_summary(balance: float, pnl_today: float,
                         trades_today: int, open_positions: int,
                         positions_detail: str = "") -> bool:
    """Notifica report giornaliero."""
    pnl_emoji = "📈" if pnl_today >= 0 else "📉"

    message = f"""📊 <b>REPORT GIORNALIERO</b>

<b>Balance:</b> ${balance:,.2f}
<b>P&L Oggi:</b> {pnl_emoji} ${pnl_today:+.2f}
<b>Trades Oggi:</b> {trades_today}
<b>Posizioni Aperte:</b> {open_positions}

{positions_detail}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_timeout(timeout_seconds: int) -> bool:
    """Notifica timeout del bot."""
    message = f"""💀 <b>BOT TIMEOUT</b>

Il bot ha superato il timeout di {timeout_seconds} secondi ed è stato terminato.

Possibili cause:
• Database bloccato
• API non risponde
• Connessione di rete lenta

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


# ============================================
# FUNZIONE PRINCIPALE PER IL BOT
# ============================================

def notify_trading_decision(decision: Dict[str, Any],
                            pnl_usd: Optional[float] = None,
                            pnl_pct: Optional[float] = None) -> bool:
    """
    Notifica una decisione di trading basata sul payload.

    Args:
        decision: Dict con operation, symbol, direction, reason, etc.
        pnl_usd: P&L in USD (solo per close)
        pnl_pct: P&L in percentuale (solo per close)
    """
    operation = decision.get("operation", "hold")
    symbol = decision.get("symbol", "N/A")
    direction = decision.get("direction", "long")
    reason = decision.get("reason", "No reason provided")
    leverage = decision.get("leverage", 1)
    target_pct = decision.get("target_portion_of_balance", 0)

    if operation == "open":
        return notify_trade_open(symbol, direction, leverage, target_pct, reason)
    elif operation == "close":
        return notify_trade_close(symbol, direction, reason, pnl_usd, pnl_pct)
    elif operation == "hold":
        return notify_hold(symbol, reason)
    else:
        return False


# ============================================
# TEST
# ============================================

if __name__ == "__main__":
    print(f"Telegram configurato: {is_telegram_configured()}")
    print(f"Token: {'***' + TELEGRAM_BOT_TOKEN[-10:] if TELEGRAM_BOT_TOKEN else 'Non impostato'}")
    print(f"Chat ID: {TELEGRAM_CHAT_ID or 'Non impostato'}")
    print(f"Enabled: {TELEGRAM_ENABLED}")

    if is_telegram_configured():
        # Test message
        send_telegram_message("🧪 <b>Test</b>\n\nIl bot Telegram funziona correttamente!")
