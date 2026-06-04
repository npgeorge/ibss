"""
Exit Signal Detection

Stine's exit framework goes beyond the Magic-Line violation. This module layers
two more advisory exits on top of it:

- Parabolic blow-off: a sharp, unsustainable run-up (or price stretched far
  above the Magic Line) — take profits / trim into strength.
- Stall (time-stop): a position that has gone nowhere under resistance for
  weeks — free up the capital.

These are computed from price action alone, so they work on the detail page
without any held-position context. The Magic-Line violation (already computed
elsewhere) is folded in so the page shows one consolidated exit view.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ExitSignal:
    signal_type: str  # "magic_line_violation" | "parabolic" | "stall"
    severity: str  # "critical" | "warning" | "info"
    message: str


@dataclass
class ExitAnalysis:
    symbol: str
    has_exit_signal: bool = False
    recommendation: str = "hold"  # "hold" | "trim" | "exit"
    signals: List[ExitSignal] = field(default_factory=list)


# Thresholds (tuned to be advisory, not trigger-happy)
PARABOLIC_RUNUP_PCT = 0.25  # +25% over ~5 sessions = blow-off risk
PARABOLIC_DISTANCE_PCT = 40.0  # >40% above the Magic Line = overextended
STALL_LOOKBACK_DAYS = 30  # ~6 trading weeks
STALL_RANGE_PCT = 8.0  # range tighter than this = going nowhere
STALL_BELOW_HIGH_PCT = 5.0  # still this far under the recent high


class ExitSignalDetector:
    """Compute advisory exit signals from price action."""

    def __init__(
        self,
        price_data: pd.DataFrame,
        symbol: str = "",
        magic_line_distance_pct: Optional[float] = None,
        violation_detected: bool = False,
    ):
        self.data = price_data
        self.symbol = symbol
        self.magic_line_distance_pct = magic_line_distance_pct
        self.violation_detected = violation_detected

    def detect(self) -> ExitAnalysis:
        analysis = ExitAnalysis(symbol=self.symbol)
        signals: List[ExitSignal] = []

        # 1. Magic-Line violation (most severe — Stine's primary exit)
        if self.violation_detected:
            signals.append(
                ExitSignal(
                    signal_type="magic_line_violation",
                    severity="critical",
                    message="Magic Line violated on consecutive weekly closes — the trend that "
                    "supported the position has broken. Exit.",
                )
            )

        # 2. Parabolic blow-off
        parabolic = self._detect_parabolic()
        if parabolic:
            signals.append(parabolic)

        # 3. Stall / time-stop
        stall = self._detect_stall()
        if stall:
            signals.append(stall)

        analysis.signals = signals
        analysis.has_exit_signal = len(signals) > 0

        # Recommendation by highest severity present.
        if any(s.signal_type == "magic_line_violation" for s in signals):
            analysis.recommendation = "exit"
        elif any(s.signal_type in ("parabolic", "stall") for s in signals):
            analysis.recommendation = "trim"
        else:
            analysis.recommendation = "hold"

        return analysis

    def _detect_parabolic(self) -> Optional[ExitSignal]:
        try:
            closes = self.data["close"]
            if len(closes) >= 6:
                runup = closes.iloc[-1] / closes.iloc[-6] - 1.0
                if runup >= PARABOLIC_RUNUP_PCT:
                    return ExitSignal(
                        signal_type="parabolic",
                        severity="warning",
                        message=f"Parabolic move: +{runup * 100:.0f}% in ~5 sessions. Sharp run-ups "
                        "tend to mean-revert — consider trimming into strength.",
                    )

            if (
                self.magic_line_distance_pct is not None
                and self.magic_line_distance_pct >= PARABOLIC_DISTANCE_PCT
            ):
                return ExitSignal(
                    signal_type="parabolic",
                    severity="warning",
                    message=f"Price is {self.magic_line_distance_pct:.0f}% above the Magic Line — "
                    "overextended. Reversion to support is likely; consider trimming.",
                )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Parabolic detection failed: {e}")
        return None

    def _detect_stall(self) -> Optional[ExitSignal]:
        try:
            if len(self.data) < STALL_LOOKBACK_DAYS + 1:
                return None

            window = self.data.tail(STALL_LOOKBACK_DAYS)
            hi = float(window["high"].max())
            lo = float(window["low"].min())
            if lo <= 0:
                return None

            range_pct = (hi - lo) / lo * 100.0
            current = float(self.data["close"].iloc[-1])
            below_high_pct = (hi - current) / hi * 100.0 if hi > 0 else 0.0

            if range_pct <= STALL_RANGE_PCT and below_high_pct >= STALL_BELOW_HIGH_PCT:
                return ExitSignal(
                    signal_type="stall",
                    severity="info",
                    message=f"Stalled: ~6 weeks in a tight {range_pct:.0f}% range and still "
                    f"{below_high_pct:.0f}% below its recent high. Capital may be better deployed "
                    "elsewhere (time-stop).",
                )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Stall detection failed: {e}")
        return None
