# akshare-fundamental 参数/别名兼容

来自 `akshare_mcp/tool_aliases.py` 的常用映射（仅列基本面相关）。

## 工具别名
- get_financial_summary -> get_financials
- get_historical_financials -> get_financials
- get_valuation_metrics -> get_stock_info（兼容层）

## 返回字段别名（Python -> Node）
- net_profit -> netProfit
- total_revenue -> revenue
- gross_margin -> grossMargin
- net_margin -> netMargin
- debt_ratio -> debtRatio
- current_ratio -> currentRatio
- pe_ratio -> peRatio
- pb_ratio -> pbRatio
- market_cap -> marketCap
