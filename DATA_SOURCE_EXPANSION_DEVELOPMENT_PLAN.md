# 数据源深度审查与扩展开发计划

> 日期：2026-05-21  
> 范围：本文件是数据源能力审查和后续开发计划，不代表代码已经改造完成。  
> 本轮约束：只维护根目录 Markdown 文档，不修改 Python 源码、测试、配置、依赖声明、数据库 schema，不执行迁移、同步任务或真实数据写入。

## 1. 总体结论

当前项目的数据源体系已经具备较强的 A 股本地化能力，但真实能力分布并不是“TDX 覆盖全部”。后续扩展必须先把“数据源、资产类型、能力边界、质量状态”显式化，否则 ETF、港股、美股、可转债、指数和板块会继续混在“股票代码”语义里。

核心判断：

- TDX tqcenter 本地客户端是 A 股、ETF、可转债、指数、板块的主数据源，实测能拿到大量真实数据。
- TDX vipdoc/pytdx 是行情和 K 线兜底源，适合做本地日线、分钟线和快照兜底，但当前本地列表函数仍偏 A 股股票过滤。
- Tushare Pro 是可选授权源，适合补充 A 股财务、指数、基金、港股基础信息、宏观等结构化数据，但受 token、权限和白名单限制。
- AKShare 是公共补充源，适合补 ETF 画像、指数、宏观、新闻、港美股只读数据等 TDX 缺口，但当前项目依赖声明不完整，且公共源稳定性需要质量标记。
- eFinance、Baostock、Sina、Tencent、Eastmoney HTTP 当前在工具层作为兜底路径散落存在，应收敛为外部 Provider，而不是继续分散调用。
- SQLite 是本地缓存和回测数据底座，但当前 `kline_1d` 与 `stocks` 表仍偏 A 股，无法清晰表达 ETF、HK、US、指数、可转债等多资产身份。
- 港股和美股不能依赖当前 TDX 本地客户端：`get_stock_list("102")`、`get_stock_list("103")` 实测为空，应通过外部只读 Provider 接入。

## 2. 当前数据源清单

### 2.1 TDX tqcenter 本地客户端

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py`
- `packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py` 中的 `TdxQCenterMixin`

运行依赖：

- Windows 本地通达信客户端正在运行。
- `TDX_INSTALL_DIR` 指向通达信目录，默认形态类似 `C:\new_tdx_test`。
- `TDX_PYPLUGINS_PATH` 指向 `PYPlugins\sys`。
- `TDX_TQCENTER_REQUIRED=1` 时客户端不可用应直接报错；默认应允许 fallback。

已验证真实能力：

- 交易日历：`get_trading_dates`。
- 证券列表：A 股、主板、创业板、科创板、北交所、指数、ETF、REITs、LOF、场内基金、可转债、板块、行业、概念、地区、指数成分。
- K 线：A 股、北交所、指数、ETF、可转债、板块指数。
- K 线周期：`1m`、`5m`、`15m`、`30m`、`1h`、`1d`、`1w`、`1mon`、`1q`、`1y`。
- 实时快照：价格、昨收、开高低、成交量额、五档盘口、内外盘、均价等。
- 扩展行情：涨跌停价、换手率、量比、总市值、流通市值、PE、PB、股息率、52 周高低、封单、连板、近期事件日期等。
- 基础信息：名称、上市日期、行业、地区、股本、基础财务摘要、指数/融资融券/沪深港通标识。
- 企业行为：股票和 ETF 分红、股本、新股/新债申购。
- 板块关系：个股所属行业、地区、概念、风格、指数等。
- 可转债：正股、转股价、剩余规模、强赎/回售触发价、到期日、评级等。
- 公式：单股指标、选股公式、批量指标和批量选股公式。
- 文件下载：十大股东、舆情、综合信息等文件落地成功。

实测为空或不可用：

- 港股列表 `market=102` 为空。
- 美股列表 `market=103` 为空。
- 国内期货 `market=92/101` 为空。
- ETF 跟踪指数 `market=91` 或 `get_trackzs_etf_info` 对常见指数为空。
- 专业财务 FN 字段当前为占位符或空。
- GP/BK/SC 的 by-date 接口多数字段为占位符。
- 宏观 HG 示例代码为空。
- `period="tick"` 返回错误 payload，当前本机 SDK 不支持。

推荐角色：

- 作为中国市场核心主源：A 股、ETF、REITs、LOF、可转债、指数、板块。
- 对港股、美股、期货、宏观、结构化新闻、ETF 跟踪指数不做主源声明。
- 所有输出必须带 `backend_used="tdx_tqcenter"` 与质量状态。

### 2.2 TDX vipdoc 本地文件与 pytdx 在线兜底

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/data_source/tdx_local.py`
- `packages/finance-mcp-servers/src/aiask_finance_mcp/tongdaxin/server.py`

运行依赖：

- 本地 vipdoc 数据文件，或 pytdx 行情服务器。
- pytdx server 地址由相关环境变量或默认服务器列表控制。

已具备能力：

- 日线和分钟 K 线兜底。
- 部分实时行情兜底。
- 交易日历兜底。
- pytdx 版本的分钟、逐笔、财务摘要、市场快照能力在独立 finance MCP server 中存在。

当前限制：

- `tdx_local.list_local_stocks()` 当前明确排除 ETF、可转债、指数、B 股、板块指数。
- pytdx 是行情服务器路径，不等同于 tqcenter 本地客户端的全量能力。
- 港股、美股不应默认认为可用。
- finance MCP server 是独立 MCP 服务，不应被 AKShare MCP 或 Agent 直接 import，需要通过 MCP 聚合或配置接入。

推荐角色：

- 作为 TDX tqcenter 不可用时的行情/K 线兜底。
- 后续新增 `list_local_securities(asset_type=...)`，不要继续把本地证券列表写死为 A 股个股。
- finance MCP server 保持独立服务定位，主要用于外部客户端或 MCP 聚合，不混入 AKShare MCP 内部实现。

### 2.3 Tushare Pro

代码入口：

- `DataSourceManager.get_tushare_pro()`
- `packages/akshare-mcp/src/akshare_mcp/config/tushare_proxy_whitelist.json`
- 多个工具层仍有 Tushare 直接或间接调用。

运行依赖：

- `TUSHARE_TOKEN`
- 可选 `TUSHARE_HTTP_URL`
- `TDX_LOCAL_ONLY=1` 时应跳过。

白名单显示可支持的能力：

- A 股基础：`stock_basic`、`daily`、`weekly`、`monthly`、`daily_basic`、`adj_factor`。
- A 股事件和市场结构：名称变更、股东人数、增减持、质押、回购、概念、概念成分、大宗交易、涨跌停、停牌、沪深港通、龙虎榜、资金流。
- 指数：`index_basic`、`index_daily`、`index_weekly`、`index_monthly`、`index_dailybasic`、`index_classify`、`index_weight`。
- 财务：`income`、`balancesheet`、`cashflow`、`fina_indicator`、`fina_audit`、`fina_mainbz`、`dividend`、`report_rc`。
- 基金：`fund_basic`、`fund_nav`、`fund_manager`、`fund_company`、`fund_portfolio`、`fund_share`。
- 可转债：`cb_basic`、`cb_call`。
- 两融、期货、期权、港股基础、宏观利率和中国宏观指标。

白名单中已知问题：

- `hk_daily` 标记为 `no_permission`。
- `news`、`anns_d` 标记为 `no_permission`。
- `fund_daily`、`cb_daily`、`opt_daily` 等标记为空。
- `fund_adj_factor`、`anns` 标记为不支持。

推荐角色：

- 授权可用时作为结构化数据增强源。
- 对港股 v1 可先使用 `hk_basic` 做基础列表，但 `hk_daily` 不能默认可用，必须按权限探测。
- 对专业财务、基金画像、指数权重、宏观数据可作为 TDX 缺口补充。
- 所有 Tushare 调用必须 lazy-load，不能成为启动硬依赖。

### 2.4 AKShare

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/tools/*` 中多处 `import akshare as ak`。
- `tools/market/kline.py`、`tools/market/quote.py`、`tools/macro.py`、`tools/options.py` 等。

运行依赖：

- 当前代码大量使用 AKShare，但 `packages/akshare-mcp/pyproject.toml` 未把 `akshare` 声明为直接依赖，需要后续修正。
- 受网络、公共接口稳定性和字段变更影响。
- `TDX_LOCAL_ONLY=1` 时不能调用。

适合补充的功能：

- ETF 跟踪指数、基金画像、基金规模份额、基金公司等。
- 港股、美股只读行情和 K 线的公共源 fallback。
- 指数、宏观、新闻、公告、期权、部分资金流和行业数据。
- TDX 没有结构化接口的新闻、研报、公告正文。

当前限制：

- 工具层直接调用较分散，质量元数据不统一。
- 公共源字段常变，必须做字段兼容和质量标记。
- 不能在 local-only 模式下绕过 TDX_LOCAL_ONLY。

推荐角色：

- 作为 `ExternalProvider`，不再散落在工具函数中作为隐式 fallback。
- 用于补 TDX 实测为空的数据域，而不是替代 TDX 已经稳定可取的数据。

### 2.5 eFinance

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py`
- `packages/finance-mcp-servers/src/aiask_finance_mcp/eastmoney/server.py`

运行依赖：

- `efinance` 在 `akshare-mcp` 的 `legacy` optional dependency 中。
- `finance-mcp-servers` 已把 `efinance` 作为依赖。

适合能力：

- A 股行情和历史行情兜底。
- 东方财富相关基金、债券、期货、新闻流能力在独立 Eastmoney MCP server 中已有工具定义。

当前限制：

- 在 AKShare MCP 内部目前是 legacy fallback，不应成为主路径。
- 港股、美股支持能力需单独实测后才能声明。
- 需要超时控制，避免公共接口卡死。

推荐角色：

- 作为可选兜底 Provider。
- 在 `DATA_SOURCE_KEEP_LEGACY_FALLBACK=1` 或显式外部源启用时使用。

### 2.6 Baostock

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/baostock_api.py`
- `data_source/quotes.py`
- `tools/market/kline.py`

适合能力：

- A 股历史日线 K 线。
- 补充换手率、涨跌幅等日线字段。

当前限制：

- 覆盖范围偏 A 股。
- 不适合 ETF/HK/US 主扩展。
- 连接状态和返回字段需要容错。

推荐角色：

- 保留为 A 股历史日线质量兜底。
- 不作为新资产扩展核心源。

### 2.7 Sina、Tencent、Eastmoney HTTP 直连

代码入口：

- `tools/market/quote.py`
- `tools/market/kline.py`
- `tools/market/order_book.py`
- `tools/market/helpers.py`

适合能力：

- 单只或小批量行情兜底。
- 指数行情兜底。
- 分钟线或轻量 K 线兜底。

当前限制：

- 当前以工具内部函数形式散落存在。
- 字段质量、延迟、可用性没有统一 Provider 合约。
- 直接 HTTP fallback 容易绕过统一数据源策略。

推荐角色：

- 收敛为 `external_http_provider`。
- 只在非 local-only 且主源失败时使用。
- 必须统一返回 `backend_used`、`fallback_reason`、`quality_flags`。

### 2.8 SQLite 本地库

代码入口：

- `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/`
- `kline.py`
- `quotes.py`
- `tdx_storage.py`
- `schema_market.py`

现有能力：

- `kline_1d` 存储日线 K 线。
- `stock_quotes` 存储快照行情。
- `stocks` 存储股票基础信息。
- TDX phase-8 表已支持 TDX 扩展数据、可转债、板块关系、GO/GP/BK/SC 等。
- 数据完整性状态可记录到 `tdx_data_completeness`。

当前限制：

- `kline_1d` 主键为 `(time, code)`，不表达 `asset_type/exchange/currency/source_code`。
- `stocks` 表语义偏 A 股股票，不适合直接承载 ETF、港股、美股、指数、板块。
- 同码资产可能冲突，例如指数、ETF、股票在不同市场或来源下代码相近。

推荐角色：

- 继续作为回测和本地缓存底座。
- 扩展统一 `securities` 主数据表，或对 `stocks` 做多资产兼容迁移。
- HK/US v1 只同步 watchlist，不做全市场入库。

## 3. 数据源功能特性详表

本节把每个数据源从“能不能连上”拆成“能拿什么、适合支撑什么项目功能、不能拿什么、如何接入”。后续开发时应优先按本节判断数据源归属，再进入工具层和存储层实现。

### 3.1 TDX tqcenter：本地客户端主源

定位：

- 中国市场主行情源。
- 依赖本机 Windows 通达信客户端和 `PYPlugins/sys/tqcenter.py`。
- 适合支撑项目中的实时行情、K 线、证券列表、ETF、指数、板块、可转债和 TDX 特色字段。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py`
- `packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py` 的 `TdxQCenterMixin`
- 上层间接入口：`data_source.get_realtime_quote()`、`data_source.get_kline()`、`data_source.get_tdx_stock_list()`、`data_source.get_more_info()` 等。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 本地客户端驱动 | 数据来自正在运行的通达信客户端 | 不应把它当成纯文件源或公网 API |
| 中国市场覆盖强 | A 股、ETF、REIT、LOF、场内基金、指数、板块、可转债均有真实样本 | 这些资产应优先走 TDX |
| 行情字段丰富 | 快照、五档盘口、扩展行情、估值、涨跌停、量比、换手等 | quote/order_book/more_info 可用 TDX 合并增强 |
| 周期覆盖广 | `1m/5m/15m/30m/1h/1d/1w/1mon/1q/1y` 实测可用 | K 线 period 白名单应按实测周期维护 |
| 字段质量不均 | FN 财务为空或占位，GP/BK/SC by-date 多占位 | 必须做字段级质量标记，不能一刀切成功 |
| 含副作用 API | 自选股、客户端消息、交易、刷新、订阅等接口存在 | 数据源开发只使用只读接口，交易和写操作另走风控 |

能拿到的真实数据：

| 数据域 | 可用接口或路径 | 典型样本 | 项目功能 |
| --- | --- | --- | --- |
| 交易日历 | `get_trading_dates` | SH 交易日 | 交易日判断、同步窗口、回测日历 |
| A 股列表 | `get_stock_list("5/7/8/50/51/52/53")` | `600519.SH`、`000001.SZ`、`920000.BJ` | 股票池、搜索、同步 universe |
| ETF/基金列表 | `get_stock_list("30/31/33/34/35/36")` | `510300.SH`、`159001.SZ` | ETF/REIT/LOF 接入 |
| 可转债列表 | `get_stock_list("32")` | `123054.SZ` | 可转债行情、转债基础资料 |
| 指数和指数成分 | `get_stock_list("9/23/24/25/26/27/28")` | `999999.SH`、沪深300成分 | 指数行情、指数样本池 |
| 板块/行业/概念 | `get_sector_list`、`get_stock_list("10-18")`、`get_stock_list_in_sector` | `881002.SH` | 板块轮动、主题研究 |
| 历史 K 线 | `get_market_data` | 股票、ETF、指数、可转债、板块 | 技术分析、回测、因子计算 |
| 实时快照 | `get_market_snapshot` | 价格、量额、五档盘口 | 实时看板、盘口、交易信号输入 |
| 扩展行情 | `get_more_info` | 涨跌停、市值、PE、PB、52 周高低 | 风险过滤、估值过滤、涨停分析 |
| 基础信息 | `get_stock_info` | 名称、行业、地区、上市日、股本摘要 | 证券主数据、画像 |
| 分红/股本/IPO | `get_divid_factors`、`get_gb_info`、`get_ipo_info` | A 股和 ETF 分红 | 复权、企业行为、申购日历 |
| 可转债详情 | `get_kzz_info` | 正股、转股价、剩余规模 | 转债分析 |
| 公式数据 | `formula_*` | MACD、CCI、选股公式 | TDX 公式互通、指标校验 |
| 文件下载 | `download_file` | 股东、舆情、综合信息 | 离线文本/文件解析候选 |

拿不到或不能声明可用的数据：

| 数据域 | 实测状态 | 处理策略 |
| --- | --- | --- |
| 港股列表 | `get_stock_list("102")` 为空 | 标记 `empty`，走外部 Provider |
| 美股列表 | `get_stock_list("103")` 为空 | 标记 `empty`，走外部 Provider |
| 期货列表 | `market=92/101` 为空 | 不在本轮扩展中声明 |
| ETF 跟踪指数 | `market=91` 和 `get_trackzs_etf_info` 对样本为空 | ETF profile 走外部源 |
| 专业财务 FN | by-date 占位，history 为空 | 不进入真实财务链路 |
| Tick/逐笔 | `period="tick"` 返回错误 payload | 工具层标记 `unsupported` |
| 文档有但 SDK 缺失 API | `get_full_tick`、`get_real_time_data`、`get_report_data` 等 | 不实现直接调用，需另找路径 |

推荐开发方式：

- `tdx_tqcenter` Provider 暴露能力矩阵，所有空源、占位源、错误 payload 都记录为明确状态。
- ETF、指数、板块、可转债不再通过普通 A 股股票校验硬塞进 `stock_code`。
- TDX 返回成功但字段全空、全 0、`--` 时，返回 `success=false` 或 `success=true + quality_flags=["placeholder_only"]`，具体按功能语义决定。

### 3.2 TDX vipdoc / pytdx：TDX 行情兜底源

定位：

- TDX 本地文件和 pytdx 公网行情服务器的兜底层。
- 适合在 tqcenter 不可用或客户端未启动时补日线、分钟线、部分实时行情。
- 不等价于 tqcenter，覆盖面和字段丰富度明显低于 tqcenter。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/data_source/tdx_local.py`
- `QuotesMixin.get_realtime_quote()` 和 `QuotesMixin.get_kline()` 的第二优先级。
- 独立 `finance-mcp-servers` 中也有 Tongdaxin MCP server，但它是外部 MCP 服务，不应直接 import 到 AKShare MCP。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| vipdoc 零网络 | 读取本地 `.day/.lc1/.lc5` 文件 | 适合离线日线和分钟线缓存 |
| pytdx 可联网兜底 | 可连公网行情服务器 | `TDX_LOCAL_ONLY=1` 下要谨慎，不能误发公网请求 |
| 字段较标准 | OHLCV、amount、部分 quote | 适合 K 线兜底，不适合扩展画像 |
| 列表过滤偏 A 股 | 当前 `list_local_stocks()` 排除 ETF/债券/指数/板块 | 后续必须扩展为 `list_local_securities(asset_type)` |

能支撑的项目功能：

| 功能 | 当前可用性 | 说明 |
| --- | --- | --- |
| A 股日线 K 线 | 可用 | 本地 `.day` 文件优先 |
| A 股分钟 K 线 | 部分可用 | 取决于本地 lc 文件或 pytdx |
| A 股实时行情 | 兜底可用 | 低于 tqcenter 优先级 |
| ETF K 线 | 代码层可扩展 | 当前列表过滤不完整，需按文件和市场目录实测 |
| 港股/美股 | 不声明可用 | 不作为 HK/US 扩展主源 |
| 扩展行情/估值/FN | 不适合 | 字段能力不足 |

推荐开发方式：

- 保持为 `tdx_tqcenter -> tdx_local -> external` 链路中的 TDX 兜底。
- `TDX_LOCAL_ONLY=1` 时允许 vipdoc，本地文件应可用；pytdx 公网路径是否允许需要单独配置开关，避免“local-only”语义混乱。
- 后续 ETF 支持要先扩展列表和代码识别，再接 K 线路径。

### 3.3 SQLite：本地缓存、回测和 DB-first 源

定位：

- 不是原始行情源，而是项目内部缓存、回测、同步和数据质量追踪底座。
- 适合支撑 DB-first 行情读取、历史 K 线读取、策略/因子/研究模块复用。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/`
- `packages/akshare-mcp/src/akshare_mcp/services/market_data_access.py`
- `packages/akshare-mcp/src/akshare_mcp/services/tdx_sync_service.py`
- 工具层：quote/kline/order_book 等会先读或回退到 DB。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| DB-first | quote 和日线 K 线可先读 SQLite | 适合低延迟和回测一致性 |
| 可追踪来源 | 部分返回已有 `backend_used/source_chain/fallback_reason` | 新资产必须继续带来源元数据 |
| Schema 偏 A 股 | `stocks`、`kline_1d(time, code)` 语义偏股票 | 多资产扩展必须加 `asset_type/exchange/security_id` |
| 同码冲突风险 | ETF、指数、股票、港股、美股可能代码相近 | 不能只用 6 位代码作为长期主键 |

能支撑的项目功能：

| 功能 | 当前可用性 | 说明 |
| --- | --- | --- |
| A 股日线缓存 | 可用 | `kline_1d` |
| A 股 quote 快照缓存 | 可用 | `stock_quotes` |
| TDX 扩展数据缓存 | 部分可用 | phase-8 表覆盖 TDX extra/sector/kzz 等 |
| ETF 缓存 | 可扩展 | 需要主数据身份和 K 线主键兼容 |
| HK/US 缓存 | watchlist 可扩展 | 不建议全市场同步 |
| 财务/基本面缓存 | A 股为主 | 不应把 HK/US 写入 A 股财务表 |

推荐开发方式：

- 新增 `securities` 或等价证券主数据层，最少包含 `security_id/code/exchange/asset_type/currency/source/source_code`。
- K 线长期主键从 `(time, code)` 升级到 `(time, security_id)` 或兼容字段组合。
- 现有 A 股表保持兼容，新增多资产视图或 adapter，避免破坏旧工具。

### 3.4 Tushare Pro：授权型结构化补充源

定位：

- 授权数据源，适合补 TDX 不稳定或没有结构化覆盖的数据。
- 对 A 股财务、指数权重、基金画像、港股基础资料、宏观等更有价值。
- 受 token、积分、接口权限、白名单和网络可用性影响。

当前项目接入：

- `DataSourceManager.get_tushare_pro()`
- `packages/akshare-mcp/src/akshare_mcp/config/tushare_proxy_whitelist.json`
- `QuotesMixin` 旧 fallback 中有 daily/daily_basic/stock_basic 调用。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 授权依赖 | 需要 `TUSHARE_TOKEN`，部分接口还需要权限 | 所有调用必须懒加载和权限探测 |
| 日频结构化强 | A 股 daily、daily_basic、财务、指数、基金、宏观 | 适合补 TDX 财务和 ETF profile |
| 实时能力弱 | 主要不是实时源 | 不作为实时 quote 主源 |
| 白名单已有状态 | 当前项目有接口白名单和 no_permission/empty 标记 | 能力矩阵可直接吸收白名单状态 |

适合支撑的功能：

| 功能 | 可用方向 | 边界 |
| --- | --- | --- |
| A 股基础列表 | `stock_basic` | 非 local-only 才可用 |
| A 股日线/复权因子 | `daily/weekly/monthly/adj_factor` | 可作为 TDX/DB 兜底或校验 |
| 财务报表与指标 | `income/balancesheet/cashflow/fina_indicator` | 优先替代 TDX FN |
| 指数基础和权重 | `index_basic/index_weight/index_daily` | 支撑指数增强和 ETF tracking 映射 |
| 基金画像 | `fund_basic/fund_nav/fund_portfolio/fund_share` | 支撑 ETF profile 的补充字段 |
| 港股基础列表 | `hk_basic` | 只做基础信息，行情权限需单测 |
| 港股日线 | `hk_daily` | 当前白名单标记无权限，不能默认依赖 |
| 新闻公告 | `news/anns_d` | 当前无权限，不能作为功能承诺 |

推荐开发方式：

- `TDX_LOCAL_ONLY=1` 时完全跳过。
- Provider 层返回 `permission_required`、`empty`、`stale`，不把权限失败吞成空数组成功。
- 作为 ETF tracking/profile、财务、指数权重、宏观的优先外部补源。

### 3.5 AKShare：公共外部补充源

定位：

- 公共数据聚合源，适合补 TDX/Tushare 的缺口。
- 覆盖广，但字段和接口稳定性弱于授权源，需要质量标记和超时控制。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- `packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py`
- 多个宏观、期权、资金流、市场工具中直接 `import akshare as ak`。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 覆盖面广 | 股票、ETF、指数、港美股、宏观、新闻等 | 适合做外部 Provider 池 |
| 公共接口易变 | 字段名、接口地址、限流都可能变化 | 必须封装，不应散落直接调用 |
| 依赖声明需审查 | 当前 `akshare-mcp` 代码使用 AKShare，但 pyproject 直接依赖需要核对 | 正式扩展要补依赖或 optional group |
| 不适合 local-only | 需要网络 | `TDX_LOCAL_ONLY=1` 必须拦截 |

适合支撑的功能：

| 功能 | 可用方向 | 边界 |
| --- | --- | --- |
| A 股 K 线 fallback | `stock_zh_a_hist` 等 | 只在 TDX/DB 不可用时使用 |
| 分钟 K 线 fallback | Eastmoney/Sina 相关接口 | 公共源失败率要记录 |
| ETF profile | 跟踪指数、基金规模、基金公司、基金份额 | 正是 TDX ETF 缺口 |
| 港股 quote/kline | AKShare 港股接口候选 | 实现前需 live probe |
| 美股 quote/kline | AKShare 美股接口候选 | v1 只做 watchlist |
| 宏观/新闻/公告 | 宏观和文本类工具 | 需要来源和时间戳 |

推荐开发方式：

- 从工具层散调用收敛为 `akshare_provider`。
- 每个接口要有字段映射、超时、异常分类和质量状态。
- 对 HK/US 扩展只读，不写交易相关逻辑。

### 3.6 eFinance / Eastmoney：东方财富生态补充源

定位：

- eFinance 是东方财富生态的 Python 封装，当前在 AKShare MCP 中是 legacy fallback，在 `finance-mcp-servers` 中已有独立 Eastmoney MCP server。
- 适合行情、K 线、基金、债券、新闻流等补充。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py`
- `packages/finance-mcp-servers/src/aiask_finance_mcp/eastmoney/server.py`
- `packages/akshare-mcp/pyproject.toml` 的 `legacy` optional dependency。

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 行情和基金较方便 | quote、K 线、fund info/nav、债券等 | 可补 ETF profile 和行情兜底 |
| 独立 MCP 已存在 | Eastmoney server 提供 read-only 工具 | 不应直接把另一个 MCP server 的实现 import 进 AKShare MCP |
| 公共源不稳定 | HTTP 失败和字段变化需要处理 | 必须加 timeout 和 fallback_reason |
| 当前是 legacy | 默认不应盖过 TDX | 只在外部源启用或 fallback 场景使用 |

适合支撑的功能：

| 功能 | 可用方向 | 边界 |
| --- | --- | --- |
| A 股 quote/K 线 fallback | `ef.stock` | 不作为主源 |
| 基金信息和净值 | `ef.fund` | 可补 ETF/fund profile |
| 可转债/债券 | `ef.bond` | 可作为 TDX kzz 校验 |
| 新闻流 | `ef.stock.get_latest_news` | 需要文本来源和去重 |
| HK/US | 待实测 | 不能在文档中承诺可用 |

推荐开发方式：

- AKShare MCP 内部只作为 `efinance_provider` 兜底。
- Eastmoney MCP server 通过 MCP 聚合层对 Agent 暴露，不跨包直接 import。
- 全部调用遵守 `TDX_LOCAL_ONLY`。

### 3.7 Baostock：A 股历史日线兜底源

定位：

- A 股历史日线补充源。
- 覆盖面窄，但对历史日线和换手率、涨跌幅等字段有兜底价值。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/baostock_api.py`
- `packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 偏 A 股日线 | 适合 `daily` K 线 | 不支撑 ETF/HK/US 扩展主路径 |
| 登录连接状态 | 需要客户端会话状态 | 失败应快速降级 |
| 字段较少 | OHLCV、amount、turnover、pctChg | 不适合画像或实时功能 |

适合支撑的功能：

| 功能 | 可用方向 | 边界 |
| --- | --- | --- |
| A 股 daily K 线兜底 | 可保留 | 排在 TDX/DB 之后 |
| 回测日线补洞 | 可保留 | 要标记来源 |
| ETF/HK/US | 不推荐 | 不作为扩展源 |
| 实时行情/盘口 | 不适合 | 不进入 quote/order_book 主链路 |

推荐开发方式：

- 继续作为 legacy fallback。
- 不把 Baostock 纳入 ETF、港股、美股扩展的核心方案。

### 3.8 Sina / Tencent / Eastmoney HTTP 直连：轻量兜底源

定位：

- 轻量 HTTP 兜底，当前主要散落在 quote、kline、order_book 等工具内部。
- 适合单只或小批量的应急行情、盘口、分钟线兜底。

当前项目接入：

- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/helpers.py`

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 无 SDK 重依赖 | 直接 HTTP 请求 | 易于兜底，但要限流和超时 |
| 适合小批量 | 单只 quote、指数 quote、盘口、分钟线 | 不适合全市场同步 |
| 字段非统一 | 不同源格式差异大 | 必须收敛成 Provider contract |
| 容易绕过策略 | 当前散落在工具函数中 | 需要集中治理，特别是 local-only |

适合支撑的功能：

| 功能 | 可用方向 | 边界 |
| --- | --- | --- |
| A 股 quote fallback | Sina/Tencent/Eastmoney | 非 local-only |
| 指数 quote fallback | Eastmoney single-security | 非 local-only |
| 五档盘口 fallback | Sina/Tencent | 仅单只，字段可能缺失 |
| 分钟 K 线 fallback | Sina/Tencent/AKShare HTTP | 需质量标记 |
| HK/US | 可作为候选 | 实现前必须实测，不先承诺 |

推荐开发方式：

- 收敛为 `http_external_provider`。
- 工具层不再直接决定数据源优先级，而是调用统一 Provider。
- 失败要写入 `fallback_reason`，成功要写 `backend_used`。

### 3.9 finance-mcp-servers：独立金融 MCP 服务源

定位：

- 项目中还存在 Tongdaxin、Eastmoney 等独立 MCP server。
- 它们是面向 MCP 聚合和外部客户端的服务，不是 AKShare MCP 内部库。

当前项目接入：

- `packages/finance-mcp-servers/src/aiask_finance_mcp/tongdaxin/server.py`
- `packages/finance-mcp-servers/src/aiask_finance_mcp/eastmoney/server.py`

功能特性：

| 特性 | 说明 | 开发含义 |
| --- | --- | --- |
| 服务边界独立 | stdio/JSON-RPC MCP 工具 | AKShare MCP 不应跨包直接 import |
| read-only 工具有价值 | Eastmoney quote/kline/fund/news 等 | 可通过 Agent MCP 聚合层暴露 |
| TDX server 可能有 pytdx 能力 | 分笔、快照、财务摘要等候选 | 需单独 probe，不混同 tqcenter 实测结果 |

适合支撑的功能：

| 功能 | 使用方式 | 边界 |
| --- | --- | --- |
| Agent 外部工具扩展 | MCP 聚合调用 | 不作为 AKShare 内部 Provider 直接依赖 |
| Eastmoney read-only | 通过独立 MCP 工具 | 需要统一工具命名和安全标记 |
| 交易/账户工具 | 必须走确认/token 防护 | 不纳入本数据源扩展计划 |

推荐开发方式：

- 若后续 Desktop/Agent 需要同时使用 AKShare MCP 和 finance MCP，应在 Agent MCP 聚合层做工具编排。
- 不把独立 MCP server 当成 Python 模块内部复用，避免包边界和依赖混乱。

### 3.10 按项目功能选择数据源

| 项目功能 | 主源 | 第一兜底 | 外部补充 | 当前结论 |
| --- | --- | --- | --- | --- |
| A 股列表 | TDX tqcenter | Tushare/AKShare | SQLite 缓存 | TDX 主源明确可用 |
| A 股实时行情 | TDX tqcenter | TDX local/pytdx | eFinance/Sina/Tencent/AKShare | 现有链路可用，但要收敛元数据 |
| A 股日线 K 线 | SQLite + TDX tqcenter | TDX local | Tushare/Baostock/AKShare/Tencent | DB-first 保持，来源要显式 |
| A 股分钟 K 线 | TDX tqcenter | TDX local/pytdx | AKShare/Sina | TDX 主源更稳定 |
| 五档盘口 | TDX tqcenter snapshot | Sina/Tencent | DB quote 降级为单价盘口 | TDX 应成为主路径 |
| ETF 列表 | TDX tqcenter | AKShare/Tushare 校验 | SQLite 缓存 | 可立即扩展为正式资产 |
| ETF quote/K 线 | TDX tqcenter | TDX local 待扩展 | AKShare/eFinance | TDX 已有真实数据 |
| ETF profile | AKShare/Tushare/Eastmoney | TDX basic_info 部分字段 | 手工映射/外部 HTTP | 跟踪指数和申赎不是 TDX 主能力 |
| 指数列表/K 线 | TDX tqcenter | AKShare/Tushare | SQLite 缓存 | TDX 可用，权重外部补充 |
| 板块列表/成分/K 线 | TDX tqcenter | SQLite 缓存 | AKShare/Tushare | TDX 主源 |
| 可转债列表/行情/详情 | TDX tqcenter | Tushare/AKShare/eFinance 校验 | SQLite 缓存 | TDX 主源 |
| 专业财务 | Tushare | AKShare | TDX `stock_info` 摘要 | TDX FN 不进入正式财务 |
| 宏观 | Tushare/AKShare | 官方公共源 | SQLite 缓存 | 当前 TDX HG 示例为空 |
| 新闻/公告/研报 | AKShare/Eastmoney/Tushare 权限源 | TDX download_file 解析 | SQLite 文本库 | 不从 TDX 直接承诺结构化正文 |
| 港股列表 | Tushare `hk_basic` 或 AKShare | eFinance/Eastmoney 待测 | SQLite watchlist | TDX 不可用 |
| 港股 quote/K 线 | AKShare/eFinance/Eastmoney 待测 | Tushare 权限可用时 | SQLite watchlist | 外部只读 Provider |
| 美股 quote/K 线 | AKShare/eFinance/yfinance 候选 | 其他外部源 | SQLite watchlist | v1 只做 watchlist |
| Tick/逐笔 | 暂不支持 | finance MCP/pytdx 待单测 | 外部源待测 | 当前工具标记 unsupported |

### 3.11 数据源输出质量状态

为避免“空数据也显示成功”，后续所有 Provider 都应使用同一组质量状态：

| 状态 | 含义 | 示例 | 工具层行为 |
| --- | --- | --- | --- |
| `real_data` | 返回非空且核心字段可信 | TDX ETF K 线、TDX 快照 | 可作为成功数据 |
| `empty` | 接口可调用但返回空 | TDX `market=102/103` | 不伪装成功，允许 fallback |
| `unsupported` | 当前源不支持该功能 | TDX `period="tick"` | 直接短路或换源 |
| `placeholder_only` | 返回占位、`--`、全 0 或无意义字段 | TDX FN by-date | 禁止入库到正式数据链路 |
| `permission_required` | 需要 token、积分或权限 | Tushare `hk_daily/news` | 返回权限提示，不当作空市场 |
| `external_required` | TDX 不具备，需要外部源 | ETF 跟踪指数、HK/US | Provider 编排进入外部源 |
| `stale` | 有数据但新鲜度不足 | DB quote 超过 TTL | 可返回但标 degraded |
| `not_tested` | 代码或文档提示存在，但未实测 | eFinance HK/US 候选 | 不写入能力承诺 |

### 3.12 最小开发接口清单

为了把上述数据源真正变成项目功能，后续开发至少需要这些接口。注意：本文件只是计划，本轮不实现。

| 接口 | 作用 | 数据源选择 |
| --- | --- | --- |
| `get_data_source_capabilities()` | 返回按 provider/asset/domain 的真实能力矩阵 | 静态注册 + probe 结果 |
| `resolve_security_id(symbol, asset_type=None)` | 解析 A 股、ETF、指数、可转债、港股、美股身份 | TDX 列表 + 规则 + 外部列表 |
| `get_security_list(asset_type, market=None)` | 多资产证券列表 | TDX 为 CN 主源，HK/US 外部源 |
| `get_security_quote(symbol, asset_type=None)` | 多资产实时/准实时行情 | TDX CN 主源，HK/US 外部源 |
| `get_security_kline(symbol, period, limit)` | 多资产 K 线 | DB-first + TDX/external |
| `get_etf_profile(symbol)` | ETF 跟踪指数、规模、公司、申赎等画像 | 外部源 + TDX basic/more_info |
| `get_provider_health(provider)` | 查看 token、local-only、依赖、最近错误 | 各 Provider 自报 |

### 3.13 ETF、港股、美股扩展可行性结论

| 扩展方向 | 可行性 | 原因 | v1 范围 |
| --- | --- | --- | --- |
| ETF | 高 | TDX 实测列表、K 线、快照、基础信息、分红均可用 | 正式支持列表、quote、kline、snapshot、basic、dividend；profile 外部补充 |
| REIT/LOF/场内基金 | 中高 | TDX 列表可用，行情/K 线需按样本补测 | 先纳入列表和 quote/kline，画像后置 |
| 可转债 | 高 | TDX 列表、K 线、快照、kzz_info 可用 | 正式资产类型，补外部校验 |
| 指数/板块 | 高 | TDX 列表、成员、K 线、快照可用 | 指数权重和板块解释外部补充 |
| 港股 | 中 | TDX 不可用，但外部源可做只读 | 列表、quote、daily kline，遵守 local-only |
| 美股 | 中 | TDX 不可用，外部源可做 watchlist | 显式 symbol quote/daily kline，不做全市场 |
| 期货/期权 | 低到中 | TDX 实测列表为空，项目有其他外部工具但未统一 | 暂不纳入本次主扩展 |

## 4. 功能能力矩阵

状态说明：

- `主源可用`：当前或后续应以该源为主。
- `兜底可用`：可作为 fallback，不应作为首选。
- `需外部源`：TDX 当前实测不可用，需要 Tushare/AKShare/eFinance 等补充。
- `不可用`：当前不应开发或不应声明可用。
- `需解析`：可以下载或获得原始数据，但需要结构化解析。

| 功能域 | TDX tqcenter | TDX vipdoc/pytdx | SQLite | Tushare | AKShare | eFinance/Baostock/HTTP | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A 股列表 | 主源可用 | 部分可用 | 可缓存 | 可用 | 可用 | 不适合 | TDX 主源 |
| ETF/REIT/LOF 列表 | 主源可用 | 当前需扩展 | 可缓存 | 可补充基金画像 | 可补充基金画像 | 不适合 | TDX 列表，外部补画像 |
| 可转债列表与基础信息 | 主源可用 | 部分行情兜底 | 可缓存 | 可补充 | 可补充 | 不适合 | TDX 主源 |
| 指数列表与指数成分 | 主源可用 | 行情兜底 | 可缓存 | 指数权重可补 | 可补充 | HTTP 可兜底 | TDX + Tushare/AKShare |
| 板块/行业/概念 | 主源可用 | 不完整 | 可缓存 | 可补概念 | 可补行业概念 | 不适合 | TDX 主源 |
| 日线 K 线 | 主源可用 | 兜底可用 | 主缓存 | 可补 | 可补 | 可兜底 | DB first + TDX 主源 |
| 分钟 K 线 | 主源可用 | 兜底可用 | 可选缓存 | 不适合 | 可补 | HTTP 可兜底 | TDX 主源 |
| Tick/逐笔 | 当前不可用 | pytdx 独立服务可能有 | 不建议 | 不适合 | 可探测 | 可探测 | 当前标记 unsupported |
| 实时快照 | 主源可用 | 兜底可用 | 可缓存 | 日频替代 | 可补 | 可兜底 | TDX 主源 |
| 五档盘口 | 主源可用 | pytdx 可兜底 | 可缓存 | 不适合 | 可补 | 可兜底 | TDX 主源 |
| 基础信息 | 主源可用 | 部分可用 | 可缓存 | 可补 | 可补 | 不适合 | TDX 主源 |
| 扩展行情/估值 | 主源可用 | 不完整 | 可缓存 | 可补日频 | 可补 | 不适合 | TDX 主源，外部校验 |
| 分红/股本/IPO | 主源可用 | 不完整 | 可缓存 | 可补 | 可补 | 不适合 | TDX 主源 |
| 专业财务 FN | 占位或空 | 不适合 | 可缓存但需禁用污染 | 可主源 | 可补 | 不适合 | Tushare/外部源 |
| GO 一致预期 | 部分真实 | 不适合 | 可缓存 | 可补研报预期 | 可补 | 不适合 | TDX 部分使用 |
| GP/BK/SC 特色字段 | 历史接口部分真实，by-date 多占位 | 不适合 | 可每日累积 | 可补部分 | 可补部分 | 不适合 | TDX 可用字段白名单 |
| ETF 跟踪指数 | 空 | 不适合 | 可缓存 | 可补 | 可补 | 不适合 | 外部源 |
| ETF 申赎清单 | 可能可下载 | 不适合 | 可缓存 | 可补 | 可补 | 不适合 | TDX 下载需解析，否则外部源 |
| 港股列表 | 空 | 不适合 | 可缓存 | `hk_basic` 可用 | 可补 | 可补 | 外部源 |
| 港股 K 线 | 空 | 不适合 | watchlist 缓存 | `hk_daily` 当前无权限 | 可补 | 可补 | 外部源，权限探测 |
| 美股列表 | 空 | 不适合 | watchlist 缓存 | 白名单无完整股票源 | 可补 | 可补 | 外部源，先 watchlist |
| 美股 K 线 | 空 | 不适合 | watchlist 缓存 | 不作为默认 | 可补 | 可补 | 外部源 |
| 宏观 | HG 示例空 | 不适合 | 可缓存 | 可用部分 | 可用 | 不适合 | 外部源 |
| 新闻/公告/研报正文 | 文件下载需解析 | 不适合 | 可缓存文本 | 部分无权限 | 可用 | Eastmoney 可补 | 外部源或 TDX 文件解析 |
| 期货/期权 | 列表为空或未覆盖 | 不适合 | 可缓存 | 部分可用 | 可用 | Eastmoney 可补 | 后续单独专题 |

## 5. 按资产类型的目标能力

| 资产类型 | v1 目标 | 主数据源 | 补充源 | 不做内容 |
| --- | --- | --- | --- | --- |
| A 股股票 | 列表、行情、K 线、基础信息、扩展行情、分红、股本、板块归属 | TDX tqcenter | SQLite、vipdoc/pytdx、Tushare/AKShare | 不默认使用 FN 占位财务 |
| 北交所股票 | 列表、行情、K 线、基础信息、扩展行情 | TDX tqcenter | SQLite | 港美股式代码混用 |
| ETF | 列表、行情、K 线、基础信息、扩展行情、分红、ETF profile | TDX tqcenter | AKShare/Tushare/Eastmoney | 不把跟踪指数声明为 TDX 可用 |
| REITs/LOF/场内基金 | 列表、行情、K 线、基础信息 | TDX tqcenter | 外部基金画像 | 不做基金净值全量历史主线 |
| 可转债 | 列表、行情、K 线、可转债基础信息 | TDX tqcenter | Tushare/AKShare | 不把分红空值当异常 |
| 指数 | 列表、行情、K 线、指数成分 | TDX tqcenter | Tushare/AKShare | 不与股票同码混写 |
| 板块/行业/概念 | 列表、成员、行情、K 线、统计字段 | TDX tqcenter | AKShare/Tushare | 不假设所有 BK 字段真实 |
| 港股 | 列表、行情、日线 K 线 | 外部 Provider | Tushare/AKShare/eFinance | 不走 TDX |
| 美股 | watchlist 行情、日线 K 线 | 外部 Provider | AKShare/eFinance/yfinance 可选 | 不做全市场同步 |
| 宏观 | 查询和缓存常用指标 | Tushare/AKShare | 官方 HTTP 源 | 不走当前 TDX HG 示例 |

## 6. 现有代码问题清单

### 5.1 数据源入口问题

`DataSourceManager` 已经是统一入口，但部分能力仍分散在工具层直接调用外部库。后续应把数据源选择收敛到 `data_source` 或独立 Provider 层。

需要处理：

- 统一 `get_security_list`、`get_security_quote`、`get_security_kline`。
- 保留 `get_realtime_quote`、`get_kline`、`get_stock_list` 兼容旧调用。
- 增加能力查询：`get_data_source_capabilities`。
- 输出中统一加入 `asset_type`、`source`、`backend_used`、`fallback_used`、`fallback_reason`、`quality_flags`。

### 5.2 代码规范化与校验问题

当前 `utils.py` 的严格股票代码校验只接受：

- 1 到 6 位数字。
- `sh/sz/bj` 前缀。
- `.SH/.SZ/.BJ` 后缀。

这会挡住：

- `00700.HK`
- `09988.HK`
- `AAPL.US`
- `MSFT.US`

后续需要新增多资产代码解析，而不是继续扩大 `stock_code` 的语义。

建议：

- `resolve_security_id()` 负责识别多资产。
- `validate_stock_code_format()` 继续只服务 A 股兼容接口。
- 新工具全部使用 `symbol` 或 `security_id`，不再把港美股塞进 `stock_code`。

### 5.3 存储模型问题

当前 `kline_1d` 和 `stocks` 更适合 A 股：

- `kline_1d(time, code)` 缺少资产类型和交易所。
- `stocks.stock_code` 不能表达港股、美股、ETF、指数、板块的完整身份。

建议：

- 新增 `securities` 表：
  - `security_id`
  - `code`
  - `exchange`
  - `asset_type`
  - `currency`
  - `name`
  - `source`
  - `source_code`
  - `list_status`
  - `updated_at`
- K 线表短期使用 canonical id 避免冲突，长期扩展主键为 `(time, security_id)` 或 `(time, code, exchange, asset_type)`。
- A 股财务表不写 HK/US。

### 5.4 依赖声明问题

当前 `akshare-mcp` 代码大量 `import akshare as ak`，但 `pyproject.toml` 没有把 `akshare` 作为直接依赖。后续如果把 AKShare 作为港股、美股、ETF profile 的正式补充源，必须补依赖声明或新增 optional dependency group。

建议：

- 核心包只保留必须依赖。
- 新增可选组：`global-markets = ["akshare", "efinance", "yfinance"]`，具体是否引入 yfinance 需实现阶段确认。
- 外部 Provider 不可影响 TDX_LOCAL_ONLY 的启动路径。

## 7. 扩展设计

### 6.1 统一证券身份

目标结构：

```text
SecurityId
- security_id: 内部唯一 ID，例如 CN_ETF:SH:510300
- symbol: 用户输入符号，例如 510300.SH
- code: 裸代码，例如 510300
- exchange: SH / SZ / BJ / HK / US
- asset_type: CN_STOCK / CN_ETF / CN_CB / HK_STOCK / US_STOCK 等
- currency: CNY / HKD / USD
- source_code: Provider 原始代码，例如 510300.SH、00700.HK
```

识别规则：

- `.SH/.SZ/.BJ`：中国市场资产，继续结合 TDX 列表判断股票、ETF、可转债、指数、板块。
- `.HK`：港股资产，默认 `HK_STOCK`。
- `.US` 或纯美股 ticker：默认 `US_STOCK`，纯 ticker 只有在显式 `asset_type=US_STOCK` 时接受。
- `88xxxx.SH`：板块指数。
- `123xxx.SZ`、`11xxxx.SH`：可转债，最终以 TDX 列表校验为准。
- `159xxx.SZ`、`510xxx.SH`、`588xxx.SH` 等基金代码不能只靠前缀硬判，应以 TDX `market=31/30/33/34/35/36` 列表为准。

### 6.2 数据源能力矩阵

新增能力注册结构：

```text
Capability
- provider: tdx_tqcenter / tdx_local / sqlite / tushare / akshare / efinance / baostock / http_external
- asset_type
- domain: list / quote / kline / snapshot / more_info / basic_info / dividend / financial / relation / formula / profile
- status: available / empty / unsupported / external_required / permission_required / not_tested
- freshness: realtime / intraday / daily / static / unknown
- notes
```

必须区分：

- `empty`：接口可调用但当前无数据。
- `unsupported`：当前源不支持，不应调用。
- `placeholder_only`：返回 `--`、全 0 或占位值，不可进入真实数据链路。
- `permission_required`：需要 token、权限或付费包。
- `external_required`：TDX 不可用，需要外部源。

### 6.3 Provider 输出契约

所有新旧数据源最终应归一为：

```text
{
  "success": true,
  "data": ...,
  "source": "tdx_tqcenter",
  "backend_requested": "tdx_tqcenter",
  "backend_used": "tdx_tqcenter",
  "fallback_used": false,
  "fallback_reason": null,
  "quality_flags": [],
  "asset_type": "CN_ETF",
  "currency": "CNY",
  "asof_time": "..."
}
```

失败或不可用时：

```text
{
  "success": false,
  "data": null,
  "error": "HK_STOCK is unsupported when TDX_LOCAL_ONLY=1",
  "source": "none",
  "backend_requested": "akshare",
  "backend_used": "none",
  "fallback_used": false,
  "fallback_reason": "tdx_local_only",
  "quality_flags": ["unsupported_asset_type", "tdx_local_only"],
  "asset_type": "HK_STOCK"
}
```

## 8. ETF 详细开发方案

### 7.1 ETF 数据域

| 数据域 | TDX 能力 | 外部补充 | v1 处理 |
| --- | --- | --- | --- |
| ETF 列表 | `get_stock_list("31")` 可用 | AKShare/Tushare 校验 | TDX 主源 |
| REITs 列表 | `get_stock_list("30")` 可用 | AKShare/Tushare | TDX 主源 |
| LOF 列表 | `get_stock_list("33")` 可用 | AKShare/Tushare | TDX 主源 |
| 场内基金列表 | `get_stock_list("34/35/36")` 可用 | AKShare/Tushare | TDX 主源 |
| 行情快照 | `get_market_snapshot` 可用 | HTTP fallback | TDX 主源 |
| K 线 | `get_market_data` 可用 | AKShare fallback | TDX 主源 |
| 扩展行情 | `get_more_info` 可用 | 无 | TDX 主源 |
| 基础信息 | `get_stock_info` 可用 | 基金画像补充 | TDX + 外部 |
| 分红 | `get_divid_factors` 可用 | 外部校验 | TDX 主源 |
| 跟踪指数 | 当前为空 | AKShare/Eastmoney/Tushare | 外部源 |
| 申赎清单 | `download_file(2)` 待解析 | AKShare/Eastmoney | 先外部，TDX 文件解析后接入 |

### 7.2 ETF 新工具

建议新增：

- `get_security_list(asset_type="CN_ETF", market=None, limit=500, offset=0)`
- `get_security_quote(symbol="510300.SH", asset_type="CN_ETF")`
- `get_security_kline(symbol="510300.SH", asset_type="CN_ETF", period="daily", limit=100)`
- `get_etf_profile(symbol="510300.SH")`

`get_etf_profile` 字段建议：

- `symbol`
- `name`
- `exchange`
- `asset_type`
- `tracking_index_code`
- `tracking_index_name`
- `fund_company`
- `fund_manager`
- `fund_size`
- `fund_share`
- `expense_ratio`
- `creation_redemption_available`
- `quote`
- `source_chain`
- `quality_flags`

### 7.3 ETF 验收样本

- `510300.SH`：沪市宽基 ETF。
- `159001.SZ`：深市 ETF。
- `588000.SH`：科创类 ETF。

验收要求：

- 列表可找到样本。
- 日线和分钟线可返回真实数据。
- 快照可返回价格、成交量额、五档盘口。
- 基础信息可返回名称等字段。
- profile 中跟踪指数如不可取，必须标明 `external_required`，不能留空伪装成功。

## 9. 港股和美股详细开发方案

### 8.1 港股

当前 TDX 状态：

- `get_stock_list("102")` 为空。
- 不作为 TDX 能力声明。

目标能力：

- 基础列表。
- watchlist 行情。
- 日线 K 线。
- 基础名称、交易所、币种。

Provider 策略：

- 首选：Tushare `hk_basic` 用于列表和基础信息。
- K 线：Tushare `hk_daily` 只有权限可用时使用；当前白名单标记为无权限，因此不能默认依赖。
- fallback：AKShare/Eastmoney/eFinance 公共源，需实现时实测。

代码格式：

- `00700.HK`
- `09988.HK`

质量规则：

- 无权限返回 `permission_required`。
- 公共源失败返回 `external_provider_failed`。
- `TDX_LOCAL_ONLY=1` 返回 `unsupported_asset_type` + `tdx_local_only`。

### 8.2 美股

当前 TDX 状态：

- `get_stock_list("103")` 为空。
- 不作为 TDX 能力声明。

目标能力：

- v1 只支持 watchlist 或显式输入 symbol。
- 支持 quote 和 daily kline。
- 不做全市场列表和全市场同步。

Provider 策略：

- AKShare/eFinance/yfinance 可选，具体实现前必须进行最小可用性探测。
- 如新增 yfinance，应放入 optional dependency，不影响默认安装。

代码格式：

- `AAPL.US`
- `MSFT.US`
- 允许纯 `AAPL` 仅在 `asset_type=US_STOCK` 显式指定时解析。

质量规则：

- 标注延迟。
- 标注币种 `USD`。
- 不写入 A 股财务表。
- 不走任何交易接口。

## 10. 分阶段开发计划

### Phase 1：证券身份与能力矩阵

目标：

- 建立多资产身份。
- 明确每个 Provider 的真实能力和不可用能力。

涉及文件：

- `packages/akshare-mcp/src/akshare_mcp/data_source/`
- `packages/akshare-mcp/src/akshare_mcp/utils.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/`

开发内容：

- 新增 `SecurityId` 解析模块。
- 新增 `DataSourceCapability` 注册表。
- 新增 `get_data_source_capabilities()`。
- 保留旧 A 股工具兼容。

验收：

- 能查询 TDX 对 ETF/HK/US/FN/tick 的真实状态。
- `00700.HK` 不再被 A 股校验误拒到模糊错误，而是识别为 `HK_STOCK`。
- `period="tick"` 在 TDX 路径被标记 unsupported。

### Phase 2：ETF 正式接入

目标：

- 让 ETF 成为正式资产类型。

涉及文件：

- `data_source/tdx_tqcenter.py`
- `data_source/tdx_local.py`
- `tools/market/stock_list.py`
- `tools/market/quote.py`
- `tools/market/kline.py`

开发内容：

- 接入 ETF/REIT/LOF/场内基金列表。
- ETF quote/kline/snapshot/more_info/basic_info/dividend 全部走 TDX 主源。
- 新增 ETF profile 外部补充。

验收：

- `510300.SH`、`159001.SZ`、`588000.SH` 全链路可查。
- 返回 `asset_type=CN_ETF`。
- 外部 profile 失败不影响 TDX 行情和 K 线。

### Phase 3：港股/美股只读 Provider

目标：

- 接入 HK/US quote 和 kline，但不污染 TDX 能力声明。

涉及文件：

- 新增 external provider 模块。
- `tools/market/quote.py`
- `tools/market/kline.py`
- `packages/akshare-mcp/pyproject.toml`

开发内容：

- 港股 Provider：基础列表、quote、daily kline。
- 美股 Provider：watchlist quote、daily kline。
- 外部依赖声明调整。
- `TDX_LOCAL_ONLY` 统一拦截。

验收：

- `TDX_LOCAL_ONLY=1` 下 HK/US 不发起网络请求。
- mock provider 测试可覆盖 quote/kline。
- 无 token 或无权限时返回明确质量状态。

### Phase 4：存储与同步

目标：

- 让多资产数据可缓存、可回测、可追踪来源。

涉及文件：

- `storage/sqlite/schema_market.py`
- `storage/sqlite/kline.py`
- `storage/sqlite/stock_info.py`
- `services/tdx_sync_service.py`

开发内容：

- 新增或扩展证券主数据表。
- ETF universe/quote/kline 同步。
- HK/US watchlist kline 同步。
- 数据完整性状态增加 ETF/HK/US 项。

验收：

- ETF 不再被误写为普通股票。
- HK/US 不进入 A 股财务链路。
- DB 查询可按 asset_type 过滤。

### Phase 5：工具层与 Agent/Desktop 契约

目标：

- 对外暴露统一多资产工具。

新增工具建议：

- `get_security_list`
- `get_security_quote`
- `get_security_kline`
- `get_etf_profile`
- `get_data_source_capabilities`

兼容策略：

- `get_stock_list` 继续表示 A 股股票列表。
- `get_realtime_quote` 继续支持原 A 股参数。
- `get_kline` 继续支持原 A 股/ETF 6 位代码路径，但新场景推荐 `get_security_kline`。

验收：

- 旧工具不破坏。
- 新工具能表达 asset_type。
- 返回质量元数据一致。

### Phase 6：测试与数据质量审计

测试范围：

- 单元测试：代码解析、asset_type 判断、TDX_LOCAL_ONLY。
- Provider mock：Tushare/AKShare/eFinance fallback。
- TDX live-gated 测试：ETF、可转债、指数、板块。
- 回归测试：A 股 quote/kline/list。
- 数据质量脚本：扩展 ETF/HK/US 能力矩阵。

验收：

- 空、占位、unsupported、无权限、真实数据可区分。
- 文档中的数据源能力与探测报告一致。
- 新 Provider 不引入启动硬依赖。

## 11. 风险与控制

| 风险 | 影响 | 控制 |
| --- | --- | --- |
| 把 TDX 空源当作可用源 | 港股/美股返回空数据还显示成功 | 能力矩阵标记 `empty` 或 `unsupported` |
| ETF 与股票混写 | 回测、筛选、风险分析语义错误 | 引入 `asset_type` 和 canonical security id |
| FN 占位字段进入财务链路 | 财务分析污染 | 默认禁用 FN，使用 Tushare/外部源或 `get_stock_info` 摘要 |
| tick 继续被传给 TDX | 错误 payload 污染工具结果 | TDX period map 移除 tick 或返回 unsupported |
| 外部公共源不稳定 | HK/US/ETF profile 间歇失败 | 统一 fallback、超时和质量标记 |
| local-only 被绕过 | 用户预期离线但实际联网 | Provider 层统一检查 `TDX_LOCAL_ONLY` |
| 依赖声明不完整 | 部署后 import 失败 | 将正式 Provider 依赖写入 pyproject 或 optional group |
| 全市场 HK/US 同步过大 | 慢、脏、不可控 | v1 仅 watchlist 或显式列表 |

## 12. 后续验收清单

文档级验收：

- 本文件说明每个数据源的角色、可用能力、限制和推荐用途。
- 本文件说明每类核心功能应该使用哪个主源和哪个补充源。
- 本文件说明 ETF、港股、美股的扩展路径和边界。

实现级验收：

- `get_data_source_capabilities()` 能返回实际能力矩阵。
- `510300.SH` 可作为 `CN_ETF` 获取列表、quote、kline、snapshot、basic_info。
- `00700.HK` 在 local-only 下返回 unsupported，在外部源启用时可通过 Provider 获取只读数据。
- `AAPL.US` 在 local-only 下返回 unsupported，在外部源启用时可通过 Provider 获取只读数据。
- `period="tick"` 不再被当作 TDX 可用周期。
- 所有新工具返回 `source/backend_used/fallback_reason/quality_flags/asset_type/currency`。
- 现有 A 股核心工具保持兼容。

## 13. 本轮变更约束

本轮只创建和维护 `DATA_SOURCE_EXPANSION_DEVELOPMENT_PLAN.md`。

不做以下事项：

- 不修改业务代码。
- 不修改测试。
- 不修改配置和依赖。
- 不修改数据库 schema。
- 不运行同步、迁移或真实数据写入。
- 不改变当前工具行为。
