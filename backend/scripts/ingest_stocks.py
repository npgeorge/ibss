"""
Stock Data Ingestion Script

Populates the database with initial stock data for screening.

Usage:
    python scripts/ingest_stocks.py --symbols AAPL MSFT GOOGL
    python scripts/ingest_stocks.py --file symbols.txt
    python scripts/ingest_stocks.py --sp500  # Ingest S&P 500 stocks
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import get_sync_db
from app.core.repository import StockRepository
from app.services.market_data import YahooFinanceCollector
from app.models.database import Stock, PriceDataDaily
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockDataIngester:
    """Ingest stock data into the database"""

    def __init__(self):
        self.collector = YahooFinanceCollector()

    def ingest_stock(self, symbol: str):
        """
        Ingest a single stock

        Args:
            symbol: Stock ticker symbol
        """
        try:
            logger.info(f"Ingesting {symbol}...")

            with get_sync_db() as db:
                stock_repo = StockRepository(db)

                # Get stock info
                stock_info = self.collector.fetch_stock_info(symbol)

                # Create or update stock
                stock = stock_repo.create_or_update_stock(stock_info)

                # Get historical price data (2 years)
                price_df = self.collector.fetch_historical_data(symbol, period="2y")

                if price_df.empty:
                    logger.warning(f"No price data for {symbol}")
                    return

                # Insert price data
                for _, row in price_df.iterrows():
                    # Check if exists
                    existing = (
                        db.query(PriceDataDaily)
                        .filter(
                            PriceDataDaily.stock_id == stock.id,
                            PriceDataDaily.date == row["date"]
                        )
                        .first()
                    )

                    if not existing:
                        price_data = PriceDataDaily(
                            stock_id=stock.id,
                            date=row["date"],
                            open=row["open"],
                            high=row["high"],
                            low=row["low"],
                            close=row["close"],
                            volume=row["volume"],
                            adjusted_close=row["adjusted_close"],
                        )
                        db.add(price_data)

                db.commit()
                logger.info(f"✓ {symbol} ingested successfully ({len(price_df)} days)")

        except Exception as e:
            logger.error(f"✗ Error ingesting {symbol}: {e}")

    def ingest_multiple(self, symbols: list[str]):
        """
        Ingest multiple stocks

        Args:
            symbols: List of stock symbols
        """
        total = len(symbols)
        logger.info(f"Ingesting {total} stocks...")

        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{total}] Processing {symbol}")
            self.ingest_stock(symbol.upper())

            # Rate limiting
            import time
            time.sleep(0.5)  # Avoid overwhelming APIs

        logger.info(f"✓ Completed ingestion of {total} stocks")


def get_sp500_symbols():
    """Get S&P 500 stock symbols"""
    try:
        import pandas as pd
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = table[0]
        return df['Symbol'].str.replace('.', '-').tolist()
    except:
        logger.error("Could not fetch S&P 500 list")
        return []


def get_sample_stocks():
    """Get a sample list of stocks for testing"""
    return [
        # Tech
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "NVDA", "AMD", "INTC", "QCOM", "AVGO",

        # Small/Mid caps (better for Superstocks)
        "PLTR", "SNOW", "DDOG", "CRWD", "ZS",
        "NET", "MDB", "DOCN", "FROG", "S",

        # Healthcare/Biotech
        "MRNA", "BNTX", "NVCR", "CRSP", "EDIT",

        # Other sectors
        "TSLA", "NIO", "RIVN", "LCID",
    ]


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Ingest stock data into IBSS database")

    parser.add_argument("--symbols", nargs="+", help="List of stock symbols")
    parser.add_argument("--file", help="File containing stock symbols (one per line)")
    parser.add_argument("--sp500", action="store_true", help="Ingest all S&P 500 stocks")
    parser.add_argument("--sample", action="store_true", help="Ingest sample stocks for testing")

    args = parser.parse_args()

    symbols = []

    if args.symbols:
        symbols = args.symbols
    elif args.file:
        with open(args.file) as f:
            symbols = [line.strip() for line in f if line.strip()]
    elif args.sp500:
        logger.info("Fetching S&P 500 symbols...")
        symbols = get_sp500_symbols()
    elif args.sample:
        symbols = get_sample_stocks()
    else:
        logger.error("Please specify --symbols, --file, --sp500, or --sample")
        parser.print_help()
        return

    if not symbols:
        logger.error("No symbols to ingest")
        return

    # Run ingestion
    ingester = StockDataIngester()
    ingester.ingest_multiple(symbols)


if __name__ == "__main__":
    main()
