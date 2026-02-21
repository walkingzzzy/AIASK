"""市场洞察管理器 - 市场趋势、板块分析（接入真实行情与资金流）"""

import logging
import numpy as np
from ...utils import ok, fail

logger = logging.getLogger(__name__)


def _safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def register_market_insight_manager(mcp):
    """注册市场洞察管理器工具"""

    @mcp.tool()
    async def market_insight_manager(action: str, **kwargs):
        """市场洞察管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/market_trend/sector_analysis
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - market_trend: 无需额外参数（返回大盘趋势分析）
                - sector_analysis: sector(str, optional, 板块名称)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            market_insight_manager(action="help", kwargs="{}")
            # 市场趋势分析
            market_insight_manager(action="market_trend", kwargs="{}")
            # 板块分析
            market_insight_manager(action="sector_analysis", kwargs="{}")
        """
        try:
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'market_trend': '市场趋势分析（基于真实指数行情与K线）',
                        'sector_analysis': '板块分析（基于真实板块资金流向）',
                        'help': '显示帮助信息',
                    }
                })

            elif action == 'market_trend':
                return await _market_trend()

            elif action == 'sector_analysis':
                return await _sector_analysis()

            else:
                return fail(f'Unknown action: {action}. Supported: help, market_trend, sector_analysis')
        except Exception as e:
            logger.exception("[market_insight_manager] error")
            return fail(str(e))

    async def _market_trend():
        """基于真实指数行情判断市场趋势"""
        from ..market.quote import get_index_quote
        from ..market.kline import get_index_kline

        # 1. 获取上证指数实时行情
        idx_quote = get_index_quote("000001")
        current_price = 0.0
        change_pct = 0.0
        if idx_quote.get('success') and idx_quote.get('data'):
            d = idx_quote['data']
            current_price = _safe_float(d.get('price') or d.get('最新价') or d.get('close'))
            change_pct = _safe_float(d.get('changePercent') or d.get('change_pct') or d.get('涨跌幅'))

        # 2. 获取近60日指数K线计算趋势（使用指数专用接口，避免与个股000001混淆）
        kline_res = get_index_kline(index_code="000001", period="daily", limit=60)
        trend = 'unknown'
        strength = 'unknown'
        support = 0.0
        resistance = 0.0
        ma5 = ma20 = ma60 = 0.0

        if kline_res.get('success') and kline_res.get('data'):
            klines = kline_res['data']
            if isinstance(klines, list) and len(klines) >= 20:
                closes = [_safe_float(k.get('close') or k.get('Close')) for k in klines]
                closes = [c for c in closes if c > 0]
                if len(closes) >= 20:
                    ma5 = float(np.mean(closes[-5:]))
                    ma20 = float(np.mean(closes[-20:]))
                    ma60 = float(np.mean(closes[-min(60, len(closes)):])) if len(closes) >= 10 else ma20

                    # 趋势判断
                    if ma5 > ma20 > ma60:
                        trend = 'bullish'
                    elif ma5 < ma20 < ma60:
                        trend = 'bearish'
                    else:
                        trend = 'sideways'

                    # 强度判断（基于MA5偏离MA20的幅度）
                    if ma20 > 0:
                        deviation = abs(ma5 - ma20) / ma20
                        if deviation > 0.03:
                            strength = 'strong'
                        elif deviation > 0.01:
                            strength = 'medium'
                        else:
                            strength = 'weak'

                    # 支撑/阻力（近20日最低/最高）
                    lows = [_safe_float(k.get('low') or k.get('Low')) for k in klines[-20:]]
                    highs = [_safe_float(k.get('high') or k.get('High')) for k in klines[-20:]]
                    lows = [v for v in lows if v > 0]
                    highs = [v for v in highs if v > 0]
                    support = round(min(lows), 2) if lows else 0.0
                    resistance = round(max(highs), 2) if highs else 0.0

        return ok({
            'trend': trend,
            'strength': strength,
            'currentPrice': round(current_price, 2),
            'changePercent': round(change_pct, 2),
            'keyLevels': {
                'support': support,
                'resistance': resistance,
            },
            'movingAverages': {
                'ma5': round(ma5, 2),
                'ma20': round(ma20, 2),
                'ma60': round(ma60, 2),
            },
            'index': '上证指数(000001)',
        })

    async def _sector_analysis():
        """基于真实板块资金流向数据"""
        from ..fund_flow import get_sector_fund_flow, get_concept_fund_flow

        hot_sectors = []
        cold_sectors = []
        rotation = 'unknown'

        # 行业板块资金流向
        sector_res = get_sector_fund_flow(top_n=10)
        if sector_res.get('success') and sector_res.get('data'):
            sectors = sector_res['data']
            if isinstance(sectors, list) and len(sectors) > 0:
                for s in sectors[:5]:
                    name = s.get('name') or s.get('板块名称') or s.get('sector') or str(s)
                    flow = _safe_float(s.get('mainNetInflow') or s.get('net_inflow') or s.get('主力净流入') or s.get('net_amount'))
                    hot_sectors.append({'name': name, 'mainNetInflow': flow})
                for s in sectors[-3:]:
                    name = s.get('name') or s.get('板块名称') or s.get('sector') or str(s)
                    flow = _safe_float(s.get('mainNetInflow') or s.get('net_inflow') or s.get('主力净流入') or s.get('net_amount'))
                    cold_sectors.append({'name': name, 'mainNetInflow': flow})

        # 概念板块资金流向
        concept_hot = []
        concept_res = get_concept_fund_flow(top_n=5)
        if concept_res.get('success') and concept_res.get('data'):
            concepts = concept_res['data']
            if isinstance(concepts, list):
                for c in concepts[:5]:
                    name = c.get('name') or c.get('板块名称') or c.get('concept') or str(c)
                    flow = _safe_float(c.get('mainNetInflow') or c.get('net_inflow') or c.get('主力净流入') or c.get('net_amount'))
                    concept_hot.append({'name': name, 'mainNetInflow': flow})

        # 简单轮动判断
        if hot_sectors:
            top_names = [s['name'] for s in hot_sectors[:3]]
            growth_keywords = ['科技', '电子', '计算机', '通信', '半导体', '新能源', '软件']
            value_keywords = ['银行', '保险', '地产', '煤炭', '钢铁', '石油']
            growth_count = sum(1 for n in top_names for kw in growth_keywords if kw in str(n))
            value_count = sum(1 for n in top_names for kw in value_keywords if kw in str(n))
            if growth_count > value_count:
                rotation = 'value_to_growth'
            elif value_count > growth_count:
                rotation = 'growth_to_value'
            else:
                rotation = 'balanced'

        return ok({
            'hotSectors': hot_sectors,
            'coldSectors': cold_sectors,
            'hotConcepts': concept_hot,
            'rotation': rotation,
        })
