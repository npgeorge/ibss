"""
Superstock Screener Service

Implements the complete Superstock screening methodology:
- Technical scoring (Magic Line, volume, patterns)
- Fundamental scoring (earnings growth, revenue, valuation)
- Insider scoring (recent buying, cluster activity)
- Composite scoring and ranking

Pipeline: Finviz pre-filter → batch yfinance fetch → score → rank
"""
import asyncio
import time
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging

from app.services.magic_line import MagicLineDetector
from app.services.technical_indicators import TechnicalIndicatorCalculator
from app.services.pattern_recognition import PatternRecognizer
from app.services.openinsider import (
    OpenInsiderScraper,
    InsiderActivitySummary,
    get_insider_score,
)
from app.services.volume_analysis import VolumeAnalyzer, VolumeAnalysis
from app.services.entry_signals import EntrySignalDetector, EntrySignalResult
from app.services.finviz_screener import (
    FinvizPreFilter,
    FinvizDetailFetcher,
    ScanMode,
    PreFilterResult,
    StockMetrics,
)
from app.services.market_data import YahooFinanceCollector

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

    # Extended details from new services
    volume_signal: Optional[str] = None
    entry_recommendation: Optional[str] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None

    # Metadata carried through so the cache/API path can render full cards
    # without a separate DB read.
    current_price: Optional[float] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[int] = None

    # Entry-timing overlay
    entry_score: Optional[float] = None  # 0-100 entry quality
    dont_chase: bool = False
    scale_in_guidance: Optional[str] = None


class SuperstockScorer:
    """
    Score stocks based on Superstock methodology

    Scoring Weights:
    - Technical: 40% (Magic Line 15%, Volume 10%, Patterns 10%, RS-vs-SPY 5%)
    - Fundamental: 30% (Earnings 8%, Revenue 6%, Valuation 3%, Float 5%,
      Balance Sheet 4%, Analyst Coverage 2%, Earnings Acceleration 2%)
    - Insider: 30% (Recent 15%, Cluster 10%, Increasing 5%)
    """

    # Top-level composite split. Single source of truth for the 40/30/30 model —
    # both the scoring math and the Method page (via /screen/scoring-model) read this.
    COMPOSITE_WEIGHTS = {
        "technical": 0.40,
        "fundamental": 0.30,
        "insider": 0.30,
    }

    # Entry-timing overlay bounds. The composite is multiplied by a factor in
    # [ENTRY_FACTOR_FLOOR, ENTRY_FACTOR_FLOOR + ENTRY_FACTOR_SPAN]; a chase
    # (price extended beyond DONT_CHASE_DISTANCE_PCT above the Magic Line) caps
    # the factor at the floor.
    ENTRY_FACTOR_FLOOR = 0.90
    ENTRY_FACTOR_SPAN = 0.15
    DONT_CHASE_DISTANCE_PCT = 20.0

    # Sub-law weights (as a fraction of the total score).
    WEIGHTS = {
        "technical": {
            "magic_line": 0.15,
            "volume": 0.10,
            "patterns": 0.10,
            "relative_strength": 0.05,
        },
        "fundamental": {
            "earnings_growth": 0.08,
            "revenue_growth": 0.06,
            "valuation": 0.03,
            "share_structure": 0.05,   # small float (Stine: low supply → explosive moves)
            "balance_sheet": 0.04,     # low debt + adequate liquidity
            "analyst_coverage": 0.02,  # under-followed / undiscovered
            "earnings_acceleration": 0.02,  # forward growth > trailing growth
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
        insider_activity: Optional[InsiderActivitySummary] = None,
        benchmark_data: Optional[pd.DataFrame] = None,
    ):
        self.price_data = price_data
        self.stock_info = stock_info
        self.fundamentals = fundamentals or {}
        self.insider_activity = insider_activity
        # Benchmark (typically SPY) used for true relative strength.
        self.benchmark_data = benchmark_data

    def calculate_composite_score(self) -> StockScore:
        """Calculate complete composite score"""
        tech_score, tech_details = self.calculate_technical_score()
        fund_score, fund_details = self.calculate_fundamental_score()
        insider_score, insider_details = self.calculate_insider_score()
        pattern_score, pattern_details = self.calculate_pattern_score()

        # Calculate total (weighted)
        cw = self.COMPOSITE_WEIGHTS
        total_score = (
            tech_score * cw["technical"]
            + fund_score * cw["fundamental"]
            + insider_score * cw["insider"]
        )

        # Volume analysis (enrichment, does not change score)
        volume_signal = None
        try:
            va = VolumeAnalyzer(self.price_data)
            vol_result = va.analyze()
            volume_signal = vol_result.signal
            tech_details["volume_analysis"] = {
                "signal": vol_result.signal,
                "overall_score": vol_result.overall_score,
                "dryup_score": vol_result.dryup.score,
                "pullback_score": vol_result.pullback.score,
                "surge_score": vol_result.surge.score,
            }
        except Exception as e:
            logger.debug(f"Volume analysis failed: {e}")

        # Entry signals (enrichment + entry-timing overlay)
        entry_rec = None
        entry_stop = None
        entry_target = None
        entry_score = None
        dont_chase = False
        scale_in_guidance = None
        try:
            ml_period = tech_details.get("magic_line_period", 10) or 10
            detector = EntrySignalDetector(self.price_data, magic_line_period=ml_period)
            sig_result = detector.detect_signals()
            entry_rec = sig_result.recommendation
            entry_score = sig_result.overall_score
            dont_chase = sig_result.dont_chase
            scale_in_guidance = sig_result.scale_in_guidance
            if sig_result.best_signal:
                entry_stop = sig_result.best_signal.stop_loss
                entry_target = sig_result.best_signal.target_price
            tech_details["entry_signals"] = {
                "recommendation": sig_result.recommendation,
                "signal_count": len(sig_result.signals),
                "best_signal_type": sig_result.best_signal.signal_type.value if sig_result.best_signal else None,
                "best_signal_score": sig_result.best_signal.score if sig_result.best_signal else 0,
                "overall_score": sig_result.overall_score,
                "dont_chase": sig_result.dont_chase,
                "distance_from_magic_line_pct": sig_result.distance_from_magic_line_pct,
            }
        except Exception as e:
            logger.debug(f"Entry signal detection failed: {e}")

        # Entry-timing overlay: bounded multiplier on the 40/30/30 core so a clean
        # entry near the Magic Line is rewarded and a chase is penalized, without
        # overriding the underlying quality score. Factor stays in [0.90, 1.05].
        if entry_score is not None:
            entry_factor = self.ENTRY_FACTOR_FLOOR + (entry_score / 100.0) * self.ENTRY_FACTOR_SPAN
        else:
            entry_factor = 1.0
        if dont_chase:
            entry_factor = min(entry_factor, self.ENTRY_FACTOR_FLOOR)
        total_score = min(total_score * entry_factor, 100.0)
        tech_details["entry_factor"] = round(entry_factor, 3)

        breakdown = {
            "technical": tech_details,
            "fundamental": fund_details,
            "insider": insider_details,
            "patterns": pattern_details,
        }

        try:
            current_price = float(self.price_data.iloc[-1]["close"])
        except Exception:
            current_price = None

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
            volume_signal=volume_signal,
            entry_recommendation=entry_rec,
            stop_loss=entry_stop,
            target_price=entry_target,
            entry_score=round(entry_score, 2) if entry_score is not None else None,
            dont_chase=dont_chase,
            scale_in_guidance=scale_in_guidance,
            current_price=current_price,
            company_name=self.stock_info.get("company_name"),
            sector=self.stock_info.get("sector"),
            market_cap=self.stock_info.get("market_cap"),
        )

    def calculate_technical_score(self) -> Tuple[float, Dict]:
        """
        Calculate technical analysis score

        Components:
        - Magic Line respect (15%)
        - Volume profile (10%)
        - Pattern strength (10%)
        - Relative strength (5%)
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

            # Relative Strength
            rs_score = self._calculate_relative_strength_score()
            score += rs_score * (self.WEIGHTS["technical"]["relative_strength"] / 0.40)
            details["relative_strength_score"] = rs_score

            # Pattern contribution
            pattern_score, _ = self.calculate_pattern_score()
            score += pattern_score * (self.WEIGHTS["technical"]["patterns"] / 0.40)
            details["pattern_contribution"] = pattern_score

        except Exception as e:
            logger.error(f"Error calculating technical score: {e}")

        return min(score, 100), details

    def calculate_fundamental_score(self) -> Tuple[float, Dict]:
        """
        Calculate fundamental analysis score

        Components:
        - Earnings growth (15%)
        - Revenue growth (10%)
        - Valuation (5%)
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

            # Share structure — small float (Stine favors low supply / explosive moves)
            float_shares = self.fundamentals.get("float_shares")  # millions
            structure_score = self._score_share_structure(float_shares)
            score += structure_score * (self.WEIGHTS["fundamental"]["share_structure"] / 0.30)
            details["float_shares_m"] = float_shares
            details["share_structure_score"] = structure_score

            # Balance sheet — low debt + adequate liquidity
            d2e = self.fundamentals.get("debt_to_equity")
            current_ratio = self.fundamentals.get("current_ratio")
            balance_score = self._score_balance_sheet(d2e, current_ratio)
            score += balance_score * (self.WEIGHTS["fundamental"]["balance_sheet"] / 0.30)
            details["debt_to_equity"] = d2e
            details["current_ratio"] = current_ratio
            details["balance_sheet_score"] = balance_score

            # Analyst coverage — under-followed names are favored
            analyst_count = self.fundamentals.get("analyst_count")
            coverage_score = self._score_analyst_coverage(analyst_count)
            score += coverage_score * (self.WEIGHTS["fundamental"]["analyst_coverage"] / 0.30)
            details["analyst_count"] = analyst_count
            details["analyst_coverage_score"] = coverage_score

            # Earnings acceleration — forward growth exceeding trailing growth
            eps_next = self.fundamentals.get("eps_growth_next_y")
            accel_score = self._score_earnings_acceleration(eps_growth, eps_next)
            score += accel_score * (self.WEIGHTS["fundamental"]["earnings_acceleration"] / 0.30)
            details["eps_growth_next_y"] = eps_next
            details["earnings_acceleration_score"] = accel_score

        except Exception as e:
            logger.error(f"Error calculating fundamental score: {e}")

        return min(score, 100), details

    @staticmethod
    def _score_share_structure(float_shares: Optional[float]) -> float:
        """Small float scores high (float in millions of shares)."""
        if float_shares is None or float_shares <= 0:
            return 50.0
        if float_shares < 20:
            return 100.0
        if float_shares < 50:
            return 85.0
        if float_shares < 100:
            return 70.0
        if float_shares < 300:
            return 50.0
        if float_shares < 1000:
            return 30.0
        return 15.0

    @staticmethod
    def _score_balance_sheet(
        debt_to_equity: Optional[float], current_ratio: Optional[float]
    ) -> float:
        """Low debt + adequate liquidity. Averages a debt score and a liquidity score."""
        if debt_to_equity is None:
            debt_score = 50.0
        elif debt_to_equity < 0.3:
            debt_score = 100.0
        elif debt_to_equity < 0.7:
            debt_score = 80.0
        elif debt_to_equity < 1.5:
            debt_score = 55.0
        else:
            debt_score = 25.0

        if current_ratio is None:
            liquidity_score = 50.0
        elif current_ratio >= 2.0:
            liquidity_score = 100.0
        elif current_ratio >= 1.5:
            liquidity_score = 80.0
        elif current_ratio >= 1.0:
            liquidity_score = 55.0
        else:
            liquidity_score = 25.0

        return (debt_score + liquidity_score) / 2.0

    @staticmethod
    def _score_analyst_coverage(analyst_count: Optional[int]) -> float:
        """Fewer covering analysts → more undiscovered → higher score."""
        if analyst_count is None:
            return 50.0
        if analyst_count <= 2:
            return 90.0
        if analyst_count <= 5:
            return 70.0
        if analyst_count <= 10:
            return 50.0
        if analyst_count <= 20:
            return 30.0
        return 15.0

    @staticmethod
    def _score_earnings_acceleration(
        eps_growth: Optional[float], eps_growth_next: Optional[float]
    ) -> float:
        """Forward EPS growth exceeding trailing growth signals acceleration."""
        if eps_growth is None or eps_growth_next is None:
            return 50.0
        accel = eps_growth_next - eps_growth  # percentage points
        if accel > 20:
            return 100.0
        if accel > 0:
            return 60 + accel / 20 * 40
        if accel > -20:
            return 40 + (accel + 20) / 20 * 20
        return 20.0

    def calculate_insider_score(self) -> Tuple[float, Dict]:
        """
        Calculate insider activity score using OpenInsider data

        Components:
        - Recent buying activity (15%)
        - Cluster buying (10%)
        - Buying at increasing prices (5%)
        """
        score = 0.0
        details = {}

        activity = self.insider_activity
        if not activity:
            return 0.0, {"note": "No insider data"}

        # The Superstock model scores insider *buying*; selling earns no points.
        # But report the selling so the UI shows activity exists rather than
        # implying the data is missing.
        if activity.total_purchases == 0:
            if activity.total_sales > 0:
                note = (
                    f"No insider buying — {activity.total_sales} sells "
                    f"by {activity.unique_sellers} insider(s)"
                )
            else:
                note = "No insider data"
            return 0.0, {
                "note": note,
                "total_purchases": 0,
                "total_sales": activity.total_sales,
                "unique_sellers": activity.unique_sellers,
            }

        try:

            # Recent buying score
            recent_score = min(activity.total_purchases * 20, 100)
            score += recent_score * (self.WEIGHTS["insider"]["recent_buying"] / 0.30)
            details["recent_purchases"] = activity.total_purchases
            details["total_sales"] = activity.total_sales
            details["recent_buying_score"] = recent_score

            # Cluster buying
            cluster_score = 100 if activity.has_cluster_buying else 30
            score += cluster_score * (self.WEIGHTS["insider"]["cluster_buying"] / 0.30)
            details["cluster_buying"] = activity.has_cluster_buying
            details["cluster_score"] = cluster_score

            # Price trend (buying at increasing prices)
            price_trend_score = self._calculate_insider_price_trend_from_activity(activity)
            score += price_trend_score * (self.WEIGHTS["insider"]["price_trend"] / 0.30)
            details["price_trend_score"] = price_trend_score

            # Also compute the enriched insider score from openinsider module
            details["overall_confidence"] = activity.buyer_conviction
            details["openinsider_score"] = get_insider_score(activity)

        except Exception as e:
            logger.error(f"Error calculating insider score: {e}")

        return min(score, 100), details

    def calculate_pattern_score(self) -> Tuple[float, Dict]:
        """Calculate pattern recognition score"""
        score = 0.0
        details = {"patterns_detected": []}

        try:
            recognizer = PatternRecognizer(self.price_data)
            patterns = recognizer.detect_all_patterns()

            if patterns:
                avg_strength = sum(p.strength_score for p in patterns) / len(patterns)
                score = avg_strength

                details["patterns_detected"] = [p.pattern_type for p in patterns]
                details["pattern_count"] = len(patterns)
                details["average_strength"] = avg_strength

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

        volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio >= 2.0:
            return 100
        elif volume_ratio >= 1.5:
            return 70 + (volume_ratio - 1.5) * 60
        elif volume_ratio >= 1.0:
            return volume_ratio * 70
        else:
            return volume_ratio * 50

    def _calculate_relative_strength_score(self) -> float:
        """
        Relative strength vs the market benchmark (SPY).

        Stine's superstocks dramatically *outperform* the market, so RS is
        measured as the stock's trailing return minus SPY's return over the
        same window. When no benchmark is supplied we fall back to absolute
        momentum so the score still degrades gracefully.
        """
        if len(self.price_data) < 50:
            return 50.0

        # ~3-month lookback (63 trading days), bounded by available history.
        lookback = min(len(self.price_data) - 1, 63)
        stock_closes = self.price_data["close"]
        stock_gain = stock_closes.iloc[-1] / stock_closes.iloc[-1 - lookback] - 1

        bench = self.benchmark_data
        if bench is None or "close" not in getattr(bench, "columns", []) or len(bench) < lookback + 1:
            # No benchmark available — score on absolute momentum (legacy behavior).
            return self._momentum_score(stock_gain)

        bench_closes = bench["close"]
        bench_gain = bench_closes.iloc[-1] / bench_closes.iloc[-1 - lookback] - 1

        # Outperformance of the market over the window.
        rel = stock_gain - bench_gain

        if rel >= 0.30:
            return 100.0
        elif rel >= 0.15:
            return 80 + (rel - 0.15) / 0.15 * 20
        elif rel >= 0.05:
            return 65 + (rel - 0.05) / 0.10 * 15
        elif rel >= 0:
            return 50 + (rel / 0.05) * 15
        elif rel >= -0.10:
            return 30 + (rel + 0.10) / 0.10 * 20
        else:
            return max(30 + (rel + 0.10) * 100, 0.0)

    @staticmethod
    def _momentum_score(gain: float) -> float:
        """Absolute-momentum fallback when no benchmark is available."""
        if gain > 0.30:
            return 100.0
        elif gain > 0.10:
            return 70 + (gain - 0.10) / 0.20 * 30
        elif gain > 0:
            return 50 + (gain / 0.10) * 20
        else:
            return max(50 + gain * 100, 0.0)

    def _calculate_insider_price_trend_from_activity(
        self, activity: InsiderActivitySummary
    ) -> float:
        """Check if insiders are buying at increasing prices"""
        purchases = [
            t for t in activity.transactions
            if t.is_purchase and t.price > 0
        ]

        if len(purchases) < 2:
            return 50.0

        sorted_purchases = sorted(purchases, key=lambda x: x.trade_date)
        prices = [t.price for t in sorted_purchases]

        if prices[-1] > prices[0]:
            return 100
        else:
            return 30


class SuperstockScreener:
    """
    Screen stocks for Superstock opportunities

    Full pipeline: Finviz pre-filter → batch yfinance → score → rank
    """

    def __init__(self, criteria: ScreeningCriteria):
        self.criteria = criteria

    def screen_stock(
        self,
        price_data: pd.DataFrame,
        stock_info: Dict,
        fundamentals: Optional[Dict] = None,
        insider_activity: Optional[InsiderActivitySummary] = None,
        benchmark_data: Optional[pd.DataFrame] = None,
    ) -> Optional[StockScore]:
        """
        Screen a single stock

        Args:
            price_data: Price history
            stock_info: Stock metadata
            fundamentals: Fundamental data
            insider_activity: InsiderActivitySummary from OpenInsider
            benchmark_data: Market benchmark (SPY) price history for relative strength

        Returns:
            StockScore if passes filters, None otherwise
        """
        if not self._passes_filters(price_data, stock_info, fundamentals):
            return None

        scorer = SuperstockScorer(
            price_data, stock_info, fundamentals, insider_activity, benchmark_data
        )
        score = scorer.calculate_composite_score()

        if score.total_score < self.criteria.min_total_score:
            return None

        return score

    def _passes_filters(
        self, price_data: pd.DataFrame, stock_info: Dict, fundamentals: Optional[Dict]
    ) -> bool:
        """
        Check if stock passes hard filter criteria.

        Only filter on structural requirements (price range, volume, market cap).
        Fundamentals and magic line quality are scored, not gated — the composite
        score threshold handles quality filtering.
        """
        current_price = float(price_data.iloc[-1]["close"])
        if not (self.criteria.price_min <= current_price <= self.criteria.price_max):
            return False

        avg_volume = price_data.tail(20)["volume"].mean()
        if avg_volume < self.criteria.volume_min:
            return False

        market_cap = stock_info.get("market_cap", 0)
        if self.criteria.market_cap_min and market_cap < self.criteria.market_cap_min:
            return False
        if self.criteria.market_cap_max and market_cap > self.criteria.market_cap_max:
            return False

        return True


async def run_full_pipeline(
    criteria: Optional[ScreeningCriteria] = None,
    mode: ScanMode = ScanMode.STANDARD,
    progress_callback=None,
    max_symbols: Optional[int] = None,
    persist: bool = False,
    symbols: Optional[List[str]] = None,
) -> List[StockScore]:
    """
    Run the complete screening pipeline:
    1. Finviz pre-filter to get candidate symbols
    2. Batch yfinance fetch for price data
    3. OpenInsider fetch for insider data
    4. Score each stock
    5. Rank and return results
    6. (optional) Persist prices/insider/indicators/results to the database

    Args:
        criteria: Screening criteria (defaults to standard)
        mode: Finviz scan mode
        progress_callback: Optional async callable(stage, pct, msg)
        persist: When True, upsert the qualifying stocks' data into the DB

    Returns:
        List of StockScore sorted by total_score descending
    """
    if criteria is None:
        criteria = ScreeningCriteria()

    # A discrete scan targets an explicit ticker list (e.g. the AI sector
    # watch). The market-wide OpenInsider feeds rarely overlap such a list, so
    # discrete scans fetch insider activity per-symbol instead (see Stage 3).
    discrete = bool(symbols)

    screener = SuperstockScreener(criteria)
    start_time = time.time()

    async def _progress(stage: str, pct: int, msg: str):
        if progress_callback:
            await progress_callback(stage, pct, msg)
        logger.info(f"[{stage}] {pct}% - {msg}")

    # --- Stage 1: Build the candidate universe ---
    if symbols:
        # Discrete symbol list (e.g. the AI sector watch): skip the Finviz
        # universe pre-filter and pull per-symbol fundamentals instead.
        symbols = [s.upper() for s in symbols]
        await _progress("finviz", 0, f"Fetching fundamentals for {len(symbols)} symbols...")
        finviz_metrics = await FinvizDetailFetcher().fetch_stock_details(symbols)
        await _progress("finviz", 100, f"Got fundamentals for {len(finviz_metrics)} symbols")
    else:
        await _progress("finviz", 0, "Fetching Finviz pre-filtered universe...")
        prefilter = FinvizPreFilter()
        pf_result: PreFilterResult = await prefilter.get_prefiltered_symbols(mode)
        symbols = pf_result.symbols
        finviz_metrics = pf_result.metrics

        if not symbols:
            logger.warning("Finviz pre-filter returned 0 symbols")
            return []

        # Cap symbols if requested (speeds up QUICK mode dramatically)
        if max_symbols and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]

        await _progress("finviz", 100, f"Got {len(symbols)} candidates from Finviz")

    # --- Stage 2: Batch yfinance fetch ---
    await _progress("fetch", 0, f"Batch fetching price data for {len(symbols)} symbols...")
    price_data_map: Dict[str, pd.DataFrame] = YahooFinanceCollector.batch_fetch_historical_data(
        symbols, period="1y"
    )
    await _progress("fetch", 100, f"Got price data for {len(price_data_map)} symbols")

    # Benchmark (SPY) fetched once for true relative-strength scoring.
    benchmark_data: Optional[pd.DataFrame] = None
    try:
        benchmark_data = YahooFinanceCollector.batch_fetch_historical_data(
            ["SPY"], period="1y"
        ).get("SPY")
    except Exception as e:
        logger.warning(f"SPY benchmark fetch failed; relative strength falls back to momentum: {e}")

    # --- Stage 3: OpenInsider fetch ---
    await _progress("insider", 0, "Fetching insider buying data...")
    insider_by_symbol: Dict[str, InsiderActivitySummary] = {}
    try:
        async with OpenInsiderScraper() as scraper:
            if discrete:
                # Per-symbol lookups: the market-wide purchase feed almost never
                # overlaps a hand-picked list, so query each ticker directly.
                # This also surfaces sells, not just purchases.
                fetched = 0
                for sym in symbols:
                    insider_by_symbol[sym] = await scraper.fetch_stock_insider_activity(
                        sym, days=criteria.insider_buying_days
                    )
                    fetched += 1
                    await _progress(
                        "insider",
                        int(fetched / max(len(symbols), 1) * 100),
                        f"Insider activity {fetched}/{len(symbols)}",
                    )
                    await asyncio.sleep(0.3)  # be gentle with OpenInsider
            else:
                cluster_buys = await scraper.fetch_recent_cluster_buys(
                    days=criteria.insider_buying_days,
                    price_min=criteria.price_min,
                    price_max=criteria.price_max,
                )
                # For symbols with cluster buy data, create summaries
                for sym, txns in cluster_buys.items():
                    insider_by_symbol[sym] = scraper._summarize_activity(sym, txns)

                # Also fetch all recent purchases for broader coverage
                all_purchases = await scraper.fetch_all_recent_purchases(
                    days=criteria.insider_buying_days,
                    price_min=criteria.price_min,
                    price_max=criteria.price_max,
                )
                for sym, txns in all_purchases.items():
                    if sym not in insider_by_symbol:
                        insider_by_symbol[sym] = scraper._summarize_activity(sym, txns)
    except Exception as e:
        logger.error(f"OpenInsider fetch failed: {e}")

    await _progress("insider", 100, f"Got insider data for {len(insider_by_symbol)} symbols")

    # --- Stage 4: Score each stock ---
    await _progress("score", 0, "Scoring stocks...")
    scored: List[StockScore] = []
    total = len(price_data_map)

    for i, (sym, pdf) in enumerate(price_data_map.items()):
        if len(pdf) < 50:
            continue

        # Build stock_info from Finviz metrics if available
        fm = finviz_metrics.get(sym)
        stock_info = {
            "symbol": sym,
            "company_name": fm.company if fm else sym,
            "sector": fm.sector if fm else "Unknown",
            "market_cap": int(fm.market_cap) if fm and fm.market_cap else 0,
        }

        # Build fundamentals from Finviz metrics
        fundamentals = None
        if fm:
            fundamentals = {
                "eps_growth_yoy": fm.eps_growth_yoy or 0,
                "revenue_growth_yoy": fm.revenue_growth_yoy or 0,
                "peg_ratio": fm.peg_ratio,
                "pe_ratio": fm.pe_ratio,
                "float_shares": fm.float_shares,
                "debt_to_equity": fm.debt_to_equity,
                "current_ratio": fm.current_ratio,
                "analyst_count": fm.analyst_count,
                "eps_growth_next_y": fm.eps_growth_next_y,
            }

        # Insider data
        insider = insider_by_symbol.get(sym)

        try:
            result = screener.screen_stock(
                pdf, stock_info, fundamentals, insider, benchmark_data
            )
            if result:
                scored.append(result)
        except Exception as e:
            logger.debug(f"Error scoring {sym}: {e}")

        if i % 50 == 0 and total > 0:
            pct = int(i / total * 100)
            await _progress("score", pct, f"Scored {i}/{total} stocks...")

    # --- Stage 5: Rank ---
    scored.sort(key=lambda s: s.total_score, reverse=True)
    for rank, s in enumerate(scored, 1):
        s.rank = rank

    # --- Stage 6: Persist (optional) ---
    if persist and scored:
        await _progress("persist", 0, f"Persisting {len(scored)} results to database...")
        try:
            # Run the blocking DB writes off the event loop
            counts = await asyncio.to_thread(
                _persist_scan_results, scored, price_data_map, insider_by_symbol, finviz_metrics
            )
            await _progress(
                "persist", 100,
                f"Persisted {counts['stocks']} stocks, "
                f"{counts['price_rows']} price rows, "
                f"{counts['insider_rows']} insider rows",
            )
        except Exception as e:
            logger.error(f"Persistence stage failed (scan results still returned): {e}")
            await _progress("persist", 100, f"Persistence failed: {e}")

    elapsed = time.time() - start_time
    await _progress("done", 100, f"Pipeline complete: {len(scored)} results in {elapsed:.1f}s")

    return scored


def _to_jsonable(value):
    """Recursively convert numpy/pandas scalars to native Python types.

    The score breakdown is assembled from pandas/numpy computations, so it can
    contain numpy.bool_/int64/float64 values that psycopg2's JSON encoder
    rejects. Normalize before persisting to the JSON column.
    """
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return _to_jsonable(value.tolist())
    return value


def _persist_scan_results(
    scored: List[StockScore],
    price_data_map: Dict[str, pd.DataFrame],
    insider_by_symbol: Dict[str, InsiderActivitySummary],
    finviz_metrics: Dict[str, StockMetrics],
) -> Dict[str, int]:
    """
    Upsert the qualifying stocks' data into the database.

    Idempotent: relies on the bulk upsert helpers in the repository layer, so
    re-running a scan updates existing rows instead of erroring or duplicating.
    Only the scored (qualifying) stocks are persisted to keep the write volume
    proportional to the signal.
    """
    from datetime import date as _date, datetime as _datetime
    from app.core.database import get_sync_db
    from app.core.repository import StockRepository, InsiderRepository, ScreeningRepository
    from app.models.database import DataUpdate

    today = _date.today()
    counts = {"stocks": 0, "price_rows": 0, "insider_rows": 0, "indicator_rows": 0}

    with get_sync_db() as db:
        stock_repo = StockRepository(db)
        insider_repo = InsiderRepository(db)
        screen_repo = ScreeningRepository(db)

        # Log this persistence run so the Monitoring page can report freshness.
        update_log = DataUpdate(
            update_type="scan_persist",
            status="running",
            started_at=_datetime.utcnow(),
        )
        db.add(update_log)
        db.flush()

        screening_rows: List[Dict] = []

        for s in scored:
            sym = s.symbol
            pdf = price_data_map.get(sym)
            if pdf is None or pdf.empty:
                continue

            fm = finviz_metrics.get(sym)

            # 1. Stock metadata
            stock = stock_repo.create_or_update_stock({
                "symbol": sym,
                "company_name": fm.company if fm else sym,
                "sector": fm.sector if fm else "Unknown",
                "market_cap": int(fm.market_cap) if fm and fm.market_cap else 0,
                "magic_line_period": s.magic_line_period or 10,
                "is_active": True,
            })
            counts["stocks"] += 1

            # 2. Daily price data
            price_rows = []
            for _, row in pdf.iterrows():
                d = pd.to_datetime(row["date"]).date() if "date" in row else None
                if d is None:
                    continue
                close = float(row["close"])
                price_rows.append({
                    "stock_id": stock.id,
                    "date": d,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": close,
                    "volume": int(row["volume"]) if not pd.isna(row["volume"]) else 0,
                    "adjusted_close": close,
                })
            if price_rows:
                stock_repo.bulk_insert_price_data(price_rows)
                counts["price_rows"] += len(price_rows)

            # 3. Latest technical indicators
            try:
                indicator_df = pdf.copy()
                if "date" in indicator_df.columns:
                    indicator_df = indicator_df.set_index("date")
                calc = TechnicalIndicatorCalculator(indicator_df)
                with_ind = calc.calculate_all_indicators()
                latest = with_ind.iloc[-1]
                latest_date = pd.to_datetime(with_ind.index[-1]).date()
                stock_repo.bulk_upsert_technical_indicators([{
                    "stock_id": stock.id,
                    "date": latest_date,
                    "sma_8w": _num(latest.get("sma_8w")),
                    "sma_10w": _num(latest.get("sma_10w")),
                    "sma_12w": _num(latest.get("sma_12w")),
                    "sma_14w": _num(latest.get("sma_14w")),
                    "sma_20d": _num(latest.get("sma_20d")),
                    "sma_50d": _num(latest.get("sma_50d")),
                    "sma_200d": _num(latest.get("sma_200d")),
                    "volume_avg_20d": _num(latest.get("volume_avg_20d")),
                    "volume_avg_50d": _num(latest.get("volume_avg_50d")),
                    "volume_ratio": _num(latest.get("volume_ratio")),
                    "rsi_14": _num(latest.get("rsi_14")),
                    "macd": _num(latest.get("macd")),
                    "macd_signal": _num(latest.get("macd_signal")),
                    "macd_histogram": _num(latest.get("macd_histogram")),
                }])
                counts["indicator_rows"] += 1
            except Exception as e:
                logger.debug(f"Indicator persistence failed for {sym}: {e}")

            # 4. Insider transactions
            activity = insider_by_symbol.get(sym)
            if activity and activity.transactions:
                txn_rows = []
                for t in activity.transactions:
                    txn_rows.append({
                        "stock_id": stock.id,
                        "filing_date": t.filing_date.date() if t.filing_date else today,
                        "transaction_date": t.trade_date.date() if t.trade_date else today,
                        "insider_name": t.insider_name or "Unknown",
                        "insider_title": t.insider_title,
                        "transaction_type": "purchase" if t.is_purchase else (
                            "sale" if t.transaction_type == "S" else "other"
                        ),
                        "shares": int(t.quantity or 0),
                        "price_per_share": float(t.price or 0),
                        "total_value": float(t.total_value or 0),
                        "shares_owned_after": int(t.shares_owned or 0),
                    })
                if txn_rows:
                    insider_repo.bulk_insert_transactions(txn_rows)
                    counts["insider_rows"] += len(txn_rows)

            # 5. Screening result row
            screening_rows.append({
                "stock_id": stock.id,
                "screen_date": today,
                "technical_score": s.technical_score,
                "fundamental_score": s.fundamental_score,
                "insider_score": s.insider_score,
                "pattern_score": s.pattern_score,
                "total_score": s.total_score,
                "rank": s.rank,
                "score_breakdown": _to_jsonable(s.score_breakdown),
            })

        if screening_rows:
            screen_repo.bulk_save_screening_results(screening_rows)

        update_log.status = "completed"
        update_log.records_processed = counts["stocks"]
        update_log.records_failed = 0
        update_log.completed_at = _datetime.utcnow()

    logger.info(
        f"Persisted scan: {counts['stocks']} stocks, {counts['price_rows']} price rows, "
        f"{counts['insider_rows']} insider rows, {counts['indicator_rows']} indicator rows"
    )
    return counts


def _num(value):
    """Coerce a possibly-NaN pandas value to float or None for DB storage."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
