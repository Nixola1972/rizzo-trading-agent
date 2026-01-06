# CLAUDE.md - Botone V6 (Aggiornato 6 Gennaio 2026)

---

## 📊 STATO ATTUALE DEL BOT

### Container in Esecuzione
```
botone_v6_slow  - AI decisions (SLOW loop ogni 3 min)
botone_v6_fast  - Position monitoring (FAST loop ogni 10s)
```

### Database
- **Host**: `memory_postgres`
- **Database**: `botone_baseline`
- **Tabella trade**: `botone_trades`
- **Connection**: `postgresql://tradingbot:YOUR_PASSWORD@memory_postgres:5432/botone_baseline`

---

## ✅ FILTRI IMPLEMENTATI (6 Gennaio 2026)

### Architettura Filtri

```
SLOW LOOP (ogni 3 min) - Decisioni AI
├── PRE-AI (risparmia token se bloccato)
│   ├── Volume VETO
│   ├── OBV VETO
│   ├── Symbol Cooldown VETO
│   └── ADX Filter VETO (NUOVO!)
│
├── → Chiama AI →
│
└── POST-AI (dipendono dalla direzione)
    ├── BTC RSI VETO
    ├── RSI Entry Filter
    └── EMA Trend Filter (NUOVO!)

FAST LOOP (ogni 10s) - Monitoraggio Posizioni
├── Aggiorna MFE/MAE
├── Early Exit Bad Entry (NUOVO!)
├── Check TP hit
├── Check SL hit
├── Trailing Stop update
└── Health Check
```

---

## 🆕 NUOVI FILTRI (6 Gennaio 2026)

### 1. EMA Trend Filter
**Problema risolto**: SHORT contro-trend perdevano (es: XRP -11 trade, -$7.64)

```env
EMA_TREND_FILTER_ENABLED=true
```

| EMA Stack | LONG | SHORT |
|-----------|------|-------|
| Bullish (uptrend) | ✅ OK | ❌ BLOCKED |
| Bearish (downtrend) | ❌ BLOCKED | ✅ OK |
| Neutral/Mixed | ✅ OK | ✅ OK |

**Risultato atteso**: Blocca trade contro-trend che hanno 8% win rate.

---

### 2. ADX Filter
**Problema risolto**: Trade con ADX >40 avevano P&L medio -1.17%

```env
ADX_FILTER_ENABLED=true
ADX_MAX=40
```

| ADX | Performance | Azione |
|-----|-------------|--------|
| <20 | +3.79% avg, 100% win | ✅ OK |
| 20-40 | ~0% avg | ✅ OK |
| >40 | -1.17% avg | ❌ BLOCKED |

**Motivo**: ADX alto = trend già maturo, si entra troppo tardi.

---

### 3. Early Exit for Bad Entry
**Problema risolto**: Trade con MAE > MFE avevano solo 8% win rate

```env
EARLY_EXIT_ENABLED=true
EARLY_EXIT_MINUTES=5
EARLY_EXIT_MAE=1.5
EARLY_EXIT_MFE=0.5
```

**Logica**: Dopo 5 minuti, se:
- MAE >= 1.5% (è andato contro di 1.5%+)
- MFE < 0.5% (non è MAI andato in profitto significativo)
→ Chiudi subito (bad entry, non recupererà)

**Esempio salvato**:
- ADA: chiuso a -1.5% invece di -11.60% → **salvato 10%!**
- BTC: chiuso a -1.5% invece di -6.48% → **salvato 5%!**

---

### 4. RSI Entry Filter
```env
RSI_ENTRY_FILTER_ENABLED=true
LONG_MAX_RSI=65    # Blocca LONG se RSI >= 65
SHORT_MIN_RSI=35   # Blocca SHORT se RSI <= 35
```

---

### 5. Symbol Cooldown (Spostato PRE-AI)
```env
SYMBOL_COOLDOWN_ENABLED=true
SYMBOL_COOLDOWN_MINUTES=60
```

**Novità**: Ora viene controllato PRIMA della chiamata AI per risparmiare token.

---

## 📊 ANALISI DATI (6 Gennaio 2026)

### Performance per Direzione
| Direzione | Trades | Win Rate | Total P&L |
|-----------|--------|----------|-----------|
| LONG | 35 | 60% | +$54.54 |
| SHORT | 26 | 42% | -$8.70 |

### Performance per Simbolo
| Symbol | Trades | P&L | Note |
|--------|--------|-----|------|
| BTC | 11 | +$19.01 | Migliore |
| ADA | 8 | +$13.38 | Ottimo |
| SUI | 9 | +$11.94 | Buono |
| XRP | 13 | **-$7.64** | Problema (troppi SHORT contro-trend) |

### MFE Analysis
| MFE Range | Win Rate | Conclusione |
|-----------|----------|-------------|
| 0-1% | 25% | Bad entries |
| 1-2% | 55% | Borderline |
| 3%+ | **100%** | Se raggiunge +3%, non perde MAI |

### Trade Quality
| Quality | Trades | Win Rate |
|---------|--------|----------|
| Clean Win (MAE<0.5, MFE>2) | 13 | 92% |
| Good Entry (MAE<1, MFE>1) | 9 | 100% |
| Bad Entry (MAE > MFE) | 24 | **8%** |

### Alignment (Trend)
| Setup | Total P&L | Note |
|-------|-----------|------|
| LONG + Bullish | **+$52.95** | TUTTO IL PROFITTO! |
| SHORT + Bullish | **-$8.06** | Disastro |

---

## ⚙️ CONFIGURAZIONE CONSIGLIATA

### .env.baseline
```env
# === FILTRI ENTRY (6 Gennaio 2026) ===

# EMA Trend Filter - no trade contro-trend
EMA_TREND_FILTER_ENABLED=true

# ADX Filter - no trade in trend troppo forti
ADX_FILTER_ENABLED=true
ADX_MAX=40

# RSI Entry Filter
RSI_ENTRY_FILTER_ENABLED=true
LONG_MAX_RSI=65
SHORT_MIN_RSI=35

# Symbol Cooldown (pre-AI per risparmiare token)
SYMBOL_COOLDOWN_ENABLED=true
SYMBOL_COOLDOWN_MINUTES=60

# === EARLY EXIT (6 Gennaio 2026) ===

# Chiudi bad entry prima che peggiorino
EARLY_EXIT_ENABLED=true
EARLY_EXIT_MINUTES=5
EARLY_EXIT_MAE=1.5
EARLY_EXIT_MFE=0.5

# === TRAILING STOP ===
STOP_LOSS_PCT=4.0
TAKE_PROFIT_PCT=99.0
TRAILING_STEPS=0.5:-2.0,1.0:-1.8,1.8:0.3,3.0:1.5,4.0:2.5,5.0:3.5,6.5:4.5,8.0:6.0,10.0:7.5,12.5:9.5,15.0:11.5,17.5:14.0,20.0:16.0,25.0:21.0,30.0:26.0,35.0:31.0,40.0:36.0

# === ALTRI FILTRI ===
BTC_ENTRY_VETO_ENABLED=true
BTC_ENTRY_VETO_LONG_RSI=70
BTC_ENTRY_VETO_SHORT_RSI=30

OBV_VETO_ENABLED=true
OBV_VETO_MIN_PRICE_CHANGE=0.5
```

---

## 🔧 QUERY UTILI

### Statistiche Generali
```sql
SELECT
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_pct > 0) / NULLIF(COUNT(*), 0), 1) as win_rate,
    ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl_usd
FROM botone_trades WHERE closed_at IS NOT NULL;
```

### Performance per Simbolo
```sql
SELECT
    symbol,
    COUNT(*) as trades,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(SUM(pnl_usd)::numeric, 2) as pnl_usd
FROM botone_trades WHERE closed_at IS NOT NULL
GROUP BY symbol ORDER BY pnl_usd DESC;
```

### Analisi MFE/MAE
```sql
SELECT
    CASE WHEN pnl_pct > 0 THEN 'WIN' ELSE 'LOSS' END as result,
    ROUND(AVG(mfe_pct)::numeric, 2) as avg_mfe,
    ROUND(AVG(mae_pct)::numeric, 2) as avg_mae,
    COUNT(*) as trades
FROM botone_trades WHERE closed_at IS NOT NULL
GROUP BY CASE WHEN pnl_pct > 0 THEN 'WIN' ELSE 'LOSS' END;
```

### Trade Quality Analysis
```sql
SELECT
    CASE
        WHEN mae_pct < 0.5 AND mfe_pct > 2 THEN 'Clean Win'
        WHEN mae_pct < 1 AND mfe_pct > 1 THEN 'Good Entry'
        WHEN mae_pct > mfe_pct THEN 'Bad Entry'
        ELSE 'Choppy'
    END as quality,
    COUNT(*) as trades,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins
FROM botone_trades
WHERE closed_at IS NOT NULL AND mfe_pct IS NOT NULL
GROUP BY 1 ORDER BY avg_pnl DESC;
```

### Verifica Filtri nei Log
```bash
# Verifica che i filtri siano attivi
docker logs botone_v6_slow 2>&1 | grep -E "EMA Trend|ADX Filter|Early Exit|Cooldown"

# Conta VETO per tipo
docker logs botone_v6_slow 2>&1 | grep "VETO" | tail -100
```

---

## 📁 STRUTTURA DATABASE

### Schema botone_trades
```sql
id, symbol, direction, opened_at, closed_at, duration_seconds,
entry_price, exit_price, size_usd, leverage, pnl_usd, pnl_pct,
max_price, min_price, mfe_pct, mae_pct, conviction_tier,
ai_confidence, ai_reasoning, prompt_style, entry_macd, entry_rsi,
entry_adx, entry_ema_stack, entry_volume_ratio, entry_bb_position,
entry_bb_squeeze, entry_obv_trend, exit_reason, sl_price, tp_price
```

### Exit Reasons
| exit_reason | Descrizione |
|-------------|-------------|
| SYNC_CLOSED | Chiuso da sync con exchange |
| SL hit | Stop Loss colpito |
| TP hit | Take Profit colpito |
| EARLY_EXIT | Bad entry detection (NUOVO!) |
| HEALTH_EMERGENCY | Health check critico |
| TIMEOUT_LOSS | Timeout con perdita |
| AI profit-take | AI decide di prendere profitto |

---

## 🚀 DEPLOY

```bash
cd /root/trading-bots/rizzo-trading-agent && \
git pull origin claude/update-botone-v6-4YxZq && \
docker build -t botone-v6:latest . && \
docker stop botone_v6_fast botone_v6_slow && \
docker rm botone_v6_fast botone_v6_slow && \
docker run -d --name botone_v6_fast --env-file /root/trading-bots/rizzo-trading-agent/.env.baseline -e PYTHONUNBUFFERED=1 --network unified-memory-stack_memory-net --restart unless-stopped --entrypoint python botone-v6:latest botone_v6.py --mode fast --loop && \
docker run -d --name botone_v6_slow --env-file /root/trading-bots/rizzo-trading-agent/.env.baseline -e PYTHONUNBUFFERED=1 --network unified-memory-stack_memory-net --restart unless-stopped --entrypoint python botone-v6:latest botone_v6.py --mode slow --loop
```

---

## 📝 STORICO MODIFICHE

### 6 Gennaio 2026
- ✅ Implementato EMA Trend Filter (blocca contro-trend)
- ✅ Implementato ADX Filter (blocca ADX > 40)
- ✅ Implementato Early Exit for Bad Entry
- ✅ Spostato Symbol Cooldown pre-AI (risparmia token)
- ✅ Analisi completa MFE/MAE/Trade Quality

### 5 Gennaio 2026
- ✅ Implementato RSI Entry Filter
- ✅ Implementato Symbol Cooldown
- ✅ Analisi trade XRP (problema SHORT contro-trend)

### 4 Gennaio 2026
- Analisi iniziale problemi bot
- Identificato problema troppi VETO
- Identificato problema OBV troppo sensibile

---

*Ultimo aggiornamento: 6 Gennaio 2026*
