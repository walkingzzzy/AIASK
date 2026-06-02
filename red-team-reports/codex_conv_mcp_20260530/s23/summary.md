# N23 · 统一决策

**工具**: decision_consensus / get_unified_decision_summary / get_unified_decision_details / get_unified_decision(wrapper)
**调用**: 30 次 · **结论**: pass

## 覆盖
- decision_consensus：8 标的 × 多 style；带 buy_price+holding_days(引入 should_i_sell)；min_agreement_ratio=0.5/0.6；BADX
- get_unified_decision_summary/details/wrapper：多标的多 style

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N23-1 | medium | 统一决策链对所有买入一律合规阻断(周末非交易)，8 标的全 style 的 action 恒为 watch、suggested_position=0，失去区分度(同 F-N21-1) |
| F-N23-2 | low | 顶层 degraded=true 主因 user_profile_fallback + industry_chain 未匹配，核心决策数据实际完整(envelope 高估降级) |

## 正向能力（本场景为最佳设计样板）
- **★★ decision_consensus 是解决跨工具分歧的核心机制**：系统性暴露 should_i_buy(watch/hold) ↔ build_stock_context(sell) 的 split，输出 directions_distribution / agreement_ratio / tools_agree / tools_split / rationale，把历史已知的"sell vs hold 矛盾"转为透明可审计的共识结论。
- **★ 持仓感知**：传 buy_price+holding_days 引入 should_i_sell——亏损持仓 → 2/3 sell；盈利持仓(300750 +3.7%) → 2/3 hold；actionable 随 P&L 自适应。
- **★ min_agreement_ratio 可调**：0.5 → agree/watch，0.6 → split/hold。
- get_unified_decision_summary 含 data_provenance(各源时间戳)+compliance_notice+details_hint，合规与可追溯性优秀。
- get_unified_decision_details 一站式全量证据；wrapper detail_level 兼容；BADX 全工具优雅拒绝。
- 三分量 diagnostics 与 weights 与 N21 fuse 完全一致。

## standing caveat
周末非交易时段，统一决策因合规闸门一律 action=watch；跨标的 quant/event context 新鲜度不一(05-13~05-29)。
