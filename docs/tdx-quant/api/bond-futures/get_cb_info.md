# 获取可转债基础信息 get_cb_info

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1h137euvcjn98.html
> 抓取时间: 2026-02-03

## 函数说明

根据可转债代码获取可转债基础信息。

```python
get_cb_info(stock_code: str = ''):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 可转债代码 |

## 主要返回字段

| 字段 | 说明 |
|------|------|
| KZZCode | 可转债代码 |
| HSCode | 正股代码 |
| HSScore | 正股评级 |
| KZZScore | 可转债评级 |
| CurRate | 当前利率 |
| EndDate | 到期日期 |
| EndPrice | 到期价格 |
| ExpireYield | 到期收益率 |
| ForceRedeem | 强赎价格 |
| PutBack | 回售价格 |
| PutDate | 回售日期 |
| PutPrice | 回售价格 |
| RealValue | 实际价值 |
| RedeemDate | 赎回日期 |
| RedeemPrice | 赎回价格 |
| RestScope | 剩余规模 |
| ZGCode | 转股代码 |
| ZGDate | 转股日期 |
| ZGPrice | 转股价格 |
| ZGRate | 转股比例 |
| setcode | 市场代码 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
cb_info = tq.get_cb_info(stock_code='123039.SZ')
print(cb_info)
```

## 返回数据样本

```python
{'CurRate': '2.80',
'EndDate': '20251226',
'EndPrice': '115.00',
'ExpireYield': '0.00',
'ForceRedeem': '37.90',
'HSCode': '300577',
'HSScore': 'A+',
'KZZCode': '123039',
'KZZScore': 'A+',
'PutBack': '20.41',
'PutDate': '0',
'PutPrice': '0.00',
'RealValue': '0.00',
'RedeemDate': '0',
'RedeemPrice': '0.00',
'RestScope': '22044.02',
'ZGCode': '123039',
'ZGDate': '20200702',
'ZGPrice': '29.15',
'ZGRate': '1.15',
'setcode': '0'}
```

