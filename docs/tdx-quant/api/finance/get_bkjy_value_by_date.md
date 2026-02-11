# 获取指定日期板块交易数据 get_bkjy_value_by_date

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10p3d31736g.html
> 抓取时间: 2026-02-03

## 函数说明

根据板块代码，获取指定日期的板块交易数据，需要先在客户端中下载股票数据包。

```python
get_bkjy_value_by_date(stock_list: List[str] = [],
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

同 get_bkjy_value 一样。

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

bk_one = tq.get_bkjy_value_by_date(stock_list=['880660.SH'],
                                   field_list=['BK9','BK10','BK11','BK12','BK13'],
                                   year=0, mmdd=0)
print(bk_one)
```

## 返回数据样本

```python
{'880660.SH': {'BK10': ['6705.83', '191.60'], 'BK11': ['6183.65', '176.68'], 'BK12': ['0.00', '0.00'], 'BK13': ['0.00', '0.00'], 'BK9': ['3.00', '31.00']}}
```

