"""数据同步管理器 - 任务调度、状态跟踪、即时执行"""

import json
import logging
from datetime import datetime
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
                        'sync': '执行数据同步（需要 codes）',
                        'get_task': '获取任务详情（需要 task_id）',
                        'list_tasks': '列出同步任务',
                        'cancel_task': '取消任务（需要 task_id）',
                        'schedule': '调度管理',
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
                    'status': 'running' if running_tasks > 0 else 'idle',
                    'pending_tasks': int(pending_tasks),
                    'running_tasks': int(running_tasks),
                })
            
            elif action == 'sync':
                task_type = kwargs.get('type', 'kline')
                codes = kwargs.get('codes', [])
                priority = kwargs.get('priority', 'normal')

                if not codes:
                    return fail('需要提供codes参数')

                task_id = f'sync_{task_type}_{int(datetime.now().timestamp())}'

                # 写入任务记录
                try:
                    async with db.acquire() as conn:
                        await conn.execute(
                            """INSERT INTO sync_tasks (task_id, task_type, codes, priority, status, created_at)
                               VALUES ($1, $2, $3, $4, 'running', NOW())""",
                            task_id, task_type, codes, priority
                        )
                except Exception as e:
                    logger.warning(f"[DataSyncManager] 写入任务记录失败: {e}")

                # 立即执行同步（而非等待不存在的worker）
                results = {'success': 0, 'failed': 0, 'errors': []}
                final_status = 'completed'
                try:
                    if task_type == 'kline':
                        results = await _sync_klines_now(codes)
                    elif task_type == 'financial':
                        results = await _sync_financials_check(codes)
                    else:
                        # 其他类型默认走K线同步
                        results = await _sync_klines_now(codes)

                    if results.get('failed', 0) > 0 and results.get('success', 0) == 0:
                        final_status = 'failed'
                except Exception as e:
                    final_status = 'failed'
                    results['errors'].append(str(e))
                    logger.warning(f"[DataSyncManager] 同步执行异常: {e}")

                # 更新任务状态
                try:
                    async with db.acquire() as conn:
                        await conn.execute(
                            "UPDATE sync_tasks SET status = $1 WHERE task_id = $2",
                            final_status, task_id
                        )
                except Exception:
                    pass

                return ok({
                    'task_id': task_id,
                    'task_type': task_type,
                    'codes_count': len(codes),
                    'priority': priority,
                    'status': final_status,
                    'results': results,
                    'message': f'同步完成: 成功 {results.get("success", 0)}, 失败 {results.get("failed", 0)}',
                })
            
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
                codes = kwargs.get('codes', [])
                schedule = kwargs.get('schedule', 'daily')
                
                if not codes:
                    return fail('需要提供codes参数')
                
                schedule_id = f'schedule_{task_type}_{int(datetime.now().timestamp())}'
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO sync_schedules (schedule_id, task_type, codes, schedule, enabled, created_at)
                           VALUES ($1, $2, $3, $4, true, NOW())""",
                        schedule_id, task_type, codes, schedule
                    )
                
                return ok({
                    'schedule_id': schedule_id,
                    'task_type': task_type,
                    'schedule': schedule,
                    'codes_count': len(codes),
                    'enabled': True,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, status, sync, get_task, list_tasks, cancel_task, schedule')
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
