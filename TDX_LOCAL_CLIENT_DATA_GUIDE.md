# 通达信本地客户端数据获取说明

> 生成日期：2026-05-20  
> 实测环境：Windows，本地通达信客户端 `C:\new_tdx_test\tdxw.exe` 已运行  
> SDK 文件：`C:\new_tdx_test\PYPlugins\sys\tqcenter.py`  
> 深度实测脚本：`scripts/tdx_probe/probe_tdx_data_quality.py`  
> 实测结果：`scripts/tdx_probe/data_quality_result.json`、`scripts/tdx_probe/data_quality_report.md`

本文档说明当前项目通过通达信本地客户端实际能获取到哪些数据、哪些数据目前为空或只有占位符，以及如何调用。

## 1. 基本使用方式

通达信 TdxQuant SDK 需要先把 `PYPlugins/sys` 加到 `sys.path`，并初始化 `tq`。

```python
import sys

TDX_PYPLUGINS = r"C:\new_tdx_test\PYPlugins\sys"
if TDX_PYPLUGINS not in sys.path:
    sys.path.insert(0, TDX_PYPLUGINS)

from tqcenter import tq

tq.initialize(__file__)
```

注意事项：

- 通达信客户端必须正在运行。
- 代码格式必须带市场后缀，例如 `600519.SH`、`000001.SZ`、`920000.BJ`。
- K 线一次最多约 24000 条，完整分钟线需要分批。
- 本机 SDK 当前不支持 `period="tick"`，调用会返回周期错误。
- 专业财务 `FN` 字段当前只有占位符，不能作为真实财务数据使用。

## 2. 当前能拿到真实数据的数据源

### 2.1 交易日历

可获取指定市场的交易日列表。

```python
dates = tq.get_trading_dates(
    market="SH",
    start_time="20240101",
    end_time="",
    count=50,
)
```

实测状态：有真实数据。

### 2.2 证券与板块列表

使用 `get_stock_list(market, list_type=1)` 获取代码和名称。

```python
all_a = tq.get_stock_list("5", list_type=1)
etfs = tq.get_stock_list("31", list_type=1)
convertible_bonds = tq.get_stock_list("32", list_type=1)
```

当前实测可用分类：

| market | 含义 | 实测数量 |
| --- | --- | ---: |
| `0` | 用户自选股 | 1 |
| `5` | 全 A | 5525 |
| `6` | 上证指数成份股 | 2213 |
| `7` | 上证主板 | 1705 |
| `8` | 深证主板 | 1495 |
| `9` | 重点指数 | 100 |
| `10` | 全部板块指数 | 586 |
| `11` | 缺省行业 | 127 |
| `12` | 概念板块 | 269 |
| `13` | 风格板块 | 158 |
| `14` | 地区板块 | 32 |
| `15` | 行业 + 概念 | 396 |
| `16` | 研究行业一级 | 30 |
| `17` | 研究行业二级 | 127 |
| `18` | 研究行业三级 | 344 |
| `21` | 含 H 股 | 189 |
| `22` | 含可转债 | 333 |
| `23` | 沪深300 | 300 |
| `24` | 中证500 | 500 |
| `25` | 中证1000 | 1000 |
| `26` | 国证2000 | 2000 |
| `27` | 中证2000 | 2000 |
| `28` | 中证A500 | 500 |
| `30` | REITs | 87 |
| `31` | ETF | 1578 |
| `32` | 可转债 | 344 |
| `33` | LOF | 465 |
| `34` | 可交易基金 | 2130 |
| `35` | 沪深基金 | 2343 |
| `36` | T+0 基金 | 376 |
| `49` | 金融类企业 | 101 |
| `50` | 沪深 A 股 | 5208 |
| `51` | 创业板 | 1398 |
| `52` | 科创板 | 610 |
| `53` | 北交所 | 317 |

当前为空的分类：

| market | 含义 |
| --- | --- |
| `1` | 持仓股 |
| `91` | ETF 跟踪指数 |
| `92` | 国内期货主力合约 |
| `101` | 国内期货 |
| `102` | 港股 |
| `103` | 美股 |

### 2.3 板块列表与成分股

```python
sectors = tq.get_sector_list(list_type=1)
members = tq.get_stock_list_in_sector("881002.SH")
```

实测状态：

- `get_sector_list` 有真实数据。
- `get_stock_list_in_sector` 有真实数据。

### 2.4 K 线行情

`get_market_data` 是历史行情主入口，返回结构为 `{字段名: pandas.DataFrame}`。

```python
kline = tq.get_market_data(
    field_list=["Open", "High", "Low", "Close", "Volume", "Amount"],
    stock_list=["600519.SH", "000001.SZ"],
    period="1d",
    start_time="",
    end_time="",
    count=20,
    dividend_type="front",
    fill_data=True,
)

close_df = kline["Close"]
```

当前实测有真实数据的品种：

- A 股：`600519.SH`、`000001.SZ`
- 北交所：`920000.BJ`
- 指数：`999999.SH`、`399001.SZ`
- ETF：`510300.SH`
- 可转债：`123054.SZ`
- 板块指数：`881001.SH`

当前实测有真实数据的周期：

| period | 含义 |
| --- | --- |
| `1m` | 1 分钟 |
| `5m` | 5 分钟 |
| `15m` | 15 分钟 |
| `30m` | 30 分钟 |
| `1h` | 1 小时 |
| `1d` | 日线 |
| `1w` | 周线 |
| `1mon` | 月线 |
| `1q` | 季线 |
| `1y` | 年线 |

当前不支持：

```python
tq.get_market_data(stock_list=["600519.SH"], period="tick", count=20)
```

本机 SDK 返回错误：`period="tick"` 不在支持周期列表中。

### 2.5 实时快照

```python
snapshot = tq.get_market_snapshot("600519.SH", field_list=[])
```

实测对股票、北交所、指数、ETF、板块都有真实数据。

常用字段包括：

- `LastClose`：昨收
- `Open`：开盘价
- `Max` / `Min`：最高/最低
- `Now`：现价
- `Volume`：成交量
- `Amount`：成交额
- `Buyp` / `Buyv`：五档买价/买量
- `Sellp` / `Sellv`：五档卖价/卖量
- `Inside` / `Outside`：内外盘
- `Average`：均价
- `Zangsu`：涨速

### 2.6 更多行情与估值信息

```python
info = tq.get_more_info("600519.SH", field_list=[])
```

实测对股票、北交所、指数、ETF、板块都有真实数据。

常用字段包括：

- 涨跌停：`ZTPrice`、`DTPrice`
- 行情日期：`HqDate`
- 换手率/量比/委比：`fHSL`、`fLianB`、`Wtb`
- 市值：`Zsz`、`Ltsz`
- 涨幅：`ZAF`、`ZAFPre5`、`ZAFPre20`、`ZAFYear`
- 资金：`Zjl`、`Zjl_HB`
- 估值：`StaticPE_TTM`、`PB_MRQ`、`DYRatio`
- 涨停统计：`FCAmo`、`EverZTCount`、`YearZTDay`
- 价格位置：`MA5Value`、`HisHigh`、`HisLow`
- 事件日期：`RecentReleaseDate`、`RecentDZDate`、`TopDate_Recent`

### 2.7 证券基本信息

```python
basic = tq.get_stock_info("600519.SH", field_list=[])
```

实测对股票、北交所、ETF、板块都有真实数据。

常用字段包括：

- `Name`：名称
- `BelongHS300`：是否沪深300
- `BelongRZRQ`：是否融资融券标的
- `BelongHSGT`：是否沪深港通
- `IsSTGP`：是否 ST
- `J_start`：上市日期
- `tdx_dyname`：地区
- `rs_hyname`：行业
- `J_zgb` / `J_bg` / `J_hg`：股本类字段
- `J_yysy` / `J_jly` / `J_mgsy` / `J_mgjzc`：基础财务摘要

### 2.8 分红、股本、新股申购

分红配送：

```python
divid = tq.get_divid_factors(
    stock_code="600519.SH",
    start_time="20180101",
    end_time="20261231",
)
```

实测股票和 ETF 有真实数据；可转债 `123054.SZ` 分红配送为空。

股本：

```python
gb = tq.get_gb_info(
    stock_code="600519.SH",
    date_list=["20240101", "20250520", "20260520"],
    count=3,
)
```

新股申购：

```python
ipo = tq.get_ipo_info(ipo_type=2, ipo_date=1)
```

实测均有真实数据。

### 2.9 股票所属板块

```python
relation = tq.get_relation("600519.SH")
```

实测 `600519.SH`、`000001.SZ`、`688318.SH`、`920000.BJ` 都能返回真实板块归属。

返回字段包括：

- `BlockCode`
- `BlockName`
- `BlockType`
- `GPNume`

### 2.10 可转债信息

```python
kzz = tq.get_kzz_info("123054.SZ", field_list=[])
```

实测可转债列表和多只可转债详情有真实数据。

常用字段包括：

- `KZZCode`：转债代码
- `HSCode`：正股代码
- `ZGPrice`：转股价
- `CurRate`：票面利率
- `RestScope`：剩余规模
- `ForceRedeem`：强赎触发价
- `EndDate`：到期日
- `KZZScore` / `HSScore`：评级
- `RedeemDate` / `RedeemPrice`
- `KZZNow` / `AGNow`

### 2.11 数据文件下载

```python
# 十大股东数据
ret1 = tq.download_file(
    stock_code="600519.SH",
    down_time="20241231",
    down_type=1,
)

# 最新舆情信息
ret2 = tq.download_file(
    stock_code="600519.SH",
    down_time="",
    down_type=3,
)

# 股票综合信息
ret3 = tq.download_file(
    stock_code="600519.SH",
    down_time="",
    down_type=4,
)
```

实测 `down_type=1/3/4` 均返回成功。文件会落到通达信 `PYPlugins/data` 目录，后续如要作为结构化数据源，还需要解析落盘文件。

### 2.12 通达信公式

单股公式：

```python
tq.formula_set_data_info(
    stock_code="600519.SH",
    stock_period="1d",
    count=60,
    dividend_type=1,
)

macd = tq.formula_zb("MACD", "12,26,9", xsflag=6)
xg = tq.formula_xg("UPN", "3")
exp = tq.formula_exp("CCI", "12")
```

批量公式：

```python
stocks = ["600519.SH", "000001.SZ", "688318.SH"]

macd_many = tq.formula_process_mul_zb(
    formula_name="MACD",
    formula_arg="12,26,9",
    return_count=3,
    return_date=True,
    stock_list=stocks,
    stock_period="1d",
    count=60,
    dividend_type=1,
)

upn_many = tq.formula_process_mul_xg(
    formula_name="UPN",
    formula_arg="3",
    return_count=3,
    return_date=True,
    stock_list=stocks,
    stock_period="1d",
    count=60,
    dividend_type=1,
)
```

实测 `MACD`、`CCI`、`UPN` 以及批量指标/选股公式都有真实数据。

## 3. 当前部分可用的数据

### 3.1 GO 一致预期/个股单项数据

```python
fields = [f"GO{i}" for i in range(1, 48)]
go = tq.get_gp_one_data(
    stock_list=["600519.SH"],
    field_list=fields,
)
```

实测结果：

- 真实数据字段：33 个
- 全零字段：14 个

有真实数据的字段：

```text
GO1, GO2, GO3, GO4, GO5, GO6, GO7, GO8, GO9, GO10,
GO11, GO12, GO13, GO14, GO15, GO16, GO17, GO18, GO19,
GO20, GO21, GO22, GO23, GO24, GO25, GO29, GO30, GO31,
GO32, GO33, GO34, GO42, GO43
```

全零字段：

```text
GO26, GO27, GO28, GO35, GO36, GO37, GO38, GO39,
GO40, GO41, GO44, GO45, GO46, GO47
```

### 3.2 GP 个股交易特色数据

```python
fields = [f"GP{i:02d}" for i in range(1, 47)]
gp = tq.get_gpjy_value(
    stock_list=["600519.SH"],
    field_list=fields,
    start_time="20240101",
    end_time="",
)
```

当前有真实数据的字段：

```text
GP25, GP36
```

注意：

- `get_gpjy_value_by_date` 当前 `GP01-GP46` 全部是 `--` 占位符。
- 这类字段更适合每日落库累积，不适合作为一次性历史全量来源。

### 3.3 BK 板块交易特色数据

```python
fields = [f"BK{i}" for i in range(5, 20)]
bk = tq.get_bkjy_value(
    stock_list=["881002.SH"],
    field_list=fields,
    start_time="20240101",
    end_time="",
)
```

当前有真实数据的字段：

```text
BK9, BK12, BK13, BK17
```

注意：

- `get_bkjy_value_by_date` 当前 `BK5-BK19` 全部是 `--` 占位符。

### 3.4 SC 市场交易特色数据

```python
fields = [f"SC{i:02d}" for i in range(1, 43)]
sc = tq.get_scjy_value(
    field_list=fields,
    start_time="20240101",
    end_time="",
)
```

当前有真实数据的字段：

```text
SC25, SC36
```

注意：

- `get_scjy_value_by_date` 当前 `SC01-SC42` 全部是 `--` 占位符。

## 4. 当前为空或不可用的数据

### 4.1 专业财务 FN 字段

```python
fields = [f"FN{i}" for i in range(1, 585)]

fn = tq.get_financial_data_by_date(
    stock_list=["600519.SH"],
    field_list=fields,
    year=0,
    mmdd=0,
)
```

当前结果：

- `FN1-FN584` 全部是 `--` 占位符。
- `get_financial_data` 历史接口返回空。

结论：

- 当前本机通达信客户端没有可用的专业财务数据包。
- 项目内不能把 FN 字段作为真实财务来源。
- 可以使用 `get_stock_info` 中的基础财务摘要字段作为免费替代，专业财务需要外部源或补齐通达信专业财务数据包。

### 4.2 跟踪指数 ETF 信息

```python
etfs = tq.get_trackzs_etf_info("000300.SH")
```

实测以下代码均为空：

```text
000300.SH, 000016.SH, 000905.SH, 000852.SH, 881001.SH, 950162.CSI
```

### 4.3 宏观 HG 数据

```python
macro = tq.get_market_data(
    field_list=[],
    stock_list=["280002.HG"],
    period="1mon",
    start_time="20200101",
    end_time="",
    count=60,
    dividend_type="none",
    fill_data=True,
)
```

实测以下样例为空：

```text
280002.HG, 280001.HG, 880001.HG
```

### 4.4 港股、美股、期货列表

当前为空：

```text
market=92   国内期货主力合约
market=101  国内期货
market=102  港股
market=103  美股
```

### 4.5 Tick 数据

虽然文档常量里出现 `tick`，但当前本机 `tqcenter.py` 的 `get_market_data` 不支持。

```python
tick = tq.get_market_data(
    stock_list=["600519.SH"],
    period="tick",
    count=20,
)
```

返回错误：

```text
周期格式错误：tick
支持 ['5m', '15m', '30m', '1h', '1d', '1w', '1mon', '1m', '10m', '45d', '1q', '1y']
```

### 4.6 当前自选/订阅/持仓相关空数据

当前为空：

- `get_stock_list("1")`：持仓股列表
- `get_user_sector()`：用户自定义板块列表
- `get_subscribe_hq_stock_list()`：当前订阅列表

这不代表接口不可用，只代表当前客户端状态下没有对应数据。

## 5. 未执行的接口

以下接口有副作用，本次数据源测试未执行：

- 下单/撤单：`order_stock`、`cancel_order_stock`
- 自定义板块写入：`create_sector`、`delete_sector`、`rename_sector`、`clear_sector`、`send_user_block`
- 客户端交互：`send_message`、`send_warn`、`send_file`、`send_bt_data`、`print_to_tdx`、`exec_to_tdx`
- 缓存/订阅：`refresh_cache`、`refresh_kline`、`subscribe_hq`、`unsubscribe_hq`

账户读取接口未执行：

- `stock_account`
- `query_stock_asset`
- `query_stock_orders`
- `query_stock_positions`

原因：未设置 `TDX_PROBE_ACCOUNT`，为避免暴露账户信息，默认不跑交易账户读取。

## 6. 本机 SDK 中未实现但文档提到的接口

以下接口在文档或示例中出现，但当前 `C:\new_tdx_test\PYPlugins\sys\tqcenter.py` 没有实现：

```text
get_full_tick
get_real_time_data
get_report_data
get_gb_info_by_date
get_benchmark_data
get_valid_stock_codes
```

## 7. 复测命令

深度质量测试：

```powershell
F:\Python311\python.exe scripts\tdx_probe\probe_tdx_data_quality.py
```

文档驱动全量接口测试：

```powershell
F:\Python311\python.exe scripts\tdx_probe\probe_tdx_docs_full.py
```

输出文件：

```text
scripts/tdx_probe/data_quality_result.json
scripts/tdx_probe/data_quality_report.md
scripts/tdx_probe/docs_full_result.json
scripts/tdx_probe/docs_full_report.md
```

如果要测试账户读取接口，需要临时设置账户环境变量：

```powershell
$env:TDX_PROBE_ACCOUNT="你的资金账号"
$env:TDX_PROBE_ACCOUNT_TYPE="STOCK"
F:\Python311\python.exe scripts\tdx_probe\probe_tdx_data_quality.py
```

不要在仓库文件中保存真实资金账号。

## 8. 项目接入建议

当前可作为项目主数据源的数据：

- 交易日历
- 证券列表和板块成分
- 股票/指数/ETF/可转债/板块 K 线
- 快照和扩展行情
- 基础信息和基础财务摘要
- 分红、股本、新股申购
- 板块归属
- 可转债基础信息
- 通达信公式计算
- 部分 GO/GP/BK/SC 特色字段

当前需要外部源补充的数据：

- 专业财务 FN 字段
- 港股/美股/期货列表和行情
- 宏观 HG 数据
- ETF 跟踪指数映射
- Tick/逐笔数据
- 结构化新闻、研报、公告正文
- 完整北向、融资融券、龙虎榜、大宗交易等历史数据

