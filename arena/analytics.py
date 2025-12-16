"""
Arena Analytics Engine

Analyzes trading data to find optimal parameters and provide
recommendations for production model improvements.

Runs every 24 hours (configurable) and generates insights.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import json
import statistics

logger = logging.getLogger("arena.analytics")


class RecommendationType(Enum):
    """Types of recommendations."""
    AI_MODEL = "ai_model"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    LEVERAGE = "leverage"
    INDICATOR_WEIGHT = "indicator_weight"
    TRADING_STYLE = "trading_style"
    SCORE_THRESHOLD = "score_threshold"


class RecommendationPriority(Enum):
    """Priority levels for recommendations."""
    HIGH = "high"      # Strong evidence, significant improvement
    MEDIUM = "medium"  # Good evidence, moderate improvement
    LOW = "low"        # Weak evidence, minor improvement


@dataclass
class Recommendation:
    """A single recommendation for production."""
    type: RecommendationType
    priority: RecommendationPriority
    title: str
    description: str
    current_value: Any
    recommended_value: Any
    expected_improvement: str
    confidence: float  # 0.0 - 1.0
    evidence: str
    created_at: datetime
    details: Optional[Dict[str, Any]] = None  # Detailed breakdown data

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "expected_improvement": self.expected_improvement,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
        }
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class AIModelStats:
    """Statistics for an AI model."""
    model_id: str
    model_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl_usd: float
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_hold_time_hours: float
    api_calls: int
    api_errors: int
    api_error_rate: float


@dataclass
class ParameterAnalysis:
    """Analysis of a specific parameter."""
    parameter_name: str
    current_value: Any
    optimal_value: Any
    improvement_pct: float
    sample_size: int
    confidence: float
    breakdown: Optional[Dict[str, Any]] = None  # Detailed breakdown by category


@dataclass
class AnalyticsReport:
    """Complete analytics report."""
    report_id: str
    generated_at: datetime
    analysis_period_hours: int
    total_trades_analyzed: int

    # AI Model Rankings
    ai_rankings: List[AIModelStats]
    best_ai_model: Optional[str]

    # Parameter Optimizations
    parameter_analyses: List[ParameterAnalysis]

    # Recommendations for Production
    recommendations: List[Recommendation]

    # Summary Statistics
    total_pnl_usd: float
    avg_win_rate: float
    best_performing_variant: Optional[str]
    worst_performing_variant: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "analysis_period_hours": self.analysis_period_hours,
            "total_trades_analyzed": self.total_trades_analyzed,
            "ai_rankings": [asdict(r) for r in self.ai_rankings],
            "best_ai_model": self.best_ai_model,
            "parameter_analyses": [asdict(p) for p in self.parameter_analyses],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "total_pnl_usd": self.total_pnl_usd,
            "avg_win_rate": self.avg_win_rate,
            "best_performing_variant": self.best_performing_variant,
            "worst_performing_variant": self.worst_performing_variant,
        }


class AnalyticsEngine:
    """
    Analytics Engine for Arena.

    Analyzes trading data and generates recommendations
    for improving the production model.
    """

    def __init__(self, db):
        """Initialize analytics engine."""
        self.db = db
        self.analysis_period_hours = 24
        self.min_trades_for_analysis = 10
        self._last_report: Optional[AnalyticsReport] = None
        self._last_report_time: Optional[datetime] = None

    def run_analysis(self, force: bool = False) -> Optional[AnalyticsReport]:
        """
        Run full analytics analysis.

        Args:
            force: If True, run even if recently run

        Returns:
            AnalyticsReport with findings and recommendations
        """
        # Check if we should run
        if not force and self._last_report_time:
            hours_since = (datetime.now() - self._last_report_time).total_seconds() / 3600
            if hours_since < self.analysis_period_hours:
                logger.info(f"Analytics: Skipping, last run {hours_since:.1f}h ago")
                return self._last_report

        logger.info("📊 Starting Arena Analytics...")

        try:
            # Gather data
            trades = self._get_recent_trades()
            if len(trades) < self.min_trades_for_analysis:
                logger.warning(f"Not enough trades for analysis: {len(trades)} < {self.min_trades_for_analysis}")
                return None

            sub_variants = self.db.get_all_sub_variants()

            # Analyze AI models
            ai_rankings = self._analyze_ai_models(trades, sub_variants)

            # Analyze parameters
            parameter_analyses = self._analyze_parameters(trades)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                ai_rankings, parameter_analyses, trades
            )

            # Calculate summary stats
            total_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd)
            win_rates = [r.win_rate for r in ai_rankings if r.total_trades > 0]
            avg_win_rate = statistics.mean(win_rates) if win_rates else 0.0

            # Find best/worst variants
            variant_pnl: Dict[str, float] = {}
            for t in trades:
                sv = self.db.get_sub_variant(t.sub_variant_id)
                if sv:
                    variant_id = sv.variant_id
                    variant_pnl[variant_id] = variant_pnl.get(variant_id, 0) + (t.pnl_usd or 0)

            best_variant = max(variant_pnl, key=variant_pnl.get) if variant_pnl else None
            worst_variant = min(variant_pnl, key=variant_pnl.get) if variant_pnl else None

            # Create report
            report = AnalyticsReport(
                report_id=f"AR_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                generated_at=datetime.now(),
                analysis_period_hours=self.analysis_period_hours,
                total_trades_analyzed=len(trades),
                ai_rankings=ai_rankings,
                best_ai_model=ai_rankings[0].model_id if ai_rankings else None,
                parameter_analyses=parameter_analyses,
                recommendations=recommendations,
                total_pnl_usd=total_pnl,
                avg_win_rate=avg_win_rate,
                best_performing_variant=best_variant,
                worst_performing_variant=worst_variant,
            )

            self._last_report = report
            self._last_report_time = datetime.now()

            # Save report to database
            self._save_report(report)

            logger.info(f"📊 Analytics complete: {len(recommendations)} recommendations generated")
            return report

        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return None

    def get_latest_report(self) -> Optional[AnalyticsReport]:
        """Get the most recent analytics report."""
        return self._last_report

    def get_recommendations(
        self,
        priority: Optional[RecommendationPriority] = None,
        type_filter: Optional[RecommendationType] = None,
    ) -> List[Recommendation]:
        """Get filtered recommendations from latest report."""
        if not self._last_report:
            return []

        recs = self._last_report.recommendations

        if priority:
            recs = [r for r in recs if r.priority == priority]

        if type_filter:
            recs = [r for r in recs if r.type == type_filter]

        return recs

    def get_ai_leaderboard(self) -> List[AIModelStats]:
        """Get AI model rankings from latest report."""
        if not self._last_report:
            return []
        return self._last_report.ai_rankings

    def _get_recent_trades(self):
        """Get trades from the analysis period."""
        # Use get_recent_trades with large limit to get all trades in period
        return self.db.get_recent_trades(
            hours=self.analysis_period_hours,
            limit=10000
        )

    def _analyze_ai_models(self, trades, sub_variants) -> List[AIModelStats]:
        """Analyze performance of each AI model."""
        model_trades: Dict[str, List] = {}

        # Group trades by AI model
        for t in trades:
            sv = self.db.get_sub_variant(t.sub_variant_id)
            if sv:
                model = sv.ai_model
                if model not in model_trades:
                    model_trades[model] = []
                model_trades[model].append(t)

        # Calculate stats for each model
        stats = []
        for model, model_trade_list in model_trades.items():
            sv = next((s for s in sub_variants if s.ai_model == model), None)
            model_name = sv.ai_model_name if sv else model.split("/")[-1]

            winning = [t for t in model_trade_list if t.pnl_usd and t.pnl_usd > 0]
            losing = [t for t in model_trade_list if t.pnl_usd and t.pnl_usd < 0]

            total_trades = len(model_trade_list)
            winning_trades = len(winning)
            losing_trades = len(losing)

            total_pnl = sum(t.pnl_usd for t in model_trade_list if t.pnl_usd)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

            avg_win = statistics.mean([t.pnl_usd for t in winning]) if winning else 0.0
            avg_loss = abs(statistics.mean([t.pnl_usd for t in losing])) if losing else 0.0

            gross_profit = sum(t.pnl_usd for t in winning) if winning else 0.0
            gross_loss = abs(sum(t.pnl_usd for t in losing)) if losing else 0.0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

            # Calculate average hold time
            hold_times = []
            for t in model_trade_list:
                if t.entry_time and t.exit_time:
                    hold_hours = (t.exit_time - t.entry_time).total_seconds() / 3600
                    hold_times.append(hold_hours)
            avg_hold_time = statistics.mean(hold_times) if hold_times else 0.0

            # Get API stats
            api_calls = sv.api_calls if sv else 0
            api_errors = sv.api_errors if sv else 0
            api_error_rate = api_errors / api_calls if api_calls > 0 else 0.0

            # Calculate Sharpe ratio (simplified)
            if len(model_trade_list) > 1:
                returns = [t.pnl_usd for t in model_trade_list if t.pnl_usd]
                if returns:
                    avg_return = statistics.mean(returns)
                    std_return = statistics.stdev(returns) if len(returns) > 1 else 1
                    sharpe = avg_return / std_return if std_return > 0 else 0
                else:
                    sharpe = 0.0
            else:
                sharpe = 0.0

            stats.append(AIModelStats(
                model_id=model,
                model_name=model_name,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                total_pnl_usd=total_pnl,
                win_rate=win_rate,
                avg_win_usd=avg_win,
                avg_loss_usd=avg_loss,
                profit_factor=profit_factor,
                max_drawdown_pct=0.0,  # Would need equity curve
                sharpe_ratio=sharpe,
                avg_hold_time_hours=avg_hold_time,
                api_calls=api_calls,
                api_errors=api_errors,
                api_error_rate=api_error_rate,
            ))

        # Sort by total P&L descending
        stats.sort(key=lambda x: x.total_pnl_usd, reverse=True)
        return stats

    def _analyze_parameters(self, trades) -> List[ParameterAnalysis]:
        """Analyze which parameters perform best."""
        analyses = []

        # Analyze Stop Loss effectiveness
        sl_analysis = self._analyze_stop_loss(trades)
        if sl_analysis:
            analyses.append(sl_analysis)

        # Analyze leverage effectiveness
        leverage_analysis = self._analyze_leverage(trades)
        if leverage_analysis:
            analyses.append(leverage_analysis)

        # Analyze entry score threshold
        score_analysis = self._analyze_score_threshold(trades)
        if score_analysis:
            analyses.append(score_analysis)

        # Analyze trailing stop effectiveness
        trailing_analysis = self._analyze_trailing_stop(trades)
        if trailing_analysis:
            analyses.append(trailing_analysis)

        # Analyze symbol performance
        symbol_analysis = self._analyze_symbols(trades)
        if symbol_analysis:
            analyses.extend(symbol_analysis)

        return analyses

    def _analyze_stop_loss(self, trades) -> Optional[ParameterAnalysis]:
        """
        Analyze stop loss effectiveness by looking at exit reasons and P&L.

        Evaluates:
        - % of trades hitting SL vs TP
        - Average loss when SL hit
        - Whether SL is too tight (many small losses) or too loose (big losses)
        """
        if len(trades) < 5:
            return None

        # Count exits by reason
        sl_trades = [t for t in trades if t.exit_reason and 'SL' in t.exit_reason.value]
        tp_trades = [t for t in trades if t.exit_reason and 'TP' in t.exit_reason.value]

        if not sl_trades:
            return None

        sl_count = len(sl_trades)
        tp_count = len(tp_trades)
        total = len(trades)

        sl_rate = sl_count / total if total > 0 else 0
        avg_sl_loss = statistics.mean([abs(t.pnl_pct) for t in sl_trades]) if sl_trades else 0

        # Analyze if SL might be too tight
        # If >60% hit SL but average loss is small (<2%), SL might be too tight
        sl_too_tight = sl_rate > 0.6 and avg_sl_loss < 2.0

        # Analyze if SL might be too loose
        # If SL hits are rare but average loss is large (>4%), SL might be too loose
        sl_too_loose = sl_rate < 0.3 and avg_sl_loss > 4.0

        # Get current SL from variant config (default 3%)
        current_sl = 3.0

        if sl_too_tight:
            # Suggest widening SL
            suggested_sl = min(current_sl + 1.0, 5.0)
            return ParameterAnalysis(
                parameter_name="stop_loss_pct",
                current_value=current_sl,
                optimal_value=suggested_sl,
                improvement_pct=15.0,  # Estimated
                sample_size=sl_count,
                confidence=min(sl_count / 15, 0.8),
            )
        elif sl_too_loose:
            # Suggest tightening SL
            suggested_sl = max(current_sl - 0.5, 2.0)
            return ParameterAnalysis(
                parameter_name="stop_loss_pct",
                current_value=current_sl,
                optimal_value=suggested_sl,
                improvement_pct=10.0,  # Estimated
                sample_size=sl_count,
                confidence=min(sl_count / 15, 0.7),
            )

        return None

    def _analyze_score_threshold(self, trades) -> Optional[ParameterAnalysis]:
        """
        Analyze optimal entry score threshold.

        Groups trades by entry_score ranges and identifies which thresholds
        produce the best results.
        """
        if len(trades) < 10:
            return None

        # Group trades by score ranges
        score_groups: Dict[str, List[float]] = {
            "10-15": [],
            "15-20": [],
            "20-25": [],
            "25-30": [],
            "30+": [],
        }

        for t in trades:
            if t.entry_score and t.pnl_usd is not None:
                score = abs(t.entry_score)
                if 10 <= score < 15:
                    score_groups["10-15"].append(t.pnl_usd)
                elif 15 <= score < 20:
                    score_groups["15-20"].append(t.pnl_usd)
                elif 20 <= score < 25:
                    score_groups["20-25"].append(t.pnl_usd)
                elif 25 <= score < 30:
                    score_groups["25-30"].append(t.pnl_usd)
                elif score >= 30:
                    score_groups["30+"].append(t.pnl_usd)

        # Calculate performance per group (need at least 3 trades)
        score_performance = {}
        for range_name, pnls in score_groups.items():
            if len(pnls) >= 3:
                avg_pnl = statistics.mean(pnls)
                win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
                score_performance[range_name] = {
                    "avg_pnl": avg_pnl,
                    "win_rate": win_rate,
                    "count": len(pnls),
                    "score": avg_pnl * win_rate  # Combined metric
                }

        if not score_performance:
            return None

        # Find best performing score range
        best_range = max(score_performance, key=lambda x: score_performance[x]["score"])
        best_data = score_performance[best_range]

        # Map range to threshold value
        threshold_map = {
            "10-15": 12.0,
            "15-20": 15.0,
            "20-25": 20.0,
            "25-30": 25.0,
            "30+": 30.0,
        }

        optimal_threshold = threshold_map.get(best_range, 15.0)
        current_threshold = 15.0  # Default

        # Build detailed breakdown for display
        breakdown = {
            "ranges": [],
            "best_range": best_range,
            "total_trades": sum(len(pnls) for pnls in score_groups.values()),
        }
        for range_name in ["10-15", "15-20", "20-25", "25-30", "30+"]:
            if range_name in score_performance:
                perf = score_performance[range_name]
                breakdown["ranges"].append({
                    "range": range_name,
                    "trades": perf["count"],
                    "win_rate": perf["win_rate"],
                    "avg_pnl": perf["avg_pnl"],
                    "is_best": range_name == best_range,
                })
            elif range_name in score_groups and len(score_groups[range_name]) > 0:
                # Not enough trades but show count
                breakdown["ranges"].append({
                    "range": range_name,
                    "trades": len(score_groups[range_name]),
                    "win_rate": None,
                    "avg_pnl": None,
                    "is_best": False,
                    "note": "< 3 trade"
                })

        if optimal_threshold != current_threshold:
            return ParameterAnalysis(
                parameter_name="score_threshold_open",
                current_value=current_threshold,
                optimal_value=optimal_threshold,
                improvement_pct=best_data["avg_pnl"] * 10 if best_data["avg_pnl"] > 0 else 0,
                sample_size=best_data["count"],
                confidence=min(best_data["count"] / 20, 0.9),
                breakdown=breakdown,
            )

        return None

    def _analyze_trailing_stop(self, trades) -> Optional[ParameterAnalysis]:
        """
        Analyze trailing stop effectiveness by comparing peak P&L vs final P&L.

        High "give-back" indicates trailing stop might be too loose.
        """
        if len(trades) < 10:
            return None

        # Calculate give-back for profitable trades that hit SL
        giveback_trades = [
            t for t in trades
            if t.peak_pnl_pct > 2.0  # Had significant profit
            and t.exit_reason and 'SL' in t.exit_reason.value
        ]

        if len(giveback_trades) < 3:
            return None

        # Calculate average give-back percentage
        givebacks = []
        for t in giveback_trades:
            if t.peak_pnl_pct > 0:
                giveback = t.peak_pnl_pct - t.pnl_pct
                givebacks.append(giveback)

        if not givebacks:
            return None

        avg_giveback = statistics.mean(givebacks)

        # If giving back >3% on average, trailing is too loose
        if avg_giveback > 3.0:
            return ParameterAnalysis(
                parameter_name="trailing_steps",
                current_value="current",
                optimal_value="tighter",
                improvement_pct=avg_giveback / 2,  # Could capture half the giveback
                sample_size=len(giveback_trades),
                confidence=min(len(giveback_trades) / 10, 0.7),
            )

        # If giving back <1%, trailing might be too tight (exits too early)
        # Check if many profitable trades hit SL instead of running
        tp_trades = [t for t in trades if t.exit_reason and 'TP' in t.exit_reason.value]
        sl_with_profit = [t for t in trades if t.pnl_usd > 0 and t.exit_reason and 'SL' in t.exit_reason.value]

        if len(sl_with_profit) > len(tp_trades) * 2:  # 2x more SL exits than TP
            return ParameterAnalysis(
                parameter_name="trailing_steps",
                current_value="current",
                optimal_value="looser",
                improvement_pct=10.0,
                sample_size=len(sl_with_profit),
                confidence=0.5,
            )

        return None

    def _analyze_symbols(self, trades) -> List[ParameterAnalysis]:
        """
        Analyze performance by symbol to identify best/worst performers.
        """
        if len(trades) < 10:
            return []

        # Group by symbol
        symbol_groups: Dict[str, List] = {}
        for t in trades:
            if t.symbol not in symbol_groups:
                symbol_groups[t.symbol] = []
            symbol_groups[t.symbol].append(t)

        analyses = []
        symbol_stats = {}

        for symbol, symbol_trades in symbol_groups.items():
            if len(symbol_trades) >= 3:
                total_pnl = sum(t.pnl_usd for t in symbol_trades if t.pnl_usd)
                win_rate = sum(1 for t in symbol_trades if t.pnl_usd and t.pnl_usd > 0) / len(symbol_trades)
                symbol_stats[symbol] = {
                    "pnl": total_pnl,
                    "win_rate": win_rate,
                    "count": len(symbol_trades)
                }

        if len(symbol_stats) < 2:
            return []

        # Find worst performing symbol
        worst_symbol = min(symbol_stats, key=lambda x: symbol_stats[x]["pnl"])
        worst_data = symbol_stats[worst_symbol]

        # If a symbol is consistently losing, suggest disabling it
        if worst_data["pnl"] < -5.0 and worst_data["win_rate"] < 0.4:
            analyses.append(ParameterAnalysis(
                parameter_name=f"symbol_{worst_symbol}",
                current_value="enabled",
                optimal_value="disabled",
                improvement_pct=abs(worst_data["pnl"]),
                sample_size=worst_data["count"],
                confidence=min(worst_data["count"] / 10, 0.8),
            ))

        # Find best performing symbol
        best_symbol = max(symbol_stats, key=lambda x: symbol_stats[x]["pnl"])
        best_data = symbol_stats[best_symbol]

        # If one symbol is significantly outperforming, note it
        if best_data["pnl"] > 5.0 and best_data["win_rate"] > 0.6:
            analyses.append(ParameterAnalysis(
                parameter_name=f"symbol_{best_symbol}",
                current_value="standard_weight",
                optimal_value="increased_weight",
                improvement_pct=best_data["pnl"],
                sample_size=best_data["count"],
                confidence=min(best_data["count"] / 10, 0.7),
            ))

        return analyses

    def _analyze_leverage(self, trades) -> Optional[ParameterAnalysis]:
        """Analyze leverage effectiveness."""
        leverage_groups: Dict[int, List[float]] = {}

        for t in trades:
            if t.leverage and t.pnl_usd is not None:
                if t.leverage not in leverage_groups:
                    leverage_groups[t.leverage] = []
                leverage_groups[t.leverage].append(t.pnl_usd)

        if not leverage_groups:
            return None

        # Find best leverage
        leverage_performance = {
            lev: statistics.mean(pnls) for lev, pnls in leverage_groups.items() if len(pnls) >= 3
        }

        if not leverage_performance:
            return None

        best_leverage = max(leverage_performance, key=leverage_performance.get)

        return ParameterAnalysis(
            parameter_name="leverage",
            current_value=3,
            optimal_value=best_leverage,
            improvement_pct=0,  # Complex to calculate
            sample_size=len(leverage_groups.get(best_leverage, [])),
            confidence=min(len(leverage_groups.get(best_leverage, [])) / 20, 1.0),
        )

    def _generate_recommendations(
        self,
        ai_rankings: List[AIModelStats],
        parameter_analyses: List[ParameterAnalysis],
        trades,
    ) -> List[Recommendation]:
        """Generate recommendations for production."""
        recommendations = []
        now = datetime.now()

        # Recommendation 1: Best AI Model
        if ai_rankings and len(ai_rankings) >= 2:
            best = ai_rankings[0]
            worst = ai_rankings[-1]

            if best.total_pnl_usd > 0 and best.total_trades >= 5:
                recommendations.append(Recommendation(
                    type=RecommendationType.AI_MODEL,
                    priority=RecommendationPriority.HIGH if best.win_rate > 0.6 else RecommendationPriority.MEDIUM,
                    title=f"Usa {best.model_name} come modello principale",
                    description=(
                        f"{best.model_name} ha il miglior P&L (${best.total_pnl_usd:.2f}) "
                        f"con win rate {best.win_rate:.1%} su {best.total_trades} trade."
                    ),
                    current_value="deepseek/deepseek-v3.2-speciale",
                    recommended_value=best.model_id,
                    expected_improvement=f"+${best.total_pnl_usd - worst.total_pnl_usd:.2f} potenziale",
                    confidence=min(best.total_trades / 30, 1.0),
                    evidence=f"Basato su {best.total_trades} trade nelle ultime 24h",
                    created_at=now,
                ))

            # Warn about worst model
            if worst.total_pnl_usd < -10 and worst.total_trades >= 5:
                recommendations.append(Recommendation(
                    type=RecommendationType.AI_MODEL,
                    priority=RecommendationPriority.HIGH,
                    title=f"Disabilita {worst.model_name}",
                    description=(
                        f"{worst.model_name} sta perdendo ${abs(worst.total_pnl_usd):.2f} "
                        f"con win rate {worst.win_rate:.1%}. Considera di disabilitarlo."
                    ),
                    current_value="enabled",
                    recommended_value="disabled",
                    expected_improvement=f"Evita -${abs(worst.total_pnl_usd):.2f} perdite",
                    confidence=min(worst.total_trades / 20, 1.0),
                    evidence=f"Basato su {worst.total_trades} trade negativi",
                    created_at=now,
                ))

        # Recommendation 2: Stop Loss optimization
        sl_analysis = next((p for p in parameter_analyses if p.parameter_name == "stop_loss_pct"), None)
        if sl_analysis and sl_analysis.improvement_pct > 10:
            recommendations.append(Recommendation(
                type=RecommendationType.STOP_LOSS,
                priority=RecommendationPriority.MEDIUM,
                title=f"Cambia Stop Loss da {sl_analysis.current_value}% a {sl_analysis.optimal_value}%",
                description=(
                    f"Lo stop loss a {sl_analysis.optimal_value}% mostra performance migliori "
                    f"basandosi su {sl_analysis.sample_size} trade."
                ),
                current_value=sl_analysis.current_value,
                recommended_value=sl_analysis.optimal_value,
                expected_improvement=f"+{sl_analysis.improvement_pct:.1f}% avg P&L",
                confidence=sl_analysis.confidence,
                evidence=f"Analisi di {sl_analysis.sample_size} trade",
                created_at=now,
            ))

        # Recommendation 3: Leverage optimization
        lev_analysis = next((p for p in parameter_analyses if p.parameter_name == "leverage"), None)
        if lev_analysis and lev_analysis.optimal_value != lev_analysis.current_value:
            recommendations.append(Recommendation(
                type=RecommendationType.LEVERAGE,
                priority=RecommendationPriority.LOW,
                title=f"Considera leva {lev_analysis.optimal_value}x invece di {lev_analysis.current_value}x",
                description=(
                    f"La leva {lev_analysis.optimal_value}x ha mostrato risultati migliori "
                    f"su {lev_analysis.sample_size} trade."
                ),
                current_value=lev_analysis.current_value,
                recommended_value=lev_analysis.optimal_value,
                expected_improvement="Da valutare con più dati",
                confidence=lev_analysis.confidence,
                evidence=f"Analisi di {lev_analysis.sample_size} trade",
                created_at=now,
            ))

        # Recommendation 4: Score threshold optimization
        score_analysis = next((p for p in parameter_analyses if p.parameter_name == "score_threshold_open"), None)
        if score_analysis and score_analysis.optimal_value != score_analysis.current_value:
            recommendations.append(Recommendation(
                type=RecommendationType.SCORE_THRESHOLD,
                priority=RecommendationPriority.MEDIUM if score_analysis.confidence > 0.6 else RecommendationPriority.LOW,
                title=f"Alza threshold a {score_analysis.optimal_value} (attuale: {score_analysis.current_value})",
                description=(
                    f"I trade con score {score_analysis.optimal_value}+ performano meglio. "
                    f"Win rate e P&L superiori su {score_analysis.sample_size} trade."
                ),
                current_value=score_analysis.current_value,
                recommended_value=score_analysis.optimal_value,
                expected_improvement=f"+{score_analysis.improvement_pct:.1f}% P&L stimato",
                confidence=score_analysis.confidence,
                evidence=f"Analisi di {score_analysis.sample_size} trade per fascia di score",
                created_at=now,
                details=score_analysis.breakdown,  # Include detailed breakdown
            ))

        # Recommendation 5: Trailing stop optimization
        trailing_analysis = next((p for p in parameter_analyses if p.parameter_name == "trailing_steps"), None)
        if trailing_analysis:
            if trailing_analysis.optimal_value == "tighter":
                recommendations.append(Recommendation(
                    type=RecommendationType.TRADING_STYLE,
                    priority=RecommendationPriority.MEDIUM,
                    title="Trailing stop troppo largo - stringi gli step",
                    description=(
                        f"I trade restituiscono troppo profitto prima di chiudersi. "
                        f"Considera di attivare step più aggressivi nel trailing."
                    ),
                    current_value="trailing_steps attuale",
                    recommended_value="Aggiungi step intermedi (es: 4.0:2.0)",
                    expected_improvement=f"+{trailing_analysis.improvement_pct:.1f}% profitto recuperabile",
                    confidence=trailing_analysis.confidence,
                    evidence=f"Basato su {trailing_analysis.sample_size} trade con profit restituito",
                    created_at=now,
                ))
            elif trailing_analysis.optimal_value == "looser":
                recommendations.append(Recommendation(
                    type=RecommendationType.TRADING_STYLE,
                    priority=RecommendationPriority.LOW,
                    title="Trailing stop troppo stretto - lascia correre i profitti",
                    description=(
                        "Molti trade profittevoli vengono chiusi dal trailing prima "
                        "di raggiungere il take profit."
                    ),
                    current_value="trailing_steps attuale",
                    recommended_value="Allarga gli step (es: 3.0:0.0,6.0:2.0)",
                    expected_improvement="Più trade potrebbero raggiungere TP",
                    confidence=trailing_analysis.confidence,
                    evidence=f"Basato su {trailing_analysis.sample_size} trade",
                    created_at=now,
                ))

        # Recommendation 6: Symbol-specific recommendations
        for p in parameter_analyses:
            if p.parameter_name.startswith("symbol_"):
                symbol = p.parameter_name.replace("symbol_", "")
                if p.optimal_value == "disabled":
                    recommendations.append(Recommendation(
                        type=RecommendationType.TRADING_STYLE,
                        priority=RecommendationPriority.MEDIUM if p.confidence > 0.6 else RecommendationPriority.LOW,
                        title=f"Considera di disabilitare {symbol}",
                        description=(
                            f"{symbol} sta perdendo ${p.improvement_pct:.2f} con win rate basso. "
                            f"Potrebbe non essere adatto alla strategia corrente."
                        ),
                        current_value="enabled",
                        recommended_value="disabled",
                        expected_improvement=f"Evita -${p.improvement_pct:.2f} perdite",
                        confidence=p.confidence,
                        evidence=f"Basato su {p.sample_size} trade su {symbol}",
                        created_at=now,
                    ))
                elif p.optimal_value == "increased_weight":
                    recommendations.append(Recommendation(
                        type=RecommendationType.TRADING_STYLE,
                        priority=RecommendationPriority.LOW,
                        title=f"{symbol} è il symbol più performante",
                        description=(
                            f"{symbol} sta generando ${p.improvement_pct:.2f} di profitto "
                            f"con win rate alto. Considera di aumentare la size su questo symbol."
                        ),
                        current_value="standard",
                        recommended_value="aumenta position size",
                        expected_improvement=f"Potenziale +${p.improvement_pct:.2f}",
                        confidence=p.confidence,
                        evidence=f"Basato su {p.sample_size} trade su {symbol}",
                        created_at=now,
                    ))

        # Sort by priority
        priority_order = {
            RecommendationPriority.HIGH: 0,
            RecommendationPriority.MEDIUM: 1,
            RecommendationPriority.LOW: 2,
        }
        recommendations.sort(key=lambda r: priority_order[r.priority])

        return recommendations

    def _save_report(self, report: AnalyticsReport) -> None:
        """Save report to database."""
        try:
            # For now, just log. Could add a reports table later.
            logger.info(f"Report saved: {report.report_id}")
            logger.info(f"  - Trades analyzed: {report.total_trades_analyzed}")
            logger.info(f"  - Total P&L: ${report.total_pnl_usd:.2f}")
            logger.info(f"  - Best AI: {report.best_ai_model}")
            logger.info(f"  - Recommendations: {len(report.recommendations)}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    def apply_recommendation(self, recommendation: Recommendation) -> Dict[str, Any]:
        """
        Apply a recommendation by updating the variant configuration.

        Returns dict with success status and details.
        """
        result = {
            "success": False,
            "recommendation_type": recommendation.type.value,
            "message": "",
            "changes": [],
        }

        try:
            if recommendation.type == RecommendationType.AI_MODEL:
                # Toggle AI model on/off
                if recommendation.recommended_value == "disabled":
                    # Find sub-variants with this model and disable them
                    sub_variants = self.db.get_all_sub_variants()
                    for sv in sub_variants:
                        if recommendation.current_value in sv.ai_model:
                            self.db.toggle_sub_variant(sv.id, enabled=False)
                            result["changes"].append(f"Disabilitato {sv.ai_model_name}")
                    result["success"] = True
                    result["message"] = f"AI model disabilitato"

            elif recommendation.type == RecommendationType.STOP_LOSS:
                # Update stop loss in variant trading params
                variants = self.db.get_all_variants(enabled_only=True)
                for variant in variants:
                    old_sl = variant.trading_params.stop_loss_pct
                    variant.trading_params.stop_loss_pct = recommendation.recommended_value
                    self.db.save_variant(variant)
                    result["changes"].append(
                        f"{variant.id}: SL {old_sl}% → {recommendation.recommended_value}%"
                    )
                result["success"] = True
                result["message"] = f"Stop loss aggiornato a {recommendation.recommended_value}%"

            elif recommendation.type == RecommendationType.SCORE_THRESHOLD:
                # Update score threshold in variant trading params
                variants = self.db.get_all_variants(enabled_only=True)
                for variant in variants:
                    old_threshold = variant.trading_params.score_threshold_open
                    variant.trading_params.score_threshold_open = recommendation.recommended_value
                    self.db.save_variant(variant)
                    result["changes"].append(
                        f"{variant.id}: threshold {old_threshold} → {recommendation.recommended_value}"
                    )
                result["success"] = True
                result["message"] = f"Score threshold aggiornato a {recommendation.recommended_value}"

            elif recommendation.type == RecommendationType.LEVERAGE:
                # Update leverage in variant trading params
                variants = self.db.get_all_variants(enabled_only=True)
                for variant in variants:
                    old_lev = variant.trading_params.leverage
                    variant.trading_params.leverage = int(recommendation.recommended_value)
                    self.db.save_variant(variant)
                    result["changes"].append(
                        f"{variant.id}: leverage {old_lev}x → {recommendation.recommended_value}x"
                    )
                result["success"] = True
                result["message"] = f"Leverage aggiornato a {recommendation.recommended_value}x"

            elif recommendation.type == RecommendationType.TRADING_STYLE:
                # Handle symbol disable or trailing stop changes
                if "symbol_" in str(recommendation.title).lower() or "disabilita" in recommendation.title.lower():
                    # Extract symbol from title
                    import re
                    match = re.search(r'(BTC|ETH|SOL|DOGE|AVAX|ARB|SUI)', recommendation.title)
                    if match:
                        symbol = match.group(1)
                        variants = self.db.get_all_variants(enabled_only=True)
                        for variant in variants:
                            if symbol in variant.symbols:
                                variant.symbols.remove(symbol)
                                self.db.save_variant(variant)
                                result["changes"].append(f"{variant.id}: rimosso {symbol}")
                        result["success"] = True
                        result["message"] = f"Symbol {symbol} rimosso dalle strategie"
                elif "trailing" in recommendation.title.lower():
                    # Log suggestion - trailing steps require manual review
                    result["success"] = False
                    result["message"] = "Modifica trailing steps richiede revisione manuale"
                    result["changes"].append(
                        f"Suggerimento: {recommendation.recommended_value}"
                    )

            else:
                result["message"] = f"Tipo raccomandazione non supportato: {recommendation.type.value}"

        except Exception as e:
            result["message"] = f"Errore applicando raccomandazione: {str(e)}"
            logger.error(f"Error applying recommendation: {e}")

        return result

    def apply_all_high_priority(self) -> List[Dict[str, Any]]:
        """
        Apply all HIGH priority recommendations automatically.

        Returns list of results for each applied recommendation.
        """
        if not self._last_report:
            return [{"success": False, "message": "Nessun report disponibile"}]

        results = []
        high_priority = [
            r for r in self._last_report.recommendations
            if r.priority == RecommendationPriority.HIGH
        ]

        for rec in high_priority:
            result = self.apply_recommendation(rec)
            results.append(result)
            logger.info(f"Applied recommendation: {rec.title} - {result['message']}")

        return results

    def get_insights_for_prompt(self) -> str:
        """
        Generate insights text to include in V5_AI_FREE prompt.
        This gives the AI context about what's working.
        """
        if not self._last_report:
            return ""

        insights = []

        # Best performing model
        if self._last_report.ai_rankings:
            best = self._last_report.ai_rankings[0]
            insights.append(
                f"Top performing AI: {best.model_name} "
                f"(Win rate: {best.win_rate:.0%}, P&L: ${best.total_pnl_usd:.2f})"
            )

        # Key recommendations
        high_priority = [r for r in self._last_report.recommendations
                        if r.priority == RecommendationPriority.HIGH]
        for rec in high_priority[:2]:
            insights.append(f"Insight: {rec.description}")

        # Best variant
        if self._last_report.best_performing_variant:
            insights.append(
                f"Best strategy: {self._last_report.best_performing_variant}"
            )

        if insights:
            return "\n\nARENA INSIGHTS (from last 24h analysis):\n" + "\n".join(f"- {i}" for i in insights)
        return ""
