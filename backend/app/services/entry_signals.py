"""
Entry Signals Service

Detects specific entry signals based on Jesse Stine's methodology:
- Magic Line touch (low-risk entry at support)
- Pullback in uptrend (15-25% off highs = buy the dip)
- Breakout with volume (momentum entry)
- Pattern completion (cup & handle, staircase completion)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    """Types of entry signals"""
    MAGIC_LINE_TOUCH = "magic_line_touch"
    PULLBACK_ENTRY = "pullback_entry"
    BREAKOUT_VOLUME = "breakout_volume"
    PATTERN_COMPLETE = "pattern_complete"
    CONSOLIDATION_BREAK = "consolidation_break"
    BOUNCE_CONFIRMATION = "bounce_confirmation"


class SignalStrength(str, Enum):
    """Signal strength classification"""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class EntrySignal:
    """Individual entry signal"""
    signal_type: SignalType
    strength: SignalStrength
    description: str

    # Price levels
    entry_price: float
    stop_loss: float
    target_price: Optional[float] = None

    # Risk/reward
    risk_pct: float = 0.0  # % risk from entry to stop
    reward_pct: float = 0.0  # % reward from entry to target
    risk_reward_ratio: float = 0.0

    # Timing
    is_actionable_now: bool = False  # Can trade right now
    days_valid: int = 5  # Days signal remains valid

    # Score
    score: float = 0.0  # 0-100 signal quality

    @property
    def is_quality_setup(self) -> bool:
        """Check if this is a quality setup worth trading"""
        return self.score >= 70 and self.risk_reward_ratio >= 2.0


@dataclass
class EntrySignalResult:
    """Result of entry signal detection"""
    symbol: str
    has_signal: bool
    signals: List[EntrySignal]
    best_signal: Optional[EntrySignal]

    # Current context
    current_price: float
    distance_from_magic_line_pct: float
    distance_from_high_pct: float

    # Overall assessment
    overall_score: float
    recommendation: str  # "buy_now", "wait_for_pullback", "watch", "avoid"

    # Book entry laws
    dont_chase: bool = False  # price extended >20% above Magic Line — do not chase
    scale_in_guidance: str = ""  # how to build the position (scale-in plan)


class EntrySignalDetector:
    """
    Detect entry signals for Superstock candidates

    Jesse Stine's entry rules:
    1. Wait for price to touch Magic Line for low-risk entry
    2. Buy 15-25% pullbacks in established uptrends
    3. Chase breakouts only with 2x+ volume confirmation
    4. Pattern completions (cup handle, staircase) trigger entries
    """

    def __init__(
        self,
        price_data: pd.DataFrame,
        magic_line_period: int = 10
    ):
        """
        Initialize with price data

        Args:
            price_data: DataFrame with OHLCV data
            magic_line_period: Period for Magic Line (weekly SMA)
        """
        self.data = price_data.copy()
        self.magic_line_period = magic_line_period
        self._calculate_indicators()

    def _calculate_indicators(self):
        """Calculate required technical indicators"""
        # Magic Line (10-week SMA, ~50 trading days)
        ml_lookback = self.magic_line_period * 5  # Approximate trading days
        self.data["magic_line"] = self.data["close"].rolling(window=ml_lookback).mean()

        # 20-day SMA
        self.data["sma_20"] = self.data["close"].rolling(window=20).mean()

        # 50-day SMA
        self.data["sma_50"] = self.data["close"].rolling(window=50).mean()

        # 20-day average volume
        self.data["avg_volume"] = self.data["volume"].rolling(window=20).mean()

        # ATR for stop loss calculation
        high_low = self.data["high"] - self.data["low"]
        high_close = abs(self.data["high"] - self.data["close"].shift(1))
        low_close = abs(self.data["low"] - self.data["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        self.data["atr_14"] = true_range.rolling(window=14).mean()

        # 52-week high
        self.data["high_52w"] = self.data["high"].rolling(window=252).max()

    def detect_signals(self) -> EntrySignalResult:
        """
        Detect all entry signals

        Returns:
            EntrySignalResult with all detected signals
        """
        signals = []

        # Get current values
        latest = self.data.iloc[-1]
        current_price = latest["close"]
        magic_line = latest["magic_line"]
        high_52w = latest["high_52w"]

        # Calculate distances
        if pd.notna(magic_line) and magic_line > 0:
            distance_from_ml = (current_price - magic_line) / magic_line * 100
        else:
            distance_from_ml = 0

        if pd.notna(high_52w) and high_52w > 0:
            distance_from_high = (high_52w - current_price) / high_52w * 100
        else:
            distance_from_high = 0

        # Detect each signal type
        ml_signal = self._detect_magic_line_touch()
        if ml_signal:
            signals.append(ml_signal)

        pullback_signal = self._detect_pullback_entry()
        if pullback_signal:
            signals.append(pullback_signal)

        breakout_signal = self._detect_breakout_volume()
        if breakout_signal:
            signals.append(breakout_signal)

        consolidation_signal = self._detect_consolidation_break()
        if consolidation_signal:
            signals.append(consolidation_signal)

        bounce_signal = self._detect_bounce_confirmation()
        if bounce_signal:
            signals.append(bounce_signal)

        # Find best signal
        best_signal = None
        if signals:
            best_signal = max(signals, key=lambda s: s.score)

        # Calculate overall score
        overall_score = best_signal.score if best_signal else 0

        # Don't-chase law: never enter when extended >20% above the Magic Line.
        dont_chase = distance_from_ml > 20

        # Determine recommendation
        recommendation = self._get_recommendation(signals, distance_from_ml, distance_from_high)
        if dont_chase and recommendation == "buy_now":
            recommendation = "wait_for_pullback"

        scale_in_guidance = self._get_scale_in_guidance(
            best_signal, distance_from_ml, dont_chase
        )

        symbol = self.data["symbol"].iloc[0] if "symbol" in self.data.columns else "UNKNOWN"

        return EntrySignalResult(
            symbol=symbol,
            has_signal=len(signals) > 0,
            signals=signals,
            best_signal=best_signal,
            current_price=round(current_price, 2),
            distance_from_magic_line_pct=round(distance_from_ml, 2),
            distance_from_high_pct=round(distance_from_high, 2),
            overall_score=overall_score,
            recommendation=recommendation,
            dont_chase=dont_chase,
            scale_in_guidance=scale_in_guidance,
        )

    @staticmethod
    def _get_scale_in_guidance(
        best_signal: Optional["EntrySignal"],
        distance_from_ml: float,
        dont_chase: bool,
    ) -> str:
        """
        Stine's scale-in law: build positions in tranches rather than all at once.

        Guidance keys off how extended price is and how strong the entry is.
        """
        if dont_chase:
            return "Extended >20% above the Magic Line — wait for a pullback; do not chase."
        if best_signal is None:
            return "No active entry signal — wait for a Magic Line touch before committing capital."
        if best_signal.score >= 80 and distance_from_ml <= 5:
            return "Strong signal near the Magic Line: start with a 1/2 position, add the rest on a confirmed bounce."
        if best_signal.score >= 60:
            return "Decent setup: scale in 1/3 now, 1/3 on confirmation, 1/3 on a higher low."
        return "Marginal setup: take a starter 1/4 position only, or wait for a cleaner entry."

    def _detect_magic_line_touch(self) -> Optional[EntrySignal]:
        """
        Detect Magic Line touch entry

        Jesse's principle: Price touching or coming within 2-3% of Magic Line
        in an uptrend is a low-risk entry point.
        """
        if len(self.data) < 60:
            return None

        latest = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        current_price = latest["close"]
        magic_line = latest["magic_line"]

        if pd.isna(magic_line):
            return None

        # Calculate distance from Magic Line
        distance_pct = (current_price - magic_line) / magic_line * 100

        # Check if touching or very close (within 3%)
        is_touching = -1 <= distance_pct <= 3

        if not is_touching:
            return None

        # Verify uptrend (Magic Line rising)
        ml_5_days_ago = self.data.iloc[-5]["magic_line"] if len(self.data) >= 5 else magic_line
        ml_rising = magic_line > ml_5_days_ago

        if not ml_rising:
            return None

        # Calculate entry levels
        entry_price = current_price
        atr = latest["atr_14"]
        stop_loss = magic_line - (atr * 1.5)  # Stop below Magic Line
        target_price = current_price + (current_price - stop_loss) * 3  # 3:1 R/R

        # Calculate risk/reward
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        reward_pct = (target_price - entry_price) / entry_price * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0

        # Determine strength
        if distance_pct <= 1 and ml_rising:
            strength = SignalStrength.STRONG
            score = 90
        elif distance_pct <= 2:
            strength = SignalStrength.MODERATE
            score = 75
        else:
            strength = SignalStrength.WEAK
            score = 60

        return EntrySignal(
            signal_type=SignalType.MAGIC_LINE_TOUCH,
            strength=strength,
            description=f"Price at Magic Line support ({distance_pct:.1f}% away) - LOW RISK ENTRY",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            is_actionable_now=True,
            days_valid=3,
            score=score,
        )

    def _detect_pullback_entry(self) -> Optional[EntrySignal]:
        """
        Detect pullback entry in uptrend

        Jesse's principle: 15-25% pullback from highs in an established
        uptrend is a buying opportunity (buy the dip).
        """
        if len(self.data) < 100:
            return None

        latest = self.data.iloc[-1]
        current_price = latest["close"]

        # Find 52-week high
        high_52w = self.data["high"].tail(252).max()

        # Calculate pullback depth
        pullback_pct = (high_52w - current_price) / high_52w * 100

        # Check if in ideal pullback zone (15-30%)
        if not (15 <= pullback_pct <= 30):
            return None

        # Verify uptrend context
        # Price should still be above 200-day MA
        sma_200 = self.data["close"].tail(200).mean()
        if current_price < sma_200:
            return None

        # Check for orderly pullback (not panicked selling)
        recent_atr = self.data["atr_14"].tail(10).mean()
        avg_atr = self.data["atr_14"].mean()
        is_orderly = recent_atr <= avg_atr * 1.3

        if not is_orderly:
            return None

        # Calculate entry levels
        entry_price = current_price
        stop_loss = self.data["low"].tail(10).min() * 0.98  # Below recent lows
        target_price = high_52w  # First target = retest of highs

        # Calculate risk/reward
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        reward_pct = (target_price - entry_price) / entry_price * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0

        # Determine strength based on pullback depth
        if 18 <= pullback_pct <= 25:
            strength = SignalStrength.STRONG
            score = 85
        elif 15 <= pullback_pct < 18 or 25 < pullback_pct <= 28:
            strength = SignalStrength.MODERATE
            score = 70
        else:
            strength = SignalStrength.WEAK
            score = 55

        return EntrySignal(
            signal_type=SignalType.PULLBACK_ENTRY,
            strength=strength,
            description=f"{pullback_pct:.0f}% pullback in uptrend - BUY THE DIP",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            is_actionable_now=True,
            days_valid=5,
            score=score,
        )

    def _detect_breakout_volume(self) -> Optional[EntrySignal]:
        """
        Detect breakout with volume confirmation

        Jesse's principle: Breakout on 2x+ average volume confirms
        institutional buying. Chase with tight stop.
        """
        if len(self.data) < 30:
            return None

        latest = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        current_price = latest["close"]
        current_volume = latest["volume"]
        avg_volume = latest["avg_volume"]

        # Check for volume surge
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio < 1.5:
            return None

        # Check for price breakout (new 20-day high)
        high_20d = self.data["high"].tail(20).iloc[:-1].max()  # Exclude today
        is_breakout = current_price > high_20d

        if not is_breakout:
            return None

        # Verify trend support
        sma_50 = latest["sma_50"]
        if pd.notna(sma_50) and current_price < sma_50:
            return None  # Don't chase breakouts in downtrends

        # Calculate entry levels
        entry_price = current_price
        atr = latest["atr_14"]
        stop_loss = prev["low"] - atr * 0.5  # Tight stop below prev low
        target_price = entry_price + (entry_price - stop_loss) * 2.5  # 2.5:1 R/R

        # Calculate risk/reward
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        reward_pct = (target_price - entry_price) / entry_price * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0

        # Determine strength based on volume surge
        if volume_ratio >= 3.0:
            strength = SignalStrength.STRONG
            score = 85
        elif volume_ratio >= 2.0:
            strength = SignalStrength.MODERATE
            score = 70
        else:
            strength = SignalStrength.WEAK
            score = 55

        return EntrySignal(
            signal_type=SignalType.BREAKOUT_VOLUME,
            strength=strength,
            description=f"Breakout on {volume_ratio:.1f}x volume - MOMENTUM ENTRY",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            is_actionable_now=True,
            days_valid=2,
            score=score,
        )

    def _detect_consolidation_break(self) -> Optional[EntrySignal]:
        """
        Detect consolidation/tight range breakout

        Price consolidating in tight range followed by expansion
        """
        if len(self.data) < 20:
            return None

        latest = self.data.iloc[-1]
        current_price = latest["close"]

        # Check recent range tightness
        recent = self.data.tail(10)
        range_high = recent["high"].max()
        range_low = recent["low"].min()
        range_pct = (range_high - range_low) / range_low * 100

        # Range should be tight (<10%)
        if range_pct > 10:
            return None

        # Check for range breakout
        is_breaking_up = current_price > range_high * 0.99
        is_breaking_down = current_price < range_low * 1.01

        if not is_breaking_up:
            return None

        # Calculate entry levels
        entry_price = current_price
        stop_loss = range_low * 0.98
        target_price = entry_price + (range_high - range_low) * 2  # 2x range expansion

        # Calculate risk/reward
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        reward_pct = (target_price - entry_price) / entry_price * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0

        # Score based on range tightness
        if range_pct < 5:
            strength = SignalStrength.STRONG
            score = 80
        elif range_pct < 7:
            strength = SignalStrength.MODERATE
            score = 65
        else:
            strength = SignalStrength.WEAK
            score = 50

        return EntrySignal(
            signal_type=SignalType.CONSOLIDATION_BREAK,
            strength=strength,
            description=f"Breaking out of {range_pct:.1f}% consolidation range",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            is_actionable_now=True,
            days_valid=3,
            score=score,
        )

    def _detect_bounce_confirmation(self) -> Optional[EntrySignal]:
        """
        Detect confirmed bounce from support

        Price bouncing from key support with follow-through
        """
        if len(self.data) < 20:
            return None

        latest = self.data.iloc[-1]
        prev_1 = self.data.iloc[-2]
        prev_2 = self.data.iloc[-3]

        current_price = latest["close"]

        # Look for reversal pattern (down, down, up with close near high)
        is_reversal = (
            prev_2["close"] < prev_2["open"] and  # Day -2 was red
            prev_1["close"] < prev_1["open"] and  # Day -1 was red
            latest["close"] > latest["open"] and  # Today is green
            latest["close"] > (latest["high"] + latest["low"]) / 2  # Close in upper half
        )

        if not is_reversal:
            return None

        # Check if bounce from support level (recent lows)
        recent_low = self.data["low"].tail(20).min()
        bounced_from_support = prev_1["low"] <= recent_low * 1.02

        if not bounced_from_support:
            return None

        # Calculate entry levels
        entry_price = current_price
        stop_loss = recent_low * 0.97
        atr = latest["atr_14"]
        target_price = entry_price + atr * 4  # 4 ATR target

        # Calculate risk/reward
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        reward_pct = (target_price - entry_price) / entry_price * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0

        # Volume confirmation
        volume_ratio = latest["volume"] / latest["avg_volume"] if latest["avg_volume"] > 0 else 1

        if volume_ratio >= 1.5:
            strength = SignalStrength.STRONG
            score = 75
        elif volume_ratio >= 1.2:
            strength = SignalStrength.MODERATE
            score = 60
        else:
            strength = SignalStrength.WEAK
            score = 45

        return EntrySignal(
            signal_type=SignalType.BOUNCE_CONFIRMATION,
            strength=strength,
            description="Confirmed bounce from support with follow-through",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            is_actionable_now=True,
            days_valid=2,
            score=score,
        )

    def _get_recommendation(
        self,
        signals: List[EntrySignal],
        distance_from_ml: float,
        distance_from_high: float
    ) -> str:
        """Get overall recommendation"""
        if not signals:
            # No signals - determine if should wait or avoid
            if 0 < distance_from_ml < 5:
                return "watch"  # Close to Magic Line
            elif distance_from_ml > 20:
                return "wait_for_pullback"  # Extended from Magic Line
            else:
                return "watch"

        # Have signals - check quality
        best = max(signals, key=lambda s: s.score)

        if best.score >= 80 and best.is_actionable_now:
            return "buy_now"
        elif best.score >= 60:
            return "watch"
        else:
            return "avoid"


def detect_entry_signals(
    price_data: pd.DataFrame,
    magic_line_period: int = 10
) -> EntrySignalResult:
    """
    Convenience function to detect entry signals

    Args:
        price_data: DataFrame with OHLCV data
        magic_line_period: Period for Magic Line

    Returns:
        EntrySignalResult with all signals
    """
    detector = EntrySignalDetector(price_data, magic_line_period)
    return detector.detect_signals()
