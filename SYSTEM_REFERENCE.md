# Rizzo Trading Agent - Documentazione Completa di Riferimento

> **IMPORTANTE PER CLAUDE**: Leggi questo documento all'inizio di ogni sessione per comprendere il sistema.

---

## 1. ARCHITETTURA GENERALE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RIZZO TRADING AGENT                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────┐              ┌────────────────────────────────────┐ │
│  │   SENTINEL.PY      │   wake_ai    │            MAIN.PY (AI)            │ │
│  │   (loop 30 sec)    │─────────────▶│         (loop 10-15 min)           │ │
│  │                    │              │                                    │ │
│  │ • Monitor posizioni│              │ • Raccolta dati completa           │ │
│  │ • Trailing SL      │              │ • Chiamata AI (OpenRouter)         │ │
│  │ • MICRO_GAIN auto  │              │ • Decisioni open/close             │ │
│  │ • Score check      │              │ • Trade journal                    │ │
│  │ • SL verification  │              │                                    │ │
│  └────────────────────┘              └────────────────────────────────────┘ │
│           │                                       │                          │
│           ▼                                       ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      HYPERLIQUID EXCHANGE                             │   │
│  │  • Ordini LIMIT/MARKET                                               │   │
│  │  • Ordini TRIGGER (Stop Loss) - ATTENZIONE: open_orders() non li vede│   │
│  │  • Posizioni con leva fino a 50x                                     │   │
│  │  • API: exchange.market_open(), exchange.cancel(), etc.              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                       │                          │
│           ▼                                       ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    POSTGRESQL DATABASE                                │   │
│  │  • position_tracking: stato posizioni con SL level                   │   │
│  │  • signal_scores: storico score per analisi                          │   │
│  │  • trades: trade journal completo                                    │   │
│  │  • sentiment_cache: Fear & Greed Index                               │   │
│  │  • bot_operations: log operazioni AI                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. FILE PRINCIPALI E LORO FUNZIONI

### 2.1 sentinel.py (151 KB - File più grande e critico)

**Scopo**: Loop continuo ogni 30 secondi che monitora e gestisce le posizioni.

#### Funzioni Principali:

| Funzione | Linea | Descrizione |
|----------|-------|-------------|
| `run_loop()` | 3633 | Loop principale del sentinel |
| `run_sentinel_check()` | 3231 | Singolo ciclo di controllo |
| `check_and_open_micro_gain()` | 2945 | Auto-apertura MICRO_GAIN/PAY |
| `check_and_wake_ai_for_normal()` | 3032 | Wake AI per score NORMAL range |
| `calculate_quick_score()` | 805 | Calcola score tecnico rapido |
| `get_smoothed_score()` | 700 | Media mobile degli score |
| `check_score_confirmation()` | 737 | Verifica N cicli sopra soglia |
| `update_micro_gain_sl_order()` | 1516 | Aggiorna trailing SL MICRO_GAIN |
| `update_normal_sl_order()` | 1704 | Aggiorna trailing SL NORMAL |
| `verify_and_fix_sl_order()` | 2163 | Verifica e corregge ordini SL |
| `check_take_profit()` | 3086 | Controlla condizioni TP |
| `check_trailing_stop()` | 3140 | Controlla trailing stop |
| `check_micro_gain_reversal()` | 932 | Controlla inversione score |
| `open_micro_gain_position()` | 993 | Apre posizione MICRO_GAIN |
| `open_micro_pay_position()` | 1204 | Apre posizione MICRO_PAY |
| `place_micro_gain_sl_order()` | 1144 | Piazza SL per MICRO_GAIN |
| `wake_ai_agent()` | 239 | Sveglia main.py in background |
| `should_wake_ai_for_symbol()` | 298 | Decide se svegliare AI per score |
| `should_wake_ai_for_event()` | 376 | Decide se svegliare AI per eventi |
| `detect_externally_closed_positions()` | 1403 | Rileva chiusure esterne |
| `check_leverage_scaling_conditions()` | 2360 | Verifica condizioni per scaling leva |
| `execute_leverage_scaling()` | 2421 | Esegue aumento leva |
| `check_and_place_auto_tp()` | 2717 | Piazza TP automatico |
| `get_step_sl_level()` | 1682 | Calcola livello SL per step |
| `parse_trailing_steps()` | 141 | Parsing "pnl:sl,pnl:sl" string |
| `log()` | 218 | Logging con timestamp |

#### Variabili Globali Importanti:
```python
_trailing_peaks = {}      # symbol -> peak price raggiunto
_current_sl_level = {}    # symbol -> livello SL corrente (%)
_last_close_time = {}     # symbol -> timestamp ultima chiusura (cooldown)
_score_history = {}       # symbol -> lista ultimi N score (smoothing)
_leverage_scaling_cooldown = {}  # symbol -> cicli rimanenti
_auto_tp_orders = {}      # symbol -> order_id TP piazzato
```

---

### 2.2 main.py (48 KB)

**Scopo**: Ciclo AI che analizza mercato e prende decisioni di trading.

#### Funzioni Principali:

| Funzione | Linea | Descrizione |
|----------|-------|-------------|
| `run_analysis_cycle()` | 258 | Singolo ciclo di analisi completa |
| `run_autonomous_loop()` | 931 | Loop autonomo ogni N minuti |
| `main()` | 1004 | Entry point |
| `determine_trading_mode()` | 94 | Determina MICRO_GAIN/NORMAL |
| `should_skip_ai_call()` | 202 | Verifica intervallo minimo |
| `get_symbol_trade_stats()` | 117 | Statistiche trade per simbolo |
| `get_position_context()` | 142 | Contesto posizione per AI |
| `get_overall_performance()` | 176 | Performance ultimi N giorni |

#### Flusso del Ciclo:
1. Recupera indicatori tecnici (`indicators.py`)
2. Recupera news e whale alerts
3. Recupera sentiment e forecast
4. Calcola score per ogni simbolo
5. Chiama AI per decisione
6. Verifica score confirmation (NUOVO)
7. Esegue operazione
8. Salva in trade journal

---

### 2.3 hyperliquid_trader.py (20 KB)

**Scopo**: Interfaccia con exchange Hyperliquid.

#### Classe: `HyperLiquidTrader`

| Metodo | Descrizione |
|--------|-------------|
| `__init__()` | Inizializza connessione exchange |
| `execute_signal()` | Esegue operazione (open/close/adjust) |
| `get_account_status()` | Ritorna balance e posizioni |
| `get_current_leverage()` | Legge leva attuale |
| `set_leverage_for_symbol()` | Imposta leva per simbolo |
| `_round_to_tick()` | Arrotonda prezzo al tick |
| `_get_tick_size()` | Ottiene tick size per simbolo |

#### Metodi Exchange Sottostanti:
```python
# ATTENZIONE: Differenza critica!
self.exchange.open_orders()           # Solo ordini LIMIT - NON vede trigger!
self.exchange.frontend_open_orders()  # TUTTI gli ordini inclusi TRIGGER (SL)

self.exchange.market_open()           # Apre posizione a mercato
self.exchange.market_close()          # Chiude posizione a mercato
self.exchange.order()                 # Piazza ordine limit/trigger
self.exchange.cancel()                # Cancella ordine per oid
```

---

### 2.4 signal_scorer.py (16 KB)

**Scopo**: Calcola score dei segnali tecnici.

#### Funzioni:

| Funzione | Descrizione |
|----------|-------------|
| `calculate_signal_score()` | Calcolo principale score |
| `get_weight()` | Legge peso da env |
| `format_score_for_prompt()` | Formatta per prompt AI |
| `get_scoring_config()` | Ritorna config pesi |

#### Pesi Default:
```python
RSI_WEIGHT = 15        # Overbought/Oversold
TREND_WEIGHT = 10      # EMA + MACD aligned
MACD_WEIGHT = 5        # MACD standalone
FG_WEIGHT = 8          # Fear & Greed
VOLUME_WEIGHT = 4      # Volume imbalance
```

#### Output:
```python
{
    'score_bullish': 18.0,
    'score_bearish': 5.0,
    'net_score': 13.0,        # bullish - bearish
    'direction': 'LONG',       # LONG/SHORT/HOLD
    'confidence': 'NORMAL',    # STRONG/NORMAL/WEAK
    'signals': [...]           # Dettaglio ogni indicatore
}
```

---

### 2.5 db_utils.py (60 KB)

**Scopo**: Tutte le operazioni database PostgreSQL.

#### Funzioni Principali:

| Funzione | Descrizione |
|----------|-------------|
| `get_connection()` | Connessione al DB |
| `init_db()` | Crea tabelle se non esistono |
| **Position Tracking** | |
| `get_position_tracking()` | Legge tracking posizione |
| `upsert_position_tracking()` | Crea/aggiorna tracking |
| `delete_position_tracking()` | Elimina tracking |
| `get_all_position_trackings()` | Lista tutti i tracking |
| **Signal Scores** | |
| `log_signal_score()` | Salva score nel DB |
| `get_recent_scores()` | Ultimi N score per simbolo |
| `check_score_confirmation_db()` | Verifica conferma cicli |
| **Account & Operations** | |
| `log_account_status()` | Snapshot account |
| `log_bot_operation()` | Log operazione AI |
| `get_latest_account_snapshot()` | Ultimo snapshot |
| **Sentiment** | |
| `save_sentiment_cache()` | Salva F&G in cache |
| `get_cached_sentiment()` | Legge F&G da cache |
| `get_sentiment_trend()` | Trend F&G |
| **Sentinel** | |
| `log_sentinel_check()` | Log controllo sentinel |
| `get_sentinel_logs()` | Legge log sentinel |
| `get_sentinel_status()` | Stato corrente |
| **Errors** | |
| `log_error()` | Logga errore |

---

### 2.6 trade_journal.py (36 KB)

**Scopo**: Registrazione dettagliata di tutti i trade.

#### Funzioni Principali:

| Funzione | Descrizione |
|----------|-------------|
| `open_trade()` | Registra apertura trade |
| `close_trade()` | Registra chiusura con P&L |
| `get_open_trade()` | Trade aperto per simbolo |
| `update_trade_peak()` | Aggiorna peak price |
| `log_event()` | Evento generico |
| `log_sl_placed()` | SL piazzato |
| `log_sl_modified()` | SL modificato |
| `log_trailing_activated()` | Trailing attivato |
| `save_snapshot()` | Snapshot periodico |
| `get_trade_summary()` | Riepilogo trade |
| `get_summary_by_mode()` | Riepilogo per mode |
| `get_summary_by_symbol()` | Riepilogo per simbolo |
| `get_fee_analysis()` | Analisi fees |
| `calculate_fees()` | Calcola fees (~0.035% taker) |

---

### 2.7 trading_agent.py (31 KB)

**Scopo**: Gestione chiamate AI e parsing risposte.

#### Funzioni Principali:

| Funzione | Descrizione |
|----------|-------------|
| `previsione_trading_agent()` | Chiamata principale AI |
| `call_ai_api()` | Chiamata HTTP a OpenRouter |
| `extract_json_from_text()` | Estrae JSON da risposta |
| `validate_trading_decision()` | Valida decisione AI |
| `calculate_scores_for_symbols()` | Calcola score per tutti |
| `enhance_prompt_with_scoring()` | Aggiunge score al prompt |
| `check_trailing_stop()` | Check trailing (legacy) |
| `check_close_protection()` | Protezione chiusure |
| `evaluate_position_override()` | Override decisioni AI |

---

### 2.8 indicators.py (19 KB)

**Scopo**: Calcolo indicatori tecnici.

#### Classe: `CryptoTechnicalAnalysisHL`

| Metodo | Descrizione |
|--------|-------------|
| `get_complete_analysis()` | Analisi completa simbolo |
| `calculate_rsi()` | RSI 14 periodi |
| `calculate_macd()` | MACD (12,26,9) |
| `calculate_ema()` | EMA 20 periodi |

#### Funzione:
| Funzione | Descrizione |
|----------|-------------|
| `analyze_multiple_tickers()` | Analizza lista simboli |

---

### 2.9 telegram_notifier.py (8 KB)

**Scopo**: Notifiche Telegram.

#### Funzioni:

| Funzione | Descrizione |
|----------|-------------|
| `send_telegram_message()` | Invia messaggio |
| `notify_trade_open()` | Notifica apertura |
| `notify_trade_close()` | Notifica chiusura |
| `notify_hold()` | Notifica hold |
| `notify_error()` | Notifica errore |
| `notify_bot_started()` | Bot avviato |
| `notify_trading_decision()` | Decisione AI |

---

### 2.10 Altri File

| File | Descrizione |
|------|-------------|
| `forecaster.py` | Previsioni Prophet (ML) |
| `sentiment.py` | API Fear & Greed |
| `news_feed.py` | Feed news crypto |
| `whalealert.py` | Alert whale transactions |
| `ai_context.py` | Costruisce contesto AI arricchito |
| `analytics.py` | Analisi performance |
| `dashboard.py` | Dashboard principale (porta 8501) |
| `dashboard_fresh.py` | Dashboard compatta/fresh (porta 8502) |
| `dashboard_ai_analyzer.py` | AI Prompt Analyzer (porta 8503) |
| `trade_analyzer.py` | Analisi dettagliata trade |
| `weight_optimizer.py` | Ottimizzazione pesi score |
| `strategy_controller.py` | Controllo strategie |
| `backtester.py` | Backtesting strategie |

---

### 2.11 Dashboard Web (Streamlit)

| Dashboard | File | Porta | Descrizione |
|-----------|------|-------|-------------|
| **Principale** | `dashboard.py` | 8501 | Dashboard completa con grafici P&L, analisi performance, confronto trading mode, analisi AI vs Auto |
| **Fresh** | `dashboard_fresh.py` | 8502 | Dashboard compatta con overview rapido, trade journal, posizioni aperte |
| **AI Analyzer** | `dashboard_ai_analyzer.py` | 8503 | Visualizza prompt AI completi, risposte, esporta per analisi esterna |

#### Comandi Docker per avviare le Dashboard

```bash
# Dashboard Principale (porta 8501)
docker run -d \
  --name rizzo_dashboard \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  -p 8501:8501 \
  --restart unless-stopped \
  --entrypoint "" \
  rizzo-sentinel:latest \
  streamlit run /app/dashboard.py --server.port 8501 --server.address 0.0.0.0

# Dashboard Fresh (porta 8502)
docker run -d \
  --name rizzo_dashboard_fresh \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  -p 8502:8502 \
  --restart unless-stopped \
  --entrypoint "" \
  rizzo-sentinel:latest \
  streamlit run /app/dashboard_fresh.py --server.port 8502 --server.address 0.0.0.0

# AI Prompt Analyzer (porta 8503)
docker run -d \
  --name rizzo_ai_analyzer \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  -p 8503:8503 \
  --restart unless-stopped \
  --entrypoint "" \
  rizzo-sentinel:latest \
  streamlit run /app/dashboard_ai_analyzer.py --server.port 8503 --server.address 0.0.0.0
```

**NOTA**: Il flag `--entrypoint ""` è necessario per sovrascrivere l'entrypoint del Dockerfile.

#### Accesso Dashboard
- Dashboard Principale: `http://VPS_IP:8501`
- Dashboard Fresh: `http://VPS_IP:8502`
- AI Prompt Analyzer: `http://VPS_IP:8503`

---

## 3. SCHEMA DATABASE COMPLETO

### 3.1 position_tracking
```sql
CREATE TABLE position_tracking (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    direction VARCHAR(10),           -- 'long' o 'short'
    entry_price DECIMAL(20, 8),
    current_price DECIMAL(20, 8),
    trailing_active BOOLEAN DEFAULT FALSE,
    peak_price DECIMAL(20, 8),
    opening_score DECIMAL(10, 4),
    trading_mode VARCHAR(20),        -- 'MICRO_GAIN', 'MICRO_PAY', 'NORMAL'
    sl_level DECIMAL(10, 4),         -- Livello SL corrente (% P&L)
    sl_price DECIMAL(20, 8),         -- Prezzo SL attuale
    opened_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 3.2 signal_scores
```sql
CREATE TABLE signal_scores (
    id SERIAL PRIMARY KEY,
    context_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    score_bullish DECIMAL(10, 4),
    score_bearish DECIMAL(10, 4),
    net_score DECIMAL(10, 4),
    direction VARCHAR(10),           -- 'LONG', 'SHORT', 'HOLD'
    confidence VARCHAR(20),          -- 'STRONG', 'NORMAL', 'WEAK'
    signals JSONB,                   -- Dettaglio ogni indicatore
    thresholds JSONB,
    weights_config JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);
-- Indici per query veloci
CREATE INDEX idx_signal_scores_symbol ON signal_scores(symbol);
CREATE INDEX idx_signal_scores_created_at ON signal_scores(timestamp);
```

### 3.3 trades (Trade Journal)
```sql
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trade_uuid UUID UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10),           -- 'long', 'short'
    status VARCHAR(20),              -- 'open', 'closed'
    trading_mode VARCHAR(20),        -- 'MICRO_GAIN', 'NORMAL', etc.

    -- Apertura
    entry_price DECIMAL(20, 8),
    entry_size DECIMAL(20, 8),
    entry_notional DECIMAL(20, 8),
    leverage INTEGER,
    open_score DECIMAL(10, 4),
    open_reason TEXT,
    opened_at TIMESTAMP,

    -- Chiusura
    exit_price DECIMAL(20, 8),
    close_reason VARCHAR(50),
    close_score DECIMAL(10, 4),
    closed_at TIMESTAMP,

    -- P&L
    gross_pnl_usd DECIMAL(20, 8),
    fees_usd DECIMAL(20, 8),
    net_pnl_usd DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 4),

    -- Tracking
    peak_price DECIMAL(20, 8),
    peak_pnl_percent DECIMAL(10, 4),
    profitable BOOLEAN
);
```

### 3.4 trade_events
```sql
CREATE TABLE trade_events (
    id SERIAL PRIMARY KEY,
    trade_uuid UUID REFERENCES trades(trade_uuid),
    event_type VARCHAR(50),          -- 'sl_placed', 'sl_modified', 'trailing_activated'
    event_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.5 bot_operations
```sql
CREATE TABLE bot_operations (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(50),           -- 'open', 'close', 'hold', 'adjust'
    symbol VARCHAR(20),
    direction VARCHAR(10),
    reason TEXT,
    context_id INTEGER,
    execution_result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.6 sentiment_cache
```sql
CREATE TABLE sentiment_cache (
    id SERIAL PRIMARY KEY,
    valore INTEGER,                  -- Fear & Greed value (0-100)
    classificazione VARCHAR(50),     -- 'Extreme Fear', 'Fear', etc.
    timestamp_aggiornamento TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.7 account_snapshots
```sql
CREATE TABLE account_snapshots (
    id SERIAL PRIMARY KEY,
    balance_usd DECIMAL(20, 8),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE open_positions (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES account_snapshots(id),
    symbol VARCHAR(20),
    side VARCHAR(10),
    size DECIMAL(20, 8),
    entry_price DECIMAL(20, 8),
    mark_price DECIMAL(20, 8),
    pnl_usd DECIMAL(20, 8),
    leverage VARCHAR(20)
);
```

### 3.8 sentinel_logs
```sql
CREATE TABLE sentinel_logs (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    action VARCHAR(50),              -- 'trailing_update', 'sl_placed', etc.
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 4. MODALITÀ DI TRADING

### 4.1 Range Score
```
Score:  -30    -20    -17    -12    -5     0     5     12     17     20     30
         │      │      │      │     │     │     │      │      │      │      │
         └──────┴──────┴──────┴─────┴─────┴─────┴──────┴──────┴──────┴──────┘
                │             │                        │             │
         STRONG SHORT    MICRO_PAY              MICRO_GAIN    STRONG LONG
                          (disabled)              (12-17)        (NORMAL)
```

### 4.2 MICRO_GAIN Mode
```python
# Configurazione
SCORE_THRESHOLD_HOLD = 12           # Score minimo
SCORE_THRESHOLD_OPEN = 17           # Sopra questo è NORMAL
MICRO_GAIN_TARGET_PERCENT = 3.0     # Target P&L %
MICRO_GAIN_STOP_LOSS_PERCENT = 3.0  # SL iniziale %
MICRO_GAIN_LEVERAGE = 4             # Leva
MICRO_GAIN_PORTION = 0.3            # 30% balance
MICRO_GAIN_TRAILING_STEPS = "1:0,2:1,3:2"  # P&L:SL pairs

# Apertura automatica dal sentinel quando:
# - Score in range [12, 17)
# - Score confermato (N cicli consecutivi)
# - Stessa direzione per tutti i cicli
# - Nessuna posizione esistente
# - Non in cooldown
```

### 4.3 NORMAL Mode
```python
# Configurazione
SCORE_THRESHOLD_OPEN = 17           # Score minimo
NORMAL_STOP_LOSS_PERCENT = 5.0      # SL iniziale
NORMAL_TRAILING_STEPS = "3:0,5:2,8:5,12:8,15:10"

# Gestito dall'AI in main.py
# Trailing più ampio e conservativo
```

### 4.4 Trailing Stop a Gradini
```python
# Esempio: "3:0,5:2,8:5"
# Significa:
# - A P&L +3% → SL = 0% (breakeven)
# - A P&L +5% → SL = +2%
# - A P&L +8% → SL = +5%

# Il SL NON scende mai, solo sale
# get_step_sl_level() calcola il livello appropriato
```

---

## 5. LOGICA SMART WAKE AI

### 5.1 AI_FREE_MODE = true
```python
# AI gira su schedule proprio (ogni AI_CALL_INTERVAL_MINUTES)
# Sentinel sveglia AI SOLO per EVENTI:
#   - Chiusure (SL, TP, trailing)
#   - Volatility spike
# Sentinel NON sveglia per score (AI decide da sola)
```

### 5.2 AI_FREE_MODE = false
```python
# Sentinel sveglia AI quando:
should_wake_ai_for_symbol(symbol, score, positions):
    # 1. Score >= SCORE_THRESHOLD_OPEN + confermato + no posizione → Wake
    # 2. Score opposto alla posizione esistente → Wake
    # 3. Score allineato con posizione → NO wake
    # 4. Score sotto soglia → NO wake
```

### 5.3 Score Confirmation (NUOVA LOGICA - usa MEDIA)

```
                    SCORE CONFIRMATION FLOW
                    ══════════════════════

  Ogni 30 secondi (1 ciclo):
  ┌─────────────────────────────────────────────────────────┐
  │ 1. Calcola score RAW dagli indicatori (RSI, MACD, etc.) │
  │    Esempio: -23                                         │
  │                                                         │
  │ 2. SMOOTHING: media ultimi N raw scores                 │
  │    SCORE_SMOOTHING_SAMPLES=3                            │
  │    Esempio: media(-20, -8, -23) = -17.0                 │
  │    Scopo: riduce volatilità singolo score               │
  │                                                         │
  │ 3. Salva score "smooth" nella history                   │
  └─────────────────────────────────────────────────────────┘
                           │
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │ 4. CONFIRMATION: controlla se aprire trade              │
  │    SCORE_CONFIRMATION_CYCLES=3                          │
  │                                                         │
  │    Prende ultimi 3 smooth scores: [-20, -17, -15]       │
  │    Calcola MEDIA: (-20 + -17 + -15) / 3 = -17.3         │
  │                                                         │
  │    Verifica:                                            │
  │    ✓ Media nel range MICRO_GAIN (13-18)? → -17.3 ✅     │
  │    ✓ Almeno 2/3 stessa direzione? → 3/3 short ✅        │
  │                                                         │
  │    → CONFERMATO! Apre posizione SHORT                   │
  └─────────────────────────────────────────────────────────┘

  ESEMPIO PRATICO:
  ┌────────┬───────────┬─────────────────┬──────────────────┐
  │ Ciclo  │ Score RAW │ Smooth (media 3)│ Confirmation     │
  ├────────┼───────────┼─────────────────┼──────────────────┤
  │   1    │   -20     │  -20            │ Need 3, have 1   │
  │   2    │   -8      │  -14            │ Need 3, have 2   │
  │   3    │   -25     │  -17.7          │ Avg=-17.2 ✅ APRI│
  └────────┴───────────┴─────────────────┴──────────────────┘
```

```python
# VECCHIA LOGICA (troppo rigida):
# ALL individual scores must be in range
# [-7, -23, -15] → ❌ blocked (il -7 è fuori range 13-18)

# NUOVA LOGICA (usa media):
# AVERAGE of scores must be in range + 2/3 same direction
# [-7, -23, -15] → avg=-15.0 ✅ nel range + tutti negativi ✅
```

### 5.4 Sentinel Score Passing (NUOVO)

```
               SENTINEL → AI COMMUNICATION FLOW
               ════════════════════════════════

  ┌─────────────────────────────────────────────────────────────┐
  │ SENTINEL calcola score (ogni 30 sec)                        │
  │                                                             │
  │ Se score >= SCORE_THRESHOLD_OPEN:                           │
  │   wake_ai_agent(symbol, "score_signal", sentinel_score=22)  │
  │                                                             │
  │ Lancia: python main.py --ticker BTC --priority high         │
  │                        --sentinel-score 22.0                │
  └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ MAIN.PY riceve lo score dalla sentinel                      │
  │                                                             │
  │ • NON ricalcola lo score (evita discrepanze)               │
  │ • Usa sentinel_score per le decisioni                       │
  │ • Aggiunge contesto extra al prompt AI:                     │
  │                                                             │
  │   "SENTINEL TRIGGER - ADDITIONAL CONTEXT                    │
  │    Sentinel Score: 22.0                                     │
  │    Suggested Direction: LONG                                │
  │    The sentinel score is informational only.                │
  │    You have full autonomy to decide."                       │
  └─────────────────────────────────────────────────────────────┘

  DIFFERENZA TRA CHIAMATE:
  ┌────────────────────┬────────────────────┬────────────────────┐
  │                    │ SENTINEL TRIGGER   │ LOOP AUTOMATICO    │
  ├────────────────────┼────────────────────┼────────────────────┤
  │ Score              │ Passato da sentinel│ Ricalcolato        │
  │ Prompt             │ + context sentinel │ Standard           │
  │ priority           │ high               │ normal             │
  │ Interval check     │ Skipped            │ Applied            │
  └────────────────────┴────────────────────┴────────────────────┘
```

### 5.5 DOUBLE_CHECK_AI (Preparato, disabilitato)

```python
# DOUBLE_CHECK_AI_ENABLED=false (default)
#
# Quando abilitato:
# - Le aperture automatiche MICRO_GAIN passano attraverso AI
# - L'AI può validare o bloccare l'apertura
#
# ATTENZIONE: Attivare SOLO dopo aver verificato che l'AI non sia
# troppo conservativa, altrimenti bloccherà tutti i trade.
#
# Flusso con DOUBLE_CHECK=true:
# 1. Sentinel rileva score in range MICRO_GAIN
# 2. Invece di aprire automaticamente, chiama AI
# 3. AI valuta e decide se aprire o HOLD
```

### 5.6 SMART EXIT Warning System

```
              SMART EXIT - SISTEMA DI WARNING INTELLIGENTI
              ═════════════════════════════════════════════

  SCOPO:
  Fornire all'AI warning strutturati quando le condizioni di mercato
  suggeriscono di valutare la chiusura di una posizione aperta.

  MODALITÀ DISPONIBILI:
  ┌────────────────┬─────────────────────────────────────────────────┐
  │ WARN-ONLY      │ I warning vengono solo passati all'AI           │
  │ (SMART_EXIT_   │ L'AI decide liberamente se chiudere o holdare   │
  │  MODE=warn)    │ Nessuna chiusura automatica                     │
  │                │ Nessun tracking tra cicli                       │
  ├────────────────┼─────────────────────────────────────────────────┤
  │ HYBRID         │ Warning passati all'AI + tracking persistente   │
  │ (SMART_EXIT_   │ Se stesso warning confermato N cicli consecutivi│
  │  MODE=hybrid)  │ → warning marcato come "CONFIRMED" nel prompt   │
  │                │ L'AI riceve info extra sulla persistenza        │
  │                │ MA sempre l'AI decide (no chiusure automatiche) │
  └────────────────┴─────────────────────────────────────────────────┘

  COME FUNZIONA HYBRID MODE:
  ┌────────────────────────────────────────────────────────────────────┐
  │ Ciclo 1: EMA_INVALIDATION rilevato → warning_counts[BTC] = 1      │
  │ Ciclo 2: EMA_INVALIDATION ancora → warning_counts[BTC] = 2        │
  │ Ciclo 3: EMA_INVALIDATION ancora → CONFIRMED! (>= CONFIRM_CYCLES) │
  │                                                                    │
  │ Se warning NON si verifica in un ciclo → counter resettato a 0    │
  │ Se posizione chiusa → tutti i counter per quel simbolo resettati  │
  └────────────────────────────────────────────────────────────────────┘

  REGOLE IMPLEMENTATE:
  ┌─────────────────────┬───────────────────────────────────────────┐
  │ EMA_INVALIDATION    │ Prezzo ha attraversato EMA20 contro       │
  │                     │ direzione posizione                       │
  │                     │ LONG: price < EMA20                       │
  │                     │ SHORT: price > EMA20                      │
  ├─────────────────────┼───────────────────────────────────────────┤
  │ SCORE_DECAY         │ Lo score si è indebolito o invertito:     │
  │                     │ - Score cambiato segno                    │
  │                     │ - Score decaduto >50% da apertura         │
  ├─────────────────────┼───────────────────────────────────────────┤
  │ TIME_STOP           │ Posizione aperta troppo a lungo con       │
  │                     │ profitto minimo (<1% P&L)                 │
  │                     │ Default: 60 minuti                        │
  └─────────────────────┴───────────────────────────────────────────┘

  SEVERITY LEVELS:
  - warning (🟡): Condizione potenzialmente problematica
  - critical (🔴): Condizione seria, considerare azione
  - CONFIRMED (⚠️): Warning persistente per N cicli consecutivi

  ESEMPIO PROMPT AI CON WARNING (HYBRID MODE):
  ┌──────────────────────────────────────────────────────────────┐
  │ ## ⚠️ SMART EXIT WARNINGS                                    │
  │                                                              │
  │ 🔴 **EMA_INVALIDATION** [CONFIRMED - 3 cycles]: LONG         │
  │    position: Price $95,123 is 0.42% BELOW EMA20 ($95,523)    │
  │                                                              │
  │ 🟡 **SCORE_DECAY**: LONG: Score decayed 65% from opening     │
  │    (18.0 → 6.3)                                              │
  │                                                              │
  │ ### Your task:                                               │
  │ Evaluate these warnings alongside other factors and          │
  │ decide whether to CLOSE or HOLD. CONFIRMED warnings have     │
  │ persisted across multiple cycles - consider them seriously.  │
  └──────────────────────────────────────────────────────────────┘
```

```python
# CONFIGURAZIONE ENV:
SMART_EXIT_ENABLED=true           # Abilita sistema (default: true)
SMART_EXIT_MODE=hybrid            # 'warn' o 'hybrid' (default: warn)
SMART_EXIT_EMA_CHECK=true         # Check EMA invalidation
SMART_EXIT_SCORE_DECAY_CHECK=true # Check score decay
SMART_EXIT_TIME_STOP_MINUTES=60   # Time stop (0 = disabilitato)
SMART_EXIT_CONFIRM_CYCLES=2       # Cicli per conferma in hybrid mode

# FUNZIONI PRINCIPALI (main.py):
# generate_smart_exit_warnings(symbol, ...) → Lista di warning
# clear_smart_exit_warnings(symbol)         → Reset al close
# get_smart_exit_warnings(symbol)           → Lista warning attivi

# STORAGE (in memoria, non persistente):
# _smart_exit_warning_counts[symbol][warning_type] = count
```

### 5.7 Data Collection per Backtesting (Trade Journal V2)

```
              NUOVI CAMPI TRADE JOURNAL
              ═════════════════════════

  Campi aggiunti per analisi Smart Exit e backtesting:

  ALL'APERTURA (per correlazione con successo trade):
  ┌──────────────────────┬────────────────────────────────────────┐
  │ open_price_vs_ema20  │ % distanza prezzo da EMA20             │
  │ open_ema_alignment   │ "bullish", "bearish", "neutral"        │
  │ open_trend_direction │ "UP", "DOWN", "SIDEWAYS"               │
  │ open_atr             │ Average True Range al momento apertura │
  └──────────────────────┴────────────────────────────────────────┘

  ALLA CHIUSURA (per analisi exit):
  ┌──────────────────────┬────────────────────────────────────────┐
  │ close_price_vs_ema20 │ % distanza prezzo da EMA20             │
  │ exit_warnings        │ JSON array dei warning attivi          │
  │ cycles_open          │ Numero cicli posizione aperta          │
  └──────────────────────┴────────────────────────────────────────┘

  MIGRAZIONE:
  La migrazione è automatica al primo avvio dopo l'update.
  Eseguire manualmente: python trade_journal.py
```

---

## 6. ORDINI SU HYPERLIQUID

### 6.1 Tipi di Ordine
```python
# LIMIT - Ordine con prezzo specifico
# MARKET - Esegue subito a mercato
# TRIGGER (Stop Market) - Si attiva quando prezzo raggiunge trigger

# CRITICO: Differenza tra API
exchange.open_orders()           # Vede SOLO ordini LIMIT
exchange.frontend_open_orders()  # Vede TUTTI inclusi TRIGGER
```

### 6.2 Cancellazione Ordini SL
```python
# SEMPRE usare frontend_open_orders per vedere SL
open_orders = bot.exchange.frontend_open_orders(bot.address)

# Cancellare TUTTI gli ordini per il simbolo prima di piazzarne uno nuovo
expected_side = "B" if direction == "short" else "A"  # Buy per chiudere short
for order in open_orders:
    if order.get("coin") == symbol and order.get("side") == expected_side:
        bot.exchange.cancel(symbol, order.get("oid"))
        time.sleep(0.1)  # Delay tra cancellazioni
```

---

## 7. PARAMETRI .env COMPLETI

> Ogni parametro è spiegato con significato, valore default e range consigliato.

### 7.1 API Keys e Connessioni
```bash
OPENROUTER_API_KEY=sk-xxx            # Chiave API OpenRouter per AI
OPENROUTER_MODEL=deepseek/deepseek-r1  # Modello AI da usare
DATABASE_URL=postgresql://user:pass@host:5432/db  # Connessione PostgreSQL
PRIVATE_KEY=xxx                       # Chiave privata Hyperliquid
WALLET_ADDRESS=0x...                  # Indirizzo wallet Hyperliquid
```

### 7.2 Bot Settings Generali
```bash
TESTNET=false                         # true=testnet, false=mainnet (SOLDI VERI!)
VERBOSE=true                          # Log dettagliati
AI_PROVIDER=openrouter                # Provider AI

# TESTING_MODE (default: false)
# Quando true, l'AI NON usa le metriche storiche di performance.
# Utile durante test per evitare che risultati negativi influenzino decisioni.
TESTING_MODE=false

# AI_FREE_MODE (default: false)
# Quando true, l'AI viene SEMPRE chiamata indipendentemente dallo score.
# Lo score è solo un suggerimento, non un filtro.
AI_FREE_MODE=false

# MAX_POSITIONS_PER_SYMBOL (default: 1)
# Numero massimo posizioni per singolo simbolo.
# 1 = una posizione per moneta, 2 = permette pyramiding
MAX_POSITIONS_PER_SYMBOL=1
```

### 7.3 Timeouts
```bash
BOT_TIMEOUT_SECONDS=300               # Timeout totale ciclo bot
DB_CONNECT_TIMEOUT=30                 # Timeout connessione DB
DB_QUERY_TIMEOUT=60000                # Timeout query DB (ms)
```

### 7.4 Telegram
```bash
TELEGRAM_ENABLED=true                 # Abilita notifiche Telegram
TELEGRAM_BOT_TOKEN=xxx                # Token bot Telegram
TELEGRAM_CHAT_ID=xxx                  # Chat ID destinazione
TELEGRAM_NOTIFY_HOLDS=false           # Notifica anche HOLD (rumoroso)
SENTINEL_TELEGRAM_NOTIFY=true         # Notifiche da sentinel
```

### 7.5 Signal Scoring Weights (Pesi Segnali)
> Ogni peso va da 0 a 20. Valore più alto = maggiore importanza. 0 = disabilitato.

#### Segnali BEARISH (favoriscono SHORT)
```bash
# Fear & Greed < 30 (mercato in paura)
# Logica: Paura = possibile continuazione ribasso
WEIGHT_FEAR_GREED_FEAR=8              # Range: 5-12

# RSI > 70 (ipercomprato)
# Logica: RSI alto = probabile correzione al ribasso
WEIGHT_RSI_OVERBOUGHT=15              # Range: 10-20 (molto affidabile)

# Prezzo < EMA20 E MACD < 0 (trend ribassista confermato)
# Logica: Due indicatori concordi = segnale forte
WEIGHT_TREND_BEARISH=10               # Range: 8-15

# Prophet prevede ribasso > 0.3%
WEIGHT_FORECAST_NEGATIVE=6            # Range: 4-10

# MACD < 0 (momentum negativo, senza conferma EMA)
WEIGHT_MACD_NEGATIVE=5                # Range: 3-8

# Volume Ask > Volume Bid * 1.5 (venditori dominano)
WEIGHT_VOLUME_BEARISH=4               # Range: 2-8
```

#### Segnali BULLISH (favoriscono LONG)
```bash
# Fear & Greed > 60 (mercato euforico)
# ATTENZIONE: Extreme Greed (>80) potrebbe indicare top
WEIGHT_FEAR_GREED_GREED=8             # Range: 5-12

# RSI < 30 (ipervenduto)
# Logica: RSI basso = probabile rimbalzo
WEIGHT_RSI_OVERSOLD=15                # Range: 10-20 (molto affidabile)

# Prezzo > EMA20 E MACD > 0 (trend rialzista confermato)
WEIGHT_TREND_BULLISH=10               # Range: 8-15

# Prophet prevede rialzo > 0.3%
WEIGHT_FORECAST_POSITIVE=6            # Range: 4-10

# MACD > 0 (momentum positivo)
WEIGHT_MACD_POSITIVE=5                # Range: 3-8

# Volume Bid > Volume Ask * 1.5 (compratori dominano)
WEIGHT_VOLUME_BULLISH=4               # Range: 2-8
```

### 7.6 Soglie Decisionali
```bash
# SCORE_THRESHOLD_OPEN: Score minimo per aprire posizione NORMAL
# Net Score > +15 = LONG, < -15 = SHORT, |score| < 15 = HOLD
SCORE_THRESHOLD_OPEN=15               # Range: 10-20

# SCORE_THRESHOLD_STRONG: Score per segnale forte (più leva/size)
SCORE_THRESHOLD_STRONG=25             # Range: 20-35

# SCORE_THRESHOLD_HOLD: Sotto questo il segnale è troppo debole
# Usato come soglia minima per MICRO_GAIN
SCORE_THRESHOLD_HOLD=10               # Range: 5-15

# ═══════════════════════════════════════════════════════════════
# SCORE CONFIRMATION E SMOOTHING (vedi sezione 5.3 per dettagli)
# ═══════════════════════════════════════════════════════════════

# SCORE_SMOOTHING_SAMPLES: Campioni per media mobile score RAW
# Ogni ciclo (30s) calcola la media degli ultimi N score raw
# Scopo: ridurre volatilità dello score singolo
# Più alto = score più stabile ma meno reattivo
SCORE_SMOOTHING_SAMPLES=3             # Range: 2-7
# Esempio: 3 = media 90 secondi di dati raw

# SCORE_CONFIRMATION_CYCLES: Cicli per confermare apertura trade
# Prima di aprire, calcola la MEDIA degli ultimi N score smooth
# Se media è nel range target + 2/3 stessa direzione → apri
# Più alto = trend più confermato ma più lento ad aprire
SCORE_CONFIRMATION_CYCLES=3           # Range: 2-10
# Esempio: 3 cicli × 30 sec = 1.5 minuti di conferma

# COMBINAZIONE CONSIGLIATA:
# Reattivo:    SMOOTHING=3, CONFIRMATION=3 (1.5 min)
# Bilanciato:  SMOOTHING=5, CONFIRMATION=5 (2.5 min)
# Conservativo: SMOOTHING=5, CONFIRMATION=10 (5 min)
```

### 7.7 Soglie Indicatori
```bash
RSI_OVERBOUGHT_THRESHOLD=70           # RSI sopra = ipercomprato (Range: 65-80)
RSI_OVERSOLD_THRESHOLD=30             # RSI sotto = ipervenduto (Range: 20-35)
FEAR_GREED_FEAR_THRESHOLD=30          # F&G sotto = paura (Range: 25-40)
FEAR_GREED_GREED_THRESHOLD=60         # F&G sopra = avidità (Range: 55-70)
FORECAST_MIN_CHANGE_PCT=0.3           # Minimo cambio % per forecast (Range: 0.2-0.5)
```

### 7.8 Anti-Overtrading
```bash
# Minimo movimento % atteso per aprire posizione
MIN_PRICE_CHANGE_PCT=0.3              # Range: 0.2-0.5

# Minuti minimi tra trade sullo stesso simbolo
MIN_MINUTES_BETWEEN_TRADES=30         # Range: 15-60

# MIN_HOLD_MINUTES: Tempo minimo prima che AI possa chiudere posizione
# Evita chiusure premature appena aperto
MIN_HOLD_MINUTES=10                   # Range: 5-30
```

### 7.9 Risk Management
```bash
# Percentuale massima portafoglio per singola operazione (PRIMA della leva)
MAX_POSITION_SIZE_PCT=50              # Range: 25-75

# Leva MASSIMA consentita (override su qualsiasi decisione)
MAX_LEVERAGE=10                       # Range: 5-20
```

### 7.10 Trailing Stop Legacy (usato da main.py)
```bash
TRAILING_STOP_ENABLED=true            # Abilita trailing stop
TRAILING_STOP_PERCENT=7               # % discesa da max per chiudere (Range: 5-10)
TRAILING_STOP_ACTIVATION_PERCENT=3    # Profitto % per attivare trailing (Range: 2-5)
INITIAL_STOP_LOSS_PERCENT=10          # SL fisso prima di trailing (Range: 5-15)
```

### 7.11 Protezione Chiusure
```bash
# Score minimo direzione opposta per chiudere posizione
# Es: LONG con score < -10 = chiudi
SCORE_THRESHOLD_CLOSE_REVERSAL=10     # Range: 8-15
```

### 7.12 Sentinel
```bash
SENTINEL_ENABLED=true                 # Abilita sentinel
SENTINEL_INTERVAL_SECONDS=60          # Intervallo controllo (Range: 30-120)
SENTINEL_TELEGRAM_NOTIFY=true         # Notifiche Telegram

# Sveglia AI su tutte le chiusure (non solo TP)
SENTINEL_WAKE_ON_ALL_CLOSES=true

# Verifica SL passiva
SENTINEL_SL_VERIFICATION=true
SENTINEL_SL_VERIFICATION_INTERVAL=300 # Ogni 5 minuti
```

### 7.13 Take Profit
```bash
TAKE_PROFIT_ENABLED=true              # Abilita TP automatico
TAKE_PROFIT_PERCENT=5                 # Target % P&L (Range: 3-10)
TAKE_PROFIT_TRIGGER_BOT=true          # Dopo TP, lancia bot per rivalutare
```

### 7.14 MICRO_GAIN Mode
```bash
MICRO_GAIN_ENABLED=true               # Abilita modalità
MICRO_GAIN_AUTO_OPEN=true             # Sentinel apre automaticamente

# Target e Stop Loss (% P&L con leva)
MICRO_GAIN_TARGET_PERCENT=3.0         # Range: 0.15-5.0
MICRO_GAIN_STOP_LOSS_PERCENT=3.0      # Range: 1.0-5.0

MICRO_GAIN_LEVERAGE=4                 # Leva (Range: 3-10)
MICRO_GAIN_PORTION=0.3                # % balance per trade (Range: 0.2-0.5)
MICRO_GAIN_COOLDOWN_SECONDS=180       # Attesa dopo chiusura (Range: 60-300)
MICRO_GAIN_MAX_POSITIONS=2            # Max posizioni simultanee (Range: 1-3)

# Trailing Mode: "steps", "continuous", "disable"
MICRO_GAIN_TRAILING_MODE=steps
# Formato: "pnl:sl,pnl:sl" - A P&L X%, metti SL a Y%
MICRO_GAIN_TRAILING_STEPS=1:0,2:1,3:2

# Score per inversione (chiudi se score inverte oltre questo)
MICRO_GAIN_REVERSAL_SCORE=15          # Range: 5-20

# Piazza limit order TP su Hyperliquid
MICRO_GAIN_USE_LIMIT_ORDER=true

# DOUBLE_CHECK_AI: Se true, MICRO_GAIN passa attraverso AI per validazione
# ATTENZIONE: Attivare solo dopo aver verificato che AI non sia troppo conservativa
DOUBLE_CHECK_AI_ENABLED=false         # Default: false
```

### 7.15 NORMAL Mode Trailing (gestito da Sentinel)
```bash
NORMAL_TRAILING_ENABLED=true          # Abilita trailing per NORMAL
NORMAL_STOP_LOSS_PERCENT=5.0          # SL iniziale % P&L (Range: 3-8)
NORMAL_TRAILING_ACTIVATION=2.0        # Attiva trailing a +X% P&L (Range: 1-5)
NORMAL_TRAILING_GAP=1.5               # Gap tra P&L e SL (Range: 1-3)

# Trailing Mode: "steps", "continuous", "disable"
NORMAL_TRAILING_MODE=steps
NORMAL_TRAILING_STEPS=3:0,5:2,8:5,12:8,15:10
```

### 7.16 MICRO_PAY Mode (per segnali molto deboli)
```bash
MICRO_PAY_ENABLED=false               # Disabilitato di default
MICRO_PAY_THRESHOLD=5                 # Score minimo (Range: 3-8)
MICRO_PAY_TARGET_PERCENT=1.2          # Target % P&L (Range: 0.8-2.0)
MICRO_PAY_STOP_LOSS_PERCENT=1.2       # SL % P&L (Range: 1.0-2.0)
MICRO_PAY_LEVERAGE=3                  # Leva (Range: 2-5)
MICRO_PAY_PORTION=0.15                # % balance (Range: 0.10-0.25)
MICRO_PAY_COOLDOWN_SECONDS=120        # Cooldown (Range: 60-300)
MICRO_PAY_TRAILING_MODE=disable       # Nessun trailing per MICRO_PAY
```

### 7.17 AI Timing
```bash
# Intervallo minimo tra chiamate AI per stesso simbolo
AI_CALL_INTERVAL_MINUTES=15           # Range: 10-30

# Timeout singola chiamata AI
AI_DECISION_TIMEOUT_SECONDS=60        # Range: 30-120

# Tentativi se chiamata AI fallisce
AI_MAX_RETRIES=2                      # Range: 1-3

# Attesa tra tentativi
AI_RETRY_DELAY_SECONDS=5              # Range: 3-10
```

### 7.18 Leverage Scaling (aumenta leva su profitto protetto)
```bash
LEVERAGE_SCALING_ENABLED=true         # Abilita scaling
LEVERAGE_SCALING_MIN_PROTECTED_PROFIT=0.5  # SL deve proteggere almeno X%
LEVERAGE_SCALING_STEP=2               # Aumento leva per scaling (+2x)
LEVERAGE_SCALING_MAX=15               # Leva massima raggiungibile
LEVERAGE_SCALING_COOLDOWN_CYCLES=2    # Cicli attesa tra scaling
```

### 7.19 Auto Take Profit (piazza TP automatico dopo X minuti)
```bash
AUTO_TP_ENABLED=true                  # Abilita auto TP
AUTO_TP_PERCENT=0.4                   # Target % P&L
AUTO_TP_DELAY_MINUTES=15              # Piazza TP dopo X minuti dall'apertura
```

### 7.20 Smart Exit Warning System (NUOVO)
```bash
# ═══════════════════════════════════════════════════════════════
# SMART EXIT - Sistema di warning intelligenti per chiusura posizioni
# ═══════════════════════════════════════════════════════════════

# SMART_EXIT_ENABLED: Abilita/disabilita l'intero sistema
# Quando true, genera warning per posizioni aperte e li passa all'AI
# L'AI rimane LIBERA di decidere se chiudere o holdare
SMART_EXIT_ENABLED=true               # Default: true

# SMART_EXIT_MODE: Modalità operativa del sistema
# - 'warn': Solo warning passati all'AI (CONSIGLIATO inizialmente)
#           L'AI vede i warning ma decide liberamente
# - 'hybrid': Warning + tracking cicli consecutivi
#             Se stesso warning ripetuto N volte → marcato [CONFIRMED]
#             Ancora l'AI decide, ma ha info sulla persistenza del segnale
SMART_EXIT_MODE=warn                  # Default: warn

# ═══════════════════════════════════════════════════════════════
# REGOLE INDIVIDUALI (puoi abilitare/disabilitare singolarmente)
# ═══════════════════════════════════════════════════════════════

# SMART_EXIT_EMA_CHECK: Controlla invalidazione EMA20
# LONG: warning se prezzo < EMA20 (trend invalidato)
# SHORT: warning se prezzo > EMA20 (trend invalidato)
# Severity: warning se <1%, critical se >1% distanza
SMART_EXIT_EMA_CHECK=true             # Default: true

# SMART_EXIT_SCORE_DECAY_CHECK: Controlla indebolimento score
# Warning se:
# - Score cambia segno rispetto alla posizione (LONG ma score negativo)
# - Score decade >50% rispetto all'apertura
# Severity: warning normale, critical se score opposto >10
SMART_EXIT_SCORE_DECAY_CHECK=true     # Default: true

# SMART_EXIT_TIME_STOP_MINUTES: Time stop in minuti
# Warning se posizione aperta > X minuti con P&L < 1%
# Logica: se dopo tanto tempo non hai profitto, forse è meglio uscire
# 0 = disabilitato
# Severity: warning fino a 2x tempo, poi critical
SMART_EXIT_TIME_STOP_MINUTES=60       # Default: 60 (0 = disabilitato)

# ═══════════════════════════════════════════════════════════════
# HYBRID MODE SETTINGS (solo se SMART_EXIT_MODE=hybrid)
# ═══════════════════════════════════════════════════════════════

# SMART_EXIT_CONFIRM_CYCLES: Cicli consecutivi per conferma
# Quando un warning si ripete per N cicli consecutivi:
# - Viene marcato come [CONFIRMED] nel prompt
# - L'AI riceve info aggiuntiva sulla persistenza del segnale
# Esempio: EMA_INVALIDATION per 3 cicli = segnale più affidabile
SMART_EXIT_CONFIRM_CYCLES=2           # Default: 2

# ═══════════════════════════════════════════════════════════════
# ESEMPI CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════════

# CONSERVATIVA (default - per iniziare):
# SMART_EXIT_ENABLED=true
# SMART_EXIT_MODE=warn
# SMART_EXIT_TIME_STOP_MINUTES=60

# MODERATA (dopo 1-2 settimane di dati):
# SMART_EXIT_MODE=hybrid
# SMART_EXIT_CONFIRM_CYCLES=2
# SMART_EXIT_TIME_STOP_MINUTES=45

# AGGRESSIVA (dopo validazione backtesting):
# SMART_EXIT_MODE=hybrid
# SMART_EXIT_CONFIRM_CYCLES=1
# SMART_EXIT_TIME_STOP_MINUTES=30

# SOLO EMA (disabilita altre regole):
# SMART_EXIT_SCORE_DECAY_CHECK=false
# SMART_EXIT_TIME_STOP_MINUTES=0
```

---

## 8. DEPLOY E COMANDI DOCKER

### 8.1 Struttura Container
```
Container: rizzo_sentinel
Network: unified-memory-stack_memory-net
Env file: /root/trading-bots/rizzo-trading-agent/.env
Entrypoint: bash /app/entrypoint.sh

entrypoint.sh esegue:
1. main.py in loop (AI ogni 10-15 min)
2. sentinel.py in loop (monitoring ogni 30s)
```

### 8.2 Comandi Docker (COPIA-INCOLLA)

#### Stop e Rimuovi Container
```bash
docker stop rizzo_sentinel && docker rm rizzo_sentinel
```

#### Avvia Container
```bash
docker run -d \
  --name rizzo_sentinel \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  rizzo-sentinel:latest \
  bash /app/entrypoint.sh
```

#### Visualizza Log
```bash
docker logs -f rizzo_sentinel
```

#### Ricostruzione Completa (dopo modifiche codice)
```bash
cd /root/trading-bots/rizzo-trading-agent
git pull origin <branch>
docker build -t rizzo-sentinel:latest .
docker stop rizzo_sentinel && docker rm rizzo_sentinel
docker run -d \
  --name rizzo_sentinel \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  --network unified-memory-stack_memory-net \
  --restart unless-stopped \
  rizzo-sentinel:latest \
  bash /app/entrypoint.sh
docker logs -f rizzo_sentinel
```

### 8.3 Accesso Database
```bash
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading
```

---

## 9. TROUBLESHOOTING

### 9.1 Ordini SL Duplicati
**Problema**: Multipli ordini SL per stesso simbolo
**Causa**: `open_orders()` non vede trigger orders
**Soluzione**: Usare `frontend_open_orders()` e cancellare TUTTI prima di piazzare nuovo

### 9.2 Aperture su Score Instabili
**Problema**: Apre su spike momentanei
**Causa**: Score non confermato
**Soluzione**: `SCORE_CONFIRMATION_CYCLES=3`

### 9.3 AI Chiamata Inutilmente
**Problema**: AI svegliata quando non serve
**Causa**: Wake senza verificare condizioni
**Soluzione**: Smart wake logic implementata

### 9.4 Posizione Chiusa ma Tracking Rimane
**Problema**: Tracking orfano nel DB
**Causa**: Chiusura esterna (TP/SL su exchange)
**Soluzione**: `detect_externally_closed_positions()` pulisce

### 9.5 SL Non Aggiornato
**Problema**: Trailing non funziona
**Causa**: Errore cancellazione ordine precedente
**Soluzione**: Delay tra cancellazioni, retry logic

---

## 10. NOTE PER CLAUDE

### 10.1 Prima di Modificare
- Leggere SEMPRE il file con Read tool
- Verificare sintassi: `python3 -m py_compile file.py`
- Testare logica prima di committare

### 10.2 Ordini Hyperliquid
- SEMPRE usare `frontend_open_orders()` per trigger orders
- SEMPRE cancellare TUTTI gli ordini prima di piazzarne uno nuovo
- Aggiungere delay tra cancellazioni

### 10.3 Score History
- In sentinel.py: usa `_score_history` (in-memory)
- In main.py: usa `db_utils.check_score_confirmation_db()` (database)

### 10.4 Commit
- Usare HEREDOC per messaggi multi-linea
- Branch: quello specificato a inizio sessione

### 10.5 Variabili Critiche
```python
# Direzioni
direction = "long" | "short"
side (Hyperliquid) = "A" (sell/ask) | "B" (buy/bid)

# Per chiudere LONG → vendi → side "A"
# Per chiudere SHORT → compra → side "B"
# Per SL su LONG → trigger sell → side "A"
# Per SL su SHORT → trigger buy → side "B"
```

---

*Ultimo aggiornamento: 2025-12-02*
*Versione: 2.1 - Smart Exit + Prompt Libero + Data Collection*
