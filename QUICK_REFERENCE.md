# 🚀 QUICK REFERENCE - Rizzo Trading Bot

Guida rapida per gestire il trading bot sul VPS.

---

## 📍 COMANDI ESSENZIALI

### 🔧 Fix Configurazione AI (SE HAI ERRORI JSON)
```bash
cd ~/trading-bots/rizzo-trading-agent
./fix_ai_model.sh
```

### ⏰ Gestione Cron
```bash
# Avvia il bot automatico (ogni 15 minuti)
./setup_cron.sh

# Ferma il bot automatico
./remove_cron.sh

# Verifica se cron è attivo
crontab -l
```

### 🧪 Test Manuale
```bash
# Esegui il bot una volta per testare
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

### 📊 Monitoraggio Log
```bash
# Log in tempo reale
tail -f /var/log/rizzo-trading-bot.log

# Ultimi 100 log
tail -100 /var/log/rizzo-trading-bot.log

# Solo decisioni AI
grep "Decisione AI" /var/log/rizzo-trading-bot.log | tail -20

# Cerca errori
grep "❌" /var/log/rizzo-trading-bot.log | tail -20
```

### 🔄 Aggiornamento Codice
```bash
cd ~/trading-bots/rizzo-trading-agent

# Ferma cron (se attivo)
./remove_cron.sh

# Pull nuove modifiche
git pull

# Rebuild container
docker compose -f docker-compose.existing-postgres.yml build

# Riavvia cron
./setup_cron.sh
```

### 🗄️ Database
```bash
# Accedi al database
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading

# Query utili dentro psql:
\dt                                    # Lista tabelle
SELECT COUNT(*) FROM bot_operations;   # Conta operazioni
SELECT * FROM bot_operations ORDER BY created_at DESC LIMIT 10;  # Ultime 10 operazioni
\q                                     # Esci
```

### 🐳 Docker
```bash
# Verifica container attivi
docker ps

# Rebuild bot (dopo modifiche codice)
docker compose -f docker-compose.existing-postgres.yml build

# Stop tutti i container del bot
docker compose -f docker-compose.existing-postgres.yml down

# Vedi log container
docker compose -f docker-compose.existing-postgres.yml logs -f
```

---

## 🎯 DASHBOARD WEB

Accedi alla dashboard: **http://69.62.114.142:8501**

Cosa puoi vedere:
- 💰 Balance account in tempo reale
- 📊 Grafici performance
- 🤖 Decisioni AI con motivazioni
- 📈 P&L per symbol
- ⚙️ Configurazione bot

---

## ⚙️ FILE CONFIGURAZIONE

### `.env` (principale)
```bash
# Visualizza configurazione (senza API keys)
cat .env | grep -v "KEY\|PASSWORD"

# Modifica configurazione
nano .env
```

**Variabili importanti**:
- `AI_PROVIDER=openrouter` - Provider AI
- `OPENROUTER_MODEL=anthropic/claude-3.5-sonnet` - Modello AI (**NON modificare!**)
- `TESTNET=true` - Modalità test (true) o reale (false)
- `DATABASE_URL=...` - Connessione PostgreSQL
- Tutte le API keys (OpenRouter, HyperLiquid, CoinMarketCap)

---

## 🚨 TROUBLESHOOTING

### ❌ Errore: "Expecting value: line 1 column 1"
```bash
# Fix automatico
./fix_ai_model.sh

# Verifica modello
cat .env | grep OPENROUTER_MODEL
# Deve mostrare: OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

### ❌ Errore: Rate Limit 429 (troppo frequente)
```bash
# Cambia da 15 a 30 minuti
nano setup_cron.sh
# Cambia */15 in */30
./setup_cron.sh
```

### ❌ Cron non parte
```bash
# Verifica servizio cron
systemctl status cron

# Restart cron
systemctl restart cron

# Verifica job configurato
crontab -l
```

### ❌ Database non si connette
```bash
# Verifica container PostgreSQL attivo
docker ps | grep postgres

# Verifica DATABASE_URL nel .env
cat .env | grep DATABASE_URL

# Test connessione
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "SELECT 1;"
```

### ❌ Dashboard non accessibile
```bash
# Verifica container dashboard attivo
docker ps | grep dashboard

# Riavvia dashboard
docker compose -f docker-compose.existing-postgres.yml restart dashboard

# Verifica porta 8501
netstat -tuln | grep 8501
```

---

## 📈 ASPETTATIVE PERFORMANCE

### Modalità TESTNET (attuale)
- 🕐 Esecuzione: Ogni 15 minuti (96 volte/giorno)
- 🌐 API calls: ~1,000 richieste HyperLiquid/giorno
- ⏱️ Durata buffer: ~10 giorni (10,000 richieste TESTNET)
- 💰 Capitale: Virtuale (non soldi reali)

### Dopo 24 ore
- ~96 esecuzioni completate
- ~100-150 decisioni AI registrate
- Dashboard popolata con dati e grafici

### Dopo 1 settimana
- ~672 esecuzioni
- Pattern di trading visibili
- Valutazione profittabilità in simulazione

---

## ⚠️ SICUREZZA

### ✅ SEMPRE in TESTNET per iniziare
```bash
# Verifica modalità test
cat .env | grep TESTNET
# Deve mostrare: TESTNET=true
```

### 🚨 Passaggio a MAINNET (soldi reali!)
```bash
# SOLO quando sei sicuro che il bot funziona bene!
nano .env
# Cambia: TESTNET=false
# ATTENZIONE: Userà soldi reali!
```

---

## 📁 STRUTTURA FILE CHIAVE

```
rizzo-trading-agent/
├── main.py                    # Entry point bot
├── trading_agent.py           # Logica AI
├── hyperliquid_trader.py      # Connessione exchange
├── db_utils.py                # Database operations
├── dashboard.py               # Web dashboard
├── .env                       # Configurazione (NON committare!)
├── setup_cron.sh              # Setup automazione
├── remove_cron.sh             # Rimuovi automazione
├── fix_ai_model.sh            # Fix configurazione AI
├── docker-compose.existing-postgres.yml  # Docker config
├── CRON_SETUP.md              # Guida cron completa
├── AI_MODEL_FIX.md            # Guida fix AI model
└── QUICK_REFERENCE.md         # Questa guida
```

---

## 📞 SUPPORTO

### Documentazione
- `CRON_SETUP.md` - Setup cron dettagliato
- `AI_MODEL_FIX.md` - Risoluzione errori AI
- `QUICK_REFERENCE.md` - Questa guida

### Verifica Stato Completo
```bash
# Script di verifica configurazione
python3 verify_config.py
```

---

## ✅ CHECKLIST OPERATIVA

Prima di attivare il bot:
- [ ] `.env` configurato con tutte le API keys
- [ ] `TESTNET=true` nel `.env`
- [ ] `OPENROUTER_MODEL=anthropic/claude-3.5-sonnet` nel `.env`
- [ ] Test manuale completato con successo
- [ ] Dashboard accessibile (http://69.62.114.142:8501)
- [ ] Database PostgreSQL attivo e connesso
- [ ] Log directory `/var/log` accessibile

Bot in esecuzione:
- [ ] Cron job configurato (`crontab -l`)
- [ ] Log puliti senza errori JSON
- [ ] Decisioni AI visibili nei log
- [ ] Dashboard mostra operazioni

---

**Sviluppato da Rizzo AI Academy** 🤖

Per dubbi o problemi, controlla prima:
1. `AI_MODEL_FIX.md` per errori JSON/AI
2. `CRON_SETUP.md` per problemi cron
3. Log: `tail -50 /var/log/rizzo-trading-bot.log`
