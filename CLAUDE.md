# AlphaTrader 1H - Trading Bot Documentation

## Overview

AlphaTrader 1H is an RL-powered trading bot using Policy Network + Value Network + MCTS for 1-hour timeframe trading on HyperLiquid.

## Recent Changes (January 2026)

### v2_trailing_5x - Current Configuration

#### 1. Zombie Positions Fix (commit 1ad7449)
- **Problem**: After container restart, bot lost track of open positions
- **Solution**: Added `_load_open_positions_from_db()` to restore positions on startup
- **Files**: `alpha/trader_1h.py`, `alpha/db_1h.py`

#### 2. TIME STOP Implementation (commit 2ed7bda)
- **Problem**: Positions held >2h had negative PnL (-37.04 avg)
- **Solution**: Force close after `max_hold_minutes` (default 90min)
- **Analysis**: Golden zone 30-45min (+61.52), Death zone >2h (-37.04)

#### 3. ENV Configuration Refactoring (commit 934d98d)
- All trading parameters now configurable via ENV variables
- Added FAST/SLOW loop structure (30s monitoring, 300s decisions)

#### 4. Trailing Stop Implementation (commit c534174)
- **Logic**: Lock in profits when price drops from MFE
- **Activation**: When profit reaches `trailing_activate_pct`
- **Trigger**: When profit drops `trailing_distance_pct` from max

#### 5. 5x Leverage Scaling (commit cb1fea2)
- Increased leverage from 3x to 5x
- Scaled all TP/SL/trailing parameters proportionally
- Added `config_version` tracking

## Exit Priority

```
1. TIME STOP     - Force close after max_hold_minutes
2. STOP LOSS     - Emergency exit at fixed loss %
3. TRAILING STOP - Lock in profits when price drops from MFE
4. TAKE PROFIT   - Fixed profit target
5. SIGNAL        - AI model says CLOSE
```

## Configuration

### ENV Variables (see .env.alpha)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPHA_CONFIG_VERSION` | v2_trailing_5x | Config tracking |
| `ALPHA_MIN_HOLD_MINUTES` | 30 | Minimum hold time |
| `ALPHA_MAX_HOLD_MINUTES` | 90 | Time stop (force close) |
| `ALPHA_TAKE_PROFIT_PCT` | 1.5 | Take profit % |
| `ALPHA_STOP_LOSS_PCT` | 5.0 | Stop loss % |
| `ALPHA_TRAILING_ACTIVATE_PCT` | 0.8 | Trailing activation threshold |
| `ALPHA_TRAILING_DISTANCE_PCT` | 0.5 | Trailing distance from max |
| `ALPHA_POSITION_USD` | 25.0 | Position size in USD |
| `ALPHA_MAX_LEVERAGE` | 5 | Leverage multiplier |
| `ALPHA_SLOW_INTERVAL` | 300 | Decision loop interval (seconds) |

### MFE/MAE Analysis (basis for parameters)

Original analysis @ 3x leverage:
- Winner avg MFE: 0.98%
- Winner avg MAE: -0.39%
- Loser avg MAE: -1.66%
- Only 8% of trades reached MFE >= 2%

Scaled for 5x leverage:
- Same price movements = 1.67x higher PnL %
- Parameters adjusted proportionally

## Deployment

### Docker Build & Run

```bash
# Stop existing container
docker rm -f alpha_trader_1h

# Build
docker build -t alpha-trader .

# Run Paper Trading
docker run -d --name alpha_trader_1h \
  --network unified-memory-stack_memory-net \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env.alpha \
  -e TRADING_SYMBOLS="BTC,ETH,SOL,SUI,DOGE,LINK,PEPE,XRP,ADA,AVAX,WIF" \
  alpha-trader python -m alpha.trader_1h --mode paper --loop

# Check logs
docker logs -f alpha_trader_1h
```

### Production (subset of symbols)

```bash
docker run -d --name alpha_trader_1h \
  --network unified-memory-stack_memory-net \
  -v $(pwd)/alpha/checkpoints:/app/alpha/checkpoints \
  --env-file .env.alpha \
  -e TRADING_SYMBOLS="BTC,ETH" \
  alpha-trader python -m alpha.trader_1h --mode paper --loop
```

## Database Tables

- `alpha_trades_1h` - Trade records with MFE/MAE tracking
- `alpha_decisions_1h` - Every decision made by the model
- `alpha_equity_1h` - Equity curve snapshots

### Useful Queries

```sql
-- Performance by exit reason
SELECT exit_reason,
       COUNT(*) as trades,
       ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
       ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades_1h
WHERE status = 'CLOSED'
GROUP BY exit_reason;

-- MFE/MAE analysis
SELECT
  CASE WHEN pnl_pct > 0 THEN 'Winner' ELSE 'Loser' END as result,
  ROUND(AVG(mfe_pct)::numeric, 2) as avg_mfe,
  ROUND(AVG(mae_pct)::numeric, 2) as avg_mae
FROM alpha_trades_1h
WHERE status = 'CLOSED'
GROUP BY CASE WHEN pnl_pct > 0 THEN 'Winner' ELSE 'Loser' END;
```

## Files Structure

```
alpha/
├── trader_1h.py      # Main 1H trading bot
├── trader.py         # 15m trading bot
├── db_1h.py          # Database module for 1H
├── db.py             # Database module for 15m
├── config.py         # Configuration classes
├── policy_network.py # Policy network
├── value_network.py  # Value network
├── mcts.py           # Monte Carlo Tree Search
└── checkpoints/      # Model weights
```
