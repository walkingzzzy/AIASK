# OpenBB 借鉴方案可行性全量审查报告

审查日期：2026-05-20

关联方案文档：`OPENBB_DEEP_REVIEW_AND_AIASK_OPTIMIZATION_PLAN.md`

## 1. 总体结论

结论：方案可行，建议按原计划分阶段实施；其中 Phase 1 和 Phase 2 是最高价值入口，Phase 3 需要更谨慎拆分。

可行性的核心依据：

- AKShare MCP 已经有清晰的数据源优先级、fallback 行为、freshness/quality/source metadata 雏形，可以在现有 data source 外包一层 provider contract，而不需要重写数据源。
- Agent 已经有 `agent_*` 工具边界、tool registry、OpenAI schema 输出、`/v1/tools` catalog payload、read-only Desktop API gate，可兼容增加 contract metadata。
- Desktop 已经通过 `aiaskApi.ts` 消费 Agent HTTP API，`ToolCatalogItem.parameters` 已是可选字段，可以扩展 `input_schema/output_schema/freshness/examples` 等字段而不破坏现有界面。
- 交易安全边界已有测试保护：ActionIntent 和 broker token guard 都适合作为后续改造的不可回退红线。
- 现有测试能覆盖关键风险面；本次抽跑的契约、数据源、交易防护、桌面工具目录测试均通过。

主要风险：

- Agent `server.py` 约 2453 行，路由拆分有较高回归风险，必须晚于 provider contract 和 schema bridge。
- 工具契约当前分散在 AKShare MCP `tool_catalog.py`、`search.py` runtime inference、Agent `catalog.py`、Agent `schemas.py`、Desktop 类型和面板中，Phase 2 必须以“兼容校验桥”开局，不能一步替换。
- `packages/` 下仍有约 90 个 `__pycache__` 目录和 2257 个 `.pyc` 文件，多处 Python 文件存在 mojibake 文本，会干扰长期维护。
- 默认 `python` 是 3.11.8，而 Agent/AKShare MCP 要求 Python >=3.12；本机存在 uv 管理的 Python 3.12.13，因此不是技术阻塞，但执行测试/开发命令时要显式使用正确环境。

## 2. 本次审查覆盖

本次按“方案实施链路”审查，而不是只审查单个文件：

- 数据源层：`packages/akshare-mcp/src/akshare_mcp/data_source/`
- MCP 工具层：`packages/akshare-mcp/src/akshare_mcp/tools/`
- MCP server：`packages/akshare-mcp/src/akshare_mcp/server.py`
- Agent 工具注册和策略：`packages/agent/src/aiask_agent/tool_registry.py`、`tools/policy.py`、`tools/schemas.py`、`tools/catalog.py`
- Agent HTTP API：`packages/agent/src/aiask_agent/server.py`
- Agent MCP wrapper 和风险识别：`mcp_client.py`、`tool_risk.py`
- Desktop API 和类型：`desktop/src/services/aiaskApi.ts`、`desktop/src/types.ts`
- Desktop 工具目录 UI：`desktop/src/components/InspectorPanels.tsx`
- 交易防护：`packages/finance-mcp-servers/src/aiask_finance_mcp/_shared/trade_guard.py`
- 现有测试：Agent registry/server、AKShare tool catalog/data source、finance trade guard、Desktop tool catalog。

规模核验：

- AIASK 当前 `packages + desktop` 下约 1046 个 Python/TypeScript/TSX 文件。
- 关键文件行数：
  - `packages/agent/src/aiask_agent/server.py`：2453 行。
  - `packages/agent/src/aiask_agent/tool_registry.py`：627 行。
  - `packages/agent/src/aiask_agent/tools/schemas.py`：893 行。
  - `packages/agent/src/aiask_agent/tools/catalog.py`：810 行。
  - `packages/akshare-mcp/src/akshare_mcp/server.py`：522 行。
  - `packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog.py`：875 行。
  - `packages/akshare-mcp/src/akshare_mcp/data_source/market_data.py`：877 行。
  - `desktop/src/services/aiaskApi.ts`：317 行。
  - `desktop/src/types.ts`：494 行。

## 3. Phase 0 可行性：文档和源码卫生

结论：可行，低风险，应先做。

依据：

- 根目录方案文档已经存在。
- `.pyc/__pycache__` 数量明确，清理可以作为纯卫生任务，不影响业务行为。
- mojibake 已出现在 package metadata、docstring、测试文本、用户可见 description 等位置，适合分批修复。

建议执行顺序：

1. 确认 `.gitignore` 覆盖 `__pycache__/`、`*.pyc`、临时日志。
2. 清理缓存文件。
3. 对 AKShare MCP 的用户可见文本和测试文本建立 mojibake 修复清单。
4. 不在本阶段重构工具或数据源。

阻塞项：无。

## 4. Phase 1 可行性：AKShare MCP provider contract 薄层

结论：可行，中低风险，是最适合第一批实施的代码改造。

依据：

- `data_source/__init__.py` 已经通过 `DataSourceManager` 聚合 `QuotesMixin`、`MarketDataMixin`、`TdxQCenterMixin`。
- `quotes.py` 已有 K 线和实时行情的 TDX local-only、tqcenter、tdx_local、Tushare/legacy fallback 分支。
- `market_data.py` 已经返回 `source`、`backend_requested`、`backend_used`、`fallback_used`、`fallback_reason`、`freshness_sec`、`quality_flags` 等质量/来源字段。
- `data_quality.py` 已经有 `build_quality_meta`、freshness 计算、fallback 标记、quality flags，可复用为 provider contract 的质量元数据基础。
- `test_data_source_tdx_routing.py` 已经覆盖 tqcenter 优先、tdx_local fallback、local-only/legacy disabled、实时行情关键字段、交易日期等行为。

推荐实施方式：

- 新增 `packages/akshare-mcp/src/akshare_mcp/provider_contracts/`，不要改动现有 `data_source` 主逻辑。
- 首批只覆盖 4 个模型：`EquityQuote`、`EquityHistorical`、`StockInfo`、`TradingCalendar`。
- provider wrapper 只做适配和标准化，不直接发明新数据源优先级。
- 旧工具返回 `data` shape 保持兼容，把新 provider contract 结果先放入 `meta` 或 adapter 输出中。

必须保留：

- `TDX_LOCAL_ONLY=1` 禁止在线 fallback。
- Tushare lazy load。
- SQLite path/env 行为不硬编码。
- 工具 envelope 中保留 source_chain/fallback/quality。

主要风险：

- `DataSourceManager` 是 singleton，测试中需要重置 `_instance`，新增 contract 测试也要隔离环境变量。
- 历史行情和交易日历的日期格式不完全统一，需要 contract 中明确 ISO/原始格式转换边界。
- 不要在 provider wrapper 内触发大规模同步或网络 fallback。

## 5. Phase 2 可行性：统一工具契约来源

结论：可行，中等风险，收益很高，但必须渐进。

依据：

- AKShare MCP 已有显式 `TOOL_CONTRACTS`，`list_tool_contracts()` 和 `get_tool_contract()` 已可返回工具契约。
- AKShare MCP `search.py` 仍支持 runtime inferred contract，并用 `inferred_from_runtime=True` 标记退化来源。
- Agent `tool_registry.py` 注册工具时已经把 `TOOL_SCHEMAS[name]` 和 metadata 合并进 registry。
- Agent `server.py` 的 `tool_catalog_payload()` 已经从 `selected.tool_registry.openai_tools()` 反查 schema，并把 `parameters` 注入 `/v1/tools` 返回。
- Desktop `ToolCatalogItem` 已有 `parameters?: Record<string, unknown>`，工具目录 UI 已基于 category/status/side_effect 做筛选。

推荐实施方式：

1. 不直接删除 Agent `TOOL_SCHEMAS`。
2. 先新增 contract sync/check 测试：验证 Agent schema 和 AKShare MCP tool contract 的关键字段不冲突。
3. `/v1/tools` 增加 optional 字段：`input_schema`、`output_schema`、`freshness`、`examples`、`contract_version`、`contract_source`。
4. Desktop 类型先加 optional 字段，UI 先只展示，不依赖字段必定存在。
5. Runtime inferred contract 继续保留，但在 UI/日志中标记 degraded。

主要风险：

- 当前 Agent catalog 和 schemas 都是手写，直接切到生成式 contract 容易破坏工具可见性。
- MCP tool 名和 Agent wrapper 名并非一一相同，映射层要明确 `raw_tool_name -> agent_* wrapped_name`。
- `available_tools`、`get_tool_contract` 不能作为模型可见 Agent 工具泄露。

## 6. Phase 3 可行性：拆分 Agent routes

结论：可行，但风险最高，建议排在 Phase 1/2 后。

依据：

- `server.py` 已经集成 app factory、FastAPI routes、fallback/simple ASGI path、auth、CORS、Desktop routes、MCP routes、Hermes/full control routes。
- `test_server.py` 已覆盖 health、chat/completions、Desktop CORS、`/v1/tools`、read-only tool API、ActionIntent、Hermes full mode control gate。
- 现有 `desktop/src/services/aiaskApi.ts` endpoint 很集中，可以作为兼容性清单。

推荐实施方式：

- 先抽纯函数，不先移动 route 行为。
- 每次只拆一个 route group，例如 health/tools，再跑 Agent server tests。
- 保留 `build_server()` 对外行为。
- fallback/simple ASGI path 要和 FastAPI path 同步验证。

主要风险：

- 控制 token/API token 行为在多个 route group 复用，拆分时很容易漏 gate。
- `/v1/tools/{tool_name}` read-only gate 是关键安全边界，不能被通用 tool call route 绕过。
- Desktop 和测试依赖 endpoint 名称，不建议改 URL。

## 7. Phase 4 可行性：Desktop 契约驱动展示

结论：可行，中低风险。

依据：

- Desktop 已只通过 Agent HTTP API 获取 tools/capabilities/MCP/quant/factory 数据。
- `ToolCatalogItem.parameters` 已存在，新增 optional metadata 不会破坏现有消费。
- 工具目录 UI 已有 category/status/side_effect 筛选，适合自然加入 freshness、contract_source、examples 展示。
- 相关 Vitest 本次运行通过。

推荐实施方式：

- 先扩展 `desktop/src/types.ts`。
- 再在 `ToolCatalog` 中展示 provider/source/freshness/contract_source。
- JSON schema 表单渲染放后，不要第一步就替换现有 workflow 面板。

主要风险：

- 大 schema 直接展示会让 UI 变噪，应该摘要展示，详情折叠。
- control token 相关接口仍要维持降级 UI，不能因为 contract metadata 缺失而报错。

## 8. Phase 5 可行性：数据质量 gate 与多源对账

结论：可行，中等风险，适合在 provider contract 稳定后做。

依据：

- 已有 `data_quality.py` 和 `db_freshness.py`。
- `agent_data_validation`、`agent_quant_data_gate` 已是 Agent facade 中的 read-only 金融工具。
- `manager_protocol.py` 已有 `quality`、`lineage`、`side_effect`、`data_timestamp`、`degraded` 元数据位置。

推荐实施方式：

- 先做字段完整性、日期连续性、价格关系校验。
- 多源对账只在显式允许时运行，避免默认触发慢网络。
- quality status 使用有限枚举：`pass`、`degraded`、`stale`、`schema_mismatch`、`source_unavailable`。
- quant/backtest gate 先报阻断原因和 remediation hint，不自动修复。

主要风险：

- 外部数据源可用性不稳定，测试必须使用 monkeypatch/fake provider。
- 多源对账可能导致延迟变高，不能默认阻塞所有行情读取。

## 9. 实际验证结果

已执行并通过：

- `pytest -q packages/finance-mcp-servers/tests/test_trade_guard.py`
  - 结果：5 passed。
  - 覆盖：broker token 缺失、错误、匹配、trade_risk envelope。

- `pytest -q packages/akshare-mcp/tests/test_tool_catalog_vector_contracts.py`
  - 结果：2 passed。
  - 覆盖：显式 tool contract、contract_version、非 runtime inferred。

- `pytest -q packages/agent/tests/test_tool_registry.py`
  - 结果：2 passed。
  - 覆盖：`agent_*` allowlist、禁止 manager token 泄露、ActionIntent envelope。

- `pytest -q packages/akshare-mcp/tests/test_data_source_tdx_routing.py`
  - 结果：14 passed。
  - 覆盖：tqcenter、tdx_local、local-only/legacy disabled、实时行情关键字段、交易日期等。

- `npm.cmd test -- ToolCatalog.test.tsx`
  - 结果：8 test files passed，12 tests passed。
  - 覆盖：Desktop 工具目录相关 jsdom 测试集合。

注意：

- 直接运行 `npm` 在 PowerShell 下被执行策略拦截，改用 `npm.cmd` 后通过。
- 以上 Python 测试使用当前环境 + `PYTHONPATH` 指向本地包源码运行；默认 `python` 是 3.11.8，但本机有 uv Python 3.12.13，正式开发建议使用 uv/3.12 环境。

## 10. Go / No-Go 判断

Go：

- Phase 0 立即可做。
- Phase 1 可作为第一批开发任务。
- Phase 2 可在 Phase 1 首批模型稳定后启动。
- Phase 4 可以和 Phase 2 后半段并行做展示增强。

Conditional Go：

- Phase 3 route 拆分需要先冻结 endpoint 兼容清单，并按 route group 小步提交。
- Phase 5 多源对账要等 provider contract 输出稳定后再做。

No-Go：

- 不建议直接复制 OpenBB provider/fetcher 代码。
- 不建议一次性把 Agent `TOOL_SCHEMAS` 全部替换成生成式 schema。
- 不建议在 provider contract wrapper 内默认触发网络全量同步。
- 不建议在 Desktop 中绕过 Agent 直接调用 MCP/manager。
- 不建议在 route 拆分时同时改 auth、tool policy、ActionIntent。

## 11. 推荐落地顺序

1. `Phase 0A`：清理 `.pyc/__pycache__`，确认 `.gitignore`。
2. `Phase 0B`：修复最影响维护的 mojibake 文本，优先 package metadata、public docstring、测试名/断言信息。
3. `Phase 1A`：新增 provider contract 基础类型和 registry，不接入旧工具。
4. `Phase 1B`：接入 `EquityQuote` 和 `EquityHistorical`，只补 meta，不改变 data shape。
5. `Phase 1C`：接入 `TradingCalendar` 和 `StockInfo`。
6. `Phase 2A`：新增 Agent/MCP contract consistency tests。
7. `Phase 2B`：扩展 `/v1/tools` optional contract metadata。
8. `Phase 4A`：Desktop 类型和工具目录展示新增 metadata。
9. `Phase 3A`：在行为冻结后拆 Agent health/tools routes。
10. `Phase 5A`：增加数据质量 gate 和抽样多源对账。

## 12. 最终确认

开发方案具备工程可行性。它和当前 AIASK 架构的关系不是“外部大改造”，而是把已经存在的 source/fallback/quality/side_effect 能力补上一层明确、可测试、可生成的 contract spine。

最关键的成功条件：

- 先薄层适配，不重写数据源。
- 先增加 optional metadata，不破坏现有 API。
- 先做一致性测试，不直接删除旧 schema。
- 始终保留 `agent_*`、Desktop 经 Agent HTTP、ActionIntent、broker token 这些金融安全边界。
