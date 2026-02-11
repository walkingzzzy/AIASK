# 刷新行情缓存 refresh_cache

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10f9145us1g.html
> 抓取时间: 2026-02-03

## 函数说明

刷新行情缓存(最新snapshot和K线数据)。如果不调用，首次取snapshot和K线时系统会自动刷新一次行情。

```python
def refresh_cache(market: str = 'AG', force: bool = False)
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| force | Y | bool | 是否强制刷新 |
| market | Y | str | 指定刷新的市场 |

**说明**：
- `force` 为 `false` 时距离上次刷新不足10分钟则不会刷新，为 `true` 时强制刷新
- `market` 赋值：
  - `'AG'` 表示A股
  - `'HK'` 表示港股
  - `'US'` 表示美股
  - `'QH'` 表示国内期货
  - `'QQ'` 表示股票期权
  - `'NQ'` 表示新三板
  - `'ZZ'` 表示中证和国证指数

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
refresh_cache = tq.refresh_cache()
print(refresh_cache)
```

## 返回数据样本

使用后会在客户端弹出刷新数据的加载界面，加载完成后才会有返回：

```json
{
   "Error" : "Refresh Cache Success.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

