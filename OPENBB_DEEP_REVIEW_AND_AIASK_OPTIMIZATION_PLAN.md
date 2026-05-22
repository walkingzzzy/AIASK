# OpenBB 深度代码审查与 AIASK 优化调整方案

审查日期：2026-05-20

审查对象：

- OpenBB 本地快照：`OpenBB/`
- AIASK 当前项目：`packages/`、`desktop/`、根目录运行脚本

本文档只记录审查结论、架构借鉴点和优化路线，不直接引入 OpenBB 代码，也不改变当前业务实现。

## 1. 结论先行

OpenBB 最值得借鉴的不是某个具体 provider 的实现，而是它围绕金融数据建立的一整套“标准模型 + provider 插件 + fetcher 执行链 + 自动契约生成 + 多入口复用”的工程体系。它把大量异构数据源收敛到统一的 Query/Data 模型，再通过 RegistryMap、ProviderInterface、Router、PackageBuilder、MCP Server、CLI/Desktop 等层层派生出可调用接口。

AIASK 当前的优势在另一个方向：A 股本地数据优先级、TDX/Tushare/AKShare 降级链、Agent 安全门面、`aiask_envelope`、lineage/quality/side_effect 元数据、ActionIntent、broker token 交易防护、Strategy Factory 与量化验证能力。这些是 OpenBB 没有直接覆盖的高价值能力，不能为了模仿 OpenBB 而削弱。

建议采用“吸收 OpenBB 的契约化与生成式架构，不复制 OpenBB 实现”的路线：先在 AKShare MCP 内建立 AIASK 自有的 `ProviderContract / Fetcher / StandardModel` 薄层，覆盖行情、K 线、股票基础资料、交易日历等高频模型；再把 AKShare MCP 工具契约、Agent `TOOL_SCHEMAS`、Desktop 表单元数据收敛到同一份契约来源。

## 2. 审查范围与方法

本次不是只看几个文件下结论，而是按子系统横向抽样并对照 AIASK 当前实现。

OpenBB 侧统计和取样：

- 代码规模：约 1319 个 Python/TypeScript/TSX 文件。
- Provider 规模：约 32 个 provider 包、18 个 extension 包、180 个 standard model 文件、341 个 fetcher 类。
- 测试规模：约 260 个测试文件，其中包含 core app/provider、provider fetcher、MCP server、static package builder、desktop route/component tests。
- 重点文件和模块：
  - `OpenBB/openbb_platform/core/openbb_core/provider/abstract/fetcher.py`
  - `OpenBB/openbb_platform/core/openbb_core/provider/abstract/provider.py`
  - `OpenBB/openbb_platform/core/openbb_core/provider/registry.py`
  - `OpenBB/openbb_platform/core/openbb_core/provider/registry_map.py`
  - `OpenBB/openbb_platform/core/openbb_core/provider/query_executor.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/extension_loader.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/router.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/provider_interface.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/query.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/command_runner.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/model/obbject.py`
  - `OpenBB/openbb_platform/core/openbb_core/app/static/package_builder.py`
  - `OpenBB/openbb_platform/extensions/equity/openbb_equity/equity_router.py`
  - `OpenBB/openbb_platform/extensions/equity/openbb_equity/price/price_router.py`
  - `OpenBB/openbb_platform/extensions/mcp_server/openbb_mcp_server/app/app.py`
  - `OpenBB/openbb_platform/extensions/mcp_server/openbb_mcp_server/models/settings.py`
  - `OpenBB/desktop/src/routes/backends.tsx`
  - `OpenBB/desktop/src/components/AddExtensionSelector.tsx`

AIASK 侧统计和取样：

- 代码规模：约 1042 个 Python/TypeScript/TSX 文件。
- 重点文件和模块：
  - `packages/agent/src/aiask_agent/server.py`
  - `packages/agent/src/aiask_agent/tool_registry.py`
  - `packages/agent/src/aiask_agent/tools/policy.py`
  - `packages/agent/src/aiask_agent/tools/catalog.py`
  - `packages/agent/src/aiask_agent/tools/schemas.py`
  - `packages/akshare-mcp/src/akshare_mcp/server.py`
  - `packages/akshare-mcp/src/akshare_mcp/data_source/__init__.py`
  - `packages/akshare-mcp/src/akshare_mcp/tools/manager_protocol.py`
  - `packages/akshare-mcp/src/akshare_mcp/tools/search.py`
  - `packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog.py`
  - `packages/akshare-mcp/src/akshare_mcp/tools/market/`
  - `packages/aiask-quant-core/src/aiask_quant_core/`
  - `packages/strategy-factory/src/strategy_factory/api/facade.py`
  - `packages/finance-mcp-servers/src/aiask_finance_mcp/_shared/trade_guard.py`
  - `desktop/src/services/aiaskApi.ts`

审查方法：

- 先看核心抽象，再看扩展/路由/测试如何使用这些抽象。
- 对比数据质量、数据源控制、工具契约、结果 envelope、安全边界、前端消费方式。
- 只把 OpenBB 的工程思想作为参考；OpenBB 许可证是 AGPL-3.0-only，不复制源代码实现。

## 3. OpenBB 的架构优势

### 3.1 Provider + Fetcher + StandardModel 是核心护城河

OpenBB 的金融数据调用不是散落函数，而是围绕三个层次组织：

- StandardModel：定义跨 provider 的标准 QueryParams 和 Data 字段。
- Provider：声明 provider 名称、描述、官网、凭证需求、fetcher 字典。
- Fetcher：把一次数据请求拆成 `transform_query -> extract_data/aextract_data -> transform_data`。

关键点：

- `Fetcher` 使用泛型绑定 QueryParams 与返回 Data 类型，类属性能反推出 `query_params_type`、`return_type`、`data_type`。
- `Fetcher.test()` 会验证 query 不为空、query 类型正确、原始 data 非空、transform 后类型和字段正确。
- provider 可以有标准字段以外的 extra params/data，但这些 extra 会被 RegistryMap 收集并标注 provider 来源。
- `QueryExecutor` 在执行前检查 provider 是否存在、fetcher 是否存在、credential 是否缺失或为空。

这个结构的价值是：新增数据源时，不是“再写一个函数”，而是必须放进统一模型、统一注册、统一凭证、统一测试链路里。

### 3.2 RegistryMap + ProviderInterface 把异构 provider 变成可生成契约

`RegistryMap` 会遍历所有 provider 的 fetcher，拆出标准字段与 provider extra 字段，生成：

- provider 列表；
- provider credential map；
- model -> provider -> QueryParams/Data map；
- 原始 provider model；
- standard/extra 字段差异。

`ProviderInterface` 再用这些 map 动态生成：

- provider choices；
- 标准 params / extra params dataclass；
- data schema；
- return schema；
- OpenAPI/FastAPI 可消费的参数结构。

这意味着 OpenBB 不需要在 CLI、REST API、MCP、桌面端分别维护一份完整参数表。它先有 provider contract，再派生 UI/API/tool contract。

### 3.3 Router 与 Command 体系让多入口复用同一业务能力

OpenBB 的 extension router 使用 `Router` 和 `@router.command` 注册金融命令。典型路径如 equity 下再 include price、fundamental、calendar 等子 router。

优势：

- 路由和金融模型绑定，而不是和某个 provider 实现强绑定。
- 同一条命令可以通过 Python API、REST API、CLI、MCP 暴露。
- `command_runner` 会在结果中补 provider、route、params 等上下文。
- extension loader 通过 entrypoint 加载 core extension、provider extension、OBBject extension，适合生态扩展。

### 3.4 OBBject 统一结果对象降低下游适配成本

OpenBB 的 `OBBject` 是统一结果容器，支持：

- 转 DataFrame；
- 转 Polars；
- 转 dict；
- 给 LLM 的简化输出；
- chart 扩展；
- metadata 中带 provider、route、params 等上下文。

这类统一结果对象的价值在于让 provider 差异停在数据层，下游分析、展示、LLM 消费都可以面对一致结构。

### 3.5 PackageBuilder 与 reference.json 是生成式 SDK 的关键

OpenBB 的 static package builder 会扫描 router、provider interface、extension map，生成 package 和 reference assets。它不是只靠手写文档维护 API 表，而是从实际安装的 extension 和路由状态生成可引用资产。

这点对 AIASK 很重要：当工具越来越多时，手工维护 Agent schema、MCP contract、Desktop forms 很容易漂移。OpenBB 的经验说明，应该从一个权威 registry 生成多个消费层。

### 3.6 MCP Server 把 REST 路由自动转换成可发现工具

OpenBB MCP Server 的关键设计：

- 从 FastAPI app 处理 routes，生成 MCP tools/resources/prompts。
- 按 API path 自动推导 category、subcategory、tool name。
- 支持 schema compression，减少工具 schema 体积。
- 支持 `allowed_tool_categories`、`default_tool_categories`。
- 可开启 discovery mode，让工具默认禁用，由 agent 通过 admin tools 激活 category 或具体 tool。
- `CategoryIndex` 维护 category/subcategory/tool 的只读索引。

这对 AIASK 的启发是：工具数量增长后，不应该把所有工具一次性暴露给模型。应当有 category/subcategory、默认可见集合、按需激活、side_effect 可见性和安全策略。

### 3.7 Desktop 更像运行环境/扩展管理器，不直接耦合数据函数

OpenBB Desktop 重点是：

- 管理 backends；
- 管理 Python environments；
- 安装 provider/router/other extensions；
- 配置 API keys；
- 查看 backend/Jupyter logs。

`AddExtensionSelector.tsx` 会从 GitHub extension json 拉取 provider/router/obbject 扩展列表，再映射成统一 Extension 模型。它说明桌面端应该消费契约和元数据，而不是写死每一个后端函数的调用细节。

## 4. OpenBB 如何确保数据质量与数据源

OpenBB 的数据质量保障更准确地说是“结构质量、契约质量、执行链路质量”，而不是保证外部金融数据一定真实。

### 4.1 它能保证什么

结构质量：

- 所有 QueryParams/Data 继承统一 Pydantic 基类。
- 标准模型定义跨 provider 的字段语义。
- provider extra 字段被保留并标注来源，不会无声混入标准字段。
- alias、extra、schema dump 由 Pydantic 管理，减少手写参数转换错误。

契约质量：

- provider 必须注册到 provider extension。
- fetcher 必须声明 QueryParams/Data 类型。
- RegistryMap 会验证 fetcher 的 query/data model 是否继承正确基类。
- ProviderInterface 可以把 provider choices、params、return schema 生成出来。

执行链路质量：

- Fetcher 的 TET 流程要求 query transform、data extract、data transform 分离。
- `Fetcher.test()` 可以验证每个阶段是否返回正确形态。
- `QueryExecutor` 执行前验证 provider、fetcher、credential。
- empty data、unauthorized、provider error 有统一异常路径和 API 映射。

数据源可控性：

- provider extension entrypoint 是 provider 能否进入系统的入口。
- provider 对 credential 有声明，执行时只传递对应 provider 所需凭证。
- model -> provider 的映射可枚举，API/CLI/MCP 可以展示 provider choices。

测试保障：

- core provider、abstract fetcher、query executor、registry map、provider fetcher、MCP server、desktop route/component 都有对应测试。
- provider 测试不是只测工具存在，而是覆盖 fetcher 行为、helper、integration API/Python 调用等层面。

### 4.2 它不能保证什么

OpenBB 没有从根本上保证第三方数据源“绝对准确”。它依赖 yfinance、FMP、SEC、BLS、FINRA、CFTC、Benzinga 等外部源自身质量。

它通常不强制做：

- 多源交叉核验；
- 每个字段的业务合理性校验；
- A 股本地行情优先级；
- 本地数据库 freshness gate；
- point-in-time 合规；
- 交易 side effect 安全策略。

因此，OpenBB 的“数据质量”适合概括为：通过标准模型和 provider contract 降低结构错误和接入错误，通过测试与错误处理提高链路可靠性，但不替代原始数据源的真实性审核。

## 5. AIASK 当前优势与短板

### 5.1 AIASK 已经强于 OpenBB 的地方

A 股数据源策略更贴近本项目目标：

- 当前 AKShare MCP 数据源优先级是本地 TDX vipdoc -> 在线 TDX -> Tushare/AKShare。
- `TDX_LOCAL_ONLY=1` 时不会强行走在线 fallback。
- Tushare lazy load，不会成为启动硬依赖。
- 现有测试覆盖 TDX routing、tqcenter fallback、tdx_local fallback、字段存在性等行为。

安全边界更强：

- Agent 模型可见工具必须使用 `agent_*`。
- `strategy_manager`、`live_trading_manager`、`paper_trading_manager`、`execution_manager`、`available_tools`、`get_tool_contract` 等 token 不能出现在模型可见工具名。
- Desktop 只消费 Agent HTTP API，不直接调用 MCP 或 manager。
- stateful financial action 通过 ActionIntent。
- live order/cancel 需要 broker token，拒绝 envelope 中带 `side_effect.level=trade_risk` 和 `explicit_token_required=True`。

结果 envelope 与审计更强：

- `manager_protocol.py` 已经有 trace_id、audit_event_id、source_chain、data_timestamp、quality、side_effect、lineage、idempotency_key、degraded。
- Agent `ensure_aiask_envelope` 统一补齐 trace、source_chain、side_effect、toolset。
- 这比 OpenBB 普通 provider 返回结果更适合金融 agent 场景。

量化与策略工厂更深入：

- `aiask-quant-core` 包含 backtest、risk model、slippage、factor validation、strategy DSL、walk-forward、purged k-fold、bootstrap、deflated Sharpe、PBO 等更偏研究生产的能力。
- Strategy Factory 有 public facade、scheduler、quality gates、submission gate、dedup/elimination、domain events、promotion thresholds。

### 5.2 AIASK 当前主要短板

缺少 OpenBB 式统一 provider 标准模型层：

- 当前数据源优先级清晰，但工具层和数据层之间缺少统一 `StandardModel -> ProviderFetcher -> Result` 规范。
- 不同工具的返回字段、source metadata、quality metadata 一致性依赖各工具自觉维护。

工具契约重复：

- AKShare MCP 有 `tools/tool_catalog.py`。
- AKShare MCP `tools/search.py` 还有 runtime inference 和 category map。
- Agent 有 `tools/catalog.py` 和 `tools/schemas.py`。
- Desktop 有 `types.ts`、`aiaskApi.ts`、各 feature panel 的表单和渲染逻辑。
- 这几处一旦不一致，模型、MCP、Desktop 会看到不同的“同一个工具”。

部分契约仍依赖运行时推断：

- `search.py` 通过 module name、manager name、tool name token 推断 category/freshness。
- 这在工具数量少时可行，但随着工具增长会变脆；OpenBB 的做法是尽量从标准模型和路由/registry 派生。

Agent HTTP surface 过集中：

- `packages/agent/src/aiask_agent/server.py` 约 2453 行，聚合 health、tools、desktop、AI、responses、runs、Hermes、MCP、skills、plugins、jobs、terminal、browser 等大量路由。
- 继续增长会增加回归风险，尤其是 Desktop API 和 fallback/simple ASGI 逻辑需要保持一致时。

源码卫生问题：

- 当前 `packages/` 下发现约 90 个 `__pycache__` 目录、2251 个 `.pyc` 文件。
- 多个 AKShare 相关 Python 文件和测试存在 mojibake 中文字符串，影响审查、搜索、维护和用户可读性。

## 6. OpenBB 对 AIASK 的可借鉴清单

| OpenBB 做法 | AIASK 借鉴方式 | 注意事项 |
| --- | --- | --- |
| StandardModel 分离标准字段和 provider extra | 在 AKShare MCP 增加高频金融模型的标准 Query/Data | 不复制 OpenBB 模型代码，按 A 股语义自定义 |
| Fetcher TET 流程 | 把 TDX local、TDX online、Tushare、AKShare 包成统一 fetcher | 先包薄层，不重写现有 data_source |
| RegistryMap | 生成 model -> provider -> params/data/quality map | 保留 source priority 和 local-only 逻辑 |
| ProviderInterface | 从 registry 生成 Agent/MCP/Desktop 可消费 schema | 避免多处手写 schema 漂移 |
| OBBject | 设计 AIASK 的统一 financial result/envelope adapter | 保留 `aiask_envelope`、lineage、side_effect |
| PackageBuilder/reference.json | 生成 tool reference/contract assets | 先做只读生成，不自动改代码 |
| MCP CategoryIndex/discovery | 增强 Agent/MCP 工具 category/subcategory 和按需激活 | read-only 与 trade-risk 必须分层 |
| Desktop extension catalog | Desktop 从契约读取工具分类、参数、示例、风险等级 | Desktop 仍只走 Agent HTTP API |

## 7. 优化路线图

### Phase 0：文档与源码卫生清单

目标：

- 保留本文件作为 OpenBB 审查和 AIASK 优化路线的根目录基线。
- 单独建立源码卫生任务，处理 `.pyc/__pycache__` 和 mojibake。

建议动作：

- 确认 `.gitignore` 是否已经覆盖 `__pycache__/`、`*.pyc`。
- 清理非源码缓存文件，但不要改动业务逻辑。
- 对 AKShare MCP 中 mojibake 文件建立修复清单，优先处理 public docstring、测试断言文本、用户可见 description。

验收标准：

- 根目录存在本方案文档。
- 不包含密钥值。
- 不复制 OpenBB 源码实现。
- 后续任务能直接引用本文件拆分。

### Phase 1：建立 AIASK 自有 provider contract 薄层

目标：

- 不推翻现有 `data_source`，先在其上包一层标准契约。
- 覆盖最常用、最能形成统一质量基线的数据模型。

建议新增模块：

- `packages/akshare-mcp/src/akshare_mcp/provider_contracts/base.py`
- `packages/akshare-mcp/src/akshare_mcp/provider_contracts/models.py`
- `packages/akshare-mcp/src/akshare_mcp/provider_contracts/providers.py`
- `packages/akshare-mcp/src/akshare_mcp/provider_contracts/registry.py`
- `packages/akshare-mcp/src/akshare_mcp/provider_contracts/quality.py`

首批标准模型：

- `EquityQuoteQuery` / `EquityQuoteData`
- `EquityHistoricalQuery` / `EquityHistoricalData`
- `StockInfoQuery` / `StockInfoData`
- `TradingCalendarQuery` / `TradingCalendarData`

首批 provider wrapper：

- `TdxLocalProvider`
- `TdxOnlineProvider`
- `TushareProvider`
- `AkshareProvider`

关键规则：

- source priority 必须保持本地 TDX -> 在线 TDX -> Tushare/AKShare。
- `TDX_LOCAL_ONLY=1` 时禁止在线 fallback。
- 每个结果必须带 `source_chain`、`provider_used`、`provider_requested`、`fallback_used`、`fallback_reason`、`data_timestamp`、`freshness`、`quality.status`。
- 旧工具返回结构先保持兼容，新契约作为 meta 或 adapter 输出逐步引入。

验收标准：

- K 线、行情、交易日历至少各有一个 contract test。
- 原有 `test_data_source_tdx_routing.py` 行为不变。
- local-only 模式测试必须覆盖。

### Phase 2：收敛 MCP/Agent/Desktop 工具契约来源

目标：

- 减少 `tool_catalog.py`、`search.py` runtime inference、Agent `catalog.py`、Agent `schemas.py`、Desktop 表单之间的重复。

建议动作：

- 在 AKShare MCP 建立显式 tool contract registry，runtime inference 只作为 fallback。
- Agent 的 `TOOL_SCHEMAS` 从契约 registry 派生或校验，不再独立漂移。
- `/v1/tools` 增加可选 contract metadata 字段：`input_schema`、`output_schema`、`category`、`subcategory`、`freshness`、`side_effect`、`examples`、`source_contract_version`。
- Desktop 的工具表单和工具详情读取这些 metadata，而不是为每个金融工具手写字段。

兼容策略：

- 保留现有 `/v1/tools` 基本 shape。
- 新字段全部 optional，Desktop 渐进使用。
- 模型可见工具名仍必须是 `agent_*`。
- 不暴露 raw manager name 或 MCP stateful action。

验收标准：

- `agent_tool_catalog` 仍不泄露 forbidden manager tokens。
- `available_tools`、`get_tool_contract` 不作为模型可见 Agent 工具出现。
- Desktop 老 UI 在没有新 metadata 时仍能降级显示。

### Phase 3：模块化 Agent HTTP routes

目标：

- 降低 `server.py` 继续膨胀带来的维护风险。

建议拆分方向：

- `routes/health.py`
- `routes/tools.py`
- `routes/desktop.py`
- `routes/responses.py`
- `routes/runs.py`
- `routes/mcp.py`
- `routes/control.py`
- `routes/intents.py`

关键规则：

- 保留现有 app factory 行为。
- 保持 fallback/simple ASGI 路径兼容。
- `desktop/src/services/aiaskApi.ts` 依赖的 endpoint 不改名。
- 控制 token、API token、loopback/CORS 行为不弱化。

验收标准：

- `packages/agent/tests/test_server.py`、`test_desktop_capabilities_api.py`、`test_tool_registry.py` 通过。
- `/health/detailed`、`/v1/tools`、`/v1/desktop/capabilities`、`/v1/responses`、`/v1/mcp/*` 行为兼容。

### Phase 4：增强 Desktop 的契约驱动能力

目标：

- Desktop 不理解 Python/MCP 内部实现，只消费 Agent HTTP contract。

建议动作：

- 在 `desktop/src/services/aiaskApi.ts` 扩展 tool contract 类型。
- 在 capabilities/MCP/quant 面板中展示 freshness、source、side_effect、examples。
- 表单字段优先由 JSON schema 渲染，保留当前手写 workflow 面板。

验收标准：

- `cd desktop && npm test` 通过。
- `cd desktop && npm run typecheck` 通过。
- 没有 Desktop 直接 import Python 或调用 raw MCP manager。

### Phase 5：数据质量 gate 与多源对账

目标：

- 在 OpenBB 的结构质量基础上，加入 AIASK 更需要的业务质量。

建议动作：

- 对行情/K 线加入字段完整性、日期连续性、价格关系校验。
- 对 TDX/Tushare/AKShare 多源可用场景加入抽样对账。
- 输出 `quality.status`：`pass`、`degraded`、`stale`、`schema_mismatch`、`source_unavailable`。
- 为 quant/backtest 增加 hard gate：数据不足、过期、字段缺失时阻止高风险研究结论。

验收标准：

- `agent_data_validation`、`agent_quant_data_gate` 能显示 provider/source/freshness 证据。
- 数据不足时给出 remediation hint，不静默 fallback 成看似正常结果。

### Phase 6：发布与回滚策略

目标：

- 以低风险方式把 provider contract 引入现有系统。

建议策略：

- 先加 feature flag，例如 `AIASK_PROVIDER_CONTRACTS_ENABLED=1`。
- 首批工具双写 meta，不改变原始 `data` shape。
- Desktop 只读新 metadata，不依赖其必定存在。
- 出现兼容问题时关闭 feature flag 回到旧路径。

## 8. 公共接口影响

短期：

- 本文档创建不影响任何代码接口。

后续实现建议：

- AKShare MCP 新增 provider contract registry，但现有工具名和参数保持兼容。
- Agent `/v1/tools` 追加 metadata 字段，不破坏现有 `{ data: ToolCatalogItem[] }`。
- Desktop 类型新增可选字段。
- 所有 stateful/trade-risk 行为继续通过 ActionIntent 或 broker token guard。

禁止事项：

- 不允许把 raw manager name 暴露成模型可见工具。
- 不允许 Desktop 直接调用 MCP manager。
- 不允许在文档或代码里写入 `.env` 密钥值。
- 不允许复制 OpenBB AGPL 源码实现。

## 9. 测试与验收计划

文档阶段：

- 确认 `OPENBB_DEEP_REVIEW_AND_AIASK_OPTIMIZATION_PLAN.md` 位于仓库根目录。
- 检查章节包含 OpenBB 架构、数据质量、AIASK 对照、优化路线、接口影响、测试计划。
- 检查没有密钥值和大段 OpenBB 源码复制。

Provider contract 阶段：

- `cd packages/akshare-mcp && pytest -q tests/test_data_source_tdx_routing.py`
- `cd packages/akshare-mcp && pytest -q tests/test_tool_argument_contract.py`
- `cd packages/akshare-mcp && pytest -q tests/test_tool_catalog_vector_contracts.py`
- 新增 provider contract tests，覆盖 TDX local、TDX online fallback、local-only 禁止 fallback、schema mismatch。

Agent contract 阶段：

- `cd packages/agent && pytest -q tests/test_tool_registry.py`
- `cd packages/agent && pytest -q tests/test_server.py`
- `cd packages/agent && pytest -q tests/test_desktop_capabilities_api.py`
- 或运行 `make test-agent`。

Desktop 阶段：

- `cd desktop && npm test`
- `cd desktop && npm run typecheck`

金融安全阶段：

- `cd packages/finance-mcp-servers && pytest -q tests/test_trade_guard.py`
- 验证 live order/cancel 缺少 broker token 时仍失败。
- 验证 read-only tool 不需要 ActionIntent。
- 验证 stateful financial action 仍要求 durable intent。

## 10. 优先级建议

P0：

- 保留本审查文档作为根目录决策基线。
- 清理 `.pyc/__pycache__` 与 mojibake 清单。
- 不触碰交易安全边界。

P1：

- 建立 AKShare MCP provider contract 薄层。
- 先覆盖 `EquityQuote`、`EquityHistorical`、`TradingCalendar`、`StockInfo`。
- 把 source/freshness/quality/source_chain 标准化。

P2：

- 统一 MCP tool contract、Agent schema、Desktop metadata。
- 将 runtime inference 降级为 fallback。

P3：

- 拆分 Agent `server.py` routes。
- Desktop 增强 schema-driven 工具渲染。

P4：

- 引入多源对账和更严格 quant data gates。
- 把 provider contract 扩展到财务、资金流、行业、宏观、期权等领域。

## 11. 最终建议

AIASK 不应该简单变成 OpenBB 的 A 股版本。更好的方向是：

- 用 OpenBB 的标准化 provider 架构解决工具和数据契约分散问题。
- 保留 AIASK 的本地数据源优先级、金融安全、交易防护、量化研究和 Strategy Factory 能力。
- 让 AKShare MCP 成为数据与工具契约的权威来源。
- 让 Agent 成为模型可见安全门面。
- 让 Desktop 成为契约驱动的操作台。

这样既能降低未来工具增长带来的维护成本，也能让数据质量、来源、freshness、side effect 在模型、API、桌面端之间保持一致。
