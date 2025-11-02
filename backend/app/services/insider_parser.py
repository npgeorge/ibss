"""
SEC EDGAR Insider Transaction Parser

Parses Form 4 filings from SEC EDGAR to track insider buying activity.
This is a critical component of the Superstock strategy.
"""
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class SECEdgarInsiderParser:
    """
    Parse insider transactions from SEC EDGAR

    SEC provides free access to Form 4 filings (insider transactions)
    """

    BASE_URL = "https://www.sec.gov"
    SEARCH_URL = f"{BASE_URL}/cgi-bin/browse-edgar"

    def __init__(self):
        self.headers = {
            "User-Agent": settings.SEC_EDGAR_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }

    async def fetch_recent_form4_filings(
        self, symbol: str, days: int = 90
    ) -> List[Dict]:
        """
        Fetch recent Form 4 filings for a stock

        Args:
            symbol: Stock ticker symbol
            days: Number of days to look back

        Returns:
            List of Form 4 filing URLs and metadata
        """
        params = {
            "action": "getcompany",
            "CIK": symbol,
            "type": "4",  # Form 4 - Statement of Changes in Beneficial Ownership
            "dateb": "",
            "owner": "include",
            "count": "100",
            "search_text": "",
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.SEARCH_URL, params=params) as response:
                    if response.status != 200:
                        logger.error(
                            f"SEC request failed for {symbol}: {response.status}"
                        )
                        return []

                    html = await response.text()
                    filings = self._parse_filing_list(html, days)
                    logger.info(
                        f"Found {len(filings)} Form 4 filings for {symbol} in last {days} days"
                    )
                    return filings

        except Exception as e:
            logger.error(f"Error fetching Form 4 filings for {symbol}: {e}")
            return []

    def _parse_filing_list(self, html: str, days: int) -> List[Dict]:
        """
        Parse the filing list HTML to extract Form 4 URLs

        Args:
            html: HTML content from SEC search
            days: Filter filings from last N days

        Returns:
            List of filing metadata
        """
        soup = BeautifulSoup(html, "html.parser")
        filings = []

        cutoff_date = datetime.now() - timedelta(days=days)

        # Find the table with filings
        table = soup.find("table", {"class": "tableFile2"})
        if not table:
            return []

        rows = table.find_all("tr")[1:]  # Skip header

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            # Extract filing date
            filing_date_str = cols[3].text.strip()
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            except ValueError:
                continue

            # Filter by date
            if filing_date < cutoff_date:
                continue

            # Extract document link
            doc_link = cols[1].find("a")
            if not doc_link:
                continue

            filing_url = self.BASE_URL + doc_link.get("href")

            filings.append(
                {"filing_date": filing_date.date(), "filing_url": filing_url}
            )

        return filings

    async def parse_form4_filing(self, filing_url: str) -> List[Dict]:
        """
        Parse a single Form 4 filing to extract transaction details

        Args:
            filing_url: URL to the Form 4 filing index page

        Returns:
            List of transactions from this filing
        """
        try:
            # Get the XML document
            xml_url = await self._get_xml_document_url(filing_url)
            if not xml_url:
                return []

            # Parse the XML
            transactions = await self._parse_form4_xml(xml_url)
            return transactions

        except Exception as e:
            logger.error(f"Error parsing Form 4 from {filing_url}: {e}")
            return []

    async def _get_xml_document_url(self, filing_url: str) -> Optional[str]:
        """
        Get the XML document URL from the filing index page

        Args:
            filing_url: Filing index page URL

        Returns:
            XML document URL
        """
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(filing_url) as response:
                    html = await response.text()

            soup = BeautifulSoup(html, "html.parser")

            # Find XML document link
            table = soup.find("table", {"class": "tableFile"})
            if not table:
                return None

            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 3:
                    doc_type = cols[3].text.strip()
                    if doc_type == "4":  # Primary document
                        link = cols[2].find("a")
                        if link:
                            return self.BASE_URL + link.get("href")

            return None

        except Exception as e:
            logger.error(f"Error getting XML URL from {filing_url}: {e}")
            return None

    async def _parse_form4_xml(self, xml_url: str) -> List[Dict]:
        """
        Parse Form 4 XML document

        Args:
            xml_url: URL to XML document

        Returns:
            List of transactions
        """
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(xml_url) as response:
                    xml_content = await response.text()

            # Parse XML
            root = ET.fromstring(xml_content)

            transactions = []

            # Extract reporting owner info
            owner_name = self._get_xml_text(
                root, ".//reportingOwner/reportingOwnerId/rptOwnerName"
            )
            owner_title = self._get_xml_text(
                root, ".//reportingOwner/reportingOwnerRelationship/officerTitle"
            )

            # Extract non-derivative transactions
            for trans_elem in root.findall(
                ".//nonDerivativeTransaction"
            ) or root.findall(".//derivativeTransaction"):
                transaction = self._parse_transaction_element(
                    trans_elem, owner_name, owner_title
                )
                if transaction:
                    transactions.append(transaction)

            return transactions

        except Exception as e:
            logger.error(f"Error parsing XML from {xml_url}: {e}")
            return []

    def _parse_transaction_element(
        self, trans_elem, owner_name: str, owner_title: str
    ) -> Optional[Dict]:
        """
        Parse a single transaction element from XML

        Args:
            trans_elem: XML element for transaction
            owner_name: Insider's name
            owner_title: Insider's title

        Returns:
            Transaction dictionary
        """
        try:
            # Transaction date
            trans_date_str = self._get_xml_text(trans_elem, ".//transactionDate/value")
            trans_date = (
                datetime.strptime(trans_date_str, "%Y-%m-%d").date()
                if trans_date_str
                else None
            )

            # Transaction code (P=Purchase, S=Sale, etc.)
            trans_code = self._get_xml_text(
                trans_elem, ".//transactionCoding/transactionCode"
            )

            # Map transaction codes
            trans_type_map = {
                "P": "purchase",
                "S": "sale",
                "M": "option_exercise",
                "A": "grant",
                "D": "disposition",
            }
            trans_type = trans_type_map.get(trans_code, "other")

            # Shares
            shares_str = self._get_xml_text(
                trans_elem, ".//transactionAmounts/transactionShares/value"
            )
            shares = int(float(shares_str)) if shares_str else 0

            # Price per share
            price_str = self._get_xml_text(
                trans_elem, ".//transactionAmounts/transactionPricePerShare/value"
            )
            price = float(price_str) if price_str else 0.0

            # Shares owned after
            shares_after_str = self._get_xml_text(
                trans_elem, ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value"
            )
            shares_after = int(float(shares_after_str)) if shares_after_str else 0

            return {
                "insider_name": owner_name,
                "insider_title": owner_title or "Unknown",
                "transaction_date": trans_date,
                "transaction_type": trans_type,
                "shares": shares,
                "price_per_share": price,
                "total_value": shares * price,
                "shares_owned_after": shares_after,
            }

        except Exception as e:
            logger.error(f"Error parsing transaction element: {e}")
            return None

    @staticmethod
    def _get_xml_text(root, xpath: str) -> Optional[str]:
        """
        Get text from XML element

        Args:
            root: XML root element
            xpath: XPath to element

        Returns:
            Text content or None
        """
        elem = root.find(xpath)
        return elem.text.strip() if elem is not None and elem.text else None

    async def get_all_insider_transactions(
        self, symbol: str, days: int = 90
    ) -> List[Dict]:
        """
        Get all insider transactions for a symbol

        Args:
            symbol: Stock symbol
            days: Days to look back

        Returns:
            List of all transactions
        """
        # Get list of filings
        filings = await self.fetch_recent_form4_filings(symbol, days)

        if not filings:
            return []

        # Parse each filing
        all_transactions = []

        for filing in filings:
            transactions = await self.parse_form4_filing(filing["filing_url"])

            # Add filing date to each transaction
            for trans in transactions:
                trans["filing_date"] = filing["filing_date"]
                trans["sec_filing_url"] = filing["filing_url"]

            all_transactions.extend(transactions)

            # Rate limiting - SEC requests max 10 per second
            await asyncio.sleep(0.15)

        logger.info(
            f"Retrieved {len(all_transactions)} insider transactions for {symbol}"
        )
        return all_transactions


class InsiderActivityAnalyzer:
    """
    Analyze insider transaction patterns

    Key signals:
    - Cluster buying (multiple insiders buying within short period)
    - Buying at increasing prices (strong conviction)
    - Executive buying (CEO, CFO more significant than directors)
    """

    @staticmethod
    def detect_cluster_buying(
        transactions: List[Dict], days_window: int = 30, min_insiders: int = 2
    ) -> bool:
        """
        Detect if multiple insiders are buying within a time window

        Args:
            transactions: List of insider transactions
            days_window: Time window in days
            min_insiders: Minimum number of different insiders

        Returns:
            True if cluster buying detected
        """
        # Filter to purchases only
        purchases = [t for t in transactions if t["transaction_type"] == "purchase"]

        if len(purchases) < min_insiders:
            return False

        # Group by insider name
        unique_buyers = set(t["insider_name"] for t in purchases)

        if len(unique_buyers) < min_insiders:
            return False

        # Check if purchases are within time window
        sorted_purchases = sorted(purchases, key=lambda x: x["transaction_date"])

        for i in range(len(sorted_purchases) - min_insiders + 1):
            window_purchases = sorted_purchases[i : i + min_insiders]
            first_date = window_purchases[0]["transaction_date"]
            last_date = window_purchases[-1]["transaction_date"]

            if (last_date - first_date).days <= days_window:
                return True

        return False

    @staticmethod
    def calculate_insider_confidence_score(transactions: List[Dict]) -> float:
        """
        Calculate insider confidence score (0-100)

        Higher score = more bullish insider activity

        Factors:
        - Number of buyers vs sellers
        - Purchase value
        - Executive purchases (weighted higher)
        - Buying at increasing prices
        """
        if not transactions:
            return 0.0

        score = 0.0

        purchases = [t for t in transactions if t["transaction_type"] == "purchase"]
        sales = [t for t in transactions if t["transaction_type"] == "sale"]

        # Factor 1: Buy vs sell ratio (max 40 points)
        if len(purchases) > 0:
            buy_sell_ratio = len(purchases) / (len(sales) + 1)
            score += min(buy_sell_ratio * 10, 40)

        # Factor 2: Total purchase value (max 30 points)
        total_purchase_value = sum(t["total_value"] for t in purchases)
        if total_purchase_value > 1_000_000:
            score += 30
        elif total_purchase_value > 500_000:
            score += 20
        elif total_purchase_value > 100_000:
            score += 10

        # Factor 3: Executive purchases (max 20 points)
        exec_titles = ["CEO", "CFO", "President", "COO"]
        exec_purchases = [
            t for t in purchases if any(title in t["insider_title"] for title in exec_titles)
        ]
        if exec_purchases:
            score += min(len(exec_purchases) * 10, 20)

        # Factor 4: Increasing prices (max 10 points)
        if len(purchases) >= 2:
            sorted_purchases = sorted(purchases, key=lambda x: x["transaction_date"])
            prices = [t["price_per_share"] for t in sorted_purchases if t["price_per_share"] > 0]

            if len(prices) >= 2 and prices[-1] > prices[0]:
                score += 10

        return min(score, 100)
