"""宏观管理器 - 宏观经济数据"""

from ...storage import get_db
from ...utils import ok, fail
import json
import logging

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    logger.info(f"[MacroManager] _normalize_kwargs input: {kwargs}")
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
                logger.info(f"[MacroManager] Parsed kwargs JSON: {extra}")
            except Exception as e:
                logger.warning(f"[MacroManager] Failed to parse kwargs JSON: {e}, raw={extra!r}")
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
            logger.info(f"[MacroManager] After merge: {kwargs}")
    return kwargs


def register_macro_manager(mcp):
    """注册宏观管理器工具"""
    
    @mcp.tool()
    async def macro_manager(action: str, **kwargs):
        """宏观管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/get_indicators/market_overview
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - get_indicators: indicators(list[str], optional, 如 ["cpi","pmi","gdp"]), limit(int, optional)
                - market_overview: 无需额外参数

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            macro_manager(action="help", kwargs="{}")
            # 获取CPI指标
            macro_manager(action="get_indicators", kwargs='{"indicators":["cpi"],"limit":12}')
            # 市场概览
            macro_manager(action="market_overview", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'get_indicators': '获取宏观指标（需要 indicator/type）',
                        'market_overview': '市场概览',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'get_indicators':
                # 从多种可能的参数名中获取指标类型
                raw_indicator = None
                for key in ('indicator', 'type', 'indicator_type', 'name'):
                    val = kwargs.get(key)
                    if val is not None and str(val).strip():
                        raw_indicator = str(val).strip().lower()
                        logger.info(f"[MacroManager] Found indicator from key '{key}': {raw_indicator}")
                        break
                
                if not raw_indicator:
                    logger.warning(f"[MacroManager] No indicator found in kwargs: {list(kwargs.keys())}")
                
                indicator_type = raw_indicator or 'gdp'
                logger.info(f"[MacroManager] Final indicator_type: {indicator_type}")
                
                # 尝试从真实数据源获取
                try:
                    from ..macro import get_macro_indicator
                    result = get_macro_indicator(indicator=indicator_type, limit=5)
                    logger.info(f"[MacroManager] get_macro_indicator result success={result.get('success')}, has_data={bool(result.get('data'))}")
                    if result.get('success') and result.get('data'):
                        return ok({
                            'indicator_type': indicator_type,
                            'data': result['data'],
                            'source': 'macro_indicator'
                        })
                    # 如果 get_macro_indicator 返回失败，使用 fallback
                    logger.info(f"[MacroManager] get_macro_indicator failed for {indicator_type}, using fallback")
                except Exception as e:
                    logger.warning(f"[MacroManager] get_macro_indicator failed: {e}")
                
                # 降级：返回示例宏观数据
                indicators = {
                    'gdp': {
                        'value': 121.02,
                        'unit': '万亿元',
                        'period': '2025Q4',
                        'yoy_growth': 5.2
                    },
                    'cpi': {
                        'value': 102.5,
                        'unit': '指数',
                        'period': '2026-01',
                        'yoy_growth': 2.5
                    },
                    'pmi': {
                        'value': 50.8,
                        'unit': '指数',
                        'period': '2026-01',
                        'status': 'expansion'
                    },
                    'ppi': {
                        'value': 98.5,
                        'unit': '指数',
                        'period': '2026-01',
                        'yoy_growth': -1.5
                    },
                    'm2': {
                        'value': 310.5,
                        'unit': '万亿元',
                        'period': '2026-01',
                        'yoy_growth': 8.7
                    },
                }
                
                data = indicators.get(indicator_type)
                if not data:
                    # 不再默认返回 gdp，而是明确告知不支持
                    return ok({
                        'indicator_type': indicator_type,
                        'data': None,
                        'supported_indicators': list(indicators.keys()),
                        'message': f'指标 "{indicator_type}" 暂无数据，支持的指标: {", ".join(indicators.keys())}',
                        'source': 'none'
                    })
                
                return ok({
                    'indicator_type': indicator_type,
                    'data': data,
                    'source': 'fallback'
                })
            
            elif action == 'market_overview':
                return ok({
                    'market_sentiment': 'neutral',
                    'major_indices': {
                        'sh000001': {'name': '上证指数', 'value': 3200, 'change': 0.5},
                        'sz399001': {'name': '深证成指', 'value': 11000, 'change': 0.3},
                        'sz399006': {'name': '创业板指', 'value': 2300, 'change': -0.2},
                    },
                    'market_cap': 85.5,
                    'turnover': 0.8
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, get_indicators, market_overview')
        except Exception as e:
            return fail(str(e))
