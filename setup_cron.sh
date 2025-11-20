#!/bin/bash
# ===========================================
# SETUP CRON - Rizzo Trading Bot
# Esegue il bot ogni 15 minuti in TESTNET
# ===========================================

set -e

echo "⏰ CONFIGURAZIONE CRON - Trading Bot ogni 15 minuti"
echo "=================================================="
echo ""

# Percorso del progetto
PROJECT_DIR="/root/trading-bots/rizzo-trading-agent"
LOG_FILE="/var/log/rizzo-trading-bot.log"

# Verifica che il progetto esista
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Directory $PROJECT_DIR non trovata!"
    exit 1
fi

# Crea directory log se non esiste
mkdir -p /var/log
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

echo "📁 Directory progetto: $PROJECT_DIR"
echo "📝 Log file: $LOG_FILE"
echo ""

# Crea il comando cron
CRON_COMMAND="*/15 * * * * cd $PROJECT_DIR && /usr/bin/docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot >> $LOG_FILE 2>&1"

# Verifica se il cron esiste già
if crontab -l 2>/dev/null | grep -q "rizzo-trading-bot"; then
    echo "⚠️  Cron job già esistente. Lo rimuovo e lo ricreo..."
    crontab -l 2>/dev/null | grep -v "rizzo-trading-bot" | crontab -
fi

# Aggiungi il nuovo cron job
(crontab -l 2>/dev/null; echo "# Rizzo Trading Bot - Esecuzione ogni 15 minuti") | crontab -
(crontab -l 2>/dev/null; echo "$CRON_COMMAND") | crontab -

echo "✅ Cron job configurato!"
echo ""
echo "📋 Configurazione:"
echo "   Frequenza: Ogni 15 minuti"
echo "   Comando: docker compose run --rm trading-bot"
echo "   Log: $LOG_FILE"
echo ""
echo "🕐 Prossime esecuzioni (approssimate):"

# Mostra prossime 5 esecuzioni
current_min=$(date +%M)
current_hour=$(date +%H)

for i in {1..5}; do
    next_min=$((($current_min / 15 + $i) * 15 % 60))
    next_hour=$(($current_hour + ($current_min / 15 + $i) * 15 / 60))
    next_hour=$(($next_hour % 24))
    printf "   %2d:%02d\n" $next_hour $next_min
done

echo ""
echo "=================================================="
echo "✅ SETUP COMPLETATO!"
echo ""
echo "Comandi utili:"
echo "  • Vedi cron attivi:     crontab -l"
echo "  • Rimuovi cron:         crontab -r"
echo "  • Vedi log live:        tail -f $LOG_FILE"
echo "  • Vedi ultimi 50 log:   tail -50 $LOG_FILE"
echo "  • Test manuale:         cd $PROJECT_DIR && docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot"
echo ""
