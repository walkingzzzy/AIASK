"""合规管理器 - 交易限制、合规检查"""

import json
from datetime import datetime, timedelta, timezone
from ...utils import ok, fail, normalize_code

MAX_SINGLE_ORDER_SHARES = 1_000_000
MAX_SINGLE_ORDER_AMOUNT = 50_000_000.0
MIN_LOT_SIZE = 100


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
    if "code" not in kwargs or kwargs.get("code") is None:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    if kwargs.get("quantity") is None:
        kwargs["quantity"] = kwargs.get("shares") or kwargs.get("qty")
    if kwargs.get("direction") is None:
        kwargs["direction"] = kwargs.get("side") or kwargs.get("order_side")
    return kwargs


def _in_cn_trading_hours() -> bool:
    """简单交易时段校验（北京时间，工作日 09:30-11:30, 13:00-15:00）"""
    now_cn = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    if now_cn.weekday() >= 5:
        return False
    minutes = now_cn.hour * 60 + now_cn.minute
    return (570 <= minutes <= 690) or (780 <= minutes <= 900)



def evaluate_order_compliance(code: str, direction: str, quantity_raw, price_raw=None) -> dict:
    """可复用的合规检查核心逻辑（供 execution_manager 强制前置闸门调用）。"""
    code_n = normalize_code(code or '') if code else None
    direction_n = str(direction or '').strip().lower()

    violations = []
    warnings = []

    quantity = None
    if quantity_raw is not None:
        try:
            quantity = int(float(quantity_raw))
        except Exception:
            violations.append('quantity 格式无效，需为正整数')

    price = None
    if price_raw is not None:
        try:
            price = float(price_raw)
        except Exception:
            violations.append('price 格式无效，需为正数')

    if not code_n:
        violations.append('缺少 code 参数')
    if direction_n not in ('buy', 'sell'):
        violations.append('direction 仅支持 buy/sell')
    if quantity is None or quantity <= 0:
        violations.append('quantity 必须大于 0')
    if price is not None and price <= 0:
        violations.append('price 必须大于 0')

    if quantity is not None and quantity > MAX_SINGLE_ORDER_SHARES:
        violations.append(f'单笔数量超限（>{MAX_SINGLE_ORDER_SHARES}）')

    if direction_n == 'buy' and quantity is not None and quantity % MIN_LOT_SIZE != 0:
        violations.append(f'买入数量必须为 {MIN_LOT_SIZE} 的整数倍')

    order_amount = None
    if quantity is not None and price is not None and price > 0:
        order_amount = quantity * price
        if order_amount > MAX_SINGLE_ORDER_AMOUNT:
            violations.append(f'单笔金额超限（>{MAX_SINGLE_ORDER_AMOUNT:.0f}）')

    trading_hours = _in_cn_trading_hours()
    checks = {
        'position_limit': quantity is not None and quantity <= MAX_SINGLE_ORDER_SHARES,
        'trading_hours': trading_hours,
        'suspended': False,
        'st_stock': False,
        'lot_size': not (direction_n == 'buy' and quantity is not None and quantity % MIN_LOT_SIZE != 0),
        'order_amount': (order_amount is None) or (order_amount <= MAX_SINGLE_ORDER_AMOUNT),
    }

    if not trading_hours:
        warnings.append('当前时间不在交易时段内（仅提示，部分券商支持预委托）')
    warnings.append('停牌/ST/涨跌停校验当前为静态规则，建议在下单前接入实时行情复核')

    blocked = len(violations) > 0
    passed = not blocked
    return {
        'code': code_n,
        'direction': direction_n,
        'quantity': quantity,
        'price': price,
        'order_amount': float(order_amount) if order_amount is not None else None,
        'passed': passed,
        'blocked': blocked,
        'checks': checks,
        'violations': violations,
        'warnings': warnings,
    }


def register_compliance_manager(mcp):
    """注册合规管理器工具"""

    @mcp.tool()
    async def compliance_manager(action: str, **kwargs):
        """合规管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/check_order/get_restrictions/check/check_trade/rules
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - check_order: code(str), direction(str, "buy"/"sell"), quantity(int), price(float)
                - get_restrictions: code(str, optional)
                - check / check_trade: code(str), direction(str), quantity(int)
                - rules: 无需额外参数（列出合规规则）

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            compliance_manager(action="help", kwargs="{}")
            # 检查订单合规
            compliance_manager(action="check_order", kwargs='{"code":"600519","direction":"buy","quantity":100,"price":1800}')
            # 获取交易限制
            compliance_manager(action="get_restrictions", kwargs='{"code":"600519"}')
            # 查看合规规则
            compliance_manager(action="rules", kwargs="{}")
        """
        try:
            kwargs = _normalize_kwargs(dict(kwargs))
            SUPPORTED_ACTIONS = {
                'check_order': '检查订单合规',
                'get_restrictions': '获取交易限制',
                'check': '检查订单合规（别名）',
                'check_trade': '检查交易合规（别名）',
                'rules': '获取合规规则',
                'help': '显示帮助信息',
            }

            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})

            elif action in ['check_order', 'check', 'check_trade']:
                code = normalize_code(kwargs.get('code') or '') if kwargs.get('code') else None
                direction = str(kwargs.get('direction') or '').strip().lower()
                quantity_raw = kwargs.get('quantity')
                price_raw = kwargs.get('price')

                violations = []
                warnings = []

                quantity = None
                if quantity_raw is not None:
                    try:
                        quantity = int(float(quantity_raw))
                    except Exception:
                        violations.append('quantity 格式无效，需为正整数')

                price = None
                if price_raw is not None:
                    try:
                        price = float(price_raw)
                    except Exception:
                        violations.append('price 格式无效，需为正数')

                if not code:
                    violations.append('缺少 code 参数')
                if direction not in ('buy', 'sell'):
                    violations.append('direction 仅支持 buy/sell')
                if quantity is None or quantity <= 0:
                    violations.append('quantity 必须大于 0')
                if price is not None and price <= 0:
                    violations.append('price 必须大于 0')

                if quantity is not None and quantity > MAX_SINGLE_ORDER_SHARES:
                    violations.append(f'单笔数量超限（>{MAX_SINGLE_ORDER_SHARES}）')

                if direction == 'buy' and quantity is not None and quantity % MIN_LOT_SIZE != 0:
                    violations.append(f'买入数量必须为 {MIN_LOT_SIZE} 的整数倍')

                order_amount = None
                if quantity is not None and price is not None and price > 0:
                    order_amount = quantity * price
                    if order_amount > MAX_SINGLE_ORDER_AMOUNT:
                        violations.append(f'单笔金额超限（>{MAX_SINGLE_ORDER_AMOUNT:.0f}）')

                trading_hours = _in_cn_trading_hours()
                checks = {
                    'position_limit': quantity is not None and quantity <= MAX_SINGLE_ORDER_SHARES,
                    'trading_hours': trading_hours,
                    'suspended': False,   # 当前未接入实时停牌源
                    'st_stock': False,    # 当前未接入 ST 名单实时校验
                    'lot_size': not (direction == 'buy' and quantity is not None and quantity % MIN_LOT_SIZE != 0),
                    'order_amount': (order_amount is None) or (order_amount <= MAX_SINGLE_ORDER_AMOUNT),
                }

                if not trading_hours:
                    warnings.append('当前时间不在交易时段内（仅提示，部分券商支持预委托）')
                warnings.append('停牌/ST/涨跌停校验当前为静态规则，建议在下单前接入实时行情复核')

                blocked = len(violations) > 0
                passed = not blocked

                return ok({
                    'code': code,
                    'direction': direction,
                    'quantity': quantity,
                    'price': price,
                    'order_amount': float(order_amount) if order_amount is not None else None,
                    'passed': passed,
                    'blocked': blocked,
                    'checks': checks,
                    'violations': violations,
                    'warnings': warnings,
                })

            elif action == 'get_restrictions':
                code = kwargs.get('code')
                return ok({
                    'code': code,
                    'restrictions': {
                        'max_position_pct': 0.1,
                        'max_single_order_shares': MAX_SINGLE_ORDER_SHARES,
                        'max_single_order_amount': MAX_SINGLE_ORDER_AMOUNT,
                        'min_lot_size': MIN_LOT_SIZE,
                        'trading_allowed': True,
                        'trading_hours': '09:30-11:30, 13:00-15:00 (Asia/Shanghai)',
                    }
                })

            elif action == 'rules':
                return ok({
                    'rules': [
                        {'name': 'position_limit', 'description': '单只股票持仓不超过净资产10%'},
                        {'name': 'single_order_shares', 'description': f'单笔数量不超过 {MAX_SINGLE_ORDER_SHARES} 股'},
                        {'name': 'single_order_amount', 'description': f'单笔金额不超过 {MAX_SINGLE_ORDER_AMOUNT:.0f} 元'},
                        {'name': 'lot_size', 'description': f'买入数量建议为 {MIN_LOT_SIZE} 的整数倍'},
                        {'name': 'trading_hours', 'description': '只能在交易时间内下单（9:30-11:30, 13:00-15:00）'},
                        {'name': 'st_restriction', 'description': 'ST股票每日涨跌幅限制5%'},
                        {'name': 'suspended', 'description': '停牌股票不可交易'},
                        {'name': 'limit_up_down', 'description': '涨跌停股票限制交易'},
                    ]
                })

            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            return fail(str(e))
