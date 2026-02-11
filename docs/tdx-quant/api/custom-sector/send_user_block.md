# 添加自定义板块成份股 send_user_block

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10sec960u0c.html
> 抓取时间: 2026-02-03

## 函数说明

往指定自定义板块中添加成份股。

```python
send_user_block(block_code: str = '',
                stocks: List[str] = [],
                show: bool = False) -> Dict
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| block_code | Y | str | 自定义板块简称 |
| stocks | Y | List[str] | 添加的自选股 |
| show | N | bool | 客户端是否切换至对应板块界面 |

**说明**：
- `block_code` 为客户端已有的自定义板块简称，如果不存在则无效果
- `block_code` 为空则为添加到临时条件股
- `block_code` 存在时，传入空列表则表示清空该板块所有股票，否则为添加新股票

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
zxg_result = tq.send_user_block(
    block_code='CSBK',
    stocks=["600000.SH", "600004.SH", "000001.SZ", "000002.SZ"]
)
print(zxg_result)
```

## 返回数据样本

```python
{'Error': 'Add User Block Completed', 'ErrorId': '0', 'run_id': '1'}
```

