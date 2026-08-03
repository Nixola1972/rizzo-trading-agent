#!/bin/bash
# Move 37 — avvio su Mac.
# Doppio clic su questo file. La prima volta impiega qualche minuto perché
# scarica quello che serve; dalle volte successive parte in pochi secondi.

cd "$(dirname "$0")" || exit 1
set -e

echo ""
echo "  MOVE 37"
echo "  ------------------------------------------------------------"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "  Python non è installato."
  echo ""
  echo "  Scaricalo da https://www.python.org/downloads/ (bottone giallo),"
  echo "  installalo, poi fai di nuovo doppio clic su questo file."
  echo ""
  read -r -p "  Premi Invio per chiudere."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "  Prima installazione — ci vogliono alcuni minuti."
  echo "  Succede una volta sola."
  echo ""
  python3 -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  ./.venv/bin/python -m pip install --quiet -r tools/requirements.txt
  echo "  Fatto."
  echo ""
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "  Nota: ffmpeg non è installato, quindi la trascrizione automatica"
  echo "  dell'audio non funziona. Puoi comunque incollare gli appunti."
  echo ""
  echo "  Per abilitarla: installa Homebrew da https://brew.sh"
  echo "  e poi da Terminale:  brew install ffmpeg"
  echo ""
fi

exec ./.venv/bin/python app/server.py
