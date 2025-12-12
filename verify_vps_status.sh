#!/bin/bash

# =========================================
# SCRIPT VERIFICA STATO VPS
# Rizzo Trading Agent
# =========================================

echo "======================================"
echo "🔍 VERIFICA STATO VPS"
echo "======================================"
echo ""

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Info sistema
echo "1️⃣  INFO SISTEMA"
echo "---"
echo "Hostname: $(hostname)"
echo "Data: $(date)"
echo "Uptime: $(uptime -p)"
echo ""

# 2. Verifica Docker
echo "2️⃣  DOCKER STATUS"
echo "---"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅ Docker installato${NC}"
    docker --version
    echo ""
    echo "Container in esecuzione:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -10
else
    echo -e "${RED}❌ Docker NON installato${NC}"
fi
echo ""

# 3. Verifica PostgreSQL containers
echo "3️⃣  DATABASE POSTGRESQL"
echo "---"
echo "Container postgres attivi:"
docker ps -a | grep postgres | awk '{print $1, $2, $NF, $(NF-1)}'
echo ""
echo "Volume postgres:"
docker volume ls | grep postgres
echo ""

# 4. Verifica network Docker
echo "4️⃣  DOCKER NETWORKS"
echo "---"
docker network ls | grep -E "NAME|memory|rizzo|supabase|unified"
echo ""

# 5. Verifica directory progetto
echo "5️⃣  DIRECTORY PROGETTO"
echo "---"
if [ -d "/root/trading-bots/rizzo-trading-agent" ]; then
    echo -e "${GREEN}✅ Directory esiste${NC}: /root/trading-bots/rizzo-trading-agent"
    cd /root/trading-bots/rizzo-trading-agent
    echo ""
    echo "Branch corrente:"
    git branch | grep "*"
    echo ""
    echo "Ultimo commit:"
    git log --oneline -1
    echo ""
    echo "File Docker presenti:"
    ls -1 Dockerfile* docker-compose*.yml .env* 2>/dev/null | head -10 || echo "Nessun file Docker/env trovato"
    echo ""
    echo "File Python chiave:"
    ls -1 main.py trading_agent.py requirements.txt 2>/dev/null || echo "File Python non trovati"
else
    echo -e "${RED}❌ Directory NON esiste${NC}: /root/trading-bots/rizzo-trading-agent"
fi
echo ""

# 6. Verifica file .env
echo "6️⃣  FILE .ENV"
echo "---"
if [ -f "/root/trading-bots/rizzo-trading-agent/.env" ]; then
    echo -e "${GREEN}✅ File .env esiste${NC}"
    echo "Variabili configurate:"
    grep -E "^[A-Z_]+=.+" /root/trading-bots/rizzo-trading-agent/.env | sed 's/=.*/=***/' | head -15
else
    echo -e "${RED}❌ File .env NON esiste${NC}"
fi
echo ""

# 7. Verifica cron jobs
echo "7️⃣  CRON JOBS"
echo "---"
crontab -l 2>/dev/null | grep -i "rizzo\|trading" || echo "Nessun cron job per trading bot"
echo ""

# 8. Verifica log
echo "8️⃣  LOG FILE"
echo "---"
if [ -f "/var/log/rizzo-trading-bot.log" ]; then
    echo -e "${GREEN}✅ Log file esiste${NC}"
    echo "Dimensione: $(du -h /var/log/rizzo-trading-bot.log | cut -f1)"
    echo ""
    echo "Ultime 5 righe:"
    tail -5 /var/log/rizzo-trading-bot.log 2>/dev/null
else
    echo -e "${YELLOW}⚠️  Log file non esiste${NC}"
fi
echo ""

# 9. Verifica connessione database
echo "9️⃣  TEST CONNESSIONE DATABASE"
echo "---"
echo "Database disponibili in memory_postgres:"
docker exec -it memory_postgres psql -U tradingbot -l 2>/dev/null | grep -E "Name|rizzo|trading" || echo "Impossibile connettersi"
echo ""

# 10. Riepilogo
echo "======================================"
echo "📊 RIEPILOGO"
echo "======================================"
echo ""
echo "Per ulteriori dettagli:"
echo "  - Log Docker: docker compose logs trading-bot"
echo "  - Status container: docker ps -a | grep rizzo"
echo "  - Network inspect: docker inspect memory_postgres | grep -A 5 Networks"
echo ""
echo "✅ Verifica completata"
