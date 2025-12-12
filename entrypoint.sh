#!/bin/bash

# Trap per gestire shutdown graceful
cleanup() {
    echo "[entrypoint] Ricevuto segnale di stop, terminando processi..."
    kill $MAIN_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[entrypoint] =========================================="
echo "[entrypoint] AVVIO CONTAINER TRADING BOT"
echo "[entrypoint] =========================================="
echo "[entrypoint] IMPORTANTE: Questo container esegue sia main.py che sentinel.py"
echo "[entrypoint] NON avviare altri container con sentinel.py!"
echo "[entrypoint] =========================================="

# Avvia main.py in background
echo "[entrypoint] Avvio main.py in loop (intervallo da AI_CALL_INTERVAL_MINUTES)..."
python3 main.py --loop &
MAIN_PID=$!

# Attendi un momento per evitare conflitti di avvio
sleep 3

# Avvia sentinel.py in foreground (se muore, il container si ferma)
echo "[entrypoint] Avvio sentinel.py --loop..."
python3 sentinel.py --loop

# Se sentinel.py termina, ferma anche main.py
echo "[entrypoint] sentinel.py terminato, fermo main.py..."
kill $MAIN_PID 2>/dev/null
