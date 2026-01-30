# AKShare MCP Server v2

完整的A股量化分析MCP服务

## 安装

```bash
cd packages/akshare-mcp
pip install -e .
```

## 依赖安装

```bash
# 基础依赖
pip install -r requirements.txt

# TA-Lib需要先安装C库
# Windows: 下载whl文件安装
# Linux: sudo apt-get install ta-lib
# macOS: brew install ta-lib

# 可选：并行计算
pip install ray[default]
```

## 环境变量

```bash
# TimescaleDB配置
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=postgres
export DB_USER=postgres
export DB_PASSWORD=password
```

## 启动服务

```bash
python -m akshare_mcp.server
```

## 已实现工具

### 市场数据 (market)
- get_realtime_quote
- get_batch_quotes
- get_kline_data
- get_stock_info
- search_stocks

### 财务数据 (finance)
- get_financials

### 技术分析 (technical)
- calculate_technical_indicators
- check_candlestick_patterns
- get_available_patterns

### 回测 (backtest)
- run_simple_backtest

### 组合管理 (portfolio)
- optimize_portfolio
- analyze_portfolio_risk

### 估值 (valuation)
- get_valuation_metrics
- dcf_valuation

### 决策 (decision)
- should_i_buy
- should_i_sell

### 搜索 (search)
- search_stocks
- available_tools
- get_available_categories

## 性能优化

- 使用Numba JIT编译回测核心代码
- 使用asyncpg异步数据库访问
- 使用pandas-ta/TA-Lib高性能技术指标计算
- 支持Ray并行计算（可选）

## 开发

```bash
# 运行测试
pytest

# 性能测试
pytest --benchmark-only
```
