"""实盘交易管理器（仅监控，不实际交易）"""

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
    return kwargs


def register_live_trading_manager(mcp):
    """注册实盘交易管理器工具"""
    
    @mcp.tool()
    async def live_trading_manager(action: str, **kwargs):
        """实盘交易管理器（统一 action + kwargs 协议，仅监控，不实际交易）

        Args:
            action (str, required): 操作类型，可选 help/monitor/sync_positions
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - monitor: codes(list[str], optional, 监控股票列表)
                - sync_positions: 无需额外参数（同步持仓数据）

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            live_trading_manager(action="help", kwargs="{}")
            # 监控股票
            live_trading_manager(action="monitor", kwargs='{"codes":["600519","000858"]}')
            # 同步持仓
            live_trading_manager(action="sync_positions", kwargs="{}")
        """
        try:
            kwargs = _normalize_kwargs(dict(kwargs))
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'monitor': '监控账户（需要 account_id）',
                        'sync_positions': '同步持仓',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'monitor':
                account_id = kwargs.get('account_id')
                
                return ok({
                    'account_id': account_id,
                    'status': 'monitoring',
                    'message': '实盘交易监控功能，不执行实际交易'
                })
            
            elif action == 'sync_positions':
                return ok({
                    'synced': True,
                    'positions': [],
                    'message': '仅监控模式，不同步实际持仓'
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, monitor, sync_positions')
        except Exception as e:
            return fail(str(e))
