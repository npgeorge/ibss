"""
Smoke test for scoring pipeline.

Verifies that scores stay in reasonable 0-100 ranges and are NOT
all blown to 100 by the double-scaling bug.

Usage:
    python -m scripts.test_scoring
"""
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.services.screener import SuperstockScorer
from app.services.pattern_recognition import PatternRecognizer


def _make_price_data(days: int = 120, start_price: float = 5.0) -> pd.DataFrame:
    """Generate synthetic price data with a mild uptrend."""
    dates = pd.bdate_range(end=datetime.now(), periods=days)
    n = len(dates)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.02, n)
    trend = np.linspace(0, 0.3, n)
    closes = start_price * (1 + trend + np.cumsum(noise))
    highs = closes * (1 + np.abs(rng.normal(0, 0.01, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.01, n)))
    opens = (closes + lows) / 2
    volumes = rng.integers(100_000, 500_000, size=n).astype(float)

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
    df.index.name = "date"
    return df


def test_score_ranges():
    """Scores should be in 0-100, NOT all pegged to 100."""
    price_data = _make_price_data()
    stock_info = {"symbol": "TEST", "company_name": "Test Inc", "sector": "Tech", "market_cap": 500_000_000}
    fundamentals = {
        "eps_growth_yoy": 25,
        "revenue_growth_yoy": 15,
        "peg_ratio": 1.5,
        "pe_ratio": 18,
    }

    scorer = SuperstockScorer(price_data, stock_info, fundamentals)
    result = scorer.calculate_composite_score()

    errors = []
    for name, val in [
        ("technical_score", result.technical_score),
        ("fundamental_score", result.fundamental_score),
        ("insider_score", result.insider_score),
        ("pattern_score", result.pattern_score),
        ("total_score", result.total_score),
    ]:
        if val < 0 or val > 100:
            errors.append(f"{name}={val} out of [0,100]")
        if name in ("technical_score", "fundamental_score") and val == 100:
            errors.append(f"{name}=100 looks suspiciously pegged (double-scaling bug?)")

    # With moderate fundamentals (25% EPS, 15% revenue, PEG 1.5),
    # fundamental_score should be well below 100
    if result.fundamental_score > 95:
        errors.append(f"fundamental_score={result.fundamental_score} too high for moderate inputs")

    return errors, result


def test_pattern_recognizer_with_index():
    """PatternRecognizer should handle DataFrames with DatetimeIndex named 'date'."""
    df = _make_price_data()
    # df has DatetimeIndex named "date" and NO "date" column — matches batch fetcher output
    assert df.index.name == "date"
    assert "date" not in df.columns

    try:
        recognizer = PatternRecognizer(df)
        patterns = recognizer.detect_all_patterns()
        return None  # success
    except Exception as e:
        return f"PatternRecognizer failed: {e}"


def main():
    print("=== IBSS Scoring Smoke Test ===\n")
    passed = 0
    failed = 0

    # Test 1: Score ranges
    errors, result = test_score_ranges()
    print(f"Scores: tech={result.technical_score:.1f}  fund={result.fundamental_score:.1f}  "
          f"insider={result.insider_score:.1f}  pattern={result.pattern_score:.1f}  "
          f"total={result.total_score:.1f}")
    if errors:
        print(f"FAIL: test_score_ranges")
        for e in errors:
            print(f"  - {e}")
        failed += 1
    else:
        print("PASS: test_score_ranges")
        passed += 1

    # Test 2: Pattern recognizer handles DatetimeIndex
    err = test_pattern_recognizer_with_index()
    if err:
        print(f"FAIL: test_pattern_recognizer_with_index — {err}")
        failed += 1
    else:
        print("PASS: test_pattern_recognizer_with_index")
        passed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
