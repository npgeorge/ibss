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
from datetime import datetime, timezone
from typing import Optional, List, Dict

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    import redis as _redis_lib
except ImportError:  # pragma: no cover — redis is an optional dependency
    _redis_lib = None

from app.services.screener import (
    run_full_pipeline,
    ScreeningCriteria,
    StockScore,
    SuperstockScorer,
)
from app.services.finviz_screener import ScanMode
from app.core.config import settings
from app.core.database import get_sync_db
from app.core.repository import ScreeningRepository, StockRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Two-tier cache: in-memory dict (fast) write-through to Redis (durable).
#
# The in-memory tier is wiped on every backend reload/restart, which is why
# scan results "disappeared" — an expensive weekly AI scan must not be lost to
# a code reload. Redis (already provisioned) is the durable tier: writes go to
# both, and a cold in-memory cache reads back from Redis and repopulates. If
# Redis is unavailable the cache degrades gracefully to in-memory only.
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 900  # 15 minutes
# AI-sector scans run on a weekly cadence and only when explicitly requested,
# so the cached result must outlive the short opportunities TTL.
AI_CACHE_TTL = 14 * 24 * 3600  # 14 days
_pipeline_running = False
_ai_scan_running = False

_REDIS_KEY_PREFIX = "ibss:cache:"
_redis_client = None
_redis_unavailable = False


def _get_redis():
    """Lazily connect to Redis. Returns None (and disables further attempts)
    if the library is missing or the server can't be reached, so the cache
    falls back to in-memory only."""
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    if _redis_lib is None:
        _redis_unavailable = True
        return None
    try:
        client = _redis_lib.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        return client
    except Exception as e:  # noqa: BLE001 — any failure means "no Redis"
        logger.warning("Redis cache unavailable (%s); using in-memory cache only", e)
        _redis_unavailable = True
        return None


def _redis_set(key: str, data: list, ts: float, ttl: float) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        payload = json.dumps({
            "data": [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            "ts": ts,
            "ttl": ttl,
        })
        # Let Redis expire it too (with a small grace margin over the logical ttl).
        client.set(_REDIS_KEY_PREFIX + key, payload, ex=int(ttl) + 60)
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis cache write failed for %s: %s", key, e)


def _redis_get(key: str):
    """Return (data, ts, ttl) from Redis, or None. data is rehydrated into
    StockScreenResult objects so consumers can use attribute access."""
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_REDIS_KEY_PREFIX + key)
        if not raw:
            return None
        env = json.loads(raw)
        ts = env.get("ts", 0)
        ttl = env.get("ttl", CACHE_TTL)
        if time.time() - ts >= ttl:
            return None
        data = [StockScreenResult(**item) for item in env.get("data", [])]
        return data, ts, ttl
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis cache read failed for %s: %s", key, e)
        return None

# Curated AI / AI-adjacent watch list. "AI" is a theme spanning several GICS
# sectors, so there is no clean Finviz industry filter for it — this list is
# hand-maintained across the segments that make up the AI value chain. Scored
# as a discrete sector rather than via the low-priced superstock pre-filter.
AI_SECTOR_SYMBOLS = [
    # Semiconductors & AI compute hardware
    "NVDA", "AMD", "AVGO", "TSM", "ARM", "MRVL", "MU", "SMCI", "INTC",
    "QCOM", "TXN", "ASML", "AMAT", "LRCX", "KLAC", "ALAB", "CRDO", "MPWR",
    "COHR", "LITE",
    # AI networking & data-center infrastructure
    "ANET", "VRT", "DELL", "HPE", "CIEN", "NTAP", "PSTG", "WDC", "STX", "CRWV",
    # AI cloud, platforms & mega-cap operators
    "NBIS", "MSFT", "GOOGL", "AMZN", "META", "ORCL", "IBM", "NOW", "SNOW",
    # AI software, applications & pure-plays
    "PLTR", "AI", "SOUN", "BBAI", "INOD", "TEM", "PATH", "VERI", "DDOG",
    "MDB", "CFLT", "CRWD", "PANW", "S", "PEGA", "GTLB",
    # Quantum computing
    "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ",
    # Autonomy & robotics
    "TSLA", "SERV", "PONY", "AUR", "SYM", "WRD", "KSCP",
    # Lidar & perception sensors
    "OUST", "LAZR", "INVZ", "AEVA", "MVIS", "LIDR", "INDI",
    # AI drug discovery & healthcare AI
    "RXRX", "SDGR", "ABCL",
]


def _get_cached(key: str) -> Optional[list]:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < entry.get("ttl", CACHE_TTL):
        return entry["data"]
    # Cold in-memory tier (e.g. after a reload) — fall back to Redis and
    # repopulate the fast tier so subsequent reads stay local.
    redis_entry = _redis_get(key)
    if redis_entry is not None:
        data, ts, ttl = redis_entry
        _cache[key] = {"data": data, "ts": ts, "ttl": ttl}
        return data
    return None


def _set_cached(key: str, data: list, ttl: float = CACHE_TTL):
    ts = time.time()
    _cache[key] = {"data": data, "ts": ts, "ttl": ttl}
    _redis_set(key, data, ts, ttl)


def _cached_at(key: str) -> Optional[float]:
    """Unix timestamp of the last cache write for a key, ignoring TTL."""
    entry = _cache.get(key)
    if entry:
        return entry["ts"]
    redis_entry = _redis_get(key)
    if redis_entry is not None:
        data, ts, ttl = redis_entry
        _cache[key] = {"data": data, "ts": ts, "ttl": ttl}
        return ts
    return None


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

    # Per-sub-law scores (0-100) keyed by law id, for the table breakdown view.
    law_scores: Dict[str, Optional[float]] = {}

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

# Maps each table column (law id) to the detail key the scorer emits inside
# score_breakdown[<group>]. Keep in sync with SuperstockScorer.WEIGHTS.
_LAW_SCORE_KEYS = {
    "technical": {
        "magic_line": "magic_line_score",
        "volume": "volume_score",
        "patterns": "pattern_contribution",
        "relative_strength": "relative_strength_score",
    },
    "fundamental": {
        "earnings_growth": "earnings_score",
        "revenue_growth": "revenue_score",
        "valuation": "valuation_score",
        "share_structure": "share_structure_score",
        "balance_sheet": "balance_sheet_score",
        "analyst_coverage": "analyst_coverage_score",
        "earnings_acceleration": "earnings_acceleration_score",
    },
    "insider": {
        "recent_buying": "recent_buying_score",
        "cluster_buying": "cluster_score",
        "price_trend": "price_trend_score",
    },
}


def _extract_law_scores(breakdown: Optional[Dict]) -> Dict[str, Optional[float]]:
    """Flatten the scorer's nested score_breakdown into a flat law_id -> score map.

    Missing laws map to None so the table can distinguish "scored 0" from
    "not computed". Accepts the raw score_breakdown dict (live or from DB).
    """
    breakdown = breakdown or {}
    law_scores: Dict[str, Optional[float]] = {}
    for group, mapping in _LAW_SCORE_KEYS.items():
        group_details = breakdown.get(group) or {}
        for law_id, detail_key in mapping.items():
            value = group_details.get(detail_key)
            law_scores[law_id] = (
                round(float(value), 2) if isinstance(value, (int, float)) else None
            )
    return law_scores


def _score_to_result(score: StockScore) -> StockScreenResult:
    """Convert internal StockScore to API response model"""
    return StockScreenResult(
        symbol=score.symbol,
        company_name=score.company_name or score.symbol,
        sector=score.sector or "Unknown",
        price=score.current_price or 0.0,
        market_cap=int(score.market_cap or 0),
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
        law_scores=_extract_law_scores(score.score_breakdown),
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


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so events flush live
}


async def _scan_event_stream(
    criteria: ScreeningCriteria,
    mode: ScanMode,
    limit: int,
    persist: bool,
):
    """
    Run the pipeline in a background task and yield SSE events as progress
    arrives. A queue bridges the pipeline's async progress callback to the
    streaming generator so events flush live instead of being buffered.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    async def on_progress(stage: str, pct: int, msg: str):
        await queue.put({"type": "progress", "stage": stage, "percent": pct, "message": msg})

    async def runner():
        try:
            scored = await run_full_pipeline(
                criteria=criteria,
                mode=mode,
                progress_callback=on_progress,
                persist=persist,
            )
            results = [_score_to_result(s) for s in scored[:limit]]
            await queue.put({
                "type": "complete",
                "total": len(results),
                "results": [r.model_dump() for r in results],
            })
        except Exception as e:  # noqa: BLE001 — surface error to the client
            logger.exception("Streaming scan failed")
            await queue.put({"type": "error", "error": str(e)})
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            yield f"data: {json.dumps(item)}\n\n"
    finally:
        if not task.done():
            task.cancel()


@router.post("/run")
async def run_scan(
    criteria: ScreenerCriteriaRequest,
    limit: int = Query(100, le=1000),
    persist: bool = Query(True),
):
    """
    Launch a unified scan and stream progress via Server-Sent Events.

    This is the orchestrated entrypoint: it runs the live pipeline and (by
    default) persists qualifying results to the database, emitting live
    progress events the frontend ScanProgress component can consume.
    """
    screening_criteria = _criteria_from_request(criteria)
    mode = _parse_scan_mode(criteria.scan_mode)
    return StreamingResponse(
        _scan_event_stream(screening_criteria, mode, limit, persist),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/stream")
async def screen_stocks_stream(
    criteria: ScreenerCriteriaRequest,
    limit: int = Query(100, le=1000),
):
    """
    Stream screening progress via Server-Sent Events (no persistence).

    Sends live progress events during the pipeline, then the final results.
    """
    screening_criteria = _criteria_from_request(criteria)
    mode = _parse_scan_mode(criteria.scan_mode)
    return StreamingResponse(
        _scan_event_stream(screening_criteria, mode, limit, persist=False),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
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
    if cached:
        return cached[:limit]

    # No fresh cache — serve the latest persisted results so the dashboard
    # reflects the unified DB that /screen/run writes to.
    db_results = await asyncio.to_thread(_latest_results_from_db, limit)
    if db_results:
        return db_results

    # Nothing persisted yet — trigger a background scan, return empty for now.
    if not _pipeline_running and background_tasks is not None:
        background_tasks.add_task(_run_pipeline_background)

    return []


class AISectorResponse(BaseModel):
    """AI-sector watch results plus group averages for the dashboard section."""

    results: List[StockScreenResult] = []
    averages: dict = {}
    count: int = 0
    scanning: bool = False
    last_scan: Optional[str] = None  # ISO timestamp of the last completed scan


def _ai_averages(results: List[StockScreenResult]) -> dict:
    if not results:
        return {}
    n = len(results)
    return {
        "total_score": round(sum(r.total_score for r in results) / n, 1),
        "technical_score": round(sum(r.technical_score for r in results) / n, 1),
        "fundamental_score": round(sum(r.fundamental_score for r in results) / n, 1),
        "insider_score": round(sum(r.insider_score for r in results) / n, 1),
        "pattern_score": round(sum(r.pattern_score for r in results) / n, 1),
    }


async def _run_ai_scan_background():
    """Score the curated AI watch list and cache it for the dashboard section."""
    global _ai_scan_running
    if _ai_scan_running:
        return
    _ai_scan_running = True
    try:
        logger.info("AI sector scan starting...")
        scored = await run_full_pipeline(
            # Open the gates: AI names span price/cap ranges far outside the
            # low-priced superstock band, so score them all rather than filter.
            criteria=ScreeningCriteria(
                price_min=0.01,
                price_max=1_000_000.0,
                volume_min=0,
                market_cap_min=None,
                market_cap_max=None,
                min_total_score=0.0,
            ),
            symbols=AI_SECTOR_SYMBOLS,
        )
        results = [_score_to_result(s) for s in scored]
        _set_cached("ai_sector", results, ttl=AI_CACHE_TTL)
        logger.info(f"AI sector scan done: {len(results)} results cached")
    except Exception as e:
        logger.exception(f"AI sector scan failed: {e}")
    finally:
        _ai_scan_running = False


def _ai_last_scan_iso() -> Optional[str]:
    ts = _cached_at("ai_sector")
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@router.get("/ai", response_model=AISectorResponse)
async def get_ai_sector():
    """
    Return the most recent AI-sector scan (Nebius, Ouster, and peers) plus group
    averages. This endpoint is passive: it NEVER starts a scan. Scans are
    expensive and run on a weekly cadence, so they are triggered only by an
    explicit POST /ai/run (the dashboard "Scan" button).
    """
    cached = _get_cached("ai_sector") or []
    return AISectorResponse(
        results=cached,
        averages=_ai_averages(cached),
        count=len(cached),
        scanning=_ai_scan_running,
        last_scan=_ai_last_scan_iso(),
    )


@router.post("/ai/run", response_model=AISectorResponse)
async def run_ai_sector(background_tasks: BackgroundTasks):
    """Explicitly start a fresh AI-sector scan (background); returns current state."""
    if not _ai_scan_running:
        background_tasks.add_task(_run_ai_scan_background)
    cached = _get_cached("ai_sector") or []
    return AISectorResponse(
        results=cached,
        averages=_ai_averages(cached),
        count=len(cached),
        scanning=True,
        last_scan=_ai_last_scan_iso(),
    )


def _latest_results_from_db(limit: int) -> List[StockScreenResult]:
    """Map the most recent persisted screening_results to the API response shape."""
    try:
        with get_sync_db() as db:
            screen_repo = ScreeningRepository(db)
            stock_repo = StockRepository(db)
            rows = screen_repo.get_latest_screening_results(min_score=0.0, limit=limit)
            results: List[StockScreenResult] = []
            for r in rows:
                breakdown = r.score_breakdown or {}
                # score_breakdown is the scorer's nested dict, not flat — the
                # entry/stop/target live under "patterns", and the magic line /
                # entry recommendation live under "technical".
                patterns = breakdown.get("patterns") or {}
                technical = breakdown.get("technical") or {}
                entry_signals = technical.get("entry_signals") or {}
                volume = technical.get("volume_analysis") or {}

                # No price column on screening_results; use the latest close.
                latest_price = 0.0
                latest = stock_repo.get_price_data(r.stock_id, limit=1)
                if latest:
                    latest_price = float(latest[0].close or 0)

                results.append(
                    StockScreenResult(
                        symbol=r.stock.symbol,
                        company_name=r.stock.company_name or r.stock.symbol,
                        sector=r.stock.sector or "Unknown",
                        price=latest_price,
                        market_cap=int(r.stock.market_cap or 0),
                        technical_score=float(r.technical_score or 0.0),
                        fundamental_score=float(r.fundamental_score or 0.0),
                        insider_score=float(r.insider_score or 0.0),
                        pattern_score=float(r.pattern_score or 0.0),
                        total_score=float(r.total_score or 0.0),
                        rank=r.rank,
                        patterns=patterns.get("patterns_detected") or [],
                        magic_line_period=technical.get("magic_line_period"),
                        magic_line_distance=technical.get("magic_line_distance"),
                        entry_price=patterns.get("entry_price"),
                        stop_loss=patterns.get("stop_loss"),
                        target_price=patterns.get("target_price"),
                        volume_signal=volume.get("signal"),
                        entry_recommendation=entry_signals.get("recommendation"),
                        law_scores=_extract_law_scores(breakdown),
                    )
                )
            return results
    except Exception as e:
        logger.error(f"Failed to read screening results from DB: {e}")
        return []


@router.get("/scoring-model")
async def get_scoring_model():
    """
    Expose the live scoring model so the Method page documents what the code
    actually does (single source of truth — weights come straight from
    SuperstockScorer, so the docs cannot drift from the scorer).
    """
    return {
        "composite": SuperstockScorer.COMPOSITE_WEIGHTS,
        "weights": SuperstockScorer.WEIGHTS,
        "entry_overlay": {
            "floor_factor": SuperstockScorer.ENTRY_FACTOR_FLOOR,
            "max_factor": round(
                SuperstockScorer.ENTRY_FACTOR_FLOOR + SuperstockScorer.ENTRY_FACTOR_SPAN, 3
            ),
            "dont_chase_distance_pct": SuperstockScorer.DONT_CHASE_DISTANCE_PCT,
        },
        # Recommendation tiers mirror app/api/stocks.py get_stock_profile.
        "recommendation_tiers": [
            {"label": "STRONG BUY", "min_score": 85, "risk": "LOW"},
            {"label": "BUY", "min_score": 75, "risk": "MEDIUM"},
            {"label": "HOLD", "min_score": 60, "risk": "MEDIUM"},
            {"label": "WATCH", "min_score": 50, "risk": "HIGH"},
            {"label": "AVOID", "min_score": 0, "risk": "HIGH"},
        ],
    }


@router.get("/status")
async def pipeline_status():
    """Check if the screening pipeline is currently running."""
    cached = _get_cached("top_opportunities")
    return {
        "pipeline_running": _pipeline_running,
        "cache_available": cached is not None,
        "cached_results": len(cached) if cached else 0,
    }
