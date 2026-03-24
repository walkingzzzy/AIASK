"""数据同步管理器 - MCP 工具层，供用户/AI 按需触发同步任务。

与 DataSyncScheduler (services/data_sync_scheduler.py) 的区别：
- DataSyncScheduler 是后台自动调度器（启动时 + 每日 15:30）
- 本模块是 MCP 工具，通过 ``data_sync_manager(action=...)`` 按需执行
- sync_daily/sync_init.py 是独立脚本，用于深度历史全量回填
"""

import argparse
import contextlib
import importlib.util
import json
import logging
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta
from ...storage import get_db
from ...utils import ok, fail

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    return kwargs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _core_market_script_path() -> Path:
    return _repo_root() / "scripts" / "audit_sync_core_market_data.py"


def _factor_context_script_path() -> Path:
    return _repo_root() / "scripts" / "audit_sync_factor_context_data.py"


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _normalize_codes(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace(";", ",").split(",")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _decode_json_obj(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "{}")
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _compute_next_run(schedule: str, now: datetime | None = None) -> datetime:
    current = (now or _now_local()).astimezone()
    normalized = str(schedule or "daily").strip().lower()
    delta_map = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }
    if normalized not in delta_map:
        raise ValueError(f"不支持的schedule: {schedule}")
    return (current + delta_map[normalized]).replace(microsecond=0)


def _build_schedule_params(task_type: str, kwargs: dict, codes: list[str]) -> dict:
    params: dict = {}
    if kwargs.get("priority"):
        params["priority"] = str(kwargs.get("priority"))

    if task_type == "core_market":
        params["years"] = max(int(kwargs.get("years", 1) or 1), 1)
        params["north_days"] = max(int(kwargs.get("north_days", 365) or 365), 1)
        params["margin_days"] = max(int(kwargs.get("margin_days", 90) or 90), 1)
        params["calendar_year"] = int(kwargs.get("calendar_year") or _now_local().year)
        stock_codes = _normalize_codes(kwargs.get("stock_codes"))
        if stock_codes:
            params["stock_codes"] = stock_codes
        elif codes:
            params["stock_codes"] = list(codes)
    elif task_type == "factor_context":
        params["news_days"] = max(int(kwargs.get("news_days", 30) or 30), 1)
        params["notice_days"] = max(int(kwargs.get("notice_days", 30) or 30), 1)
        params["item_limit"] = max(int(kwargs.get("item_limit", 10) or 10), 1)
        params["active_pool_limit"] = max(int(kwargs.get("active_pool_limit", 12) or 12), 1)
        params["task_run_limit"] = max(int(kwargs.get("task_run_limit", 50) or 50), 1)
        params["scope_sources"] = str(
            kwargs.get("scope_sources") or "explicit,representative,active_pool,factory_targets"
        ).strip()
    elif task_type == "vector_backfill_market_docs":
        stock_codes = _normalize_codes(kwargs.get("stock_codes"))
        if stock_codes:
            params["stock_codes"] = stock_codes
        elif codes:
            params["stock_codes"] = list(codes)
        doc_types = _normalize_codes(kwargs.get("doc_types"))
        if doc_types:
            params["doc_types"] = [str(item).strip().lower() for item in doc_types if str(item).strip()]
        if kwargs.get("start_date"):
            params["start_date"] = str(kwargs.get("start_date")).strip()
        if kwargs.get("end_date"):
            params["end_date"] = str(kwargs.get("end_date")).strip()
        params["limit"] = max(int(kwargs.get("limit", 500) or 500), 1)
        params["batch_size"] = max(int(kwargs.get("batch_size", 100) or 100), 1)
        params["chunk_size"] = max(int(kwargs.get("chunk_size", 800) or 800), 200)
        params["overlap"] = max(int(kwargs.get("overlap", 120) or 120), 0)
        params["embed"] = _as_bool(kwargs.get("embed", True), True)
        params["dry_run"] = _as_bool(kwargs.get("dry_run", False), False)
        params["rebuild_existing"] = _as_bool(kwargs.get("rebuild_existing", False), False)
        params["include_legacy_research_docs"] = _as_bool(
            kwargs.get("include_legacy_research_docs", False),
            False,
        )
    elif task_type == "vector_backfill_kline_patterns":
        stock_codes = _normalize_codes(kwargs.get("stock_codes"))
        if stock_codes:
            params["stock_codes"] = stock_codes
        elif codes:
            params["stock_codes"] = list(codes)
        params["code_limit"] = max(int(kwargs.get("code_limit", 200) or 200), 1)
        params["window_size"] = max(int(kwargs.get("window_size", kwargs.get("days", 20)) or 20), 5)
        params["lookback_days"] = max(int(kwargs.get("lookback_days", 180) or 180), params["window_size"])
        params["max_windows_per_code"] = max(int(kwargs.get("max_windows_per_code", 1) or 1), 1)
        params["step_days"] = max(int(kwargs.get("step_days", 5) or 5), 1)
        params["vector_method"] = str(kwargs.get("vector_method", "returns") or "returns").strip().lower()
        params["period"] = str(kwargs.get("period", "daily") or "daily").strip().lower()
        params["adjust"] = str(kwargs.get("adjust", "") or "").strip().lower()
        params["version"] = str(kwargs.get("version", "v1") or "v1").strip()
        params["dry_run"] = _as_bool(kwargs.get("dry_run", False), False)
        params["rebuild_existing"] = _as_bool(kwargs.get("rebuild_existing", False), False)
    elif task_type == "vector_backfill_stock_profiles":
        stock_codes = _normalize_codes(kwargs.get("stock_codes"))
        if stock_codes:
            params["stock_codes"] = stock_codes
        elif codes:
            params["stock_codes"] = list(codes)
        profile_types = _normalize_codes(kwargs.get("profile_types") or kwargs.get("similarity_types"))
        if profile_types:
            params["profile_types"] = [str(item).strip().lower() for item in profile_types if str(item).strip()]
        params["code_limit"] = max(int(kwargs.get("code_limit", 200) or 200), 1)
        params["kline_limit"] = max(int(kwargs.get("kline_limit", 90) or 90), 30)
        params["version"] = str(kwargs.get("version", "v1") or "v1").strip()
        params["dry_run"] = _as_bool(kwargs.get("dry_run", False), False)
        params["rebuild_existing"] = _as_bool(kwargs.get("rebuild_existing", False), False)
    elif task_type == "vector_backfill_factor_candidates":
        params["limit"] = max(int(kwargs.get("limit", 200) or 200), 1)
        codes_arg = _normalize_codes(kwargs.get("codes") or kwargs.get("stock_codes"))
        if codes_arg:
            params["codes"] = list(codes_arg)
        if kwargs.get("status"):
            params["status"] = str(kwargs.get("status")).strip().lower()
        if kwargs.get("family"):
            params["family"] = str(kwargs.get("family")).strip().lower()
        params["version"] = str(kwargs.get("version", "v1") or "v1").strip()
        params["dry_run"] = _as_bool(kwargs.get("dry_run", False), False)
        params["rebuild_existing"] = _as_bool(kwargs.get("rebuild_existing", False), False)
    else:
        period = kwargs.get("period")
        if period:
            params["period"] = str(period)

    return params


def _build_task_payload(task_type: str, codes: list[str], payload: dict | None = None) -> dict:
    merged = dict(payload or {})
    if codes:
        merged["codes"] = list(codes)
    if task_type == "core_market":
        stock_codes = _normalize_codes(merged.get("stock_codes"))
        if not stock_codes and codes:
            stock_codes = list(codes)
        if stock_codes:
            merged["stock_codes"] = stock_codes
    elif task_type == "factor_context":
        merged["codes"] = list(codes)
    elif task_type == "vector_backfill_market_docs":
        stock_codes = _normalize_codes(merged.get("stock_codes"))
        if not stock_codes and codes:
            stock_codes = list(codes)
        if stock_codes:
            merged["stock_codes"] = stock_codes
        doc_types = _normalize_codes(merged.get("doc_types"))
        if doc_types:
            merged["doc_types"] = [str(item).strip().lower() for item in doc_types if str(item).strip()]
    elif task_type == "vector_backfill_kline_patterns":
        stock_codes = _normalize_codes(merged.get("stock_codes"))
        if not stock_codes and codes:
            stock_codes = list(codes)
        if stock_codes:
            merged["stock_codes"] = stock_codes
    elif task_type == "vector_backfill_stock_profiles":
        stock_codes = _normalize_codes(merged.get("stock_codes"))
        if not stock_codes and codes:
            stock_codes = list(codes)
        if stock_codes:
            merged["stock_codes"] = stock_codes
        profile_types = _normalize_codes(merged.get("profile_types") or merged.get("similarity_types"))
        if profile_types:
            merged["profile_types"] = [str(item).strip().lower() for item in profile_types if str(item).strip()]
    elif task_type == "vector_backfill_factor_candidates":
        record_codes = _normalize_codes(merged.get("codes") or merged.get("stock_codes"))
        if record_codes:
            merged["codes"] = record_codes
    return merged


async def _update_schedule_runtime(db, schedule_id: str, *, last_run: datetime, next_run: datetime) -> None:
    async with db.acquire() as conn:
        try:
            await conn.execute(
                """
                UPDATE sync_schedules
                SET last_run = $2, next_run = $3, updated_at = NOW()
                WHERE schedule_id = $1
                """,
                schedule_id,
                last_run,
                next_run,
            )
        except Exception:
            await conn.execute(
                """
                UPDATE sync_schedules
                SET last_run = $2, next_run = $3
                WHERE schedule_id = $1
                """,
                schedule_id,
                last_run,
                next_run,
            )


async def _execute_sync_task(
    db,
    *,
    task_type: str,
    codes: list[str],
    priority: str,
    payload: dict | None = None,
    trigger: str = "manual",
    schedule_id: str | None = None,
) -> dict:
    task_id = f"sync_{task_type}_{int(datetime.now().timestamp())}"
    results = {"success": 0, "failed": 0, "errors": []}
    final_status = "completed"
    effective_codes = _normalize_codes(codes)
    effective_payload = _build_task_payload(task_type, effective_codes, payload)

    if task_type not in {
        "core_market",
        "factor_context",
        "vector_backfill_market_docs",
        "vector_backfill_kline_patterns",
        "vector_backfill_stock_profiles",
        "vector_backfill_factor_candidates",
    } and not effective_codes:
        raise ValueError("需要提供codes参数")

    try:
        async with db.acquire() as conn:
            await conn.execute(
                """INSERT INTO sync_tasks (task_id, task_type, codes, priority, status, created_at)
                   VALUES ($1, $2, $3, $4, 'running', NOW())""",
                task_id,
                task_type,
                effective_codes,
                priority,
            )
    except Exception as e:
        logger.warning(f"[DataSyncManager] 写入任务记录失败: {e}")

    try:
        if task_type == "kline":
            results = await _sync_klines_now(effective_codes)
        elif task_type == "financial":
            results = await _sync_financials_check(effective_codes)
        elif task_type == "core_market":
            results = await _sync_core_market_now(effective_payload)
        elif task_type == "factor_context":
            results = await _sync_factor_context_now(effective_payload)
        elif task_type == "vector_backfill_market_docs":
            results = await _sync_vector_backfill_market_docs_now(effective_payload)
        elif task_type == "vector_backfill_kline_patterns":
            results = await _sync_vector_backfill_kline_patterns_now(effective_payload)
        elif task_type == "vector_backfill_stock_profiles":
            results = await _sync_vector_backfill_stock_profiles_now(effective_payload)
        elif task_type == "vector_backfill_factor_candidates":
            results = await _sync_vector_backfill_factor_candidates_now(effective_payload)
        else:
            results = await _sync_klines_now(effective_codes)

        if results.get("failed", 0) > 0 and results.get("success", 0) == 0:
            final_status = "failed"
    except Exception as e:
        final_status = "failed"
        results["errors"].append(str(e))
        logger.warning(f"[DataSyncManager] 同步执行异常: {e}")

    try:
        async with db.acquire() as conn:
            try:
                await conn.execute(
                    """
                    UPDATE sync_tasks
                    SET status = $1, error_message = $2, updated_at = NOW(), completed_at = NOW()
                    WHERE task_id = $3
                    """,
                    final_status,
                    "; ".join(results.get("errors") or [])[:2000] or None,
                    task_id,
                )
            except Exception:
                await conn.execute(
                    "UPDATE sync_tasks SET status = $1 WHERE task_id = $2",
                    final_status,
                    task_id,
                )
    except Exception:
        pass

    return {
        "task_id": task_id,
        "task_type": task_type,
        "codes_count": len(effective_codes),
        "priority": priority,
        "status": final_status,
        "results": results,
        "trigger": trigger,
        "schedule_id": schedule_id,
        "message": f'同步完成: 成功 {results.get("success", 0)}, 失败 {results.get("failed", 0)}',
    }


async def _run_due_schedules(
    db,
    *,
    force: bool = False,
    limit: int = 20,
    schedule_id: str | None = None,
    task_type: str | None = None,
) -> dict:
    now = _now_local()
    async with db.acquire() as conn:
        if force:
            if schedule_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sync_schedules
                    WHERE enabled = true AND schedule_id = $1
                    ORDER BY COALESCE(next_run, created_at) ASC
                    LIMIT $2
                    """,
                    schedule_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sync_schedules
                    WHERE enabled = true
                    ORDER BY COALESCE(next_run, created_at) ASC
                    LIMIT $1
                    """,
                    limit,
                )
        else:
            if schedule_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sync_schedules
                    WHERE enabled = true
                      AND schedule_id = $1
                      AND (next_run IS NULL OR next_run <= $2)
                    ORDER BY COALESCE(next_run, created_at) ASC
                    LIMIT $3
                    """,
                    schedule_id,
                    now,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sync_schedules
                    WHERE enabled = true
                      AND (next_run IS NULL OR next_run <= $1)
                    ORDER BY COALESCE(next_run, created_at) ASC
                    LIMIT $2
                    """,
                    now,
                    limit,
                )

    if task_type:
        normalized_task_type = str(task_type).strip().lower()
        rows = [
            row for row in rows
            if str(dict(row).get("task_type") or "").strip().lower() == normalized_task_type
        ]
    rows = list(rows)[: max(1, int(limit or 20))]

    executions = []
    for row in rows:
        schedule = dict(row)
        schedule["params"] = _decode_json_obj(schedule.get("params"))
        task_type = str(schedule.get("task_type") or "kline")
        codes = _normalize_codes(schedule.get("codes"))
        params = dict(schedule.get("params") or {})
        priority = str(params.get("priority") or "normal")
        payload = _build_task_payload(task_type, codes, params)
        run_started_at = _now_local()
        result = await _execute_sync_task(
            db,
            task_type=task_type,
            codes=codes,
            priority=priority,
            payload=payload,
            trigger="schedule",
            schedule_id=str(schedule.get("schedule_id")),
        )
        next_run = _compute_next_run(str(schedule.get("schedule") or "daily"), run_started_at)
        await _update_schedule_runtime(
            db,
            str(schedule.get("schedule_id")),
            last_run=run_started_at,
            next_run=next_run,
        )
        executions.append(
            {
                "schedule_id": schedule.get("schedule_id"),
                "task_type": task_type,
                "schedule": schedule.get("schedule"),
                "last_run": run_started_at.isoformat(),
                "next_run": next_run.isoformat(),
                "task": result,
            }
        )

    return {
        "matched": len(rows),
        "executed": len(executions),
        "force": force,
        "schedules": executions,
    }


async def _count_enabled_schedules(db, *, task_type: str) -> int:
    async with db.acquire() as conn:
        try:
            value = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM sync_schedules
                WHERE enabled = true AND task_type = $1
                """,
                str(task_type or "").strip().lower(),
            )
            return int(value or 0)
        except Exception:
            return 0


async def _ensure_runtime_warmup_schedule(db, *, task_type: str) -> dict:
    normalized_task_type = str(task_type or "core_market").strip().lower() or "core_market"
    schedule_id = f"schedule_runtime_{normalized_task_type}"
    params = _build_schedule_params(normalized_task_type, {}, [])
    next_run = _now_local().replace(microsecond=0)
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sync_schedules (schedule_id, task_type, codes, schedule, params, enabled, next_run, created_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, NOW())
            ON CONFLICT (schedule_id) DO UPDATE SET
                task_type = EXCLUDED.task_type,
                codes = EXCLUDED.codes,
                schedule = EXCLUDED.schedule,
                params = EXCLUDED.params,
                enabled = EXCLUDED.enabled,
                next_run = EXCLUDED.next_run
            """,
            schedule_id,
            normalized_task_type,
            [],
            "daily",
            json.dumps(params, ensure_ascii=False, default=str),
            True,
            next_run,
        )
    return {
        "schedule_id": schedule_id,
        "task_type": normalized_task_type,
        "schedule": "daily",
        "enabled": True,
        "params": params,
        "next_run": next_run.isoformat(),
    }


async def run_runtime_data_warmup(
    *,
    task_type: str = "core_market",
    force: bool = False,
    limit: int = 4,
    schedule_id: str | None = None,
    source: str = "runtime",
    bootstrap_missing: bool = True,
) -> dict:
    db = get_db()
    raw_task_type = str(task_type or "core_market").strip().lower() or "core_market"
    task_types = [item for item in _normalize_codes(raw_task_type) if item]
    if not task_types:
        task_types = ["core_market"]

    schedule_results = []
    schedules = []
    bootstrapped_task_types: list[str] = []
    bootstrapped_schedules: list[dict] = []
    for one_task_type in task_types:
        result = await _run_due_schedules(
            db,
            force=force,
            limit=max(1, int(limit or 4)),
            schedule_id=schedule_id,
            task_type=one_task_type,
        )
        if bootstrap_missing and result.get("matched", 0) <= 0:
            existing_schedule_count = await _count_enabled_schedules(db, task_type=one_task_type)
            if existing_schedule_count <= 0:
                bootstrapped = await _ensure_runtime_warmup_schedule(db, task_type=one_task_type)
                bootstrapped_task_types.append(one_task_type)
                bootstrapped_schedules.append(bootstrapped)
                result = await _run_due_schedules(
                    db,
                    force=force,
                    limit=max(1, int(limit or 4)),
                    schedule_id=None,
                    task_type=one_task_type,
                )
                result["bootstrapped"] = True
                result["bootstrap_schedule"] = bootstrapped
            else:
                result["bootstrapped"] = False
        else:
            result["bootstrapped"] = False
        schedule_results.append({"task_type": one_task_type, **result})
        schedules.extend(list(result.get("schedules") or []))

    failed_items = [
        item for item in schedules
        if str(((item.get("task") or {}).get("status") or "")).strip().lower() not in {"completed", "success"}
    ]
    status = "completed"
    ok = True
    matched_total = sum(int(item.get("matched") or 0) for item in schedule_results)
    executed_total = sum(int(item.get("executed") or 0) for item in schedule_results)
    if matched_total <= 0:
        status = "skipped"
    elif failed_items and len(failed_items) == len(schedules):
        status = "failed"
        ok = False
    elif failed_items:
        status = "partial"

    return {
        "ok": ok,
        "status": status,
        "source": source,
        "task_type": raw_task_type,
        "task_types": task_types,
        "force": bool(force),
        "bootstrap_missing": bool(bootstrap_missing),
        "bootstrapped_task_types": bootstrapped_task_types,
        "bootstrapped_schedules": bootstrapped_schedules,
        "schedule_id": schedule_id,
        "matched": matched_total,
        "executed": executed_total,
        "failed": len(failed_items),
        "executed_task_ids": [
            (item.get("task") or {}).get("task_id")
            for item in schedules
            if (item.get("task") or {}).get("task_id")
        ],
        "failed_schedule_ids": [
            item.get("schedule_id")
            for item in failed_items
            if item.get("schedule_id")
        ],
        "results_by_task_type": schedule_results,
        "schedules": schedules,
    }


async def _load_market_aux_status(db) -> dict:
    async with db.acquire() as conn:
        async def _fetch_meta(table: str, date_col: str = "trade_date") -> dict:
            try:
                row = await conn.fetchrow(
                    f"SELECT COUNT(*) AS cnt, MIN({date_col}) AS min_d, MAX({date_col}) AS max_d FROM {table}"
                )
            except Exception:
                row = None
            if not row:
                return {"count": 0, "min_date": None, "max_date": None}
            return {
                "count": int(row.get("cnt") or 0),
                "min_date": row.get("min_d").isoformat() if row.get("min_d") else None,
                "max_date": row.get("max_d").isoformat() if row.get("max_d") else None,
            }

        return {
            "north_fund_flow": await _fetch_meta("north_fund_flow"),
            "margin_market_flow": await _fetch_meta("margin_market_flow"),
            "margin_detail": await _fetch_meta("margin_detail"),
            "vector_documents": await conn.fetchval("SELECT COUNT(*) FROM vector_documents") or 0,
            "vector_documents_news": await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'news'") or 0,
            "vector_documents_notice": await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'notice'") or 0,
            "vector_documents_research": await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'research'") or 0,
            "market_documents": await conn.fetchval("SELECT COUNT(*) FROM market_documents") or 0,
            "market_doc_chunks": await conn.fetchval("SELECT COUNT(*) FROM market_doc_chunks") or 0,
            "market_doc_chunks_news": await conn.fetchval("SELECT COUNT(*) FROM market_doc_chunks WHERE doc_type = 'news'") or 0,
            "market_doc_chunks_notice": await conn.fetchval("SELECT COUNT(*) FROM market_doc_chunks WHERE doc_type = 'notice'") or 0,
            "market_doc_chunks_research": await conn.fetchval("SELECT COUNT(*) FROM market_doc_chunks WHERE doc_type = 'research'") or 0,
            "vector_collections": await conn.fetchval("SELECT COUNT(*) FROM vector_collections") or 0,
            "vector_profiles": await conn.fetchval("SELECT COUNT(*) FROM vector_profiles") or 0,
            "kline_pattern_windows": await conn.fetchval("SELECT COUNT(*) FROM kline_pattern_windows") or 0,
            "vector_profiles_kline_patterns": await conn.fetchval(
                "SELECT COUNT(*) FROM vector_profiles WHERE collection_name = 'kline_pattern_embeddings'"
            ) or 0,
            "vector_profiles_stock_profiles": await conn.fetchval(
                "SELECT COUNT(*) FROM vector_profiles WHERE collection_name = 'stock_profile_embeddings'"
            ) or 0,
            "vector_profiles_factor_candidates": await conn.fetchval(
                "SELECT COUNT(*) FROM vector_profiles WHERE collection_name = 'factor_candidate_embeddings'"
            ) or 0,
            "research_reports": await _fetch_meta("research_reports", date_col="publish_date"),
            "stock_fund_flow": await _fetch_meta("stock_fund_flow"),
        }


def register_data_sync_manager(mcp):
    """注册数据同步管理器工具"""
    
    @mcp.tool()
    async def data_sync_manager(action: str, **kwargs):
        """数据同步管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/status/sync/get_task/list_tasks/cancel_task/schedule
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - status: 无需额外参数（查看同步状态）
                - sync: codes(list[str]), period(str, optional)
                - get_task: task_id(str)
                - list_tasks: status(str, optional)
                - cancel_task: task_id(str)
                - schedule: codes(list[str]), cron(str, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            data_sync_manager(action="help", kwargs="{}")
            # 查看同步状态
            data_sync_manager(action="status", kwargs="{}")
            # 同步指定股票K线
            data_sync_manager(action="sync", kwargs='{"codes":["600519","000001"],"period":"daily"}')
            # 列出同步任务
            data_sync_manager(action="list_tasks", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(kwargs)

            if action == 'list':
                action = 'list_tasks'

            if action == 'help':
                return ok({
                    'supported_actions': {
                        'status': '数据同步状态',
                        'sync': '执行数据同步（K线/财务需 codes；core_market/vector_backfill_market_docs/vector_backfill_kline_patterns/vector_backfill_stock_profiles/vector_backfill_factor_candidates 可直接运行）',
                        'get_task': '获取任务详情（需要 task_id）',
                        'list_tasks': '列出同步任务',
                        'cancel_task': '取消任务（需要 task_id）',
                        'schedule': '创建调度任务',
                        'list_schedules': '列出已登记调度',
                        'run_due_schedules': '执行到期调度（force=true 可强制执行）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'status':
                async with db.acquire() as conn:
                    async def _max_ts(c, table_cols):
                        for table, col in table_cols:
                            try:
                                return await c.fetchval(f"SELECT MAX({col}) FROM {table}")
                            except Exception:
                                continue
                        return None
                    kline_sync = await _max_ts(conn, [('kline_1d', 'updated_at'), ('kline_1d', 'time')])
                    quote_sync = await _max_ts(conn, [('stock_quotes', 'updated_at'), ('stock_quotes', 'time')])
                    financial_sync = await _max_ts(conn, [('financials', 'updated_at'), ('financials', 'report_date')])
                    pending_tasks = await conn.fetchval(
                        "SELECT COUNT(*) FROM sync_tasks WHERE status = 'pending'"
                    ) or 0
                    running_tasks = await conn.fetchval(
                        "SELECT COUNT(*) FROM sync_tasks WHERE status = 'running'"
                    ) or 0
                    due_schedule_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM sync_schedules
                        WHERE enabled = true
                          AND (next_run IS NULL OR next_run <= NOW())
                        """
                    ) or 0
                    next_schedule_run = await conn.fetchval(
                        """
                        SELECT MIN(next_run)
                        FROM sync_schedules
                        WHERE enabled = true AND next_run IS NOT NULL
                        """
                    )
                def _ts_iso(ts):
                    if ts is None:
                        return None
                    return ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                return ok({
                    'last_sync': {
                        'kline': _ts_iso(kline_sync),
                        'quote': _ts_iso(quote_sync),
                        'financial': _ts_iso(financial_sync),
                    },
                    'market_aux': await _load_market_aux_status(db),
                    'status': 'running' if running_tasks > 0 else 'idle',
                    'pending_tasks': int(pending_tasks),
                    'running_tasks': int(running_tasks),
                    'due_schedule_count': int(due_schedule_count),
                    'next_schedule_run': _ts_iso(next_schedule_run),
                })
            
            elif action == 'sync':
                task_type = kwargs.get('type', 'kline')
                codes = _normalize_codes(kwargs.get('codes') or kwargs.get('stock_codes'))
                priority = kwargs.get('priority', 'normal')

                if task_type not in {
                    'core_market',
                    'factor_context',
                    'vector_backfill_market_docs',
                    'vector_backfill_kline_patterns',
                    'vector_backfill_stock_profiles',
                    'vector_backfill_factor_candidates',
                } and not codes:
                    return fail('需要提供codes参数')
                payload = _build_task_payload(task_type, codes, kwargs)
                result = await _execute_sync_task(
                    db,
                    task_type=task_type,
                    codes=codes,
                    priority=str(priority),
                    payload=payload,
                )
                return ok(result)
            
            elif action == 'get_task':
                task_id = kwargs.get('task_id')
                
                if not task_id:
                    return fail('需要提供task_id参数')
                
                async with db.acquire() as conn:
                    task = await conn.fetchrow(
                        "SELECT * FROM sync_tasks WHERE task_id = $1",
                        task_id
                    )
                    
                    if not task:
                        return fail(f'未找到任务: {task_id}')
                    
                    task_data = dict(task)
                
                return ok(task_data)
            
            elif action == 'list_tasks':
                status = kwargs.get('status')
                limit = kwargs.get('limit', 20)
                
                async with db.acquire() as conn:
                    if status:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_tasks WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
                            status, limit
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_tasks ORDER BY created_at DESC LIMIT $1",
                            limit
                        )
                    
                    tasks = [dict(row) for row in rows]
                
                return ok({
                    'tasks': tasks,
                    'count': len(tasks),
                })
            
            elif action == 'cancel_task':
                task_id = kwargs.get('task_id')
                
                if not task_id:
                    return fail('需要提供task_id参数')
                
                async with db.acquire() as conn:
                    try:
                        result = await conn.execute(
                            "UPDATE sync_tasks SET status = 'cancelled', updated_at = NOW() WHERE task_id = $1 AND status IN ('pending', 'running')",
                            task_id
                        )
                    except Exception:
                        result = await conn.execute(
                            "UPDATE sync_tasks SET status = 'cancelled' WHERE task_id = $1 AND status IN ('pending', 'running')",
                            task_id
                        )
                    if result == 'UPDATE 0':
                        return fail('任务不存在或无法取消（已完成或已失败）')
                
                return ok({
                    'task_id': task_id,
                    'status': 'cancelled',
                })
            
            elif action == 'schedule':
                task_type = kwargs.get('type', 'kline')
                codes = _normalize_codes(kwargs.get('codes') or kwargs.get('stock_codes'))
                schedule = str(kwargs.get('schedule', 'daily')).strip().lower()
                enabled = _as_bool(kwargs.get('enabled', True), True)
                
                if task_type not in {
                    'core_market',
                    'factor_context',
                    'vector_backfill_market_docs',
                    'vector_backfill_kline_patterns',
                    'vector_backfill_stock_profiles',
                    'vector_backfill_factor_candidates',
                } and not codes:
                    return fail('需要提供codes参数')
                
                schedule_id = f'schedule_{task_type}_{int(datetime.now().timestamp())}'
                next_run = _compute_next_run(schedule)
                params = _build_schedule_params(task_type, kwargs, codes)
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO sync_schedules (schedule_id, task_type, codes, schedule, params, enabled, next_run, created_at)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, NOW())
                        """,
                        schedule_id,
                        task_type,
                        codes,
                        schedule,
                        json.dumps(params, ensure_ascii=False, default=str),
                        enabled,
                        next_run,
                    )
                
                return ok({
                    'schedule_id': schedule_id,
                    'task_type': task_type,
                    'schedule': schedule,
                    'codes_count': len(codes),
                    'enabled': enabled,
                    'params': params,
                    'next_run': next_run.isoformat(),
                })

            elif action == 'list_schedules':
                enabled = kwargs.get('enabled')
                schedule_id = kwargs.get('schedule_id')
                limit = int(kwargs.get('limit', 20) or 20)

                async with db.acquire() as conn:
                    if schedule_id and enabled is None:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_schedules WHERE schedule_id = $1 ORDER BY created_at DESC LIMIT $2",
                            str(schedule_id),
                            limit,
                        )
                    elif schedule_id and enabled is not None:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_schedules WHERE schedule_id = $1 AND enabled = $2 ORDER BY created_at DESC LIMIT $3",
                            str(schedule_id),
                            _as_bool(enabled),
                            limit,
                        )
                    elif enabled is None:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_schedules ORDER BY created_at DESC LIMIT $1",
                            limit,
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_schedules WHERE enabled = $1 ORDER BY created_at DESC LIMIT $2",
                            _as_bool(enabled),
                            limit,
                        )

                schedules = []
                for row in rows:
                    item = dict(row)
                    item['params'] = _decode_json_obj(item.get('params'))
                    schedules.append(item)

                return ok({
                    'schedules': schedules,
                    'count': len(schedules),
                })

            elif action == 'run_due_schedules':
                force = _as_bool(kwargs.get('force', False), False)
                schedule_id = kwargs.get('schedule_id')
                task_type = kwargs.get('task_type')
                limit = int(kwargs.get('limit', 20) or 20)
                result = await _run_due_schedules(
                    db,
                    force=force,
                    limit=limit,
                    schedule_id=str(schedule_id).strip() if schedule_id else None,
                    task_type=str(task_type).strip() if task_type else None,
                )
                return ok(result)
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, status, sync, get_task, list_tasks, cancel_task, schedule, list_schedules, run_due_schedules')
        except Exception as e:
            return fail(str(e))


async def _sync_klines_now(codes: list) -> dict:
    """立即执行K线同步，使用 data_source.get_kline() 完整降级链"""
    from ...data_source import data_source
    from ...storage import get_db

    db = get_db()
    results = {'success': 0, 'failed': 0, 'errors': []}

    for code in codes:
        try:
            klines = data_source.get_kline(code, 'daily', 250)
            if klines:
                try:
                    await db.save_klines(code, klines)
                except Exception as e:
                    logger.warning(f"[DataSyncManager] {code} K线写入DB失败: {e}")
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"{code}: 所有数据源均无数据")
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{code}: {e}")

    # 截断错误列表避免过长
    if len(results['errors']) > 10:
        total = len(results['errors'])
        results['errors'] = results['errors'][:10] + [f'...及其他 {total - 10} 个错误']

    return results


async def _sync_financials_check(codes: list) -> dict:
    """检查财务数据是否存在，不存在则提示用户运行 sync_init.py"""
    from ...storage import get_db

    db = get_db()
    results = {'success': 0, 'failed': 0, 'errors': [], 'message': ''}

    missing = []
    for code in codes:
        try:
            async with db.acquire() as conn:
                cnt = await conn.fetchval(
                    "SELECT COUNT(*) FROM financials WHERE stock_code = $1", code
                )
                if cnt and cnt > 0:
                    results['success'] += 1
                else:
                    missing.append(code)
                    results['failed'] += 1
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{code}: {e}")

    if missing:
        results['message'] = (
            f'{len(missing)} 只股票无财务数据，'
            f'建议运行 python sync_init.py 进行历史数据初始化'
        )

    return results


async def _sync_core_market_now(kwargs: dict) -> dict:
    """调用核心市场审查补数脚本，补齐指数/北向/融资融券数据。"""
    script_path = _core_market_script_path()
    if not script_path.exists():
        return {'success': 0, 'failed': 1, 'errors': [f'脚本不存在: {script_path}']}

    spec = importlib.util.spec_from_file_location("audit_sync_core_market_data_runtime", script_path)
    if spec is None or spec.loader is None:
        return {'success': 0, 'failed': 1, 'errors': [f'无法加载脚本: {script_path}']}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = argparse.Namespace(
        years=max(int(kwargs.get('years', 1) or 1), 1),
        stock_codes=",".join([str(item).strip() for item in list(kwargs.get('codes') or kwargs.get('stock_codes') or []) if str(item).strip()])
        if isinstance(kwargs.get('codes') or kwargs.get('stock_codes'), list)
        else str(kwargs.get('stock_codes') or kwargs.get('codes') or ",".join(getattr(module, 'DEFAULT_STOCK_CODES', []))),
        calendar_year=int(kwargs.get('calendar_year') or datetime.now().year),
        north_days=max(int(kwargs.get('north_days', 365) or 365), 1),
        margin_days=max(int(kwargs.get('margin_days', 90) or 90), 1),
    )

    capture = StringIO()
    exit_code = 1
    with contextlib.redirect_stdout(capture):
        exit_code = await module._main(args)

    db = get_db()
    market_aux = await _load_market_aux_status(db)
    output_lines = [line for line in capture.getvalue().splitlines() if line.strip()]
    tail_lines = output_lines[-40:]
    result = {
        'success': 1 if exit_code == 0 else 0,
        'failed': 0 if exit_code == 0 else 1,
        'errors': [] if exit_code == 0 else [f'core_market_sync exit_code={exit_code}'],
        'exit_code': int(exit_code),
        'args': {
            'years': args.years,
            'stock_codes': args.stock_codes,
            'calendar_year': args.calendar_year,
            'north_days': args.north_days,
            'margin_days': args.margin_days,
        },
        'market_aux': market_aux,
        'stdout_tail': tail_lines,
    }
    return result


async def _sync_factor_context_now(kwargs: dict) -> dict:
    """调用因子上下文补数脚本，补齐新闻/公告/研报/个股资金流。"""
    script_path = _factor_context_script_path()
    if not script_path.exists():
        return {'success': 0, 'failed': 1, 'errors': [f'脚本不存在: {script_path}']}

    spec = importlib.util.spec_from_file_location("audit_sync_factor_context_runtime", script_path)
    if spec is None or spec.loader is None:
        return {'success': 0, 'failed': 1, 'errors': [f'无法加载脚本: {script_path}']}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_codes = kwargs.get('codes') or kwargs.get('stock_codes')
    args = argparse.Namespace(
        codes=",".join([str(item).strip() for item in list(raw_codes) if str(item).strip()]) if isinstance(raw_codes, list) else str(raw_codes or ""),
        scope_sources=str(kwargs.get('scope_sources') or "explicit,representative,active_pool,factory_targets"),
        active_pool_limit=max(int(kwargs.get('active_pool_limit', 12) or 12), 1),
        task_run_limit=max(int(kwargs.get('task_run_limit', 50) or 50), 1),
        news_days=max(int(kwargs.get('news_days', 30) or 30), 1),
        notice_days=max(int(kwargs.get('notice_days', 30) or 30), 1),
        item_limit=max(int(kwargs.get('item_limit', 10) or 10), 1),
    )

    capture = StringIO()
    exit_code = 1
    with contextlib.redirect_stdout(capture):
        exit_code = await module._main(args)

    db = get_db()
    market_aux = await _load_market_aux_status(db)
    output_lines = [line for line in capture.getvalue().splitlines() if line.strip()]
    tail_lines = output_lines[-40:]
    return {
        'success': 1 if exit_code == 0 else 0,
        'failed': 0 if exit_code == 0 else 1,
        'errors': [] if exit_code == 0 else [f'factor_context_sync exit_code={exit_code}'],
        'exit_code': int(exit_code),
        'args': {
            'codes': args.codes,
            'scope_sources': args.scope_sources,
            'active_pool_limit': args.active_pool_limit,
            'task_run_limit': args.task_run_limit,
            'news_days': args.news_days,
            'notice_days': args.notice_days,
            'item_limit': args.item_limit,
        },
        'market_aux': market_aux,
        'stdout_tail': tail_lines,
    }


async def _sync_vector_backfill_market_docs_now(kwargs: dict) -> dict:
    """回填历史市场文本到统一向量层。"""
    from ...services.vector_backfill import backfill_market_document_vectors

    db = get_db()
    result = await backfill_market_document_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        doc_types=kwargs.get('doc_types'),
        start_date=kwargs.get('start_date'),
        end_date=kwargs.get('end_date'),
        limit=kwargs.get('limit', 500),
        batch_size=kwargs.get('batch_size', 100),
        embed=kwargs.get('embed', True),
        chunk_size=kwargs.get('chunk_size', 800),
        overlap=kwargs.get('overlap', 120),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
        include_legacy_research_docs=kwargs.get('include_legacy_research_docs', False),
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'doc_types': result.get('doc_types'),
            'start_date': result.get('start_date'),
            'end_date': result.get('end_date'),
            'limit': result.get('limit'),
            'batch_size': result.get('batch_size'),
            'embed': result.get('embed'),
            'chunk_size': result.get('chunk_size'),
            'overlap': result.get('overlap'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
            'include_legacy_research_docs': result.get('include_legacy_research_docs'),
        },
        'backfill': result,
        'market_aux': market_aux,
        'message': (
            f"market_doc_backfill docs={int(result.get('saved_docs') or 0)} "
            f"chunks={int(result.get('saved_chunks') or 0)} "
            f"embedded={int(result.get('embedded_chunks') or 0)}"
        ),
    }


async def _sync_vector_backfill_kline_patterns_now(kwargs: dict) -> dict:
    """回填 K 线模式窗口到统一向量层。"""
    from ...services.pattern_embedding_pipeline import backfill_kline_pattern_vectors

    db = get_db()
    result = await backfill_kline_pattern_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        code_limit=kwargs.get('code_limit', 200),
        window_size=kwargs.get('window_size', kwargs.get('days', 20)),
        lookback_days=kwargs.get('lookback_days', 180),
        max_windows_per_code=kwargs.get('max_windows_per_code', 1),
        step_days=kwargs.get('step_days', 5),
        vector_method=kwargs.get('vector_method', 'returns'),
        period=kwargs.get('period', 'daily'),
        adjust=kwargs.get('adjust', ''),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'code_limit': kwargs.get('code_limit', 200),
            'window_size': result.get('window_size'),
            'lookback_days': result.get('lookback_days'),
            'max_windows_per_code': result.get('max_windows_per_code'),
            'step_days': result.get('step_days'),
            'vector_method': result.get('vector_method'),
            'period': result.get('period'),
            'adjust': result.get('adjust'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
        },
        'backfill': result,
        'market_aux': market_aux,
        'message': (
            f"kline_pattern_backfill windows={int(result.get('saved_windows') or 0)} "
            f"profiles={int(result.get('saved_profiles') or 0)}"
        ),
    }


async def _sync_vector_backfill_stock_profiles_now(kwargs: dict) -> dict:
    """回填股票画像向量到统一向量层。"""
    from ...services.stock_profile_pipeline import backfill_stock_profile_vectors

    db = get_db()
    result = await backfill_stock_profile_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        code_limit=kwargs.get('code_limit', 200),
        profile_types=kwargs.get('profile_types') or kwargs.get('similarity_types'),
        kline_limit=kwargs.get('kline_limit', 90),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'code_limit': kwargs.get('code_limit', 200),
            'profile_types': result.get('profile_types'),
            'kline_limit': result.get('kline_limit'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
        },
        'backfill': result,
        'market_aux': market_aux,
        'message': (
            f"stock_profile_backfill profiles={int(result.get('saved_profiles') or 0)} "
            f"codes={int(result.get('processed_codes') or 0)}"
        ),
    }


async def _sync_vector_backfill_factor_candidates_now(kwargs: dict) -> dict:
    """回填因子研究记忆向量到统一向量层。"""
    from ...services.factor_candidate_vector_backfill import backfill_factor_candidate_vectors

    db = get_db()
    result = await backfill_factor_candidate_vectors(
        db,
        limit=kwargs.get('limit', 200),
        codes=kwargs.get('codes') or kwargs.get('stock_codes'),
        status=kwargs.get('status'),
        family=kwargs.get('family'),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'limit': result.get('limit'),
            'codes': result.get('codes'),
            'status': result.get('status'),
            'family': result.get('family'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
        },
        'backfill': result,
        'market_aux': market_aux,
        'message': (
            f"factor_candidate_backfill profiles={int(result.get('saved_profiles') or 0)} "
            f"records={int(result.get('processed_records') or 0)}"
        ),
    }
