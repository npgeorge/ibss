"""
Production Monitoring Service

Provides comprehensive monitoring for the stock screening application:
- Performance metrics tracking
- Error logging and categorization
- API endpoint monitoring
- Data source health checks
- Alerting capabilities
"""
import json
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from collections import defaultdict
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class APIMetrics:
    """Metrics for a single API endpoint"""
    endpoint: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    last_request_time: Optional[datetime] = None
    error_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    def record_request(self, latency_ms: float, success: bool, error_type: Optional[str] = None):
        self.total_requests += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.last_request_time = datetime.utcnow()

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error_type:
                self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1


@dataclass
class DataSourceHealth:
    """Health status of a data source"""
    name: str
    is_healthy: bool = True
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    avg_response_time_ms: float = 0.0
    total_checks: int = 0
    successful_checks: int = 0

    @property
    def uptime_pct(self) -> float:
        if self.total_checks == 0:
            return 100.0
        return (self.successful_checks / self.total_checks) * 100

    def record_check(self, success: bool, response_time_ms: float, error: Optional[str] = None):
        self.total_checks += 1
        self.last_check = datetime.utcnow()

        # Update rolling average response time
        if self.avg_response_time_ms == 0:
            self.avg_response_time_ms = response_time_ms
        else:
            self.avg_response_time_ms = (self.avg_response_time_ms * 0.9) + (response_time_ms * 0.1)

        if success:
            self.successful_checks += 1
            self.last_success = datetime.utcnow()
            self.consecutive_failures = 0
            self.is_healthy = True
        else:
            self.consecutive_failures += 1
            self.last_error = error
            # Mark unhealthy after 3 consecutive failures
            if self.consecutive_failures >= 3:
                self.is_healthy = False


@dataclass
class ScreeningMetrics:
    """Metrics specific to screening operations"""
    total_scans: int = 0
    successful_scans: int = 0
    failed_scans: int = 0
    total_stocks_screened: int = 0
    total_stocks_scored: int = 0
    avg_scan_time_ms: float = 0.0
    avg_stocks_per_scan: float = 0.0
    scans_by_mode: Dict[str, int] = field(default_factory=dict)

    def record_scan(self, success: bool, scan_time_ms: float, stocks_screened: int, stocks_scored: int, mode: str):
        self.total_scans += 1

        if success:
            self.successful_scans += 1
        else:
            self.failed_scans += 1

        self.total_stocks_screened += stocks_screened
        self.total_stocks_scored += stocks_scored

        # Update rolling averages
        if self.avg_scan_time_ms == 0:
            self.avg_scan_time_ms = scan_time_ms
        else:
            self.avg_scan_time_ms = (self.avg_scan_time_ms * 0.9) + (scan_time_ms * 0.1)

        if self.avg_stocks_per_scan == 0:
            self.avg_stocks_per_scan = stocks_screened
        else:
            self.avg_stocks_per_scan = (self.avg_stocks_per_scan * 0.9) + (stocks_screened * 0.1)

        self.scans_by_mode[mode] = self.scans_by_mode.get(mode, 0) + 1


@dataclass
class AlertConfig:
    """Configuration for an alert"""
    name: str
    metric: str
    threshold: float
    comparison: str  # "gt", "lt", "eq"
    cooldown_minutes: int = 15
    last_triggered: Optional[datetime] = None
    enabled: bool = True


class MonitoringService:
    """
    Central monitoring service for the application.

    Tracks API metrics, data source health, screening performance,
    and provides alerting capabilities.
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            base_dir = Path(__file__).parent.parent.parent
            storage_path = base_dir / "data" / "monitoring"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Metrics storage
        self._api_metrics: Dict[str, APIMetrics] = {}
        self._data_sources: Dict[str, DataSourceHealth] = {}
        self._screening_metrics = ScreeningMetrics()
        self._custom_metrics: List[MetricPoint] = []
        self._alerts: List[AlertConfig] = []
        self._alert_handlers: List[Callable[[str, str], None]] = []

        # Initialize known data sources
        for source in ["finviz", "yfinance", "openinsider", "sec_edgar"]:
            self._data_sources[source] = DataSourceHealth(name=source)

        # Load persisted metrics
        self._load_metrics()

        # Set up default alerts
        self._setup_default_alerts()

    def _load_metrics(self):
        """Load persisted metrics from disk"""
        metrics_file = self.storage_path / "metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file) as f:
                    data = json.load(f)

                # Restore screening metrics
                if "screening" in data:
                    sm = data["screening"]
                    self._screening_metrics = ScreeningMetrics(
                        total_scans=sm.get("total_scans", 0),
                        successful_scans=sm.get("successful_scans", 0),
                        failed_scans=sm.get("failed_scans", 0),
                        total_stocks_screened=sm.get("total_stocks_screened", 0),
                        total_stocks_scored=sm.get("total_stocks_scored", 0),
                        avg_scan_time_ms=sm.get("avg_scan_time_ms", 0),
                        avg_stocks_per_scan=sm.get("avg_stocks_per_scan", 0),
                        scans_by_mode=sm.get("scans_by_mode", {}),
                    )

            except Exception as e:
                logger.warning(f"Error loading metrics: {e}")

    def _save_metrics(self):
        """Persist metrics to disk"""
        metrics_file = self.storage_path / "metrics.json"
        try:
            data = {
                "screening": {
                    "total_scans": self._screening_metrics.total_scans,
                    "successful_scans": self._screening_metrics.successful_scans,
                    "failed_scans": self._screening_metrics.failed_scans,
                    "total_stocks_screened": self._screening_metrics.total_stocks_screened,
                    "total_stocks_scored": self._screening_metrics.total_stocks_scored,
                    "avg_scan_time_ms": self._screening_metrics.avg_scan_time_ms,
                    "avg_stocks_per_scan": self._screening_metrics.avg_stocks_per_scan,
                    "scans_by_mode": self._screening_metrics.scans_by_mode,
                },
                "updated_at": datetime.utcnow().isoformat(),
            }
            with open(metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving metrics: {e}")

    def _setup_default_alerts(self):
        """Set up default alerting rules"""
        self._alerts = [
            AlertConfig(
                name="High API Error Rate",
                metric="api_error_rate",
                threshold=0.1,  # 10% error rate
                comparison="gt",
                cooldown_minutes=15,
            ),
            AlertConfig(
                name="Slow Scan Performance",
                metric="avg_scan_time_ms",
                threshold=300000,  # 5 minutes
                comparison="gt",
                cooldown_minutes=30,
            ),
            AlertConfig(
                name="Data Source Unhealthy",
                metric="data_source_health",
                threshold=0,
                comparison="eq",
                cooldown_minutes=15,
            ),
        ]

    def record_api_request(
        self,
        endpoint: str,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None
    ):
        """Record an API request"""
        if endpoint not in self._api_metrics:
            self._api_metrics[endpoint] = APIMetrics(endpoint=endpoint)

        self._api_metrics[endpoint].record_request(latency_ms, success, error_type)

        # Check for alerts
        if not success:
            self._check_api_alerts(endpoint)

    def record_data_source_check(
        self,
        source: str,
        success: bool,
        response_time_ms: float,
        error: Optional[str] = None
    ):
        """Record a data source health check"""
        if source not in self._data_sources:
            self._data_sources[source] = DataSourceHealth(name=source)

        self._data_sources[source].record_check(success, response_time_ms, error)

        # Check for data source alerts
        if not self._data_sources[source].is_healthy:
            self._trigger_alert(
                "Data Source Unhealthy",
                f"Data source '{source}' is unhealthy after {self._data_sources[source].consecutive_failures} failures. Last error: {error}"
            )

    def record_screening(
        self,
        success: bool,
        scan_time_ms: float,
        stocks_screened: int,
        stocks_scored: int,
        mode: str
    ):
        """Record a screening operation"""
        self._screening_metrics.record_scan(success, scan_time_ms, stocks_screened, stocks_scored, mode)
        self._save_metrics()

        # Check for slow scan alerts
        if scan_time_ms > 300000:  # 5 minutes
            self._trigger_alert(
                "Slow Scan Performance",
                f"Scan took {scan_time_ms/1000:.1f} seconds ({mode} mode, {stocks_screened} stocks)"
            )

    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a custom metric"""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {}
        )
        self._custom_metrics.append(point)

        # Keep only last 1000 custom metrics in memory
        if len(self._custom_metrics) > 1000:
            self._custom_metrics = self._custom_metrics[-1000:]

    def add_alert_handler(self, handler: Callable[[str, str], None]):
        """Add a callback to be called when alerts trigger"""
        self._alert_handlers.append(handler)

    def _trigger_alert(self, alert_name: str, message: str):
        """Trigger an alert"""
        # Find the alert config
        alert = next((a for a in self._alerts if a.name == alert_name), None)
        if not alert or not alert.enabled:
            return

        # Check cooldown
        if alert.last_triggered:
            cooldown = timedelta(minutes=alert.cooldown_minutes)
            if datetime.utcnow() - alert.last_triggered < cooldown:
                return

        # Update last triggered
        alert.last_triggered = datetime.utcnow()

        # Log the alert
        logger.warning(f"ALERT: {alert_name} - {message}")

        # Call handlers
        for handler in self._alert_handlers:
            try:
                handler(alert_name, message)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")

    def _check_api_alerts(self, endpoint: str):
        """Check for API-related alerts"""
        metrics = self._api_metrics.get(endpoint)
        if not metrics:
            return

        # Check error rate (over last 100 requests minimum)
        if metrics.total_requests >= 100 and metrics.success_rate < 0.9:
            self._trigger_alert(
                "High API Error Rate",
                f"Endpoint {endpoint} has {(1-metrics.success_rate)*100:.1f}% error rate"
            )

    def get_api_metrics(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get API metrics, optionally for a specific endpoint"""
        if endpoint:
            metrics = self._api_metrics.get(endpoint)
            if not metrics:
                return {}
            return {
                "endpoint": metrics.endpoint,
                "total_requests": metrics.total_requests,
                "success_rate": round(metrics.success_rate * 100, 2),
                "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                "min_latency_ms": round(metrics.min_latency_ms, 2) if metrics.min_latency_ms != float('inf') else 0,
                "max_latency_ms": round(metrics.max_latency_ms, 2),
                "error_counts": metrics.error_counts,
            }

        return {
            endpoint: self.get_api_metrics(endpoint)
            for endpoint in self._api_metrics
        }

    def get_data_source_health(self, source: Optional[str] = None) -> Dict[str, Any]:
        """Get data source health status"""
        if source:
            ds = self._data_sources.get(source)
            if not ds:
                return {}
            return {
                "name": ds.name,
                "is_healthy": ds.is_healthy,
                "uptime_pct": round(ds.uptime_pct, 2),
                "avg_response_time_ms": round(ds.avg_response_time_ms, 2),
                "consecutive_failures": ds.consecutive_failures,
                "last_check": ds.last_check.isoformat() if ds.last_check else None,
                "last_error": ds.last_error,
            }

        return {
            source: self.get_data_source_health(source)
            for source in self._data_sources
        }

    def get_screening_metrics(self) -> Dict[str, Any]:
        """Get screening performance metrics"""
        sm = self._screening_metrics
        return {
            "total_scans": sm.total_scans,
            "successful_scans": sm.successful_scans,
            "failed_scans": sm.failed_scans,
            "success_rate": round(sm.successful_scans / sm.total_scans * 100, 2) if sm.total_scans > 0 else 100,
            "total_stocks_screened": sm.total_stocks_screened,
            "total_stocks_scored": sm.total_stocks_scored,
            "avg_scan_time_ms": round(sm.avg_scan_time_ms, 2),
            "avg_stocks_per_scan": round(sm.avg_stocks_per_scan, 2),
            "scans_by_mode": sm.scans_by_mode,
        }

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get a summary of all monitoring data for dashboard display"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "api_health": {
                "total_endpoints": len(self._api_metrics),
                "endpoints_with_errors": sum(1 for m in self._api_metrics.values() if m.failed_requests > 0),
                "overall_success_rate": round(
                    sum(m.successful_requests for m in self._api_metrics.values()) /
                    max(sum(m.total_requests for m in self._api_metrics.values()), 1) * 100, 2
                ),
            },
            "data_sources": {
                "total": len(self._data_sources),
                "healthy": sum(1 for ds in self._data_sources.values() if ds.is_healthy),
                "unhealthy": [ds.name for ds in self._data_sources.values() if not ds.is_healthy],
            },
            "screening": {
                "total_scans": self._screening_metrics.total_scans,
                "avg_scan_time_seconds": round(self._screening_metrics.avg_scan_time_ms / 1000, 1),
                "stocks_scored_total": self._screening_metrics.total_stocks_scored,
            },
            "active_alerts": [
                a.name for a in self._alerts
                if a.last_triggered and datetime.utcnow() - a.last_triggered < timedelta(hours=1)
            ],
        }


def get_data_freshness(staleness_days: int = 5) -> Dict[str, Any]:
    """
    Report database data freshness for the Monitoring page.

    Queries the DB (not the in-memory metrics) for:
    - last successful scan/persist time (from data_updates)
    - latest price date across all stocks + per-stock staleness count
    - coverage (how many tracked stocks actually have price data)
    - the most recent data_update log rows

    staleness_days: a stock is "stale" if its newest daily bar is older than
    this many calendar days (default 5 to tolerate weekends/holidays).
    """
    from datetime import date as _date
    from sqlalchemy import func
    from app.core.database import get_sync_db
    from app.models.database import Stock, PriceDataDaily, DataUpdate

    result: Dict[str, Any] = {
        "checked_at": datetime.utcnow().isoformat(),
        "last_scan_at": None,
        "last_scan_status": None,
        "total_stocks": 0,
        "stocks_with_prices": 0,
        "latest_price_date": None,
        "stale_stock_count": 0,
        "staleness_threshold_days": staleness_days,
        "recent_updates": [],
    }

    try:
        with get_sync_db() as db:
            result["total_stocks"] = db.query(func.count(Stock.id)).scalar() or 0

            # Latest price date per stock
            per_stock = (
                db.query(
                    PriceDataDaily.stock_id.label("stock_id"),
                    func.max(PriceDataDaily.date).label("last_date"),
                )
                .group_by(PriceDataDaily.stock_id)
                .all()
            )
            result["stocks_with_prices"] = len(per_stock)
            if per_stock:
                latest = max(row.last_date for row in per_stock)
                result["latest_price_date"] = latest.isoformat()
                cutoff = _date.today() - timedelta(days=staleness_days)
                result["stale_stock_count"] = sum(
                    1 for row in per_stock if row.last_date < cutoff
                )

            # Last successful scan/persist
            last_completed = (
                db.query(DataUpdate)
                .filter(DataUpdate.status == "completed")
                .order_by(DataUpdate.completed_at.desc())
                .first()
            )
            if last_completed and last_completed.completed_at:
                result["last_scan_at"] = last_completed.completed_at.isoformat()
                result["last_scan_status"] = last_completed.status

            # Recent update log rows
            recent = (
                db.query(DataUpdate)
                .order_by(DataUpdate.started_at.desc())
                .limit(10)
                .all()
            )
            result["recent_updates"] = [
                {
                    "update_type": u.update_type,
                    "status": u.status,
                    "records_processed": u.records_processed,
                    "records_failed": u.records_failed,
                    "started_at": u.started_at.isoformat() if u.started_at else None,
                    "completed_at": u.completed_at.isoformat() if u.completed_at else None,
                }
                for u in recent
            ]
    except Exception as e:
        logger.warning(f"Data freshness query failed: {e}")
        result["error"] = str(e)

    return result


# Singleton instance
_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    """Get the global monitoring service instance"""
    global _service
    if _service is None:
        _service = MonitoringService()
    return _service


def monitor_endpoint(endpoint_name: str):
    """Decorator to automatically monitor API endpoint performance"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error_type = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_type = type(e).__name__
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                get_monitoring_service().record_api_request(
                    endpoint_name,
                    latency_ms,
                    success,
                    error_type
                )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error_type = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_type = type(e).__name__
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                get_monitoring_service().record_api_request(
                    endpoint_name,
                    latency_ms,
                    success,
                    error_type
                )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


async def check_all_data_sources():
    """
    Perform health checks on all data sources.

    Can be called periodically to update health status.
    """
    import aiohttp

    service = get_monitoring_service()

    # Check Finviz
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get("https://finviz.com/screener.ashx", timeout=10) as resp:
                success = resp.status == 200
                latency = (time.time() - start) * 1000
                service.record_data_source_check("finviz", success, latency)
    except Exception as e:
        service.record_data_source_check("finviz", False, 0, str(e))

    # Check Yahoo Finance
    try:
        start = time.time()
        import yfinance as yf
        ticker = yf.Ticker("SPY")
        info = ticker.fast_info
        success = info is not None
        latency = (time.time() - start) * 1000
        service.record_data_source_check("yfinance", success, latency)
    except Exception as e:
        service.record_data_source_check("yfinance", False, 0, str(e))

    # Check OpenInsider
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get("http://openinsider.com/", timeout=10) as resp:
                success = resp.status == 200
                latency = (time.time() - start) * 1000
                service.record_data_source_check("openinsider", success, latency)
    except Exception as e:
        service.record_data_source_check("openinsider", False, 0, str(e))
