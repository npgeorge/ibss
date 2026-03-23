"""
Volume Analysis Service

Implements Jesse Stine's volume analysis criteria:
- Volume dry-up detection (accumulation signature before breakouts)
- Orderly pullback detection (low volatility during consolidations)
- Volume surge confirmation on breakouts
- Relative volume analysis
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VolumeDryUpResult:
    """Result of volume dry-up analysis"""
    dryup_ratio: float  # Current volume / historical volume (<0.5 = significant dry-up)
    tightness: float  # Price consolidation tightness (<0.04 = tight base)
    is_accumulating: bool  # True if showing accumulation signature

    # Additional metrics
    avg_volume_start: float  # Average volume at start of period
    avg_volume_end: float  # Average volume at end of period
    volume_decline_pct: float  # Percent decline in volume
    price_range_pct: float  # Average price range as % of close
    consolidation_days: int  # Days of consolidation

    # Scoring
    score: float  # 0-100 score for dry-up quality

    @property
    def is_strong_dryup(self) -> bool:
        """Check if this is a strong dry-up pattern"""
        return self.dryup_ratio < 0.5 and self.tightness < 0.03


@dataclass
class OrderlyPullbackResult:
    """Result of orderly pullback analysis"""
    is_orderly: bool  # True if pullback is orderly (not chaotic)
    pullback_depth: float  # Percent pullback from recent high
    atr_volatility: float  # ATR-based volatility measure
    volatility_score: float  # 0-100 (higher = more orderly)

    # Trend context
    in_uptrend: bool  # True if overall trend is up
    trend_strength: float  # 0-100 trend strength

    # Entry quality
    is_entry_opportunity: bool  # True if pullback is 15-25% in uptrend
    distance_from_high: float  # Percent from recent high

    # Scoring
    score: float  # 0-100 overall orderly pullback score


@dataclass
class VolumeSurgeResult:
    """Result of volume surge analysis"""
    has_surge: bool  # True if recent volume surge detected
    surge_ratio: float  # Current volume / average volume
    surge_days: int  # Number of recent high-volume days

    # Price action during surge
    price_direction: str  # "up", "down", "flat"
    price_change_pct: float  # Price change during surge

    # Quality assessment
    is_breakout_volume: bool  # True if surge on price breakout
    is_distribution: bool  # True if surge on price decline (bearish)

    # Scoring
    score: float  # 0-100 volume surge quality score


@dataclass
class VolumeAnalysis:
    """Complete volume analysis for a stock"""
    symbol: str
    dryup: VolumeDryUpResult
    pullback: OrderlyPullbackResult
    surge: VolumeSurgeResult

    # Combined score
    overall_score: float  # Weighted combination
    signal: str  # "accumulating", "breakout_ready", "pullback_entry", "neutral", "distribution"

    @property
    def is_bullish(self) -> bool:
        """Check if volume analysis is bullish"""
        return self.signal in ["accumulating", "breakout_ready", "pullback_entry"]


class VolumeAnalyzer:
    """
    Analyze volume patterns for Superstock criteria

    Jesse Stine's volume principles:
    1. Volume dry-up during base = accumulation by smart money
    2. Volume surge on breakout = confirmation
    3. Orderly pullbacks = healthy consolidation
    4. High volume selling = distribution (avoid)
    """

    def __init__(self, price_data: pd.DataFrame):
        """
        Initialize with price data

        Args:
            price_data: DataFrame with columns: date, open, high, low, close, volume
        """
        self.data = price_data.copy()
        self._ensure_columns()

    def _ensure_columns(self):
        """Ensure required columns exist"""
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in self.data.columns:
                raise ValueError(f"Missing required column: {col}")

    def analyze(self) -> VolumeAnalysis:
        """
        Run complete volume analysis

        Returns:
            VolumeAnalysis with all components
        """
        dryup = self.detect_volume_dryup()
        pullback = self.detect_orderly_pullback()
        surge = self.detect_volume_surge()

        # Calculate overall score
        overall_score = (
            dryup.score * 0.35 +
            pullback.score * 0.35 +
            surge.score * 0.30
        )

        # Determine signal
        signal = self._determine_signal(dryup, pullback, surge)

        symbol = self.data.get("symbol", ["UNKNOWN"])[0] if "symbol" in self.data.columns else "UNKNOWN"

        return VolumeAnalysis(
            symbol=symbol,
            dryup=dryup,
            pullback=pullback,
            surge=surge,
            overall_score=round(overall_score, 2),
            signal=signal,
        )

    def detect_volume_dryup(
        self,
        lookback: int = 20,
        start_period: int = 10,
        end_period: int = 5
    ) -> VolumeDryUpResult:
        """
        Detect volume dry-up pattern (accumulation signature)

        Jesse's principle: Smart money accumulates during low-volume consolidation.
        Volume decreases as weak hands exit, setting up for explosive breakout.

        Args:
            lookback: Total lookback period
            start_period: Days at start to measure initial volume
            end_period: Days at end to measure current volume

        Returns:
            VolumeDryUpResult with analysis
        """
        if len(self.data) < lookback:
            return self._empty_dryup_result()

        recent = self.data.tail(lookback)

        # Calculate volume trend
        avg_vol_start = recent.head(start_period)["volume"].mean()
        avg_vol_end = recent.tail(end_period)["volume"].mean()

        # Prevent division by zero
        if avg_vol_start == 0:
            dryup_ratio = 1.0
        else:
            dryup_ratio = avg_vol_end / avg_vol_start

        volume_decline_pct = (1 - dryup_ratio) * 100 if dryup_ratio <= 1 else 0

        # Calculate price tightness (consolidation)
        price_range = (recent["high"] - recent["low"]) / recent["close"]
        tightness = price_range.tail(end_period).mean()
        price_range_pct = tightness * 100

        # Determine if accumulating
        is_accumulating = dryup_ratio < 0.6 and tightness < 0.04

        # Count consolidation days (days with below-average volume)
        avg_volume = self.data["volume"].mean()
        consolidation_days = (recent["volume"] < avg_volume * 0.7).sum()

        # Calculate score
        score = self._calculate_dryup_score(dryup_ratio, tightness, consolidation_days)

        return VolumeDryUpResult(
            dryup_ratio=round(dryup_ratio, 3),
            tightness=round(tightness, 4),
            is_accumulating=is_accumulating,
            avg_volume_start=avg_vol_start,
            avg_volume_end=avg_vol_end,
            volume_decline_pct=round(volume_decline_pct, 1),
            price_range_pct=round(price_range_pct, 2),
            consolidation_days=consolidation_days,
            score=score,
        )

    def detect_orderly_pullback(
        self,
        lookback: int = 50,
        atr_period: int = 14
    ) -> OrderlyPullbackResult:
        """
        Detect orderly pullback in uptrend

        Jesse's principle: Orderly pullbacks (15-25%) in uptrends are buying
        opportunities. Chaotic, high-volatility pullbacks signal trouble.

        Args:
            lookback: Lookback period for trend analysis
            atr_period: Period for ATR calculation

        Returns:
            OrderlyPullbackResult with analysis
        """
        if len(self.data) < lookback:
            return self._empty_pullback_result()

        recent = self.data.tail(lookback)

        # Find recent high and calculate pullback
        recent_high = recent["high"].max()
        current_close = recent.iloc[-1]["close"]
        pullback_depth = (recent_high - current_close) / recent_high * 100
        distance_from_high = pullback_depth

        # Calculate ATR-based volatility
        high_low = recent["high"] - recent["low"]
        high_close = abs(recent["high"] - recent["close"].shift(1))
        low_close = abs(recent["low"] - recent["close"].shift(1))

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.tail(atr_period).mean()
        atr_volatility = atr / current_close * 100  # ATR as % of price

        # Check if in uptrend (price above start of lookback period)
        start_price = recent.iloc[0]["close"]
        in_uptrend = current_close > start_price
        trend_strength = (current_close / start_price - 1) * 100 if in_uptrend else 0

        # Determine if orderly (low volatility during pullback)
        is_orderly = atr_volatility < 5.0  # Less than 5% daily ATR = orderly

        # Entry opportunity: 15-25% pullback in uptrend
        is_entry_opportunity = in_uptrend and 15 <= pullback_depth <= 30

        # Calculate volatility score (higher = more orderly)
        if atr_volatility < 2:
            volatility_score = 100
        elif atr_volatility < 3:
            volatility_score = 85
        elif atr_volatility < 4:
            volatility_score = 70
        elif atr_volatility < 5:
            volatility_score = 55
        elif atr_volatility < 7:
            volatility_score = 35
        else:
            volatility_score = 15

        # Calculate overall score
        score = self._calculate_pullback_score(
            is_orderly, pullback_depth, in_uptrend, volatility_score
        )

        return OrderlyPullbackResult(
            is_orderly=is_orderly,
            pullback_depth=round(pullback_depth, 2),
            atr_volatility=round(atr_volatility, 2),
            volatility_score=volatility_score,
            in_uptrend=in_uptrend,
            trend_strength=round(trend_strength, 2),
            is_entry_opportunity=is_entry_opportunity,
            distance_from_high=round(distance_from_high, 2),
            score=score,
        )

    def detect_volume_surge(
        self,
        lookback: int = 20,
        surge_threshold: float = 1.5
    ) -> VolumeSurgeResult:
        """
        Detect volume surge patterns

        Jesse's principle: Volume surge on breakout confirms institutional buying.
        Volume surge on decline indicates distribution (bearish).

        Args:
            lookback: Lookback for average volume calculation
            surge_threshold: Multiple of average volume to consider a surge

        Returns:
            VolumeSurgeResult with analysis
        """
        if len(self.data) < lookback:
            return self._empty_surge_result()

        recent = self.data.tail(lookback)
        latest = recent.iloc[-1]

        # Calculate average volume (excluding most recent days)
        avg_volume = recent.head(lookback - 3)["volume"].mean()

        # Calculate surge ratio
        if avg_volume == 0:
            surge_ratio = 1.0
        else:
            surge_ratio = latest["volume"] / avg_volume

        has_surge = surge_ratio >= surge_threshold

        # Count high-volume days in recent period
        surge_days = (recent["volume"] >= avg_volume * surge_threshold).sum()

        # Price action during surge
        price_change = (latest["close"] - recent.iloc[-5]["close"]) / recent.iloc[-5]["close"] * 100

        if price_change > 2:
            price_direction = "up"
        elif price_change < -2:
            price_direction = "down"
        else:
            price_direction = "flat"

        # Determine if breakout or distribution
        is_breakout_volume = has_surge and price_direction == "up"
        is_distribution = has_surge and price_direction == "down"

        # Calculate score
        score = self._calculate_surge_score(
            has_surge, surge_ratio, is_breakout_volume, is_distribution
        )

        return VolumeSurgeResult(
            has_surge=has_surge,
            surge_ratio=round(surge_ratio, 2),
            surge_days=surge_days,
            price_direction=price_direction,
            price_change_pct=round(price_change, 2),
            is_breakout_volume=is_breakout_volume,
            is_distribution=is_distribution,
            score=score,
        )

    def _calculate_dryup_score(
        self,
        dryup_ratio: float,
        tightness: float,
        consolidation_days: int
    ) -> float:
        """Calculate dry-up pattern score"""
        score = 0.0

        # Volume decline score (lower ratio = better, 0.3-0.5 ideal)
        if dryup_ratio < 0.3:
            score += 40
        elif dryup_ratio < 0.5:
            score += 35
        elif dryup_ratio < 0.6:
            score += 25
        elif dryup_ratio < 0.8:
            score += 15
        else:
            score += 5

        # Tightness score (lower = better, <0.03 ideal)
        if tightness < 0.02:
            score += 35
        elif tightness < 0.03:
            score += 30
        elif tightness < 0.04:
            score += 20
        elif tightness < 0.06:
            score += 10
        else:
            score += 0

        # Consolidation days bonus
        score += min(consolidation_days * 2, 25)

        return min(score, 100)

    def _calculate_pullback_score(
        self,
        is_orderly: bool,
        pullback_depth: float,
        in_uptrend: bool,
        volatility_score: float
    ) -> float:
        """Calculate orderly pullback score"""
        score = 0.0

        # Must be in uptrend for high score
        if not in_uptrend:
            return max(volatility_score * 0.3, 0)

        # Orderly bonus
        if is_orderly:
            score += 30

        # Ideal pullback depth (15-25%)
        if 15 <= pullback_depth <= 25:
            score += 35  # Perfect entry zone
        elif 10 <= pullback_depth < 15:
            score += 25
        elif 25 < pullback_depth <= 30:
            score += 20
        elif pullback_depth < 10:
            score += 10  # Too shallow
        else:
            score += 5  # Too deep

        # Add volatility score component
        score += volatility_score * 0.35

        return min(score, 100)

    def _calculate_surge_score(
        self,
        has_surge: bool,
        surge_ratio: float,
        is_breakout_volume: bool,
        is_distribution: bool
    ) -> float:
        """Calculate volume surge score"""
        if not has_surge:
            return 30  # Neutral, no surge

        if is_distribution:
            return 10  # Bearish, avoid

        score = 50  # Base score for having a surge

        # Breakout volume bonus
        if is_breakout_volume:
            score += 25

        # Surge magnitude bonus
        if surge_ratio >= 3.0:
            score += 25
        elif surge_ratio >= 2.5:
            score += 20
        elif surge_ratio >= 2.0:
            score += 15
        elif surge_ratio >= 1.5:
            score += 10

        return min(score, 100)

    def _determine_signal(
        self,
        dryup: VolumeDryUpResult,
        pullback: OrderlyPullbackResult,
        surge: VolumeSurgeResult
    ) -> str:
        """Determine overall volume signal"""
        if surge.is_distribution:
            return "distribution"

        if surge.is_breakout_volume:
            return "breakout_ready"

        if pullback.is_entry_opportunity and pullback.is_orderly:
            return "pullback_entry"

        if dryup.is_accumulating:
            return "accumulating"

        return "neutral"

    def _empty_dryup_result(self) -> VolumeDryUpResult:
        """Return empty dry-up result"""
        return VolumeDryUpResult(
            dryup_ratio=1.0,
            tightness=0.1,
            is_accumulating=False,
            avg_volume_start=0,
            avg_volume_end=0,
            volume_decline_pct=0,
            price_range_pct=0,
            consolidation_days=0,
            score=0,
        )

    def _empty_pullback_result(self) -> OrderlyPullbackResult:
        """Return empty pullback result"""
        return OrderlyPullbackResult(
            is_orderly=False,
            pullback_depth=0,
            atr_volatility=10,
            volatility_score=0,
            in_uptrend=False,
            trend_strength=0,
            is_entry_opportunity=False,
            distance_from_high=0,
            score=0,
        )

    def _empty_surge_result(self) -> VolumeSurgeResult:
        """Return empty surge result"""
        return VolumeSurgeResult(
            has_surge=False,
            surge_ratio=1.0,
            surge_days=0,
            price_direction="flat",
            price_change_pct=0,
            is_breakout_volume=False,
            is_distribution=False,
            score=30,
        )


def analyze_volume(price_data: pd.DataFrame) -> VolumeAnalysis:
    """
    Convenience function for volume analysis

    Args:
        price_data: DataFrame with OHLCV data

    Returns:
        VolumeAnalysis result
    """
    analyzer = VolumeAnalyzer(price_data)
    return analyzer.analyze()


def detect_volume_dryup(
    price_data: pd.DataFrame,
    lookback: int = 20
) -> VolumeDryUpResult:
    """
    Convenience function for volume dry-up detection

    Args:
        price_data: DataFrame with OHLCV data
        lookback: Lookback period

    Returns:
        VolumeDryUpResult
    """
    analyzer = VolumeAnalyzer(price_data)
    return analyzer.detect_volume_dryup(lookback)
