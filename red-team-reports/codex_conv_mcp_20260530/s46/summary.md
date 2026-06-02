# N46 · 交易计划与关键价位 (get_key_levels / calculate_stop_levels / generate_trade_plan)

- **运行**: 2026-05-30 19:54 · 30 次真实调用
- **判定**: Pass 19 / Degraded 1 / Fail-graceful 2 / Fail-schema 8
- **verdict**: `fail_schema_index_contamination_and_invalid_input_validation_gaps_but_core_stop_rr_position_logic_sound`

## 场景说明
多标的（600519/000001/000651/000858/002594/300750/601318/002304）× 方向（long/short）× 参数（atr_multiplier/capital/risk_per_trade/lookback）全面覆盖三个交易决策工具，并系统注入非法输入：999999 非法码、entry=0/负、risk_per_trade=5/0、lookback=5、非法 direction。

## 关键发现

### ★★ F-N46-1（HIGH）get_key_levels(000001) 指数污染 — 且与同代码其他工具直接矛盾
`get_key_levels('000001')` → current_price=4068.57，`price_calibration{kline_close:10.78, factor:377.4, calibrated:true}` —— 把平安银行 K 线（10.78 元）用 377 倍 factor 校准到上证指数点位（4068），关键价位全锚定错误标的。**而 `calculate_stop_levels('000001')` 用 ~11 元、`generate_trade_plan('000001')` 用 10.78 元都正确**。同一代码三工具两种标的认知，证明 000001↔sh000001 污染修复不彻底，仅 get_key_levels 残留。

### ★★ F-N46-2（HIGH）非法码 999999 三工具均静默坐标化到上证指数
`get_key_levels/calculate_stop_levels/generate_trade_plan('999999')` 全 success=true，回退到上证指数数据产出完整结果（name='' 是唯一线索）。无存在性校验。

### ★★ F-N46-5（HIGH）非正 entry_price 产出负止损价与负股数
`entry=0` → 止损 -57.01；`entry=-50` → 止损 -107.01 + **max_shares=-6000（负股数）**。股价不可能 ≤0，应拒绝。

### ★ F-N46-7（MED）signal_decay 恒报"近60日命中率0%"误警
所有 generate_trade_plan 都报"信号严重衰减：近60日命中率仅为历史的0%"，但 recent_n=0（近60日无样本）。999999 案例 full_sample_hr=1.0（100%命中）仍报此警。把"无近期数据"误判为"近期差"，系统性误导降仓。

### ★ F-N46-8（MED）scenario 仓位超风格上限
conservative 风格 `max_position_pct=25%`，但 scenarios 入场 `position_pct≈29.4-29.9%` 全超 25%。

### F-N46-3（MED）short 止损 method 标签方向错误
做空止损数值正确（entry 上方），但 method 文案仍写"支撑位下方"（应阻力位上方）。

### F-N46-4（MED）risk_per_trade 无上界校验
`risk_per_trade=5`（500%）→ risk_budget=500万（>本金）未拒绝（虽 max_amount 30% 上限意外兜住实际开仓）。

### F-N46-6（LOW）generate_trade_plan confidence 字段不一致
顶层 confidence（0.79）vs confidence_breakdown.final（0.93），系统性偏差 ~0.14。

## 正向亮点

- **★★ calculate_stop_levels 核心逻辑正确**：ATR/结构止损取较近者、RR 1:1/1:2/1:3 随 long/short 正确翻转、A股整手、max_amount 30% 仓位上限、risk_budget=capital×risk_per_trade、trailing_stop；小资金不足1手→0仓、risk=0→0仓 均优雅。
- **★★ get_key_levels 多算法投票质量高**：pivot+volume_cluster+fibonacci+swing+MA 汇聚，strength 1-5 分级，sources/confirmation/breach_action 可执行。
- **★★ generate_trade_plan 信息丰富且诚实**：regime-adaptive、Kelly（负→不建仓）、多 scenario、hit_rate_by_regime（标 reliable）、VaR、daily_checklist；偏空+Kelly 负时 direction=avoid 合理保守。
- ★ 错误路径多数规范（非法 direction/lookback 不足/risk=0 均优雅）；000001 在 stop_levels/trade_plan 已修对，修复方向明确。

## 护栏遵守
全只读分析工具，无写/下单操作；generate_trade_plan 全程不触发真实交易。
