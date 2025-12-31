from packages.core.services.stock_data_service import StockDataService

s = StockDataService()
print('=== 测试StockDataService ===')

print('获取600519行情:')
quote = s.get_realtime_quote('600519')
if quote:
    print(f'  股票: {quote.get("stock_name")}')
    print(f'  价格: {quote.get("current_price")}')
else:
    print('  未获取到行情')

print('获取日线数据:')
df = s.get_daily_bars('600519', days=10)
if df is not None:
    print(f'  获取到 {len(df)} 条数据')
    print(df.tail(3))
else:
    print('  未获取到日线数据')

print('计算技术指标:')
indicators = s.calculate_indicators('600519')
if indicators:
    print(f'  MA5: {indicators.get("ma5")}')
    print(f'  MA20: {indicators.get("ma20")}')
    print(f'  RSI: {indicators.get("rsi")}')
    print(f'  收盘价: {indicators.get("close")}')
else:
    print('  未计算出指标')
