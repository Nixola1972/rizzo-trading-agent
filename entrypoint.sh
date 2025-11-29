#!/bin/bash
echo "[entrypoint] Avvio iniziale main.py..."
python3 main.py &
MAIN_PID=$!

echo "[entrypoint] Avvio sentinel.py --loop..."
python3 sentinel.py --loop
