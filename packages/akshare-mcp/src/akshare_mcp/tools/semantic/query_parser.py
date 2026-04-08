"""选股查询解析 — parse_selection_query + 辅助函数"""

import re
from ...utils import ok, fail


def parse_selection_query(query: str):
    """
    解析自然语言选股查询，将中文条件转换为结构化筛选参数

    适用场景: 将用户口语化的选股需求转换为 screener_manager 可消费的条件格式

    Args:
        query (str, required): 自然语言查询，支持基本面+技术面混合条件
            基本面示例: "市盈率小于20且ROE大于15%"、"市值大于100亿"
            技术面示例: "MACD金叉且放量"、"连续3天上涨"
            组合示例: "PE<20且MACD金叉"

    Returns:
        dict: {"success": bool, "data": {
            "query": str,                          # 原始查询
            "fundamental_conditions": list[dict],  # 基本面条件，每项含 field/operator/value
            "technical_conditions": list[dict],    # 技术面条件，每项含 id(str), params(dict|null)
            "logic": str,                          # 条件逻辑关系 "AND"|"OR"
            "parsed": bool,                        # 是否解析成功
            "has_fundamental": bool,
            "has_technical": bool,
            "suggestion": str                      # 推荐的后续调用建议
        }}

    Errors:
        - 无法解析出有效条件时 suggestion 会提示用户使用更具体的描述

    Examples:
        parse_selection_query("市盈率小于20且ROE大于15%")
        parse_selection_query("MACD金叉且放量")
    """
    try:
        conditions = []
        tech_conditions = []

        q = query.lower()

        # 通用比较运算符模式（支持中英文）
        LT = r'(?:[<＜]|小于|低于|不超过|不高于|<=|≤)'
        GT = r'(?:[>＞]|大于|高于|超过|不低于|>=|≥)'

        # ============== 基本面条件解析 ==============
        _parse_fundamental(q, conditions, LT, GT)

        # ============== 技术面条件解析 ==============
        _parse_technical(q, tech_conditions)

        # 确定逻辑关系
        logic = 'AND'
        if '或' in query or '或者' in query or 'or' in q:
            logic = 'OR'

        return ok({
            'query': query,
            'fundamental_conditions': conditions,
            'technical_conditions': tech_conditions,
            'logic': logic,
            'parsed': True,
            'has_fundamental': len(conditions) > 0,
            'has_technical': len(tech_conditions) > 0,
            'suggestion': _build_suggestion(conditions, tech_conditions, logic),
        })

    except Exception as e:
        return fail(str(e))


# --------------- 内部辅助 ---------------

def _parse_fundamental(q: str, conditions: list, LT: str, GT: str):
    """解析基本面条件"""
    # PE / 市盈率
    pe_match = re.search(rf'(?:pe|市盈率)\s*{LT}\s*(\d+\.?\d*)', q)
    if pe_match:
        conditions.append({'field': 'pe_ratio', 'operator': '<', 'value': float(pe_match.group(1))})
    pe_match2 = re.search(rf'(?:pe|市盈率)\s*{GT}\s*(\d+\.?\d*)', q)
    if pe_match2:
        conditions.append({'field': 'pe_ratio', 'operator': '>', 'value': float(pe_match2.group(1))})
    pe_range = re.search(r'(?:pe|市盈率)\s*(?:在)?\s*(\d+\.?\d*)\s*(?:到|至|-|~)\s*(\d+\.?\d*)', q)
    if pe_range:
        conditions.append({'field': 'pe_ratio', 'operator': '>', 'value': float(pe_range.group(1))})
        conditions.append({'field': 'pe_ratio', 'operator': '<', 'value': float(pe_range.group(2))})

    # PB / 市净率
    pb_match = re.search(rf'(?:pb|市净率)\s*{LT}\s*(\d+\.?\d*)', q)
    if pb_match:
        conditions.append({'field': 'pb_ratio', 'operator': '<', 'value': float(pb_match.group(1))})
    pb_match2 = re.search(rf'(?:pb|市净率)\s*{GT}\s*(\d+\.?\d*)', q)
    if pb_match2:
        conditions.append({'field': 'pb_ratio', 'operator': '>', 'value': float(pb_match2.group(1))})

    # ROE / 净资产收益率
    roe_match = re.search(rf'(?:roe|净资产收益率)\s*{GT}\s*(\d+\.?\d*)%?', q)
    if roe_match:
        val = float(roe_match.group(1))
        conditions.append({'field': 'roe', 'operator': '>', 'value': val / 100 if val > 1 else val})
    roe_match2 = re.search(rf'(?:roe|净资产收益率)\s*{LT}\s*(\d+\.?\d*)%?', q)
    if roe_match2:
        val = float(roe_match2.group(1))
        conditions.append({'field': 'roe', 'operator': '<', 'value': val / 100 if val > 1 else val})

    # 负债率
    debt_match = re.search(rf'负债率\s*{LT}\s*(\d+\.?\d*)%?', q)
    if debt_match:
        val = float(debt_match.group(1))
        conditions.append({'field': 'debt_ratio', 'operator': '<', 'value': val / 100 if val > 1 else val})
    debt_match2 = re.search(rf'负债率\s*{GT}\s*(\d+\.?\d*)%?', q)
    if debt_match2:
        val = float(debt_match2.group(1))
        conditions.append({'field': 'debt_ratio', 'operator': '>', 'value': val / 100 if val > 1 else val})

    # 营收增长
    rev_match = re.search(rf'(?:营收增长|收入增长|营收增速|净利润增长|利润增速)\s*{GT}\s*(\d+\.?\d*)%?', q)
    if rev_match:
        val = float(rev_match.group(1))
        conditions.append({'field': 'revenue_growth', 'operator': '>', 'value': val / 100 if val > 1 else val})

    # 市值
    cap_match = re.search(rf'市值\s*{GT}\s*(\d+\.?\d*)\s*亿', q)
    if cap_match:
        conditions.append({'field': 'market_cap', 'operator': '>', 'value': float(cap_match.group(1)) * 1e8})
    cap_match2 = re.search(rf'市值\s*{LT}\s*(\d+\.?\d*)\s*亿', q)
    if cap_match2:
        conditions.append({'field': 'market_cap', 'operator': '<', 'value': float(cap_match2.group(1)) * 1e8})

    # 股息率
    div_match = re.search(rf'(?:股息率|分红率)\s*{GT}\s*(\d+\.?\d*)%?', q)
    if div_match:
        conditions.append({'field': 'dividend_yield', 'operator': '>', 'value': float(div_match.group(1))})


# 关键词 → 条件ID 映射
KEYWORD_MAP = {
    # 趋势
    'macd金叉': 'macd_golden_cross',
    'macd死叉': 'macd_death_cross',
    'macd零轴上': 'macd_above_zero',
    'macd底背离': 'macd_divergence_bull',
    'macd顶背离': 'macd_divergence_bear',
    'kdj金叉': 'kdj_golden_cross',
    'kdj死叉': 'kdj_death_cross',
    'kdj超卖': 'kdj_oversold',
    'kdj超买': 'kdj_overbought',
    'rsi超卖': 'rsi_oversold',
    'rsi超买': 'rsi_overbought',
    '布林收窄': 'boll_squeeze',
    '突破布林上轨': 'boll_breakout_upper',
    '跌破布林下轨': 'boll_breakout_lower',
    'dmi趋势增强': 'dmi_trend_strong',
    # 均线
    '均线多头': 'ma_bull',
    '多头排列': 'ma_bull',
    '均线空头': 'ma_bear',
    '空头排列': 'ma_bear',
    '均线金叉': 'golden_cross_ma',
    '均线死叉': 'death_cross_ma',
    '站上均线': 'price_above_ma',
    '跌破均线': 'price_below_ma',
    '创新高': 'new_high',
    '创新低': 'new_low',
    '突破前高': 'breakout_high',
    '上升趋势': 'trend_up',
    # 量价
    '放量': 'volume_breakout',
    '放量突破': 'volume_breakout',
    '缩量': 'volume_shrink',
    '缩量整理': 'volume_shrink',
    '量价齐升': 'volume_price_up',
    '量价背离': 'volume_price_diverge',
    '地量': 'low_volume_bottom',
    '量比': 'volume_ratio_high',
    # K线形态
    '锤头线': 'pattern_hammer',
    '流星线': 'pattern_shooting_star',
    '看涨吞没': 'pattern_engulfing_bull',
    '看跌吞没': 'pattern_engulfing_bear',
    '早晨之星': 'pattern_morning_star',
    '黄昏之星': 'pattern_evening_star',
    '红三兵': 'pattern_three_white',
    '三只乌鸦': 'pattern_three_black',
    '十字星': 'pattern_doji',
    '长下影线': 'pattern_long_lower_shadow',
    # A股特色
    '涨停': 'limit_up',
    '跌停': 'limit_down',
    '连板': 'continuous_limit_up',
    '首板': 'first_limit_up',
    '缩量涨停': 'limit_up_volume_shrink',
    't字板': 't_board',
    '一字板': 'one_line_board',
    '大阳线': 'big_yang',
    '大阴线': 'big_yin',
    '跳空高开': 'gap_up',
    '跳空低开': 'gap_down',
    # 组合策略
    '强势突破': 'strong_breakout',
    '底部反转': 'bottom_reversal',
    '趋势跟踪': 'trend_following',
    'vcp': 'vcp',
    '动量爆发': 'momentum_burst',
    '超跌反弹': 'oversold_bounce',
    '背离买入': 'divergence_buy',
}


def _parse_technical(q: str, tech_conditions: list):
    """解析技术面条件"""
    existing_ids = set()

    def _append_condition(condition_id: str, params: dict | None = None):
        if condition_id in existing_ids:
            return
        payload = {'id': condition_id}
        if isinstance(params, dict) and params:
            payload['params'] = params
        tech_conditions.append(payload)
        existing_ids.add(condition_id)

    # 连续上涨/下跌 带天数
    up_match = re.search(r'连(?:续|涨)\s*(\d+)\s*(?:天|日|个交易日)?\s*(?:上涨)?', q)
    if up_match or '连续上涨' in q or '连涨' in q:
        n = int(up_match.group(1)) if up_match else 3
        _append_condition('upn', {'n': n})

    down_match = re.search(r'连(?:续|跌)\s*(\d+)\s*(?:天|日|个交易日)?\s*(?:下跌)?', q)
    if down_match or '连续下跌' in q or '连跌' in q:
        n = int(down_match.group(1)) if down_match else 3
        _append_condition('downn', {'n': n})

    # 连板天数
    board_match = re.search(r'(\d+)\s*连板', q)
    if board_match:
        _append_condition('continuous_limit_up', {'n': int(board_match.group(1))})

    # 价格与均线关系
    ma_above_match = re.search(r'(?:站上|突破|上穿)\s*(\d+)\s*日?均线', q)
    if ma_above_match:
        _append_condition('price_above_ma', {'n': int(ma_above_match.group(1))})

    ma_below_match = re.search(r'(?:跌破|失守|下穿)\s*(\d+)\s*日?均线', q)
    if ma_below_match:
        _append_condition('price_below_ma', {'n': int(ma_below_match.group(1))})

    # 均线交叉
    ma_golden_match = re.search(r'(\d+)\s*日均线\s*(?:上穿|金叉)\s*(\d+)\s*日均线', q)
    if ma_golden_match:
        _append_condition(
            'golden_cross_ma',
            {'short': int(ma_golden_match.group(1)), 'long': int(ma_golden_match.group(2))},
        )

    ma_death_match = re.search(r'(\d+)\s*日均线\s*(?:下穿|死叉)\s*(\d+)\s*日均线', q)
    if ma_death_match:
        _append_condition(
            'death_cross_ma',
            {'short': int(ma_death_match.group(1)), 'long': int(ma_death_match.group(2))},
        )

    # 关键词匹配
    for keyword, cond_id in KEYWORD_MAP.items():
        if keyword in q:
            _append_condition(cond_id)


def _build_suggestion(fundamental, technical, logic):
    """根据解析结果生成调用建议"""
    if fundamental and technical:
        return (
            f"建议使用 screener_manager(action='combined_screen', "
            f"fundamental_criteria={{{_fmt_fund(fundamental)}}}, "
            f"tech_conditions={_fmt_tech(technical)}, "
            f"logic='{logic}')"
        )
    elif technical:
        return (
            f"建议使用 screener_manager(action='technical_screen', "
            f"conditions={_fmt_tech(technical)}, "
            f"logic='{logic}')"
        )
    elif fundamental:
        return (
            f"建议使用 screener_manager(action='screen', "
            f"criteria={{{_fmt_fund(fundamental)}}})"
        )
    else:
        return "未能解析出有效条件，请尝试更具体的描述"


def _fmt_fund(conditions):
    """格式化基本面条件为 criteria 参数"""
    mapping = {
        'pe_ratio': {'<': 'max_pe', '>': 'min_pe'},
        'pb_ratio': {'<': 'max_pb', '>': 'min_pb'},
        'roe': {'>': 'min_roe', '<': 'max_roe'},
        'debt_ratio': {'<': 'max_debt_ratio'},
        'revenue_growth': {'>': 'min_revenue_growth'},
        'market_cap': {'>': 'min_market_cap', '<': 'max_market_cap'},
        'dividend_yield': {'>': 'min_dividend_yield'},
    }
    parts = []
    for c in conditions:
        field_map = mapping.get(c['field'], {})
        key = field_map.get(c['operator'])
        if key:
            parts.append(f"'{key}': {c['value']}")
    return ', '.join(parts)


def _fmt_tech(conditions):
    """格式化技术条件，保留参数化条件。"""
    formatted = []
    for item in conditions:
        if not isinstance(item, dict):
            continue
        condition_id = item.get('id')
        params = item.get('params')
        if params:
            formatted.append({'id': condition_id, 'params': params})
        else:
            formatted.append(condition_id)
    return repr(formatted)
