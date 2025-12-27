#!/usr/bin/env python3
"""
Check all available data on HyperLiquid.

This script queries HyperLiquid API to find:
1. All available trading pairs (coins)
2. The earliest data available for each
3. Total days of history per coin

Usage:
    python -m alpha.check_available_data
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import time

HL_API = "https://api.hyperliquid.xyz/info"

def get_all_coins() -> List[Dict]:
    """Get list of all available coins on HyperLiquid."""
    try:
        response = requests.post(
            HL_API,
            json={"type": "meta"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            # universe contains all tradeable assets
            return data.get("universe", [])
    except Exception as e:
        print(f"Error fetching coins: {e}")
    return []


def get_earliest_candle(symbol: str, interval: str = "1d") -> Tuple[datetime, int]:
    """
    Find the earliest available candle for a symbol.

    Returns: (earliest_date, total_days)
    """
    # Start from a very old date and work forward
    # HyperLiquid launched in late 2022
    test_start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    try:
        response = requests.post(
            HL_API,
            json={
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": interval,
                    "startTime": int(test_start.timestamp() * 1000),
                    "endTime": int(now.timestamp() * 1000),
                }
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                # First candle timestamp
                first_ts = data[0].get('t', 0)
                if first_ts:
                    earliest = datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc)
                    days = (now - earliest).days
                    return earliest, days
    except Exception as e:
        print(f"  Error checking {symbol}: {e}")

    return None, 0


def check_s3_dates() -> List[str]:
    """Check available dates in S3 bucket."""
    try:
        # List S3 bucket contents (public bucket)
        import subprocess
        result = subprocess.run(
            ["aws", "s3", "ls", "s3://hyperliquid-archive/", "--no-sign-request"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # Parse dates from directory listing
            dates = []
            for line in result.stdout.split('\n'):
                if 'PRE' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        date_str = parts[-1].rstrip('/')
                        if len(date_str) == 10:  # YYYY-MM-DD format
                            dates.append(date_str)
            return sorted(dates)
    except Exception as e:
        print(f"  S3 check failed (AWS CLI may not be installed): {e}")
    return []


def main():
    print("=" * 70)
    print("🔍 HyperLiquid Data Availability Check")
    print("=" * 70)

    # 1. Get all coins
    print("\n📊 Fetching available coins...")
    coins = get_all_coins()

    if not coins:
        print("❌ Could not fetch coin list")
        return

    print(f"✅ Found {len(coins)} tradeable assets\n")

    # 2. Check each coin
    print("📅 Checking historical data availability...")
    print("-" * 70)
    print(f"{'Coin':<10} {'Earliest Date':<20} {'Days':<10} {'~Candles (15m)':<15}")
    print("-" * 70)

    results = []

    for coin_info in coins:
        name = coin_info.get("name", "")
        if not name:
            continue

        earliest, days = get_earliest_candle(name)

        if earliest:
            candles_15m = days * 96  # 96 candles per day at 15m
            results.append({
                "name": name,
                "earliest": earliest,
                "days": days,
                "candles_15m": candles_15m
            })
            print(f"{name:<10} {earliest.strftime('%Y-%m-%d'):<20} {days:<10} {candles_15m:,}")
        else:
            print(f"{name:<10} {'No data':<20} {'-':<10} {'-'}")

        time.sleep(0.1)  # Rate limiting

    # 3. Summary
    print("-" * 70)
    print(f"\n📈 SUMMARY:")
    print(f"   Total coins with data: {len(results)}")

    if results:
        # Sort by days available
        results.sort(key=lambda x: x["days"], reverse=True)

        print(f"\n🏆 Top 10 coins by history length:")
        for i, r in enumerate(results[:10], 1):
            print(f"   {i}. {r['name']}: {r['days']} days ({r['earliest'].strftime('%Y-%m-%d')} - today)")

        total_candles = sum(r["candles_15m"] for r in results)
        print(f"\n📊 Total potential training data:")
        print(f"   • {len(results)} coins")
        print(f"   • {total_candles:,} candles (15m interval)")
        print(f"   • Oldest data: {min(r['earliest'] for r in results).strftime('%Y-%m-%d')}")

    # 4. Check S3
    print(f"\n📦 Checking S3 bulk data...")
    s3_dates = check_s3_dates()
    if s3_dates:
        print(f"   ✅ S3 data available: {s3_dates[0]} to {s3_dates[-1]}")
        print(f"   Total days in S3: {len(s3_dates)}")
    else:
        print("   ⚠️ Could not check S3 (AWS CLI needed)")

    # 5. Recommendation
    print(f"\n" + "=" * 70)
    print("💡 RECOMMENDATION:")
    print("=" * 70)

    if results:
        # Top coins with most data
        top_coins = [r["name"] for r in results[:15]]
        oldest = min(r["days"] for r in results[:15])

        print(f"\nFor maximum training data, use these {len(top_coins)} coins:")
        print(f"   {','.join(top_coins)}")
        print(f"\nAll have at least {oldest} days of history.")
        print(f"\nDownload command:")
        print(f"   docker run -v $(pwd)/alpha/data:/app/alpha/data \\")
        print(f"     -e DAYS={oldest} \\")
        print(f"     -e SYMBOLS=\"{' '.join(top_coins)}\" \\")
        print(f"     alphatrader download-api")

    # Save results to JSON
    output = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_coins": len(results),
        "coins": [
            {
                "name": r["name"],
                "earliest": r["earliest"].isoformat(),
                "days": r["days"],
                "candles_15m": r["candles_15m"]
            }
            for r in results
        ]
    }

    with open("alpha/data/available_data.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n📄 Results saved to: alpha/data/available_data.json")


if __name__ == "__main__":
    main()
