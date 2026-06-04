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

import pandas as pd

from app.core.database import get_sync_db
from app.core.repository import StockRepository
from app.services.market_data import YahooFinanceCollector
from app.models.database import Stock, PriceDataDaily
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockDataIngester:
    """Ingest stock data into the database"""

    # Symbols per batched yfinance download
    BATCH_SIZE = 150

    def __init__(self):
        self.collector = YahooFinanceCollector()

    @staticmethod
    def _price_rows(stock_id: int, df: pd.DataFrame) -> list[dict]:
        """Convert a price DataFrame into upsert-ready row dicts."""
        rows = []
        for _, row in df.iterrows():
            if "date" in row:
                d = pd.to_datetime(row["date"]).date()
            else:
                d = pd.to_datetime(row.name).date()
            close = float(row["close"])
            rows.append({
                "stock_id": stock_id,
                "date": d,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close,
                "volume": int(row["volume"]) if not pd.isna(row["volume"]) else 0,
                "adjusted_close": float(row.get("adjusted_close", close)),
            })
        return rows

    def ingest_stock(self, symbol: str, price_df: pd.DataFrame = None):
        """
        Ingest a single stock. If price_df is provided (from a batched
        download) it is used directly; otherwise it is fetched per-symbol.
        """
        try:
            logger.info(f"Ingesting {symbol}...")

            with get_sync_db() as db:
                stock_repo = StockRepository(db)

                stock_info = self.collector.fetch_stock_info(symbol)
                stock = stock_repo.create_or_update_stock(stock_info)

                if price_df is None:
                    price_df = self.collector.fetch_historical_data(symbol, period="2y")

                if price_df is None or price_df.empty:
                    logger.warning(f"No price data for {symbol}")
                    return

                stock_repo.bulk_insert_price_data(self._price_rows(stock.id, price_df))
                logger.info(f"✓ {symbol} ingested successfully ({len(price_df)} days)")

        except Exception as e:
            logger.error(f"✗ Error ingesting {symbol}: {e}")

    def ingest_multiple(self, symbols: list[str]):
        """
        Ingest multiple stocks using batched price downloads.

        Price history is fetched in chunks via a single yf.download() per
        chunk (dramatically faster than one call per symbol); company metadata
        is still fetched per symbol since yfinance .info is not batchable.
        """
        import time

        symbols = [s.upper() for s in symbols]
        total = len(symbols)
        logger.info(f"Ingesting {total} stocks (batched)...")

        done = 0
        for start in range(0, total, self.BATCH_SIZE):
            chunk = symbols[start:start + self.BATCH_SIZE]
            logger.info(f"Batch downloading {len(chunk)} symbols...")
            data_map = self.collector.batch_fetch_historical_data(chunk, period="2y")

            for symbol in chunk:
                done += 1
                logger.info(f"[{done}/{total}] Processing {symbol}")
                self.ingest_stock(symbol, data_map.get(symbol))

            time.sleep(0.5)  # polite pause between batches

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
