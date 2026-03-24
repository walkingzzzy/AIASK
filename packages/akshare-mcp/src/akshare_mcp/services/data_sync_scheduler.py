"""数据同步调度器 — 启动时同步 + 每日收盘后定时同步

A股交易时间: 9:30—11:30, 13:00—15:00
默认同步时间: 15:30 CST（收盘后30分钟，等待数据源更新）

功能:
1. 启动时自动执行一次增量同步（后台非阻塞）
2. 每日 15:30 自动触发同步（仅交易日）
3. 同步范围: K线数据 + 财务数据

本项目有三套并行的数据同步入口，职责不同：

1. **DataSyncScheduler**（本模块）
   - 角色：运行时后台调度器，由 MCP server 启动
   - 触发：启动时自动 + 每日 15:30
   - 范围：DEFAULT_UNIVERSE K 线 + 财务增量同步
   - 适用：日常运行

2. **data_sync_manager** (tools/managers/data_sync_manager.py)
   - 角色：MCP 工具，供用户/AI 按需触发任务
   - 触发：通过 ``data_sync_manager(action=...)`` 工具调用
   - 范围：sync_schedules 表中的到期任务 + run_runtime_data_warmup
   - 适用：手动补数据、审计脚本

3. **sync_init.py** (sync_daily/sync_init.py)
   - 角色：独立脚本，深度历史全量回填
   - 触发：手工运行
   - 范围：多年 K 线/财务/龙虎榜/北向/大宗/宏观等
   - 适用：首次部署或数据修复

使用方式:
    from .data_sync_scheduler import get_data_sync_scheduler
    scheduler = get_data_sync_scheduler()
    scheduler.start()
"""

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, time, timedelta, date
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# 复用 FactorScheduler 已有的沪深 300 成分股池
from .factor_scheduler import DEFAULT_UNIVERSE


class DataSyncScheduler:
    """异步数据同步调度器 — 启动同步 + 每日定时同步"""

    def __init__(
        self,
        sync_time: time = time(15, 30),   # 15:30 CST
        universe: Optional[List[str]] = None,
        sync_on_startup: bool = True,
        batch_size: int = 50,
        concurrency: int = 5,
    ):
        # 从环境变量读取配置
        env_time = os.getenv("DATA_SYNC_TIME", "").strip()
        if env_time:
            try:
                parts = env_time.split(":")
                sync_time = time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        env_startup = os.getenv("DATA_SYNC_ON_STARTUP", "").strip().lower()
        if env_startup in ("false", "0", "no"):
            sync_on_startup = False
        elif env_startup in ("true", "1", "yes"):
            sync_on_startup = True

        self.sync_time = sync_time
        self.universe = universe or list(DEFAULT_UNIVERSE)
        self.sync_on_startup = sync_on_startup
        self.batch_size = batch_size
        self.concurrency = concurrency

        self._task: Optional[asyncio.Task] = None
        self._startup_task: Optional[asyncio.Task] = None
        self._running = False

        # 状态追踪
        self.last_sync: Optional[datetime] = None
        self.last_result: Optional[Dict[str, Any]] = None
        self._sync_count = 0

    def start(self):
        """启动调度器（非阻塞）"""
        if self._running:
            logger.warning("[DataSyncScheduler] already running")
            return
        self._running = True

        # 启动定时器循环
        self._task = asyncio.create_task(self._loop(), name="data-sync-scheduler")
        logger.info(
            "[DataSyncScheduler] started — daily sync at %s, universe=%d stocks, startup_sync=%s",
            self.sync_time, len(self.universe), self.sync_on_startup,
        )

        # 启动时异步同步
        if self.sync_on_startup:
            self._startup_task = asyncio.create_task(self._startup_sync(), name="data-sync-startup")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._startup_task:
            self._startup_task.cancel()
            self._startup_task = None
        logger.info("[DataSyncScheduler] stopped")

    async def shutdown(self, grace_sec: float = 3.0):
        """停止调度器并等待后台任务退出（给予 grace period 完成当前工作）。"""
        self._running = False
        tasks = [task for task in (self._startup_task, self._task) if task is not None]
        self._startup_task = None
        self._task = None
        for task in tasks:
            if not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, grace_sec))
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            else:
                with suppress(asyncio.CancelledError):
                    await task
        logger.info("[DataSyncScheduler] stopped")

    # ------------------------------------------------------------------
    # 启动同步
    # ------------------------------------------------------------------
    async def _startup_sync(self):
        """启动后延迟 10s 执行一次同步（避免阻塞启动流程）"""
        try:
            await asyncio.sleep(10)  # 等待 DB 连接池就绪

            # 读取 StartupValidator 的校验结果，决定同步范围
            try:
                from .startup_validator import get_startup_validator
                validator = get_startup_validator()
                # 等待校验器完成（最多再等 30 秒）
                for _ in range(30):
                    if validator.completed:
                        break
                    await asyncio.sleep(1)

                report = validator.last_report
                if report:
                    if not report.get("db_available"):
                        logger.warning(
                            "[DataSyncScheduler] DB 不可达，跳过启动同步"
                        )
                        return
                    if report.get("data_stale"):
                        logger.info(
                            "[DataSyncScheduler] 数据已过期，启动同步将使用完整范围"
                        )
                    if report.get("coverage_low"):
                        logger.info(
                            "[DataSyncScheduler] 覆盖率不足，启动同步将使用完整范围"
                        )
            except Exception as e:
                logger.warning("[DataSyncScheduler] 读取校验结果失败: %s", e)

            logger.info("[DataSyncScheduler] startup sync begin (%d stocks)", len(self.universe))
            result = await self.run_once(reason="startup")
            logger.info(
                "[DataSyncScheduler] startup sync done: %s",
                {k: v for k, v in (result or {}).items() if k != "errors"},
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[DataSyncScheduler] startup sync error: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # 定时循环
    # ------------------------------------------------------------------
    async def _loop(self):
        """每日等待到 sync_time，执行同步"""
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.sync_time)
                if target <= now:
                    target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()
                logger.info(
                    "[DataSyncScheduler] next scheduled sync in %.0fs at %s",
                    wait_seconds, target.strftime("%Y-%m-%d %H:%M"),
                )
                await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                # 检查是否为交易日
                is_td = await self._is_trading_day(datetime.now().date())
                if not is_td:
                    logger.info("[DataSyncScheduler] skipped — not a trading day")
                    continue

                logger.info("[DataSyncScheduler] daily sync begin")
                result = await self.run_once(reason="daily_schedule")
                logger.info(
                    "[DataSyncScheduler] daily sync done: %s",
                    {k: v for k, v in (result or {}).items() if k != "errors"},
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[DataSyncScheduler] loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # 核心同步逻辑
    # ------------------------------------------------------------------
    async def run_once(self, reason: str = "manual") -> Dict[str, Any]:
        """执行一次完整同步"""
        from ..data_source import data_source
        from ..storage import get_db

        start = datetime.now()
        db = get_db()

        kline_ok = 0
        kline_fail = 0
        fin_ok = 0
        fin_fail = 0
        errors: List[str] = []

        # ---- Phase 1: K线同步 (并发抓取 + 串行写库) ----
        #
        # 之前这里在同一批次内并发调用 save_klines，会让多个 asyncpg 连接同时执行
        # ON CONFLICT upsert，启动期高并发时容易出现死锁。这里保留并发抓取外部数据，
        # 但统一改为串行落库，优先保证启动同步稳定性。
        for i in range(0, len(self.universe), self.batch_size):
            batch = self.universe[i:i + self.batch_size]

            semaphore = asyncio.Semaphore(self.concurrency)

            async def _fetch_kline(code: str):
                async with semaphore:
                    try:
                        klines = await asyncio.to_thread(
                            data_source.get_kline, code, "daily", 250
                        )
                        return code, klines, None
                    except Exception as e:
                        return code, None, e

            fetch_results = await asyncio.gather(
                *[_fetch_kline(code) for code in batch],
                return_exceptions=True,
            )

            for result in fetch_results:
                if isinstance(result, Exception):
                    kline_fail += 1
                    if len(errors) < 10:
                        errors.append(f"kline:batch:{result}")
                    continue

                code, klines, fetch_error = result
                if fetch_error is not None:
                    kline_fail += 1
                    if len(errors) < 10:
                        errors.append(f"kline:{code}:{fetch_error}")
                    continue

                if not klines:
                    kline_fail += 1
                    continue

                try:
                    await db.save_klines(code, klines)
                    kline_ok += 1
                except Exception as e:
                    kline_fail += 1
                    logger.warning("[DataSyncScheduler] %s save klines error: %s", code, e)
                    if len(errors) < 10:
                        errors.append(f"kline_save:{code}:{e}")

        # ---- Phase 2: 财务数据同步 (分批) ----
        try:
            for i in range(0, len(self.universe), self.batch_size):
                batch = self.universe[i:i + self.batch_size]

                semaphore = asyncio.Semaphore(self.concurrency)

                async def _sync_financial(code: str):
                    nonlocal fin_ok, fin_fail
                    async with semaphore:
                        try:
                            from ..tools.finance import get_financials
                            result = await get_financials(code)
                            if result and result.get("success"):
                                fin_ok += 1
                            else:
                                fin_fail += 1
                        except Exception as e:
                            fin_fail += 1
                            if len(errors) < 10:
                                errors.append(f"fin:{code}:{e}")

                await asyncio.gather(
                    *[_sync_financial(code) for code in batch],
                    return_exceptions=True,
                )
        except Exception as e:
            logger.warning("[DataSyncScheduler] financial sync phase error: %s", e)

        elapsed = (datetime.now() - start).total_seconds()
        self.last_sync = datetime.now()
        self._sync_count += 1

        self.last_result = {
            "reason": reason,
            "kline_success": kline_ok,
            "kline_failed": kline_fail,
            "financial_success": fin_ok,
            "financial_failed": fin_fail,
            "universe_size": len(self.universe),
            "elapsed_seconds": round(elapsed, 1),
            "sync_count": self._sync_count,
            "errors": errors[:10],
        }
        return self.last_result

    # ------------------------------------------------------------------
    # 交易日判断
    # ------------------------------------------------------------------
    async def _is_trading_day(self, check_date: date) -> bool:
        """查询 DB 判断是否交易日，查询失败则按工作日判断"""
        try:
            from ..storage import get_db
            db = get_db()
            async with db.acquire() as conn:
                # 尝试查 trading_dates 表
                row = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM trading_dates WHERE trade_date = $1)",
                    check_date,
                )
                return bool(row)
        except Exception:
            # 表不存在或查询失败，回退到简单工作日判断
            # 周一=0 … 周五=4 是工作日
            return check_date.weekday() < 5

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        """返回调度器状态"""
        return {
            "running": self._running,
            "sync_time": str(self.sync_time),
            "sync_on_startup": self.sync_on_startup,
            "universe_size": len(self.universe),
            "sync_count": self._sync_count,
            "last_sync": str(self.last_sync) if self.last_sync else None,
            "last_result": self.last_result,
        }


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------
_scheduler: Optional[DataSyncScheduler] = None


def get_data_sync_scheduler() -> DataSyncScheduler:
    """获取或创建全局 DataSyncScheduler 实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = DataSyncScheduler()
    return _scheduler
