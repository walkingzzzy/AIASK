"""市场洞察管理器 - 市场趋势、板块分析（接入真实行情与资金流）"""

from typing import Any
import logging
import time
import numpy as np
from ..manager_protocol import (
    normalize_manager_payload,
    fail_with_meta,
    normalize_manager_kwargs,
    ok_with_meta,
)

logger = logging.getLogger(__name__)


def _safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _rounded_or_none(val, digits=2):
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (ValueError, TypeError):
        return None


def _dedupe_chain(values: list[str]) -> list[str]:
    chain = []
    seen = set()
    for value in values:
        label = str(value or "").strip()
        if not label or label in seen:
            continue
        chain.append(label)
        seen.add(label)
    return chain


def register_market_insight_manager(mcp):
    """注册市场洞察管理器工具"""

    @mcp.tool()
    async def market_insight_manager(action: str, params: dict | None = None, kwargs: Any = None):
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
        start_time = time.perf_counter()
        try:
            kwargs = normalize_manager_kwargs(
                dict(kwargs),
                field_aliases={"sector": ("block_name", "name")},
            )

            def _ok(data: dict, source_chain=None):
                return ok_with_meta(
                    data,
                    tool_name="market_insight_manager",
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )

            def _fail(message: str, source_chain=None):
                return fail_with_meta(
                    message,
                    tool_name="market_insight_manager",
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )

            if action == 'help':
                return _ok({
                    'supported_actions': {
                        'market_trend': '市场趋势分析（基于真实指数行情与K线）',
                        'sector_analysis': '板块分析（基于真实板块资金流向）',
                        'help': '显示帮助信息',
                    }
                }, source_chain=['market_insight_manager'])

            elif action == 'market_trend':
                payload, source_chain = await _market_trend()
                return _ok(payload, source_chain=source_chain)

            elif action == 'sector_analysis':
                sector = kwargs.get('sector') or kwargs.get('block_name') or kwargs.get('name')
                payload, source_chain = await _sector_analysis(sector=sector)
                return _ok(payload, source_chain=source_chain)

            else:
                return _fail(
                    f'Unknown action: {action}. Supported: help, market_trend, sector_analysis',
                    source_chain=['market_insight_manager'],
                )
        except Exception as e:
            logger.exception("[market_insight_manager] error")
            return fail_with_meta(
                str(e),
                tool_name='market_insight_manager',
                action=action,
                started_at=start_time,
                source_chain=['market_insight_manager'],
            )

    async def _market_trend():
        """基于真实指数行情判断市场趋势"""
        from ..market.quote import get_index_quote
        from ..market.kline import get_index_kline
        source_chain = ['market_insight_manager', 'market.quote.get_index_quote']

        # 1. 获取上证指数实时行情
        idx_quote = get_index_quote("000001")
        current_price = 0.0
        change_pct = 0.0
        day_open = None
        day_high = None
        day_low = None
        pre_close = None
        if idx_quote.get('success') and idx_quote.get('data'):
            d = idx_quote['data']
            current_price = _safe_float(d.get('price') or d.get('最新价') or d.get('close'))
            change_pct = _safe_float(d.get('changePercent') or d.get('change_pct') or d.get('涨跌幅'))
            day_open = _safe_float(d.get('open') or d.get('今开'), None)
            day_high = _safe_float(d.get('high') or d.get('最高'), None)
            day_low = _safe_float(d.get('low') or d.get('最低'), None)
            pre_close = _safe_float(d.get('preClose') or d.get('昨收') or d.get('prev_close'), None)
            if (change_pct == 0.0 or not np.isfinite(change_pct)) and current_price and pre_close:
                change_pct = ((current_price - pre_close) / pre_close) * 100

        # 2. 获取近60日指数K线计算趋势（使用指数专用接口，避免与个股000001混淆）
        kline_res = await get_index_kline(index_code="000001", period="daily", limit=60)
        source_chain.append('market.kline.get_index_kline')
        trend = 'unknown'
        strength = 'unknown'
        support = None
        resistance = None
        ma5 = ma20 = ma60 = None
        analysis_mode = 'insufficient_data'

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
                    analysis_mode = 'kline'

        if analysis_mode != 'kline' and current_price > 0:
            quote_levels = [
                value for value in (day_low, day_open, pre_close, current_price)
                if value is not None and value > 0
            ]
            if quote_levels:
                support = min(quote_levels)
            resistance_levels = [
                value for value in (day_high, day_open, pre_close, current_price)
                if value is not None and value > 0
            ]
            if resistance_levels:
                resistance = max(resistance_levels)

            baseline = next((value for value in (pre_close, day_open, current_price) if value is not None and value > 0), None)
            if baseline is not None:
                ma20 = baseline
                ma60 = baseline
            ma5 = current_price

            if change_pct >= 1.0:
                trend = 'bullish'
            elif change_pct <= -1.0:
                trend = 'bearish'
            else:
                trend = 'sideways'

            abs_change = abs(change_pct)
            if abs_change >= 2.0:
                strength = 'strong'
            elif abs_change >= 0.8:
                strength = 'medium'
            else:
                strength = 'weak'

            analysis_mode = 'quote_fallback'
            source_chain.append('market_trend.quote_fallback')

        return (
            {
                'trend': trend,
                'strength': strength,
                'currentPrice': round(current_price, 2),
                'changePercent': round(change_pct, 2),
                'keyLevels': {
                    'support': _rounded_or_none(support),
                    'resistance': _rounded_or_none(resistance),
                },
                'movingAverages': {
                    'ma5': _rounded_or_none(ma5),
                    'ma20': _rounded_or_none(ma20),
                    'ma60': _rounded_or_none(ma60),
                },
                'analysisMode': analysis_mode,
                'index': '上证指数(000001)',
            },
            _dedupe_chain(source_chain),
        )

    async def _sector_analysis(sector: str | None = None):
        """基于真实板块资金流向数据"""
        from ..fund_flow import get_sector_fund_flow, get_concept_fund_flow
        source_chain = ['market_insight_manager']

        hot_sectors = []
        cold_sectors = []
        rotation = 'unknown'

        # 行业板块资金流向
        sector_res = get_sector_fund_flow(top_n=10)
        if sector_res.get('success') and sector_res.get('data'):
            source_chain.append('fund_flow.get_sector_fund_flow')
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
            source_chain.append('fund_flow.get_concept_fund_flow')
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

        requested_sector = str(sector or '').strip()
        matched_count = 0
        if requested_sector:
            keyword = requested_sector.lower()

            def _match_name(item):
                return keyword in str(item.get('name') or '').lower()

            def _dedupe_items(items):
                deduped = []
                seen = set()
                for item in items:
                    name_key = str(item.get('name') or '').lower()
                    if name_key in seen:
                        continue
                    seen.add(name_key)
                    deduped.append(item)
                return deduped

            hot_sectors = _dedupe_items([item for item in hot_sectors if _match_name(item)])
            cold_sectors = _dedupe_items([item for item in cold_sectors if _match_name(item)])
            concept_hot = _dedupe_items([item for item in concept_hot if _match_name(item)])
            matched_names = {
                str(item.get('name') or '').lower()
                for item in [*hot_sectors, *cold_sectors, *concept_hot]
                if item.get('name')
            }
            matched_count = len(matched_names)

        payload = {
            'hotSectors': hot_sectors,
            'coldSectors': cold_sectors,
            'hotConcepts': concept_hot,
            'rotation': rotation,
        }
        if requested_sector:
            payload['requestedSector'] = requested_sector
            payload['matchedCount'] = matched_count
            if matched_count == 0:
                payload['message'] = f'未在当前热点板块中匹配到 {requested_sector}'
        return payload, _dedupe_chain(source_chain)
