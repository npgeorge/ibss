"""
Technical Indicators Calculator

Calculates various technical indicators for stock analysis:
- Moving Averages (SMA)
- Volume indicators
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Relative Strength vs Market
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional


class TechnicalIndicatorCalculator:
    """Calculate technical indicators for stock analysis"""

    def __init__(self, price_data: pd.DataFrame):
        """
        Initialize with price data

        Args:
            price_data: DataFrame with columns ['date', 'open', 'high', 'low', 'close', 'volume']
                       Indexed by date
        """
        self.data = price_data.copy()
        self.data = self.data.sort_index()

    def calculate_all_indicators(self) -> pd.DataFrame:
        """
        Calculate all technical indicators

        Returns:
            DataFrame with all indicators added
        """
        df = self.data.copy()

        # Moving Averages
        df = self._calculate_moving_averages(df)

        # Volume Indicators
        df = self._calculate_volume_indicators(df)

        # Momentum Indicators
        df = self._calculate_rsi(df)
        df = self._calculate_macd(df)

        return df

    def _calculate_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all moving averages"""
        # Weekly MAs (converted to daily)
        df["sma_8w"] = df["close"].rolling(window=40, min_periods=40).mean()  # 8 weeks * 5 days
        df["sma_10w"] = df["close"].rolling(window=50, min_periods=50).mean()  # 10 weeks * 5 days
        df["sma_12w"] = df["close"].rolling(window=60, min_periods=60).mean()  # 12 weeks * 5 days
        df["sma_14w"] = df["close"].rolling(window=70, min_periods=70).mean()  # 14 weeks * 5 days

        # Common daily MAs
        df["sma_20d"] = df["close"].rolling(window=20, min_periods=20).mean()
        df["sma_50d"] = df["close"].rolling(window=50, min_periods=50).mean()
        df["sma_200d"] = df["close"].rolling(window=200, min_periods=200).mean()

        return df

    def _calculate_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume indicators"""
        # Average volumes
        df["volume_avg_20d"] = df["volume"].rolling(window=20, min_periods=20).mean()
        df["volume_avg_50d"] = df["volume"].rolling(window=50, min_periods=50).mean()

        # Volume ratio (current vs average)
        df["volume_ratio"] = df["volume"] / df["volume_avg_20d"]

        return df

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculate Relative Strength Index (RSI)

        RSI oscillates between 0-100:
        - Above 70: Overbought
        - Below 30: Oversold
        """
        delta = df["close"].diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=period).mean()

        rs = gain / loss
        df["rsi_14"] = 100 - (100 / (1 + rs))

        return df

    def _calculate_macd(
        self,
        df: pd.DataFrame,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> pd.DataFrame:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        MACD = 12-day EMA - 26-day EMA
        Signal = 9-day EMA of MACD
        Histogram = MACD - Signal
        """
        # Calculate EMAs
        ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()

        # MACD line
        df["macd"] = ema_fast - ema_slow

        # Signal line
        df["macd_signal"] = df["macd"].ewm(span=signal_period, adjust=False).mean()

        # Histogram
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        return df

    def calculate_relative_strength(
        self, df: pd.DataFrame, market_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate relative strength vs market (e.g., SPY)

        Higher values = outperforming market
        Lower values = underperforming market

        Args:
            df: Stock price data
            market_data: Market index price data (e.g., SPY)
        """
        # Calculate percent changes
        stock_returns = df["close"].pct_change()
        market_returns = market_data["close"].pct_change()

        # Relative strength = stock returns / market returns
        # Use rolling average to smooth
        df["relative_strength"] = (
            (stock_returns / market_returns).rolling(window=20, min_periods=20).mean()
        )

        return df

    @staticmethod
    def detect_volume_surge(
        current_volume: float, avg_volume: float, threshold: float = 1.5
    ) -> bool:
        """
        Detect if volume has surged above average

        Args:
            current_volume: Current day's volume
            avg_volume: Average volume
            threshold: Multiplier threshold (1.5 = 50% above average)

        Returns:
            True if volume surge detected
        """
        if avg_volume == 0:
            return False

        return current_volume >= (avg_volume * threshold)

    @staticmethod
    def calculate_price_change_rate(
        current_price: float, previous_price: float
    ) -> float:
        """
        Calculate price change percentage

        Returns:
            Percentage change (e.g., 5.25 for 5.25% gain)
        """
        if previous_price == 0:
            return 0.0

        return ((current_price - previous_price) / previous_price) * 100

    def get_latest_indicators(self) -> Dict[str, Optional[float]]:
        """
        Get latest calculated indicators

        Returns:
            Dictionary of indicator values
        """
        df = self.calculate_all_indicators()

        if len(df) == 0:
            return {}

        latest = df.iloc[-1]

        return {
            "sma_8w": float(latest.get("sma_8w", 0)) if pd.notna(latest.get("sma_8w")) else None,
            "sma_10w": float(latest.get("sma_10w", 0)) if pd.notna(latest.get("sma_10w")) else None,
            "sma_12w": float(latest.get("sma_12w", 0)) if pd.notna(latest.get("sma_12w")) else None,
            "sma_14w": float(latest.get("sma_14w", 0)) if pd.notna(latest.get("sma_14w")) else None,
            "sma_20d": float(latest.get("sma_20d", 0)) if pd.notna(latest.get("sma_20d")) else None,
            "sma_50d": float(latest.get("sma_50d", 0)) if pd.notna(latest.get("sma_50d")) else None,
            "sma_200d": float(latest.get("sma_200d", 0)) if pd.notna(latest.get("sma_200d")) else None,
            "volume_avg_20d": int(latest.get("volume_avg_20d", 0)) if pd.notna(latest.get("volume_avg_20d")) else None,
            "volume_avg_50d": int(latest.get("volume_avg_50d", 0)) if pd.notna(latest.get("volume_avg_50d")) else None,
            "volume_ratio": float(latest.get("volume_ratio", 0)) if pd.notna(latest.get("volume_ratio")) else None,
            "rsi_14": float(latest.get("rsi_14", 0)) if pd.notna(latest.get("rsi_14")) else None,
            "macd": float(latest.get("macd", 0)) if pd.notna(latest.get("macd")) else None,
            "macd_signal": float(latest.get("macd_signal", 0)) if pd.notna(latest.get("macd_signal")) else None,
            "macd_histogram": float(latest.get("macd_histogram", 0)) if pd.notna(latest.get("macd_histogram")) else None,
            "relative_strength": float(latest.get("relative_strength", 0)) if pd.notna(latest.get("relative_strength")) else None,
        }


def detect_golden_cross(sma_50: float, sma_200: float, prev_sma_50: float, prev_sma_200: float) -> bool:
    """
    Detect Golden Cross pattern (50 SMA crosses above 200 SMA)

    Bullish signal

    Args:
        sma_50: Current 50-day SMA
        sma_200: Current 200-day SMA
        prev_sma_50: Previous 50-day SMA
        prev_sma_200: Previous 200-day SMA

    Returns:
        True if golden cross detected
    """
    # Was below, now above
    return prev_sma_50 < prev_sma_200 and sma_50 > sma_200


def detect_death_cross(sma_50: float, sma_200: float, prev_sma_50: float, prev_sma_200: float) -> bool:
    """
    Detect Death Cross pattern (50 SMA crosses below 200 SMA)

    Bearish signal

    Args:
        sma_50: Current 50-day SMA
        sma_200: Current 200-day SMA
        prev_sma_50: Previous 50-day SMA
        prev_sma_200: Previous 200-day SMA

    Returns:
        True if death cross detected
    """
    # Was above, now below
    return prev_sma_50 > prev_sma_200 and sma_50 < sma_200


def is_above_moving_average(price: float, ma: float, tolerance: float = 0.0) -> bool:
    """
    Check if price is above moving average

    Args:
        price: Current price
        ma: Moving average value
        tolerance: Tolerance percentage (e.g., 0.02 for 2%)

    Returns:
        True if price is above MA (within tolerance)
    """
    if ma == 0:
        return False

    threshold = ma * (1 + tolerance)
    return price >= threshold


def calculate_distance_from_ma(price: float, ma: float) -> float:
    """
    Calculate distance from moving average in percentage

    Args:
        price: Current price
        ma: Moving average value

    Returns:
        Percentage distance (positive = above, negative = below)
    """
    if ma == 0:
        return 0.0

    return ((price - ma) / ma) * 100
