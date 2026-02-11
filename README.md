# AIASK - AI驱动的A股量化分析系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个基于 MCP (Model Context Protocol) 的智能股票分析系统，集成了数据获取、技术分析、回测和可视化功能。

## 🌟 主要特性

### 📊 数据获取
- **多数据源支持**：东方财富、新浪、腾讯、Tushare、AKShare、Baostock
- **实时行情**：支持A股实时行情查询
- **历史数据**：日线、分钟级K线数据（1m, 5m, 15m, 30m, 60m）
- **基本面数据**：财务报表、估值指标、龙虎榜、北向资金等
- **高级数据**：融资融券、大宗交易、新闻资讯

### 🔧 技术分析
- **技术指标**：MA、EMA、MACD、RSI、KDJ、BOLL等30+指标
- **形态识别**：K线形态、趋势线、支撑阻力位识别
- **因子分析**：多因子模型、因子相关性分析
- **风险模型**：VaR、最大回撤、夏普比率等

### 📈 量化回测
- **策略回测**：支持自定义策略回测
- **向量化回测**：高性能批量回测
- **参数优化**：网格搜索、遗传算法优化
- **绩效分析**：详细的回测报告和可视化

### 💼 投资组合
- **组合优化**：马科维茨模型、风险平价
- **仓位管理**：动态仓位调整
- **模拟交易**：纸上交易功能

### 🧩 客户端接入
- **MCP 客户端**：支持 Claude Desktop、Cursor 等标准 MCP 客户端
- **可视化能力**：通过客户端或外部面板展示 K 线图、指标图表、回测曲线

## 🏗️ 系统架构

```
AIASK/
├── packages/
│   ├── mcp-server-compact/     # MCP服务器（核心）
│   │   ├── src/
│   │   │   ├── adapters/       # 数据源适配器
│   │   │   ├── services/       # 业务逻辑
│   │   │   ├── storage/        # 数据存储（TimescaleDB）
│   │   │   └── tools/          # MCP工具定义
│   │   └── scripts/            # 数据初始化脚本
│   │
│   ├── akshare-mcp/            # Python数据适配器
│   │   └── src/akshare_mcp/
│   │       ├── tools/          # 数据获取工具
│   │       └── core/           # 核心功能
│
├── workflows/                  # 回测模板
└── reports/                    # 测试报告
```

## 🚀 快速开始

### 前置要求

- Node.js >= 20.0.0
- Python >= 3.12
- PostgreSQL + TimescaleDB
- Docker（推荐）

### 1. 安装依赖

```bash
# 安装 Node.js 依赖
cd packages/mcp-server-compact
npm install

# 安装 Python 依赖
cd ../akshare-mcp
pip install -e .
```

### 2. 启动数据库

```bash
# 使用 Docker 启动 TimescaleDB
docker run -d \
  --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=password \
  timescale/timescaledb:latest-pg16
```

### 3. 初始化数据

```bash
cd packages/mcp-server-compact

# 创建数据表
npm run db:migrate

# 下载基础数据（日线K线、财务数据）
npm run init-db

# 下载高级数据（分钟K线、龙虎榜等）- 可选
npm run init-db-full
```

### 4. 启动服务

```bash
# 启动 MCP 服务器
cd packages/mcp-server-compact
npm start
```

## 📖 使用文档

### MCP 工具列表

系统提供了100+个MCP工具，主要分类：

- **市场数据**：实时行情、K线数据、板块数据
- **基本面分析**：财务数据、估值指标、行业分析
- **技术分析**：技术指标计算、形态识别
- **量化回测**：策略回测、参数优化
- **投资组合**：组合优化、风险管理
- **数据管理**：数据同步、缓存管理

详细文档请查看：[MCP工具文档](./packages/mcp-server-compact/README.md)

### 数据下载说明

系统支持两种数据下载模式：

1. **基础数据**（必需）：
   - 股票列表（5,473只A股）
   - 日线K线（250天历史）
   - 财务数据
   - 存储空间：约200MB
   - 下载时间：1-2小时

2. **高级数据**（可选）：
   - 分钟K线（1m, 5m, 15m, 30m, 60m）
   - 龙虎榜、北向资金、融资融券
   - 大宗交易、新闻资讯
   - 存储空间：约2-3GB（30天）
   - 下载时间：2-4小时

详细说明：[高级数据下载指南](./packages/mcp-server-compact/ADVANCED_DATA_GUIDE.md)

## 🔧 配置

### 环境变量

创建 `.env` 文件：

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=password

# Tushare Token（可选）
TUSHARE_TOKEN=your_token_here

# 日志级别
LOG_LEVEL=info
```

### MCP 配置

在 Claude Desktop 或其他 MCP 客户端中配置：

```json
{
  "mcpServers": {
    "aiask-stock": {
      "command": "node",
      "args": ["/path/to/packages/mcp-server-compact/dist/index.js"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432"
      }
    }
  }
}
```

## 📊 数据统计

当前系统包含：

- **股票数量**：5,473只A股
- **日线K线**：128万+条记录
- **分钟K线**：2500万+条记录（部分）
- **数据源**：6个主要数据源
- **技术指标**：30+个
- **MCP工具**：100+个

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

## 📄 许可证

MIT License

## 🙏 致谢

- [AKShare](https://github.com/akfamily/akshare) - 开源金融数据接口
- [TimescaleDB](https://www.timescale.com/) - 时序数据库
- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP协议

## 📞 联系方式

- GitHub: [@walkingzzzy](https://github.com/walkingzzzy)
- 项目地址: https://github.com/walkingzzzy/AIASK

---

⭐ 如果这个项目对你有帮助，请给个 Star！
