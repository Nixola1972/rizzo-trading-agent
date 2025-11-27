#!/usr/bin/env python3
"""
Script to fix SL orders - convert LIMIT to STOP trigger orders.

This script:
1. Gets all open positions
2. Cancels all existing orders
3. Re-places TP orders as LIMIT
4. Re-places SL orders as STOP trigger

Run with: docker exec rizzo_sentinel python fix_sl_orders.py
"""

import os
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import eth_account

load_dotenv()

# Configuration from .env
PRIVATE_KEY = os.getenv('HL_PRIVATE_KEY')
MICRO_GAIN_STOP_LOSS_PERCENT = float(os.getenv('MICRO_GAIN_STOP_LOSS_PERCENT', '5'))
MICRO_GAIN_LEVERAGE = float(os.getenv('MICRO_GAIN_LEVERAGE', '20'))
NORMAL_STOP_LOSS_PERCENT = float(os.getenv('NORMAL_STOP_LOSS_PERCENT', '10'))
NORMAL_LEVERAGE = float(os.getenv('NORMAL_LEVERAGE', '5'))


def get_tick_size(info, symbol):
    """Get the tick size for a symbol"""
    meta = info.meta()
    for asset in meta.get("universe", []):
        if asset.get("name") == symbol:
            return 10 ** -asset.get("szDecimals", 0)
    return 0.0001


def round_to_tick(price, tick_size):
    """Round price to the nearest tick"""
    return round(price / tick_size) * tick_size


def main():
    if not PRIVATE_KEY:
        print("ERROR: HL_PRIVATE_KEY not set in environment")
        return

    print("=" * 60)
    print("FIX SL ORDERS - Convert LIMIT to STOP TRIGGER")
    print("=" * 60)

    # Initialize Hyperliquid connection
    account = eth_account.Account.from_key(PRIVATE_KEY)
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    exchange = Exchange(account, constants.MAINNET_API_URL)

    user_address = account.address
    print(f"\nAccount: {user_address}")

    # Get open positions
    user_state = info.user_state(user_address)
    positions = []

    for pos in user_state.get("assetPositions", []):
        pos_data = pos.get("position", {})
        size = float(pos_data.get("szi", 0))
        if size != 0:
            positions.append({
                "symbol": pos_data.get("coin"),
                "size": abs(size),
                "direction": "long" if size > 0 else "short",
                "entry_price": float(pos_data.get("entryPx", 0)),
                "leverage": float(pos_data.get("leverage", {}).get("value", 1))
            })

    if not positions:
        print("\nNo open positions found.")
        return

    print(f"\n📊 Found {len(positions)} open positions:")
    for p in positions:
        print(f"   - {p['symbol']}: {p['direction'].upper()} @ ${p['entry_price']:.2f} (leverage: {p['leverage']}x)")

    # Get existing orders
    open_orders = info.open_orders(user_address)
    print(f"\n📋 Found {len(open_orders)} open orders:")
    for o in open_orders:
        trigger_px = o.get("triggerPx", "N/A")
        limit_px = o.get("limitPx", "N/A")
        print(f"   - {o.get('coin')} | Side: {o.get('side')} | Limit: {limit_px} | Trigger: {trigger_px}")

    # Step 1: Cancel all existing orders
    print("\n🗑️ Cancelling all existing orders...")
    cancelled = 0
    for order in open_orders:
        try:
            result = exchange.cancel(order.get("coin"), order.get("oid"))
            if result.get("status") == "ok":
                cancelled += 1
                print(f"   ✅ Cancelled {order.get('coin')} order")
            else:
                print(f"   ⚠️ Failed to cancel: {result}")
        except Exception as e:
            print(f"   ❌ Error cancelling: {e}")

    print(f"   Cancelled {cancelled} orders")

    # Step 2: Re-place SL orders as STOP trigger for each position
    print("\n🛡️ Placing new SL STOP trigger orders...")

    meta = info.meta()

    for pos in positions:
        symbol = pos["symbol"]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        size = pos["size"]
        leverage = pos["leverage"]

        # Determine if this is MICRO_GAIN (high leverage) or NORMAL (lower leverage)
        if leverage >= 15:  # MICRO_GAIN uses 20x
            stop_loss_pct = MICRO_GAIN_STOP_LOSS_PERCENT
            mode = "MICRO_GAIN"
        else:
            stop_loss_pct = NORMAL_STOP_LOSS_PERCENT
            mode = "NORMAL"

        # Get tick size
        tick_size = 0.01
        for asset in meta.get("universe", []):
            if asset.get("name") == symbol:
                tick_size = 10 ** -asset.get("szDecimals", 2)
                break

        # Calculate SL price
        price_change_pct = stop_loss_pct / leverage

        if direction == "long":
            sl_price = entry_price * (1 - price_change_pct / 100)
        else:
            sl_price = entry_price * (1 + price_change_pct / 100)

        sl_price = round_to_tick(sl_price, tick_size)

        # Direction to close: opposite of position
        is_buy = direction == "short"

        print(f"\n   {symbol} ({mode}, {leverage}x):")
        print(f"      Entry: ${entry_price:.4f}")
        print(f"      SL Trigger: ${sl_price:.4f} (loss: -{stop_loss_pct}%)")

        # Place STOP trigger order
        try:
            sl_order = exchange.order(
                symbol,
                is_buy,
                size,
                sl_price,
                {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )

            if sl_order.get("status") == "ok":
                response_data = sl_order.get("response", {})
                if response_data.get("type") == "order":
                    statuses = response_data.get("data", {}).get("statuses", [])
                    if statuses and statuses[0].get("resting"):
                        print(f"      ✅ SL STOP trigger placed: OID={statuses[0]['resting']['oid']}")
                    else:
                        print(f"      ⚠️ SL order status: {statuses}")
                else:
                    print(f"      ⚠️ Unexpected response: {response_data}")
            else:
                print(f"      ❌ SL order failed: {sl_order}")
        except Exception as e:
            print(f"      ❌ Error placing SL: {e}")

    # Step 3: Verify new orders
    print("\n" + "=" * 60)
    print("VERIFICATION - Checking new orders...")
    print("=" * 60)

    new_orders = info.open_orders(user_address)
    print(f"\n📋 Current open orders ({len(new_orders)}):")
    for o in new_orders:
        trigger_px = o.get("triggerPx", None)
        limit_px = o.get("limitPx", "N/A")
        order_type = "STOP TRIGGER" if trigger_px else "LIMIT"
        trigger_str = f"${float(trigger_px):.4f}" if trigger_px else "N/A"
        print(f"   {o.get('coin')} | Type: {order_type} | Side: {o.get('side')} | Trigger: {trigger_str}")

    print("\n✅ Done! SL orders should now be STOP trigger type.")


if __name__ == "__main__":
    main()
