# 获取K线数据 get_market_data

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10g60jt68sc.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取历史行情。

```python
get_market_data(field_list: List[str] = [],
                stock_list: List[str] = [],
                period: str = '',
                start_time: str = '',
                end_time: str = '',
                count: int = -1,
                dividend_type: Optional[str] = None,
                fill_data: bool = True) -> Dict
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | N | List[str] | 字段筛选，传空则返回全部 |
| stock_list | Y | List[str] | 证券代码列表 |
| period | Y | str | 周期 |
| start_time | N | str | 起始时间 |
| end_time | N | str | 结束时间 |
| count | N | int | 返回数据个数（每只股票） |
| dividend_type | N | str | 复权类型：none不复权、front前复权、back后复权 |
| fill_data | N | bool | 是否向后填充空缺数据 |

## 返回参数

返回 `dict { field1: value1, field2: value2, ... }`

| 参数 | 默认返回 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| Amount | Y | str | 成交额 |
| Volume | Y | str | 成交量 |
| Date | Y | str | 日期 |
| Time | Y | str | 时间 |
| Open | Y | str | 开盘价 |
| High | Y | str | 最高价 |
| Low | Y | str | 最低价 |
| Close | Y | str | 收盘价 |
| ForwardFactor | Y | str | 前复权因子，当dividend_type=none时候返回有效值 |

**说明**：只有 `dividend_type` 传入为 `none` 时，会返回有效的前复权因子 `ForwardFactor`

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
df = tq.get_market_data(
    field_list=[],
    stock_list=['688318.SH'],
    start_time='20251220',
    end_time='',
    count=1,
    dividend_type='none',
    period='1d',
    fill_data=True
)
print(df)
```

## 返回数据样本

```python
{'Amount':             688318.SH
2025-12-24   29394.81,
'Low':             688318.SH
2025-12-24      128.0,
'Date':              688318.SH
2025-12-24  20251224.0,
'Volume':             688318.SH
2025-12-24  2257325.0,
'Close':             688318.SH
2025-12-24     131.58,
'Open':             688318.SH
2025-12-24     128.01,
'Time':             688318.SH
2025-12-24        0.0,
'High':             688318.SH
2025-12-24     131.87,
'ForwardFactor':             688318.SH
2025-12-24        1.0}
```

