# akshare-market 参数/别名兼容

来自 `akshare_mcp/tool_aliases.py` 的常用映射（仅列市场相关）。

## 参数别名
- get_batch_quotes: codes -> stock_codes
- get_kline_data: code -> stock_code, startDate -> start_date, endDate -> end_date

## 工具别名
- get_kline_data -> get_kline（仅在兼容层使用；优先使用实际工具名）
