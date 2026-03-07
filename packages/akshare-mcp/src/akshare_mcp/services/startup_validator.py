"""启动校验器 — 服务启动时自动检查数据库状态与数据有效性

功能:
1. DB 连通性预检（带超时与重试）
2. 核心表存在性检查（kline_1d, stocks, financials, stock_quotes）
3. K线数据新鲜度检查（最新记录距今天数）
4. 股票池覆盖率检查（stocks 表记录数）
5. 校验结果汇总日志 + 写入 sync_tasks 表

使用方式:
    from .startup_validator import get_startup_validator
    validator = get_startup_validator()
    asyncio.ensure_future(validator.run_async())
"""

import asyncio
import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 核心表清单
CORE_TABLES = ["kline_1d", "stocks", "financials", "stock_quotes"]

# 默认阈值
DEFAULT_FRESHNESS_THRESHOLD_DAYS = 5   # K线数据超过 5 天视为过期
DEFAULT_COVERAGE_MIN_STOCKS = 100      # stocks 表至少 100 条记录
DEFAULT_RETRY_COUNT = 3                # DB 连接重试次数
DEFAULT_RETRY_DELAY_SECONDS = 5        # 重试间隔


class StartupValidator:
    """启动校验器 — 检查 DB 连通性、Schema 完整性、数据有效性"""

    def __init__(
        self,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_THRESHOLD_DAYS,
        coverage_min_stocks: int = DEFAULT_COVERAGE_MIN_STOCKS,
        retry_count: int = DEFAULT_RETRY_COUNT,
        retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ):
        # 从环境变量覆盖默认值
        self.freshness_threshold_days = int(
            os.getenv("STARTUP_FRESHNESS_DAYS", str(freshness_threshold_days))
        )
        self.coverage_min_stocks = int(
            os.getenv("STARTUP_COVERAGE_MIN", str(coverage_min_stocks))
        )
        self.retry_count = int(
            os.getenv("STARTUP_DB_RETRY_COUNT", str(retry_count))
        )
        self.retry_delay = float(
            os.getenv("STARTUP_DB_RETRY_DELAY", str(retry_delay))
        )

        # 校验结果
        self.last_report: Optional[Dict[str, Any]] = None
        self._completed = False

    @property
    def completed(self) -> bool:
        return self._completed

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    async def run_async(self) -> Dict[str, Any]:
        """延迟 5 秒后执行全部校验（避免阻塞 MCP 协议启动）"""
        try:
            await asyncio.sleep(5)
            logger.info("[StartupValidator] ===== 开始启动校验 =====")
            report = await self._run_all_checks()
            self.last_report = report
            self._completed = True
            self._log_report(report)
            await self._persist_report(report)
            return report
        except asyncio.CancelledError:
            logger.info("[StartupValidator] cancelled")
            return {"status": "cancelled"}
        except Exception as e:
            logger.error("[StartupValidator] unexpected error: %s", e, exc_info=True)
            self.last_report = {"status": "error", "error": str(e)}
            self._completed = True
            return self.last_report

    # ------------------------------------------------------------------
    # 核心校验
    # ------------------------------------------------------------------
    async def _run_all_checks(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "db_available": False,
            "tables_ok": False,
            "data_stale": True,
            "coverage_low": True,
            "details": {},
        }

        # ---- 1. DB 连通性 ----
        db = await self._check_db_connectivity(report)
        if db is None:
            report["status"] = "degraded"
            return report

        # ---- 2. 核心表存在性 ----
        await self._check_core_tables(db, report)

        # ---- 3. K线新鲜度 ----
        await self._check_data_freshness(db, report)

        # ---- 4. 股票池覆盖率 ----
        await self._check_coverage(db, report)

        # 汇总状态
        if report["db_available"] and report["tables_ok"] and not report["data_stale"] and not report["coverage_low"]:
            report["status"] = "healthy"
        elif report["db_available"]:
            report["status"] = "degraded"
        else:
            report["status"] = "unhealthy"

        return report

    # ------------------------------------------------------------------
    # 1. DB 连通性
    # ------------------------------------------------------------------
    async def _check_db_connectivity(self, report: Dict[str, Any]):
        """带重试的 DB 连通性检查，返回 db 实例或 None"""
        from ..storage import get_db

        for attempt in range(1, self.retry_count + 1):
            try:
                db = get_db()
                await db.initialize()
                async with db.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                report["db_available"] = True
                report["details"]["db_connectivity"] = {
                    "success": True,
                    "attempt": attempt,
                }
                logger.info("[StartupValidator] ✓ DB 连通性检查通过 (第 %d 次)", attempt)
                return db
            except Exception as e:
                logger.warning(
                    "[StartupValidator] DB 连接失败 (第 %d/%d 次): %s",
                    attempt, self.retry_count, e,
                )
                if attempt < self.retry_count:
                    await asyncio.sleep(self.retry_delay)

        report["db_available"] = False
        report["details"]["db_connectivity"] = {
            "success": False,
            "retries_exhausted": True,
        }
        logger.error("[StartupValidator] ✗ DB 连通性检查失败，所有重试已耗尽")
        return None

    # ------------------------------------------------------------------
    # 2. 核心表存在性
    # ------------------------------------------------------------------
    async def _check_core_tables(self, db, report: Dict[str, Any]) -> None:
        missing: List[str] = []
        try:
            async with db.acquire() as conn:
                for table in CORE_TABLES:
                    exists = await conn.fetchval(
                        "SELECT EXISTS ("
                        "  SELECT 1 FROM information_schema.tables"
                        "  WHERE table_schema = 'public' AND table_name = $1"
                        ")",
                        table,
                    )
                    if not exists:
                        missing.append(table)

            if missing:
                logger.warning("[StartupValidator] ✗ 缺失核心表: %s — 将自动创建", missing)
                # 触发 SchemaBase._init_tables() 重新建表
                try:
                    await db._init_tables()
                    logger.info("[StartupValidator] ✓ 自动创建表完成")
                    report["tables_ok"] = True
                except Exception as e:
                    logger.error("[StartupValidator] 自动创建表失败: %s", e)
                    report["tables_ok"] = False
            else:
                report["tables_ok"] = True
                logger.info("[StartupValidator] ✓ 核心表检查通过 (%d/%d)", len(CORE_TABLES), len(CORE_TABLES))

            report["details"]["core_tables"] = {
                "checked": CORE_TABLES,
                "missing": missing,
                "auto_created": bool(missing) and report["tables_ok"],
            }
        except Exception as e:
            logger.error("[StartupValidator] 核心表检查异常: %s", e)
            report["tables_ok"] = False
            report["details"]["core_tables"] = {"error": str(e)}

    # ------------------------------------------------------------------
    # 3. K线新鲜度
    # ------------------------------------------------------------------
    async def _check_data_freshness(self, db, report: Dict[str, Any]) -> None:
        try:
            async with db.acquire() as conn:
                latest_time = await conn.fetchval(
                    "SELECT MAX(time) FROM kline_1d"
                )

            if latest_time is None:
                report["data_stale"] = True
                days_since = None
                logger.warning("[StartupValidator] ✗ K线表无数据")
            else:
                # latest_time 可能带时区也可能不带，统一转为 date
                if hasattr(latest_time, "date"):
                    latest_date = latest_time.date()
                else:
                    latest_date = latest_time
                days_since = (date.today() - latest_date).days
                report["data_stale"] = days_since > self.freshness_threshold_days
                if report["data_stale"]:
                    logger.warning(
                        "[StartupValidator] ✗ K线数据过期 — 最新数据距今 %d 天（阈值 %d 天）",
                        days_since, self.freshness_threshold_days,
                    )
                else:
                    logger.info(
                        "[StartupValidator] ✓ K线新鲜度检查通过 — 最新数据距今 %d 天",
                        days_since,
                    )

            report["details"]["data_freshness"] = {
                "latest_kline_date": str(latest_time) if latest_time else None,
                "days_since_latest": days_since,
                "threshold_days": self.freshness_threshold_days,
                "stale": report["data_stale"],
            }
        except Exception as e:
            logger.error("[StartupValidator] K线新鲜度检查异常: %s", e)
            report["data_stale"] = True
            report["details"]["data_freshness"] = {"error": str(e)}

    # ------------------------------------------------------------------
    # 4. 股票池覆盖率
    # ------------------------------------------------------------------
    async def _check_coverage(self, db, report: Dict[str, Any]) -> None:
        try:
            async with db.acquire() as conn:
                stock_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM stocks"
                )

            stock_count = stock_count or 0
            report["coverage_low"] = stock_count < self.coverage_min_stocks
            if report["coverage_low"]:
                logger.warning(
                    "[StartupValidator] ✗ 股票池覆盖率不足 — 当前 %d 条（最低 %d 条）",
                    stock_count, self.coverage_min_stocks,
                )
            else:
                logger.info(
                    "[StartupValidator] ✓ 股票池覆盖率检查通过 — 共 %d 条",
                    stock_count,
                )

            report["details"]["coverage"] = {
                "stock_count": stock_count,
                "min_threshold": self.coverage_min_stocks,
                "low": report["coverage_low"],
            }
        except Exception as e:
            logger.error("[StartupValidator] 覆盖率检查异常: %s", e)
            report["coverage_low"] = True
            report["details"]["coverage"] = {"error": str(e)}

    # ------------------------------------------------------------------
    # 日志输出
    # ------------------------------------------------------------------
    def _log_report(self, report: Dict[str, Any]) -> None:
        status = report.get("status", "unknown")
        icon = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(status, "❓")
        logger.info("[StartupValidator] ===== 校验结果: %s %s =====", icon, status.upper())
        logger.info("[StartupValidator]   DB 连通: %s", "✓" if report.get("db_available") else "✗")
        logger.info("[StartupValidator]   核心表: %s", "✓" if report.get("tables_ok") else "✗")
        logger.info("[StartupValidator]   数据新鲜: %s", "✗ 过期" if report.get("data_stale") else "✓")
        logger.info("[StartupValidator]   覆盖率: %s", "✗ 不足" if report.get("coverage_low") else "✓")

    # ------------------------------------------------------------------
    # 持久化校验报告到 sync_tasks 表
    # ------------------------------------------------------------------
    async def _persist_report(self, report: Dict[str, Any]) -> None:
        if not report.get("db_available"):
            return  # DB 不可达时无法写入

        try:
            from ..storage import get_db
            import uuid

            db = get_db()
            task_id = f"startup_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sync_tasks (task_id, task_type, status, progress, total, error_message)
                    VALUES ($1, 'startup_validation', $2, 100, 100, $3)
                    ON CONFLICT (task_id) DO NOTHING
                    """,
                    task_id,
                    report.get("status", "unknown"),
                    json.dumps(report.get("details", {}), ensure_ascii=False, default=str),
                )
            logger.info("[StartupValidator] 校验报告已写入 sync_tasks (task_id=%s)", task_id)
        except Exception as e:
            logger.warning("[StartupValidator] 写入 sync_tasks 失败: %s", e)


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------
_validator: Optional[StartupValidator] = None


def get_startup_validator() -> StartupValidator:
    """获取或创建全局 StartupValidator 实例"""
    global _validator
    if _validator is None:
        _validator = StartupValidator()
    return _validator
