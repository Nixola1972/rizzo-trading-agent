# 🔬 Guida al Sistema di Backtesting e Ottimizzazione Pesi

## Indice
1. [Cos'è il Backtesting](#cosè-il-backtesting)
2. [Come Funziona](#come-funziona)
3. [Parametri Configurabili](#parametri-configurabili)
4. [Valori Consigliati](#valori-consigliati)
5. [Metriche di Performance](#metriche-di-performance)
6. [Modalità Operative](#modalità-operative)
7. [Uso da Command Line](#uso-da-command-line)
8. [Troubleshooting](#troubleshooting)

---

## Cos'è il Backtesting

Il **backtesting** è un sistema che ti permette di testare diverse configurazioni di pesi sui **dati storici** prima di applicarle al trading reale.

### Esempio pratico:
> "Se avessi usato `WEIGHT_RSI_OVERBOUGHT=12` invece di `15`, quale sarebbe stato il risultato?"

Il backtester risponde a questa domanda simulando tutti i trade che sarebbero stati eseguiti con quella configurazione.

### Vantaggi:
- ✅ Testa configurazioni **senza rischiare soldi reali**
- ✅ Confronta multiple configurazioni **contemporaneamente**
- ✅ Trova i **parametri ottimali** per il tuo stile di trading
- ✅ Usa dati **reali** da Yahoo Finance (BTC, ETH, SOL)

---

## Come Funziona

### Architettura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Yahoo Finance  │────▶│    Backtester    │────▶│    Risultati    │
│  (dati storici) │     │  (simulazione)   │     │  (performance)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │ Weight Optimizer │
                        │ (trova ottimali) │
                        └──────────────────┘
```

### Flusso di esecuzione:

1. **Download dati**: Scarica candele storiche da Yahoo Finance
2. **Calcolo indicatori**: EMA20, RSI14, MACD, ATR per ogni candela
3. **Simulazione trade**: Applica i pesi e simula aperture/chiusure
4. **Calcolo metriche**: Win rate, profit factor, P&L, ecc.
5. **Report**: Genera risultati e suggerimenti per .env

### File coinvolti:

| File | Descrizione |
|------|-------------|
| `backtester.py` | Motore di backtesting principale |
| `weight_optimizer.py` | Algoritmi di ottimizzazione (random, grid, genetic) |
| `dashboard.py` | Interfaccia web (tab "🔬 Backtesting") |

---

## Parametri Configurabili

### Pesi Bearish (segnali SHORT)

| Parametro | Variabile .env | Descrizione | Range |
|-----------|----------------|-------------|-------|
| RSI Overbought | `WEIGHT_RSI_OVERBOUGHT` | Peso quando RSI > 70 (ipercomprato) | 5-25 |
| Fear & Greed Fear | `WEIGHT_FEAR_GREED_FEAR` | Peso quando F&G < 30 (paura) | 4-15 |
| Trend Bearish | `WEIGHT_TREND_BEARISH` | Peso quando prezzo < EMA e MACD negativo | 5-15 |
| Forecast Negativo | `WEIGHT_FORECAST_NEGATIVE` | Peso quando previsione negativa | 3-12 |
| MACD Negativo | `WEIGHT_MACD_NEGATIVE` | Peso quando MACD < 0 | 2-10 |

### Pesi Bullish (segnali LONG)

| Parametro | Variabile .env | Descrizione | Range |
|-----------|----------------|-------------|-------|
| RSI Oversold | `WEIGHT_RSI_OVERSOLD` | Peso quando RSI < 30 (ipervenduto) | 5-25 |
| Fear & Greed Greed | `WEIGHT_FEAR_GREED_GREED` | Peso quando F&G > 60 (avidità) | 4-15 |
| Trend Bullish | `WEIGHT_TREND_BULLISH` | Peso quando prezzo > EMA e MACD positivo | 5-15 |
| Forecast Positivo | `WEIGHT_FORECAST_POSITIVE` | Peso quando previsione positiva | 3-12 |
| MACD Positivo | `WEIGHT_MACD_POSITIVE` | Peso quando MACD > 0 | 2-10 |

### Soglie Decisionali

| Parametro | Variabile .env | Descrizione | Range |
|-----------|----------------|-------------|-------|
| Score Threshold Open | `SCORE_THRESHOLD_OPEN` | Punteggio minimo per aprire posizione | 3-30 |
| Score Threshold Strong | `SCORE_THRESHOLD_STRONG` | Punteggio per segnale "forte" | 20-35 |

### Parametri Trading

| Parametro | Variabile .env | Descrizione | Range |
|-----------|----------------|-------------|-------|
| Take Profit | `TAKE_PROFIT_PERCENT` | % profitto per chiusura automatica | 1-20 |
| Stop Loss | `INITIAL_STOP_LOSS_PERCENT` | % perdita massima accettabile | 3-25 |
| Trailing Stop | `TRAILING_STOP_PERCENT` | % di ritracciamento dal peak | 4-12 |
| Trailing Activation | `TRAILING_STOP_ACTIVATION_PERCENT` | % profitto per attivare trailing | 2-6 |

---

## Valori Consigliati

### Configurazione Base (Bilanciata)

```bash
# Pesi BEARISH
WEIGHT_FEAR_GREED_FEAR=8
WEIGHT_RSI_OVERBOUGHT=15
WEIGHT_TREND_BEARISH=10
WEIGHT_FORECAST_NEGATIVE=6
WEIGHT_MACD_NEGATIVE=5

# Pesi BULLISH
WEIGHT_FEAR_GREED_GREED=8
WEIGHT_RSI_OVERSOLD=15
WEIGHT_TREND_BULLISH=10
WEIGHT_FORECAST_POSITIVE=6
WEIGHT_MACD_POSITIVE=5

# Soglie
SCORE_THRESHOLD_OPEN=10
SCORE_THRESHOLD_STRONG=25

# Trading
TAKE_PROFIT_PERCENT=5
INITIAL_STOP_LOSS_PERCENT=10
TRAILING_STOP_PERCENT=7
TRAILING_STOP_ACTIVATION_PERCENT=3
```

### Configurazione Conservativa (Meno trade, più selettivi)

```bash
WEIGHT_RSI_OVERBOUGHT=18
WEIGHT_RSI_OVERSOLD=18
SCORE_THRESHOLD_OPEN=18
TAKE_PROFIT_PERCENT=4
INITIAL_STOP_LOSS_PERCENT=8
```

### Configurazione Aggressiva (Più trade, più rischio)

```bash
WEIGHT_RSI_OVERBOUGHT=12
WEIGHT_RSI_OVERSOLD=12
SCORE_THRESHOLD_OPEN=8
TAKE_PROFIT_PERCENT=6
INITIAL_STOP_LOSS_PERCENT=12
```

---

## Metriche di Performance

### Metriche Principali

| Metrica | Descrizione | Valori Ideali |
|---------|-------------|---------------|
| **Win Rate** | % di trade chiusi in profitto | > 50% buono, > 60% ottimo |
| **Profit Factor** | Profitti totali / Perdite totali | > 1.5 buono, > 2.0 ottimo |
| **Total P&L** | Profitto/perdita totale nel periodo | Positivo! |
| **Total Trades** | Numero di trade eseguiti | Dipende dallo stile |

### Metriche Secondarie

| Metrica | Descrizione |
|---------|-------------|
| **Avg Win** | Media percentuale dei trade vincenti |
| **Avg Loss** | Media percentuale dei trade perdenti |
| **Max Win** | Miglior trade nel periodo |
| **Max Loss** | Peggior trade nel periodo |

### Come interpretare i risultati

1. **Profit Factor < 1**: Stai perdendo soldi. Cambia configurazione!
2. **Profit Factor 1-1.5**: Marginalmente profittevole, ma rischioso
3. **Profit Factor 1.5-2**: Buona configurazione
4. **Profit Factor > 2**: Ottima configurazione (ma verifica non sia overfitting)

### Attenzione all'Overfitting!

> ⚠️ **Overfitting** = configurazione che funziona perfettamente sui dati storici ma fallisce nel trading reale.

Per evitarlo:
- Non ottimizzare su periodi troppo brevi (< 14 giorni)
- Verifica che il numero di trade sia significativo (> 20)
- Testa su periodi diversi per confermare la robustezza

---

## Modalità Operative

### 1. Confronta Configurazioni (Manuale)

**Quando usarlo**: Vuoi testare configurazioni specifiche che hai in mente.

**Come funziona**:
1. Definisci 2-6 configurazioni diverse
2. Il sistema le testa tutte sui dati storici
3. Mostra una classifica ordinata per Profit Factor

**Configurazioni pre-impostate**:
- **Attuale (.env)**: I valori correnti del tuo file .env
- **Conservativa**: Meno trade, più selettivi, meno rischio
- **Aggressiva**: Più trade, più opportunità, più rischio

### 2. Ottimizzazione Automatica

**Quando usarlo**: Vuoi che il sistema trovi i valori ottimali.

**Metodi disponibili**:

| Metodo | Velocità | Qualità | Uso |
|--------|----------|---------|-----|
| 🎲 Random Search | ⭐⭐⭐ Veloce | ⭐⭐ Buona | Esplorazione iniziale |
| 📊 Grid Search | ⭐ Lento | ⭐⭐⭐ Completa | Test esaustivo |
| 🧬 Genetic Algorithm | ⭐⭐ Media | ⭐⭐⭐ Ottima | Spazi grandi |

**Consiglio**: Inizia con **Random Search** (50 iterazioni) per avere un'idea, poi usa **Genetic Algorithm** per raffinare.

---

## Uso da Command Line

### Test rapido

```bash
docker exec -it rizzo_dashboard python -c "
from backtester import Backtester, WeightsConfig

bt = Backtester(symbols=['BTC', 'ETH'], days=30, interval='15m')
bt.download_data()

config = WeightsConfig.from_env('Current')
result = bt.run(config)

print(f'Trades: {result.total_trades}')
print(f'Win Rate: {result.win_rate*100:.1f}%')
print(f'Profit Factor: {result.profit_factor:.2f}')
print(f'Total P&L: {result.total_pnl_pct:+.2f}%')
"
```

### Ottimizzazione completa

```bash
docker exec -it rizzo_dashboard python -c "
from backtester import Backtester
from weight_optimizer import WeightOptimizer

bt = Backtester(symbols=['BTC', 'ETH', 'SOL'], days=30, interval='15m')
bt.download_data()

optimizer = WeightOptimizer(bt)
result = optimizer.random_search(n_iterations=50)

print(result.summary())
print(optimizer.generate_report(result))
"
```

### Confronto configurazioni

```bash
docker exec -it rizzo_dashboard python -c "
from backtester import Backtester, WeightsConfig

bt = Backtester(symbols=['BTC', 'ETH'], days=30, interval='1h')
bt.download_data()

configs = [
    WeightsConfig.from_env('Current'),
    WeightsConfig(name='Conservative', score_threshold_open=18, take_profit_pct=4),
    WeightsConfig(name='Aggressive', score_threshold_open=8, take_profit_pct=6),
]

results = bt.compare_configs(configs)
print(bt.generate_report(results))
"
```

---

## Troubleshooting

### Errore: "yfinance not installed"

```bash
docker exec rizzo_dashboard pip install yfinance
docker restart rizzo_dashboard
```

### Errore: "No data for symbol"

- Verifica la connessione internet del container
- Yahoo Finance potrebbe essere temporaneamente non disponibile
- Prova con un intervallo diverso (1h invece di 15m)

### Errore: "StreamlitValueBelowMinError"

Il tuo .env ha valori fuori dai range della dashboard. Aggiorna la dashboard o modifica i valori nel .env.

### Risultati troppo ottimistici (Profit Factor > 5)

Probabilmente **overfitting**:
- Aumenta il periodo di test (60 giorni)
- Verifica che ci siano abbastanza trade (> 30)
- Testa su simboli diversi

### "No trades found" nella AI Strategy Analysis

**Questo è diverso dal backtesting!**

L'AI Strategy Analysis analizza i **tuoi trade reali** dal database. Se non hai trade chiusi, vedrai questo errore.

**Soluzioni**:
1. Aspetta che il sentinel chiuda alcune posizioni
2. Aumenta il periodo di analisi (60 giorni)
3. Usa il **Backtesting** che funziona sempre (usa dati Yahoo Finance)

---

## Differenza tra Backtesting e AI Strategy Analysis

| Aspetto | 🔬 Backtesting | 🧠 AI Strategy Analysis |
|---------|---------------|------------------------|
| **Dati** | Yahoo Finance (storici) | Database (tuoi trade) |
| **Scopo** | Testare configurazioni | Analizzare performance reale |
| **Requisiti** | Connessione internet | Trade chiusi nel DB |
| **Funziona sempre** | ✅ Sì | ❌ Solo con trade nel DB |

---

## Aggiornamenti VPS

Dopo ogni modifica, aggiorna il VPS:

```bash
cd ~/trading-bots/rizzo-trading-agent
git pull origin claude/improve-agent-analysis-01TDiREsQLHAhcv6V8Ko4yBr
docker restart rizzo_dashboard
```

---

## Changelog

### 2024-11-25
- ✅ Creato `backtester.py` - motore di backtesting
- ✅ Creato `weight_optimizer.py` - ottimizzazione automatica
- ✅ Integrato tab "🔬 Backtesting" nella dashboard
- ✅ Tradotto tutto in italiano
- ✅ Aggiunti valori "Consigliato" come riferimento
- ✅ Configurazioni pre-impostate (Conservativa, Aggressiva)
- ✅ Default intervallo 15m (stesso del bot)
- ✅ Migliorato messaggio errore "No trades found"

---

*Documentazione creata automaticamente. Per domande: controlla i log del container o apri un issue su GitHub.*
