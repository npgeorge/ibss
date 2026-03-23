# Superstock Screening Skill

## Overview
This skill implements Jesse Stine's Superstock methodology for identifying potential 100%+ return stocks before they break out. The methodology focuses on finding small-cap stocks with insider buying, strong technical setups near the "Magic Line", and favorable fundamental characteristics.

## Core Principles

### 1. The Magic Line
The Magic Line is a weekly moving average (8, 10, 12, or 14 weeks) that acts as support for Superstocks during their run. Stocks that respect this line multiple times show institutional accumulation.

- **Identification**: Test each period (8, 10, 12, 14 WMA) and use the one with highest "respect rate"
- **Respect**: Price bounces off the line within 3% tolerance
- **Entry Signal**: Price touching or within 5% of Magic Line = low-risk entry

### 2. Volume Signature
Superstocks exhibit a specific volume pattern:
- **Dry-up**: Volume decreases 40-60% during base formation (accumulation)
- **Surge**: Volume spikes 50-200% above average on breakout
- **Confirmation**: High volume on up days, low volume on down days

### 3. Insider Buying
Smart money knows before the market:
- **Cluster Buys**: Multiple insiders buying within 90 days = strong signal
- **CEO/CFO Buys**: Executive purchases carry more weight
- **Price Context**: Buying near highs = confidence; buying into weakness = bottom fishing

### 4. Technical Setup
Ideal entry conditions:
- Price within 25% of 52-week high (showing strength)
- Above 50 and 200 day moving averages (uptrend)
- Pullback of 15-25% from highs (buyable dip)
- Low ATR during consolidation (orderly, not volatile)

### 5. Fundamental Filters
Not hard requirements, but scoring factors:
- Small float (<50M shares) for explosive moves
- Low analyst coverage (<5) for undiscovered potential
- PEG ratio <1 for value relative to growth
- Earnings growth >20% YoY
- Low debt (D/E <0.5)

## Scoring System

Each stock receives a composite score (0-100) based on 19 criteria. Stocks are ranked by score, not hard-filtered. This prevents missing opportunities that fail 1-2 minor criteria but excel everywhere else.

### Score Interpretation
- **90-100 (A+)**: Textbook Superstock, immediate watchlist
- **80-89 (A)**: Strong candidate, monitor closely
- **70-79 (B)**: Good potential, needs catalyst
- **60-69 (C)**: Mixed signals, selective interest
- **<60 (D/F)**: Not currently a Superstock candidate

## Entry Signals

Beyond scoring, specific conditions trigger entry signals:
1. **Magic Line Touch**: Price at Magic Line support
2. **Pullback Entry**: 15-25% pullback in uptrend
3. **Breakout**: Breaking resistance on 2x+ volume
4. **Pattern Completion**: Cup & handle, flat base complete

## Market Conditions

Never buy into a falling market:
- SPY must be above 50-day MA
- VIX should be under 20
- If conditions unfavorable, reduce position sizes or wait

## Risk Management

- Never chase: Don't buy if price >20% above Magic Line
- Position sizing: Risk 1-2% of portfolio per trade
- Stop loss: Below Magic Line or recent swing low
- Take profits: Scale out at 50%, 100%, 200% gains
