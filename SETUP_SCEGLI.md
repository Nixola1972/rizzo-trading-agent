# 🎯 QUALE SETUP SCEGLIERE?

Hai **2 opzioni** per installare il bot sul VPS:

---

## 🔵 OPZIONE 1: PostgreSQL Esistente (🏆 CONSIGLIATO per te)

**Usa il PostgreSQL che hai già sul VPS**

✅ **Vantaggi:**
- Non crea container duplicati
- Usa risorse già esistenti
- Nessun conflitto di porte
- Più pulito e organizzato

❌ **Svantaggi:**
- Richiede configurazione manuale della connessione
- Devi conoscere i dati del postgres esistente

### 🚀 Come procedere:

```bash
# 1. Analizza il VPS
./analyze_vps.sh

# 2. Crea database nel postgres esistente
./create_database.sh

# 3. Configura
cp .env.existing-postgres .env
nano .env  # Compila con i dati

# 4. Avvia
docker compose -f docker-compose.existing-postgres.yml up -d
```

📖 **Guida completa:** `SETUP_WITH_EXISTING_POSTGRES.md`

---

## 🟢 OPZIONE 2: PostgreSQL Nuovo e Isolato

**Crea un nuovo container PostgreSQL dedicato solo al bot**

✅ **Vantaggi:**
- Setup velocissimo (3 comandi)
- Tutto automatico
- Completamente isolato

❌ **Svantaggi:**
- Crea un nuovo container postgres (più risorse)
- Possibili conflitti di porta se 5433 è occupata

### 🚀 Come procedere:

```bash
# 1. Configura
cp .env.docker .env
nano .env  # Compila API keys

# 2. Avvia (tutto automatico)
docker compose up -d
```

📖 **Guida completa:** `QUICK_START.md` o `VPS_SETUP_GUIDE.md`

---

## 🤔 Quale scegliere?

### Scegli **OPZIONE 1** (Postgres Esistente) se:
- ✅ Hai già PostgreSQL sul VPS
- ✅ Vuoi risparmiare risorse
- ✅ Preferisci un setup pulito
- ✅ Non hai problemi a configurare manualmente

### Scegli **OPZIONE 2** (Postgres Nuovo) se:
- ✅ Vuoi il setup più veloce possibile
- ✅ Preferisci isolamento totale
- ✅ Non hai PostgreSQL o vuoi uno dedicato
- ✅ Hai risorse sufficienti sul VPS

---

## 📋 CONFRONTO COMPLETO

| Caratteristica | Opzione 1: Esistente | Opzione 2: Nuovo |
|---------------|---------------------|------------------|
| **Setup** | 4 step manuali | 2 step automatici |
| **Tempo setup** | 5-10 minuti | 2-3 minuti |
| **PostgreSQL** | Usa esistente | Crea nuovo container |
| **Porta** | Quella del tuo postgres | 5433 (dedicata) |
| **Network** | Network esistente | Nuova network isolata |
| **Risorse RAM** | ~50 MB (solo bot) | ~200 MB (bot + postgres) |
| **Isolamento** | Database separato | Container completamente isolato |
| **Manutenzione** | Usa backup esistente | Backup dedicato necessario |
| **Comando avvio** | `docker compose -f docker-compose.existing-postgres.yml up -d` | `docker compose up -d` |

---

## 💡 RACCOMANDAZIONE

**Per il tuo caso specifico (VPS con molti container):**

➡️ **USA OPZIONE 1** (PostgreSQL Esistente)

**Motivi:**
1. Hai già PostgreSQL → eviti duplicati
2. Rispetti l'architettura esistente
3. Meno risorse utilizzate
4. Più facile gestire backup (centralizzato)

---

## 🚀 QUICK START - Opzione 1 (per te)

```bash
ssh root@69.62.114.142

cd /opt/trading-bots
git clone https://github.com/Nixola1972/rizzo-trading-agent.git
cd rizzo-trading-agent

# Analizza VPS
./analyze_vps.sh
# Leggi output e annota: nome container postgres, network, porta

# Crea database
./create_database.sh
# Inserisci password quando richiesta
# Copia la CONNECTION STRING che ti viene mostrata

# Configura bot
cp .env.existing-postgres .env
nano .env
# Incolla connection string e compila API keys

# Avvia bot
docker compose -f docker-compose.existing-postgres.yml up -d

# Verifica
docker compose -f docker-compose.existing-postgres.yml logs -f trading-bot
```

---

## 📞 Hai dubbi?

**Esegui prima l'analisi:**
```bash
./analyze_vps.sh
```

Poi condividi l'output per ricevere supporto personalizzato!

---

**Sviluppato da Rizzo AI Academy** 🤖
