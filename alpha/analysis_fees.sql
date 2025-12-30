-- ============================================================
-- ANALISI SIMBOLI CON FEES - 5-7 MINUTI (Sweet Spot)
-- ============================================================
-- Assumendo:
-- - Position size: $25
-- - Fee per trade: ~0.1€ (0.2€ round trip open+close)
-- - Leva: 5x (quindi P&L sul notional $125)

-- 1. ANALISI BASE: P&L lordo vs netto per simbolo (5-7 min)
SELECT
    symbol,
    COUNT(*) as trades,
    COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
    ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
    ROUND(SUM(pnl_pct)::numeric, 2) as gross_pnl_pct,
    -- Fee totali: 0.2€ per trade
    ROUND((COUNT(*) * 0.2)::numeric, 2) as total_fees_eur,
    -- P&L lordo in EUR (pnl_pct sul notional $125, converti in EUR ~0.92)
    ROUND((SUM(pnl_pct) / 100.0 * 125 * 0.92)::numeric, 2) as gross_pnl_eur,
    -- P&L netto dopo fees
    ROUND(((SUM(pnl_pct) / 100.0 * 125 * 0.92) - (COUNT(*) * 0.2))::numeric, 2) as net_pnl_eur,
    ROUND(AVG(pnl_pct)::numeric, 3) as avg_pnl_pct
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds >= 300
  AND duration_seconds < 420
GROUP BY symbol
ORDER BY net_pnl_eur DESC;

-- 2. ANALISI PROFITTO PER TRADE dopo fees
SELECT
    symbol,
    COUNT(*) as trades,
    -- P&L medio per trade in EUR (lordo)
    ROUND((AVG(pnl_pct) / 100.0 * 125 * 0.92)::numeric, 3) as avg_gross_eur,
    -- Fee per trade
    0.2 as fee_per_trade_eur,
    -- P&L netto per trade
    ROUND(((AVG(pnl_pct) / 100.0 * 125 * 0.92) - 0.2)::numeric, 3) as avg_net_eur,
    -- Break-even P&L% richiesto per coprire fees (0.2€ / 1.15€ = 0.174%)
    ROUND(0.2 / (125 * 0.92) * 100, 3) as breakeven_pct,
    -- Quanto siamo sopra/sotto breakeven
    ROUND(AVG(pnl_pct)::numeric, 3) as actual_avg_pct,
    CASE
        WHEN AVG(pnl_pct) > 0.174 THEN '✅ PROFITTEVOLE'
        WHEN AVG(pnl_pct) > 0 THEN '⚠️ MARGINALE'
        ELSE '❌ IN PERDITA'
    END as status
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds >= 300
  AND duration_seconds < 420
GROUP BY symbol
ORDER BY avg_net_eur DESC;

-- 3. RACCOMANDAZIONE FINALE: Solo simboli con net positive
SELECT
    symbol,
    COUNT(*) as trades,
    ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
    ROUND(((SUM(pnl_pct) / 100.0 * 125 * 0.92) - (COUNT(*) * 0.2))::numeric, 2) as net_pnl_eur,
    ROUND(((AVG(pnl_pct) / 100.0 * 125 * 0.92) - 0.2)::numeric, 3) as net_per_trade_eur,
    CASE
        WHEN ((SUM(pnl_pct) / 100.0 * 125 * 0.92) - (COUNT(*) * 0.2)) > 5 THEN '🟢 TOP PICK'
        WHEN ((SUM(pnl_pct) / 100.0 * 125 * 0.92) - (COUNT(*) * 0.2)) > 0 THEN '🟡 INCLUDE'
        ELSE '🔴 EXCLUDE'
    END as recommendation
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds >= 300
  AND duration_seconds < 420
GROUP BY symbol
HAVING ((SUM(pnl_pct) / 100.0 * 125 * 0.92) - (COUNT(*) * 0.2)) > 0
ORDER BY net_pnl_eur DESC;

-- 4. CONFRONTO: Tutti i simboli vs solo top performers
WITH symbol_stats AS (
    SELECT
        symbol,
        SUM(pnl_pct) / 100.0 * 125 * 0.92 as gross_eur,
        COUNT(*) * 0.2 as fees_eur
    FROM alpha_trades
    WHERE status = 'CLOSED'
      AND duration_seconds >= 300
      AND duration_seconds < 420
    GROUP BY symbol
)
SELECT
    'TUTTI (11 simboli)' as strategy,
    SUM(gross_eur) as gross_total_eur,
    SUM(fees_eur) as fees_total_eur,
    ROUND((SUM(gross_eur) - SUM(fees_eur))::numeric, 2) as net_total_eur
FROM symbol_stats
UNION ALL
SELECT
    'SOLO TOP (net > 5€)' as strategy,
    SUM(gross_eur) as gross_total_eur,
    SUM(fees_eur) as fees_total_eur,
    ROUND((SUM(gross_eur) - SUM(fees_eur))::numeric, 2) as net_total_eur
FROM symbol_stats
WHERE (gross_eur - fees_eur) > 5
UNION ALL
SELECT
    'SOLO POSITIVI (net > 0€)' as strategy,
    SUM(gross_eur) as gross_total_eur,
    SUM(fees_eur) as fees_total_eur,
    ROUND((SUM(gross_eur) - SUM(fees_eur))::numeric, 2) as net_total_eur
FROM symbol_stats
WHERE (gross_eur - fees_eur) > 0;
