#!/bin/bash
# ===========================================
# FIX AI MODEL CONFIGURATION
# Risolve i problemi di JSON parsing con OpenRouter
# ===========================================

set -e

echo "🔧 FIX CONFIGURAZIONE AI MODEL"
echo "=============================="
echo ""

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ File .env non trovato!"
    echo "Assicurati di essere nella directory del progetto: ~/trading-bots/rizzo-trading-agent"
    exit 1
fi

echo "📝 Verifico configurazione attuale..."
echo ""

# Mostra configurazione corrente (senza mostrare le API keys)
if grep -q "AI_PROVIDER" "$ENV_FILE"; then
    CURRENT_PROVIDER=$(grep "^AI_PROVIDER=" "$ENV_FILE" | cut -d'=' -f2)
    echo "   AI_PROVIDER attuale: $CURRENT_PROVIDER"
else
    echo "   ⚠️  AI_PROVIDER non configurato"
fi

if grep -q "OPENROUTER_MODEL" "$ENV_FILE"; then
    CURRENT_MODEL=$(grep "^OPENROUTER_MODEL=" "$ENV_FILE" | cut -d'=' -f2)
    echo "   OPENROUTER_MODEL attuale: $CURRENT_MODEL"
else
    echo "   ℹ️  OPENROUTER_MODEL non configurato"
fi

echo ""
echo "🔄 Applicazione fix..."
echo ""

# Rimuovi eventuali configurazioni precedenti di AI_PROVIDER e OPENROUTER_MODEL
sed -i '/^AI_PROVIDER=/d' "$ENV_FILE"
sed -i '/^OPENROUTER_MODEL=/d' "$ENV_FILE"

# Aggiungi le configurazioni corrette alla fine del file
echo "" >> "$ENV_FILE"
echo "# ----- AI PROVIDER CONFIGURATION -----" >> "$ENV_FILE"
echo "AI_PROVIDER=openrouter" >> "$ENV_FILE"
echo "OPENROUTER_MODEL=anthropic/claude-3.5-sonnet" >> "$ENV_FILE"

echo "✅ Configurazione aggiornata!"
echo ""
echo "📋 Nuova configurazione:"
echo "   AI_PROVIDER=openrouter"
echo "   OPENROUTER_MODEL=anthropic/claude-3.5-sonnet"
echo ""
echo "🧪 TEST IMMEDIATO:"
echo "   docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot"
echo ""
echo "✅ Il bot ora userà Claude 3.5 Sonnet, che gestisce correttamente il JSON!"
echo ""
