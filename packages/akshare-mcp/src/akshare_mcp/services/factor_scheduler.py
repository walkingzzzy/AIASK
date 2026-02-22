"""Lightweight asyncio-based factor scheduler.

Runs batch_compute_factors periodically (default: daily at 18:00 CST)
without requiring external dependencies like APScheduler or Celery.

Usage:
    from .factor_scheduler import FactorScheduler
    scheduler = FactorScheduler()
    scheduler.start()  # non-blocking, runs in background
    # ... later ...
    scheduler.stop()
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default stock universe for daily factor computation
DEFAULT_UNIVERSE = [
    "000001", "000002", "000063", "000069", "000100",
    "000157", "000333", "000338", "000425", "000538",
    "000568", "000596", "000625", "000651", "000661",
    "000725", "000768", "000776", "000858", "000895",
    "002001", "002007", "002024", "002027", "002032",
    "002049", "002120", "002142", "002230", "002236",
    "002271", "002304", "002352", "002371", "002415",
    "002460", "002475", "002493", "002555", "002594",
    "002714", "002736", "002841", "002916", "002938",
    "300003", "300014", "300015", "300033", "300059",
    "600000", "600009", "600010", "600011", "600015",
    "600016", "600018", "600019", "600025", "600028",
    "600029", "600030", "600031", "600036", "600048",
    "600050", "600061", "600085", "600089", "600104",
    "600109", "600111", "600115", "600132", "600150",
    "600176", "600183", "600196", "600276", "600309",
    "600332", "600346", "600352", "600362", "600383",
    "600406", "600436", "600438", "600519", "600547",
    "600570", "600585", "600588", "600600", "600660",
    "600690", "600703", "600741", "600745", "600809",
    "600837", "600887", "600893", "600900", "601006",
    "601009", "601012", "601018", "601066", "601088",
    "601100", "601111", "601138", "601155", "601166",
    "601169", "601186", "601211", "601225", "601229",
    "601236", "601238", "601288", "601318", "601328",
    "601336", "601360", "601390", "601398", "601601",
    "601607", "601618", "601628", "601633", "601668",
    "601669", "601688", "601698", "601766", "601788",
    "601800", "601818", "601857", "601877", "601878",
    "601881", "601888", "601899", "601901", "601919",
    "601933", "601939", "601985", "601988", "601989",
    "601998", "603019", "603160", "603259", "603288",
    "603501", "603799", "603833", "603899", "603986",
]

DEFAULT_FACTORS = ["momentum", "value", "quality", "volatility", "liquidity"]


class FactorScheduler:
    """Asyncio-based daily factor computation scheduler."""

    def __init__(
        self,
        run_time: time = time(18, 0),  # 18:00 CST
        universe: Optional[List[str]] = None,
        factors: Optional[List[str]] = None,
        batch_size: int = 50,
    ):
        self.run_time = run_time
        self.universe = universe or DEFAULT_UNIVERSE
        self.factors = factors or DEFAULT_FACTORS
        self.batch_size = batch_size
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None

    def start(self):
        """Start the scheduler in the background (non-blocking)."""
        if self._running:
            logger.warning("FactorScheduler already running")
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info("FactorScheduler started, daily run at %s", self.run_time)

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("FactorScheduler stopped")

    async def _loop(self):
        """Main scheduler loop — sleeps until next run_time, then executes."""
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.run_time)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("FactorScheduler: next run in %.0f seconds at %s", wait_seconds, target)
                await asyncio.sleep(wait_seconds)

                if self._running:
                    await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("FactorScheduler loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)  # retry after 1 min on error

    async def run_once(self):
        """Execute a single batch factor computation run."""
        from ..storage import get_db
        from ..data_source import data_source

        logger.info("FactorScheduler: starting batch compute for %d stocks", len(self.universe))
        start = datetime.now()
        db = get_db()
        total_computed = 0
        total_errors = 0

        # Process in batches
        for i in range(0, len(self.universe), self.batch_size):
            batch = self.universe[i:i + self.batch_size]
            try:
                # Import and call the quant_manager batch action directly
                from ..tools.managers.quant_manager import quant_manager
                result = await quant_manager(
                    action="batch_compute_factors",
                    kwargs=f'{{"codes": {batch}, "factors": {self.factors}, "persist": true, "compute_ic": true}}'
                )
                if isinstance(result, dict):
                    data = result.get("data", result)
                    total_computed += data.get("computed_count", 0)
                    total_errors += data.get("error_count", 0)
            except Exception as e:
                logger.error("FactorScheduler batch %d-%d error: %s", i, i + len(batch), e)
                total_errors += len(batch)

        elapsed = (datetime.now() - start).total_seconds()
        self.last_run = datetime.now()
        self.last_result = {
            "computed": total_computed,
            "errors": total_errors,
            "elapsed_seconds": round(elapsed, 1),
            "universe_size": len(self.universe),
        }
        logger.info(
            "FactorScheduler: completed in %.1fs — %d computed, %d errors",
            elapsed, total_computed, total_errors,
        )
        return self.last_result

    def status(self) -> dict:
        """Return current scheduler status."""
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "universe_size": len(self.universe),
            "factors": self.factors,
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
        }


# Singleton instance
_scheduler: Optional[FactorScheduler] = None


def get_factor_scheduler() -> FactorScheduler:
    """Get or create the global FactorScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = FactorScheduler()
    return _scheduler
