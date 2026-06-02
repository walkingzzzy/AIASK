# N07 · 估值多方法 consensus

- **判定**: ⚠ 通过（含 1 项 HIGH 级回归）(Pass=23 / Degraded=8 / Fail-schema=0)
- **真实工具调用数**: 31

## 核心成果

1. **DCF（driver_v2）**：WACC 分解 + 5 年 FCF 投影 + terminal + profit_basis 完整；茅台内在价值 4019 亿，比亚迪含 27 点敏感性矩阵（growth×discount×terminal）。
2. **DDM**：Gordon 模型，茅台 548 元（g=5%）/705 元（g=8%,r=12%），参数敏感正确。
3. **相对估值（亮点）**：`peer_pool_build` 完全透明（候选数/各过滤阶段/放松原因/质量阈值）。茅台 PB 溢价 140%（deviation=extreme），宁德 PE 折价 80%。
4. **情景 DCF**：Bull/Base/Bear 概率加权，茅台 per_share=929.5 元。
5. **行业模板**：19 个行业（银行/白酒/半导体...）DCF 参数齐全。

## ⚠ 关键发现

- **F-N07-1 [HIGH / 回归]**：`valuation_consensus` 内部 **DCF/DDM 全部失败**（`non_positive_net_income_or_shares` / `dividend_unavailable`），但同会话**独立** `dcf_valuation`/`ddm_valuation` 对**同一标的全部成功**（茅台 DCF=4019亿、DDM=548元）。4 个标的稳定复现。consensus（号称汇聚 5 路估值）实际退化为单一 relative_pe。这是 v2 §3.2 宣称"完美修复"工具的**回归**——内部调用与独立工具的数据契约不一致。
- **F-N07-2 [MEDIUM]**：consensus 在 n=1（仅 relative_pe）、stdev=0 时仍输出 `confidence='medium'` 且 rationale 称"across 5 valuation methods"。措辞与实际不符，AI 会高估单点可信度。
- **F-N07-3 [LOW]**：`dcf_valuation.intrinsic_value` 是企业价值（4019 亿元）而 `ddm_valuation.intrinsic_value` 是每股（548 元），同名字段量纲不同，易混淆。

## 评价

单个估值工具（DCF/DDM/相对/情景）质量都很高，但**汇聚层 valuation_consensus 出现回归**，把本应 5 路的 consensus 退化成 1 路且未如实降级 confidence。这是建议优先复查的问题（对照 v2 §3.2 的修复是否在某次改动中被破坏）。
