"""
Market Conditions API

Surfaces the market-timing engine (Jesse Stine's Entry Law #6: SPY trend, VIX
regime, breadth) so the dashboard can show a market-regime banner and the user
can judge whether the environment favors new positions.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.market_conditions import (
    check_market_conditions,
    get_market_warning_message,
    MarketConditions,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class TrendSummary(BaseModel):
    symbol: str
    current_price: float
    sma_50: float
    sma_200: float
    above_sma_50: bool
    above_sma_200: bool
    distance_from_50sma_pct: float
    trend: str
    score: float


class VixSummary(BaseModel):
    current_vix: float
    regime: str
    score: float
    is_favorable: bool


class MarketConditionsResponse(BaseModel):
    regime: str  # risk_on | neutral | risk_off | crisis
    overall_score: float
    market_favorable: bool
    should_be_aggressive: bool
    should_be_defensive: bool
    warning_message: Optional[str] = None
    warnings: List[str] = []
    spy: Optional[TrendSummary] = None
    vix: Optional[VixSummary] = None
    timestamp: str


def _serialize(conditions: MarketConditions) -> MarketConditionsResponse:
    spy = None
    if conditions.spy_trend:
        t = conditions.spy_trend
        spy = TrendSummary(
            symbol=t.symbol,
            current_price=t.current_price,
            sma_50=t.sma_50,
            sma_200=t.sma_200,
            above_sma_50=t.above_sma_50,
            above_sma_200=t.above_sma_200,
            distance_from_50sma_pct=t.distance_from_50sma_pct,
            trend=t.trend,
            score=t.score,
        )

    vix = None
    if conditions.vix_analysis:
        v = conditions.vix_analysis
        vix = VixSummary(
            current_vix=v.current_vix,
            regime=v.regime,
            score=v.score,
            is_favorable=v.is_favorable,
        )

    return MarketConditionsResponse(
        regime=conditions.regime,
        overall_score=conditions.overall_score,
        market_favorable=conditions.market_favorable,
        should_be_aggressive=conditions.should_be_aggressive,
        should_be_defensive=conditions.should_be_defensive,
        warning_message=get_market_warning_message(conditions),
        warnings=conditions.warnings,
        spy=spy,
        vix=vix,
        timestamp=conditions.timestamp.isoformat(),
    )


@router.get("/conditions", response_model=MarketConditionsResponse)
async def get_market_conditions():
    """
    Assess the current market environment (SPY trend + VIX regime).

    Used to annotate recommendations and render a regime banner. On data-fetch
    failure the analyzer returns neutral conditions rather than erroring, so the
    dashboard never blocks on this.
    """
    try:
        conditions = await check_market_conditions()
        return _serialize(conditions)
    except Exception as e:
        logger.exception("Market conditions check failed")
        raise HTTPException(status_code=500, detail=f"Market conditions error: {str(e)}")
