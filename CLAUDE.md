# CLAUDE.md - Analisi Botone V6 (4 Gennaio 2026)

---

## 📊 STATO ATTUALE DEL BOT

### Container in Esecuzione
```
botone_v6_slow  - AI decisions (SLOW loop ogni 3 min)
botone_v6_fast  - Position monitoring (FAST loop ogni 5s)
```

### Database
- **Host**: `memory_postgres`
- **Database**: `botone_baseline`
- **Tabella trade**: `botone_trades` (NON `bot_operations`)
- **Connection**: `postgresql://tradingbot:BotoneDB2025@memory_postgres:5432/botone_baseline`

---

## 🔴 PROBLEMI IDENTIFICATI (4 Gennaio 2026)

### 1. Pochissimi Trade
| Metrica | Valore | Problema |
|---------|--------|----------|
| Trade totali | 7 | Solo 7 in 10 giorni! |
| Ultimo trade | 29 Dicembre | 6 giorni senza trade |
| Trade/giorno | 0.7 | Troppo pochi |

### 2. Solo LONG, Mai SHORT
Tutti i 7 trade sono LONG. Il bot non apre mai posizioni SHORT.

### 3. P&L Minimo
| Trade | P&L USD | P&L % |
|-------|---------|-------|
| ETH 29 Dic | +$0.25 | +0.70% |
| BTC 29 Dic | +$0.15 | +0.61% |
| Altri 5 | $0.00 | LEGACY_UNTRACKED |

### 4. VETO Blocca Tutto
Il bot ha troppi filtri che bloccano i trade:
```
[RESEARCH] AVAX: 🚫 VETO: Volume 0.93x < 1.0x min for Tier-3
[RESEARCH] BTC: 🚫 VETO: Volume 0.52x < 1.5x
```

---

## 📈 DATI TRADE (da botone_trades)

### Ultimi 7 Trade Registrati
```sql
SELECT id, symbol, direction, opened_at, pnl_usd, pnl_pct, exit_reason
FROM botone_trades ORDER BY opened_at DESC;
```

| ID | Symbol | Dir | Data Apertura | P&L USD | P&L % | Exit |
|----|--------|-----|---------------|---------|-------|------|
| 7 | ETH | LONG | 29 Dic 09:57 | +0.25 | +0.70% | SYNC_CLOSED |
| 6 | BTC | LONG | 29 Dic 09:56 | +0.15 | +0.61% | SYNC_CLOSED |
| 5 | SOL | LONG | 26 Dic 15:01 | 0.00 | 0% | LEGACY_UNTRACKED |
| 4 | BTC | LONG | 26 Dic 08:13 | 0.00 | 0% | LEGACY_UNTRACKED |
| 3 | BTC | LONG | 26 Dic 08:08 | 0.00 | 0% | LEGACY_UNTRACKED |
| 2 | ETH | LONG | 26 Dic 07:59 | 0.00 | 0% | LEGACY_UNTRACKED |
| 1 | BTC | LONG | 25 Dic 20:33 | 0.00 | 0% | LEGACY_UNTRACKED |

### Bilancio Account
```
Start:   $162.23
Current: $160.79
P&L:     -$1.44 (-0.9%)
```

---

## ⚙️ CONFIGURAZIONE ATTUALE (Troppo Restrittiva)

### Filtri VETO (Bloccano i Trade)
```env
VOLUME_LOW_ACTION=VETO          # ❌ BLOCCA se volume basso
VOLUME_MIN_TIER1=0.5            # BTC/ETH: minimo 50% volume
VOLUME_MIN_TIER2=0.8            # SOL/XRP: minimo 80% volume
VOLUME_MIN_TIER3=1.0            # Altre: minimo 100% volume
```

### Requisiti TIER3 (Troppo Alti)
```env
TIER3_MIN_ADX=25                # ADX deve essere >= 25
TIER3_MIN_VOLUME_RATIO=1.2      # Volume ratio >= 1.2x
TIER3_MIN_SCORE_MARGIN=15       # Score margin >= 15
```

### BTC Entry VETO
```env
BTC_ENTRY_VETO_ENABLED=true
BTC_ENTRY_VETO_LONG_RSI=70      # Blocca LONG se BTC RSI >= 70
BTC_ENTRY_VETO_SHORT_RSI=30     # Blocca SHORT se BTC RSI <= 30
```

### Position Size
```env
TIER1_SIZE_USD=25               # Speculativo: $25
TIER2_SIZE_USD=35               # Standard: $35
TIER3_SIZE_USD=50               # High Conviction: $50
```

---

## ✅ RACCOMANDAZIONI PER MIGLIORARE

### 1. Riduci Restrizioni VETO
```env
# PROPOSTA: Cambia da VETO a WARN
VOLUME_LOW_ACTION=WARN          # Solo avviso, non blocca

# Abbassa i minimi
VOLUME_MIN_TIER1=0.3            # Era: 0.5
VOLUME_MIN_TIER2=0.5            # Era: 0.8
VOLUME_MIN_TIER3=0.8            # Era: 1.0
```

### 2. Riduci Requisiti TIER3
```env
TIER3_MIN_ADX=20                # Era: 25
TIER3_MIN_VOLUME_RATIO=1.0      # Era: 1.2
```

### 3. Aumenta Position Size (Opzionale)
```env
TIER1_SIZE_USD=50               # Era: 25
TIER2_SIZE_USD=75               # Era: 35
TIER3_SIZE_USD=100              # Era: 50
```

### 4. Considera Disabilitare BTC VETO
```env
BTC_ENTRY_VETO_ENABLED=false    # Permetti trade anche in zone estreme
```

---

## 🔧 QUERY UTILI

### Conta Trade per Stato
```sql
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE closed_at IS NULL) as open,
    COUNT(*) FILTER (WHERE closed_at IS NOT NULL) as closed,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl_pct,
    SUM(pnl_usd) as total_pnl
FROM botone_trades;
```

### Trade Oggi
```sql
SELECT * FROM botone_trades
WHERE opened_at > NOW() - INTERVAL '24 hours'
ORDER BY opened_at DESC;
```

### Vedi Posizioni Aperte su HyperLiquid (dal bot)
```bash
docker logs --tail 100 botone_v6_fast 2>&1 | grep -v "No open positions"
```

### Vedi Decisioni AI
```bash
docker logs --tail 200 botone_v6_slow 2>&1 | grep -E "(AI →|VETO|OPEN|CLOSE)"
```

### Conta VETO vs Trade
```bash
docker logs --tail 5000 botone_v6_slow 2>&1 | grep -c "VETO"
docker logs --tail 5000 botone_v6_slow 2>&1 | grep -c "OPEN"
```

---

## 📁 STRUTTURA DATABASE

### Tabelle Principali
| Tabella | Uso |
|---------|-----|
| `botone_trades` | Trade di Botone V6 (USARE QUESTA!) |
| `bot_operations` | Vecchio sistema (non più usato) |
| `account_snapshots` | Snapshot bilancio |
| `alpha_trades` | Trade di AlphaTrader (sistema RL) |

### Schema botone_trades
```sql
id, symbol, direction, opened_at, closed_at, duration_seconds,
entry_price, exit_price, size_usd, leverage, pnl_usd, pnl_pct,
max_price, min_price, mfe_pct, mae_pct, conviction_tier,
ai_confidence, ai_reasoning, prompt_style, entry_macd, entry_rsi,
entry_adx, entry_ema_stack, entry_volume_ratio, entry_bb_position,
entry_bb_squeeze, entry_obv_trend, exit_reason, sl_price, tp_price
```

---

## 🚀 PROSSIMI PASSI

1. [ ] Modificare configurazione per ridurre VETO
2. [ ] Testare con VOLUME_LOW_ACTION=WARN
3. [ ] Monitorare per 24-48h
4. [ ] Analizzare se aumentano i trade
5. [ ] Valutare aumento position size

---

## 📝 NOTE SESSIONE

- **Data analisi**: 4 Gennaio 2026
- **Container analizzati**: botone_v6_slow, botone_v6_fast
- **Problema principale**: Troppi VETO bloccano i trade
- **Soluzione proposta**: Ridurre restrizioni volume

---

*Ultimo aggiornamento: 4 Gennaio 2026*
