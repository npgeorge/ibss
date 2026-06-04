"""
OpenInsider Integration Service

Replaces SEC EDGAR real-time calls with OpenInsider scraping for faster
insider data retrieval. Single HTTP request gets insider activity for
multiple stocks with 1-hour caching.

OpenInsider aggregates SEC Form 4 filings and provides pre-filtered
cluster buying information.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TransactionType(str, Enum):
    """Insider transaction types"""
    PURCHASE = "P"
    SALE = "S"
    OPTION_EXERCISE = "M"
    GIFT = "G"


@dataclass
class InsiderTransaction:
    """Single insider transaction"""
    filing_date: datetime
    trade_date: datetime
    symbol: str
    company: str
    insider_name: str
    insider_title: str
    transaction_type: TransactionType
    price: float
    quantity: int
    total_value: float
    shares_owned: int
    delta_owned: float  # Percent change in ownership

    # Classification
    is_cluster: bool = False

    @property
    def is_purchase(self) -> bool:
        return self.transaction_type == TransactionType.PURCHASE

    @property
    def is_significant(self) -> bool:
        """Check if transaction is significant (>$25k or >10% ownership change)"""
        return self.total_value >= 25000 or abs(self.delta_owned) >= 10


@dataclass
class InsiderActivitySummary:
    """Summary of insider activity for a stock"""
    symbol: str
    total_purchases: int
    total_sales: int
    net_shares: int  # Bought - sold
    net_value: float
    unique_buyers: int
    unique_sellers: int
    latest_purchase_date: Optional[datetime] = None
    latest_sale_date: Optional[datetime] = None
    has_cluster_buying: bool = False
    cluster_count: int = 0
    transactions: List[InsiderTransaction] = field(default_factory=list)

    @property
    def is_bullish(self) -> bool:
        """Check if insider activity is bullish"""
        return self.net_shares > 0 or self.unique_buyers > self.unique_sellers

    @property
    def buyer_conviction(self) -> float:
        """Calculate buyer conviction score (0-100)"""
        if self.unique_buyers == 0:
            return 0.0

        # Factors: cluster buying, number of buyers, recency
        score = 0.0

        # Cluster buying is huge
        if self.has_cluster_buying:
            score += 40

        # More buyers = more conviction
        score += min(self.unique_buyers * 15, 30)

        # Recent activity bonus
        if self.latest_purchase_date:
            days_ago = (datetime.utcnow() - self.latest_purchase_date).days
            if days_ago <= 7:
                score += 30
            elif days_ago <= 30:
                score += 20
            elif days_ago <= 60:
                score += 10

        return min(score, 100)


@dataclass
class ClusterBuyInfo:
    """Information about a cluster buying event"""
    symbol: str
    company: str
    num_insiders: int
    total_value: float
    avg_price: float
    start_date: datetime
    end_date: datetime
    insiders: List[str]
    transactions: List[InsiderTransaction]

    @property
    def is_strong_cluster(self) -> bool:
        """Check if this is a strong cluster (3+ insiders, >$100k)"""
        return self.num_insiders >= 3 and self.total_value >= 100000


class OpenInsiderScraper:
    """
    Scrape insider transaction data from OpenInsider

    OpenInsider provides pre-aggregated SEC Form 4 data with:
    - Recent cluster buys (multiple insiders buying within 30 days)
    - Large purchases and sales
    - CEO/CFO transactions
    - Screen by various criteria
    """

    BASE_URL = "http://openinsider.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Cache for insider data (1 hour TTL)
    _cache: Dict[str, Tuple[datetime, List[InsiderTransaction]]] = {}
    _cluster_cache: Dict[str, Tuple[datetime, List[ClusterBuyInfo]]] = {}
    CACHE_TTL = timedelta(hours=1)

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self):
        if self._owns_session:
            self._session = aiohttp.ClientSession(headers=self.HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_session and self._session:
            await self._session.close()

    async def fetch_recent_cluster_buys(
        self,
        days: int = 90,
        min_value: int = 10000,
        price_min: float = 0.5,
        price_max: float = 300.0
    ) -> Dict[str, List[InsiderTransaction]]:
        """
        Fetch recent cluster buys from OpenInsider

        Args:
            days: Look back period in days
            min_value: Minimum transaction value
            price_min: Minimum stock price
            price_max: Maximum stock price

        Returns:
            Dict mapping symbol to list of transactions
        """
        cache_key = f"cluster_{days}_{min_value}_{price_min}_{price_max}"

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self.CACHE_TTL:
                logger.debug("Returning cached cluster buy data")
                return self._group_by_symbol(cached_data)

        try:
            # Build URL for cluster buying screener
            url = (
                f"{self.BASE_URL}/screener?"
                f"s=&o=&pl={price_min}&ph={price_max}"
                f"&ll=&lh=&fd={days}&fdr=&td=0&tdr=&"
                f"fdlyl=&fdlyh=&dtefrom=&dteto=&"
                f"xp=1&xs=0&vl={min_value}&vh=&"
                f"ocl=&och=&session=1&"
                f"cnt=500"  # Get up to 500 results
            )

            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.error(f"OpenInsider returned status {response.status}")
                    return {}

                html = await response.text()
                transactions = self._parse_transaction_table(html)

                # Cache results
                self._cache[cache_key] = (datetime.utcnow(), transactions)

                logger.info(f"Fetched {len(transactions)} cluster buy transactions")
                return self._group_by_symbol(transactions)

        except Exception as e:
            logger.error(f"Error fetching cluster buys: {e}")
            return {}

    async def fetch_stock_insider_activity(
        self,
        symbol: str,
        days: int = 180
    ) -> InsiderActivitySummary:
        """
        Fetch insider activity for a specific stock

        Args:
            symbol: Stock ticker symbol
            days: Look back period

        Returns:
            InsiderActivitySummary for the stock
        """
        cache_key = f"stock_{symbol}_{days}"

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self.CACHE_TTL:
                return self._summarize_activity(symbol, cached_data)

        try:
            url = f"{self.BASE_URL}/screener?s={symbol}&fd={days}&cnt=100"

            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.error(f"OpenInsider returned status {response.status}")
                    return self._empty_summary(symbol)

                html = await response.text()
                transactions = self._parse_transaction_table(html)

                # Filter to just this symbol
                symbol_transactions = [
                    t for t in transactions
                    if t.symbol.upper() == symbol.upper()
                ]

                # Cache results
                self._cache[cache_key] = (datetime.utcnow(), symbol_transactions)

                return self._summarize_activity(symbol, symbol_transactions)

        except Exception as e:
            logger.error(f"Error fetching insider activity for {symbol}: {e}")
            return self._empty_summary(symbol)

    async def fetch_all_recent_purchases(
        self,
        days: int = 30,
        price_min: float = 0.5,
        price_max: float = 300.0
    ) -> Dict[str, List[InsiderTransaction]]:
        """
        Fetch ALL recent insider purchases (not just clusters)

        This is faster than fetching individual stocks.

        Args:
            days: Look back period
            price_min: Minimum stock price
            price_max: Maximum stock price

        Returns:
            Dict mapping symbol to list of purchase transactions
        """
        cache_key = f"all_purchases_{days}_{price_min}_{price_max}"

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self.CACHE_TTL:
                return self._group_by_symbol(cached_data)

        try:
            # URL for all purchases
            url = (
                f"{self.BASE_URL}/screener?"
                f"s=&o=&pl={price_min}&ph={price_max}"
                f"&ll=&lh=&fd={days}&fdr=&td=0&tdr=&"
                f"fdlyl=&fdlyh=&dtefrom=&dteto=&"
                f"xp=1&xs=0&vl=10000&vh=&"  # Purchases only, >$10k
                f"ocl=&och=&session=1&"
                f"cnt=1000"  # Get up to 1000 results
            )

            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.error(f"OpenInsider returned status {response.status}")
                    return {}

                html = await response.text()
                transactions = self._parse_transaction_table(html)

                # Cache results
                self._cache[cache_key] = (datetime.utcnow(), transactions)

                logger.info(f"Fetched {len(transactions)} recent purchase transactions")
                return self._group_by_symbol(transactions)

        except Exception as e:
            logger.error(f"Error fetching recent purchases: {e}")
            return {}

    # Maps a normalized OpenInsider header label to the InsiderTransaction field
    # it feeds. The "ticker" search page and the market-wide screener emit
    # different column sets (the per-symbol view omits "Company Name"), so we
    # resolve columns by header name rather than by fixed index.
    _COLUMN_ALIASES = {
        "filing date": "filing_date",
        "trade date": "trade_date",
        "ticker": "symbol",
        "company name": "company",
        "insider name": "insider_name",
        "title": "insider_title",
        "trade type": "tx_type",
        "price": "price",
        "qty": "quantity",
        "owned": "shares_owned",
        "δown": "delta_owned",
        "value": "total_value",
    }

    def _build_column_map(self, table) -> Dict[str, int]:
        """Map InsiderTransaction field names to their <td> index via headers."""
        header_row = None
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
        if header_row is None:
            header_row = table.find("tr")
        if header_row is None:
            return {}

        col_map = {}
        for idx, th in enumerate(header_row.find_all(["th", "td"])):
            label = th.get_text(strip=True).replace("\xa0", " ").lower()
            field = self._COLUMN_ALIASES.get(label)
            if field and field not in col_map:
                col_map[field] = idx
        return col_map

    def _parse_transaction_table(self, html: str) -> List[InsiderTransaction]:
        """Parse OpenInsider transaction table"""
        soup = BeautifulSoup(html, "lxml")
        transactions = []

        # Find the transaction table
        table = soup.find("table", {"class": "tinytable"})
        if not table:
            return transactions

        col_map = self._build_column_map(table)
        # Without a recognizable header we cannot trust column positions
        # (the two OpenInsider layouts differ), so bail rather than misparse.
        required = ("trade_date", "symbol", "tx_type", "price")
        if not all(c in col_map for c in required):
            logger.warning(
                "OpenInsider header not recognized; columns=%s", sorted(col_map)
            )
            return transactions

        body = table.find("tbody")
        rows = body.find_all("tr") if body else table.find_all("tr")[1:]
        max_idx = max(col_map.values())

        def cell(cells, field, default=""):
            idx = col_map.get(field)
            if idx is None or idx >= len(cells):
                return default
            return cells[idx].text.strip()

        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) <= max_idx:
                    continue

                filing_date = self._parse_date(cell(cells, "filing_date"))
                trade_date = self._parse_date(cell(cells, "trade_date"))

                # Get ticker from link when present
                ticker_cell = cells[col_map["symbol"]]
                ticker_link = ticker_cell.find("a")
                symbol = (
                    ticker_link.text.strip() if ticker_link else ticker_cell.text.strip()
                )

                company = cell(cells, "company")
                insider_name = cell(cells, "insider_name")
                insider_title = cell(cells, "insider_title")

                # Transaction type (e.g. "P - Purchase", "S - Sale+OE")
                tx_type_text = cell(cells, "tx_type")
                if tx_type_text.startswith("P"):
                    tx_type = TransactionType.PURCHASE
                elif tx_type_text.startswith("S"):
                    tx_type = TransactionType.SALE
                elif tx_type_text.startswith("M"):
                    tx_type = TransactionType.OPTION_EXERCISE
                else:
                    tx_type = TransactionType.GIFT

                price = self._parse_float(cell(cells, "price"))
                quantity = self._parse_int(cell(cells, "quantity"))
                shares_owned = self._parse_int(cell(cells, "shares_owned"))
                delta_owned = self._parse_percent(cell(cells, "delta_owned"))
                total_value = self._parse_float(cell(cells, "total_value"))

                transaction = InsiderTransaction(
                    filing_date=filing_date or datetime.utcnow(),
                    trade_date=trade_date or datetime.utcnow(),
                    symbol=symbol,
                    company=company,
                    insider_name=insider_name,
                    insider_title=insider_title,
                    transaction_type=tx_type,
                    price=price,
                    quantity=quantity,
                    total_value=total_value,
                    shares_owned=shares_owned,
                    delta_owned=delta_owned,
                )

                transactions.append(transaction)

            except Exception as e:
                logger.debug(f"Error parsing transaction row: {e}")
                continue

        return transactions

    def _group_by_symbol(
        self,
        transactions: List[InsiderTransaction]
    ) -> Dict[str, List[InsiderTransaction]]:
        """Group transactions by symbol"""
        grouped = {}
        for tx in transactions:
            symbol = tx.symbol.upper()
            if symbol not in grouped:
                grouped[symbol] = []
            grouped[symbol].append(tx)
        return grouped

    def _summarize_activity(
        self,
        symbol: str,
        transactions: List[InsiderTransaction]
    ) -> InsiderActivitySummary:
        """Summarize insider activity for a stock"""
        if not transactions:
            return self._empty_summary(symbol)

        purchases = [t for t in transactions if t.is_purchase]
        sales = [t for t in transactions if t.transaction_type == TransactionType.SALE]

        buyers = set(t.insider_name for t in purchases)
        sellers = set(t.insider_name for t in sales)

        # Detect cluster buying (3+ insiders buying within 30 days)
        has_cluster = len(buyers) >= 3

        # Find latest dates
        latest_purchase = max((t.trade_date for t in purchases), default=None)
        latest_sale = max((t.trade_date for t in sales), default=None)

        return InsiderActivitySummary(
            symbol=symbol,
            total_purchases=len(purchases),
            total_sales=len(sales),
            net_shares=sum(t.quantity for t in purchases) - sum(t.quantity for t in sales),
            net_value=sum(t.total_value for t in purchases) - sum(t.total_value for t in sales),
            unique_buyers=len(buyers),
            unique_sellers=len(sellers),
            latest_purchase_date=latest_purchase,
            latest_sale_date=latest_sale,
            has_cluster_buying=has_cluster,
            cluster_count=1 if has_cluster else 0,
            transactions=transactions,
        )

    def _empty_summary(self, symbol: str) -> InsiderActivitySummary:
        """Return empty summary for a stock"""
        return InsiderActivitySummary(
            symbol=symbol,
            total_purchases=0,
            total_sales=0,
            net_shares=0,
            net_value=0.0,
            unique_buyers=0,
            unique_sellers=0,
        )

    @staticmethod
    def _parse_date(value: str) -> Optional[datetime]:
        """Parse date string"""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            try:
                return datetime.strptime(value, "%m/%d/%Y")
            except ValueError:
                return None

    @staticmethod
    def _parse_float(value: str) -> float:
        """Parse float value"""
        if not value or value == "-":
            return 0.0
        try:
            return float(value.replace(",", "").replace("$", "").replace("+", ""))
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_int(value: str) -> int:
        """Parse int value"""
        if not value or value == "-":
            return 0
        try:
            return int(value.replace(",", "").replace("+", ""))
        except ValueError:
            return 0

    @staticmethod
    def _parse_percent(value: str) -> float:
        """Parse percent value"""
        if not value or value == "-" or value == "New":
            return 0.0
        try:
            return float(value.replace(",", "").replace("%", "").replace("+", ""))
        except ValueError:
            return 0.0


def get_insider_score(
    activity: InsiderActivitySummary,
    weight_recency: float = 0.4,
    weight_cluster: float = 0.35,
    weight_volume: float = 0.25
) -> float:
    """
    Calculate insider score from activity summary

    Args:
        activity: InsiderActivitySummary for the stock
        weight_recency: Weight for recency factor
        weight_cluster: Weight for cluster buying factor
        weight_volume: Weight for volume/size factor

    Returns:
        Score from 0-100
    """
    if not activity.total_purchases:
        return 0.0

    score = 0.0

    # Recency score (0-100)
    recency_score = 0.0
    if activity.latest_purchase_date:
        days_ago = (datetime.utcnow() - activity.latest_purchase_date).days
        if days_ago <= 7:
            recency_score = 100
        elif days_ago <= 14:
            recency_score = 90
        elif days_ago <= 30:
            recency_score = 75
        elif days_ago <= 60:
            recency_score = 50
        elif days_ago <= 90:
            recency_score = 30
        else:
            recency_score = 10

    score += recency_score * weight_recency

    # Cluster score (0-100)
    cluster_score = 0.0
    if activity.has_cluster_buying:
        cluster_score = min(activity.unique_buyers * 25, 100)
    elif activity.unique_buyers >= 2:
        cluster_score = 50
    elif activity.unique_buyers == 1:
        cluster_score = 25

    score += cluster_score * weight_cluster

    # Volume score (0-100) based on net value
    volume_score = 0.0
    if activity.net_value > 0:
        if activity.net_value >= 1_000_000:
            volume_score = 100
        elif activity.net_value >= 500_000:
            volume_score = 85
        elif activity.net_value >= 100_000:
            volume_score = 70
        elif activity.net_value >= 50_000:
            volume_score = 50
        else:
            volume_score = 30

    score += volume_score * weight_volume

    return round(score, 2)


async def fetch_recent_cluster_buys(
    days: int = 90
) -> Dict[str, List[InsiderTransaction]]:
    """
    Convenience function to fetch recent cluster buys

    Args:
        days: Look back period in days

    Returns:
        Dict mapping symbol to list of transactions
    """
    async with OpenInsiderScraper() as scraper:
        return await scraper.fetch_recent_cluster_buys(days=days)
