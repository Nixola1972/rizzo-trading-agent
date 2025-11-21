# 📊 PROJECT STATUS - Rizzo Trading Agent

**Data Ultimo Aggiornamento:** 2025-01-21
**Branch Attivo:** `claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB`
**Versione:** v2.0 (Multi-Model Support + OpenRouter)

---

## 📋 SOMMARIO ESECUTIVO

**Rizzo Trading Agent** è un bot di trading automatizzato per criptovalute che:
- Opera su **HyperLiquid** (exchange decentralizzato con leva fino a 10x)
- Usa **AI** (OpenAI GPT-4 o OpenRouter con modelli multipli) per decisioni di trading
- Analizza **multiple fonti di dati**: indicatori tecnici, news, sentiment, forecasting
- Supporta **TESTNET** (simulazione) e **MAINNET** (soldi reali)
- Salva tutto in **PostgreSQL** per analisi storica
- Include **Dashboard web** (Streamlit) per monitoraggio in tempo reale

---

## 🎯 ASSET SUPPORTATI

Il bot opera ESCLUSIVAMENTE su 3 criptovalute:

| Asset | Simbolo | Note |
|-------|---------|------|
| Bitcoin | BTC | Asset principale |
| Ethereum | ETH | Asset secondario |
| Solana | SOL | Asset terziario |

---

## 🏗️ ARCHITETTURA DEL SISTEMA

### Moduli Principali

```
rizzo-trading-agent/
├── main.py                    # Loop principale del bot
├── trading_agent.py           # AI decision maker (multi-provider)
├── hyperliquid_trader.py      # Interfaccia con HyperLiquid exchange
├── indicators.py              # Analisi tecnica (RSI, MACD, EMA, ATR, etc.)
├── forecaster.py              # Previsioni prezzo con Prophet (15m, 1h)
├── sentiment.py               # Fear & Greed Index (CoinMarketCap)
├── news_feed.py               # Feed RSS notizie crypto (CoinJournal)
├── whalealert.py              # Movimenti grandi wallet (whale alerts)
├── db_utils.py                # Gestione database PostgreSQL
├── dashboard.py               # Dashboard web Streamlit
└── system_prompt.txt          # Prompt per l'AI
```

### Flusso di Esecuzione

```
┌─────────────────────────────────────────────────────────────┐
│ 1. RACCOLTA DATI                                            │
│    ├─ Indicatori Tecnici (15min candles da HyperLiquid)   │
│    ├─ News Feed (ultimi articoli crypto)                   │
│    ├─ Sentiment (Fear & Greed Index)                       │
│    └─ Forecasting (previsioni a 15min e 1h con Prophet)    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. DECISIONE AI                                             │
│    ├─ Compone prompt con tutti i dati                       │
│    ├─ Chiama AI (OpenAI/OpenRouter)                        │
│    └─ Riceve decisione JSON: {operation, symbol, ...}      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. ESECUZIONE TRADE                                         │
│    ├─ OPEN:  Apre posizione long/short con leva            │
│    ├─ CLOSE: Chiude posizione esistente                    │
│    └─ HOLD:  Nessuna azione                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. SALVATAGGIO                                              │
│    ├─ Snapshot account (balance, posizioni)                │
│    ├─ Decisione AI con reasoning                           │
│    ├─ Tutti gli indicatori e dati usati                    │
│    └─ Eventuali errori                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤖 CONFIGURAZIONE AI PROVIDER

### Supporto Multi-Provider

Il bot supporta **2 provider AI** con switching flessibile:

#### 1. OpenAI (Provider Originale)

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

**Modelli supportati:**
- `gpt-4-turbo` (default)
- `gpt-4o`
- `gpt-4o-mini`

**Costo:** ~$0.01-0.05 per decisione

#### 2. OpenRouter (Multi-Model Gateway) ⭐ CONSIGLIATO

```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

**Modelli consigliati:**

| Modello | Costo/decisione | Qualità | Note |
|---------|----------------|---------|------|
| `anthropic/claude-3.5-sonnet` | ~$0.015 | ⭐⭐⭐⭐⭐ | **Migliore per trading**, reasoning avanzato |
| `anthropic/claude-sonnet-4.5` | ~$0.02 | ⭐⭐⭐⭐⭐ | Più recente, richiede parsing manuale JSON |
| `deepseek/deepseek-chat` | ~$0.002 | ⭐⭐⭐⭐ | **Economico**, buone performance (DeepSeek V3) |
| `deepseek/deepseek-r1` | ~$0.003 | ⭐⭐⭐⭐ | Reasoning avanzato, modello 2025 |
| `google/gemini-2.5-pro` | ~$0.001 | ⭐⭐⭐ | Molto economico |
| `meta-llama/llama-3.3-70b` | ~$0.0005 | ⭐⭐⭐ | Open source, economicissimo |

**Gestione JSON:**
- **Modelli con JSON nativo**: Claude 3.5, GPT-4, GPT-4o → Usano `response_format={"type": "json_object"}`
- **Modelli senza JSON nativo**: Claude 4.5, DeepSeek, Gemini → Parsing manuale con regex
- **Retry automatico**: 3 tentativi con fallback su parsing manuale
- **Validazione**: Controllo campi obbligatori (operation, symbol, reason)

### Struttura Decisione AI

```json
{
  "operation": "open|close|hold",
  "symbol": "BTC|ETH|SOL",
  "direction": "long|short",
  "target_portion_of_balance": 0.3,
  "leverage": 2,
  "reason": "Detailed reasoning for this decision..."
}
```

---

## 🗄️ DATABASE POSTGRESQL

### Schema Database

```sql
-- Snapshots stato account
account_snapshots (id, created_at, balance_usd, raw_payload)

-- Posizioni aperte al momento dello snapshot
open_positions (id, snapshot_id, symbol, side, size, entry_price,
                mark_price, pnl_usd, leverage, raw_payload)

-- Contesti AI (input del modello)
ai_contexts (id, created_at, system_prompt)

-- Indicatori tecnici per ogni ticker
indicators_contexts (id, context_id, ticker, ts, price, ema20, macd,
                    rsi_7, volume_bid, volume_ask, pp, s1, s2, r1, r2,
                    open_interest_latest, open_interest_average,
                    funding_rate, ema20_15m, ema50_15m, atr3_15m,
                    atr14_15m, volume_15m_current, volume_15m_average,
                    intraday_mid_prices, intraday_ema20_series,
                    intraday_macd_series, intraday_rsi7_series,
                    intraday_rsi14_series, lt15m_macd_series,
                    lt15m_rsi14_series)

-- News feed
news_contexts (id, context_id, news_text)

-- Sentiment (Fear & Greed Index)
sentiment_contexts (id, context_id, value, classification,
                   sentiment_timestamp, raw)

-- Forecast (previsioni Prophet)
forecasts_contexts (id, context_id, ticker, timeframe, last_price,
                   prediction, lower_bound, upper_bound, change_pct,
                   forecast_timestamp, raw)

-- Decisioni del bot
bot_operations (id, created_at, context_id, operation, symbol,
               direction, target_portion_of_balance, leverage,
               raw_payload)

-- Log errori
errors (id, created_at, error_type, error_message, traceback,
       context, source)
```

### Configurazioni Database Supportate

#### Opzione 1: Database Dedicato (Isolato)

```bash
# docker-compose.yml
# Crea nuovo PostgreSQL dedicato solo al bot
DATABASE_URL=postgresql://tradingbot:password@postgres:5432/rizzo_trading
POSTGRES_NETWORK=rizzo_trading_network
```

**Pro:**
- ✅ Isolamento completo
- ✅ Backup indipendenti
- ✅ Nessun conflitto con altri progetti

**Contro:**
- ⚠️ Un container PostgreSQL in più

#### Opzione 2: Database Esistente (Condiviso)

```bash
# docker-compose.existing-postgres.yml
# Usa PostgreSQL già presente sul server
DATABASE_URL=postgresql://tradingbot:password@memory_postgres:5432/rizzo_trading
POSTGRES_NETWORK=unified-memory-stack_memory-net
```

**Pro:**
- ✅ Riusa database esistente
- ✅ Un solo PostgreSQL da gestire

**Contro:**
- ⚠️ Deve collegarsi alla network corretta
- ⚠️ Serve creare database `rizzo_trading` manualmente

---

## 🐳 DOCKER SETUP

### File Docker

```
docker-compose.yml                    # Setup standalone (con postgres)
docker-compose.existing-postgres.yml  # Setup con postgres esistente
Dockerfile                            # Build immagine bot
```

### Build & Run

```bash
# Setup standalone (crea tutto)
docker compose up -d

# Setup con postgres esistente
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot

# Rebuild dopo modifiche
docker compose build

# Logs
docker compose logs -f trading-bot
```

---

## 📊 DASHBOARD WEB

**File:** `dashboard.py`
**Framework:** Streamlit
**Porta:** 8501

### Funzionalità

- 💰 Balance account in tempo reale
- 📈 Grafici balance storico
- 🤖 Ultime decisioni AI con reasoning completo
- 📊 P&L per simbolo
- 🔄 Refresh automatico ogni 30s
- 📉 Statistiche trading (win rate, profitto medio, etc.)

### Avvio

```bash
# Standalone
docker compose up -d dashboard

# Manuale
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
```

Accesso: `http://VPS_IP:8501`

---

## ⏱️ ESECUZIONE AUTOMATICA (CRON)

### Setup Cron

```bash
# Installa cron job (ogni 15 minuti)
./setup_cron.sh

# Verifica
crontab -l

# Rimuovi
./remove_cron.sh
```

### Cron Job

```cron
*/15 * * * * cd /root/trading-bots/rizzo-trading-agent && docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> /var/log/rizzo-trading-bot.log 2>&1
```

### Monitoraggio

```bash
# Tail log
tail -f /var/log/rizzo-trading-bot.log

# Solo errori
grep "❌" /var/log/rizzo-trading-bot.log

# Solo decisioni AI
grep "Decisione AI" /var/log/rizzo-trading-bot.log
```

---

## 🔧 VARIABILI D'AMBIENTE (.env)

### Variabili Richieste

```bash
# === AI PROVIDER ===
AI_PROVIDER=openrouter                              # openai | openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx          # Se usi OpenRouter
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet       # Modello OpenRouter
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx               # Se usi OpenAI

# === HYPERLIQUID EXCHANGE ===
PRIVATE_KEY=0xABCDEF123456...                      # Ethereum private key
WALLET_ADDRESS=0x1234567890abcdef...               # Ethereum address

# === COINMARKETCAP (Sentiment) ===
CMC_PRO_API_KEY=abcdef-1234-5678-...              # API key CoinMarketCap

# === DATABASE ===
DATABASE_URL=postgresql://user:pass@host:5432/db   # Connection string
POSTGRES_NETWORK=rizzo_trading_network             # Docker network

# === BOT CONFIG ===
TESTNET=true                                        # true=testnet, false=MAINNET
VERBOSE=true                                        # Log dettagliati
```

### File Template Disponibili

```
.env.example                    # Template base
.env.docker                     # Per docker-compose.yml
.env.existing-postgres          # Per docker-compose.existing-postgres.yml
.env.existing-postgres.updated  # Con configurazione AI aggiornata
.env.template                   # Template generico
```

---

## 🌳 STATO REPOSITORY GIT

### Branch Disponibili

| Branch | Commit | Stato | Note |
|--------|--------|-------|------|
| `claude/review-project-status-01JBWiEE8H8qGffgjKWWZvaX` | `f1a9753` | 📦 Vecchio | Pre-railway, NO OpenRouter |
| `claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB` | `b346701` | ✅ **ATTUALE** | Multi-model, OpenRouter, molti fix |

### Differenze Tra Branch

**Branch vecchio → nuovo (25+ commit):**

```
File AGGIUNTI (23):
- AI_MODEL_FIX.md, AI_PROVIDER_GUIDE.md
- DEPLOYMENT_SUMMARY.md, CRON_SETUP.md
- QUICK_REFERENCE.md, QUICK_START.md
- SUPPORTED_MODELS.md, SUPPORTED_MODELS_2025.md
- dashboard.py (Streamlit)
- fix_ai_model.sh, setup_cron.sh, setup_deepseek.sh
- test_connections.py, debug_hyperliquid.py
- investigate_wallet.py
- Docker files (docker-compose.existing-postgres.yml, Dockerfile)
- Vari .env.*
- ...

File MODIFICATI (6):
- trading_agent.py: Multi-provider support, retry logic, JSON parsing
- main.py: Inizializzazione database, error handling
- hyperliquid_trader.py: Balance extraction robusto, leverage management
- system_prompt.txt: Schema JSON esplicito con esempi
- requirements.txt: Aggiunti openai, requests, streamlit, plotly
```

---

## 📈 INDICATORI TECNICI UTILIZZATI

### Timeframe Principale: 15 Minuti

Il bot usa principalmente candele a **15 minuti** per decisioni intraday:

| Indicatore | Descrizione | Uso |
|------------|-------------|-----|
| **EMA 20** | Exponential Moving Average 20 periodi | Trend short-term |
| **EMA 50** | Exponential Moving Average 50 periodi | Trend medium-term |
| **MACD** | Moving Average Convergence Divergence | Momentum |
| **RSI 7** | Relative Strength Index 7 periodi | Ipercomprato/ipervenduto veloce |
| **RSI 14** | Relative Strength Index 14 periodi | Ipercomprato/ipervenduto standard |
| **ATR 3** | Average True Range 3 periodi | Volatilità short-term |
| **ATR 14** | Average True Range 14 periodi | Volatilità standard |
| **Pivot Points** | Supporti/resistenze calcolati su dati daily | Livelli chiave |
| **Volume** | Bid/Ask volume da orderbook | Pressione buy/sell |
| **Funding Rate** | Tasso di finanziamento perpetual | Sentiment long/short |
| **Open Interest** | Posizioni aperte totali | Liquidità mercato |

### Forecast (Prophet)

- **15 minuti ahead**: Previsione prezzo prossimi 15min
- **1 ora ahead**: Previsione prezzo prossima ora
- **Confidence intervals**: Lower/upper bound previsioni
- **Variazione %**: Quanto dovrebbe salire/scendere

---

## 🗂️ FILE DI DOCUMENTAZIONE

| File | Descrizione |
|------|-------------|
| `README.md` | Introduzione progetto |
| `PROJECT_STATUS.md` | **Questo file** - Stato completo progetto |
| `DEPLOYMENT_SUMMARY.md` | Riassunto deployment e fix AI |
| `AI_PROVIDER_GUIDE.md` | Come configurare OpenAI/OpenRouter |
| `AI_MODEL_FIX.md` | Fix problemi modelli AI e JSON |
| `SUPPORTED_MODELS.md` | Lista modelli supportati (aggiornata 2025) |
| `SUPPORTED_MODELS_2025.md` | Modelli 2025 (Claude 4.5, DeepSeek R1, Gemini 2.5) |
| `QUICK_START.md` | Setup veloce in 5 minuti |
| `QUICK_REFERENCE.md` | Comandi essenziali e troubleshooting |
| `VPS_SETUP_GUIDE.md` | Guida completa deployment su VPS |
| `CRON_SETUP.md` | Setup esecuzione automatica cron |
| `SETUP_SCEGLI.md` | Come scegliere tra postgres standalone/esistente |
| `SETUP_WITH_EXISTING_POSTGRES.md` | Guida uso postgres esistente |
| `FIX_DEEPSEEK_NAMES.md` | Fix nomi modelli DeepSeek su OpenRouter |
| `UPDATE_MULTI_MODEL.md` | Guida aggiornamento a multi-model support |

---

## 🛠️ SCRIPT UTILITY

| Script | Descrizione |
|--------|-------------|
| `setup.sh` | Setup iniziale completo |
| `deploy.sh` | Deploy/update su VPS |
| `setup_cron.sh` | Installa cron job |
| `remove_cron.sh` | Rimuove cron job |
| `setup_deepseek.sh` | Configura DeepSeek (economico!) |
| `fix_ai_model.sh` | Fix configurazione AI nel .env |
| `analyze_vps.sh` | Analisi stato VPS (memoria, disk, processi) |
| `create_database.sh` | Crea database PostgreSQL |
| `test_connections.py` | Test connessione DB + HyperLiquid + AI |
| `test_hyperliquid_mainnet.py` | Test specifico mainnet HyperLiquid |
| `debug_hyperliquid.py` | Debug connessione HyperLiquid |
| `investigate_wallet.py` | Investigate wallet status |
| `test_trading.py` | Test apertura/chiusura posizioni |

---

## 🚨 SITUAZIONE ATTUALE (Dal Tuo Server)

### Deployment

**Server VPS:** `69.62.114.142`
**Path:** `/root/trading-bots/rizzo-trading-agent`
**Branch Corrente:** `claude/review-project-status-01JBWiEE8H8qGffgjKWWZvaX` (VECCHIO!)

### Database PostgreSQL Esistenti

| Container | Porta | Scopo | Stato |
|-----------|-------|-------|-------|
| `memory_postgres` | 5433 | Database per altro progetto | ✅ Attivo (12 giorni) |
| `supabase_db_supabase-cli` | 54322 | Database Supabase | ✅ Attivo (2 mesi) |
| `rizzo_postgres` | N/A | Database trading bot (vecchio) | ❌ Rimosso per errore |

### Volume Dati

```bash
# Volume con dati ancora presente
rizzo_postgres_data  ✅ Esiste (dati salvati)
```

### Problemi Identificati dalla Conversazione Precedente

1. **Container `rizzo_postgres` rimosso**: Cancellato con `--remove-orphans`, ma volume dati ancora presente
2. **Confusione tra docker-compose**: Mescolati `docker-compose.yml` e `docker-compose.existing-postgres.yml`
3. **Branch vecchio**: Il codice sul server è del branch vecchio (pre-OpenRouter)
4. **File .env**: Non verificato se esiste e se è configurato correttamente

---

## ✅ PROSSIMI PASSI RACCOMANDATI

### 1. Aggiorna il Branch sul Server

```bash
cd /root/trading-bots/rizzo-trading-agent

# Salva .env corrente se esiste
cp .env .env.backup 2>/dev/null || true

# Pull branch aggiornato
git fetch --all
git checkout claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB
git pull origin claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB

# Ripristina .env se esisteva
[ -f .env.backup ] && cp .env.backup .env
```

### 2. Configura Database

**IMPORTANTE:** Decidi quale database usare!

#### Opzione A: Usa `memory_postgres` (Esistente) ⭐ CONSIGLIATO

```bash
# 1. Crea database nel postgres esistente
docker exec -it memory_postgres psql -U tradingbot -c "CREATE DATABASE rizzo_trading;"

# 2. Configura .env
cp .env.existing-postgres .env
nano .env

# Verifica questi valori:
DATABASE_URL=postgresql://tradingbot:TradingBot2025!Secure@memory_postgres:5432/rizzo_trading
POSTGRES_NETWORK=unified-memory-stack_memory-net  # Verifica nome reale network!
```

#### Opzione B: Crea Nuovo Postgres Dedicato

```bash
# Usa docker-compose.yml standard
docker compose up -d postgres

# Il database verrà creato automaticamente
```

### 3. Configura AI Provider

```bash
nano .env

# CONSIGLIATO: OpenRouter con Claude 3.5 Sonnet
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# OPPURE: OpenAI (più costoso)
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

### 4. Test Manuale

```bash
# Test singola esecuzione
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot

# Output atteso (successo):
# 🤖 Usando OpenRouter con modello: anthropic/claude-3.5-sonnet
# 🗄️  Inizializzazione database...
# ✅ Database inizializzato
# ...
# ✅ Decisione AI: hold BTC - Market showing consolidation...
```

### 5. Attiva Cron (Esecuzione Automatica)

```bash
# Setup cron (ogni 15 minuti)
./setup_cron.sh

# Verifica
crontab -l

# Monitora log
tail -f /var/log/rizzo-trading-bot.log
```

### 6. Avvia Dashboard

```bash
# Modifica docker-compose per includere dashboard
docker compose up -d dashboard

# Accedi a: http://69.62.114.142:8501
```

---

## 🔍 VERIFICA CONFIGURAZIONE CORRETTA

### Checklist Pre-Produzione

- [ ] Git branch aggiornato (`claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB`)
- [ ] File `.env` configurato con tutte le variabili
- [ ] `AI_PROVIDER` configurato (openrouter o openai)
- [ ] API keys valide e con credito
- [ ] Database PostgreSQL accessibile
- [ ] Network Docker corretta (`docker network ls`)
- [ ] Test manuale completato senza errori
- [ ] `TESTNET=true` (per sicurezza!)
- [ ] Cron job installato
- [ ] Dashboard accessibile
- [ ] Log puliti per almeno 1 ora

### Comandi Diagnostica

```bash
# Verifica network postgres esistente
docker inspect memory_postgres | grep -A 5 '"Networks"'

# Verifica database
docker exec -it memory_postgres psql -U tradingbot -l

# Test connessione bot → postgres
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python3 -c "import db_utils; db_utils.init_db(); print('✅ DB OK')"

# Test connessione HyperLiquid
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python3 test_connections.py

# Verifica .env
cat .env | grep -E "AI_PROVIDER|DATABASE_URL|TESTNET"
```

---

## 📞 SUPPORTO & TROUBLESHOOTING

### Problemi Comuni

| Problema | Soluzione |
|----------|-----------|
| "could not translate host name to address" | Verifica `POSTGRES_NETWORK` corretta |
| "Expecting value: line 1 column 1" (JSON) | Usa modello con JSON nativo (claude-3.5-sonnet) o attendi fix parsing |
| "Campo mancante: reason" | Aggiorna `system_prompt.txt` (branch nuovo) |
| "Balance account = 0" | Verifica wallet HyperLiquid ha fondi (mainnet) o usa testnet |
| "API key not found" | Verifica `.env` ha le keys corrette |

### File di Riferimento Rapido

- **Troubleshooting generale**: `QUICK_REFERENCE.md`
- **Problemi AI/JSON**: `AI_MODEL_FIX.md`
- **Setup cron**: `CRON_SETUP.md`
- **Deployment completo**: `DEPLOYMENT_SUMMARY.md`

---

## 🎯 OBIETTIVI FUTURI

### Short-term (1-2 settimane)

- [x] Multi-model support (OpenRouter)
- [x] Dashboard web
- [x] Cron automation
- [ ] Test 1 settimana in TESTNET
- [ ] Ottimizzazione parametri trading
- [ ] Alert Telegram/Discord per operazioni

### Medium-term (1 mese)

- [ ] Backtesting su dati storici
- [ ] Ottimizzazione AI prompt basata su performance
- [ ] Supporto più asset (AVAX, MATIC, LINK, ...)
- [ ] Risk management avanzato (stop-loss dinamici)
- [ ] Dashboard con più metriche (Sharpe ratio, max drawdown, ...)

### Long-term (3+ mesi)

- [ ] Machine learning per ottimizzare parametri
- [ ] Multi-exchange support (oltre HyperLiquid)
- [ ] API REST per controllo remoto
- [ ] Mobile app per monitoraggio
- [ ] Strategie multiple in parallelo

---

## ⚠️ DISCLAIMER

**ATTENZIONE:** Il trading di criptovalute comporta rischi significativi.

- ✅ **TESTNET**: Usa fondi virtuali, ideale per test
- ⚠️ **MAINNET**: Usa soldi reali, rischio perdita capitale

**Raccomandazioni:**
1. Testa ALMENO 1 settimana in TESTNET
2. Monitora le decisioni AI per verificare che siano sensate
3. Inizia con piccole somme in MAINNET
4. NON investire più di quanto puoi permetterti di perdere
5. Tieni monitorato il bot (log, dashboard)

**Questo bot è per scopi educativi e sperimentali. Non è consiglianza finanziaria.**

---

## 📝 CHANGELOG

### v2.0 (Branch: claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB)

- ✅ Multi-model AI support (OpenRouter + OpenAI)
- ✅ Supporto Claude 3.5, Claude 4.5, DeepSeek R1/V3, Gemini 2.5, GPT-4/5
- ✅ Parsing JSON robusto con retry per modelli senza JSON nativo
- ✅ Dashboard Streamlit con grafici e statistiche
- ✅ Cron automation scripts
- ✅ Balance extraction robusto (mainnet/testnet compatibility)
- ✅ Documentazione completa (15+ file MD)
- ✅ Script utility per setup/test/debug
- ✅ Leverage management migliorato
- ✅ Error handling e logging avanzato

### v1.0 (Branch: claude/review-project-status-01JBWiEE8H8qGffgjKWWZvaX)

- ✅ Bot base con OpenAI GPT-4
- ✅ Indicatori tecnici (15min)
- ✅ Forecasting Prophet
- ✅ Sentiment & News
- ✅ Database PostgreSQL
- ✅ HyperLiquid integration

---

**Sviluppato da Rizzo AI Academy** 🤖
**Ultima modifica:** 2025-01-21
