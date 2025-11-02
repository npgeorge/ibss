"""
API Router configuration
"""
from fastapi import APIRouter

from app.api import screener, stocks, insider, alerts, portfolio

api_router = APIRouter()

# Include sub-routers
api_router.include_router(screener.router, prefix="/screen", tags=["Screener"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
api_router.include_router(insider.router, prefix="/insider", tags=["Insider Trading"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
