#!/usr/bin/env python3
"""
Strategy Controller - AI-powered analytics e ottimizzazione

Usa AI (OpenAI/OpenRouter) per:
1. Analizzare performance del trading bot
2. Identificare pattern vincenti/perdenti
3. Suggerire modifiche concrete ai parametri
4. Generare report settimanali automatici
"""

import os
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import analytics

load_dotenv()

# AI Configuration
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openrouter').lower()

if AI_PROVIDER == 'openrouter':
    from openai import OpenAI
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-r1')

    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY mancante nel file .env")

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    MODEL = OPENROUTER_MODEL
else:
    from openai import OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-turbo')

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY mancante nel file .env")

    client = OpenAI(api_key=OPENAI_API_KEY)


def read_current_config() -> Dict[str, str]:
    """Legge la configurazione attuale dal .env"""
    load_dotenv()

    return {
        # Signal Scoring Weights
        'WEIGHT_RSI_OVERBOUGHT': os.getenv('WEIGHT_RSI_OVERBOUGHT', '15'),
        'WEIGHT_RSI_OVERSOLD': os.getenv('WEIGHT_RSI_OVERSOLD', '15'),
        'WEIGHT_TREND_BULLISH': os.getenv('WEIGHT_TREND_BULLISH', '10'),
        'WEIGHT_TREND_BEARISH': os.getenv('WEIGHT_TREND_BEARISH', '10'),
        'WEIGHT_FORECAST_POSITIVE': os.getenv('WEIGHT_FORECAST_POSITIVE', '6'),
        'WEIGHT_FORECAST_NEGATIVE': os.getenv('WEIGHT_FORECAST_NEGATIVE', '6'),
        'WEIGHT_MACD_POSITIVE': os.getenv('WEIGHT_MACD_POSITIVE', '5'),
        'WEIGHT_MACD_NEGATIVE': os.getenv('WEIGHT_MACD_NEGATIVE', '5'),
        'WEIGHT_VOLUME_BULLISH': os.getenv('WEIGHT_VOLUME_BULLISH', '4'),
        'WEIGHT_VOLUME_BEARISH': os.getenv('WEIGHT_VOLUME_BEARISH', '4'),
        'WEIGHT_FEAR_GREED_GREED': os.getenv('WEIGHT_FEAR_GREED_GREED', '8'),
        'WEIGHT_FEAR_GREED_FEAR': os.getenv('WEIGHT_FEAR_GREED_FEAR', '8'),

        # Thresholds
        'SCORE_THRESHOLD_OPEN': os.getenv('SCORE_THRESHOLD_OPEN', '15'),
        'SCORE_THRESHOLD_STRONG': os.getenv('SCORE_THRESHOLD_STRONG', '25'),
        'SCORE_THRESHOLD_CLOSE_REVERSAL': os.getenv('SCORE_THRESHOLD_CLOSE_REVERSAL', '10'),

        # Risk Management
        'TAKE_PROFIT_PERCENT': os.getenv('TAKE_PROFIT_PERCENT', '5'),
        'INITIAL_STOP_LOSS_PERCENT': os.getenv('INITIAL_STOP_LOSS_PERCENT', '10'),
        'TRAILING_STOP_PERCENT': os.getenv('TRAILING_STOP_PERCENT', '7'),
        'TRAILING_STOP_ACTIVATION_PERCENT': os.getenv('TRAILING_STOP_ACTIVATION_PERCENT', '3'),
        'MAX_POSITION_SIZE_PCT': os.getenv('MAX_POSITION_SIZE_PCT', '50'),
    }


def analyze_with_ai(days: int = 30, verbose: bool = True) -> Dict[str, Any]:
    """
    Usa AI per analizzare performance e suggerire miglioramenti.

    Args:
        days: Giorni di storico da analizzare
        verbose: Se True, stampa dettagli

    Returns:
        {
            'analysis': 'Testo analisi AI',
            'suggestions': {...},
            'timestamp': datetime
        }
    """

    if verbose:
        print(f"\n{'='*70}")
        print(f"🤖 AI STRATEGY CONTROLLER")
        print(f"{'='*70}\n")
        print(f"📊 Raccolta dati performance (ultimi {days} giorni)...\n")

    # 1. Raccolta dati
    performance = analytics.get_performance_summary(days)
    sentinel_stats = analytics.get_sentinel_effectiveness()
    current_config = read_current_config()

    if performance.get('error'):
        print(f"❌ Errore: {performance['error']}")
        return {
            'error': performance['error'],
            'timestamp': datetime.now()
        }

    # NEW: Per-symbol analysis
    if verbose:
        print(f"🔍 Analisi opportunità perse per simbolo...\n")

    missed_opportunities = analytics.analyze_missed_opportunities_per_symbol(days=min(days, 7))
    threshold_optimization = analytics.optimize_thresholds_per_symbol(days=min(days, 7))
    portfolio_cost = analytics.analyze_portfolio_opportunity_cost(days=min(days, 7))

    if verbose:
        print(f"\n{'='*70}")
        print(f"🧠 Analisi AI in corso...")
        print(f"   Modello: {MODEL}")
        print(f"{'='*70}\n")

    # 2. Costruisci prompt per AI
    prompt = _build_analysis_prompt(
        performance,
        sentinel_stats,
        current_config,
        days,
        missed_opportunities,
        threshold_optimization,
        portfolio_cost
    )

    # 3. Chiama AI
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a quantitative trading analyst expert. Analyze trading bot performance data and provide concrete, actionable suggestions to improve profitability."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3  # Più deterministico per analisi
        )

        analysis_text = response.choices[0].message.content

        if verbose:
            print(f"\n{'='*70}")
            print(f"📋 AI ANALYSIS REPORT")
            print(f"{'='*70}\n")
            print(analysis_text)
            print(f"\n{'='*70}\n")

        # 4. Salva report
        report_path = _save_report(analysis_text, performance, days)

        if verbose:
            print(f"💾 Report salvato in: {report_path}\n")

        return {
            'analysis': analysis_text,
            'performance_data': performance,
            'sentinel_stats': sentinel_stats,
            'current_config': current_config,
            'report_path': report_path,
            'timestamp': datetime.now()
        }

    except Exception as e:
        print(f"❌ Errore chiamata AI: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now()
        }


def _build_analysis_prompt(
    performance: Dict[str, Any],
    sentinel_stats: Dict[str, Any],
    current_config: Dict[str, str],
    days: int,
    missed_opportunities: Dict[str, Any] = None,
    threshold_optimization: Dict[str, Any] = None,
    portfolio_cost: Dict[str, Any] = None
) -> str:
    """Costruisce il prompt per l'AI con tutti i dati."""

    # Estrai trade di esempio (best/worst)
    trades = performance.get('trades', [])
    best_trades = sorted(trades, key=lambda t: t['pnl_pct'], reverse=True)[:3]
    worst_trades = sorted(trades, key=lambda t: t['pnl_pct'])[:3]

    # Trade con peggiori missed opportunities
    trades_with_analysis = [t for t in trades if 'close_analysis' in t]
    worst_timing = sorted(
        trades_with_analysis,
        key=lambda t: t['close_analysis'].get('missed_opportunity_pct', 0),
        reverse=True
    )[:3]

    prompt = f"""
You are analyzing a cryptocurrency trading bot's performance over the last {days} days.

## PERFORMANCE SUMMARY

**Overall Results:**
- Total Trades: {performance['total_trades']}
- Win Rate: {performance['win_rate']*100:.1f}% ({performance['winning_trades']}W / {performance['losing_trades']}L)
- Profit Factor: {performance['profit_factor']:.2f}
- Net Profit: ${performance['net_profit_usd']:.2f}

**Trade Metrics:**
- Average Win: +{performance['avg_win_pct']:.2f}%
- Average Loss: {performance['avg_loss_pct']:.2f}%
- Max Win: +{performance['max_win_pct']:.2f}%
- Max Loss: {performance['max_loss_pct']:.2f}%
- Avg Duration: {performance['avg_duration_minutes']:.0f} minutes

## CLOSE QUALITY ANALYSIS (Hindsight)

**Quality Distribution:**
{json.dumps(performance['close_quality_distribution'], indent=2)}

**Missed Opportunities:**
- Total: {performance['total_missed_profit_pct']:.1f}% cumulative
- Per Trade Average: {performance['avg_missed_per_trade_pct']:.2f}%

**Worst Timing Examples:**
"""

    for i, trade in enumerate(worst_timing, 1):
        analysis = trade['close_analysis']
        prompt += f"""
{i}. {trade['symbol']} {trade['side'].upper()}:
   - Closed at: +{trade['pnl_pct']:.2f}%
   - Peak after close: +{analysis.get('peak_after_close_pct', 0):.2f}%
   - Missed: {analysis.get('missed_opportunity_pct', 0):.2f}%
   - Verdict: {analysis.get('verdict', 'N/A')}
"""

    prompt += f"""

## PER-SYMBOL BREAKDOWN

"""
    for symbol, stats in performance['per_symbol'].items():
        prompt += f"""
**{symbol}:**
- Trades: {stats['total_trades']}
- Win Rate: {stats['win_rate']*100:.1f}%
- Profit Factor: {stats['profit_factor']:.2f}
- Net Profit: ${stats['net_profit_usd']:.2f}
- Avg Win: +{stats['avg_win_pct']:.2f}%
- Avg Loss: {stats['avg_loss_pct']:.2f}%
"""

    prompt += f"""

## SENTINEL EFFECTIVENESS

**Close Actions:**
- Take Profit: {sentinel_stats['take_profit_count']} ({sentinel_stats['take_profit_rate']*100:.1f}%)
  - Avg profit at TP: {sentinel_stats['avg_profit_at_take_profit']:.2f}%
- Stop Loss: {sentinel_stats['stop_loss_count']}
  - Avg loss at SL: {sentinel_stats['avg_loss_at_stop_loss']:.2f}%
- Trailing Stop: {sentinel_stats['trailing_stop_count']}
  - Avg profit at TS: {sentinel_stats['avg_profit_at_trailing']:.2f}%

## CURRENT CONFIGURATION

```env
{json.dumps(current_config, indent=2)}
```
"""

    # NEW: Per-symbol missed opportunities
    if missed_opportunities:
        prompt += f"""

## 🔍 PER-SYMBOL MISSED OPPORTUNITIES ANALYSIS

Bot inactivity and missed trades analysis for each symbol:
"""
        for symbol, data in missed_opportunities.items():
            prompt += f"""

**{symbol}:**
- Missed Opportunities: {data['total_missed_opportunities']}
- Avg Missed Profit: {data['avg_missed_profit_pct']:.2f}%
- Total Potential Profit: {data['total_potential_profit_pct']:.1f}%
- Reasons:
  - Score below threshold: {data['reasons']['score_below_threshold']}
  - Other: {data['reasons']['other']}
- **Optimal Threshold:** {data['optimal_threshold']} (current: {current_config['SCORE_THRESHOLD_OPEN']})
"""

            # Top 3 esempi
            if data['details']:
                prompt += f"\nTop Missed:\n"
                for detail in data['details'][:3]:
                    prompt += f"  - Score {detail['score']:.1f} | Movement: +{detail['movement_pct']:.1f}% | Reason: {detail['reason']}\n"

    # NEW: Threshold optimization
    if threshold_optimization:
        total_additional_profit = sum(d['impact']['estimated_additional_profit_pct'] for d in threshold_optimization.values())
        prompt += f"""

## 🎯 THRESHOLD OPTIMIZATION

Current SCORE_THRESHOLD_OPEN={current_config['SCORE_THRESHOLD_OPEN']} appears suboptimal.

**Optimization Results:**
"""
        for symbol, opt in threshold_optimization.items():
            prompt += f"""
{symbol}: Optimal={opt['optimal_threshold']} (current={opt['current_threshold']})
  → +{opt['impact']['additional_trades_per_week']:.1f} trades/week
  → +{opt['impact']['estimated_additional_profit_pct']:.1f}% potential profit
"""
        prompt += f"""
**TOTAL IMPACT IF APPLIED:** +{total_additional_profit:.1f}% additional profit potential
"""

    # NEW: Portfolio opportunity cost
    if portfolio_cost and portfolio_cost['suboptimal_choices']:
        prompt += f"""

## 💰 PORTFOLIO OPPORTUNITY COST

Analysis of suboptimal position choices:

- Total Suboptimal Choices: {len(portfolio_cost['suboptimal_choices'])}
- Total Opportunity Cost: {portfolio_cost['total_opportunity_cost_pct']:.1f}%

Top Examples:
"""
        for choice in portfolio_cost['suboptimal_choices'][:3]:
            prompt += f"""
- Had {choice['had_position']} (+{choice['performance']:.1f}%)
  Alternatives:"""
            for alt_symbol, alt_data in choice['missed_alternatives'].items():
                prompt += f"""
    {alt_symbol}: score {alt_data['score']:.1f}, performance +{alt_data['performance']:.1f}% (cost: +{alt_data['opportunity_cost']:.1f}%)"""
            prompt += "\n"

        if portfolio_cost['suggestions']:
            prompt += f"\n**Suggestions:**\n"
            for sug in portfolio_cost['suggestions']:
                prompt += f"- {sug}\n"

    prompt += f"""

## YOUR TASK

Based on REAL data above, provide:

### 1. 🔍 DIAGNOSIS
Analyze what's working and what's not. Be specific and data-driven.

### 2. 🎯 TOP 3 PRIORITY SUGGESTIONS
Suggest concrete parameter changes with:
- What to change and why
- Expected impact (quantified)
- Risk/difficulty level

Focus on:
- Reducing missed opportunities (close timing)
- Optimizing TAKE_PROFIT_PERCENT, TRAILING_STOP_PERCENT
- Improving win rate or profit factor
- Avoiding bad trades (which symbols/conditions to skip)

### 3. 📝 RECOMMENDED .ENV CHANGES

Provide exact changes to make to .env file, format:
```
PARAMETER_NAME=new_value  # was old_value, reason: ...
```

### 4. ⚠️ WARNINGS & RISKS
Any potential downsides or things to watch out for.

Be concise, actionable, and focus on HIGH IMPACT changes.
"""

    return prompt


def _save_report(analysis: str, performance: Dict[str, Any], days: int) -> str:
    """Salva il report in reports/"""

    # Crea directory se non esiste
    os.makedirs('reports', exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"reports/strategy_analysis_{timestamp}.md"

    with open(filename, 'w') as f:
        f.write(f"# Trading Bot Strategy Analysis\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Period:** Last {days} days\n")
        f.write(f"**Total Trades:** {performance.get('total_trades', 0)}\n")
        f.write(f"**Win Rate:** {performance.get('win_rate', 0)*100:.1f}%\n")
        f.write(f"**Net Profit:** ${performance.get('net_profit_usd', 0):.2f}\n\n")
        f.write("---\n\n")
        f.write(analysis)

    return filename


def main():
    parser = argparse.ArgumentParser(description="AI Strategy Controller")
    parser.add_argument("--days", type=int, default=30, help="Days of history to analyze (default: 30)")
    parser.add_argument("--silent", action="store_true", help="Suppress output (for cron)")
    args = parser.parse_args()

    result = analyze_with_ai(days=args.days, verbose=not args.silent)

    if result.get('error'):
        print(f"❌ Error: {result['error']}")
        exit(1)

    print(f"\n✅ Analysis complete!")
    print(f"📄 Report: {result.get('report_path', 'N/A')}")


if __name__ == "__main__":
    main()
