# 🤖 MODELLI AI SUPPORTATI

Il bot ora supporta **qualsiasi modello** disponibile su OpenAI o OpenRouter, con gestione automatica delle differenze tra modelli!

---

## ✨ NOVITÀ: Sistema Multi-Modello Flessibile

### Cosa è cambiato?

1. ✅ **Supporto automatico per tutti i modelli** - Non sei più limitato a claude-3.5-sonnet
2. ✅ **Rilevamento automatico capacità JSON** - Il bot sa quali modelli supportano JSON nativo
3. ✅ **Parsing robusto** - Funziona anche se il modello restituisce testo + JSON
4. ✅ **Retry automatico** - Se fallisce, riprova con prompt migliorato
5. ✅ **Validazione intelligente** - Aggiunge campi mancanti con valori di default

---

## 🎯 MODELLI RACCOMANDATI

### OpenRouter (via AI_PROVIDER=openrouter)

#### 🔥 Tier 1: Eccellenti per Trading
```bash
# Claude 3.5 Sonnet (bilanciato qualità/prezzo)
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Claude Opus 3 (massima qualità, costoso)
OPENROUTER_MODEL=anthropic/claude-3-opus

# GPT-4o (veloce e potente)
OPENROUTER_MODEL=openai/gpt-4o

# GPT-4 Turbo (affidabile)
OPENROUTER_MODEL=openai/gpt-4-turbo
```

#### ⭐ Tier 2: Buoni e Economici
```bash
# Claude Sonnet 4.5 (NUOVO - ora supportato!)
OPENROUTER_MODEL=anthropic/claude-sonnet-4.5

# GPT-4o Mini (economico e veloce)
OPENROUTER_MODEL=openai/gpt-4o-mini

# Gemini 2.0 Flash (gratuito/economico)
OPENROUTER_MODEL=google/gemini-2.0-flash-exp

# Llama 3.3 70B (open source, economico)
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```

#### 💰 Tier 3: Free/Ultra-Economici
```bash
# DeepSeek Chat (molto economico)
OPENROUTER_MODEL=deepseek/deepseek-chat

# Qwen 2.5 72B (buon rapporto qualità/prezzo)
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct

# Mistral Large (alternativa europea)
OPENROUTER_MODEL=mistralai/mistral-large
```

### OpenAI Diretta (via AI_PROVIDER=openai)

```bash
# GPT-4 Turbo (default)
OPENAI_MODEL=gpt-4-turbo

# GPT-4o (più recente)
OPENAI_MODEL=gpt-4o

# GPT-4o Mini (economico)
OPENAI_MODEL=gpt-4o-mini
```

---

## 📊 COMPARAZIONE MODELLI

| Modello | Provider | Qualità | Velocità | Costo | JSON Nativo |
|---------|----------|---------|----------|-------|-------------|
| **anthropic/claude-3.5-sonnet** | OpenRouter | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡ | 💰💰💰 | ✅ |
| **anthropic/claude-sonnet-4.5** | OpenRouter | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ | 💰💰💰 | ❌ (ma funziona!) |
| **openai/gpt-4o** | OpenRouter | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ | 💰💰💰💰 | ✅ |
| **openai/gpt-4-turbo** | OpenRouter | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡ | 💰💰💰💰 | ✅ |
| **google/gemini-2.0-flash-exp** | OpenRouter | ⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ | 💰 (free) | ❌ (ma funziona!) |
| **meta-llama/llama-3.3-70b** | OpenRouter | ⭐⭐⭐⭐ | ⚡⚡⚡⚡ | 💰 | ❌ (ma funziona!) |
| **deepseek/deepseek-chat** | OpenRouter | ⭐⭐⭐ | ⚡⚡⚡ | 💰 (molto economico) | ❌ (ma funziona!) |

**JSON Nativo**: ✅ = Supporta `response_format`, ❌ = Usa parsing robusto

---

## 🔧 COME CAMBIARE MODELLO

### Metodo 1: Modifica .env (raccomandato)

```bash
cd ~/trading-bots/rizzo-trading-agent
nano .env

# Cambia il modello (esempi):
AI_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-sonnet-4.5

# Oppure
OPENROUTER_MODEL=google/gemini-2.0-flash-exp

# Oppure
OPENROUTER_MODEL=openai/gpt-4o

# Salva: CTRL+O, ENTER, CTRL+X
```

### Metodo 2: Test Rapido (senza modificare .env)

```bash
# Test con variabile d'ambiente temporanea
OPENROUTER_MODEL=anthropic/claude-sonnet-4.5 docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot

# Test con Gemini
OPENROUTER_MODEL=google/gemini-2.0-flash-exp docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

---

## 🧪 COME TESTARE UN NUOVO MODELLO

### 1. Test Singolo
```bash
cd ~/trading-bots/rizzo-trading-agent

# Modifica .env con il nuovo modello
nano .env
# OPENROUTER_MODEL=nome/del/modello

# Test
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot
```

### 2. Cosa Verificare

**✅ Test Superato** se vedi:
```
🤖 Usando OpenRouter con modello: nome/del/modello
   📋 Usando formato JSON nativo (supportato)
   # OPPURE
   📝 Usando parsing JSON manuale
...
✅ Decisione AI: hold BTC - Market showing consolidation...
```

**❌ Test Fallito** se vedi:
```
❌ Errore nella chiamata AI dopo tutti i retry: ...
```

### 3. Cosa Fare se Fallisce

Il bot ha **retry automatico**, ma se continua a fallire:

1. **Verifica che il modello esista** su OpenRouter: https://openrouter.ai/models
2. **Controlla il log completo** per capire l'errore specifico
3. **Prova un modello diverso** dalla lista raccomandata
4. **Segnala il problema** - aggiungeremo supporto specifico per quel modello

---

## 🎨 ESEMPI DI CONFIGURAZIONE

### Configurazione Bilanciata (raccomandato)
```bash
AI_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```
- ✅ Ottima qualità decisioni
- ✅ Costo medio (~$3/1M token)
- ✅ Supporto JSON nativo
- ✅ Affidabile e testato

### Configurazione Economica
```bash
AI_PROVIDER=openrouter
OPENROUTER_MODEL=google/gemini-2.0-flash-exp
```
- ✅ Gratuito o molto economico
- ✅ Veloce
- ⚠️ Qualità leggermente inferiore
- ✅ Parsing JSON robusto

### Configurazione Premium
```bash
AI_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-3-opus
```
- ✅ Massima qualità decisioni
- ⚠️ Più costoso (~$15/1M token)
- ✅ Analisi più profonde
- ✅ Supporto JSON nativo

### Configurazione Ultra-Veloce
```bash
AI_PROVIDER=openrouter
OPENROUTER_MODEL=openai/gpt-4o-mini
```
- ✅ Velocissimo
- ✅ Molto economico
- ✅ Qualità buona
- ✅ Supporto JSON nativo

---

## 🔬 COME FUNZIONA IL NUOVO SISTEMA

### Rilevamento Automatico Capacità

Il bot ha due liste interne:

**Modelli con supporto JSON nativo** (`response_format` supportato):
- ✅ Tutti i GPT-4 (turbo, 4o, 4o-mini)
- ✅ Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Sonnet

**Modelli senza supporto nativo** (usa parsing robusto):
- ✅ Claude 4.5 (Sonnet, Haiku, Opus)
- ✅ Gemini (Pro, Flash)
- ✅ DeepSeek, Qwen, Llama, Mistral

### Parsing Robusto

Se un modello restituisce:
```
Here's my analysis:

{
  "operation": "hold",
  "symbol": "BTC",
  "reason": "Market unclear"
}

I recommend holding because...
```

Il bot **estrae automaticamente il JSON** ignorando il testo circostante.

### Retry Automatico

1. **Tentativo 1**: Chiamata normale
2. **Tentativo 2** (se fallisce): Prompt più esplicito "ONLY JSON, no other text"
3. **Tentativo 3** (se fallisce): Rimuove `response_format` e usa parsing robusto

Se falliscono tutti: **HOLD** con messaggio di errore (safe default).

---

## 💡 SUGGERIMENTI

### Per Risparmiare Costi
1. Usa **gemini-2.0-flash-exp** (gratuito/economico) per le prime settimane di test
2. Passa a **claude-3.5-sonnet** quando sei pronto per produzione
3. Usa **gpt-4o-mini** se preferisci OpenAI ed economicità

### Per Massima Qualità
1. Usa **claude-3-opus** per analisi più profonde
2. Usa **gpt-4o** per velocità + qualità
3. Confronta i risultati tra modelli diversi per 1 settimana

### Per Testing
1. Testa almeno 3 modelli diversi per 24 ore ciascuno
2. Confronta le decisioni AI nella dashboard
3. Scegli quello che produce decisioni più sensate per la tua strategia

---

## 🚨 TROUBLESHOOTING

### Errore: "JSON parsing failed after all retries"

**Causa**: Il modello non produce JSON valido

**Soluzione**:
```bash
# Prova un modello dalla lista "Tier 1" raccomandata
nano .env
# OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

### Errore: "Model not found"

**Causa**: Nome modello errato o non disponibile su OpenRouter

**Soluzione**:
1. Verifica nome modello su: https://openrouter.ai/models
2. Controlla di aver scritto correttamente (case-sensitive!)

### Errore: "Rate limit exceeded"

**Causa**: Troppe richieste al modello

**Soluzione**:
```bash
# Riduci frequenza cron a 30 minuti
nano setup_cron.sh
# Cambia */15 in */30
./setup_cron.sh
```

---

## 📈 PROSSIMI PASSI

1. **Scegli un modello** dalla lista raccomandata
2. **Modifica .env** con il modello scelto
3. **Testa**: `docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot`
4. **Monitora** per 24 ore: `tail -f /var/log/rizzo-trading-bot.log`
5. **Confronta** le decisioni nella dashboard: http://69.62.114.142:8501

---

## ✅ CONCLUSIONE

Ora puoi usare **qualsiasi modello AI** che preferisci:
- ✅ Claude 4.5 (più recenti)
- ✅ GPT-4o (OpenAI)
- ✅ Gemini (Google, economico)
- ✅ Llama (open source)
- ✅ Qualsiasi altro modello su OpenRouter

Il bot gestisce automaticamente le differenze tra modelli e fa il parsing del JSON in modo robusto!

**Sviluppato da Rizzo AI Academy** 🤖
