#!/usr/bin/env python3
"""
Analytics Engine - Analisi performance trading bot

Funzionalità:
1. Fetch trade storici da Hyperliquid
2. Analisi "hindsight" (cosa è successo dopo ogni close)
3. Metriche: win rate, profit factor, opportunity loss
4. Ottimizzazione parametri basata su dati reali
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import db_utils
from hyperliquid_trader import HyperLiquidTrader

load_dotenv()

TESTNET = os.getenv("TESTNET", "true").lower() == "true"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")


def get_hyperliquid_bot():
    """Crea istanza HyperLiquidTrader per fetch dati."""
    if not PRIVATE_KEY or not WALLET_ADDRESS:
        raise RuntimeError("PRIVATE_KEY o WALLET_ADDRESS mancanti nel .env")

    return HyperLiquidTrader(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        testnet=TESTNET
    )


def fetch_completed_trades_from_hyperliquid(days: int = 30) -> List[Dict[str, Any]]:
    """
    Recupera tutti i trade completati da Hyperliquid API.

    Args:
        days: Numero di giorni di storico da recuperare

    Returns:
        Lista di trade con formato:
        {
            'symbol': 'BTC',
            'side': 'long' | 'short',
            'entry_price': 50000.0,
            'exit_price': 51500.0,
            'size': 0.1,
            'pnl_usd': 150.0,
            'pnl_pct': 3.0,
            'open_time': datetime,
            'close_time': datetime,
            'duration_minutes': 86,
            'close_reason': 'take_profit' | 'stop_loss' | 'manual'
        }
    """

    bot = get_hyperliquid_bot()

    # Fetch user fills (operazioni eseguite)
    # Nota: Hyperliquid API restituisce fills (esecuzioni), non trade completi
    # Dobbiamo matchare buy/sell per ricostruire trade completi

    try:
        # user_fills restituisce tutte le esecuzioni recenti
        fills = bot.exchange.info.user_fills(WALLET_ADDRESS)

        # Raggruppa fills in trade completi (match buy + sell)
        trades = _group_fills_into_trades(fills, days)

        return trades

    except Exception as e:
        print(f"⚠️  Errore fetch trade da Hyperliquid: {e}")
        return []


def _group_fills_into_trades(fills: List[Dict], days: int) -> List[Dict[str, Any]]:
    """
    Raggruppa fills (esecuzioni) in trade completi.

    Match buy/sell dello stesso simbolo per ricostruire:
    - Entry price (da open fill)
    - Exit price (da close fill)
    - P&L
    """

    trades = []

    # Filtra fills per data
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
    recent_fills = [
        f for f in fills
        if datetime.fromtimestamp(f['time'] / 1000, tz=timezone.utc) > cutoff_time
    ]

    # Raggruppa per simbolo
    by_symbol = {}
    for fill in recent_fills:
        symbol = fill['coin']
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(fill)

    # Per ogni simbolo, ricostruisci trade
    for symbol, symbol_fills in by_symbol.items():
        # Ordina per timestamp
        symbol_fills.sort(key=lambda x: x['time'])

        position = None  # Posizione corrente

        for fill in symbol_fills:
            is_buy = fill['side'] == 'B'  # B = buy, A = sell/ask
            size = float(fill['sz'])
            price = float(fill['px'])
            timestamp = datetime.fromtimestamp(fill['time'] / 1000, tz=timezone.utc)

            if position is None:
                # Nuova posizione aperta
                position = {
                    'symbol': symbol,
                    'side': 'long' if is_buy else 'short',
                    'entry_price': price,
                    'entry_size': size,
                    'open_time': timestamp,
                    'fills': [fill]
                }
            else:
                # Chiusura posizione (o aggiunta)
                is_close = (position['side'] == 'long' and not is_buy) or \
                           (position['side'] == 'short' and is_buy)

                if is_close:
                    # Chiusura completa o parziale
                    exit_price = price
                    close_time = timestamp

                    # Calcola P&L
                    if position['side'] == 'long':
                        pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
                    else:
                        pnl_pct = ((position['entry_price'] - exit_price) / position['entry_price']) * 100

                    # P&L in USD (approssimato, potrebbe servire leverage)
                    pnl_usd = (pnl_pct / 100) * position['entry_price'] * size

                    duration = (close_time - position['open_time']).total_seconds() / 60

                    # Crea trade completato
                    trade = {
                        'symbol': symbol,
                        'side': position['side'],
                        'entry_price': position['entry_price'],
                        'exit_price': exit_price,
                        'size': size,
                        'pnl_usd': pnl_usd,
                        'pnl_pct': pnl_pct,
                        'open_time': position['open_time'],
                        'close_time': close_time,
                        'duration_minutes': duration,
                        'close_reason': _infer_close_reason(pnl_pct)
                    }

                    trades.append(trade)

                    # Reset posizione
                    position = None
                else:
                    # Aggiunta alla posizione (DCA)
                    position['fills'].append(fill)

    return trades


def _infer_close_reason(pnl_pct: float) -> str:
    """Inferisce il motivo della chiusura dal P&L."""
    # Leggi configurazione
    TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '5'))
    INITIAL_STOP_LOSS_PERCENT = float(os.getenv('INITIAL_STOP_LOSS_PERCENT', '10'))

    if pnl_pct >= TAKE_PROFIT_PERCENT * 0.8:  # Vicino al take profit
        return 'take_profit'
    elif pnl_pct <= -INITIAL_STOP_LOSS_PERCENT * 0.8:  # Vicino allo stop loss
        return 'stop_loss'
    else:
        return 'manual'


def analyze_close_decision_quality(trade: Dict[str, Any], lookback_minutes: int = 60) -> Dict[str, Any]:
    """
    Analizza se la chiusura è stata fatta al momento giusto.
    Usa candles storiche di Hyperliquid per vedere cosa è successo dopo.

    Args:
        trade: Trade completato
        lookback_minutes: Minuti da analizzare dopo la chiusura

    Returns:
        {
            'close_quality': 'EXCELLENT' | 'GOOD' | 'ACCEPTABLE' | 'TOO_EARLY' | 'TOO_LATE',
            'peak_after_close': 53000.0,
            'peak_after_close_pct': 6.0,
            'missed_opportunity_pct': 3.0,
            'price_at_30min': 48000.0,
            'verdict': 'Descrizione qualitativa'
        }
    """

    bot = get_hyperliquid_bot()

    try:
        # Fetch candles 1-minute per lookback_minutes dopo close
        start_time = int(trade['close_time'].timestamp() * 1000)
        end_time = int((trade['close_time'] + timedelta(minutes=lookback_minutes)).timestamp() * 1000)

        # API Hyperliquid: candle_snapshot
        candles = bot.exchange.info.candle_snapshot(
            coin=trade['symbol'],
            interval='1m',
            startTime=start_time,
            endTime=end_time
        )

        if not candles or len(candles) == 0:
            return {
                'close_quality': 'UNKNOWN',
                'verdict': 'Dati insufficienti per analisi'
            }

        # Trova peak nei candles successivi
        if trade['side'] == 'long':
            peak_price = max([float(c['h']) for c in candles])  # high
        else:  # short
            peak_price = min([float(c['l']) for c in candles])  # low

        # Calcola P&L del peak
        if trade['side'] == 'long':
            peak_pct = ((peak_price - trade['entry_price']) / trade['entry_price']) * 100
        else:
            peak_pct = ((trade['entry_price'] - peak_price) / trade['entry_price']) * 100

        # Prezzo a 30 minuti (se disponibile)
        price_30min = None
        price_30min_pct = None
        if len(candles) > 30:
            price_30min = float(candles[30]['c'])  # close
            if trade['side'] == 'long':
                price_30min_pct = ((price_30min - trade['entry_price']) / trade['entry_price']) * 100
            else:
                price_30min_pct = ((trade['entry_price'] - price_30min) / trade['entry_price']) * 100

        # Calcola missed opportunity
        missed_opportunity = peak_pct - trade['pnl_pct']

        # Valuta qualità
        if missed_opportunity < 1.0:
            quality = 'EXCELLENT'
            verdict = f"Timing perfetto: peak post-close solo +{missed_opportunity:.1f}%"
        elif missed_opportunity < 3.0:
            if price_30min_pct and price_30min_pct < trade['pnl_pct']:
                quality = 'GOOD'
                verdict = f"Chiuso {missed_opportunity:.1f}% prima del peak, ma poi prezzo crollato"
            else:
                quality = 'ACCEPTABLE'
                verdict = f"Accettabile: perso {missed_opportunity:.1f}% di profitto potenziale"
        elif missed_opportunity > 5.0:
            quality = 'TOO_EARLY'
            verdict = f"Uscito troppo presto: perso +{missed_opportunity:.1f}% di profitto"
        else:
            quality = 'ACCEPTABLE'
            verdict = f"Accettabile: perso {missed_opportunity:.1f}%"

        return {
            'close_quality': quality,
            'peak_after_close': peak_price,
            'peak_after_close_pct': peak_pct,
            'missed_opportunity_pct': missed_opportunity,
            'price_at_30min': price_30min,
            'price_at_30min_pct': price_30min_pct,
            'verdict': verdict
        }

    except Exception as e:
        print(f"⚠️  Errore analisi close quality per {trade['symbol']}: {e}")
        return {
            'close_quality': 'UNKNOWN',
            'verdict': f'Errore: {e}'
        }


def get_performance_summary(days: int = 30) -> Dict[str, Any]:
    """
    Restituisce metriche complete di performance con analisi hindsight.

    Args:
        days: Giorni di storico da analizzare

    Returns:
        {
            'total_trades': 45,
            'winning_trades': 26,
            'losing_trades': 19,
            'win_rate': 0.58,
            'total_profit_usd': 450.0,
            'total_loss_usd': -250.0,
            'net_profit_usd': 200.0,
            'profit_factor': 1.8,
            'avg_win_pct': 6.2,
            'avg_loss_pct': -4.1,
            'max_win_pct': 12.5,
            'max_loss_pct': -8.9,
            'avg_duration_minutes': 85,
            'close_quality_distribution': {...},
            'total_missed_profit_usd': 340.0,
            'avg_missed_per_trade_pct': 2.8,
            'per_symbol': {...}
        }
    """

    print(f"\n{'='*60}")
    print(f"📊 PERFORMANCE ANALYSIS - Last {days} days")
    print(f"{'='*60}\n")

    # Fetch trade da Hyperliquid
    print("1️⃣  Fetching trade completati da Hyperliquid...")
    trades = fetch_completed_trades_from_hyperliquid(days)
    print(f"   ✅ {len(trades)} trade trovati\n")

    if not trades:
        return {
            'error': 'Nessun trade trovato',
            'total_trades': 0
        }

    # Analizza ogni trade con hindsight
    print("2️⃣  Analisi hindsight (cosa è successo dopo ogni close)...")
    for i, trade in enumerate(trades):
        print(f"   Analizzando {trade['symbol']} #{i+1}/{len(trades)}...", end='\r')
        trade['close_analysis'] = analyze_close_decision_quality(trade)
    print(f"   ✅ Analisi hindsight completata\n")

    # Calcola metriche aggregate
    print("3️⃣  Calcolo metriche...\n")

    winning_trades = [t for t in trades if t['pnl_usd'] > 0]
    losing_trades = [t for t in trades if t['pnl_usd'] <= 0]

    total_profit = sum(t['pnl_usd'] for t in winning_trades)
    total_loss = abs(sum(t['pnl_usd'] for t in losing_trades))

    # Close quality distribution
    quality_dist = {}
    for t in trades:
        q = t['close_analysis'].get('close_quality', 'UNKNOWN')
        quality_dist[q] = quality_dist.get(q, 0) + 1

    # Missed opportunities
    total_missed = sum(
        t['close_analysis'].get('missed_opportunity_pct', 0)
        for t in trades
        if t['close_analysis'].get('missed_opportunity_pct') is not None
    )

    # Per symbol stats
    per_symbol = _calculate_per_symbol_stats(trades)

    summary = {
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': len(winning_trades) / len(trades) if trades else 0,
        'total_profit_usd': total_profit,
        'total_loss_usd': total_loss,
        'net_profit_usd': total_profit - total_loss,
        'profit_factor': total_profit / total_loss if total_loss > 0 else float('inf'),
        'avg_win_pct': sum(t['pnl_pct'] for t in winning_trades) / len(winning_trades) if winning_trades else 0,
        'avg_loss_pct': sum(t['pnl_pct'] for t in losing_trades) / len(losing_trades) if losing_trades else 0,
        'max_win_pct': max([t['pnl_pct'] for t in winning_trades]) if winning_trades else 0,
        'max_loss_pct': min([t['pnl_pct'] for t in losing_trades]) if losing_trades else 0,
        'avg_duration_minutes': sum(t['duration_minutes'] for t in trades) / len(trades),
        'close_quality_distribution': quality_dist,
        'total_missed_profit_pct': total_missed,
        'avg_missed_per_trade_pct': total_missed / len(trades) if trades else 0,
        'per_symbol': per_symbol,
        'trades': trades  # Include tutti i trade per analisi dettagliata
    }

    # Print summary
    _print_performance_summary(summary)

    return summary


def _calculate_per_symbol_stats(trades: List[Dict]) -> Dict[str, Any]:
    """Calcola statistiche per ogni simbolo."""

    by_symbol = {}
    for trade in trades:
        symbol = trade['symbol']
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(trade)

    per_symbol = {}
    for symbol, symbol_trades in by_symbol.items():
        winning = [t for t in symbol_trades if t['pnl_usd'] > 0]
        losing = [t for t in symbol_trades if t['pnl_usd'] <= 0]

        total_profit = sum(t['pnl_usd'] for t in winning)
        total_loss = abs(sum(t['pnl_usd'] for t in losing))

        per_symbol[symbol] = {
            'total_trades': len(symbol_trades),
            'win_rate': len(winning) / len(symbol_trades) if symbol_trades else 0,
            'profit_factor': total_profit / total_loss if total_loss > 0 else float('inf'),
            'net_profit_usd': total_profit - total_loss,
            'avg_win_pct': sum(t['pnl_pct'] for t in winning) / len(winning) if winning else 0,
            'avg_loss_pct': sum(t['pnl_pct'] for t in losing) / len(losing) if losing else 0,
        }

    return per_symbol


def _print_performance_summary(summary: Dict[str, Any]):
    """Stampa summary in formato leggibile."""

    print(f"{'='*60}")
    print(f"📈 PERFORMANCE SUMMARY")
    print(f"{'='*60}\n")

    print(f"Total Trades:        {summary['total_trades']}")
    print(f"Win Rate:            {summary['win_rate']*100:.1f}% ({summary['winning_trades']}W / {summary['losing_trades']}L)")
    print(f"Profit Factor:       {summary['profit_factor']:.2f}")
    print(f"\nP&L:")
    print(f"  Total Profit:      ${summary['total_profit_usd']:.2f}")
    print(f"  Total Loss:        ${summary['total_loss_usd']:.2f}")
    print(f"  Net Profit:        ${summary['net_profit_usd']:.2f}")
    print(f"\nAverage Trade:")
    print(f"  Avg Win:           +{summary['avg_win_pct']:.2f}%")
    print(f"  Avg Loss:          {summary['avg_loss_pct']:.2f}%")
    print(f"  Max Win:           +{summary['max_win_pct']:.2f}%")
    print(f"  Max Loss:          {summary['max_loss_pct']:.2f}%")
    print(f"  Avg Duration:      {summary['avg_duration_minutes']:.0f} min")

    print(f"\n{'='*60}")
    print(f"🎯 CLOSE QUALITY ANALYSIS")
    print(f"{'='*60}\n")

    for quality, count in summary['close_quality_distribution'].items():
        pct = (count / summary['total_trades']) * 100
        print(f"  {quality:15} {count:3} trades ({pct:5.1f}%)")

    print(f"\nMissed Opportunities:")
    print(f"  Total:             {summary['total_missed_profit_pct']:.1f}% cumulative")
    print(f"  Per Trade Avg:     {summary['avg_missed_per_trade_pct']:.2f}%")

    print(f"\n{'='*60}")
    print(f"📊 PER-SYMBOL BREAKDOWN")
    print(f"{'='*60}\n")

    for symbol, stats in summary['per_symbol'].items():
        print(f"{symbol}:")
        print(f"  Trades: {stats['total_trades']}, Win Rate: {stats['win_rate']*100:.1f}%, "
              f"Profit Factor: {stats['profit_factor']:.2f}, Net: ${stats['net_profit_usd']:.2f}")

    print(f"\n{'='*60}\n")


def get_sentinel_effectiveness() -> Dict[str, Any]:
    """
    Analizza effectiveness del sentinel (take profit vs stop loss).

    Returns:
        {
            'total_sentinel_closes': 45,
            'take_profit_count': 28,
            'stop_loss_count': 12,
            'trailing_stop_count': 5,
            'take_profit_rate': 0.62,
            'avg_profit_at_take_profit': 5.2,
            'avg_loss_at_stop_loss': -9.1,
            'avg_profit_at_trailing': 4.8
        }
    """

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            # Statistiche sentinel
            cur.execute("""
                SELECT
                    action_taken,
                    COUNT(*) as count,
                    AVG(profit_pct) as avg_profit
                FROM sentinel_logs
                WHERE action_taken IS NOT NULL
                  AND created_at > NOW() - INTERVAL '30 days'
                GROUP BY action_taken
            """)

            rows = cur.fetchall()

    stats = {}
    for row in rows:
        action = row[0]
        count = row[1]
        avg_profit = float(row[2]) if row[2] else 0
        stats[action] = {'count': count, 'avg_profit': avg_profit}

    total = sum(s['count'] for s in stats.values())

    return {
        'total_sentinel_closes': total,
        'take_profit_count': stats.get('CLOSE_TAKE_PROFIT', {}).get('count', 0),
        'stop_loss_count': stats.get('CLOSE_STOP_LOSS', {}).get('count', 0),
        'trailing_stop_count': stats.get('CLOSE_TRAILING_STOP', {}).get('count', 0),
        'take_profit_rate': stats.get('CLOSE_TAKE_PROFIT', {}).get('count', 0) / total if total > 0 else 0,
        'avg_profit_at_take_profit': stats.get('CLOSE_TAKE_PROFIT', {}).get('avg_profit', 0),
        'avg_loss_at_stop_loss': stats.get('CLOSE_STOP_LOSS', {}).get('avg_profit', 0),
        'avg_profit_at_trailing': stats.get('CLOSE_TRAILING_STOP', {}).get('avg_profit', 0),
    }


if __name__ == "__main__":
    # Test analytics
    print("🔬 Testing Analytics Engine\n")

    # Performance summary
    summary = get_performance_summary(days=30)

    # Sentinel effectiveness
    print("\n📡 Sentinel Effectiveness:")
    sentinel_stats = get_sentinel_effectiveness()
    print(f"  Take Profit: {sentinel_stats['take_profit_count']} ({sentinel_stats['take_profit_rate']*100:.1f}%)")
    print(f"  Stop Loss: {sentinel_stats['stop_loss_count']}")
    print(f"  Trailing Stop: {sentinel_stats['trailing_stop_count']}")
