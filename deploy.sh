#!/bin/bash
# ===========================================
# DEPLOY SCRIPT - Rizzo Trading Agent
# Aggiorna e rilancia il bot in un comando
# ===========================================

set -e

# Colori per output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 DEPLOY RIZZO TRADING AGENT${NC}"
echo "=================================="
echo ""

# 1. Pull ultimo codice da Git
echo -e "${YELLOW}📥 Step 1: Pull codice da GitHub...${NC}"
git fetch origin
CURRENT_BRANCH=$(git branch --show-current)
echo "Branch corrente: $CURRENT_BRANCH"

# Controlla se ci sono modifiche locali
if [[ -n $(git status -s) ]]; then
    echo -e "${YELLOW}⚠️  Modifiche locali rilevate. Stashing...${NC}"
    git stash
    STASHED=true
fi

git pull origin "$CURRENT_BRANCH"
echo -e "${GREEN}✅ Codice aggiornato${NC}"
echo ""

# 2. Rebuild container (se Dockerfile è cambiato)
echo -e "${YELLOW}🔨 Step 2: Rebuild container...${NC}"
docker-compose build --no-cache trading-bot
echo -e "${GREEN}✅ Container rebuilt${NC}"
echo ""

# 3. Restart servizi
echo -e "${YELLOW}🔄 Step 3: Restart servizi...${NC}"
docker-compose down
docker-compose up -d
echo -e "${GREEN}✅ Servizi riavviati${NC}"
echo ""

# 4. Verifica stato
echo -e "${YELLOW}🔍 Step 4: Verifica stato...${NC}"
sleep 5  # Attendi che i container si avviino
docker-compose ps
echo ""

# 5. Mostra log
echo -e "${YELLOW}📋 Step 5: Log ultimi 20 righe...${NC}"
docker-compose logs --tail=20 trading-bot
echo ""

# Restore stash se necessario
if [ "$STASHED" = true ]; then
    echo -e "${YELLOW}📦 Ripristino modifiche locali...${NC}"
    git stash pop
fi

echo "=================================="
echo -e "${GREEN}✅ DEPLOY COMPLETATO!${NC}"
echo ""
echo "Comandi utili:"
echo "  • Log live:    docker-compose logs -f trading-bot"
echo "  • Restart:     docker-compose restart trading-bot"
echo "  • Stop:        docker-compose down"
echo "  • Status:      docker-compose ps"
echo "  • Shell:       docker-compose exec trading-bot bash"
echo ""
