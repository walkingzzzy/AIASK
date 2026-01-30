# akshare-fundamental 工具清单

## 财务与基础信息
- get_stock_info(stock_code: str)
- get_financials(stock_code: str)

## 估值
- get_valuation_metrics(code: str)
- get_historical_valuation(code: str, days: int = 30)
- dcf_valuation(code: str, discount_rate: float = 0.10, growth_rate: float = 0.05, years: int = 5)
- ddm_valuation(code: str, dividend: float = None, growth_rate: float = 0.05, required_return: float = 0.10)
- relative_valuation(code: str, metrics: list[str] = None, peers: list[str] = None)

## 情绪与语义
- analyze_stock_sentiment(code: str)
- calculate_fear_greed_index()
- parse_selection_query(query: str)
- smart_stock_diagnosis(stock_code: str)
- generate_daily_report(date: str = None)

## 关键参数说明
- DDM: growth_rate 必须小于 required_return
- date: YYYY-MM-DD（日报默认今日）
