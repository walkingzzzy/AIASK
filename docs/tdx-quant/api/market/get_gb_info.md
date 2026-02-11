# 获取每天的股本数据 get_gb_info

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3ru0b1tssrc.html
> 抓取时间: 2026-02-03

## 函数说明

获取指定股票的股本数据。

```python
def get_gb_info(stock_code: str = '',
                date_list: List[str] = [],
                count: int = 1):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 股票代码 |
| date_list | Y | List[str] | 日期数组 |
| count | Y | int | 日期有效个数 |

**说明**：
- `date_list` 传入的日期须从小到大排序
- `date_list` 有效数据个数须不小于 `count`，且不能小于1

## 返回参数

| 名称 | 类型 | 说明 |
|------|------|------|
| Date | double | 日期 |
| ltgb | double | 流通股本 |
| zgb | double | 总股本 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
gb_info = tq.get_gb_info(stock_code='688318.SH', date_list=['20250101', '20250601'], count=2)
print(gb_info)
```

## 返回数据样本

```python
[{'Date': 20250101, 'ltgb': 182942480.0, 'zgb': 182942480.0},
{'Date': 20250601, 'ltgb': 182942480.0, 'zgb': 182942480.0}]
```

