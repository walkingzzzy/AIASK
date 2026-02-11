# 获取指定日期财务数据 get_financial_data_by_date

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10mdt617qss.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取指定日期的专业财务数据，与基础财务数据不同，需要先在客户端中下载专业财务数据。

```python
get_financial_data_by_date(stock_list: List[str] = [],
                           field_list: List[str] = [],
                           year: int = 0,
                           mmdd: int = 0) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空（如 FN193） |
| stock_list | Y | List[str] | 证券代码列表 |
| year | Y | int | 指定年份 |
| mmdd | Y | int | 指定月日 |

**说明**：当year和mmdd默认为0时返回最近一条数据。

## 输出参数

同 get_financial_data 一样。

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

fd = tq.get_financial_data_by_date(
        stock_list=['688318.SH'],
        field_list=['Fn193','Fn194','Fn195','Fn196','Fn197'],
        year=0,
        mmdd=0)
print(fd)
```

## 返回数据样本

```python
{'600519.SH':
{'FN193': '162.47',
'FN194': '69.67',
'FN195': '16.07',
'FN196': '8.71',
'FN197': '25.14'}}
```

