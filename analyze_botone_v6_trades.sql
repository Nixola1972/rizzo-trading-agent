-- ============================================================================
-- ANALISI TRADES BOTONE_V6 - Query specifica per tabella trades
-- ============================================================================
-- Esegui con: PGPASSWORD=xxx psql -h localhost -p 5432 -U tradingbot -d DATABASE_NAME -f analyze_botone_v6_trades.sql
-- IMPORTANTE: Cambia DATABASE_NAME e aggiungi filtro bot_name se necessario
-- ============================================================================

-- Se c'è un campo bot_name, decommentare e modificare il filtro:
-- WHERE bot_name = 'botone-v6'

SELECT 'info' AS info FROM (SELECT '=== SUMMARY GENERALE ===' AS info) t;

SELECT
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(COALESCE(SUM(pnl) FILTER (WHERE pnl > 0), 0) / NULLIF(ABS(SUM(pnl) FILTER (WHERE pnl < 0)), 0), 2) as profit_factor,
    ROUND(SUM(pnl)::numeric, 2) as total_pnl,
    ROUND(AVG(pnl)::numeric, 3) as avg_pnl
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
;

SELECT 'info' AS info FROM (SELECT '=== EXIT REASONS ===' AS info) t;

SELECT
    exit_reason,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl)::numeric, 2) as total
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
GROUP BY exit_reason
ORDER BY total DESC;

SELECT 'info' AS info FROM (SELECT '=== DIRECTION ===' AS info) t;

SELECT
    direction,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(SUM(pnl)::numeric, 2) as total
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
GROUP BY direction
ORDER BY total DESC;

SELECT 'info' AS info FROM (SELECT '=== SIMBOLI ===' AS info) t;

SELECT
    symbol,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl)::numeric, 2) as total
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
GROUP BY symbol
ORDER BY total DESC;

SELECT 'info' AS info FROM (SELECT '=== MFE/MAE ===' AS info) t;

SELECT
    CASE WHEN pnl > 0 THEN 'Winner' ELSE 'Loser' END as result,
    COUNT(*) as trades,
    ROUND(AVG(mfe)::numeric, 2) as avg_mfe,
    ROUND(AVG(mae)::numeric, 2) as avg_mae,
    ROUND(AVG(EXTRACT(epoch FROM (closed_at - opened_at))/60)::numeric, 0) as avg_hold_min
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
GROUP BY CASE WHEN pnl > 0 THEN 'Winner' ELSE 'Loser' END
ORDER BY result;

SELECT 'info' AS info FROM (SELECT '=== HOLD TIME ===' AS info) t;

SELECT
    CASE
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 30 THEN '0-30 min'
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 60 THEN '30-60 min'
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 90 THEN '60-90 min'
        ELSE '90+ min'
    END as hold_time,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(SUM(pnl)::numeric, 2) as total
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
GROUP BY 1
ORDER BY
    CASE
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 30 THEN 1
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 60 THEN 2
        WHEN EXTRACT(epoch FROM (closed_at - opened_at))/60 < 90 THEN 3
        ELSE 4
    END;

SELECT 'info' AS info FROM (SELECT '=== ULTIMI 7 GIORNI ===' AS info) t;

SELECT
    DATE(closed_at) as giorno,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / COUNT(*), 1) as win_pct,
    ROUND(SUM(pnl)::numeric, 2) as pnl
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
  AND closed_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(closed_at)
ORDER BY giorno DESC;

SELECT 'info' AS info FROM (SELECT '=== ULTIMI 15 TRADE ===' AS info) t;

SELECT
    symbol,
    direction,
    ROUND(pnl::numeric, 2) as pnl,
    exit_reason,
    ROUND(EXTRACT(epoch FROM (closed_at - opened_at))/60)::int as min,
    ROUND(mfe::numeric, 2) as mfe,
    ROUND(mae::numeric, 2) as mae,
    TO_CHAR(closed_at, 'DD/MM HH24:MI') as closed
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
ORDER BY closed_at DESC
LIMIT 15;

SELECT 'info' AS info FROM (SELECT '=== OPEN POSITIONS ===' AS info) t;

SELECT
    symbol,
    direction,
    entry_price,
    ROUND(EXTRACT(epoch FROM (NOW() - opened_at))/60)::int as min_open,
    TO_CHAR(opened_at, 'DD/MM HH24:MI') as opened
FROM trades
WHERE bot_name = 'botone-v6'  -- FILTRO PER BOTONE V6
  AND closed_at IS NULL
ORDER BY opened_at;
