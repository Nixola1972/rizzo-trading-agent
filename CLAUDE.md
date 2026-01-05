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
- **Connection**: `postgresql://tradingbot:YOUR_PASSWORD@memory_postgres:5432/botone_baseline`

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

---

## 🔬 ANALISI APPROFONDITA LOG (4 Gennaio 2026 - Pomeriggio)

### Statistiche Decisioni (ultimi 10000 log)
| Decisione | Count | % |
|-----------|-------|---|
| **VETO** | 626+ | ~55% |
| HOLD | 202 | ~35% |
| CLOSE | 5 | <1% |
| **OPEN** | **0** | **0%** ❌ |

### Motivi VETO (Top 5)
| Motivo | Count | % dei VETO |
|--------|-------|------------|
| **OBV Divergence** | 156 | 25% |
| Volume < Tier-2 (0.8x) | ~300 | 48% |
| Volume < Tier-3 (1.0x) | ~100 | 16% |
| Volume < Tier-1 (0.5x) | ~70 | 11% |

### VETO per Simbolo (distribuiti uniformemente)
```
SUI: 39 | LINK: 39 | BNB: 37 | ARB: 35 | DOGE: 34
AVAX: 34 | SOL: 33 | XRP: 30 | ETH: 30 | BTC: 29 | ADA: 27
```

---

## 🐛 BUG/PROBLEMI NEL CODICE

### 1. OBV Divergence VETO Troppo Semplice (linea 363-370)
```python
# PROBLEMA: Usa solo change_1h, troppo sensibile
price_trend = "up" if market_data.get('change_1h', 0) > 0 else "down"
obv_opposite = (price_trend == "down" and obv_trend == "RISING")
if obv_opposite:
    return VETO  # Blocca anche con -0.01% e OBV RISING!
```

**Esempio dai log**:
- EMA Stack: bullish ✅
- Volume Ratio: 3.67x ✅ (ottimo!)
- OBV: RISING ✅
- Ma price change_1h: -0.1% → **VETO!** ❌

**Soluzione proposta**: Aggiungere soglia minima, es:
```python
if abs(change_1h) > 0.5 and obv_opposite:  # Solo se movimento > 0.5%
    return VETO
```

### 2. Threshold Troppo Alti per TIER 3
```python
# Configurazione attuale (linee 216-228)
"BTC":  {"tier": 1, "threshold": 60},   # OK
"ETH":  {"tier": 1, "threshold": 57},   # OK
"SOL":  {"tier": 2, "threshold": 74},   # Alto
"DOGE": {"tier": 3, "threshold": 114},  # TROPPO ALTO!
"AVAX": {"tier": 3, "threshold": 107},  # TROPPO ALTO!
```

**Dai log**:
```
AVAX: adjusted_score=66, threshold=107 → NO_TRADE (66 < 107)
ADA:  adjusted_score=50, threshold=74  → NO_TRADE
```

**Soluzione proposta**: Abbassare threshold TIER 3:
```python
"DOGE": {"tier": 3, "threshold": 80},   # Era: 114
"AVAX": {"tier": 3, "threshold": 75},   # Era: 107
```

### 3. Bug Parsing CLOSE (linee 960-961)
```python
# PROBLEMA: Se l'AI menziona "close" nel reasoning, viene parsato come azione CLOSE
elif "close" in content_lower or "sell" in content_lower:
    return {"action": "close", "reason": reason}
```

L'AI risponde `"action": "hold"` ma il log dice `AI → CLOSE` perché il reasoning contiene la parola "close".

---

## 🛠️ MODIFICHE PROPOSTE

### Opzione A: Configurazione Meno Restrittiva (Veloce)
```env
# .env.baseline modifiche
VOLUME_LOW_ACTION=WARN           # Era: VETO
VOLUME_MIN_TIER1=0.2             # Era: 0.5
VOLUME_MIN_TIER2=0.4             # Era: 0.8
VOLUME_MIN_TIER3=0.6             # Era: 1.0
```

### Opzione B: Modifiche al Codice (Consigliato)

#### B1. Ammorbidire OBV VETO
```python
# Aggiungere soglia minima per OBV divergence
change_1h = market_data.get('change_1h', 0)
if abs(change_1h) > 1.0 and obv_opposite:  # Solo se movimento > 1%
    # VETO solo per divergenze significative
```

#### B2. Abbassare Threshold TIER 3
```python
"DOGE": {"tier": 3, "multiplier": 0.70, "threshold": 80},   # Era: 114
"AVAX": {"tier": 3, "multiplier": 0.75, "threshold": 80},   # Era: 107
```

#### B3. Fixare Parsing CLOSE
```python
# Controllare prima il campo "action" esplicito, poi il contenuto
if parsed.get("action") == "close":
    return {"action": "close", ...}
# Solo dopo cercare parole chiave nel contenuto
```

---

## 🚀 PROSSIMI PASSI

1. [ ] **Decidere approccio**: Config (A) o Codice (B)
2. [ ] Implementare modifiche
3. [ ] Restart container
4. [ ] Monitorare per 24-48h
5. [ ] Verificare aumento trade
6. [ ] Analizzare P&L

---

## 📝 NOTE SESSIONE

- **Data analisi**: 4 Gennaio 2026
- **Container analizzati**: botone_v6_slow, botone_v6_fast
- **Problema principale**: Troppi VETO bloccano i trade
- **Soluzione proposta**: Ridurre restrizioni volume

---

*Ultimo aggiornamento: 4 Gennaio 2026*
