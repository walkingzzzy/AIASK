# 获取板块交易数据 get_bkjy_value

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10p0ncmp5mc.html
> 抓取时间: 2026-02-03

## 函数说明

根据板块代码，获取指定时间段内的板块交易数据，需要先在客户端中下载股票数据包。

```python
get_bkjy_value(stock_list: List[str] = [],
               field_list: List[str] = [],
               start_time: str = '',
               end_time: str = '') -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空 |
| stock_list | Y | List[str] | 证券代码列表 |
| start_time | N | str | 起始时间 |
| end_time | N | str | 结束时间 |

## 输出字段

| 字段 | 说明 |
|------|------|
| BK5 | 市盈率TTM 整体法 算术平均 |
| BK6 | 市净率MRQ 整体法 算术平均 |
| BK7 | 市销率TTM 整体法 算术平均 |
| BK8 | 市现率TTM 整体法 算术平均 |
| BK9 | 涨跌数 上涨家数 下跌家数 |
| BK10 | 板块总市值(亿元) 整体法 算术平均 |
| BK11 | 板块流通市值(亿元) 整体法 算术平均 |
| BK12 | 涨停数 涨停家数 曾涨停家数 |
| BK13 | 跌停数 跌停家数 曾跌停家数 |
| BK14 | 涨停数据 市场高度 2板及以上涨停个数 |
| BK15 | 融资融券 沪深京融资余额(万元) 沪深京融券余额(万元) |
| BK16 | 陆股通资金流入 沪股通流入金额(亿元) 深股通流入金额(亿元) |
| BK17 | 开盘成交数 开盘成交额(万元) 开盘成交量(万股) |
| BK18 | 板块股息率(%) 算数平均 整体法 |
| BK19 | 板块自由流通市值(亿元) 整体法 算术平均 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

bk_data = tq.get_bkjy_value(stock_list=['880660.SH'],
        field_list=['BK5','BK6','BK7','BK8','BK9'],
        start_time='20250101',
        end_time='20250102')
print(bk_data)
```

## 返回数据样本

```python
{'880660.SH': {'BK5': [{'Date': '20250102', 'Value': ['55.28', '55.50']}],
'BK6': [{'Date': '20250102', 'Value': ['4.62', '3.79']}],
'BK7': [{'Date': '20250102', 'Value': ['5.25', '8.22']}],
'BK8': [{'Date': '20250102', 'Value': ['46.52', '312.41']}],
'BK9': [{'Date': '20250102', 'Value': ['0.00', '35.00']}]}}
```

