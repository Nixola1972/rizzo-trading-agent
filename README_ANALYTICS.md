# 🧠 AI Strategy Controller - Guida Completa

Sistema di analisi performance e ottimizzazione automatica con AI.

## 📊 Cosa fa

### **1. Analytics Engine** (`analytics.py`)
Analizza le tue performance reali:
- ✅ Recupera tutti i trade da Hyperliquid (ultimi 30 giorni)
- ✅ Analisi "hindsight": cosa sarebbe successo se avessi chiuso dopo?
- ✅ Calcola: Win Rate, Profit Factor, Missed Opportunities
- ✅ Identifica pattern vincenti/perdenti per simbolo

### **2. AI Controller** (`strategy_controller.py`)
L'AI ragiona sui dati e suggerisce miglioramenti:
- 🤖 Analizza i numeri con GPT-4/DeepSeek/Claude
- 🎯 Suggerisce modifiche concrete ai parametri
- 📝 Genera report settimanali automatici
- 💡 Identifica cosa funziona e cosa no

---

## 🚀 Come Usare

### **Analisi Manuale (una volta a settimana)**

```bash
# Dentro il Docker container
docker exec -it trading-bot bash

# Esegui analisi completa
python strategy_controller.py --days 30
```

**Output:**
```
==================================================================
📊 PERFORMANCE ANALYSIS - Last 30 days
==================================================================

1️⃣  Fetching trade completati da Hyperliquid...
   ✅ 45 trade trovati

2️⃣  Analisi hindsight (cosa è successo dopo ogni close)...
   ✅ Analisi hindsight completata

3️⃣  Calcolo metriche...

==================================================================
📈 PERFORMANCE SUMMARY
==================================================================

Total Trades:        45
Win Rate:            58.0% (26W / 19L)
Profit Factor:       1.80

P&L:
  Total Profit:      $450.00
  Total Loss:        $250.00
  Net Profit:        $200.00

Average Trade:
  Avg Win:           +6.20%
  Avg Loss:          -4.10%
  Max Win:           +12.50%
  Max Loss:          -8.90%
  Avg Duration:      85 min

==================================================================
🎯 CLOSE QUALITY ANALYSIS
==================================================================

  EXCELLENT        12 trades ( 26.7%)
  GOOD              8 trades ( 17.8%)
  ACCEPTABLE       15 trades ( 33.3%)
  TOO_EARLY        10 trades ( 22.2%)

Missed Opportunities:
  Total:             125.0% cumulative
  Per Trade Avg:     2.78%

==================================================================
📊 PER-SYMBOL BREAKDOWN
==================================================================

BTC:
  Trades: 20, Win Rate: 65.0%, Profit Factor: 2.10, Net: $150.00
ETH:
  Trades: 18, Win Rate: 55.6%, Profit Factor: 1.60, Net: $80.00
SOL:
  Trades: 7, Win Rate: 28.6%, Profit Factor: 0.75, Net: -$30.00

==================================================================

==================================================================
🤖 AI STRATEGY CONTROLLER
==================================================================

🧠 Analisi AI in corso...
   Modello: deepseek/deepseek-r1

==================================================================
📋 AI ANALYSIS REPORT
==================================================================

## 🔍 DIAGNOSIS

**Strengths:**
- Win rate di 58% è sopra breakeven (good!)
- Profit Factor 1.8 indica trade profittevoli
- BTC performa molto bene (65% win rate, PF 2.1)

**Weaknesses:**
- 22% dei trade chiusi TOO EARLY (perso 2.78% medio per trade)
- SOL ha win rate disastroso (28.6%) e profit factor <1
- Missed opportunities totalizzano $125 = 62.5% del net profit!

## 🎯 TOP 3 PRIORITY SUGGESTIONS

### 1. AUMENTA TAKE_PROFIT_PERCENT: 5% → 7%
**Why:** L'analisi hindsight mostra che 80% delle volte il prezzo
continua a salire fino a +7.2% dopo il tuo take profit a 5%.

**Expected Impact:**
- Recuperi ~$125/mese di missed opportunities
- Win rate potrebbe scendere leggermente ma profit factor sale

**Risk:** Low - testato su dati reali

### 2. RIDUCI TRAILING_STOP_PERCENT: 7% → 4%
**Why:** Drawdown medio dal peak è solo 2.8%, quindi 7% è troppo largo.
Perdi profitto inutilmente aspettando troppo.

**Expected Impact:**
- +$50-80/mese chiudendo più vicino al peak
- Meno "TOO_LATE" closes

**Risk:** Medium - potrebbe aumentare falsi trailing stop

### 3. EVITA TRADING SU SOL (temporaneamente)
**Why:** Win rate 28.6% con profit factor 0.75 = loss sistematico.
Rimuovi SOL da all_tickers in main.py fino a nuovo setup.

**Expected Impact:**
- Risparmia $30-50/mese
- Focus su BTC/ETH (performano meglio)

**Risk:** None - SOL sta perdendo soldi

## 📝 RECOMMENDED .ENV CHANGES

```env
TAKE_PROFIT_PERCENT=7                      # was 5, reason: hindsight shows peak avg at 7.2%
TRAILING_STOP_PERCENT=4                    # was 7, reason: avg drawdown only 2.8%
TRAILING_STOP_ACTIVATION_PERCENT=4         # was 3, reason: align with new TP
```

## ⚠️ WARNINGS & RISKS

1. **Take Profit a 7%**: Potrebbe ridurre win rate del 5-10% ma aumenta
   profit per trade. Monitor per 1-2 settimane.

2. **Trailing Stop a 4%**: Più aggressivo. Se vedi troppi falsi stop,
   torna a 5%.

3. **SOL removal**: Controlla ogni 2 settimane se SOL cambia comportamento.

==================================================================

💾 Report salvato in: reports/strategy_analysis_2025-11-24_15-30-45.md

✅ Analysis complete!
```

---

## 📈 Metriche Spiegate

### **Win Rate**
Percentuale di trade vincenti.
- >60% = Eccellente
- 50-60% = Buono
- <50% = Problematico (a meno che profit factor > 2)

### **Profit Factor**
Rapporto profitti totali / perdite totali.
- >2.0 = Eccellente
- 1.5-2.0 = Buono
- <1.0 = Stai perdendo soldi!

### **Close Quality**
Quanto bene hai chiuso le posizioni:
- **EXCELLENT**: Chiuso vicino al peak (perso <1%)
- **GOOD**: Chiuso ok, prezzo poi è crollato
- **TOO_EARLY**: Perso >5% uscendo presto
- **TOO_LATE**: Aspettato troppo, prezzo è crollato

### **Missed Opportunity**
Quanto profitto hai lasciato sul tavolo chiudendo presto.
Esempio: chiuso a +5% ma peak era +8% = 3% missed.

---

## ⚙️ Configurazione Automatica

### **Cron Job Settimanale**

Aggiungi al crontab per analisi automatica ogni lunedì alle 9:00:

```bash
# Apri crontab
crontab -e

# Aggiungi questa linea
0 9 * * 1 cd /path/to/rizzo-trading-agent && docker exec trading-bot python strategy_controller.py --days 7 --silent
```

Riceverai un report in `reports/` ogni settimana.

---

## 🔧 Opzioni Avanzate

### **Cambia periodo analisi**
```bash
python strategy_controller.py --days 7   # Ultima settimana
python strategy_controller.py --days 60  # Ultimi 2 mesi
```

### **Solo analytics (senza AI)**
```bash
python analytics.py
```

### **Analizza specifico simbolo**
Modifica `analytics.py` per filtrare solo BTC/ETH/SOL.

---

## 📊 Esempio Report AI

I report vengono salvati in `reports/strategy_analysis_YYYY-MM-DD_HH-MM-SS.md`

Contengono:
1. **Diagnosis**: Cosa funziona, cosa no
2. **Top 3 Suggestions**: Modifiche prioritarie con impatto stimato
3. **Recommended .env Changes**: Esatto cosa modificare
4. **Warnings**: Potenziali rischi

---

## 🎯 Come Applicare i Suggerimenti

1. **Leggi il report** in `reports/`
2. **Modifica `.env`** con i parametri suggeriti
3. **Riavvia il bot** (i nuovi parametri vengono caricati)
4. **Monitora per 1 settimana** i risultati
5. **Ripeti analisi** e verifica miglioramenti

**Nota**: Non servono rebuild Docker - `.env` è montato come volume!

---

## 💡 Tips

- Esegui analisi **dopo chiusura posizioni** per dati completi
- Confronta report settimana su settimana per vedere progressi
- Se AI suggerisce cambio >30%, testa prima in testnet
- Tieni backup di `.env` prima di modifiche: `cp .env .env.backup`

---

## 🐛 Troubleshooting

### "No trade trovati"
- Verifica che ci siano trade chiusi su Hyperliquid
- Prova ad aumentare `--days`

### "Errore API Hyperliquid"
- Controlla PRIVATE_KEY e WALLET_ADDRESS in `.env`
- Verifica connessione internet

### "Errore AI"
- Verifica OPENROUTER_API_KEY in `.env`
- Controlla credito API su OpenRouter

---

## 🚀 Prossimi Step (Fase 3)

- [ ] Auto-apply suggestions (con conferma utente)
- [ ] A/B testing automatico (test 2 config in parallelo)
- [ ] Adaptive weights (AI cambia pesi automaticamente)
- [ ] Market regime detection (bull/bear/crab)
- [ ] Backtesting simulator

---

**Domande? Controlla i report generati in `reports/` per esempi concreti!**
