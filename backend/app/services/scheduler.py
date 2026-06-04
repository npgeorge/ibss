"""
Pipeline Orchestration Scheduler

In-process APScheduler that drives the unified data workflow on a cadence:

- Daily (weekdays, after market close): incremental price + weekly upsert for
  all tracked stocks via DataUpdateScheduler.update_all_stock_prices().
- Weekly (Sunday morning): full persist-enabled screening scan via
  run_full_pipeline(persist=True), which refreshes prices, indicators,
  insider transactions, and screening results in one pass.

Enable with settings.ENABLE_SCHEDULER (off by default so dev/test runs don't
kick off background network jobs). For prod, an external cron/docker alternative
is documented below.

Cron / docker alternative (instead of in-process scheduling):
    # Daily incremental price update (weekdays 16:30 ET)
    30 16 * * 1-5  cd /app && python -m scripts.weekly_scan --mode quick --persist
    # Weekly full persist scan (Sunday 06:00 ET)
    0 6 * * 0      cd /app && python -m scripts.weekly_scan --mode standard --persist
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.services.finviz_screener import ScanMode

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def _daily_price_update_job():
    """Incremental price + weekly aggregation upsert for all tracked stocks."""
    from app.services.data_scheduler import DataUpdateScheduler

    logger.info("[scheduler] Daily price update job starting")
    try:
        updater = DataUpdateScheduler()
        await updater.update_all_stock_prices()
        logger.info("[scheduler] Daily price update job complete")
    except Exception:
        logger.exception("[scheduler] Daily price update job failed")


async def _weekly_scan_job():
    """Full persist-enabled screening scan (the unified workflow)."""
    from app.services.screener import run_full_pipeline, ScreeningCriteria

    logger.info("[scheduler] Weekly scan job starting (mode=%s)", settings.WEEKLY_SCAN_MODE)
    try:
        mode = ScanMode(settings.WEEKLY_SCAN_MODE.lower())
    except ValueError:
        mode = ScanMode.STANDARD

    try:
        scored = await run_full_pipeline(
            criteria=ScreeningCriteria(min_total_score=settings.WEEKLY_SCAN_MIN_SCORE),
            mode=mode,
            persist=True,
        )
        logger.info("[scheduler] Weekly scan job complete — %d stocks persisted", len(scored))
    except Exception:
        logger.exception("[scheduler] Weekly scan job failed")


def start_scheduler() -> Optional[AsyncIOScheduler]:
    """Start the in-process scheduler if enabled. Idempotent."""
    global _scheduler

    if not settings.ENABLE_SCHEDULER:
        logger.info("[scheduler] Disabled (ENABLE_SCHEDULER=false)")
        return None

    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)

    scheduler.add_job(
        _daily_price_update_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=settings.DAILY_PRICE_UPDATE_HOUR,
            minute=settings.DAILY_PRICE_UPDATE_MINUTE,
        ),
        id="daily_price_update",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _weekly_scan_job,
        CronTrigger(
            day_of_week=settings.WEEKLY_SCAN_DAY,
            hour=settings.WEEKLY_SCAN_HOUR,
        ),
        id="weekly_full_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "[scheduler] Started (tz=%s): daily price @ %02d:%02d mon-fri, weekly scan @ %s %02d:00",
        settings.SCHEDULER_TIMEZONE,
        settings.DAILY_PRICE_UPDATE_HOUR,
        settings.DAILY_PRICE_UPDATE_MINUTE,
        settings.WEEKLY_SCAN_DAY,
        settings.WEEKLY_SCAN_HOUR,
    )
    return scheduler


def stop_scheduler():
    """Shut down the scheduler if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[scheduler] Stopped")
