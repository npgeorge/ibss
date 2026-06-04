"""
Monitoring API Endpoints

Provides access to application health, metrics, and monitoring data.
"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.services.monitoring import (
    get_monitoring_service,
    check_all_data_sources,
    get_data_freshness,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    api_healthy: bool
    data_sources_healthy: bool
    unhealthy_sources: List[str] = []


class DataSourceHealthResponse(BaseModel):
    """Data source health response"""
    name: str
    is_healthy: bool
    uptime_pct: float
    avg_response_time_ms: float
    consecutive_failures: int
    last_check: Optional[str] = None
    last_error: Optional[str] = None


class ScreeningMetricsResponse(BaseModel):
    """Screening metrics response"""
    total_scans: int
    successful_scans: int
    failed_scans: int
    success_rate: float
    total_stocks_screened: int
    total_stocks_scored: int
    avg_scan_time_ms: float
    avg_stocks_per_scan: float
    scans_by_mode: Dict[str, int] = {}


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response"""
    timestamp: str
    api_health: Dict[str, Any]
    data_sources: Dict[str, Any]
    screening: Dict[str, Any]
    active_alerts: List[str] = []


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Application health check endpoint.

    Returns overall health status based on API and data source health.
    """
    from datetime import datetime

    service = get_monitoring_service()
    summary = service.get_dashboard_summary()

    data_sources_healthy = summary["data_sources"]["healthy"] == summary["data_sources"]["total"]
    api_healthy = summary["api_health"]["overall_success_rate"] > 90

    return HealthResponse(
        status="healthy" if (api_healthy and data_sources_healthy) else "degraded",
        timestamp=summary["timestamp"],
        api_healthy=api_healthy,
        data_sources_healthy=data_sources_healthy,
        unhealthy_sources=summary["data_sources"]["unhealthy"],
    )


@router.get("/metrics/api", response_model=Dict[str, Any])
async def get_api_metrics():
    """
    Get API performance metrics.

    Returns metrics for all monitored endpoints including:
    - Request counts
    - Success rates
    - Latency statistics
    - Error breakdowns
    """
    service = get_monitoring_service()
    return service.get_api_metrics()


@router.get("/metrics/data-sources", response_model=Dict[str, DataSourceHealthResponse])
async def get_data_source_health():
    """
    Get health status of all data sources.

    Monitors:
    - Finviz (stock screening)
    - Yahoo Finance (price data)
    - OpenInsider (insider transactions)
    - SEC EDGAR (regulatory filings)
    """
    service = get_monitoring_service()
    return service.get_data_source_health()


@router.get("/metrics/screening", response_model=ScreeningMetricsResponse)
async def get_screening_metrics():
    """
    Get screening performance metrics.

    Returns:
    - Total scans performed
    - Success/failure rates
    - Average scan times
    - Stocks processed statistics
    - Breakdown by scan mode
    """
    service = get_monitoring_service()
    metrics = service.get_screening_metrics()
    return ScreeningMetricsResponse(**metrics)


@router.get("/dashboard", response_model=DashboardSummaryResponse)
async def get_dashboard_summary():
    """
    Get a summary of all monitoring data for dashboard display.

    Provides a quick overview of:
    - API health
    - Data source status
    - Screening activity
    - Active alerts
    """
    service = get_monitoring_service()
    summary = service.get_dashboard_summary()
    return DashboardSummaryResponse(**summary)


@router.post("/data-sources/check")
async def trigger_health_checks(background_tasks: BackgroundTasks):
    """
    Trigger health checks for all data sources.

    Checks are performed asynchronously in the background.
    """
    background_tasks.add_task(check_all_data_sources)
    return {"message": "Health checks triggered", "status": "pending"}


@router.get("/alerts/active", response_model=List[str])
async def get_active_alerts():
    """
    Get list of currently active alerts.

    Returns alert names that have been triggered within the last hour.
    """
    service = get_monitoring_service()
    summary = service.get_dashboard_summary()
    return summary["active_alerts"]


@router.get("/data-freshness", response_model=Dict[str, Any])
async def data_freshness(staleness_days: int = 5):
    """
    Report database data freshness:

    - Last successful scan/persist time
    - Latest price date and how many tracked stocks have stale prices
    - Coverage (stocks with price data) and recent data-update log rows

    A stock counts as stale if its newest daily bar is older than
    staleness_days (default 5, to tolerate weekends/holidays).
    """
    import asyncio

    return await asyncio.to_thread(get_data_freshness, staleness_days)
