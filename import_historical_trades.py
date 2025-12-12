#!/usr/bin/env python3
"""
Script per importare trade storici nel Trade Journal.
Parsifica i dati dal formato Hyperliquid trade history.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2.extras import execute_values
import uuid

# Configurazione DB
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "memory_postgres"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "rizzo_trading"),
    "user": os.getenv("POSTGRES_USER", "tradingbot"),
    "password": os.getenv("POSTGRES_PASSWORD", "TradingBot2025!Secure")
}

# Dati storici (formato: data,symbol,action,price,size,notional,fee,pnl)
HISTORICAL_DATA = """
27/11/2025 - 19:43:16,BTC,Close Long,91758,0.001,91.758,0.039639,0.313361
27/11/2025 - 19:43:52,BTC,Open Long,91750,0.001,91.75,0.039636,-0.039636
27/11/2025 - 21:16:46,BTC,Close Long,91407,0.001,91.407,0.039487,-0.382487
27/11/2025 - 21:22:06,BTC,Open Short,91356,0.001,91.356,0.039465,-0.039465
27/11/2025 - 21:45:27,BTC,Close Short,91422,0.001,91.422,0.039494,-0.105494
27/11/2025 - 22:02:40,SOL,Open Short,142.16,0.15,21.324,0.009211,-0.009211
27/11/2025 - 22:06:08,BTC,Open Short,91215,0.001,91.215,0.039404,-0.039404
27/11/2025 - 23:07:17,SOL,Close Short,141.62,0.15,21.243,0.009176,0.071824
27/11/2025 - 23:34:14,ETH,Open Short,3027.3,0.0071,21.494,0.009285,-0.009285
27/11/2025 - 23:42:18,SOL,Open Short,141.21,0.11,15.533,0.00671,-0.00671
27/11/2025 - 23:44:15,ETH,Close Short,3010.8,0.0071,21.377,0.009234,0.108234
27/11/2025 - 23:45:14,ETH,Open Short,3005.2,0.0072,21.637,0.009347,-0.009347
27/11/2025 - 23:45:18,SOL,Close Short,140.49,0.11,15.454,0.006676,0.072524
27/11/2025 - 23:47:46,SOL,Open Short,140.95,0.11,15.505,0.006697,-0.006697
27/11/2025 - 23:53:16,SOL,Close Short,140.49,0.11,15.454,0.006676,0.043924
27/11/2025 - 23:53:27,SOL,Open Short,140.47,0.12,16.856,0.007281,-0.007281
28/11/2025 - 00:18:51,SOL,Close Short,141.3,0.12,16.956,0.007324,-0.106924
28/11/2025 - 00:19:26,SOL,Open Short,141.15,0.11,15.527,0.006707,-0.006707
28/11/2025 - 00:28:14,SOL,Close Short,140.76,0.11,15.484,0.006688,0.036212
28/11/2025 - 00:28:47,SOL,Open Short,140.81,0.11,15.489,0.006691,-0.006691
28/11/2025 - 00:31:05,SOL,Close Short,140.75,0.11,15.483,0.006688,-0.000088
28/11/2025 - 00:31:30,SOL,Open Short,140.73,0.11,15.480,0.006687,-0.006687
28/11/2025 - 00:47:25,SOL,Close Short,140.77,0.11,15.485,0.006689,-0.011089
28/11/2025 - 00:47:47,SOL,Open Short,140.74,0.11,15.481,0.006687,-0.006687
28/11/2025 - 00:52:22,ETH,Close Short,3014.6,0.0072,21.705,0.009376,-0.077576
28/11/2025 - 00:52:26,BTC,Close Short,91247,0.001,91.247,0.039418,-0.071418
28/11/2025 - 00:52:28,ETH,Open Short,3014.5,0.0064,19.293,0.008334,-0.008334
28/11/2025 - 00:53:17,BTC,Open Short,91265,0.001,91.265,0.039426,-0.039426
28/11/2025 - 01:01:09,SOL,Close Short,140.78,0.11,15.486,0.006689,-0.011089
28/11/2025 - 01:01:12,ETH,Close Short,3014.6,0.0064,19.293,0.008334,-0.008974
28/11/2025 - 01:01:17,BTC,Close Short,91301,0.001,91.301,0.039442,-0.075442
28/11/2025 - 01:01:43,BTC,Open Short,91244,0.001,91.244,0.039417,-0.039417
28/11/2025 - 01:01:55,ETH,Open Short,3012.4,0.0071,21.388,0.009239,-0.009239
28/11/2025 - 01:02:05,SOL,Open Short,140.66,0.11,15.473,0.006684,-0.006684
28/11/2025 - 02:10:33,BTC,Close Short,90940,0.001,90.94,0.013095,0.290905
28/11/2025 - 02:11:14,ETH,Close Short,2999.9,0.0071,21.299,0.009201,0.079701
28/11/2025 - 02:11:25,BTC,Open Short,90895,0.001,90.895,0.039266,-0.039266
28/11/2025 - 02:11:37,ETH,Open Short,2998.1,0.0065,19.487,0.008418,-0.008418
28/11/2025 - 02:22:57,SOL,Close Short,139.25,0.11,15.318,0.002205,0.152895
28/11/2025 - 02:23:22,SOL,Open Short,139.21,0.14,19.489,0.008419,-0.008419
28/11/2025 - 02:56:12,SOL,Close Short,138.78,0.14,19.429,0.008393,0.051807
28/11/2025 - 02:56:57,SOL,Open Short,138.86,0.14,19.440,0.008398,-0.008398
28/11/2025 - 03:55:49,ETH,Close Short,3013,0.0065,19.585,0.00846,-0.10531
28/11/2025 - 03:56:14,ETH,Open Short,3013.5,0.0062,18.684,0.008071,-0.008071
28/11/2025 - 04:07:09,SOL,Close Short,139.56,0.14,19.538,0.00844,-0.106440
28/11/2025 - 04:07:34,SOL,Open Short,139.54,0.14,19.536,0.008439,-0.008439
28/11/2025 - 04:14:59,ETH,Close Short,3003.5,0.0062,18.622,0.002681,0.059319
28/11/2025 - 04:15:06,ETH,Open Short,2999.9,0.0063,18.899,0.008164,-0.008164
28/11/2025 - 04:30:27,BTC,Close Short,91196,0.001,91.196,0.039395,-0.340395
28/11/2025 - 04:30:40,BTC,Open Short,91192,0.00099,90.280,0.039,-0.039
28/11/2025 - 05:10:50,ETH,Close Short,3015.4,0.0063,18.997,0.008206,-0.105856
28/11/2025 - 05:11:41,ETH,Open Short,3015.3,0.006,18.092,0.007815,-0.007815
28/11/2025 - 06:50:47,BTC,Close Short,91653,0.00099,90.736,0.039198,-0.495588
28/11/2025 - 06:52:27,BTC,Open Long,91673,0.00096,88.006,0.038018,-0.038018
"""

def parse_datetime(date_str):
    """Parse datetime from format: 27/11/2025 - 19:43:16"""
    return datetime.strptime(date_str.strip(), "%d/%m/%Y - %H:%M:%S")

def parse_trades():
    """Parse historical data into trade records."""
    lines = [l.strip() for l in HISTORICAL_DATA.strip().split('\n') if l.strip()]

    trades = []
    for line in lines:
        parts = line.split(',')
        if len(parts) < 8:
            print(f"Skipping invalid line: {line}")
            continue

        dt = parse_datetime(parts[0])
        symbol = parts[1].strip()
        action = parts[2].strip()
        price = float(parts[3])
        size = float(parts[4])
        notional = float(parts[5])
        fee = float(parts[6])
        pnl = float(parts[7])

        # Determine direction and operation
        if "Long" in action:
            direction = "LONG"
        else:
            direction = "SHORT"

        if "Open" in action:
            operation = "OPEN"
        else:
            operation = "CLOSE"

        trades.append({
            "datetime": dt,
            "symbol": symbol,
            "direction": direction,
            "operation": operation,
            "price": price,
            "size": size,
            "notional": notional,
            "fee": fee,
            "pnl": pnl
        })

    return trades

def match_trades(trades):
    """Match OPEN/CLOSE pairs to create complete trades."""
    # Group by symbol
    by_symbol = {}
    for t in trades:
        if t["symbol"] not in by_symbol:
            by_symbol[t["symbol"]] = []
        by_symbol[t["symbol"]].append(t)

    complete_trades = []

    for symbol, symbol_trades in by_symbol.items():
        # Sort by datetime
        symbol_trades.sort(key=lambda x: x["datetime"])

        open_trade = None

        for t in symbol_trades:
            if t["operation"] == "OPEN":
                open_trade = t
            elif t["operation"] == "CLOSE" and open_trade:
                # Match found!
                entry_price = open_trade["price"]
                exit_price = t["price"]
                size = open_trade["size"]
                direction = open_trade["direction"]

                # Calculate P&L
                if direction == "LONG":
                    pnl_usd = (exit_price - entry_price) * size
                else:  # SHORT
                    pnl_usd = (entry_price - exit_price) * size

                fee_total = open_trade["fee"] + t["fee"]
                net_pnl = pnl_usd - fee_total

                # Determine close reason based on P&L direction
                if net_pnl > 0:
                    close_reason = "TP_HIT"
                else:
                    close_reason = "SL_HIT"

                complete_trades.append({
                    "symbol": symbol,
                    "direction": direction,
                    "trading_mode": "MICRO_PAY",  # Assume MICRO_PAY for historical
                    "opened_at": open_trade["datetime"],
                    "closed_at": t["datetime"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "size": size,
                    "leverage": 3,
                    "notional_value": open_trade["notional"],
                    "pnl_usd": pnl_usd,
                    "fee_open": open_trade["fee"],
                    "fee_close": t["fee"],
                    "fee_total": fee_total,
                    "net_pnl_usd": net_pnl,
                    "profitable": net_pnl > 0,
                    "close_reason": close_reason
                })

                open_trade = None

    return complete_trades

def import_to_db(complete_trades):
    """Import complete trades to database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0

    for trade in complete_trades:
        try:
            # Calculate duration
            duration = int((trade["closed_at"] - trade["opened_at"]).total_seconds())

            # Calculate margin used
            margin_used = trade["notional_value"] / trade["leverage"] if trade["leverage"] > 0 else trade["notional_value"]

            # Calculate net P&L percent (on margin)
            net_pnl_percent = (trade["net_pnl_usd"] / margin_used * 100) if margin_used > 0 else 0

            # Calculate gross P&L percent
            pnl_percent = (trade["pnl_usd"] / margin_used * 100) if margin_used > 0 else 0

            cur.execute("""
                INSERT INTO trades (
                    trade_uuid, symbol, direction, trading_mode, status,
                    opened_at, closed_at, duration_seconds,
                    entry_price, exit_price, size, leverage,
                    notional_value, margin_used,
                    pnl_percent, pnl_usd,
                    fee_open, fee_close, fee_total,
                    net_pnl_usd, net_pnl_percent, profitable,
                    close_reason,
                    sl_percent_config, tp_percent_config
                ) VALUES (
                    %s, %s, %s, %s, 'CLOSED',
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s
                )
            """, (
                str(uuid.uuid4()),
                trade["symbol"],
                trade["direction"],
                trade["trading_mode"],
                trade["opened_at"],
                trade["closed_at"],
                duration,
                trade["entry_price"],
                trade["exit_price"],
                trade["size"],
                trade["leverage"],
                trade["notional_value"],
                margin_used,
                pnl_percent,
                trade["pnl_usd"],
                trade["fee_open"],
                trade["fee_close"],
                trade["fee_total"],
                trade["net_pnl_usd"],
                net_pnl_percent,
                trade["profitable"],
                trade["close_reason"],
                1.5,  # SL percent config
                1.2   # TP percent config
            ))

            inserted += 1
            print(f"✅ Imported: {trade['symbol']} {trade['direction']} @ {trade['opened_at']} -> P&L: ${trade['net_pnl_usd']:.4f}")

        except Exception as e:
            print(f"❌ Error importing trade: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()

    return inserted

def main():
    print("=" * 60)
    print("IMPORT HISTORICAL TRADES")
    print("=" * 60)

    # Parse data
    print("\n📊 Parsing trade data...")
    trades = parse_trades()
    print(f"   Found {len(trades)} trade records")

    # Match open/close pairs
    print("\n🔗 Matching OPEN/CLOSE pairs...")
    complete_trades = match_trades(trades)
    print(f"   Matched {len(complete_trades)} complete trades")

    # Show summary
    print("\n📈 Trade Summary:")
    wins = sum(1 for t in complete_trades if t["profitable"])
    losses = len(complete_trades) - wins
    total_pnl = sum(t["net_pnl_usd"] for t in complete_trades)

    print(f"   Total trades: {len(complete_trades)}")
    print(f"   Wins: {wins} ({wins/len(complete_trades)*100:.1f}%)")
    print(f"   Losses: {losses} ({losses/len(complete_trades)*100:.1f}%)")
    print(f"   Total Net P&L: ${total_pnl:.4f}")

    # Import to DB
    print("\n💾 Importing to database...")
    inserted = import_to_db(complete_trades)
    print(f"\n✅ Successfully imported {inserted} trades!")

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == "__main__":
    main()
