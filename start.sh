#!/bin/bash
# Script di avvio che lancia sia main.py che sentinel.py

echo "🚀 Avvio Trading Bot + Sentinel..."

# Avvia main.py in background
echo "📊 Avvio main.py --loop (AI decisions)..."
python main.py --loop &
MAIN_PID=$!

# Aspetta un po' per evitare conflitti di avvio
sleep 5

# Avvia sentinel.py in background
echo "🛡️  Avvio sentinel.py --loop (trailing stop monitor)..."
python sentinel.py --loop &
SENTINEL_PID=$!

echo "✅ Processi avviati:"
echo "   - main.py PID: $MAIN_PID"
echo "   - sentinel.py PID: $SENTINEL_PID"

# Aspetta che uno dei due termini (trap per shutdown graceful)
trap "kill $MAIN_PID $SENTINEL_PID 2>/dev/null; exit" SIGTERM SIGINT

# Mantieni il container attivo
wait
