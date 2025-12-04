# Database Summary - Trading Bot Analysis
**Data Analisi:** 2025-12-04
**Branch:** `claude/fix-trading-risk-reward-017YvTjwd7Mvj1tPbx1JP2j2`

---

## 📊 Schema Database

### Panoramica Tabelle

| Tabella | Righe | Descrizione |
|---------|-------|-------------|
| `sentinel_logs` | 44,035 | Log del sentinel (monitoraggio continuo) |
| `forecasts_contexts` | 28,824 | Previsioni Prophet per ogni decisione |
| `indicators_contexts` | 9,492 | Indicatori tecnici per ogni decisione |
| `sentiment_contexts` | 4,809 | Fear & Greed Index |
| `bot_operations` | 4,809 | Decisioni AI (open/close/hold) |
| `ai_contexts` | 4,809 | System prompt usato per ogni decisione |
| `news_contexts` | 4,667 | News aggregate |
| `signal_scores` | 4,483 | Score calcolati dal signal_scorer |
| `account_snapshots` | 3,805 | Snapshot balance account |
| `errors` | 3,523 | Log errori |
| `open_positions` | 2,154 | Snapshot posizioni aperte |
| `trade_events` | 1,893 | Eventi durante la vita di un trade |
| `sentiment_cache` | 957 | Cache sentiment |
| `trades` | 286 | **Trade completi con P&L** |
| `ai_prompt_logs` | 79 | Log prompt AI dettagliati |
| `position_tracking` | 2 | Posizioni attualmente aperte |
| `trade_snapshots` | 0 | Snapshot periodici (non usato) |

### Viste (Views)

| Vista | Descrizione |
|-------|-------------|
| `v_trade_summary` | Riepilogo per symbol e trading_mode |
| `v_profitability_analysis` | Analisi profittabilità per giorno |

---

## 🗃️ Schema Dettagliato Tabelle Principali

### `trades` (Tabella principale per analisi)

```sql
CREATE TABLE trades (
    id                    BIGSERIAL PRIMARY KEY,
    trade_uuid            UUID NOT NULL DEFAULT gen_random_uuid(),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol                TEXT NOT NULL,           -- BTC, ETH, SOL
    direction             TEXT NOT NULL,           -- LONG, SHORT
    trading_mode          TEXT NOT NULL,           -- MICRO_GAIN, MICRO_PAY, NORMAL
    status                TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, CLOSED
    opened_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at             TIMESTAMPTZ,
    duration_seconds      INTEGER,
    entry_price           NUMERIC NOT NULL,
    exit_price            NUMERIC,
    size                  NUMERIC NOT NULL,
    leverage              INTEGER NOT NULL DEFAULT 1,
    notional_value        NUMERIC,
    margin_used           NUMERIC,
    pnl_percent           NUMERIC,                 -- P&L % lordo
    pnl_usd               NUMERIC,                 -- P&L USD lordo
    fee_open              NUMERIC DEFAULT 0,
    fee_close             NUMERIC DEFAULT 0,
    fee_funding           NUMERIC DEFAULT 0,
    fee_total             NUMERIC DEFAULT 0,
    net_pnl_usd           NUMERIC,                 -- P&L USD NETTO (dopo fee)
    net_pnl_percent       NUMERIC,
    profitable            BOOLEAN,                 -- true se net_pnl_usd > 0
    close_reason          TEXT,                    -- TP_HIT, SL_HIT, AI_DECISION, REVERSAL
    open_score            NUMERIC,                 -- Score all'apertura
    open_rsi              NUMERIC,
    open_macd             NUMERIC,
    open_fg               INTEGER,                 -- Fear & Greed all'apertura
    open_volume_ratio     NUMERIC,
    close_score           NUMERIC,
    close_rsi             NUMERIC,
    sl_percent_config     NUMERIC,                 -- Stop Loss configurato
    tp_percent_config     NUMERIC,                 -- Take Profit configurato
    trailing_activation   NUMERIC,
    trailing_gap          NUMERIC,
    peak_price            NUMERIC,                 -- Prezzo massimo raggiunto
    peak_pnl_percent      NUMERIC,                 -- Max P&L raggiunto
    metadata              JSONB DEFAULT '{}',
    open_source           TEXT                     -- Sorgente apertura (AI, SENTINEL, etc.)
);
```

### `bot_operations` (Decisioni AI)

```sql
CREATE TABLE bot_operations (
    id                        BIGSERIAL PRIMARY KEY,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id                BIGINT REFERENCES ai_contexts(id),
    operation                 TEXT NOT NULL,        -- open, close, hold
    symbol                    TEXT,
    direction                 TEXT,                 -- long, short
    target_portion_of_balance NUMERIC,
    leverage                  NUMERIC,
    raw_payload               JSONB NOT NULL        -- Contiene opening_score, trading_mode, reason
);
```

### `signal_scores` (Score calcolati)

```sql
CREATE TABLE signal_scores (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id      BIGINT REFERENCES ai_contexts(id),
    symbol          TEXT NOT NULL,
    score_bullish   NUMERIC NOT NULL,
    score_bearish   NUMERIC NOT NULL,
    net_score       NUMERIC NOT NULL,           -- score_bullish - score_bearish
    direction       TEXT NOT NULL,              -- LONG, SHORT, HOLD
    confidence      TEXT,                       -- STRONG, MEDIUM, WEAK
    signals         JSONB NOT NULL,             -- Dettaglio segnali
    thresholds      JSONB,
    weights_config  JSONB
);
```

### `sentinel_logs` (Monitoraggio continuo)

```sql
CREATE TABLE sentinel_logs (
    id                   BIGSERIAL PRIMARY KEY,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol               TEXT NOT NULL,
    direction            TEXT NOT NULL,
    entry_price          NUMERIC NOT NULL,
    current_price        NUMERIC NOT NULL,
    peak_price           NUMERIC NOT NULL,
    profit_pct           NUMERIC,
    profit_from_peak_pct NUMERIC,
    trailing_active      BOOLEAN DEFAULT false,
    action_taken         TEXT,                   -- CLOSE, NONE, UPDATE_SL
    action_reason        TEXT,                   -- TP_HIT, SL_HIT, TRAILING_STOP
    bot_triggered        BOOLEAN DEFAULT false
);
```

### `position_tracking` (Posizioni aperte)

```sql
CREATE TABLE position_tracking (
    id                 BIGSERIAL PRIMARY KEY,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol             TEXT NOT NULL,
    direction          TEXT NOT NULL,
    entry_price        NUMERIC NOT NULL,
    peak_price         NUMERIC NOT NULL,
    trailing_active    BOOLEAN DEFAULT false,
    last_checked_price NUMERIC,
    opening_score      DOUBLE PRECISION,
    trading_mode       VARCHAR DEFAULT 'NORMAL'
);
```

---

## 📈 Analisi Performance (Dal DB - 27 Nov - 4 Dic 2025)

### Performance per Trading Mode

| Symbol | Mode | Trades | Win Rate | Net PnL |
|--------|------|--------|----------|---------|
| BTC | MICRO_GAIN | 77 | 58.44% | **+3.98** ✅ |
| ETH | MICRO_GAIN | 59 | 59.32% | **+1.31** ✅ |
| SOL | MICRO_GAIN | 66 | 62.12% | -0.30 |
| BTC | NORMAL | 19 | 10.53% | -1.17 ❌ |
| ETH | NORMAL | 13 | 0.00% | -0.37 ❌ |
| SOL | NORMAL | 24 | 37.50% | -0.19 ❌ |
| BTC | MICRO_PAY | 7 | 14.29% | -1.46 ❌ |

**Conclusione:** MICRO_GAIN è l'unico mode profittevole!

### Performance per Close Reason

| Close Reason | Trades | Win Rate Lordo | Win Rate Netto | PnL Netto |
|--------------|--------|----------------|----------------|-----------|
| TP_HIT | 140 | 100% | 97.1% | **+33.60** ✅ |
| SL_HIT | 81 | 12.3% | 4.9% | **-25.47** ❌ |
| AI_DECISION | 46 | 0% | 0% | **-4.52** ❌ |
| REVERSAL | 16 | 12.5% | 12.5% | **-1.79** ❌ |

**Conclusione:**
- TP_HIT funziona bene (+33.60)
- SL_HIT è il problema principale (-25.47)
- AI_DECISION ha 0% win rate - mai profittevole!

### Performance per Fascia di Score

| Score Range | Trades | Win Rate | Net PnL |
|-------------|--------|----------|---------|
| 13-16 (medio) | 192 | **59.9%** | **+9.40** ✅ |
| 10-13 (debole) | 21 | 23.8% | -1.77 ❌ |
| 16-20 (buono) | 25 | 44.0% | -2.87 ❌ |
| 20+ (forte) | 45 | 24.4% | -2.95 ❌ |

**Conclusione SHOCK:** Score 13-16 è il MIGLIORE! Score > 20 performa PEGGIO!

### Analisi SL_HIT Dettagliata

| Tipo Risultato | Trades | Avg PnL Netto |
|----------------|--------|---------------|
| LOSS | 71 | -0.360 |
| WIN lordo+netto (trailing OK) | 4 | +0.050 |
| WIN lordo, LOSS netto (fee!) | 6 | -0.020 |

→ 10 SL_HIT erano in profitto LORDO (trailing ha funzionato!)
→ 6 di questi sono diventati perdita per le FEE

### Performance per Giorno

| Giorno | Trade | TP Hit | SL Hit | Net PnL |
|--------|-------|--------|--------|---------|
| 4 dic | 55 | 28 | 23 | -1.32 ❌ |
| 3 dic | 62 | 42 | 20 | -0.83 ❌ |
| 2 dic | 29 | 18 | 10 | +3.29 ✅ |
| 1 dic | 28 | 22 | 5 | +1.81 ✅ |
| 30 nov | 28 | 9 | 4 | +1.43 ✅ |

**Pattern:** Meno trade = più profitto!
- 28-29 trade/giorno → Profittevole
- 55-62 trade/giorno → In perdita

---

## ⚠️ Problemi Identificati

### 1. Dati Mancanti nel DB
- DB mostra: +1.82 USDC totale
- Hyperliquid reale: -25.28 USDC
- **DIFFERENZA: ~27 USDC di trade mancanti!**

### 2. Tabelle Non Popolate
- `trade_snapshots`: 0 righe (dovrebbe tracciare snapshot periodici)
- `position_tracking`: Solo 2 righe (posizioni attuali)

### 3. AI_DECISION Sempre in Perdita
- 46 trade con close_reason = AI_DECISION
- **0% win rate** - l'AI chiude sempre in perdita!

**Dettaglio per giorno AI_DECISION:**
| Data | Trade | Net PnL |
|------|-------|---------|
| 4 dic | 2 | -2.71 |
| 30 nov | 7 | -0.35 |
| **29 nov** | **36** | **-1.45** |
| 28 nov | 1 | -0.01 |

→ Il 29 novembre: **36 chiusure AI in un solo giorno!** Anomalia.

### 4. Fee Mangiano Profitti Piccoli
- 4 TP_HIT diventano LOSS dopo le fee
- 6 SL_HIT erano WIN lordo ma LOSS netto

---

## 🔧 Configurazione Attuale (.env)

```bash
# Score Thresholds
SCORE_THRESHOLD_HOLD=10         # Sotto = HOLD
SCORE_THRESHOLD_OPEN=15-20      # Sopra = NORMAL
# Tra HOLD e OPEN = MICRO_GAIN

# Trailing Stop
MICRO_GAIN_TRAILING_MODE=steps
MICRO_GAIN_TRAILING_STEPS=0.4:-3,1.0:0.6,1.3:0.9,1.8:1.4,2.5:2.0...

# Stop Loss / Take Profit
MICRO_GAIN_TARGET_PERCENT=3.0
MICRO_GAIN_STOP_LOSS_PERCENT=3.0

# Cooldown
MIN_MINUTES_BETWEEN_TRADES=30
```

---

## 📋 Raccomandazioni

### Basate sui Dati

1. **Alzare SCORE_THRESHOLD_HOLD a 13**
   - Score 10-13 ha win rate 24% → Troppo basso

2. **Abbassare SCORE_THRESHOLD_OPEN a 16**
   - Score 13-16 è il migliore (60% win rate)
   - Score > 20 performa peggio (24% win rate)

3. **Ridurre numero trade/giorno a max 30**
   - Giorni con 28-29 trade sono profittevoli
   - Giorni con 55+ trade sono in perdita

4. **Disabilitare o rivedere AI_DECISION**
   - 0% win rate è inaccettabile

5. **Verificare dati con API Hyperliquid**
   - Mancano ~27 USDC di trade nel DB

---

## 🔍 Query Utili

### Win Rate per Score Range
```sql
SELECT
    CASE
        WHEN ABS(open_score) < 13 THEN '10-13 (debole)'
        WHEN ABS(open_score) < 16 THEN '13-16 (medio)'
        WHEN ABS(open_score) < 20 THEN '16-20 (buono)'
        ELSE '20+ (forte)'
    END as score_range,
    COUNT(*) as trades,
    ROUND(100.0 * SUM(CASE WHEN profitable THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl
FROM trades WHERE status = 'CLOSED'
GROUP BY 1 ORDER BY 1;
```

### Win Rate Lordo vs Netto per Close Reason
```sql
SELECT
    close_reason,
    COUNT(*) as trades,
    ROUND(100.0 * SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_lordo,
    ROUND(100.0 * SUM(CASE WHEN net_pnl_usd > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_netto,
    ROUND(SUM(net_pnl_usd)::numeric, 2) as tot_pnl_netto
FROM trades WHERE status = 'CLOSED'
GROUP BY 1 ORDER BY trades DESC;
```

### Trade per Giorno
```sql
SELECT
    DATE(created_at) as giorno,
    COUNT(*) as trade_db,
    SUM(CASE WHEN close_reason = 'TP_HIT' THEN 1 ELSE 0 END) as tp_hit,
    SUM(CASE WHEN close_reason = 'SL_HIT' THEN 1 ELSE 0 END) as sl_hit,
    ROUND(SUM(net_pnl_usd)::numeric, 2) as net_pnl
FROM trades
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY 1 ORDER BY 1 DESC;
```

### Viste Predefinite
```sql
-- Riepilogo per Symbol e Mode
SELECT * FROM v_trade_summary;

-- Analisi profittabilità per giorno
SELECT * FROM v_profitability_analysis ORDER BY trade_date DESC LIMIT 10;
```

---

## 📁 File Correlati

| File | Descrizione |
|------|-------------|
| `db_utils.py` | Funzioni per interazione DB |
| `sentinel.py` | Monitoraggio continuo e trailing stop |
| `signal_scorer.py` | Calcolo score segnali |
| `trade_journal.py` | Logging trade (se presente) |
| `verify_trades_vs_hyperliquid.py` | Script verifica API (da creare) |

---

## 🔄 Aggiornamenti

| Data | Modifica |
|------|----------|
| 2025-12-04 | Creazione documento con analisi completa |
