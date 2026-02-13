"""执行管理器 - TWAP、VWAP算法交易"""

import json
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
    if "code" not in kwargs or kwargs.get("code") is None:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    # 参数别名兼容：文档使用 total_quantity/duration_minutes，历史实现使用 total_shares/duration
    if kwargs.get("total_shares") is None:
        kwargs["total_shares"] = kwargs.get("total_quantity") or kwargs.get("quantity")
    if kwargs.get("duration") is None:
        kwargs["duration"] = kwargs.get("duration_minutes") or kwargs.get("minutes")
    if kwargs.get("slices") is None and kwargs.get("slice_count") is not None:
        kwargs["slices"] = kwargs.get("slice_count")
    return kwargs


def register_execution_manager(mcp):
    """注册执行管理器工具"""
    
    @mcp.tool()
    async def execution_manager(action: str, **kwargs):
        """执行管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/twap/vwap/list/summary
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - twap: code(str), total_quantity(int), duration_minutes(int), slices(int, optional)
                - vwap: code(str), total_quantity(int), duration_minutes(int)
                - list: 无需额外参数（列出执行任务）
                - summary: task_id(str)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            execution_manager(action="help", kwargs="{}")
            # TWAP算法交易
            execution_manager(action="twap", kwargs='{"code":"600519","total_quantity":1000,"duration_minutes":60,"slices":6}')
            # VWAP算法交易
            execution_manager(action="vwap", kwargs='{"code":"600519","total_quantity":1000,"duration_minutes":60}')
            # 列出执行任务
            execution_manager(action="list", kwargs="{}")
        """
        try:
            kwargs = _normalize_kwargs(dict(kwargs))
            SUPPORTED_ACTIONS = {
                'twap': 'TWAP算法交易（时间加权平均价格）',
                'vwap': 'VWAP算法交易（成交量加权平均价格）',
                'list': '列出执行计划（同 twap）',
                'summary': '执行摘要',
                'help': '显示帮助信息',
            }
            
            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})
            
            elif action == 'twap':
                code = kwargs.get('code')
                total_shares = kwargs.get('total_shares')
                duration = kwargs.get('duration', 60)
                slices = kwargs.get('slices')
                
                if not code:
                    return fail('需要提供 code 参数')
                if total_shares is None:
                    return fail('需要提供 total_shares 或 total_quantity 参数')
                if not isinstance(total_shares, (int, float)) or total_shares <= 0:
                    return fail('total_shares 必须是正数')
                if not isinstance(duration, (int, float)) or duration <= 0:
                    return fail('duration 必须是正数')
                
                if slices is None:
                    slices = int(duration) // 5
                else:
                    try:
                        slices = int(slices)
                    except Exception:
                        return fail('slices 必须是正整数')
                if slices <= 0:
                    slices = 1
                interval = max(1, int(duration) // slices)
                shares_per_slice = int(total_shares) // slices
                remainder = int(total_shares) - shares_per_slice * slices
                
                return ok({
                    'algorithm': 'TWAP',
                    'code': code,
                    'total_shares': int(total_shares),
                    'total_quantity': int(total_shares),  # 向后兼容文档参数名
                    'duration': int(duration),
                    'duration_minutes': int(duration),  # 向后兼容文档参数名
                    'slices': slices,
                    'shares_per_slice': shares_per_slice,
                    'interval': interval,
                    'remainder_shares': remainder,
                })
            
            elif action == 'vwap':
                code = kwargs.get('code')
                total_shares = kwargs.get('total_shares')
                duration = kwargs.get('duration', 60)
                
                if not code:
                    return fail('需要提供 code 参数')
                if total_shares is None:
                    return fail('需要提供 total_shares 或 total_quantity 参数')
                
                return ok({
                    'algorithm': 'VWAP',
                    'code': code,
                    'total_shares': int(total_shares),
                    'total_quantity': int(total_shares),  # 向后兼容文档参数名
                    'duration': int(duration),
                    'duration_minutes': int(duration),  # 向后兼容文档参数名
                    'status': 'scheduled',
                })
            
            elif action in ['list', 'summary']:
                return ok({
                    'message': '暂无执行中的任务',
                    'pending_orders': [],
                    'completed_orders': [],
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            return fail(str(e))
