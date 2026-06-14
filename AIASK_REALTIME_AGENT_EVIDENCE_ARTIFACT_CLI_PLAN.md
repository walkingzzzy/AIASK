# AIASK Realtime Agent Evidence, Artifact and CLI Development Plan

日期: 2026-06-12

状态: 开发方案。本文档先完成代码现状核验、联网资料对比、差距定位和实施路线。按照用户要求，本阶段不开始功能代码开发。

## 1. 问题定义

当前 AIASK 已经具备 AI 对话、工具调用、会话、运行事件、部分金融工具、文件/终端工具、数据源设置和 TUI 能力，但产品体验仍容易停留在“AI 在聊天框里回答”：

- 实时股票行情、新闻、数据来源链没有稳定变成会话中的可视化卡片和可追溯证据。
- 新闻链接、发布时间、来源站点、抓取时间没有统一成一等 citation/source 对象。
- 文件、代码、脚本、终端输出等生成结果没有像 Hermes Agent 的 deliverables 一样被稳定记录、复用、导出和在桌面端/CLI 中浏览。
- Agent run 虽有事件，但缺少“数据源 -> 工具调用 -> 来源证据 -> 产物 -> UI/CLI 展示”的完整链路。
- CLI/TUI 能力还没有形成可脚本化、可查看 artifacts/sources/runs 的统一入口。

本方案的核心判断是：AIASK 不是没有底层能力，而是缺少统一的 evidence/artifact/source 数据模型、运行期抽取器、HTTP API、Desktop 展示和 CLI 消费层。

## 2. 代码证据

以下证据来自当前仓库实查，路径均相对仓库根目录。

### 2.1 Agent 已有会话、响应、运行和事件存储

- `packages/agent/src/aiask_agent/session_store.py:167` 创建 `sessions` 表。
- `packages/agent/src/aiask_agent/session_store.py:175` 创建 `messages` 表。
- `packages/agent/src/aiask_agent/session_store.py:188` 创建 `responses` 表。
- `packages/agent/src/aiask_agent/session_store.py:195` 创建 `runs` 表。
- `packages/agent/src/aiask_agent/session_store.py:203` 创建 `run_events` 表。
- `packages/agent/src/aiask_agent/session_store.py:594` 存储 response。
- `packages/agent/src/aiask_agent/session_store.py:636` 创建 run。
- `packages/agent/src/aiask_agent/session_store.py:705` 追加 run event。
- `packages/agent/src/aiask_agent/session_store.py:1422` 已有 session/search 能力。

结论: 持久会话和 run event 基础存在，可以在其上补 artifacts/sources，而不应另造一套平行会话系统。

### 2.2 Agent 已有 tool invocation 审计，但还没有一等 artifact/source

- `packages/agent/src/aiask_agent/session_store.py:249` 已创建 `tool_invocations` 表。
- `packages/agent/src/aiask_agent/session_store.py:926` `start_tool_invocation()` 记录工具名、参数摘要、run/session/trace、side effect 和 source chain。
- `packages/agent/src/aiask_agent/session_store.py:988` `finish_tool_invocation()` 写入输出摘要、错误、耗时和审批信息。
- `packages/agent/src/aiask_agent/session_store.py:1049` 可按 user/session/run/tool 查询 invocation。

结论: `tool_invocations` 应复用为链路中“工具调用账本”。缺口是 `agent_artifacts` 与 `agent_sources`，以及从 tool result 中抽取它们。

### 2.3 Runtime 已发 run event，但事件粒度不够产品化

- `packages/agent/src/aiask_agent/runtime.py:45` 定义 `AgentRunResult`。
- `packages/agent/src/aiask_agent/runtime.py:148` `run()` 驱动模型、工具循环和持久化。
- `packages/agent/src/aiask_agent/runtime.py:379` 发出 `tool.started`。
- `packages/agent/src/aiask_agent/runtime.py:486` 发出 `tool.completed` / `tool.failed`。
- `packages/agent/src/aiask_agent/runtime.py:336`、`:434` 附近将 `tool_call_record["result"]` 存入响应 metadata。
- `packages/agent/src/aiask_agent/runtime.py:531`、`:532` 附近保存 response/run。

结论: 当前 run event 可用于时间线，但没有生成 `artifact.created`、`source.linked`、`market.quote_snapshot`、`news.source_linked` 这类 UI 友好的事件。

### 2.4 代码执行目前使用临时脚本，不适合作为长期产物

- `packages/agent/src/aiask_agent/runtime.py:729` 注册 `agent_execute_python`。
- `packages/agent/src/aiask_agent/runtime.py:759` 使用 `tempfile.TemporaryDirectory(prefix="aiask_agent_code_")`。
- `packages/agent/src/aiask_agent/general_tools.py:647` 也会把执行链路标记到 `aiask_agent.general_tools.execute_python`。

结论: Python 执行能力存在，但 snippet 文件默认随临时目录消失。若要接近 Hermes Agent 的 deliverables，需要把脚本、stdout/stderr 摘要、生成文件路径、hash、preview 持久化为 artifact。

### 2.5 Agent HTTP API 已有 responses/runs/events/search/terminal/data-source 入口

- `packages/agent/src/aiask_agent/server.py:2610` GET `/v1/desktop/stock-data-sources`。
- `packages/agent/src/aiask_agent/server.py:2615` POST `/v1/desktop/stock-data-sources`。
- `packages/agent/src/aiask_agent/server.py:2625` POST `/v1/desktop/stock-data-sources/test`。
- `packages/agent/src/aiask_agent/server.py:2876` POST `/v1/tools/{tool_name}`。
- `packages/agent/src/aiask_agent/server.py:3001` POST `/v1/responses`。
- `packages/agent/src/aiask_agent/server.py:3051` GET `/v1/runs/{run_id}/events`。
- `packages/agent/src/aiask_agent/server.py:3057` GET `/v1/runs/{run_id}/events/stream`。
- `packages/agent/src/aiask_agent/server.py:3098` GET `/v1/search`。
- `packages/agent/src/aiask_agent/server.py:3219` GET `/v1/terminal/backends`。
- `packages/agent/src/aiask_agent/server.py:3224` GET `/v1/terminal/sessions`。

结论: Desktop 已有 HTTP 合同骨架。新增 artifact/source API 应放在 Agent HTTP，不允许 Desktop 直连 AKShare/MCP/Python。

### 2.6 金融与通用工具已在 `agent_*` facade 下

- `packages/agent/src/aiask_agent/tools/catalog.py:16` `agent_analyze_stock`。
- `packages/agent/src/aiask_agent/tools/catalog.py:65` `agent_quant_research_run`，描述中已经提到 persist report artifact。
- `packages/agent/src/aiask_agent/tools/catalog.py:205` `agent_stock_radar_status`。
- `packages/agent/src/aiask_agent/tools/catalog.py:250` `agent_file_write`。
- `packages/agent/src/aiask_agent/tools/catalog.py:271` `agent_file_patch`。
- `packages/agent/src/aiask_agent/tools/catalog.py:306` `agent_terminal`。
- `packages/agent/src/aiask_agent/tools/catalog.py:432` `agent_web_search`。
- `packages/agent/src/aiask_agent/tools/catalog.py:439` `agent_web_extract`。
- `packages/agent/src/aiask_agent/tools/catalog.py:915` `agent_memory_search`。
- `packages/agent/src/aiask_agent/tools/catalog.py:929` `agent_session_search`。

结论: 新能力必须继续走 `agent_*` 门面，例如 `agent_stock_live_quote`、`agent_stock_news_digest`、`agent_market_snapshot`，不能把原始 MCP/manager 名称暴露给模型。

### 2.7 数据源配置已覆盖行情和搜索供应商

- `packages/agent/src/aiask_agent/stock_data_sources.py:21` 定义 `SEARCH_PROVIDERS = {"duckduckgo", "tavily", "brave_search", "serpapi", "exa"}`。
- 同文件包含 AKShare、Tushare、Baostock、TDX、Eastmoney、QMT、Alpha Vantage、Finnhub、Twelve Data、Polygon/Massive、Nasdaq Data Link、DuckDuckGo、Tavily、Brave Search、SerpApi、Exa 等 preset。
- `packages/agent/src/aiask_agent/stock_data_sources.py:433` list 数据源。
- `packages/agent/src/aiask_agent/stock_data_sources.py:469` save 数据源。
- `packages/agent/src/aiask_agent/stock_data_sources.py:719` test 数据源。

结论: 数据源管理初步具备。短板不是“没有可配数据源”，而是没有把配置结果接到每次 agent run 的 quote/news/source/artifact 展示链路。

### 2.8 AKShare MCP 已有实时行情和来源链

- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:326` `get_realtime_quote()`。
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:66`、`:67` 处理 `attempted_sources` 与 `source_chain`。
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:83`、`:84` 写入 `fallback_reason` 与 `data_timestamp`。
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:104` 以后附加 provider contract metadata。
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:397` 以后会记录 db、akshare、sina、tencent 等尝试链。

结论: 实时行情并非缺失；需要 Agent facade、证据抽取和前端卡片展示。

### 2.9 新闻工具和财经 MCP 已有基础，但链接需标准化

- `packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py:30` `get_stock_news()`。
- `packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py:152` `get_market_news()`。
- `packages/finance-mcp-servers/src/aiask_finance_mcp/eastmoney/server.py:53` `em_realtime_quote` handler。
- `packages/finance-mcp-servers/src/aiask_finance_mcp/eastmoney/server.py:165` `em_news_flow` handler。
- `packages/finance-mcp-servers/src/aiask_finance_mcp/tongdaxin/server.py:283` `tdx_realtime_quote` handler。

结论: 新闻/行情后端来源存在，但需要统一成 `{title,url,provider,published_at,fetched_at,excerpt,source_type}`，并避免只把原始 JSON 藏在 payload 里。

### 2.10 Desktop 已有时间线和产物面板，但产物是派生的

- `desktop/src/components/TaskPanels.tsx:23` `buildTaskArtifacts()`。
- `desktop/src/components/TaskPanels.tsx:64` 将 `response.metadata.tool_calls` 派生成工具调用产物。
- `desktop/src/components/TaskPanels.tsx:79` 将 recent run 派生成 run 产物。
- `desktop/src/components/Timeline.tsx:72` `buildTimeline()`。
- `desktop/src/components/Timeline.tsx:106` 将 `response.metadata.tool_calls` 放入 timeline。
- `desktop/src/hooks/useAgentWorkbench.ts:284` 加载 run events。
- `desktop/src/services/aiaskApi.ts:362` 调 `/v1/runs/{run_id}/events`。

结论: UI 容器已经有，但缺稳定后端 artifact/source API 和类型。现有 artifact panel 主要是“从响应和事件推断”，不是 durable artifact library。

### 2.11 CLI/TUI 只有部分能力

- `packages/agent/src/aiask_agent/tui.py:17` 至 `:26` 支持 `/tools`、`/sessions`、`/stop`、`/steer`、`/skills`、`/approvals`、`/undo`、`/rollback`。
- `packages/agent/src/aiask_agent/tui.py:235` TUI 通过 `/v1/responses` 发起响应。
- `packages/agent/src/aiask_agent/tui.py:321` 渲染 run timeline。
- `packages/agent/pyproject.toml:39` 目前只暴露 `aiask-agent = "aiask_agent.server:main"`。

结论: TUI 存在但不是完整 CLI。应新增 `aiask = aiask_agent.cli:main` 或兼容扩展 `aiask-agent` 子命令，支持脚本化 run、follow、artifacts、sources、data-sources。

## 3. 联网资料与外部对比

联网资料用于确定行业实现方向，不替代当前代码事实。

- Hermes Agent Desktop 文档: [https://hermes-agent.nousresearch.com/docs/user-guide/desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop)。文档展示 Hermes 的桌面代理强调文件/浏览器/终端/长期任务一体化，用户关注的是可见任务过程和 deliverables，而不只是聊天回答。
- Hermes Agent v2026.6.5 release: [https://github.com/NousResearch/hermes-agent/releases/tag/v2026.6.5](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.6.5)。可作为产品对标参考，但 AIASK 应按金融数据和安全边界做自己的 evidence/artifact 模型。
- MCP Tools 官方文档: [https://modelcontextprotocol.io/docs/concepts/tools](https://modelcontextprotocol.io/docs/concepts/tools)。MCP 将 tools 定义为模型可发现、可调用的能力，AIASK 的 `agent_*` facade 应继续作为模型可见工具边界，原始 MCP 工具不直接泄露给 Desktop 或模型。
- OpenAI Agents SDK Tracing: [https://openai.github.io/openai-agents-python/tracing/](https://openai.github.io/openai-agents-python/tracing/)。tracing 思路证明 agent run 应可观察、可分段追踪；AIASK 的 run_events/tool_invocations 可以扩展为更完整的 trace/evidence 层。
- OpenAI Agents SDK Sessions: [https://openai.github.io/openai-agents-python/sessions/](https://openai.github.io/openai-agents-python/sessions/)。session 记录历史上下文，AIASK 已有 session_store，应在同一 store 中补 source/artifact，而不是旁路保存。
- AKShare 官方介绍: [https://akshare.akfamily.xyz/introduction.html](https://akshare.akfamily.xyz/introduction.html)。AKShare 是开源金融数据接口库，适合继续作为本地/开源数据入口之一。
- Tushare Pro 数据文档: [https://tushare.pro/document/1?doc_id=40](https://tushare.pro/document/1?doc_id=40)。Tushare 是可配置数据源，适合纳入 provider registry 和 freshness/fallback 展示。
- Alpha Vantage 文档: [https://www.alphavantage.co/documentation/](https://www.alphavantage.co/documentation/)。其 API 提供行情和技术指标等接口，但有 key/rate limit，适合作为可选在线源。
- Finnhub quote API: [https://finnhub.io/docs/api/quote](https://finnhub.io/docs/api/quote)。适合美股实时 quote 补充源，需显示 provider 和 timestamp。
- Twelve Data 文档: [https://twelvedata.com/docs](https://twelvedata.com/docs)。适合作为多市场数据补充源，需要 key、额度和 provider 标记。
- Polygon/Massive REST quickstart: [https://massive.com/docs/rest/quickstart](https://massive.com/docs/rest/quickstart)。适合作为美股/市场数据可选源，必须记录订阅级别与延迟风险。
- Nasdaq Data Link 文档: [https://docs.data.nasdaq.com/](https://docs.data.nasdaq.com/)。更适合宏观、基本面、历史数据类补充，不应被误称为全部实时。
- Tavily Search API: [https://docs.tavily.com/documentation/api-reference/endpoint/search](https://docs.tavily.com/documentation/api-reference/endpoint/search)。搜索结果天然包含 URL、title、content/excerpt，应映射为 `agent_sources`。
- Brave Search API: [https://api-dashboard.search.brave.com/app/documentation/web-search/get-started](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started)。可作为 web/news source provider，结果链接必须作为 citation 保存。
- SerpApi Search API: [https://serpapi.com/search-api](https://serpapi.com/search-api)。可作为搜索聚合源，注意付费与 provider 标识。
- Exa Search API: [https://docs.exa.ai/reference/search](https://docs.exa.ai/reference/search)。适合语义搜索/网页链接来源，需要统一映射 title/url/published/excerpt。

外部资料给出的方向是：Agent 产品必须让工具调用、来源、文件、浏览器/终端动作和最终 deliverable 可见、可追踪、可复用。AIASK 的实现应利用已有 Agent HTTP、session_store、tool_invocations 和 AKShare/Finance MCP，不要把 Desktop 改成直接调用外部 API。

## 4. 目标架构

目标链路:

```text
StockDataSource Registry
  -> AKShare MCP / Finance MCP / Quant Core / Search Providers
  -> Agent agent_* facade tools
  -> Runtime tool invocation ledger
  -> Evidence extractor
  -> agent_sources + agent_artifacts
  -> run_events enriched events
  -> Desktop Timeline / Artifacts / Sources / Finance Cards
  -> CLI/TUI same APIs
```

边界规则:

- Desktop 只能调用 Agent HTTP API。
- 模型可见工具必须是 `agent_*`。
- 原始 MCP/manager/stateful 动作不直接暴露。
- 交易、外部平台、持久副作用继续走 ActionIntent/control-token 守护。
- 数据采集和存储归 AKShare MCP / Quant Core；Agent 负责编排、审计、证据抽取和 HTTP 输出；Desktop 负责展示。

## 5. 数据模型方案

### 5.1 复用 `tool_invocations`

现有 `tool_invocations` 保留为工具调用账本。建议补充或规范以下字段使用:

- `invocation_id`: 等于 OpenAI/tool_call_id，贯穿 run event、artifact、source。
- `session_id`, `run_id`, `trace_id`: 关联会话、运行和 trace。
- `input_summary_json`, `output_summary_json`: 继续使用 `sanitize_for_audit()`，避免泄露 secrets。
- `source_chain_json`: 保存工具级来源链，例如 `["aiask_agent.runtime","akshare_mcp.quote","sina"]`。
- `side_effect`: 保持 read_only/code_execution/filesystem_write/process_control 等风险等级。

### 5.2 新增 `agent_sources`

建议表结构:

```sql
CREATE TABLE IF NOT EXISTS agent_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL UNIQUE,
  user_id TEXT,
  session_id TEXT,
  run_id TEXT,
  trace_id TEXT,
  tool_call_id TEXT,
  tool_name TEXT,
  provider TEXT,
  source_type TEXT NOT NULL,
  title TEXT,
  url TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  data_timestamp TEXT,
  excerpt TEXT,
  source_tier TEXT,
  credibility_score REAL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
```

`source_type` 建议值:

- `market_quote`
- `news`
- `announcement`
- `research_report`
- `web_search`
- `web_extract`
- `data_provider`
- `local_db`
- `generated`

### 5.3 新增 `agent_artifacts`

建议表结构:

```sql
CREATE TABLE IF NOT EXISTS agent_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  artifact_id TEXT NOT NULL UNIQUE,
  user_id TEXT,
  session_id TEXT,
  run_id TEXT,
  trace_id TEXT,
  tool_call_id TEXT,
  tool_name TEXT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  path TEXT,
  uri TEXT,
  mime_type TEXT,
  size_bytes INTEGER,
  sha256 TEXT,
  preview_text TEXT,
  preview_json TEXT NOT NULL DEFAULT '{}',
  source_id TEXT,
  status TEXT NOT NULL DEFAULT 'ready',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

`kind` 建议值:

- `file`
- `code`
- `script`
- `terminal_output`
- `quote_snapshot`
- `news_digest`
- `research_report`
- `chart`
- `table`
- `screenshot`
- `patch`
- `run_summary`

### 5.4 产物目录

建议默认路径:

```text
.aiask/artifacts/{session_id}/{run_id}/
```

规则:

- `agent_execute_python` 的 snippet 保存为 `script.py` artifact，而不是只放临时目录。
- 终端 stdout/stderr 超过阈值时保存为 `.log` artifact，并在 DB 中保存 preview。
- `agent_file_write` / `agent_file_patch` 成功后将目标路径、hash、大小、patch summary 记录为 artifact。
- 金融 research report、xlsx、pptx、csv、json、png 图表均记录 artifact。
- 所有 artifact 都要带 `tool_call_id`，能回到来源工具调用。

## 6. Evidence Extractor

新增模块建议:

```text
packages/agent/src/aiask_agent/evidence.py
```

职责:

- 输入 `tool_name`, `arguments`, `result`, `session_id`, `run_id`, `tool_call_id`, `trace_id`。
- 从标准 envelope 中提取:
  - `meta.source_chain`
  - `data.source_chain`
  - `attempted_sources`
  - `fallback_reason`
  - `data_timestamp`
  - `provider`
  - `url/link/source_url`
  - `title/headline/name`
  - `published_at/time/date`
  - `path/file_path/output_path/report_path`
  - `stdout/stderr/process_id`
- 写入 `agent_sources` 与 `agent_artifacts`。
- 发出 run events:
  - `source.linked`
  - `artifact.created`
  - `market.quote_snapshot`
  - `news.source_linked`
  - `terminal.output_artifact`

Runtime 接入点:

- 在 `finish_tool_invocation()` 之后、`emit("tool.completed")` 前后调用 extractor。
- extractor 失败不得让工具调用失败，但必须发 `evidence.extract_failed` run event 并记录错误摘要。

## 7. Agent 工具方案

### 7.1 行情工具

新增或规范:

- `agent_stock_live_quote`
  - 输入: `code`, `market`, `include_source_chain`, `prefer_provider`
  - 调用: AKShare MCP `get_realtime_quote()` 或 finance MCP `tdx_realtime_quote` / `em_realtime_quote`
  - 输出: 标准 quote envelope，包含 price/change/change_pct/volume/amount/time/data_timestamp/provider/source_chain/fallback_reason。
  - 产物: `quote_snapshot` artifact。
  - 来源: `market_quote` source。

- `agent_market_snapshot`
  - 输入: `symbols`, `indices`, `include_news`, `include_source_chain`
  - 输出: 多标的 snapshot、指数、行情状态、数据新鲜度。
  - 产物: `table` / `quote_snapshot` artifact。

### 7.2 新闻工具

新增或规范:

- `agent_stock_news_digest`
  - 输入: `code`, `limit`, `hours`, `providers`, `include_links`
  - 调用: AKShare MCP `get_stock_news()`、Eastmoney `em_news_flow`、搜索 provider。
  - 输出: 标准 news items。
  - 每条新闻至少字段: `title`, `url`, `provider`, `published_at`, `fetched_at`, `excerpt`, `source_type`, `source_tier`。
  - 产物: `news_digest` artifact。
  - 来源: 多条 `news` / `announcement` / `web_search` source。

### 7.3 生成文件/脚本工具

规范既有:

- `agent_file_write`: 成功后记录 file artifact。
- `agent_file_patch`: 成功后记录 patch/file artifact。
- `agent_terminal`: 将命令、cwd、exit code、截断输出、完整日志 artifact 关联 run。
- `agent_execute_python`: 持久化 snippet 脚本、stdout/stderr、生成文件扫描结果。

### 7.4 Web 搜索和提取工具

规范既有:

- `agent_web_search`: 将搜索结果 URL 映射为 `agent_sources`。
- `agent_web_extract`: 将提取页面 URL、title、fetched_at、excerpt 映射为 `agent_sources`。

## 8. HTTP API 方案

新增 Agent HTTP API:

- `GET /v1/runs/{run_id}/artifacts`
- `GET /v1/sessions/{session_id}/artifacts`
- `GET /v1/artifacts/{artifact_id}`
- `GET /v1/artifacts/{artifact_id}/content`
- `GET /v1/runs/{run_id}/sources`
- `GET /v1/sessions/{session_id}/sources`
- `GET /v1/sources/{source_id}`
- `GET /v1/tool-invocations/{invocation_id}`

增强已有 SSE:

- `/v1/runs/{run_id}/events/stream` 增加以下事件类型:
  - `artifact.created`
  - `source.linked`
  - `market.quote_snapshot`
  - `news.source_linked`
  - `terminal.output_artifact`

返回安全要求:

- 不返回 API key、token、cookie、broker 凭据。
- 文件内容 API 默认只允许 artifact path 在 `.aiask/artifacts` 或 Agent guard 允许根目录下。
- artifact 预览限制大小，完整内容需单独 endpoint。

## 9. Desktop 开发方案

涉及文件:

- `desktop/src/types.ts`
- `desktop/src/services/aiaskApi.ts`
- `desktop/src/mockApi.ts`
- `desktop/src/hooks/useAgentWorkbench.ts`
- `desktop/src/components/Timeline.tsx`
- `desktop/src/components/TaskPanels.tsx`
- `desktop/src/components/WorkbenchView.tsx`
- `desktop/src/components/InspectorPanel.tsx`
- 可能新增 `desktop/src/components/SourcePanel.tsx`、`FinanceEvidenceCards.tsx`

UI 行为:

- Timeline 不只显示 generic tool payload，而是识别:
  - Quote snapshot card: 股票代码、最新价、涨跌幅、成交量、时间戳、provider、fallback。
  - News source card: 标题、来源、发布时间、链接、摘要。
  - Artifact created card: 文件名、类型、大小、hash、路径、打开/复制路径/预览。
  - Terminal output card: 命令、退出码、耗时、stdout/stderr preview、完整日志 artifact。
- Artifacts 面板从后端 artifact API 拉取 durable artifacts，不再只依赖 response metadata 派生。
- Sources 面板按 run/session 展示 citation 列表，支持按 quote/news/web/local_db 过滤。
- StockDataSourcesPanel 与 run evidence 关联，显示当前启用 provider 和测试状态，但不直接发外部行情请求。

## 10. CLI/TUI 开发方案

新增入口建议:

```toml
[project.scripts]
aiask-agent = "aiask_agent.server:main"
aiask = "aiask_agent.cli:main"
```

CLI 子命令:

- `aiask chat`
  - 交互式聊天，复用 `/v1/responses`。
- `aiask run "分析 600519 最新行情和新闻"`
  - 发起 run，输出 response、run_id。
- `aiask runs list`
  - 列出最近 runs。
- `aiask events follow <run_id>`
  - SSE 跟随 run events。
- `aiask artifacts list --run <run_id>` / `--session <session_id>`
  - 列出 durable artifacts。
- `aiask artifacts show <artifact_id>`
  - 显示 artifact metadata/preview。
- `aiask artifacts export <artifact_id> --to <path>`
  - 导出 artifact。
- `aiask sources list --run <run_id>`
  - 列出 citation/source links。
- `aiask tools list`
  - 列工具。
- `aiask data-sources list/test`
  - 查看和测试数据源配置。

TUI 增强:

- 增加 `/artifacts [run_id]`
- 增加 `/sources [run_id]`
- timeline 中显示 quote/news/artifact/source 事件摘要。

## 11. 分阶段实施路线

### Phase 0: 合同与测试先行

- 为 `tool_invocations`、新 `agent_sources`、`agent_artifacts` 写 session_store 单元测试。
- 为 evidence extractor 写 fixture:
  - quote result with source_chain/fallback。
  - news result with url/published_at。
  - file write result with path。
  - terminal result with stdout/stderr。
- 为 HTTP API 写 contract tests。

验收:

- 不改 Desktop 的情况下，Agent 能从模拟工具结果生成 sources/artifacts 并查询。

### Phase 1: Agent 持久化与事件

- 新增 DB schema 和迁移兼容逻辑。
- 新增 `evidence.py`。
- Runtime 在工具完成后调用 extractor。
- server.py 增加 artifacts/sources API。
- SSE/run_events 加入新增事件。

验收:

- 任意工具调用完成后，若 result 含 path/url/source_chain，可在 `/v1/runs/{run_id}/artifacts` 或 `/sources` 查到。
- extractor 错误只产生 `evidence.extract_failed`，不破坏主 run。

### Phase 2: 实时行情与新闻 facade

- 新增 `agent_stock_live_quote`。
- 新增 `agent_stock_news_digest`。
- 复用 AKShare MCP、Finance MCP、stock_data_sources registry。
- 标准化 quote/news envelope。
- 将 provider、fallback、data_timestamp、source URL 映射为 source/artifact。

验收:

- 提问“分析 600519 最新行情和相关新闻”，run 中出现 quote snapshot、news links、source_chain 和 timestamp。

### Phase 3: Desktop 展示

- 扩展 `types.ts`。
- 扩展 `aiaskApi.ts` 与 `mockApi.ts`。
- `useAgentWorkbench` 加载 artifacts/sources。
- Timeline 增加 quote/news/source/artifact 卡片。
- Artifacts 面板改为后端 durable artifacts 优先，metadata 派生作为 fallback。
- 新增 Sources/Citations 面板。

验收:

- Desktop 中同一个 run 能看到实时行情卡、新闻链接卡、生成文件卡。
- 点击 artifact 可看 metadata/preview/path。
- 点击 source URL 可打开来源。

### Phase 4: CLI/TUI

- 新增 `aiask_agent/cli.py`。
- 增加 `aiask` console script。
- 实现 run/follow/artifacts/sources/tools/data-sources 子命令。
- TUI 增加 `/artifacts`、`/sources`。

验收:

- 命令行可发起一次股票分析 run。
- 命令行可 follow run events。
- 命令行可列出同一 run 的 artifacts/sources。

### Phase 5: 保留、导出、审计与清理

- artifact retention policy 接入 user data policies。
- 支持 session/run export bundle。
- 大文件预览截断与 hash 校验。
- 数据源 freshness/degraded/fallback 在 UI/CLI 中明确显示。
- 补充端到端测试和文档。

验收:

- 可导出一个 run 的 response、events、tool_invocations、sources、artifacts manifest。
- 不泄露 secrets。
- 旧数据迁移兼容。

## 12. 验收标准

最终完成后必须满足:

- 股票实时行情: 用户在 Desktop 或 CLI 问某只股票的最新行情时，Agent 调用实时行情 facade，并显示价格、时间戳、provider、source_chain、fallback/degraded 状态。
- 新闻来源链接: 新闻结果必须展示 title、URL、provider、published_at/fetched_at，并保存为 `agent_sources`。
- 生成文件/代码/脚本: `agent_file_write`、`agent_file_patch`、`agent_execute_python`、`agent_terminal` 生成或影响的文件、脚本、日志必须保存为 `agent_artifacts`，包含 path、kind、size、sha256、preview。
- 完整链路: 每个 artifact/source 能追溯到 session_id、run_id、tool_call_id、tool_name。
- Desktop: Timeline 和 Artifacts/Sources 面板展示 durable records，而不是只展示 raw JSON。
- CLI: `aiask run`、`aiask events follow`、`aiask artifacts list/show/export`、`aiask sources list` 可用。
- 安全边界: Desktop 不直连 AKShare/MCP/外部 provider；模型只看到 `agent_*`；stateful/trade-risk 操作继续走审批/控制令牌。
- 测试: Agent session_store/evidence/server contract tests、Desktop API/mock/component tests、CLI smoke tests 均通过。

## 13. 风险与注意事项

- 已有工作树存在大量改动和未跟踪文件，开发时必须小步提交，避免覆盖用户或其他任务改动。
- provider API 有额度、延迟和地域限制，UI 必须展示 provider、timestamp、fallback，不得把延迟数据说成绝对实时。
- 新闻链接字段在不同源中命名不一致，需要 extractor 使用白名单字段映射，不应用脆弱字符串猜测覆盖所有情况。
- artifact 路径必须受 guard root 限制，避免任意文件读取。
- CLI 应作为 Agent HTTP client，不应绕过 server 直接 import MCP/manager。

## 14. 建议下一步

按 Phase 0 开始开发:

1. 在 `session_store.py` 增加 `agent_sources` / `agent_artifacts` schema 和 CRUD。
2. 新增 `evidence.py` 与单元测试。
3. 在 runtime 工具完成点接入 extractor。
4. 增加 artifacts/sources HTTP API 与测试。
5. 再进入行情/新闻 facade 和 Desktop/CLI 展示。

## 15. 开发落地记录

日期: 2026-06-12

本节记录本方案首轮开发已经完成的范围，便于后续继续增量开发和验收。

### 15.1 Agent 持久证据与产物链路

- `packages/agent/src/aiask_agent/session_store.py` 已新增 `agent_sources`、`agent_artifacts` 表、索引和查询/写入方法。
- `packages/agent/src/aiask_agent/evidence.py` 已新增运行期 evidence extractor，可从工具结果中抽取新闻来源、行情快照、文件路径、终端输出和 Python snippet 产物。
- `packages/agent/src/aiask_agent/runtime.py` 已在工具完成后接入 extractor，并写入 `source.linked`、`news.source_linked`、`artifact.created`、`market.quote_snapshot`、`terminal.output_artifact` 等 run events。
- `packages/agent/src/aiask_agent/server.py` 已在工具审计调用路径中接入 extractor，并新增 artifacts/sources/tool-invocation 查询 HTTP API。

### 15.2 实时行情与新闻 Agent facade

- `packages/agent/src/aiask_agent/adapters/akshare.py` 已新增 `stock_live_quote()` 和 `stock_news_digest()`，复用 AKShare MCP 的实时行情和新闻工具。
- `packages/agent/src/aiask_agent/tools/catalog.py`、`packages/agent/src/aiask_agent/tools/schemas.py`、`packages/agent/src/aiask_agent/tool_registry.py` 已注册 `agent_stock_live_quote` 和 `agent_stock_news_digest`。
- 两个新工具保持 `agent_*` 模型可见边界，且标记为只读金融读取能力。

### 15.3 Desktop 展示链路

- `desktop/src/types.ts` 已新增 `AgentArtifactRecord`、`AgentSourceRecord`，并扩展任务产物类型。
- `desktop/src/services/aiaskApi.ts` 已新增 run/session artifacts 和 sources 查询方法。
- `desktop/src/hooks/useAgentWorkbench.ts` 已在加载 run events 时并行加载 artifacts/sources。
- `desktop/src/components/TaskPanels.tsx`、`Timeline.tsx`、`WorkbenchView.tsx`、`InspectorPanel.tsx` 已接入 durable artifacts/sources 展示。

### 15.4 CLI

- `packages/agent/src/aiask_agent/cli.py` 已新增 HTTP-only CLI。
- `packages/agent/pyproject.toml` 已新增 `aiask = "aiask_agent.cli:main"` console script。
- CLI 已支持 `run`、`artifacts list/show/export`、`sources list/show`、`events list/follow`、`tools`、`data-sources`。

### 15.5 测试与验证

已通过:

- `python -m compileall packages/agent/src/aiask_agent/evidence.py packages/agent/src/aiask_agent/cli.py packages/agent/src/aiask_agent/runtime.py packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/adapters/akshare.py`
- `uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_tool_registry.py -q`
- `uv run pytest packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_runtime.py packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_tool_registry.py -q`
- `uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q`
- `uv run pytest packages/agent/tests/test_endpoint_drift_gate.py -q`
- `npm run typecheck`，工作目录为 `desktop/`。
- `$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.cli --help`

已知剩余风险:

- 当前工作树已有大量未提交改动和未跟踪文件，后续继续开发或提交前应先确认哪些属于本任务、哪些属于其它并行任务。
- 第一轮记录中的 `packages/agent/tests/test_server.py::test_desktop_http_surface_and_read_only_tool_api` health/detailed `SECRET` 字符串问题已在第二轮修复并通过验证。

## 16. 第二轮开发落地记录

日期: 2026-06-12

本轮继续推进“执行开发方案完成项目开发”，补齐首轮实现后仍缺的可见闭环、TUI/CLI 导出、安全和验证项。

### 16.1 Desktop mock 与测试闭环

- `desktop/src/mockApi.ts` 已加入 mock durable artifacts/sources，包括行情快照、新闻来源和 Python snippet 产物。
- `desktop/src/mockApi.ts` 已补齐 `/v1/runs/{run_id}/artifacts`、`/v1/runs/{run_id}/sources`、`/v1/sessions/{session_id}/artifacts`、`/v1/sessions/{session_id}/sources`、`/v1/artifacts/{artifact_id}`、`/v1/artifacts/{artifact_id}/content`、`/v1/sources/{source_id}` mock 路由。
- mock 工具目录和工具调用结果已包含 `agent_stock_live_quote`、`agent_stock_news_digest`，可在演示模式返回 provider、timestamp、source_chain 和新闻 URL。
- `desktop/src/services/aiaskApi.test.ts` 已新增 run/session artifacts/sources API contract 测试。

### 16.2 TUI 与 CLI 导出

- `packages/agent/src/aiask_agent/tui.py` 已新增 `/artifacts`、`/sources` 命令，可按当前 run 或指定 run 查询 durable records。
- `packages/agent/tests/test_hermes_native_live_adapters.py` 已覆盖 TUI 新命令自动补全和能力声明。
- `packages/agent/src/aiask_agent/cli.py` 已新增 `export-run` 子命令，通过 Agent HTTP 导出 run、events、tool_invocations、artifacts、sources manifest。
- `packages/agent/src/aiask_agent/server.py` 已新增 `GET /v1/runs/{run_id}/tool-invocations`，并同步 fallback/simple HTTP 分支。

### 16.3 安全与契约修复

- `packages/agent/src/aiask_agent/evidence.py` 已限制文件 artifact 的 preview/hash 读取范围：只读取 `AIASK_AGENT_HOME` 或 `AIASK_AGENT_WORKSPACE_ROOTS` 内路径，越界路径只记录 blocked artifact，不读取内容。
- `packages/agent/tests/test_evidence_artifacts_sources.py` 已新增越界路径不会读取 preview/hash 的安全测试。
- `packages/agent/src/aiask_agent/server.py` 已修复 `/health/detailed` 中敏感 env 名称和 notes 文本导致的 `secret` 字符串暴露问题；诊断接口仍保留必要结构，健康接口使用 strict redaction。
- `packages/agent/src/aiask_agent/adapters/akshare.py` 已补齐 `ticker` alias 到 `code` 的映射，和 schema 保持一致。

### 16.4 第二轮验证结果

已通过:

- `python -m compileall packages/agent/src/aiask_agent/evidence.py packages/agent/src/aiask_agent/cli.py packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/tui.py packages/agent/src/aiask_agent/adapters/akshare.py`
- `uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_tool_registry.py packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_runtime.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_server.py::test_desktop_http_surface_and_read_only_tool_api packages/agent/tests/test_hermes_native_live_adapters.py::test_tui_controller_parser_reducers_and_resume -q`
- `npm run typecheck`，工作目录为 `desktop/`。
- `npm test -- --run src/services/aiaskApi.test.ts src/components/WorkbenchView.test.tsx`，工作目录为 `desktop/`。
- `$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.cli --help`
- `$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.cli export-run --help`
- `$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.cli artifacts --help`
- `$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.cli sources --help`
