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
                        'get_indicators': '获取宏观指标（支持 indicator/type 或 indicators 列表）',
                        'market_overview': '市场概览',
                        'help': '显示帮助信息',
                    }
                })

            elif action == 'get_indicators':
                # P1-2 修复说明：
                # 旧实现在未命中参数时会默认 gdp，且仅支持单指标，容易出现“请求 CPI/PMI 却返回 GDP”的口径错配。
                # 新实现统一支持 indicator/type + indicators(list/逗号串)，并保证响应只包含请求指标结果。

                def _normalize_indicator_list(raw_kwargs: dict) -> list[str]:
                    values = []

                    # 1) 优先读取 indicators（可为 list / 逗号字符串）
                    raw_list = raw_kwargs.get('indicators')
                    if isinstance(raw_list, list):
                        values.extend(raw_list)
                    elif isinstance(raw_list, str) and raw_list.strip():
                        values.extend([x.strip() for x in raw_list.split(',') if x.strip()])

                    # 2) 兼容单值参数
                    if not values:
                        for key in ('indicator', 'type', 'indicator_type', 'name'):
                            val = raw_kwargs.get(key)
                            if val is not None and str(val).strip():
                                values.append(str(val).strip())
                                break

                    # 3) 保持向后兼容：完全未传时默认 gdp
                    if not values:
                        values = ['gdp']

                    # 4) 归一 + 去重
                    normalized = []
                    seen = set()
                    for v in values:
                        item = str(v).strip().lower()
                        if item and item not in seen:
                            normalized.append(item)
                            seen.add(item)
                    return normalized

                requested_indicators = _normalize_indicator_list(kwargs)

                limit_raw = kwargs.get('limit', 5)
                try:
                    limit = int(limit_raw)
                except Exception:
                    limit = 5
                if limit <= 0:
                    limit = 5

                fallback_indicators = {
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

                results_by_indicator = {}
                sources_by_indicator = {}

                for indicator_type in requested_indicators:
                    data = None
                    source = 'none'

                    # 先尝试真实数据源
                    try:
                        from ..macro import get_macro_indicator
                        result = get_macro_indicator(indicator=indicator_type, limit=limit)
                        if result.get('success') and result.get('data'):
                            data = result.get('data')
                            source = result.get('data', [{}])[0].get('source', 'macro_indicator') if isinstance(result.get('data'), list) else 'macro_indicator'
                    except Exception as e:
                        logger.warning(f"[MacroManager] get_macro_indicator failed for {indicator_type}: {e}")

                    # 再用本地 fallback（仅当前请求指标）
                    if data is None and indicator_type in fallback_indicators:
                        data = fallback_indicators[indicator_type]
                        source = 'fallback'

                    results_by_indicator[indicator_type] = data
                    sources_by_indicator[indicator_type] = source

                unsupported = [k for k, v in results_by_indicator.items() if v is None]

                # 向后兼容：单指标请求保留 indicator_type + data 结构
                if len(requested_indicators) == 1:
                    indicator_type = requested_indicators[0]
                    payload = {
                        'indicator_type': indicator_type,
                        'data': results_by_indicator[indicator_type],
                        'source': sources_by_indicator[indicator_type],
                        'requested_indicators': requested_indicators,
                    }
                    if unsupported:
                        payload.update({
                            'supported_indicators': list(fallback_indicators.keys()),
                            'message': f'指标 "{indicator_type}" 暂无数据，支持的指标: {", ".join(fallback_indicators.keys())}',
                        })
                    return ok(payload)

                # 多指标：返回分指标结果，严格与请求口径一致
                payload = {
                    'requested_indicators': requested_indicators,
                    'data': results_by_indicator,
                    'sources': sources_by_indicator,
                }
                if unsupported:
                    payload.update({
                        'unsupported_indicators': unsupported,
                        'supported_indicators': list(fallback_indicators.keys()),
                        'message': '部分指标暂无数据，请参考 supported_indicators',
                    })
                return ok(payload)
            
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
