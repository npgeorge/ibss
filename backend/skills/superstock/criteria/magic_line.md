# Magic Line Criterion

## Weight: 12%

## Description
The Magic Line is Jesse Stine's primary technical indicator - a weekly moving average (8, 10, 12, or 14 periods) that acts as dynamic support for Superstocks during their uptrend. True Superstocks will "respect" this line multiple times, bouncing off it before continuing higher.

## Calculation

### 1. Find Optimal Period
For each candidate period (8, 10, 12, 14 weeks):
```python
for period in [8, 10, 12, 14]:
    wma = calculate_weekly_ma(weekly_prices, period)
    respect_rate = count_bounces(prices, wma) / total_touches
```

### 2. Detect Bounces
A "bounce" occurs when:
- Price approaches within 3% of the Magic Line
- Price doesn't close below the line (or quickly recovers)
- Price moves higher after the touch

### 3. Calculate Respect Rate
```
respect_rate = successful_bounces / total_approaches
```

## Scoring

| Condition | Score |
|-----------|-------|
| Respect rate ≥90%, 4+ bounces | 100 |
| Respect rate ≥80%, 3+ bounces | 90 |
| Respect rate ≥70%, 2+ bounces | 75 |
| Respect rate ≥60%, 1+ bounce | 50 |
| No clear Magic Line | 0 |

## Entry Signal
**Magic Line Touch**: When current price is within 5% of the identified Magic Line, this is a low-risk entry point.

## Examples

### Strong Magic Line (Score: 100)
- Stock XYZ has bounced off its 10-week MA 5 times in 12 months
- Each time, price recovered within 2 weeks
- Respect rate: 5/5 = 100%

### Weak Magic Line (Score: 25)
- Stock ABC touched its 12-week MA 4 times
- Only 2 resulted in bounces; 2 broke through
- Respect rate: 50%

## Integration
```python
from services.magic_line import calculate_magic_line

result = calculate_magic_line(price_data, min_bounces=2)
score = result.score  # 0-100
period = result.optimal_period  # e.g., 10
is_entry_signal = result.distance_pct < 0.05  # Within 5%
```
