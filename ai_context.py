#!/usr/bin/env python3
"""
AI Context Builder - Costruisce contesto arricchito per le decisioni AI.

Questo modulo centralizza tutti gli indici e le metriche che vengono
passate all'AI per migliorare la qualità delle decisioni di trading.

Categorie di indici:
1. Indicatori Tecnici Avanzati (ATR, RSI trend, MACD trend, etc.)
2. Performance per Condizioni (win rate by mode/direction, etc.)
3. Risk Metrics (drawdown, exposure, profit factor)
4. Contesto di Mercato (correlazione BTC, market regime)
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import deque
import statistics

from dotenv import load_dotenv
load_dotenv()

# Testing Mode - quando abilitato, usa metriche neutre invece di quelle storiche
TESTING_MODE = os.getenv("TESTING_MODE", "false").lower() == "true"
if TESTING_MODE:
    print("[AI_CONTEXT] ⚠️ TESTING_MODE attivo: metriche storiche disabilitate")

# Import opzionali per retrocompatibilità
try:
    import trade_journal as tj
    TRADE_JOURNAL_ENABLED = True
except ImportError:
    TRADE_JOURNAL_ENABLED = False
    tj = None

try:
    import db_utils
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False
    db_utils = None


# ============================================================================
# 1. INDICATORI TECNICI AVANZATI
# ============================================================================

def get_technical_indicators_advanced(indicators_data: dict) -> dict:
    """
    Estrae indicatori tecnici avanzati dai dati degli indicatori.

    Args:
        indicators_data: Dizionario con i dati degli indicatori per un simbolo

    Returns:
        dict con indicatori avanzati calcolati
    """
    result = {
        "atr_current": None,
        "atr_percentile": None,  # "high", "normal", "low"
        "atr_vs_avg_ratio": None,
        "rsi_trend": None,  # "rising", "falling", "stable"
        "rsi_current": None,
        "rsi_zone": None,  # "overbought", "oversold", "neutral"
        "macd_histogram_trend": None,  # "rising", "falling", "stable"
        "macd_current": None,
        "price_vs_ema20_pct": None,
        "price_vs_ema50_pct": None,
        "ema_alignment": None,  # "bullish", "bearish", "mixed"
        "volume_ratio": None,  # current vs avg
        "volume_trend": None,  # "increasing", "decreasing", "stable"
        "pivot_distances": None,  # distanze da S1, S2, R1, R2
    }

    if not indicators_data:
        return result

    try:
        # === ATR (Average True Range) ===
        longer_term = indicators_data.get("longer_term_15m", {})
        atr_current = longer_term.get("atr_14_current")
        atr_3 = longer_term.get("atr_3_current")

        if atr_current:
            result["atr_current"] = round(atr_current, 4)

            # Calcola ATR percentile rispetto alla media storica
            # ATR alto = volatilità alta, ATR basso = volatilità bassa
            if atr_3 and atr_current:
                ratio = atr_3 / atr_current if atr_current > 0 else 1
                if ratio > 1.3:
                    result["atr_percentile"] = "high"  # Volatilità in aumento
                elif ratio < 0.7:
                    result["atr_percentile"] = "low"   # Volatilità in calo
                else:
                    result["atr_percentile"] = "normal"
                result["atr_vs_avg_ratio"] = round(ratio, 2)

        # === RSI Trend ===
        intraday = indicators_data.get("intraday", {})
        rsi_series = intraday.get("rsi_14", [])

        if rsi_series and len(rsi_series) >= 3:
            rsi_current = rsi_series[-1]
            result["rsi_current"] = round(rsi_current, 1)

            # Zona RSI
            if rsi_current >= 70:
                result["rsi_zone"] = "overbought"
            elif rsi_current <= 30:
                result["rsi_zone"] = "oversold"
            else:
                result["rsi_zone"] = "neutral"

            # Trend RSI (ultimi 3 valori)
            rsi_recent = rsi_series[-3:]
            if len(rsi_recent) >= 3:
                delta1 = rsi_recent[-1] - rsi_recent[-2]
                delta2 = rsi_recent[-2] - rsi_recent[-3]
                avg_delta = (delta1 + delta2) / 2

                if avg_delta > 2:
                    result["rsi_trend"] = "rising"
                elif avg_delta < -2:
                    result["rsi_trend"] = "falling"
                else:
                    result["rsi_trend"] = "stable"

        # === MACD Histogram Trend ===
        macd_series = intraday.get("macd", [])

        if macd_series and len(macd_series) >= 3:
            result["macd_current"] = round(macd_series[-1], 6)

            # Trend MACD (ultimi 3 valori)
            macd_recent = macd_series[-3:]
            if len(macd_recent) >= 3:
                delta1 = macd_recent[-1] - macd_recent[-2]
                delta2 = macd_recent[-2] - macd_recent[-3]

                if delta1 > 0 and delta2 > 0:
                    result["macd_histogram_trend"] = "rising"
                elif delta1 < 0 and delta2 < 0:
                    result["macd_histogram_trend"] = "falling"
                else:
                    result["macd_histogram_trend"] = "mixed"

        # === Price vs EMA ===
        current = indicators_data.get("current", {})
        price = current.get("price")
        ema20 = current.get("ema20")
        ema50 = longer_term.get("ema_50_current")

        if price and ema20:
            pct_diff = ((price - ema20) / ema20) * 100
            result["price_vs_ema20_pct"] = round(pct_diff, 2)

        if price and ema50:
            pct_diff = ((price - ema50) / ema50) * 100
            result["price_vs_ema50_pct"] = round(pct_diff, 2)

        # EMA Alignment
        if ema20 and ema50:
            ema20_current = longer_term.get("ema_20_current", ema20)
            if ema20_current > ema50:
                result["ema_alignment"] = "bullish"  # EMA20 sopra EMA50
            elif ema20_current < ema50:
                result["ema_alignment"] = "bearish"  # EMA20 sotto EMA50
            else:
                result["ema_alignment"] = "neutral"

        # === Volume ===
        vol_current = longer_term.get("volume_current")
        vol_avg = longer_term.get("volume_average")

        if vol_current and vol_avg and vol_avg > 0:
            ratio = vol_current / vol_avg
            result["volume_ratio"] = round(ratio, 2)

            if ratio > 1.5:
                result["volume_trend"] = "high"
            elif ratio < 0.5:
                result["volume_trend"] = "low"
            else:
                result["volume_trend"] = "normal"

        # === Pivot Points Distance ===
        pivot = indicators_data.get("pivot_points", {})
        if pivot and price:
            pp = pivot.get("pp", 0)
            s1 = pivot.get("s1", 0)
            s2 = pivot.get("s2", 0)
            r1 = pivot.get("r1", 0)
            r2 = pivot.get("r2", 0)

            if pp > 0:
                result["pivot_distances"] = {
                    "to_pp_pct": round(((price - pp) / pp) * 100, 2),
                    "to_s1_pct": round(((price - s1) / s1) * 100, 2) if s1 > 0 else None,
                    "to_s2_pct": round(((price - s2) / s2) * 100, 2) if s2 > 0 else None,
                    "to_r1_pct": round(((price - r1) / r1) * 100, 2) if r1 > 0 else None,
                    "to_r2_pct": round(((price - r2) / r2) * 100, 2) if r2 > 0 else None,
                    "nearest_support": "S1" if abs(price - s1) < abs(price - s2) else "S2",
                    "nearest_resistance": "R1" if abs(price - r1) < abs(price - r2) else "R2",
                }

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo indicatori tecnici: {e}")

    return result


# ============================================================================
# 2. PERFORMANCE PER CONDIZIONI
# ============================================================================

def get_performance_by_conditions(symbol: str, days: int = 14) -> dict:
    """
    Recupera statistiche di performance segmentate per condizioni.

    Args:
        symbol: Simbolo da analizzare
        days: Giorni di storico da considerare

    Returns:
        dict con performance segmentate
    """
    # Valori neutri per TESTING_MODE
    neutral_result = {
        "win_rate_by_mode": {
            "MICRO_GAIN": 50.0,
            "MICRO_PAY": 50.0,
            "NORMAL": 50.0,
        },
        "win_rate_by_direction": {
            "LONG": 50.0,
            "SHORT": 50.0,
        },
        "avg_pnl_by_mode": {
            "MICRO_GAIN": 0.0,
            "MICRO_PAY": 0.0,
            "NORMAL": 0.0,
        },
        "avg_duration_by_mode": {
            "MICRO_GAIN": None,
            "MICRO_PAY": None,
            "NORMAL": None,
        },
        "consecutive_losses": 0,
        "consecutive_wins": 0,
        "last_trade_result": None,
        "trades_today": 0,
        "pnl_today": 0.0,
        "_testing_mode": True,  # Flag per indicare che sono valori neutri
    }

    # Se TESTING_MODE attivo, ritorna valori neutri
    if TESTING_MODE:
        return neutral_result

    result = {
        "win_rate_by_mode": {
            "MICRO_GAIN": None,
            "MICRO_PAY": None,
            "NORMAL": None,
        },
        "win_rate_by_direction": {
            "LONG": None,
            "SHORT": None,
        },
        "avg_pnl_by_mode": {
            "MICRO_GAIN": None,
            "MICRO_PAY": None,
            "NORMAL": None,
        },
        "avg_duration_by_mode": {
            "MICRO_GAIN": None,
            "MICRO_PAY": None,
            "NORMAL": None,
        },
        "consecutive_losses": 0,
        "consecutive_wins": 0,
        "last_trade_result": None,  # "win" o "loss"
        "trades_today": 0,
        "pnl_today": 0.0,
    }

    if not TRADE_JOURNAL_ENABLED:
        return result

    try:
        # Recupera trades chiusi per questo simbolo
        from datetime import datetime, timedelta

        # Query trades per simbolo
        closed_trades = tj.get_closed_trades(symbol=symbol, days=days)

        if not closed_trades:
            return result

        # Calcola statistiche per mode
        trades_by_mode = {"MICRO_GAIN": [], "MICRO_PAY": [], "NORMAL": []}
        trades_by_direction = {"LONG": [], "SHORT": []}

        for trade in closed_trades:
            mode = trade.get("trading_mode", "NORMAL")
            direction = trade.get("direction", "LONG").upper()
            net_pnl = float(trade.get("net_pnl_usd") or 0)
            is_win = net_pnl > 0

            if mode in trades_by_mode:
                trades_by_mode[mode].append({
                    "pnl": net_pnl,
                    "win": is_win,
                    "duration": trade.get("duration_seconds", 0)
                })

            if direction in trades_by_direction:
                trades_by_direction[direction].append({
                    "pnl": net_pnl,
                    "win": is_win
                })

        # Calcola win rate e avg PnL per mode
        for mode, trades in trades_by_mode.items():
            if trades:
                wins = sum(1 for t in trades if t["win"])
                result["win_rate_by_mode"][mode] = round((wins / len(trades)) * 100, 1)
                result["avg_pnl_by_mode"][mode] = round(
                    sum(t["pnl"] for t in trades) / len(trades), 2
                )
                durations = [t["duration"] for t in trades if t["duration"]]
                if durations:
                    result["avg_duration_by_mode"][mode] = round(
                        sum(durations) / len(durations) / 60, 1  # in minuti
                    )

        # Calcola win rate per direction
        for direction, trades in trades_by_direction.items():
            if trades:
                wins = sum(1 for t in trades if t["win"])
                result["win_rate_by_direction"][direction] = round(
                    (wins / len(trades)) * 100, 1
                )

        # Consecutive losses/wins (ordina per data)
        sorted_trades = sorted(closed_trades, key=lambda x: x.get("closed_at", ""), reverse=True)

        if sorted_trades:
            # Ultimo trade
            last_pnl = float(sorted_trades[0].get("net_pnl_usd") or 0)
            result["last_trade_result"] = "win" if last_pnl > 0 else "loss"

            # Conta consecutive
            consecutive = 0
            is_winning_streak = last_pnl > 0

            for trade in sorted_trades:
                pnl = float(trade.get("net_pnl_usd") or 0)
                if (pnl > 0) == is_winning_streak:
                    consecutive += 1
                else:
                    break

            if is_winning_streak:
                result["consecutive_wins"] = consecutive
            else:
                result["consecutive_losses"] = consecutive

        # Trades oggi
        today = datetime.now(timezone.utc).date()
        trades_today = [
            t for t in closed_trades
            if t.get("closed_at") and
            datetime.fromisoformat(str(t["closed_at"]).replace("Z", "+00:00")).date() == today
        ]
        result["trades_today"] = len(trades_today)
        result["pnl_today"] = round(sum(float(t.get("net_pnl_usd") or 0) for t in trades_today), 2)

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo performance by conditions: {e}")

    return result


def get_global_performance_stats(days: int = 7) -> dict:
    """
    Recupera statistiche di performance globali (tutti i simboli).

    Returns:
        dict con metriche globali
    """
    # Valori neutri per TESTING_MODE
    neutral_result = {
        "total_trades": 0,
        "win_rate": 50.0,  # Neutro
        "profit_factor": 1.0,  # Neutro (break-even)
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "expectancy": 0.0,
        "best_symbol": None,
        "worst_symbol": None,
        "_testing_mode": True,  # Flag per indicare che sono valori neutri
    }

    # Se TESTING_MODE attivo, ritorna valori neutri
    if TESTING_MODE:
        return neutral_result

    result = {
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": None,  # gross_profit / gross_loss
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "expectancy": 0.0,  # (win_rate * avg_win) - (loss_rate * avg_loss)
        "best_symbol": None,
        "worst_symbol": None,
    }

    if not TRADE_JOURNAL_ENABLED:
        return result

    try:
        summary = tj.get_trade_summary(days)
        if summary:
            result["total_trades"] = summary.get("total_trades", 0)
            result["win_rate"] = float(summary.get("win_rate") or 0)

            # Profit factor
            gross_profit = float(summary.get("total_profit") or 0)
            gross_loss = abs(float(summary.get("total_loss") or 0))
            if gross_loss > 0:
                result["profit_factor"] = round(gross_profit / gross_loss, 2)

            result["avg_win"] = float(summary.get("avg_win") or 0)
            result["avg_loss"] = float(summary.get("avg_loss") or 0)
            result["largest_win"] = float(summary.get("max_win") or 0)
            result["largest_loss"] = float(summary.get("max_loss") or 0)

            # Expectancy
            win_rate_decimal = result["win_rate"] / 100
            loss_rate_decimal = 1 - win_rate_decimal
            result["expectancy"] = round(
                (win_rate_decimal * result["avg_win"]) -
                (loss_rate_decimal * abs(result["avg_loss"])),
                2
            )

        # Best/Worst symbol
        by_symbol = tj.get_summary_by_symbol(days)
        if by_symbol:
            sorted_symbols = sorted(
                by_symbol,
                key=lambda x: float(x.get("net_pnl") or 0),
                reverse=True
            )
            if sorted_symbols:
                result["best_symbol"] = {
                    "symbol": sorted_symbols[0].get("symbol"),
                    "pnl": float(sorted_symbols[0].get("net_pnl") or 0),
                    "win_rate": float(sorted_symbols[0].get("win_rate") or 0)
                }
                result["worst_symbol"] = {
                    "symbol": sorted_symbols[-1].get("symbol"),
                    "pnl": float(sorted_symbols[-1].get("net_pnl") or 0),
                    "win_rate": float(sorted_symbols[-1].get("win_rate") or 0)
                }

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo global performance: {e}")

    return result


# ============================================================================
# 3. RISK METRICS
# ============================================================================

def get_risk_metrics(account_status: dict, days: int = 7) -> dict:
    """
    Calcola metriche di rischio correnti.

    Args:
        account_status: Stato account da Hyperliquid
        days: Giorni per calcoli storici

    Returns:
        dict con metriche di rischio
    """
    result = {
        "current_drawdown_pct": None,
        "max_drawdown_7d_pct": None,
        "total_exposure_pct": None,  # somma posizioni / balance
        "largest_position_pct": None,
        "position_count": 0,
        "available_margin_pct": None,
        "risk_level": "low",  # "low", "medium", "high", "critical"
        "max_position_loss_pct": None,  # worst current position P&L
        "total_unrealized_pnl": 0.0,
    }

    if not account_status:
        return result

    try:
        balance = float(account_status.get("balance_usd") or 0)
        positions = account_status.get("open_positions", [])

        result["position_count"] = len(positions)

        if balance > 0:
            # Exposure totale
            total_notional = 0
            worst_pnl_pct = 0
            total_unrealized = 0

            for pos in positions:
                size = float(pos.get("size") or 0)
                entry_price = float(pos.get("entry_price") or 0)
                mark_price = float(pos.get("mark_price") or 0)
                pnl = float(pos.get("pnl_usd") or 0)

                notional = size * mark_price
                total_notional += notional
                total_unrealized += pnl

                # Calcola P&L % per questa posizione
                if entry_price > 0:
                    direction = pos.get("side", "long").lower()
                    if direction == "long":
                        pnl_pct = ((mark_price - entry_price) / entry_price) * 100
                    else:
                        pnl_pct = ((entry_price - mark_price) / entry_price) * 100

                    # Parse leverage
                    leverage_raw = pos.get("leverage", 1)
                    if isinstance(leverage_raw, str):
                        import re
                        match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                        leverage = float(match.group(1)) if match else 1.0
                    else:
                        leverage = float(leverage_raw)

                    real_pnl_pct = pnl_pct * leverage

                    if real_pnl_pct < worst_pnl_pct:
                        worst_pnl_pct = real_pnl_pct

            result["total_exposure_pct"] = round((total_notional / balance) * 100, 1)
            result["max_position_loss_pct"] = round(worst_pnl_pct, 2) if worst_pnl_pct < 0 else None
            result["total_unrealized_pnl"] = round(total_unrealized, 2)

            # Largest position
            if positions:
                largest = max(positions, key=lambda p: float(p.get("size") or 0) * float(p.get("mark_price") or 0))
                largest_notional = float(largest.get("size") or 0) * float(largest.get("mark_price") or 0)
                result["largest_position_pct"] = round((largest_notional / balance) * 100, 1)

            # Available margin (stima)
            margin_used = account_status.get("margin_used", 0)
            if margin_used:
                result["available_margin_pct"] = round(((balance - float(margin_used)) / balance) * 100, 1)

        # Risk level
        exposure = result["total_exposure_pct"] or 0
        position_count = result["position_count"]
        worst_loss = abs(result["max_position_loss_pct"] or 0)

        if exposure > 200 or worst_loss > 15 or position_count >= 5:
            result["risk_level"] = "critical"
        elif exposure > 150 or worst_loss > 10 or position_count >= 4:
            result["risk_level"] = "high"
        elif exposure > 100 or worst_loss > 5 or position_count >= 3:
            result["risk_level"] = "medium"
        else:
            result["risk_level"] = "low"

        # Drawdown da Trade Journal
        if TRADE_JOURNAL_ENABLED:
            try:
                # Calcola drawdown dal peak equity
                equity_history = tj.get_equity_history(days)
                if equity_history:
                    peak = max(e.get("equity", 0) for e in equity_history)
                    current = equity_history[-1].get("equity", 0) if equity_history else balance
                    if peak > 0:
                        dd = ((peak - current) / peak) * 100
                        result["current_drawdown_pct"] = round(dd, 2) if dd > 0 else 0
                        result["max_drawdown_7d_pct"] = round(dd, 2)  # Semplificato
            except Exception:
                pass

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo risk metrics: {e}")

    return result


# ============================================================================
# 4. CONTESTO DI MERCATO
# ============================================================================

def get_market_context(all_indicators: List[dict]) -> dict:
    """
    Analizza il contesto di mercato generale.

    Args:
        all_indicators: Lista di indicatori per tutti i simboli

    Returns:
        dict con contesto di mercato
    """
    result = {
        "btc_trend": None,  # "bullish", "bearish", "neutral"
        "btc_rsi": None,
        "btc_momentum": None,  # "strong_up", "up", "neutral", "down", "strong_down"
        "market_correlation": None,  # correlazione media tra asset
        "market_regime": None,  # "trending_up", "trending_down", "ranging", "volatile"
        "overall_sentiment_score": None,
        "volatility_regime": None,  # "high", "normal", "low"
        # Derivatives data
        "funding_rates": {},  # funding rate per coin
        "open_interest": {},  # OI per coin
        "correlations": {},  # price return correlations
    }

    if not all_indicators:
        return result

    try:
        # Trova BTC indicators
        btc_data = None
        for ind in all_indicators:
            if ind.get("ticker", "").upper() == "BTC":
                btc_data = ind
                break

        if btc_data:
            current = btc_data.get("current", {})
            intraday = btc_data.get("intraday", {})
            longer_term = btc_data.get("longer_term_15m", {})

            # BTC RSI
            rsi_series = intraday.get("rsi_14", [])
            if rsi_series:
                result["btc_rsi"] = round(rsi_series[-1], 1)

            # BTC Trend (basato su EMA)
            price = current.get("price")
            ema20 = current.get("ema20")
            ema50 = longer_term.get("ema_50_current")

            if price and ema20 and ema50:
                if price > ema20 > ema50:
                    result["btc_trend"] = "bullish"
                elif price < ema20 < ema50:
                    result["btc_trend"] = "bearish"
                else:
                    result["btc_trend"] = "neutral"

            # BTC Momentum (basato su MACD)
            macd_series = intraday.get("macd", [])
            if macd_series and len(macd_series) >= 2:
                macd_current = macd_series[-1]
                macd_prev = macd_series[-2]
                macd_delta = macd_current - macd_prev

                if macd_current > 0 and macd_delta > 0:
                    result["btc_momentum"] = "strong_up"
                elif macd_current > 0:
                    result["btc_momentum"] = "up"
                elif macd_current < 0 and macd_delta < 0:
                    result["btc_momentum"] = "strong_down"
                elif macd_current < 0:
                    result["btc_momentum"] = "down"
                else:
                    result["btc_momentum"] = "neutral"

        # Extract derivatives data (OI, Funding, Correlations)
        for ind in all_indicators:
            ticker = ind.get("ticker", "").upper()
            deriv = ind.get("derivatives", {})
            if deriv:
                # Funding rate
                funding = deriv.get("funding_rate")
                if funding is not None:
                    result["funding_rates"][ticker] = funding

                # Open Interest
                oi = deriv.get("open_interest_latest")
                if oi is not None:
                    result["open_interest"][ticker] = oi

                # Correlations (same for all, just grab once)
                if not result["correlations"] and deriv.get("correlations"):
                    result["correlations"] = deriv["correlations"]

        # Calculate average correlation if available
        if result["correlations"]:
            corr_values = list(result["correlations"].values())
            if corr_values:
                result["market_correlation"] = round(sum(corr_values) / len(corr_values), 2)

        # Market Regime (basato su ATR medio)
        atr_ratios = []
        for ind in all_indicators:
            lt = ind.get("longer_term_15m", {})
            atr_14 = lt.get("atr_14_current")
            atr_3 = lt.get("atr_3_current")
            if atr_14 and atr_3 and atr_14 > 0:
                atr_ratios.append(atr_3 / atr_14)

        if atr_ratios:
            avg_ratio = sum(atr_ratios) / len(atr_ratios)
            if avg_ratio > 1.5:
                result["volatility_regime"] = "high"
                result["market_regime"] = "volatile"
            elif avg_ratio < 0.7:
                result["volatility_regime"] = "low"
                result["market_regime"] = "ranging"
            else:
                result["volatility_regime"] = "normal"
                # Determina trending o ranging basandosi su BTC trend
                if result["btc_trend"] in ["bullish", "bearish"]:
                    result["market_regime"] = f"trending_{result['btc_trend'].replace('ish', '')}"
                else:
                    result["market_regime"] = "ranging"

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo market context: {e}")

    return result


def get_correlation_analysis(all_indicators: List[dict]) -> dict:
    """
    Analizza la correlazione tra asset.

    Args:
        all_indicators: Lista di indicatori per tutti i simboli

    Returns:
        dict con analisi correlazione
    """
    result = {
        "symbols_aligned": [],  # Simboli con trend allineato
        "symbols_diverging": [],  # Simboli con trend divergente
        "strongest_signal": None,
        "weakest_signal": None,
    }

    if not all_indicators or len(all_indicators) < 2:
        return result

    try:
        trends = {}
        signal_strength = {}

        for ind in all_indicators:
            ticker = ind.get("ticker", "")
            current = ind.get("current", {})
            longer_term = ind.get("longer_term_15m", {})

            price = current.get("price")
            ema20 = current.get("ema20")
            ema50 = longer_term.get("ema_50_current")

            if price and ema20 and ema50:
                if price > ema20 > ema50:
                    trends[ticker] = "bullish"
                    signal_strength[ticker] = ((price - ema50) / ema50) * 100
                elif price < ema20 < ema50:
                    trends[ticker] = "bearish"
                    signal_strength[ticker] = ((ema50 - price) / ema50) * 100
                else:
                    trends[ticker] = "neutral"
                    signal_strength[ticker] = 0

        # Trova trend dominante
        bullish_count = sum(1 for t in trends.values() if t == "bullish")
        bearish_count = sum(1 for t in trends.values() if t == "bearish")

        dominant_trend = "bullish" if bullish_count > bearish_count else (
            "bearish" if bearish_count > bullish_count else "neutral"
        )

        for ticker, trend in trends.items():
            if trend == dominant_trend:
                result["symbols_aligned"].append(ticker)
            elif trend != "neutral":
                result["symbols_diverging"].append(ticker)

        # Strongest/Weakest signal
        if signal_strength:
            sorted_signals = sorted(signal_strength.items(), key=lambda x: abs(x[1]), reverse=True)
            result["strongest_signal"] = {
                "symbol": sorted_signals[0][0],
                "strength": round(sorted_signals[0][1], 2)
            }
            result["weakest_signal"] = {
                "symbol": sorted_signals[-1][0],
                "strength": round(sorted_signals[-1][1], 2)
            }

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo correlation: {e}")

    return result


# ============================================================================
# 5. POSITION CONTEXT (migliorato)
# ============================================================================

def get_position_context_enhanced(symbol: str, position: dict = None) -> dict:
    """
    Recupera contesto esteso della posizione aperta.

    Args:
        symbol: Simbolo
        position: Dati posizione opzionali

    Returns:
        dict con contesto posizione
    """
    result = {
        "duration_minutes": 0,
        "entry_price": None,
        "current_price": None,
        "peak_price": None,
        "opening_score": None,
        "trading_mode": "NORMAL",
        "trailing_active": False,
        "unrealized_pnl_pct": None,
        "distance_from_peak_pct": None,
        "sl_level_pct": None,
        "time_in_profit_minutes": None,
        "max_profit_pct": None,
        "current_vs_max_profit": None,  # % del max profit attuale
    }

    if not DB_ENABLED:
        return result

    try:
        tracking = db_utils.get_position_tracking(symbol)
        if not tracking:
            return result

        from datetime import datetime, timezone

        created_at = tracking.get('created_at')
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            result["duration_minutes"] = int((now - created_at).total_seconds() / 60)

        result["entry_price"] = tracking.get('entry_price')
        result["peak_price"] = tracking.get('peak_price')
        result["opening_score"] = tracking.get('opening_score')
        result["trading_mode"] = tracking.get('trading_mode', 'NORMAL')
        result["trailing_active"] = tracking.get('trailing_active', False)

        # Se abbiamo dati posizione, calcola metriche aggiuntive
        if position:
            entry_price = float(position.get("entry_price") or 0)
            mark_price = float(position.get("mark_price") or 0)
            peak_price = float(tracking.get("peak_price") or mark_price)
            direction = position.get("side", "long").lower()

            # Parse leverage
            leverage_raw = position.get("leverage", 1)
            if isinstance(leverage_raw, str):
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', leverage_raw)
                leverage = float(match.group(1)) if match else 1.0
            else:
                leverage = float(leverage_raw)

            if entry_price > 0:
                # Unrealized P&L %
                if direction == "long":
                    price_change = ((mark_price - entry_price) / entry_price) * 100
                else:
                    price_change = ((entry_price - mark_price) / entry_price) * 100

                result["unrealized_pnl_pct"] = round(price_change * leverage, 2)
                result["current_price"] = mark_price

                # Distance from peak
                if direction == "long" and peak_price > 0:
                    peak_change = ((mark_price - peak_price) / peak_price) * 100
                elif direction == "short" and peak_price > 0:
                    peak_change = ((peak_price - mark_price) / peak_price) * 100
                else:
                    peak_change = 0

                result["distance_from_peak_pct"] = round(peak_change * leverage, 2)

                # Max profit achieved
                if direction == "long" and peak_price > entry_price:
                    max_profit = ((peak_price - entry_price) / entry_price) * 100 * leverage
                elif direction == "short" and peak_price < entry_price:
                    max_profit = ((entry_price - peak_price) / entry_price) * 100 * leverage
                else:
                    max_profit = max(0, result["unrealized_pnl_pct"])

                result["max_profit_pct"] = round(max_profit, 2)

                # Current vs max profit
                if max_profit > 0:
                    current_pnl = result["unrealized_pnl_pct"]
                    result["current_vs_max_profit"] = round((current_pnl / max_profit) * 100, 1)

    except Exception as e:
        print(f"[AI_CONTEXT] Errore calcolo position context: {e}")

    return result


# ============================================================================
# 6. BUILDER PRINCIPALE
# ============================================================================

def build_full_ai_context(
    symbol: str,
    indicators_json: List[dict],
    sentiment_json: dict,
    forecasts_json: Any,
    account_status: dict,
    position: dict = None,
    score_data: dict = None,
    whale_data: dict = None,
) -> dict:
    """
    Costruisce il contesto completo per l'AI.

    Args:
        symbol: Simbolo da analizzare
        indicators_json: Lista indicatori per tutti i simboli
        sentiment_json: Dati sentiment
        forecasts_json: Dati forecast
        account_status: Stato account
        position: Posizione aperta (se esiste)
        score_data: Score calcolato
        whale_data: Dati whale alerts strutturati (da get_whale_alerts_json)

    Returns:
        dict con contesto completo per AI
    """
    # Trova indicatori per questo simbolo
    symbol_indicators = None
    for ind in indicators_json:
        if ind.get("ticker", "").upper() == symbol.upper():
            symbol_indicators = ind
            break

    has_position = position is not None

    context = {
        # === BASE INFO ===
        "symbol": symbol,
        "has_position": has_position,
        "score": score_data,

        # === TECHNICAL INDICATORS ADVANCED ===
        "technical_advanced": get_technical_indicators_advanced(symbol_indicators),

        # === PERFORMANCE BY CONDITIONS ===
        "performance_conditions": get_performance_by_conditions(symbol),

        # === GLOBAL PERFORMANCE ===
        "global_performance": get_global_performance_stats(days=7),

        # === RISK METRICS ===
        "risk_metrics": get_risk_metrics(account_status),

        # === MARKET CONTEXT ===
        "market_context": get_market_context(indicators_json),

        # === CORRELATION ===
        "correlation": get_correlation_analysis(indicators_json),

        # === POSITION CONTEXT (if open) ===
        "position_context": get_position_context_enhanced(symbol, position) if has_position else None,

        # === POSITION DATA ===
        "position": position,

        # === RAW INDICATORS ===
        "indicators": symbol_indicators,

        # === SENTIMENT ===
        "sentiment": sentiment_json,

        # === FORECAST ===
        "forecast": forecasts_json,

        # === WHALE ALERTS (strutturati) ===
        "whale_alerts": _extract_whale_context(symbol, whale_data) if whale_data else None,

        # === ACCOUNT ===
        "account_balance": account_status.get("balance_usd", 0) if account_status else 0,
        "open_positions_count": len(account_status.get("open_positions", [])) if account_status else 0,

        # === TIMESTAMP ===
        "context_generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return context


def _extract_whale_context(symbol: str, whale_data: dict) -> dict:
    """
    Estrae contesto whale rilevante per un simbolo specifico.

    Args:
        symbol: Simbolo da analizzare
        whale_data: Dati whale completi da get_whale_alerts_json()

    Returns:
        dict con whale context per il simbolo
    """
    if not whale_data or whale_data.get("error"):
        return {
            "available": False,
            "error": whale_data.get("error") if whale_data else "No data"
        }

    symbol_upper = symbol.upper()
    summary = whale_data.get("summary", {})
    by_symbol = whale_data.get("by_symbol", {})

    # Dati specifici per il simbolo
    symbol_whale = by_symbol.get(symbol_upper, {})

    # Estrai solo gli alert rilevanti per questo simbolo (ultimi 3)
    relevant_alerts = [
        {
            "timestamp": a.get("timestamp"),
            "amount": a.get("amount"),
            "usd_value": a.get("usd_value"),
            "movement_type": a.get("movement_type"),
            "sentiment": a.get("sentiment"),
            "reason": a.get("reason")
        }
        for a in whale_data.get("alerts", [])
        if a.get("symbol") == symbol_upper
    ][:3]  # Max 3 alert per non appesantire il context

    return {
        "available": True,

        # === MARKET-WIDE WHALE SENTIMENT ===
        "market_summary": {
            "total_alerts": summary.get("total_alerts", 0),
            "net_sentiment": summary.get("net_sentiment", "neutral"),
            "net_flow": summary.get("net_flow", "neutral"),
            "exchange_inflow_usd": summary.get("exchange_inflow_usd", 0),
            "exchange_outflow_usd": summary.get("exchange_outflow_usd", 0),
            "interpretation": _interpret_whale_flow(summary)
        },

        # === SYMBOL-SPECIFIC WHALE DATA ===
        "symbol_data": {
            "alerts_count": symbol_whale.get("count", 0),
            "total_volume_usd": symbol_whale.get("total_usd", 0),
            "bullish_movements": symbol_whale.get("bullish", 0),
            "bearish_movements": symbol_whale.get("bearish", 0),
            "net_sentiment": symbol_whale.get("net_sentiment", "neutral") if symbol_whale else "no_data"
        } if symbol_whale else None,

        # === RECENT ALERTS FOR SYMBOL ===
        "recent_alerts": relevant_alerts if relevant_alerts else None
    }


def _interpret_whale_flow(summary: dict) -> str:
    """
    Genera interpretazione leggibile del flusso whale.
    """
    net_flow = summary.get("net_flow", "neutral")
    net_sentiment = summary.get("net_sentiment", "neutral")
    inflow = summary.get("exchange_inflow_usd", 0)
    outflow = summary.get("exchange_outflow_usd", 0)

    if net_flow == "bullish" and net_sentiment == "bullish":
        return "Strong accumulation: whales withdrawing from exchanges (bullish)"
    elif net_flow == "bearish" and net_sentiment == "bearish":
        return "Distribution phase: whales depositing to exchanges (bearish)"
    elif net_flow == "bullish":
        return "Net outflow from exchanges suggests accumulation"
    elif net_flow == "bearish":
        return "Net inflow to exchanges suggests selling pressure"
    elif inflow > 0 or outflow > 0:
        return "Mixed whale activity, no clear direction"
    else:
        return "Low whale activity"


def format_context_summary(context: dict) -> str:
    """
    Formatta un riassunto leggibile del contesto per logging.

    Args:
        context: Contesto completo

    Returns:
        str con riassunto formattato
    """
    lines = []
    symbol = context.get("symbol", "???")

    # Technical
    tech = context.get("technical_advanced", {})
    if tech.get("rsi_current"):
        lines.append(f"RSI={tech['rsi_current']:.0f}({tech.get('rsi_zone', 'N/A')})")
    if tech.get("atr_percentile"):
        lines.append(f"Vol={tech['atr_percentile']}")
    if tech.get("ema_alignment"):
        lines.append(f"EMA={tech['ema_alignment']}")

    # Performance
    perf = context.get("performance_conditions", {})
    wr_long = perf.get("win_rate_by_direction", {}).get("LONG")
    wr_short = perf.get("win_rate_by_direction", {}).get("SHORT")
    if wr_long is not None:
        lines.append(f"WR_L={wr_long:.0f}%")
    if wr_short is not None:
        lines.append(f"WR_S={wr_short:.0f}%")

    # Risk
    risk = context.get("risk_metrics", {})
    if risk.get("risk_level"):
        lines.append(f"Risk={risk['risk_level']}")

    # Market
    market = context.get("market_context", {})
    if market.get("btc_trend"):
        lines.append(f"BTC={market['btc_trend']}")

    # Derivatives
    if market.get("market_correlation") is not None:
        lines.append(f"Corr={market['market_correlation']:.2f}")
    funding = market.get("funding_rates", {}).get(symbol)
    if funding is not None:
        lines.append(f"Fund={funding:.6f}")
    oi = market.get("open_interest", {}).get(symbol)
    if oi is not None:
        lines.append(f"OI=${oi/1e6:.1f}M")

    # Whale alerts
    whale = context.get("whale_alerts", {})
    if whale and whale.get("available"):
        whale_summary = whale.get("market_summary", {})
        whale_symbol = whale.get("symbol_data", {})
        net_sent = whale_summary.get("net_sentiment", "N/A")
        lines.append(f"Whale={net_sent}")
        if whale_symbol:
            sym_sent = whale_symbol.get("net_sentiment", "N/A")
            if sym_sent != net_sent:
                lines.append(f"Whale_{symbol}={sym_sent}")

    return f"[{symbol}] " + " | ".join(lines) if lines else f"[{symbol}] No context"


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "build_full_ai_context",
    "format_context_summary",
    "get_technical_indicators_advanced",
    "get_performance_by_conditions",
    "get_global_performance_stats",
    "get_risk_metrics",
    "get_market_context",
    "get_correlation_analysis",
    "get_position_context_enhanced",
]
