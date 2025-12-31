# AIASK - A股智能分析系统

基于 AKShare + CrewAI 的 A股智能分析平台，通过多 Agent 协作提供专业的投资分析服务。

> 🖥️ **跨平台桌面应用**：Tauri 2.0 + React 18 + TypeScript 构建（Windows / macOS / Linux）

## ✨ 核心特性

| 功能模块 | 说明 |
|---------|------|
| 🎯 AI 智能评分 | 技术面/基本面/资金面/情绪面/风险 五维度 1-10 分综合评分 |
| 🤖 多 Agent 协作 | CrewAI 驱动的专业化 AI 角色协同分析 |
| � 自然语言查询* | 支持股票筛选、个股分析、数据查询等意图识别 |
| � 技术指标情库 | MA/EMA/MACD/RSI/KDJ/BOLL/ATR 等 10+ 核心指标 |
| � 涨停 板分析 | 涨停原因、连板预测、热门概念追踪 |
| 💰 北向资金追踪 | 资金流向、个股持仓、持仓排名 |
| 🐉 龙虎榜分析 | 席位分析、机构/游资追踪 |
| 📈 策略回测 | 基于 backtrader 的 AI 评分策略和动量策略回测 |
| 🧠 向量知识库 | SQLite 向量存储 + FTS5 全文搜索，支持 RAG 检索 |

## 🏗️ 项目架构

```
AIASK/
├── packages/
│   ├── core/           # Python 核心分析引擎
│   │   ├── scoring/        # AI 评分系统
│   │   ├── indicators/     # 技术指标库
│   │   ├── nlp_query/      # 自然语言查询
│   │   ├── backtest/       # 回测系统
│   │   ├── vector_store/   # 向量知识库
│   │   ├── data_layer/     # 数据层（多源聚合+缓存）
│   │   ├── tools/          # CrewAI 工具集
│   │   └── ...
│   ├── api/            # FastAPI 后端服务
│   ├── app/            # Streamlit Web 应用
│   └── frontend/       # React + Tauri 桌面前端
├── tests/              # 测试用例
├── scripts/            # 工具脚本
├── docs/               # 文档
└── data/               # 数据文件（本地缓存）
```

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+（前端开发）
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）

### 安装

```bash
# 克隆项目
git clone https://github.com/walkingzzzy/AIASK.git
cd AIASK

# 安装 Python 依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写 API 密钥
```

### 运行

**方式一：Streamlit Web 应用**
```bash
uv run stock-app
# 访问 http://localhost:8501
```

**方式二：FastAPI 后端 + 前端**
```bash
# 终端 1：启动后端
cd packages/api
uv run uvicorn main:app --reload --port 8000

# 终端 2：启动前端
cd packages/frontend
npm install
npm run dev
```

**方式三：Tauri 桌面应用**
```bash
cd packages/frontend
npm run tauri:dev
```

## 📦 技术栈

| 层级 | 技术 |
|-----|------|
| 前端 | React 18 + TypeScript + Ant Design + ECharts + TailwindCSS |
| 桌面 | Tauri 2.0 |
| 后端 | FastAPI + Uvicorn |
| AI 引擎 | CrewAI + LangChain |
| 数据源 | AKShare（主）+ Tushare（备用） |
| 缓存 | 内存 + SQLite 两级缓存 |
| 向量库 | SQLite + FTS5 |

## 🔧 配置

### 环境变量 (.env)

```bash
# LLM 配置
OPENAI_API_KEY=your_api_key
OPENAI_MODEL_NAME=gpt-4

# 可选：Tushare 备用数据源
TUSHARE_TOKEN=your_token
```

### 支持的股票代码格式

- 上交所：`600519` 或 `600519.SH`
- 深交所：`000001` 或 `000001.SZ`
- 创业板：`300750` 或 `300750.SZ`
- 科创板：`688001` 或 `688001.SH`

## 📖 文档

- [功能使用手册](docs/功能使用手册.md)
- [用户快速入门](docs/用户快速入门.md)
- [投资术语词典](docs/投资术语词典.md)
- [常见问题 FAQ](docs/常见问题FAQ.md)
- [风险提示说明](docs/风险提示说明.md)

## ⚠️ 风险提示

- 本系统仅供学习研究使用，**不构成投资建议**
- A股市场风险较高，投资需谨慎
- 过往业绩不代表未来表现

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

[MIT License](LICENSE)

---

**免责声明**：本系统提供的信息和分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。
