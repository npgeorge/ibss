"""
IBSS Management CLI

Provides command-line tools for managing the IBSS database and services.

Usage:
    python scripts/manage.py init-db          # Initialize database
    python scripts/manage.py screen           # Run stock screening
    python scripts/manage.py update-prices    # Update price data
    python scripts/manage.py update-insider   # Update insider transactions
    python scripts/manage.py stats            # Show database statistics
"""
import asyncio
import argparse
import sys
from pathlib import Path
from datetime import date, datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import init_db, get_sync_db
from app.core.repository import StockRepository, ScreeningRepository, InsiderRepository
from app.services.data_scheduler import DataUpdateScheduler
from app.services.screener import SuperstockScreener, ScreeningCriteria
from app.services.insider_parser import SECEdgarInsiderParser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cmd_init_db():
    """Initialize the database"""
    logger.info("Initializing database...")
    init_db()
    logger.info("✓ Database initialized successfully")


async def cmd_screen(min_score: float = 70.0):
    """Run stock screening"""
    logger.info(f"Running stock screening (min score: {min_score})...")

    with get_sync_db() as db:
        stock_repo = StockRepository(db)
        screening_repo = ScreeningRepository(db)
        insider_repo = InsiderRepository(db)

        # Get all stocks
        stocks = stock_repo.get_all_active_stocks()
        logger.info(f"Screening {len(stocks)} stocks...")

        criteria = ScreeningCriteria(min_total_score=min_score)
        screener = SuperstockScreener(criteria)

        scored_stocks = []

        for stock in stocks:
            try:
                # Get price data
                price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=365)
                if price_df.empty or len(price_df) < 50:
                    continue

                # Get insider transactions
                insider_trans = insider_repo.get_transactions_by_stock(stock.id, days=90)
                insider_transactions = [
                    {
                        "insider_name": t.insider_name,
                        "insider_title": t.insider_title or "Unknown",
                        "transaction_date": t.transaction_date,
                        "transaction_type": t.transaction_type,
                        "shares": t.shares,
                        "price_per_share": float(t.price_per_share or 0),
                        "total_value": float(t.total_value or 0),
                        "shares_owned_after": t.shares_owned_after or 0,
                    }
                    for t in insider_trans
                ]

                stock_info = {
                    "symbol": stock.symbol,
                    "company_name": stock.company_name,
                    "sector": stock.sector,
                    "market_cap": stock.market_cap,
                }

                # Screen
                score = screener.screen_stock(price_df, stock_info, None, insider_transactions)

                if score:
                    scored_stocks.append((stock, score))

            except Exception as e:
                logger.error(f"Error screening {stock.symbol}: {e}")

        # Sort by score
        scored_stocks.sort(key=lambda x: x[1].total_score, reverse=True)

        # Save results
        for rank, (stock, score) in enumerate(scored_stocks, 1):
            screening_repo.save_screening_result({
                "stock_id": stock.id,
                "screen_date": date.today(),
                "technical_score": score.technical_score,
                "fundamental_score": score.fundamental_score,
                "insider_score": score.insider_score,
                "pattern_score": score.pattern_score,
                "total_score": score.total_score,
                "rank": rank,
                "score_breakdown": score.score_breakdown,
            })

        logger.info(f"✓ Screening complete: {len(scored_stocks)} stocks scored")

        # Show top 10
        logger.info("\n=== Top 10 Superstocks ===")
        for i, (stock, score) in enumerate(scored_stocks[:10], 1):
            logger.info(
                f"{i}. {stock.symbol:6} - {score.total_score:.1f} "
                f"(T:{score.technical_score:.0f} F:{score.fundamental_score:.0f} I:{score.insider_score:.0f})"
            )


async def cmd_update_prices():
    """Update stock prices"""
    logger.info("Updating stock prices...")

    scheduler = DataUpdateScheduler()
    await scheduler.update_all_stock_prices()

    logger.info("✓ Price update complete")


async def cmd_update_insider():
    """Update insider transactions"""
    logger.info("Updating insider transactions...")

    scheduler = DataUpdateScheduler()
    await scheduler.check_insider_filings()

    logger.info("✓ Insider update complete")


async def cmd_stats():
    """Show database statistics"""
    from app.models.database import Stock, PriceDataDaily, InsiderTransaction, Pattern, ScreeningResult

    with get_sync_db() as db:
        stock_count = db.query(Stock).filter(Stock.is_active == True).count()
        price_count = db.query(PriceDataDaily).count()
        insider_count = db.query(InsiderTransaction).count()
        pattern_count = db.query(Pattern).filter(Pattern.status == 'active').count()
        screening_count = db.query(ScreeningResult).count()

        # Get latest screening
        latest_screen = (
            db.query(ScreeningResult.screen_date)
            .order_by(ScreeningResult.screen_date.desc())
            .first()
        )

        logger.info("\n=== IBSS Database Statistics ===")
        logger.info(f"Active Stocks:       {stock_count:>8}")
        logger.info(f"Price Records:       {price_count:>8}")
        logger.info(f"Insider Transactions:{insider_count:>8}")
        logger.info(f"Active Patterns:     {pattern_count:>8}")
        logger.info(f"Screening Results:   {screening_count:>8}")

        if latest_screen:
            logger.info(f"Latest Screening:    {latest_screen[0]}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="IBSS Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init-db
    subparsers.add_parser("init-db", help="Initialize database")

    # screen
    screen_parser = subparsers.add_parser("screen", help="Run stock screening")
    screen_parser.add_argument("--min-score", type=float, default=70.0,
                              help="Minimum total score")

    # update-prices
    subparsers.add_parser("update-prices", help="Update stock prices")

    # update-insider
    subparsers.add_parser("update-insider", help="Update insider transactions")

    # stats
    subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run command
    if args.command == "init-db":
        asyncio.run(cmd_init_db())
    elif args.command == "screen":
        asyncio.run(cmd_screen(args.min_score))
    elif args.command == "update-prices":
        asyncio.run(cmd_update_prices())
    elif args.command == "update-insider":
        asyncio.run(cmd_update_insider())
    elif args.command == "stats":
        asyncio.run(cmd_stats())


if __name__ == "__main__":
    main()
