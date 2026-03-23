# IBSS Enhancement Plan: Lessons from Financial AI Agents

Based on the article "Lessons from Building AI Agents for Financial Services"

## Executive Summary

The IBSS Superstock screener can be significantly improved by adopting patterns from production financial AI systems. The key improvements focus on:
1. Real-time streaming for better UX during scans
2. Normalized data context from multiple sources
3. Markdown-based "skills" encoding Jesse Stine's methodology
4. Domain-specific evaluation to ensure accuracy

---

## Phase 1: Real-Time Streaming (Highest Impact)

### Problem
Current scanning of 200+ stocks takes 30+ seconds with no feedback. Users see a loading spinner and may think it's broken.

### Solution
Implement Server-Sent Events (SSE) streaming so users see:
- Which stock is being analyzed
- Running count of scored stocks
- Partial results appearing as they're computed

### Implementation

**Backend Changes:**

```python
# app/api/screener.py - New streaming endpoint

from fastapi.responses import StreamingResponse
import json

@router.post("/stream")
async def stream_screening(criteria: ScreenerCriteriaRequest):
    """Stream screening results as they're computed"""

    async def generate():
        # Initial status
        yield f"data: {json.dumps({'type': 'status', 'message': 'Starting pre-filter...'})}\n\n"

        # Pre-filter
        prefilter_result = await get_prefiltered_symbols(criteria.mode)
        yield f"data: {json.dumps({'type': 'prefilter', 'count': len(prefilter_result.symbols)})}\n\n"

        # Screen each stock
        for i, symbol in enumerate(prefilter_result.symbols[:200]):
            yield f"data: {json.dumps({'type': 'progress', 'current': i+1, 'total': 200, 'symbol': symbol})}\n\n"

            # Score the stock
            score = await screen_single_stock(symbol, prefilter_result, criteria)

            if score and score.total_score >= criteria.min_total_score:
                yield f"data: {json.dumps({'type': 'result', 'data': score.dict()})}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Frontend Changes:**

```typescript
// src/services/api.ts - Streaming client

export async function streamScreening(
  criteria: ScreeningCriteria,
  onProgress: (data: ProgressEvent) => void,
  onResult: (result: StockScreenResult) => void,
  onComplete: () => void
) {
  const response = await fetch('/api/v1/screen/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(criteria),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        switch (data.type) {
          case 'progress': onProgress(data); break;
          case 'result': onResult(data.data); break;
          case 'complete': onComplete(); break;
        }
      }
    }
  }
}
```

**UI Updates:**
- Show progress bar with "Scanning AAPL (45/200)"
- Results table populates incrementally as stocks are scored
- User can see top candidates appearing in real-time

### Files to Create/Modify
- `backend/app/api/screener.py` - Add streaming endpoint
- `frontend/src/services/api.ts` - Add streaming client
- `frontend/src/pages/Screener.tsx` - Progressive results display
- `frontend/src/components/ScanProgress.tsx` - New progress component

---

## Phase 2: Context Normalization Layer

### Problem
Data comes from multiple sources with different formats:
- Finviz: Web scraping, HTML tables
- yfinance: API, pandas DataFrames
- OpenInsider: Web scraping, different HTML structure
- SEC EDGAR: Complex HTML filings

### Solution
Create a unified `StockContext` that normalizes all data into a clean, consistent format.

### Implementation

```python
# app/services/context_builder.py

from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import date

@dataclass
class NormalizedFinancials:
    """Normalized financial metrics - all in same units"""
    revenue_ttm: Optional[float] = None  # Always in millions USD
    revenue_growth_yoy: Optional[float] = None  # Always as decimal (0.15 = 15%)
    eps_ttm: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    market_cap: Optional[float] = None  # Always in millions USD
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

@dataclass
class NormalizedTechnicals:
    """Normalized technical data"""
    price: float
    volume: int
    avg_volume_20d: int
    relative_volume: float  # current / avg

    # Moving averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None

    # Position relative to MAs
    above_sma_20: bool = False
    above_sma_50: bool = False
    above_sma_200: bool = False

    # 52-week range
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    pct_from_52w_high: Optional[float] = None

    # Magic Line (calculated)
    magic_line_period: Optional[int] = None
    magic_line_value: Optional[float] = None
    magic_line_distance_pct: Optional[float] = None

@dataclass
class NormalizedInsider:
    """Normalized insider activity"""
    has_recent_buys: bool = False
    buy_count_90d: int = 0
    total_buy_value_90d: float = 0  # USD
    is_cluster_buy: bool = False  # Multiple insiders buying
    most_recent_buy_date: Optional[date] = None
    insider_names: List[str] = None

@dataclass
class StockContext:
    """Complete normalized context for a stock"""
    # Identity
    symbol: str
    company_name: str
    sector: str
    industry: str

    # Data quality
    data_freshness: date
    confidence_score: float  # 0-1, based on data completeness

    # Normalized data
    financials: NormalizedFinancials
    technicals: NormalizedTechnicals
    insider: NormalizedInsider

    # Raw data references (for debugging)
    source_finviz: Optional[Dict] = None
    source_yfinance: Optional[Dict] = None
    source_openinsider: Optional[Dict] = None


class ContextBuilder:
    """Build normalized stock context from multiple sources"""

    async def build_context(
        self,
        symbol: str,
        finviz_data: Optional[StockMetrics] = None,
        price_df: Optional[pd.DataFrame] = None,
        insider_data: Optional[List[InsiderTransaction]] = None,
    ) -> StockContext:
        """
        Normalize and merge data from all sources into unified context
        """
        financials = self._normalize_financials(finviz_data, price_df)
        technicals = self._normalize_technicals(price_df, finviz_data)
        insider = self._normalize_insider(insider_data)

        # Calculate confidence based on data completeness
        confidence = self._calculate_confidence(financials, technicals, insider)

        return StockContext(
            symbol=symbol,
            company_name=finviz_data.company if finviz_data else "",
            sector=finviz_data.sector if finviz_data else "Unknown",
            industry=finviz_data.industry if finviz_data else "Unknown",
            data_freshness=date.today(),
            confidence_score=confidence,
            financials=financials,
            technicals=technicals,
            insider=insider,
        )

    def _normalize_financials(self, finviz, price_df) -> NormalizedFinancials:
        """Normalize financial data from Finviz"""
        # Convert all values to standard units
        # Handle missing data gracefully
        pass

    def _normalize_technicals(self, price_df, finviz) -> NormalizedTechnicals:
        """Calculate technical indicators from price data"""
        # Compute all technicals from raw price data
        # Don't rely on pre-computed values
        pass

    def _normalize_insider(self, transactions) -> NormalizedInsider:
        """Normalize insider activity"""
        # Aggregate transactions into summary metrics
        pass

    def _calculate_confidence(self, fin, tech, ins) -> float:
        """Score 0-1 based on data completeness"""
        # More complete data = higher confidence
        pass
```

### Benefits
1. **Single source of truth** - Screener only uses `StockContext`, not raw data
2. **Testable** - Can verify normalization logic independently
3. **Extensible** - Add new data sources without changing screener
4. **Debuggable** - Raw data preserved for investigation

### Files to Create
- `backend/app/services/context_builder.py` - Context normalization
- `backend/app/models/context.py` - Dataclass definitions

---

## Phase 3: Skills System (Jesse Stine Methodology)

### Problem
The Jesse Stine methodology is currently embedded in Python code. Hard to:
- Understand what criteria are being used
- Modify weights or thresholds
- Add new strategies
- Let users customize

### Solution
Encode the methodology as markdown "skills" that define:
- What criteria to check
- How to score each criterion
- What thresholds to use
- How to weight the composite score

### Implementation

**Skill Structure:**
```
/skills
├── superstock/
│   ├── SKILL.md           # Main skill definition
│   ├── criteria/
│   │   ├── price_range.md
│   │   ├── magic_line.md
│   │   ├── volume_dryup.md
│   │   ├── insider_buying.md
│   │   └── ...
│   └── profiles/
│       ├── aggressive.yaml  # Higher risk tolerance
│       ├── conservative.yaml
│       └── default.yaml
├── momentum/
│   └── SKILL.md
└── value/
    └── SKILL.md
```

**Main Skill File:**
```markdown
# skills/superstock/SKILL.md

---
name: superstock
version: 1.0
description: Jesse Stine's Superstock methodology - find 100-1000% gainers
author: IBSS
---

# Superstock Screening Skill

## Overview
This skill implements Jesse Stine's Superstock methodology from
"Insider Buy Superstocks". It identifies stocks with potential for
100-1000% gains based on technical, fundamental, and insider criteria.

## When to Use
- Searching for high-growth small cap opportunities
- Looking for stocks with insider buying activity
- Finding stocks respecting their "Magic Line" (10-week SMA)

## Criteria (19 Total)

### Technical Criteria (45% weight)
| Criterion | Weight | Ideal | Acceptable | Reference |
|-----------|--------|-------|------------|-----------|
| Price Range | 4% | $3-10 | $1-50 | criteria/price_range.md |
| Magic Line Respect | 10% | >80% bounce rate | >60% | criteria/magic_line.md |
| Volume Surge | 5% | >2x avg | >1.5x | criteria/volume_surge.md |
| Volume Dry-up | 5% | <0.5x in base | <0.7x | criteria/volume_dryup.md |
| Near 52w High | 4% | Within 10% | Within 25% | criteria/52w_high.md |
| Relative Strength | 5% | RS > 1.5 | RS > 1.0 | criteria/relative_strength.md |
| Orderly Pullback | 4% | 15-25% pullback | 10-35% | criteria/pullback.md |
| Pattern Detected | 4% | Cup & handle | Any base | criteria/patterns.md |
| Distance from ML | 4% | <5% above | <15% above | criteria/ml_distance.md |

### Fundamental Criteria (30% weight)
| Criterion | Weight | Ideal | Acceptable | Reference |
|-----------|--------|-------|------------|-----------|
| Small Float | 6% | <30M shares | <100M | criteria/float.md |
| EPS Growth | 6% | >50% YoY | >20% | criteria/eps_growth.md |
| Revenue Growth | 5% | >30% YoY | >15% | criteria/revenue_growth.md |
| PEG Ratio | 4% | <0.5 | <1.5 | criteria/peg.md |
| Low Debt | 3% | D/E < 0.3 | D/E < 1.0 | criteria/debt.md |
| Adequate Cash | 3% | CR > 2.0 | CR > 1.0 | criteria/cash.md |
| Low Analyst Coverage | 3% | 0-2 analysts | <5 | criteria/analysts.md |

### Insider/Sentiment (25% weight)
| Criterion | Weight | Ideal | Acceptable | Reference |
|-----------|--------|-------|------------|-----------|
| Insider Buying | 10% | Cluster buys | Any buys | criteria/insider_buying.md |
| No Options | 2% | No options | - | criteria/options.md |
| Market Conditions | 8% | SPY>50MA, VIX<20 | Neutral | criteria/market.md |
| Earnings Surprise | 5% | Beat streak | Recent beat | criteria/earnings.md |

## Scoring
- Each criterion scored 0-100
- Weighted by percentages above
- Composite = sum(criterion_score * weight)
- Grade: A (80+), B (65-79), C (50-64), D (35-49), F (<35)

## Entry Signals
When composite score > 70 AND any of:
- Price touching Magic Line (low risk entry)
- Breakout on 2x+ volume (momentum entry)
- 15-25% pullback in uptrend (buy the dip)

## Risk Management
- Position size: Never >5% of portfolio
- Stop loss: 7-8% below entry OR below Magic Line
- Take profits: Scale out at 50%, 100%, 200% gains
```

**Individual Criterion File:**
```markdown
# skills/superstock/criteria/magic_line.md

---
criterion: magic_line_respect
weight: 0.10
category: technical
---

# Magic Line Respect

## Definition
The "Magic Line" is the moving average that a stock most consistently
respects as support. For most stocks this is the 10-week (50-day) SMA,
but some stocks respect 8, 12, or 14 week periods.

## Detection Algorithm
1. Test 8, 10, 12, 14 week SMAs
2. For each, count "bounces" (price touches MA and reverses up)
3. Calculate respect rate = bounces / touches
4. Select period with highest respect rate

## Scoring
| Respect Rate | Bounces | Score |
|--------------|---------|-------|
| >90% | 5+ | 100 |
| 80-90% | 4+ | 90 |
| 70-80% | 3+ | 75 |
| 60-70% | 2+ | 60 |
| 50-60% | 1+ | 40 |
| <50% | any | 20 |

## Why It Matters
Stocks that respect their Magic Line show institutional accumulation.
The MA acts as support because large buyers step in at that level.

## Entry Signal
When price touches Magic Line with:
- RSI oversold (<40)
- Volume declining into touch
- No negative news catalyst

This is a LOW RISK entry point.

## Reference
Jesse Stine, "Insider Buy Superstocks", Chapter 4
```

**Profile Configuration:**
```yaml
# skills/superstock/profiles/default.yaml

name: default
description: Balanced approach for most users

# Minimum thresholds
min_score: 50
min_criteria_met: 8

# Weight adjustments (multipliers on base weights)
weight_adjustments:
  insider_buying: 1.0
  magic_line_respect: 1.0
  volume_surge: 1.0

# Universe filters
universe:
  min_price: 1.0
  max_price: 100.0
  min_volume: 50000
  min_market_cap: 50000000  # $50M

# Risk parameters
risk:
  max_position_pct: 5.0
  default_stop_loss_pct: 8.0
```

### Skill Loader

```python
# app/services/skill_loader.py

import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class CriterionConfig:
    name: str
    weight: float
    category: str
    scoring_table: Dict

@dataclass
class SkillConfig:
    name: str
    version: str
    criteria: List[CriterionConfig]
    profiles: Dict[str, Dict]

class SkillLoader:
    def __init__(self, skills_dir: Path = Path("skills")):
        self.skills_dir = skills_dir

    def load_skill(self, skill_name: str) -> SkillConfig:
        """Load a skill and all its criteria"""
        skill_path = self.skills_dir / skill_name

        # Parse main SKILL.md
        main_config = self._parse_skill_md(skill_path / "SKILL.md")

        # Load criteria definitions
        criteria = []
        criteria_dir = skill_path / "criteria"
        if criteria_dir.exists():
            for md_file in criteria_dir.glob("*.md"):
                criterion = self._parse_criterion_md(md_file)
                criteria.append(criterion)

        # Load profiles
        profiles = {}
        profiles_dir = skill_path / "profiles"
        if profiles_dir.exists():
            for yaml_file in profiles_dir.glob("*.yaml"):
                profile = yaml.safe_load(yaml_file.read_text())
                profiles[profile['name']] = profile

        return SkillConfig(
            name=main_config['name'],
            version=main_config['version'],
            criteria=criteria,
            profiles=profiles,
        )
```

### Benefits
1. **Readable** - Anyone can understand the methodology by reading markdown
2. **Editable** - Change weights/thresholds without code changes
3. **Extensible** - Add new strategies as new skill folders
4. **Customizable** - Users can override with their own profiles
5. **Documented** - Each criterion explains WHY it matters

### Files to Create
- `skills/superstock/SKILL.md`
- `skills/superstock/criteria/*.md` (19 files)
- `skills/superstock/profiles/*.yaml`
- `backend/app/services/skill_loader.py`

---

## Phase 4: Domain-Specific Evaluation

### Problem
No automated way to verify screening accuracy. How do we know:
- The Magic Line calculation is correct?
- Insider data is being parsed properly?
- Scores correlate with actual stock performance?

### Solution
Build evaluation datasets and automated tests.

### Implementation

**Test Categories:**

1. **Known Superstocks Test Set**
```python
# tests/evals/known_superstocks.py

KNOWN_SUPERSTOCKS = [
    # Stocks that made 100%+ moves after meeting criteria
    {"symbol": "NVDA", "date": "2023-01-15", "expected_score": ">70"},
    {"symbol": "SMCI", "date": "2023-06-01", "expected_score": ">75"},
    # Add 50+ historical examples
]

def test_known_superstocks_score_high():
    """Verify known winners would have scored well"""
    for case in KNOWN_SUPERSTOCKS:
        score = backtest_screen(case["symbol"], case["date"])
        assert score >= int(case["expected_score"].replace(">", ""))
```

2. **Magic Line Accuracy**
```python
# tests/evals/magic_line_evals.py

MAGIC_LINE_TEST_CASES = [
    {
        "symbol": "AAPL",
        "expected_period": 10,  # 10-week MA
        "expected_bounces": 4,
    },
    # 100+ test cases with manually verified values
]

def test_magic_line_detection():
    """Verify Magic Line detection matches manual analysis"""
    for case in MAGIC_LINE_TEST_CASES:
        result = detect_magic_line(case["symbol"])
        assert result.period == case["expected_period"]
        assert result.bounces >= case["expected_bounces"] - 1  # Allow ±1
```

3. **Insider Parsing Accuracy**
```python
# tests/evals/insider_parsing.py

INSIDER_TEST_CASES = [
    {
        "symbol": "AAPL",
        "date_range": ("2024-01-01", "2024-03-31"),
        "expected_buys": 5,
        "expected_total_value": 1500000,  # $1.5M ± 10%
    },
]

def test_insider_parsing():
    """Verify insider data matches SEC filings"""
    for case in INSIDER_TEST_CASES:
        insider = fetch_insider_activity(case["symbol"], case["date_range"])
        assert abs(insider.total_value - case["expected_total_value"]) < 0.1 * case["expected_total_value"]
```

4. **Backtesting Framework**
```python
# tests/evals/backtest.py

def backtest_strategy(
    start_date: date,
    end_date: date,
    min_score: float = 70,
) -> BacktestResult:
    """
    Run screening on historical data and measure returns
    """
    portfolio_returns = []

    for month in months_between(start_date, end_date):
        # Screen stocks as of month start
        candidates = screen_stocks_historical(month, min_score)

        # Track 3-month forward returns
        for stock in candidates[:10]:  # Top 10
            returns = calculate_forward_returns(stock, month, months=3)
            portfolio_returns.append(returns)

    return BacktestResult(
        total_return=sum(portfolio_returns) / len(portfolio_returns),
        win_rate=len([r for r in portfolio_returns if r > 0]) / len(portfolio_returns),
        avg_winner=mean([r for r in portfolio_returns if r > 0]),
        avg_loser=mean([r for r in portfolio_returns if r < 0]),
    )
```

### Files to Create
- `tests/evals/known_superstocks.py`
- `tests/evals/magic_line_evals.py`
- `tests/evals/insider_parsing.py`
- `tests/evals/backtest.py`
- `tests/fixtures/` - Test data files

---

## Phase 5: Production Monitoring

### Implementation

```python
# app/core/monitoring.py

import logging
import time
from functools import wraps
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ScanMetrics:
    scan_id: str
    mode: str
    start_time: float
    end_time: float
    stocks_scanned: int
    stocks_scored: int
    errors: List[str]

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def success_rate(self) -> float:
        return self.stocks_scored / self.stocks_scanned if self.stocks_scanned > 0 else 0

class ScanMonitor:
    """Track scanning metrics for monitoring"""

    def __init__(self):
        self.metrics: Dict[str, ScanMetrics] = {}

    def start_scan(self, scan_id: str, mode: str) -> None:
        self.metrics[scan_id] = ScanMetrics(
            scan_id=scan_id,
            mode=mode,
            start_time=time.time(),
            end_time=0,
            stocks_scanned=0,
            stocks_scored=0,
            errors=[],
        )

    def record_stock(self, scan_id: str, scored: bool, error: str = None) -> None:
        m = self.metrics[scan_id]
        m.stocks_scanned += 1
        if scored:
            m.stocks_scored += 1
        if error:
            m.errors.append(error)

    def end_scan(self, scan_id: str) -> ScanMetrics:
        m = self.metrics[scan_id]
        m.end_time = time.time()

        # Log summary
        logging.info(
            f"Scan {scan_id} complete: {m.stocks_scored}/{m.stocks_scanned} scored "
            f"in {m.duration_seconds:.1f}s ({m.success_rate:.1%} success)"
        )

        # Alert on high error rate
        if m.success_rate < 0.5:
            logging.warning(f"Scan {scan_id} had low success rate: {m.success_rate:.1%}")

        return m
```

---

## Implementation Order

### Week 1: Real-Time Streaming
- Add SSE endpoint to backend
- Update frontend to consume stream
- Show progressive results

### Week 2: Context Normalization
- Create StockContext dataclass
- Build ContextBuilder service
- Refactor screener to use context

### Week 3-4: Skills System
- Create skill markdown files
- Build skill loader
- Refactor screener to use skill configs

### Week 5: Evaluation
- Build test datasets
- Create eval scripts
- Set up CI to run evals

### Week 6: Monitoring & Polish
- Add metrics tracking
- Improve error handling
- Performance optimization

---

## Success Metrics

1. **UX**: Scan feels responsive (streaming shows progress)
2. **Accuracy**: Known Superstocks score >70 in backtests
3. **Maintainability**: Non-engineers can modify skill weights
4. **Reliability**: <5% error rate on scans
5. **Performance**: Quick scan <30s, Standard <2min
