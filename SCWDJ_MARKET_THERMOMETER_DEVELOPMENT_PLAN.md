# scwdj.top 市场温度计分析与 AIASK 开发方案

日期：2026-06-09

## 1. 站点观察

目标站点：https://scwdj.top/

站点标题为“市场温度计 - 行业热度分析工具”，是一个面向 A 股的市场宽度、行业热度和行业轮动分析工具。实际页面为 React/Vite 单页应用，静态资源包含 Tailwind CSS v4 风格样式、React Router hash 路由与 ECharts 图表。前端路由包括：

- `/`：市场热力图首页
- `/market-breadth`：市场轮动/行业宽度矩阵
- `/industry/:industryCode`：行业详情与成分股明细

前端 API 统一挂在 `/api`：

- `/api/index/info`
- `/api/index/datas`
- `/api/stock/info`
- `/api/stock/datas`
- `/api/sw/info`
- `/api/sw/datas`
- `/api/sw/stocks/datas`

接口数据形态：

- 指数数据：`code/date/pct_change/close`
- 股票基础信息：`code/name/industry`
- 股票行情快照：`code/date/close/pct_change/ma20/amount/turnover/marketCap`
- 申万一级行业：`code/name`
- 行业温度：`code/date/close/temperature/ma20`
- 行业成分股：同股票行情快照

页面当前会停留在“正在分析全市场行情数据...”。只读探测显示，部分接口可返回数据，但首页依赖的大体量接口容易超过前端 10 秒超时；并且 2026-06-09 的行业成分股接口为空，最近可用交易日为 2026-06-08。这说明产品方向成立，但生产级实现必须强调本地缓存、数据新鲜度、降级提示和分层加载。

## 2. 对 AIASK 的帮助

这个站点对 AIASK 有三类直接价值：

1. 市场状态压缩：把 5000+ 股票的涨跌、均线位置、成交额和市值压缩成可解释的市场温度、行业宽度、冷热行业排行，适合喂给 Agent、策略工厂和风控模块。
2. 策略工厂前置筛选：行业温度和 MA20 宽度可以作为候选池、主题暴露、策略生成和孵化评分的上游 regime 信号。
3. 桌面体验升级：AIASK Desktop 可以增加“市场温度计/行业轮动”面板，给用户一个比原始行情表更直观的盘面总览。

## 3. 技术难度评估

整体难度：中等偏上。

低难度部分：

- React/Vite/Tailwind/ECharts 前端热力图、排行表、行业详情页。
- 只读 API 契约设计。
- MA20 宽度、涨跌家数、行业均值、冷热排行等聚合计算。

中等难度部分：

- 申万行业分类、股票成分映射、行业指数与个股行情的字段统一。
- 大规模股票数据的增量同步、缓存、交易日对齐和缺失数据处理。
- 页面渐进加载与接口超时降级，避免首页卡死。

高难度部分：

- 生产级全市场历史数据管线：停牌、复权、退市、北交所过滤、指数/行业/个股多数据源校验。
- 策略工厂接入后的因果污染控制：温度信号必须带 as_of、数据时间戳和 PIT 元信息。
- 实盘/准实盘环境的数据新鲜度、缓存失效和风控解释。

## 4. AIASK 实现路线

### Phase 1：后端核心能力

- 新增 `akshare_mcp.services.market_temperature` 纯计算服务。
- 输入股票快照与行业映射，输出：
  - 市场温度
  - 涨跌家数
  - MA20 宽度
  - 行业温度排行
  - 热门/冷门行业
  - 数据质量与降级原因
- 新增只读 MCP 工具 `get_market_temperature_snapshot`，优先从本地 SQLite 股票池和 K 线读取，按配置限制样本量，返回结构化降级元信息。

### Phase 2：数据管线增强

- 在 TDX/AKShare 同步任务中补齐：
  - 股票最新行情快照
  - 20 日均线
  - 行业/板块映射
  - 行业级温度历史快照
- 将每日温度快照落库，避免每次请求重新扫描全市场。
- 增加 freshness/readiness gate，区分“可用、陈旧、样本不足、行业映射不足”。

### Phase 3：Agent 与 Desktop 接线

- Agent 增加只读 HTTP 契约，Desktop 通过 Agent HTTP 获取市场温度，不直接调用 MCP 或 Python。
- Desktop 增加“市场温度计/行业轮动”视图：
  - 顶部市场温度与涨跌宽度
  - 行业温度矩阵
  - 热门/冷门行业排行
  - 行业详情与成分股列表
- Mock API 覆盖空态、降级态、正常态。

### Phase 4：策略工厂联动

- 将行业温度作为策略工厂候选池 admission 信号。
- 将行业温度历史作为 factor mining / incubation 的上下文特征。
- 对温度信号做前向收益验证，形成可解释的命中率矩阵。

## 5. 本轮开发切片

本轮先完成 Phase 1 的可测试核心：

- 根目录保留本方案，作为后续开发依据。
- 新增市场温度纯计算服务。
- 新增只读 MCP 工具入口。
- 新增目标单元测试并实际运行。

不在本轮做 live trading、写交易状态、修改用户已有大规模桌面改动，也不依赖外站 API 作为运行时数据源。

## 6. 2026-06-09 执行进展

- 已完成 Phase 1 核心后端：新增纯计算服务、只读 MCP 工具、工具目录契约和目标测试。
- 已完成 Agent 只读 facade：新增 `agent_market_temperature_snapshot`，继续保持模型可见工具统一使用 `agent_*` 命名。
- 已完成 Desktop 初版接入：新增“市场温度”高级金融页面，通过 Agent HTTP `/v1/tools/agent_market_temperature_snapshot` 获取快照，展示市场温度、MA20 宽度、涨跌宽度、冷热行业和质量指标。
- 已完成 mock、类型、路由和组件测试，当前仍不依赖 `scwdj.top` 作为运行时数据源。
- 已完成 Phase 2 本地缓存底座：在 Quant Core SQLite 中新增 `market_temperature_snapshots` 表、读写 mixin 和真实 roundtrip 测试。
- 已完成 MCP 缓存工具面：`get_market_temperature_snapshot` 支持 `use_cache` 优先读取本地快照；新增显式本地状态工具 `refresh_market_temperature_snapshot_cache` 用于数据同步任务刷新缓存。
- 已完成数据同步入口：新增 `sync_market_temperature_snapshot_cache`，在 data-sync surface 中安全触发市场温度缓存刷新，并保留底层刷新链路到 `meta.data_sync_source_chain`。
- 已完成市场温度缓存 freshness/readiness gate：新增只读 `check_market_temperature_cache_readiness`，可报告缓存缺失、陈旧、不可用、质量异常和 source_chain。
- 已完成历史缓存查询：新增只读 `list_market_temperature_snapshot_cache`，默认返回紧凑的日期、温度、状态、样本数和质量摘要，为后续行业轮动历史视图/策略工厂上下文做准备。
- 已完成 Agent 缓存就绪度只读 facade：新增 `agent_market_temperature_cache_readiness`，通过 Agent HTTP 读取 `check_market_temperature_cache_readiness` 的缓存状态、陈旧天数、blockers 和质量摘要。
- 已完成 Desktop 缓存 gate 展示：市场温度页并行读取快照与 cache readiness，在左侧质量区展示 ready/as_of/staleness/updated_at，并把 readiness envelope 纳入原始证据面板。
- 已完成历史缓存只读 surface：新增 `agent_market_temperature_cache_history`，Desktop 市场温度页展示最近缓存日期、温度、市场状态、样本/行业数和质量状态，为行业轮动历史视图提供轻量入口。
- 已完成受控缓存刷新接入：DataSync Manager 新增 `market_temperature_snapshot_cache` 任务类型，Desktop 数据同步页可生成 `data_sync.sync` 审批意图，确认后刷新本地市场温度缓存。
- 已保持 Agent/Desktop 安全边界：Agent 只暴露 read-only `agent_market_temperature_snapshot`、`agent_market_temperature_cache_readiness` 与 `agent_market_temperature_cache_history`，刷新缓存工具不进入 finance_safe 模型可见 facade。
- 已完成 Phase 4 最小联动：Strategy Factory `ReadinessService` 可从 cycle snapshot 的 `market_temperature_context`、`market_temperature` 或 `market_internals.market_temperature` 读取市场温度上下文，输出标准化 `market_temperature_context` 与质量/陈旧 warning；该接入不直接依赖 AKShare、Agent 或 Desktop，也不把陈旧/降级温度信号升级为策略准入 blocker。
- 已完成策略出生环境追踪：`StrategySubmitter._extract_birth_regime` 复用同一市场温度上下文解析逻辑，把 compact `market_temperature_context` 写入 lineage 的出生市场环境快照，避免保存全量 cycle snapshot，同时为后续孵化、淘汰和前向验证保留 PIT 线索。
- 已完成周期报告透出：Strategy Factory success summary 顶层新增市场温度、状态、as_of、质量状态、就绪状态和完整 compact context，方便 Desktop/Agent/运维报告直接检索市场温度背景。
- 已完成行业历史温度查询：MCP 新增只读 `list_market_temperature_industry_history`，从持久化 `market_temperature_snapshots` 中抽取行业级温度时间序列；Agent 新增 `agent_market_temperature_industry_history` finance-safe facade；Desktop 市场温度页新增 “Industry history” 区块，通过 Agent HTTP 展示最近缓存日的行业轮动历史。
- 已完成本轮验证：后端单元测试、工具目录契约测试、Python 编译检查、Desktop Vitest、typecheck、生产构建和浏览器 mock 页面验证均通过。

下一阶段优先继续 Phase 2/4：把缓存刷新接入日常数据同步/调度，完善行业成分股查询，并把市场温度上下文纳入前向验证矩阵。

## 7. 2026-06-09 追加进展：行业成分股下钻

- 已完成只读行业成分股查询：MCP 新增 `list_market_temperature_industry_constituents`，从本地 `stocks`/stock universe 读取行业内股票，支持 `industry`、`limit`、`offset`、`match_mode` 和 `include_source_chain`，缺少行业参数时返回标准 `PARAM_ERROR`，不触发外部数据源或本地状态写入。
- 已完成 Agent finance-safe facade：新增 `agent_market_temperature_industry_constituents`，继续保持模型可见工具统一 `agent_*` 命名，并通过 Agent HTTP 暴露给 Desktop。
- 已完成 Desktop 下钻入口：市场温度页面会以最热行业为默认下钻对象，展示本地行业成分股、股票代码、市值、PE/PB、上市日期，并把响应 envelope 纳入原始证据面板。
- 下一阶段优先级调整为：将市场温度缓存刷新接入日常调度/运维观测，建设 forward validation 命中率矩阵，并补充更完整的行业详情交互与历史趋势图表。

## 8. 2026-06-09 追加进展：缓存刷新调度接入

- 已将市场温度缓存刷新接入 AKShare MCP 后台 `DataSyncScheduler`：每日/启动同步执行现有 `sync_schedules` 后，会默认通过 DataSync Manager `run_runtime_data_warmup` bootstrap 并运行 `market_temperature_snapshot_cache` schedule。
- 调度仍复用 `sync_schedules`、`data_sync_manager` 与 `refresh_market_temperature_snapshot_cache`，不新增绕过审批/审计的直接写入通道；运行结果写入 scheduler `last_result.runtime_warmup`，便于后续 Desktop/运维状态面板读取。
- 新增环境开关：`DATA_SYNC_BOOTSTRAP_RUNTIME_SCHEDULES` 可关闭 bootstrap，`DATA_SYNC_RUNTIME_WARMUP_TASK_TYPES` 可扩展 runtime warmup 任务类型，`DATA_SYNC_RUNTIME_WARMUP_LIMIT` 控制每轮执行上限。
- 下一阶段继续推进 forward validation 命中率矩阵，将市场温度/行业温度与后续收益、方向命中、样本质量做 PIT 归因。

## 9. 2026-06-09 追加进展：Forward validation 矩阵

- 已完成只读 `get_market_temperature_forward_validation` MCP 工具：从持久化 `market_temperature_snapshots` 读取 PIT 快照，按市场温度状态分桶，统计未来 1/3/5 等缓存交易日窗口的方向命中率、样本数、平均前向涨跌和可靠性标记。
- 已完成 Agent facade：新增 `agent_market_temperature_forward_validation`，保持 finance-safe/read-only 工具边界，不暴露原始 stateful 数据同步工具。
- 已完成 Desktop 展示：市场温度页新增 “Forward validation” 区块，展示状态桶、样本数、1d/3d hit rate 与平均前向表现，并将验证矩阵纳入原始证据面板。
- 当前矩阵使用缓存快照中的 `weighted_pct_change`/`avg_pct_change`/`temperature_delta` 作为前向目标代理；后续可在市场指数/组合收益序列可用后扩展为更严格的真实收益回测。

## 10. 2026-06-09 追加进展：真实基准指数前向收益

- 已将 `get_market_temperature_forward_validation` 扩展为支持 `target_field="benchmark_return"`：默认读取本地沪深300/`000300` 指数 K 线，按 PIT 快照交易日对齐未来 1/3/5 等窗口收盘价，计算真实基准指数前向收益，而不是只依赖快照中的当日涨跌代理字段。
- 已保留生产降级路径：如果本地 `db.kline_1d` 中缺少基准指数数据，工具会显式返回 `benchmark_status="unavailable_fallback_to_weighted_pct_change"`，并降级使用 `weighted_pct_change`，同时在 `quality.warnings` 中标记 `benchmark_kline_unavailable`。
- 已同步 MCP tool catalog、Agent schema、Desktop 类型、Mock API 和市场温度页面默认请求；Desktop 现在默认请求 `benchmark_return + benchmark_code=000300`，页面展示 benchmark 可用状态，Agent 仍保持 read-only `agent_market_temperature_forward_validation` facade。
- 已新增测试覆盖真实基准指数 K 线命中率矩阵、Agent 参数透传、Desktop API 请求体和页面渲染，确认该能力可以作为 Strategy Factory、孵化工厂和风控面板后续判断市场 regime 的可解释验证层。

## 11. 2026-06-09 追加进展：上线前 smoke 覆盖

- 已扩展 `scripts/ops/live_readiness_smoke.py`：`tools` 检查现在要求 `agent_market_temperature_cache_readiness` 与 `agent_market_temperature_forward_validation` 已注册，避免部署后市场温度页面缺 Agent facade 才被发现。
- 已新增两个只读 smoke 检查：`market_temperature_cache` 调用缓存 freshness/readiness；`market_temperature_forward_validation` 以 `benchmark_return + 000300` 调用前向验证矩阵，并在缺少基准指数 K 线时报告透明降级状态。
- smoke 检查只读 Agent HTTP 工具，不触发缓存刷新、不写运行库、不碰 live trading；缺依赖的 `--self-test` 路径也会返回结构化 JSON，而不是直接 traceback。
- 已通过契约测试和临时 Agent self-test 验证：临时库缺少真实行情时，缓存状态会显示 `missing`，forward validation 会显示 `unavailable_fallback_to_weighted_pct_change`，但工具链、side-effect 和降级 envelope 仍可验证。

## 12. 2026-06-09 追加进展：Readiness 可观测闭环

- 已将 `/v1/financial-system/readiness` 返回的 `live_smoke.checks` 与 `scripts/ops/live_readiness_smoke.py` 对齐，新增 `market_temperature_cache` 和 `market_temperature_forward_validation` 两项，让健康页、部署检查和脚本看到同一套市场温度上线前检查清单。
- 已清理 Desktop `ReadinessHealthPage` 与 `ReadinessDiagnostic` 的可见乱码，恢复正常中文标签、诊断说明、下一步行动、前置检查路径和联调 smoke 清单。
- Desktop 健康页现在会在“数据与量化研究”前置步骤中明确提示 smoke 已覆盖市场温度与 `quant_research`，并在联调清单中展示 `agent_market_temperature_cache_readiness` 与 `agent_market_temperature_forward_validation` 路径。
- 已通过 Readiness 页面 Vitest、Agent readiness pytest、Desktop typecheck/build、Playwright 健康页冒烟和全页面矩阵验证，确认前端无控制台错误且健康页未出现目标乱码片段。

## 13. 2026-06-09 追加进展：共享状态文案修复

- 已清理 Desktop 共享 UI `StatusBadge`/`MetricCard`/`GatedState` 的状态标签映射，修复 `ready`、`approval_required`、`capabilities_synced`、`blocked`、`missing_credentials`、`unavailable_fallback_to_weighted_pct_change` 等常见状态在全局页面显示乱码的问题。
- 已修复共享阻塞原因提示和危险操作确认弹窗文案，控制令牌缺失、完整模式未开启、Agent endpoint 不可达、MCP 授权缺失等场景现在会显示可读中文。
- 已更新共享组件测试，覆盖状态标签本地化、GatedState 阻塞原因、RawEvidencePanel 默认折叠、JSON 敏感信息遮盖和危险操作确认。
- 已通过共享组件/健康页 Vitest、Desktop typecheck/build、浏览器健康页冒烟和全页面矩阵验证，确认市场温度相关运营路径以及常见状态标签不再出现目标乱码片段。

## 14. 2026-06-09 追加进展：市场温度页面缓存优先与失败态修复

- 已将 Desktop 市场温度页面的快照请求默认改为 `use_cache: true`，让页面优先读取 `market_temperature_snapshots` 持久化结果，避免每次打开页面都触发全市场扫描；这直接吸收了 `scwdj.top` 首屏大体量接口容易超时的经验。
- 已修复快照刷新失败时旧快照继续残留的问题：当 `agent_market_temperature_snapshot` 返回 HTTP/Agent 错误或失败 envelope 时，页面会清空旧的主快照和原始 envelope，只保留缓存 readiness、历史、前向验证等独立证据，避免把过期热行业误读成当前结果。
- 已新增组件测试覆盖缓存优先请求体和失败刷新场景，确认失败后旧热行业不会继续显示。

## 15. 2026-06-09 追加进展：基准缺失降级文案闭环

- 已修复 Desktop 市场温度页对 `unavailable_fallback_to_weighted_pct_change` 的本地化展示：当沪深300等基准指数 K 线缺失、前向验证降级为缓存快照涨跌代理时，页面现在显示“基准不可用，已降级”，而不是暴露内部状态码。
- 已新增组件测试覆盖该降级路径，确认页面主要可见区域不会出现裸 `unavailable_fallback_to_weighted_pct_change` 文案，保留 raw evidence 用于排障即可。

## 16. 2026-06-09 追加进展：Forward validation 参数降级透明化

- 已修复 `get_market_temperature_forward_validation` 对不支持 `target_field` 的处理：工具现在会保留原始 `requested_target_field`，并在 `meta.quality.warnings` 中写入 `unsupported_target_field_fallback_to_weighted_pct_change`，不再把请求值悄悄覆盖成实际降级字段。
- 实际计算仍安全降级到 `weighted_pct_change`，保持只读、缓存内计算和 side-effect metadata 不变；该修复主要提升生产排障、Agent smoke 与后续运维面板的解释性。
- 已新增 AKShare MCP 单元测试覆盖 unsupported target fallback，确认 `meta.degraded` 与 warnings 会明确暴露降级原因。

## 17. 2026-06-09 追加进展：测试配置去噪

- 已在根目录、Agent、AKShare MCP、Strategy Factory 与 Finance MCP Servers 的 pytest 配置中显式设置 `asyncio_default_fixture_loop_scope=function`，对齐 `pytest-asyncio` 后续默认行为，避免异步 fixture 作用域警告在生产验证日志中反复出现。
- 已重新运行 AKShare、Agent、Strategy Factory 和 Finance MCP Servers 的目标测试，确认配置项被正确识别，原有测试行为保持稳定。

## 18. 2026-06-09 追加进展：Smoke 降级原因透出

- 已增强 `scripts/ops/live_readiness_smoke.py` 的市场温度前向验证检查：结果现在会把 `meta.quality.status` 和 `meta.quality.warnings` 汇总到 `market_temperature_forward_validation.data`，让上线前 smoke 不只看到 `unavailable_fallback_to_weighted_pct_change` 状态，也能直接看到 `benchmark_kline_unavailable` 等原因。
- 已更新 Agent smoke 契约测试，模拟基准指数 K 线缺失时的降级 envelope，并断言 smoke 输出包含 `quality_status` 与 `warnings`。
- 已通过 Agent smoke/registry/native parity 与 AKShare 市场温度/数据 readiness 测试组合，确认新增可观测字段不影响只读工具边界与现有 readiness gate。

## 19. 2026-06-09 追加进展：Readiness 清单观测字段

- 已扩展 `/v1/financial-system/readiness` 的 `live_smoke.checks` 清单：市场温度缓存检查现在声明会观测 `ready/status/blockers/warnings`，前向验证检查声明会观测 `benchmark_status/quality_status/warnings/sample_count`。
- 已同步 Desktop 类型、Mock API 与健康页展示，准备度 / 健康页面现在会在真实联调检查清单中显示这些观测字段，用户能在跑脚本前知道 smoke 会验证哪些降级原因。
- 已补充 Agent readiness 契约测试与 Desktop 健康页测试，确保后续改动不会丢失市场温度 smoke 的可观测字段。
