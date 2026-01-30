# akshare-quant 工具清单

## 技术指标与形态
- calculate_technical_indicators(code: str, indicators: list[str], period: str = 'daily', limit: int = 100)
- check_candlestick_patterns(code: str, period: str = 'daily', limit: int = 100)
- get_available_patterns()

## 因子
- get_factor_library(category: str = 'all')
- calculate_factor(code: str, factor: str)
- calculate_factor_ic(codes: list, factor: str, period: int = 20)
- backtest_factor(codes: list, factor: str, groups: int = 5, holding_days: int = 20)

## 向量/相似度
- search_by_kline(code: str, days: int = 20, top_n: int = 10)
- search_similar_stocks(code: str, top_n: int = 10, similarity_type: str = 'both')
- semantic_stock_search(query: str, limit: int = 20)

## 关键参数说明
- indicators 常见：MA/EMA/RSI/MACD/KDJ/BOLL/ATR
- similarity_type: fundamental/technical/both
