# Float and Share Structure Criterion

## Weight: 8%

## Description
A small float (shares available for public trading) creates the conditions for explosive price moves. When demand exceeds the limited supply, prices can move dramatically. This is one of Jesse Stine's most important filters.

## Key Metrics

### 1. Float Size
```python
float_shares = shares_outstanding - insider_shares - institutional_locked
```

**Ideal ranges**:
- <20M shares: Extremely small, highly explosive potential
- 20-50M shares: Small, good potential
- 50-100M shares: Moderate, still tradeable
- >100M shares: Large, harder to move

### 2. Short Interest
High short interest can fuel a squeeze:
```python
short_float_pct = shares_shorted / float_shares
days_to_cover = shares_shorted / avg_daily_volume
```

### 3. Institutional Ownership
Some institutional ownership is good (validation), too much reduces float:
```python
inst_ownership_pct = institutional_shares / shares_outstanding
# Ideal: 20-60%
# Too low (<10%): No smart money interest
# Too high (>80%): Crowded, limited upside
```

## Scoring

### Float Size Score
| Float (millions) | Score |
|------------------|-------|
| <10 | 100 |
| 10-20 | 90 |
| 20-30 | 80 |
| 30-50 | 70 |
| 50-75 | 50 |
| 75-100 | 30 |
| >100 | 10 |

### Bonus: Short Squeeze Potential
| Short Float % | Bonus |
|---------------|-------|
| >30% | +15 |
| 20-30% | +10 |
| 15-20% | +5 |

### Bonus: Ideal Institutional Range
| Inst. Ownership | Bonus |
|-----------------|-------|
| 30-50% | +10 |
| 20-30% or 50-60% | +5 |
| <10% or >70% | 0 |

## Why Float Matters

### Example 1: Small Float ($1B company)
- Market cap: $1B
- Float: 15M shares
- Price: $66/share
- If fund wants to buy $10M = 150K shares = 1% of float
- Meaningful buying pressure, price moves up

### Example 2: Large Float ($1B company)
- Market cap: $1B
- Float: 200M shares
- Price: $5/share
- If fund wants to buy $10M = 2M shares = 1% of float
- Same pressure, but diluted across huge supply

## Data Sources
- **Finviz**: Float, short float %, institutional ownership
- **Yahoo Finance**: Shares outstanding, insider ownership

## Red Flags
- Float >200M: Too large for explosive moves
- Recent secondary offering: Dilution increases float
- Insider selling: May increase float, signals concern

## Integration
```python
from services.finviz_screener import get_stock_metrics

metrics = get_stock_metrics(symbol)
float_score = score_float(metrics.float_shares)
short_bonus = score_short_squeeze_potential(metrics.short_float_pct)
inst_bonus = score_institutional(metrics.institutional_ownership)

total_score = min(100, float_score + short_bonus + inst_bonus)
```
