"""
Pattern Recognition Engine

Detects chart patterns critical to the Superstock strategy:
1. Staircase Pattern - Series of higher lows and higher highs with consolidations
2. Cup & Handle - Classic continuation pattern
3. Flat Base - Tight consolidation before breakout
4. Flag Pattern - Short-term consolidation in strong uptrend
5. Breakout - Price breaking resistance with volume
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import date
import logging

logger = logging.getLogger(__name__)


@dataclass
class PatternResult:
    """Result of pattern detection"""

    pattern_type: str
    detected: bool
    strength_score: float  # 0-100
    confidence: float  # 0-100
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    pattern_start_date: Optional[date] = None
    pattern_end_date: Optional[date] = None
    consolidation_days: Optional[int] = None
    notes: str = ""


class PatternRecognizer:
    """
    Recognize chart patterns in price data

    Patterns are detected using technical analysis of price action,
    volume, and moving averages
    """

    def __init__(self, price_data: pd.DataFrame):
        """
        Initialize with price data

        Args:
            price_data: DataFrame with columns ['date', 'open', 'high', 'low', 'close', 'volume']
        """
        self.data = price_data.copy()
        # Normalize: ensure "date" is a plain column, not an index
        if self.data.index.name == "date":
            if "date" in self.data.columns:
                # "date" exists as both index and column — drop the index
                self.data = self.data.reset_index(drop=True)
            else:
                # "date" is only the index — move it to a column
                self.data = self.data.reset_index()
        self.data = self.data.sort_values("date").reset_index(drop=True)

    def detect_all_patterns(self) -> List[PatternResult]:
        """
        Detect all patterns

        Returns:
            List of detected patterns
        """
        patterns = []

        # Detect each pattern type
        patterns.append(self.detect_staircase_pattern())
        patterns.append(self.detect_cup_and_handle())
        patterns.append(self.detect_flat_base())
        patterns.append(self.detect_flag_pattern())
        patterns.append(self.detect_breakout())

        # Return only detected patterns
        return [p for p in patterns if p.detected]

    def detect_staircase_pattern(self, min_steps: int = 3) -> PatternResult:
        """
        Detect Staircase Pattern

        Characteristics:
        - Series of higher lows and higher highs
        - Consolidation periods between steps
        - Volume increases on up-moves, decreases on consolidations
        - Pattern length: 2-6 months typically

        Args:
            min_steps: Minimum number of steps required

        Returns:
            PatternResult
        """
        if len(self.data) < 60:  # Need at least ~3 months
            return PatternResult("staircase", False, 0.0, 0.0, notes="Insufficient data")

        try:
            # Find consolidation periods (low volatility)
            consolidations = self._find_consolidation_periods()

            if len(consolidations) < min_steps:
                return PatternResult(
                    "staircase", False, 0.0, 0.0, notes="Not enough consolidation steps"
                )

            # Check for ascending pattern
            is_ascending = self._check_ascending_pattern(consolidations)

            if not is_ascending:
                return PatternResult(
                    "staircase", False, 0.0, 0.0, notes="Not ascending pattern"
                )

            # Calculate strength score
            strength = self._calculate_staircase_strength(consolidations)

            # Calculate entry/exit levels
            current_price = float(self.data.iloc[-1]["close"])
            recent_low = float(self.data.tail(20)["low"].min())
            recent_high = float(self.data.tail(20)["high"].max())

            entry = recent_low * 1.01  # Just above recent low
            stop_loss = recent_low * 0.95  # 5% below recent low
            target = current_price * 1.5  # 50% gain target

            return PatternResult(
                pattern_type="staircase",
                detected=True,
                strength_score=strength,
                confidence=strength,
                entry_price=entry,
                stop_loss=stop_loss,
                target_price=target,
                pattern_start_date=consolidations[0]["start_date"],
                pattern_end_date=self.data.iloc[-1]["date"],
                consolidation_days=sum(c["duration"] for c in consolidations),
                notes=f"Found {len(consolidations)} steps",
            )

        except Exception as e:
            logger.error(f"Error detecting staircase pattern: {e}")
            return PatternResult("staircase", False, 0.0, 0.0, notes=f"Error: {e}")

    def detect_cup_and_handle(self) -> PatternResult:
        """
        Detect Cup & Handle Pattern

        Characteristics:
        - U-shaped price decline and recovery (cup)
        - Small downward drift or consolidation (handle)
        - Breakout above resistance
        - Duration: 1-6 months

        Returns:
            PatternResult
        """
        if len(self.data) < 30:
            return PatternResult("cup_handle", False, 0.0, 0.0, notes="Insufficient data")

        try:
            # Look for U-shaped pattern in last 60-120 days
            window = min(120, len(self.data))
            recent_data = self.data.tail(window)

            # Find the cup (high-low-high pattern)
            cup_result = self._find_cup_pattern(recent_data)

            if not cup_result:
                return PatternResult("cup_handle", False, 0.0, 0.0, notes="No cup found")

            # Find the handle (pullback after cup)
            handle_result = self._find_handle_pattern(recent_data, cup_result["cup_right"])

            if not handle_result:
                return PatternResult(
                    "cup_handle", False, 0.0, 0.0, notes="Cup found but no handle"
                )

            # Calculate strength
            strength = self._calculate_cup_handle_strength(cup_result, handle_result)

            # Entry/exit levels
            resistance = cup_result["resistance"]
            entry = resistance * 1.02  # 2% above resistance
            stop_loss = handle_result["handle_low"] * 0.98
            target = resistance + (resistance - cup_result["cup_bottom"])  # Same distance as cup depth

            return PatternResult(
                pattern_type="cup_handle",
                detected=True,
                strength_score=strength,
                confidence=strength,
                entry_price=entry,
                stop_loss=stop_loss,
                target_price=target,
                pattern_start_date=cup_result["start_date"],
                pattern_end_date=handle_result["end_date"],
                notes="Cup & Handle pattern detected",
            )

        except Exception as e:
            logger.error(f"Error detecting cup & handle: {e}")
            return PatternResult("cup_handle", False, 0.0, 0.0, notes=f"Error: {e}")

    def detect_flat_base(self, max_volatility: float = 0.15) -> PatternResult:
        """
        Detect Flat Base Pattern

        Characteristics:
        - Tight price consolidation (low volatility)
        - Duration: 2-8 weeks
        - Price stays within 10-15% range
        - Volume dries up

        Args:
            max_volatility: Maximum price variation (0.15 = 15%)

        Returns:
            PatternResult
        """
        if len(self.data) < 10:
            return PatternResult("flat_base", False, 0.0, 0.0, notes="Insufficient data")

        try:
            # Look at last 20-40 days
            window = min(40, len(self.data))
            recent_data = self.data.tail(window)

            # Calculate price range
            high = recent_data["high"].max()
            low = recent_data["low"].min()
            price_range = (high - low) / low

            # Check if within volatility threshold
            if price_range > max_volatility:
                return PatternResult(
                    "flat_base",
                    False,
                    0.0,
                    0.0,
                    notes=f"Too volatile: {price_range:.1%}",
                )

            # Check volume is decreasing
            volume_trend = self._check_declining_volume(recent_data)

            # Calculate strength
            strength = 100 - (price_range / max_volatility * 50)  # Tighter = higher score
            if volume_trend:
                strength += 20  # Bonus for declining volume

            strength = min(strength, 100)

            # Entry/exit levels
            current_price = float(recent_data.iloc[-1]["close"])
            entry = high * 1.01  # Just above resistance
            stop_loss = low * 0.97  # Below base
            target = entry * 1.3  # 30% target

            return PatternResult(
                pattern_type="flat_base",
                detected=True,
                strength_score=strength,
                confidence=strength,
                entry_price=entry,
                stop_loss=stop_loss,
                target_price=target,
                pattern_start_date=recent_data.iloc[0]["date"],
                pattern_end_date=recent_data.iloc[-1]["date"],
                consolidation_days=len(recent_data),
                notes=f"Tight base: {price_range:.1%} range",
            )

        except Exception as e:
            logger.error(f"Error detecting flat base: {e}")
            return PatternResult("flat_base", False, 0.0, 0.0, notes=f"Error: {e}")

    def detect_flag_pattern(self) -> PatternResult:
        """
        Detect Flag Pattern

        Characteristics:
        - Strong uptrend (flagpole)
        - Short consolidation/pullback (flag)
        - Duration: 1-4 weeks
        - Breakout continuation

        Returns:
            PatternResult
        """
        if len(self.data) < 30:
            return PatternResult("flag", False, 0.0, 0.0, notes="Insufficient data")

        try:
            # Need strong uptrend first (flagpole)
            recent_60 = self.data.tail(60)
            pole_gain = (
                recent_60.iloc[-20]["close"] / recent_60.iloc[0]["close"] - 1
            )

            if pole_gain < 0.2:  # Need at least 20% gain
                return PatternResult("flag", False, 0.0, 0.0, notes="No strong uptrend")

            # Check for consolidation/pullback (flag)
            recent_20 = self.data.tail(20)
            flag_high = recent_20["high"].max()
            flag_low = recent_20["low"].min()
            flag_range = (flag_high - flag_low) / flag_low

            # Flag should be relatively tight
            if flag_range > 0.25:  # Max 25% range
                return PatternResult("flag", False, 0.0, 0.0, notes="Consolidation too wide")

            # Check if currently near top of flag
            current_price = float(recent_20.iloc[-1]["close"])
            distance_from_high = (flag_high - current_price) / flag_high

            if distance_from_high > 0.1:  # More than 10% from high
                return PatternResult(
                    "flag", False, 0.0, 0.0, notes="Not near breakout level"
                )

            # Calculate strength
            strength = min(pole_gain * 100, 100)  # Based on flagpole strength

            # Entry/exit levels
            entry = flag_high * 1.01
            stop_loss = flag_low * 0.98
            target = entry * (1 + pole_gain)  # Expect similar move

            return PatternResult(
                pattern_type="flag",
                detected=True,
                strength_score=strength,
                confidence=strength,
                entry_price=entry,
                stop_loss=stop_loss,
                target_price=target,
                pattern_start_date=recent_60.iloc[0]["date"],
                pattern_end_date=recent_20.iloc[-1]["date"],
                notes=f"Flagpole gain: {pole_gain:.1%}",
            )

        except Exception as e:
            logger.error(f"Error detecting flag pattern: {e}")
            return PatternResult("flag", False, 0.0, 0.0, notes=f"Error: {e}")

    def detect_breakout(self, lookback_days: int = 20, volume_threshold: float = 1.5) -> PatternResult:
        """
        Detect Breakout

        Characteristics:
        - Price breaks above resistance (recent high)
        - Volume surge (50%+ above average)
        - Strong close near high of day

        Args:
            lookback_days: Days to look back for resistance
            volume_threshold: Volume multiplier threshold

        Returns:
            PatternResult
        """
        if len(self.data) < lookback_days + 20:
            return PatternResult("breakout", False, 0.0, 0.0, notes="Insufficient data")

        try:
            # Get recent data
            recent = self.data.tail(lookback_days)
            current = self.data.iloc[-1]

            # Find resistance (recent high excluding today)
            resistance = recent.iloc[:-1]["high"].max()

            # Check if current price broke above
            current_price = float(current["close"])
            if current_price <= resistance:
                return PatternResult("breakout", False, 0.0, 0.0, notes="No breakout yet")

            # Check volume surge
            avg_volume = recent["volume"].mean()
            current_volume = float(current["volume"])

            if current_volume < (avg_volume * volume_threshold):
                return PatternResult(
                    "breakout", False, 0.0, 0.0, notes="Insufficient volume"
                )

            # Check close near high (indicates strength)
            day_range = float(current["high"]) - float(current["low"])
            close_position = (
                (current_price - float(current["low"])) / day_range if day_range > 0 else 0
            )

            if close_position < 0.7:  # Should close in top 30% of range
                return PatternResult(
                    "breakout", False, 0.0, 0.0, notes="Weak close position"
                )

            # Calculate strength
            breakout_pct = (current_price - resistance) / resistance
            volume_ratio = current_volume / avg_volume

            strength = min((breakout_pct * 100) + (volume_ratio * 10), 100)

            # Entry/exit levels
            entry = current_price
            stop_loss = resistance * 0.98  # Just below old resistance
            target = current_price * 1.25  # 25% target

            return PatternResult(
                pattern_type="breakout",
                detected=True,
                strength_score=strength,
                confidence=strength,
                entry_price=entry,
                stop_loss=stop_loss,
                target_price=target,
                pattern_start_date=recent.iloc[0]["date"],
                pattern_end_date=current["date"],
                notes=f"Breakout: {breakout_pct:.1%}, Vol: {volume_ratio:.1f}x",
            )

        except Exception as e:
            logger.error(f"Error detecting breakout: {e}")
            return PatternResult("breakout", False, 0.0, 0.0, notes=f"Error: {e}")

    # Helper methods
    def _find_consolidation_periods(
        self, min_days: int = 5, max_volatility: float = 0.10
    ) -> List[Dict]:
        """Find periods of price consolidation"""
        consolidations = []
        i = 0

        while i < len(self.data) - min_days:
            window = self.data.iloc[i : i + min_days]

            # Check volatility
            high = window["high"].max()
            low = window["low"].min()
            volatility = (high - low) / low if low > 0 else 1.0

            if volatility <= max_volatility:
                # Found consolidation
                consolidations.append(
                    {
                        "start_idx": i,
                        "end_idx": i + min_days,
                        "start_date": window.iloc[0]["date"],
                        "end_date": window.iloc[-1]["date"],
                        "duration": min_days,
                        "low": low,
                        "high": high,
                    }
                )
                i += min_days
            else:
                i += 1

        return consolidations

    def _check_ascending_pattern(self, consolidations: List[Dict]) -> bool:
        """Check if consolidations form ascending pattern"""
        for i in range(len(consolidations) - 1):
            curr = consolidations[i]
            next = consolidations[i + 1]

            # Each step should have higher low and higher high
            if next["low"] <= curr["low"] or next["high"] <= curr["high"]:
                return False

        return True

    def _calculate_staircase_strength(self, consolidations: List[Dict]) -> float:
        """Calculate strength of staircase pattern"""
        if not consolidations:
            return 0.0

        # More steps = stronger
        score = min(len(consolidations) * 20, 60)

        # Check angle of ascent
        first_low = consolidations[0]["low"]
        last_high = consolidations[-1]["high"]
        gain = (last_high - first_low) / first_low

        score += min(gain * 100, 40)

        return min(score, 100)

    def _find_cup_pattern(self, data: pd.DataFrame) -> Optional[Dict]:
        """Find cup portion of cup & handle"""
        if len(data) < 30:
            return None

        # Find left rim (early high)
        left_third = data.iloc[: len(data) // 3]
        left_high_idx = left_third["high"].idxmax()

        # Find bottom
        middle_third = data.iloc[len(data) // 3 : 2 * len(data) // 3]
        bottom_idx = middle_third["low"].idxmin()

        # Find right rim
        right_third = data.iloc[2 * len(data) // 3 :]
        right_high_idx = right_third["high"].idxmax()

        # Check if it forms a U shape
        left_high = float(data.loc[left_high_idx, "high"])
        bottom = float(data.loc[bottom_idx, "low"])
        right_high = float(data.loc[right_high_idx, "high"])

        # Rims should be similar height
        if abs(left_high - right_high) / left_high > 0.10:  # Within 10%
            return None

        # Bottom should be significantly lower
        if (left_high - bottom) / left_high < 0.15:  # At least 15% depth
            return None

        return {
            "start_date": data.iloc[0]["date"],
            "cup_bottom": bottom,
            "resistance": (left_high + right_high) / 2,
            "cup_right": right_high_idx,
        }

    def _find_handle_pattern(self, data: pd.DataFrame, cup_right_idx: int) -> Optional[Dict]:
        """Find handle portion after cup"""
        # Handle is after cup right side
        handle_data = data.loc[cup_right_idx:]

        if len(handle_data) < 5:  # Need at least 5 days
            return None

        handle_low = float(handle_data["low"].min())
        handle_end = handle_data.iloc[-1]["date"]

        return {"handle_low": handle_low, "end_date": handle_end}

    def _calculate_cup_handle_strength(self, cup: Dict, handle: Dict) -> float:
        """Calculate cup & handle pattern strength"""
        # Depth of cup
        depth = (cup["resistance"] - cup["cup_bottom"]) / cup["resistance"]

        # Deeper cups (15-30%) are better
        score = min(depth * 200, 60)

        # Handle should be shallow (less than 15% pullback from resistance)
        handle_depth = (cup["resistance"] - handle["handle_low"]) / cup["resistance"]

        if handle_depth < 0.15:
            score += 40
        elif handle_depth < 0.25:
            score += 20

        return min(score, 100)

    def _check_declining_volume(self, data: pd.DataFrame) -> bool:
        """Check if volume is declining"""
        if len(data) < 10:
            return False

        # Compare recent volume to earlier volume
        early_vol = data.iloc[: len(data) // 2]["volume"].mean()
        recent_vol = data.iloc[len(data) // 2 :]["volume"].mean()

        return recent_vol < early_vol * 0.8  # 20% decrease
