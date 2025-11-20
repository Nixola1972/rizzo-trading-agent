#!/bin/bash
# ===========================================
# RIMUOVI CRON - Rizzo Trading Bot
# ===========================================

echo "🗑️  RIMOZIONE CRON JOB"
echo "===================="
echo ""

# Verifica se esiste
if crontab -l 2>/dev/null | grep -q "rizzo-trading-bot"; then
    # Rimuovi il cron job
    crontab -l 2>/dev/null | grep -v "rizzo-trading-bot" | grep -v "Rizzo Trading Bot" | crontab -
    echo "✅ Cron job rimosso con successo!"
else
    echo "ℹ️  Nessun cron job trovato"
fi

echo ""
echo "Cron jobs rimanenti:"
crontab -l 2>/dev/null || echo "  (nessuno)"
echo ""
