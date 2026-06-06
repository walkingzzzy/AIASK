# AIASK 项目 Skills 能力配置指南

> 生成时间: 2026-06-05
> 基于: AGENT.md 规范 + 深度功能审查 + 最新行业实践

## 📊 现状分析

### 用户级配置
- ❌ 无独立 `~/.claude/skills` 目录
- ✅ 官方插件市场已安装 (200+ 可用插件)
- ⚠️ 具体插件需按需安装

### 项目级 Skills
- ✅ 16 个专属业务 skills 在 `.codex/skills/`
- ✅ 完整覆盖 Agent、Desktop、三大工厂、金融 MCP、量化核心
- ✅ 符合 AGENT.md 架构规范

---

## 🎯 推荐插件配置

### P0 - 安全与合规（立即安装）

基于 AGENT.md 第 5 节外部基线映射和第 18 条开发优先级。

| 插件 | 用途 | 规范对齐 |
|------|------|---------|
| **code-review** | 多专家 agent 代码审查 | NIST SSDF, OWASP Top 10 |
| **security-guidance** | 安全开发指导 | CISA Secure by Design |
| **42crunch-api-security-testing** | API 安全审计 | OWASP API Security Top 10 2023 |
| **aikido** | SAST/secrets/IaC 扫描 | 综合漏洞检测 |
| **coderabbit** | 外部验证代码审查 | 40+ 静态分析器 |

**参考资料**:
- [OWASP Top 10 2025-2026 工具覆盖指南](https://appsecsanta.com/owasp-top-10-guide)
- [2026 年顶级 SAST 工具](https://www.ox.security/how-sast-tools-help-secure-software/)
- [开源 AppSec 工具对比](https://appsecsanta.com/open-source-tools)

---

### P1 - 开发工具（核心支持）

基于技术栈需求和 AGENT.md 第 3 节"当前工程事实"。

| 插件 | 用途 | 项目需求 |
|------|------|---------|
| **agent-sdk-dev** | Agent SDK 开发 | Agent 控制面开发必需 |
| **mcp-server-dev** | MCP 服务器开发 | 金融 MCP 开发必需 |
| **pyright-lsp** | Python 类型检查 | FastAPI/Pydantic 开发 |
| **typescript-lsp** | TypeScript 语言服务器 | Desktop React/Vite 开发 |
| **pr-review-toolkit** | PR 审查工具 | 收敛 Desktop/Agent 契约 |

**最新发现**（2026 年 6 月）:
- 🔥 [fastmcp-builder](https://github.com/husniadil/fastmcp-builder) - Claude Code 专用 MCP 生产构建 skill
- 🔥 [tauri-plugin-mcp](https://github.com/P3GLEG/tauri-plugin-mcp) - Tauri 应用 AI 调试插件
- 🔥 [fastapi-mcp](https://pypi.org/project/fastapi-mcp/) - 零配置 FastAPI → MCP 工具转换

**参考资料**:
- [构建自定义 MCP 服务器（Python SDK）](https://startdebugging.net/2026/04/how-to-build-a-custom-mcp-server-in-python-with-the-official-sdk/)
- [FastAPI MCP 集成指南](https://medium.com/@ruchi.awasthi63/integrating-mcp-servers-with-fastapi-2c6d0c9a4749)
- [Tauri 安全开发最佳实践](https://code.claude.com/docs/en/plugins-reference)

---

### P2 - 效率提升（按需安装）

| 插件 | 用途 |
|------|------|
| **skill-creator** | 创建和评估自定义 skills |
| **plugin-dev** | 插件开发工具 |
| **claude-code-setup** | 代码库分析与自动化推荐 |
| **claude-md-management** | CLAUDE.md 文件管理 |
| **session-report** | 会话报告生成 |
| **code-simplifier** | 代码简化与重构 |
| **frontend-design** | 前端设计辅助 |

**参考资料**:
- [Claude Code 插件最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code 技能插件终极指南](https://skywork.ai/blog/ai-bot/claude-code-skills-plugin-ultimate-guide/)

---

## 🛠️ 配置步骤

### 步骤 1: 安装 P0 安全插件

```bash
# 在项目根目录执行
claude plugin install code-review
claude plugin install security-guidance
claude plugin install 42crunch-api-security-testing
claude plugin install aikido
claude plugin install coderabbit
```

### 步骤 2: 安装 P1 开发工具

```bash
claude plugin install agent-sdk-dev
claude plugin install mcp-server-dev
claude plugin install pyright-lsp
claude plugin install typescript-lsp
```

### 步骤 3: 配置项目级插件清单

创建 `.claude/plugins.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/plugins.schema.json",
  "version": "1.0",
  "plugins": [
    {
      "source": "marketplace:claude-plugins-official/code-review",
      "enabled": true,
      "description": "多专家代码审查"
    },
    {
      "source": "marketplace:claude-plugins-official/security-guidance",
      "enabled": true,
      "description": "安全开发指导"
    },
    {
      "source": "marketplace:claude-plugins-official/agent-sdk-dev",
      "enabled": true,
      "description": "Agent SDK 开发工具"
    },
    {
      "source": "marketplace:claude-plugins-official/mcp-server-dev",
      "enabled": true,
      "description": "MCP 服务器开发工具"
    }
  ]
}
```

### 步骤 4: 配置 MCP 服务器集成

创建 `.claude/mcp-servers.json`:

```json
{
  "mcpServers": {
    "fastapi-mcp": {
      "command": "uvx",
      "args": ["fastapi-mcp"],
      "env": {
        "FASTAPI_BASE_URL": "http://localhost:8000"
      }
    },
    "tauri-debug": {
      "command": "npx",
      "args": ["-y", "tauri-plugin-mcp"]
    },
    "python-repl": {
      "command": "uvx",
      "args": ["mcp-server-py3repl"]
    }
  }
}
```

---

## 🚀 金融 AI 专用工具

基于量化金融和交易开发需求的特殊配置。

### Model Context Protocol (MCP) 在金融中的应用

**关键发现**:
- MCP 已成为连接 AI 系统与金融服务/交易平台的标准化层
- 描述为"agent 能力的 USB-C"接口
- 支持审计就绪的企业金融工作流

**参考资料**:
- [MCP 如何重塑交易者市场访问](https://www.forbes.com/councils/forbesfinancecouncil/2026/05/08/from-apis-to-ai-interfaces-model-context-protocol-could-reshape-how-traders-access-markets/)
- [MCP 驱动的 Databricks 金融 AI 工作流](https://www.databricks.com/blog/mcp-powered-financial-ai-workflows-databricks)
- [使用 Alpaca 构建 MCP 交易工作流](https://alpaca.markets/learn/mcp-trading-with-claude-alpaca-google-sheets)

### 推荐的金融 MCP 服务器

1. **QuantConnect MCP** - 算法交易平台编排
   - GitHub: [taylorwilsdon/quantconnect-mcp](https://github.com/taylorwilsdon/quantconnect-mcp)
   - 用途: 量化策略回测与实盘集成

2. **Alpaca MCP** - 美股交易 API
   - 用途: 自主交易 agent 构建
   - 支持: 实时市场数据、订单执行

3. **Crypto APIs for MCP** - 加密货币量化研究
   - 推荐: [CoinAPI](https://www.coinapi.io/blog/best-crypto-apis-for-ai-trading-bots-quant-research-and-mcp-workflows-2026)
   - 支持: AI 交易机器人、量化研究工作流

**⚠️ AIASK 项目注意事项**:
根据 AGENT.md 第 2 节和第 9 节：
- ✅ 这些工具适用于研究、回测、paper trading
- ❌ 真实交易默认关闭，需要额外确认、权限 guard、审计
- ✅ 必须明确隔离 dry-run/paper/sandbox 与实盘环境

---

## 📋 最佳实践建议

### 1. 版本锁定策略

根据 [Claude Code 插件标准化指南](https://skywork.ai/blog/claude-code-plugin-standardization-team-guide/)：

- ✅ **锁定插件版本**：防止"在我的机器上能运行"问题
- ✅ **锁定市场版本**：确保团队成员加载相同工具和上下文
- ✅ **减少设置时间**：从数小时降至数分钟

```json
{
  "plugins": [
    {
      "source": "marketplace:claude-plugins-official/code-review@1.2.3",
      "enabled": true
    }
  ]
}
```

### 2. 权限与安全

根据 [Claude Code 安全检查清单](https://repello.ai/blog/claude-code-security-checklist/)：

- ✅ **最小权限原则**：选择性启用代码执行和技能
- ✅ **沙箱测试**：在隔离环境中测试插件
- ✅ **审计追踪**：运行受治理、可审计的自动化
- ⚠️ **显式权限请求**：Claude Code 默认只读，其他操作需请求权限

### 3. 文档驱动开发

- ✅ 清晰的 SKILL.md 设计文件产生最佳结果
- ✅ 记录插件行为和需求
- ✅ 为新贡献者提供明确的入门路径

### 4. 容器化开发（可选）

根据 [容器化 Claude Code + MCP 集成](https://medium.com/@brett_4870/building-a-secure-ai-development-environment-containerized-claude-code-mcp-integration-e2129fe3af5a)：

- 环境隔离，防止意外损害宿主系统
- 完整 MCP 服务器访问
- 适用于高安全需求场景

---

## 📊 用户级 Skills 现状

### 已安装的官方插件（截至 2026-06-05）

通过查看 `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/`，发现已安装：

✅ **已安装的关键插件**:
- `agent-sdk-dev` - Agent SDK 开发 ✓
- `code-review` - 代码审查 ✓
- `code-simplifier` - 代码简化 ✓
- `claude-code-setup` - 代码库分析 ✓
- `claude-md-management` - CLAUDE.md 管理 ✓
- `commit-commands` - Git 提交命令 ✓
- `feature-dev` - 功能开发 ✓
- `frontend-design` - 前端设计 ✓
- `mcp-server-dev` - MCP 服务器开发 ✓
- `mcp-tunnels` - MCP 隧道 ✓
- `plugin-dev` - 插件开发 ✓
- `pr-review-toolkit` - PR 审查工具 ✓

✅ **已安装的 LSP 插件**:
- `clangd-lsp` - C/C++
- `csharp-lsp` - C#
- `gopls-lsp` - Go
- `jdtls-lsp` - Java
- `kotlin-lsp` - Kotlin
- `lua-lsp` - Lua
- `php-lsp` - PHP

⚠️ **缺少但推荐的插件**:
- `pyright-lsp` - Python (项目核心语言) ⚠️
- `typescript-lsp` - TypeScript (Desktop 核心语言) ⚠️
- `security-guidance` - 安全指导 ⚠️
- `42crunch-api-security-testing` - API 安全 ⚠️
- `aikido` - SAST/secrets 扫描 ⚠️
- `coderabbit` - 外部验证代码审查 ⚠️

### 用户级 Skills 目录结构

```
~/.claude/
├── plugins/                           # 插件管理
│   └── marketplaces/
│       └── claude-plugins-official/
│           ├── plugins/               # 官方插件（28+ 个已安装）
│           └── external_plugins/      # 外部插件（Discord, iMessage, Telegram）
├── projects/                          # 项目配置
│   └── c--Users-walking-Desktop-aiask/
│       └── memory/                    # 项目记忆
└── settings.json                      # 全局设置
```

**关键发现**:
- ❌ 没有独立的 `~/.claude/skills` 目录
- ✅ Skills 通过插件（plugins）机制提供
- ✅ 官方市场已安装，但部分关键插件未启用

---

## ⚡ 立即行动：安装缺失的关键插件

基于 AGENT.md 规范和项目技术栈（Python 后端 + React/TypeScript 前端），以下插件**缺失但必需**：

### 1. Python 类型检查（P0 优先级）
```bash
# pyright-lsp 未安装，但项目大量使用 FastAPI + Pydantic
claude plugin install pyright-lsp
```

### 2. TypeScript 类型检查（P0 优先级）
```bash
# typescript-lsp 未安装，但 Desktop 是 React/TypeScript/Vite
claude plugin install typescript-lsp
```

### 3. 安全审查插件（P0 优先级）
```bash
# 根据 AGENT.md 第 5 节外部基线映射要求
claude plugin install security-guidance
claude plugin install 42crunch-api-security-testing
claude plugin install aikido
claude plugin install coderabbit
```

### 4. 测试与质量工具（P1 优先级）
```bash
# 补充测试自动化能力
claude plugin install codspeed           # 性能基准测试
claude plugin install chrome-devtools-mcp  # E2E 测试
```

---

## 📦 推荐的项目级配置

创建 `.claude/project-config.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/project-config.schema.json",
  "project": {
    "name": "aiask",
    "type": "monorepo",
    "languages": ["python", "typescript", "rust"],
    "frameworks": ["fastapi", "react", "tauri", "vite"]
  },
  "development": {
    "required_plugins": [
      "pyright-lsp",
      "typescript-lsp",
      "code-review",
      "security-guidance",
      "agent-sdk-dev",
      "mcp-server-dev"
    ],
    "optional_plugins": [
      "skill-creator",
      "plugin-dev",
      "frontend-design"
    ]
  },
  "security": {
    "baseline": ["NIST SSDF SP 800-218", "OWASP API Security Top 10 2023", "CISA Secure by Design"],
    "required_checks": ["sast", "secrets", "api-security"],
    "plugins": ["aikido", "42crunch-api-security-testing"]
  }
}
```

