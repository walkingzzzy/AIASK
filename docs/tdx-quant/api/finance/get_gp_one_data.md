# 获取股票的单个数据 get_gp_one_data

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10pk3rsg044.html
> 抓取时间: 2026-02-03

## 函数说明

根据证券代码，获取股票的单个数据，需要先在客户端中下载股票数据包。

```python
get_gp_one_data(stock_list: List[str] = [],
                field_list: List[str] = []) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空（如 GO47表示第47号个股数据） |
| stock_list | Y | List[str] | 证券代码列表 |

## 主要输出字段

| 字段 | 说明 |
|------|------|
| GO1 | 发行价(元) |
| GO2 | 总发行数量(万股) |
| GO3 | 一致预期目标价(元) |
| GO4 | 一致预期T年度 |
| GO5 | 一致预期T年每股收益 |
| GO6 | 一致预期T+1年每股收益 |
| GO7 | 一致预期T+2年每股收益 |
| GO8 | 一致预期T年净利润(万元) |
| GO26 | 最新解禁日(YYMMDD格式) |
| GO27 | 最新解禁数量（万股） |
| GO28 | 下一报告期的预约披露时间 |
| GO29 | 最新持股机构家数 |
| GO30 | 最新机构持股总量（万股） |
| GO33 | 最新总股本（万股） |
| GO34 | 最新实际流通A股（万股） |
| GO35 | 最新业绩预告 报告期 |
| GO36 | 最新业绩预告 本期归母净利润下限（万元） |
| GO37 | 最新业绩预告 本期归母净利润上限（万元） |
| GO42 | 分红募资 派现总额（万元） |
| GO43 | 分红募资 募资总额（万元） |

> 完整字段列表请参考官方文档，共支持GO1-GO47等数十个个股指标

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

go = tq.get_gp_one_data(stock_list=['688318.SH'], field_list=['GO1','GO2','GO3','GO4','GO5'])
print(go)
```

## 返回数据样本

```python
{'688318.SH': {'GO1': '107.41', 'GO2': '1667.00', 'GO3': '0.00', 'GO4': '2025.00', 'GO5': '1.74'}}
```

