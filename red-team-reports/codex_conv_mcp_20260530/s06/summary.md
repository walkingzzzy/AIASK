# N06 · 财务基本面深挖

- **判定**: ⚠ 通过（含 1 项 HIGH 级计算缺陷）(Pass=25 / Fail-graceful=1 / Fail-schema=1)
- **真实工具调用数**: 31

## 核心成果

1. **财务数据**：`get_financials` 对 4 标的均返回完整 provider-contract（5 源优先级 + quality_gate 6 项检查全 passed + 逐字段 present/null 标注）。茅台净利率 50.5% / 格力 14.2% / 平安 41.2% / 五粮液 35.3%，数值合理。
2. **估值指标**：`get_valuation_metrics` 9 标的全成功，茅台 PE 19.91 / 平安 PE 4.86 / 招行 PE 6.22，`missing_metrics=[]`。
3. **历史估值**：含去重统计（raw 133 → dedup 10）+ PE/PB mean/median/min/max。
4. **同行对比**：茅台 vs 五粮液 vs 洋河，ROE 10.06/6.3/4.97。

## ⚠ 关键发现

- **F-N06-1 [HIGH]**：**杜邦分析三因子分解失效**。`fundamental_analysis_manager(action=dupont)` 对 600519/000001/000651/000858 **全部**返回 `asset_turnover=0.0` + `equity_multiplier=0.0`，但同时返回 `roe=10.06/2.67/4.0/6.3`。杜邦恒等式 ROE = net_margin × asset_turnover × equity_multiplier 完全不成立（0×0×任何值=0≠返回的 ROE）。杜邦分析的核心价值（拆解 ROE 驱动）失效，AI 会得出"资产周转率为零"的荒谬结论。根因疑似总资产/权益数据未回填。
- **F-N06-2 [LOW]**：revenue_growth/profit_growth/roa/cash_flow 多字段 null（仅单期数据），但 quality_gate 已显式标注 null_fields。

## 评价

财务原始数据与估值层质量很高（contract/quality_gate 完备），但**杜邦分解是确凿的计算逻辑缺陷**，跨 4 个标的稳定复现，建议优先修复（补回总资产周转率与权益乘数的计算）。
