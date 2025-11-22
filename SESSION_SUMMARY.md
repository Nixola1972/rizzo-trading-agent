# Session Summary - Trading Agent Bot Troubleshooting
**Date**: 2025-11-22
**Branch**: `claude/review-project-status-01JBWiEE8H8qGffgjKWWZvaX`

---

## Overview

This session focused on troubleshooting and fixing the Trading Agent Bot deployment on a VPS server. Multiple critical issues were identified and resolved.

---

## Issues Found and Resolved

### 1. Zombie Container Accumulation (CRITICAL)
**Problem**: The cron job was starting a new bot container every 15 minutes, but containers never terminated. This caused:
- 36+ containers running simultaneously
- RAM usage growing from 4GB to 8GB
- Database connections accumulating (70+ zombie connections)

**Root Cause**: The `db_utils.init_db()` function was blocking due to database lock contention from accumulated connections.

**Solution**:
```bash
# Stop all zombie containers
docker ps -a | grep "trading-bot" | awk '{print $1}' | xargs docker stop
docker ps -a | grep "trading-bot" | awk '{print $1}' | xargs docker rm

# Kill zombie database connections
docker exec memory_postgres psql -U tradingbot -d rizzo_trading -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rizzo_trading' AND pid != pg_backend_pid();"

# Add timeout to cron (prevents future accumulation)
# Changed from:
*/15 * * * * cd /root/trading-bots/rizzo-trading-agent && /usr/bin/docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> /var/log/rizzo-trading-bot.log 2>&1
# To:
*/15 * * * * cd /root/trading-bots/rizzo-trading-agent && timeout 600 /usr/bin/docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> /var/log/rizzo-trading-bot.log 2>&1
```

### 2. Dashboard SQL Errors
**Problem**: Dashboard showed "column 'reason' does not exist" errors.

**Root Cause**: The `reason` field is stored in JSONB column `raw_payload`, not as a direct column.

**Solution**: Updated dashboard.py queries from:
```sql
SELECT reason FROM bot_operations
```
To:
```sql
SELECT raw_payload->>'reason' as reason FROM bot_operations
```

### 3. Dashboard Branding
**Problem**: User wanted to remove "Rizzo" branding from dashboard.

**Solution**: Changed all occurrences in dashboard.py:
- `page_title`: "Rizzo Trading Bot Dashboard" → "Trading Agent Dashboard"
- Header: "🤖 Rizzo Trading Bot Dashboard" → "🤖 Trading Agent Dashboard"
- Footer: Same change

### 4. Missing docker-compose.existing-postgres.yml
**Problem**: File was missing on the current branch, causing cron to fail.

**Solution**: Copied from other branch:
```bash
git show claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB:docker-compose.existing-postgres.yml > docker-compose.existing-postgres.yml
```

### 5. TESTNET vs MAINNET Configuration
**Problem**: Bot was showing 0 USDC balance despite having 47.27 USDC.

**Root Cause**: `main.py` had hardcoded `TESTNET = True` ignoring .env file.

**Solution**: Changed main.py to read from environment:
```python
# From:
TESTNET = True

# To:
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
```

### 6. API Key Error (CURRENT)
**Problem**: Bot using OpenAI API instead of OpenRouter.

**Error**: `openai.AuthenticationError: Error code: 401 - Incorrect API key`

**Status**: Needs investigation in `trading_agent.py` - should use OpenRouter when `AI_PROVIDER=openrouter`.

---

## Current Configuration

### Environment Variables (.env)
```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1
PRIVATE_KEY=0x***
WALLET_ADDRESS=0x***
CMC_PRO_API_KEY=xxxxx
DATABASE_URL=postgresql://tradingbot:TradingBot2025!Secure@memory_postgres:5432/rizzo_trading
POSTGRES_NETWORK=unified-memory-stack_memory-net
TESTNET=false
VERBOSE=true
```

### Docker Setup
- **Dashboard**: `rizzo_dashboard` on port 8501
- **Bot**: Runs via cron every 15 minutes with 10-minute timeout
- **Database**: `memory_postgres` (shared PostgreSQL container)
- **Network**: `unified-memory-stack_memory-net`

### Cron Configuration
```bash
*/15 * * * * cd /root/trading-bots/rizzo-trading-agent && timeout 600 /usr/bin/docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> /var/log/rizzo-trading-bot.log 2>&1
```

---

## Important Commands

### Check Bot Status
```bash
# View recent logs
tail -100 /var/log/rizzo-trading-bot.log

# Check running containers
docker ps | grep rizzo

# Check database operations
docker exec memory_postgres psql -U tradingbot -d rizzo_trading -c "SELECT created_at, operation, symbol FROM bot_operations ORDER BY created_at DESC LIMIT 10;"

# Check active DB connections
docker exec memory_postgres psql -U tradingbot -d rizzo_trading -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'rizzo_trading';"
```

### Kill Zombie Connections
```bash
docker exec memory_postgres psql -U tradingbot -d rizzo_trading -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rizzo_trading' AND pid != pg_backend_pid();"
```

### Restart Dashboard
```bash
cd /root/trading-bots/rizzo-trading-agent
docker compose -f docker-compose.dashboard.yml down
docker compose -f docker-compose.dashboard.yml build --no-cache
docker compose -f docker-compose.dashboard.yml up -d
```

### Manual Bot Test
```bash
cd /root/trading-bots/rizzo-trading-agent
timeout 120 docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

---

## Files Modified

| File | Change |
|------|--------|
| `dashboard.py` | Fixed SQL queries, added period selector, open positions tab, removed "Rizzo" branding |
| `main.py` | Read TESTNET/VERBOSE from .env instead of hardcoded |
| `docker-compose.existing-postgres.yml` | Restored from other branch |
| Cron | Added `timeout 600` protection |

---

## Pending Issues

1. **trading_agent.py** - Needs to be updated to use OpenRouter when `AI_PROVIDER=openrouter` instead of always using OpenAI
2. **Dashboard rebuild** - May need rebuild after git pull to load latest changes

---

## URLs and Access

- **Dashboard**: http://69.62.114.142:8501
- **VPS**: root@srv778971 (69.62.114.142)
- **Alternative Dashboard Repo**: https://github.com/Nixola1972/trading_agent_dashboard (FastAPI + HTMX, more professional)

---

## Lessons Learned

1. Always add timeout to cron jobs that run Docker containers
2. Check for zombie database connections when containers don't terminate
3. The `--rm` flag in docker-compose run doesn't always clean up if container hangs
4. JSONB fields in PostgreSQL need `->>'field'` syntax to extract as text
5. Docker images cache old code - need `--no-cache` rebuild after file changes

---

## Future Improvements (TODO)

### 1. Dati Aggiuntivi per l'AI
| Dato | Perché serve | Priorità |
|------|--------------|----------|
| **Order Book Depth** | Vedere bid/ask walls, liquidità | Media |
| **Liquidation Heatmap** | Dove sono i cluster di liquidazioni | Media |
| **Funding Rate History** | Trend del funding, non solo snapshot | Alta |
| **Open Interest Delta** | Variazione OI, non solo valore assoluto | Alta |
| **Volume Profile** | Dove si concentra il volume (POC, VAH, VAL) | Media |
| **Correlation Matrix** | BTC/ETH/SOL si muovono insieme? | Bassa |
| **Whale Alerts** | Già nel codice (`whalealert.py`), da attivare | Alta |

### 2. Dashboard Analytics
- **Win Rate**: % operazioni in profitto
- **Avg P&L per Trade**: Media guadagno/perdita
- **Max Drawdown**: Peggior perdita dal picco
- **Sharpe Ratio**: Risk-adjusted return
- **Performance by Symbol**: BTC vs ETH vs SOL
- **Performance by Direction**: Long vs Short
- **Equity Curve**: Grafico del balance nel tempo

### 3. Alerting & Monitoring
- **Telegram Bot**: Alert su ogni trade, errori, daily summary
- **Health Check**: Ping ogni 15 min, alert se bot non risponde
- **Daily Report**: Email/Telegram con P&L giornaliero

### 4. Logging Migliorato
- **AI Response Time**: quanto impiega il modello
- **Confidence Score**: se il modello potesse dare un punteggio 0-100
- **Alternative Decisions**: cosa avrebbe fatto come seconda scelta

### 5. Backtesting
- Salvare tutti i dati di input per poter ri-simulare decisioni
- Confrontare "cosa ha deciso l'AI" vs "cosa sarebbe successo"

---

## Profilo di Rischio del Bot

**Valutazione: MODERATAMENTE AGGRESSIVO**

| Parametro | Valore | Note |
|-----------|--------|------|
| Leverage | 1-10x (default 1x) | Potenzialmente aggressivo |
| Position Size | 0-100% (default 30%) | Moderato |
| Frequenza | Ogni 15 minuti | Alta frequenza |
| Asset | BTC, ETH, SOL | Solo major (conservativo) |
| Posizioni | 1 per coin max | Limitato |
| Direzione | Long + Short | Bidirezionale |

**Manca**: Stop-loss, take-profit, hard cap su leverage/position size
