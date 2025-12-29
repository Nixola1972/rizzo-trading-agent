#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              AlphaTrader 15m Model                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

case "$1" in
    "download-api")
        echo -e "${GREEN}📡 Downloading data via REST API...${NC}"
        python -m alpha.data_loader --source api --symbols BTC ETH --days ${DAYS:-60}
        ;;
    "download-s3")
        echo -e "${GREEN}📦 Downloading data via S3...${NC}"
        python -m alpha.data_loader --source s3 --symbols BTC ETH --days ${DAYS:-60}
        ;;
    "download-binance"|"download")
        echo -e "${GREEN}📥 Downloading 15m candles from Binance (optimized)...${NC}"

        # All 11 symbols
        SYMBOLS=${SYMBOLS:-"BTC ETH SOL DOGE XRP BNB ADA AVAX LINK ARB SUI"}
        START_YEAR=${START_YEAR:-2017}
        DATA_TYPE=${DATA_TYPE:-"spot"}  # Use spot for 2017+ data
        EPISODE_OVERLAP=${EPISODE_OVERLAP:-50}  # 50% overlap for more episodes

        echo "   Symbols: $SYMBOLS"
        echo "   Start year: $START_YEAR"
        echo "   Data type: $DATA_TYPE (spot=2017+, futures=2020+)"
        echo "   Episode overlap: $EPISODE_OVERLAP (optimized)"
        echo "   Output: alpha/data/"

        python -m alpha.binance_data_loader \
            --symbols $SYMBOLS \
            --interval 15m \
            --start-year $START_YEAR \
            --data-type $DATA_TYPE \
            --episode-overlap $EPISODE_OVERLAP \
            --output-dir alpha/data

        echo -e "${GREEN}✓ Download complete!${NC}"
        ;;
    "train")
        echo -e "${GREEN}🧠 Starting training...${NC}"
        EPISODES=${EPISODES:-10000}
        ENTROPY_COEF=${ENTROPY_COEF:-0.05}

        echo "   Episodes: $EPISODES"
        echo "   Entropy: $ENTROPY_COEF"

        python -m alpha.trainer \
            --data-source binance \
            --episodes $EPISODES \
            --entropy-coef $ENTROPY_COEF \
            --checkpoint-dir alpha/checkpoints
        ;;
    "trade-paper"|"paper")
        echo -e "${GREEN}📝 Starting paper trading...${NC}"
        python -m alpha.trader --mode paper --loop
        ;;
    "trade-live"|"live")
        echo -e "${RED}🚀 Starting LIVE trading...${NC}"
        echo -e "${YELLOW}Starting in 10 seconds... Press Ctrl+C to cancel${NC}"
        sleep 10
        python -m alpha.trader --mode live --loop
        ;;
    "check")
        echo -e "${BLUE}🔍 Checking data sources...${NC}"
        python -m alpha.data_loader --check
        ;;
    "status")
        echo -e "${BLUE}📊 Checking training status...${NC}"
        if [ -f alpha/checkpoints/training_status.json ]; then
            cat alpha/checkpoints/training_status.json
        else
            echo "No training in progress"
        fi

        echo ""
        echo "=== Checkpoints ==="
        ls -la alpha/checkpoints/*.pt 2>/dev/null || echo "No checkpoints found"
        ;;
    "shell"|"bash")
        exec /bin/bash
        ;;
    *)
        echo ""
        echo "Usage: docker run alphatrader <command>"
        echo ""
        echo "Commands:"
        echo "  download      - Download 15m candles from Binance (2017+, optimized)"
        echo "  train         - Train the model"
        echo "  trade-paper   - Paper trading"
        echo "  trade-live    - Live trading (DANGEROUS!)"
        echo "  status        - Check training status"
        echo "  shell         - Open bash shell"
        echo ""
        echo "Environment variables:"
        echo "  SYMBOLS       Space-separated symbols (default: all 11)"
        echo "  START_YEAR    Year to start from (default: 2017)"
        echo "  DATA_TYPE     spot or futures/um (default: spot)"
        echo "  EPISODES      Training episodes (default: 10000)"
        echo "  ENTROPY_COEF  Entropy coefficient (default: 0.05)"
        echo ""
        exec "$@"
        ;;
esac
