[深度分析]

# AKShare MCP Server v2.0 代码审查与能力对标报告

> 审查范围：`packages/akshare-mcp/src/akshare_mcp/`（重点：`services/`、`tools/`）

## 一、第一阶段：代码审查与功能盘点

### 1.1 因子与量化核心（services）

#### `services/factor_calculator.py`
已实现基础因子计算、IC评估、分组回测主链路：
- 技术因子：`calculate_momentum`、`calculate_reversal`、`calculate_volatility`
- 基本面/风格因子：`calculate_value_factor`、`calculate_quality_factor`、`calculate_growth_factor`、`calculate_beta_factor`、`calculate_liquidity_factor`
- 评估与回测：`calculate_factor_ic`、`backtest_factor`

#### `services/factor_analysis.py`
因子分析体系较完整：
- `calculate_ic`、`calculate_ic_series`
- `factor_group_backtest`、`factor_turnover`
- `factor_decay`、`_calculate_half_life`
- `factor_correlation_matrix`

#### `services/multi_factor.py`
多因子工程能力明确：
- 标准化：`z_score`、`rank_normalize`、`mad_normalize`
- 合成：`equal_weight`、`ic_weight`、`optimize_weight`
- 分析：`calculate_ic`、`calculate_ic_ir`、`detect_decay`
- 组合构建：`quantile_portfolio`、`optimize_portfolio`

#### `services/llm_alpha.py`
提供 LLM Alpha 原型能力：
- `generate_factor_candidates`
- `evaluate_factor`
- `detect_alpha_decay`
- `optimize_factor_combination`

#### `services/portfolio_optimization.py`
组合优化方法覆盖较全：
- `mean_variance_optimization`
- `black_litterman`
- `efficient_frontier`
- `risk_parity`
- `max_sharpe_ratio`
- `min_variance`

### 1.2 估值与决策工具（tools）

#### `tools/valuation.py`
已实现估值工具：
- `get_valuation_metrics`
- `dcf_valuation`
- `ddm_valuation`（Gordon 模型）
- `relative_valuation`
- `get_historical_valuation`

关键实现观察：
- DCF 使用简化假设：`fcf = net_profit * 0.8`
- 终值计算：`terminal_value = terminal_fcf / (discount_rate - growth_rate)`
- 相对估值支持行业 peer 自动检索与 percentile 比较

#### `tools/decision.py`
决策工具：
- `should_i_buy`
- `should_i_sell`

特征：
- buy 端融合估值、技术、基本面、动量
- 提供 `meta`（`trace_id`、`tool_version`、`source_chain`、`latency_ms`）
- 投资风格阈值映射（aggressive / balanced / conservative）

#### `tools/semantic/diagnosis.py`
四维诊断：
- `smart_stock_diagnosis`
- 综合维度：technical / fundamental / valuation / sentiment
- 加权评分并输出 recommendation + risks

---

## 二、第二阶段：行业标准对标研究

### 2.1 因子研究（Fama-French / Barra / AQR）
行业常见要求：
- 中性化处理（行业/市值/风格）
- 样本外验证（walk-forward / 时间分层CV）
- 因子稳定性（IC/IR/衰减）+ 可交易性（换手/容量/冲击）

当前状态：
- ✅ 已有 IC、分组、衰减、换手、相关矩阵
- ⚠️ 中性化、容量/拥挤度、严格样本外协议仍需增强

### 2.2 估值体系（Damodaran）
行业常见要求：
- 驱动式 DCF（增长、利润率、再投资、WACC）
- 多情景估值（Base/Bull/Bear）
- 行业特异模型（金融、周期、公用事业等）

当前状态：
- ✅ 已有 DCF/DDM/Relative 框架
- ⚠️ DCF 假设偏静态，行业特异与情景估值不足

### 2.3 组合与风控（机构量化）
行业常见要求：
- 成本/冲击建模与约束一体化
- 风险归因与压力测试联动投资建议

当前状态：
- ✅ 优化方法覆盖较全
- ⚠️ 成本、容量、风格暴露约束仍偏基础

---

## 三、第三阶段：差距分析与改进建议

## 3.1 功能完整性对比（现有 vs 行业标准）

| 能力域 | 现状 | 差距 | 优先级 |
|---|---|---|---|
| 因子覆盖 | 技术+基本面+风格较全 | 另类数据因子体系不完整 | P1 |
| 因子评估 | IC/分组/衰减/换手齐备 | 中性化与样本外协议不足 | P0 |
| 回测落地 | 有分组回测 | 成本/冲击/容量建模不足 | P0 |
| 估值能力 | DCF/DDM/Relative 已有 | 行业特异与情景估值不足 | P0 |
| 决策支持 | 规则评分+解释 | 概率化与风险联动不足 | P1 |
| 工程治理 | 模块划分清晰 | 编码一致性与口径契约需强化 | P0 |

## 3.2 重点改进建议

### P0（优先）
1. 建立统一中性化层（industry/size/beta）
2. 建立样本外验证协议（walk-forward + 时间CV）
3. 回测引入交易成本/滑点/冲击/容量模型
4. DCF 升级为驱动式模型（含 WACC 拆解）
5. 增加行业特异估值模板（先银行、消费、科技）

### P1（增强）
1. 决策建议概率化（score -> calibrated probability）
2. 动态因子加权（regime-aware）
3. 另类数据因子插件化（新闻情绪、公告、产业链）

## 3.3 结论
- 项目“功能覆盖”已达到中上水平，尤其因子分析与组合优化骨架完整。
- 主要差距在“研究可复现 + 实盘可迁移”的工程化深度，而非功能缺失。
- 推荐先完成 P0（研究有效性、估值可靠性、回测真实性），再推进 P1（ML/另类数据与决策增强）。

---

## 关键参考链接（联网来源）
- Ken French Data Library: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- Fama/French 5 Factors: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html
- Momentum 因子说明: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html
- MSCI Equity Factor Models: https://www.msci.com/data-and-analytics/factor-investing/equity-factor-models
- MSCI Foundations of Factor Investing: https://www.msci.com/documents/1296102/1336482/Foundations_of_Factor_Investing.pdf
- Damodaran Valuation: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valuation/val.htm
- Damodaran Intrinsic Valuation: https://people.stern.nyu.edu/adamodar/pdfiles/eqnotes/packet1.pdf
- Damodaran Relative Valuation: https://people.stern.nyu.edu/adamodar/pdfiles/eqnotes/packet2pg2.pdf
- AQR Fact, Fiction, and Factor Investing: https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/AQRJPMQuant23FactFictionandFactorInvesting.pdf
- AQR The Case for Momentum Investing: https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/The-Case-for-Momentum-Investing.pdf

使用模型：[gpt-5.3-codex]

