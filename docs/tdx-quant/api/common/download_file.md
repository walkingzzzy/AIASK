# 下载特定数据文件 download_file

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10pqrdlj71o.html
> 抓取时间: 2026-02-03

## 函数说明

下载10大股东数据或ETF申赎数据。

```python
download_file(stock_code: str = '',
              down_time: str = '',
              down_type: int = 1):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 证券代码 |
| down_time | Y | str | 指定时间 |
| down_type | Y | int | 指定下载类型 |

**说明**：
- `down_type=1` 时，下载10大股东数据，`down_time` 只生效年份
- `down_type=2` 时，下载ETF申赎清单，`down_time` 生效到日期
- 下载的文件保存在 `.\PYPlugins\data` 文件夹

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

# 下载10大股东数据
down_ptr_10 = tq.download_file(stock_code='688318.SH', down_time='20250101', down_type=1)
print(down_ptr_10)

# 下载ETF申赎数据
dowm_ptr_etf = tq.download_file(stock_code='159109.SH', down_time='20250101', down_type=2)
print(dowm_ptr_etf)
```

## 返回数据样本

```python
# 10大股东数据
{
   "ErrorId": "0",
   "Msg": "下载十大股东数据[2025]成功。",
   "run_id": "1"
}

# ETF申赎数据
{
   "ErrorId": "0",
   "Msg": "下载ETF申述清单[20250101]成功。",
   "run_id": "1"
}
```

