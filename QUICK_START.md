# ⚡ QUICK START - Installazione Veloce

## 🚀 Setup in 5 minuti sul VPS

### 1️⃣ Connettiti al VPS

```bash
ssh root@69.62.114.142
```

### 2️⃣ Clona il progetto

```bash
cd /opt
mkdir -p trading-bots
cd trading-bots
git clone https://github.com/TUO_USERNAME/rizzo-trading-agent.git
cd rizzo-trading-agent
```

### 3️⃣ Configura le API keys

```bash
# Copia il template
cp .env.docker .env

# Modifica con i tuoi dati
nano .env
```

**Compila questi campi:**
- `PRIVATE_KEY` - Dal tuo wallet Ethereum
- `WALLET_ADDRESS` - Indirizzo wallet
- `OPENAI_API_KEY` - Da OpenAI
- `CMC_PRO_API_KEY` - Da CoinMarketCap
- `POSTGRES_PASSWORD` - Password database (inventane una sicura)

**Salva:** CTRL+O, ENTER, CTRL+X

### 4️⃣ Avvia il bot

```bash
# Build e start
docker compose up -d

# Verifica che funzioni
docker compose ps
docker compose logs -f trading-bot
```

### 5️⃣ Fatto! 🎉

Il bot è attivo e isolato dal resto del sistema.

---

## 📊 Comandi Essenziali

```bash
# Log in tempo reale
docker compose logs -f trading-bot

# Restart
docker compose restart trading-bot

# Stop
docker compose down

# Aggiorna codice
./deploy.sh
```

---

## 🔧 Prima volta con Docker?

Installa Docker:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt-get install docker-compose-plugin -y
```

---

## 📖 Guida Completa

Vedi **VPS_SETUP_GUIDE.md** per documentazione dettagliata.

---

## ⚠️ IMPORTANTE

- Inizia con `TESTNET=true` nel file `.env`
- Monitora i log per almeno 24h prima di usare soldi veri
- Il trading crypto è ad alto rischio!
