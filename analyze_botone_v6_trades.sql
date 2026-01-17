-- ============================================================================
-- ANALISI BOTONE_V6 - Query per tabella botone_trades
-- ============================================================================
-- Esegui con: psql $DATABASE_URL -f analyze_botone_v6_trades.sql
-- ============================================================================

SELECT '=== SUMMARY GENERALE ===' AS info;

SELECT
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(COALESCE(SUM(pnl_usd) FILTER (WHERE pnl_usd > 0), 0) / NULLIF(ABS(SUM(pnl_usd) FILTER (WHERE pnl_usd < 0)), 0), 2) as profit_factor,
    ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl,
    ROUND(AVG(pnl_pct)::numeric, 3) as avg_pnl
FROM botone_trades
WHERE closed_at IS NOT NULL;

SELECT '=== EXIT REASONS ===' AS info;

SELECT
    exit_reason,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY exit_reason
ORDER BY total DESC;

SELECT '=== DIRECTION ===' AS info;

SELECT
    direction,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY direction
ORDER BY total DESC;

SELECT '=== SIMBOLI ===' AS info;

SELECT
    symbol,
    COUNT(*) as n,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY symbol
ORDER BY total DESC;

SELECT '=== MFE/MAE ===' AS info;

SELECT
    CASE WHEN pnl_pct > 0 THEN 'Winner' ELSE 'Loser' END as result,
    COUNT(*) as trades,
    ROUND(AVG(mfe_pct)::numeric, 2) as avg_mfe,
    ROUND(AVG(mae_pct)::numeric, 2) as avg_mae,
    ROUND(AVG(duration_seconds / 60.0)::numeric, 0) as avg_hold_min
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY CASE WHEN pnl_pct > 0 THEN 'Winner' ELSE 'Loser' END
ORDER BY result;

SELECT '=== HOLD TIME ===' AS info;

SELECT
    CASE
        WHEN duration_seconds / 60 < 30 THEN '0-30 min'
        WHEN duration_seconds / 60 < 60 THEN '30-60 min'
        WHEN duration_seconds / 60 < 90 THEN '60-90 min'
        ELSE '90+ min'
    END as hold_time,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY 1
ORDER BY
    CASE
        WHEN duration_seconds / 60 < 30 THEN 1
        WHEN duration_seconds / 60 < 60 THEN 2
        WHEN duration_seconds / 60 < 90 THEN 3
        ELSE 4
    END;

SELECT '=== ULTIMI 7 GIORNI ===' AS info;

SELECT
    DATE(closed_at) as giorno,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(SUM(pnl_usd)::numeric, 2) as pnl
FROM botone_trades
WHERE closed_at IS NOT NULL
  AND closed_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(closed_at)
ORDER BY giorno DESC;

SELECT '=== ULTIMI 15 TRADE ===' AS info;

SELECT
    symbol,
    direction,
    ROUND(pnl_pct::numeric, 2) as pnl_pct,
    ROUND(pnl_usd::numeric, 2) as pnl_usd,
    exit_reason,
    ROUND(duration_seconds / 60.0)::int as min,
    ROUND(mfe_pct::numeric, 2) as mfe,
    ROUND(mae_pct::numeric, 2) as mae,
    TO_CHAR(closed_at, 'DD/MM HH24:MI') as closed
FROM botone_trades
WHERE closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 15;

SELECT '=== OPEN POSITIONS ===' AS info;

SELECT
    symbol,
    direction,
    ROUND(entry_price::numeric, 6) as entry_price,
    leverage,
    ROUND(EXTRACT(epoch FROM (NOW() - opened_at))/60)::int as min_open,
    TO_CHAR(opened_at, 'DD/MM HH24:MI') as opened
FROM botone_trades
WHERE closed_at IS NULL
ORDER BY opened_at;

SELECT '=== CONVICTION TIER ANALYSIS ===' AS info;

SELECT
    conviction_tier as tier,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY conviction_tier
ORDER BY conviction_tier;

SELECT '=== PROMPT STYLE ANALYSIS ===' AS info;

SELECT
    prompt_style,
    COUNT(*) as trades,
    ROUND(COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_pct,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_usd)::numeric, 2) as total
FROM botone_trades
WHERE closed_at IS NOT NULL
GROUP BY prompt_style
ORDER BY total DESC;
