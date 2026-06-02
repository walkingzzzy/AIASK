# N05 · K线形态与相似形态检索 + 条件收益 + 信号命中率

- **判定**: ✅ 通过 (Pass=12 / Degraded=16 / Fail-graceful=2 / Fail-schema=0)
- **真实工具调用数**: 30

## 核心成果

1. **信号命中率（亮点）**：`get_signal_hit_rate(600519, rsi_oversold)` sample=27，5d/10d/20d hit_rate=0.67/0.92/1.0，**按牛/震/熊三种 regime 分层**统计 + recent_signals 带日期与 regime + reliable 标志。证据质量极高。
2. **条件收益（亮点）**：`get_conditional_returns(600519, rsi_14<30)` 命中 24 次，10d win_rate=0.79 / mean=2.48%，含 median/std/worst/best 完整分布。多条件 AND（volume_ratio>2 AND pct_change>0）也正确。
3. **相似检索**：K 线相似（茅台→泸州老窖/汾酒同业）、基本面相似（含 roe/pe/pb features）、技术面相似均正常；`search_by_kline` 主动排除 ST/退市股（quality_filter，v2 §2.4 修复保持）。
4. **市场文档检索**：`vector_search_manager.market_docs` 用 hybrid（dense+lexical）返回真实研报（万联证券"增持"、华鑫"买入"）。
5. **样本不足保护**：sample<10 时 reliability_warning + insufficient_sample 标志显式。

## ⚠ 关键发现

- **F-N05-1 [MEDIUM]**：`get_conditional_returns` 不支持**字段对字段比较**。传 `{field:'close', op:'>', value:'ma_5'}` 时 `condition_matches=0`（静默），字符串 'ma_5' 未被解析为字段而当作常量。AI 想表达"价格上穿 5 日线"会静默得空结果，且无 value 类型校验提示。
- **F-N05-2 [LOW]**：向量检索全线 `db_empty_result → python` 兜底（向量库为空）。结果质量正常，显式标注。

## 评价

量化条件概率证据链是本系统的强项（hit_rate/regime/分布/reliable 一应俱全）。唯一改进点是条件收益的 value 应支持字段引用或对非数值 value 给出明确校验错误。
