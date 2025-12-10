#!/usr/bin/env python3
"""
Simulazione "LET IT RUN" - Cosa sarebbe successo lasciando correre i trade?

Questo script analizza i trade chiusi in perdita e simula cosa sarebbe successo
se avessimo usato SL più ampi o nessuno SL.

Esegui con: python3 simulate_letitrun.py
"""

import sys
sys.path.insert(0, '.')

import db_utils
from datetime import datetime, timedelta
from decimal import Decimal
import time

# Prova a importare hyperliquid per le candele
try:
    from hyperliquid.info import Info
    HL_AVAILABLE = True
except ImportError:
    HL_AVAILABLE = False
    print("⚠️ hyperliquid SDK non disponibile, uso dati simulati")


def get_candles_after_trade(symbol: str, start_time: datetime, hours: int = 24):
    """
    Ottiene le candele dopo un certo momento per simulare cosa sarebbe successo.
    """
    if not HL_AVAILABLE:
        return None

    try:
        info = Info(skip_ws=True)

        # Converti a timestamp milliseconds
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int((start_time + timedelta(hours=hours)).timestamp() * 1000)

        # Candele 15 minuti
        candles = info.candles_snapshot(symbol, "15m", start_ts, end_ts)

        if candles:
            return [{
                'timestamp': c['t'],
                'open': float(c['o']),
                'high': float(c['h']),
                'low': float(c['l']),
                'close': float(c['c'])
            } for c in candles]
        return None
    except Exception as e:
        print(f"   ⚠️ Errore fetch candele: {e}")
        return None


def simulate_trade_scenarios(entry_price: float, direction: str, candles: list, leverage: int = 5):
    """
    Simula vari scenari di SL/TP per un trade dato le candele future.

    Returns dict con risultati per ogni scenario.
    """
    results = {}

    # Scenari da testare
    scenarios = [
        {"name": "SL -1% (attuale)", "sl_pct": -1.0, "tp_pct": 4.0},
        {"name": "SL -2%", "sl_pct": -2.0, "tp_pct": 4.0},
        {"name": "SL -3%", "sl_pct": -3.0, "tp_pct": 4.0},
        {"name": "SL -5%", "sl_pct": -5.0, "tp_pct": 4.0},
        {"name": "SL -10%", "sl_pct": -10.0, "tp_pct": 4.0},
        {"name": "NO SL (solo TP 4%)", "sl_pct": -100.0, "tp_pct": 4.0},
        {"name": "TP 2% / SL -2%", "sl_pct": -2.0, "tp_pct": 2.0},
        {"name": "TP 1.5% / SL -1.5%", "sl_pct": -1.5, "tp_pct": 1.5},
        {"name": "TP 1% / SL -1%", "sl_pct": -1.0, "tp_pct": 1.0},
    ]

    for scenario in scenarios:
        sl_pct = scenario["sl_pct"]
        tp_pct = scenario["tp_pct"]

        # Calcola prezzi SL e TP
        if direction.upper() == "LONG":
            sl_price = entry_price * (1 + sl_pct / leverage / 100)
            tp_price = entry_price * (1 + tp_pct / leverage / 100)
        else:  # SHORT
            sl_price = entry_price * (1 - sl_pct / leverage / 100)
            tp_price = entry_price * (1 - tp_pct / leverage / 100)

        # Simula attraverso le candele
        exit_price = None
        exit_reason = None
        exit_candle_idx = None
        max_profit_pct = 0
        max_loss_pct = 0

        for i, candle in enumerate(candles):
            high = candle['high']
            low = candle['low']

            # Calcola P&L ai prezzi high/low
            if direction.upper() == "LONG":
                pnl_at_high = ((high - entry_price) / entry_price) * 100 * leverage
                pnl_at_low = ((low - entry_price) / entry_price) * 100 * leverage
            else:
                pnl_at_high = ((entry_price - high) / entry_price) * 100 * leverage
                pnl_at_low = ((entry_price - low) / entry_price) * 100 * leverage

            max_profit_pct = max(max_profit_pct, pnl_at_high, pnl_at_low)
            max_loss_pct = min(max_loss_pct, pnl_at_high, pnl_at_low)

            # Check SL hit
            if direction.upper() == "LONG":
                if low <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    exit_candle_idx = i
                    break
                if high >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    exit_candle_idx = i
                    break
            else:  # SHORT
                if high >= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    exit_candle_idx = i
                    break
                if low <= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    exit_candle_idx = i
                    break

        # Se non ha triggerato nulla, usa l'ultima candela
        if exit_price is None:
            exit_price = candles[-1]['close']
            exit_reason = "TIMEOUT"
            exit_candle_idx = len(candles) - 1

        # Calcola P&L finale
        if direction.upper() == "LONG":
            final_pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * leverage
        else:
            final_pnl_pct = ((entry_price - exit_price) / entry_price) * 100 * leverage

        results[scenario["name"]] = {
            "exit_reason": exit_reason,
            "exit_candle": exit_candle_idx,
            "exit_minutes": exit_candle_idx * 15 if exit_candle_idx else 0,
            "final_pnl_pct": round(final_pnl_pct, 2),
            "max_profit_pct": round(max_profit_pct, 2),
            "max_loss_pct": round(max_loss_pct, 2),
            "profitable": final_pnl_pct > 0
        }

    return results


def run_simulation():
    """Esegue la simulazione su tutti i trade persi."""

    print("=" * 90)
    print("🔬 SIMULAZIONE 'LET IT RUN' - Cosa sarebbe successo lasciando correre?")
    print("=" * 90)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:

            # Prendi i trade chiusi in perdita negli ultimi 7 giorni
            cur.execute("""
                SELECT
                    trade_uuid,
                    symbol,
                    direction,
                    entry_price,
                    exit_price,
                    opened_at,
                    closed_at,
                    pnl_percent,
                    net_pnl_usd,
                    leverage,
                    close_reason,
                    peak_pnl_percent
                FROM trades
                WHERE status = 'CLOSED'
                  AND profitable = false
                  AND opened_at > NOW() - INTERVAL '7 days'
                ORDER BY net_pnl_usd ASC
                LIMIT 50
            """)

            losing_trades = cur.fetchall()

            if not losing_trades:
                print("Nessun trade in perdita negli ultimi 7 giorni!")
                return

            print(f"\n📊 Analizzando {len(losing_trades)} trade in perdita...\n")

            # Aggregatori per statistiche
            scenario_stats = {}

            for trade in losing_trades:
                trade_uuid = str(trade[0])[:8]
                symbol = trade[1]
                direction = trade[2]
                entry_price = float(trade[3])
                actual_exit = float(trade[4]) if trade[4] else 0
                opened_at = trade[5]
                closed_at = trade[6]
                actual_pnl = float(trade[7]) if trade[7] else 0
                actual_net_usd = float(trade[8]) if trade[8] else 0
                leverage = int(trade[9]) if trade[9] else 5
                close_reason = trade[10]
                peak_pnl = float(trade[11]) if trade[11] else 0

                print(f"\n{'='*80}")
                print(f"📈 Trade {trade_uuid}: {symbol} {direction}")
                print(f"   Entry: ${entry_price:.2f} | Actual Exit: ${actual_exit:.2f}")
                print(f"   Actual P&L: {actual_pnl:.2f}% (${actual_net_usd:.2f}) | Peak: {peak_pnl:.2f}%")
                print(f"   Close Reason: {close_reason}")

                # Ottieni candele per simulazione (24 ore dopo apertura)
                if HL_AVAILABLE and opened_at:
                    candles = get_candles_after_trade(symbol, opened_at, hours=24)

                    if candles and len(candles) > 10:
                        print(f"   📊 Candele disponibili: {len(candles)} (15min ciascuna)")

                        # Simula scenari
                        results = simulate_trade_scenarios(entry_price, direction, candles, leverage)

                        print(f"\n   {'Scenario':<25} {'Exit':>10} {'P&L':>8} {'MaxProfit':>10} {'MaxLoss':>10} {'Mins':>6}")
                        print(f"   {'-'*75}")

                        for scenario_name, result in results.items():
                            pnl_str = f"{result['final_pnl_pct']:+.2f}%"
                            profit_str = f"{result['max_profit_pct']:+.2f}%"
                            loss_str = f"{result['max_loss_pct']:+.2f}%"

                            # Emoji per profitto/perdita
                            emoji = "✅" if result['profitable'] else "❌"

                            print(f"   {scenario_name:<25} {result['exit_reason']:>10} {pnl_str:>8} {profit_str:>10} {loss_str:>10} {result['exit_minutes']:>6} {emoji}")

                            # Aggrega statistiche
                            if scenario_name not in scenario_stats:
                                scenario_stats[scenario_name] = {
                                    "total_trades": 0,
                                    "wins": 0,
                                    "total_pnl": 0,
                                    "tp_hits": 0,
                                    "sl_hits": 0,
                                    "timeouts": 0
                                }

                            scenario_stats[scenario_name]["total_trades"] += 1
                            if result['profitable']:
                                scenario_stats[scenario_name]["wins"] += 1
                            scenario_stats[scenario_name]["total_pnl"] += result['final_pnl_pct']

                            if result['exit_reason'] == "TP_HIT":
                                scenario_stats[scenario_name]["tp_hits"] += 1
                            elif result['exit_reason'] == "SL_HIT":
                                scenario_stats[scenario_name]["sl_hits"] += 1
                            else:
                                scenario_stats[scenario_name]["timeouts"] += 1
                    else:
                        print("   ⚠️ Candele insufficienti per simulazione")
                else:
                    print("   ⚠️ Simulazione non disponibile (SDK mancante o data mancante)")

                time.sleep(0.5)  # Rate limiting

            # ========================================
            # RIEPILOGO FINALE
            # ========================================
            if scenario_stats:
                print("\n" + "=" * 90)
                print("📊 RIEPILOGO: QUALE STRATEGIA AVREBBE FUNZIONATO MEGLIO?")
                print("=" * 90)

                print(f"\n{'Scenario':<25} {'Trades':>7} {'Wins':>6} {'WR%':>6} {'Tot P&L':>10} {'TP':>5} {'SL':>5} {'T/O':>5}")
                print("-" * 85)

                # Ordina per P&L totale
                sorted_scenarios = sorted(scenario_stats.items(),
                                         key=lambda x: x[1]['total_pnl'],
                                         reverse=True)

                for scenario_name, stats in sorted_scenarios:
                    total = stats['total_trades']
                    wins = stats['wins']
                    wr = 100 * wins / total if total > 0 else 0
                    total_pnl = stats['total_pnl']

                    # Evidenzia il migliore
                    marker = " 🏆" if scenario_name == sorted_scenarios[0][0] else ""

                    print(f"{scenario_name:<25} {total:>7} {wins:>6} {wr:>5.1f}% {total_pnl:>+9.1f}% {stats['tp_hits']:>5} {stats['sl_hits']:>5} {stats['timeouts']:>5}{marker}")

                # Raccomandazioni
                best = sorted_scenarios[0]
                worst = sorted_scenarios[-1]

                print(f"\n💡 INSIGHT:")
                print(f"   🏆 Miglior scenario: {best[0]}")
                print(f"      - Avrebbe trasformato {best[1]['total_trades']} perdite in {best[1]['wins']} vincite")
                print(f"      - P&L totale: {best[1]['total_pnl']:+.1f}% invece di perdita")

                print(f"\n   ❌ Peggior scenario: {worst[0]}")
                print(f"      - P&L totale: {worst[1]['total_pnl']:+.1f}%")

                # Confronto con SL attuale
                if "SL -1% (attuale)" in scenario_stats:
                    current = scenario_stats["SL -1% (attuale)"]
                    print(f"\n   📊 Con SL attuale (-1%):")
                    print(f"      - Win Rate: {100*current['wins']/current['total_trades']:.1f}%")
                    print(f"      - P&L: {current['total_pnl']:+.1f}%")

                    improvement = best[1]['total_pnl'] - current['total_pnl']
                    print(f"\n   📈 Passando a '{best[0]}' guadagneresti {improvement:+.1f}% in più!")


def run_quick_analysis():
    """Analisi veloce senza API esterne - usa solo i dati del DB."""

    print("=" * 90)
    print("🔬 ANALISI 'LET IT RUN' - Basata su Peak P&L dei trade")
    print("=" * 90)

    with db_utils.get_connection() as conn:
        with conn.cursor() as cur:

            # Analisi: quanti trade in perdita avevano peak positivo?
            print("\n📊 TRADE PERSI CHE AVEVANO RAGGIUNTO PROFITTO:")

            cur.execute("""
                SELECT
                    COUNT(*) as total_losses,
                    COUNT(CASE WHEN peak_pnl_percent > 0 THEN 1 END) as had_profit,
                    COUNT(CASE WHEN peak_pnl_percent >= 1.0 THEN 1 END) as reached_1pct,
                    COUNT(CASE WHEN peak_pnl_percent >= 2.0 THEN 1 END) as reached_2pct,
                    COUNT(CASE WHEN peak_pnl_percent >= 3.0 THEN 1 END) as reached_3pct,
                    ROUND(AVG(peak_pnl_percent)::numeric, 2) as avg_peak,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_lost
                FROM trades
                WHERE status = 'CLOSED' AND profitable = false
            """)

            row = cur.fetchone()
            total_losses = row[0]
            had_profit = row[1]
            reached_1 = row[2]
            reached_2 = row[3]
            reached_3 = row[4]
            avg_peak = row[5]
            avg_exit = row[6]
            total_lost = row[7]

            print(f"\n   Trade totali in perdita: {total_losses}")
            print(f"   Perdita totale: ${total_lost}")
            print(f"\n   Di questi:")
            print(f"   - {had_profit} ({100*had_profit/total_losses:.1f}%) erano stati IN PROFITTO prima di perdere")
            print(f"   - {reached_1} ({100*reached_1/total_losses:.1f}%) avevano raggiunto +1%")
            print(f"   - {reached_2} ({100*reached_2/total_losses:.1f}%) avevano raggiunto +2%")
            print(f"   - {reached_3} ({100*reached_3/total_losses:.1f}%) avevano raggiunto +3%")
            print(f"\n   Peak medio prima di perdere: {avg_peak}%")
            print(f"   Uscita media: {avg_exit}%")

            # Analisi dettagliata per fascia di peak
            print("\n" + "=" * 90)
            print("📊 DETTAGLIO: TRADE PERSI PER FASCIA DI PEAK RAGGIUNTO")
            print("=" * 90)

            cur.execute("""
                SELECT
                    CASE
                        WHEN peak_pnl_percent < 0 THEN 'Mai in profit'
                        WHEN peak_pnl_percent < 0.5 THEN 'Peak 0-0.5%'
                        WHEN peak_pnl_percent < 1.0 THEN 'Peak 0.5-1%'
                        WHEN peak_pnl_percent < 1.5 THEN 'Peak 1-1.5%'
                        WHEN peak_pnl_percent < 2.0 THEN 'Peak 1.5-2%'
                        ELSE 'Peak 2%+'
                    END as peak_range,
                    COUNT(*) as count,
                    ROUND(AVG(pnl_percent)::numeric, 2) as avg_exit_pnl,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as total_lost,
                    ROUND(AVG(duration_seconds/60.0)::numeric, 0) as avg_duration_min
                FROM trades
                WHERE status = 'CLOSED' AND profitable = false
                GROUP BY
                    CASE
                        WHEN peak_pnl_percent < 0 THEN 'Mai in profit'
                        WHEN peak_pnl_percent < 0.5 THEN 'Peak 0-0.5%'
                        WHEN peak_pnl_percent < 1.0 THEN 'Peak 0.5-1%'
                        WHEN peak_pnl_percent < 1.5 THEN 'Peak 1-1.5%'
                        WHEN peak_pnl_percent < 2.0 THEN 'Peak 1.5-2%'
                        ELSE 'Peak 2%+'
                    END
                ORDER BY
                    CASE
                        WHEN peak_pnl_percent < 0 THEN 1
                        WHEN peak_pnl_percent < 0.5 THEN 2
                        WHEN peak_pnl_percent < 1.0 THEN 3
                        WHEN peak_pnl_percent < 1.5 THEN 4
                        WHEN peak_pnl_percent < 2.0 THEN 5
                        ELSE 6
                    END
            """)

            print(f"\n{'Peak Range':<15} {'Count':>7} {'Avg Exit':>10} {'Tot Lost':>12} {'Avg Mins':>10}")
            print("-" * 60)

            for row in cur.fetchall():
                print(f"{row[0]:<15} {row[1]:>7} {row[2]:>9}% ${row[3]:>11} {row[4]:>9}")

            # Simulazione: se avessimo chiuso al peak invece che in perdita
            print("\n" + "=" * 90)
            print("💰 SIMULAZIONE: SE AVESSIMO CHIUSO AL PEAK?")
            print("=" * 90)

            cur.execute("""
                SELECT
                    COUNT(*) as count,
                    ROUND(SUM(net_pnl_usd)::numeric, 2) as actual_lost,
                    -- Simula chiusura al peak (approssimativo, senza fees)
                    ROUND(SUM(
                        CASE WHEN peak_pnl_percent > 0
                        THEN (peak_pnl_percent / 100) * notional_value
                        ELSE net_pnl_usd END
                    )::numeric, 2) as if_closed_at_peak
                FROM trades
                WHERE status = 'CLOSED' AND profitable = false
            """)

            sim_row = cur.fetchone()
            actual_lost = float(sim_row[1] or 0)
            if_peak = float(sim_row[2] or 0)

            print(f"\n   Perdita REALE: ${actual_lost:.2f}")
            print(f"   Se chiusi al PEAK: ${if_peak:.2f}")
            print(f"   Differenza: ${if_peak - actual_lost:.2f}")

            if if_peak > actual_lost:
                print(f"\n   💡 Avresti GUADAGNATO ${if_peak - actual_lost:.2f} in più!")
                print(f"      → Suggerimento: TP più basso per catturare questi profitti")

            # Suggerimenti finali
            print("\n" + "=" * 90)
            print("💡 RACCOMANDAZIONI")
            print("=" * 90)

            if had_profit and had_profit > total_losses * 0.5:
                print(f"""
   ⚠️ PROBLEMA IDENTIFICATO: {100*had_profit/total_losses:.0f}% dei trade persi erano stati in profitto!

   Questo significa che:
   1. Il prezzo va NELLA TUA DIREZIONE ma poi torna indietro
   2. Non stai catturando i profitti quando li hai

   SOLUZIONI:

   A) TRAILING PIÙ AGGRESSIVO:
      MICRO_GAIN_TRAILING_STEPS=0.3:-1.5,0.5:0.0,0.8:0.3,1.2:0.6
      → Blocca breakeven appena raggiungi +0.5%

   B) TP PIÙ BASSO:
      MICRO_GAIN_TARGET_PERCENT=1.5
      → Chiudi prima, quando sei in profitto

   C) COMBO (raccomandato):
      MICRO_GAIN_TARGET_PERCENT=2.0
      MICRO_GAIN_TRAILING_STEPS=0.4:-1.0,0.7:0.0,1.0:0.4,1.5:0.8
      MICRO_GAIN_STOP_LOSS_PERCENT=1.5
""")

            if reached_1 and reached_1 > total_losses * 0.3:
                print(f"""
   📊 {100*reached_1/total_losses:.0f}% dei trade persi avevano raggiunto +1%!

   Con TP a 1.0%, questi sarebbero stati VINCENTI.

   Valuta: MICRO_GAIN_TARGET_PERCENT=1.0
""")


if __name__ == "__main__":
    # Prima esegui analisi veloce (solo DB)
    run_quick_analysis()

    print("\n" + "=" * 90)
    print("Vuoi eseguire la simulazione completa con candele? (richiede più tempo)")
    print("Per eseguirla: python3 simulate_letitrun.py --full")
    print("=" * 90)

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        run_simulation()
