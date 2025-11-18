#!/bin/bash
# ===========================================
# SCRIPT DI SETUP RIZZO TRADING AGENT
# ===========================================

set -e  # Esci in caso di errore

echo "🤖 SETUP RIZZO TRADING AGENT"
echo "================================"
echo ""

# Colori per output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Verifica Python
echo "📌 Step 1: Verifica Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 non trovato! Installa Python 3.11+${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ $PYTHON_VERSION trovato${NC}"
echo ""

# 2. Verifica pip
echo "📌 Step 2: Verifica pip..."
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 non trovato! Installa pip${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip3 trovato${NC}"
echo ""

# 3. Crea virtual environment (opzionale ma consigliato)
echo "📌 Step 3: Virtual Environment..."
if [ ! -d "venv" ]; then
    echo "Creo virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment creato${NC}"
else
    echo -e "${YELLOW}⚠️  Virtual environment già esistente${NC}"
fi
echo ""

# 4. Attiva virtual environment
echo "📌 Step 4: Attivazione venv..."
source venv/bin/activate
echo -e "${GREEN}✅ Virtual environment attivato${NC}"
echo ""

# 5. Installa dipendenze
echo "📌 Step 5: Installazione dipendenze..."
echo "Questo può richiedere alcuni minuti..."
pip3 install --upgrade pip
pip3 install -r requirements.txt
echo -e "${GREEN}✅ Dipendenze installate${NC}"
echo ""

# 6. Verifica file .env
echo "📌 Step 6: Verifica configurazione..."
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ File .env non trovato!${NC}"
    echo "Copia .env.example e compila con i tuoi dati:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
else
    echo -e "${GREEN}✅ File .env trovato${NC}"
fi
echo ""

# 7. Test connessioni
echo "📌 Step 7: Test connessioni..."
echo "Eseguo test_connections.py..."
if python3 test_connections.py; then
    echo -e "${GREEN}✅ Tutte le connessioni OK!${NC}"
else
    echo -e "${RED}❌ Alcune connessioni fallite. Controlla il file .env${NC}"
    exit 1
fi
echo ""

echo "================================"
echo -e "${GREEN}🎉 SETUP COMPLETATO!${NC}"
echo ""
echo "Per avviare il bot:"
echo "  1. Attiva venv: source venv/bin/activate"
echo "  2. Esegui: python3 main.py"
echo ""
echo "Per esecuzione automatica:"
echo "  sudo ./install_service.sh"
echo ""
