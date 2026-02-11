# 获取快照数据 get_market_snapshot

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10iig4pb6e0.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取最新行情数据。

```python
get_market_snapshot(stock_code: str) -> Dict
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 证券代码 |

## 返回参数

| 参数 | 默认返回 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| ItemNum | Y | str | 采样点数 |
| Open | Y | str | 开盘价 |
| High | Y | str | 最高价 |
| Low | Y | str | 最低价 |
| LastClose | Y | str | 前收盘价 |
| Now | Y | str | 现价 |
| RefreshNum | Y | str | 刷新数/行情时间 |
| Volume | Y | str | 总手 |
| NowVol | Y | str | 现手 |
| Amount | Y | str | 总成交金额 |
| Inside | Y | str | 内盘 |
| Outside | Y | str | 外盘 |
| TickDiff | Y | str | 笔涨跌 |
| InOutFlag | Y | str | 内外盘标志：0:Buy 1:Sell 2:None |
| CJBS | Y | str | 成交笔数 |
| Jjjz | Y | str | 基金净值 |
| Buyp | Y | List[str] | 五个买价 |
| Buyv | Y | List[str] | 对应的五个买盘量 |
| Sellp | Y | List[str] | 五个卖价 |
| Sellv | Y | List[str] | 对应的五个卖盘量 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

market_snapshot = tq.get_market_snapshot(stock_code='688318.SH')
print(market_snapshot)
```

## 返回数据样本

```python
{'Amount': '33832.39',
 'Buyp': ['131.32', '0.00', '0.00', '0.00', '0.00'],
 'Buyv': ['3', '0', '0', '0', '0'],
 'CJBS': '0',
 'ErrorId': '0',
 'InOutFlag': '0',
 'Inside': '10060',
 'ItemNum': '2079',
 'Jjjz': '0.00',
 'LastClose': '128.42',
 'Max': '131.87',
 'Min': '128.00',
 'Now': '131.29',
 'NowVol': '25',
 'Open': '128.01',
 'Outside': '15889',
 'RefreshNum': '0',
 'Sellp': ['131.33', '0.00', '0.00', '0.00', '0.00'],
 'Sellv': ['10', '0', '0', '0', '0'],
 'TickDiff': '0.11',
 'Volume': '25949'}
```

