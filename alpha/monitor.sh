#!/bin/bash
# =============================================================================
# AlphaTrader Training Monitor
# =============================================================================
# Usage:
#   ./alpha/monitor.sh              # Mostra stato una volta
#   ./alpha/monitor.sh --watch      # Aggiorna ogni 5 secondi
#   ./alpha/monitor.sh --logs       # Mostra ultimi log del container
# =============================================================================

STATUS_FILE="alpha/checkpoints/training_status.json"
CONTAINER_NAME="alpha_training"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_status() {
    clear
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}              🧠 ALPHATRADER TRAINING MONITOR               ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Check if container is running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "Container: ${GREEN}● RUNNING${NC}"
    else
        echo -e "Container: ${RED}○ STOPPED${NC}"
    fi
    echo ""

    # Check if status file exists
    if [ -f "$STATUS_FILE" ]; then
        # Parse JSON with basic tools
        STATUS=$(grep -o '"status": *"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)
        EPISODE=$(grep -o '"episode": *[0-9]*' "$STATUS_FILE" | grep -o '[0-9]*')
        TOTAL=$(grep -o '"total_episodes": *[0-9]*' "$STATUS_FILE" | grep -o '[0-9]*')
        PROGRESS=$(grep -o '"progress_pct": *[0-9.]*' "$STATUS_FILE" | grep -o '[0-9.]*')
        WIN_RATE=$(grep -o '"win_rate": *[0-9.]*' "$STATUS_FILE" | grep -o '[0-9.]*')
        AVG_REWARD=$(grep -o '"avg_reward": *[-0-9.]*' "$STATUS_FILE" | grep -o '[-0-9.]*')
        AVG_PNL=$(grep -o '"avg_pnl": *[-0-9.]*' "$STATUS_FILE" | grep -o '[-0-9.]*')
        LAST_UPDATE=$(grep -o '"last_update": *"[^"]*"' "$STATUS_FILE" | cut -d'"' -f4)

        # Status color
        if [ "$STATUS" = "completed" ]; then
            echo -e "Status: ${GREEN}✅ COMPLETATO${NC}"
        elif [ "$STATUS" = "training" ]; then
            echo -e "Status: ${YELLOW}🔄 TRAINING...${NC}"
        else
            echo -e "Status: ${RED}❓ $STATUS${NC}"
        fi
        echo ""

        # Progress bar
        if [ -n "$PROGRESS" ]; then
            PROG_INT=${PROGRESS%.*}
            BAR_WIDTH=40
            FILLED=$((PROG_INT * BAR_WIDTH / 100))
            EMPTY=$((BAR_WIDTH - FILLED))

            printf "Progresso: ["
            printf "%${FILLED}s" | tr ' ' '█'
            printf "%${EMPTY}s" | tr ' ' '░'
            printf "] ${PROGRESS}%%\n"
        fi
        echo ""

        echo -e "${YELLOW}📊 STATISTICHE${NC}"
        echo "───────────────────────────────────────"
        printf "Episode:     %s / %s\n" "$EPISODE" "$TOTAL"
        printf "Win Rate:    %s%%\n" "$WIN_RATE"
        printf "Avg Reward:  %s\n" "$AVG_REWARD"
        printf "Avg P&L:     %s%%\n" "$AVG_PNL"
        echo "───────────────────────────────────────"
        echo ""
        echo -e "Ultimo aggiornamento: ${BLUE}$LAST_UPDATE${NC}"

    else
        echo -e "${RED}❌ File di stato non trovato${NC}"
        echo ""
        echo "Possibili cause:"
        echo "  1. Training non ancora iniziato"
        echo "  2. Container non avviato"
        echo "  3. Path errato"
        echo ""
        echo "Per avviare il training:"
        echo "  docker run -d --name alpha_training \\"
        echo "    -v \$(pwd)/alpha/data:/app/alpha/data \\"
        echo "    -v \$(pwd)/alpha/checkpoints:/app/alpha/checkpoints \\"
        echo "    alphatrader train"
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo "Comandi: q=esci | l=logs | r=refresh"
}

show_logs() {
    echo -e "${BLUE}📜 Ultimi 30 log del container...${NC}"
    echo ""
    docker logs --tail 30 "$CONTAINER_NAME" 2>/dev/null || echo "Container non trovato"
}

# Main
case "$1" in
    "--watch"|"-w")
        while true; do
            show_status
            echo ""
            echo -e "${YELLOW}Aggiornamento ogni 5 secondi... (Ctrl+C per uscire)${NC}"
            sleep 5
        done
        ;;
    "--logs"|"-l")
        show_logs
        ;;
    *)
        show_status
        ;;
esac
