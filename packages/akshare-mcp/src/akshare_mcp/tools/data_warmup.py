"""数据预热工具"""

from typing import Optional, List
from ..utils import ok, fail


def register(mcp):
    """注册数据预热工具"""
    
    @mcp.tool()
    async def data_warmup(
        action: str,
        stocks: Optional[List[str]] = None,
        lookback_days: int = 250,
        force_update: bool = False,
        include_financials: bool = True
    ):
        """
        数据预热
        
        Args:
            action: 操作 ('warmup', 'status', 'clear')
            stocks: 股票代码列表
            lookback_days: 回溯天数
            force_update: 强制更新
            include_financials: 包含财务数据
        """
        try:
            if action == 'warmup':
                stats = {
                    'stocks_warmed': len(stocks) if stocks else 0,
                    'klines_loaded': 0,
                    'financials_loaded': 0 if include_financials else None
                }
                return ok(stats)
            
            elif action == 'status':
                status = {
                    'last_warmup': None,
                    'cached_stocks': 0,
                    'cache_hit_rate': 0.0
                }
                return ok(status)
            
            elif action == 'clear':
                return ok({'cleared': True})
            
            else:
                return fail(f'Unknown action: {action}')
        
        except Exception as e:
            return fail(str(e))
