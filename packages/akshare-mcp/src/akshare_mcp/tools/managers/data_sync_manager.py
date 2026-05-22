"""数据同步管理器 - MCP 工具层，供用户/AI 按需触发同步任务。

与 DataSyncScheduler (services/data_sync_scheduler.py) 的区别：
- DataSyncScheduler 是后台自动调度器（启动时 + 每日 15:30）
- 本模块是 MCP 工具，通过 ``data_sync_manager(action=...)`` 按需执行
- sync_daily/sync_init.py 是独立脚本，用于深度历史全量回填
"""

from typing import Any
import argparse
import contextlib
import importlib.util
import json
import logging
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta
from ...services.market_data_access import quote_max_stale_seconds
from ...storage import get_db
from ...utils import ok, fail
from ..manager_protocol import normalize_manager_payload

logger = logging.getLogger(__name__)

from . import _data_sync_manager_support_core as _data_sync_core_mod
from . import _data_sync_manager_support_sync as _data_sync_sync_mod

_normalize_codes = _data_sync_core_mod._normalize_codes
_decode_json_obj = _data_sync_core_mod._decode_json_obj
_as_bool = _data_sync_core_mod._as_bool
_compute_next_run = _data_sync_core_mod._compute_next_run
_build_schedule_params = _data_sync_core_mod._build_schedule_params
_build_task_payload = _data_sync_core_mod._build_task_payload
_execute_sync_task = _data_sync_core_mod._execute_sync_task
_run_due_schedules = _data_sync_core_mod._run_due_schedules
_load_market_aux_status = _data_sync_core_mod._load_market_aux_status

_core_market_script_path = _data_sync_core_mod._core_market_script_path
_factor_context_script_path = _data_sync_core_mod._factor_context_script_path
_sync_klines_now = _data_sync_sync_mod._sync_klines_now
_sync_quotes_now = _data_sync_sync_mod._sync_quotes_now
_sync_financials_check = _data_sync_sync_mod._sync_financials_check
_sync_core_market_now = _data_sync_sync_mod._sync_core_market_now
_sync_factor_context_now = _data_sync_sync_mod._sync_factor_context_now
_sync_market_text_source_ingest_now = _data_sync_sync_mod._sync_market_text_source_ingest_now
_sync_vector_backfill_market_docs_now = _data_sync_sync_mod._sync_vector_backfill_market_docs_now
_sync_vector_backfill_kline_patterns_now = _data_sync_sync_mod._sync_vector_backfill_kline_patterns_now
_sync_vector_backfill_stock_profiles_now = _data_sync_sync_mod._sync_vector_backfill_stock_profiles_now
_sync_vector_backfill_factor_candidates_now = _data_sync_sync_mod._sync_vector_backfill_factor_candidates_now
_sync_factor_external_research_ingest_now = _data_sync_sync_mod._sync_factor_external_research_ingest_now
_sync_vector_build_snapshot_now = _data_sync_sync_mod._sync_vector_build_snapshot_now
_sync_vector_benchmark_collection_now = _data_sync_sync_mod._sync_vector_benchmark_collection_now
_sync_vector_optimize_bootstrap_now = _data_sync_sync_mod._sync_vector_optimize_bootstrap_now
_sync_factor_validation_bootstrap_now = _data_sync_sync_mod._sync_factor_validation_bootstrap_now


def _sync_data_sync_support_overrides() -> None:
    """Keep core/sync support modules aligned with top-level monkeypatches."""
    _data_sync_core_mod.get_db = get_db
    _data_sync_sync_mod.get_db = get_db

    _data_sync_core_mod._sync_klines_now = _sync_klines_now
    _data_sync_core_mod._sync_quotes_now = _sync_quotes_now
    _data_sync_core_mod._sync_financials_check = _sync_financials_check
    _data_sync_core_mod._sync_core_market_now = _sync_core_market_now
    _data_sync_core_mod._sync_factor_context_now = _sync_factor_context_now
    _data_sync_core_mod._sync_market_text_source_ingest_now = _sync_market_text_source_ingest_now
    _data_sync_core_mod._sync_vector_backfill_market_docs_now = _sync_vector_backfill_market_docs_now
    _data_sync_core_mod._sync_vector_backfill_kline_patterns_now = _sync_vector_backfill_kline_patterns_now
    _data_sync_core_mod._sync_vector_backfill_stock_profiles_now = _sync_vector_backfill_stock_profiles_now
    _data_sync_core_mod._sync_vector_backfill_factor_candidates_now = _sync_vector_backfill_factor_candidates_now
    _data_sync_core_mod._sync_factor_external_research_ingest_now = _sync_factor_external_research_ingest_now
    _data_sync_core_mod._sync_vector_build_snapshot_now = _sync_vector_build_snapshot_now
    _data_sync_core_mod._sync_vector_benchmark_collection_now = _sync_vector_benchmark_collection_now
    _data_sync_core_mod._sync_vector_optimize_bootstrap_now = _sync_vector_optimize_bootstrap_now
    _data_sync_core_mod._sync_factor_validation_bootstrap_now = _sync_factor_validation_bootstrap_now

    _data_sync_sync_mod._as_bool = _as_bool
    _data_sync_sync_mod._load_market_aux_status = _load_market_aux_status
    _data_sync_sync_mod._core_market_script_path = _core_market_script_path
    _data_sync_sync_mod._factor_context_script_path = _factor_context_script_path


async def run_runtime_data_warmup(*args, **kwargs):
    """Run runtime warmup with top-level monkeypatches propagated to support modules."""
    _sync_data_sync_support_overrides()
    return await _data_sync_core_mod.run_runtime_data_warmup(*args, **kwargs)

def register_data_sync_manager(mcp):
    """注册数据同步管理器工具"""
    
    @mcp.tool()
    async def data_sync_manager(action: str, params: dict | None = None, kwargs: Any = None, codes: list[str] | None = None, task_id: str | None = None, task_type: str | None = None, period: str | None = None, status: str | None = None, schedule: str | None = None, force: bool | None = None, limit: int | None = None, priority: str | None = None):
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
            _sync_data_sync_support_overrides()
            db = get_db()
            kwargs = normalize_manager_payload(
                params=params,
                kwargs=kwargs,
                extra={
                    "codes": codes,
                    "task_id": task_id,
                    "task_type": task_type,
                    "period": period,
                    "status": status,
                    "schedule": schedule,
                    "force": force,
                    "limit": limit,
                    "priority": priority,
                },
            )

            if action == 'list':
                action = 'list_tasks'

            if action == 'help':
                return ok({
                    'supported_actions': {
                        'status': '数据同步状态',
                        'sync': '执行数据同步（K线/财务需 codes；core_market/market_text_source_ingest/factor_external_research_ingest/vector_optimize_bootstrap/factor_validation_bootstrap/vector_backfill_market_docs/vector_backfill_kline_patterns/vector_backfill_stock_profiles/vector_backfill_factor_candidates/vector_build_snapshot/vector_benchmark_collection 可直接运行）',
                        'get_task': '获取任务详情（需要 task_id）',
                        'list_tasks': '列出同步任务',
                        'cancel_task': '取消任务（需要 task_id）',
                        'schedule': '创建调度任务',
                        'list_schedules': '列出已登记调度',
                        'cancel_schedule': '禁用调度任务（需要 schedule_id）',
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
                          AND (next_run IS NULL OR next_run <= CURRENT_TIMESTAMP)
                        """
                    ) or 0
                    next_schedule_run = await conn.fetchval(
                        """
                        SELECT MIN(next_run)
                        FROM sync_schedules
                        WHERE enabled = true AND next_run IS NOT NULL
                        """
                    )
                    quote_ttl = quote_max_stale_seconds()
                    quote_fresh_cutoff = datetime.now() - timedelta(seconds=quote_ttl)
                    stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks") or 0
                    quote_count = await conn.fetchval("SELECT COUNT(*) FROM stock_quotes") or 0
                    quote_unique_codes = await conn.fetchval("SELECT COUNT(DISTINCT code) FROM stock_quotes") or 0
                    fresh_quote_count = await conn.fetchval(
                        """
                        SELECT COUNT(DISTINCT code)
                        FROM stock_quotes
                        WHERE time >= $1 OR updated_at >= $1
                        """,
                        quote_fresh_cutoff,
                    ) or 0
                    stale_quote_count = max(int(quote_unique_codes) - int(fresh_quote_count), 0)
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
                    'quote_snapshot': {
                        'row_count': int(quote_count),
                        'covered_code_count': int(quote_unique_codes),
                        'fresh_code_count': int(fresh_quote_count),
                        'stale_code_count': int(stale_quote_count),
                        'universe_stock_count': int(stock_count),
                        'coverage_ratio': round((int(quote_unique_codes) / int(stock_count)), 4) if int(stock_count) > 0 else None,
                        'freshness_ttl_seconds': quote_ttl,
                        'latest_quote_time': _ts_iso(quote_sync),
                    },
                })
            
            elif action == 'sync':
                task_type = kwargs.get('type') or kwargs.get('task_type') or 'kline'
                codes = _normalize_codes(kwargs.get('codes') or kwargs.get('stock_codes'))
                priority = kwargs.get('priority', 'normal')

                if task_type not in {
                    'core_market',
                    'factor_context',
                    'market_text_source_ingest',
                    'vector_backfill_market_docs',
                    'vector_backfill_kline_patterns',
                    'vector_backfill_stock_profiles',
                    'vector_backfill_factor_candidates',
                    'factor_external_research_ingest',
                    'vector_build_snapshot',
                    'vector_benchmark_collection',
                    'vector_optimize_bootstrap',
                    'factor_validation_bootstrap',
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

                if str(task_id).startswith('schedule_'):
                    async with db.acquire() as conn:
                        schedule_row = await conn.fetchrow(
                            "SELECT * FROM sync_schedules WHERE schedule_id = $1",
                            str(task_id),
                        )
                    if not schedule_row:
                        return fail(f'璋冨害浠诲姟涓嶅瓨鍦? {task_id}')
                    schedule_data = dict(schedule_row)
                    schedule_data['params'] = _decode_json_obj(schedule_data.get('params'))
                    schedule_data['target_type'] = 'schedule'
                    schedule_data['task_id'] = str(task_id)
                    schedule_data.setdefault('schedule_id', str(task_id))
                    schedule_data.setdefault(
                        'status',
                        'scheduled' if _as_bool(schedule_data.get('enabled'), True) else 'cancelled',
                    )
                    return ok(schedule_data)
                
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

                if str(task_id).startswith('schedule_'):
                    async with db.acquire() as conn:
                        try:
                            result = await conn.execute(
                                "UPDATE sync_schedules SET enabled = false, updated_at = CURRENT_TIMESTAMP WHERE schedule_id = $1",
                                str(task_id),
                            )
                        except Exception:
                            result = await conn.execute(
                                "UPDATE sync_schedules SET enabled = false WHERE schedule_id = $1",
                                str(task_id),
                            )
                    if result == 'UPDATE 0':
                        return fail(f'调度任务不存在: {task_id}')
                    return ok({
                        'task_id': task_id,
                        'schedule_id': task_id,
                        'status': 'cancelled',
                        'enabled': False,
                        'target_type': 'schedule',
                    })
                
                async with db.acquire() as conn:
                    try:
                        result = await conn.execute(
                            "UPDATE sync_tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE task_id = $1 AND status IN ('pending', 'running')",
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

            elif action == 'cancel_schedule':
                schedule_id = kwargs.get('schedule_id') or kwargs.get('task_id')
                if not schedule_id:
                    return fail('需要提供 schedule_id 参数')
                async with db.acquire() as conn:
                    try:
                        result = await conn.execute(
                            "UPDATE sync_schedules SET enabled = false, updated_at = CURRENT_TIMESTAMP WHERE schedule_id = $1",
                            str(schedule_id),
                        )
                    except Exception:
                        result = await conn.execute(
                            "UPDATE sync_schedules SET enabled = false WHERE schedule_id = $1",
                            str(schedule_id),
                        )
                if result == 'UPDATE 0':
                    return fail(f'调度任务不存在: {schedule_id}')
                return ok({
                    'schedule_id': str(schedule_id),
                    'status': 'cancelled',
                    'enabled': False,
                    'target_type': 'schedule',
                })
            
            elif action == 'schedule':
                task_type = kwargs.get('type') or kwargs.get('task_type') or 'kline'
                codes = _normalize_codes(kwargs.get('codes') or kwargs.get('stock_codes'))
                schedule = str(kwargs.get('schedule', 'daily')).strip().lower()
                enabled = _as_bool(kwargs.get('enabled', True), True)
                
                if task_type not in {
                    'core_market',
                    'factor_context',
                    'market_text_source_ingest',
                    'vector_backfill_market_docs',
                    'vector_backfill_kline_patterns',
                    'vector_backfill_stock_profiles',
                    'vector_backfill_factor_candidates',
                    'factor_external_research_ingest',
                    'vector_build_snapshot',
                    'vector_benchmark_collection',
                    'vector_optimize_bootstrap',
                    'factor_validation_bootstrap',
                } and not codes:
                    return fail('需要提供codes参数')
                
                schedule_id = f'schedule_{task_type}_{int(datetime.now().timestamp())}'
                next_run = _compute_next_run(schedule)
                params = _build_schedule_params(task_type, kwargs, codes)
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO sync_schedules (schedule_id, task_type, codes, schedule, params, enabled, next_run, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
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
                return fail(f'Unknown action: {action}. Supported: help, status, sync, get_task, list_tasks, cancel_task, schedule, list_schedules, cancel_schedule, run_due_schedules')
        except Exception as e:
            return fail(str(e))
