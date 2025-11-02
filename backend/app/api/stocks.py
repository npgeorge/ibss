"""
Stock Data API Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.repository import (
    StockRepository, PatternRepository, InsiderRepository,
    FundamentalRepository, ScreeningRepository
)
from app.services.magic_line import MagicLineDetector
from app.services.pattern_recognition import PatternRecognizer
from app.services.screener import SuperstockScorer
from app.services.technical_indicators import TechnicalIndicatorCalculator

router = APIRouter()


class MagicLineInfo(BaseModel):
    """Magic Line information for a stock"""

    symbol: str
    period: int  # weeks
    current_price: float
    magic_line_value: float
    distance_percent: float
    respect_score: float
    bounces: int
    last_touch_date: Optional[str] = None


class PatternInfo(BaseModel):
    """Detected pattern information"""

    pattern_type: str
    strength_score: float
    confidence: float
    detected_date: str
    entry_point: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    status: str
    notes: str = ""


class TechnicalIndicators(BaseModel):
    """Technical indicators"""

    sma_8w: Optional[float] = None
    sma_10w: Optional[float] = None
    sma_12w: Optional[float] = None
    sma_14w: Optional[float] = None
    sma_20d: Optional[float] = None
    sma_50d: Optional[float] = None
    sma_200d: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    volume_avg_20d: Optional[int] = None
    volume_ratio: Optional[float] = None


class StockProfile(BaseModel):
    """Complete stock profile"""

    symbol: str
    company_name: str
    sector: str
    industry: str
    price: float
    volume: int
    market_cap: int

    # Analysis
    magic_line: MagicLineInfo
    patterns: List[PatternInfo]
    technical_indicators: TechnicalIndicators

    # Scores
    technical_score: float
    fundamental_score: float
    insider_score: float
    total_score: float

    # Summary
    recommendation: str
    risk_level: str


@router.get("/{symbol}", response_model=StockProfile)
async def get_stock_profile(symbol: str, db: Session = Depends(get_db)):
    """
    Get complete stock profile with full analysis

    Returns comprehensive Superstock analysis including:
    - Magic Line detection
    - Pattern recognition
    - Technical indicators
    - Composite scoring
    - Buy/sell recommendation
    """
    try:
        symbol = symbol.upper()

        # Get repositories
        stock_repo = StockRepository(db)
        pattern_repo = PatternRepository(db)
        insider_repo = InsiderRepository(db)
        fundamental_repo = FundamentalRepository(db)

        # Get stock
        stock = stock_repo.get_stock_by_symbol(symbol)
        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        # Get price data
        price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=365)
        if price_df.empty or len(price_df) < 50:
            raise HTTPException(status_code=400, detail=f"Insufficient price data for {symbol}")

        # Get current price and volume
        latest = price_df.iloc[-1]
        current_price = float(latest["close"])
        current_volume = int(latest["volume"])

        # Magic Line Detection
        ml_detector = MagicLineDetector(price_df)
        ml_result = ml_detector.find_magic_line()

        magic_line = MagicLineInfo(
            symbol=symbol,
            period=ml_result.period,
            current_price=current_price,
            magic_line_value=ml_result.magic_line_value,
            distance_percent=ml_result.distance_percent,
            respect_score=ml_result.score,
            bounces=ml_result.bounces,
            last_touch_date=ml_result.last_touch_date,
        )

        # Pattern Recognition
        recognizer = PatternRecognizer(price_df)
        detected_patterns = recognizer.detect_all_patterns()

        patterns = [
            PatternInfo(
                pattern_type=p.pattern_type,
                strength_score=p.strength_score,
                confidence=p.confidence,
                detected_date=str(p.pattern_end_date or date.today()),
                entry_point=p.entry_price,
                stop_loss=p.stop_loss,
                target_price=p.target_price,
                status="active",
                notes=p.notes,
            )
            for p in detected_patterns
        ]

        # Technical Indicators
        indicator_calc = TechnicalIndicatorCalculator(price_df)
        indicators_dict = indicator_calc.get_latest_indicators()

        technical_indicators = TechnicalIndicators(**indicators_dict)

        # Get fundamentals
        fundamentals_obj = fundamental_repo.get_latest_fundamentals(stock.id)
        fundamentals = None
        if fundamentals_obj:
            fundamentals = {
                "eps_growth_yoy": 0,  # Placeholder
                "revenue_growth_yoy": 0,
                "peg_ratio": float(fundamentals_obj.peg_ratio or 0),
                "pe_ratio": float(fundamentals_obj.pe_ratio or 0),
            }

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

        # Calculate composite score
        stock_info = {
            "symbol": symbol,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "market_cap": stock.market_cap,
        }

        scorer = SuperstockScorer(price_df, stock_info, fundamentals, insider_transactions)
        score = scorer.calculate_composite_score()

        # Generate recommendation
        recommendation = "NEUTRAL"
        risk_level = "MEDIUM"

        if score.total_score >= 85:
            recommendation = "STRONG BUY"
            risk_level = "LOW"
        elif score.total_score >= 75:
            recommendation = "BUY"
            risk_level = "MEDIUM"
        elif score.total_score >= 60:
            recommendation = "HOLD"
            risk_level = "MEDIUM"
        elif score.total_score >= 50:
            recommendation = "WATCH"
            risk_level = "HIGH"
        else:
            recommendation = "AVOID"
            risk_level = "HIGH"

        # Check for sell signals
        if ml_detector.check_magic_line_violation(ml_result.period):
            recommendation = "SELL"
            risk_level = "HIGH"

        return StockProfile(
            symbol=symbol,
            company_name=stock.company_name,
            sector=stock.sector or "Unknown",
            industry=stock.industry or "Unknown",
            price=current_price,
            volume=current_volume,
            market_cap=stock.market_cap or 0,
            magic_line=magic_line,
            patterns=patterns,
            technical_indicators=technical_indicators,
            technical_score=score.technical_score,
            fundamental_score=score.fundamental_score,
            insider_score=score.insider_score,
            total_score=score.total_score,
            recommendation=recommendation,
            risk_level=risk_level,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing {symbol}: {str(e)}")


@router.get("/{symbol}/magic-line", response_model=MagicLineInfo)
async def get_magic_line(symbol: str, db: Session = Depends(get_db)):
    """
    Get Magic Line information for a stock

    The Magic Line is the key support level (moving average)
    that the stock respects most consistently
    """
    try:
        symbol = symbol.upper()

        stock_repo = StockRepository(db)
        stock = stock_repo.get_stock_by_symbol(symbol)

        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        # Get price data
        price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=365)
        if price_df.empty:
            raise HTTPException(status_code=400, detail=f"No price data for {symbol}")

        # Detect Magic Line
        ml_detector = MagicLineDetector(price_df)
        ml_result = ml_detector.find_magic_line()

        current_price = float(price_df.iloc[-1]["close"])

        return MagicLineInfo(
            symbol=symbol,
            period=ml_result.period,
            current_price=current_price,
            magic_line_value=ml_result.magic_line_value,
            distance_percent=ml_result.distance_percent,
            respect_score=ml_result.score,
            bounces=ml_result.bounces,
            last_touch_date=ml_result.last_touch_date,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating magic line: {str(e)}")


@router.get("/{symbol}/patterns", response_model=List[PatternInfo])
async def get_patterns(symbol: str, db: Session = Depends(get_db)):
    """
    Get detected chart patterns for a stock

    Detects 5 key patterns:
    - Staircase (higher lows/highs)
    - Cup & Handle
    - Flat Base
    - Flag
    - Breakout
    """
    try:
        symbol = symbol.upper()

        stock_repo = StockRepository(db)
        stock = stock_repo.get_stock_by_symbol(symbol)

        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        # Get price data
        price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=180)
        if price_df.empty:
            raise HTTPException(status_code=400, detail=f"No price data for {symbol}")

        # Detect patterns
        recognizer = PatternRecognizer(price_df)
        detected = recognizer.detect_all_patterns()

        return [
            PatternInfo(
                pattern_type=p.pattern_type,
                strength_score=p.strength_score,
                confidence=p.confidence,
                detected_date=str(p.pattern_end_date or date.today()),
                entry_point=p.entry_price,
                stop_loss=p.stop_loss,
                target_price=p.target_price,
                status="active",
                notes=p.notes,
            )
            for p in detected
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting patterns: {str(e)}")


@router.get("/{symbol}/technical-indicators", response_model=TechnicalIndicators)
async def get_technical_indicators(symbol: str, db: Session = Depends(get_db)):
    """
    Get technical indicators for a stock

    Includes:
    - Moving averages (multiple timeframes)
    - RSI (Relative Strength Index)
    - MACD
    - Volume indicators
    """
    try:
        symbol = symbol.upper()

        stock_repo = StockRepository(db)
        stock = stock_repo.get_stock_by_symbol(symbol)

        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        # Get price data
        price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=365)
        if price_df.empty:
            raise HTTPException(status_code=400, detail=f"No price data for {symbol}")

        # Calculate indicators
        indicator_calc = TechnicalIndicatorCalculator(price_df)
        indicators_dict = indicator_calc.get_latest_indicators()

        return TechnicalIndicators(**indicators_dict)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating indicators: {str(e)}")
