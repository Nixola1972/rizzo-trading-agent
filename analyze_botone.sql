-- ============================================================================
-- ANALISI BOTONE_V6 - Query per capire le performance del bot
-- ============================================================================
-- Esegui con: docker exec -i memory_postgres psql -U tradingbot -d botone_baseline < analyze_botone.sql
-- Oppure: PGPASSWORD=BotoneDB2025 psql -h localhost -p 5432 -U tradingbot -d botone_baseline -f analyze_botone.sql
-- ============================================================================

\echo '============================================================'
\echo '1. PANORAMICA GENERALE - Ultimi 7 giorni'
\echo '============================================================'

-- Totale operazioni per tipo
SELECT
    operation,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY operation
ORDER BY count DESC;

\echo ''
\echo '============================================================'
\echo '2. DISTRIBUZIONE OPERAZIONI PER SIMBOLO'
\echo '============================================================'

SELECT
    symbol,
    operation,
    direction,
    COUNT(*) as count,
    ROUND(AVG(leverage), 1) as avg_leverage,
    ROUND(AVG(target_portion_of_balance) * 100, 1) as avg_portion_pct
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
    AND operation != 'hold'
GROUP BY symbol, operation, direction
ORDER BY count DESC;

\echo ''
\echo '============================================================'
\echo '3. ANDAMENTO BILANCIO NEL TEMPO'
\echo '============================================================'

SELECT
    DATE(created_at) as date,
    ROUND(MIN(balance_usd)::numeric, 2) as min_balance,
    ROUND(MAX(balance_usd)::numeric, 2) as max_balance,
    ROUND(AVG(balance_usd)::numeric, 2) as avg_balance,
    COUNT(*) as snapshots
FROM account_snapshots
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date;

\echo ''
\echo '============================================================'
\echo '4. BILANCIO ATTUALE VS INIZIALE'
\echo '============================================================'

WITH first_last AS (
    SELECT
        (SELECT balance_usd FROM account_snapshots ORDER BY created_at ASC LIMIT 1) as first_balance,
        (SELECT balance_usd FROM account_snapshots ORDER BY created_at DESC LIMIT 1) as last_balance,
        (SELECT created_at FROM account_snapshots ORDER BY created_at ASC LIMIT 1) as first_date,
        (SELECT created_at FROM account_snapshots ORDER BY created_at DESC LIMIT 1) as last_date
)
SELECT
    ROUND(first_balance::numeric, 2) as starting_balance,
    ROUND(last_balance::numeric, 2) as current_balance,
    ROUND((last_balance - first_balance)::numeric, 2) as pnl_usd,
    ROUND(((last_balance - first_balance) / first_balance * 100)::numeric, 2) as pnl_pct,
    first_date::date as start_date,
    last_date::date as end_date,
    EXTRACT(days FROM (last_date - first_date)) as days_running
FROM first_last;

\echo ''
\echo '============================================================'
\echo '5. POSIZIONI APERTE ATTUALI'
\echo '============================================================'

SELECT
    op.symbol,
    op.side,
    ROUND(op.size::numeric, 4) as size,
    ROUND(op.entry_price::numeric, 2) as entry_price,
    ROUND(op.mark_price::numeric, 2) as mark_price,
    ROUND(op.pnl_usd::numeric, 2) as pnl_usd,
    op.leverage,
    s.created_at as snapshot_time
FROM open_positions op
JOIN account_snapshots s ON op.snapshot_id = s.id
WHERE s.id = (SELECT MAX(id) FROM account_snapshots);

\echo ''
\echo '============================================================'
\echo '6. FREQUENZA TRADING - Operazioni per ora del giorno'
\echo '============================================================'

SELECT
    EXTRACT(hour FROM created_at) as hour_utc,
    COUNT(*) FILTER (WHERE operation = 'open') as opens,
    COUNT(*) FILTER (WHERE operation = 'close') as closes,
    COUNT(*) FILTER (WHERE operation = 'hold') as holds
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(hour FROM created_at)
ORDER BY hour_utc;

\echo ''
\echo '============================================================'
\echo '7. RATIO HOLD vs TRADING'
\echo '============================================================'

SELECT
    DATE(created_at) as date,
    COUNT(*) FILTER (WHERE operation = 'hold') as holds,
    COUNT(*) FILTER (WHERE operation IN ('open', 'close')) as trades,
    ROUND(COUNT(*) FILTER (WHERE operation = 'hold')::numeric /
          NULLIF(COUNT(*) FILTER (WHERE operation IN ('open', 'close')), 0), 1) as hold_to_trade_ratio
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date;

\echo ''
\echo '============================================================'
\echo '8. ANALISI REASONS (Motivi decisioni AI)'
\echo '============================================================'

SELECT
    operation,
    symbol,
    direction,
    raw_payload->>'reason' as reason,
    created_at
FROM bot_operations
WHERE created_at > NOW() - INTERVAL '2 days'
    AND operation != 'hold'
ORDER BY created_at DESC
LIMIT 20;

\echo ''
\echo '============================================================'
\echo '9. SENTIMENT DURANTE DECISIONI'
\echo '============================================================'

SELECT
    sc.classification,
    sc.value as fear_greed_value,
    bo.operation,
    COUNT(*) as count
FROM bot_operations bo
JOIN ai_contexts ac ON bo.context_id = ac.id
JOIN sentiment_contexts sc ON sc.context_id = ac.id
WHERE bo.created_at > NOW() - INTERVAL '7 days'
GROUP BY sc.classification, sc.value, bo.operation
ORDER BY count DESC;

\echo ''
\echo '============================================================'
\echo '10. FORECAST ACCURACY - Previsioni vs Realtà'
\echo '============================================================'

SELECT
    fc.ticker,
    fc.timeframe,
    ROUND(AVG(fc.change_pct)::numeric, 3) as avg_predicted_change_pct,
    ROUND(AVG(fc.prediction - fc.last_price)::numeric, 2) as avg_predicted_move,
    COUNT(*) as forecasts_count
FROM forecasts_contexts fc
JOIN ai_contexts ac ON fc.context_id = ac.id
WHERE ac.created_at > NOW() - INTERVAL '7 days'
GROUP BY fc.ticker, fc.timeframe
ORDER BY fc.ticker, fc.timeframe;

\echo ''
\echo '============================================================'
\echo '11. INDICATORI QUANDO SI APRE POSIZIONE'
\echo '============================================================'

SELECT
    ic.ticker,
    bo.direction,
    ROUND(AVG(ic.rsi_7)::numeric, 1) as avg_rsi,
    ROUND(AVG(ic.macd)::numeric, 4) as avg_macd,
    ROUND(AVG(ic.price)::numeric, 2) as avg_entry_price,
    COUNT(*) as opens
FROM bot_operations bo
JOIN ai_contexts ac ON bo.context_id = ac.id
JOIN indicators_contexts ic ON ic.context_id = ac.id AND ic.ticker = bo.symbol
WHERE bo.operation = 'open'
    AND bo.created_at > NOW() - INTERVAL '7 days'
GROUP BY ic.ticker, bo.direction
ORDER BY opens DESC;

\echo ''
\echo '============================================================'
\echo '12. ERRORI RECENTI'
\echo '============================================================'

SELECT
    error_type,
    error_message,
    source,
    created_at
FROM errors
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT 10;

\echo ''
\echo '============================================================'
\echo '13. ULTIME 30 OPERAZIONI (NON HOLD)'
\echo '============================================================'

SELECT
    created_at,
    operation,
    symbol,
    direction,
    ROUND(target_portion_of_balance * 100, 1) as portion_pct,
    leverage,
    LEFT(raw_payload->>'reason', 80) as reason_truncated
FROM bot_operations
WHERE operation != 'hold'
ORDER BY created_at DESC
LIMIT 30;

\echo ''
\echo '============================================================'
\echo '14. CICLI DI TRADING - Apertura/Chiusura'
\echo '============================================================'

WITH opens AS (
    SELECT
        created_at as open_time,
        symbol,
        direction,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at) as trade_num
    FROM bot_operations
    WHERE operation = 'open'
),
closes AS (
    SELECT
        created_at as close_time,
        symbol,
        direction,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at) as trade_num
    FROM bot_operations
    WHERE operation = 'close'
)
SELECT
    o.symbol,
    o.direction,
    o.open_time,
    c.close_time,
    EXTRACT(epoch FROM (c.close_time - o.open_time))/3600 as duration_hours
FROM opens o
LEFT JOIN closes c ON o.symbol = c.symbol AND o.trade_num = c.trade_num
WHERE o.open_time > NOW() - INTERVAL '7 days'
ORDER BY o.open_time DESC
LIMIT 20;

\echo ''
\echo '============================================================'
\echo 'FINE ANALISI'
\echo '============================================================'
