# 🔗 Setup con PostgreSQL Esistente

Guida per collegare il trading bot a un container PostgreSQL già presente sul VPS.

---

## 📋 STEP 1: Analizza il tuo VPS

Esegui sul VPS:

```bash
ssh root@69.62.114.142

# Scarica il progetto se non l'hai già fatto
cd /opt/trading-bots
git clone https://github.com/Nixola1972/rizzo-trading-agent.git
cd rizzo-trading-agent

# Analizza i container esistenti
chmod +x analyze_vps.sh
./analyze_vps.sh
```

**Annota queste informazioni:**
- ✅ Nome del container PostgreSQL (es: `my_postgres`)
- ✅ Network Docker (es: `my_network`)
- ✅ Porta host (es: `5432` o `5433`)
- ✅ User admin postgres (di solito `postgres`)

---

## 📊 STEP 2: Crea il Database

Una volta identificato il container PostgreSQL, crea il database dedicato:

```bash
# Metodo 1: Script automatico
chmod +x create_database.sh

# Se il container si chiama "postgres"
./create_database.sh

# Se ha un altro nome
POSTGRES_CONTAINER=nome_tuo_container ./create_database.sh
```

**Lo script creerà:**
- Database: `rizzo_trading`
- User: `tradingbot`
- Password: quella che inserisci

**Copia la connection string** che ti viene mostrata!

### Metodo 2: Manuale

```bash
# Entra nel container postgres
docker exec -it NOME_CONTAINER psql -U postgres

# Esegui questi comandi SQL
CREATE USER tradingbot WITH PASSWORD 'tua_password_sicura';
CREATE DATABASE rizzo_trading OWNER tradingbot;
GRANT ALL PRIVILEGES ON DATABASE rizzo_trading TO tradingbot;

\c rizzo_trading
GRANT ALL ON SCHEMA public TO tradingbot;

\q
```

---

## ⚙️ STEP 3: Configura il Bot

```bash
# Copia il template per postgres esistente
cp .env.existing-postgres .env

# Modifica con i tuoi dati
nano .env
```

### Compila questi campi:

#### 🔗 DATABASE_URL

**Opzione A:** Se il bot è nella stessa Docker network del postgres:
```
DATABASE_URL=postgresql://tradingbot:password@nome_container_postgres:5432/rizzo_trading
```

**Opzione B:** Se usi la porta esposta sull'host:
```
DATABASE_URL=postgresql://tradingbot:password@host.docker.internal:5432/rizzo_trading
```

#### 🌐 POSTGRES_NETWORK

Inserisci il nome della network Docker del postgres (vedi output di `analyze_vps.sh`):
```
POSTGRES_NETWORK=nome_network_del_postgres
```

#### 🔑 API Keys

- `PRIVATE_KEY` - Wallet Ethereum
- `WALLET_ADDRESS` - Indirizzo wallet
- `OPENAI_API_KEY` - OpenAI API
- `CMC_PRO_API_KEY` - CoinMarketCap API

**Salva:** CTRL+O, ENTER, CTRL+X

---

## 🚀 STEP 4: Avvia il Bot

```bash
# Usa il docker-compose per postgres esistente
docker compose -f docker-compose.existing-postgres.yml up -d

# Verifica stato
docker compose -f docker-compose.existing-postgres.yml ps

# Controlla i log
docker compose -f docker-compose.existing-postgres.yml logs -f trading-bot
```

---

## 🔍 Verifica Connessione Database

```bash
# Verifica che il bot sia nella network giusta
docker inspect rizzo_trading_bot | grep -A 10 Networks

# Testa connessione al database dal bot
docker exec rizzo_trading_bot python3 -c "
import os
import psycopg2
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    print('✅ Connessione database OK!')
    conn.close()
except Exception as e:
    print(f'❌ Errore: {e}')
"
```

---

## 🔧 Troubleshooting

### Errore: "could not connect to server"

**Soluzione 1:** Verifica la network

```bash
# Network del postgres
docker inspect nome_postgres_container | grep NetworkMode

# Network del bot (deve essere la stessa)
docker inspect rizzo_trading_bot | grep NetworkMode

# Se diversa, modifica POSTGRES_NETWORK nel .env e riavvia
```

**Soluzione 2:** Usa host.docker.internal

Nel `.env` cambia:
```
DATABASE_URL=postgresql://tradingbot:password@host.docker.internal:PORTA/rizzo_trading
```

Dove `PORTA` è la porta esposta sull'host (vedi output `analyze_vps.sh`)

### Errore: "FATAL: password authentication failed"

```bash
# Verifica credenziali
docker exec -it nome_postgres_container psql -U tradingbot -d rizzo_trading -W

# Se non funziona, ricrea l'utente
docker exec -it nome_postgres_container psql -U postgres -c "ALTER USER tradingbot WITH PASSWORD 'nuova_password';"

# Aggiorna DATABASE_URL nel .env
```

### Errore: "database does not exist"

```bash
# Lista database esistenti
docker exec nome_postgres_container psql -U postgres -c "\l"

# Ricrea il database
./create_database.sh
```

---

## 📊 Comandi Utili

```bash
# Log bot
docker compose -f docker-compose.existing-postgres.yml logs -f trading-bot

# Restart bot
docker compose -f docker-compose.existing-postgres.yml restart trading-bot

# Stop bot
docker compose -f docker-compose.existing-postgres.yml down

# Query database
docker exec -it nome_postgres_container psql -U tradingbot -d rizzo_trading

# Vedi tabelle create dal bot
docker exec -it nome_postgres_container psql -U tradingbot -d rizzo_trading -c "\dt"
```

---

## 🆚 Differenza con Setup Standard

| Aspetto | Setup Standard | Con Postgres Esistente |
|---------|---------------|----------------------|
| PostgreSQL | Nuovo container | Usa container esistente |
| Network | Nuova isolata | Usa network esistente |
| Porta | 5433 dedicata | Porta esistente |
| Comando avvio | `docker compose up -d` | `docker compose -f docker-compose.existing-postgres.yml up -d` |
| Database | Dedicato e isolato | Database condiviso (ma separato) |

---

## ⚠️ Note Importanti

- ✅ Il bot crea le sue tabelle automaticamente nel database `rizzo_trading`
- ✅ Non tocca altri database nel postgres
- ✅ Completamente isolato dagli altri servizi
- ⚠️  Assicurati che la network sia corretta per evitare problemi di connessione
- 💡 Se hai dubbi, usa `host.docker.internal` con la porta esposta

---

## 🔄 Per Aggiornamenti

```bash
cd /opt/trading-bots/rizzo-trading-agent
git pull

# Rebuild e restart
docker compose -f docker-compose.existing-postgres.yml down
docker compose -f docker-compose.existing-postgres.yml build
docker compose -f docker-compose.existing-postgres.yml up -d
```

Oppure usa lo script (da modificare per il file compose giusto):

```bash
# Modifica deploy.sh e cambia
# "docker-compose" -> "docker compose -f docker-compose.existing-postgres.yml"

./deploy.sh
```

---

**Sviluppato da Rizzo AI Academy** 🤖
