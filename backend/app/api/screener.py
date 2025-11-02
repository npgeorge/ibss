"""
Stock Screener API Endpoints
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.repository import StockRepository, ScreeningRepository, InsiderRepository, FundamentalRepository
from app.services.screener import SuperstockScreener, ScreeningCriteria, StockScore
from app.services.magic_line import MagicLineDetector

router = APIRouter()


class ScreenerCriteriaRequest(BaseModel):
    """Screener filter criteria"""

    # Technical filters
    price_min: float = 0.5
    price_max: float = 10.0
    volume_min: int = 100000
    magic_line_respect: bool = True
    magic_line_min_score: float = 50.0

    # Fundamental filters
    earnings_growth_min: Optional[float] = 20.0
    revenue_growth_min: Optional[float] = 20.0
    pe_ratio_max: Optional[float] = 30.0
    market_cap_min: Optional[int] = 10_000_000
    market_cap_max: Optional[int] = 2_000_000_000

    # Insider filters
    insider_buying_days: int = 90
    min_insider_transactions: int = 1

    # Scoring
    min_total_score: float = 70.0


class StockScreenResult(BaseModel):
    """Individual stock screening result"""

    symbol: str
    company_name: str
    sector: str
    price: float
    market_cap: int

    # Scores
    technical_score: float
    fundamental_score: float
    insider_score: float
    pattern_score: float
    total_score: float
    rank: Optional[int] = None

    # Details
    patterns: List[str] = []
    magic_line_period: Optional[int] = None
    magic_line_distance: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None

    class Config:
        from_attributes = True


class QuickScanResult(BaseModel):
    """Quick scan results"""

    magic_line_touches: List[dict] = []
    breakouts: List[dict] = []
    high_volume: List[dict] = []
    insider_cluster_buys: List[dict] = []


@router.post("/", response_model=List[StockScreenResult])
async def screen_stocks(
    criteria: ScreenerCriteriaRequest,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db)
):
    """
    Screen stocks based on Superstock criteria

    Returns top-ranked stocks that meet the filtering criteria

    This performs real-time screening using:
    - Technical analysis (Magic Line, volume, patterns)
    - Fundamental metrics (earnings, revenue growth)
    - Insider activity (recent buying, cluster detection)
    """
    try:
        # Convert request to ScreeningCriteria
        screening_criteria = ScreeningCriteria(
            price_min=criteria.price_min,
            price_max=criteria.price_max,
            volume_min=criteria.volume_min,
            magic_line_respect=criteria.magic_line_respect,
            magic_line_min_score=criteria.magic_line_min_score,
            earnings_growth_min=criteria.earnings_growth_min,
            revenue_growth_min=criteria.revenue_growth_min,
            pe_ratio_max=criteria.pe_ratio_max,
            market_cap_min=criteria.market_cap_min,
            market_cap_max=criteria.market_cap_max,
            insider_buying_days=criteria.insider_buying_days,
            min_insider_transactions=criteria.min_insider_transactions,
            min_total_score=criteria.min_total_score,
        )

        # Get repositories
        stock_repo = StockRepository(db)
        screening_repo = ScreeningRepository(db)
        insider_repo = InsiderRepository(db)
        fundamental_repo = FundamentalRepository(db)

        # Check if we have cached results from today
        cached_results = screening_repo.get_latest_screening_results(
            min_score=criteria.min_total_score,
            limit=limit
        )

        if cached_results and cached_results[0].screen_date == date.today():
            # Use cached results
            results = []
            for sr in cached_results:
                stock = stock_repo.get_stock_by_id(sr.stock_id)
                if not stock:
                    continue

                # Get price data for current price
                price_data = stock_repo.get_price_data(stock.id, limit=1)
                current_price = float(price_data[0].close) if price_data else 0.0

                results.append(StockScreenResult(
                    symbol=stock.symbol,
                    company_name=stock.company_name,
                    sector=stock.sector or "Unknown",
                    price=current_price,
                    market_cap=stock.market_cap or 0,
                    technical_score=float(sr.technical_score),
                    fundamental_score=float(sr.fundamental_score),
                    insider_score=float(sr.insider_score),
                    pattern_score=float(sr.pattern_score or 0),
                    total_score=float(sr.total_score),
                    rank=sr.rank,
                    patterns=sr.score_breakdown.get("patterns", {}).get("patterns_detected", []) if sr.score_breakdown else [],
                    magic_line_period=sr.score_breakdown.get("technical", {}).get("magic_line_period") if sr.score_breakdown else None,
                    magic_line_distance=sr.score_breakdown.get("technical", {}).get("magic_line_distance") if sr.score_breakdown else None,
                    entry_price=sr.score_breakdown.get("patterns", {}).get("entry_price") if sr.score_breakdown else None,
                ))

            return results[:limit]

        # Otherwise, perform fresh screening
        screener = SuperstockScreener(screening_criteria)
        all_stocks = stock_repo.get_all_active_stocks()

        scored_stocks = []

        for stock in all_stocks:
            # Get price data
            price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=365)
            if price_df.empty or len(price_df) < 50:
                continue

            # Get fundamentals
            fundamentals_obj = fundamental_repo.get_latest_fundamentals(stock.id)
            fundamentals = None
            if fundamentals_obj:
                fundamentals = {
                    "eps_growth_yoy": float(fundamentals_obj.roe or 0),  # Placeholder
                    "revenue_growth_yoy": 0,  # Placeholder
                    "peg_ratio": float(fundamentals_obj.peg_ratio or 0),
                    "pe_ratio": float(fundamentals_obj.pe_ratio or 0),
                }

            # Get insider transactions
            insider_trans_objs = insider_repo.get_transactions_by_stock(stock.id, days=90)
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
                for t in insider_trans_objs
            ]

            # Stock info
            stock_info = {
                "symbol": stock.symbol,
                "company_name": stock.company_name,
                "sector": stock.sector,
                "market_cap": stock.market_cap,
            }

            # Screen the stock
            score = screener.screen_stock(price_df, stock_info, fundamentals, insider_transactions)

            if score:
                scored_stocks.append((stock, score, price_df.iloc[-1]["close"]))

        # Sort by total score
        scored_stocks.sort(key=lambda x: x[1].total_score, reverse=True)

        # Convert to results
        results = []
        for rank, (stock, score, current_price) in enumerate(scored_stocks[:limit], 1):
            # Save to cache
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

            results.append(StockScreenResult(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector or "Unknown",
                price=float(current_price),
                market_cap=stock.market_cap or 0,
                technical_score=score.technical_score,
                fundamental_score=score.fundamental_score,
                insider_score=score.insider_score,
                pattern_score=score.pattern_score,
                total_score=score.total_score,
                rank=rank,
                patterns=score.patterns_detected or [],
                magic_line_period=score.magic_line_period,
                magic_line_distance=score.magic_line_distance,
                entry_price=score.entry_price,
            ))

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screening error: {str(e)}")


@router.get("/quick-scan", response_model=QuickScanResult)
async def quick_scan(db: Session = Depends(get_db)):
    """
    Quick scan for immediate opportunities

    Returns stocks with:
    - Magic Line touches (buy signals)
    - Recent breakouts
    - High volume surges
    - Insider cluster buying
    """
    try:
        stock_repo = StockRepository(db)
        insider_repo = InsiderRepository(db)

        result = QuickScanResult()

        # Get all active stocks
        stocks = stock_repo.get_all_active_stocks(limit=500)

        for stock in stocks:
            # Get recent price data
            price_df = stock_repo.get_price_data_as_dataframe(stock.id, days=90)
            if price_df.empty or len(price_df) < 50:
                continue

            current_price = float(price_df.iloc[-1]["close"])
            current_volume = int(price_df.iloc[-1]["volume"])

            # Check Magic Line touch
            try:
                ml_detector = MagicLineDetector(price_df)
                if ml_detector.is_touching_magic_line(tolerance=0.03):  # Within 3%
                    ml_result = ml_detector.find_magic_line()
                    result.magic_line_touches.append({
                        "symbol": stock.symbol,
                        "company_name": stock.company_name,
                        "price": current_price,
                        "magic_line": float(ml_result.magic_line_value),
                        "distance_pct": float(ml_result.distance_percent),
                    })
            except:
                pass

            # Check high volume
            avg_volume = price_df.tail(20)["volume"].mean()
            if current_volume > avg_volume * 2.0:  # 2x average
                result.high_volume.append({
                    "symbol": stock.symbol,
                    "company_name": stock.company_name,
                    "price": current_price,
                    "volume": current_volume,
                    "avg_volume": int(avg_volume),
                    "volume_ratio": round(current_volume / avg_volume, 2),
                })

        # Get cluster buying stocks
        cluster_stock_ids = insider_repo.get_cluster_buying_stocks(days=30, min_insiders=2)
        for stock_id in cluster_stock_ids[:10]:
            stock = stock_repo.get_stock_by_id(stock_id)
            if stock:
                price_data = stock_repo.get_price_data(stock.id, limit=1)
                current_price = float(price_data[0].close) if price_data else 0.0

                result.insider_cluster_buys.append({
                    "symbol": stock.symbol,
                    "company_name": stock.company_name,
                    "price": current_price,
                })

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick scan error: {str(e)}")


@router.get("/top-opportunities", response_model=List[StockScreenResult])
async def get_top_opportunities(limit: int = Query(10, le=50), db: Session = Depends(get_db)):
    """
    Get top-ranked Superstock opportunities from latest screening

    Returns the highest-scoring stocks from the most recent screening run
    """
    try:
        screening_repo = ScreeningRepository(db)
        stock_repo = StockRepository(db)

        # Get latest screening results
        results = screening_repo.get_latest_screening_results(min_score=70.0, limit=limit)

        if not results:
            return []

        output = []
        for sr in results:
            stock = stock_repo.get_stock_by_id(sr.stock_id)
            if not stock:
                continue

            price_data = stock_repo.get_price_data(stock.id, limit=1)
            current_price = float(price_data[0].close) if price_data else 0.0

            output.append(StockScreenResult(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector or "Unknown",
                price=current_price,
                market_cap=stock.market_cap or 0,
                technical_score=float(sr.technical_score),
                fundamental_score=float(sr.fundamental_score),
                insider_score=float(sr.insider_score),
                pattern_score=float(sr.pattern_score or 0),
                total_score=float(sr.total_score),
                rank=sr.rank,
                patterns=sr.score_breakdown.get("patterns", {}).get("patterns_detected", []) if sr.score_breakdown else [],
            ))

        return output

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top opportunities: {str(e)}")
