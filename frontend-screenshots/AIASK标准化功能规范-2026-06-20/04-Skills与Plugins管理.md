# Skills 与 Plugins 管理

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Skills 与 Plugins 管理 |
| 功能编号前缀 | `PLUGIN` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P1 必做 |
| 代码基准 | `desktop/src/features/agent-pages/PluginsSkillsPage.tsx`、`desktop/src/services/aiaskApi.ts`、`packages/agent/src/aiask_agent/routes/plugins_skills.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐 Skills/Plugins 生命周期、门禁、接口和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Skill | 可被 Agent/Workbench 采用的能力说明与流程资产 | `/v1/skills` |
| Plugin | 原生扩展，可能包含工具、命令和 hooks | `/v1/plugins` |
| Command Test | 插件命令测试，不等于启用插件写入能力 | `/v1/plugins/{name}/commands/{command}/test` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 技能和插件是扩展能力，如果只列名字，用户不知道是否启用、可测试、需要令牌还是失败。 |
| 解决方案 | 分 Skills、Plugins、commands、tools、test、enable/config 状态展示；变更动作受 control token 约束。 |
| 业务价值 | 扩展能力可发现、可验证、可审计。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| PLUGIN-US-001 | P1 | 作为用户，我希望查看已安装技能，以便把能力应用到任务。 | Skills 列表和描述可见。 |
| PLUGIN-US-002 | P1 | 作为管理员，我希望测试插件工具和命令，以便确认扩展可用。 | test 状态和错误可见。 |
| PLUGIN-US-003 | P1 | 作为安全负责人，我希望插件安装/启停受控，以便避免扩展越权。 | 无 control token 时变更按钮禁用。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| PLUGIN-F001 | Skills 列表 | P1 | `GET /v1/skills` | 与 Workbench 上下文联动 | 技能名称、描述、路径可见 |
| PLUGIN-F002 | Plugins 列表 | P1 | `GET /v1/plugins` | 失败态细化 | enabled/ready/configured 可见 |
| PLUGIN-F003 | Plugin commands | P1 | `/v1/plugins/{name}/commands` | 参数展示 | 命令和 schema 可见 |
| PLUGIN-F004 | Test/变更动作 | P1 | plugin test/POST/PATCH routes | control token 状态 | 变更不静默执行 |

### 1.4 业务规则与边界

| 规则 | 说明 | 验收 |
|---|---|---|
| 只读和变更分离 | 列表可读，安装/启停/删除受控 | token 状态可见 |
| 动态工具审查 | 插件工具进入模型可见前必须经过 `agent_*` facade | 工具目录不出现 raw plugin bypass |
| Secret redaction | 插件凭据只显示配置状态 | 不展示 token |

## 2. 流程设计

| 步骤 | 用户操作 | 前端行为 | Agent/API | 异常 |
|---|---|---|---|---|
| 1 | 打开插件技能页 | 加载 skills/plugins | `/v1/skills`、`/v1/plugins` | gated/degraded |
| 2 | 查看插件 | 展开 commands/tools/hooks | `/v1/plugins/{name}/commands` | plugin missing |
| 3 | 测试命令 | 输入参数并测试 | command/tool test routes | test failed |
| 4 | 修改启用状态 | 点击启停/安装 | plugin mutation route | 无 control token disabled |

状态机：`loading -> ready|empty|error -> testing|mutating -> success|failed|gated`。

## 3. 架构设计

Desktop 插件技能页只展示和触发 Agent route；Agent 负责插件生命周期、工具测试和策略约束。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 前端方法 | 关键字段 |
|---|---|---|---|---|---|
| Skills 列表 | `/v1/skills` | GET | API/control | `skillsList()` | `name`、`description`、`path` |
| Plugins 列表 | `/v1/plugins` | GET | API/control | `pluginsList()` | `enabled`、`ready`、`configured` |
| Plugin commands | `/v1/plugins/{name}/commands` | GET | control | `pluginCommands()` | `name`、`schema` |
| Tool test | `/v1/plugins/{name}/tools/{tool}/test` | POST | control | plugin test | `status`、`error_code` |

## 5. 前端设计

组件：`PluginsSkillsPage -> SkillList -> PluginTable -> CommandDrawer -> TestResultPanel -> RawPayloadDetails`。

## 6. 开发规范

新增插件 UI 必须同步 mock、API client、组件测试，并标记哪些动作只是测试、哪些动作会修改本地扩展状态。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| PLUGIN-201 | 插件未配置 | missing env/config | 显示配置项名 |
| PLUGIN-401 | 插件操作需要控制令牌 | control token missing | 禁用变更 |
| PLUGIN-302 | 插件测试失败 | command/tool error | 显示 error_code |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-PLUGIN-001 | Skills list | 展示技能描述和状态 |
| TC-PLUGIN-002 | Plugin commands | 展示命令 schema |
| TC-PLUGIN-003 | Tool test fail | 显示失败原因 |
| TC-PLUGIN-004 | 无 control token | 变更按钮 gated |

## 9. 不做什么

- 不让插件动态工具绕过 `agent_*`。
- 不把测试按钮写成启用/安装。
- 不展示 secret。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| 页面 | `desktop/src/features/agent-pages/PluginsSkillsPage.tsx` | 通过 `useCapabilityWorkbench()` 读取 plugins/skills，并把 selected skill 应用回 chat | 技能不是静态说明，需要有 apply-to-chat 流程 |
| 组件 | `PluginLifecycleCard.tsx`、`SkillsPanel.tsx`、`PluginsPanel.tsx` | 插件启停、测试、命令、安装/更新/删除均有 gated/disabled 状态 | 文档要写生命周期和门禁，不只是“管理插件” |
| API | `routes/plugins_skills.py`、`services/api/ops.ts` | `/v1/skills`、`/v1/plugins`、`/v1/plugins/{name}/commands`、tool/command test | 新增插件必须补命令和工具测试契约 |
| 安全边界 | `tools/policy.py` | 动态工具进入模型可见面前必须通过 `agent_*` | 不允许 raw plugin tool 绕过 Agent policy |

### 10.2 可执行功能说明

| 小功能 | PM 可读说明 | 开发细节 | QA 断言 |
|---|---|---|---|
| Skills 列表 | 用户看到技能名称、描述、来源、启用状态和可应用入口 | `skillsList()` 聚合能力 payload | 列表为空时有 empty 和安装入口 |
| Skill 安装/更新/删除 | 修改技能是本地扩展变更，需要 control token | `skillInstall()`、`skillUpdate()`、`skillDelete()` | 无 token 禁用；失败显示 error_code |
| Plugin 工具测试 | 插件工具可以测试，但测试结果不等于模型可见 | `pluginToolTest()`、`pluginCommandTest()` | 测试失败不影响其他插件 |
| 插件启停 | 启停是状态写入，需要审计 | `pluginToggle()`、`pluginUpsert()` | 变更后刷新状态，secret redacted |

### 10.3 成熟技术采用

参考 MCP 和 OWASP API Security：扩展系统必须有来源、权限、测试、失败隔离和名称混淆防护。AIASK 采用静态页面 + Agent HTTP 管理 + control token 的方式，不采用浏览器动态加载第三方插件 JavaScript。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 顶部指标 | skills、plugins、enabled、configured、ready、failed、tools、commands、hooks | `PluginsSkillsPage.tsx`、`MetricCard` | failed 数量高亮，control token 状态常驻 |
| Skills 列表 | skill 名称、描述、适用场景、启用/可用状态 | `routes/plugins_skills.py`、`SkillsPanel.tsx` | 可被 Workbench 引用，但不直接执行副作用 |
| Plugins 列表 | plugin manifest、enabled、configured、tool/command/hook 数量 | `PluginLifecycleCard.tsx` | 安装/启停/更新必须 gated 或创建受控动作 |
| 详情与测试 | 命令、工具、hook、错误、raw manifest | `RawEvidencePanel`、`AiaskApi.plugin*` | command/tool test 显示输入、输出、错误码 |

### 11.2 组件树

```text
PluginsSkillsPage
├── PluginSkillMetricStrip
├── SkillsList
├── PluginsList
│   └── PluginLifecycleCard
└── PluginCommandToolDetailPanel
```

### 11.3 状态和响应式

- `empty`：说明没有安装技能/插件，并显示目录或配置入口，不显示空白表格。
- `blocked`：插件操作被策略拒绝时保留后端 reason，不能提供绕过按钮。
- 窄屏采用 tabs：Skills、Plugins、Commands、Raw；插件卡片单列展示。

## 原有内容保留

## 功能目标

Skills 是任务能力模板，Plugins 是可扩展运行能力。第一版需要支持内置 skills 浏览、搜索、安装/更新/删除，以及插件启用、配置、工具测试、命令测试。Codex 本地技能、Agent runtime skills、AKShare MCP runtime skills 三者必须分清。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Agent skills/plugins routes | `packages/agent/src/aiask_agent/routes/plugins_skills.py` |
| Plugin runtime | `packages/agent/src/aiask_agent/plugin_runtime.py` |
| Skill packs | `packages/agent/src/aiask_agent/skill_packs.py` |
| 金融技能模板 | `packages/agent/src/aiask_agent/financial_skill_templates.py` |
| AKShare runtime skills | `packages/akshare-mcp/src/akshare_mcp/tools/skills.py`、`skills_registry.py` |
| 前端页面 | `desktop/src/features/agent-pages/PluginsSkillsPage.tsx`、`desktop/src/features/skills/SkillsPanel.tsx` |
| API client | `skillsList`、`skillInstall`、`skillUpdate`、`skillDelete`、`pluginToggle`、`pluginUpsert`、`pluginToolTest` |

## 用户流程

1. 打开 Plugins/Skills 页面，先加载内置 skill 与插件列表。
2. 用户搜索技能，查看用途、输入、输出、适用任务、是否可执行。
3. 安装或更新技能需要 control token；删除也需要确认。
4. 插件展示 manifest、启用状态、命令、工具和测试结果。
5. 点击测试插件工具，展示输入参数、输出摘要和错误。
6. 技能应用到对话时，应进入 Workbench 上下文，而不是直接执行高风险动作。

## 前端展现

| 区域 | 内容 |
|---|---|
| 内置 Skills | 名称、分类、描述、可执行状态、适用场景 |
| 添加 Skills | 来源、版本、安装按钮、更新按钮 |
| 插件列表 | enabled、manifest、commands、tools、风险 |
| 测试区 | 参数输入、运行结果、错误详情、raw payload 折叠 |

## API 合约

| 操作 | Endpoint |
|---|---|
| skills 列表 | `GET /v1/skills` |
| 安装 | `POST /v1/skills` |
| 更新 | `PATCH /v1/skills/{name}` |
| 删除 | `DELETE /v1/skills/{name}` |
| plugins 列表 | `GET /v1/plugins` |
| upsert plugin | `POST /v1/plugins` |
| toggle plugin | `PATCH /v1/plugins/{name}` |
| 测试工具 | `POST /v1/plugins/{name}/tools/{tool}/test` |
| 命令列表/测试 | `/v1/plugins/{name}/commands`、`/commands/{command}/test` |

## 验收规则

1. 页面必须明确区分 Codex 技能、Agent 技能、AKShare MCP 技能。
2. 插件/技能变更不能无 token 执行。
3. 插件工具测试不能泄露 secret。
4. 删除技能必须二次确认。
5. 技能应用到 Workbench 后要能在右侧上下文看到引用。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 前端表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 用户分不清三类 skill | 页面分 Codex/Agent/AKShare runtime 三个来源 | payload 增加 source/type 字段 | `skill_packs.py`、AKShare `tools/skills.py` | 来源标签清楚 |
| 安装 skill 失败 | 显示原因和回滚状态 | `/v1/skills` 返回 structured error | `routes/plugins_skills.py` | 不留下半安装状态 |
| skill 可注册但不可执行 | 状态黄色，显示 registered_only | AKShare runtime skills 返回 executable_count | `tools/skills.py` | 不显示运行按钮 |
| 插件启用后工具不可用 | 插件卡显示工具测试失败 | plugin tool test routes | `plugin_runtime.py` | 失败不影响插件列表 |
| 删除误操作 | 二次确认，显示影响范围 | DELETE 需要 control token | `routes/plugins_skills.py` | 无 token 禁用 |
| 将 skill 用于对话 | Workbench 右侧显示已应用 skill | skill context 写入任务上下文 | Workbench context panel | skill 名称、版本、参数可见 |

### 页面信息架构

| 区域 | 字段/控件 |
|---|---|
| Skill Catalog | name、source、category、version、executable、description |
| Skill Detail | inputs、outputs、examples、risks、related tools |
| Skill Manage | install、update、delete、apply to workbench |
| Plugin Catalog | name、enabled、manifest、commands、tools、last_error |
| Plugin Test | tool/command selector、params editor、result、raw payload |

### 状态机

| 状态 | 说明 |
|---|---|
| `installed` | 已安装 |
| `registered_only` | 已注册但不可执行 |
| `enabled` | 插件启用 |
| `disabled` | 插件禁用 |
| `testing` | 正在测试工具/命令 |
| `failed` | 安装、更新、测试失败 |
| `gated` | 缺 control token |

### 代码生成/修改步骤

1. 后端新增 skill 字段时同步更新 `desktop/src/types.ts` 或局部类型。
2. `AiaskApi` 增加/复用 `skillsList`、`skillInstall`、`pluginToolTest` 等方法。
3. `PluginsSkillsPage.tsx` 拆分 Catalog、Detail、Manage、TestPanel。
4. mock 覆盖 installed、registered_only、test_failed、control_missing。
5. 测试补：secret redaction、删除确认、缺 token 禁用、应用 skill 到 Workbench。

### 不做什么

- 不把 Codex 本地技能当成 Agent runtime skill 自动安装。
- 不在 skill 描述里承诺不存在的后端能力。
- 不让插件管理绕过 control token。
- 不把插件工具未经测试就加入默认工具推荐。
