#!/usr/bin/env python3
"""
Script diagnostico per verificare i simboli disponibili su HyperLiquid.
Esegui: docker exec rizzo-arena python /app/check_hl_symbols.py
"""

from hyperliquid.info import Info
from hyperliquid.utils import constants

def main():
    print("=" * 60)
    print("HYPERLIQUID - SIMBOLI DISPONIBILI")
    print("=" * 60)

    info = Info(constants.MAINNET_API_URL, skip_ws=True)

    # Get all mids (prices)
    mids = info.all_mids()

    print(f"\nTotale simboli disponibili: {len(mids)}")

    # Simboli che vogliamo testare
    test_symbols = ['BTC', 'ETH', 'SOL', 'DOGE', 'LINK', 'AVAX', 'ARB', 'SUI']

    print("\n--- VERIFICA SIMBOLI ARENA ---")
    for sym in test_symbols:
        if sym in mids:
            print(f"  ✅ {sym}: ${float(mids[sym]):,.2f}")
        else:
            print(f"  ❌ {sym}: NON TROVATO")
            # Cerca varianti
            variants = [s for s in mids.keys() if sym.lower() in s.lower()]
            if variants:
                print(f"     Possibili varianti: {variants}")

    print("\n--- TUTTI I SIMBOLI DISPONIBILI ---")
    for sym in sorted(mids.keys()):
        price = float(mids[sym])
        print(f"  {sym:12s} ${price:>12,.2f}")

    # Anche la meta per vedere i nomi esatti
    print("\n--- META UNIVERSE (nomi perp) ---")
    meta = info.meta()
    for perp in meta.get("universe", []):
        name = perp.get("name", "?")
        max_lev = perp.get("maxLeverage", "?")
        print(f"  {name:12s} (max leverage: {max_lev}x)")

if __name__ == "__main__":
    main()
