# 回测及模拟交易

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h12t4q6fg29o.html
> 抓取时间: 2026-02-03

## 什么是量化交易

量化交易是指利用计算机科技并采用一定的数学模型去实现投资理念、实现投资策略的过程。简单的说，量化交易主要是做这样的事：

```
一个简单的投资想法 => 可执行的交易策略 => 可执行的代码程序 => 检验交易策略效果 => 实盘交易验证改进
```

## Step 1：从一个简单的投资想法开始

投资想法即我们认为可能会盈利的投资方法、理念，比如熊市时期银行股是潜力股、复制基金经理的增强指数、金叉买入死叉卖出等等。

以一个简单的投资想法为例：
- 如果遇到股价金叉，则买入
- 如果遇到股价死叉，则卖出

## Step 2：完善这个想法，形成明确的可执行的交易策略

一个可执行的交易策略至少需要明确以下几点:
- **Security**：确定投资品种或范围
- **Condition**：确定触发买/卖的具体条件
- **Quantity**：确定买卖的数量/金额等

细化后的策略：
- 监测沪深300指数的所有成分股的收盘价
- 如果收盘价上穿收盘价的5日简单移动平均，则用全部可用资金买入该股票
- 如果收盘价的5日简单移动平均上穿收盘价，则卖出该股票所有持仓

## Step 3：编写代码，把交易策略转成可执行的代码程序

```python
import pandas as pd
import vectorbt as vbt
from tqcenter import tq

tq.initialize(__file__)

# 核心配置
target_start = '20240930'
target_end = '20250930'
stock_code_list = ['688318.SH']
window = 5  # MA周期

start_time = (pd.to_datetime(target_start) - pd.Timedelta(days=window + 10)).strftime('%Y%m%d')

# 1.获取价格数据
df_real = tq.get_market_data(
    field_list=['Close', 'Open'],
    stock_list=stock_code_list,
    start_time=start_time,
    end_time=target_end,
    dividend_type='front',
    period='1d',
    fill_data=True
)
close_df = tq.price_df(df_real, 'Close', column_names=stock_code_list)
open_df = tq.price_df(df_real, 'Open', column_names=stock_code_list)

# 2.买卖信号计算
ma5_dynamic = vbt.MA.run(close_df, window=window).ma
entries_raw = close_df.vbt.crossed_above(ma5_dynamic)
exits_raw = close_df.vbt.crossed_below(ma5_dynamic)
entries_df = entries_raw.shift(1).fillna(False).astype(bool)
exits_df = exits_raw.shift(1).fillna(False).astype(bool)

# 3.执行回测
portfolio = vbt.Portfolio.from_signals(
    close=close_df,
    entries=entries_df,
    exits=exits_df,
    price=open_df,
    init_cash=100000,
    fees=0.0003,
    freq='D',
    size_granularity=100
)

# 4.输出结果
print(portfolio.stats())
print(portfolio.trades.records_readable)
```

## Step 4：回测或模拟交易，检验策略效果

- **回测**：用历史数据模拟执行策略
- **模拟交易**：用未来的实际数据模拟执行策略

## Step 5：实盘执行交易策略

实盘交易就是让计算机能根据实际行情，用真实资金账号来自动下单交易。

