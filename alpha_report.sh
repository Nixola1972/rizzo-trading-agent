#!/bin/bash
# ALPHA TRADER 1H - REPORT COMPLETO
# Esegui con: ./alpha_report.sh
# Config: v2_trailing_5x (SL=5%, TP=1.5%, Trailing=0.8%/0.5%)

docker exec memory_postgres psql -U tradingbot -d botone_baseline -c "
-- ============================================================
-- ALPHA TRADER 1H - REPORT COMPLETO
-- ============================================================

-- 1. SOMMARIO GENERALE
SELECT '=== SOMMARIO GENERALE ===' as section;
SELECT
  COUNT(*) as total_trades,
  SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as winners,
  SUM(CASE WHEN pnl_pct <= 0 THEN 1 ELSE 0 END) as losers,
  ROUND(100.0 * SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl,
  ROUND(AVG(CASE WHEN pnl_pct > 0 THEN pnl_pct END)::numeric, 2) as avg_win,
  ROUND(AVG(CASE WHEN pnl_pct <= 0 THEN pnl_pct END)::numeric, 2) as avg_loss
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED';

-- 2. PERFORMANCE PER EXIT REASON
SELECT '=== PER EXIT REASON ===' as section;
SELECT
  exit_reason,
  COUNT(*) as trades,
  SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
  ROUND(100.0 * SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
GROUP BY exit_reason
ORDER BY total_pnl DESC;

-- 3. PERFORMANCE PER SYMBOL
SELECT '=== PER SYMBOL ===' as section;
SELECT
  symbol,
  COUNT(*) as trades,
  ROUND(100.0 * SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
GROUP BY symbol
ORDER BY total_pnl DESC;

-- 4. MFE/MAE ANALYSIS (Winners vs Losers)
SELECT '=== MFE/MAE ANALYSIS ===' as section;
SELECT
  CASE WHEN pnl_pct > 0 THEN 'Winners' ELSE 'Losers' END as result,
  COUNT(*) as trades,
  ROUND(AVG(mfe_pct)::numeric, 2) as avg_mfe,
  ROUND(AVG(mae_pct)::numeric, 2) as avg_mae,
  ROUND(PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY mae_pct)::numeric, 2) as mae_p10,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mae_pct)::numeric, 2) as mae_median
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
GROUP BY CASE WHEN pnl_pct > 0 THEN 'Winners' ELSE 'Losers' END;

-- 5. RECOVERY ANALYSIS PER FASCIA MAE
SELECT '=== RECOVERY PER MAE RANGE ===' as section;
SELECT
  CASE
    WHEN mae_pct < -4 THEN '1. MAE < -4%'
    WHEN mae_pct < -3 THEN '2. MAE -4% to -3%'
    WHEN mae_pct < -2 THEN '3. MAE -3% to -2%'
    WHEN mae_pct < -1 THEN '4. MAE -2% to -1%'
    ELSE '5. MAE > -1%'
  END as mae_range,
  COUNT(*) as trades,
  SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as winners,
  ROUND(100.0 * SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
GROUP BY 1 ORDER BY 1;

-- 6. PERFORMANCE GIORNALIERA
SELECT '=== PER GIORNO ===' as section;
SELECT
  opened_at::date as date,
  COUNT(*) as trades,
  ROUND(100.0 * SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
GROUP BY opened_at::date
ORDER BY opened_at::date DESC
LIMIT 10;

-- 7. ULTIME 20 OPERAZIONI
SELECT '=== ULTIMI 20 TRADE ===' as section;
SELECT
  symbol,
  direction,
  ROUND(pnl_pct::numeric, 2) as pnl,
  ROUND(mfe_pct::numeric, 2) as mfe,
  ROUND(mae_pct::numeric, 2) as mae,
  exit_reason,
  opened_at::timestamp(0) as opened
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED'
ORDER BY closed_at DESC
LIMIT 20;

-- 8. PROFIT FACTOR
SELECT '=== PROFIT FACTOR ===' as section;
SELECT
  ROUND(SUM(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE 0 END)::numeric, 2) as gross_profit,
  ROUND(ABS(SUM(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE 0 END))::numeric, 2) as gross_loss,
  ROUND((SUM(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE 0 END) /
         NULLIF(ABS(SUM(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE 0 END)), 0))::numeric, 2) as profit_factor
FROM alpha_trades_1h
WHERE leverage = 5 AND status = 'CLOSED';
"
