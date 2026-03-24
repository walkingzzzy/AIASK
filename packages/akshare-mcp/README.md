# AKShare MCP Server v2.0

> 当前定位：本包是 AIASK monorepo 中的 **Python MCP 服务端**，为 Web / BFF / AI 客户端提供股票数据、研究、回测、风险分析、策略工厂等能力。
>
> **文档校准说明**：本 README 以当前仓库可见代码、脚本、测试与审计文档为依据，强调“当前状态 + 环境依赖 + 已知限制”。除非有明确证据，本文件不再使用“完整”“生产就绪”“全覆盖”等绝对表述。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 1. 当前已确认的角色与边界

### 1.1 在 monorepo 中的职责
- `apps/web`：Next.js 前端，负责页面与交互层
- `apps/bff`：NestJS BFF，负责 HTTP/WebSocket API、鉴权、降级包装、审计等
- `packages/akshare-mcp`：Python MCP 服务，提供数据、回测、研究、策略等能力
- `packages/shared-types`：前后端共享类型；当前仍存在 workspace 解析与构建顺序风险

### 1.2 当前能力范围
按代码与现有文档可确认，本包覆盖以下方向：
- 行情 / K 线 / 盘口 / 板块 / 资金流 / 基本面 / 估值 / 研报等数据能力
- 技术分析、回测、绩效指标、部分参数优化与批量研究能力
- 风险分析、压力测试、组合优化、策略管理、策略工厂相关能力
- Skills / Managers / 工具注册表支撑的流程化调用能力
- 公共数据源降级与失败隔离能力

### 1.3 不应被当作当前事实的表述
以下内容在当前仓库中**不应直接写成既成事实**：
- 所有模块“生产就绪”
- 运行时工具总数固定不变，或“所有工具在任意环境下都可稳定调用”
- 所有数据源都长期稳定且口径一致
- 所有回测、组合、压力测试口径都已完全统一
- 所有可选环境能力都可在当前主机上直接运行

---

## 2. 运行与环境依赖

### 2.1 Python 与依赖
- Python 基线：`>=3.12`
- 项目定义见：`pyproject.toml`
- 可选依赖组：
  - `legacy`：包含 `akshare`、`baostock`、`efinance` 等兼容/历史数据链路依赖
  - `parallel`：包含 `ray[default]`，用于部分并行能力

### 2.2 重要外部依赖
不同能力对环境要求不同，请不要假设“开箱即全量可用”：
- **数据库**：部分存储、回测工件、策略工厂、运行历史能力依赖 PostgreSQL / TimescaleDB 配置
- **Tushare Token**：会影响部分结构化财务/基本面覆盖
- **外部数据源可用性**：AKShare、Eastmoney、Sina、Tencent、Tushare 等链路都可能波动或降级

### 2.3 当前已知运行约束
- `start_server.py` 已确认会设置安全默认值：`MCP_HOST=127.0.0.1`、`MCP_ALLOW_TOKEN_PASSTHROUGH=false`
- `start_server.py` 已明确 stdio 模式下日志走 `stderr`，避免污染 MCP 协议输出
- 但“HTTP 启动时一定会强制拒绝所有不安全配置”的完整校验链，本次仅在部分代码中看到默认值设置，**仍需结合更多实现再次核实**

---

## 3. 安装与启动

### 3.1 使用 uv（推荐）
```bash
cd packages/akshare-mcp
uv sync --extra legacy
uv run python start_server.py
```

说明：
- `legacy` extras 对当前仓库中的部分历史/兼容数据源导入很重要
- 若首次在 macOS 上通过 MCP 客户端直接 `uv run`，可能因建环境和下载依赖而超时

### 3.2 使用 venv / 已有 Python 环境
```bash
cd packages/akshare-mcp
python -m venv .venv
source .venv/bin/activate   # Windows 改为 .venv\Scripts\activate
pip install -r requirements.txt
python start_server.py
```

### 3.3 推荐的 MCP 接入方式
- **首选：stdio**
- HTTP / SSE / streamable-http 仅建议在明确理解本地绑定、来源校验、鉴权与 token 透传风险后再启用
- 配置示例请以 `docs/MCP_CONFIG_GUIDE.md` 为准

---

## 4. 配置项说明

建议在 `packages/akshare-mcp/.env` 中维护项目配置，并区分“必需项”和“增强项”：

```bash
# 数据库（部分功能强依赖）
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stockdb
DB_USER=postgres
DB_PASSWORD=your_password

# 可选：增强部分结构化数据能力
TUSHARE_TOKEN=your_tushare_token

```

说明：
- 数据库不是所有工具都强依赖，但部分能力没有数据库时会降级、不可用或无法沉淀结果
- macOS / 非 Windows 主机会仅保留公共工具与降级逻辑
- 若未配置相关依赖，请在文档、演示和测试时明确说明能力边界

---

## 5. 验证方式（按当前仓库可见线索整理）

### 5.1 基础启动验证
```bash
cd packages/akshare-mcp
python start_server.py
```

可观察点：
- 进程能否正常启动
- stdio 场景下日志是否写入 `stderr`
- `.env` 与 `PYTHONPATH` 是否生效

### 5.2 数据库与测试
```bash
cd packages/akshare-mcp
python scripts/verify_db_connection.py
pytest tests/ -v
```

说明：
- 测试存在并不等于所有模块都被充分覆盖
- 数据质量、跨源一致性、回测口径等仍应结合专项报告复核

### 5.3 守卫与审计脚本
```bash
cd /Users/mac/Desktop/股票
python scripts/skill_coverage_audit.py --check-thresholds
python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt
```

若需要继续核对运行时注册、健康检查和回归结果，可再结合仓库中已有的 `make` 目标与 `reports/` 目录产物进行复核；但请以实际存在的命令和当前环境为准，不要默认所有目标在所有机器上都能直接通过。

---

## 6. 当前已知限制与风险提示

### 6.1 数据质量与跨源一致性
历史数据质量报告显示，部分数据链路曾出现以下问题：
- CPI、财务、估值等字段存在 `null` 或覆盖不足
- 涨停统计异常为 0
- DMA / 指标值跳变
- 跨源一致性不足

这些问题更适合被理解为：**已有历史审计证据，当前状态需结合最新测试与数据源返回重新验证。**

### 6.2 回测与指标口径
当前仓库中已有 `docs/metrics-contract.md` 对 Sharpe、`win_rate`、执行时点、JIT / mask 路径一致性提出契约要求；但历史审计文档也记录过：
- Sharpe 口径差异
- `win_rate` 统计口径不统一
- look-ahead bias
- 滑点建模仍偏简化

因此，回测结果应视为**研究与验证辅助**，不应在文档中表述为“完全统一且无偏差”。

### 6.3 平台专用能力
- 当前文档与验证默认以 macOS / 非 Windows 主机的公共数据能力为前提
- 无对应平台依赖时，专用能力会降级、跳过或失败
- 相关能力可用不应被视为默认前提

### 6.4 工具层 / 服务层不一致风险
历史可行性分析报告记录过若干“工具层与服务层不一致”问题，例如恐贪指数与压力测试口径不对齐。这类问题会优先影响：
- MCP 工具直接调用
- AI 客户端消费结果
- BFF 透传或编排链路

当前状态需按具体模块重新回归验证。

### 6.5 日志与审计语义
`logs/risk_audit.jsonl` 中存在 `success=false` 但 `reason="passed"`、`compliance_passed=true` 的记录，说明审计日志语义仍可能引发误解。若基于这些日志做风控结论，应先统一字段解释。

---

## 7. 常见问题（保留当前仍有参考价值的部分）

### 7.1 找不到模块 `akshare_mcp`
- 确认当前目录为 `packages/akshare-mcp`
- 优先使用 `uv run python start_server.py`
- 或执行 `pip install -e .`

### 7.2 数据库连接失败
- 检查 `.env` 中的数据库配置
- 确认 PostgreSQL / TimescaleDB 服务正在运行
- 用 `python scripts/verify_db_connection.py` 做最小验证

### 7.3 首次 MCP 启动超时
- 常见于 macOS + `uv run` 首次建环境
- 可先执行 `uv sync --extra legacy`
- 或改用 `.venv/bin/python start_server.py`

### 7.4 依赖包冲突或可选依赖缺失
- 优先执行 `uv sync --reinstall`
- 若缺 `akshare` 等模块，检查是否安装了 `legacy` extras

---

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

### Cursor MCP 与 Conda/venv 环境统一

若本机有 Conda、MCP 又使用虚拟环境，希望 MCP 使用**项目源码和 .env**，请按 [CURSOR_MCP_SETUP.md](CURSOR_MCP_SETUP.md) 配置：用 **Conda 或 venv 的 Python 直接运行 `start_server.py`**，并设置 **cwd** 为 `packages/akshare-mcp`。也可使用 `run_mcp.sh` 自动选择 Conda/venv。

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


### 6. 估值（Driver DCF v2，P0-1）
```python
# MCP tool: dcf_valuation
# 兼容旧签名：仅传 discount_rate/growth_rate/years 仍可运行
result = await mcp.dcf_valuation(
    code='600519',
    discount_rate=0.10,         # 显式传入则优先使用
    growth_rate=0.05,
    years=5,
    # 以下为新增可选参数（P0-1）
    risk_free_rate=0.03,
    beta=1.0,
    market_risk_premium=0.06,
    cost_of_debt=0.05,
    tax_rate=0.25,
    equity_weight=0.7,
    debt_weight=0.3,
    terminal_growth_rate=0.03,
    capex_ratio=0.04,
    depreciation_ratio=0.03,
    nwc_ratio=0.01,
    enable_sensitivity=True,
)

# 新增关键返回字段
# result['data']['wacc_breakdown']      # 权益成本/税后债务成本/WACC拆解
# result['data']['driver_assumptions']  # 收入驱动项假设
# result['data']['projection']          # 显性期FCF与折现明细
# result['data']['sensitivity']         # g/r/tg 三维敏感性情景
# result['data']['meta']                # 审计字段（trace/兼容模式/折现率来源）
```

> 说明：`dcf_valuation` 已从简化近似模型升级为驱动式 DCF（Revenue→EBIT→NOPAT→FCF）并支持 WACC 拆解与情景敏感性分析。保持工具名与旧调用方式不变，通过参数扩展实现向后兼容。

### 7. 因子IC双口径 + 中性化（P0-2）
```python
# MCP tool: calculate_factor_ic
# 新增可选参数 enable_neutralization（默认 True）
result = await mcp.calculate_factor_ic(
    codes=['600519', '000858', '000001', '600036'],
    factor='momentum',
    period=20,
    enable_neutralization=True,
)

# 兼容字段（历史调用不受影响）
# result['data']['ic']       == result['data']['rank_ic']
# result['data']['p_value']  == result['data']['rank_p_value']

# 新增字段（P0-2）
# result['data']['normal_ic']
# result['data']['rank_ic']
# result['data']['normal_p_value']
# result['data']['rank_p_value']
# result['data']['neutralization']   # 行业/市值/Beta中性化元信息
# result['data']['source_chain']     # 审计来源链
```

> 说明：`calculate_factor_ic` 现已输出 Normal IC（Pearson）+ Rank IC（Spearman）双口径；默认开启行业/市值/Beta中性化。若风格暴露缺失，会自动降级并在 `neutralization.reason` 留痕。
---

## 🏗️ 架构

### 技术栈
- **语言**: Python 3.12+
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

### 数据源测试
在项目根目录下运行数据源完整性测试（Tushare Pro/Legacy、Baostock、eFinance、AKShare 及 DataSourceManager 整合接口）：
```bash
# 从仓库根目录执行（会加载 packages/akshare-mcp/src 并读取 .env）
python scripts/test_data_sources.py
```
需在 `packages/akshare-mcp/.env` 中配置 `TUSHARE_TOKEN` 后 Tushare Pro 测试才会执行；其他数据源无需配置即可尝试。


### Manager 参数与返回格式说明（P1 修复）

为保证 manager 层调用的一致性与向后兼容，新增如下约定：

1. `options_manager` 参数规范
   - `implied_volatility` 标准参数为 `option_price`。
   - 兼容别名：`market_price` / `price`（内部统一映射到 `option_price`）。
   - `calculate_price` / `implied_volatility` 对已传入但非法参数显式报错（如 `option_type` 非 `call/put`、`volatility<=0`）。
   - 当提供 `expiry_date`（`YYYY-MM-DD`）时，会自动换算 `time_to_maturity`；若剩余期限 `<=0` 返回错误。

2. `macro_manager.get_indicators` 口径规范
   - 支持 `indicators`（list 或逗号分隔字符串）。
   - 兼容单值参数：`indicator` / `type` / `indicator_type` / `name`。
   - 完全未传指标参数时，默认 `gdp`（兼容历史调用）。
   - 响应口径与请求严格一致：
     - 单指标：`{indicator_type, data, source, requested_indicators}`
     - 多指标：`{requested_indicators, data, sources}`
   - 对暂无数据指标返回 `unsupported_indicators`（多指标）或 `data=None + message`（单指标）。

3. 回归测试
   - 新增：`tests/test_p1_regressions_managers.py`
   - 覆盖点：
     - `option_price` 别名兼容（`market_price`）
     - `calculate_price` 参数校验错误分支
     - 过期 `expiry_date` 错误分支
     - `macro_manager` 单/多指标口径一致性
     - 未知指标与默认 `gdp` 兼容行为

- 建议执行：`python -m pytest packages/akshare-mcp/tests/test_p1_regressions_managers.py -q`

---

### Manager 参数与返回格式说明（P2 修复）

在 P1 基础上，继续增强可解释性与跨 manager 元数据一致性：

1. `get_realtime_quote`（实时行情）结构化降级字段
   - 新增字段：
     - `attempted_sources`: 实际尝试的数据源列表（按顺序）
     - `source_chain`: 命中链路（如 `['data_source']` 或 `['data_source','akshare']`）
     - `fallback_used`: 是否发生降级
     - `fallback_reason`: 降级原因摘要
     - `data_timestamp`: 数据日期（`YYYY-MM-DD`）
   - 兼容性：原有行情字段（`code/name/price/...`）保持不变，仅增量补充。

2. `decision_manager(action='analyze')` 数据质量语义增强
   - 新增字段：
     - `raw_total_score`: 扣分前原始总分
     - `data_quality.missing_fields`: 缺失财务字段列表
     - `data_quality.financial_data_completeness`: 财务完整度（0~1）
     - `data_quality.score_penalty`: 数据缺失导致的降权分
   - 评分规则：`total_score = max(0, raw_total_score - score_penalty)`。
   - 兼容性：保留 `overall_score/total_score/recommendation` 等原有核心字段。

3. `quant_manager` 统一 `meta` 字段
   - 默认补齐：
     - `meta.data_timestamp`（默认当天 `YYYY-MM-DD`）
     - `meta.source_chain`（默认 `['quant_manager']`）
   - 与既有 `trace_id/tool_version/cached/latency_ms` 等保持统一风格。

4. P2 回归测试
   - 新增：`tests/test_p2_data_quality_and_meta.py`
   - 覆盖点：
     - 行情结构化降级字段注入（含 pydantic 模型返回路径）
     - 决策分析 `data_quality` 与 `raw_total_score` 语义
     - quant manager `meta` 默认值一致性

- 建议执行：
  - `python -m pytest packages/akshare-mcp/tests/test_p2_data_quality_and_meta.py -q`
  - `python -m pytest packages/akshare-mcp/tests/test_p0_regressions.py packages/akshare-mcp/tests/test_p1_regressions_managers.py -q`

---

### 测试覆盖
- ✅ 单元测试: 50+个
- ✅ 性能测试: 7个基准
- ✅ 集成测试: 完整流程
- ✅ P0/P1 回归测试: manager 关键兼容与校验路径

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

### Cursor 中数据库连不上时

依赖数据库的工具（search_stocks、valuation、Manager 等）需要正确连接 PostgreSQL/TimescaleDB。若出现 `password authentication failed for user "postgres"`：

1. **确保 MCP 从项目内启动且能读到 .env**：在 Cursor 的 MCP 配置里把 `command` 设为在**项目根目录**下执行，例如：
   - `command`: `uvx` 或 `python`，`args`: `["--from", "packages/akshare-mcp", "akshare-mcp"]` 或 `["-m", "akshare_mcp.server"]`，并确认**工作目录为项目根**（含 `packages/akshare-mcp/.env` 的目录的上一级）。

2. **或显式传入环境变量**：在 MCP 配置里为该 server 设置 `env`，例如：
   - `DB_PASSWORD`: 你的数据库密码（与 `packages/akshare-mcp/.env` 中一致）
   - `DB_NAME`: 数据库名（如 `stockdb`）
   - 或 `AKSHARE_MCP_ENV`: `.env` 文件的**绝对路径**（如 `/Users/xxx/股票/packages/akshare-mcp/.env`）

保存后**完全重启 Cursor**（或先关闭该 MCP 再重新打开），使新环境生效。


## P1 性能优化说明（方案 C / D）

### 1) 批量回测并发取数（`run_batch_backtest`）

`run_batch_backtest` 新增参数：

- `fetch_concurrency`（默认 `8`）：前置 K 线拉取并发度（内部自动约束在 `1~20`）

返回结果新增字段：

- `timings.io_fetch_seconds`：取数阶段耗时
- `timings.compute_seconds`：回测计算阶段耗时
- `timings.aggregation_seconds`：结果汇总阶段耗时
- `timings.total_seconds`：总耗时
- `source_stats`：各数据来源命中统计（如 `timescaledb`、`market_fallback`、`none`）
- `fetch_concurrency`：本次执行实际并发度
- `performance_goal`：性能目标说明

示例：

```python
result = await run_batch_backtest(
    codes=["600519", "000001", "000858"],
    strategy="ma_cross",
    fetch_concurrency=8,
)
print(result["data"]["timings"])
```

### 2) 缓存层升级（`SimpleCache`）

`SimpleCache` 已升级为 **内存 LRU + 文件缓存** 双层结构：

- 文件写入采用原子替换（临时文件 + `os.replace`）
- 并发访问使用 `threading.RLock` 保护
- 新增统计指标：`total_requests / hits / misses / hit_rate / miss_rate`
- 兼容保留：`get_stats()`，并新增语义化别名 `get_cache_stats()`

示例：

```python
from akshare_mcp.cache import cache

stats = cache.get_cache_stats()
print(stats["hit_rate"], stats["total_requests"])
```

> 说明：以上改动保持原有 `cache.get/set/clear/get_stats` 调用方式不变。

---

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
