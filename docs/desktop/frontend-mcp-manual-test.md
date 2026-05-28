# AIASK Desktop 前端 MCP 手工测试指南

## 真实环境前置条件

Desktop 现在是中文优先界面。请先在默认端点启动 Agent，再使用真实环境 URL `http://127.0.0.1:1420/`：

```powershell
$env:AIASK_AGENT_CONTROL_TOKEN="codex-mcp-test-token"
$env:AIASK_LOCAL_CONTROL_TOKEN="codex-mcp-test-token"
$env:AIASK_AGENT_ENABLE_HERMES_FULL="1"
$env:AIASK_AGENT_TOOLSET="general_full"
$env:AIASK_AGENT_ENABLE_GENERAL_TOOLS="1"
cd C:\Users\walking\Desktop\aiask\packages\agent
uv run aiask-agent
```

第二个终端启动 Desktop dev server：

```powershell
cd C:\Users\walking\Desktop\aiask\desktop
npm.cmd run dev
```

如果“设置”显示旧端点，例如 `http://127.0.0.1:8769`，点击“恢复默认 Agent 端点”，确认 `Endpoint` 字段恢复为 `http://127.0.0.1:8767`，再把同一个测试令牌填入“控制令牌 Control token”，最后点击“测试连接”。

## Mock 环境

使用 `http://127.0.0.1:1420/?mock=1` 验证不依赖真实 Agent 的稳定成功路径。Mock 模式使用 `mock://aiask` 作为预期端点，不应提示切回真实环境的 `8767`。

## 稳定控件名

MCP / 手工测试时使用这些可见名称或 accessible names：

- Agent 提交按钮：`运行`
- Settings endpoint 字段：`Endpoint`
- Settings 恢复操作：`恢复默认 Agent 端点`
- Settings 连接操作：`测试连接`
- Settings 分区：`常规`、`连接`、`令牌与权限`、`技能管理`、`自动化管理`、`模型状态`、`MCP 管理入口`、`工作流入口`、`数据路径`、`高级诊断入口`、`关于`
- MCP 注册操作：`注册本地 MCP 服务`
- MCP 发现操作：`发现或刷新 MCP 服务`
- MCP 资源操作：`读取 MCP 资源`
- MCP 提示词操作：`获取 MCP 提示词`
- MCP OAuth 操作：`启动 MCP OAuth 流程`
- Capabilities 内部 tab：`总览`、`覆盖矩阵`、`连接器`、`Hermes`、`MCP`、`策略工厂`、`孵化`、`技能`、`插件`、`AI 测试`

## 真实环境阻塞分类

真实环境阻塞项按 UI 显示的可执行原因记录：

- `AIASK_OFFLINE`：Agent 在当前配置端点不可达。
- 缺少控制令牌 Control token：启动 Agent 时设置 `AIASK_AGENT_CONTROL_TOKEN` 或 `AIASK_LOCAL_CONTROL_TOKEN`，在“设置”中填入相同值，然后点击“测试连接”。
- Full mode 未就绪：启动 Agent 时设置 `AIASK_AGENT_ENABLE_HERMES_FULL=1`、`AIASK_AGENT_TOOLSET=general_full` 和 `AIASK_AGENT_ENABLE_GENERAL_TOOLS=1`。
- 控制令牌未通过验证：设置页令牌与 Agent 启动环境中的令牌不一致。

不要读取 `.env` 文件，也不要把真实密钥写入报告；只记录环境变量名和已脱敏的测试令牌。

## 设置页真实性边界

设置页只覆盖真实可操作设置、真实管理入口和只读状态：

- 可操作设置：`常规`、`连接`、`令牌与权限`。
- 高级管理：`技能管理`、`自动化管理`。
- 状态与入口：`模型状态`、`MCP 管理入口`、`工作流入口`、`数据路径`、`高级诊断入口`、`关于`。

以下候选设置当前没有真实前端控件，已从设置导航隐藏，测试时不再要求覆盖：`外观`、`Git / 环境`、`工作树`、`浏览器`、`电脑操控`、`归档`。
