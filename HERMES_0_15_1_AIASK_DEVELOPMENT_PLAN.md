# Hermes 0.15.1 参考基线下的 AIASK-native 开发方案

Date: 2026-06-04

## 1. 文档定位

这不是一份“方向性提纲”，而是一份可直接用于后续拆分 issue、安排阶段交付、
前后端协同和验收的实施方案。

一句话定位：

> 这是一份 AIASK-native Agent 产品化重构计划，不是 Hermes runtime 集成、
> 迁移或替换计划。Hermes 0.15.1 只作为通用 Agent 能力基线和架构参考；
> AIASK Desktop、Agent Runtime、金融 MCP/Manager 仍是主产品与主实现。

本方案建立在以下审查结论之上：

- Hermes 当前参考基线为 `vendor/hermes-agent-upstream` 的 `main` 快照，
  版本 `0.15.1`，提交 `7402706c5`
- AIASK 当前 Hermes 基线仍停留在 `0.14.0 / v2026.5.16`
- AIASK 的 `/v1/hermes/*` 不是空壳，而是已经接入原生 runtime、gateway、
  plugins、skills、MCP、terminal/process 等能力
- AIASK 的 Desktop + Agent + 金融 MCP/Manager 已经形成金融产品主线，
  不应被 Hermes runtime 替换，也不应把金融系统并入 Hermes core
- AIASK 的短板主要不在能力缺失，而在前端信息架构、session 主链路、
  运维产品化、扩展承载方式
- AIASK 的核心护栏必须保持不变：
  - Desktop 只消费 Agent HTTP API，不直连 MCP / managers
  - `agent_*` 为唯一模型可见工具名
  - `finance_safe` 为默认模式
  - stateful 金融动作必须通过 intent / confirmation
  - Financial Manager V1 的通用 stateful manager 动作是 intent-only，
    除非补专用 confirmed-action executor，否则确认后不直接落地执行
  - live broker 下单/撤单在 Financial Manager V1 中继续保持 blocked
  - Hermes 代码只作为 reference，不允许 embed/import/sidecar-run

参考文档：

- `docs/architecture/hermes-0.15.1-vs-aiask-deep-review-2026-06-04.md`
- `docs/architecture/hermes-boundary.md`
- `docs/architecture/hermes-financial-product-parity.md`

## 2. 本轮开发要解决的真实问题

### 2.1 基线问题

当前 AIASK 在 runtime、文档、桌面测试三个层面同时存在 Hermes 基线陈旧问题：

- 后端基线常量停留在 `0.14.0`
- parity 文档仍以 `v0.14.0` 为参考
- 桌面 test/mock 仍使用 `0.14.0` 叙述

这会直接导致：

- 审查和实现依据不一致
- `/v1/hermes/status` 的叙事可信度下降
- 前端状态面与后端真实能力之间出现认知漂移

### 2.2 前端主路径问题

当前桌面端更像“金融功能工作台集合”，还不是一个强 Agent 主路径产品。

具体表现：

- `desktop/src/App.tsx` 承担了大量 workspace 分发职责
- session、thread、run event、tool call、approval、gateway、MCP、plugins
  缺少一条清晰的主用户路径把它们串起来
- diagnostics/full console 同时承担了太多“真实平台入口”的角色

这会造成：

- 用户难以判断“我现在是在和 Agent 工作，还是在做运维排查”
- 很多后端已具备的能力只能以 snapshot/诊断方式被看到，无法高效操作

### 2.3 运维产品化问题

AIASK 当前已经有大量原生管理接口，但前端未形成成体系的运维管理面：

- sessions / runs
- tools / approvals
- plugins / skills
- MCP / connectors
- gateway / delivery
- readiness / health / diagnostics

这导致后端广度已经具备，但产品化承载和使用效率不匹配。

### 2.4 扩展承载问题

AIASK 现有插件机制更像“runner 桥接层”，而不是“前后端统一扩展系统”。

问题不在于当前实现错误，而在于：

- 没有统一的页面扩展机制
- 没有统一的前端 slot/page 承载协议
- 插件 readiness、生命周期、安装/启用状态的表达还比较薄

### 2.5 安全边界问题

这个不是“缺口”，而是必须保持的边界：

- 不执行外部 Hermes dashboard JavaScript
- 不引入 vendor Hermes runtime
- 不让 raw manager / raw stateful MCP 动作直达模型
- 不削弱 `finance_safe -> intent -> confirmation` 这条链
- 不把金融数据、策略工厂、交易/纸面交易、券商连接实现迁入 Hermes core
- 不让 Desktop 绕过 Agent HTTP API 直接调用 MCP 或 manager

本方案所有借鉴都必须在这个边界内完成。

### 2.6 金融工作台边界问题

当前 AIASK 的金融能力不是占位能力，而是已经有完整的产品与安全链路：

- Desktop 有 Financial Manager、Quant Research、Strategy Factory、Factor Factory、
  Incubation Factory、Data Sync 等入口
- Agent 已注册 `agent_analyze_stock`、`agent_quant_data_gate`、`agent_backtest_suite`、
  `agent_portfolio_risk`、`agent_quant_research_run`、`agent_factory_*`、
  `agent_action_intent_*` 等金融工具
- AKShare MCP、Strategy Factory、Quant Core、finance MCP servers 仍是金融领域实现 owner
- Financial Manager V1 支持只读查询与 ActionIntent 创建，但通用 stateful manager 动作
  在确认后仍为 intent-only，不由 Desktop 自动执行
- live broker 下单/撤单保持禁用；券商区域只展示账户、持仓、订单、成交等只读能力

因此本轮不做“金融系统迁移到 Hermes”。金融工作台的处理原则是：

1. 先在信息架构上从总导航中拆出独立金融分组
2. 保持现有金融业务页面与 Agent 安全 facade
3. 如需补状态型动作闭环，只为明确低风险动作补专用 confirmed-action executor
4. 不把金融 manager 的 raw action 暴露给模型或 Desktop

## 3. 产品目标与非目标

### 3.1 产品目标

本轮开发后，AIASK 桌面端应更接近下面的产品结构：

1. 进入应用后，用户首先看到清晰的 Agent 主工作流入口
2. 用户可以围绕 session 连续工作，而不是在不同 workspace 之间跳来跳去
3. 运维、扩展、连接能力有各自独立、可操作的管理页
4. 金融工作台仍然存在，但不再承担整个应用的总导航逻辑
5. 插件、skills、gateway、MCP 的状态与可用性更容易理解

### 3.2 非目标

本轮明确不做：

1. 不复刻 Hermes runtime
2. 不复刻 Hermes dashboard 外部插件执行模型
3. 不优先做“视觉上更像 Hermes”的 UI 模仿
4. 不在 session 主链路未成型前，继续横向扩大量平台页面
5. 不削弱金融安全约束来换取表面通用性
6. 不把金融系统并入 Hermes core
7. 不把 Financial Manager V1 的 intent-only 动作默认为确认后自动执行

## 4. 目标产品结构

### 4.1 目标信息架构

桌面端建议重构为三层主分组：

#### A. Agent

面向主链路：

- Workbench
- Sessions
- Runs / Events
- Tools / Intents / Approvals

#### B. 金融工作台

面向金融研究与操作：

- Financial Manager
- Quant Research
- Strategy Factory
- Factor Factory
- Incubation Factory
- Data / Automation / Workflows

#### C. 运维与扩展

面向连接、配置、扩展、诊断：

- MCP / Connectors
- Gateway / Delivery
- Plugins / Skills
- Readiness / Health
- Settings / Modes

### 4.2 目标用户主路径

本轮重点把以下链路做顺：

1. 用户连接本地 Agent
2. 进入 Workbench
3. 选择最近会话或创建新任务
4. 看到任务运行状态、tool call 摘要、关键事件
5. 如遇 ActionIntent、approval 或连接问题，可以快速进入 Tools / Intents / Approvals
   或 MCP / Gateway 页面
6. 如需金融研究或工厂动作，再进入金融工作台分组

这条路径要比当前更自然，不能继续依赖 diagnostics 作为默认观察入口。

## 5. 前端详细方案

下面按页面级拆解前端开发目标。

### 5.1 导航与外壳层

#### 页面目标

- 让用户一眼区分 Agent、金融、运维三类功能
- 让应用外壳不再被单一大文件持续堆分支

#### 当前问题

- `desktop/src/App.tsx` 同时承担：
  - 页面分发
  - 连接状态控制
  - session/workbench 调度
  - Hermes 控制台刷新
  - settings 模式切换

#### 设计目标

- 侧边导航分组明确
- 顶层页面注册与分发结构更清晰
- Settings 不再和主工作流混在一个巨大条件分支里

#### 涉及文件

- `desktop/src/App.tsx`
- `desktop/src/views.ts`
- `desktop/src/components/AppSidebar.tsx`

#### 任务

- FE-001 重构顶层 view model
- FE-002 为 Agent/金融/运维建立分组配置
- FE-003 让 sidebar 支持分组、当前状态、可达性提示
- FE-004 把硬编码 view switch 逐步替换为页面注册表

#### 验收

- 主导航至少分成三组
- 不需要通读整个 `App.tsx` 才知道页面结构
- 新增一个页面时，不需要继续复制大型 `mainView === "..."` 条件分支

### 5.2 Workbench 主页面

#### 页面目标

Workbench 要成为 AIASK 的第一工作入口，而不是“众多 workspace 中的一个”。

#### 页面职责

- 展示当前连接状态
- 新建任务
- 继续最近会话
- 展示当前运行态
- 展示关键 tool call / approval / event 摘要
- 支持快速跳转到相关管理页面

#### 数据来源

- `health`
- `/v1/hermes/status`
- 会话历史/线程数据
- run events
- tool catalog
- approvals 摘要

#### 涉及文件

- `desktop/src/features/agent/AgentWorkspace.tsx`
- `desktop/src/hooks/useAgentWorkbench.ts`
- `desktop/src/App.tsx`

#### 组件建议

- `WorkbenchHeader`
- `RecentSessionsPanel`
- `CurrentRunPanel`
- `ToolActivityPanel`
- `PendingApprovalsPanel`
- `QuickJumpPanel`

#### 任务

- FE-010 定义 workbench 页面信息架构
- FE-011 增加最近会话与最近运行摘要区
- FE-012 增加关键事件摘要区
- FE-013 增加快速跳转：
  - Tools
  - Approvals
  - MCP
  - Gateway
  - Readiness

#### 验收

- 用户可在 workbench 完成：
  - 开始会话
  - 继续会话
  - 查看当前运行状态
  - 跳转处理审批或连接问题

### 5.3 Sessions 页面

#### 页面目标

让会话成为可独立浏览、筛选、恢复、审查的核心对象。

#### 页面职责

- 查看会话列表
- 根据时间、状态、用户筛选
- 打开某个会话
- 查看该会话的最近运行摘要
- 支持从会话回到 workbench

#### 数据来源

- `/v1/hermes/sessions`
- 会话搜索/会话详情相关接口

#### 建议交互

- 左侧列表，右侧详情
- 支持“最近活跃”“最近创建”“有审批”“有报错”筛选

#### 任务

- FE-020 设计 sessions 列表页
- FE-021 增加会话筛选与搜索
- FE-022 增加会话摘要卡片：
  - 时间
  - 用户
  - 最近事件
  - 当前状态

#### 验收

- 用户能快速找到过去的会话并恢复上下文

### 5.4 Runs / Events 页面

#### 页面目标

把 run events 从“调试信息”升级为一等运行观察面。

#### 页面职责

- 查看当前/历史 run 的事件时间线
- 查看关键 tool call、approval、error、gateway 投递、MCP 失败节点
- 支持从事件跳转到相关管理面

#### 数据来源

- runs / run events 接口

#### 建议交互

- 时间线视图
- 列表视图
- 事件类型过滤：
  - tool
  - approval
  - gateway
  - MCP
  - error
  - system

#### 任务

- FE-030 设计 run/event 数据模型
- FE-031 设计时间线组件
- FE-032 为关键事件增加跳转能力

#### 验收

- 用户能用 run/event 页面而不是 console 文本去理解一次任务过程

### 5.5 Tools / Intents / Approvals 页面

#### 页面目标

把工具目录与审批动作做成真正的管理页。

#### 页面职责

- 查看当前可用工具
- 区分：
  - finance_safe
  - full mode
  - read_only
  - stateful
- 查看当前审批项、ActionIntent 与状态
- 让用户理解为什么某些动作被阻断

需要明确区分两条控制链：

- `/intents`：金融/状态型业务动作的 durable intent 链路，
  例如 strategy/data/factor/incubation/gateway/webhook 以及 Financial Manager V1 的意图创建
- `/v1/approvals`：通用控制面审批链路，
  例如危险命令、Home Assistant、learning proposal、平台管理动作等

两者都属于“需要人工确认”的用户体验，但不是同一个后端对象，
前端可以在同一页面展示，但必须用不同标签和操作文案表达。

#### 数据来源

- `/v1/tools`
- `/v1/hermes/tools`
- `/intents`
- `/v1/approvals`

#### 建议交互

- 左侧工具列表 + 右侧详情
- 标签显示：
  - category
  - side_effect
  - confirmation_required
  - toolset

#### 任务

- FE-040 设计工具目录页
- FE-041 增加工具过滤器
- FE-042 设计 intents / approvals 双面板
- FE-043 补上被阻断原因与 full mode 提示文案

#### 验收

- 用户能理解：
  - 当前模式下哪些工具可用
  - 哪些工具需要 full mode
  - 哪些金融或业务动作进入 ActionIntent
  - 哪些通用控制动作进入 approval
  - Financial Manager V1 哪些动作只是 intent-only，不会确认后自动落地

### 5.6 MCP / Connectors 页面

#### 页面目标

把连接能力做成统一的接入中心。

#### 页面职责

- 展示 MCP 服务器状态、OAuth 状态、发现状态
- 展示 connector 的配置与连接情况
- 支持诊断常见失败：
  - 未配置
  - OAuth 缺失
  - discovery 失败
  - server down

#### 数据来源

- `/v1/mcp/servers`
- `/v1/mcp/tools`
- `/v1/mcp/resources`
- `/v1/mcp/prompts`
- `/v1/mcp/oauth_status`
- `/v1/connectors`
- `/v1/connectors/summary`

#### 建议交互

- 顶部摘要区
- MCP 列表
- connector 列表
- 详情抽屉或详情页

#### 任务

- FE-050 统一 MCP 与 connectors 视图层结构
- FE-051 设计状态徽标体系
- FE-052 增加错误原因解释与下一步动作建议

#### 验收

- 用户能在单一页面理解“接入层为什么不能工作”

### 5.7 Gateway / Delivery 页面

#### 页面目标

让消息交付、平台状态、目录刷新、重试路径更可见。

#### 页面职责

- 查看各平台状态
- 查看消息投递记录
- 查看 directory/channel 目录
- 重试失败消息
- 查看 daemon / platform health

#### 数据来源

- `/v1/gateway/status`
- `/v1/gateway/platforms`
- `/v1/gateway/messages`
- `/v1/gateway/directory`
- `/v1/gateway/daemon/status`
- `/v1/gateway/platforms/{platform}/health`

#### 任务

- FE-060 设计 gateway 总览页
- FE-061 设计消息记录列表
- FE-062 增加平台健康状态细节
- FE-063 增加失败消息重试入口

#### 验收

- 用户能知道：
  - 哪个平台挂了
  - 最近一次进出站消息是否成功
  - 重试是否有效

### 5.8 Plugins / Skills 页面

#### 页面目标

把当前偏“注册表展示”的能力，重构为生命周期管理页。

#### 页面职责

- 区分已安装、已启用、已配置、可测试、失败原因
- 展示 tool / command / hook 数量
- 展示 quick use / apply to chat 能力
- 展示 readiness

#### 数据来源

- `/v1/plugins`
- `/v1/skills`
- plugin commands/test 接口

#### 任务

- FE-070 设计 plugins 列表页与详情页
- FE-071 设计 skills 列表页与 quick use 流程
- FE-072 增加 readiness/test 状态展示
- FE-073 把“只读注册表视角”收敛为“状态总览 + 详情”

#### 验收

- 用户能判断：
  - 插件是否真的可用
  - skill 能否快速应用到当前会话

### 5.9 Readiness / Health 页面

#### 页面目标

让健康检查不再散落在各处，而是成为统一运维入口。

#### 页面职责

- 总览 AIASK 当前运行健康
- 拆分查看：
  - AI provider
  - gateway
  - plugins
  - MCP
  - financial system
  - full mode / control token

#### 数据来源

- `/health`
- `/health/detailed`
- `/v1/hermes/status`
- `/v1/hermes/readiness`
- `/v1/financial-system/readiness`

#### 任务

- FE-080 设计 readiness overview
- FE-081 增加子系统状态卡
- FE-082 增加缺 token / mode mismatch 提示

#### 验收

- 用户进入此页后可以 10-20 秒内判断问题主要在哪一层

### 5.10 Settings / Mode 页面

#### 页面目标

让 endpoint、token、profile、mode 的设置更明确。

#### 页面职责

- endpoint 管理
- API token / control token 状态提示
- `finance_safe` / `hermes_full` 模式说明
- 当前 user / profile 说明

#### 任务

- FE-090 优化 settings 分区
- FE-091 增加模式影响说明
- FE-092 增加 token / endpoint 测试反馈

#### 验收

- 用户清楚知道当前运行模式以及它影响哪些页面和能力

### 5.11 前端状态模型重构

#### 目标

把当前较容易缠绕的状态分层。

#### 建议状态切片

- `connectionState`
- `sessionState`
- `runState`
- `opsState`
- `settingsState`
- `extensionState`

#### 涉及文件

- `desktop/src/App.tsx`
- `desktop/src/hooks/useHermesConsole.ts`
- `desktop/src/hooks/useAgentWorkbench.ts`
- `desktop/src/types.ts`

#### 任务

- FE-100 梳理现有状态职责图
- FE-101 定义新状态边界
- FE-102 拆分 hook 职责

#### 验收

- 页面切换与刷新行为更可预测
- 不同视图不再通过单一大状态对象互相牵连

### 5.12 前端测试方案

#### 测试重点

- 顶层导航分组
- workbench 主路径
- sessions 页面
- tools/intents/approvals 页面
- MCP / gateway 页面
- readiness 页面
- baseline 版本展示

#### 任务

- FE-110 更新旧的 baseline 断言
- FE-111 为新页面加组件测试
- FE-112 为主流程加 e2e

#### 验收

- 核心主链路不依赖纯人工验证

## 6. 后端详细方案

后端本轮不以“新增更多通用能力”为目标，而以“收敛、补强、产品化既有能力”
为目标。

### 6.1 Hermes 基线刷新

#### 任务

- BE-001 更新 `packages/agent/src/aiask_agent/capabilities.py` 中的版本常量
- BE-002 更新 parity 相关文档引用
- BE-003 增加针对 baseline 一致性的测试或 drift 检查

#### 验收

- runtime、doc、test 三层基线一致

### 6.2 `/v1/hermes/status` 与 readiness contract 收敛

#### 目标

让前端更容易用统一方式解释系统状态。

#### 方向

- 保留现有原生字段
- 清理不必要的概念噪音
- 让前端更容易读出：
  - 当前 toolset
  - full mode 是否可用/已激活
  - parity 摘要
  - 关键子系统状态

#### 任务

- BE-010 梳理 status payload 字段表
- BE-011 梳理 readiness payload 字段表
- BE-012 明确前端展示所需字段与可选字段

#### 验收

- 前端不需要堆很多 defensive mapping 就能组织核心状态页

### 6.3 Sessions / Runs / Events 支撑能力

#### 目标

支撑前端做独立 sessions/runs 页面。

#### 当前方向

- 复用现有 session store 和 run event 能力
- 如现有接口过于零散，可补 AIASK-native summary 接口

#### 可补充接口候选

- session 列表摘要接口
- run 列表摘要接口
- 单个 run 的事件聚合摘要

#### 任务

- BE-020 盘点现有 session/run/event API 是否足够
- BE-021 若不足，新增 summary 接口而不是让前端做过多 N 次请求拼装
- BE-022 统一 event 类型枚举与展示字段

#### 验收

- 前端可以低成本做出 sessions / runs / events 页面

### 6.4 Tools / Intents / Approvals 支撑能力

#### 目标

让工具、ActionIntent 和通用 approval 状态更易展示。

#### 任务

- BE-030 梳理 `/v1/tools` 与 `/v1/hermes/tools` 的语义差异
- BE-031 为工具项补齐展示所需 metadata：
  - category
  - side_effect
  - confirmation_required
  - toolset visibility
- BE-032 梳理 `/intents` 状态模型，明确金融/业务 stateful action 的确认链
- BE-033 梳理 `/v1/approvals` 状态模型，明确通用控制面 approval 的确认链
- BE-034 明确两类对象在前端同页展示时的字段映射、操作文案与错误码

#### 验收

- 前端可以直接构建工具标签、ActionIntent 面板和通用 approval 面板
- 用户不会把 Financial Manager V1 的 intent-only 动作误解为确认后一定会执行

### 6.5 MCP / Gateway / Connectors 支撑能力

#### 目标

让接入层状态更适合产品化页面。

#### 任务

- BE-040 统一 MCP summary 字段
- BE-041 统一 connector summary 字段
- BE-042 统一 gateway platform health 字段
- BE-043 为常见失败原因提供稳定错误码/状态码

#### 验收

- 前端可以稳定展示“未配置 / 认证缺失 / 发现失败 / 服务不可达”等状态

### 6.6 Plugins / Skills 支撑能力

#### 目标

让插件和 skill 的可用性判断更清晰。

#### 任务

- BE-050 梳理 plugin 列表返回字段
- BE-051 补齐 readiness / configured / failure reason 表达
- BE-052 梳理 skill snapshot 返回结构，便于前端分组展示

#### 验收

- 前端可明确区分：
  - 已存在但未启用
  - 已启用但未配置
  - 已启用且可用

### 6.7 前后端契约与类型同步

#### 目标

减少 `desktop/src/types.ts` 与服务端 contract 漂移。

#### 任务

- BE-060 盘点前端关键类型：
  - HermesStatus
  - FullModeConsoleData
  - Plugin/Skill/MCP/Gateway 状态结构
- BE-061 建立 contract 清单
- BE-062 补契约测试或 snapshot 测试

#### 验收

- 大版本前端重构时不再靠“猜字段”

## 7. 插件与扩展机制方案

### 7.1 本轮目标

本轮不是把 AIASK 变成 Hermes dashboard plugin host，而是做一套
AIASK-native 的受控扩展承载。

### 7.2 设计原则

1. 不执行外部 JS
2. 不引入 vendor dashboard SDK 作为运行时依赖
3. 先支持内部 slot/page 扩展，再考虑更广的扩展能力
4. 插件扩展服务于：
   - 页面挂载
   - 状态展示
   - quick action
   - readiness 呈现

### 7.3 前端插槽建议

- sidebar-top
- sidebar-secondary
- header-left
- header-right
- pre-main
- post-main
- overlay

### 7.4 页面扩展 contract 建议

每个扩展页面至少要声明：

- `id`
- `label`
- `group`
- `icon`
- `route`
- `requiresControlToken`
- `requiresFullMode`
- `mountPosition`

### 7.5 任务

- EXT-001 定义 slot schema
- EXT-002 定义 page registration schema
- EXT-003 选 1-2 个内部页面试点挂载

## 8. 分阶段实施计划

### 阶段 0：基线与契约整理

目标：

- 先把“我们到底在对齐哪个 Hermes”这个问题彻底清掉
- 为后续前端重组整理接口与契约

任务范围：

- BE-001 ~ BE-003
- BE-060 ~ BE-062
- FE-110

交付物：

- 更新后的基线常量
- 更新后的文档
- 更新后的旧测试
- 契约清单

建议周期：

- 1 周

### 阶段 1A：前端外壳与导航重组

目标：

- 先把 Agent / 金融 / 运维三层信息架构落地
- 收敛 `App.tsx` 的页面分发职责
- 只搬迁金融工作台入口，不先改金融业务页面内部逻辑

任务范围：

- FE-001 ~ FE-004
- FE-100 ~ FE-101

交付物：

- 新导航分组
- 初步 view registry / route registry
- `App.tsx` 分发复杂度下降
- 金融工作台在独立分组下保持原功能可用

建议周期：

- 1 周

### 阶段 1B：Workbench 主入口增强

目标：

- 让 Workbench 成为 AIASK 的第一工作入口
- 先提供最近会话、最近运行、关键事件和待处理项摘要，不追求一次做完整控制台

任务范围：

- FE-010 ~ FE-013
- BE-020 初步盘点

交付物：

- 新 workbench 信息架构
- 最近会话 / 最近运行摘要
- quick jump：Readiness、Tools / Intents / Approvals、MCP / Gateway

建议周期：

- 1-2 周

### 阶段 1C：Sessions / Runs / Events 一等页面

目标：

- 把 session、run、event 从诊断信息升级为可浏览、可恢复、可审查的核心对象

任务范围：

- FE-020 ~ FE-022
- FE-030 ~ FE-032
- FE-102
- BE-020 ~ BE-022

交付物：

- sessions 页面
- runs/events 页面
- event 类型与跳转策略

建议周期：

- 2 周

### 阶段 2：运维产品化页面

目标：

- 把 Tools/Intents/Approvals、MCP/Connectors、Gateway、Readiness 做成可操作页面

任务范围：

- FE-040 ~ FE-043
- FE-050 ~ FE-052
- FE-060 ~ FE-063
- FE-080 ~ FE-082
- BE-030 ~ BE-043

交付物：

- Tools / Intents / Approvals 页面
- MCP / Connectors 页面
- Gateway 页面
- Readiness / Health 页面

建议周期：

- 2-3 周

### 阶段 3：扩展承载与生命周期管理

目标：

- 解决页面扩展承载和插件状态表达问题

任务范围：

- FE-070 ~ FE-073
- FE-090 ~ FE-092
- EXT-001 ~ EXT-003
- BE-050 ~ BE-052

交付物：

- Plugins / Skills 页面重构
- Settings / Mode 页面增强
- 内部 slot/page 扩展机制试点

建议周期：

- 2-4 周

## 9. 任务包拆分建议

为了方便排期，建议按任务包拆：

### 包 A：基线修复包

- 后端常量
- 文档
- 前端 mock/test
- baseline drift 检查

### 包 B：桌面 IA 包

- 导航分组
- view 注册结构
- App.tsx 收敛

### 包 C：Agent 主链路包

- Workbench
- Sessions
- Runs / Events

### 包 D：运维页面包

- Tools / Intents / Approvals
- MCP / Connectors
- Gateway
- Readiness

### 包 E：扩展承载包

- Plugins / Skills
- Settings / Mode
- slot / page contract

## 10. 依赖关系

### 强依赖

- 阶段 1A 依赖阶段 0 的基线与契约清理
- 阶段 1B 依赖阶段 1A 的导航与 App 外壳收敛
- 阶段 1C 依赖阶段 1B 的 Workbench 主入口结构
- 阶段 2 依赖阶段 1A 的导航分组稳定；Readiness 可提前并行
- 阶段 3 依赖阶段 2 的页面组织大致稳定

### 弱依赖

- Gateway 页面与 MCP 页面可并行
- Plugins 页面与 Skills 页面可并行
- Readiness 页面可与 Tools / Intents / Approvals 页面并行

## 11. 风险与应对

### 风险 1：前端重构过大，影响现有金融工作台

应对：

- 先做导航重分组，不先大改金融业务页面本身
- 先让金融工作台“搬家”，再考虑内部细节重构

### 风险 2：前端页面想做得太完整，倒逼后端增加过多新接口

应对：

- 先盘点现有接口
- 仅在前端拼装成本过高时增加 summary API
- 优先补 contract，不追求扩 runtime breadth

### 风险 3：为了借鉴 Hermes 扩展机制而误触安全边界

应对：

- 坚持内部 slot/page 扩展
- 不执行外部 JS
- 不引入 vendor runtime 依赖

### 风险 4：状态模型重构期间产生临时复杂度

应对：

- 先画状态职责图
- 逐步拆而不是一次性替换全部 hooks

## 12. 测试与验收方案

### 12.1 后端

- 基线一致性测试
- contract/shape 测试
- endpoint drift 继续保留
- intent/confirmation 护栏测试继续保留

### 12.2 前端

- 导航分组测试
- workbench 主流程测试
- sessions / runs 页面测试
- tools/intents/approvals 页面测试
- MCP / gateway 页面测试
- readiness 页面测试

### 12.3 E2E

建议覆盖：

1. 连接本地 Agent -> 进入 Workbench -> 发起任务
2. 查看会话 -> 查看运行事件
3. 查看 ActionIntent / approval -> 跳转处理
4. 查看 MCP / Gateway 健康状态
5. 查看 Plugins / Skills 状态

## 13. 验收标准

### 13.1 产品验收

- 用户能通过 session-first 路径使用 AIASK
- 运维能力不再深埋在 diagnostics 中
- 金融工作台仍然完整，但与 Agent 主路径分层清晰

### 13.2 技术验收

- Hermes 基线统一到 `0.15.1`
- 无 vendor runtime 依赖引入
- `agent_*` / `finance_safe` / intent guardrails 未被削弱

### 13.3 维护性验收

- `App.tsx` 复杂度下降
- 状态职责更清晰
- 前后端 contract 漂移减少

## 14. 建议的首批 issue

如果马上开工，建议先拆这 10 个 issue：

1. 基线刷新：更新 AIASK Hermes baseline 到 0.15.1
2. 基线刷新：更新 parity/doc/test/mock 中的旧基线叙述
3. 桌面 IA：重构导航分组为 Agent/金融/运维
4. Workbench：增加最近会话与运行摘要
5. Sessions：实现会话列表与详情页
6. Runs：实现运行事件页
7. Tools：实现工具目录、ActionIntent 与 approval 页面
8. MCP：实现 MCP/connector 接入页面
9. Gateway：实现平台状态与消息页面
10. Readiness：实现健康总览页

## 15. 下一步建议

最推荐的推进顺序是：

1. 先做基线修复与 contract 清单
2. 同时出桌面 IA 草图
3. 然后优先做：
   - Workbench
   - Sessions
   - Runs
   - Readiness
4. 再做：
   - Tools / Intents / Approvals
   - MCP / Gateway
   - Plugins / Skills

这样做的原因是，先把主链路做顺，后面的运维页面和扩展机制才不会再次堆回一个大杂烩 UI 里。
