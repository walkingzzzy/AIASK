# 获得订阅列表 get_subscribe_hq_stock_list

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h1137r4k2mas.html
> 抓取时间: 2026-02-03

## 函数说明

获得当前策略订阅的股票列表。

```python
get_subscribe_hq_stock_list():
```

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

sub_list = tq.get_subscribe_hq_stock_list()
print(sub_list)
```

## 返回数据样本

```python
['600519.SH']
```

