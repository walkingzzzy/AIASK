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


#### DCF估值（P0-1 升级说明）
- `dcf_valuation` 已从简化近似升级为 **Driver DCF + WACC**：
  - 显性期：Revenue→EBIT→NOPAT→FCF
  - 折现率：支持 CAPM + 税后债务成本 + 资本结构拆解
  - 终值：Gordon Growth（校验 `discount_rate/WACC > terminal_growth_rate`）
- 新增可选参数：
  - `risk_free_rate`, `beta`, `market_risk_premium`
  - `cost_of_debt`, `tax_rate`, `equity_weight`, `debt_weight`
  - `terminal_growth_rate`, `capex_ratio`, `depreciation_ratio`, `nwc_ratio`
  - `enable_sensitivity`
- 新增返回字段：
  - `wacc_breakdown`, `driver_assumptions`, `projection`
  - `pv_sum`, `pv_terminal`, `terminal_value`, `sensitivity`, `meta`
- 向后兼容：旧调用方式（仅 `discount_rate/growth_rate/years`）无需改动。

### 因子IC分析（P0-2 升级说明）
- `calculate_factor_ic` 升级为 **双口径 IC 输出**：
  - `normal_ic` / `normal_p_value`（Pearson）
  - `rank_ic` / `rank_p_value`（Spearman）
- 默认启用中性化：`enable_neutralization=True`
  - 中性化维度：行业 / 市值（log） / Beta
  - 返回 `neutralization` 元信息（是否启用、使用风格、降级原因等）
- 向后兼容：保留旧字段
  - `ic` 继续可用（映射 `rank_ic`）
  - `p_value` 继续可用（映射 `rank_p_value`）
- 审计留痕：补充 `source_chain`，记录计算链路。

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
