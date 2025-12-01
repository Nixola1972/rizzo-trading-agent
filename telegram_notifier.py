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
                      target_pct: float, reason: str,
                      entry_price: Optional[float] = None,
                      size: Optional[float] = None,
                      value_usd: Optional[float] = None) -> bool:
    """Notifica apertura posizione (messaggio breve)."""

    # Formato breve per apertura
    price_str = f" @ ${entry_price:,.2f}" if entry_price else ""
    size_str = f" ({size} {symbol})" if size else ""
    value_str = f" [${value_usd:.2f}]" if value_usd else ""

    message = f"""🟢 <b>APERTO</b> {symbol} {direction.upper()} {leverage}x{price_str}{size_str}{value_str}

🕐 {datetime.now().strftime('%H:%M:%S')}"""

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


def notify_trade_summary(
    symbol: str,
    direction: str,
    leverage: float,
    # Apertura
    entry_price: float,
    entry_time: datetime,
    size: float,
    value_usd: float,
    margin: float,
    # Chiusura
    exit_price: float,
    exit_time: datetime,
    close_reason: str,
    # P&L
    pnl_usd: float,
    pnl_pct: float,
    # Stats opzionali
    max_pnl_usd: Optional[float] = None,
    max_pnl_pct: Optional[float] = None,
    min_pnl_usd: Optional[float] = None,
    min_pnl_pct: Optional[float] = None,
    score_open: Optional[float] = None,
    score_close: Optional[float] = None,
    # Balance
    balance: Optional[float] = None,
    pnl_today: Optional[float] = None,
    pnl_week: Optional[float] = None,
) -> bool:
    """
    Notifica riassuntiva completa di un trade chiuso.
    Include tutte le info di apertura, chiusura e performance.
    """

    # Determina se profit o loss
    is_profit = pnl_usd >= 0
    result_emoji = "✅" if is_profit else "❌"
    result_label = "GUADAGNO" if is_profit else "PERDITA"
    pnl_emoji = "💰" if is_profit else "💸"

    # Calcola durata
    duration = exit_time - entry_time
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m"
    else:
        duration_str = f"{minutes}m"

    # Escape close reason
    safe_reason = html.escape(close_reason[:100]) if close_reason else "N/A"

    # Stats section (opzionale)
    stats_section = ""
    if max_pnl_usd is not None or score_open is not None:
        stats_lines = []
        if max_pnl_usd is not None and max_pnl_pct is not None:
            stats_lines.append(f"├─ Max P&L: +${max_pnl_usd:.2f} (+{max_pnl_pct:.1f}%)")
        if min_pnl_usd is not None and min_pnl_pct is not None:
            stats_lines.append(f"├─ Min P&L: ${min_pnl_usd:.2f} ({min_pnl_pct:.1f}%)")
        if score_open is not None and score_close is not None:
            stats_lines.append(f"└─ Score: {score_open:.1f} → {score_close:.1f}")
        elif score_open is not None:
            stats_lines.append(f"└─ Score apertura: {score_open:.1f}")

        if stats_lines:
            # Fix last line to use └─
            if len(stats_lines) > 0:
                stats_lines[-1] = stats_lines[-1].replace("├─", "└─")
            stats_section = f"""
📊 <b>STATS</b>
{chr(10).join(stats_lines)}
"""

    # Balance section (opzionale)
    balance_section = ""
    if balance is not None:
        balance_change = f" ({'+' if pnl_usd >= 0 else ''}{pnl_usd:.2f})"
        balance_lines = [f"💼 Balance: ${balance:,.2f}{balance_change}"]
        if pnl_today is not None or pnl_week is not None:
            extra = []
            if pnl_today is not None:
                extra.append(f"Oggi: ${pnl_today:+.2f}")
            if pnl_week is not None:
                extra.append(f"Week: ${pnl_week:+.2f}")
            if extra:
                balance_lines.append(f"📈 {' | '.join(extra)}")
        balance_section = f"""
══════════════════════════════
{chr(10).join(balance_lines)}"""

    message = f"""📊 <b>TRADE COMPLETATO</b> {result_emoji}

══════════════════════════════
{pnl_emoji} <b>{result_label}:</b> ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)
══════════════════════════════

📈 <b>APERTURA</b>
├─ {symbol} {direction.upper()} {leverage}x
├─ Entry: ${entry_price:,.2f}
├─ Size: {size} {symbol}
├─ Valore: ${value_usd:.2f}
├─ Margine: ${margin:.2f}
└─ 🕐 {entry_time.strftime('%d/%m %H:%M')}

📉 <b>CHIUSURA</b>
├─ Exit: ${exit_price:,.2f}
├─ Motivo: {safe_reason}
├─ Durata: {duration_str}
└─ 🕐 {exit_time.strftime('%d/%m %H:%M')}{stats_section}{balance_section}"""

    return send_telegram_message(message)


def notify_ai_cycle_summary(
    reason: str,
    tickers_analyzed: list,
    decisions: list,
    scores: dict = None,
    duration_seconds: float = None,
    balance: float = None,
    open_positions: int = None,
) -> bool:
    """
    Notifica riassuntiva di un ciclo AI completato.

    Args:
        reason: Motivo del trigger (scheduled, take_profit, stop_loss, etc.)
        tickers_analyzed: Lista ticker analizzati
        decisions: Lista di decisioni [{symbol, operation, direction, reason}, ...]
        scores: Dict di score per simbolo {BTC: {net: -5.2, bull: 3, bear: 8}, ...}
        duration_seconds: Durata del ciclo in secondi
        balance: Balance attuale
        open_positions: Numero posizioni aperte
    """
    # Emoji per reason
    reason_emoji_map = {
        "scheduled": "⏰",
        "take_profit": "💰",
        "stop_loss": "🛑",
        "trailing_stop": "📉",
        "reversal": "🔄",
        "volatility_spike": "⚡",
        "position_closed": "🔒",
        "manual": "👤",
        "score_signal": "📊",
    }
    reason_emoji = reason_emoji_map.get(reason, "🤖")

    # Formatta reason in italiano
    reason_label_map = {
        "scheduled": "Ciclo programmato",
        "take_profit": "Take Profit raggiunto",
        "stop_loss": "Stop Loss triggerato",
        "trailing_stop": "Trailing Stop",
        "reversal": "Score reversal",
        "volatility_spike": "Spike volatilità",
        "position_closed": "Posizione chiusa",
        "manual": "Manuale",
        "score_signal": "Segnale score",
    }
    reason_label = reason_label_map.get(reason, reason)

    # Durata
    duration_str = ""
    if duration_seconds:
        if duration_seconds >= 60:
            mins = int(duration_seconds // 60)
            secs = int(duration_seconds % 60)
            duration_str = f" ({mins}m {secs}s)"
        else:
            duration_str = f" ({int(duration_seconds)}s)"

    # Conta azioni
    opens = [d for d in decisions if d.get("operation") == "open"]
    closes = [d for d in decisions if d.get("operation") == "close"]
    holds = [d for d in decisions if d.get("operation") == "hold"]

    # Costruisci sezione decisioni
    decisions_lines = []
    for d in decisions:
        op = d.get("operation", "?")
        sym = d.get("symbol", "?")
        direction = d.get("direction", "")
        ai_reason = d.get("reason", "")[:50]  # Troncato

        if op == "open":
            op_emoji = "🟢"
            op_text = f"OPEN {direction.upper()}"
        elif op == "close":
            op_emoji = "🔴"
            op_text = "CLOSE"
        else:
            op_emoji = "⚪"
            op_text = "HOLD"

        # Score per questo simbolo
        score_str = ""
        if scores and sym in scores:
            net = scores[sym].get("net", 0)
            score_str = f" [score: {net:+.1f}]"

        decisions_lines.append(f"{op_emoji} <b>{sym}</b>: {op_text}{score_str}")
        if ai_reason and op != "hold":
            decisions_lines.append(f"   <i>{html.escape(ai_reason)}</i>")

    # Se nessuna azione, mostra che tutto è HOLD
    if not decisions_lines:
        decisions_lines = ["⚪ Nessuna azione (tutte HOLD)"]

    # Account info
    account_info = ""
    if balance is not None or open_positions is not None:
        parts = []
        if balance is not None:
            parts.append(f"💼 ${balance:,.2f}")
        if open_positions is not None:
            parts.append(f"📈 {open_positions} pos")
        account_info = f"\n{' | '.join(parts)}"

    # Statistiche ciclo
    stats = f"✅ {len(opens)} open | 🔴 {len(closes)} close | ⚪ {len(holds)} hold"

    message = f"""🤖 <b>AI CYCLE COMPLETATO</b>{duration_str}

{reason_emoji} <b>Trigger:</b> {reason_label}
📋 <b>Ticker:</b> {', '.join(tickers_analyzed)}

━━━━━━━━━━━━━━━━
<b>DECISIONI:</b>
{chr(10).join(decisions_lines)}
━━━━━━━━━━━━━━━━
{stats}{account_info}

🕐 {datetime.now().strftime('%H:%M:%S')}"""

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
