#!/bin/bash
# ===========================================
# SETUP DEEPSEEK - Miglior modello 2025!
# ===========================================

set -e

echo "🚀 CONFIGURAZIONE DEEPSEEK V3.1"
echo "=============================="
echo ""
echo "DeepSeek V3.1 è il modello raccomandato per il trading bot:"
echo "  ✅ Performance eccellenti (paragonabile a GPT-4o)"
echo "  ✅ Economicissimo ($0.20/1M vs $5+/1M di GPT)"
echo "  ✅ Reasoning avanzato per decisioni complesse"
echo "  ✅ 128K context per analizzare tanti dati"
echo ""
echo "💰 Risparmio stimato: 95% rispetto a GPT-4o!"
echo ""

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ File .env non trovato!"
    echo "Assicurati di essere nella directory del progetto: ~/trading-bots/rizzo-trading-agent"
    exit 1
fi

echo "📝 Configurazione attuale:"
if grep -q "OPENROUTER_MODEL" "$ENV_FILE"; then
    CURRENT_MODEL=$(grep "^OPENROUTER_MODEL=" "$ENV_FILE" | cut -d'=' -f2)
    echo "   OPENROUTER_MODEL: $CURRENT_MODEL"
else
    echo "   ⚠️  OPENROUTER_MODEL non configurato"
fi
echo ""

# Chiedi all'utente quale versione vuole
echo "🔥 Scegli la versione DeepSeek:"
echo ""
echo "1) deepseek/deepseek-v3.1 (raccomandato!)"
echo "   - 671B parametri, 37B attivi"
echo "   - $0.20/1M input, $0.80/1M output"
echo "   - Best overall per trading"
echo ""
echo "2) deepseek/deepseek-r1"
echo "   - Reasoning avanzato"
echo "   - Paragonabile a OpenAI o1"
echo "   - Decisioni più ponderate"
echo ""
echo "3) deepseek/deepseek-r1:free"
echo "   - COMPLETAMENTE GRATUITO! 🎉"
echo "   - Performance eccellenti"
echo "   - Perfetto per testing"
echo ""
read -p "Scelta (1/2/3) [default: 1]: " choice
choice=${choice:-1}

case $choice in
    1)
        MODEL="deepseek/deepseek-v3.1"
        echo "✅ Hai scelto: DeepSeek V3.1 (raccomandato)"
        ;;
    2)
        MODEL="deepseek/deepseek-r1"
        echo "✅ Hai scelto: DeepSeek R1 (reasoning avanzato)"
        ;;
    3)
        MODEL="deepseek/deepseek-r1:free"
        echo "✅ Hai scelto: DeepSeek R1 Free (gratuito!)"
        ;;
    *)
        echo "❌ Scelta non valida. Uso default: deepseek/deepseek-v3.1"
        MODEL="deepseek/deepseek-v3.1"
        ;;
esac

echo ""
echo "🔄 Applicazione configurazione..."

# Backup del .env
cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
echo "   📦 Backup creato: ${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"

# Rimuovi configurazioni precedenti
sed -i '/^OPENROUTER_MODEL=/d' "$ENV_FILE"

# Assicurati che AI_PROVIDER sia openrouter
if grep -q "^AI_PROVIDER=" "$ENV_FILE"; then
    sed -i 's/^AI_PROVIDER=.*/AI_PROVIDER=openrouter/' "$ENV_FILE"
else
    # Aggiungi AI_PROVIDER se non esiste
    sed -i '/^# ----- AI PROVIDER/a AI_PROVIDER=openrouter' "$ENV_FILE"
fi

# Aggiungi il nuovo modello
echo "" >> "$ENV_FILE"
echo "# Model configurato da setup_deepseek.sh ($(date))" >> "$ENV_FILE"
echo "OPENROUTER_MODEL=$MODEL" >> "$ENV_FILE"

echo ""
echo "✅ Configurazione completata!"
echo ""
echo "📋 Nuova configurazione:"
echo "   AI_PROVIDER=openrouter"
echo "   OPENROUTER_MODEL=$MODEL"
echo ""

# Verifica che OPENROUTER_API_KEY sia configurata
if ! grep -q "^OPENROUTER_API_KEY=sk-or-v1-" "$ENV_FILE"; then
    echo "⚠️  ATTENZIONE: OPENROUTER_API_KEY non sembra configurata!"
    echo "   Assicurati di avere una API key valida nel file .env"
    echo ""
fi

echo "🧪 PROSSIMI PASSI:"
echo ""
echo "1. Rebuild container Docker:"
echo "   docker compose -f docker-compose.existing-postgres.yml build"
echo ""
echo "2. Test manuale:"
echo "   docker compose -f docker-compose.existing-postgres.yml run --rm trading-bot"
echo ""
echo "3. Se il test funziona, il cron userà automaticamente DeepSeek!"
echo ""
echo "📊 Output atteso (corretto):"
echo "   🤖 Usando OpenRouter con modello: $MODEL"
echo "   📝 Usando parsing JSON manuale"
echo "   ✅ Decisione AI: hold BTC - [reasoning dettagliato]"
echo ""
echo "💡 TIP: Monitora i log per le prime 24h:"
echo "   tail -f /var/log/rizzo-trading-bot.log"
echo ""
echo "✨ Buon trading con DeepSeek! 🚀"
echo ""
