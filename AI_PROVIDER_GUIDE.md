# 🤖 Configurazione AI Provider

Il bot supporta **due provider AI**:

---

## 1️⃣ OpenAI (Default)

**Modello:** GPT-4 Turbo

**Costo:** ~$0.01-0.05 per decisione

**Setup:**
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

**Come ottenere API key:**
1. Vai su https://platform.openai.com/api-keys
2. Crea account
3. Aggiungi credito ($5-10 per iniziare)
4. Genera API key
5. Copia nel file `.env`

---

## 2️⃣ OpenRouter (Alternativa)

**Vantaggi:**
- ✅ Accesso a **molti modelli** (GPT-4, Claude, Gemini, Llama, ecc.)
- ✅ Spesso **più economico** di OpenAI
- ✅ Nessun lock-in: cambi modello quando vuoi
- ✅ Crediti ricaricabili, nessun abbonamento

**Modelli consigliati:**

| Modello | Costo/decisione | Qualità | Note |
|---------|----------------|---------|------|
| `anthropic/claude-3.5-sonnet` | ~$0.015 | ⭐⭐⭐⭐⭐ | Molto bravo, ragionamento avanzato |
| `openai/gpt-4-turbo` | ~$0.01 | ⭐⭐⭐⭐ | Simile a OpenAI diretto |
| `google/gemini-pro-1.5` | ~$0.001 | ⭐⭐⭐ | Economico, buono |
| `meta-llama/llama-3.1-70b` | ~$0.0005 | ⭐⭐⭐ | Open source, molto economico |

**Setup:**
```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

**Come ottenere API key:**
1. Vai su https://openrouter.ai/keys
2. Crea account (anche con Google/GitHub)
3. Vai su "Keys" e genera una nuova key
4. Aggiungi credito ($5-20 per iniziare)
5. Copia nel file `.env`

**Lista completa modelli:** https://openrouter.ai/models

---

## 🔄 Come Cambiare Provider

Nel file `.env`, cambia semplicemente:

```bash
# Usa OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxx...

# Oppure usa OpenRouter
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxx...
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

Poi riavvia il bot:
```bash
docker compose -f docker-compose.existing-postgres.yml restart trading-bot
```

---

## 💡 Quale Scegliere?

### Scegli **OpenAI** se:
- Vuoi il modello "ufficiale" GPT-4
- Hai già account OpenAI
- Non vuoi sperimentare

### Scegli **OpenRouter** se:
- Vuoi risparmiare sui costi
- Vuoi provare Claude/Gemini/altri modelli
- Vuoi flessibilità di cambiare modello
- **CONSIGLIATO per iniziare!**

---

## 📊 Confronto Costi (esempio 100 decisioni/mese)

| Provider | Modello | Costo |
|----------|---------|-------|
| OpenAI | GPT-4 Turbo | $1-5/mese |
| OpenRouter | Claude 3.5 Sonnet | $1.50/mese |
| OpenRouter | Gemini Pro 1.5 | $0.10/mese |
| OpenRouter | Llama 3.1 70B | $0.05/mese |

---

## 🧪 Test

Per testare che funzioni:

```bash
# Test manuale
docker exec -it rizzo_trading_bot python3 -c "
from trading_agent import previsione_trading_agent
result = previsione_trading_agent('Test prompt: recommend a trade for BTC')
print(result)
"
```

---

## 🔧 Troubleshooting

**Errore: "API key not found"**
- Verifica che la key sia nel `.env`
- Controlla che non ci siano spazi extra
- Riavvia il container

**Errore: "Model not found" (OpenRouter)**
- Controlla che il modello esista: https://openrouter.ai/models
- Alcuni modelli richiedono più credito

**Decisioni sempre "hold"**
- Controlla i log: `docker compose -f docker-compose.existing-postgres.yml logs trading-bot`
- Verifica che l'API key abbia credito
- Prova a cambiare modello

---

**Raccomandazione:** Inizia con **OpenRouter + Claude 3.5 Sonnet** per il miglior rapporto qualità/prezzo! 🚀
