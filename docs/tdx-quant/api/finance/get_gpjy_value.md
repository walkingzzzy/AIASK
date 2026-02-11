# 获取股票交易数据 get_gpjy_value

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10muc82r55k.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取指定时间段内的股票交易数据，需要先在客户端中下载股票数据包。

```python
get_gpjy_value(stock_list: List[str] = [],
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

## 主要输出字段

| 字段 | 说明 |
|------|------|
| GP01 | 股东人数 股东户数(户) |
| GP02 | 龙虎榜 买入总计(万元) 卖出总计(万元) |
| GP03 | 融资融券 融资余额(万元) 融券余量(股) |
| GP04 | 大宗交易 成交均价(元) 成交额(万元) |
| GP05 | 增减持 成交均价(元) 变动股数(股) |
| GP06 | 陆股通持股量 持股数量(股) |
| GP07 | 陆股通市场成交净额 陆股通市场净买入(万元) |
| GP15 | 涨跌停 涨跌停状态 封单金额(万元) |
| GP16 | 总市值 总市值(万元) |
| GP21 | 股息率 股息率(%) |

> 完整字段列表请参考官方文档，共支持GP01-GP46等数十个交易指标

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

gp_val = tq.get_gpjy_value(
        stock_list=['688318.SH'],
        field_list=['GP1','GP2','GP3','GP4','GP5'],
        start_time='20250101',
        end_time='20250102')
print(gp_val)
```

## 返回数据样本

```python
{'688318.SH': {'GP3': [{'Date': '20250102', 'Value': ['141405.89', '11113.00']}]}}
```

