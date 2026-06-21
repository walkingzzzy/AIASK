# Learning、RL、MoA 学习能力

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Learning、RL、MoA 学习能力 |
| 功能编号前缀 | `LEARN` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P1 高级能力，可发现但写回受控 |
| 代码基准 | `desktop/src/features/user/LocalUserWorkspace.tsx`、`desktop/src/services/aiaskApi.ts`、`packages/agent/src/aiask_agent/routes/learning_rl.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐学习、RL、MoA 的授权、接口、状态和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Learning Proposal | 学习建议和改进候选 | `/v1/learning/review` |
| RL Run | 强化学习/Atropos 训练运行 | `/v1/rl/runs` |
| MoA | Mixture-of-Agents 能力，可通过工具目录体现 | Agent tool catalog |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 学习和 RL 能力会影响系统行为，必须区分只读审查、配置更新、训练启动和学习写回。 |
| 解决方案 | 页面展示 learning status/review/apply、RL environments/config/runs/results/logs，写回和训练动作受控。 |
| 业务价值 | 让高级学习能力可见但不失控。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| LEARN-US-001 | P1 | 作为用户，我希望查看学习建议。 | proposals 可筛选和审查。 |
| LEARN-US-002 | P1 | 作为管理员，我希望启动/停止 RL run 前有门禁。 | start/stop 需要 control token。 |
| LEARN-US-003 | P1 | 作为隐私负责人，我希望学习写回受数据策略约束。 | `allow_learning` 可见。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| LEARN-F001 | Learning status/review | P1 | `/v1/learning/status|review` | 空态补强 | proposals 可见 |
| LEARN-F002 | Learning apply | P1 | `/v1/learning/apply` | 审批/门禁 | 写回受控 |
| LEARN-F003 | RL config/env/runs | P1 | `/v1/rl/*` | 参数说明 | run 状态可见 |
| LEARN-F004 | MoA 可见性 | P2 | tools/capabilities | 只读展示 | 不静默改模型策略 |

### 1.4 业务规则与边界

学习写回、RL config update、run start/stop 必须有 control token 或明确审批；用户数据进入学习必须受 data policy 约束。

## 2. 流程设计

状态机：`loading -> ready|empty|error -> reviewing -> applying|training -> success|failed|gated`。

| 步骤 | 用户操作 | API | 异常 |
|---|---|---|---|
| 查看学习状态 | `/v1/learning/status` | 无数据 empty |
| 审查建议 | `/v1/learning/review` | proposal 缺失 |
| 应用建议 | `/v1/learning/apply` | 无 token gated |
| 启停训练 | `/v1/rl/runs`、`/stop` | 训练失败显示 logs |

## 3. 架构设计

Desktop 只展示学习/RL 控制面；Agent learning_rl routes 负责状态、配置、运行和日志；用户数据策略由 desktop_user routes 约束。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 前端方法 |
|---|---|---|---|---|
| Learning status | `/v1/learning/status` | GET | API/control | `learningStatus()` |
| Learning review | `/v1/learning/review` | GET | control | `learningReview()` |
| Apply | `/v1/learning/apply` | POST | control | `learningApply()` |
| RL env/config/runs | `/v1/rl/*` | GET/PATCH/POST | control | `rl*()` |

## 5. 前端设计

组件：`LearningRlPanel -> LearningProposalTable -> DataPolicyNotice -> RlEnvironmentPanel -> RlRunsTable -> LogsViewer`。

## 6. 开发规范

新增学习写回必须补 data policy 判断、redaction、audit、negative test。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| LEARN-201 | 学习未授权 | allow_learning false | 禁止写回 |
| LEARN-401 | 训练操作需要控制令牌 | control missing | disabled |
| LEARN-501 | 训练失败 | RL run error | 显示 logs |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-LEARN-001 | proposals | 可审查 |
| TC-LEARN-002 | apply 无授权 | gated |
| TC-LEARN-003 | RL start/stop | 需要 control token |
| TC-LEARN-004 | logs/results | 可查看 |

## 9. 不做什么

- 不静默学习写回。
- 不在无授权时启动训练。
- 不展示用户敏感原文或 secret。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| 前端面板 | `desktop/src/features/settings/LearningRlPanel.tsx` | 读取 learning status/review、RL environments/config/runs/results/logs，apply/start/stop 需要 control token | Learning/RL 是高级可发现能力，不是默认自动学习 |
| API | `services/api/ops.ts` | `learningStatus()`、`learningReview()`、`learningApply()`、`rl*()` | 每个状态写入都要 gated |
| Agent routes | `routes/learning_rl.py` | `/v1/learning/*`、`/v1/rl/*` | route 已有，但 live 环境需单独验收 |
| 测试 | `LearningRlPanel.test.tsx` | 覆盖读写 endpoint 和无 token 禁用 | QA 要区分读、apply、start、stop |

### 10.2 功能细节

| 功能 | 展示字段 | 门禁 |
|---|---|---|
| Learning status | enabled/status/proposals/counts | 只读 |
| Review proposals | proposal id、status、reason、diff/skill impact | apply 需要 control token |
| RL config | environment、params、policy | patch 需要 control token |
| RL runs | run id、status、results、logs | start/stop 需要 control token |

### 10.3 成熟技术采用

学习/RL 功能按 MLOps/实验治理原则处理：配置、运行、结果、日志、停止动作分离；状态写入可审计。AIASK 不采用默认后台自我修改技能或自动启动 RL 的方式。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 学习状态 | learning status、proposal count、RL config、environment count、run count | `LearningRlPanel.tsx`、`learningStatus()` | 未启用时显示 not_loaded/degraded |
| 学习建议表 | proposal id、status、source、impact、created_at、review action | `learningReview()` | apply/reject 需要 control token 或确认 |
| RL 配置表单 | environment、config patch、budget、safety flags | `rlConfig()`、`rlConfigUpdate()` | patch 展示 diff，不直接覆盖未知字段 |
| RL runs/result/logs | run id、environment、status、result metrics、tail logs | `rlRuns()`、`rlRunLogs()` | logs 固定高度滚动，结果可折叠 |

### 11.2 组件树

```text
LearningRlPanel
├── LearningStatusSummary
├── LearningProposalTable
├── RlConfigEditor
├── RlRunsTable
└── RlRunResultLogsPanel
```

### 11.3 状态和响应式

- `blocked`：训练/应用建议被策略拒绝时展示 reason，不隐藏 proposal。
- `mock/live`：训练结果如果来自 mock fixture 必须标明，不可作为能力达标证明。
- 窄屏 proposals、config、runs 分 tabs；logs 独立折叠。

## 原有内容保留

## 功能目标

AIASK 代码中存在学习循环、技能反思、Mixture-of-Agents、RL/Atropos 相关能力。第一版不一定把它们作为普通用户主入口，但必须在设置/高级运维里标准化展示状态、配置、运行、日志和安全边界。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Learning loop | `packages/agent/src/aiask_agent/learning_loop.py` |
| MoA | `packages/agent/src/aiask_agent/moa.py` |
| RL Atropos | `packages/agent/src/aiask_agent/rl_atropos.py` |
| Routes | `packages/agent/src/aiask_agent/routes/learning_rl.py` |
| Capabilities | `capabilities.py` 的 `agent_learning_*`、`agent_skill_reflect`、`agent_moa`、`agent_rl_*` |
| 前端设置 | `desktop/src/features/settings/LearningRlPanel.tsx` |
| API client | `learningStatus`、`learningReview`、`learningApply`、`rlEnvironments`、`rlRuns`、`rlRunStart` |

## 用户流程

1. 打开高级设置里的 Learning/RL。
2. 查看学习状态、待审核 proposal、来源和风险。
3. 管理员可 apply proposal；普通用户只能查看。
4. 查看 RL environments、config、runs、results、logs。
5. 启动/停止 RL run 需要 control token 和明确确认。
6. MoA 作为推理能力状态展示，缺模型 key 时红/黄灯。

## 前端展现

| 区域 | 内容 |
|---|---|
| Learning status | enabled、proposal count、last review |
| Proposal review | proposal_id、source、diff、risk、apply/deny |
| RL environments | name、available、backend、requirements |
| RL runs | run_id、status、started_at、metrics、logs |
| MoA | provider readiness、模型池、失败分类 |

## API 合约

| 操作 | Endpoint |
|---|---|
| 学习状态 | `GET /v1/learning/status` |
| proposal | `GET /v1/learning/review` |
| 应用 | `POST /v1/learning/apply` |
| RL env | `GET /v1/rl/environments` |
| RL config | `GET/PATCH /v1/rl/config` |
| RL runs | `GET/POST /v1/rl/runs` |
| stop/results/logs | `/v1/rl/runs/{id}/stop|results|logs` |

## 验收规则

1. 学习建议不能自动应用。
2. RL 启动/停止必须有 control token。
3. 缺外部训练 provider 时显示 unavailable，不假装可用。
4. 日志需要折叠和截断。
5. 这些高级能力默认不抢占 V1 主工作流。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 学习建议不可信 | proposal 显示来源和 diff | review/apply 分离 | `learning_loop.py` | 不自动应用 |
| RL 环境不可用 | env 卡红/黄灯 | environments/status | `rl_atropos.py` | unavailable 可见 |
| RL 日志过大 | 折叠日志和尾部查看 | logs endpoint + UI truncation | `routes/learning_rl.py` | 页面不卡顿 |
| MoA 缺模型 | MoA 状态显示 provider 缺失 | model readiness + MoA status | `moa.py` | 不假装可用 |
| 普通用户误用高级能力 | 高级设置入口，不在主导航抢占 | settings panel + control token | `LearningRlPanel.tsx` | 缺 token 禁用 |

### 代码生成/修改步骤

1. 新 learning proposal 类型必须有 source、risk、diff、apply_action。
2. RL run 创建/停止必须走 control token。
3. 前端拆分 ProposalReview、RlEnvironmentList、RlRunTable、LogViewer。
4. mock 覆盖 unavailable、running、failed、completed、proposal pending。
5. 测试覆盖 apply gate、日志截断、缺 provider 状态。

### 不做什么

- 不自动修改 skills 或配置。
- 不把实验性 RL 功能放到普通用户首屏。
- 不隐藏训练 provider 缺失。

### 状态机补充

Learning：`proposals_loading -> proposals_ready -> proposal_selected -> applying -> applied/apply_failed`

RL：`env_loading -> env_ready -> run_starting -> running -> stopping -> completed/failed/stopped`

MoA：`provider_checking -> available/degraded/unavailable`。
