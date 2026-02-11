# 向通达信公式系统设置数据信息 formula_set_data_info

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hs08rn02uc.html
> 抓取时间: 2026-02-03

## 函数说明

在调用公式前须先设置公式参数，此接口与 `formula_set_data` 功能相同，会互相覆盖。

```python
def formula_set_data_info(stock_code: str = '',
                          stock_period: str = '1d',
                          start_time: str = '',
                          end_time: str = '',
                          count: int = -1,
                          dividend_type: int = 0):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 股票代码 |
| stock_period | Y | str | K线周期 |
| start_time | Y | str | 起始时间 |
| end_time | Y | str | 结束时间 |
| count | Y | int | 截取K线数量 |
| dividend_type | Y | int | 复权类型：0不复权 1前复权 2后复权 |

**说明**：
- `count` 为截取最新交易日开始往前的n条K线，当 `count` 参数不为0时，`start_time` 和 `end_time` 失效
- `count=-1` 时，获取所有数据；`count=-2` 时，使用无序列数据
- 当 `count` 为0时，`start_time` 和 `end_time` 生效，指定K线为对应时间段内
- `count` 最大值为24000，`count` 为-1时为获取对应股票全部K线
- 设置的数据在断开连接前一直生效，后设置的数据会覆盖前面设置的数据

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

formula_set_res = tq.formula_set_data_info(stock_code='688318.SH', stock_period='1d', count=100, dividend_type=1)
print(formula_set_res)
```

## 返回数据样本

```python
{'ErrorId': '0', 'Msg': '向通达信公式系统设置数据信息成功！', 'run_id': '1'}
```

