# 获取专业财务数据 get_financial_data

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取指定时间段内的专业财务数据，与基础财务数据不同，需要先在客户端中下载专业财务数据。

```python
get_financial_data(stock_list: List[str] = [],
                   field_list: List[str] = [],
                   start_time: str = '',
                   end_time: str = '',
                   report_type: str = 'report_time') -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空，字段名须与系统定义一致（如 FN193） |
| stock_list | Y | List[str] | 证券代码列表例如 ["600519.SH"] |
| start_time | Y | str | 起始时间，格式 YYYYMMDD，如 '20250101' |
| end_time | N | str | 结束时间，格式 YYYYMMDD，为空表示无结束限制 |
| report_type | N | str | 按截止日期还是公告日期筛选，可选值：'announce_time'（按公告日期筛选）或 'tag_time'（按报告期筛选） |

## 主要输出字段

| 字段 | 说明 |
|------|------|
| announce_time | 公告日期 |
| tag_time | 报告期 |
| FN1 | 基本每股收益 |
| FN2 | 扣除非经常性损益每股收益 |
| FN3 | 每股未分配利润 |
| FN4 | 每股净资产 |
| FN6 | 净资产收益率 |
| FN193 | 成本费用利润率(%) |
| FN194 | 营业利润率 |
| FN197 | 净资产收益率 |
| FN199 | 销售净利率(%) |
| FN210 | 资产负债率(%) |
| FN230 | 营业收入 |
| FN231 | 营业利润 |
| FN232 | 归属于母公司所有者的净利润 |

> 完整字段列表请参考官方文档，共支持FN1-FN584等数百个财务指标

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

fd = tq.get_financial_data(
        stock_list=['688318.SH'],
        field_list=['Fn193','Fn194','Fn195','Fn196','Fn197'],
        start_time='20250101',
        end_time='',
        report_type='announce_time')
print(fd)
```

## 返回数据样本

```python
{'600519.SH':     FN193  FN194  FN195 FN196  FN197 announce_time  tag_time
0  164.82  70.03  15.76  8.07  36.99      20250403  20241231
1  193.43  73.19  14.16  8.03  10.39      20250430  20250331
2  166.69  70.22  15.60  8.70  19.02      20250813  20250630
3  162.47  69.67  16.07  8.71  25.14      20251030  20250930}
```

