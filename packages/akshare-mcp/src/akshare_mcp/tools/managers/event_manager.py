"""事件管理器 - 财报、分红、重组"""

from ...storage import get_db
from ...utils import ok, fail
import json


def _normalize_kwargs(kwargs: dict) -> dict:
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    if "code" not in kwargs or kwargs.get("code") is None:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def register_event_manager(mcp):
    """注册事件管理器工具"""
    
    @mcp.tool()
    async def event_manager(action: str, **kwargs):
        """事件管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/upcoming_events/get_by_code/calendar/list_events/get_events
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - upcoming_events: days(int, optional, 未来天数)
                - get_by_code / get_events: code(str, 股票代码)
                - calendar: start_date(str, optional), end_date(str, optional)
                - list_events: type(str, optional, 事件类型)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            event_manager(action="help", kwargs="{}")
            # 获取未来7天事件
            event_manager(action="upcoming_events", kwargs='{"days":7}')
            # 按股票查询事件
            event_manager(action="get_by_code", kwargs='{"code":"600519"}')
            # 事件日历
            event_manager(action="calendar", kwargs='{"start_date":"2025-01-01","end_date":"2025-01-31"}')
        """
        try:
            kwargs = _normalize_kwargs(kwargs)
            SUPPORTED_ACTIONS = {
                'upcoming_events': '获取即将到来的事件',
                'get_by_code': '根据股票代码获取事件',
                'calendar': '获取事件日历（别名）',
                'list_events': '列出事件（别名）',
                'get_events': '获取事件（别名）',
                'help': '显示帮助信息',
            }
            
            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})
            
            elif action in ['upcoming_events', 'calendar', 'list_events']:
                days = int(kwargs.get('days') or 7)
                event_type = kwargs.get('type', 'all')
                
                db = get_db()
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT * FROM events 
                           WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + $1 * INTERVAL '1 day'
                           ORDER BY event_date""",
                        days
                    )
                    events = [dict(row) for row in rows]
                
                return ok({'events': events, 'count': len(events)})
            
            elif action in ['get_by_code', 'get_events']:
                code = kwargs.get('code')
                if not code:
                    return fail('需要提供股票代码')
                
                db = get_db()
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM events WHERE code = $1 ORDER BY event_date DESC LIMIT 20",
                        code
                    )
                    events = [dict(row) for row in rows]
                
                return ok({'code': code, 'events': events, 'count': len(events)})
            
            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            return fail(str(e))
