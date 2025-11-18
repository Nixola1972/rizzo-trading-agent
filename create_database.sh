#!/bin/bash
# ===========================================
# CREA DATABASE nel PostgreSQL esistente
# ===========================================

set -e

echo "🗄️  CREAZIONE DATABASE RIZZO TRADING"
echo "========================================"
echo ""

# Parametri (modifica questi se necessario)
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-postgres}"
DB_NAME="${DB_NAME:-rizzo_trading}"
DB_USER="${DB_USER:-tradingbot}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Chiedi password se non impostata
if [ -z "$DB_PASSWORD" ]; then
    echo "Inserisci la password per l'utente '$DB_USER':"
    read -s DB_PASSWORD
    echo ""
fi

echo "📋 Configurazione:"
echo "  Container:  $POSTGRES_CONTAINER"
echo "  Admin user: $POSTGRES_ADMIN_USER"
echo "  DB name:    $DB_NAME"
echo "  DB user:    $DB_USER"
echo ""

# Verifica che il container esista
if ! docker ps --format "{{.Names}}" | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo "❌ Container '$POSTGRES_CONTAINER' non trovato!"
    echo ""
    echo "Container disponibili:"
    docker ps --format "{{.Names}}"
    echo ""
    echo "Riprova con:"
    echo "  POSTGRES_CONTAINER=nome_corretto ./create_database.sh"
    exit 1
fi

echo "✅ Container PostgreSQL trovato"
echo ""

# Crea utente e database
echo "📝 Creazione database e utente..."
docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_ADMIN_USER" <<EOF
-- Crea utente se non esiste
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
    END IF;
END
\$\$;

-- Crea database se non esiste
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

-- Grant privilegi
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

\c $DB_NAME

-- Grant privilegi sullo schema public
GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

-- Lista database
\l
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "✅ DATABASE CREATO CON SUCCESSO!"
    echo ""
    echo "📊 Informazioni connessione:"
    echo ""
    echo "  Database: $DB_NAME"
    echo "  User:     $DB_USER"
    echo "  Password: $DB_PASSWORD"
    echo ""
    echo "🔗 Connection String per il bot:"
    echo ""

    # Ottieni la network del container postgres
    NETWORK=$(docker inspect "$POSTGRES_CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' | head -1)

    if [ -n "$NETWORK" ]; then
        echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$POSTGRES_CONTAINER:5432/$DB_NAME"
        echo ""
        echo "⚠️  IMPORTANTE: Aggiungi il trading bot alla stessa network:"
        echo "  Network: $NETWORK"
    else
        # Fallback: usa host e porta host
        HOST_PORT=$(docker port "$POSTGRES_CONTAINER" 5432 2>/dev/null | grep -oE '[0-9]+$' | head -1)
        if [ -z "$HOST_PORT" ]; then
            HOST_PORT="5432"
        fi
        echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@host.docker.internal:$HOST_PORT/$DB_NAME"
    fi

    echo ""
    echo "📝 Copia questa connection string nel file .env"
    echo ""
else
    echo ""
    echo "❌ Errore durante la creazione del database"
    exit 1
fi
