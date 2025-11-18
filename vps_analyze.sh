#!/bin/bash
# ===========================================
# ANALISI VPS - Esegui questo sul VPS come root
# ===========================================

echo "🔍 ANALISI CONFIGURAZIONE VPS"
echo "=================================="
echo ""

# Sistema operativo
echo "📌 Sistema Operativo:"
cat /etc/os-release | grep PRETTY_NAME
uname -r
echo ""

# Docker
echo "📌 Docker:"
if command -v docker &> /dev/null; then
    docker --version
    echo "✅ Docker installato"
else
    echo "❌ Docker NON installato"
fi
echo ""

# Docker Compose
echo "📌 Docker Compose:"
if command -v docker-compose &> /dev/null; then
    docker-compose --version
    echo "✅ docker-compose installato"
else
    echo "⚠️  docker-compose NON installato (proverò con 'docker compose')"
    if docker compose version &> /dev/null 2>&1; then
        docker compose version
        echo "✅ docker compose (v2) installato"
    fi
fi
echo ""

# Container attivi
echo "📌 Container Docker attivi:"
echo ""
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Nessun container attivo"
echo ""

# Tutti i container (anche fermi)
echo "📌 Tutti i container (inclusi quelli fermi):"
echo ""
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null
echo ""

# Reti Docker
echo "📌 Reti Docker:"
docker network ls 2>/dev/null
echo ""

# PostgreSQL
echo "📌 PostgreSQL:"
POSTGRES_CONTAINERS=$(docker ps -a --format "{{.Names}}" | grep -i postgres 2>/dev/null)
if [ -n "$POSTGRES_CONTAINERS" ]; then
    echo "✅ Container PostgreSQL trovati:"
    echo "$POSTGRES_CONTAINERS"
    for container in $POSTGRES_CONTAINERS; do
        echo ""
        echo "  Container: $container"
        echo "  Network: $(docker inspect $container --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
        echo "  Ports: $(docker inspect $container --format '{{range $p, $conf := .NetworkSettings.Ports}}{{$p}} {{end}}')"
    done
else
    echo "⚠️  Nessun container PostgreSQL trovato"
    echo "Cercando servizio PostgreSQL sul host..."
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        echo "✅ PostgreSQL installato sul host"
    fi
fi
echo ""

# Docker Compose files
echo "📌 File docker-compose esistenti:"
find /root /home -name "docker-compose.yml" -o -name "docker-compose.yaml" 2>/dev/null | head -10
echo ""

# Spazio disco
echo "📌 Spazio Disco:"
df -h / | tail -1
echo ""

# Memoria
echo "📌 Memoria:"
free -h
echo ""

# Porte in uso
echo "📌 Porte in uso (sample):"
ss -tlnp 2>/dev/null | grep LISTEN | head -15 || netstat -tlnp 2>/dev/null | grep LISTEN | head -15
echo ""

# Directory /root
echo "📌 Directory /root:"
ls -la /root/ | head -20
echo ""

echo "=================================="
echo "✅ Analisi completata!"
echo ""
echo "📋 Copia tutto l'output di questo script e condividilo"
echo "   per configurare il bot in modo isolato."
