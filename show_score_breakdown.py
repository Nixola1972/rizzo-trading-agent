#!/usr/bin/env python3
"""
Score Breakdown - Mostra il dettaglio di come viene calcolato lo score per ogni crypto.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from indicators import CryptoTechnicalAnalysisHL
from signal_scorer import calculate_signal_score
import db_utils

TESTNET = os.getenv("TESTNET", "true").lower() == "true"
ENABLED_SYMBOLS = [s.strip() for s in os.getenv('ENABLED_SYMBOLS', 'BTC,ETH,SOL').split(',')]

def show_breakdown():
    analyzer = CryptoTechnicalAnalysisHL(testnet=TESTNET)

    # Leggi Fear & Greed (globale per tutti)
    fear_greed = 50
    try:
        cached_sentiment = db_utils.get_cached_sentiment(max_age_minutes=60)
        if cached_sentiment and cached_sentiment.get('valore') is not None:
            fear_greed = cached_sentiment['valore']
    except:
        pass

    print("=" * 80)
    print(f"📊 SCORE BREAKDOWN - Fear & Greed GLOBALE: {fear_greed}")
    print("=" * 80)

    for symbol in ENABLED_SYMBOLS:
        print(f"\n{'='*40}")
        print(f"🪙 {symbol}")
        print(f"{'='*40}")

        try:
            data = analyzer.get_complete_analysis(symbol)
            if not data:
                print(f"   ❌ Nessun dato")
                continue

            intraday = data.get('intraday', {})

            rsi = intraday.get('rsi_14', [50])[-1] if intraday.get('rsi_14') else 50
            macd = intraday.get('macd', [0])[-1] if intraday.get('macd') else 0
            ema20 = intraday.get('ema_20', [0])[-1] if intraday.get('ema_20') else 0
            price = intraday.get('mid_prices', [0])[-1] if intraday.get('mid_prices') else 0

            # Volume
            volume_str = data.get('volume', '')
            volume_bid = 0.0
            volume_ask = 0.0
            if isinstance(volume_str, str) and "Bid Vol" in volume_str:
                try:
                    parts = volume_str.replace("Bid Vol:", "").split("Ask Vol:")
                    volume_bid = float(parts[0].strip().strip(","))
                    volume_ask = float(parts[1].strip())
                except:
                    pass

            print(f"\n📈 INDICATORI RAW:")
            print(f"   Price:    ${price:,.2f}")
            print(f"   EMA20:    ${ema20:,.2f}  {'(Price > EMA20 ✓)' if price > ema20 else '(Price < EMA20 ✗)'}")
            print(f"   RSI:      {rsi:.1f}     {'(OVERBOUGHT >70)' if rsi > 70 else '(OVERSOLD <30)' if rsi < 30 else '(Neutral 30-70)'}")
            print(f"   MACD:     {macd:.4f}  {'(Positive ✓)' if macd > 0 else '(Negative ✗)'}")
            print(f"   F&G:      {fear_greed}       {'(FEAR <30)' if fear_greed < 30 else '(GREED >60)' if fear_greed > 60 else '(Neutral 30-60)'}")
            print(f"   Volume:   Bid={volume_bid:.0f}, Ask={volume_ask:.0f}")

            # Calcola score
            result = calculate_signal_score(
                price=price,
                ema20=ema20,
                rsi=rsi,
                macd=macd,
                fear_greed=fear_greed,
                forecast_change_pct=0.0,
                volume_bid=volume_bid,
                volume_ask=volume_ask,
                symbol=symbol
            )

            print(f"\n📊 CONTRIBUTI SCORE:")
            for sig in result['signals']:
                direction_icon = "🟢" if sig['direction'] == 'BULLISH' else "🔴" if sig['direction'] == 'BEARISH' else "⚪"
                contrib = sig['contribution']
                if contrib != 0:
                    print(f"   {direction_icon} {sig['indicator']:20} → {'+' if sig['direction']=='BULLISH' else '-'}{abs(contrib):.1f} pts")
                    print(f"      {sig['reason']}")
                else:
                    print(f"   {direction_icon} {sig['indicator']:20} → 0 pts (neutral)")

            print(f"\n📈 RISULTATO:")
            print(f"   Bullish: +{result['score_bullish']:.1f}")
            print(f"   Bearish: -{result['score_bearish']:.1f}")
            print(f"   ─────────────────")
            print(f"   NET SCORE: {result['net_score']:+.1f} → {result['direction']} ({result['confidence']})")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

    print("\n" + "=" * 80)
    print("📝 LEGENDA:")
    print("   - Score contribuisce SOLO quando indicatore è FUORI dalla zona neutra")
    print("   - RSI: contribuisce solo se <30 o >70")
    print("   - F&G: contribuisce solo se <30 o >60")
    print("   - Trend: contribuisce solo se Price vs EMA20 E MACD concordano")
    print("=" * 80)


if __name__ == "__main__":
    show_breakdown()
