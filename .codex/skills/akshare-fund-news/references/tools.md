# akshare-fund-news 工具清单

## 资金流/北向/龙虎榜/两融/大宗
- get_stock_fund_flow(stock_code: str)
- get_north_fund()
- get_north_fund_holding(...)
- get_north_fund_top(...)
- get_sector_fund_flow(...)
- get_concept_fund_flow(...)
- get_dragon_tiger(...)
- get_margin_data(...)
- get_margin_ranking(...)
- get_block_trades(...)

## 研报/公告/新闻
- get_stock_notices(start_date: str, end_date: str, types: list[str] = None, stock_code: str = "")
- get_stock_research(stock_code: str, limit: int = 10)
- get_research_reports(symbol: str = "", limit: int = 10)
- search_research(keyword: str = "", stock_code: str = "", days: int = 30)
- get_analyst_ranking(year: str = "")
- get_profit_forecast(symbol: str = "")
- get_stock_news(stock_code: str, limit: int = 20)
- get_market_news(limit: int = 20)

## 关键参数说明
- 公告日期：YYYY-MM-DD 或 YYYYMMDD
- types: 全部/重大事项/财务报告/融资公告/风险提示/资产重组/信息变更/持股变动
