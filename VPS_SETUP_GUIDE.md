# 🚀 GUIDA SETUP VPS - Rizzo Trading Agent

Guida completa per installare e configurare il trading bot su VPS Ubuntu con Docker.

---

## 📋 PREREQUISITI

- VPS Ubuntu (testato su 20.04/22.04)
- Accesso SSH come root
- Docker e Docker Compose installati

---

## 🎯 STEP 1: ANALISI VPS

Esegui questo script sul VPS per analizzare la configurazione attuale:

```bash
# Connettiti al VPS
ssh root@69.62.114.142

# Scarica lo script di analisi
curl -o vps_analyze.sh https://raw.githubusercontent.com/TUO_REPO/rizzo-trading-agent/main/vps_analyze.sh

# Rendilo eseguibile
chmod +x vps_analyze.sh

# Esegui l'analisi
./vps_analyze.sh
```

**Copia tutto l'output e condividilo per personalizzare la configurazione.**

---

## 🐳 STEP 2: INSTALLA DOCKER (se non presente)

```bash
# Update sistema
apt-get update && apt-get upgrade -y

# Installa Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Verifica installazione
docker --version

# Installa Docker Compose v2
apt-get install docker-compose-plugin -y

# Verifica Docker Compose
docker compose version
```

---

## 📦 STEP 3: CLONA IL PROGETTO

Scegli una directory dedicata (es. `/opt/trading-bots/`):

```bash
# Crea directory per i trading bots
mkdir -p /opt/trading-bots
cd /opt/trading-bots

# Clona il repository
git clone https://github.com/TUO_USERNAME/rizzo-trading-agent.git
cd rizzo-trading-agent
```

---

## ⚙️ STEP 4: CONFIGURA LE VARIABILI D'AMBIENTE

```bash
# Copia il template
cp .env.docker .env

# Modifica con i tuoi dati
nano .env
```

### Dati necessari:

#### 🔐 HyperLiquid (Exchange)
- `PRIVATE_KEY`: Chiave privata Ethereum
- `WALLET_ADDRESS`: Indirizzo wallet Ethereum

#### 🤖 OpenAI (AI)
- `OPENAI_API_KEY`: https://platform.openai.com/api-keys

#### 📊 CoinMarketCap (Sentiment)
- `CMC_PRO_API_KEY`: https://coinmarketcap.com/api/

#### 🗄️ PostgreSQL (Database)
- `POSTGRES_PASSWORD`: Scegli password sicura
- Altri lascia default

#### ⚙️ Configurazione Bot
- `TESTNET=true` per test senza soldi veri
- `TESTNET=false` per trading reale (⚠️ ATTENZIONE!)

**Salva e esci:** `CTRL+O`, `ENTER`, `CTRL+X`

---

## 🚀 STEP 5: AVVIA IL BOT

```bash
# Build e avvio
docker compose up -d

# Verifica stato
docker compose ps

# Controlla i log
docker compose logs -f trading-bot
```

**Output atteso:**
```
✅ rizzo_postgres      running
✅ rizzo_trading_bot   running
```

---

## 🔍 STEP 6: VERIFICA FUNZIONAMENTO

```bash
# Log in tempo reale
docker compose logs -f trading-bot

# Ultimi 50 log
docker compose logs --tail=50 trading-bot

# Verifica database
docker compose exec postgres psql -U tradingbot -d rizzo_trading -c "\dt"
```

**Dovresti vedere tabelle come:**
- `account_snapshots`
- `open_positions`
- `bot_operations`
- `ai_contexts`
- Etc.

---

## 🔄 AGGIORNARE IL BOT

### Metodo automatico:

```bash
cd /opt/trading-bots/rizzo-trading-agent
./deploy.sh
```

### Metodo manuale:

```bash
cd /opt/trading-bots/rizzo-trading-agent

# Pull codice
git pull origin main

# Rebuild e restart
docker compose down
docker compose build --no-cache
docker compose up -d

# Verifica
docker compose logs -f trading-bot
```

---

## 📊 COMANDI UTILI

```bash
# Stato container
docker compose ps

# Log live
docker compose logs -f trading-bot

# Restart bot (senza rebuild)
docker compose restart trading-bot

# Stop tutto
docker compose down

# Start tutto
docker compose up -d

# Entra nel container
docker compose exec trading-bot bash

# Vedi risorse usate
docker stats rizzo_trading_bot

# Database: query manuale
docker compose exec postgres psql -U tradingbot -d rizzo_trading
```

---

## 🔧 TROUBLESHOOTING

### Il bot non parte

```bash
# Controlla errori
docker compose logs trading-bot

# Verifica configurazione
docker compose config

# Verifica connessione database
docker compose exec postgres pg_isready
```

### Database non connette

```bash
# Verifica che postgres sia avviato
docker compose ps postgres

# Controlla DATABASE_URL in .env
cat .env | grep DATABASE_URL

# Dovrebbe essere:
# postgresql://tradingbot:PASSWORD@postgres:5432/rizzo_trading
```

### API non funzionano

```bash
# Test connessioni
docker compose exec trading-bot python3 test_connections.py
```

### Porta già in uso (5432)

Nel `docker-compose.yml` la porta postgres è `5433` su host per evitare conflitti.
Se anche 5433 è occupata, cambia in `docker-compose.yml`:

```yaml
ports:
  - "127.0.0.1:5434:5432"  # Usa 5434 o altra porta libera
```

---

## 🛡️ SICUREZZA

### Backup Database

```bash
# Backup manuale
docker compose exec postgres pg_dump -U tradingbot rizzo_trading > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20250118.sql | docker compose exec -T postgres psql -U tradingbot rizzo_trading
```

### Backup automatico (cron)

```bash
# Aggiungi a crontab
crontab -e

# Backup giornaliero alle 3 AM
0 3 * * * cd /opt/trading-bots/rizzo-trading-agent && docker compose exec postgres pg_dump -U tradingbot rizzo_trading > /opt/backups/rizzo_$(date +\%Y\%m\%d).sql
```

### Monitoring

```bash
# Controlla risorse
docker stats rizzo_trading_bot

# Alert se il bot si ferma (simple check)
*/5 * * * * docker compose -f /opt/trading-bots/rizzo-trading-agent/docker-compose.yml ps | grep -q "rizzo_trading_bot.*Up" || echo "Bot down!" | mail -s "Trading Bot Alert" tuaemail@example.com
```

---

## 📝 LOG PERSISTENTI

I log sono gestiti da Docker. Per salvarli su file:

```bash
# Crea directory log
mkdir -p /opt/trading-bots/rizzo-trading-agent/logs

# I log Docker sono già configurati in docker-compose.yml
# Per esportarli:
docker compose logs trading-bot > logs/bot_$(date +%Y%m%d).log
```

---

## 🔥 ENVIRONMENT COMPLETAMENTE ISOLATO

Questo setup crea:

- ✅ Rete Docker dedicata (`rizzo_trading_network`)
- ✅ PostgreSQL dedicato (porta 5433, non conflitti)
- ✅ Volume persistente per dati
- ✅ Restart automatico container
- ✅ Log rotation automatico
- ✅ Non interferisce con altri servizi

**Puoi avere MULTIPLI trading bot così configurati!**

---

## 📞 SUPPORTO

- 📺 Video: https://www.youtube.com/watch?v=Vrl2Ar_SvSo
- 📧 GitHub Issues: https://github.com/TUO_REPO/rizzo-trading-agent/issues

---

## ⚠️ DISCLAIMER

**ATTENZIONE:** Questo bot fa trading REALE con soldi VERI quando `TESTNET=false`.

- ✅ Inizia SEMPRE con `TESTNET=true`
- ✅ Monitora le operazioni per almeno 1 settimana in testnet
- ✅ Usa solo capitale che puoi permetterti di perdere
- ⚠️  Il trading crypto è ad alto rischio
- ⚠️  Nessuna garanzia di profitto

**Gli sviluppatori non sono responsabili per perdite finanziarie.**

---

**Sviluppato da Rizzo AI Academy** 🤖
