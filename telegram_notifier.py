"""
Telegram Notifier per Trading Bot - ENHANCED VERSION
Invia notifiche su Telegram con focus su:
1. Identificazione chiara del decisore (AI vs Sentinel)
2. Dati economici dettagliati da Hyperliquid
3. Diagnostica sistema e stato operativo

Configurazione .env:
    TELEGRAM_BOT_TOKEN=123456:ABC-DEF...  # Token da @BotFather
    TELEGRAM_CHAT_ID=123456789            # Il tuo Chat ID
    TELEGRAM_ENABLED=true                 # Abilita/disabilita notifiche
"""

import os
import requests
import html
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Configurazione
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

# Timeout per le richieste HTTP (in secondi)
TELEGRAM_TIMEOUT = int(os.getenv("TELEGRAM_TIMEOUT", "10"))

# Emoji per identificare il decisore
BRAIN_AI = "🧠"        # AI/GPT decision
BRAIN_SENTINEL = "🛡️"  # Sentinel/Rules decision
BRAIN_MANUAL = "👤"    # Manual intervention

# Costanti economiche
ESTIMATED_FEES_PCT = 0.025  # 0.025% per side = ~0.05% round trip


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
        print("[TG] Telegram non configurato o disabilitato")
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
            print(f"[TG] Messaggio inviato")
            return True
        else:
            print(f"[TG] Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[TG] Exception: {e}")
        return False


def _get_brain_emoji(source: str) -> str:
    """Ritorna l'emoji appropriato per il decisore."""
    source_lower = source.lower() if source else ""
    if "sentinel" in source_lower or "trailing" in source_lower or "stop" in source_lower:
        return BRAIN_SENTINEL
    elif "manual" in source_lower or "user" in source_lower:
        return BRAIN_MANUAL
    else:
        return BRAIN_AI


def _format_source_label(source: str) -> str:
    """Formatta il label del decisore in modo chiaro."""
    source_lower = source.lower() if source else ""
    if "sentinel" in source_lower:
        return "SENTINEL (regole automatiche)"
    elif "trailing" in source_lower:
        return "SENTINEL (trailing stop)"
    elif "stop_loss" in source_lower:
        return "SENTINEL (stop loss)"
    elif "take_profit" in source_lower:
        return "SENTINEL (take profit)"
    elif "micro" in source_lower:
        return "SENTINEL (micro-gain)"
    elif "manual" in source_lower:
        return "MANUALE"
    else:
        return "AI (GPT analysis)"


def _calculate_fees_usd(notional: float) -> float:
    """Calcola le fees stimate per un'operazione."""
    return notional * (ESTIMATED_FEES_PCT / 100)


def _format_pnl_breakdown(
    pnl_gross: float,
    fees_estimated: float,
    funding_paid: float = 0
) -> str:
    """Formatta il breakdown del P&L."""
    pnl_net = pnl_gross - fees_estimated - funding_paid

    lines = []
    lines.append(f"  Lordo: ${pnl_gross:+.2f}")
    lines.append(f"  Fees: -${fees_estimated:.2f}")
    if funding_paid != 0:
        lines.append(f"  Funding: ${funding_paid:+.2f}")
    lines.append(f"  <b>Netto: ${pnl_net:+.2f}</b>")

    return "\n".join(lines)


# ============================================
# MESSAGGI TRADE CON IDENTIFICAZIONE DECISORE
# ============================================

def notify_trade_open(
    symbol: str,
    direction: str,
    leverage: float,
    target_pct: float,
    reason: str,
    source: str = "AI",
    entry_price: Optional[float] = None,
    size: Optional[float] = None,
    notional: Optional[float] = None,
    score: Optional[float] = None,
    trading_mode: Optional[str] = None
) -> bool:
    """
    Notifica apertura posizione con dettagli economici.

    Args:
        source: "AI", "SENTINEL", "MANUAL" - chi ha preso la decisione
    """
    brain = _get_brain_emoji(source)
    source_label = _format_source_label(source)
    safe_reason = html.escape(reason[:400]) if reason else "N/A"

    # Calcola fees stimate
    fees_est = _calculate_fees_usd(notional) if notional else 0

    # Header con identificazione chiara del decisore
    message = f"""{brain} <b>TRADE APERTO</b>

<b>Decisore:</b> {source_label}
<b>Symbol:</b> {symbol}
<b>Direction:</b> {"LONG" if direction.lower() == "long" else "SHORT"}
<b>Leverage:</b> {leverage}x
<b>Allocazione:</b> {target_pct * 100:.1f}% del balance"""

    # Aggiungi dettagli economici se disponibili
    if entry_price:
        message += f"\n\n<b>Entry Price:</b> ${entry_price:,.2f}"
    if size:
        message += f"\n<b>Size:</b> {size:.6f} {symbol}"
    if notional:
        message += f"\n<b>Notional:</b> ${notional:,.2f}"
        message += f"\n<b>Fees stimate:</b> ~${fees_est:.2f}"

    # Trading mode se specificato
    if trading_mode:
        mode_emoji = "🎯" if "MICRO" in trading_mode.upper() else "📊"
        message += f"\n\n{mode_emoji} <b>Mode:</b> {trading_mode}"

    # Score se disponibile
    if score is not None:
        score_emoji = "📈" if score > 0 else "📉"
        message += f"\n{score_emoji} <b>Score:</b> {score:+.1f}"

    message += f"""

<b>Motivo:</b>
<i>{safe_reason}</i>

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_trade_close(
    symbol: str,
    direction: str,
    reason: str,
    source: str = "AI",
    pnl_usd: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
    size: Optional[float] = None,
    duration_minutes: Optional[int] = None,
    fees_paid: Optional[float] = None,
    funding_paid: Optional[float] = None,
    trading_mode: Optional[str] = None
) -> bool:
    """
    Notifica chiusura posizione con breakdown economico completo.
    """
    brain = _get_brain_emoji(source)
    source_label = _format_source_label(source)
    safe_reason = html.escape(reason[:400]) if reason else "N/A"

    # Determina risultato trade
    if pnl_usd is not None:
        if pnl_usd > 0:
            result_emoji = "💰"
            result_text = "PROFITTO"
        elif pnl_usd < 0:
            result_emoji = "📉"
            result_text = "PERDITA"
        else:
            result_emoji = "⚖️"
            result_text = "BREAK-EVEN"
    else:
        result_emoji = "🔴"
        result_text = "CHIUSO"

    message = f"""{brain} <b>TRADE {result_text}</b> {result_emoji}

<b>Decisore:</b> {source_label}
<b>Symbol:</b> {symbol}
<b>Direction:</b> {"LONG" if direction.lower() == "long" else "SHORT"}"""

    # P&L principale
    if pnl_usd is not None:
        pnl_emoji = "📈" if pnl_usd >= 0 else "📉"
        message += f"\n\n{pnl_emoji} <b>P&L:</b> ${pnl_usd:+.2f}"
        if pnl_pct is not None:
            message += f" ({pnl_pct:+.2f}%)"

    # Dettagli trade
    details = []
    if entry_price:
        details.append(f"Entry: ${entry_price:,.2f}")
    if exit_price:
        details.append(f"Exit: ${exit_price:,.2f}")
    if size:
        details.append(f"Size: {size:.6f}")

    if details:
        message += f"\n\n<b>Dettagli Trade:</b>\n" + " | ".join(details)

    # Breakdown costi
    if fees_paid or funding_paid:
        message += f"\n\n<b>Costi:</b>"
        if fees_paid:
            message += f"\n  Fees: ${fees_paid:.2f}"
        if funding_paid:
            message += f"\n  Funding: ${funding_paid:+.2f}"

    # Durata
    if duration_minutes:
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        if hours > 0:
            message += f"\n\n<b>Durata:</b> {hours}h {mins}m"
        else:
            message += f"\n\n<b>Durata:</b> {mins} minuti"

    # Trading mode
    if trading_mode:
        mode_emoji = "🎯" if "MICRO" in trading_mode.upper() else "📊"
        message += f"\n{mode_emoji} <b>Mode:</b> {trading_mode}"

    message += f"""

<b>Motivo chiusura:</b>
<i>{safe_reason}</i>

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_hold(symbol: str, reason: str, source: str = "AI") -> bool:
    """Notifica decisione HOLD (opzionale, può essere disabilitata)."""
    notify_holds = os.getenv("TELEGRAM_NOTIFY_HOLDS", "false").lower() == "true"
    if not notify_holds:
        return True

    brain = _get_brain_emoji(source)
    source_label = _format_source_label(source)
    safe_reason = html.escape(reason[:300]) if reason else "N/A"

    message = f"""{brain} <b>HOLD</b>

<b>Decisore:</b> {source_label}
<b>Symbol:</b> {symbol}

<b>Motivo:</b>
<i>{safe_reason}</i>

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


# ============================================
# MESSAGGI SENTINEL SPECIFICI
# ============================================

def notify_trailing_stop_triggered(
    symbol: str,
    direction: str,
    trigger_price: float,
    entry_price: float,
    peak_price: float,
    pnl_usd: float,
    pnl_pct: float
) -> bool:
    """Notifica attivazione trailing stop dal Sentinel."""

    profit_emoji = "💰" if pnl_usd >= 0 else "📉"

    message = f"""{BRAIN_SENTINEL} <b>TRAILING STOP TRIGGERED</b> {profit_emoji}

<b>Decisore:</b> SENTINEL (trailing stop)
<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}

<b>Prezzi:</b>
  Entry: ${entry_price:,.2f}
  Peak: ${peak_price:,.2f}
  Trigger: ${trigger_price:,.2f}

<b>P&L Finale:</b> ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_stop_loss_triggered(
    symbol: str,
    direction: str,
    trigger_price: float,
    entry_price: float,
    pnl_usd: float,
    pnl_pct: float
) -> bool:
    """Notifica attivazione stop loss dal Sentinel."""

    message = f"""{BRAIN_SENTINEL} <b>STOP LOSS TRIGGERED</b> 🛑

<b>Decisore:</b> SENTINEL (stop loss)
<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}

<b>Prezzi:</b>
  Entry: ${entry_price:,.2f}
  Trigger: ${trigger_price:,.2f}

<b>P&L:</b> ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_take_profit_triggered(
    symbol: str,
    direction: str,
    target_price: float,
    entry_price: float,
    pnl_usd: float,
    pnl_pct: float
) -> bool:
    """Notifica raggiungimento take profit."""

    message = f"""{BRAIN_SENTINEL} <b>TAKE PROFIT</b> 💰

<b>Decisore:</b> SENTINEL (take profit)
<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}

<b>Prezzi:</b>
  Entry: ${entry_price:,.2f}
  Target: ${target_price:,.2f}

<b>P&L:</b> ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


# ============================================
# DIAGNOSTICA SISTEMA
# ============================================

def notify_system_heartbeat(
    balance: float,
    open_positions: List[Dict],
    ai_status: str = "OK",
    sentinel_status: str = "OK",
    last_ai_call: Optional[datetime] = None,
    last_sentinel_check: Optional[datetime] = None
) -> bool:
    """
    Invia heartbeat periodico con stato sistema.
    """
    # Calcola totale unrealized P&L
    total_pnl = sum(p.get("pnl_usd", 0) for p in open_positions)
    pnl_emoji = "📈" if total_pnl >= 0 else "📉"

    # Status icons
    ai_icon = "🟢" if ai_status == "OK" else "🔴"
    sentinel_icon = "🟢" if sentinel_status == "OK" else "🔴"

    message = f"""📡 <b>SYSTEM HEARTBEAT</b>

<b>Account:</b>
  Balance: ${balance:,.2f}
  Unrealized P&L: {pnl_emoji} ${total_pnl:+.2f}
  Posizioni: {len(open_positions)}

<b>Status Componenti:</b>
  {BRAIN_AI} AI: {ai_icon} {ai_status}
  {BRAIN_SENTINEL} Sentinel: {sentinel_icon} {sentinel_status}"""

    if last_ai_call:
        mins_ago = int((datetime.now(timezone.utc) - last_ai_call).total_seconds() / 60)
        message += f"\n  Ultima AI call: {mins_ago}m fa"

    if last_sentinel_check:
        secs_ago = int((datetime.now(timezone.utc) - last_sentinel_check).total_seconds())
        message += f"\n  Ultimo Sentinel check: {secs_ago}s fa"

    # Dettaglio posizioni
    if open_positions:
        message += f"\n\n<b>Posizioni Aperte:</b>"
        for pos in open_positions:
            pos_pnl = pos.get("pnl_usd", 0)
            pos_emoji = "📈" if pos_pnl >= 0 else "📉"
            message += f"\n  {pos.get('symbol')} {pos.get('side', '').upper()}: ${pos_pnl:+.2f}"

    message += f"\n\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

    return send_telegram_message(message)


def notify_position_update(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    pnl_usd: float,
    pnl_pct: float,
    peak_pnl_pct: Optional[float] = None,
    trailing_active: bool = False,
    current_sl: Optional[float] = None,
    leverage: Optional[float] = None,
    duration_minutes: Optional[int] = None
) -> bool:
    """
    Notifica aggiornamento posizione con dettagli economici.
    Utile per monitoraggio periodico.
    """
    pnl_emoji = "📈" if pnl_usd >= 0 else "📉"

    message = f"""📊 <b>POSITION UPDATE</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}"""

    if leverage:
        message += f"\n<b>Leverage:</b> {leverage}x"

    message += f"""

<b>Prezzi:</b>
  Entry: ${entry_price:,.2f}
  Current: ${current_price:,.2f}
  Change: {((current_price - entry_price) / entry_price * 100):+.2f}%

{pnl_emoji} <b>P&L:</b> ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)"""

    if peak_pnl_pct is not None:
        message += f"\n<b>Peak P&L:</b> {peak_pnl_pct:+.2f}%"
        if pnl_pct < peak_pnl_pct:
            drawdown = peak_pnl_pct - pnl_pct
            message += f" (drawdown: -{drawdown:.1f}%)"

    if trailing_active:
        message += f"\n\n🎯 <b>Trailing Stop:</b> ATTIVO"
        if current_sl is not None:
            message += f"\n  SL Level: {current_sl:+.1f}%"

    if duration_minutes:
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        if hours > 0:
            message += f"\n\n<b>Durata:</b> {hours}h {mins}m"
        else:
            message += f"\n\n<b>Durata:</b> {mins} minuti"

    message += f"\n\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

    return send_telegram_message(message)


def notify_bot_started(
    balance: float,
    open_positions: int,
    mode: str = "NORMAL",
    testnet: bool = True
) -> bool:
    """Notifica avvio bot con dettagli configurazione."""
    env_emoji = "🧪" if testnet else "🔴"
    env_text = "TESTNET" if testnet else "MAINNET"

    message = f"""🤖 <b>BOT AVVIATO</b>

{env_emoji} <b>Environment:</b> {env_text}
<b>Mode:</b> {mode}
<b>Balance:</b> ${balance:,.2f}
<b>Posizioni aperte:</b> {open_positions}

<b>Componenti attivi:</b>
  {BRAIN_AI} AI Agent: READY
  {BRAIN_SENTINEL} Sentinel: READY

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_daily_summary(
    balance: float,
    pnl_today: float,
    trades_today: int,
    open_positions: int,
    win_rate: Optional[float] = None,
    fees_today: Optional[float] = None,
    funding_today: Optional[float] = None,
    positions_detail: str = ""
) -> bool:
    """Notifica report giornaliero con metriche economiche."""
    pnl_emoji = "📈" if pnl_today >= 0 else "📉"

    message = f"""📊 <b>REPORT GIORNALIERO</b>

<b>Account:</b>
  Balance: ${balance:,.2f}
  P&L Oggi: {pnl_emoji} ${pnl_today:+.2f}

<b>Trading:</b>
  Trades: {trades_today}
  Posizioni Aperte: {open_positions}"""

    if win_rate is not None:
        message += f"\n  Win Rate: {win_rate:.1f}%"

    # Costi
    if fees_today or funding_today:
        message += f"\n\n<b>Costi Oggi:</b>"
        if fees_today:
            message += f"\n  Fees: ${fees_today:.2f}"
        if funding_today:
            message += f"\n  Funding: ${funding_today:+.2f}"

    # P&L netto
    if fees_today or funding_today:
        total_costs = (fees_today or 0) + (funding_today or 0)
        net_pnl = pnl_today - total_costs
        message += f"\n  <b>P&L Netto:</b> ${net_pnl:+.2f}"

    if positions_detail:
        message += f"\n\n{positions_detail}"

    message += f"\n\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

    return send_telegram_message(message)


# ============================================
# ERRORI E WARNING
# ============================================

def notify_error(
    error_type: str,
    error_message: str,
    source: Optional[str] = None,
    severity: str = "ERROR"
) -> bool:
    """Notifica errore con contesto."""
    severity_emoji = {
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🚨"
    }.get(severity.upper(), "⚠️")

    safe_error_type = html.escape(error_type)
    safe_error_message = html.escape(error_message[:500])
    source_text = f"\n<b>Source:</b> {html.escape(source)}" if source else ""

    message = f"""{severity_emoji} <b>{severity.upper()}</b>

<b>Tipo:</b> {safe_error_type}{source_text}

<b>Messaggio:</b>
<code>{safe_error_message}</code>

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_timeout(timeout_seconds: int, component: str = "BOT") -> bool:
    """Notifica timeout del bot."""
    message = f"""💀 <b>{component} TIMEOUT</b>

Il componente {component} ha superato il timeout di {timeout_seconds} secondi.

Possibili cause:
- Database bloccato
- API Hyperliquid non risponde
- Connessione di rete lenta
- OpenAI API timeout

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"""

    return send_telegram_message(message)


def notify_connection_issue(
    service: str,
    issue: str,
    retry_in: Optional[int] = None
) -> bool:
    """Notifica problemi di connessione."""
    message = f"""🔌 <b>CONNECTION ISSUE</b>

<b>Service:</b> {service}
<b>Issue:</b> {issue}"""

    if retry_in:
        message += f"\n<b>Retry in:</b> {retry_in} secondi"

    message += f"\n\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

    return send_telegram_message(message)


# ============================================
# FUNZIONE PRINCIPALE COMPATIBILE
# ============================================

def notify_trading_decision(
    decision: Dict[str, Any],
    pnl_usd: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    source: str = "AI",
    **kwargs
) -> bool:
    """
    Notifica una decisione di trading basata sul payload.
    Mantiene compatibilità con il vecchio formato.

    Args:
        decision: Dict con operation, symbol, direction, reason, etc.
        pnl_usd: P&L in USD (solo per close)
        pnl_pct: P&L in percentuale (solo per close)
        source: Chi ha preso la decisione (AI, SENTINEL, MANUAL)
        **kwargs: Parametri aggiuntivi per i nuovi campi
    """
    operation = decision.get("operation", "hold")
    symbol = decision.get("symbol", "N/A")
    direction = decision.get("direction", "long")
    reason = decision.get("reason", "No reason provided")
    leverage = decision.get("leverage", 1)
    target_pct = decision.get("target_portion_of_balance", 0)
    trading_mode = decision.get("trading_mode")
    score = decision.get("opening_score") or decision.get("score")

    if operation == "open":
        return notify_trade_open(
            symbol=symbol,
            direction=direction,
            leverage=leverage,
            target_pct=target_pct,
            reason=reason,
            source=source,
            entry_price=kwargs.get("entry_price"),
            size=kwargs.get("size"),
            notional=kwargs.get("notional"),
            score=score,
            trading_mode=trading_mode
        )
    elif operation == "close":
        return notify_trade_close(
            symbol=symbol,
            direction=direction,
            reason=reason,
            source=source,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            entry_price=kwargs.get("entry_price"),
            exit_price=kwargs.get("exit_price"),
            size=kwargs.get("size"),
            duration_minutes=kwargs.get("duration_minutes"),
            fees_paid=kwargs.get("fees_paid"),
            funding_paid=kwargs.get("funding_paid"),
            trading_mode=trading_mode
        )
    elif operation == "hold":
        return notify_hold(symbol, reason, source)
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
        # Test completo
        send_telegram_message(f"""🧪 <b>TEST NOTIFICHE ENHANCED</b>

Verifica identificazione decisore:
  {BRAIN_AI} AI (GPT)
  {BRAIN_SENTINEL} Sentinel (Rules)
  {BRAIN_MANUAL} Manual

{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC""")
