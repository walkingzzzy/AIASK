---
name: akshare-fund-news
description: 资金流、北向资金、龙虎榜、融资融券、大宗交易，以及公告/研报/新闻/分析师排名/盈利预测等资讯类请求时使用。
---

# 目标
在资金流与资讯场景下，给出可复用的结构化结果，并明确日期范围与数量限制。

# 使用流程
- 资金流向
  - 个股资金流：用 `get_stock_fund_flow`。
  - 北向资金：用 `get_north_fund`，个股/Top/持股用 `get_north_fund_holding`、`get_north_fund_top`。
  - 板块资金：行业/概念分别用 `get_sector_fund_flow`、`get_concept_fund_flow`。
  - 龙虎榜：用 `get_dragon_tiger`。
  - 两融：用 `get_margin_data`、`get_margin_ranking`。
  - 大宗交易：用 `get_block_trades`。
- 研报与新闻
  - 个股研报列表：`get_stock_research` 或 `get_research_reports`。
  - 研报检索：`search_research`（支持关键词与股票代码）。
  - 公告日历：`get_stock_notices`（必须给起止日期）。
  - 个股新闻：`get_stock_news`；市场新闻：`get_market_news`。
  - 分析师排名：`get_analyst_ranking`；盈利预测：`get_profit_forecast`。

# 失败与兜底
- 研报/新闻为空：提示接口可能受限，并建议缩小日期范围或改用公告数据。
- 公告日期跨度过大：缩短到允许范围（参考 env 配置）。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。
- 读取 `references/env.md` 了解数据源与限额配置。
