# 初始化 initialize

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1cv85e8u9nb0c.html
> 抓取时间: 2026-02-03

## 函数说明

所有策略连接通达信客户端都必须调用此函数进行初始化。

```python
initialize(__file__)
```

**注意**: `"initialize"` 不可修改

## 调用方法

```python
from tqcenter import tq

tq.initialize(__file__)
```

## 注意事项

1. 该函数用于初始化，任何一个策略都必须有该函数。
2. 必须在调用其他tq函数之前先调用此初始化函数。
3. 参数 `__file__` 是Python内置变量，表示当前脚本的文件路径。

