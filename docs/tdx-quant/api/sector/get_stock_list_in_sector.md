# 获取板块成份股 get_stock_list_in_sector

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r92mchgug.html
> 抓取时间: 2026-02-03

## 函数说明

根据板块代码获取其成份股列表。

```python
get_stock_list_in_sector(block_code: str, block_type: int = 0) -> List
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| block_code | Y | str | 板块代码 |
| block_type | N | int | 板块类型 |

**说明**：
- 获取A股成份股时支持板块名称或板块代码两种方式传入
- `block_type=0` 表示传入板块代码或名称（默认）
- `block_type=1` 表示传入自定义板块简称
- 需要是客户端中预先定义好板块简称
- 不能是"自选股"或"临时条件股"

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

# 通过板块代码获取成份股
block_stocks = tq.get_stock_list_in_sector('880081.SH')
print(block_stocks)
print(len(block_stocks))

# 通过板块名获取成份股
block_stocks = tq.get_stock_list_in_sector('钛金属')
print(block_stocks)
print(len(block_stocks))

# 获取自定义板块成份股
block_stocks = tq.get_stock_list_in_sector('CSBK', block_type=1)
print(block_stocks)
print(len(block_stocks))
```

## 返回数据样本

```python
['159922.SZ', '510500.SH', '512500.SH']
3
['000545.SZ', '000629.SZ', '000635.SZ', ...]
23
['600000.SH', '600004.SH', '600006.SH', '600007.SH', '600008.SH', '600009.SH', '600010.SH']
7
```

