# AKShare MCP Server v2.0

🎉 **完整的A股量化分析服务器** - 集成数据获取、技术分析、回测系统、因子分析、组合优化、智能分析于一体

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)](.)

---

## ✨ 特性

### 🚀 核心功能
- **数据获取**: 实时行情、历史K线、财务数据、龙虎榜、资金流向、板块数据
- **技术分析**: 20+技术指标、形态识别、趋势分析、向量搜索
- **回测系统**: 4种策略、动态止损、仓位管理、并行回测、参数优化
- **因子系统**: 8大类32个因子、IC分析、分组回测、因子评估
- **风险管理**: VaR/CVaR、4种压力测试、Barra风险分解
- **组合优化**: Black-Litterman、有效前沿、风险平价、最大夏普

### 🤖 智能功能
- **NLP查询**: 自然语言查询解析、智能诊断
- **向量搜索**: K线形态相似度搜索、DTW动态时间规整
- **知识图谱**: 产业链分析、影响传导、瓶颈识别
- **AI决策**: 综合分析、智能推荐

### 🛠️ 管理工具
- **30个Managers**: 统一接口管理所有功能
- **100+工具**: 覆盖量化分析全流程

---

## 📊 项目状态

| 模块 | 完成度 | 状态 |
|------|--------|------|
| 数据获取 | 95% | ✅ 生产就绪 |
| 技术分析 | 95% | ✅ 生产就绪 |
| 回测系统 | 100% | ✅ 生产就绪 |
| 因子系统 | 100% | ✅ 生产就绪 |
| 风险管理 | 95% | ✅ 生产就绪 |
| 组合优化 | 100% | ✅ 生产就绪 |
| Manager系统 | 100% | ✅ 生产就绪 |
| 智能分析 | 90% | ✅ 生产就绪 |

**总体状态**: ✅ **生产就绪** (v2.0)

---

## 🚀 快速开始

### 安装
```bash
cd packages/akshare-mcp
pip install -r requirements.txt
```

### 基础使用
```python
from akshare_mcp.storage import get_db
from akshare_mcp.services.backtest import BacktestEngine

# 获取数据
db = get_db()
await db.initialize()
klines = await db.get_klines('000001', limit=250)

# 运行回测
result = BacktestEngine.run_backtest(
    code='000001',
    klines=klines,
    strategy='momentum',
    params={'lookback': 20, 'threshold': 0.02}
)

print(f"收益率: {result['data']['total_return']:.2%}")
```

详细教程请查看 [快速开始指南](GETTING_STARTED.md)

---

## 📚 文档

### 核心文档
- [快速开始](GETTING_STARTED.md) - 新手入门指南
- [完整总结](COMPLETE_SUMMARY.md) - 项目完整总结
- [开发路线图](DEVELOPMENT_ROADMAP.md) - 开发计划和进度

### 阶段报告
- [优先级1报告](README_PRIORITY1.md) - 阻塞性问题修复
- [优先级2报告](PRIORITY2_COMPLETION.md) - 核心功能补充
- [优先级3报告](PRIORITY3_COMPLETION.md) - 高级功能完善

### 快速参考
- [优先级1快速开始](QUICK_START.md)
- [优先级2快速开始](PHASE2_QUICK_START.md)

---

## 🎯 核心功能示例

### 1. 回测系统
```python
# 动量策略回测
result = BacktestEngine.run_backtest(
    code='000001',
    klines=klines,
    strategy='momentum',
    params={'lookback': 20, 'threshold': 0.02}
)

# 参数优化
result = BacktestEngine.optimize_parameters(
    code='000001',
    klines=klines,
    strategy='ma_cross',
    param_ranges={'short_period': [5, 10], 'long_period': [20, 30]}
)

# 并行回测
result = ParallelBacktestEngine.batch_backtest(
    codes=['000001', '000002', '000003'],
    klines_dict=klines_dict,
    strategy='ma_cross'
)
```

### 2. 因子分析
```python
from akshare_mcp.services.factor_calculator_extended import factor_calculator_extended
from akshare_mcp.services.factor_analysis import factor_analyzer

# 计算因子
factors = factor_calculator_extended.calculate_all_factors(
    klines, stock_info, financials
)

# IC分析
ic_result = factor_analyzer.calculate_ic(factor_values, forward_returns)

# 分组回测
backtest_result = factor_analyzer.factor_group_backtest(
    factor_values, returns, n_groups=5
)
```

### 3. 组合优化
```python
from akshare_mcp.services.portfolio_optimization import portfolio_optimizer

# Black-Litterman模型
result = portfolio_optimizer.black_litterman(
    market_weights, cov_matrix, views
)

# 有效前沿
frontier = portfolio_optimizer.efficient_frontier(
    expected_returns, cov_matrix, n_points=50
)

# 风险平价
result = portfolio_optimizer.risk_parity(cov_matrix)
```

### 4. 向量搜索
```python
from akshare_mcp.services.vector_search import vector_search_engine

# 查找相似形态
similar = vector_search_engine.find_similar_patterns(
    query_klines, candidates, top_k=10, method='technical'
)

# 形态识别
pattern = vector_search_engine.recognize_pattern(klines)
```

### 5. NLP查询
```python
from akshare_mcp.services.nlp_query_engine import nlp_query_engine

# 解析自然语言查询
parsed = nlp_query_engine.parse_query('选出市盈率小于30且ROE大于10的股票')

# 智能诊断
diagnosis = nlp_query_engine.diagnose_stock(query, stock_data)
```

---

## 🏗️ 架构

### 技术栈
- **语言**: Python 3.10+
- **框架**: FastMCP
- **数据库**: PostgreSQL + TimescaleDB
- **并行**: Ray
- **优化**: Numba JIT
- **数据源**: AKShare, Tushare, Baostock, 东方财富

### 模块结构
```
akshare-mcp/
├── src/akshare_mcp/
│   ├── services/          # 核心服务
│   │   ├── backtest.py
│   │   ├── factor_calculator_extended.py
│   │   ├── factor_analysis.py
│   │   ├── portfolio_optimization.py
│   │   ├── vector_search.py
│   │   ├── nlp_query_engine.py
│   │   └── industry_knowledge_graph.py
│   ├── tools/             # 工具层
│   │   ├── managers_complete.py
│   │   ├── managers_extended.py
│   │   └── market_blocks.py
│   ├── storage/           # 存储层
│   │   └── timescaledb.py
│   └── server.py          # 服务器入口
├── tests/                 # 测试
│   ├── test_backtest_performance.py
│   └── test_priority3_features.py
└── docs/                  # 文档
```

---

## 📈 性能指标

| 操作 | 数据量 | 性能 | 状态 |
|------|--------|------|------|
| MA Cross回测 | 250天 | < 100ms | ✅ |
| Momentum回测 | 250天 | < 100ms | ✅ |
| RSI回测 | 250天 | < 150ms | ✅ |
| 大数据集回测 | 1000天 | < 500ms | ✅ |
| 参数优化 | 4组参数 | < 1s | ✅ |
| 蒙特卡洛 | 100次 | < 2s | ✅ |
| 并行回测 | 5只股票 | 并发 | ✅ |

---

## 🧪 测试

### 运行测试
```bash
# 所有测试
make test

# 性能测试
make test-perf

# 或使用pytest
pytest tests/ -v
pytest tests/ -v --benchmark-only
```

### 测试覆盖
- ✅ 单元测试: 50+个
- ✅ 性能测试: 7个基准
- ✅ 集成测试: 完整流程

---

## 📦 依赖

### 核心依赖
```
mcp>=1.0.0
akshare>=1.10.0
pandas>=2.0.0
numpy>=1.26.0
scipy>=1.11.0
numba>=0.59.0
asyncpg>=0.29.0
ray>=2.9.0
```

### 开发依赖
```
pytest>=7.0.0
pytest-benchmark>=4.0.0
pytest-asyncio>=0.21.0
```

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 开发流程
1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

### 代码规范
- PEP 8代码风格
- Type hints类型注解
- Docstring文档字符串
- 单元测试覆盖

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [AKShare](https://github.com/akfamily/akshare) - 主要数据源
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP框架
- [Ray](https://github.com/ray-project/ray) - 并行计算
- [Numba](https://github.com/numba/numba) - JIT编译

---

## 📞 联系方式

- **项目**: AKShare MCP Server
- **版本**: v2.0
- **状态**: 生产就绪
- **更新**: 2026-01-29

---

**⭐ 如果这个项目对你有帮助，请给个Star！**

基于 AKShare 的 MCP Server，提供 A 股数据服务。

## 功能

- 实时行情：单只/批量股票行情
- K线数据：日线/周线/月线
- 财务数据：财务指标分析
- 北向资金：沪深港通资金流向
- 板块资金：行业/概念板块资金流向
- 龙虎榜：每日龙虎榜数据
- 融资融券：市场两融数据
- 指数行情：主要指数实时行情
- 股票信息：基本信息查询

## 安装

```bash
cd packages/akshare-mcp
pip install -e .
```

或使用 uv：

```bash
uv pip install -e .
```

## 运行

```bash
akshare-mcp
```

或：

```bash
python -m akshare_mcp.server
```

## MCP 配置

在 `.kiro/settings/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "akshare": {
      "command": "akshare-mcp",
      "args": [],
      "disabled": false
    }
  }
}
```

或使用 uvx（推荐）：

```json
{
  "mcpServers": {
    "akshare": {
      "command": "uvx",
      "args": ["--from", "packages/akshare-mcp", "akshare-mcp"],
      "disabled": false
    }
  }
}
```

## 北向资金数据源说明

北向资金优先使用 Tushare（稳定），其次使用港交所公开日度数据（若可解析），最后才回退到东方财富历史接口。

可选环境变量：

- `TUSHARE_TOKEN`: Tushare Pro token（建议在运行环境里设置，不要写入仓库）
- `NORTH_FUND_STALE_DAYS`: 数据允许的最大滞后天数（默认 5）
- `NORTH_FUND_DAILY_QUOTA`: 北向资金日额度（人民币元，默认 52000000000）
- `HKEX_DAILY_STAT_URL`: 港交所日度数据 URL 模板（默认 `https://www.hkex.com.hk/eng/csm/DailyStat/data_tab_daily_{date}e.js`，`{date}`=YYYYMMDD）

## 可用工具

| 工具名 | 描述 |
|--------|------|
| get_stock_list | 获取A股股票列表 |
| get_realtime_quote | 获取单只股票实时行情 |
| get_batch_quotes | 批量获取股票实时行情 |
| get_kline | 获取K线数据 |
| get_financials | 获取财务指标数据 |
| get_north_fund | 获取北向资金数据 |
| get_sector_fund_flow | 获取行业板块资金流向 |
| get_concept_fund_flow | 获取概念板块资金流向 |
| get_dragon_tiger | 获取龙虎榜数据 |
| get_margin_data | 获取融资融券数据 |
| get_index_quote | 获取指数实时行情 |
| get_stock_info | 获取股票基本信息 |
