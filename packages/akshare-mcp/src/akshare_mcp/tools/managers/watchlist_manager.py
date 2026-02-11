"""自选股管理器"""

import json
from ...storage import get_db
from ...utils import ok, fail


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
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
    # 兼容 code / stock_code / symbol
    if "code" not in kwargs or not kwargs["code"]:
        kwargs["code"] = kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def register_watchlist_manager(mcp):
    """注册自选股管理器工具"""
    
    @mcp.tool()
    async def watchlist_manager(action: str, **kwargs):
        """自选股管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/add/remove
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: user_id(str, optional)
                - add: code(str, 股票代码), user_id(str, optional)
                - remove: code(str), user_id(str, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            watchlist_manager(action="help", kwargs="{}")
            # 列出自选股
            watchlist_manager(action="list", kwargs="{}")
            # 添加自选股
            watchlist_manager(action="add", kwargs='{"code":"600519"}')
            # 删除自选股
            watchlist_manager(action="remove", kwargs='{"code":"600519"}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            user_id = kwargs.get('user_id', 'default')
            
            if action == 'list':
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM watchlist WHERE user_id = $1 ORDER BY added_at DESC",
                        user_id
                    )
                    stocks = [dict(row) for row in rows]
                
                if not stocks:
                    return ok({
                        'stocks': [],
                        'count': 0,
                        'message': '自选股为空',
                        'suggestions': {
                            'popular_stocks': [
                                {'code': '600519', 'name': '贵州茅台', 'reason': '白酒龙头'},
                                {'code': '000001', 'name': '平安银行', 'reason': '金融蓝筹'},
                                {'code': '600036', 'name': '招商银行', 'reason': '银行龙头'},
                                {'code': '300750', 'name': '宁德时代', 'reason': '新能源龙头'},
                                {'code': '000858', 'name': '五粮液', 'reason': '白酒板块'}
                            ],
                            'quick_add': '使用 watchlist_manager(action="add", code="600519") 添加股票'
                        }
                    })
                
                # 补充股票名称（watchlist 表可能没有 name 列）
                try:
                    from ...data_source import data_source
                    for s in stocks:
                        if not s.get('name'):
                            s['name'] = data_source._get_stock_name(s.get('code', ''))
                except Exception:
                    pass
                
                return ok({'stocks': stocks, 'count': len(stocks)})
            
            elif action == 'add':
                code = kwargs.get('code')
                note = kwargs.get('note', '')
                
                if not code:
                    return fail('需要提供 code 参数（股票代码）')
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO watchlist (user_id, code, note, added_at)
                           VALUES ($1, $2, $3, NOW())
                           ON CONFLICT (user_id, code) DO UPDATE SET note = EXCLUDED.note""",
                        user_id, code, note
                    )
                return ok({'code': code, 'added': True})
            
            elif action == 'remove':
                code = kwargs.get('code')
                if not code:
                    return fail('需要提供 code 参数（股票代码）')
                
                async with db.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM watchlist WHERE user_id = $1 AND code = $2",
                        user_id, code
                    )
                return ok({'code': code, 'removed': True})
            
            elif action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出自选股',
                        'add': '添加自选股（需要 code 参数）',
                        'remove': '删除自选股（需要 code 参数）',
                        'help': '显示帮助信息',
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: list, add, remove, help')
        except Exception as e:
            return fail(str(e))