"""
Data Update Scheduler

Manages automated data collection:
- Daily price data updates
- Hourly insider filing checks
- Weekly technical indicator calculations
- Monthly fundamental data updates
"""
import asyncio
from datetime import datetime, time
from typing import List, Optional
import logging
from sqlalchemy.orm import Session

from app.core.database import get_sync_db
from app.models.database import Stock, DataUpdate
from app.services.market_data import YahooFinanceCollector, aggregate_to_weekly
from app.services.insider_parser import SECEdgarInsiderParser
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
        self.insider_parser = SECEdgarInsiderParser()
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

    async def update_all_stock_prices(self):
        """Update price data for all active stocks"""
        update_id = self._log_update_start("price_daily")

        try:
            with get_sync_db() as db:
                # Get all active stocks
                stocks = db.query(Stock).filter(Stock.is_active == True).all()

                logger.info(f"Updating prices for {len(stocks)} stocks")

                processed = 0
                failed = 0

                for stock in stocks:
                    try:
                        await self.update_stock_price(stock.symbol, db)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Error updating {stock.symbol}: {e}")
                        failed += 1

                    # Rate limiting
                    await asyncio.sleep(0.1)

                self._log_update_complete(update_id, processed, failed)
                logger.info(
                    f"Price update complete: {processed} processed, {failed} failed"
                )

        except Exception as e:
            self._log_update_failed(update_id, str(e))
            logger.error(f"Price update failed: {e}")

    async def update_stock_price(self, symbol: str, db: Session):
        """
        Update price data for a single stock

        Args:
            symbol: Stock symbol
            db: Database session
        """
        from app.models.database import PriceDataDaily, PriceDataWeekly, Stock

        # Fetch recent data (last 30 days)
        df = self.market_data_collector.fetch_historical_data(symbol, period="1mo")

        if df.empty:
            logger.warning(f"No data retrieved for {symbol}")
            return

        # Get stock from DB
        stock = db.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            logger.warning(f"Stock {symbol} not found in database")
            return

        # Insert/update daily data
        for _, row in df.iterrows():
            existing = (
                db.query(PriceDataDaily)
                .filter(
                    PriceDataDaily.stock_id == stock.id,
                    PriceDataDaily.date == row["date"],
                )
                .first()
            )

            if existing:
                # Update
                existing.open = row["open"]
                existing.high = row["high"]
                existing.low = row["low"]
                existing.close = row["close"]
                existing.volume = row["volume"]
                existing.adjusted_close = row["adjusted_close"]
            else:
                # Insert
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

        # Also update weekly data
        await self.update_weekly_data(stock.id, db)

    async def update_weekly_data(self, stock_id: int, db: Session):
        """Aggregate daily to weekly data"""
        from app.models.database import PriceDataDaily, PriceDataWeekly

        # Get all daily data for this stock
        daily_data = (
            db.query(PriceDataDaily)
            .filter(PriceDataDaily.stock_id == stock_id)
            .order_by(PriceDataDaily.date)
            .all()
        )

        if not daily_data:
            return

        # Convert to DataFrame
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

        # Aggregate to weekly
        weekly_df = aggregate_to_weekly(df)

        # Insert/update weekly data
        for _, row in weekly_df.iterrows():
            existing = (
                db.query(PriceDataWeekly)
                .filter(
                    PriceDataWeekly.stock_id == stock_id,
                    PriceDataWeekly.week_start_date == row["week_start_date"],
                )
                .first()
            )

            if existing:
                existing.open = row["open"]
                existing.high = row["high"]
                existing.low = row["low"]
                existing.close = row["close"]
                existing.volume = row["volume"]
            else:
                weekly_data = PriceDataWeekly(
                    stock_id=stock_id,
                    week_start_date=row["week_start_date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
                db.add(weekly_data)

        db.commit()

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
