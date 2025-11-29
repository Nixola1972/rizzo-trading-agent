# Trading Signal Weights - Guida Completa

## Panoramica

Il sistema di scoring calcola due valori principali:
- **SCORE_BULLISH**: Somma dei segnali che favoriscono LONG
- **SCORE_BEARISH**: Somma dei segnali che favoriscono SHORT
- **NET_SCORE** = SCORE_BULLISH - SCORE_BEARISH

### Decisione Finale
| Net Score | Azione | Spiegazione |
|-----------|--------|-------------|
| > +THRESHOLD_OPEN | **LONG** | Segnali bullish dominano |
| < -THRESHOLD_OPEN | **SHORT** | Segnali bearish dominano |
| Tra -THRESHOLD e +THRESHOLD | **HOLD** | Segnale troppo debole |

---

## Indicatori e Pesi

### 1. Fear & Greed Index

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `WEIGHT_FEAR_GREED_FEAR` | 8 | 5-12 | Peso quando F&G < 30 |
| `WEIGHT_FEAR_GREED_GREED` | 8 | 5-12 | Peso quando F&G > 60 |
| `FEAR_GREED_FEAR_THRESHOLD` | 30 | 25-40 | Soglia paura |
| `FEAR_GREED_GREED_THRESHOLD` | 60 | 55-70 | Soglia avidità |

**Come funziona:**
```
Se F&G = 20 (Fear):
  intensity = (30 - 20) / 30 = 0.33
  contribution = 8 × 0.33 = 2.64 punti BEARISH

Se F&G = 75 (Greed):
  intensity = (75 - 60) / 40 = 0.375
  contribution = 8 × 0.375 = 3.0 punti BULLISH
```

**Quando modificare:**
- Aumenta `WEIGHT_FEAR_GREED_FEAR` se vuoi più SHORT durante panic sell
- Diminuisci se vuoi ignorare il sentiment di mercato

---

### 2. RSI (Relative Strength Index)

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `WEIGHT_RSI_OVERBOUGHT` | 15 | 10-20 | Peso quando RSI > 70 |
| `WEIGHT_RSI_OVERSOLD` | 15 | 10-20 | Peso quando RSI < 30 |
| `RSI_OVERBOUGHT_THRESHOLD` | 70 | 65-80 | Soglia ipercomprato |
| `RSI_OVERSOLD_THRESHOLD` | 30 | 20-35 | Soglia ipervenduto |

**Perché peso alto (15)?**
RSI è uno degli indicatori più affidabili per identificare inversioni a breve termine:
- RSI > 70: Prezzo troppo alto, probabile correzione → **SHORT**
- RSI < 30: Prezzo troppo basso, probabile rimbalzo → **LONG**

**Come funziona:**
```
Se RSI = 80 (molto overbought):
  intensity = (80 - 70) / 30 = 0.33
  contribution = 15 × 0.33 = 5.0 punti BEARISH

Se RSI = 20 (molto oversold):
  intensity = (30 - 20) / 30 = 0.33
  contribution = 15 × 0.33 = 5.0 punti BULLISH
```

**Quando modificare:**
- Aumenta a 18-20 se vuoi che RSI domini la decisione
- Diminuisci a 10-12 se vuoi più bilanciamento con altri indicatori

---

### 3. Trend (EMA20 + MACD)

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `WEIGHT_TREND_BEARISH` | 10 | 8-15 | Prezzo < EMA20 AND MACD < 0 |
| `WEIGHT_TREND_BULLISH` | 10 | 8-15 | Prezzo > EMA20 AND MACD > 0 |
| `WEIGHT_MACD_NEGATIVE` | 5 | 3-8 | Solo MACD < 0 |
| `WEIGHT_MACD_POSITIVE` | 5 | 3-8 | Solo MACD > 0 |

**Logica:**
- **Trend confermato** (EMA + MACD concordi): Segnale forte, peso pieno
- **Segnale singolo** (solo MACD): Segnale debole, peso ridotto (50%)

**Esempio:**
```
Prezzo = 3300, EMA20 = 3350, MACD = -2.5

Prezzo < EMA20 ✓ AND MACD < 0 ✓
→ Trend BEARISH confermato
→ +10 punti BEARISH
```

---

### 4. Forecast (Prophet)

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `WEIGHT_FORECAST_NEGATIVE` | 6 | 4-10 | Previsione ribasso |
| `WEIGHT_FORECAST_POSITIVE` | 6 | 4-10 | Previsione rialzo |
| `FORECAST_MIN_CHANGE_PCT` | 0.3 | 0.2-0.5 | Minimo cambio % |

**Come funziona:**
```
Se Forecast = -1.2%:
  intensity = min(1.2 / 2.0, 1.0) = 0.6
  contribution = 6 × 0.6 = 3.6 punti BEARISH
```

**Nota:** Prophet è meno affidabile degli indicatori tecnici, quindi peso più basso.

---

### 5. Volume

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `WEIGHT_VOLUME_BEARISH` | 4 | 2-8 | Ask Vol > Bid Vol × 1.5 |
| `WEIGHT_VOLUME_BULLISH` | 4 | 2-8 | Bid Vol > Ask Vol × 1.5 |

**Logica:**
- Più compratori (bid) che venditori → Pressione rialzista
- Più venditori (ask) che compratori → Pressione ribassista

---

## Soglie Decisionali

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `SCORE_THRESHOLD_OPEN` | 15 | 10-20 | Minimo per aprire |
| `SCORE_THRESHOLD_STRONG` | 25 | 20-35 | Segnale forte |
| `SCORE_THRESHOLD_HOLD` | 10 | 5-15 | Troppo debole |

**Esempio pratico:**

| Net Score | Azione | Confidence |
|-----------|--------|------------|
| +30 | LONG | STRONG |
| +18 | LONG | NORMAL |
| +8 | HOLD | WEAK |
| -5 | HOLD | WEAK |
| -16 | SHORT | NORMAL |
| -28 | SHORT | STRONG |

---

## Esempi di Configurazione

### 1. Conservativa (meno trade, più sicura)
```env
SCORE_THRESHOLD_OPEN=20
SCORE_THRESHOLD_STRONG=30
WEIGHT_RSI_OVERBOUGHT=18
WEIGHT_RSI_OVERSOLD=18
MIN_MINUTES_BETWEEN_TRADES=60
```

### 2. Aggressiva (più trade, più rischio)
```env
SCORE_THRESHOLD_OPEN=12
SCORE_THRESHOLD_STRONG=20
WEIGHT_RSI_OVERBOUGHT=12
WEIGHT_RSI_OVERSOLD=12
MIN_MINUTES_BETWEEN_TRADES=15
```

### 3. RSI-Dominant (focalizzata su inversioni)
```env
WEIGHT_RSI_OVERBOUGHT=20
WEIGHT_RSI_OVERSOLD=20
WEIGHT_TREND_BEARISH=6
WEIGHT_TREND_BULLISH=6
WEIGHT_FEAR_GREED_FEAR=4
WEIGHT_FEAR_GREED_GREED=4
```

### 4. Trend-Following
```env
WEIGHT_TREND_BEARISH=15
WEIGHT_TREND_BULLISH=15
WEIGHT_RSI_OVERBOUGHT=8
WEIGHT_RSI_OVERSOLD=8
```

---

## Come Viene Calcolato lo Score

### Passo 1: Raccolta Dati
Per ogni coin (BTC, ETH, SOL):
- Prezzo corrente
- EMA20
- RSI (7 periodi)
- MACD
- Fear & Greed Index (globale)
- Forecast Prophet
- Volume Bid/Ask

### Passo 2: Calcolo Contributi
Ogni indicatore contribuisce in base a:
1. **Peso** (configurato in .env)
2. **Intensità** (quanto è estremo il valore)

```
Contributo = Peso × Intensità
```

### Passo 3: Somma Score
```
SCORE_BULLISH = Somma contributi LONG
SCORE_BEARISH = Somma contributi SHORT
NET_SCORE = SCORE_BULLISH - SCORE_BEARISH
```

### Passo 4: Decisione
```
if NET_SCORE >= THRESHOLD_OPEN:
    direction = "LONG"
elif NET_SCORE <= -THRESHOLD_OPEN:
    direction = "SHORT"
else:
    direction = "HOLD"
```

---

## Dashboard - Visualizzazione Score

Nella dashboard, tab "AI Decisions", vedrai:

| Campo | Descrizione |
|-------|-------------|
| Score Bullish | Punti totali a favore di LONG |
| Score Bearish | Punti totali a favore di SHORT |
| Net Score | Differenza (positivo = LONG, negativo = SHORT) |
| Direction | LONG / SHORT / HOLD |
| Confidence | STRONG / NORMAL / WEAK |
| Signals | Dettaglio di ogni indicatore con contributo |

---

## Troubleshooting

### "Il bot fa solo LONG"
- Verifica che `WEIGHT_*_BEARISH` non siano tutti a 0
- Controlla che `SCORE_THRESHOLD_OPEN` non sia troppo alto
- RSI potrebbe essere sempre sotto 70 (non overbought)

### "Il bot fa troppi trade"
- Aumenta `SCORE_THRESHOLD_OPEN` (es. da 15 a 20)
- Aumenta `MIN_MINUTES_BETWEEN_TRADES`
- Aumenta `MIN_PRICE_CHANGE_PCT`

### "Il bot non fa mai trade"
- Diminuisci `SCORE_THRESHOLD_OPEN` (es. da 15 a 12)
- Verifica che i pesi non siano troppo bassi
- Controlla i dati: RSI, MACD, ecc. potrebbero essere in range neutro

### "Troppi SHORT in bull market"
- Diminuisci `WEIGHT_FEAR_GREED_FEAR`
- Diminuisci `WEIGHT_RSI_OVERBOUGHT`
- Aumenta `FEAR_GREED_FEAR_THRESHOLD` (es. da 30 a 25)

---

## Risk Management

### MAX_POSITION_SIZE_PCT

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| `MAX_POSITION_SIZE_PCT` | 50 | 0-100 | Percentuale massima del portafoglio per singola operazione |

**Come funziona:**
```
Portafoglio = $100
MAX_POSITION_SIZE_PCT = 50

Massimo investimento per operazione = $100 × 50% = $50

Se l'AI richiede di aprire una posizione da $80:
→ Il bot riduce automaticamente a $50
→ Viene loggato nel terminale il ridimensionamento
```

**Esempio di configurazioni:**

| Valore | Profilo | Descrizione |
|--------|---------|-------------|
| 25 | Molto conservativo | Max 1/4 del portafoglio per trade |
| 50 | Bilanciato | Max metà del portafoglio per trade |
| 75 | Aggressivo | Max 3/4 del portafoglio per trade |
| 100 | Nessun limite | Può usare tutto il portafoglio |

**NOTA IMPORTANTE:** Questo limite si applica **PRIMA** della leva.
Se `MAX_POSITION_SIZE_PCT=50` e `leverage=3x`:
- Massimo capitale impiegato: 50% del portafoglio
- Esposizione effettiva: 150% del portafoglio (50% × 3)

---

## Note Tecniche

- I pesi vengono letti da `.env` all'avvio del bot
- Per applicare modifiche, riavviare il container
- Gli score vengono salvati nel database per ogni decisione
- Puoi vedere lo storico degli score nella dashboard
