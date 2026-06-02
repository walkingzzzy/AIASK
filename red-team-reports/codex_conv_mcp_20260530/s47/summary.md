# N47 · 条件收益与信号命中率 (get_conditional_returns / get_signal_hit_rate / find_similar_patterns)

- **运行**: 2026-05-30 19:59 · 30 次真实调用
- **判定**: Pass 21 / Degraded 1 / Fail-graceful 1 / Fail-schema 7
- **verdict**: `fail_schema_ma_field_uncaught_exception_and_silent_unknown_field_and_kline_data_anomaly_but_condition_signal_pattern_engines_sound`

## 场景说明
条件收益引擎（AND/OR/区间/越界/空/非法 field/op）、信号命中率（多标的×signal×forward_days）、相似形态（多 window_days×top_n）全面覆盖，并注入 999999 非法码与 000001 污染对照。

## 关键发现

### ★★ F-N47-1（HIGH）get_conditional_returns 对 MA 族字段裸抛未捕获异常
`ma_5`/`ma_20` 字段 → `'DataFrame' object has no attribute 'tolist'`（裸 pandas 异常，整个查询崩溃）。隔离确认单 `ma_5` 即触发，而 `close`/`rsi_14`/`volume_ratio` 正常。MA 是最常用指标字段（parse_selection_query 也支持），却整族不可用。

### ★ F-N47-2（MED）未识别 field / 非法 op 静默返回 0 匹配
`nonexistent_field_zzz`、`op=BADOP`、`macd` 均 → success=true / matches=0，无"未识别字段/非法运算符"告警。AI 无法区分"真无匹配"与"拼错字段"。字段处理呈三态：有效→算 / MA族→崩 / 未识别→静默0。

### ★ F-N47-3（MED）非法码 999999 坐标化到上证指数
`get_signal_hit_rate('999999')` → 在指数数据上算 1 个信号；`find_similar_patterns('999999')` → 基于指数的 5 个相似形态。均未拒绝。**对照：000001 在本场景三工具均正确用平安银行（~11元），无 N46 get_key_levels 的指数污染** — 佐证污染仅限 get_key_levels。

### ★ F-N47-5（MED）002594（比亚迪）K线 -68% 单段收益异常透传多工具
find_similar_patterns 某 match forward 全约 -68%、conditional_returns worst 5d=-69%、signal_hit_rate 20d avg 被拖累。几乎确定是拆股/复权未对齐的数据质量问题，污染所有基于 002594 历史收益的统计。

### F-N47-4（LOW）lookback_days 静默钳制到 30
传 10 → kline_count=30 / lookback_days 回显 30（非 10）。最小约束合理但应标注 requested vs effective。

## 正向亮点

- **★★ get_conditional_returns 条件引擎正确**：AND/OR（2 vs 31 匹配）、同字段双向区间（rsi>=50 AND <=60→89）、全比较运算符、details 逐条件 true/false、forward 统计完整、rsi<0 越界优雅返回 0。
- **★★ get_signal_hit_rate 统计诚实**：sample_count 随流动性变化、reliable 阈值标注、reliability_warning、by_regime 分层、**look-ahead 截断正确**（近期信号仅显示数据可用的 forward 窗口，不编造未来收益）。
- **★★ find_similar_patterns 相似度真实**：0.32-0.85 随 window_days 物理合理（短窗易匹配/长窗难），与 N43 build_quant_context 的 avg_correlation=0 形成鲜明对照。
- ★ 空 conditions→"conditions is required"；forward_days 自定义（[3,5,10]）正确传播。

## 护栏遵守
全只读统计工具，无写操作；DB 约 250 根日线样本限制已在 standing_caveat 标注。
