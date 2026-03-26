"""
Stock Screener API Endpoints

Live pipeline: Finviz pre-filter → batch yfinance → score → rank
No DB dependency for scanning — fetches everything live.

Caching: Results are cached in Redis for 15 minutes. The first request
triggers a background pipeline run; subsequent requests serve cached data.
"""
import asyncio
import json
import logging
import time
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.screener import (
    run_full_pipeline,
    ScreeningCriteria,
    StockScore,
)
from app.services.finviz_screener import ScanMode

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory cache (Redis optional — falls back to dict)
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 900  # 15 minutes
_pipeline_running = False


def _get_cached(key: str) -> Optional[list]:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None


def _set_cached(key: str, data: list):
    _cache[key] = {"data": data, "ts": time.time()}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

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

    # Pipeline mode
    scan_mode: str = "standard"  # quick, standard, deep


class StockScreenResult(BaseModel):
    """Individual stock screening result"""

    symbol: str
    company_name: str = ""
    sector: str = "Unknown"
    price: float = 0.0
    market_cap: int = 0

    # Scores
    technical_score: float = 0.0
    fundamental_score: float = 0.0
    insider_score: float = 0.0
    pattern_score: float = 0.0
    total_score: float = 0.0
    rank: Optional[int] = None

    # Details
    patterns: List[str] = []
    magic_line_period: Optional[int] = None
    magic_line_distance: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None

    # New fields
    volume_signal: Optional[str] = None
    entry_recommendation: Optional[str] = None

    class Config:
        from_attributes = True


class QuickScanResult(BaseModel):
    """Quick scan results"""

    magic_line_touches: List[dict] = []
    breakouts: List[dict] = []
    high_volume: List[dict] = []
    insider_cluster_buys: List[dict] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_result(score: StockScore) -> StockScreenResult:
    """Convert internal StockScore to API response model"""
    breakdown = score.score_breakdown or {}
    patterns_info = breakdown.get("patterns", {})
    tech_info = breakdown.get("technical", {})

    return StockScreenResult(
        symbol=score.symbol,
        company_name=breakdown.get("fundamental", {}).get("company_name", score.symbol),
        sector="Unknown",
        price=0.0,  # Price is in the score breakdown if needed
        market_cap=0,
        technical_score=score.technical_score,
        fundamental_score=score.fundamental_score,
        insider_score=score.insider_score,
        pattern_score=score.pattern_score,
        total_score=score.total_score,
        rank=score.rank,
        patterns=score.patterns_detected or [],
        magic_line_period=score.magic_line_period,
        magic_line_distance=score.magic_line_distance,
        entry_price=score.entry_price,
        stop_loss=score.stop_loss,
        target_price=score.target_price,
        volume_signal=score.volume_signal,
        entry_recommendation=score.entry_recommendation,
    )


def _criteria_from_request(req: ScreenerCriteriaRequest) -> ScreeningCriteria:
    return ScreeningCriteria(
        price_min=req.price_min,
        price_max=req.price_max,
        volume_min=req.volume_min,
        magic_line_respect=req.magic_line_respect,
        magic_line_min_score=req.magic_line_min_score,
        earnings_growth_min=req.earnings_growth_min,
        revenue_growth_min=req.revenue_growth_min,
        pe_ratio_max=req.pe_ratio_max,
        market_cap_min=req.market_cap_min,
        market_cap_max=req.market_cap_max,
        insider_buying_days=req.insider_buying_days,
        min_insider_transactions=req.min_insider_transactions,
        min_total_score=req.min_total_score,
    )


def _parse_scan_mode(mode_str: str) -> ScanMode:
    try:
        return ScanMode(mode_str.lower())
    except ValueError:
        return ScanMode.STANDARD


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=List[StockScreenResult])
async def screen_stocks(
    criteria: ScreenerCriteriaRequest,
    limit: int = Query(100, le=1000),
):
    """
    Screen stocks using the live pipeline.

    Finviz pre-filter → batch yfinance fetch → score → rank.
    No database required — everything fetched live.
    """
    try:
        screening_criteria = _criteria_from_request(criteria)
        mode = _parse_scan_mode(criteria.scan_mode)

        scored = await run_full_pipeline(
            criteria=screening_criteria,
            mode=mode,
        )

        results = [_score_to_result(s) for s in scored[:limit]]
        return results

    except Exception as e:
        logger.exception("Screening error")
        raise HTTPException(status_code=500, detail=f"Screening error: {str(e)}")


@router.post("/stream")
async def screen_stocks_stream(
    criteria: ScreenerCriteriaRequest,
    limit: int = Query(100, le=1000),
):
    """
    Stream screening progress via Server-Sent Events.

    Sends progress events during the pipeline, then the final results.
    """
    screening_criteria = _criteria_from_request(criteria)
    mode = _parse_scan_mode(criteria.scan_mode)

    async def event_generator():
        progress_events = []

        async def on_progress(stage: str, pct: int, msg: str):
            event = {"stage": stage, "percent": pct, "message": msg}
            progress_events.append(event)
            yield f"data: {json.dumps(event)}\n\n"

        # We can't yield from inside the callback directly with run_full_pipeline,
        # so we collect progress and stream results after.
        results = []
        try:
            scored = await run_full_pipeline(
                criteria=screening_criteria,
                mode=mode,
            )
            results = [_score_to_result(s) for s in scored[:limit]]
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Send final results
        for r in results:
            yield f"data: {json.dumps({'result': r.model_dump()})}\n\n"

        yield f"data: {json.dumps({'done': True, 'total': len(results)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("/quick-scan", response_model=QuickScanResult)
async def quick_scan():
    """
    Quick scan for immediate opportunities using the live pipeline.

    Runs a QUICK mode Finviz pre-filter, batch fetches, and looks for:
    - Magic Line touches
    - Volume surges
    - Insider cluster buys
    """
    from app.services.magic_line import MagicLineDetector
    from app.services.market_data import YahooFinanceCollector
    from app.services.finviz_screener import FinvizPreFilter
    from app.services.openinsider import OpenInsiderScraper

    try:
        result = QuickScanResult()

        # Step 1: Finviz quick filter
        prefilter = FinvizPreFilter()
        pf = await prefilter.get_prefiltered_symbols(ScanMode.QUICK)

        if not pf.symbols:
            return result

        # Step 2: Batch fetch prices
        price_map = YahooFinanceCollector.batch_fetch_historical_data(
            pf.symbols[:50], period="6mo"
        )

        # Step 3: Scan for signals
        for sym, pdf in price_map.items():
            if len(pdf) < 50:
                continue

            current_price = float(pdf.iloc[-1]["close"])
            current_volume = int(pdf.iloc[-1]["volume"])

            # Magic Line touch
            try:
                ml = MagicLineDetector(pdf)
                if ml.is_touching_magic_line(tolerance=0.03):
                    ml_result = ml.find_magic_line()
                    result.magic_line_touches.append({
                        "symbol": sym,
                        "price": current_price,
                        "magic_line": float(ml_result.magic_line_value),
                        "distance_pct": float(ml_result.distance_percent),
                    })
            except Exception:
                pass

            # High volume
            avg_volume = pdf.tail(20)["volume"].mean()
            if avg_volume > 0 and current_volume > avg_volume * 2.0:
                result.high_volume.append({
                    "symbol": sym,
                    "price": current_price,
                    "volume": current_volume,
                    "avg_volume": int(avg_volume),
                    "volume_ratio": round(current_volume / avg_volume, 2),
                })

        # Step 4: Insider cluster buys
        try:
            async with OpenInsiderScraper() as scraper:
                clusters = await scraper.fetch_recent_cluster_buys(days=30)
                for sym, txns in list(clusters.items())[:10]:
                    purchases = [t for t in txns if t.is_purchase]
                    if purchases:
                        result.insider_cluster_buys.append({
                            "symbol": sym,
                            "num_insiders": len(set(t.insider_name for t in purchases)),
                            "total_value": sum(t.total_value for t in purchases),
                        })
        except Exception as e:
            logger.error(f"OpenInsider quick-scan failed: {e}")

        return result

    except Exception as e:
        logger.exception("Quick scan error")
        raise HTTPException(status_code=500, detail=f"Quick scan error: {str(e)}")


async def _run_pipeline_background():
    """Run the screening pipeline and cache results."""
    global _pipeline_running
    if _pipeline_running:
        return
    _pipeline_running = True
    try:
        logger.info("Background pipeline starting...")
        scored = await run_full_pipeline(
            criteria=ScreeningCriteria(min_total_score=50.0),
            mode=ScanMode.QUICK,
            max_symbols=50,
        )
        results = [_score_to_result(s) for s in scored]
        _set_cached("top_opportunities", results)
        logger.info(f"Background pipeline done: {len(results)} results cached")
    except Exception as e:
        logger.exception(f"Background pipeline failed: {e}")
    finally:
        _pipeline_running = False


@router.get("/top-opportunities", response_model=List[StockScreenResult])
async def get_top_opportunities(
    limit: int = Query(10, le=50),
    background_tasks: BackgroundTasks = None,
):
    """
    Return highest-scoring stocks from cache. Triggers a background
    refresh if cache is empty or stale. Returns empty list immediately
    if no cached data yet (frontend shows loading state).
    """
    cached = _get_cached("top_opportunities")
    if cached is not None:
        return cached[:limit]

    # No cache — trigger background pipeline and return empty for now
    if not _pipeline_running:
        background_tasks.add_task(_run_pipeline_background)

    return []


@router.get("/status")
async def pipeline_status():
    """Check if the screening pipeline is currently running."""
    cached = _get_cached("top_opportunities")
    return {
        "pipeline_running": _pipeline_running,
        "cache_available": cached is not None,
        "cached_results": len(cached) if cached else 0,
    }
