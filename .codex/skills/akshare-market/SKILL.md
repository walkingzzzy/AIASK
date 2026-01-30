---
name: akshare-market
description: A股行情、K线、分钟线、盘口、成交明细、涨停、指数、板块及成分股等市场数据请求时使用；适用于股票搜索/代码确认、单只或批量行情、K线与分钟线查询场景。
---

# 目标
提供快速、结构化的市场数据结果，并在必要时先完成代码解析。

# 使用流程
- 识别代码：用户给名称/简称时，先调用 `search_stocks`，若多结果则提示确认代码。
- 实时行情：单只用 `get_realtime_quote`；多只用 `get_batch_quotes`。
- K线数据：
  - 需要日期范围/复权时用 `get_kline_data`。
  - 仅最近N条时用 `get_kline`。
  - 分钟线用 `get_minute_kline`，仅支持 1m/5m/15m/30m/60m。
- 盘口与成交：盘口用 `get_order_book`，成交明细用 `get_trade_details`。
- 涨停：用 `get_limit_up_stocks` 与 `get_limit_up_statistics`。
- 指数：用 `get_index_quote`。
- 板块：用 `get_market_blocks` 获取板块，再用 `get_block_stocks` 获取成分股。

# 失败与兜底
- 未找到代码：要求用户明确代码或先执行 `search_stocks`。
- 日期不合法：要求使用 YYYY-MM-DD 或 YYYYMMDD。
- 周期不合法：提示可用周期（daily/weekly/monthly/1m/5m/15m/30m/60m）。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。
- 读取 `references/aliases.md` 了解兼容参数名与别名。
