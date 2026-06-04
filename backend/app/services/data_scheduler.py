"""
Data Update Scheduler

Manages automated data collection:
- Daily price data updates
- Hourly insider filing checks
- Weekly technical indicator calculations
- Monthly fundamental data updates
"""
import asyncio
from datetime import datetime, time, date, timedelta
from typing import List, Optional
import logging
from sqlalchemy.orm import Session

from app.core.database import get_sync_db
from app.models.database import Stock, DataUpdate
from app.services.market_data import YahooFinanceCollector, aggregate_to_weekly
from app.services.openinsider import OpenInsiderScraper
from app.services.technical_indicators import TechnicalIndicatorCalculator
import pandas as pd

logger = logging.getLogger(__name__)


class DataUpdateScheduler:
    """
    Schedule and execute data updates

    Schedule:
    - Daily: Price data (after market close - 4:30 PM ET)
    - Hourly: Insider filings check (during market hours)
    - Weekly: Pattern recognition (Sundays)
    - Monthly: Fundamental data
    """

    def __init__(self):
        self.market_data_collector = YahooFinanceCollector()
        self.insider_parser = OpenInsiderScraper()
        self.is_running = False

    async def start(self):
        """Start the scheduler"""
        self.is_running = True
        logger.info("Data scheduler started")

        # Run tasks concurrently
        await asyncio.gather(
            self.daily_price_update_loop(),
            self.hourly_insider_check_loop(),
            self.weekly_indicator_update_loop(),
        )

    async def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        logger.info("Data scheduler stopped")

    async def daily_price_update_loop(self):
        """Run daily price updates"""
        while self.is_running:
            # Wait until 4:30 PM ET (market close + 30 min)
            await self._wait_until_time(time(16, 30))

            if self.is_running:
                await self.update_all_stock_prices()

            # Sleep until next day
            await asyncio.sleep(86400)  # 24 hours

    async def hourly_insider_check_loop(self):
        """Run hourly insider filing checks"""
        while self.is_running:
            await self.check_insider_filings()

            # Sleep for 1 hour
            await asyncio.sleep(3600)

    async def weekly_indicator_update_loop(self):
        """Run weekly technical indicator updates"""
        while self.is_running:
            # Wait until Sunday midnight
            now = datetime.now()
            if now.weekday() == 6:  # Sunday
                await self.update_all_technical_indicators()

            # Sleep for 1 day
            await asyncio.sleep(86400)

    # How many symbols to request from yfinance in a single batched download
    BATCH_SIZE = 150
    # Daily window pulled on each incremental update (enough for trailing weekly)
    INCREMENTAL_PERIOD = "3mo"

    async def update_all_stock_prices(self):
        """Update price data for all active stocks using batched downloads"""
        update_id = self._log_update_start("price_daily")

        try:
            with get_sync_db() as db:
                stocks = db.query(Stock).filter(Stock.is_active == True).all()
                symbol_to_id = {s.symbol: s.id for s in stocks}
                symbols = list(symbol_to_id.keys())

                logger.info(f"Updating prices for {len(symbols)} stocks (batched)")

                processed = 0
                failed = 0

                for start in range(0, len(symbols), self.BATCH_SIZE):
                    chunk = symbols[start:start + self.BATCH_SIZE]

                    # One batched download per chunk instead of one call per symbol
                    data_map = await asyncio.to_thread(
                        YahooFinanceCollector.batch_fetch_historical_data,
                        chunk,
                        self.INCREMENTAL_PERIOD,
                    )

                    for symbol, df in data_map.items():
                        try:
                            self._upsert_daily_and_weekly(symbol_to_id[symbol], df, db)
                            processed += 1
                        except Exception as e:
                            logger.error(f"Error updating {symbol}: {e}")
                            failed += 1

                    # Light pause between chunks to stay polite to the source
                    await asyncio.sleep(0.5)

                self._log_update_complete(update_id, processed, failed)
                logger.info(
                    f"Price update complete: {processed} processed, {failed} failed"
                )

        except Exception as e:
            self._log_update_failed(update_id, str(e))
            logger.error(f"Price update failed: {e}")

    async def update_stock_price(self, symbol: str, db: Session):
        """Update price data for a single stock (manual / single-symbol path)"""
        df = self.market_data_collector.fetch_historical_data(
            symbol, period=self.INCREMENTAL_PERIOD
        )

        if df.empty:
            logger.warning(f"No data retrieved for {symbol}")
            return

        stock = db.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            logger.warning(f"Stock {symbol} not found in database")
            return

        self._upsert_daily_and_weekly(stock.id, df, db)

    def _upsert_daily_and_weekly(self, stock_id: int, df: pd.DataFrame, db: Session):
        """
        Bulk-upsert a window of daily bars and incrementally refresh the
        trailing weekly bars they cover. Only the fetched window is rewritten,
        so historical weekly bars from prior runs are preserved.
        """
        from app.core.repository import StockRepository

        if df is None or df.empty:
            return

        repo = StockRepository(db)

        # --- Daily ---
        daily_rows = []
        for _, row in df.iterrows():
            d = pd.to_datetime(row["date"]).date() if "date" in row else pd.to_datetime(row.name).date()
            close = float(row["close"])
            daily_rows.append({
                "stock_id": stock_id,
                "date": d,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close,
                "volume": int(row["volume"]) if not pd.isna(row["volume"]) else 0,
                "adjusted_close": float(row.get("adjusted_close", close)),
            })
        repo.bulk_insert_price_data(daily_rows)

        # --- Weekly (incremental over the fetched window) ---
        weekly_df = aggregate_to_weekly(pd.DataFrame(daily_rows))
        if weekly_df.empty:
            return

        # Drop the leading week: a 3-month window can start mid-week, and we
        # don't want a partial bar to overwrite a complete one from a prior run.
        if len(weekly_df) > 1:
            weekly_df = weekly_df.iloc[1:]

        weekly_rows = [
            {
                "stock_id": stock_id,
                "week_start_date": row["week_start_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
            for _, row in weekly_df.iterrows()
        ]
        repo.bulk_upsert_weekly_data(weekly_rows)

    async def update_weekly_data(self, stock_id: int, db: Session):
        """Recompute trailing weekly bars from the most recent daily data."""
        from app.models.database import PriceDataDaily

        cutoff = date.today() - timedelta(days=120)
        daily_data = (
            db.query(PriceDataDaily)
            .filter(
                PriceDataDaily.stock_id == stock_id,
                PriceDataDaily.date >= cutoff,
            )
            .order_by(PriceDataDaily.date)
            .all()
        )

        if not daily_data:
            return

        df = pd.DataFrame(
            [
                {
                    "date": d.date,
                    "open": float(d.open),
                    "high": float(d.high),
                    "low": float(d.low),
                    "close": float(d.close),
                    "volume": d.volume,
                }
                for d in daily_data
            ]
        )

        weekly_df = aggregate_to_weekly(df)
        if weekly_df.empty:
            return
        if len(weekly_df) > 1:
            weekly_df = weekly_df.iloc[1:]

        from app.core.repository import StockRepository
        weekly_rows = [
            {
                "stock_id": stock_id,
                "week_start_date": row["week_start_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
            for _, row in weekly_df.iterrows()
        ]
        StockRepository(db).bulk_upsert_weekly_data(weekly_rows)

    async def check_insider_filings(self):
        """Check for new insider filings"""
        update_id = self._log_update_start("insider")

        try:
            with get_sync_db() as db:
                stocks = db.query(Stock).filter(Stock.is_active == True).limit(50).all()

                processed = 0
                failed = 0

                for stock in stocks:
                    try:
                        await self.update_insider_transactions(stock.symbol, db)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Error checking insider for {stock.symbol}: {e}")
                        failed += 1

                    # Rate limiting (SEC: max 10/sec)
                    await asyncio.sleep(0.2)

                self._log_update_complete(update_id, processed, failed)

        except Exception as e:
            self._log_update_failed(update_id, str(e))
            logger.error(f"Insider check failed: {e}")

    async def update_insider_transactions(self, symbol: str, db: Session):
        """Update insider transactions for a stock"""
        from app.models.database import Stock, InsiderTransaction

        # Get transactions from SEC
        transactions = await self.insider_parser.get_all_insider_transactions(
            symbol, days=30
        )

        if not transactions:
            return

        stock = db.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return

        # Insert new transactions
        for trans in transactions:
            # Check if already exists
            existing = (
                db.query(InsiderTransaction)
                .filter(
                    InsiderTransaction.stock_id == stock.id,
                    InsiderTransaction.transaction_date == trans["transaction_date"],
                    InsiderTransaction.insider_name == trans["insider_name"],
                )
                .first()
            )

            if not existing:
                insider_trans = InsiderTransaction(
                    stock_id=stock.id,
                    filing_date=trans["filing_date"],
                    transaction_date=trans["transaction_date"],
                    insider_name=trans["insider_name"],
                    insider_title=trans["insider_title"],
                    transaction_type=trans["transaction_type"],
                    shares=trans["shares"],
                    price_per_share=trans["price_per_share"],
                    total_value=trans["total_value"],
                    shares_owned_after=trans["shares_owned_after"],
                    sec_filing_url=trans["sec_filing_url"],
                )
                db.add(insider_trans)

        db.commit()

    async def update_all_technical_indicators(self):
        """Update technical indicators for all stocks"""
        update_id = self._log_update_start("technical_indicators")

        try:
            with get_sync_db() as db:
                stocks = db.query(Stock).filter(Stock.is_active == True).all()

                processed = 0
                failed = 0

                for stock in stocks:
                    try:
                        await self.update_technical_indicators(stock.id, db)
                        processed += 1
                    except Exception as e:
                        logger.error(
                            f"Error updating indicators for {stock.symbol}: {e}"
                        )
                        failed += 1

                self._log_update_complete(update_id, processed, failed)

        except Exception as e:
            self._log_update_failed(update_id, str(e))
            logger.error(f"Technical indicator update failed: {e}")

    async def update_technical_indicators(self, stock_id: int, db: Session):
        """Calculate and store technical indicators"""
        from app.models.database import PriceDataDaily, TechnicalIndicator

        # Get price data
        price_data = (
            db.query(PriceDataDaily)
            .filter(PriceDataDaily.stock_id == stock_id)
            .order_by(PriceDataDaily.date)
            .all()
        )

        if len(price_data) < 200:  # Need enough data
            return

        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "date": p.date,
                    "open": float(p.open),
                    "high": float(p.high),
                    "low": float(p.low),
                    "close": float(p.close),
                    "volume": p.volume,
                }
                for p in price_data
            ]
        )
        df = df.set_index("date")

        # Calculate indicators
        calculator = TechnicalIndicatorCalculator(df)
        df_with_indicators = calculator.calculate_all_indicators()

        # Store latest indicators
        latest = df_with_indicators.iloc[-1]
        latest_date = df_with_indicators.index[-1]

        # Check if exists
        existing = (
            db.query(TechnicalIndicator)
            .filter(
                TechnicalIndicator.stock_id == stock_id,
                TechnicalIndicator.date == latest_date,
            )
            .first()
        )

        if existing:
            # Update
            existing.sma_8w = latest.get("sma_8w")
            existing.sma_10w = latest.get("sma_10w")
            existing.sma_12w = latest.get("sma_12w")
            existing.sma_14w = latest.get("sma_14w")
            existing.volume_avg_20d = latest.get("volume_avg_20d")
            existing.rsi_14 = latest.get("rsi_14")
            existing.macd = latest.get("macd")
        else:
            # Insert
            indicator = TechnicalIndicator(
                stock_id=stock_id,
                date=latest_date,
                sma_8w=latest.get("sma_8w"),
                sma_10w=latest.get("sma_10w"),
                sma_12w=latest.get("sma_12w"),
                sma_14w=latest.get("sma_14w"),
                sma_20d=latest.get("sma_20d"),
                sma_50d=latest.get("sma_50d"),
                sma_200d=latest.get("sma_200d"),
                volume_avg_20d=latest.get("volume_avg_20d"),
                volume_avg_50d=latest.get("volume_avg_50d"),
                volume_ratio=latest.get("volume_ratio"),
                rsi_14=latest.get("rsi_14"),
                macd=latest.get("macd"),
                macd_signal=latest.get("macd_signal"),
                macd_histogram=latest.get("macd_histogram"),
            )
            db.add(indicator)

        db.commit()

    # Helper methods
    def _log_update_start(self, update_type: str) -> int:
        """Log the start of an update"""
        with get_sync_db() as db:
            update = DataUpdate(update_type=update_type, status="running")
            db.add(update)
            db.commit()
            return update.id

    def _log_update_complete(self, update_id: int, processed: int, failed: int):
        """Log successful completion"""
        with get_sync_db() as db:
            update = db.query(DataUpdate).filter(DataUpdate.id == update_id).first()
            if update:
                update.status = "completed"
                update.records_processed = processed
                update.records_failed = failed
                update.completed_at = datetime.utcnow()
                db.commit()

    def _log_update_failed(self, update_id: int, error: str):
        """Log failed update"""
        with get_sync_db() as db:
            update = db.query(DataUpdate).filter(DataUpdate.id == update_id).first()
            if update:
                update.status = "failed"
                update.error_message = error
                update.completed_at = datetime.utcnow()
                db.commit()

    async def _wait_until_time(self, target_time: time):
        """Wait until a specific time of day"""
        now = datetime.now()
        target = datetime.combine(now.date(), target_time)

        if now > target:
            # Target time already passed today, wait until tomorrow
            target = datetime.combine(now.date(), target_time)
            target = target.replace(day=target.day + 1)

        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)


# Standalone functions for manual updates
async def manual_update_stock(symbol: str):
    """Manually update a single stock"""
    scheduler = DataUpdateScheduler()

    with get_sync_db() as db:
        await scheduler.update_stock_price(symbol, db)
        logger.info(f"Updated {symbol}")


async def manual_full_update():
    """Manually trigger full data update"""
    scheduler = DataUpdateScheduler()

    await scheduler.update_all_stock_prices()
    await scheduler.check_insider_filings()
    await scheduler.update_all_technical_indicators()

    logger.info("Full manual update complete")
