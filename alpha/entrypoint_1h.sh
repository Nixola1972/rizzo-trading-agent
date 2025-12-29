#!/bin/bash
#
# AlphaTrader 1H Entrypoint
# =========================
#
# Container entrypoint for the 1-hour model.
# Completely independent from 15m model.
#
# Commands:
#   download    - Download 1h candles from Binance
#   train       - Train 1h model
#   trade-paper - Paper trading with 1h model
#   trade-live  - Live trading with 1h model (CAUTION!)

set -e

# Set interval to 1h for all operations
export ALPHA_INTERVAL="1h"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              AlphaTrader 1H Model                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

COMMAND=${1:-help}

case $COMMAND in
    download|download-1h)
        echo -e "${GREEN}📥 Downloading 1H candles from Binance...${NC}"

        # Default symbols (all 11)
        SYMBOLS=${SYMBOLS:-"BTC ETH SOL DOGE XRP BNB ADA AVAX LINK ARB SUI"}
        START_YEAR=${START_YEAR:-2017}
        DATA_TYPE=${DATA_TYPE:-"spot"}  # Use spot for 2017+ data (futures only from 2020)

        echo "   Symbols: $SYMBOLS"
        echo "   Start year: $START_YEAR"
        echo "   Data type: $DATA_TYPE (spot=2017+, futures=2020+)"
        echo "   Output: alpha/data/hourly/"

        python -m alpha.binance_data_loader \
            --symbols $SYMBOLS \
            --interval 1h \
            --start-year $START_YEAR \
            --data-type $DATA_TYPE \
            --output-dir alpha/data/hourly

        echo -e "${GREEN}✓ Download complete!${NC}"
        ;;

    train|train-1h)
        echo -e "${GREEN}🧠 Training 1H model...${NC}"

        EPISODES=${EPISODES:-10000}
        ENTROPY_COEF=${ENTROPY_COEF:-0.05}
        RESUME=${RESUME:-""}

        echo "   Episodes: $EPISODES"
        echo "   Entropy: $ENTROPY_COEF"
        echo "   Data dir: alpha/data/hourly/"

        RESUME_ARG=""
        if [ -n "$RESUME" ] && [ -f "$RESUME" ]; then
            RESUME_ARG="--resume $RESUME"
            echo "   Resuming from: $RESUME"
        fi

        python -m alpha.trainer_1h \
            --episodes $EPISODES \
            --entropy-coef $ENTROPY_COEF \
            --data-dir alpha/data/hourly \
            $RESUME_ARG

        echo -e "${GREEN}✓ Training complete!${NC}"
        ;;

    trade-paper|paper)
        echo -e "${GREEN}📄 Starting 1H paper trading...${NC}"
        python -m alpha.trader_1h --mode paper --loop
        ;;

    trade-live|live)
        echo -e "${RED}⚠️  LIVE TRADING - Real money at risk!${NC}"
        echo -e "${YELLOW}Starting in 10 seconds... Press Ctrl+C to cancel${NC}"
        sleep 10
        python -m alpha.trader_1h --mode live --loop
        ;;

    once)
        echo -e "${GREEN}🔄 Running single 1H trading cycle...${NC}"
        python -m alpha.trader_1h --mode paper --once
        ;;

    status)
        echo -e "${BLUE}📊 Checking 1H model status...${NC}"

        echo ""
        echo "=== Checkpoints ==="
        ls -la alpha/checkpoints/*1h* 2>/dev/null || echo "No 1h checkpoints found"

        echo ""
        echo "=== Training Data ==="
        ls -la alpha/data/hourly/*.parquet 2>/dev/null || echo "No 1h data found"
        ls -la alpha/data/hourly/*.pkl 2>/dev/null || echo "No 1h episodes found"

        echo ""
        echo "=== Database Tables ==="
        if [ -n "$DATABASE_URL" ]; then
            psql "$DATABASE_URL" -c "SELECT COUNT(*) as trades FROM alpha_trades_1h;" 2>/dev/null || echo "Table not found"
            psql "$DATABASE_URL" -c "SELECT COUNT(*) as decisions FROM alpha_decisions_1h;" 2>/dev/null || echo "Table not found"
        else
            echo "DATABASE_URL not set"
        fi
        ;;

    shell|bash)
        exec /bin/bash
        ;;

    help|*)
        echo ""
        echo "Usage: docker run alphatrader_1h <command>"
        echo ""
        echo "Commands:"
        echo "  download     Download 1h candles from Binance (all 11 symbols)"
        echo "  train        Train the 1h model"
        echo "  trade-paper  Start paper trading with 1h model"
        echo "  trade-live   Start live trading (DANGEROUS!)"
        echo "  once         Run single trading cycle"
        echo "  status       Show status of 1h model"
        echo "  shell        Open bash shell"
        echo ""
        echo "Environment variables:"
        echo "  SYMBOLS      Space-separated symbols (default: BTC ETH SOL ...)"
        echo "  START_YEAR   Year to start downloading (default: 2017)"
        echo "  EPISODES     Training episodes (default: 10000)"
        echo "  ENTROPY_COEF Entropy coefficient (default: 0.05)"
        echo "  RESUME       Path to checkpoint to resume from"
        echo ""
        echo "Examples:"
        echo "  docker run alphatrader_1h download"
        echo "  docker run alphatrader_1h train"
        echo "  docker run -d alphatrader_1h trade-paper"
        echo ""
        ;;
esac
