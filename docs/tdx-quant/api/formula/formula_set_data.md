# 向通达信公式系统设置数据 formula_set_data

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hsvcct5sdc.html
> 抓取时间: 2026-02-03

## 函数说明

在调用公式前须先设置公式参数，此接口与 `formula_set_data_info` 功能相同，会互相覆盖。

```python
def formula_set_data(stock_code: str = '',
                     stock_period: str = '1d',
                     stock_data: List = [],
                     count: int = 1,
                     dividend_type: int = 0):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 股票代码 |
| stock_period | Y | str | K线周期 |
| stock_data | Y | List | 指定格式的K线数据 |
| count | Y | int | 选取的K线数量 |
| dividend_type | Y | int | 复权类型：0不复权 1前复权 2后复权 |

**说明**：
- `count` 为设定 `stock_data` 中生效的K线数据，即 `stock_data` 中有效数据不能小于 `count`
- `count` 须大于0，且最大不超过24000
- 设置的数据在断开连接前一直生效，后设置的数据会覆盖前面设置的数据

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

test_md = tq.get_market_data(stock_list=['688318.SH'], count=5, period='1d')
format_md = tq.formula_format_data(test_md)
formula_set_k = tq.formula_set_data(stock_code='688318.SH', stock_period='1d', stock_data=format_md['688318.SH'], count=len(format_md['688318.SH']))
print(formula_set_k)
```

## 返回数据样本

```python
{'ErrorId': '0', 'Msg': '向通达信公式系统设置数据成功！', 'run_id': '1'}
```

