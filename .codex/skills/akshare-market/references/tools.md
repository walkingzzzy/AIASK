# akshare-market 工具清单

## 股票搜索
- search_stocks(keyword: str, limit: int = 20)  搜索股票代码或名称
- get_stock_list()  获取A股股票列表

## 实时行情
- get_realtime_quote(stock_code: str)
- get_batch_quotes(stock_codes: list[str])
- get_batch_quotes_compat(codes: list[str])  兼容Node.js参数名

## K线与分钟线
- get_kline(stock_code: str, period: str = "daily", limit: int = 100)
- get_kline_data(code: str, period: str = "daily", start_date: str = None, end_date: str = None, limit: int = 30, adjust: str = "")
- get_minute_kline(stock_code: str, period: str = "5m", limit: int = 300)

## 盘口与成交
- get_order_book(stock_code: str)
- get_trade_details(stock_code: str, limit: int = 20)

## 涨停
- get_limit_up_stocks(date: str = "")
- get_limit_up_statistics(date: str = "")

## 指数
- get_index_quote(index_code: str)

## 板块
- get_market_blocks(block_type: str = "industry", limit: int = None)
- get_block_stocks(block_code: str)

## 关键参数说明
- period: daily/weekly/monthly/1m/5m/15m/30m/60m
- adjust: "" 不复权, "qfq" 前复权, "hfq" 后复权
- 日期格式: YYYY-MM-DD 或 YYYYMMDD（按工具说明）
