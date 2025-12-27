#!/bin/bash
set -e

case "$1" in
    "download-api")
        echo "📡 Downloading data via REST API..."
        python -m alpha.data_loader --source api --symbols BTC ETH --days ${DAYS:-60}
        ;;
    "download-s3")
        echo "📦 Downloading data via S3..."
        python -m alpha.data_loader --source s3 --symbols BTC ETH --days ${DAYS:-60}
        ;;
    "train")
        echo "🧠 Starting training..."
        echo "Episodes: ${EPISODES:-1000}"
        python -m alpha.trainer \
            --data-source hyperliquid \
            --episodes ${EPISODES:-1000} \
            --checkpoint-dir alpha/checkpoints
        ;;
    "trade-paper")
        echo "📝 Starting paper trading..."
        python -m alpha.trader --mode paper --loop
        ;;
    "trade-live")
        echo "🚀 Starting LIVE trading..."
        python -m alpha.trader --mode live --loop
        ;;
    "check")
        echo "🔍 Checking data sources..."
        python -m alpha.data_loader --check
        ;;
    "status")
        echo "📊 Checking training status..."
        if [ -f alpha/checkpoints/training_status.json ]; then
            cat alpha/checkpoints/training_status.json
        else
            echo "No training in progress"
        fi
        ;;
    *)
        echo "AlphaTrader Container"
        echo ""
        echo "Commands:"
        echo "  download-api  - Download data via REST API"
        echo "  download-s3   - Download data via S3 (more data)"
        echo "  train         - Start training"
        echo "  trade-paper   - Paper trading"
        echo "  trade-live    - Live trading"
        echo "  check         - Check data sources"
        echo "  status        - Check training status"
        echo ""
        echo "Environment variables:"
        echo "  DAYS=60       - Days of data to download"
        echo "  EPISODES=1000 - Training episodes"
        exec "$@"
        ;;
esac
