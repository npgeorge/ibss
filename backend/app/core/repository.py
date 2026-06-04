"""
Repository Layer for Database Operations

Provides clean interface for database access, separating
business logic from database queries.
"""
from typing import List, Optional, Dict
from datetime import datetime, date, timedelta
from sqlalchemy import desc, and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
import pandas as pd

from app.models.database import (
    Stock, PriceDataDaily, PriceDataWeekly, TechnicalIndicator,
    Earnings, Fundamental, InsiderTransaction, Pattern,
    ScreeningResult, DataUpdate
)

# Columns refreshed on price-data conflicts (OHLCV)
_PRICE_UPDATE_COLS = ("open", "high", "low", "close", "volume")


class StockRepository:
    """Repository for stock-related database operations"""

    def __init__(self, db: Session):
        self.db = db

    def get_stock_by_symbol(self, symbol: str) -> Optional[Stock]:
        """Get stock by symbol"""
        return self.db.query(Stock).filter(Stock.symbol == symbol.upper()).first()

    def get_stock_by_id(self, stock_id: int) -> Optional[Stock]:
        """Get stock by ID"""
        return self.db.query(Stock).filter(Stock.id == stock_id).first()

    def get_all_active_stocks(self, limit: Optional[int] = None) -> List[Stock]:
        """Get all active stocks"""
        query = self.db.query(Stock).filter(Stock.is_active == True)

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_stocks_by_sector(self, sector: str) -> List[Stock]:
        """Get stocks by sector"""
        return (
            self.db.query(Stock)
            .filter(Stock.sector == sector, Stock.is_active == True)
            .all()
        )

    def create_or_update_stock(self, stock_data: Dict) -> Stock:
        """Create or update stock"""
        existing = self.get_stock_by_symbol(stock_data["symbol"])

        if existing:
            # Update
            for key, value in stock_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.last_updated = datetime.utcnow()
            stock = existing
        else:
            # Create
            stock = Stock(**stock_data)
            self.db.add(stock)

        self.db.commit()
        self.db.refresh(stock)
        return stock

    def get_price_data(
        self,
        stock_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None
    ) -> List[PriceDataDaily]:
        """Get price data for a stock"""
        query = (
            self.db.query(PriceDataDaily)
            .filter(PriceDataDaily.stock_id == stock_id)
            .order_by(desc(PriceDataDaily.date))
        )

        if start_date:
            query = query.filter(PriceDataDaily.date >= start_date)
        if end_date:
            query = query.filter(PriceDataDaily.date <= end_date)
        if limit:
            query = query.limit(limit)

        return query.all()

    def get_price_data_as_dataframe(
        self,
        stock_id: int,
        days: int = 365
    ) -> pd.DataFrame:
        """Get price data as pandas DataFrame"""
        start_date = date.today() - timedelta(days=days)

        price_data = (
            self.db.query(PriceDataDaily)
            .filter(
                PriceDataDaily.stock_id == stock_id,
                PriceDataDaily.date >= start_date
            )
            .order_by(PriceDataDaily.date)
            .all()
        )

        if not price_data:
            return pd.DataFrame()

        df = pd.DataFrame([
            {
                "date": p.date,
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
                "volume": p.volume,
                "adjusted_close": float(p.adjusted_close) if p.adjusted_close else float(p.close)
            }
            for p in price_data
        ])

        df = df.set_index("date")
        return df

    def bulk_insert_price_data(self, price_data_list: List[Dict]):
        """Bulk upsert daily price data (idempotent on stock_id+date)"""
        if not price_data_list:
            return

        stmt = pg_insert(PriceDataDaily).values(price_data_list)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "adjusted_close": stmt.excluded.adjusted_close,
            },
        )
        self.db.execute(stmt)
        self.db.commit()

    def bulk_upsert_weekly_data(self, weekly_data_list: List[Dict]):
        """Bulk upsert weekly price data (idempotent on stock_id+week_start_date)"""
        if not weekly_data_list:
            return

        stmt = pg_insert(PriceDataWeekly).values(weekly_data_list)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "week_start_date"],
            set_={c: getattr(stmt.excluded, c) for c in _PRICE_UPDATE_COLS},
        )
        self.db.execute(stmt)
        self.db.commit()

    def get_latest_technical_indicators(self, stock_id: int) -> Optional[TechnicalIndicator]:
        """Get latest technical indicators"""
        return (
            self.db.query(TechnicalIndicator)
            .filter(TechnicalIndicator.stock_id == stock_id)
            .order_by(desc(TechnicalIndicator.date))
            .first()
        )

    def save_technical_indicators(self, indicator_data: Dict) -> TechnicalIndicator:
        """Save technical indicators"""
        indicator = TechnicalIndicator(**indicator_data)
        self.db.add(indicator)
        self.db.commit()
        self.db.refresh(indicator)
        return indicator

    def bulk_upsert_technical_indicators(self, indicator_list: List[Dict]):
        """Bulk upsert technical indicators (idempotent on stock_id+date)"""
        if not indicator_list:
            return

        # Columns to refresh on conflict = every provided column except the keys
        update_cols = {
            k for row in indicator_list for k in row.keys()
        } - {"stock_id", "date", "id"}

        stmt = pg_insert(TechnicalIndicator).values(indicator_list)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "date"],
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
        self.db.execute(stmt)
        self.db.commit()


class InsiderRepository:
    """Repository for insider transaction operations"""

    def __init__(self, db: Session):
        self.db = db

    def get_recent_transactions(
        self,
        stock_id: Optional[int] = None,
        days: int = 90,
        transaction_type: Optional[str] = None
    ) -> List[InsiderTransaction]:
        """Get recent insider transactions"""
        cutoff_date = date.today() - timedelta(days=days)

        query = self.db.query(InsiderTransaction).filter(
            InsiderTransaction.transaction_date >= cutoff_date
        )

        if stock_id:
            query = query.filter(InsiderTransaction.stock_id == stock_id)

        if transaction_type:
            query = query.filter(InsiderTransaction.transaction_type == transaction_type)

        return query.order_by(desc(InsiderTransaction.transaction_date)).all()

    def get_transactions_by_stock(self, stock_id: int, days: int = 90) -> List[InsiderTransaction]:
        """Get insider transactions for a specific stock"""
        cutoff_date = date.today() - timedelta(days=days)

        return (
            self.db.query(InsiderTransaction)
            .filter(
                InsiderTransaction.stock_id == stock_id,
                InsiderTransaction.transaction_date >= cutoff_date
            )
            .order_by(desc(InsiderTransaction.transaction_date))
            .all()
        )

    def bulk_insert_transactions(self, transactions: List[Dict]):
        """Bulk upsert insider transactions (idempotent on stock_id+date+name)"""
        if not transactions:
            return

        # Postgres ON CONFLICT DO UPDATE cannot touch the same target row twice
        # in one statement. An insider can file multiple transactions on the same
        # date, which collide on (stock_id, transaction_date, insider_name), so
        # collapse those to the last occurrence before issuing the upsert.
        deduped: Dict[tuple, Dict] = {}
        for row in transactions:
            key = (row.get("stock_id"), row.get("transaction_date"), row.get("insider_name"))
            deduped[key] = row
        transactions = list(deduped.values())

        update_cols = {
            k for row in transactions for k in row.keys()
        } - {"stock_id", "transaction_date", "insider_name", "id"}

        stmt = pg_insert(InsiderTransaction).values(transactions)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "transaction_date", "insider_name"],
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
        self.db.execute(stmt)
        self.db.commit()

    def get_cluster_buying_stocks(self, days: int = 30, min_insiders: int = 2) -> List[int]:
        """Get stock IDs with cluster buying activity"""
        cutoff_date = date.today() - timedelta(days=days)

        # Query for stocks with multiple buyers
        results = (
            self.db.query(
                InsiderTransaction.stock_id,
                func.count(func.distinct(InsiderTransaction.insider_name)).label('buyer_count')
            )
            .filter(
                InsiderTransaction.transaction_type == 'purchase',
                InsiderTransaction.transaction_date >= cutoff_date
            )
            .group_by(InsiderTransaction.stock_id)
            .having(func.count(func.distinct(InsiderTransaction.insider_name)) >= min_insiders)
            .all()
        )

        return [r.stock_id for r in results]


class PatternRepository:
    """Repository for pattern operations"""

    def __init__(self, db: Session):
        self.db = db

    def get_active_patterns(
        self,
        stock_id: Optional[int] = None,
        pattern_type: Optional[str] = None
    ) -> List[Pattern]:
        """Get active patterns"""
        query = self.db.query(Pattern).filter(Pattern.status == 'active')

        if stock_id:
            query = query.filter(Pattern.stock_id == stock_id)

        if pattern_type:
            query = query.filter(Pattern.pattern_type == pattern_type)

        return query.order_by(desc(Pattern.detected_date)).all()

    def save_pattern(self, pattern_data: Dict) -> Pattern:
        """Save detected pattern"""
        pattern = Pattern(**pattern_data)
        self.db.add(pattern)
        self.db.commit()
        self.db.refresh(pattern)
        return pattern

    def update_pattern_status(self, pattern_id: int, status: str, triggered_date: Optional[date] = None):
        """Update pattern status"""
        pattern = self.db.query(Pattern).filter(Pattern.id == pattern_id).first()

        if pattern:
            pattern.status = status
            if triggered_date:
                pattern.triggered_date = triggered_date
            self.db.commit()


class ScreeningRepository:
    """Repository for screening results"""

    def __init__(self, db: Session):
        self.db = db

    def get_latest_screening_results(
        self,
        min_score: float = 0.0,
        limit: int = 100
    ) -> List[ScreeningResult]:
        """Get latest screening results"""
        latest_date = (
            self.db.query(func.max(ScreeningResult.screen_date))
            .scalar()
        )

        if not latest_date:
            return []

        return (
            self.db.query(ScreeningResult)
            .filter(
                ScreeningResult.screen_date == latest_date,
                ScreeningResult.total_score >= min_score
            )
            .order_by(desc(ScreeningResult.total_score))
            .limit(limit)
            .all()
        )

    def save_screening_result(self, result_data: Dict) -> ScreeningResult:
        """Save screening result"""
        # Check if exists for today
        existing = (
            self.db.query(ScreeningResult)
            .filter(
                ScreeningResult.stock_id == result_data["stock_id"],
                ScreeningResult.screen_date == result_data["screen_date"]
            )
            .first()
        )

        if existing:
            # Update
            for key, value in result_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            result = existing
        else:
            # Create
            result = ScreeningResult(**result_data)
            self.db.add(result)

        self.db.commit()
        self.db.refresh(result)
        return result

    def bulk_save_screening_results(self, results: List[Dict]):
        """Bulk upsert screening results (idempotent on stock_id+screen_date)"""
        if not results:
            return

        update_cols = {
            k for row in results for k in row.keys()
        } - {"stock_id", "screen_date", "id"}

        stmt = pg_insert(ScreeningResult).values(results)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "screen_date"],
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
        self.db.execute(stmt)
        self.db.commit()


class FundamentalRepository:
    """Repository for fundamental data"""

    def __init__(self, db: Session):
        self.db = db

    def get_latest_fundamentals(self, stock_id: int) -> Optional[Fundamental]:
        """Get latest fundamental data"""
        return (
            self.db.query(Fundamental)
            .filter(Fundamental.stock_id == stock_id)
            .order_by(desc(Fundamental.date))
            .first()
        )

    def get_latest_earnings(self, stock_id: int, quarters: int = 4) -> List[Earnings]:
        """Get latest earnings reports"""
        return (
            self.db.query(Earnings)
            .filter(Earnings.stock_id == stock_id)
            .order_by(desc(Earnings.report_date))
            .limit(quarters)
            .all()
        )

    def save_earnings(self, earnings_data: Dict) -> Earnings:
        """Save earnings report"""
        earnings = Earnings(**earnings_data)
        self.db.add(earnings)
        self.db.commit()
        self.db.refresh(earnings)
        return earnings
