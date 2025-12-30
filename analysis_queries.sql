-- ============================================
-- ANALISI GRANULARE DURATA TRADE (5-7 minuti)
-- ============================================
-- Per capire il punto ottimale di chiusura

-- 1. GRANULARITÀ 1 MINUTO (4-8 min range)
SELECT
  CASE
    WHEN duration_seconds < 240 THEN '< 4 min'
    WHEN duration_seconds < 300 THEN '4-5 min'
    WHEN duration_seconds < 330 THEN '5.0-5.5 min'
    WHEN duration_seconds < 360 THEN '5.5-6.0 min'
    WHEN duration_seconds < 390 THEN '6.0-6.5 min'
    WHEN duration_seconds < 420 THEN '6.5-7.0 min'
    WHEN duration_seconds < 450 THEN '7.0-7.5 min'
    WHEN duration_seconds < 480 THEN '7.5-8.0 min'
    ELSE '> 8 min'
  END as duration_bucket,
  COUNT(*) as trades,
  COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades
WHERE status = 'CLOSED'
GROUP BY 1
ORDER BY
  CASE
    WHEN duration_seconds < 240 THEN 1
    WHEN duration_seconds < 300 THEN 2
    WHEN duration_seconds < 330 THEN 3
    WHEN duration_seconds < 360 THEN 4
    WHEN duration_seconds < 390 THEN 5
    WHEN duration_seconds < 420 THEN 6
    WHEN duration_seconds < 450 THEN 7
    WHEN duration_seconds < 480 THEN 8
    ELSE 9
  END;

-- 2. ANALISI PRECISA PER OGNI MINUTO (5-10)
SELECT
  FLOOR(duration_seconds / 60) as minute_bucket,
  COUNT(*) as trades,
  COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl,
  ROUND(AVG(CASE WHEN pnl_pct > 0 THEN pnl_pct END)::numeric, 3) as avg_win,
  ROUND(AVG(CASE WHEN pnl_pct <= 0 THEN pnl_pct END)::numeric, 3) as avg_loss
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds >= 300  -- Solo >= 5 min
  AND duration_seconds < 600   -- Solo < 10 min
GROUP BY FLOOR(duration_seconds / 60)
ORDER BY minute_bucket;

-- 3. PROFIT FACTOR PER BUCKET (rapporto win/loss)
SELECT
  CASE
    WHEN duration_seconds < 300 THEN '< 5 min'
    WHEN duration_seconds < 360 THEN '5-6 min'
    WHEN duration_seconds < 420 THEN '6-7 min'
    WHEN duration_seconds < 480 THEN '7-8 min'
    ELSE '> 8 min'
  END as duration_bucket,
  COUNT(*) as trades,
  ROUND(SUM(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE 0 END)::numeric, 2) as gross_profit,
  ROUND(ABS(SUM(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE 0 END))::numeric, 2) as gross_loss,
  ROUND(
    CASE
      WHEN ABS(SUM(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE 0 END)) > 0
      THEN SUM(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE 0 END) /
           ABS(SUM(CASE WHEN pnl_pct < 0 THEN pnl_pct ELSE 0 END))
      ELSE 999
    END::numeric, 2
  ) as profit_factor
FROM alpha_trades
WHERE status = 'CLOSED'
GROUP BY 1
ORDER BY profit_factor DESC;

-- 4. EDGE-CASE: Trade esattamente a 7 minuti (420s ± 30s)
SELECT
  symbol,
  direction,
  COUNT(*) as trades,
  COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds BETWEEN 390 AND 450  -- 6.5-7.5 minuti
GROUP BY symbol, direction
HAVING COUNT(*) >= 5
ORDER BY avg_pnl DESC;

-- 5. DISTRIBUZIONE ESATTA (istogramma)
SELECT
  duration_seconds / 60 as minutes,
  COUNT(*) as trades,
  STRING_AGG(
    CASE WHEN pnl_pct > 0 THEN '+' ELSE '-' END,
    ''
  ) as results_pattern
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds BETWEEN 300 AND 480
GROUP BY duration_seconds / 60
ORDER BY minutes;

-- 6. CONFRONTO: Trade chiusi a 6 min vs 7 min vs 8 min
WITH minute_groups AS (
  SELECT
    CASE
      WHEN duration_seconds BETWEEN 330 AND 390 THEN '6 min (±30s)'
      WHEN duration_seconds BETWEEN 390 AND 450 THEN '7 min (±30s)'
      WHEN duration_seconds BETWEEN 450 AND 510 THEN '8 min (±30s)'
    END as exact_minute,
    pnl_pct
  FROM alpha_trades
  WHERE status = 'CLOSED'
    AND duration_seconds BETWEEN 330 AND 510
)
SELECT
  exact_minute,
  COUNT(*) as trades,
  COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl,
  ROUND(STDDEV(pnl_pct)::numeric, 4) as std_dev
FROM minute_groups
WHERE exact_minute IS NOT NULL
GROUP BY exact_minute
ORDER BY exact_minute;

-- 7. CONFIDENZA vs DURATA (interazione)
SELECT
  CASE
    WHEN duration_seconds < 360 THEN '< 6 min'
    WHEN duration_seconds < 420 THEN '6-7 min'
    WHEN duration_seconds < 480 THEN '7-8 min'
    ELSE '> 8 min'
  END as duration,
  CASE
    WHEN policy_confidence >= 0.7 THEN 'HIGH'
    WHEN policy_confidence >= 0.5 THEN 'MEDIUM'
    ELSE 'LOW'
  END as confidence,
  COUNT(*) as trades,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl
FROM alpha_trades
WHERE status = 'CLOSED'
GROUP BY 1, 2
HAVING COUNT(*) >= 10
ORDER BY 1, 2;

-- 8. SIMBOLO × DURATA (quali simboli funzionano meglio in quale finestra)
SELECT
  symbol,
  CASE
    WHEN duration_seconds < 360 THEN '< 6 min'
    WHEN duration_seconds < 420 THEN '6-7 min'
    ELSE '> 7 min'
  END as duration,
  COUNT(*) as trades,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM alpha_trades
WHERE status = 'CLOSED'
GROUP BY symbol, 2
HAVING COUNT(*) >= 5
ORDER BY symbol, duration;

-- 9. BEST EXACT SECOND (cercare il secondo ottimale)
SELECT
  duration_seconds,
  COUNT(*) as trades,
  COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) as wins,
  ROUND(100.0 * COUNT(CASE WHEN pnl_pct > 0 THEN 1 END) / COUNT(*)::numeric, 1) as win_rate,
  ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl
FROM alpha_trades
WHERE status = 'CLOSED'
  AND duration_seconds BETWEEN 300 AND 480
GROUP BY duration_seconds
HAVING COUNT(*) >= 3
ORDER BY avg_pnl DESC
LIMIT 20;

-- 10. SUMMARY: Qual è il cutoff ottimale?
SELECT
  'CUTOFF TEST' as analysis,
  cutoff_minutes,
  trades_included,
  wins,
  ROUND(100.0 * wins / trades_included, 1) as win_rate,
  ROUND(total_pnl, 2) as total_pnl,
  ROUND(avg_pnl, 4) as avg_pnl
FROM (
  SELECT
    6.0 as cutoff_minutes,
    COUNT(*) as trades_included,
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
    SUM(pnl_pct) as total_pnl,
    AVG(pnl_pct) as avg_pnl
  FROM alpha_trades
  WHERE status = 'CLOSED' AND duration_seconds BETWEEN 300 AND 360

  UNION ALL

  SELECT
    6.5 as cutoff_minutes,
    COUNT(*),
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
    SUM(pnl_pct),
    AVG(pnl_pct)
  FROM alpha_trades
  WHERE status = 'CLOSED' AND duration_seconds BETWEEN 300 AND 390

  UNION ALL

  SELECT
    7.0 as cutoff_minutes,
    COUNT(*),
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
    SUM(pnl_pct),
    AVG(pnl_pct)
  FROM alpha_trades
  WHERE status = 'CLOSED' AND duration_seconds BETWEEN 300 AND 420

  UNION ALL

  SELECT
    7.5 as cutoff_minutes,
    COUNT(*),
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
    SUM(pnl_pct),
    AVG(pnl_pct)
  FROM alpha_trades
  WHERE status = 'CLOSED' AND duration_seconds BETWEEN 300 AND 450

  UNION ALL

  SELECT
    8.0 as cutoff_minutes,
    COUNT(*),
    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
    SUM(pnl_pct),
    AVG(pnl_pct)
  FROM alpha_trades
  WHERE status = 'CLOSED' AND duration_seconds BETWEEN 300 AND 480
) subq
ORDER BY cutoff_minutes;
