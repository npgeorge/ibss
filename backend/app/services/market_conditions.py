"""
Market Conditions Module

Checks market-level conditions before scanning (Jesse's Entry Law #6).
Determines if market environment is favorable for new positions.

Key indicators:
- SPY above 50-day MA = bullish market
- VIX under 20 = low fear, risk-on
- Market breadth = healthy internals
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MarketTrend:
    """Market trend analysis for a major index"""
    symbol: str
    current_price: float
    sma_20: float
    sma_50: float
    sma_200: float

    # Trend status
    above_sma_20: bool
    above_sma_50: bool
    above_sma_200: bool

    # Trend strength
    distance_from_50sma_pct: float
    distance_from_200sma_pct: float

    # Trend classification
    trend: str  # "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"
    score: float  # 0-100

    @property
    def is_bullish(self) -> bool:
        return self.trend in ["strong_bullish", "bullish"]


@dataclass
class VIXAnalysis:
    """VIX volatility analysis"""
    current_vix: float
    sma_20: float
    percentile_rank: float  # Where current VIX ranks historically (0-100)

    # Thresholds
    is_low_fear: bool  # VIX < 20
    is_elevated: bool  # VIX 20-30
    is_high_fear: bool  # VIX > 30

    # Classification
    regime: str  # "complacent", "normal", "elevated", "fear", "panic"
    score: float  # 0-100 (higher = more favorable)

    @property
    def is_favorable(self) -> bool:
        return self.current_vix < 25


@dataclass
class MarketBreadth:
    """Market breadth analysis"""
    advance_decline_ratio: float  # Advances / Declines
    percent_above_50sma: float  # % of stocks above 50-day SMA
    percent_above_200sma: float  # % of stocks above 200-day SMA
    new_highs_lows_ratio: float  # New highs / new lows

    # Classification
    breadth_status: str  # "strong", "healthy", "neutral", "weak", "poor"
    score: float  # 0-100

    @property
    def is_healthy(self) -> bool:
        return self.breadth_status in ["strong", "healthy"]


@dataclass
class MarketConditions:
    """Complete market conditions assessment"""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Components
    spy_trend: MarketTrend = None
    qqq_trend: Optional[MarketTrend] = None
    iwm_trend: Optional[MarketTrend] = None  # Small caps
    vix_analysis: VIXAnalysis = None
    breadth: Optional[MarketBreadth] = None

    # Overall assessment
    market_favorable: bool = False
    overall_score: float = 0.0  # 0-100
    regime: str = "neutral"  # "risk_on", "neutral", "risk_off", "crisis"

    # Warnings
    warnings: List[str] = field(default_factory=list)

    @property
    def should_be_aggressive(self) -> bool:
        """Check if conditions favor aggressive positioning"""
        return self.overall_score >= 70 and not self.warnings

    @property
    def should_be_defensive(self) -> bool:
        """Check if conditions favor defensive positioning"""
        return self.overall_score < 40 or len(self.warnings) >= 2


class MarketConditionsAnalyzer:
    """
    Analyze market conditions for entry timing

    Jesse Stine's market timing rules:
    1. SPY above 50-day MA = bullish environment
    2. VIX under 20 = low fear, favorable for risk
    3. Breadth positive = healthy market internals
    4. Small caps (IWM) leading = risk-on appetite
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[datetime, pd.DataFrame]] = {}
        self._cache_ttl = timedelta(minutes=15)

    async def check_market_conditions(self) -> MarketConditions:
        """
        Check all market conditions

        Returns:
            MarketConditions with full assessment
        """
        try:
            # Fetch data for key indices
            spy_data, qqq_data, iwm_data, vix_data = await asyncio.gather(
                self._fetch_ticker_data("SPY"),
                self._fetch_ticker_data("QQQ"),
                self._fetch_ticker_data("IWM"),
                self._fetch_ticker_data("^VIX"),
                return_exceptions=True
            )

            # Analyze SPY trend
            spy_trend = None
            if isinstance(spy_data, pd.DataFrame) and len(spy_data) > 0:
                spy_trend = self._analyze_trend("SPY", spy_data)

            # Analyze QQQ trend
            qqq_trend = None
            if isinstance(qqq_data, pd.DataFrame) and len(qqq_data) > 0:
                qqq_trend = self._analyze_trend("QQQ", qqq_data)

            # Analyze IWM trend
            iwm_trend = None
            if isinstance(iwm_data, pd.DataFrame) and len(iwm_data) > 0:
                iwm_trend = self._analyze_trend("IWM", iwm_data)

            # Analyze VIX
            vix_analysis = None
            if isinstance(vix_data, pd.DataFrame) and len(vix_data) > 0:
                vix_analysis = self._analyze_vix(vix_data)

            # Calculate overall assessment
            conditions = self._calculate_overall_conditions(
                spy_trend, qqq_trend, iwm_trend, vix_analysis
            )

            return conditions

        except Exception as e:
            logger.error(f"Error checking market conditions: {e}")
            return self._default_conditions()

    async def _fetch_ticker_data(
        self,
        symbol: str,
        period: str = "6mo"
    ) -> pd.DataFrame:
        """Fetch ticker data with caching"""
        # Check cache
        if symbol in self._cache:
            cached_time, cached_data = self._cache[symbol]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                return cached_data

        try:
            # Fetch from yfinance (runs in executor to not block)
            loop = asyncio.get_event_loop()
            ticker = yf.Ticker(symbol)
            data = await loop.run_in_executor(
                None,
                lambda: ticker.history(period=period)
            )

            # Cache result
            self._cache[symbol] = (datetime.utcnow(), data)

            return data

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            raise

    def _analyze_trend(self, symbol: str, data: pd.DataFrame) -> MarketTrend:
        """Analyze trend for an index"""
        if len(data) < 200:
            # Not enough data for full analysis
            return self._minimal_trend(symbol, data)

        close = data["Close"]
        current_price = close.iloc[-1]

        # Calculate SMAs
        sma_20 = close.tail(20).mean()
        sma_50 = close.tail(50).mean()
        sma_200 = close.tail(200).mean()

        # Check position relative to SMAs
        above_sma_20 = current_price > sma_20
        above_sma_50 = current_price > sma_50
        above_sma_200 = current_price > sma_200

        # Calculate distances
        distance_from_50sma = (current_price - sma_50) / sma_50 * 100
        distance_from_200sma = (current_price - sma_200) / sma_200 * 100

        # Classify trend
        if above_sma_20 and above_sma_50 and above_sma_200 and distance_from_50sma > 3:
            trend = "strong_bullish"
            score = 90 + min(distance_from_50sma, 10)
        elif above_sma_50 and above_sma_200:
            trend = "bullish"
            score = 70 + distance_from_50sma
        elif above_sma_200:
            trend = "neutral"
            score = 50 + distance_from_200sma * 0.5
        elif not above_sma_200 and distance_from_200sma > -10:
            trend = "bearish"
            score = 30 + distance_from_200sma
        else:
            trend = "strong_bearish"
            score = max(10 + distance_from_200sma, 0)

        return MarketTrend(
            symbol=symbol,
            current_price=round(current_price, 2),
            sma_20=round(sma_20, 2),
            sma_50=round(sma_50, 2),
            sma_200=round(sma_200, 2),
            above_sma_20=above_sma_20,
            above_sma_50=above_sma_50,
            above_sma_200=above_sma_200,
            distance_from_50sma_pct=round(distance_from_50sma, 2),
            distance_from_200sma_pct=round(distance_from_200sma, 2),
            trend=trend,
            score=round(min(max(score, 0), 100), 1),
        )

    def _minimal_trend(self, symbol: str, data: pd.DataFrame) -> MarketTrend:
        """Minimal trend analysis when not enough data"""
        close = data["Close"]
        current_price = close.iloc[-1]
        sma_20 = close.tail(min(20, len(close))).mean()

        return MarketTrend(
            symbol=symbol,
            current_price=round(current_price, 2),
            sma_20=round(sma_20, 2),
            sma_50=round(sma_20, 2),  # Use sma_20 as proxy
            sma_200=round(sma_20, 2),
            above_sma_20=current_price > sma_20,
            above_sma_50=current_price > sma_20,
            above_sma_200=current_price > sma_20,
            distance_from_50sma_pct=0,
            distance_from_200sma_pct=0,
            trend="neutral",
            score=50,
        )

    def _analyze_vix(self, data: pd.DataFrame) -> VIXAnalysis:
        """Analyze VIX for volatility regime"""
        close = data["Close"]
        current_vix = close.iloc[-1]
        sma_20 = close.tail(20).mean()

        # Calculate percentile rank
        percentile_rank = (close < current_vix).mean() * 100

        # Classify regime
        if current_vix < 15:
            regime = "complacent"
            score = 95
        elif current_vix < 20:
            regime = "normal"
            score = 85
        elif current_vix < 25:
            regime = "elevated"
            score = 60
        elif current_vix < 30:
            regime = "fear"
            score = 35
        else:
            regime = "panic"
            score = 15

        return VIXAnalysis(
            current_vix=round(current_vix, 2),
            sma_20=round(sma_20, 2),
            percentile_rank=round(percentile_rank, 1),
            is_low_fear=current_vix < 20,
            is_elevated=20 <= current_vix < 30,
            is_high_fear=current_vix >= 30,
            regime=regime,
            score=score,
        )

    def _calculate_overall_conditions(
        self,
        spy_trend: Optional[MarketTrend],
        qqq_trend: Optional[MarketTrend],
        iwm_trend: Optional[MarketTrend],
        vix_analysis: Optional[VIXAnalysis],
    ) -> MarketConditions:
        """Calculate overall market conditions"""
        warnings = []
        scores = []

        # SPY trend (40% weight)
        if spy_trend:
            scores.append(spy_trend.score * 0.4)
            if not spy_trend.above_sma_50:
                warnings.append("SPY below 50-day MA - bearish intermediate trend")
            if not spy_trend.above_sma_200:
                warnings.append("SPY below 200-day MA - bearish long-term trend")
        else:
            scores.append(50 * 0.4)
            warnings.append("Unable to analyze SPY trend")

        # VIX (30% weight)
        if vix_analysis:
            scores.append(vix_analysis.score * 0.3)
            if vix_analysis.is_high_fear:
                warnings.append(f"VIX at {vix_analysis.current_vix:.1f} - elevated fear")
            elif vix_analysis.is_elevated:
                warnings.append(f"VIX elevated at {vix_analysis.current_vix:.1f}")
        else:
            scores.append(50 * 0.3)

        # QQQ trend (15% weight)
        if qqq_trend:
            scores.append(qqq_trend.score * 0.15)
        else:
            scores.append(50 * 0.15)

        # IWM/small cap trend (15% weight)
        if iwm_trend:
            scores.append(iwm_trend.score * 0.15)
            if iwm_trend.trend in ["bearish", "strong_bearish"]:
                warnings.append("Small caps (IWM) weak - risk-off environment")
        else:
            scores.append(50 * 0.15)

        # Calculate overall score
        overall_score = sum(scores)

        # Determine regime
        if overall_score >= 75 and len(warnings) == 0:
            regime = "risk_on"
            market_favorable = True
        elif overall_score >= 55:
            regime = "neutral"
            market_favorable = len(warnings) <= 1
        elif overall_score >= 35:
            regime = "risk_off"
            market_favorable = False
        else:
            regime = "crisis"
            market_favorable = False

        return MarketConditions(
            spy_trend=spy_trend,
            qqq_trend=qqq_trend,
            iwm_trend=iwm_trend,
            vix_analysis=vix_analysis,
            market_favorable=market_favorable,
            overall_score=round(overall_score, 1),
            regime=regime,
            warnings=warnings,
        )

    def _default_conditions(self) -> MarketConditions:
        """Return default neutral conditions on error"""
        return MarketConditions(
            market_favorable=True,  # Don't block scanning on error
            overall_score=50,
            regime="neutral",
            warnings=["Unable to fetch market data - using neutral conditions"],
        )


async def check_market_conditions() -> MarketConditions:
    """
    Convenience function to check market conditions

    Returns:
        MarketConditions assessment
    """
    analyzer = MarketConditionsAnalyzer()
    return await analyzer.check_market_conditions()


def get_market_warning_message(conditions: MarketConditions) -> Optional[str]:
    """
    Get warning message if market conditions are unfavorable

    Args:
        conditions: MarketConditions assessment

    Returns:
        Warning message or None if conditions are favorable
    """
    if conditions.market_favorable:
        return None

    if conditions.regime == "crisis":
        return (
            "CAUTION: Market in crisis mode. "
            "Consider avoiding new positions until conditions improve."
        )
    elif conditions.regime == "risk_off":
        return (
            "Market conditions unfavorable for aggressive positions. "
            f"Warnings: {'; '.join(conditions.warnings)}"
        )
    else:
        return f"Market caution: {'; '.join(conditions.warnings)}"
