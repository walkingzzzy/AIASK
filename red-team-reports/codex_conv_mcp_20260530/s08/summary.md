# N08 · DCF 情景与敏感性 + 蒙特卡洛分布 + 历史估值

- **判定**: ⚠ 通过（含 2 项 HIGH 级缺陷）(Pass=19 / Degraded=6 / Fail-graceful=4 / Fail-schema=2)
- **真实工具调用数**: 31

## 核心成果

1. **蒙特卡洛分布**：`dcf_valuation(enable_distribution)` 茅台返回 mean 4315 亿 + p10/p50/p90 + std + spread_risk=wide，不确定性度量完整。
2. **参数边界保护**：DCF 在 WACC ≤ terminal_growth 时正确 Fail-graceful（终值分母保护）；DDM 在 g ≥ r 时正确报错。
3. **WACC 自定义重算**：beta/risk_free_rate/market_risk_premium 输入后 WACC 正确重算（000651 beta=1.2 → wacc 8.755%）。

## ⚠ 关键发现

- **F-N08-1 [HIGH]**：`scenario_dcf_valuation` 蒙特卡洛/低利润率情景产生**负内在价值与负每股**。300750（新能源）Base 情景 intrinsic=-2744 亿、per_share=**-53.25 元**，分布 min=-1.9 万亿；002594（汽车）三情景全负、per_share=-32.52 元。负利润率叠加高 capex 使 FCF 转负、终值公式放大成巨额负值，但工具照常 `success=true` 输出**负的每股估值**（股价不可能为负），无任何 quality_flag 警示。缺少"内在价值≤0 应转告警/不可估"的合理性护栏。
- **F-N08-2 [HIGH / v2 §2.5 复现]**：`get_historical_valuation(000001)` 混入**上证指数点位 4115.5**。2026-05-26 记录 price=4115.5（pe/pb/cap 均 null），而相邻日平安银行价格都是 10.6-10.9。指数点位污染了个股（000001）历史库，`data_quality` 标了 3 个 missing_cell 但未识别该污染异常值。
- **F-N08-3 [LOW]**：蒙特卡洛 spread_risk=extreme（std≫mean）时仍输出单点估计，应提示不可靠。

## 评价

DCF/DDM 的**参数边界保护很到位**，但两个 HIGH 级问题值得优先处理：①情景 DCF 输出负每股估值无护栏（数学上荒谬的结果直接返回）；②上证指数点位 4115.5 污染平安银行历史估值库（§2.5 老问题在历史估值路径复现）。
