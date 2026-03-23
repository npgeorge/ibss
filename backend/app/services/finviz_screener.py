"""
Finviz Pre-Filter Service

Fetches stock universe from Finviz with LIGHT pre-filters to reduce
the scanning universe from 5000+ stocks to ~200-500 candidates.

Uses the finvizfinance library for reliable data fetching.

Supports three scan modes:
- Quick: ~200-500 stocks, aggressive filters
- Standard: ~500-1000 stocks, balanced filters
- Deep: ~1000-2000 stocks, minimal filters
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.valuation import Valuation

logger = logging.getLogger(__name__)


class ScanMode(str, Enum):
    """Scanning mode determines filter strictness and universe size"""
    QUICK = "quick"       # <30 sec, ~200-500 stocks
    STANDARD = "standard" # <2 min, ~500-1000 stocks
    DEEP = "deep"         # <5 min, ~1000-2000 stocks


@dataclass
class StockMetrics:
    """Enriched stock data from Finviz"""
    symbol: str
    company: str
    sector: str
    industry: str
    country: str
    market_cap: float  # in millions
    price: float
    change: float  # percent change
    volume: int
    avg_volume: int
    relative_volume: float

    # Float and shares
    float_shares: Optional[float] = None  # in millions
    shares_outstanding: Optional[float] = None
    short_float: Optional[float] = None  # percent

    # Analyst data
    analyst_count: Optional[int] = None
    target_price: Optional[float] = None

    # Fundamentals
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    eps_ttm: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    eps_growth_next_y: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None

    # Balance sheet
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

    # Technical
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi_14: Optional[float] = None

    # Options
    has_options: bool = True  # Default to True, will be detected

    # Calculated fields
    distance_from_52w_high: Optional[float] = None

    def __post_init__(self):
        """Calculate derived metrics"""
        if self.week_52_high and self.price:
            self.distance_from_52w_high = (self.week_52_high - self.price) / self.week_52_high * 100


@dataclass
class PreFilterResult:
    """Result of Finviz pre-filtering"""
    symbols: List[str]
    metrics: Dict[str, StockMetrics]
    mode: ScanMode
    universe_size: int
    filtered_size: int
    filter_time_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class FinvizPreFilter:
    """
    Finviz-based pre-filter to reduce stock universe

    Uses finvizfinance library for reliable data fetching.
    """

    # Filter parameters by scan mode
    # Valid Price options: Under $1/$2/$3/$4/$5/$7/$10/$15/$20/$30/$40/$50, Over $X, $X to $Y
    # Keep filters tight to avoid fetching thousands of pages
    # Valid Finviz price filter options:
    # '$1 to $5', '$1 to $10', '$1 to $20', '$5 to $10', '$5 to $20', '$5 to $50',
    # '$10 to $20', '$10 to $50', '$20 to $50', '$50 to $100'
    MODE_FILTERS = {
        ScanMode.QUICK: {
            'Market Cap.': 'Small ($300mln to $2bln)',
            'Price': '$5 to $50',
            'Average Volume': 'Over 200K',
        },
        ScanMode.STANDARD: {
            'Market Cap.': '+Micro (over $50mln)',
            'Price': '$1 to $20',
            'Average Volume': 'Over 100K',
        },
        ScanMode.DEEP: {
            'Market Cap.': '+Micro (over $50mln)',
            'Price': '$1 to $20',
            'Average Volume': 'Over 50K',
        },
    }

    # Limit pages to control scan time
    MODE_PAGE_LIMITS = {
        ScanMode.QUICK: 25,     # ~500 stocks max
        ScanMode.STANDARD: 50,  # ~1000 stocks max
        ScanMode.DEEP: 100,     # ~2000 stocks max
    }

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def get_prefiltered_symbols(
        self,
        mode: ScanMode = ScanMode.STANDARD
    ) -> PreFilterResult:
        """
        Get pre-filtered stock symbols from Finviz

        Args:
            mode: Scan mode determining filter strictness

        Returns:
            PreFilterResult with symbols and enriched metrics
        """
        start_time = datetime.utcnow()

        try:
            # Run the synchronous finvizfinance call in a thread pool
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                self._executor,
                self._fetch_screener_data,
                mode
            )

            # Parse and enrich data
            metrics = {}
            symbols = []

            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    try:
                        stock = self._parse_dataframe_row(row)
                        if stock:
                            symbols.append(stock.symbol)
                            metrics[stock.symbol] = stock
                    except Exception as e:
                        logger.debug(f"Error parsing stock row: {e}")
                        continue

            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

            logger.info(
                f"Finviz pre-filter ({mode.value}): "
                f"{len(symbols)} stocks in {elapsed:.0f}ms"
            )

            return PreFilterResult(
                symbols=symbols,
                metrics=metrics,
                mode=mode,
                universe_size=len(df) if df is not None else 0,
                filtered_size=len(symbols),
                filter_time_ms=elapsed,
            )

        except Exception as e:
            logger.error(f"Error in Finviz pre-filter: {e}")
            # Return empty result on error
            return PreFilterResult(
                symbols=[],
                metrics={},
                mode=mode,
                universe_size=0,
                filtered_size=0,
                filter_time_ms=0,
            )

    def _fetch_screener_data(self, mode: ScanMode) -> Optional[pd.DataFrame]:
        """Fetch screener data using finvizfinance (synchronous)"""
        try:
            foverview = Overview()
            filters = self.MODE_FILTERS.get(mode, {})

            if filters:
                foverview.set_filter(filters_dict=filters)

            # Fetch overview data — try with verbose param, fall back without
            try:
                df = foverview.screener_view(verbose=0)
            except TypeError:
                df = foverview.screener_view()

            if df is None or df.empty:
                return df

            logger.info(f"Finviz overview returned {len(df)} rows, columns: {list(df.columns)}")

            # Also fetch valuation view for PEG, EPS growth, sales growth
            try:
                fvaluation = Valuation()
                if filters:
                    fvaluation.set_filter(filters_dict=filters)
                try:
                    val_df = fvaluation.screener_view(verbose=0)
                except TypeError:
                    val_df = fvaluation.screener_view()

                if val_df is not None and not val_df.empty:
                    logger.info(f"Finviz valuation returned {len(val_df)} rows, columns: {list(val_df.columns)}")
                    # Merge on Ticker, keeping all overview rows
                    # Only merge columns not already in overview
                    val_cols = [c for c in val_df.columns if c not in df.columns or c == 'Ticker']
                    if val_cols:
                        df = df.merge(val_df[val_cols], on='Ticker', how='left')
            except Exception as e:
                logger.warning(f"Valuation view fetch failed (non-fatal): {e}")

            return df

        except Exception as e:
            logger.error(f"Error fetching Finviz data: {e}")
            return None

    def _parse_dataframe_row(self, row: pd.Series) -> Optional[StockMetrics]:
        """Parse a DataFrame row into StockMetrics"""
        try:
            symbol = str(row.get('Ticker', '')).upper()
            if not symbol:
                return None

            # Parse PEG from valuation view (column name: "PEG")
            peg_ratio = self._parse_float(row.get('PEG'))

            # Parse EPS growth — valuation view has "EPS this Y" or "EPS next Y"
            eps_growth = (
                self._parse_float(row.get('EPS this Y'))
                or self._parse_float(row.get('EPS next Y'))
                or self._parse_float(row.get('EPS past 5Y'))
            )

            # Parse revenue/sales growth — valuation view has "Sales past 5Y"
            revenue_growth = self._parse_float(row.get('Sales past 5Y'))

            return StockMetrics(
                symbol=symbol,
                company=str(row.get('Company', '')),
                sector=str(row.get('Sector', '')),
                industry=str(row.get('Industry', '')),
                country=str(row.get('Country', 'USA')),
                market_cap=self._parse_market_cap(row.get('Market Cap', '')),
                price=self._parse_float(row.get('Price', 0)) or 0.0,
                change=self._parse_percent(row.get('Change', '')),
                volume=self._parse_volume(row.get('Volume', 0)),
                avg_volume=0,  # Not available in overview
                relative_volume=1.0,
                pe_ratio=self._parse_float(row.get('P/E')),
                peg_ratio=peg_ratio,
                eps_growth_yoy=eps_growth,
                revenue_growth_yoy=revenue_growth,
            )
        except Exception as e:
            logger.debug(f"Error parsing stock row: {e}")
            return None

    @staticmethod
    def _parse_market_cap(value) -> float:
        """Parse market cap string (e.g., '1.5B', '500M') to millions"""
        if pd.isna(value) or value == '-' or value == '':
            return 0.0

        value = str(value).strip().upper()
        multiplier = 1.0

        if value.endswith("B"):
            multiplier = 1000
            value = value[:-1]
        elif value.endswith("M"):
            multiplier = 1
            value = value[:-1]
        elif value.endswith("K"):
            multiplier = 0.001
            value = value[:-1]

        try:
            return float(value.replace(',', '')) * multiplier
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_float(value) -> Optional[float]:
        """Parse float value, return None if invalid"""
        if pd.isna(value) or value == '-' or value == '':
            return None
        try:
            if isinstance(value, (int, float)):
                return float(value)
            return float(str(value).replace(",", "").replace("%", ""))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_percent(value) -> float:
        """Parse percent string to float"""
        if pd.isna(value) or value == '-' or value == '':
            return 0.0
        try:
            if isinstance(value, (int, float)):
                return float(value)
            return float(str(value).replace(",", "").replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _parse_volume(value) -> int:
        """Parse volume string to int"""
        if pd.isna(value) or value == '-' or value == '':
            return 0
        try:
            if isinstance(value, (int, float)):
                return int(value)
            return int(str(value).replace(",", ""))
        except (ValueError, TypeError):
            return 0


class FinvizDetailFetcher:
    """
    Fetch detailed stock data from Finviz quote pages

    Used to enrich pre-filtered stocks with additional metrics
    not available in the screener view.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def fetch_stock_details(
        self,
        symbols: List[str],
        batch_size: int = 10,
    ) -> Dict[str, StockMetrics]:
        """
        Fetch detailed metrics for a list of symbols

        Args:
            symbols: List of stock symbols
            batch_size: Number of concurrent requests

        Returns:
            Dict mapping symbol to StockMetrics
        """
        # For now, return empty dict - detailed fetching is optional
        # The screener overview provides enough basic data
        return {}


async def get_prefiltered_symbols(
    mode: ScanMode = ScanMode.STANDARD
) -> PreFilterResult:
    """
    Convenience function to get pre-filtered symbols

    Args:
        mode: Scan mode (quick, standard, deep)

    Returns:
        PreFilterResult with symbols and metrics
    """
    prefilter = FinvizPreFilter()
    return await prefilter.get_prefiltered_symbols(mode)


async def get_stock_metrics(
    symbols: List[str],
    batch_size: int = 10
) -> Dict[str, StockMetrics]:
    """
    Convenience function to get detailed stock metrics

    Args:
        symbols: List of stock symbols
        batch_size: Batch size for concurrent requests

    Returns:
        Dict mapping symbol to StockMetrics
    """
    fetcher = FinvizDetailFetcher()
    return await fetcher.fetch_stock_details(symbols, batch_size)
