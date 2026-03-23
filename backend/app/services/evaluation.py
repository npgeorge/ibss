"""
Domain-Specific Evaluation Framework

Tracks and evaluates the performance of stock screening recommendations.
Measures accuracy of predictions, signal quality, and portfolio performance.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import statistics


@dataclass
class ScreeningPrediction:
    """Record of a screening recommendation for evaluation"""
    symbol: str
    scan_date: date
    composite_score: float
    grade: str
    criteria_met: int
    criteria_total: int
    entry_signal: Optional[str]
    price_at_scan: float
    magic_line_value: Optional[float]
    insider_sentiment: str

    # Fields populated after outcome known
    price_30d: Optional[float] = None
    price_60d: Optional[float] = None
    price_90d: Optional[float] = None
    max_gain_90d: Optional[float] = None
    max_drawdown_90d: Optional[float] = None
    outcome_evaluated: bool = False

    def return_30d(self) -> Optional[float]:
        if self.price_30d:
            return (self.price_30d - self.price_at_scan) / self.price_at_scan
        return None

    def return_60d(self) -> Optional[float]:
        if self.price_60d:
            return (self.price_60d - self.price_at_scan) / self.price_at_scan
        return None

    def return_90d(self) -> Optional[float]:
        if self.price_90d:
            return (self.price_90d - self.price_at_scan) / self.price_at_scan
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['scan_date'] = self.scan_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScreeningPrediction':
        data = data.copy()
        if isinstance(data.get('scan_date'), str):
            data['scan_date'] = date.fromisoformat(data['scan_date'])
        return cls(**data)


@dataclass
class EvaluationMetrics:
    """Aggregated metrics for screening performance"""
    total_predictions: int = 0
    evaluated_predictions: int = 0

    # Win rates at different thresholds
    win_rate_5pct_30d: float = 0.0   # % of picks up 5%+ at 30 days
    win_rate_10pct_60d: float = 0.0  # % of picks up 10%+ at 60 days
    win_rate_20pct_90d: float = 0.0  # % of picks up 20%+ at 90 days

    # Average returns
    avg_return_30d: float = 0.0
    avg_return_60d: float = 0.0
    avg_return_90d: float = 0.0

    # Risk metrics
    avg_max_drawdown: float = 0.0
    sharpe_ratio: Optional[float] = None

    # Score correlation
    score_return_correlation: Optional[float] = None

    # Signal effectiveness
    signal_effectiveness: Dict[str, float] = field(default_factory=dict)

    # Grade distribution performance
    grade_performance: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CriterionEvaluation:
    """Evaluation of a single criterion's predictive power"""
    criterion_name: str
    correlation_with_returns: float
    avg_score_winners: float
    avg_score_losers: float
    predictive_power: float  # 0-1 score


class EvaluationService:
    """
    Service for tracking and evaluating screening predictions.

    Stores predictions and their outcomes, calculates performance metrics,
    and identifies which criteria are most predictive.
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            base_dir = Path(__file__).parent.parent.parent
            storage_path = base_dir / "data" / "evaluations"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._predictions: List[ScreeningPrediction] = []
        self._load_predictions()

    def _load_predictions(self):
        """Load stored predictions from disk"""
        predictions_file = self.storage_path / "predictions.json"
        if predictions_file.exists():
            with open(predictions_file) as f:
                data = json.load(f)
                self._predictions = [
                    ScreeningPrediction.from_dict(p) for p in data
                ]

    def _save_predictions(self):
        """Save predictions to disk"""
        predictions_file = self.storage_path / "predictions.json"
        with open(predictions_file, 'w') as f:
            json.dump([p.to_dict() for p in self._predictions], f, indent=2)

    def record_prediction(self, prediction: ScreeningPrediction):
        """
        Record a new screening prediction for future evaluation.

        Args:
            prediction: The screening result to track
        """
        # Check for duplicate (same symbol and date)
        for existing in self._predictions:
            if existing.symbol == prediction.symbol and existing.scan_date == prediction.scan_date:
                return  # Already recorded

        self._predictions.append(prediction)
        self._save_predictions()

    def record_from_screening_result(
        self,
        symbol: str,
        composite_score: float,
        grade: str,
        criteria_met: int,
        criteria_total: int,
        entry_signal: Optional[str],
        price: float,
        magic_line: Optional[float],
        insider_sentiment: str
    ):
        """
        Record a prediction from screening results.

        Convenience method that creates a ScreeningPrediction from common fields.
        """
        prediction = ScreeningPrediction(
            symbol=symbol,
            scan_date=date.today(),
            composite_score=composite_score,
            grade=grade,
            criteria_met=criteria_met,
            criteria_total=criteria_total,
            entry_signal=entry_signal,
            price_at_scan=price,
            magic_line_value=magic_line,
            insider_sentiment=insider_sentiment
        )
        self.record_prediction(prediction)

    async def update_outcomes(self, price_fetcher):
        """
        Update outcome prices for predictions that are due.

        Args:
            price_fetcher: Async function that takes symbol and returns current price
        """
        today = date.today()
        updated = False

        for pred in self._predictions:
            if pred.outcome_evaluated:
                continue

            days_since_scan = (today - pred.scan_date).days

            # Update 30-day price
            if days_since_scan >= 30 and pred.price_30d is None:
                try:
                    price = await price_fetcher(pred.symbol)
                    if price:
                        pred.price_30d = price
                        updated = True
                except Exception:
                    pass

            # Update 60-day price
            if days_since_scan >= 60 and pred.price_60d is None:
                try:
                    price = await price_fetcher(pred.symbol)
                    if price:
                        pred.price_60d = price
                        updated = True
                except Exception:
                    pass

            # Update 90-day price (and mark as evaluated)
            if days_since_scan >= 90 and pred.price_90d is None:
                try:
                    price = await price_fetcher(pred.symbol)
                    if price:
                        pred.price_90d = price
                        pred.outcome_evaluated = True
                        updated = True
                except Exception:
                    pass

        if updated:
            self._save_predictions()

    def calculate_metrics(self) -> EvaluationMetrics:
        """
        Calculate aggregate evaluation metrics across all predictions.

        Returns:
            EvaluationMetrics with win rates, returns, and other statistics
        """
        metrics = EvaluationMetrics()
        metrics.total_predictions = len(self._predictions)

        # Filter to evaluated predictions
        evaluated = [p for p in self._predictions if p.outcome_evaluated]
        metrics.evaluated_predictions = len(evaluated)

        if not evaluated:
            return metrics

        # Calculate win rates
        wins_5pct_30d = sum(1 for p in evaluated if p.return_30d() and p.return_30d() >= 0.05)
        wins_10pct_60d = sum(1 for p in evaluated if p.return_60d() and p.return_60d() >= 0.10)
        wins_20pct_90d = sum(1 for p in evaluated if p.return_90d() and p.return_90d() >= 0.20)

        metrics.win_rate_5pct_30d = wins_5pct_30d / len(evaluated)
        metrics.win_rate_10pct_60d = wins_10pct_60d / len(evaluated)
        metrics.win_rate_20pct_90d = wins_20pct_90d / len(evaluated)

        # Calculate average returns
        returns_30d = [p.return_30d() for p in evaluated if p.return_30d() is not None]
        returns_60d = [p.return_60d() for p in evaluated if p.return_60d() is not None]
        returns_90d = [p.return_90d() for p in evaluated if p.return_90d() is not None]

        if returns_30d:
            metrics.avg_return_30d = statistics.mean(returns_30d)
        if returns_60d:
            metrics.avg_return_60d = statistics.mean(returns_60d)
        if returns_90d:
            metrics.avg_return_90d = statistics.mean(returns_90d)

        # Calculate max drawdown average
        drawdowns = [p.max_drawdown_90d for p in evaluated if p.max_drawdown_90d is not None]
        if drawdowns:
            metrics.avg_max_drawdown = statistics.mean(drawdowns)

        # Calculate score-return correlation
        if returns_90d and len(returns_90d) >= 5:
            scores = [p.composite_score for p in evaluated if p.return_90d() is not None]
            metrics.score_return_correlation = self._calculate_correlation(scores, returns_90d)

        # Calculate signal effectiveness
        metrics.signal_effectiveness = self._calculate_signal_effectiveness(evaluated)

        # Calculate grade performance
        metrics.grade_performance = self._calculate_grade_performance(evaluated)

        return metrics

    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y)

    def _calculate_signal_effectiveness(self, predictions: List[ScreeningPrediction]) -> Dict[str, float]:
        """Calculate average return by entry signal type"""
        signal_returns: Dict[str, List[float]] = {}

        for pred in predictions:
            if pred.entry_signal and pred.return_90d() is not None:
                if pred.entry_signal not in signal_returns:
                    signal_returns[pred.entry_signal] = []
                signal_returns[pred.entry_signal].append(pred.return_90d())

        return {
            signal: statistics.mean(returns) if returns else 0.0
            for signal, returns in signal_returns.items()
        }

    def _calculate_grade_performance(self, predictions: List[ScreeningPrediction]) -> Dict[str, Dict[str, float]]:
        """Calculate average return by grade"""
        grade_returns: Dict[str, List[float]] = {}

        for pred in predictions:
            if pred.return_90d() is not None:
                if pred.grade not in grade_returns:
                    grade_returns[pred.grade] = []
                grade_returns[pred.grade].append(pred.return_90d())

        return {
            grade: {
                "avg_return": statistics.mean(returns) if returns else 0.0,
                "count": len(returns),
                "win_rate": sum(1 for r in returns if r > 0) / len(returns) if returns else 0.0
            }
            for grade, returns in grade_returns.items()
        }

    def get_predictions_by_date_range(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[ScreeningPrediction]:
        """Get predictions within a date range"""
        result = self._predictions

        if start_date:
            result = [p for p in result if p.scan_date >= start_date]
        if end_date:
            result = [p for p in result if p.scan_date <= end_date]

        return result

    def get_top_performers(self, n: int = 10) -> List[ScreeningPrediction]:
        """Get the top N performing predictions by 90-day return"""
        evaluated = [p for p in self._predictions if p.return_90d() is not None]
        evaluated.sort(key=lambda p: p.return_90d() or 0, reverse=True)
        return evaluated[:n]

    def get_worst_performers(self, n: int = 10) -> List[ScreeningPrediction]:
        """Get the worst N performing predictions by 90-day return"""
        evaluated = [p for p in self._predictions if p.return_90d() is not None]
        evaluated.sort(key=lambda p: p.return_90d() or 0)
        return evaluated[:n]

    def generate_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive evaluation report.

        Returns:
            Dictionary containing metrics, top/worst performers, and insights
        """
        metrics = self.calculate_metrics()

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_predictions": metrics.total_predictions,
                "evaluated_predictions": metrics.evaluated_predictions,
                "pending_evaluation": metrics.total_predictions - metrics.evaluated_predictions
            },
            "performance": {
                "win_rates": {
                    "5%_at_30_days": f"{metrics.win_rate_5pct_30d:.1%}",
                    "10%_at_60_days": f"{metrics.win_rate_10pct_60d:.1%}",
                    "20%_at_90_days": f"{metrics.win_rate_20pct_90d:.1%}"
                },
                "average_returns": {
                    "30_day": f"{metrics.avg_return_30d:.1%}",
                    "60_day": f"{metrics.avg_return_60d:.1%}",
                    "90_day": f"{metrics.avg_return_90d:.1%}"
                },
                "risk": {
                    "avg_max_drawdown": f"{metrics.avg_max_drawdown:.1%}"
                }
            },
            "score_effectiveness": {
                "score_return_correlation": metrics.score_return_correlation,
                "interpretation": self._interpret_correlation(metrics.score_return_correlation)
            },
            "signal_effectiveness": metrics.signal_effectiveness,
            "grade_performance": metrics.grade_performance,
            "top_performers": [p.to_dict() for p in self.get_top_performers(5)],
            "worst_performers": [p.to_dict() for p in self.get_worst_performers(5)]
        }

        return report

    def _interpret_correlation(self, correlation: Optional[float]) -> str:
        """Interpret correlation strength"""
        if correlation is None:
            return "Insufficient data"
        if correlation > 0.7:
            return "Strong positive - higher scores predict better returns"
        if correlation > 0.4:
            return "Moderate positive - scores have predictive value"
        if correlation > 0.1:
            return "Weak positive - some predictive signal"
        if correlation > -0.1:
            return "No correlation - scores not predictive"
        return "Negative correlation - review scoring methodology"


# Singleton instance
_service: Optional[EvaluationService] = None


def get_evaluation_service() -> EvaluationService:
    """Get the global evaluation service instance"""
    global _service
    if _service is None:
        _service = EvaluationService()
    return _service
