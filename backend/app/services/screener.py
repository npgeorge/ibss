"""
Superstock Screener Service

Implements the complete Superstock screening methodology:
- Technical scoring (Magic Line, volume, patterns)
- Fundamental scoring (earnings growth, revenue, valuation)
- Insider scoring (recent buying, cluster activity)
- Composite scoring and ranking
"""
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

from app.services.magic_line import MagicLineDetector
from app.services.technical_indicators import TechnicalIndicatorCalculator
from app.services.pattern_recognition import PatternRecognizer
from app.services.insider_parser import InsiderActivityAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class ScreeningCriteria:
    """Screening filter criteria"""

    # Technical
    price_min: float = 0.5
    price_max: float = 10.0
    volume_min: int = 100000
    magic_line_respect: bool = True
    magic_line_min_score: float = 50.0

    # Fundamental
    earnings_growth_min: Optional[float] = 20.0  # % YoY
    revenue_growth_min: Optional[float] = 20.0  # % YoY
    pe_ratio_max: Optional[float] = 30.0
    market_cap_min: Optional[int] = 10_000_000
    market_cap_max: Optional[int] = 2_000_000_000

    # Insider
    insider_buying_days: int = 90
    min_insider_transactions: int = 1

    # Scoring
    min_total_score: float = 70.0


@dataclass
class StockScore:
    """Stock scoring result"""

    symbol: str
    technical_score: float  # 0-100
    fundamental_score: float  # 0-100
    insider_score: float  # 0-100
    pattern_score: float  # 0-100
    total_score: float  # 0-100
    rank: Optional[int] = None

    # Details
    score_breakdown: Dict = None
    magic_line_period: Optional[int] = None
    magic_line_distance: Optional[float] = None
    patterns_detected: List[str] = None
    entry_price: Optional[float] = None


class SuperstockScorer:
    """
    Score stocks based on Superstock methodology

    Scoring Weights:
    - Technical: 40% (Magic Line 15%, Volume 10%, Patterns 10%, RS 5%)
    - Fundamental: 30% (Earnings 15%, Revenue 10%, Valuation 5%)
    - Insider: 30% (Recent 15%, Cluster 10%, Increasing 5%)
    """

    # Scoring weights
    WEIGHTS = {
        "technical": {
            "magic_line": 0.15,
            "volume": 0.10,
            "patterns": 0.10,
            "relative_strength": 0.05,
        },
        "fundamental": {
            "earnings_growth": 0.15,
            "revenue_growth": 0.10,
            "valuation": 0.05,
        },
        "insider": {
            "recent_buying": 0.15,
            "cluster_buying": 0.10,
            "price_trend": 0.05,
        },
    }

    def __init__(
        self,
        price_data: pd.DataFrame,
        stock_info: Dict,
        fundamentals: Optional[Dict] = None,
        insider_transactions: Optional[List[Dict]] = None,
    ):
        """
        Initialize scorer

        Args:
            price_data: Historical price data
            stock_info: Stock information (symbol, name, sector, etc.)
            fundamentals: Fundamental metrics
            insider_transactions: Insider transaction list
        """
        self.price_data = price_data
        self.stock_info = stock_info
        self.fundamentals = fundamentals or {}
        self.insider_transactions = insider_transactions or []

    def calculate_composite_score(self) -> StockScore:
        """
        Calculate complete composite score

        Returns:
            StockScore with all component scores
        """
        # Calculate component scores
        tech_score, tech_details = self.calculate_technical_score()
        fund_score, fund_details = self.calculate_fundamental_score()
        insider_score, insider_details = self.calculate_insider_score()
        pattern_score, pattern_details = self.calculate_pattern_score()

        # Calculate total (weighted)
        total_score = (
            tech_score * 0.40 + fund_score * 0.30 + insider_score * 0.30
        )

        # Combine details
        breakdown = {
            "technical": tech_details,
            "fundamental": fund_details,
            "insider": insider_details,
            "patterns": pattern_details,
        }

        return StockScore(
            symbol=self.stock_info.get("symbol", "UNKNOWN"),
            technical_score=round(tech_score, 2),
            fundamental_score=round(fund_score, 2),
            insider_score=round(insider_score, 2),
            pattern_score=round(pattern_score, 2),
            total_score=round(total_score, 2),
            score_breakdown=breakdown,
            magic_line_period=tech_details.get("magic_line_period"),
            magic_line_distance=tech_details.get("magic_line_distance"),
            patterns_detected=pattern_details.get("patterns_detected", []),
            entry_price=pattern_details.get("entry_price"),
        )

    def calculate_technical_score(self) -> tuple[float, Dict]:
        """
        Calculate technical analysis score

        Components:
        - Magic Line respect (15%)
        - Volume profile (10%)
        - Pattern strength (10%)
        - Relative strength (5%)

        Returns:
            (score, details dict)
        """
        score = 0.0
        details = {}

        try:
            # Magic Line
            ml_detector = MagicLineDetector(self.price_data)
            ml_result = ml_detector.find_magic_line()

            ml_score = ml_result.score
            score += ml_score * (self.WEIGHTS["technical"]["magic_line"] / 0.40)

            details["magic_line_score"] = ml_score
            details["magic_line_period"] = ml_result.period
            details["magic_line_distance"] = ml_result.distance_percent

            # Volume
            volume_score = self._calculate_volume_score()
            score += volume_score * (self.WEIGHTS["technical"]["volume"] / 0.40)
            details["volume_score"] = volume_score

            # Relative Strength (simplified - compare to recent performance)
            rs_score = self._calculate_relative_strength_score()
            score += rs_score * (self.WEIGHTS["technical"]["relative_strength"] / 0.40)
            details["relative_strength_score"] = rs_score

            # Pattern contribution is separate
            # Just add base pattern score here
            pattern_score, _ = self.calculate_pattern_score()
            score += pattern_score * (self.WEIGHTS["technical"]["patterns"] / 0.40)
            details["pattern_contribution"] = pattern_score

        except Exception as e:
            logger.error(f"Error calculating technical score: {e}")

        return min(score * 100, 100), details

    def calculate_fundamental_score(self) -> tuple[float, Dict]:
        """
        Calculate fundamental analysis score

        Components:
        - Earnings growth (15%)
        - Revenue growth (10%)
        - Valuation (5%)

        Returns:
            (score, details dict)
        """
        score = 0.0
        details = {}

        if not self.fundamentals:
            return 0.0, {"note": "No fundamental data"}

        try:
            # Earnings growth
            eps_growth = self.fundamentals.get("eps_growth_yoy", 0)
            if eps_growth >= 50:
                earnings_score = 100
            elif eps_growth >= 20:
                earnings_score = 70 + (eps_growth - 20) / 30 * 30
            elif eps_growth >= 0:
                earnings_score = eps_growth / 20 * 70
            else:
                earnings_score = 0

            score += earnings_score * (self.WEIGHTS["fundamental"]["earnings_growth"] / 0.30)
            details["earnings_growth"] = eps_growth
            details["earnings_score"] = earnings_score

            # Revenue growth
            rev_growth = self.fundamentals.get("revenue_growth_yoy", 0)
            if rev_growth >= 50:
                revenue_score = 100
            elif rev_growth >= 20:
                revenue_score = 70 + (rev_growth - 20) / 30 * 30
            elif rev_growth >= 0:
                revenue_score = rev_growth / 20 * 70
            else:
                revenue_score = 0

            score += revenue_score * (self.WEIGHTS["fundamental"]["revenue_growth"] / 0.30)
            details["revenue_growth"] = rev_growth
            details["revenue_score"] = revenue_score

            # Valuation (PEG ratio - lower is better)
            peg_ratio = self.fundamentals.get("peg_ratio")
            if peg_ratio:
                if peg_ratio < 1.0:
                    valuation_score = 100
                elif peg_ratio < 2.0:
                    valuation_score = 100 - (peg_ratio - 1.0) * 50
                else:
                    valuation_score = max(50 - (peg_ratio - 2.0) * 25, 0)
            else:
                valuation_score = 50  # Neutral if no data

            score += valuation_score * (self.WEIGHTS["fundamental"]["valuation"] / 0.30)
            details["peg_ratio"] = peg_ratio
            details["valuation_score"] = valuation_score

        except Exception as e:
            logger.error(f"Error calculating fundamental score: {e}")

        return min(score * 100, 100), details

    def calculate_insider_score(self) -> tuple[float, Dict]:
        """
        Calculate insider activity score

        Components:
        - Recent buying activity (15%)
        - Cluster buying (10%)
        - Buying at increasing prices (5%)

        Returns:
            (score, details dict)
        """
        score = 0.0
        details = {}

        if not self.insider_transactions:
            return 0.0, {"note": "No insider data"}

        try:
            # Use analyzer
            analyzer = InsiderActivityAnalyzer()

            # Overall confidence score
            confidence = analyzer.calculate_insider_confidence_score(
                self.insider_transactions
            )

            # Recent buying
            purchases = [
                t for t in self.insider_transactions if t["transaction_type"] == "purchase"
            ]
            recent_score = min(len(purchases) * 20, 100)

            score += recent_score * (self.WEIGHTS["insider"]["recent_buying"] / 0.30)
            details["recent_purchases"] = len(purchases)
            details["recent_buying_score"] = recent_score

            # Cluster buying
            has_cluster = analyzer.detect_cluster_buying(self.insider_transactions)
            cluster_score = 100 if has_cluster else 30

            score += cluster_score * (self.WEIGHTS["insider"]["cluster_buying"] / 0.30)
            details["cluster_buying"] = has_cluster
            details["cluster_score"] = cluster_score

            # Price trend (buying at increasing prices)
            price_trend_score = self._calculate_insider_price_trend()
            score += price_trend_score * (self.WEIGHTS["insider"]["price_trend"] / 0.30)
            details["price_trend_score"] = price_trend_score

            details["overall_confidence"] = confidence

        except Exception as e:
            logger.error(f"Error calculating insider score: {e}")

        return min(score * 100, 100), details

    def calculate_pattern_score(self) -> tuple[float, Dict]:
        """
        Calculate pattern recognition score

        Returns:
            (score, details dict)
        """
        score = 0.0
        details = {"patterns_detected": []}

        try:
            recognizer = PatternRecognizer(self.price_data)
            patterns = recognizer.detect_all_patterns()

            if patterns:
                # Average strength of detected patterns
                avg_strength = sum(p.strength_score for p in patterns) / len(patterns)
                score = avg_strength

                details["patterns_detected"] = [p.pattern_type for p in patterns]
                details["pattern_count"] = len(patterns)
                details["average_strength"] = avg_strength

                # Best pattern for entry
                best_pattern = max(patterns, key=lambda p: p.strength_score)
                details["best_pattern"] = best_pattern.pattern_type
                details["entry_price"] = best_pattern.entry_price
                details["stop_loss"] = best_pattern.stop_loss
                details["target_price"] = best_pattern.target_price

        except Exception as e:
            logger.error(f"Error calculating pattern score: {e}")

        return score, details

    def _calculate_volume_score(self) -> float:
        """Calculate volume score based on recent activity"""
        if len(self.price_data) < 20:
            return 0.0

        recent = self.price_data.tail(20)
        avg_volume = recent["volume"].mean()
        latest_volume = recent.iloc[-1]["volume"]

        # Recent volume vs average
        volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio >= 2.0:  # 2x average
            return 100
        elif volume_ratio >= 1.5:
            return 70 + (volume_ratio - 1.5) * 60
        elif volume_ratio >= 1.0:
            return volume_ratio * 70
        else:
            return volume_ratio * 50

    def _calculate_relative_strength_score(self) -> float:
        """Calculate relative strength score"""
        if len(self.price_data) < 50:
            return 50.0

        # Simple: compare recent performance
        recent_30 = self.price_data.tail(30)
        gain_30d = (
            recent_30.iloc[-1]["close"] / recent_30.iloc[0]["close"] - 1
        )

        # Positive gains get higher scores
        if gain_30d > 0.30:  # 30%+ gain
            return 100
        elif gain_30d > 0.10:  # 10-30%
            return 70 + (gain_30d - 0.10) / 0.20 * 30
        elif gain_30d > 0:
            return 50 + (gain_30d / 0.10) * 20
        else:
            return max(50 + gain_30d * 100, 0)

    def _calculate_insider_price_trend(self) -> float:
        """Check if insiders are buying at increasing prices"""
        purchases = [
            t
            for t in self.insider_transactions
            if t["transaction_type"] == "purchase" and t["price_per_share"] > 0
        ]

        if len(purchases) < 2:
            return 50.0

        # Sort by date
        sorted_purchases = sorted(purchases, key=lambda x: x["transaction_date"])

        # Check if prices are increasing
        prices = [t["price_per_share"] for t in sorted_purchases]

        if prices[-1] > prices[0]:
            return 100
        else:
            return 30


class SuperstockScreener:
    """
    Screen stocks for Superstock opportunities

    This combines all the scoring logic with filtering criteria
    """

    def __init__(self, criteria: ScreeningCriteria):
        self.criteria = criteria

    def screen_stock(
        self,
        price_data: pd.DataFrame,
        stock_info: Dict,
        fundamentals: Optional[Dict] = None,
        insider_transactions: Optional[List[Dict]] = None,
    ) -> Optional[StockScore]:
        """
        Screen a single stock

        Args:
            price_data: Price history
            stock_info: Stock metadata
            fundamentals: Fundamental data
            insider_transactions: Insider activity

        Returns:
            StockScore if passes filters, None otherwise
        """
        # Apply filters
        if not self._passes_filters(price_data, stock_info, fundamentals):
            return None

        # Calculate score
        scorer = SuperstockScorer(price_data, stock_info, fundamentals, insider_transactions)
        score = scorer.calculate_composite_score()

        # Check minimum score
        if score.total_score < self.criteria.min_total_score:
            return None

        return score

    def _passes_filters(
        self, price_data: pd.DataFrame, stock_info: Dict, fundamentals: Optional[Dict]
    ) -> bool:
        """Check if stock passes filter criteria"""
        # Price filter
        current_price = float(price_data.iloc[-1]["close"])
        if not (self.criteria.price_min <= current_price <= self.criteria.price_max):
            return False

        # Volume filter
        avg_volume = price_data.tail(20)["volume"].mean()
        if avg_volume < self.criteria.volume_min:
            return False

        # Market cap filter
        market_cap = stock_info.get("market_cap", 0)
        if self.criteria.market_cap_min and market_cap < self.criteria.market_cap_min:
            return False
        if self.criteria.market_cap_max and market_cap > self.criteria.market_cap_max:
            return False

        # Magic Line filter
        if self.criteria.magic_line_respect:
            ml_detector = MagicLineDetector(price_data)
            ml_result = ml_detector.find_magic_line()
            if ml_result.score < self.criteria.magic_line_min_score:
                return False

        # Fundamental filters
        if fundamentals:
            if self.criteria.earnings_growth_min:
                eps_growth = fundamentals.get("eps_growth_yoy", 0)
                if eps_growth < self.criteria.earnings_growth_min:
                    return False

            if self.criteria.revenue_growth_min:
                rev_growth = fundamentals.get("revenue_growth_yoy", 0)
                if rev_growth < self.criteria.revenue_growth_min:
                    return False

            if self.criteria.pe_ratio_max:
                pe_ratio = fundamentals.get("pe_ratio")
                if pe_ratio and pe_ratio > self.criteria.pe_ratio_max:
                    return False

        return True
