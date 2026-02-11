# 发送消息到通达信客户端 send_message

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10rkbndkb0k.html
> 抓取时间: 2026-02-03

## 函数说明

发送消息给通达信客户端的TQ策略界面。

```python
send_message(msg_str: str) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| msg_str | Y | str | 消息字符串 |

**说明**：传入的字符串使用 `|` 可以让客户端将其分为两条（插入 `\n` 也可以分行显示）

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
msg_str = "这是第一行. | 这是第二行. "
tq.send_message(msg_str)
```

