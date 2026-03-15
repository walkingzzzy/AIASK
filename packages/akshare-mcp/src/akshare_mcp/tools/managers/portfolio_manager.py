"""组合管理器 - 创建、调整、查询组合"""

import json

from ...storage import get_db
from ...utils import ok, fail


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
    params = kwargs.get("params")
    if isinstance(params, dict):
        kwargs = {**kwargs, **params}
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
    if "code" not in kwargs or not kwargs.get("code"):
        kwargs["code"] = kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def _safe_portfolio_id(val):
    """将 portfolio_id 转为 int（DB schema 为 SERIAL）"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


def _safe_float(val):
    """安全转换 float，非法值返回 None。"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalize_metadata(value):
    """兼容 dict / JSON 字符串 / 其他类型的 metadata 输入。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "{}")
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


async def _load_portfolio(conn, portfolio_id, user_id=None):
    row = await conn.fetchrow("SELECT * FROM portfolios WHERE id = $1", portfolio_id)
    if not row:
        return None
    item = dict(row)
    owner = str(item.get("user_id") or "default")
    if user_id is not None and owner != str(user_id):
        return None
    return item


def register_portfolio_manager(mcp):
    """注册组合管理器工具"""

    @mcp.tool()
    async def portfolio_manager(action: str, **kwargs):
        """组合管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/create/get/update/delete/add_holding/remove_holding/get_holdings
            kwargs: 支持 structured ``params``、JSON 字符串 ``kwargs`` 或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: user_id(str, optional)
                - create: name(str), description(str, optional), metadata(dict, optional)
                - get: portfolio_id(int)
                - update: portfolio_id(int), name(str, optional), description(str, optional)
                - delete: portfolio_id(int)
                - add_holding: portfolio_id(int), code(str), shares(int), cost_price(float)
                - remove_holding: portfolio_id(int), code(str)
                - get_holdings: portfolio_id(int)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            portfolio_manager(action="help", kwargs="{}")
            # 创建组合
            portfolio_manager(action="create", kwargs='{"name":"我的组合","initial_capital":500000}')
            # 添加持仓
            portfolio_manager(action="add_holding", kwargs='{"portfolio_id":1,"code":"600519","shares":100,"cost_price":1800}')
            # 查看持仓
            portfolio_manager(action="get_holdings", kwargs='{"portfolio_id":1}')
            # 列出所有组合
            portfolio_manager(action="list", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            user_id = str(kwargs.get('user_id') or 'default').strip() or 'default'

            if action == 'list':
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM portfolios WHERE user_id = $1 ORDER BY created_at DESC",
                        user_id
                    )
                    portfolios = [dict(row) for row in rows]
                return ok({'portfolios': portfolios})

            elif action == 'create':
                name = kwargs.get('name')
                if not name:
                    return fail('需要提供 name 参数')
                user_id = kwargs.get('user_id', 'default')
                initial_capital = kwargs.get('initial_capital', 100000)
                description = kwargs.get('description')
                metadata = _normalize_metadata(kwargs.get('metadata'))

                strategy_allocations = kwargs.get('strategy_allocations')
                if isinstance(strategy_allocations, list) and 'strategy_allocations' not in metadata:
                    metadata = {**metadata, 'strategy_allocations': strategy_allocations}

                async with db.acquire() as conn:
                    portfolio_id = await conn.fetchval(
                        """INSERT INTO portfolios (name, description, metadata, user_id, initial_capital, current_value, created_at, updated_at)
                           VALUES ($1, $2, $3::jsonb, $4, $5, $5, NOW(), NOW())
                           RETURNING id""",
                        name, description, json.dumps(metadata or {}), user_id, initial_capital
                    )
                return ok({'portfolio_id': portfolio_id, 'name': name, 'description': description, 'metadata': metadata})

            elif action == 'get':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                async with db.acquire() as conn:
                    portfolio = await _load_portfolio(conn, portfolio_id, user_id)
                    if not portfolio:
                        return fail('组合不存在')
                return ok(dict(portfolio))

            elif action == 'update':
                # P0-1 修复说明：
                # 旧实现只更新 current_value，且当未传值时写入 NULL，触发 portfolios.current_value NOT NULL 约束冲突。
                # 新实现先读取现有记录并回填必填字段（尤其 current_value），同时兼容顶层字段与 updates 字段。
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                if not portfolio_id:
                    return fail('需要提供 portfolio_id 参数')

                raw_updates = kwargs.get('updates', {})
                updates = dict(raw_updates) if isinstance(raw_updates, dict) else {}
                for key in ('name', 'description', 'current_value'):
                    if key not in updates and kwargs.get(key) is not None:
                        updates[key] = kwargs.get(key)

                if not updates:
                    return fail('需要提供 updates，或在顶层提供 name/description/current_value')

                normalized = {}
                if 'name' in updates and updates.get('name') is not None:
                    normalized['name'] = str(updates.get('name'))
                if 'description' in updates:
                    normalized['description'] = updates.get('description')
                if 'current_value' in updates:
                    current_value = _safe_float(updates.get('current_value'))
                    if current_value is None:
                        return fail('current_value 必须是数字')
                    normalized['current_value'] = current_value

                async with db.acquire() as conn:
                    existing = await conn.fetchrow(
                        "SELECT id, name, description, current_value, user_id FROM portfolios WHERE id = $1",
                        portfolio_id
                    )
                    if not existing:
                        return fail('组合不存在')
                    existing = dict(existing)
                    if str(existing.get('user_id') or 'default') != user_id:
                        return fail('组合不存在')

                    final_name = normalized.get('name', existing['name'])
                    final_description = normalized.get('description', existing['description'])
                    final_current_value = normalized.get('current_value', existing['current_value'])

                    if final_current_value is None:
                        return fail('current_value 不能为空')

                    await conn.execute(
                        "UPDATE portfolios SET name = $1, description = $2, current_value = $3, updated_at = NOW() WHERE id = $4",
                        final_name, final_description, final_current_value, portfolio_id
                    )
                return ok({'portfolio_id': portfolio_id, 'updated': True, 'applied_fields': list(normalized.keys())})

            elif action == 'delete':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                async with db.acquire() as conn:
                    portfolio = await _load_portfolio(conn, portfolio_id, user_id)
                    if not portfolio:
                        return fail('组合不存在')
                    await conn.execute("DELETE FROM holdings WHERE portfolio_id = $1", portfolio_id)
                    await conn.execute("DELETE FROM portfolios WHERE id = $1", portfolio_id)
                return ok({'portfolio_id': portfolio_id, 'deleted': True})

            elif action == 'add_holding':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                code = kwargs.get('code')
                shares = kwargs.get('shares')
                cost_price = kwargs.get('cost_price', 0)

                if not portfolio_id:
                    return fail('需要提供 portfolio_id 参数')
                if not code:
                    return fail('需要提供 code 参数（股票代码）')
                if shares is None:
                    return fail('需要提供 shares 参数（持仓数量）')

                async with db.acquire() as conn:
                    # 验证组合存在
                    portfolio = await _load_portfolio(conn, portfolio_id, user_id)
                    if not portfolio:
                        return fail(f'组合 {portfolio_id} 不存在，请先创建组合')

                    await conn.execute(
                        """INSERT INTO holdings (portfolio_id, code, shares, cost_price, created_at, updated_at)
                           VALUES ($1, $2, $3, $4, NOW(), NOW())
                           ON CONFLICT (portfolio_id, code) DO UPDATE 
                           SET shares = holdings.shares + EXCLUDED.shares, updated_at = NOW()""",
                        portfolio_id, code, int(shares), float(cost_price)
                    )
                return ok({
                    'portfolio_id': portfolio_id,
                    'code': code,
                    'shares': int(shares),
                    'cost_price': float(cost_price),
                    'added': True
                })

            elif action == 'remove_holding':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                code = kwargs.get('code')

                if not portfolio_id:
                    return fail('需要提供 portfolio_id 参数')
                if not code:
                    return fail('需要提供 code 参数（股票代码）')

                async with db.acquire() as conn:
                    portfolio = await _load_portfolio(conn, portfolio_id, user_id)
                    if not portfolio:
                        return fail(f'组合 {portfolio_id} 不存在，请先创建组合')
                    await conn.execute(
                        "DELETE FROM holdings WHERE portfolio_id = $1 AND code = $2",
                        portfolio_id, code
                    )
                return ok({'portfolio_id': portfolio_id, 'code': code, 'removed': True})

            elif action == 'get_holdings':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                if not portfolio_id:
                    return fail('需要提供 portfolio_id 参数')

                async with db.acquire() as conn:
                    portfolio = await _load_portfolio(conn, portfolio_id, user_id)
                    if not portfolio:
                        return fail('组合不存在')
                    rows = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1 ORDER BY created_at",
                        portfolio_id
                    )
                    holdings = [dict(row) for row in rows]
                return ok({'portfolio_id': portfolio_id, 'holdings': holdings, 'count': len(holdings)})

            elif action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出所有组合',
                        'create': '创建组合（需要 name，可附带 description/metadata）',
                        'get': '获取组合详情（需要 portfolio_id）',
                        'update': '更新组合（需要 portfolio_id, updates）',
                        'delete': '删除组合（需要 portfolio_id）',
                        'add_holding': '添加持仓（需要 portfolio_id, code, shares）',
                        'remove_holding': '删除持仓（需要 portfolio_id, code）',
                        'get_holdings': '获取持仓列表（需要 portfolio_id）',
                        'help': '显示帮助信息',
                    }
                })

            else:
                return fail(f'Unknown action: {action}. Supported: list, create, get, update, delete, add_holding, remove_holding, get_holdings, help')

        except Exception as e:
            return fail(str(e))
