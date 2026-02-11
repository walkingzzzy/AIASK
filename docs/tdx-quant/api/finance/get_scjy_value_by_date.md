# 获取指定日期市场交易数据 get_scjy_value_by_date

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10pe678ta04.html
> 抓取时间: 2026-02-03

## 函数说明

获取指定时间的市场交易数据，需要先在客户端中下载股票数据包。

```python
get_scjy_value_by_date(field_list: List[str] = [],
                       year: int = 0,
                       mmdd: int = 0) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空 |
| year | Y | int | 指定年份 |
| mmdd | Y | int | 指定月日 |

**说明**：当year和mmdd默认为0时返回最近一条数据。

## 输出参数

同 get_scjy_value 一样。

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

sc_one = tq.get_scjy_value_by_date(field_list=['SC6','SC7','SC8','SC9','SC10'], year=0, mmdd=0)
print(sc_one)
```

## 返回数据样本

```python
{'SC10': ['0.00', '181415.13'], 'SC6': ['-30479.00', '0.00'], 'SC7': ['-26449.00', '0.00'], 'SC8': ['31752.86', '84.22'], 'SC9': ['993000.00', '2900.00']}
```

