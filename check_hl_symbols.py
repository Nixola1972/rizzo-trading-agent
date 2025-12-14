#!/usr/bin/env python3
"""
Script diagnostico per verificare i simboli disponibili su HyperLiquid.
Esegui: docker exec rizzo-arena python /app/check_hl_symbols.py
"""

from hyperliquid.info import Info
from hyperliquid.utils import constants

def main():
    print("=" * 60)
    print("HYPERLIQUID - SIMBOLI DISPONIBILI (PERPETUALS)")
    print("=" * 60)

    info = Info(constants.MAINNET_API_URL, skip_ws=True)

    # Get meta for universe (lista ufficiale dei perpetual)
    meta = info.meta()
    universe = meta.get("universe", [])

    # Costruisci set di nomi validi
    valid_perps = {perp.get("name", "").upper() for perp in universe}

    print(f"\nTotale PERPETUAL disponibili: {len(valid_perps)}")

    # Simboli che vogliamo testare
    test_symbols = ['BTC', 'ETH', 'SOL', 'DOGE', 'LINK', 'AVAX', 'ARB', 'SUI',
                    'XRP', 'ADA', 'MATIC', 'DOT', 'SHIB', 'LTC', 'ATOM']

    print("\n" + "=" * 60)
    print("VERIFICA SIMBOLI ARENA")
    print("=" * 60)

    available = []
    not_available = []

    for sym in test_symbols:
        if sym.upper() in valid_perps:
            available.append(sym)
            print(f"  ✅ {sym}: DISPONIBILE")
        else:
            not_available.append(sym)
            print(f"  ❌ {sym}: NON ESISTE COME PERPETUAL")
            # Cerca varianti simili
            variants = [s for s in valid_perps if sym.lower() in s.lower()]
            if variants:
                print(f"     → Forse intendevi: {variants}")

    print("\n" + "=" * 60)
    print(f"RIEPILOGO: {len(available)} disponibili, {len(not_available)} NON disponibili")
    print("=" * 60)
    print(f"✅ Usabili: {', '.join(available)}")
    print(f"❌ Da rimuovere: {', '.join(not_available)}")

    # Get all mids (prices) per quelli disponibili
    print("\n" + "=" * 60)
    print("PREZZI CORRENTI")
    print("=" * 60)

    try:
        mids = info.all_mids()
        for sym in available:
            if sym in mids:
                print(f"  {sym:8s} ${float(mids[sym]):>12,.2f}")
    except Exception as e:
        print(f"  Errore getting prices: {e}")

    print("\n" + "=" * 60)
    print("LISTA COMPLETA PERPETUAL HYPERLIQUID")
    print("=" * 60)

    for perp in sorted(universe, key=lambda x: x.get("name", "")):
        name = perp.get("name", "?")
        max_lev = perp.get("maxLeverage", "?")
        print(f"  {name:12s} (max leverage: {max_lev}x)")

if __name__ == "__main__":
    main()
