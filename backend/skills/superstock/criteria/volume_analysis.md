# Volume Analysis Criterion

## Weight: 12% (6% dry-up + 6% surge)

## Description
Volume tells the story of supply and demand. Superstocks exhibit a specific volume signature: decreasing volume during consolidation (accumulation), followed by volume surge on breakout.

## Key Patterns

### 1. Volume Dry-Up (Weight: 6%)
During base formation, volume should decrease significantly. This indicates:
- Weak hands have sold
- Supply is exhausted
- Smart money is quietly accumulating

**Detection**:
```python
avg_vol_early = volume[-20:-10].mean()  # First half of base
avg_vol_late = volume[-5:].mean()        # Recent
dryup_ratio = avg_vol_late / avg_vol_early

# <0.5 = significant dry-up (bullish)
# 0.5-0.7 = moderate dry-up
# >0.7 = no dry-up
```

### 2. Volume Surge (Weight: 6%)
On breakout days, volume should spike:
```python
relative_volume = current_volume / avg_volume_20d

# >3.0 = exceptional surge
# 2.0-3.0 = strong surge
# 1.5-2.0 = moderate surge
# <1.5 = no surge
```

### 3. Up/Down Volume Ratio
Healthy accumulation shows:
- High volume on up days
- Low volume on down days

```python
up_day_vol = sum(volume where close > open)
down_day_vol = sum(volume where close < open)
ratio = up_day_vol / down_day_vol

# >1.5 = bullish accumulation
```

## Scoring

### Volume Dry-Up Score
| Dry-Up Ratio | Score |
|--------------|-------|
| <0.4 | 100 |
| 0.4-0.5 | 85 |
| 0.5-0.6 | 70 |
| 0.6-0.7 | 50 |
| >0.7 | 20 |

### Volume Surge Score
| Relative Volume | Score |
|-----------------|-------|
| >3.0 | 100 |
| 2.5-3.0 | 90 |
| 2.0-2.5 | 80 |
| 1.5-2.0 | 60 |
| 1.2-1.5 | 40 |
| <1.2 | 0 |

## Entry Signals
- **Breakout Signal**: Price breaks resistance on 2x+ volume
- **Accumulation Signal**: 3+ weeks of volume dry-up in tight base

## Examples

### Ideal Volume Pattern (Combined Score: 100)
- 6-week base with volume declining 60%
- Tight price range (3% consolidation)
- Breakout day: 3.5x average volume
- Price up 8% on breakout

### No Signal (Combined Score: 0)
- Volume constant or increasing during consolidation
- Breakout on below-average volume

## Integration
```python
from services.volume_analysis import analyze_volume

analysis = analyze_volume(price_data)
dryup_score = analysis.dryup_score
surge_score = analysis.surge_score
is_accumulating = analysis.is_accumulating
breakout_volume = analysis.current_relative_volume > 2.0
```
