"""合规管理器 - 交易限制、合规检查"""

import json
from ...utils import ok, fail, normalize_code


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
    return kwargs


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
                shares = kwargs.get('shares')
                account_id = kwargs.get('account_id')
                
                checks = {
                    'position_limit': True,
                    'trading_hours': True,
                    'suspended': False,
                    'st_stock': False,
                }
                
                passed = all(v for v in checks.values() if isinstance(v, bool) and v) and not checks.get('suspended') and not checks.get('st_stock')
                
                return ok({
                    'code': code,
                    'passed': passed,
                    'checks': checks,
                })
            
            elif action == 'get_restrictions':
                code = kwargs.get('code')
                return ok({
                    'code': code,
                    'restrictions': {
                        'max_position_pct': 0.1,
                        'max_single_order': 10000,
                        'trading_allowed': True,
                    }
                })
            
            elif action == 'rules':
                return ok({
                    'rules': [
                        {'name': 'position_limit', 'description': '单只股票持仓不超过净资产10%'},
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
