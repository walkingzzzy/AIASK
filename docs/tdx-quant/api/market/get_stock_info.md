# 获取证券基本信息 get_stock_info

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10jj7r7jol4.html
> 抓取时间: 2026-02-03

## 函数说明

根据股票，获取股票基础的财务数据。

```python
get_stock_info(cls,
               stock_code: str, 
               field_list: List = []) -> Dict:
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| field_list | Y | List[str] | 字段筛选，不能为空 |
| stock_code | Y | str | 证券代码 |

## 返回参数

| 参数 | 默认返回 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| Name | Y | str | 证券名称 |
| Unit | Y | str | 交易单位 |
| VolBase | Y | str | 量比的基量 |
| Fz[8] | Y | List[str] | 开收市时间（4段） |
| InitTimer | Y | str | 初始化时间 |
| EndTimer | Y | str | 收盘时间 |
| DelayMin | Y | str | 延时分钟数 |
| BelongHS300 | Y | str | 是否属于沪深300板块 |
| BelongHasKQZ | Y | str | 是否属于可转债板块 |
| BelongRZRQ | Y | str | 是否属于融资融券板块 |
| IsQH | Y | str | 是否属于期货品种 |
| IsHKGP | Y | str | 是否是港股品种 |
| Vol_BaseRate | Y | str | 期货的每手乘数/期权合约单位 |
| MinPrice | Y | str | 最小变动价位 |
| IsQQ | Y | str | 是否是期权品种 |
| ActiveCapital | Y | str | 流通股本 |
| J_start | Y | str | 上市日期 |
| J_addr | Y | str | 所属省份 |
| J_hy | Y | str | 所属行业 |
| J_zgb | Y | str | 总股本 |
| TodayDRFlag | Y | str | 今日除权除息标识(1:分红 2:送转股 3:分红+送转股 4:配股) |
| HSStockKind | Y | str | 沪深品种类型 |
| BelongHSGT | Y | str | 是否属于陆股通板块 |
| IsZS | Y | str | 是否是指数 |
| J_bg | Y | str | B股 |
| J_hg | Y | str | H股 |
| J_zzc | Y | str | 总资产 |
| J_ldzc | Y | str | 流动资产 |
| J_gdzc | Y | str | 固定资产 |
| J_wxzc | Y | str | 无形资产 |
| J_gdrs | Y | str | 股东人数 |
| J_ldfz | Y | str | 流动负债 |
| J_cqfz | Y | str | 少数股东权益 |
| J_zbgjj | Y | str | 资本公积金 |
| J_jzc | Y | str | 股东权益（净资产） |
| J_yysy | Y | str | 营业收入 |
| J_yycb | Y | str | 营业成本 |
| J_yszk | Y | str | 应收账款 |
| J_yyly | Y | str | 营业利润 |
| J_tzsy | Y | str | 投资收益 |
| J_jyxjl | Y | str | 经营现金净流量 |
| J_zxjl | Y | str | 总现金净流量 |
| J_ch | Y | str | 存货 |
| J_lyze | Y | str | 利润总额 |
| J_shly | Y | str | 税后利润 |
| J_jly | Y | str | 净利益 |
| J_wfply | Y | str | 未分配利益 |
| J_jyl | Y | str | 净益率 |
| J_mgwfp | Y | str | 每股未分配 |
| J_mgsy | Y | str | 每股收益（折算为全年） |
| J_mgsy2 | Y | str | 季报每股收益 |
| J_mggjj | Y | str | 每股公积金 |
| J_mgjzc | Y | str | 每股净资产 |
| J_mgjzc2 | Y | str | 季报每股净资产 |
| J_gdqyb | Y | str | 股东权益比 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
fdc = tq.get_stock_info(stock_code='688318.SH', field_list=[])
print(fdc)
```

