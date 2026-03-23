"""
Stock Context Models

Normalized data structures that combine data from multiple sources
(Finviz, yfinance, OpenInsider) into a unified format for screening.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, List, Any


@dataclass
class NormalizedFinancials:
    """
    Normalized financial metrics - all in consistent units.

    Monetary values: Always in millions USD
    Growth rates: Always as decimals (0.15 = 15%)
    Ratios: Raw numbers
    """
    # Revenue
    revenue_ttm: Optional[float] = None  # millions USD
    revenue_growth_yoy: Optional[float] = None  # decimal

    # Earnings
    eps_ttm: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    eps_growth_next_y: Optional[float] = None

    # Valuation
    market_cap: Optional[float] = None  # millions USD
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None

    # Balance sheet
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

    # Shares
    shares_outstanding: Optional[float] = None  # millions
    float_shares: Optional[float] = None  # millions
    short_float_pct: Optional[float] = None  # decimal

    # Analyst coverage
    analyst_count: Optional[int] = None
    target_price: Optional[float] = None

    @property
    def has_growth(self) -> bool:
        """Check if we have growth data"""
        return self.eps_growth_yoy is not None or self.revenue_growth_yoy is not None

    @property
    def is_undervalued(self) -> bool:
        """Simple undervaluation check based on PEG"""
        if self.peg_ratio is not None:
            return self.peg_ratio < 1.0
        return False


@dataclass
class NormalizedTechnicals:
    """
    Normalized technical data calculated from price history.

    All prices in USD, volumes in shares, percentages as decimals.
    """
    # Current state
    price: float
    volume: int
    avg_volume_20d: int
    relative_volume: float  # current / avg (1.5 = 50% above average)

    # Moving averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None

    # Position relative to MAs
    above_sma_20: bool = False
    above_sma_50: bool = False
    above_sma_200: bool = False

    # Distance from MAs (as decimal, 0.05 = 5% above)
    distance_from_sma_20: Optional[float] = None
    distance_from_sma_50: Optional[float] = None
    distance_from_sma_200: Optional[float] = None

    # 52-week range
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    pct_from_52w_high: Optional[float] = None  # negative = below high
    pct_from_52w_low: Optional[float] = None  # positive = above low

    # Magic Line (Jesse Stine's key indicator)
    magic_line_period: Optional[int] = None  # weeks (8, 10, 12, or 14)
    magic_line_value: Optional[float] = None
    magic_line_distance_pct: Optional[float] = None
    magic_line_bounces: int = 0
    magic_line_respect_rate: Optional[float] = None

    # Volatility
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None  # ATR as % of price

    # RSI
    rsi_14: Optional[float] = None

    # Volume analysis
    volume_dryup_ratio: Optional[float] = None  # <0.5 = significant dry-up
    volume_surge_ratio: Optional[float] = None  # >2.0 = significant surge

    # Price change
    change_1d_pct: Optional[float] = None
    change_5d_pct: Optional[float] = None
    change_20d_pct: Optional[float] = None

    @property
    def is_near_magic_line(self) -> bool:
        """Check if price is near Magic Line (within 5%)"""
        if self.magic_line_distance_pct is not None:
            return abs(self.magic_line_distance_pct) < 0.05
        return False

    @property
    def is_in_uptrend(self) -> bool:
        """Simple uptrend check: above 50 and 200 MA"""
        return self.above_sma_50 and self.above_sma_200

    @property
    def is_near_52w_high(self) -> bool:
        """Within 25% of 52-week high"""
        if self.pct_from_52w_high is not None:
            return self.pct_from_52w_high > -0.25
        return False


@dataclass
class NormalizedInsider:
    """
    Normalized insider activity aggregated from transaction data.
    """
    # Summary
    has_recent_buys: bool = False
    buy_count_90d: int = 0
    sell_count_90d: int = 0
    total_buy_value_90d: float = 0.0  # USD
    total_sell_value_90d: float = 0.0  # USD
    net_value_90d: float = 0.0  # buys - sells

    # Cluster detection
    is_cluster_buy: bool = False  # Multiple insiders buying
    unique_buyers_90d: int = 0

    # Timing
    most_recent_buy_date: Optional[date] = None
    most_recent_sell_date: Optional[date] = None
    days_since_last_buy: Optional[int] = None

    # Notable insiders
    insider_names: List[str] = field(default_factory=list)
    ceo_bought: bool = False
    cfo_bought: bool = False

    @property
    def insider_sentiment(self) -> str:
        """Classify insider sentiment"""
        if self.is_cluster_buy:
            return "very_bullish"
        if self.net_value_90d > 1_000_000:
            return "bullish"
        if self.net_value_90d > 0:
            return "slightly_bullish"
        if self.net_value_90d < -1_000_000:
            return "bearish"
        return "neutral"

    @property
    def has_significant_buying(self) -> bool:
        """Check for significant insider buying"""
        return self.total_buy_value_90d > 100_000 or self.buy_count_90d >= 3


@dataclass
class NormalizedPatterns:
    """
    Detected chart patterns from price history.
    """
    # Pattern flags
    has_cup_and_handle: bool = False
    has_flat_base: bool = False
    has_ascending_base: bool = False
    has_double_bottom: bool = False
    has_breakout: bool = False

    # Pattern details
    patterns_detected: List[str] = field(default_factory=list)
    pattern_quality_score: float = 0.0  # 0-100
    base_length_days: Optional[int] = None
    base_depth_pct: Optional[float] = None

    # Breakout info
    breakout_level: Optional[float] = None
    is_above_breakout: bool = False

    @property
    def has_any_pattern(self) -> bool:
        return len(self.patterns_detected) > 0


@dataclass
class StockContext:
    """
    Complete normalized context for a stock.

    This is the single source of truth that the screener uses.
    All data from various sources is normalized and merged here.
    """
    # Identity
    symbol: str
    company_name: str
    sector: str
    industry: str

    # Data quality
    data_timestamp: datetime = field(default_factory=datetime.utcnow)
    data_freshness: date = field(default_factory=date.today)
    confidence_score: float = 0.0  # 0-1 based on data completeness

    # Normalized data components
    financials: NormalizedFinancials = field(default_factory=NormalizedFinancials)
    technicals: NormalizedTechnicals = field(default_factory=lambda: NormalizedTechnicals(price=0, volume=0, avg_volume_20d=0, relative_volume=0))
    insider: NormalizedInsider = field(default_factory=NormalizedInsider)
    patterns: NormalizedPatterns = field(default_factory=NormalizedPatterns)

    # Raw data references (for debugging/auditing)
    _source_finviz: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _source_yfinance: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _source_openinsider: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def is_complete(self) -> bool:
        """Check if we have all essential data"""
        return (
            self.technicals.price > 0 and
            self.technicals.avg_volume_20d > 0 and
            self.confidence_score > 0.5
        )

    @property
    def quick_summary(self) -> str:
        """One-line summary of the stock"""
        trend = "uptrend" if self.technicals.is_in_uptrend else "downtrend"
        insider = self.insider.insider_sentiment
        return f"{self.symbol}: ${self.technicals.price:.2f}, {trend}, insider: {insider}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "sector": self.sector,
            "industry": self.industry,
            "data_timestamp": self.data_timestamp.isoformat(),
            "confidence_score": self.confidence_score,
            "financials": {
                "market_cap": self.financials.market_cap,
                "pe_ratio": self.financials.pe_ratio,
                "peg_ratio": self.financials.peg_ratio,
                "eps_growth_yoy": self.financials.eps_growth_yoy,
                "revenue_growth_yoy": self.financials.revenue_growth_yoy,
                "float_shares": self.financials.float_shares,
                "analyst_count": self.financials.analyst_count,
            },
            "technicals": {
                "price": self.technicals.price,
                "volume": self.technicals.volume,
                "relative_volume": self.technicals.relative_volume,
                "magic_line_period": self.technicals.magic_line_period,
                "magic_line_distance_pct": self.technicals.magic_line_distance_pct,
                "pct_from_52w_high": self.technicals.pct_from_52w_high,
                "is_in_uptrend": self.technicals.is_in_uptrend,
            },
            "insider": {
                "has_recent_buys": self.insider.has_recent_buys,
                "buy_count_90d": self.insider.buy_count_90d,
                "total_buy_value_90d": self.insider.total_buy_value_90d,
                "is_cluster_buy": self.insider.is_cluster_buy,
                "sentiment": self.insider.insider_sentiment,
            },
            "patterns": {
                "patterns_detected": self.patterns.patterns_detected,
                "has_breakout": self.patterns.has_breakout,
            },
        }
