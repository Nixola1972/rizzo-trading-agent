# Rizzo Trading Agent - Documentazione di Riferimento

> **IMPORTANTE**: Leggi questo documento all'inizio di ogni sessione per comprendere il sistema.

## Indice
1. [Architettura Sistema](#architettura-sistema)
2. [Componenti Principali](#componenti-principali)
3. [Modalità di Trading](#modalità-di-trading)
4. [Sistema di Score](#sistema-di-score)
5. [Logica Smart Wake AI](#logica-smart-wake-ai)
6. [Trailing Stop e Stop Loss](#trailing-stop-e-stop-loss)
7. [Parametri Chiave (.env)](#parametri-chiave-env)
8. [Database e Tracking](#database-e-tracking)
9. [Deploy Docker](#deploy-docker)
10. [Troubleshooting Comune](#troubleshooting-comune)

---

## Architettura Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           RIZZO TRADING AGENT                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐         ┌──────────────────────────────────────┐  │
│  │   SENTINEL.PY    │         │            MAIN.PY (AI)              │  │
│  │  (loop 30 sec)   │────────▶│         (loop 10-15 min)             │  │
│  │                  │  wake   │                                      │  │
│  │ • Monitor posiz. │         │ • Analisi completa (news, forecast)  │  │
│  │ • Trailing SL    │         │ • Decisioni AI (OpenRouter/Claude)   │  │
│  │ • Auto TP        │         │ • Open/Close posizioni               │  │
│  │ • MICRO_GAIN     │         │                                      │  │
│  │ • Score check    │         │                                      │  │
│  └──────────────────┘         └──────────────────────────────────────┘  │
│           │                                    │                         │
│           ▼                                    ▼                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      HYPERLIQUID EXCHANGE                         │   │
│  │  • Ordini LIMIT/MARKET                                           │   │
│  │  • Ordini TRIGGER (Stop Loss)                                    │   │
│  │  • Posizioni con leva fino a 50x                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│           │                                    │                         │
│           ▼                                    ▼                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    POSTGRESQL DATABASE                            │   │
│  │  • position_tracking (stato posizioni)                           │   │
│  │  • signal_scores (storico score)                                 │   │
│  │  • trade_journal (storico trade)                                 │   │
│  │  • sentiment_cache (Fear & Greed)                                │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Componenti Principali

### 1. sentinel.py
**Loop continuo ogni 30 secondi** che:
- Monitora posizioni aperte
- Gestisce trailing stop loss
- Apre automaticamente posizioni MICRO_GAIN/MICRO_PAY
- Verifica e corregge ordini SL
- Sveglia l'AI quando necessario

### 2. main.py
**Ciclo AI ogni 10-15 minuti** che:
- Raccoglie dati completi (indicatori, news, whale alerts, forecast)
- Chiama l'AI (OpenRouter/Claude) per decisioni
- Esegue operazioni open/close
- Salva nel trade journal

### 3. hyperliquid_trader.py
Interfaccia con l'exchange Hyperliquid:
- `open_orders()`: Ordini LIMIT attivi (NON vede trigger orders!)
- `frontend_open_orders()`: TUTTI gli ordini inclusi TRIGGER (Stop Loss)
- `execute_signal()`: Esegue operazioni

### 4. signal_scorer.py
Calcola lo score dei segnali:
- RSI: peso 15
- Trend (EMA+MACD): peso 10
- Fear & Greed: peso 8
- Volume: peso 4

### 5. db_utils.py
Gestione database PostgreSQL:
- `get_position_tracking()`: Stato posizione
- `upsert_position_tracking()`: Aggiorna tracking
- `log_signal_score()`: Salva score per analisi
- `check_score_confirmation_db()`: Verifica conferma cicli

---

## Modalità di Trading

### NORMAL Mode (score >= SCORE_THRESHOLD_OPEN)
- Gestito dall'AI in main.py
- Trailing stop a gradini o continuo
- Leva configurabile (default 3x)
- Per segnali forti e affidabili

### MICRO_GAIN Mode (SCORE_THRESHOLD_HOLD <= score < SCORE_THRESHOLD_OPEN)
- Apertura automatica dal sentinel
- Trade veloci con target piccoli (+3% P&L tipico)
- Trailing stop con step bassi
- Leva più alta (4-5x tipico)
- Chiusura su reversal di score

### MICRO_PAY Mode (MICRO_PAY_THRESHOLD <= score < SCORE_THRESHOLD_HOLD)
- Per segnali deboli
- Trade molto piccoli
- TP/SL fissi (no trailing)
- Disabilitato di default

```
Score Range:
    0          5         10        12        17        20+
    |----------|---------|---------|---------|---------|
       HOLD      MICRO_    MICRO_    MICRO_     NORMAL
                  PAY       PAY       GAIN
              (se enabled)
```

---

## Sistema di Score

### Calcolo Score
```python
# Componenti positive (bullish) e negative (bearish)
score_bullish = RSI_contribution + Trend_contribution + Volume_contribution + FG_contribution
score_bearish = RSI_contribution + Trend_contribution + Volume_contribution + FG_contribution

net_score = score_bullish - score_bearish
# Positivo = LONG, Negativo = SHORT
```

### Score Smoothing
```python
SCORE_SMOOTHING_SAMPLES = 3  # Media ultimi 3 cicli
```
Riduce volatilità causata da indicatori binari.

### Score Confirmation (NUOVO)
```python
SCORE_CONFIRMATION_CYCLES = 3  # Cicli consecutivi sopra soglia
```
Prima di aprire, verifica che:
1. Tutti gli ultimi N score siano sopra la soglia
2. Tutti abbiano la stessa direzione (tutti + o tutti -)

---

## Logica Smart Wake AI

### AI_FREE_MODE = true
```
AI gira su schedule (ogni AI_CALL_INTERVAL_MINUTES)
Sentinel sveglia AI SOLO su:
  ✅ Chiusure (SL, TP, trailing)
  ✅ Volatility spike
  ❌ NON per score (AI decide da sola)
```

### AI_FREE_MODE = false (default)
```
Sentinel sveglia AI se:
  ✅ Score >= SCORE_THRESHOLD_OPEN + confermato + no posizione
  ✅ Score in direzione OPPOSTA alla posizione
  ❌ Score sotto soglia
  ❌ Posizione già allineata con score
```

### Funzioni chiave (sentinel.py):
- `should_wake_ai_for_symbol()`: Decide wake per score
- `should_wake_ai_for_event()`: Decide wake per eventi
- `check_and_wake_ai_for_normal()`: Wake proattivo per NORMAL range

---

## Trailing Stop e Stop Loss

### MICRO_GAIN Trailing (Steps Mode)
```
MICRO_GAIN_TRAILING_STEPS = "1:0,2:1,3:2"
# A +1% P&L → SL = 0% (breakeven)
# A +2% P&L → SL = +1%
# A +3% P&L → SL = +2%
```

### NORMAL Trailing (Steps Mode)
```
NORMAL_TRAILING_STEPS = "3:0,5:2,8:5,12:8,15:10"
# A +3% P&L → SL = 0% (breakeven)
# A +5% P&L → SL = +2%
# etc.
```

### Ordini SL su Hyperliquid
- Tipo: **TRIGGER ORDER** (Stop Market)
- **IMPORTANTE**: `open_orders()` NON li vede!
- Usare `frontend_open_orders()` per vedere trigger orders
- Cancellare TUTTI gli ordini prima di piazzarne uno nuovo

---

## Parametri Chiave (.env)

### Score Thresholds
```bash
SCORE_THRESHOLD_HOLD=12          # Soglia minima per MICRO_GAIN
SCORE_THRESHOLD_OPEN=17          # Soglia per NORMAL mode
SCORE_CONFIRMATION_CYCLES=3      # Cicli conferma
SCORE_SMOOTHING_SAMPLES=3        # Campioni per media
```

### MICRO_GAIN
```bash
MICRO_GAIN_ENABLED=true
MICRO_GAIN_AUTO_OPEN=true
MICRO_GAIN_TARGET_PERCENT=3.0    # TP target P&L %
MICRO_GAIN_STOP_LOSS_PERCENT=3.0 # SL iniziale P&L %
MICRO_GAIN_LEVERAGE=4
MICRO_GAIN_PORTION=0.3           # % balance per trade
MICRO_GAIN_COOLDOWN_SECONDS=180  # Attesa dopo chiusura
MICRO_GAIN_MAX_POSITIONS=2       # Max posizioni simultanee
```

### AI Configuration
```bash
AI_FREE_MODE=false               # AI libera di decidere
AI_CALL_INTERVAL_MINUTES=10      # Intervallo tra cicli AI
MIN_HOLD_MINUTES=10              # Tempo minimo prima di chiudere
```

### Trailing Stop
```bash
MICRO_GAIN_TRAILING_MODE=steps   # steps/continuous/disable
NORMAL_TRAILING_MODE=steps
NORMAL_TRAILING_STEPS=3:0,5:2,8:5,12:8,15:10
```

### Features Opzionali
```bash
LEVERAGE_SCALING_ENABLED=true    # Aumenta leva su profitto protetto
AUTO_TP_ENABLED=true             # Piazza TP automatico dopo X min
AUTO_TP_PERCENT=0.4
AUTO_TP_DELAY_MINUTES=15
```

---

## Database e Tracking

### Tabella: position_tracking
```sql
symbol, direction, entry_price, current_price, trailing_active,
trading_mode, opening_score, sl_level, sl_price, opened_at
```

### Tabella: signal_scores
```sql
symbol, net_score, score_bullish, score_bearish, direction,
confidence, signals (JSON), timestamp
```

### Query utili:
```sql
-- Ultimi score per simbolo
SELECT symbol, net_score, timestamp
FROM signal_scores
WHERE symbol = 'BTC'
ORDER BY timestamp DESC LIMIT 10;

-- Volatilità score (std dev)
SELECT symbol, STDDEV(net_score) as volatility
FROM signal_scores
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY symbol;
```

---

## Deploy Docker

### Ricostruzione completa:
```bash
cd /root/trading-bots/rizzo-trading-agent

# Pull codice
git pull origin <branch>

# Ricostruisci immagine
docker build -t rizzo-sentinel:latest .

# Stop e rimuovi vecchio container
docker stop rizzo_sentinel && docker rm rizzo_sentinel

# Avvia nuovo container
docker run -d \
  --name rizzo_sentinel \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  rizzo-sentinel:latest \
  bash /app/entrypoint.sh

# Verifica log
docker logs -f rizzo_sentinel
```

### Solo restart (senza rebuild):
```bash
docker restart rizzo_sentinel
```

---

## Troubleshooting Comune

### Problema: Ordini SL duplicati
**Causa**: `open_orders()` non vede trigger orders
**Soluzione**: Usare `frontend_open_orders()` e cancellare TUTTI gli ordini

### Problema: Aperture su score instabili
**Causa**: Score spike momentanei
**Soluzione**: `SCORE_CONFIRMATION_CYCLES=3` richiede score stabile

### Problema: AI chiamata inutilmente
**Causa**: Wake per ogni ciclo anche senza opportunità
**Soluzione**: Smart wake logic (AI_FREE_MODE e check condizioni)

### Problema: SL non aggiornato
**Causa**: Errore nella cancellazione ordine precedente
**Soluzione**: Delay tra cancellazioni (`time.sleep(0.1)`)

### Problema: Posizione chiusa ma tracking rimane
**Causa**: Chiusura esterna (TP/SL su exchange)
**Soluzione**: `detect_externally_closed_positions()` pulisce tracking

---

## File Principali

| File | Descrizione |
|------|-------------|
| `sentinel.py` | Loop monitoring, trailing, MICRO_GAIN auto |
| `main.py` | Ciclo AI, analisi completa, decisioni |
| `hyperliquid_trader.py` | Interfaccia exchange |
| `signal_scorer.py` | Calcolo score segnali |
| `db_utils.py` | Funzioni database |
| `indicators.py` | Indicatori tecnici |
| `trading_agent.py` | Prompt AI e parsing risposta |
| `trade_journal.py` | Logging trade per analisi |
| `.env` | Configurazione parametri |

---

## Note per Claude

1. **Prima di modificare**: Leggere sempre il file interessato
2. **Test sintassi**: `python3 -m py_compile <file>.py`
3. **Ordini Hyperliquid**: Usare sempre `frontend_open_orders()` per trigger orders
4. **Score history**: In sentinel usa `_score_history`, in main.py usa DB
5. **Commit**: Usare HEREDOC per messaggi multi-linea
6. **Branch**: Sempre pushare sul branch specificato all'inizio sessione

---

*Ultimo aggiornamento: 2025-11-30*
*Autore: Claude + Nicola*
