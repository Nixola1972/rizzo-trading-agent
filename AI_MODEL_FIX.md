# 🔧 FIX: Errore JSON Parsing AI Model

## ❌ PROBLEMA RILEVATO

Il bot sta fallendo con errore:
```
❌ Errore nella chiamata AI: Expecting value: line 1 column 1 (char 0)
```

**Causa**: Stai usando un modello AI che non gestisce correttamente le risposte in formato JSON.

---

## ✅ SOLUZIONE RAPIDA (1 minuto)

Sul VPS, esegui questi comandi:

```bash
cd ~/trading-bots/rizzo-trading-agent

# 1. Rendi eseguibile lo script fix
chmod +x fix_ai_model.sh

# 2. Esegui il fix
./fix_ai_model.sh

# 3. Test manuale per verificare
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

---

## 🎯 COSA FA LO SCRIPT

Lo script `fix_ai_model.sh`:
1. ✅ Verifica la configurazione attuale nel file `.env`
2. ✅ Rimuove configurazioni errate di `AI_PROVIDER` e `OPENROUTER_MODEL`
3. ✅ Aggiunge la configurazione corretta:
   - `AI_PROVIDER=openrouter`
   - `OPENROUTER_MODEL=anthropic/claude-3.5-sonnet`

---

## 📊 MODELLI OPENROUTER: COMPATIBILITÀ

### ✅ FUNZIONANO BENE (gestiscono JSON correttamente):

- **`anthropic/claude-3.5-sonnet`** ← **RACCOMANDATO** ✨
  - Migliore per trading decisions
  - Ottima gestione JSON strutturato
  - Buon rapporto qualità/prezzo

- **`openai/gpt-4-turbo`**
  - Molto affidabile
  - Più costoso

- **`openai/gpt-4o`**
  - Ottima qualità
  - Costo medio

### ❌ NON FUNZIONANO (problemi con JSON):

- ❌ `anthropic/claude-sonnet-4.5` - Troppo nuovo, non supporta `response_format`
- ❌ `anthropic/claude-haiku-4.5` - Troppo leggero per JSON strutturato
- ❌ `deepseek/deepseek-chat-v3-0324:free` - Rate limits e JSON instabile
- ❌ `openai/gpt-5-mini` - Non esiste ancora
- ❌ `qwen/*` - Problemi con schema JSON

---

## 🔍 COME VERIFICARE CHE FUNZIONA

Dopo il fix, esegui un test manuale:

```bash
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

**Output corretto**:
```
🤖 Usando OpenRouter con modello: anthropic/claude-3.5-sonnet
🗄️  Inizializzazione database...
✅ Database inizializzato
...
✅ Decisione AI: hold BTC - Market showing consolidation with neutral signals
[HyperLiquidTrader] HOLD — nessuna azione per BTC.
```

**Output errato** (se ancora presente):
```
❌ Errore nella chiamata AI: Expecting value: line 1 column 1 (char 0)
```

Se vedi ancora l'errore:
1. Verifica che il file `.env` sia stato modificato: `cat .env | grep OPENROUTER`
2. Assicurati di aver fatto rebuild del container: `docker compose -f docker-compose.existing-postgres.yml build`

---

## 🔄 ALTERNATIVA: FIX MANUALE

Se preferisci modificare manualmente il file `.env`:

```bash
cd ~/trading-bots/rizzo-trading-agent

# Apri il file .env
nano .env

# Trova e modifica (o aggiungi se non esiste):
AI_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Salva: CTRL+O, ENTER, CTRL+X
```

---

## 🚨 PERCHÉ CLAUDE 3.5 SONNET?

Il bot usa `response_format={"type": "json_object"}` nel codice (vedi `trading_agent.py:56`):

```python
response = client.chat.completions.create(
    model=MODEL,
    messages=[...],
    response_format={"type": "json_object"},  # ← Richiede supporto JSON
    temperature=0.7
)
```

**Claude 3.5 Sonnet** (`anthropic/claude-3.5-sonnet`) è l'unico modello Claude che:
- ✅ Supporta `response_format={"type": "json_object"}`
- ✅ Genera JSON valido e strutturato
- ✅ Gestisce gli schema complessi richiesti dal trading bot
- ✅ Ha un costo ragionevole (~$3 per 1M token input)

I modelli più recenti come **Claude Sonnet 4.5** e **Claude Haiku 4.5** NON supportano ancora questa funzionalità su OpenRouter.

---

## 📈 DOPO IL FIX

Una volta applicato il fix:

1. **Il cron continuerà a funzionare automaticamente** ogni 15 minuti
2. **Nessun restart necessario** - il cron usa sempre il file `.env` aggiornato
3. **Monitora i log**: `tail -f /var/log/rizzo-trading-bot.log`
4. **Dashboard**: Accedi a `http://69.62.114.142:8501` per vedere le operazioni

---

## ✅ CHECKLIST POST-FIX

- [ ] Script fix eseguito: `./fix_ai_model.sh`
- [ ] Test manuale completato con successo
- [ ] Output mostra: `🤖 Usando OpenRouter con modello: anthropic/claude-3.5-sonnet`
- [ ] Nessun errore `Expecting value: line 1 column 1`
- [ ] Bot esegue decisioni: `✅ Decisione AI: hold/open/close`
- [ ] Cron attivo: `crontab -l` mostra il job
- [ ] Log puliti: `tail -20 /var/log/rizzo-trading-bot.log`

---

## 📞 TROUBLESHOOTING

### Il fix non funziona ancora?

```bash
# 1. Verifica .env
cat .env | grep -E "(AI_PROVIDER|OPENROUTER)"

# 2. Rebuild container (potrebbe servire)
docker compose -f docker-compose.existing-postgres.yml build

# 3. Test con output completo
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot 2>&1 | head -50
```

### Altri errori?

- **"API key invalid"**: Verifica `OPENROUTER_API_KEY` nel file `.env`
- **"Rate limit"**: Aspetta 1 minuto e riprova
- **"Connection error"**: Verifica connessione internet dal VPS

---

**Sviluppato da Rizzo AI Academy** 🤖
