"""
Database models using SQLAlchemy ORM
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, BigInteger, Boolean, Date, DateTime,
    DECIMAL, Text, ForeignKey, JSON, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Stock(Base):
    """Stock master table"""
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(100), index=True)
    industry = Column(String(100))
    market_cap = Column(BigInteger, index=True)
    float_shares = Column(BigInteger)
    outstanding_shares = Column(BigInteger)
    magic_line_period = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    price_data_daily = relationship("PriceDataDaily", back_populates="stock", cascade="all, delete-orphan")
    price_data_weekly = relationship("PriceDataWeekly", back_populates="stock", cascade="all, delete-orphan")
    technical_indicators = relationship("TechnicalIndicator", back_populates="stock", cascade="all, delete-orphan")
    earnings = relationship("Earnings", back_populates="stock", cascade="all, delete-orphan")
    fundamentals = relationship("Fundamental", back_populates="stock", cascade="all, delete-orphan")
    insider_transactions = relationship("InsiderTransaction", back_populates="stock", cascade="all, delete-orphan")
    patterns = relationship("Pattern", back_populates="stock", cascade="all, delete-orphan")
    screening_results = relationship("ScreeningResult", back_populates="stock", cascade="all, delete-orphan")


class PriceDataDaily(Base):
    """Daily price data"""
    __tablename__ = "price_data_daily"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    open = Column(DECIMAL(12, 4))
    high = Column(DECIMAL(12, 4))
    low = Column(DECIMAL(12, 4))
    close = Column(DECIMAL(12, 4))
    volume = Column(BigInteger)
    adjusted_close = Column(DECIMAL(12, 4))

    # Relationship
    stock = relationship("Stock", back_populates="price_data_daily")

    __table_args__ = (
        Index("idx_price_daily_stock_date", "stock_id", "date"),
    )


class PriceDataWeekly(Base):
    """Weekly price data (aggregated)"""
    __tablename__ = "price_data_weekly"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    week_start_date = Column(Date, nullable=False)
    open = Column(DECIMAL(12, 4))
    high = Column(DECIMAL(12, 4))
    low = Column(DECIMAL(12, 4))
    close = Column(DECIMAL(12, 4))
    volume = Column(BigInteger)

    # Relationship
    stock = relationship("Stock", back_populates="price_data_weekly")

    __table_args__ = (
        Index("idx_price_weekly_stock_date", "stock_id", "week_start_date"),
    )


class TechnicalIndicator(Base):
    """Technical indicators"""
    __tablename__ = "technical_indicators"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)

    # Moving Averages
    sma_8w = Column(DECIMAL(12, 4))
    sma_10w = Column(DECIMAL(12, 4))
    sma_12w = Column(DECIMAL(12, 4))
    sma_14w = Column(DECIMAL(12, 4))
    sma_20d = Column(DECIMAL(12, 4))
    sma_50d = Column(DECIMAL(12, 4))
    sma_200d = Column(DECIMAL(12, 4))

    # Volume indicators
    volume_avg_20d = Column(BigInteger)
    volume_avg_50d = Column(BigInteger)
    volume_ratio = Column(DECIMAL(6, 2))

    # Momentum indicators
    rsi_14 = Column(DECIMAL(6, 2))
    macd = Column(DECIMAL(12, 4))
    macd_signal = Column(DECIMAL(12, 4))
    macd_histogram = Column(DECIMAL(12, 4))

    # Relative strength
    relative_strength = Column(DECIMAL(8, 4))

    calculated_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    stock = relationship("Stock", back_populates="technical_indicators")

    __table_args__ = (
        Index("idx_technical_stock_date", "stock_id", "date"),
    )


class Earnings(Base):
    """Earnings data"""
    __tablename__ = "earnings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    report_date = Column(Date, nullable=False, index=True)
    fiscal_quarter = Column(String(10))
    fiscal_year = Column(Integer)

    # Earnings metrics
    eps_actual = Column(DECIMAL(10, 4))
    eps_estimated = Column(DECIMAL(10, 4))
    eps_surprise_pct = Column(DECIMAL(6, 2))

    # Revenue metrics
    revenue = Column(BigInteger)
    revenue_estimated = Column(BigInteger)
    revenue_surprise_pct = Column(DECIMAL(6, 2))

    # Growth rates
    eps_growth_yoy = Column(DECIMAL(8, 2))
    eps_growth_qoq = Column(DECIMAL(8, 2))
    revenue_growth_yoy = Column(DECIMAL(8, 2))
    revenue_growth_qoq = Column(DECIMAL(8, 2))

    # Relationship
    stock = relationship("Stock", back_populates="earnings")


class Fundamental(Base):
    """Fundamental metrics"""
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)

    # Valuation
    pe_ratio = Column(DECIMAL(10, 2))
    peg_ratio = Column(DECIMAL(10, 2))
    price_to_sales = Column(DECIMAL(10, 2))
    price_to_book = Column(DECIMAL(10, 2))

    # Profitability
    gross_margin = Column(DECIMAL(6, 2))
    operating_margin = Column(DECIMAL(6, 2))
    net_margin = Column(DECIMAL(6, 2))
    roe = Column(DECIMAL(6, 2))
    roa = Column(DECIMAL(6, 2))

    # Financial health
    debt_to_equity = Column(DECIMAL(10, 2))
    current_ratio = Column(DECIMAL(6, 2))
    quick_ratio = Column(DECIMAL(6, 2))

    # Cash flow
    free_cash_flow = Column(BigInteger)
    operating_cash_flow = Column(BigInteger)

    last_updated = Column(DateTime, default=datetime.utcnow)

    # Relationship
    stock = relationship("Stock", back_populates="fundamentals")


class InsiderTransaction(Base):
    """Insider transactions"""
    __tablename__ = "insider_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)

    filing_date = Column(Date, nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)

    insider_name = Column(String(255), nullable=False)
    insider_title = Column(String(255))
    insider_relationship = Column(String(100))

    transaction_type = Column(String(50), nullable=False, index=True)
    shares = Column(Integer, nullable=False)
    price_per_share = Column(DECIMAL(10, 4))
    total_value = Column(DECIMAL(15, 2))

    shares_owned_after = Column(BigInteger)
    ownership_percent = Column(DECIMAL(6, 3))

    form_type = Column(String(20))
    sec_filing_url = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    stock = relationship("Stock", back_populates="insider_transactions")


class Pattern(Base):
    """Detected patterns"""
    __tablename__ = "patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)

    pattern_type = Column(String(50), nullable=False, index=True)
    detected_date = Column(Date, nullable=False)

    strength_score = Column(DECIMAL(5, 2))
    confidence = Column(DECIMAL(5, 2))

    entry_price = Column(DECIMAL(10, 4))
    stop_loss = Column(DECIMAL(10, 4))
    target_price = Column(DECIMAL(10, 4))

    pattern_start_date = Column(Date)
    pattern_end_date = Column(Date)
    consolidation_days = Column(Integer)

    status = Column(String(20), default="active", index=True)
    triggered_date = Column(Date)

    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    stock = relationship("Stock", back_populates="patterns")


class ScreeningResult(Base):
    """Screening results cache"""
    __tablename__ = "screening_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    screen_date = Column(Date, default=date.today, index=True)

    technical_score = Column(DECIMAL(5, 2))
    fundamental_score = Column(DECIMAL(5, 2))
    insider_score = Column(DECIMAL(5, 2))
    pattern_score = Column(DECIMAL(5, 2))
    total_score = Column(DECIMAL(5, 2), index=True)

    rank = Column(Integer)
    score_breakdown = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    stock = relationship("Stock", back_populates="screening_results")


class DataUpdate(Base):
    """Data update log"""
    __tablename__ = "data_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    update_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    records_processed = Column(Integer)
    records_failed = Column(Integer)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)
    error_message = Column(Text)
