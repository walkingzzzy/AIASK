"""交易计划生成器 — 信号融合 + 场景化交易方案。

设计原则:
  分析可用 10 个指标，但开仓/平仓判据最多 3 个信号:
    主信号 (1): 趋势方向 — MACD方向 + 均线排列
    触发信号 (1): 入场时机 — RSI/关键位/K线形态
    确认信号 (1): 成交量/资金流
"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'trade_plan_parts', ['parsers.py', 'payloads.py', 'formatters.py', 'actions.py'], future_annotations=True)
