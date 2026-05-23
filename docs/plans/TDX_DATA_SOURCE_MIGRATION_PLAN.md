# TDX 数据源切换方案

> 日期：2026-05-18
> 实测客户端：`C:\new_tdx_test`（通达信专业研究版，已登录）
> 实测脚本：[scripts/tdx_probe/probe_tdx_all.py](scripts/tdx_probe/probe_tdx_all.py) + [probe_tdx_deep.py](scripts/tdx_probe/probe_tdx_deep.py)
> 实测结果：[scripts/tdx_probe/result.json](scripts/tdx_probe/result.json) + [result_v2.json](scripts/tdx_probe/result_v2.json)

---

## 1. 背景与动机

仓库当前情况（已通过 grep 验证）：

- [packages/akshare-mcp/src/akshare_mcp/data_source/](packages/akshare-mcp/src/akshare_mcp/data_source/) 里 [tdx_local.py](packages/akshare-mcp/src/akshare_mcp/data_source/tdx_local.py)（vipdoc 文件 + pytdx 公网协议）正在被 `data_source.get_kline / get_realtime_quote / get_trading_dates` 调用，**只覆盖 K 线、报价、交易日历**。
- [tdx_tqcenter.py](packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py) 已经写好但**零调用**：`_get_tqcenter / _tqcenter_get_kline / _tqcenter_get_quote / _tqcenter_get_trading_dates` 在仓库里只在它自己的 import 行出现。
- 22 个 tools 文件直接 `import akshare / tushare / efinance / baostock_client`，绕开 `data_source.*`。
- 财务、龙虎榜、融资融券、北向、大宗交易、可转债、新股、板块统计、涨停盘中字段……**全部走 Tushare/AKShare**，TDX 既有能力没用上。

实测后修正之前误判：TDX **绝大多数能力都有**，只是没接进项目。本方案的目标是把项目接到 TDX。

---

## 2. TDX 实测能力总览

下表是从 [scripts/tdx_probe/result.json](scripts/tdx_probe/result.json) 和 [result_v2.json](scripts/tdx_probe/result_v2.json) 直接读出的事实，不是从文档推断。

### 2.1 已经"开箱即用"的接口（拿到真值）

| 接口 | 实测样本（来源） | 用途 |
|---|---|---|
| `tq.get_market_data` | 600519 日线 5 行 9 字段；周线 / 5min 都通；返回 `{field: DataFrame[stock×time]}` | 替代 ak/ts/baostock/efinance K 线 |
| `tq.get_market_snapshot` | 26 字段，含五档盘口、内外盘、3 日涨幅、均价 | 替代实时报价 + order_book |
| `tq.get_more_info` | **88 字段**：涨停价/跌停价/换手率/量比/PE_TTM/PB_MRQ/股息率/52周高低/封单额/连板天/年涨停天/最近回购/最近股权激励/最近预告/最近解禁/最近定增/最近龙虎榜/最近停牌日/52周高低 | 替代 daily_basic + 涨停盘中字段 + 估值 |
| `tq.get_stock_info` | 63 字段：名称/上市日 J_start/行业 rs_hyname/总股本/流通股本/资产负债/利润/EPS/BVPS/ROE/HS300/RZRQ/HSGT 标识 | 替代 stock_basic + 基础财务 |
| `tq.get_relation` | 600519 一次拿到 45 个板块（行业/地区/概念/风格/指数）含成分股数 | 替代行业归属查询 |
| `tq.get_divid_factors` | 600519 拿到 12 条历史分红，含派息/送股/配股 | 替代 dividend |
| `tq.get_stock_list('5')` | 全 A 5524；HS300 300；ZZ500 500；ZZ1000 1000；A500 500；ETF 1576；可转债 347；创业板 1398；科创板 610；北交所 316 | 替代 stock_basic + index_weight |
| `tq.get_sector_list` | 586 个板块代码 | 替代板块列表 |
| `tq.get_stock_list_in_sector` | 880xxx 即时返回成分股 | 替代板块成分 |
| `tq.get_ipo_info(2,1)` | 2 条（1 新股 1 新债），含 SGDate/SGPrice/MaxSG/PE_Issue | 替代 ak.stock_xgsglb_em |
| `tq.get_gb_info` | 600519 多日股本（总股本/流通股本） | 替代 daily_basic.total_share |
| `tq.get_trading_dates` | 10 个交易日 YYYYMMDD | 替代 trade_cal |
| `tq.get_kzz_info` | 思创转债 21 字段：转股价/强赎触发价/回售触发价/到期日/评级/剩余规模 | 替代 cb_basic |
| `tq.get_gp_one_data` | 600519 **47 字段全有真值**：目标价 31.39/3 年 EPS 净利润营收 PE 一致预期/解禁/机构持股/业绩预告/业绩快报/派现/募资/披露日 | 替代盈利预测 + 一致预期 |
| `tq.get_gpjy_value` | GP25 等返回真值，含盘前盘后成交量 | 替代龙虎榜 + 融资融券 + 陆股通 + 大宗 + 涨跌停盘中字段（GP1-46）|
| `tq.get_bkjy_value` | BK9/BK12/BK13/BK17 返回真值（涨跌家数 / 涨停家数 / 开盘成交） | 替代板块统计字段 |
| `tq.get_scjy_value_by_date` | SC25 返回真值 | 替代北向/融资融券/龙虎榜市场口径数据（SC1-42）|
| `tq.formula_zb / formula_process_mul_zb` | MACD 多股批量调通 | 替代自实现指标 |
| `tq.download_file(down_type=3/4)` | 舆情文件 + 综合信息文件下载到 `PYPlugins/data/` 落盘成功 | 替代部分新闻/公告（需后续解析）|

### 2.2 实测发现的真问题（需要在方案里处理）

| 问题 | 现象 | 处理 |
|---|---|---|
| **专业财务 `get_financial_data` 全部返 `"--"`** | 600519 取 FN1/FN6/FN197 返回 `"--"` | **通达信"专业财务数据"是付费功能**，未购买/未下载时所有 FN 字段返回 `--`。代码已按此设计：`sync_financial_pro` 默认禁用（`TDX_SYNC_ENABLE_PRO_FIN=0`），财务路径自动降级到 `sync_basic_financial`（基于 `get_stock_info` 的免费基础财务，含 营收/净利润/ROE/EPS/BVPS/资产/负债 等核心字段）。购买后置 `TDX_SYNC_ENABLE_PRO_FIN=1` 启用 |
| **GP/BK/SC 历史范围被忽略** | 传 `start='20240101' end='20241231'` 但只回当天 | 只是少数字段返回，多数字段用 by_date 或最新值；先用 by_date 拿"最新一期"，跨日历史用每日 cron 落库累积 |
| **`get_trackzs_etf_info`** | 6 个常见指数代码全空 | 不阻塞主链路，单独留 §8.3 后续探查 |
| **K 线返回 24000 行硬上限** | 文档明示 | 分钟线分批，日线足够 |
| **客户端必须运行** | tqcenter 强依赖 Windows + 通达信运行 | 用 vipdoc + pytdx 做 fallback |

### 2.3 TDX 真没有的（保留外部源）

实测后能确定 TDX 不直接给的：
1. **新闻/研报正文**（download_file 给的是文件不是结构化）
2. **ETF 期权链行情**（SDK 有期权下单常量但没 chain 接口，待 §8.4 探查）
3. **部分宏观指标的最新一期更新**（HG 系列代码体系待确认）

这三类保留 ak/ts，**其余全部切到 TDX**。

---

## 3. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│  tools/* (200+ 文件)                                        │
│  禁止直接 import akshare/tushare/efinance/baostock          │
│  统一调用 data_source.<method>                              │
└──────────────────────┬─────────────────────────────────────┘
                       │
         ┌─────────────▼──────────────┐
         │  data_source/__init__.py   │
         │  DataSourceManager 单例     │
         │  对外契约不变               │
         └──────┬──────────┬──────────┘
                │          │
   ┌────────────▼──┐   ┌───▼─────────────┐
   │ tdx_tqcenter  │   │ tdx_local        │
   │  主路径        │◄──│  fallback        │
   │ (新增 12 个    │   │ vipdoc + pytdx   │
   │  数据方法)     │   │  覆盖 K线/快照/  │
   └───────────────┘   │  交易日历         │
                       └──────────────────┘

   外部源（ak/ts/...）只在 3 类边界保留：
   - news / research（download_file 落盘文件 + ak 兜底）
   - options（期权链）
   - macro（HG 不全的指标）
```

**核心原则**：

1. **改适配器，不改业务**：tools 层 200+ 文件继续 `from ..data_source import data_source`；只把 `data_source.*` 内部实现切到 TDX。这样改动最小、回滚最容易。
2. **tqcenter 主，vipdoc/pytdx 兜底**：客户端开着时全功能；客户端没开或 Linux 部署时 K 线/快照/交易日历继续可用。
3. **ak/ts 只保留 3 类边界**：news / options / macro_HG_missing，且必须在文件头注释里写明"为什么没法用 TDX"。
4. **DB 是真相**：所有时序数据先入库再消费，不在线计算。新增 7 张表承接 TDX 的 GP/BK/SC/财务/IPO/CB/股本数据。

---

## 4. 改造分阶段

总共三阶段，每个阶段独立可发布、独立可回滚。

### Phase 1 — 适配层挂线（D1-D3，必须先做）

**1.1 让 tdx_tqcenter 真正生效**

文件 [packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py](packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py)：

- 把现有 `get_kline / get_realtime_quote / get_stock_list / get_stock_info / get_financial_data / get_gpjy_value / get_scjy_value / get_sector_list / get_stock_list_in_sector / get_trading_dates` 修正基于实测：
  - K 线：用 `tq.get_market_data` 返回的 `{field: DataFrame}` 真实结构（**index = date** 当 stock_list 长度 = 1 时；index = stock 当 stock_list > 1 时；现有代码两条分支都对，但 `_normalize_code` 北交所要从 `4/8` 改成实测看到的 `920xxx → .BJ` 的真实规则）
  - 快照：拼接 `get_market_snapshot` + `get_more_info` 共 88+26 字段，把 `preClose / change / changePercent / volume / amount / pe_ttm / pb / market_cap / 涨停价 / 跌停价 / 换手率 / 量比 / 总市值 / 流通市值 / 五档盘口` 全部填上
- **新增** 12 个方法（之前缺）：
  - `get_more_info(code)` — 88 字段封装
  - `get_relation(code)` — 行业归属
  - `get_divid_factors(code, start, end)` — 分红
  - `get_ipo_info(ipo_type, ipo_date)` — 新股新债
  - `get_gb_info(code, dates)` — 股本
  - `get_kzz_info(code)` — 可转债基础
  - `get_gp_one_data(codes, fields)` — 盈利预测/一致预期
  - `get_gpjy_value(codes, fields, start, end)` — 个股交易（已存在，验证）
  - `get_bkjy_value(blocks, fields, start, end)` — 板块统计（新增）
  - `get_scjy_value(fields, start, end)` — 市场交易（已存在，验证）
  - `get_financial_data(codes, fns, start, end)` — 专业财务（已存在，验证）
  - `formula_process_mul_zb(name, args, codes, period, count)` — 批量公式（新增）
  - `download_file(code, time, type)` — 文件下载（新增，对应文档里 down_type=1/2/3/4）

**1.2 改造 data_source/__init__.py 让 tqcenter 真正进入主路径**

[packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py](packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py) 第 28 行的 alias 写好但没人调。改 [quotes.py](packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py) 和 [market_data.py](packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py) 优先级：

```
get_kline:        DB → tdx_tqcenter → tdx_local(vipdoc) → tdx_local(pytdx) → 空
get_realtime_quote: tdx_tqcenter → tdx_local(pytdx) → tdx_local(snapshot) → 空
get_trading_dates:  tdx_tqcenter → tdx_local → 空
```

**TDX_LOCAL_ONLY=1** 的语义改为"全链路只用 TDX 任一来源（tqcenter 或 vipdoc/pytdx）"；不再降级 ak/ts。

**1.3 加 12 个新方法到 DataSourceManager**

通过 Mixin 加：[market_data.py](packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py) 已有 `get_ipo_info / get_cb_info / get_gb_info`，把它们的主路径切到 tqcenter；新增 `get_more_info / get_relation / get_divid_factors / get_gp_one_data / get_gpjy / get_bkjy / get_scjy / get_financial_data / formula_zb_batch / download_tdx_file`。

**1.4 .env 同步**

- 把 [packages/akshare-mcp/.env.example](packages/akshare-mcp/.env.example) 加上根目录 [.env.example](.env.example) 已有的 12 行 `TDX_*`
- `TDX_PYPLUGINS_PATH` 默认 `${TDX_INSTALL_DIR}\PYPlugins\sys`
- 新增 `TDX_TQCENTER_REQUIRED=0` 开关：`0`（默认）= 客户端不在时降级 vipdoc；`1` = 客户端不在直接报错（用于生产强校验）
- 新增 `TDX_DOWNLOAD_DIR=${TDX_INSTALL_DIR}\PYPlugins\data` 用于读 download_file 落地的文件

**Phase 1 验收**：
- 跑 [scripts/tdx_probe/probe_tdx_all.py](scripts/tdx_probe/probe_tdx_all.py) 必须 OK ≥ 35
- `from akshare_mcp.data_source import data_source; data_source.get_kline('600519', 'daily', 5)` 返回 `source='tqcenter'`
- 关闭客户端再跑，返回 `source='tdx_local'` 或 `source='tdx_online'`
- 单测 [tests/test_data_source_tdx_routing.py](packages/akshare-mcp/tests/test_data_source_tdx_routing.py)（新增）验证降级链

### Phase 2 — DB Schema + Sync（D3-D7）

**2.1 新增 7 张表**

走 [packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_schema_market_phase_8.py](packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_schema_market_phase_8.py)（新增）：

| 表名 | 主键 | 关键列 | 来源 |
|---|---|---|---|
| `tdx_financial_pro` | (code, report_date, fn_code) | value REAL, announce_date, updated_at | `get_financial_data` 全 FN |
| `tdx_stock_extra` | (code, trade_date) | 88 字段 + updated_at | `get_more_info` |
| `tdx_consensus` | (code, snapshot_date) | GO1-GO47 各列 | `get_gp_one_data` |
| `tdx_gpjy_daily` | (code, trade_date, gp_code) | value_a, value_b | `get_gpjy_value` |
| `tdx_bkjy_daily` | (block_code, trade_date, bk_code) | value_a, value_b | `get_bkjy_value` |
| `tdx_scjy_daily` | (trade_date, sc_code) | value_a, value_b | `get_scjy_value` |
| `tdx_kzz_basic` | (kzz_code) | 25 字段 + updated_at | `get_kzz_info` |
| `tdx_relation` | (code, block_code) | block_name, block_type, gp_num | `get_relation` |

`stocks` 表加 `tdx_industry / tdx_region / tdx_listed_date` 三列（不破坏旧字段）；`block_stocks` 已存在直接复用。

**2.2 sync 任务接入 tdx_tqcenter**

文件 [packages/akshare-mcp/src/akshare_mcp/services/data_sync_scheduler.py](packages/akshare-mcp/src/akshare_mcp/services/data_sync_scheduler.py) 在每日 15:30 跑：

| 任务 | 接口 | 频率 | 入表 |
|---|---|---|---|
| stock_basic | `get_stock_list('5')` | 每日 | stocks |
| sector_basic | `get_sector_list` + `get_stock_list_in_sector` | 每周 | market_blocks + block_stocks |
| stock_relation | `get_relation` 遍历 stocks | 每周 | tdx_relation |
| daily_kline | `get_market_data('1d', count=5)` 增量 | 每日 | kline_1d |
| daily_more_info | `get_more_info` 遍历 HS300+ZZ500+ZZ1000 | 每日 | tdx_stock_extra |
| daily_gpjy | `get_gpjy_value_by_date` 全市场 | 每日 | tdx_gpjy_daily |
| daily_bkjy | `get_bkjy_value_by_date` 全板块 | 每日 | tdx_bkjy_daily |
| daily_scjy | `get_scjy_value_by_date` | 每日 | tdx_scjy_daily |
| weekly_financial | `get_financial_data` HS300 全市场 | 每周三 | tdx_financial_pro |
| weekly_consensus | `get_gp_one_data` 全市场 | 每周 | tdx_consensus |
| daily_ipo | `get_ipo_info(2,1)` | 每日 | events 表 |
| daily_kzz | `get_kzz_info` 遍历可转债列表 | 每日 | tdx_kzz_basic |
| daily_divid | `get_divid_factors` 增量 | 每日 | events 表 |

**Phase 2 验收**：
- 跑一次 `data_sync_service.run_once()` 后，13 张表都有当日数据
- 数据量校验：HS300 + ZZ500 + ZZ1000 = ~1800 只股票 × 88 字段 → tdx_stock_extra 应有 ≥ 150k 行
- 失败告警：任一任务失败上报到 `sync_tasks.last_error`

### Phase 3 — tools 层切换（D7-D14）

按"路径已通过 data_source"和"绕开 data_source 直 import"两类处理：

**3.1 已经走 data_source.* 的（Phase 1 已自动受益，零改动）**

经 grep 验证，下面这些文件 Phase 1 完成后**自动切到 TDX**，不用动：

- [tools/managers/](packages/akshare-mcp/src/akshare_mcp/tools/managers/) 下的 backtest/quant/screener/watchlist/technical/decision 等大多数 manager
- [tools/basic_data.py](packages/akshare-mcp/src/akshare_mcp/tools/basic_data.py)
- [tools/market/stock_list.py](packages/akshare-mcp/src/akshare_mcp/tools/market/stock_list.py)
- [services/data_sync.py](packages/akshare-mcp/src/akshare_mcp/services/data_sync.py)
- [services/data_sync_scheduler.py](packages/akshare-mcp/src/akshare_mcp/services/data_sync_scheduler.py)
- [services/factor_validation_pipeline.py](packages/akshare-mcp/src/akshare_mcp/services/factor_validation_pipeline.py)

**3.2 必须改的（直 import ak/ts，TDX 有等价能力）**

按改动量从小到大：

| 文件 | 现状 | 改造动作 |
|---|---|---|
| [tools/finance.py](packages/akshare-mcp/src/akshare_mcp/tools/finance.py) | Tushare/AKShare/Baostock 三层财务降级 | 改成 `data_source.get_financial_data(code, [FN6,FN197,FN183,FN210,FN230,FN232,FN184,FN199,FN202,FN160,FN159])` 主路径，AKShare 留作 `TDX_LOCAL_ONLY=0` 时的 enrichment |
| [tools/market/quote.py](packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py) | Sina/Tencent/EM 直 HTTP fallback | 删除 fallback，全部走 `data_source.get_realtime_quote`（已是 TDX）|
| [tools/market/order_book.py](packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py) | ak.stock_bid_ask + Sina/Tencent 直 HTTP | 改用 `data_source.get_realtime_quote` 的 Buyp/Buyv/Sellp/Sellv 五档 |
| [tools/market/limit_up.py](packages/akshare-mcp/src/akshare_mcp/tools/market/limit_up.py) | Tushare stk_limit + ak.stock_zt_pool_em | 改用 `tdx_stock_extra` 表过滤 `FCAmo > 0`（涨停封单额）+ `EverZTCount`（连板天）；AKShare 留作"首封时间/炸板次数"补充（这两个字段确实需要 tick 数据，AKShare 保留有理）|
| [tools/market/helpers.py](packages/akshare-mcp/src/akshare_mcp/tools/market/helpers.py) | Tushare stock_basic + EM push2 | `get_stock_list_cached` 改读 `stocks` 表（来源 tqcenter）；spot 改读 `tdx_stock_extra` 表 |
| [tools/fund_flow.py](packages/akshare-mcp/src/akshare_mcp/tools/fund_flow.py) | Tushare moneyflow + EM | `get_stock_fund_flow` 改读 `tdx_gpjy_daily` GP01-46 子集 |
| [tools/fund_flow_north.py](packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py) | HKEX + EM datacenter | 改读 `tdx_scjy_daily` SC02/SC20/SC42 + `tdx_gpjy_daily` GP06/GP07 |
| [tools/fund_flow_market.py](packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_market.py) | ak.stock_lhb_* / ak.stock_margin_* / EM RPT_DATA_BLOCKTRADE | 改读 `tdx_gpjy_daily` GP02/GP03/GP04/GP08/GP09/GP11-13 + `tdx_scjy_daily` SC11/SC16-19/SC25 |
| [tools/fund_flow_sector.py](packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_sector.py) | EM push2 + Tushare moneyflow_ind | 改读 `tdx_bkjy_daily` BK15/BK16 |
| [tools/market_blocks.py](packages/akshare-mcp/src/akshare_mcp/tools/market_blocks.py) | ak.stock_sector_* + Tushare concept | 改读 `market_blocks` + `block_stocks`（Phase 2 sync 写入）+ `tdx_bkjy_daily` 的 BK5-19 |
| [tools/finance.py:_get_stock_info](packages/akshare-mcp/src/akshare_mcp/tools/finance.py) | Tushare stock_basic + ak.stock_individual_info_em | 改读 `stocks` 表 + `tdx_stock_extra` 字段；`industry` 用 `J_zgb`/`rs_hyname` |
| [tools/valuation_peer.py](packages/akshare-mcp/src/akshare_mcp/tools/valuation_peer.py) | Tushare daily_basic | 改用 `tdx_stock_extra`（含 PE_TTM/PB_MRQ）；历史时间序列由 daily 写入累积 |
| [tools/formula_fallback.py](packages/akshare-mcp/src/akshare_mcp/tools/formula_fallback.py) | ak.stock_zh_a_hist + ak.index_stock_cons_csindex | K 线已是 TDX；HS300 池改用 `data_source.get_stock_list('23')` |

**3.3 保留外部源（TDX 真没有）**

| 文件 | 保留原因 | 标记 |
|---|---|---|
| [tools/news/](packages/akshare-mcp/src/akshare_mcp/tools/news/) | 新闻/公告/研报正文 TDX 只能 download_file 落盘，不是结构化 | 文件头加 `# TDX_NOT_AVAILABLE: news/research full text` |
| [tools/options.py](packages/akshare-mcp/src/akshare_mcp/tools/options.py) | ETF 期权链 TDX SDK 无 list 接口 | 同上 |
| [tools/macro.py](packages/akshare-mcp/src/akshare_mcp/tools/macro.py) | TDX HG 代码体系不完整，待 §8.2 补 | 同上 |

后续做 §8 探查后，新闻/options/macro 中能切到 TDX 的字段再切。

**Phase 3 验收**：
- `grep -rn "import akshare\|import tushare\|import efinance" packages/akshare-mcp/src/akshare_mcp/tools/ | grep -v news/ | grep -v options.py | grep -v macro.py | wc -l` = 0
- E2E：取 600519 的 quote / kline / financials / fund_flow / dragon_tiger 全跑通且 source 字段全部含 `tdx_*`

---

## 5. 关键文件清单

### 5.1 新增

```
packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_schema_market_phase_8.py   # 7 张表
packages/akshare-mcp/tests/test_data_source_tdx_routing.py                       # 降级链单测
packages/akshare-mcp/tests/test_tdx_tqcenter_methods.py                          # 12 个方法契约测试（mock tqcenter）
packages/akshare-mcp/tests/fixtures/tdx_responses.json                           # 实测固化的样本（用 result.json 派生）
scripts/tdx_probe/probe_tdx_all.py            # 已写
scripts/tdx_probe/probe_tdx_deep.py           # 已写
scripts/tdx_probe/result.json                 # 已生成
scripts/tdx_probe/result_v2.json              # 已生成
scripts/sync_tdx_full.py                      # 一次性全量回填脚本
```

### 5.2 改造

```
packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py                 # 12 个方法 + 修正 _normalize_code
packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py                     # alias 真正接入
packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py                       # 优先级：tdx_tqcenter > tdx_local
packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py                  # 主路径切到 tqcenter
packages/akshare-mcp/src/akshare_mcp/services/data_sync_scheduler.py             # 13 个 sync 任务
packages/akshare-mcp/.env.example                                                # 同步 TDX_*
.env.example                                                                     # 加 TDX_TQCENTER_REQUIRED / TDX_DOWNLOAD_DIR

# Phase 3 切的 13 个 tools 文件（见 §3.2 表）
```

---

## 6. 客户端前置依赖

部署前在通达信客户端做一次：

1. 启动通达信专业研究版 / 量化模拟版（`C:\new_tdx_test\tdxw.exe`）
2. **盘后数据下载** 里勾选并下载完成：
   - 上证指数 (999999) 盘后数据 — 交易日历依赖
   - **股票数据包**（免费） — `get_gpjy_value / get_bkjy_value / get_scjy_value` 依赖
   - 沪深 A 股、ETF、可转债
3. 保持客户端**登录状态**（`tq.initialize` 会校验）
4. 在 `C:\new_tdx_test\PYPlugins\user\` 下放一个 `aiask_init.py`（可选），让管理员能在客户端策略管理器里启动一个常驻策略
5. 关闭杀毒软件对 `C:\new_tdx_test\PYPlugins\TPythClient.dll` 和 `tdxrpcx64.dll` 的拦截

> **关于专业财务数据**：通达信的"专业财务数据"是**付费订阅**功能，对应 SDK 的 `get_financial_data` 接口。本项目**不依赖**专业财务包：财务字段（营收/净利润/ROE/EPS/BVPS/资产/负债 等）由 `sync_basic_financial` 通过 `get_stock_info` 获取（免费），覆盖大多数业务需求。如已购买专业财务包，设置 `TDX_SYNC_ENABLE_PRO_FIN=1` 启用 FN 字段同步即可。

---

## 7. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 客户端进程崩溃 | tqcenter 调用失败 | 自动降级 tdx_local（vipdoc + pytdx）；K 线/快照/交易日继续可用，财务/GP/SC 类能接受短暂不可用 |
| Linux/容器部署 | tqcenter 不可用 | `TDX_TQCENTER_REQUIRED=0`（默认）+ vipdoc 文件分发到容器；或单开一台 Windows worker 跑 sync，结果写中心 DB |
| 专业财务包未下载 | FN 字段全 `--` | sync 任务里加 sentinel：连续 3 天 FN1 全 `--` 自动告警 |
| 实测发现的"历史范围被忽略" | GP/BK/SC 历史回填困难 | 方案里改用 `_by_date` + 每日累积；冷启动期允许"只有最近 30 天数据" |
| 单一来源风险 | TDX 服务故障 | 保留 tdx_local 作为兜底；新闻/options/macro 保留 ak/ts |
| Phase 1 改动影响范围大 | 业务 bug | 用 feature flag `DATA_SOURCE_TDX_PRIMARY` 控制：默认 `0`（保持现状），Phase 1 PR 合并后线下灰度，验证通过再设 `1` |

回滚方案：每个 Phase 一个 PR；任一 Phase 出问题 `git revert` 即可，下游 Phase 不依赖未合并的上游。

---

## 8. 待探查项（不阻塞主线）

1. **GP/BK/SC 历史范围真问题**：写脚本固定 stock_code，遍历不同 start/end 组合，确认是参数语义还是数据包问题。如果是数据包不全，sync 任务里加 `refresh_kline` 预热
2. **宏观 HG 系列代码**：从通达信客户端"国内宏观"行情里翻代码列表，脚本枚举 280001-289999 之类范围，找出"CPI/PPI/M2/PMI/社融/LPR/RRR/工业增加值/社消零售/进出口/外储/汇率/失业率"的真实代码
3. **`get_trackzs_etf_info` 失败原因**：实测 6 个指数都返空，怀疑入参不是指数代码而是 ETF 代码或别的。试 ETF 反向查
4. **期权链**：测 `tq.get_market_data` 对 `.SHO/.SZO` 后缀代码、`tq.exec_to_tdx('http://www.treeid/...')` 跳期权 T 型链、Dict.md 里的 `OPTION_*` 常量是否对应隐含 list 接口
5. **盈利预测细分字段** GO35-GO47（业绩预告/快报/派现/募资）跨多只股票批量验证
6. **subscribe_hq 实时推送**：测在长进程里订阅 100 只股票的稳定性，决定要不要把 watchlist 改成推送模式

---

## 9. 立即可执行的下一步

1. **你的动作**：在通达信客户端"盘后数据下载"里勾选"专业财务数据"+"股票数据包"，跑一次完整下载（约 10-30 分钟）。
2. **我的动作**（你确认后启动）：
   - 提交 Phase 1 PR：把 [tdx_tqcenter.py](packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py) 12 个方法补齐 + 改造 [quotes.py](packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py) [market_data.py](packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py) [.env.example](packages/akshare-mcp/.env.example)
   - 在你机器上跑一次 `pytest tests/test_data_source_tdx_routing.py` 和 [scripts/tdx_probe/probe_tdx_all.py](scripts/tdx_probe/probe_tdx_all.py) 确认 OK
   - 然后再做 Phase 2（DB schema + sync）和 Phase 3（tools 切换）
3. **同时启动 §8 待探查项**：把 GP/BK/SC 历史范围、HG 代码、ETF 信息这几个并行查清，最迟在 Phase 2 之前补到本方案

---

## 附录 A — TDX FN 编码到项目财务字段的映射

> 来源：实测 `get_financial_data` + 文档 [tdx_quant_docs/TdxQuant.md_mindoc-1h10m001ic888.md](tdx_quant_docs/TdxQuant.md_mindoc-1h10m001ic888.md)

| 项目字段（tools/finance.py） | TDX FN 代码 | 含义 |
|---|---|---|
| revenue | FN230 | 营业收入 |
| netProfit | FN232 | 归母净利润 |
| netProfit_excluding_nonrecurring | FN233 / FN206 | 扣非净利润 |
| eps | FN1 | 基本每股收益 |
| bvps | FN4 | 每股净资产 |
| roe | FN6 / FN197 | 净资产收益率 |
| grossMargin | FN202 | 销售毛利率 |
| netMargin | FN199 | 销售净利率 |
| debtRatio | FN210 | 资产负债率 |
| currentRatio | FN159 | 流动比率 |
| quickRatio | FN160 | 速动比率 |
| revenueGrowth | FN183 | 营业收入增长率 |
| profitGrowth | FN184 | 净利润增长率 |
| operatingCashFlow | FN107 | 经营活动现金流量净额 |
| totalAssets | FN40 | 资产总计 |
| totalLiab | FN63 | 负债合计 |
| equity | FN72 | 所有者权益合计 |
| totalShare | FN238 | 总股本 |
| floatShare | FN239 | 已上市流通A股 |
| ttmRevenue | FN319 | 营业总收入TTM |
| ttmNetProfit | FN308 | 近一年归母净利润 |
| announce_date | announce_time | 公告日期 |
| report_date | tag_time | 报告期 |

## 附录 B — TDX GP/BK/SC 编码到项目数据字段的映射（节选）

> 来源：实测 + 文档 [tdx_quant_docs/TdxQuant.md_mindoc-1h10muc82r55k.md](tdx_quant_docs/TdxQuant.md_mindoc-1h10muc82r55k.md) / [1h10p8op6ia9g.md](tdx_quant_docs/TdxQuant.md_mindoc-1h10p8op6ia9g.md) / [1h10p0ncmp5mc.md](tdx_quant_docs/TdxQuant.md_mindoc-1h10p0ncmp5mc.md)

**个股交易 GP（用于 fund_flow / dragon_tiger / margin / north_holding）**

| 项目场景 | GP 代码 | 含义 |
|---|---|---|
| 股东人数 | GP01 | 户数 |
| 龙虎榜整体 | GP02 | 买入总/卖出总（万） |
| 融资融券 | GP03 GP11 GP12 GP13 GP31 GP32 | 余额/买入额/偿还额/净买入/转融券 |
| 大宗交易 | GP04 | 成交均价/成交额 |
| 增减持 | GP05 GP23 GP26 GP35 | 实际/拟/金额/股数 |
| 陆股通 | GP06 GP07 | 持股量/市场净买入 |
| 龙虎榜机构 | GP08 GP09 GP42 | 买卖方机构数+金额+净额 |
| 机构调研 | GP10 | 近 3 月次数+机构数 |
| 涨停盘中 | GP14 GP15 GP22 GP24 GP38 GP39 GP40 | 封单额/开板次数/封成比/首末次涨停时间/年统计 |
| 跌停盘中 | GP33 GP34 | 封单额/开板次数/首末次跌停时间 |
| 总市值 | GP16 | 万元 |
| 龙虎榜营业部 | GP17 | 买卖额 |
| 龙虎榜沪深股通 | GP18 | 买卖额 |
| 股票质押 | GP19 GP20 | 质押数+比例 |
| 股息率 | GP21 | % |
| 盘前盘后成交 | GP25 | 开盘量+盘后固定量 |
| 人气排名 | GP27 | 市场+行业 |
| 股票回购 | GP28 | 回购均价+数量 |
| 复牌/更名 | GP29 | 标识 |
| 分红送转 | GP30 | 派息+送转 |
| 竞价涨停买 | GP36 | 万元 |
| 配股 | GP41 GP43 | 登记日+实施 |
| 股票评分 | GP44 GP45 | 综合分+评级系数 |
| 询价转让 | GP46 | 股数+占比 |

**市场交易 SC（用于 north_market / margin_market / lhb_market / etf_market）**

| 项目场景 | SC 代码 | 含义 |
|---|---|---|
| 融资融券市场 | SC01 SC25 SC37 | 余额/买入额/转融券 |
| 北向资金 | SC02 SC20 SC40 SC42 | 流入/净买入/成交 |
| 涨跌停统计 | SC03 SC04 SC15 SC23 SC24 SC30 SC33 SC35 SC36 | 个数/连板/封单 |
| 股指期货 | SC05 SC06 SC07 SC41 | 净持仓 |
| ETF | SC08 SC38 | 规模份额+金额 |
| 增减持市场 | SC10 | 总额 |
| 大宗交易市场 | SC11 | 溢价折价 |
| 限售解禁 | SC12 | 计划+实际 |
| 分红 | SC13 | 总额 |
| 募资 | SC14 | 总额 |
| 龙虎榜 | SC16 SC17 SC18 SC19 | 总+机构+营业部+沪深股通 |
| 股票质押市场 | SC21 SC22 SC26 | 质押率 |
| 央行投放 | SC27 | 净投放 |
| 新高新低 | SC28 SC29 SC32 SC39 | 历史/120/20 天/5%涨跌 |
| 涨跌家数 | SC31 SC34 | 含成交量 |

**板块统计 BK（用于 market_blocks / fund_flow_sector）**

| 项目场景 | BK 代码 | 含义 |
|---|---|---|
| 估值 | BK5 BK6 BK7 BK8 BK18 | PE_TTM / PB_MRQ / PS_TTM / PCF_TTM / 股息率 |
| 涨跌家数 | BK9 BK12 BK13 BK14 | 涨跌/涨停/跌停 |
| 市值 | BK10 BK11 BK19 | 总/流通/自由流通 |
| 融资融券 | BK15 | 板块 |
| 陆股通 | BK16 | 沪/深流入 |
| 开盘成交 | BK17 | 额+量 |

完整字段表见 [tdx_quant_docs/](tdx_quant_docs/) 三个核心 md。
