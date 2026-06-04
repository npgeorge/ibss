"""
Stock Data API Endpoints
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict, Any
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
from app.services.exit_signals import ExitSignalDetector
from app.services.screener import SuperstockScorer
from app.services.technical_indicators import TechnicalIndicatorCalculator
from app.services.finviz_screener import FinvizDetailFetcher
from app.services.market_data import YahooFinanceCollector
from app.services.openinsider import (
    OpenInsiderScraper,
    InsiderActivitySummary,
    InsiderTransaction as OIInsiderTransaction,
    TransactionType,
)

router = APIRouter()


def _build_insider_summary(symbol: str, db_transactions: list) -> InsiderActivitySummary:
    """
    Convert DB insider-transaction rows into an InsiderActivitySummary so the
    scorer can compute a real insider score on the detail page.

    The scorer expects an InsiderActivitySummary (not a list of dicts); passing
    the raw list silently produced a 0 insider score — the book's #1 signal.
    """
    def _to_dt(d):
        if d is None:
            return datetime.utcnow()
        return datetime(d.year, d.month, d.day) if isinstance(d, date) else d

    def _txn_type(raw: str) -> TransactionType:
        raw = (raw or "").lower()
        if raw in ("purchase", "p", "buy"):
            return TransactionType.PURCHASE
        if raw in ("sale", "s", "sell"):
            return TransactionType.SALE
        return TransactionType.OPTION_EXERCISE

    oi_txns = [
        OIInsiderTransaction(
            filing_date=_to_dt(getattr(t, "filing_date", None)),
            trade_date=_to_dt(t.transaction_date),
            symbol=symbol,
            company="",
            insider_name=t.insider_name or "Unknown",
            insider_title=t.insider_title or "",
            transaction_type=_txn_type(t.transaction_type),
            price=float(t.price_per_share or 0),
            quantity=int(t.shares or 0),
            total_value=float(t.total_value or 0),
            shares_owned=int(t.shares_owned_after or 0),
            delta_owned=0.0,
        )
        for t in db_transactions
    ]

    # Reuse the scraper's summarizer (constructor opens no network session).
    return OpenInsiderScraper()._summarize_activity(symbol, oi_txns)


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


class StockSummary(BaseModel):
    """Stock summary block (matches frontend `Stock`)"""

    id: int
    symbol: str
    company_name: str
    sector: str
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    current_price: Optional[float] = None
    magic_line_period: Optional[int] = None
    is_active: bool = True


class MagicLineProfile(BaseModel):
    """Magic Line block as rendered on the detail page (matches frontend `MagicLineResult`)"""

    period: int
    current_price: float
    magic_line_value: float
    distance_percent: float
    is_above: bool
    respect_rate: float  # 0-100
    bounce_count: int
    total_tests: int
    violation_detected: bool
    recommendation: str


class PatternProfile(BaseModel):
    """Detected pattern as rendered on the detail page (matches frontend `PatternResult`)"""

    pattern_type: str
    strength: float  # 0-1
    start_date: str
    end_date: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    description: str = ""


class TechnicalIndicatorsProfile(BaseModel):
    """Technical indicators as rendered on the detail page (matches frontend `TechnicalIndicators`)"""

    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    volume_ratio: Optional[float] = None
    avg_volume_20d: Optional[int] = None
    relative_strength: Optional[float] = None
    ma_8_week: Optional[float] = None
    ma_10_week: Optional[float] = None
    ma_12_week: Optional[float] = None
    ma_14_week: Optional[float] = None


class InsiderTransactionProfile(BaseModel):
    """Insider transaction row (matches frontend `InsiderTransaction`)"""

    insider_name: str
    insider_title: str
    transaction_date: str
    transaction_type: str  # "BUY" / "SELL"
    shares: int
    price_per_share: float
    total_value: float
    shares_owned_after: int


class StockScoreProfile(BaseModel):
    """Composite score block (matches frontend `StockScore`)"""

    technical_score: float
    fundamental_score: float
    insider_score: float
    pattern_score: float
    total_score: float
    score_breakdown: Dict[str, Any] = {}


class ExitSignalProfile(BaseModel):
    """A single advisory exit signal (matches frontend `ExitSignal`)."""

    signal_type: str  # magic_line_violation | parabolic | stall
    severity: str  # critical | warning | info
    message: str


class StockProfile(BaseModel):
    """Complete stock profile (matches frontend `StockProfile`)"""

    stock: StockSummary
    current_price: float
    price_change_percent: float
    volume: int
    avg_volume: int

    magic_line: MagicLineProfile
    patterns: List[PatternProfile]
    technical_indicators: TechnicalIndicatorsProfile
    insider_transactions: List[InsiderTransactionProfile]
    score: StockScoreProfile

    recommendation: str
    risk_level: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    entry_recommendation: Optional[str] = None
    scale_in_guidance: Optional[str] = None
    exit_signals: List[ExitSignalProfile] = []
    exit_recommendation: Optional[str] = None


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

        # Day-over-day change for the header.
        prev_close = float(price_df["close"].iloc[-2]) if len(price_df) >= 2 else current_price
        price_change_percent = (
            (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
        )

        # Magic Line Detection
        ml_detector = MagicLineDetector(price_df)
        ml_result = ml_detector.find_magic_line()
        violation_detected = ml_detector.check_magic_line_violation(ml_result.period)

        is_above = current_price > ml_result.magic_line_value and ml_result.magic_line_value > 0
        if violation_detected:
            ml_recommendation = "Magic Line violated on consecutive weekly closes — consider exiting."
        elif is_above and ml_result.respect_rate >= 60:
            ml_recommendation = "Holding above a well-respected Magic Line — trend intact."
        elif is_above:
            ml_recommendation = "Trading above the Magic Line — uptrend, but respect rate is modest."
        else:
            ml_recommendation = "Below the Magic Line — wait for a reclaim before entering."

        magic_line = MagicLineProfile(
            period=ml_result.period,
            current_price=current_price,
            magic_line_value=ml_result.magic_line_value,
            distance_percent=ml_result.distance_percent,
            is_above=is_above,
            respect_rate=ml_result.respect_rate,
            bounce_count=ml_result.bounces,
            total_tests=ml_result.total_tests,
            violation_detected=violation_detected,
            recommendation=ml_recommendation,
        )

        # Pattern Recognition
        recognizer = PatternRecognizer(price_df)
        detected_patterns = recognizer.detect_all_patterns()

        patterns = [
            PatternProfile(
                pattern_type=p.pattern_type,
                strength=round((p.strength_score or 0) / 100.0, 4),
                start_date=str(p.pattern_start_date or date.today()),
                end_date=str(p.pattern_end_date or date.today()),
                entry_price=p.entry_price,
                stop_loss=p.stop_loss,
                target_price=p.target_price,
                description=p.notes or p.pattern_type.replace("_", " ").title(),
            )
            for p in detected_patterns
        ]

        # Strongest pattern supplies the top-level entry/exit levels.
        best_pattern = max(
            detected_patterns, key=lambda p: p.strength_score or 0, default=None
        )

        # Technical Indicators (map service keys to the frontend's field names)
        indicator_calc = TechnicalIndicatorCalculator(price_df)
        indicators_dict = indicator_calc.get_latest_indicators()

        technical_indicators = TechnicalIndicatorsProfile(
            rsi_14=indicators_dict.get("rsi_14"),
            macd=indicators_dict.get("macd"),
            macd_signal=indicators_dict.get("macd_signal"),
            macd_histogram=indicators_dict.get("macd_histogram"),
            volume_ratio=indicators_dict.get("volume_ratio"),
            avg_volume_20d=indicators_dict.get("volume_avg_20d"),
            relative_strength=indicators_dict.get("relative_strength"),
            ma_8_week=indicators_dict.get("sma_8w"),
            ma_10_week=indicators_dict.get("sma_10w"),
            ma_12_week=indicators_dict.get("sma_12w"),
            ma_14_week=indicators_dict.get("sma_14w"),
        )

        # Get fundamentals — prefer live Finviz growth, fall back to stored DB row.
        # (Neither growth field is stored on the Fundamental model, so a live
        # quote is the only source of real eps/revenue growth for the detail page.)
        fundamentals_obj = fundamental_repo.get_latest_fundamentals(stock.id)
        finviz_metrics = await FinvizDetailFetcher().fetch_single(symbol)

        fundamentals = None
        if finviz_metrics or fundamentals_obj:
            def _pick(live_val, db_val):
                if live_val is not None:
                    return float(live_val)
                return float(db_val or 0) if db_val is not None else 0.0

            def _live(attr):
                return getattr(finviz_metrics, attr, None) if finviz_metrics else None

            fundamentals = {
                "eps_growth_yoy": float(finviz_metrics.eps_growth_yoy) if finviz_metrics and finviz_metrics.eps_growth_yoy is not None else 0.0,
                "revenue_growth_yoy": float(finviz_metrics.revenue_growth_yoy) if finviz_metrics and finviz_metrics.revenue_growth_yoy is not None else 0.0,
                "peg_ratio": _pick(getattr(finviz_metrics, "peg_ratio", None), getattr(fundamentals_obj, "peg_ratio", None)),
                "pe_ratio": _pick(getattr(finviz_metrics, "pe_ratio", None), getattr(fundamentals_obj, "pe_ratio", None)),
                "float_shares": _live("float_shares"),
                "debt_to_equity": _live("debt_to_equity") if _live("debt_to_equity") is not None else getattr(fundamentals_obj, "debt_to_equity", None),
                "current_ratio": _live("current_ratio") if _live("current_ratio") is not None else getattr(fundamentals_obj, "current_ratio", None),
                "analyst_count": _live("analyst_count"),
                "eps_growth_next_y": _live("eps_growth_next_y"),
            }

        # Get insider transactions and build the summary the scorer expects.
        insider_trans = insider_repo.get_transactions_by_stock(stock.id, days=90)
        insider_activity = _build_insider_summary(symbol, insider_trans)

        def _display_txn_type(raw: str) -> str:
            raw = (raw or "").lower()
            if raw in ("purchase", "p", "buy"):
                return "BUY"
            if raw in ("sale", "s", "sell"):
                return "SELL"
            return (raw or "").upper()

        insider_transactions = [
            InsiderTransactionProfile(
                insider_name=t.insider_name or "Unknown",
                insider_title=t.insider_title or "",
                transaction_date=str(t.transaction_date) if t.transaction_date else "",
                transaction_type=_display_txn_type(t.transaction_type),
                shares=int(t.shares or 0),
                price_per_share=float(t.price_per_share or 0),
                total_value=float(t.total_value or 0),
                shares_owned_after=int(t.shares_owned_after or 0),
            )
            for t in insider_trans
        ]

        # Calculate composite score
        stock_info = {
            "symbol": symbol,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "market_cap": stock.market_cap,
        }

        # Benchmark (SPY) for true relative strength; degrade gracefully on failure.
        benchmark_df = None
        try:
            benchmark_df = (
                await asyncio.to_thread(
                    YahooFinanceCollector.batch_fetch_historical_data, ["SPY"], "1y"
                )
            ).get("SPY")
        except Exception:
            benchmark_df = None

        scorer = SuperstockScorer(
            price_df, stock_info, fundamentals, insider_activity, benchmark_df
        )
        score = scorer.calculate_composite_score()

        # Surface the scorer's RS-vs-SPY (0-100) on the detail page so the
        # displayed "Relative Strength" matches what feeds the composite.
        rs_vs_spy = (score.score_breakdown or {}).get("technical", {}).get(
            "relative_strength_score"
        )
        if rs_vs_spy is not None:
            technical_indicators.relative_strength = round(float(rs_vs_spy), 2)

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

        # Entry-timing gate: don't chase names extended >20% above the Magic Line.
        if getattr(score, "dont_chase", False) and recommendation in ("STRONG BUY", "BUY"):
            recommendation = "WATCH"
            risk_level = "HIGH"

        # Check for sell signals
        if violation_detected:
            recommendation = "SELL"
            risk_level = "HIGH"

        # Advisory exit signals (Magic-Line violation + parabolic + time-stop).
        exit_analysis = ExitSignalDetector(
            price_df,
            symbol=symbol,
            magic_line_distance_pct=ml_result.distance_percent,
            violation_detected=violation_detected,
        ).detect()
        exit_signals = [
            ExitSignalProfile(
                signal_type=s.signal_type,
                severity=s.severity,
                message=s.message,
            )
            for s in exit_analysis.signals
        ]

        avg_volume = indicators_dict.get("volume_avg_20d")
        if not avg_volume:
            avg_volume = int(price_df["volume"].tail(20).mean()) if len(price_df) else current_volume

        stock_summary = StockSummary(
            id=stock.id,
            symbol=symbol,
            company_name=stock.company_name,
            sector=stock.sector or "Unknown",
            industry=stock.industry or "Unknown",
            market_cap=stock.market_cap or 0,
            current_price=current_price,
            magic_line_period=ml_result.period,
            is_active=getattr(stock, "is_active", True),
        )

        score_block = StockScoreProfile(
            technical_score=score.technical_score,
            fundamental_score=score.fundamental_score,
            insider_score=score.insider_score,
            pattern_score=score.pattern_score,
            total_score=score.total_score,
            score_breakdown=score.score_breakdown or {},
        )

        return StockProfile(
            stock=stock_summary,
            current_price=current_price,
            price_change_percent=round(price_change_percent, 2),
            volume=current_volume,
            avg_volume=int(avg_volume),
            magic_line=magic_line,
            patterns=patterns,
            technical_indicators=technical_indicators,
            insider_transactions=insider_transactions,
            score=score_block,
            recommendation=recommendation,
            risk_level=risk_level,
            entry_price=(score.entry_price if score.entry_price is not None
                         else (best_pattern.entry_price if best_pattern else None)),
            stop_loss=(score.stop_loss if score.stop_loss is not None
                       else (best_pattern.stop_loss if best_pattern else None)),
            target_price=(score.target_price if score.target_price is not None
                          else (best_pattern.target_price if best_pattern else None)),
            entry_recommendation=getattr(score, "entry_recommendation", None),
            scale_in_guidance=getattr(score, "scale_in_guidance", None),
            exit_signals=exit_signals,
            exit_recommendation=exit_analysis.recommendation,
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
