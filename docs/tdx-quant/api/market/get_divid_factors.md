# 获取分红配送数据 get_divid_factors

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10hsiat36k4.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取指定时间段内的分红配送数据。

```python
get_divid_factors(stock_code: str,
                  start_time: str,
                  end_time: str) -> pd.DataFrame:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 证券代码 |
| start_time | N | str | 起始时间 |
| end_time | N | str | 结束时间 |

## 返回参数

| 参数 | 默认返回 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| Type | Y | str | 类型 |
| Bonus | Y | str | 分红金额 |
| AllotPrice | Y | str | 配股价格 |
| ShareBonus | Y | str | 送股比例 |
| Allotment | Y | str | 配股比例 |

## 接口使用

获取688318.SH全部分红配送数据：

```python
from tqcenter import tq

tq.initialize(__file__)
divid_factors = tq.get_divid_factors(
        stock_code='688318.SH',
        start_time='',
        end_time='')
print(divid_factors)
```

## 返回数据样本

```python
           Type  Bonus  AllotPrice  ShareBonus  Allotment
Date
2020-09-29    1    6.0         0.0         0.0        0.0
2021-05-27    1   10.0         0.0         0.0        0.0
2022-06-20    1   14.0         0.0         4.0        0.0
2023-06-13    1    5.0         0.0         4.0        0.0
2024-06-14    1    8.0         0.0         4.0        0.0
```

