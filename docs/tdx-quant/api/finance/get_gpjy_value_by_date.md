# 获取指定日期股票交易数据 get_gpjy_value_by_date

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h2pci5gh6h7k.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取指定时间段内的股票交易数据，需要先在客户端中下载股票数据包。

```python
def get_gpjy_value_by_date(stock_list: List[str] = [],
                           field_list: List[str] = [],
                           year: int = 0,
                           mmdd: int = 0) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空 |
| stock_list | Y | List[str] | 证券代码列表 |
| year | Y | int | 指定年份 |
| mmdd | Y | int | 指定月日 |

**说明**：当year和mmdd默认为0时返回最近一条数据。

## 输出参数

同 get_gpjy_value 一样。

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

gp_one = tq.get_gpjy_value_by_date(
        stock_list=['688318.SH'],
        field_list=['GP1','GP2','GP3','GP4','GP5'],
        year=0, mmdd=0)
print(gp_one)
```

## 返回数据样本

```python
{'688318.SH': {'GP1': ['24154.00', '0.00'], 'GP2': ['20574.12', '18728.85'], 'GP3': ['140464.83', '55043.00'], 'GP4': ['169.80', '5943.00'], 'GP5': ['103.00', '-7000.00']}}
```

