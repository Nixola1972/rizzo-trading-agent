# ISTRUZIONI OPERATIVE - Rizzo Trading Agent

## 1. DOPO MODIFICA .env

Quando modifichi parametri nel file `.env`, devi aggiornare i container:

```bash
cd /root/trading-bots/rizzo-trading-agent

# 1. Rebuild del bot (forza rilettura .env)
docker compose -f docker-compose.existing-postgres.yml build --no-cache trading-bot

# 2. Riavvia la dashboard
docker restart rizzo_dashboard

# 3. Verifica che i valori siano corretti
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python -c "
import os
print('TRAILING_STOP_PERCENT:', os.getenv('TRAILING_STOP_PERCENT'))
print('TRAILING_STOP_ACTIVATION_PERCENT:', os.getenv('TRAILING_STOP_ACTIVATION_PERCENT'))
print('INITIAL_STOP_LOSS_PERCENT:', os.getenv('INITIAL_STOP_LOSS_PERCENT'))
print('SCORE_THRESHOLD_CLOSE_REVERSAL:', os.getenv('SCORE_THRESHOLD_CLOSE_REVERSAL'))
print('SCORE_THRESHOLD_OPEN:', os.getenv('SCORE_THRESHOLD_OPEN'))
"
```

---

## 2. VERIFICA LOG

### Log del Bot Principale (cron ogni 15 min)
```bash
# Ultimi 50 righe
tail -50 /var/log/rizzo-trading-bot.log

# Segui in tempo reale
tail -f /var/log/rizzo-trading-bot.log
```

### Log del Sentinel (cron ogni 2 min)
```bash
# Ultimi 50 righe
tail -50 /var/log/sentinel.log

# Segui in tempo reale
tail -f /var/log/sentinel.log
```

### Log della Dashboard
```bash
docker logs rizzo_dashboard --tail 50

# Segui in tempo reale
docker logs -f rizzo_dashboard
```

### Verifica crontab attivo
```bash
crontab -l
```

Dovrebbe mostrare:
```
*/15 * * * * cd /root/trading-bots/rizzo-trading-agent && timeout 600 /usr/bin/docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> /var/log/rizzo-trading-bot.log 2>&1
*/2 * * * * cd /root/trading-bots/rizzo-trading-agent && docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python sentinel.py >> /var/log/sentinel.log 2>&1
```

---

## 3. COMANDI MANUALI

### Esegui bot manualmente
```bash
cd /root/trading-bots/rizzo-trading-agent
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python main.py
```

### Esegui sentinel manualmente
```bash
cd /root/trading-bots/rizzo-trading-agent
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python sentinel.py
```

### Vedi posizioni aperte
```bash
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python -c "
from hyperliquid_trader import HyperLiquidTrader
import os

bot = HyperLiquidTrader(
    secret_key=os.getenv('PRIVATE_KEY'),
    account_address=os.getenv('WALLET_ADDRESS'),
    testnet=os.getenv('TESTNET', 'true').lower() == 'true'
)
status = bot.get_account_status()
print('Balance:', status.get('balance_usd'))
print('Posizioni:', status.get('open_positions', []))
"
```

### Vedi tracking posizioni (trailing stop)
```bash
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "
SELECT symbol, direction, entry_price, peak_price, trailing_active, updated_at
FROM position_tracking;
"
```

### Vedi ultimi log sentinel dal DB
```bash
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "
SELECT created_at, symbol, profit_pct, trailing_active, action_taken
FROM sentinel_logs
ORDER BY created_at DESC
LIMIT 20;
"
```

---

## 4. DOPO RIAVVIO VPS

Dopo un riavvio del VPS, i container Docker NON ripartono automaticamente (a meno che non siano configurati con restart policy).

### Verifica cosa è attivo
```bash
docker ps -a
```

### Riavvia tutto manualmente
```bash
cd /root/trading-bots/rizzo-trading-agent

# 1. Avvia il database (se non è su un altro stack)
# docker start memory_postgres  # Solo se il DB è in questo stack

# 2. Riavvia la dashboard
docker start rizzo_dashboard

# Se la dashboard non esiste, ricreala:
docker run -d --name rizzo_dashboard \
  --network rizzo_trading_network \
  --network unified-memory-stack_memory-net \
  -p 8501:8501 \
  -v /root/trading-bots/rizzo-trading-agent:/app \
  -w /app \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  rizzo-trading-agent-trading-bot \
  streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0

# 3. Connetti la dashboard alla rete del DB
docker network connect unified-memory-stack_memory-net rizzo_dashboard
```

### Il cron riparte automaticamente?
**SI**, il cron è gestito dal sistema, non da Docker. Dopo il riavvio del VPS, il cron riprende automaticamente.

Verifica con:
```bash
crontab -l
systemctl status cron
```

---

## 5. CONFIGURAZIONE RESTART AUTOMATICO

Per far ripartire automaticamente la dashboard dopo riavvio VPS:

```bash
# Aggiorna il container con restart policy
docker update --restart unless-stopped rizzo_dashboard
```

Oppure ricrea con la policy:
```bash
docker stop rizzo_dashboard && docker rm rizzo_dashboard

docker run -d --name rizzo_dashboard \
  --restart unless-stopped \
  --network rizzo_trading_network \
  --network unified-memory-stack_memory-net \
  -p 8501:8501 \
  -v /root/trading-bots/rizzo-trading-agent:/app \
  -w /app \
  --env-file /root/trading-bots/rizzo-trading-agent/.env \
  rizzo-trading-agent-trading-bot \
  streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0

docker network connect unified-memory-stack_memory-net rizzo_dashboard
```

---

## 6. PARAMETRI .env PRINCIPALI

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `TRAILING_STOP_ENABLED` | true | Abilita/disabilita trailing stop |
| `TRAILING_STOP_PERCENT` | 7 | % di discesa dal peak per chiudere |
| `TRAILING_STOP_ACTIVATION_PERCENT` | 0 | % profitto per attivare trailing (0 = sempre attivo) |
| `INITIAL_STOP_LOSS_PERCENT` | 10 | Stop loss fisso prima dell'attivazione trailing |
| `SCORE_THRESHOLD_OPEN` | 16 | Score minimo per aprire posizione |
| `SCORE_THRESHOLD_CLOSE_REVERSAL` | 3 | Score inversione per permettere chiusura |
| `SENTINEL_ENABLED` | true | Abilita sentinel |
| `SENTINEL_INTERVAL_SECONDS` | 120 | Intervallo sentinel in loop mode |

---

## 7. TROUBLESHOOTING

### Dashboard non si connette al DB
```bash
# Connetti alla rete del DB
docker network connect unified-memory-stack_memory-net rizzo_dashboard
docker restart rizzo_dashboard
```

### Bot non legge i nuovi parametri .env
```bash
docker compose -f docker-compose.existing-postgres.yml build --no-cache trading-bot
```

### Tabelle DB mancanti
```bash
docker exec -it memory_postgres psql -U tradingbot -d rizzo_trading -c "
CREATE TABLE IF NOT EXISTS position_tracking (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol TEXT NOT NULL UNIQUE,
    direction TEXT NOT NULL,
    entry_price NUMERIC(30, 10) NOT NULL,
    peak_price NUMERIC(30, 10) NOT NULL,
    trailing_active BOOLEAN DEFAULT FALSE,
    last_checked_price NUMERIC(30, 10)
);

CREATE TABLE IF NOT EXISTS sentinel_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price NUMERIC(30, 10) NOT NULL,
    current_price NUMERIC(30, 10) NOT NULL,
    peak_price NUMERIC(30, 10) NOT NULL,
    profit_pct NUMERIC(10, 4),
    profit_from_peak_pct NUMERIC(10, 4),
    trailing_active BOOLEAN DEFAULT FALSE,
    action_taken TEXT,
    action_reason TEXT
);
"
```

### Verificare stato container
```bash
docker ps -a | grep -E "rizzo|trading|dashboard"
```

---

## 8. URL ACCESSO

- **Dashboard**: http://[TUO-IP]:8501
- **Database**: postgresql://tradingbot:***@memory_postgres:5432/rizzo_trading

---

## 9. CHIUSURA MANUALE POSIZIONE

```bash
docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot python -c "
from hyperliquid_trader import HyperLiquidTrader
import os

bot = HyperLiquidTrader(
    secret_key=os.getenv('PRIVATE_KEY'),
    account_address=os.getenv('WALLET_ADDRESS'),
    testnet=os.getenv('TESTNET', 'true').lower() == 'true'
)

# Chiudi posizione specifica
result = bot.exchange.market_close('ETH')  # Cambia simbolo se necessario
print(result)
"
```
