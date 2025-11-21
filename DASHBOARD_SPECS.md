# 📊 SPECIFICA TECNICA - Dashboard Trading Bot

**Progetto:** Rizzo Trading Agent
**Scopo:** Interfaccia grafica per monitoraggio e analisi performance bot
**Data:** 2025-01-21

---

## 📋 SOMMARIO ESECUTIVO

Dashboard web per visualizzare in tempo reale:
- Performance bot (P&L, win rate, trades)
- Decisioni AI con reasoning
- Analisi tecnica e segnali
- Stato account e posizioni
- Grafici storici

---

## 🗄️ DATABASE - CONNESSIONE

### Credenziali

```bash
Host: memory_postgres (container Docker)
Porta: 5432 (interna), 5433 (esterna)
Database: rizzo_trading
Username: tradingbot
Password: TradingBot2025!Secure
```

### Connection String

```python
# Python (psycopg2)
DATABASE_URL = "postgresql://tradingbot:TradingBot2025!Secure@memory_postgres:5432/rizzo_trading"

# JavaScript (node-postgres)
const config = {
  host: 'memory_postgres',
  port: 5432,
  database: 'rizzo_trading',
  user: 'tradingbot',
  password: 'TradingBot2025!Secure'
}
```

---

## 📊 SCHEMA DATABASE

### Tabelle Principali

#### 1. `account_snapshots` - Stato Account nel Tempo

```sql
CREATE TABLE account_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance_usd     NUMERIC(20, 8) NOT NULL,
    raw_payload     JSONB NOT NULL
);
```

**Query esempio:**
```sql
-- Balance storico (ultimi 7 giorni)
SELECT
    created_at,
    balance_usd
FROM account_snapshots
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at;

-- Balance corrente
SELECT
    balance_usd,
    created_at
FROM account_snapshots
ORDER BY created_at DESC
LIMIT 1;
```

---

#### 2. `open_positions` - Posizioni Aperte

```sql
CREATE TABLE open_positions (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES account_snapshots(id),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,  -- 'long' o 'short'
    size            NUMERIC(30, 10) NOT NULL,
    entry_price     NUMERIC(30, 10),
    mark_price      NUMERIC(30, 10),
    pnl_usd         NUMERIC(30, 10),
    leverage        TEXT,
    raw_payload     JSONB NOT NULL
);
```

**Query esempio:**
```sql
-- Posizioni correnti
SELECT
    op.symbol,
    op.side,
    op.size,
    op.entry_price,
    op.mark_price,
    op.pnl_usd,
    op.leverage,
    as2.created_at
FROM open_positions op
JOIN account_snapshots as2 ON op.snapshot_id = as2.id
WHERE as2.created_at = (SELECT MAX(created_at) FROM account_snapshots);

-- P&L per simbolo (storico)
SELECT
    symbol,
    side,
    SUM(pnl_usd) as total_pnl,
    COUNT(*) as num_positions,
    AVG(pnl_usd) as avg_pnl
FROM open_positions
GROUP BY symbol, side
ORDER BY total_pnl DESC;
```

---

#### 3. `bot_operations` - Decisioni del Bot

```sql
CREATE TABLE bot_operations (
    id                          BIGSERIAL PRIMARY KEY,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_id                  BIGINT REFERENCES ai_contexts(id),
    operation                   TEXT NOT NULL,  -- 'open', 'close', 'hold'
    symbol                      TEXT,
    direction                   TEXT,  -- 'long' o 'short'
    target_portion_of_balance   NUMERIC(10, 4),
    leverage                    NUMERIC(10, 4),
    raw_payload                 JSONB NOT NULL
);
```

**Query esempio:**
```sql
-- Ultime 20 decisioni
SELECT
    created_at,
    operation,
    symbol,
    direction,
    leverage,
    raw_payload->>'reason' as reason
FROM bot_operations
ORDER BY created_at DESC
LIMIT 20;

-- Statistiche operazioni
SELECT
    operation,
    symbol,
    COUNT(*) as count,
    AVG(leverage) as avg_leverage
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY operation, symbol
ORDER BY count DESC;

-- Win rate (posizioni chiuse con profitto)
WITH closed_positions AS (
    SELECT
        bo.symbol,
        bo.created_at,
        op.pnl_usd
    FROM bot_operations bo
    JOIN open_positions op ON bo.symbol = op.symbol
    WHERE bo.operation = 'close'
    AND bo.created_at > NOW() - INTERVAL '30 days'
)
SELECT
    symbol,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
    ROUND(100.0 * SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate,
    SUM(pnl_usd) as total_pnl
FROM closed_positions
GROUP BY symbol;
```

---

#### 4. `ai_contexts` - Contesti AI (Input Modello)

```sql
CREATE TABLE ai_contexts (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_prompt   TEXT
);
```

---

#### 5. `indicators_contexts` - Indicatori Tecnici

```sql
CREATE TABLE indicators_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT REFERENCES ai_contexts(id),
    ticker                  TEXT NOT NULL,
    ts                      TIMESTAMPTZ,
    price                   NUMERIC(20, 8),
    ema20                   NUMERIC(20, 8),
    ema50                   NUMERIC(20, 8),
    macd                    NUMERIC(20, 8),
    rsi_7                   NUMERIC(20, 8),
    rsi_14                  NUMERIC(20, 8),
    atr3_15m                NUMERIC(20, 8),
    atr14_15m               NUMERIC(20, 8),
    volume_bid              NUMERIC(20, 8),
    volume_ask              NUMERIC(20, 8),
    pp                      NUMERIC(20, 8),  -- Pivot point
    s1                      NUMERIC(20, 8),  -- Support 1
    s2                      NUMERIC(20, 8),  -- Support 2
    r1                      NUMERIC(20, 8),  -- Resistance 1
    r2                      NUMERIC(20, 8),  -- Resistance 2
    open_interest_latest    NUMERIC(30, 10),
    open_interest_average   NUMERIC(30, 10),
    funding_rate            NUMERIC(20, 8),
    volume_15m_current      NUMERIC(30, 10),
    volume_15m_average      NUMERIC(30, 10),
    intraday_mid_prices     JSONB,  -- Array ultimi 10 prezzi
    intraday_ema20_series   JSONB,  -- Array ultimi 10 EMA20
    intraday_macd_series    JSONB,  -- Array ultimi 10 MACD
    intraday_rsi7_series    JSONB,  -- Array ultimi 10 RSI7
    intraday_rsi14_series   JSONB,  -- Array ultimi 10 RSI14
    lt15m_macd_series       JSONB,  -- Array ultimi 10 MACD (longer term)
    lt15m_rsi14_series      JSONB   -- Array ultimi 10 RSI14 (longer term)
);
```

**Query esempio:**
```sql
-- Ultimi indicatori per BTC
SELECT
    ticker,
    ts,
    price,
    ema20,
    ema50,
    rsi_7,
    rsi_14,
    macd,
    pp,
    s1,
    s2,
    r1,
    r2
FROM indicators_contexts
WHERE ticker = 'BTC'
ORDER BY ts DESC
LIMIT 1;

-- Serie temporale RSI (per grafico)
SELECT
    ts,
    ticker,
    rsi_7,
    rsi_14
FROM indicators_contexts
WHERE ticker = 'BTC'
AND ts > NOW() - INTERVAL '24 hours'
ORDER BY ts;
```

---

#### 6. `sentiment_contexts` - Sentiment Fear & Greed

```sql
CREATE TABLE sentiment_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT REFERENCES ai_contexts(id),
    value                   INTEGER,  -- 0-100
    classification          TEXT,  -- 'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'
    sentiment_timestamp     BIGINT,
    raw                     JSONB
);
```

**Query esempio:**
```sql
-- Sentiment attuale
SELECT
    value,
    classification,
    created_at
FROM sentiment_contexts
ORDER BY created_at DESC
LIMIT 1;

-- Sentiment storico (ultimi 30 giorni)
SELECT
    DATE(created_at) as date,
    AVG(value) as avg_sentiment,
    MAX(classification) as classification
FROM sentiment_contexts
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date;
```

---

#### 7. `forecasts_contexts` - Previsioni Prophet

```sql
CREATE TABLE forecasts_contexts (
    id                      BIGSERIAL PRIMARY KEY,
    context_id              BIGINT REFERENCES ai_contexts(id),
    ticker                  TEXT NOT NULL,
    timeframe               TEXT NOT NULL,  -- '15min' o '1h'
    last_price              NUMERIC(30, 10),
    prediction              NUMERIC(30, 10),
    lower_bound             NUMERIC(30, 10),
    upper_bound             NUMERIC(30, 10),
    change_pct              NUMERIC(10, 4),
    forecast_timestamp      BIGINT,
    raw                     JSONB
);
```

**Query esempio:**
```sql
-- Ultime previsioni
SELECT
    ticker,
    timeframe,
    last_price,
    prediction,
    change_pct,
    created_at
FROM forecasts_contexts
ORDER BY created_at DESC
LIMIT 10;

-- Accuracy previsioni (confronto previsione vs realtà)
WITH forecasts AS (
    SELECT
        ticker,
        prediction,
        created_at,
        LEAD(last_price) OVER (PARTITION BY ticker ORDER BY created_at) as actual_price
    FROM forecasts_contexts
    WHERE timeframe = '15min'
)
SELECT
    ticker,
    AVG(ABS(prediction - actual_price) / actual_price * 100) as avg_error_pct
FROM forecasts
WHERE actual_price IS NOT NULL
GROUP BY ticker;
```

---

#### 8. `errors` - Log Errori

```sql
CREATE TABLE errors (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_type      TEXT NOT NULL,
    error_message   TEXT,
    traceback       TEXT,
    context         JSONB,
    source          TEXT
);
```

---

## 📊 METRICHE CHIAVE DA MOSTRARE

### 1. Overview Dashboard

```
┌─────────────────────────────────────────────────────────┐
│ 💰 Balance Corrente: 45.7 USDC                         │
│ 📈 P&L Totale: +2.3 USDC (+5.3%)                       │
│ 🎯 Win Rate: 65% (13/20 trades)                        │
│ 🤖 Ultima Decisione: HOLD BTC (5 min fa)               │
└─────────────────────────────────────────────────────────┘
```

**Query:**
```sql
-- Balance corrente
SELECT balance_usd FROM account_snapshots ORDER BY created_at DESC LIMIT 1;

-- P&L totale
SELECT
    (MAX(balance_usd) - MIN(balance_usd)) as total_pnl,
    ((MAX(balance_usd) - MIN(balance_usd)) / MIN(balance_usd) * 100) as pnl_pct
FROM account_snapshots;

-- Win rate
SELECT
    COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) as wins,
    COUNT(*) as total,
    ROUND(100.0 * COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) / COUNT(*), 2) as win_rate
FROM open_positions
WHERE pnl_usd IS NOT NULL;

-- Ultima decisione
SELECT operation, symbol, created_at
FROM bot_operations
ORDER BY created_at DESC
LIMIT 1;
```

---

### 2. Grafico Balance nel Tempo

**Tipo:** Line chart
**Asse X:** Timestamp
**Asse Y:** Balance USD
**Periodo:** Ultime 24h / 7gg / 30gg (selezionabile)

**Query:**
```sql
SELECT
    created_at,
    balance_usd
FROM account_snapshots
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at;
```

---

### 3. P&L per Simbolo (Bar Chart)

**Tipo:** Bar chart orizzontale
**Asse X:** P&L USD
**Asse Y:** Simbolo (BTC, ETH, SOL)
**Colore:** Verde (profit), Rosso (loss)

**Query:**
```sql
SELECT
    symbol,
    SUM(pnl_usd) as total_pnl,
    COUNT(*) as num_trades
FROM open_positions
GROUP BY symbol
ORDER BY total_pnl DESC;
```

---

### 4. Distribuzione Operazioni (Pie Chart)

**Tipo:** Pie chart
**Fette:** OPEN, CLOSE, HOLD
**Percentuale per tipo**

**Query:**
```sql
SELECT
    operation,
    COUNT(*) as count
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY operation;
```

---

### 5. Tabella Ultime Decisioni AI

| Timestamp | Operazione | Symbol | Direction | Leverage | Reason |
|-----------|-----------|--------|-----------|----------|--------|
| 12:42 | HOLD | BTC | - | - | Market sentiment fear, no clear signal |
| 11:30 | OPEN | SOL | LONG | 3x | SOL oversold, RSI 30.7 near support |
| 10:15 | CLOSE | ETH | SHORT | - | Target reached, take profit |

**Query:**
```sql
SELECT
    TO_CHAR(created_at, 'HH24:MI') as time,
    operation,
    symbol,
    direction,
    leverage,
    SUBSTRING(raw_payload->>'reason', 1, 80) as reason
FROM bot_operations
ORDER BY created_at DESC
LIMIT 20;
```

---

### 6. Indicatori Tecnici Correnti

**Layout:** Cards o tabella

```
┌─────────────────────────────────────────┐
│ BTC/USD: $43,250                        │
│ ├─ RSI(7): 45.3  ⚪ Neutral             │
│ ├─ RSI(14): 52.1 ⚪ Neutral             │
│ ├─ MACD: +120.5  🟢 Bullish            │
│ ├─ EMA20: $43,100                       │
│ ├─ Support S1: $42,800                  │
│ └─ Resistance R1: $43,600               │
└─────────────────────────────────────────┘
```

**Query:**
```sql
SELECT
    ticker,
    price,
    rsi_7,
    rsi_14,
    macd,
    ema20,
    ema50,
    s1,
    r1
FROM indicators_contexts
WHERE ts = (SELECT MAX(ts) FROM indicators_contexts)
ORDER BY ticker;
```

---

### 7. Sentiment Fear & Greed

**Tipo:** Gauge / Meter
**Range:** 0-100
**Colori:**
- 0-25: Extreme Fear (rosso)
- 25-45: Fear (arancione)
- 45-55: Neutral (giallo)
- 55-75: Greed (verde chiaro)
- 75-100: Extreme Greed (verde)

**Query:**
```sql
SELECT
    value,
    classification
FROM sentiment_contexts
ORDER BY created_at DESC
LIMIT 1;
```

---

### 8. Forecast Accuracy

**Tipo:** Line chart con bande (prediction ± confidence)
**Mostra:** Previsione vs Prezzo Reale

**Query:**
```sql
SELECT
    ticker,
    timeframe,
    last_price,
    prediction,
    lower_bound,
    upper_bound,
    change_pct,
    created_at
FROM forecasts_contexts
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at;
```

---

### 9. Performance Metrics Table

| Metrica | Valore |
|---------|--------|
| Total Trades | 45 |
| Winning Trades | 29 (64.4%) |
| Average Profit | +0.12 USDC |
| Average Loss | -0.08 USDC |
| Profit Factor | 1.85 |
| Max Drawdown | -1.2 USDC (-2.6%) |
| Sharpe Ratio | 1.42 |

**Query:**
```sql
WITH trades AS (
    SELECT
        pnl_usd,
        CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END as is_win
    FROM open_positions
    WHERE pnl_usd IS NOT NULL
)
SELECT
    COUNT(*) as total_trades,
    SUM(is_win) as winning_trades,
    ROUND(100.0 * SUM(is_win) / COUNT(*), 2) as win_rate,
    AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END) as avg_profit,
    AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END) as avg_loss,
    ABS(SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd END) /
        SUM(CASE WHEN pnl_usd < 0 THEN pnl_usd END)) as profit_factor
FROM trades;

-- Max Drawdown
WITH balance_history AS (
    SELECT
        created_at,
        balance_usd,
        MAX(balance_usd) OVER (ORDER BY created_at) as peak_balance
    FROM account_snapshots
)
SELECT
    MIN(balance_usd - peak_balance) as max_drawdown,
    ROUND(100.0 * MIN((balance_usd - peak_balance) / peak_balance), 2) as max_drawdown_pct
FROM balance_history;
```

---

## 🎨 STACK TECNOLOGICO CONSIGLIATO

### Opzione 1: Web Dashboard (React/Vue) - ⭐ Consigliato

**Frontend:**
- React.js o Vue.js
- Chart.js / Recharts / ApexCharts (grafici)
- TailwindCSS / Material-UI (styling)
- Axios (API calls)

**Backend:**
- Node.js + Express (API REST)
- node-postgres (pg) per database
- Oppure Python FastAPI

**Vantaggi:**
- ✅ Accessibile da browser
- ✅ Responsive (mobile-friendly)
- ✅ Real-time con WebSockets
- ✅ Facile deployment

---

### Opzione 2: Streamlit (Python) - 🚀 Più Veloce

**Stack:**
- Streamlit (framework Python per dashboard)
- Plotly (grafici interattivi)
- psycopg2 (database)
- pandas (data manipulation)

**Vantaggi:**
- ✅ Velocissimo da sviluppare (1-2 giorni)
- ✅ Auto-refresh built-in
- ✅ Già disponibile nel progetto! (branch nuovo)

**Svantaggi:**
- ⚠️ Meno personalizzabile UI
- ⚠️ Performance con molti utenti

---

### Opzione 3: Grafana - 📊 Professional

**Stack:**
- Grafana (dashboard platform)
- PostgreSQL data source
- Query builder visual

**Vantaggi:**
- ✅ Professionale
- ✅ Alert system built-in
- ✅ Template pronti

**Svantaggi:**
- ⚠️ Serve setup iniziale
- ⚠️ Curva apprendimento

---

## 🖼️ MOCKUP UI (Suggerimenti Layout)

### Layout Desktop

```
┌────────────────────────────────────────────────────────────────┐
│ 🤖 Rizzo Trading Bot Dashboard          [⚙️] [🔔] [@User]     │
├────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│ │ 💰 Balance   │ │ 📈 P&L       │ │ 🎯 Win Rate  │            │
│ │ 45.7 USDC    │ │ +2.3 (+5.3%) │ │ 65% (13/20)  │            │
│ └──────────────┘ └──────────────┘ └──────────────┘            │
├────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ 📊 Balance Storico                                       │   │
│ │ [Line Chart: Balance nel tempo]                          │   │
│ │                                                           │   │
│ │   48 ┤                                    ╭──╮            │   │
│ │   46 ┤                      ╭─────╮     │  │            │   │
│ │   44 ┤        ╭─────╮      │     │    │  │            │   │
│ │   42 ┤───────╯      ╰──────╯     ╰────╯  │            │   │
│ │      └──────────────────────────────────────────        │   │
│ │        1d   2d   3d   4d   5d   6d   7d  [📅 Periodo]  │   │
│ └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────┬──────────────────────────────┤
│ 📋 Ultime Decisioni AI          │ 📊 P&L per Simbolo          │
│ ┌──────────────────────────────┐│ ┌──────────────────────────┐│
│ │Time  Op    Sym Dir  Lvg     ││ │ BTC  ████████  +1.2      ││
│ │12:42 HOLD  BTC  -    -      ││ │ SOL  ████      +0.5      ││
│ │11:30 OPEN  SOL  L    3x     ││ │ ETH  ██        +0.1      ││
│ │10:15 CLOSE ETH  S    -      ││ │                          ││
│ │09:00 HOLD  BTC  -    -      ││ └──────────────────────────┘│
│ └──────────────────────────────┘│                             │
└─────────────────────────────────┴──────────────────────────────┘
```

---

### Sezione Indicatori Tecnici

```
┌────────────────────────────────────────────────────────────────┐
│ 📈 Indicatori Tecnici                          [🔄 Refresh]    │
├────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│ │ BTC/USD         │ │ ETH/USD         │ │ SOL/USD         │   │
│ │ $43,250 ▲       │ │ $2,340 ▼        │ │ $98.50 ▲        │   │
│ │                 │ │                 │ │                 │   │
│ │ RSI(7):  45.3 ⚪│ │ RSI(7):  62.1 🟢│ │ RSI(7):  30.7 🔴│   │
│ │ RSI(14): 52.1 ⚪│ │ RSI(14): 58.3 ⚪│ │ RSI(14): 35.2 🔴│   │
│ │ MACD:   +120 🟢│ │ MACD:   -45  🔴│ │ MACD:   +78  🟢│   │
│ │                 │ │                 │ │                 │   │
│ │ S1: $42,800     │ │ S1: $2,290      │ │ S1: $96.20      │   │
│ │ R1: $43,600     │ │ R1: $2,380      │ │ R1: $100.50     │   │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

---

### Sezione Sentiment

```
┌────────────────────────────────────────────────────────────────┐
│ 😨 Fear & Greed Index                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│        ╭─────────────────────────────────────────╮             │
│        │  Extreme Fear  │  Fear  │  Greed  │  Extreme Greed  │ │
│        │────────────────●─────────│─────────│──────────│      │ │
│        0              15         50        75         100      │
│                                                                 │
│        📉 FEAR (15/100) - Extreme Fear                         │
│        "Opportunità di acquisto? Mercato in panico"            │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 🔌 API REST SUGGERITE (Backend)

### Endpoint da implementare

```javascript
// Overview
GET /api/overview
Response: {
  current_balance: 45.7,
  total_pnl: 2.3,
  pnl_percentage: 5.3,
  win_rate: 65,
  total_trades: 20,
  last_decision: {...}
}

// Balance history
GET /api/balance/history?period=7d
Response: [
  {timestamp: "2025-01-20T10:00:00Z", balance: 43.2},
  {timestamp: "2025-01-20T11:00:00Z", balance: 43.5},
  ...
]

// Operations
GET /api/operations?limit=20
Response: [
  {
    id: 2176,
    created_at: "2025-01-21T11:42:00Z",
    operation: "hold",
    symbol: "BTC",
    reason: "Market sentiment fear..."
  },
  ...
]

// Indicators
GET /api/indicators/current
Response: {
  BTC: {price: 43250, rsi_7: 45.3, ...},
  ETH: {price: 2340, rsi_7: 62.1, ...},
  SOL: {price: 98.5, rsi_7: 30.7, ...}
}

// Sentiment
GET /api/sentiment/current
Response: {
  value: 15,
  classification: "Extreme Fear"
}

// Performance metrics
GET /api/performance/metrics
Response: {
  total_trades: 45,
  winning_trades: 29,
  win_rate: 64.4,
  avg_profit: 0.12,
  max_drawdown: -1.2,
  ...
}

// P&L by symbol
GET /api/pnl/by-symbol
Response: [
  {symbol: "BTC", total_pnl: 1.2, num_trades: 12},
  {symbol: "SOL", total_pnl: 0.5, num_trades: 5},
  {symbol: "ETH", total_pnl: 0.1, num_trades: 3}
]
```

---

## 🚀 DEPLOY STREAMLIT (Già Disponibile!)

**NOTA:** Il branch nuovo ha già una dashboard Streamlit pronta!

```bash
# Sul VPS
cd /root/trading-bots/rizzo-trading-agent

# Avvia dashboard
docker compose up -d dashboard

# Accedi a: http://69.62.114.142:8501
```

Il file `dashboard.py` nel branch nuovo contiene già:
- Balance storico
- Ultime decisioni AI
- P&L per symbol
- Grafici interattivi

---

## 📦 DELIVERABLE PER PROGRAMMATORE

### File da fornire:

1. ✅ **DASHBOARD_SPECS.md** (questo documento)
2. ✅ **Credenziali database**
3. ✅ **Schema database SQL** (vedi sopra)
4. ✅ **Query SQL di esempio** (tutte incluse)
5. ✅ **Mockup UI** (ASCII art sopra)
6. ✅ **API endpoints suggeriti**

### Accesso database:

```bash
# Da dentro VPS
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading

# Da esterno (se esposto)
psql -h 69.62.114.142 -p 5433 -U tradingbot -d rizzo_trading
```

---

## 🎯 ROADMAP SVILUPPO DASHBOARD

### Fase 1: MVP (1-2 giorni)
- [ ] Connessione database
- [ ] Balance corrente + storico (line chart)
- [ ] Ultime 20 decisioni (tabella)
- [ ] P&L per symbol (bar chart)

### Fase 2: Indicatori (2-3 giorni)
- [ ] Cards indicatori tecnici (RSI, MACD, EMA)
- [ ] Sentiment Fear & Greed (gauge)
- [ ] Forecast accuracy
- [ ] Grafici serie temporali indicatori

### Fase 3: Analytics (3-4 giorni)
- [ ] Performance metrics completi
- [ ] Win rate analysis
- [ ] Profit factor & Sharpe ratio
- [ ] Max drawdown visualization
- [ ] Trade distribution (pie charts)

### Fase 4: Advanced (5+ giorni)
- [ ] Real-time updates (WebSocket)
- [ ] Alert system (email/telegram)
- [ ] Backtesting interface
- [ ] Strategy comparison
- [ ] Export reports (PDF/Excel)

---

## 🔗 RIFERIMENTI

- **Repository:** https://github.com/Nixola1972/rizzo-trading-agent
- **Branch con dashboard:** `claude/analyze-project-setup-01MnuN6LvSEacZp7BCVbWeUB`
- **File dashboard:** `dashboard.py` (Streamlit)
- **Database:** PostgreSQL 16, container `memory_postgres`

---

**Documento creato:** 2025-01-21
**Autore:** Claude (Anthropic)
**Per:** Rizzo Trading Agent Dashboard Development
