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
        insider_activity: Optional[InsiderActivitySummary] = None,
    ):
        self.price_data = price_data
        self.stock_info = stock_info
        self.fundamentals = fundamentals or {}
        self.insider_activity = insider_activity

    def calculate_composite_score(self) -> StockScore:
        """Calculate complete composite score"""
        tech_score, tech_details = self.calculate_technical_score()
        fund_score, fund_details = self.calculate_fundamental_score()
        insider_score, insider_details = self.calculate_insider_score()
        pattern_score, pattern_details = self.calculate_pattern_score()

        # Calculate total (weighted)
        total_score = (
            tech_score * 0.40 + fund_score * 0.30 + insider_score * 0.30
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

        # Entry signals (enrichment)
        entry_rec = None
        entry_stop = None
        entry_target = None
        try:
            ml_period = tech_details.get("magic_line_period", 10) or 10
            detector = EntrySignalDetector(self.price_data, magic_line_period=ml_period)
            sig_result = detector.detect_signals()
            entry_rec = sig_result.recommendation
            if sig_result.best_signal:
                entry_stop = sig_result.best_signal.stop_loss
                entry_target = sig_result.best_signal.target_price
            tech_details["entry_signals"] = {
                "recommendation": sig_result.recommendation,
                "signal_count": len(sig_result.signals),
                "best_signal_type": sig_result.best_signal.signal_type.value if sig_result.best_signal else None,
                "best_signal_score": sig_result.best_signal.score if sig_result.best_signal else 0,
            }
        except Exception as e:
            logger.debug(f"Entry signal detection failed: {e}")

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
            volume_signal=volume_signal,
            entry_recommendation=entry_rec,
            stop_loss=entry_stop,
            target_price=entry_target,
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

        except Exception as e:
            logger.error(f"Error calculating fundamental score: {e}")

        return min(score, 100), details

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

        if not self.insider_activity or self.insider_activity.total_purchases == 0:
            return 0.0, {"note": "No insider data"}

        try:
            activity = self.insider_activity

            # Recent buying score
            recent_score = min(activity.total_purchases * 20, 100)
            score += recent_score * (self.WEIGHTS["insider"]["recent_buying"] / 0.30)
            details["recent_purchases"] = activity.total_purchases
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
        """Calculate relative strength score"""
        if len(self.price_data) < 50:
            return 50.0

        recent_30 = self.price_data.tail(30)
        gain_30d = (
            recent_30.iloc[-1]["close"] / recent_30.iloc[0]["close"] - 1
        )

        if gain_30d > 0.30:
            return 100
        elif gain_30d > 0.10:
            return 70 + (gain_30d - 0.10) / 0.20 * 30
        elif gain_30d > 0:
            return 50 + (gain_30d / 0.10) * 20
        else:
            return max(50 + gain_30d * 100, 0)

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
    ) -> Optional[StockScore]:
        """
        Screen a single stock

        Args:
            price_data: Price history
            stock_info: Stock metadata
            fundamentals: Fundamental data
            insider_activity: InsiderActivitySummary from OpenInsider

        Returns:
            StockScore if passes filters, None otherwise
        """
        if not self._passes_filters(price_data, stock_info, fundamentals):
            return None

        scorer = SuperstockScorer(price_data, stock_info, fundamentals, insider_activity)
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
) -> List[StockScore]:
    """
    Run the complete screening pipeline:
    1. Finviz pre-filter to get candidate symbols
    2. Batch yfinance fetch for price data
    3. OpenInsider fetch for insider data
    4. Score each stock
    5. Rank and return results

    Args:
        criteria: Screening criteria (defaults to standard)
        mode: Finviz scan mode
        progress_callback: Optional async callable(stage, pct, msg)

    Returns:
        List of StockScore sorted by total_score descending
    """
    if criteria is None:
        criteria = ScreeningCriteria()

    screener = SuperstockScreener(criteria)
    start_time = time.time()

    async def _progress(stage: str, pct: int, msg: str):
        if progress_callback:
            await progress_callback(stage, pct, msg)
        logger.info(f"[{stage}] {pct}% - {msg}")

    # --- Stage 1: Finviz pre-filter ---
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

    # --- Stage 3: OpenInsider fetch ---
    await _progress("insider", 0, "Fetching insider buying data...")
    insider_by_symbol: Dict[str, InsiderActivitySummary] = {}
    try:
        async with OpenInsiderScraper() as scraper:
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
            }

        # Insider data
        insider = insider_by_symbol.get(sym)

        try:
            result = screener.screen_stock(pdf, stock_info, fundamentals, insider)
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

    elapsed = time.time() - start_time
    await _progress("done", 100, f"Pipeline complete: {len(scored)} results in {elapsed:.1f}s")

    return scored
