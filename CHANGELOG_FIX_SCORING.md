# CHANGELOG - Fix Sistema di Scoring Trading Bot

**Data:** 2025-11-23
**Branch:** `claude/bot-purchase-logic-015isXNcz7QF3SyoBqBbiqvU`
**Repository:** `Nixola1972/rizzo-trading-agent`

---

## Problema Identificato

### Bug Critico: AI ignorava i threshold dello scoring

**Sintomo:**
Il bot apriva posizioni anche quando il sistema di scoring calcolava "HOLD".

**Evidenza dal Database:**
```
created_at: 2024-XX-XX 11:00
net_score: +4.67 (sotto soglia 15)
direction calcolata: "HOLD"
MA il bot eseguì: operation="open", direction="long"
```

**Causa Root:**
Nel prompt all'AI c'era scritto "prefer HOLD unless you have strong conviction" - questo dava troppa libertà all'AI di ignorare le soglie calcolate dal sistema di scoring.

---

## Sistema di Scoring (Documentato in TRADING_WEIGHTS.md)

### Pesi degli Indicatori
| Indicatore | Peso | Descrizione |
|------------|------|-------------|
| RSI | 15 | Relative Strength Index |
| Trend (EMA+MACD) | 10 | Media mobile + MACD |
| Fear & Greed | 8 | Indice paura/avidità |
| Forecast (Prophet) | 6 | Previsioni ML |
| Volume | 4 | Volume bid/ask |

### Soglie Decisionali
- `SCORE_THRESHOLD_OPEN = 15` - Soglia minima per aprire posizione
- `SCORE_THRESHOLD_STRONG = 25` - Segnale forte

### Logica Decisionale
```
NET_SCORE = SCORE_BULLISH - SCORE_BEARISH

Se NET_SCORE > +15  → LONG
Se NET_SCORE < -15  → SHORT
Se |NET_SCORE| < 15 → HOLD (nessuna azione)
```

---

## Fix Applicato

### File Modificato: `trading_agent.py`

**Locazione:** Linee 477-491

**Codice Aggiunto:**
```python
# ===== FORZA RISPETTO DELLO SCORING =====
# Non permettere all'AI di aprire posizioni se lo score è sotto soglia
if scores and result.get('symbol') in scores:
    score = scores[result['symbol']]
    net_score = score.get('net_score', 0)
    threshold = score.get('thresholds', {}).get('open', 15.0)

    # Se score sotto soglia E AI vuole aprire → FORZA HOLD
    if abs(net_score) < threshold and result.get('operation') == 'open':
        original_decision = f"{result['operation']} {result['direction']}"
        print(f"⚠️  OVERRIDE: net_score={net_score:.1f} < threshold={threshold}")
        print(f"   AI voleva: {original_decision} → Forzato: HOLD")
        result['operation'] = 'hold'
        result['_override_reason'] = f"Score {net_score:.1f} sotto soglia {threshold}. AI voleva: {original_decision}"
# ===== FINE FIX =====
```

### Comportamento Dopo il Fix
1. L'AI propone una decisione (open/close/hold)
2. Se l'AI vuole aprire (`operation == "open"`):
   - Controlla `abs(net_score)` vs `threshold` (default 15)
   - Se `abs(net_score) < threshold` → **FORZA HOLD**
   - Logga l'override per tracciabilità
3. La decisione finale rispetta sempre le soglie dello scoring

---

## Commit e Deploy

### Commit
```
Commit: 4b37c97
Messaggio: Fix: forza HOLD quando score è sotto soglia threshold
```

### Comandi per Deploy
```bash
# Sul server, nella cartella del progetto
cd ~/trading-bots/rizzo-trading-agent

# Pull delle modifiche
git pull origin claude/bot-purchase-logic-015isXNcz7QF3SyoBqBbiqvU

# Riavvia il container (dipende dalla tua configurazione)
docker restart trading-bot  # oppure il nome del tuo container
# oppure se usi docker-compose in altra directory
cd /path/to/docker-compose && docker-compose restart
```

---

## File Coinvolti nel Progetto

| File | Descrizione |
|------|-------------|
| `trading_agent.py` | Logica AI + fix override scoring |
| `signal_scorer.py` | Calcolo score BULLISH/BEARISH |
| `TRADING_WEIGHTS.md` | Documentazione pesi e soglie |
| `main.py` | Entry point del bot |
| `hyperliquid_trader.py` | Esecuzione ordini su Hyperliquid |
| `system_prompt.txt` | Prompt per l'AI |

---

## Configurazione Fear & Greed

**Scelta implementata:** Fear basso = BEARISH (trend-following)

Quando Fear & Greed Index è basso (mercato spaventato), il sistema interpreta questo come segnale bearish, seguendo il trend del mercato invece di fare contrarian trading.

---

## Note Tecniche

### Database
- Tabella `bot_operations`: contiene tutte le operazioni con `raw_payload` che include `_signal_score`
- Tabella `signal_scores`: storico degli score calcolati per ogni simbolo

### Modelli AI Supportati
- OpenAI: GPT-4, GPT-4-turbo, GPT-4o
- OpenRouter: Claude 3.5/4, DeepSeek, Gemini, Llama, etc.
- Il sistema gestisce automaticamente modelli con/senza supporto JSON nativo

---

## Verifica Post-Deploy

Dopo il riavvio, verificare nei log che appaia:
```
⚠️  OVERRIDE: net_score=X.X < threshold=15
   AI voleva: open long → Forzato: HOLD
```

Questo conferma che il fix sta funzionando correttamente.

---

**Autore fix:** Claude Code
**Richiesto da:** Utente Nixola1972
