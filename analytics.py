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
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import db_utils
from hyperliquid_trader import HyperLiquidTrader

load_dotenv()

TESTNET = os.getenv("TESTNET", "true").lower() == "true"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

# Global bot instance cache to avoid recreating connections
_bot_instance = None


def get_hyperliquid_bot():
    """
    Returns cached HyperLiquidTrader instance to avoid rate limits.
    Uses exponential backoff on rate limit errors (429).
    """
    global _bot_instance

    if not PRIVATE_KEY or not WALLET_ADDRESS:
        raise RuntimeError("PRIVATE_KEY or WALLET_ADDRESS missing in .env")

    # Return cached instance if available
    if _bot_instance is not None:
        return _bot_instance

    # Create new instance with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            _bot_instance = HyperLiquidTrader(
                secret_key=PRIVATE_KEY,
                account_address=WALLET_ADDRESS,
                testnet=TESTNET
            )
            return _bot_instance
        except Exception as e:
            error_str = str(e)
            # Check if it's a 429 rate limit error
            if '429' in error_str:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # 2s, 4s, 8s
                    print(f"⚠️  Rate limit hit (429). Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Failed to connect to Hyperliquid after {max_retries} attempts due to rate limiting. Please wait a few minutes and try again.") from e
            else:
                # Not a rate limit error, raise immediately
                raise


def fetch_completed_trades_from_db(days: int = 30) -> List[Dict[str, Any]]:
    """
    Recupera trade completati dal database PostgreSQL (sentinel_logs).
    Sentinel logs contains detailed entry/exit prices and PnL data.

    Args:
        days: Numero di giorni di storico da recuperare

    Returns:
        Lista di trade con stesso formato di fetch_completed_trades_from_hyperliquid
    """
    from datetime import datetime, timedelta, timezone

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query sentinel_logs which has more detailed trade info
    query = """
        SELECT
            symbol,
            direction,
            entry_price,
            exit_price,
            pnl_usd,
            pnl_percentage,
            created_at as close_time,
            reason
        FROM sentinel_logs
        WHERE created_at >= %s
            AND action = 'close'
            AND pnl_usd IS NOT NULL
        ORDER BY created_at DESC
    """

    try:
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cutoff_date,))
                rows = cur.fetchall()

        trades = []
        for row in rows:
            symbol, direction, entry_price, exit_price, pnl_usd, pnl_pct, close_time, reason = row

            # Estimate open time (we don't have it, so approximate)
            # Could also join with position_tracking or bot_operations for accuracy
            duration_minutes = 60  # Default estimate

            trade = {
                'symbol': symbol.replace('-USD', ''),  # BTC-USD -> BTC
                'side': direction or 'long',
                'entry_price': float(entry_price) if entry_price else 0.0,
                'exit_price': float(exit_price) if exit_price else 0.0,
                'size': abs(float(pnl_usd) / float(entry_price) / (float(pnl_pct) / 100)) if entry_price and pnl_pct and pnl_usd and pnl_pct != 0 else 0.0,
                'pnl_usd': float(pnl_usd) if pnl_usd else 0.0,
                'pnl_pct': float(pnl_pct) if pnl_pct else 0.0,
                'open_time': close_time,  # Approximate
                'close_time': close_time,
                'duration_minutes': duration_minutes,
                'close_reason': reason or 'unknown'
            }

            trades.append(trade)

        print(f"   📊 Found {len(trades)} completed trades in sentinel_logs")
        return trades

    except Exception as e:
        print(f"⚠️  Error fetching trades from sentinel_logs: {e}")
        print(f"   Trying alternative method with bot_operations...")
        import traceback
        traceback.print_exc()

        # Fallback: try bot_operations (but with limited data)
        return _fetch_from_bot_operations_fallback(cutoff_date)


def _fetch_from_bot_operations_fallback(cutoff_date) -> List[Dict[str, Any]]:
    """Fallback method using bot_operations table (less accurate)"""
    query = """
        SELECT COUNT(*)
        FROM bot_operations
        WHERE created_at >= %s
            AND operation IN ('open', 'close')
            AND symbol IS NOT NULL
    """

    try:
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cutoff_date,))
                count = cur.fetchone()[0]

        print(f"   ⚠️  Found {count} operations but no detailed PnL data")
        print(f"   💡 Tip: Wait for more trades with sentinel system active to get detailed analytics")
        return []

    except Exception as e:
        print(f"⚠️  Error in fallback method: {e}")
        return []


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


def get_performance_summary(days: int = 30, use_database_only: bool = True) -> Dict[str, Any]:
    """
    Restituisce metriche complete di performance con analisi hindsight.

    Args:
        days: Giorni di storico da analizzare
        use_database_only: Se True, usa solo dati dal DB (evita rate limits Hyperliquid)

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

    # Fetch trade da database o Hyperliquid
    if use_database_only:
        print("1️⃣  Fetching trade completati dal database...")
        trades = fetch_completed_trades_from_db(days)
    else:
        print("1️⃣  Fetching trade completati da Hyperliquid...")
        try:
            trades = fetch_completed_trades_from_hyperliquid(days)
        except RuntimeError as e:
            # Fallback to database if Hyperliquid fails (rate limits)
            if "rate limiting" in str(e).lower():
                print(f"   ⚠️  {e}")
                print("   🔄 Fallback: using database instead...")
                trades = fetch_completed_trades_from_db(days)
            else:
                raise

    print(f"   ✅ {len(trades)} trade trovati\n")

    if not trades:
        return {
            'error': 'No trades found in the selected period',
            'total_trades': 0
        }

    # Analizza ogni trade con hindsight (solo se non stiamo usando solo DB)
    if not use_database_only:
        print("2️⃣  Analisi hindsight (cosa è successo dopo ogni close)...")
        for i, trade in enumerate(trades):
            print(f"   Analizzando {trade['symbol']} #{i+1}/{len(trades)}...", end='\r')
            trade['close_analysis'] = analyze_close_decision_quality(trade)
        print(f"   ✅ Analisi hindsight completata\n")
    else:
        # Skip hindsight analysis to avoid Hyperliquid API calls
        print("2️⃣  Skipping hindsight analysis (database-only mode to avoid rate limits)\n")
        for trade in trades:
            trade['close_analysis'] = {
                'close_quality': 'SKIPPED',
                'verdict': 'Hindsight analysis skipped (database-only mode)',
                'missed_opportunity_pct': 0
            }

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


def analyze_missed_opportunities_per_symbol(days: int = 7) -> Dict[str, Any]:
    """
    Analizza opportunità perse PER SIMBOLO indipendentemente.

    Identifica periodi dove:
    - Bot era HOLD su quel simbolo (nessuna posizione)
    - Score esisteva ma era sotto threshold
    - Prezzo si è mosso significativamente

    Args:
        days: Giorni di storico da analizzare

    Returns:
        {
            'BTC': {
                'total_missed_opportunities': 8,
                'avg_missed_profit_pct': 4.2,
                'total_potential_profit_usd': 280,
                'reasons': {...},
                'optimal_threshold': 12,
                'details': [...]
            },
            'ETH': {...},
            'SOL': {...}
        }
    """

    print(f"\n{'='*60}")
    print(f"🔍 ANALYZING MISSED OPPORTUNITIES PER SYMBOL")
    print(f"{'='*60}\n")

    bot = get_hyperliquid_bot()
    symbols = ['BTC', 'ETH', 'SOL']
    results = {}

    for symbol in symbols:
        print(f"   Analyzing {symbol}...", end='\r')

        # 1. Fetch signal scores per questo simbolo
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        created_at,
                        net_score,
                        direction,
                        confidence
                    FROM signal_scores
                    WHERE symbol = %s
                      AND created_at > NOW() - INTERVAL '%s days'
                    ORDER BY created_at
                """, (symbol, days))

                scores = cur.fetchall()

        # 2. Fetch bot operations per questo simbolo
        with db_utils.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        created_at,
                        operation,
                        raw_payload
                    FROM bot_operations
                    WHERE symbol = %s
                      AND created_at > NOW() - INTERVAL '%s days'
                    ORDER BY created_at
                """, (symbol, days))

                operations = cur.fetchall()

        # 3. Identifica periodi HOLD (no position su questo symbol)
        missed_opportunities = []
        total_missed_profit = 0
        reasons_count = {'score_below_threshold': 0, 'other': 0}

        SCORE_THRESHOLD_OPEN = float(os.getenv('SCORE_THRESHOLD_OPEN', '15'))

        # Per ogni score, controlla se c'era una posizione aperta
        for score_row in scores:
            score_time = score_row[0]
            net_score = float(score_row[1])
            direction = score_row[2]

            # Trova se c'era una posizione aperta in quel momento
            had_position = False
            for op in operations:
                op_time = op[0]
                op_type = op[1]
                if op_time <= score_time and op_type == 'open':
                    # Controlla se è stata chiusa prima dello score
                    closed = False
                    for close_op in operations:
                        if close_op[0] > op_time and close_op[0] <= score_time and close_op[1] == 'close':
                            closed = True
                            break
                    if not closed:
                        had_position = True
                        break

            # Se NON aveva posizione e score era vicino a threshold
            if not had_position and abs(net_score) < SCORE_THRESHOLD_OPEN and abs(net_score) > 10:
                # Controlla movimento prezzo nell'ora successiva
                try:
                    # Fetch candles per l'ora successiva
                    start_time = int(score_time.timestamp() * 1000)
                    end_time = int((score_time + timedelta(hours=1)).timestamp() * 1000)

                    candles = bot.exchange.info.candle_snapshot(
                        coin=symbol,
                        interval='1m',
                        startTime=start_time,
                        endTime=end_time
                    )

                    if candles and len(candles) > 0:
                        entry_price = float(candles[0]['c'])

                        # Trova movimento massimo
                        if direction == 'LONG':
                            peak_price = max([float(c['h']) for c in candles])
                            movement_pct = ((peak_price - entry_price) / entry_price) * 100
                        else:  # SHORT
                            peak_price = min([float(c['l']) for c in candles])
                            movement_pct = ((entry_price - peak_price) / entry_price) * 100

                        # Se movimento > 2%, è una missed opportunity
                        if movement_pct > 2.0:
                            missed_opportunities.append({
                                'timestamp': score_time,
                                'score': net_score,
                                'direction': direction,
                                'movement_pct': movement_pct,
                                'reason': 'Score below threshold' if abs(net_score) < SCORE_THRESHOLD_OPEN else 'Other'
                            })

                            total_missed_profit += movement_pct

                            if abs(net_score) < SCORE_THRESHOLD_OPEN:
                                reasons_count['score_below_threshold'] += 1
                            else:
                                reasons_count['other'] += 1

                except Exception as e:
                    # Skip se errore fetch candles
                    pass

        # 4. Calcola threshold ottimale
        optimal_threshold = _calculate_optimal_threshold(symbol, scores, days)

        results[symbol] = {
            'total_missed_opportunities': len(missed_opportunities),
            'avg_missed_profit_pct': total_missed_profit / len(missed_opportunities) if missed_opportunities else 0,
            'total_potential_profit_pct': total_missed_profit,
            'reasons': reasons_count,
            'optimal_threshold': optimal_threshold,
            'details': missed_opportunities[:5]  # Top 5
        }

        print(f"   ✅ {symbol}: {len(missed_opportunities)} missed opportunities")

    print(f"\n{'='*60}\n")
    return results


def _calculate_optimal_threshold(symbol: str, scores: List, days: int) -> float:
    """
    Calcola threshold ottimale per un simbolo basato su storico.

    Testa vari threshold (10, 12, 15, 18, 20) e vede quale massimizza profitto.
    """

    # Per semplicità, se media score è bassa, suggerisci threshold più basso
    if not scores:
        return 15.0

    avg_score = sum(abs(float(row[1])) for row in scores) / len(scores)

    if avg_score < 12:
        return 10.0
    elif avg_score < 14:
        return 12.0
    elif avg_score < 16:
        return 13.0
    else:
        return 15.0


def optimize_thresholds_per_symbol(days: int = 7) -> Dict[str, Any]:
    """
    Ottimizza SCORE_THRESHOLD_OPEN per ogni simbolo.

    Simula vari threshold e calcola quale massimizza profitto.

    Returns:
        {
            'BTC': {
                'current_threshold': 15,
                'optimal_threshold': 12,
                'impact': {
                    'additional_trades_per_week': 8,
                    'estimated_additional_profit_pct': 15.2
                }
            },
            ...
        }
    """

    missed_ops = analyze_missed_opportunities_per_symbol(days)

    results = {}
    for symbol, data in missed_ops.items():
        current_threshold = float(os.getenv('SCORE_THRESHOLD_OPEN', '15'))
        optimal_threshold = data['optimal_threshold']

        # Stima impatto: quante opportunità in più cattureresti?
        additional_trades = data['total_missed_opportunities']
        estimated_profit = data['total_potential_profit_pct']

        results[symbol] = {
            'current_threshold': current_threshold,
            'optimal_threshold': optimal_threshold,
            'impact': {
                'additional_trades_per_week': additional_trades * (7 / days),
                'estimated_additional_profit_pct': estimated_profit
            }
        }

    return results


def analyze_portfolio_opportunity_cost(days: int = 7) -> Dict[str, Any]:
    """
    Analizza opportunity cost: posizioni subottimali vs alternative migliori.

    Esempio: Avevi BTC (+2.5%) ma ETH avrebbe fatto +5.5%

    Returns:
        {
            'suboptimal_choices': [
                {
                    'timestamp': datetime,
                    'had_position': 'BTC',
                    'performance': +2.5,
                    'missed_alternatives': {
                        'ETH': {'score': 14, 'performance': +5.5, 'cost': +3.0}
                    }
                }
            ],
            'total_opportunity_cost_pct': 45.2,
            'suggestions': [...]
        }
    """

    print(f"\n{'='*60}")
    print(f"💰 ANALYZING PORTFOLIO OPPORTUNITY COST")
    print(f"{'='*60}\n")

    # Fetch tutte le operazioni e score
    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:
            # Operazioni con timestamp
            cur.execute("""
                SELECT
                    bo.created_at,
                    bo.symbol,
                    bo.operation,
                    bo.direction
                FROM bot_operations bo
                WHERE bo.created_at > NOW() - INTERVAL '%s days'
                ORDER BY bo.created_at
            """ % days)

            operations = cur.fetchall()

            # Score con timestamp
            cur.execute("""
                SELECT
                    created_at,
                    symbol,
                    net_score,
                    direction
                FROM signal_scores
                WHERE created_at > NOW() - INTERVAL '%s days'
                ORDER BY created_at
            """ % days)

            scores = cur.fetchall()

    suboptimal_choices = []
    total_opportunity_cost = 0

    # Per ogni momento con posizione aperta, confronta con alternative
    bot = get_hyperliquid_bot()

    # Raggruppa operazioni per trovare posizioni aperte in ogni momento
    open_positions_timeline = []
    current_positions = {}

    for op in operations:
        op_time, symbol, operation, direction = op

        if operation == 'open':
            current_positions[symbol] = {'time': op_time, 'direction': direction}
        elif operation == 'close' and symbol in current_positions:
            open_positions_timeline.append({
                'start': current_positions[symbol]['time'],
                'end': op_time,
                'symbol': symbol,
                'direction': current_positions[symbol]['direction']
            })
            del current_positions[symbol]

    # Per ogni periodo con posizione, confronta performance con alternative
    for period in open_positions_timeline[:5]:  # Limita a 5 per performance
        symbol = period['symbol']
        start_time = period['start']
        end_time = period['end']

        # Performance del simbolo scelto
        try:
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)

            candles = bot.exchange.info.candle_snapshot(
                coin=symbol,
                interval='1m',
                startTime=start_ts,
                endTime=end_ts
            )

            if candles:
                entry = float(candles[0]['c'])
                exit_price = float(candles[-1]['c'])
                performance = ((exit_price - entry) / entry) * 100

                # Controlla score di altri simboli nello stesso momento
                alternatives = {}
                for other_symbol in ['BTC', 'ETH', 'SOL']:
                    if other_symbol == symbol:
                        continue

                    # Score dell'alternativa
                    alt_score = None
                    for score_row in scores:
                        if score_row[1] == other_symbol and abs((score_row[0] - start_time).total_seconds()) < 300:
                            alt_score = float(score_row[2])
                            break

                    if alt_score:
                        # Performance dell'alternativa
                        try:
                            alt_candles = bot.exchange.info.candle_snapshot(
                                coin=other_symbol,
                                interval='1m',
                                startTime=start_ts,
                                endTime=end_ts
                            )

                            if alt_candles:
                                alt_entry = float(alt_candles[0]['c'])
                                alt_exit = float(alt_candles[-1]['c'])
                                alt_performance = ((alt_exit - alt_entry) / alt_entry) * 100

                                if alt_performance > performance + 2:  # Almeno 2% migliore
                                    alternatives[other_symbol] = {
                                        'score': alt_score,
                                        'performance': alt_performance,
                                        'opportunity_cost': alt_performance - performance
                                    }
                                    total_opportunity_cost += (alt_performance - performance)
                        except:
                            pass

                if alternatives:
                    suboptimal_choices.append({
                        'timestamp': start_time,
                        'had_position': symbol,
                        'performance': performance,
                        'missed_alternatives': alternatives
                    })

        except Exception as e:
            pass

    suggestions = []
    if suboptimal_choices:
        suggestions.append("Implementa position priority: chiudi posizione debole se arriva segnale più forte")
        suggestions.append("Considera aumentare MAX_OPEN_POSITIONS per catturare multiple opportunità")

    print(f"   ✅ Found {len(suboptimal_choices)} suboptimal choices\n")

    return {
        'suboptimal_choices': suboptimal_choices,
        'total_opportunity_cost_pct': total_opportunity_cost,
        'suggestions': suggestions
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

    # NEW: Per-symbol missed opportunities
    print("\n🔍 Testing Per-Symbol Analysis:")
    missed_ops = analyze_missed_opportunities_per_symbol(days=7)

    # NEW: Portfolio opportunity cost
    portfolio_cost = analyze_portfolio_opportunity_cost(days=7)
