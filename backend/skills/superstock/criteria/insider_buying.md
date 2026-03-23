# Insider Buying Criterion

## Weight: 10%

## Description
Insider buying is one of the strongest predictors of future stock performance. Corporate insiders (CEOs, CFOs, directors) have unique knowledge about their company's prospects. When they buy with their own money, it signals confidence.

## Data Sources
- **Primary**: OpenInsider (aggregated, fast)
- **Secondary**: SEC EDGAR Form 4 filings (authoritative, slower)

## Key Metrics

### 1. Cluster Buys
Multiple insiders buying within 90 days is highly significant:
```python
is_cluster = unique_buyers_90d >= 3
```

### 2. Executive Purchases
CEO/CFO purchases carry more weight than director purchases:
```python
executive_bonus = 20 if (ceo_bought or cfo_bought) else 0
```

### 3. Net Dollar Value
Buy value minus sell value over 90 days:
```python
net_value = total_buys_90d - total_sells_90d
```

### 4. Recency
More recent buys are more relevant:
```python
recency_score = max(0, 100 - days_since_last_buy * 2)
```

## Scoring

| Condition | Score |
|-----------|-------|
| Cluster buy (3+ insiders), net value >$1M | 100 |
| Cluster buy, any positive net value | 90 |
| CEO or CFO bought >$100K | 80 |
| 2+ insiders bought in 90 days | 70 |
| 1 insider bought >$50K | 50 |
| Small insider buys (<$50K) | 30 |
| No buying activity | 0 |
| Net selling | 0 |

## Red Flags
- Heavy selling by multiple insiders = negative signal
- Selling into price strength = potential top
- Routine sales (10b5-1 plans) are less meaningful

## Examples

### Strong Signal (Score: 100)
- CEO bought $500K at $15/share
- CFO bought $200K same week
- 2 directors bought $50K each
- Total: 4 unique buyers, $800K net buys

### Moderate Signal (Score: 50)
- One director bought $75K
- No other activity

### Neutral (Score: 0)
- No insider transactions in 90 days
- OR: Net selling activity

## Integration
```python
from services.openinsider import get_insider_data

insider = get_insider_data(symbol)
score = calculate_insider_score(insider)
is_cluster = insider.unique_buyers_90d >= 3
sentiment = insider.sentiment  # "very_bullish", "bullish", "neutral", "bearish"
```
