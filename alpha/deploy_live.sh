#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# ALPHATRADER 15m LIVE DEPLOYMENT
# ═══════════════════════════════════════════════════════════════════════════
# Configurazione ottimizzata:
# - 7 simboli profittevoli (esclusi BTC, SOL, XRP, BNB)
# - Max hold: 7 minuti
# - MCTS disabilitato (dati mostrano che non migliora)
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}        ALPHATRADER 15m LIVE DEPLOYMENT                     ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

# Verifica che siamo nella directory giusta
if [ ! -f "Dockerfile.alpha" ]; then
    echo -e "${RED}Errore: Esegui questo script dalla directory rizzo-trading-agent${NC}"
    exit 1
fi

# Verifica credenziali
if [ ! -f ".env.baseline" ]; then
    echo -e "${RED}Errore: .env.baseline non trovato. Crea il file con le credenziali HyperLiquid${NC}"
    exit 1
fi

echo -e "\n${YELLOW}ATTENZIONE: Stai per avviare il trading LIVE con soldi VERI!${NC}"
echo -e "${YELLOW}Simboli: SUI, ADA, DOGE, ARB, AVAX, ETH, LINK${NC}"
echo -e "${YELLOW}Esclusi: BTC, SOL, XRP, BNB (negativi dopo fees)${NC}"
echo ""
read -p "Vuoi continuare? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment annullato."
    exit 0
fi

# Step 1: Pull codice aggiornato
echo -e "\n${GREEN}[1/4] Aggiornamento codice...${NC}"
git pull origin claude/analyze-container-issues-aBfhT

# Step 2: Build immagine
echo -e "\n${GREEN}[2/4] Build Docker image...${NC}"
docker build --no-cache -t alphatrader -f Dockerfile.alpha .

# Step 3: Stop container esistente (se presente)
echo -e "\n${GREEN}[3/4] Stop container esistente...${NC}"
docker stop alpha_trader_live 2>/dev/null || true
docker rm alpha_trader_live 2>/dev/null || true

# Step 4: Avvia container LIVE
echo -e "\n${GREEN}[4/4] Avvio container LIVE...${NC}"
docker run -d \
  --name alpha_trader_live \
  -v $(pwd)/alpha/data:/app/alpha/data \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env.baseline \
  -e ALPHA_PAPER=false \
  -e TRADING_SYMBOLS="SUI,ADA,DOGE,ARB,AVAX,ETH,LINK" \
  -e ALPHA_MIN_HOLD_MINUTES=5 \
  -e ALPHA_MAX_HOLD_MINUTES=7 \
  -e ALPHA_MIN_WIN_PROB=0.0 \
  -e ALPHA_POSITION_USD=25 \
  -e ALPHA_MAX_LEVERAGE=5 \
  -e ALPHA_SLOW_INTERVAL=60 \
  -e ALPHA_FAST_INTERVAL=5 \
  -e ALPHA_INTERVAL=15m \
  -e TESTNET=false \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  --entrypoint python \
  alphatrader -m alpha.trader --mode live --loop

echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}        CONTAINER LIVE AVVIATO!                             ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Comandi utili:"
echo -e "  ${YELLOW}docker logs -f alpha_trader_live${NC}  - Vedi logs in tempo reale"
echo -e "  ${YELLOW}docker stop alpha_trader_live${NC}     - Ferma il trading"
echo -e "  ${YELLOW}docker restart alpha_trader_live${NC}  - Riavvia"
echo ""
echo -e "Query database per stats:"
echo -e "  ${YELLOW}docker exec -it memory_postgres psql -U tradingbot -d botone_baseline -c \"${NC}"
echo -e "  ${YELLOW}SELECT symbol, COUNT(*) as trades, ROUND(SUM(pnl_pct)::numeric, 2) as pnl${NC}"
echo -e "  ${YELLOW}FROM alpha_trades WHERE status='CLOSED' GROUP BY symbol ORDER BY pnl DESC;\"${NC}"
echo ""
