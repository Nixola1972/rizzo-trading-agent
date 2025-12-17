"""
Arena AI Analysis Module

Provides deep AI-powered analysis of trading data using LLM.
Can be triggered manually via button or scheduled daily.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import statistics

logger = logging.getLogger("arena.ai_analysis")


@dataclass
class AIAnalysisReport:
    """AI-generated analysis report."""
    report_id: str
    generated_at: datetime
    model_used: str
    analysis_text: str
    key_insights: List[str]
    recommended_actions: List[Dict[str, Any]]
    risk_warnings: List[str]
    market_observations: List[str]
    raw_prompt: str
    raw_response: str
    execution_time_seconds: float


class AIAnalyzer:
    """AI-powered trading analysis using LLM."""

    def __init__(self, db):
        self.db = db
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.model = os.environ.get("AI_ANALYSIS_MODEL", "deepseek/deepseek-chat")
        self._last_report: Optional[AIAnalysisReport] = None
        self._last_run: Optional[datetime] = None

    def should_run_daily(self) -> bool:
        """Check if daily analysis should run."""
        if self._last_run is None:
            return True
        return datetime.now() - self._last_run > timedelta(hours=24)

    def run_analysis(self, force: bool = False) -> Optional[AIAnalysisReport]:
        """
        Run AI analysis on trading data.

        Args:
            force: If True, run even if daily limit reached

        Returns:
            AIAnalysisReport or None if analysis fails
        """
        if not force and not self.should_run_daily():
            logger.info("AI analysis already run today, skipping")
            return self._last_report

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set, cannot run AI analysis")
            return None

        start_time = datetime.now()

        try:
            # Collect data
            data = self._collect_analysis_data()

            # Build prompt
            prompt = self._build_analysis_prompt(data)

            # Call LLM
            response = self._call_llm(prompt)

            if not response:
                return None

            # Parse response
            report = self._parse_response(response, prompt, start_time)

            self._last_report = report
            self._last_run = datetime.now()

            logger.info(f"AI analysis completed in {report.execution_time_seconds:.1f}s")
            return report

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None

    def get_last_report(self) -> Optional[AIAnalysisReport]:
        """Get the last generated report."""
        return self._last_report

    def _collect_analysis_data(self) -> Dict[str, Any]:
        """Collect all data needed for analysis."""
        from .config_loader import load_variants
        from .metrics import calculate_metrics

        # Get trades from last 48 hours for more context
        trades = self.db.get_recent_trades(hours=48, limit=500)

        # Get open positions
        positions = self.db.get_all_open_positions()

        # Load variants config
        variants = load_variants(self.db)

        # Calculate overall metrics
        metrics = calculate_metrics(trades)

        # Group trades by various dimensions
        trades_by_ai = {}
        trades_by_symbol = {}
        trades_by_direction = {"LONG": [], "SHORT": []}
        trades_by_hour = {}

        for t in trades:
            # By AI model
            ai_key = t.ai_model or "unknown"
            if ai_key not in trades_by_ai:
                trades_by_ai[ai_key] = []
            trades_by_ai[ai_key].append(t)

            # By symbol
            if t.symbol not in trades_by_symbol:
                trades_by_symbol[t.symbol] = []
            trades_by_symbol[t.symbol].append(t)

            # By direction
            if t.direction:
                dir_key = t.direction.value if hasattr(t.direction, 'value') else str(t.direction)
                if dir_key in trades_by_direction:
                    trades_by_direction[dir_key].append(t)

            # By hour of day
            if t.entry_time:
                hour = t.entry_time.hour
                if hour not in trades_by_hour:
                    trades_by_hour[hour] = []
                trades_by_hour[hour].append(t)

        # Calculate per-dimension stats
        def calc_stats(trade_list):
            if not trade_list:
                return None
            pnls = [t.pnl_usd for t in trade_list if t.pnl_usd is not None]
            if not pnls:
                return None
            return {
                "count": len(pnls),
                "total_pnl": sum(pnls),
                "avg_pnl": statistics.mean(pnls),
                "win_rate": sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0,
                "max_win": max(pnls) if pnls else 0,
                "max_loss": min(pnls) if pnls else 0,
            }

        ai_stats = {k: calc_stats(v) for k, v in trades_by_ai.items()}
        symbol_stats = {k: calc_stats(v) for k, v in trades_by_symbol.items()}
        direction_stats = {k: calc_stats(v) for k, v in trades_by_direction.items()}
        hour_stats = {k: calc_stats(v) for k, v in trades_by_hour.items()}

        # Score distribution analysis
        score_ranges = {"10-15": [], "15-20": [], "20-25": [], "25-30": [], "30+": []}
        for t in trades:
            if t.entry_score and t.pnl_usd is not None:
                score = abs(t.entry_score)
                if 10 <= score < 15:
                    score_ranges["10-15"].append(t.pnl_usd)
                elif 15 <= score < 20:
                    score_ranges["15-20"].append(t.pnl_usd)
                elif 20 <= score < 25:
                    score_ranges["20-25"].append(t.pnl_usd)
                elif 25 <= score < 30:
                    score_ranges["25-30"].append(t.pnl_usd)
                elif score >= 30:
                    score_ranges["30+"].append(t.pnl_usd)

        score_stats = {}
        for range_name, pnls in score_ranges.items():
            if len(pnls) >= 3:
                score_stats[range_name] = {
                    "count": len(pnls),
                    "avg_pnl": statistics.mean(pnls),
                    "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
                    "total_pnl": sum(pnls),
                }

        # Exit reason analysis
        exit_reasons = {}
        for t in trades:
            if t.exit_reason:
                reason = t.exit_reason.value if hasattr(t.exit_reason, 'value') else str(t.exit_reason)
                if reason not in exit_reasons:
                    exit_reasons[reason] = {"count": 0, "pnls": []}
                exit_reasons[reason]["count"] += 1
                if t.pnl_usd is not None:
                    exit_reasons[reason]["pnls"].append(t.pnl_usd)

        for reason, data in exit_reasons.items():
            if data["pnls"]:
                data["avg_pnl"] = statistics.mean(data["pnls"])
                data["total_pnl"] = sum(data["pnls"])
            del data["pnls"]  # Remove raw data

        # Recent trade details (last 20)
        recent_trades = []
        for t in trades[:20]:
            recent_trades.append({
                "symbol": t.symbol,
                "direction": t.direction.value if hasattr(t.direction, 'value') else str(t.direction),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_usd": t.pnl_usd,
                "pnl_pct": t.pnl_pct,
                "entry_score": t.entry_score,
                "exit_reason": t.exit_reason.value if t.exit_reason and hasattr(t.exit_reason, 'value') else str(t.exit_reason) if t.exit_reason else None,
                "hold_time_min": (t.exit_time - t.entry_time).total_seconds() / 60 if t.exit_time and t.entry_time else None,
                "ai_model": t.ai_model,
            })

        # Open positions details
        open_positions = []
        for p in positions:
            open_positions.append({
                "symbol": p.symbol,
                "direction": p.direction.value if hasattr(p.direction, 'value') else str(p.direction),
                "entry_price": p.entry_price,
                "current_pnl_pct": p.current_pnl_pct,
                "current_pnl_usd": p.current_pnl_usd,
                "hold_time_min": (datetime.now() - p.entry_time).total_seconds() / 60 if p.entry_time else None,
            })

        return {
            "analysis_period": "48 hours",
            "total_trades": len(trades),
            "total_pnl_usd": metrics["total_pnl_usd"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics.get("profit_factor", 0),
            "ai_model_stats": {k: v for k, v in ai_stats.items() if v},
            "symbol_stats": {k: v for k, v in symbol_stats.items() if v},
            "direction_stats": {k: v for k, v in direction_stats.items() if v},
            "hour_of_day_stats": {str(k): v for k, v in hour_stats.items() if v},
            "score_range_stats": score_stats,
            "exit_reason_stats": exit_reasons,
            "open_positions": open_positions,
            "recent_trades": recent_trades,
            "current_config": {
                "score_threshold": float(os.environ.get("SCORE_THRESHOLD_OPEN", 15)),
                "trading_style": os.environ.get("TRADING_STYLE", "moderate"),
                "leverage": int(os.environ.get("LEVERAGE", 5)),
            }
        }

    def _build_analysis_prompt(self, data: Dict[str, Any]) -> str:
        """Build comprehensive analysis prompt."""

        prompt = f"""Sei un esperto analista di trading algoritmico. Analizza i seguenti dati di trading degli ultimi {data['analysis_period']} e fornisci insight actionable.

## DATI DI TRADING

### Riepilogo Generale
- Trade totali: {data['total_trades']}
- P&L totale: ${data['total_pnl_usd']:.2f}
- Win rate: {data['win_rate']:.1f}%
- Profit factor: {data['profit_factor']:.2f}

### Performance per Modello AI
"""
        for model, stats in data['ai_model_stats'].items():
            prompt += f"- **{model}**: {stats['count']} trade, P&L ${stats['total_pnl']:.2f}, Win rate {stats['win_rate']:.1%}\n"

        prompt += "\n### Performance per Simbolo\n"
        for symbol, stats in data['symbol_stats'].items():
            prompt += f"- **{symbol}**: {stats['count']} trade, P&L ${stats['total_pnl']:.2f}, Win rate {stats['win_rate']:.1%}\n"

        prompt += "\n### Performance per Direzione\n"
        for direction, stats in data['direction_stats'].items():
            if stats:
                prompt += f"- **{direction}**: {stats['count']} trade, P&L ${stats['total_pnl']:.2f}, Win rate {stats['win_rate']:.1%}\n"

        prompt += "\n### Performance per Fascia di Score\n"
        for score_range, stats in data['score_range_stats'].items():
            prompt += f"- **Score {score_range}**: {stats['count']} trade, Avg P&L ${stats['avg_pnl']:.2f}, Win rate {stats['win_rate']:.1%}\n"

        prompt += "\n### Exit Reasons\n"
        for reason, stats in data['exit_reason_stats'].items():
            prompt += f"- **{reason}**: {stats['count']} trade"
            if 'avg_pnl' in stats:
                prompt += f", Avg P&L ${stats['avg_pnl']:.2f}"
            prompt += "\n"

        if data['hour_of_day_stats']:
            prompt += "\n### Performance per Ora del Giorno (top 5)\n"
            sorted_hours = sorted(data['hour_of_day_stats'].items(),
                                  key=lambda x: x[1]['total_pnl'] if x[1] else 0, reverse=True)[:5]
            for hour, stats in sorted_hours:
                if stats:
                    prompt += f"- **{hour}:00**: {stats['count']} trade, P&L ${stats['total_pnl']:.2f}\n"

        prompt += f"""
### Configurazione Attuale
- Score threshold: {data['current_config']['score_threshold']}
- Trading style: {data['current_config']['trading_style']}
- Leverage: {data['current_config']['leverage']}x

### Posizioni Aperte ({len(data['open_positions'])})
"""
        for pos in data['open_positions'][:5]:
            prompt += f"- {pos['symbol']} {pos['direction']}: {pos['current_pnl_pct']:.2f}% (${pos['current_pnl_usd']:.2f})\n"

        prompt += f"""
### Ultimi 10 Trade
"""
        for t in data['recent_trades'][:10]:
            prompt += f"- {t['symbol']} {t['direction']}: ${t['pnl_usd']:.2f} ({t['pnl_pct']:.2f}%) - Score {t['entry_score']}, Exit: {t['exit_reason']}\n"

        prompt += """
## RICHIESTA DI ANALISI

Fornisci un'analisi strutturata in formato JSON con i seguenti campi:

```json
{
    "summary": "Breve riassunto dello stato attuale (2-3 frasi)",
    "key_insights": [
        "Insight 1: osservazione importante sui dati",
        "Insight 2: pattern identificato",
        "Insight 3: anomalia o opportunità"
    ],
    "recommended_actions": [
        {
            "action": "Descrizione azione",
            "reason": "Motivazione basata sui dati",
            "priority": "high/medium/low",
            "expected_impact": "Impatto atteso"
        }
    ],
    "risk_warnings": [
        "Warning 1: rischio identificato",
        "Warning 2: situazione da monitorare"
    ],
    "market_observations": [
        "Osservazione 1 sul comportamento del mercato",
        "Osservazione 2 sui pattern"
    ],
    "parameter_suggestions": {
        "score_threshold": "valore suggerito o 'keep'",
        "best_hours": ["lista ore migliori"],
        "avoid_symbols": ["simboli da evitare o lista vuota"],
        "preferred_direction": "LONG/SHORT/BOTH"
    }
}
```

Sii specifico, basati SOLO sui dati forniti, e fornisci raccomandazioni actionable.
"""
        return prompt

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call the LLM API."""
        import requests

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Sei un esperto analista di trading algoritmico. Rispondi sempre in JSON valido."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()

            result = response.json()
            return result["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return None

    def _parse_response(self, response: str, prompt: str, start_time: datetime) -> AIAnalysisReport:
        """Parse LLM response into structured report."""

        execution_time = (datetime.now() - start_time).total_seconds()

        # Try to extract JSON from response
        try:
            # Find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                parsed = json.loads(json_str)
            else:
                parsed = {}
        except json.JSONDecodeError:
            parsed = {}

        report_id = f"AI_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return AIAnalysisReport(
            report_id=report_id,
            generated_at=datetime.now(),
            model_used=self.model,
            analysis_text=parsed.get("summary", response[:500]),
            key_insights=parsed.get("key_insights", []),
            recommended_actions=parsed.get("recommended_actions", []),
            risk_warnings=parsed.get("risk_warnings", []),
            market_observations=parsed.get("market_observations", []),
            raw_prompt=prompt,
            raw_response=response,
            execution_time_seconds=execution_time,
        )
