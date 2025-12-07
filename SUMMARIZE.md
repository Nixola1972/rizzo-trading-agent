# SUMMARIZE.md - Storico Modifiche Rilevanti

Questo documento traccia le modifiche significative al sistema di trading.

---

## 2025-12-07: Smart Exit Optimizer v2

### Problema Risolto
Il sistema chiudeva posizioni troppo presto o troppo tardi, senza considerare:
- Fees reali (erano stimate 0.035%, in realtà sono 0.045% taker)
- Trend della posizione durante il trade
- Interazione con il sistema di trailing steps esistente

### Soluzione Implementata

**Smart Exit Optimizer** - Un sistema che lavora IN SINERGIA col trailing esistente:

```
NON chiude posizioni → Solo ACCELERA gli step del trailing quando il trend gira
```

#### Funzionalità:
1. **Calcolo P&L Netto Reale**
   - Fee apertura: 0.045% del notional
   - Fee chiusura: 0.045% del notional
   - Funding rate: fetched da API Hyperliquid (cache 5 min)
   - Net P&L = Gross P&L - fees - funding

2. **Analisi Trend Posizione**
   - Raccoglie ultimi 100 prezzi (SMART_EXIT_HISTORY_SIZE)
   - Calcola pendenza con regressione lineare
   - R² indica forza del trend (0-1)

3. **Decisione HOLD vs ACCELERATE**
   - HOLD: Trend ok, lascia che trailing faccia il suo lavoro
   - ACCELERATE: Trend invertito, anticipa prossimo step per proteggere profitto

#### Esempio Pratico:
```
TRAILING STEPS: 0.8:-2.0, 1.4:0.3, 2.2:1.0, 3.0:1.5, ...

Situazione:
- P&L attuale: +1.2%
- SL attuale: +0.3% (da step 1.4)
- Prossimo step: a +2.2% → SL +1.0%
- Trend: invertito (slope=-0.6)

Smart Exit decide: ACCELERATE
→ Sposta SL da +0.3% a +1.0% ADESSO
→ Se prezzo scende, salvi +0.7% in più!
```

#### File Modificati:
- `smart_exit.py` - Nuovo modulo (completa riscrittura)
- `sentinel.py` - Integrazione nel FAST loop
- `.env.example` - Documentazione parametri

#### Parametri .env:
```bash
SMART_EXIT_ENABLED=true           # Abilita il sistema
SMART_EXIT_HISTORY_SIZE=100       # Letture prezzo (100 × 3s = 5 min)
SMART_EXIT_TREND_WINDOW=30        # Finestra calcolo trend
SMART_EXIT_MIN_PROFIT=0.3         # % minimo per ACCELERATE
SMART_EXIT_ACCELERATE_CONFIDENCE=75  # Soglia confidence
SMART_EXIT_AI_ENABLED=false       # AI per casi dubbi
```

#### Come Verificare che Funziona:
Nei log del FAST loop appare:
```
[FAST] BTC: LONG P&L=+1.20% trailing=ACTIVE
   [SMART] BTC: ⚡ ACCELERATE (85%)
           🟢 Net: +1.05% | Gross: +1.20% | Fees: $0.45
           📉 Trend: -0.60 (R²=0.72) | Next@2.2%→SL 1.0%
           ⚡ ACCELERATE → SL a 1.0%
           💡 Trend invertito, anticipa step
```

Se vedi `[SMART]` nei log = sistema attivo.

---

## 2025-12-07: Fix SL Leverage Bug

### Problema
Lo Stop Loss veniva piazzato usando la leva di default (5x) invece della leva effettiva dall'AI.

### Causa
Le funzioni `place_micro_gain_sl_order` e `place_micro_pay_sl_order` non accettavano il parametro `leverage`.

### Fix
Aggiunto parametro `leverage` a entrambe le funzioni e passato `actual_leverage` nelle chiamate.

```python
# PRIMA (bug):
sl_price = place_micro_gain_sl_order(bot, symbol, direction, entry_price, size)
# Usava sempre MICRO_GAIN_LEVERAGE=5

# DOPO (fix):
sl_price = place_micro_gain_sl_order(bot, symbol, direction, entry_price, size, leverage=actual_leverage)
# Usa la leva effettiva dalla posizione
```

---

## 2025-12-07: Fix P&L Discrepancy Bug

### Problema
I log mostravano P&L diversi per la stessa posizione:
- MICRO_GAIN log: +4.60%
- FAST log: +3.65%
- SMART log: +3.68%

### Causa
La funzione `update_micro_gain_sl_order` usava `MICRO_GAIN_LEVERAGE` (costante da .env) invece della leva effettiva della posizione.

Se `.env` ha `MICRO_GAIN_LEVERAGE=5` ma AI sceglie 4x:
- MICRO_GAIN log: price_change × 5 = 4.60% (SBAGLIATO)
- FAST/SMART: price_change × 4 = 3.68% (CORRETTO)

### Fix
Aggiunto parametro `leverage` a `update_micro_gain_sl_order` e passata leva reale:

```python
# PRIMA (bug):
pnl_pct = price_change_pct * MICRO_GAIN_LEVERAGE  # Sempre da .env

# DOPO (fix):
actual_leverage = leverage if leverage is not None else MICRO_GAIN_LEVERAGE
pnl_pct = price_change_pct * actual_leverage  # Usa leva reale
```

---

## 2025-12-07: Fix entry_time Bug in Smart Exit

### Problema
Il tempo in posizione mostrava sempre "5m 0s" indipendentemente dalla durata reale.

### Causa
Il codice cercava `tracking_data.get("entry_time")` ma il campo nel DB è `created_at`.
Quando non trovava `entry_time`, usava default `time.time() - 300` (5 minuti).

### Fix
Corretto per cercare prima `created_at`, poi `entry_time` come fallback:

```python
# PRIMA (bug):
entry_time = tracking_data.get("entry_time")  # Campo non esiste!

# DOPO (fix):
entry_time = tracking_data.get("created_at") or tracking_data.get("entry_time")
# Con parsing corretto per stringhe ISO format
```

### Come Verificare
Nei log Smart Exit, il tempo in posizione ora riflette la durata reale:
```
⏱️ In posizione: 12m 45s  # Prima era sempre "5m 0s"
```

---

## 2025-12-07: Fix Direction Case-Sensitivity Bug

### Problema
Potenziale bug critico: il confronto `direction == "long"` falliva se Hyperliquid ritornava "Long" (maiuscolo).
Questo poteva causare calcoli SL errati (calcolati come SHORT invece di LONG).

### Causa
In diverse funzioni, `direction` veniva estratto senza `.lower()`:
```python
direction = pos.get("side", "")  # Poteva essere "Long" invece di "long"
```

### Fix
Aggiunto `.lower()` in tutte le estrazioni di direction:
- `_update_sl_for_position` (line 5032)
- `_handle_position_close` (line 5050)
- SLOW loop (line 4375)
- FAST loop (line 4893)

---

## 2025-12-07: Fix Duplicate SL Orders Bug

### Problema
Due funzioni di verifica SL (`run_order_verification` e `run_passive_sl_verification`) potevano entrambe rilevare "SL mancante" e piazzare ordini duplicati nello stesso ciclo FAST.

### Causa
Entrambe le funzioni cercavano SL mancanti e provavano a correggerli. A causa della latenza API, la seconda funzione poteva non vedere l'SL appena piazzato dalla prima.

### Fix
`run_passive_sl_verification` ora salta se `run_order_verification` ha appena corretto degli SL:

```python
verification_result = run_order_verification(bot, positions)
if verification_result.get("fixed", 0) == 0:
    run_passive_sl_verification(bot, positions)
else:
    log("🔍 Verifica SL passiva... (skip - SL appena corretti)")
```

---

## Template per Future Modifiche

```markdown
## YYYY-MM-DD: Nome Modifica

### Problema
[Descrizione del problema]

### Soluzione
[Descrizione della soluzione]

### File Modificati
- file1.py - descrizione
- file2.py - descrizione

### Come Verificare
[Come capire se funziona]
```
