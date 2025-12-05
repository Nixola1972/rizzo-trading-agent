#!/bin/bash
echo "[entrypoint] Avvio main.py in loop (intervallo da AI_CALL_INTERVAL_MINUTES)..."
python3 main.py --loop &
MAIN_PID=$!

echo "[entrypoint] Avvio sentinel.py --loop..."
python3 sentinel.py --loop
