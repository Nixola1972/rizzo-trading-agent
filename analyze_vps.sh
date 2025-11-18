#!/bin/bash
# ===========================================
# ANALISI VPS - Trova PostgreSQL esistente
# Esegui questo sul VPS: ./analyze_vps.sh
# ===========================================

echo "🔍 ANALISI CONTAINER DOCKER SUL VPS"
echo "========================================"
echo ""

# 1. Lista tutti i container
echo "📦 CONTAINER ATTIVI:"
echo ""
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 2. Trova PostgreSQL
echo "🔍 RICERCA POSTGRESQL:"
echo ""
POSTGRES_CONTAINERS=$(docker ps --format "{{.Names}}" | grep -iE "postgres|pg|database|db")

if [ -z "$POSTGRES_CONTAINERS" ]; then
    echo "❌ Nessun container PostgreSQL trovato tra i container attivi"
    echo ""
    echo "Cerco tra TUTTI i container (anche fermi)..."
    POSTGRES_CONTAINERS=$(docker ps -a --format "{{.Names}}" | grep -iE "postgres|pg|database|db")

    if [ -z "$POSTGRES_CONTAINERS" ]; then
        echo "❌ Nessun container PostgreSQL trovato"
        echo ""
        echo "Verifico se PostgreSQL è installato sul host..."
        if command -v psql &> /dev/null; then
            echo "✅ PostgreSQL trovato sul HOST (non in container)"
            psql --version
            systemctl status postgresql | head -5
        else
            echo "❌ PostgreSQL non trovato né in container né sul host"
        fi
    else
        echo "⚠️  Container PostgreSQL trovati ma FERMI:"
        echo "$POSTGRES_CONTAINERS"
    fi
else
    echo "✅ Container PostgreSQL trovati:"
    echo "$POSTGRES_CONTAINERS"
fi

echo ""
echo "========================================"
echo ""

# 3. Per ogni container postgres, mostra dettagli
if [ -n "$POSTGRES_CONTAINERS" ]; then
    for container in $POSTGRES_CONTAINERS; do
        echo "📊 DETTAGLI: $container"
        echo "----------------------------------------"

        # Nome e immagine
        echo "Nome:      $(docker inspect $container --format '{{.Name}}' | sed 's/\///')"
        echo "Immagine:  $(docker inspect $container --format '{{.Config.Image}}')"
        echo "Status:    $(docker inspect $container --format '{{.State.Status}}')"

        # Network
        echo "Network:   $(docker inspect $container --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')"

        # Porta
        PORT=$(docker inspect $container --format '{{range $p, $conf := .NetworkSettings.Ports}}{{$p}}{{end}}' | grep -oE '[0-9]+' | head -1)
        HOST_PORT=$(docker port $container 2>/dev/null | grep -oE '0.0.0.0:[0-9]+' | cut -d: -f2 | head -1)

        echo "Porta:     ${PORT:-N/A} (container) -> ${HOST_PORT:-N/A} (host)"

        # Variabili ambiente (solo quelle postgres)
        echo ""
        echo "Variabili ambiente PostgreSQL:"
        docker inspect $container --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -iE "POSTGRES|PG_" | head -10

        # Volume
        echo ""
        echo "Volumes:"
        docker inspect $container --format '{{range .Mounts}}{{.Type}}: {{.Source}} -> {{.Destination}}{{println}}{{end}}'

        echo ""
        echo "========================================"
        echo ""
    done
fi

# 4. Lista network Docker
echo "🌐 RETI DOCKER:"
echo ""
docker network ls
echo ""

# 5. Verifica docker-compose esistenti
echo "📄 FILE DOCKER-COMPOSE ESISTENTI:"
echo ""
find /root /home /opt -name "docker-compose.yml" -o -name "docker-compose.yaml" 2>/dev/null | head -10
echo ""

echo "========================================"
echo "✅ ANALISI COMPLETATA"
echo ""
echo "📋 PROSSIMI STEP:"
echo ""
echo "1. Identifica il nome del container PostgreSQL dalla lista sopra"
echo "2. Annota:"
echo "   - Nome container (es: 'my_postgres_container')"
echo "   - Network (es: 'my_network')"
echo "   - Porta host (es: '5432' o '5433')"
echo ""
echo "3. Esegui sul container PostgreSQL:"
echo "   docker exec -it NOME_CONTAINER psql -U postgres -c '\l'"
echo "   (per vedere i database esistenti)"
echo ""
echo "4. Condividi queste informazioni per configurare il trading bot"
echo ""
