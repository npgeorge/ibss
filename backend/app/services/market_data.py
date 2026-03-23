"""
Market Data Collector

Fetches stock price data from various sources:
- Yahoo Finance (free, no API key required)
- Alpha Vantage (free tier available)
- Polygon.io (paid)
"""
import time as _time
import yfinance as yf
import pandas as pd
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class YahooFinanceCollector:
    """
    Yahoo Finance data collector (free, no API key required)

    Advantages:
    - Free
    - No API key needed
    - Good historical data
    - Supports most US stocks

    Disadvantages:
    - Rate limits (unofficial)
    - Can be unstable
    - Not suitable for high-frequency updates
    """

    @staticmethod
    def fetch_historical_data(
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "2y",
    ) -> pd.DataFrame:
        """
        Fetch historical price data from Yahoo Finance

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_date: Start date (optional)
            end_date: End date (optional)
            period: Period string if dates not provided (e.g., '1y', '2y', '5y')

        Returns:
            DataFrame with columns: ['open', 'high', 'low', 'close', 'volume', 'adjusted_close']
        """
        try:
            ticker = yf.Ticker(symbol)

            if start_date and end_date:
                df = ticker.history(start=start_date, end=end_date)
            else:
                df = ticker.history(period=period)

            if df.empty:
                logger.warning(f"No data retrieved for {symbol}")
                return pd.DataFrame()

            # Rename columns to match our schema
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )

            # Add adjusted close
            df["adjusted_close"] = df["close"]

            # Reset index to have date as column
            df = df.reset_index()
            df = df.rename(columns={"Date": "date"})

            # Select only needed columns
            df = df[["date", "open", "high", "low", "close", "volume", "adjusted_close"]]

            # Convert date to datetime
            df["date"] = pd.to_datetime(df["date"]).dt.date

            logger.info(f"Retrieved {len(df)} days of data for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    @staticmethod
    def batch_fetch_historical_data(
        symbols: List[str],
        period: str = "1y",
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical price data for multiple symbols in a single batched call.

        Uses yf.download() which is dramatically faster than per-symbol fetching.

        Args:
            symbols: List of stock symbols
            period: Period string (e.g., '1y', '2y')

        Returns:
            Dict mapping symbol to DataFrame with columns:
            ['date', 'open', 'high', 'low', 'close', 'volume']
        """
        if not symbols:
            return {}

        start = _time.time()
        results = {}

        try:
            logger.info(f"Batch fetching {len(symbols)} symbols with period={period}")

            df = yf.download(
                symbols,
                period=period,
                group_by="ticker",
                threads=True,
                progress=False,
            )

            if df.empty:
                logger.warning("Batch download returned empty DataFrame")
                return {}

            elapsed = _time.time() - start
            logger.info(f"Batch download completed in {elapsed:.1f}s for {len(symbols)} symbols")

            # Handle single symbol case: yf.download returns flat columns (no MultiIndex)
            if len(symbols) == 1:
                sym = symbols[0]
                sub = df.copy()
                sub.columns = [c.lower() if isinstance(c, str) else c for c in sub.columns]

                # Ensure expected columns exist
                required = {"open", "high", "low", "close", "volume"}
                if not required.issubset(set(sub.columns)):
                    logger.warning(f"{sym}: Missing required columns, got {list(sub.columns)}")
                    return {}

                sub = sub[["open", "high", "low", "close", "volume"]].copy()
                sub = sub.dropna(subset=["close"])

                if len(sub) < 10:
                    return {}

                sub = sub.reset_index()
                # Rename the index column (Date or Datetime) to 'date'
                if "Date" in sub.columns:
                    sub = sub.rename(columns={"Date": "date"})
                elif "Datetime" in sub.columns:
                    sub = sub.rename(columns={"Datetime": "date"})
                sub["date"] = pd.to_datetime(sub["date"])
                sub.index = sub["date"]
                sub.index.name = "date"

                results[sym] = sub
                return results

            # Multi-symbol case: MultiIndex columns (symbol, field)
            for sym in symbols:
                try:
                    if sym not in df.columns.get_level_values(0):
                        continue

                    sub = df[sym].copy()
                    sub.columns = [c.lower() for c in sub.columns]

                    required = {"open", "high", "low", "close", "volume"}
                    if not required.issubset(set(sub.columns)):
                        continue

                    sub = sub[["open", "high", "low", "close", "volume"]].copy()
                    sub = sub.dropna(subset=["close"])

                    if len(sub) < 10:
                        continue

                    sub = sub.reset_index()
                    if "Date" in sub.columns:
                        sub = sub.rename(columns={"Date": "date"})
                    elif "Datetime" in sub.columns:
                        sub = sub.rename(columns={"Datetime": "date"})
                    sub["date"] = pd.to_datetime(sub["date"])
                    sub.index = sub["date"]
                    sub.index.name = "date"

                    results[sym] = sub

                except Exception as e:
                    logger.debug(f"Error extracting data for {sym}: {e}")
                    continue

            logger.info(f"Batch fetch: {len(results)}/{len(symbols)} symbols had valid data")
            return results

        except Exception as e:
            logger.error(f"Batch fetch failed: {e}")
            return {}

    @staticmethod
    def fetch_stock_info(symbol: str) -> Dict:
        """
        Fetch stock information (company name, sector, market cap, etc.)

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with stock info
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "company_name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "market_cap": info.get("marketCap", 0),
                "float_shares": info.get("floatShares", 0),
                "outstanding_shares": info.get("sharesOutstanding", 0),
            }

        except Exception as e:
            logger.error(f"Error fetching info for {symbol}: {e}")
            return {
                "symbol": symbol,
                "company_name": symbol,
                "sector": "Unknown",
                "industry": "Unknown",
                "market_cap": 0,
                "float_shares": 0,
                "outstanding_shares": 0,
            }

    @staticmethod
    async def fetch_multiple_stocks(
        symbols: List[str], period: str = "2y"
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple stocks concurrently

        Args:
            symbols: List of stock symbols
            period: Period string

        Returns:
            Dictionary mapping symbol to DataFrame
        """
        results = {}

        # Yahoo Finance doesn't have true async support, but we can use threading
        def fetch_one(symbol: str) -> tuple:
            df = YahooFinanceCollector.fetch_historical_data(symbol, period=period)
            return symbol, df

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, fetch_one, symbol) for symbol in symbols]

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Error in batch fetch: {result}")
                continue

            symbol, df = result
            results[symbol] = df

        return results


class AlphaVantageCollector:
    """
    Alpha Vantage data collector

    Free tier: 500 API calls per day, 5 calls per minute
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

    async def fetch_daily_data(self, symbol: str, outputsize: str = "full") -> pd.DataFrame:
        """
        Fetch daily price data

        Args:
            symbol: Stock symbol
            outputsize: 'compact' (100 days) or 'full' (20+ years)

        Returns:
            DataFrame with price data
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    data = await response.json()

                    if "Time Series (Daily)" not in data:
                        logger.error(f"No data for {symbol}: {data}")
                        return pd.DataFrame()

                    # Parse the data
                    time_series = data["Time Series (Daily)"]
                    rows = []

                    for date_str, values in time_series.items():
                        rows.append(
                            {
                                "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
                                "open": float(values["1. open"]),
                                "high": float(values["2. high"]),
                                "low": float(values["3. low"]),
                                "close": float(values["4. close"]),
                                "adjusted_close": float(values["5. adjusted close"]),
                                "volume": int(values["6. volume"]),
                            }
                        )

                    df = pd.DataFrame(rows)
                    df = df.sort_values("date")
                    logger.info(f"Retrieved {len(df)} days from Alpha Vantage for {symbol}")
                    return df

        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage data for {symbol}: {e}")
            return pd.DataFrame()

    async def fetch_earnings(self, symbol: str) -> List[Dict]:
        """
        Fetch earnings data

        Returns:
            List of earnings reports
        """
        params = {
            "function": "EARNINGS",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    data = await response.json()

                    if "quarterlyEarnings" not in data:
                        return []

                    earnings = []
                    for report in data["quarterlyEarnings"]:
                        earnings.append(
                            {
                                "report_date": report.get("reportedDate"),
                                "fiscal_quarter": report.get("fiscalDateEnding"),
                                "eps_actual": float(report.get("reportedEPS", 0)),
                                "eps_estimated": float(report.get("estimatedEPS", 0)),
                                "eps_surprise": float(report.get("surprise", 0)),
                                "eps_surprise_pct": float(report.get("surprisePercentage", 0)),
                            }
                        )

                    return earnings

        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return []


def aggregate_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily data to weekly

    Args:
        daily_df: Daily price DataFrame

    Returns:
        Weekly DataFrame
    """
    if daily_df.empty:
        return pd.DataFrame()

    # Set date as index
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    # Resample to weekly (week ending Friday)
    weekly = df.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    # Remove weeks with no data
    weekly = weekly.dropna()

    # Reset index
    weekly = weekly.reset_index()
    weekly = weekly.rename(columns={"date": "week_start_date"})
    weekly["week_start_date"] = weekly["week_start_date"].dt.date

    return weekly


# Factory function
def get_market_data_collector(source: str = "yahoo"):
    """
    Get market data collector instance

    Args:
        source: 'yahoo', 'alphavantage', or 'polygon'

    Returns:
        Collector instance
    """
    if source == "yahoo":
        return YahooFinanceCollector()
    elif source == "alphavantage":
        if not settings.ALPHA_VANTAGE_API_KEY:
            raise ValueError("Alpha Vantage API key not configured")
        return AlphaVantageCollector(settings.ALPHA_VANTAGE_API_KEY)
    else:
        raise ValueError(f"Unknown data source: {source}")
