# 取消订阅 unsubscribe_hq

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h112vh7jtsms.html
> 抓取时间: 2026-02-03

## 函数说明

取消订阅股票实时更新。

```python
unsubscribe_hq(stock_list: List[str] = [])
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_list | Y | List[str] | 取消订阅的证券代码列表 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

# 取消订阅
un_sub_res = tq.unsubscribe_hq(stock_list=['688318.SH'])
print(un_sub_res)
```

