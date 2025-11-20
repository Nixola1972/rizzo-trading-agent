# ⏰ SETUP CRON - Trading Bot ogni 15 minuti

## 🚀 SETUP RAPIDO (sul VPS)

```bash
cd ~/trading-bots/rizzo-trading-agent

# 1. Rendi eseguibili gli script
chmod +x setup_cron.sh remove_cron.sh

# 2. Configura cron
./setup_cron.sh

# 3. Fatto! Il bot partirà automaticamente ogni 15 minuti
```

---

## 📋 COSA FA LO SCRIPT:

- ✅ Configura cron per eseguire il bot ogni 15 minuti
- ✅ Salva tutti i log in `/var/log/rizzo-trading-bot.log`
- ✅ Usa `docker compose run --rm` (non lascia container inutili)
- ✅ Esecuzione automatica 24/7

---

## 🕐 FREQUENZA ESECUZIONE:

Il bot partirà automaticamente a:
- **00:00, 00:15, 00:30, 00:45**
- **01:00, 01:15, 01:30, 01:45**
- ...e così via ogni 15 minuti

**96 esecuzioni al giorno** → ~1,000 chiamate API HyperLiquid/giorno

Con buffer TESTNET di 10,000 richieste → **Dura ~10 giorni**

---

## 📊 MONITORAGGIO:

### Vedi log in tempo reale:
```bash
tail -f /var/log/rizzo-trading-bot.log
```

### Ultimi 100 log:
```bash
tail -100 /var/log/rizzo-trading-bot.log
```

### Verifica cron attivo:
```bash
crontab -l
```

### Filtra solo operazioni AI:
```bash
grep "Decisione AI" /var/log/rizzo-trading-bot.log | tail -20
```

---

## 🎯 DASHBOARD WEB:

La dashboard su `http://69.62.114.142:8501` mostrerà tutte le operazioni automaticamente!

Accedi per vedere:
- Grafici balance nel tempo
- Tutte le decisioni AI
- P&L per symbol
- Operazioni recenti

---

## 🛑 FERMA IL CRON:

```bash
cd ~/trading-bots/rizzo-trading-agent

# Rimuovi cron job
./remove_cron.sh

# Oppure manualmente
crontab -e
# Cancella le righe del trading bot
```

---

## 🧪 TEST MANUALE (prima di attivare cron):

```bash
cd ~/trading-bots/rizzo-trading-agent

# Test esecuzione singola
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot

# Se funziona senza errori, attiva il cron
./setup_cron.sh
```

---

## ⚙️ CONFIGURAZIONE TESTNET:

Verifica nel `.env`:
```bash
cat .env | grep TESTNET
# Deve mostrare: TESTNET=true
```

Se non è impostato:
```bash
nano .env
# Assicurati ci sia: TESTNET=true
# Salva: CTRL+O, ENTER, CTRL+X
```

---

## 📈 ASPETTATIVE:

### Dopo 24 ore:
- ~96 esecuzioni
- ~100-150 decisioni AI registrate
- Dashboard popolata con dati

### Dopo 1 settimana:
- ~672 esecuzioni
- Vedi pattern di trading
- Capisci se il bot è profittevole (in simulazione)

### Dopo 10 giorni:
- Buffer TESTNET esaurito (10,000 richieste)
- Decidi se passare a MAINNET o aspettare reset

---

## 🔄 AGGIORNAMENTI CODICE:

Quando modifichi il codice:

```bash
cd ~/trading-bots/rizzo-trading-agent

# 1. Pull nuove modifiche
git pull

# 2. Rebuild container (se necessario)
docker compose -f docker-compose.existing-postgres.yml build

# 3. Il cron userà automaticamente la nuova versione
```

---

## 🚨 TROUBLESHOOTING:

### Il cron non parte:

```bash
# Verifica cron service
systemctl status cron

# Restart cron
systemctl restart cron

# Verifica errori nel log
tail -50 /var/log/rizzo-trading-bot.log
```

### Troppi rate limits:

Se vedi errori `429` frequenti:
```bash
# Cambia frequenza a 30 minuti
nano setup_cron.sh
# Cambia */15 in */30
./setup_cron.sh
```

---

## ✅ CHECKLIST PRE-ATTIVAZIONE:

- [ ] File `.env` configurato con tutte le API keys
- [ ] `TESTNET=true` nel `.env`
- [ ] **AI_PROVIDER=openrouter** e **OPENROUTER_MODEL=anthropic/claude-3.5-sonnet** nel `.env`
- [ ] Test manuale funziona: `docker compose run --rm trading-bot`
- [ ] Dashboard accessibile su porta 8501
- [ ] PostgreSQL container attivo
- [ ] Spazio disco sufficiente per log

## 🔧 FIX ERRORI JSON AI:

Se vedi errori come `Expecting value: line 1 column 1`:
```bash
# Esegui lo script di fix automatico
./fix_ai_model.sh

# Oppure leggi la guida completa
cat AI_MODEL_FIX.md
```

**IMPORTANTE**: Usa **SOLO** `anthropic/claude-3.5-sonnet` come modello OpenRouter.
I modelli più recenti (claude-sonnet-4.5, claude-haiku-4.5) NON funzionano con JSON strutturato!

---

**Sviluppato da Rizzo AI Academy** 🤖
