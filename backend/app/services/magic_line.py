"""
Magic Line Detection Service

The Magic Line is the cornerstone of the Superstocks strategy.
Most stocks respect their 10-week simple moving average, but some
respect 8, 12, or 14 weeks. This module automatically detects
which period each stock respects most consistently.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class MagicLineResult:
    """Result of magic line detection"""

    period: int  # weeks
    score: float  # confidence score 0-100
    current_price: float
    magic_line_value: float
    distance_percent: float
    bounces: int
    respect_rate: float
    last_touch_date: Optional[str]


class MagicLineDetector:
    """
    Detects the optimal Magic Line (moving average) for a stock

    The Magic Line is the moving average that a stock respects most
    consistently as support. This is typically the 10-week SMA, but
    can be 8, 12, or 14 weeks for some stocks.
    """

    # Test periods (in weeks)
    TEST_PERIODS = [8, 10, 12, 14]

    # Trading days per week
    DAYS_PER_WEEK = 5

    def __init__(self, price_data: pd.DataFrame):
        """
        Initialize detector with price data

        Args:
            price_data: DataFrame with columns ['date', 'open', 'high', 'low', 'close', 'volume']
                       Indexed by date, sorted ascending
        """
        self.data = price_data.copy()
        self.data = self.data.sort_index()

        # Validate required columns
        required_cols = ["open", "high", "low", "close", "volume"]
        missing = set(required_cols) - set(self.data.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

    def find_magic_line(self) -> MagicLineResult:
        """
        Find the optimal Magic Line period for this stock

        Returns:
            MagicLineResult with the best-fitting moving average period
        """
        best_result = None
        best_score = 0

        for period_weeks in self.TEST_PERIODS:
            result = self._test_period(period_weeks)

            if result.score > best_score:
                best_score = result.score
                best_result = result

        return best_result or self._default_result()

    def _test_period(self, period_weeks: int) -> MagicLineResult:
        """
        Test a specific moving average period

        Args:
            period_weeks: Number of weeks for the moving average

        Returns:
            MagicLineResult for this period
        """
        # Convert weeks to days
        period_days = period_weeks * self.DAYS_PER_WEEK

        # Calculate simple moving average
        sma = self.data["close"].rolling(window=period_days, min_periods=period_days).mean()

        # Count bounces off the MA
        bounces = self._count_bounces(sma)

        # Calculate respect rate (how often price stays above MA)
        respect_rate = self._calculate_respect_rate(sma)

        # Find last touch
        last_touch = self._find_last_touch(sma)

        # Calculate composite score
        score = self._calculate_score(bounces, respect_rate)

        # Current values
        current_price = float(self.data["close"].iloc[-1])
        magic_line_value = float(sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else 0.0
        distance_percent = (
            ((current_price - magic_line_value) / magic_line_value * 100)
            if magic_line_value > 0
            else 0.0
        )

        return MagicLineResult(
            period=period_weeks,
            score=score,
            current_price=current_price,
            magic_line_value=magic_line_value,
            distance_percent=distance_percent,
            bounces=bounces,
            respect_rate=respect_rate,
            last_touch_date=last_touch,
        )

    def _count_bounces(self, sma: pd.Series) -> int:
        """
        Count successful bounces off the moving average

        A bounce is when:
        1. Price touches or goes below the MA
        2. Price closes above the MA
        3. Price moves higher the next day
        """
        bounces = 0

        for i in range(1, len(self.data) - 1):
            if pd.isna(sma.iloc[i]):
                continue

            current_low = self.data["low"].iloc[i]
            current_close = self.data["close"].iloc[i]
            next_close = self.data["close"].iloc[i + 1]
            ma_value = sma.iloc[i]

            # Check if price touched MA
            touched = current_low <= ma_value <= self.data["high"].iloc[i]

            # Check if it bounced (closed above and went higher)
            bounced = current_close > ma_value and next_close > current_close

            if touched and bounced:
                bounces += 1

        return bounces

    def _calculate_respect_rate(self, sma: pd.Series) -> float:
        """
        Calculate what percentage of the time price stays above the MA

        This shows how consistently the stock respects this level
        """
        valid_data = ~sma.isna()
        closes = self.data.loc[valid_data, "close"]
        ma_values = sma[valid_data]

        if len(closes) == 0:
            return 0.0

        above_ma = (closes > ma_values).sum()
        total = len(closes)

        return (above_ma / total) * 100

    def _find_last_touch(self, sma: pd.Series) -> Optional[str]:
        """
        Find the date of the last time price touched the MA

        Returns:
            Date string or None
        """
        for i in range(len(self.data) - 1, 0, -1):
            if pd.isna(sma.iloc[i]):
                continue

            low = self.data["low"].iloc[i]
            high = self.data["high"].iloc[i]
            ma = sma.iloc[i]

            if low <= ma <= high:
                return str(self.data.index[i].date())

        return None

    def _calculate_score(self, bounces: int, respect_rate: float) -> float:
        """
        Calculate composite score for this MA period

        Higher score = better fit as Magic Line

        Scoring:
        - Bounces: More bounces = higher score (10 points per bounce)
        - Respect rate: Higher % = higher score (0-50 points)
        - Bonus: If respect rate > 60% and bounces > 3 (20 point bonus)
        """
        score = 0.0

        # Bounces contribution (max 100 points for 10+ bounces)
        score += min(bounces * 10, 100)

        # Respect rate contribution (max 50 points)
        score += respect_rate * 0.5

        # Bonus for strong combination
        if respect_rate > 60 and bounces > 3:
            score += 20

        return min(score, 100)  # Cap at 100

    def _default_result(self) -> MagicLineResult:
        """Return default result if no good fit found"""
        current_price = float(self.data["close"].iloc[-1])

        return MagicLineResult(
            period=10,  # Default to 10-week
            score=0.0,
            current_price=current_price,
            magic_line_value=0.0,
            distance_percent=0.0,
            bounces=0,
            respect_rate=0.0,
            last_touch_date=None,
        )

    def get_support_levels(self, period_weeks: int = 10) -> List[float]:
        """
        Get historical support levels based on the Magic Line

        Args:
            period_weeks: MA period to use

        Returns:
            List of price levels where stock found support
        """
        period_days = period_weeks * self.DAYS_PER_WEEK
        sma = self.data["close"].rolling(window=period_days).mean()

        support_levels = []

        for i in range(1, len(self.data) - 1):
            if pd.isna(sma.iloc[i]):
                continue

            # Check if price touched and bounced
            touched = (
                self.data["low"].iloc[i]
                <= sma.iloc[i]
                <= self.data["high"].iloc[i]
            )
            bounced = (
                self.data["close"].iloc[i] > sma.iloc[i]
                and self.data["close"].iloc[i + 1] > self.data["close"].iloc[i]
            )

            if touched and bounced:
                support_levels.append(float(sma.iloc[i]))

        return support_levels

    def is_touching_magic_line(
        self, period_weeks: int = 10, tolerance: float = 0.02
    ) -> bool:
        """
        Check if stock is currently touching its Magic Line

        Args:
            period_weeks: MA period
            tolerance: % tolerance (default 2%)

        Returns:
            True if currently touching Magic Line
        """
        period_days = period_weeks * self.DAYS_PER_WEEK
        sma = self.data["close"].rolling(window=period_days).mean()

        if len(sma) == 0 or pd.isna(sma.iloc[-1]):
            return False

        current_price = self.data["close"].iloc[-1]
        ma_value = sma.iloc[-1]

        # Check if within tolerance
        distance = abs(current_price - ma_value) / ma_value

        return distance <= tolerance

    def check_magic_line_violation(
        self, period_weeks: int = 10, weeks_below: int = 2
    ) -> bool:
        """
        Check if Magic Line has been violated (sell signal)

        Violation = closed below MA for consecutive weeks

        Args:
            period_weeks: MA period
            weeks_below: Number of consecutive weekly closes below MA

        Returns:
            True if Magic Line violated
        """
        # Get weekly data
        weekly_data = self.data.resample("W").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        )

        period_days_weekly = period_weeks
        sma_weekly = weekly_data["close"].rolling(window=period_days_weekly).mean()

        if len(sma_weekly) < weeks_below:
            return False

        # Check last N weeks
        recent_weeks = weekly_data["close"].iloc[-weeks_below:]
        recent_ma = sma_weekly.iloc[-weeks_below:]

        # All weeks must be below MA
        all_below = all(
            close < ma for close, ma in zip(recent_weeks, recent_ma) if pd.notna(ma)
        )

        return all_below


def calculate_all_moving_averages(price_data: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all common moving averages for a stock

    Args:
        price_data: DataFrame with price data

    Returns:
        DataFrame with added MA columns
    """
    df = price_data.copy()

    # Weekly MAs (converted to daily)
    df["sma_8w"] = df["close"].rolling(window=40).mean()  # 8 weeks * 5 days
    df["sma_10w"] = df["close"].rolling(window=50).mean()  # 10 weeks * 5 days
    df["sma_12w"] = df["close"].rolling(window=60).mean()  # 12 weeks * 5 days
    df["sma_14w"] = df["close"].rolling(window=70).mean()  # 14 weeks * 5 days

    # Common daily MAs
    df["sma_20d"] = df["close"].rolling(window=20).mean()
    df["sma_50d"] = df["close"].rolling(window=50).mean()
    df["sma_200d"] = df["close"].rolling(window=200).mean()

    return df
