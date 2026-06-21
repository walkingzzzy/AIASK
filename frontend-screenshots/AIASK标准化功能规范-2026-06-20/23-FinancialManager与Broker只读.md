# Financial Manager 与 Broker 只读

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Financial Manager 与 Broker 只读 |
| 功能编号前缀 | `FIN` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P0/P1，金融只读和受控意图 |
| 代码基准 | `desktop/src/features/financial-manager/FinancialManagerWorkspace.tsx`、`packages/agent/src/aiask_agent/routes/desktop_finance.py`、`desktop/src/services/aiaskApi.ts` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐金融经理台、券商只读、交易边界和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Financial Manager | 金融经理台 catalog/status/query/intent | `/v1/desktop/financial-manager/*` |
| Broker Read-only | 券商只读状态、账户、持仓、订单 | `/v1/desktop/broker-*` |
| Trade Risk | 实盘交易风险，V1 必须 blocked 或受控 | broker/financial readiness |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 金融经理台和券商连接容易被误解为可交易，V1 必须明确只读和受控意图。 |
| 解决方案 | 展示 catalog/status/query/intent、broker readiness/accounts/positions/orders，并阻断实盘下单/撤单。 |
| 业务价值 | 让金融能力可用但安全。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| FIN-US-M001 | P0 | 作为用户，我希望查询金融经理台能力。 | catalog/status/query 可见。 |
| FIN-US-M002 | P0 | 作为用户，我希望 stateful 动作创建意图。 | intent id 可见。 |
| FIN-US-M003 | P1 | 作为风控，我希望券商仅只读。 | accounts/positions/orders 无交易按钮。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| FIN-F301 | Manager catalog/status | P0 | manager routes | 状态说明 | 可见 |
| FIN-F302 | Manager query | P0 | query route | 错误态 | query 只读 |
| FIN-F303 | Manager intent | P0 | intent route | 审批联动 | stateful 动作受控 |
| FIN-F304 | Broker read-only | P1 | broker routes | 只读提示 | 无实盘交易 |

### 1.4 业务规则与边界

查询可只读；修改、同步、执行和金融风险动作必须 intent/control token；live order/cancel 不属于 V1。

## 2. 流程设计

状态机：`loading -> ready|degraded|error -> querying -> result|failed -> intent_pending|blocked`。

## 3. 架构设计

Desktop Financial Manager 页面调用 Agent desktop_finance routes；broker 操作通过 finance-mcp-servers guardrails；V1 不触发实盘交易。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token |
|---|---|---|---|
| Catalog | `/v1/desktop/financial-manager/catalog` | GET | API |
| Status | `/v1/desktop/financial-manager/status` | GET | API |
| Query | `/v1/desktop/financial-manager/query` | POST | API/control |
| Intent | `/v1/desktop/financial-manager/intent` | POST | control |
| Broker read-only | `/v1/desktop/broker-readiness|accounts|positions|orders` | GET | API/control |

## 5. 前端设计

组件：`FinancialManagerWorkspace -> CatalogPanel -> StatusSummary -> QueryForm -> IntentPanel -> BrokerReadOnlyPanel -> RiskNotice`。

## 6. 开发规范

新增 broker/financial action 必须声明 read-only、dry-run、intent 或 blocked；不得新增 live order/cancel V1 入口。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| FIN-M-201 | 金融经理台未就绪 | readiness failed | 显示 gates |
| FIN-M-401 | 金融动作需要审批 | intent required | 创建 intent |
| FIN-M-501 | V1 不支持实盘交易 | live trading blocked | 显示只读 |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-FIN-M-001 | catalog/status | 可见 |
| TC-FIN-M-002 | query | 只读结果 |
| TC-FIN-M-003 | stateful intent | 生成 intent |
| TC-FIN-M-004 | broker | 无交易按钮 |

## 9. 不做什么

- 不提供实盘下单/撤单。
- 不把 query 失败隐藏。
- 不绕过 broker guardrail。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| Financial Manager | `FinancialManagerWorkspace.tsx` | catalog/status/query/intent，内置只读工作流步骤 `agent_analyze_stock`、`agent_portfolio_risk`、`agent_quant_data_gate` 等 | 金融经理台要区分 read_only、stateful_intent、blocked |
| Broker read-only | `FinanceLabPage.tsx` | QMT/同花顺 provider env snippet、readiness、accounts/positions/orders/analytics、sync consent | Broker V1 只读展示，sync 也要 token/consent |
| Agent routes | `desktop_finance.py` | `/financial-manager/*`、`/broker-readiness`、`/broker/accounts|positions|orders|analytics`、`/broker/sync` | 接口表要写 read_only/live_trading_enabled |
| 测试 | `FinancialManagerWorkspace.test.tsx`、`FinanceLabPage.test.tsx`、`aiaskApi.test.ts` | 覆盖 live trading blocked、broker read-only、sync token gate | QA 必须断言无实盘按钮 |

### 10.2 功能细节

| 功能 | 展示字段 | 验收 |
|---|---|---|
| Catalog | group、capability_id、action_id、mode、availability | blocked action 只说明原因 |
| Query | request params、tool、result status、error_code | read_only action 可执行 |
| Intent | action、params、rationale、intent_id | stateful action 只创建 intent |
| Broker snapshot | accounts、positions、orders、deals、analytics、source_chain | read_only=true |
| Broker sync | provider、consent、user_id | 无 control token 或无 consent 不 sync |

### 10.3 成熟技术采用

金融/券商连接按最小权限和只读优先实现。QMT/同花顺配置只写 env 名和状态，不展示账号/路径敏感值；实盘交易、下单、撤单必须 blocked 或后续版本，V1 只保留只读和分析。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| Manager 状态 | catalog/status、read-only/stateful 分类、available actions | `FinancialManagerWorkspace.tsx`、`financialManagerCatalog()` | stateful action 不直接执行 |
| Query 表单 | manager、action、symbol/account、params、rationale | `financialManagerQuery()` | 只读 query 可执行；高风险转 intent |
| 结果面板 | response data、risk、warnings、source、raw JSON | `RawEvidencePanel` | 错误显示 manager/action/error_code |
| Broker 只读快照 | accounts、positions、orders、connector readiness、live trading blocked | `FinanceLabPage.tsx`、finance MCP servers | 固定显示 read_only 和 blocked，不展示下单入口 |

### 11.2 组件树

```text
FinancialManagerWorkspace
├── ManagerCatalogStatusPanel
├── ManagerQueryForm
├── ManagerResultPanel
├── ControlledIntentPanel
└── BrokerReadOnlySnapshot
```

### 11.3 状态和响应式

- `blocked`：实盘交易、下单、撤单等路径在 V1 固定 blocked；QA 扫描按钮和文案。
- `gated`：创建金融意图需要 control token、rationale 和审批入口。
- 窄屏 query 表单置顶，catalog 和结果按 tabs 展示。

## 原有内容保留

## 功能目标

Financial Manager 是组合、自选、风险、绩效、研究、量化、纸上交易和执行计划的统一查询/受控意图入口。Broker 第一版只做只读同步与分析，不提供实盘下单/撤单入口。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Desktop finance routes | `packages/agent/src/aiask_agent/routes/desktop_finance.py` |
| Financial payloads | `packages/agent/src/aiask_agent/financial_payloads.py` |
| Financial readiness | `packages/agent/src/aiask_agent/financial_readiness.py` |
| Broker support | `packages/akshare-mcp/src/akshare_mcp/services/_live_broker_support.py` |
| Finance MCP servers | `packages/finance-mcp-servers/src/aiask_finance_mcp/*` |
| 前端页面 | `desktop/src/features/financial-manager/FinancialManagerWorkspace.tsx`、`FinanceLabPage.tsx` |
| API client | `financialManagerCatalog`、`financialManagerStatus`、`financialManagerQuery`、`financialManagerIntent`、`broker*` |

## 用户流程

1. 打开 Financial Manager，加载 catalog 和 status。
2. 用户选择 manager/domain，执行只读 query。
3. 如果需要写入或状态变更，前端创建 `financialManagerIntent`。
4. Broker 区显示 readiness。
5. 用户确认只读后 sync broker 快照。
6. 查看 accounts、positions、orders 和 analytics。

## 前端展现

| 区域 | 内容 |
|---|---|
| Manager catalog | domain、capability、read_only/stateful/trade_risk |
| Status | configured、degraded、blocked、last_error |
| Query | 参数、结果、source、raw payload 折叠 |
| Intent | action、params、rationale、approval status |
| Broker | readiness、accounts、positions、orders、analytics |

## API 合约

| 操作 | Endpoint |
|---|---|
| catalog | `GET /v1/desktop/financial-manager/catalog` |
| status | `GET /v1/desktop/financial-manager/status` |
| query | `POST /v1/desktop/financial-manager/query` |
| intent | `POST /v1/desktop/financial-manager/intent` |
| broker readiness | `GET /v1/desktop/broker-readiness` |
| broker sync | `POST /v1/desktop/broker/sync` |
| accounts/positions/orders | `GET /v1/desktop/broker/accounts|positions|orders` |
| analytics | `POST /v1/desktop/broker/analytics/run`、`GET /latest` |

## 验收规则

1. Broker 页面必须明确“只读”。
2. 不出现下单、撤单、实盘交易主按钮。
3. trade-risk 动作必须 blocked 或 intent。
4. query 和 intent 视觉上分开。
5. Broker sync 需要用户确认只读范围。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 用户误以为能交易 | read-only badge 固定显示 | Broker route 只读 | `desktop_finance.py` | 无下单/撤单按钮 |
| Manager 能力风险不清 | catalog 显示 read_only/stateful/trade_risk | manager metadata | `financial_payloads.py` | 风险分类可见 |
| 查询失败 | query panel 显示错误和参数 | structured error | `financialManagerQuery` | 不吞错误 |
| 状态变更 | 创建 intent，不直接执行 | financialManagerIntent | `routes/intents.py` | intent id 可见 |
| Broker 同步范围不明 | 同步前确认 accounts/positions/orders | broker sync body | `brokerSync` | 未确认不执行 |

### 前端分区

| 区域 | 内容 |
|---|---|
| Catalog | manager、capability、risk、actions |
| Status | configured、degraded、blocked |
| Query | 参数表单、结果表、raw 折叠 |
| Intent | action、params、rationale、status |
| Broker | readiness、sync、accounts、positions、orders、analytics |

### 代码生成/修改步骤

1. 新 manager 能力必须在 catalog 标注 risk。
2. 查询动作和意图动作分开 API 和按钮。
3. Broker live trading 能力不得进 V1 UI。
4. mock 覆盖 broker unavailable、read-only sync success、trade-risk blocked。
5. 测试断言无 order/cancel 主按钮。

### 不做什么

- 不做实盘交易。
- 不用“执行”这种模糊按钮文案。
- 不让 trade-risk 动作绕过 intent。

### 状态机补充

Financial Manager：`catalog_loading -> status_loading -> ready -> querying -> query_success/query_error -> intent_created`

Broker：`readiness_loading -> read_only_confirm_required -> syncing -> snapshot_ready/sync_failed -> analytics_ready`。
