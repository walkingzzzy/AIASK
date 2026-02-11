# 获取股票更多信息 get_more_info

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3rtq1hij0ac.html
> 抓取时间: 2026-02-03

## 函数说明

获取指定股票更细节的信息。

```python
def get_more_info(stock_code: str = ''):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| stock_code | Y | str | 股票代码 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
more_info = tq.get_more_info(stock_code='688318.SH')
print(more_info)
```

## 返回数据样本

返回包含大量股票详细信息的字典，主要字段包括：

| 字段 | 说明 |
|------|------|
| Name | 股票名称 |
| HqDate | 行情日期 |
| HisHigh | 历史最高价 |
| HisLow | 历史最低价 |
| IPO_Price | 发行价 |
| J_Syl | 市盈率 |
| J_ltgb | 流通股本 |
| J_ltsz | 流通市值 |
| J_mgjzc | 每股净资产 |
| J_mgsy | 每股收益 |
| J_zgb | 总股本 |
| J_zsz | 总市值 |
| MA5Value | 5日均线值 |
| MainBusiness | 主营业务 |
| PB_MRQ | 市净率 |
| StaticPE_TTM | 静态市盈率TTM |
| StaffNum | 员工人数 |
| ZAF | 涨幅 |
| ZAFPre5 | 5日涨幅 |
| ZAFPre10 | 10日涨幅 |
| ZAFPre20 | 20日涨幅 |
| ZAFPre60 | 60日涨幅 |
| ZAFYear | 年涨幅 |
| fHSL | 换手率 |
| rs_hyname | 研究行业名称 |
| tdx_hyname | 通达信行业名称 |
| tdx_dyname | 地域板块名称 |

