# 订阅行情 subscribe_hq

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h1104d65vr68.html
> 抓取时间: 2026-02-03

## 函数说明

订阅股票实时更新。

```python
subscribe_hq(stock_list: List[str] = [], callback = None)
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_list | Y | List[str] | 订阅的证券代码 |
| callback | Y | function | 回调函数 |

**说明**：
- 订阅股票更新，传入回调函数
- 订阅的股票有更新时，系统会调用回调函数
- 最多订阅100条
- 回调函数格式定义为 `on_data(datas)`
- datas格式为 `{"Code":"XXXXXX.XX","ErrorId":"0"}`

## 接口使用

```python
from tqcenter import tq
import json

tq.initialize(__file__)

# 回调函数 功能为收到更新后请求最新的report数据
def my_callback_func(data_str):
    print("Callback received data:", data_str)
    code_json = json.loads(data_str)
    print(f"codes = {code_json.get('Code')}")
    report_ptr = tq.get_report_data(code_json.get('Code'))
    print(report_ptr)
    return None

sub_hq = tq.subscribe_hq(stock_list=['688318.SH'], callback=my_callback_func)
print(sub_hq)

# 收到更新时策略需要正在运行
# while True:
#     time.sleep(1)
```

## 返回数据样本

```json
{
   "Error" : "订阅688318.SH更新成功.",
   "ErrorId" : "0",
   "run_id" : "1"
}
```

