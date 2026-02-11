# 获取A股板块代码列表 get_sector_list

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r5907noko.html
> 抓取时间: 2026-02-03

## 函数说明

获取A股全部板块代码列表。

```python
get_sector_list() -> List:
```

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
block_list = tq.get_sector_list()
print(block_list)
```

## 返回数据样本

```python
['880081.SH', '880082.SH', '880201.SH', '880202.SH', '880203.SH', '880204.SH', '880205.SH', '880206.SH', '880207.SH', '880208.SH', ...]
```

