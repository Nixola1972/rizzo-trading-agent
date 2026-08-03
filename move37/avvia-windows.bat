@echo off
REM Move 37 - avvio su Windows.
REM Doppio clic su questo file. La prima volta impiega qualche minuto perche
REM scarica quello che serve; dalle volte successive parte in pochi secondi.

cd /d "%~dp0"

echo.
echo   MOVE 37
echo   ------------------------------------------------------------
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo   Python non e' installato.
  echo.
  echo   Scaricalo da https://www.python.org/downloads/
  echo   IMPORTANTE: durante l'installazione spunta la casella
  echo   "Add Python to PATH", altrimenti non funziona.
  echo.
  echo   Poi fai di nuovo doppio clic su questo file.
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo   Prima installazione - ci vogliono alcuni minuti.
  echo   Succede una volta sola.
  echo.
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet -r tools\requirements.txt
  echo   Fatto.
  echo.
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   Nota: ffmpeg non e' installato, quindi la trascrizione automatica
  echo   dell'audio non funziona. Puoi comunque incollare gli appunti.
  echo.
  echo   Per abilitarla, da PowerShell:  winget install ffmpeg
  echo.
)

.venv\Scripts\python.exe app\server.py
pause
