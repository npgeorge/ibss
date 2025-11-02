"""
Insider Trading API Endpoints
"""
from fastapi import APIRouter, Query
from typing import List
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class InsiderTransaction(BaseModel):
    """Insider transaction record"""

    symbol: str
    filing_date: datetime
    transaction_date: datetime
    insider_name: str
    insider_title: str
    transaction_type: str  # "purchase" or "sale"
    shares: int
    price_per_share: float
    value: float
    ownership_percent: float


class InsiderActivity(BaseModel):
    """Insider activity summary"""

    symbol: str
    recent_transactions: List[InsiderTransaction]
    unique_buyers: int
    total_buy_value: float
    cluster_buying: bool
    confidence_score: float


@router.get("/recent", response_model=List[InsiderTransaction])
async def get_recent_insider_activity(
    days: int = Query(90, ge=1, le=365), min_value: float = Query(0)
):
    """
    Get recent insider transactions

    Filter by timeframe and minimum transaction value
    """
    # TODO: Implement insider data retrieval
    return []


@router.get("/{symbol}", response_model=InsiderActivity)
async def get_stock_insider_activity(symbol: str, days: int = Query(90)):
    """
    Get insider activity for a specific stock
    """
    # TODO: Implement stock-specific insider activity
    return InsiderActivity(
        symbol=symbol,
        recent_transactions=[],
        unique_buyers=0,
        total_buy_value=0.0,
        cluster_buying=False,
        confidence_score=0.0,
    )
