# N21 · 决策门控与融合

**工具**: build_stock_context / build_quant_context / build_event_context / run_decision_gate / fuse_decision_payload
**调用**: 30 次 · **结论**: pass

## 覆盖
- 三大 context builder（stock/quant/event）× 多标的
- run_decision_gate：8 只标准池 × aggressive/balanced/conservative × 多 user_id
- fuse_decision_payload：多标的多 style
- 边界：BADX 非法代码

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N21-1 | medium | 所有标的所有 style 的 `run_decision_gate` 均被 compliance 阻断(`indicative_order_blocked`)，但 `detail={}` 为空，无具体合规原因（疑周末非交易时段，但未明示） |
| F-N21-2 | low | context builders 顶层 `degraded=true` 但内层 data 实际完整可用（envelope 一致性，同 F-N01-2） |
| F-N21-3 | low | 未建画像 user_id 统一 moderate；aggressive 与 balanced 的 position_cap 相同(0.2)，仅 conservative(0.1)有区分 |

## 正向能力（含关键对照）
- **★ 决策链严格校验代码**：BADX 在 run_decision_gate / fuse_decision_payload 均被拒（"代码格式无效"）。这与 N17 的 run_batch_backtest(坐标化 BAD1→000001) 和 N18 的 optimize_portfolio(丢有效股留垃圾码) 形成鲜明对照，**进一步证明量价工具的坐标化/错位是局部 bug，而非全局缺乏校验**。
- **★ 跨工具分数传递一致**：fuse.score_breakdown 的 stock/quant/event 三分量与各 build_*_context 的 score 逐一吻合(17.5/42.0/63.7)。
- fuse 权重随 style 自适应（conservative 加重 event 0.35，aggressive 加重 quant 0.35，和=1.0）。
- 三大 context builder 结构极丰富；event_context 标的隔离正确（无张冠李戴）。
- run_decision_gate 紧凑；quant_stability 弱时正确触发 gate_adjustment=-3.0。

## standing caveat
测试在周末非交易时段进行，所有指示性买入订单被合规闸门阻断；event/quant context 数据 stale（asof 2026-05-20~05-23）。融合 action 因此恒为 watch。
