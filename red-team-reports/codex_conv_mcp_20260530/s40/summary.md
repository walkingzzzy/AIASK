# N40 · AI 工作流-个股深度

**调用数**: 30 | **判定**: fail_schema_decision_bias（含 2 个 Fail-schema 级发现）

## 测试工具
`smart_stock_diagnosis` / `comprehensive_manager` / `get_unified_decision(_summary)` / `analyze_stock_workflow` / `analyze_stock_product_workflow` / `ai_workflow_artifact`

## 核心发现

### F-N40-1（HIGH，★★★最重要）— smart_stock_diagnosis 一律给 sell
9 个唯一标的全部 `recommendation=sell`：

| 标的 | 名称 | 形态 | regime | RSI | 20d动量 | positive/risk | 推荐 |
|---|---|---|---|---|---|---|---|
| 688981 | 中芯国际 | **bullish** | **bullish** | 72.43 | **+0.2394** | 3/5 | sell |
| 300750 | 宁德时代 | mixed | neutral | 52.52 | -0.047 | 2/6 | sell |
| 000651 | 格力电器 | mixed | neutral | 52.75 | -0.032 | 3/5 | sell |
| 601318 | 中国平安 | bearish | bearish | 33.82 | -0.099 | 2/6 | sell |
| 002594 | 比亚迪 | bearish | bearish | 44.94 | -0.087 | 0/8 | sell |
| 600519/000001/000858/002304 | … | … | … | … | … | … | sell |

根因：证据→risks 归类规则把中性甚至偏正面指标（除 ma_alignment=bullish 外的 PE/ROE/RSI/debt_ratio）默认塞进 risks，使 `risk_count` 恒 ≥ `positive_count`。中芯国际明显多头（+27% 20d、MACD 零轴上、regime bullish）仍被判 sell，是决策与技术面背离的最极端样本。诊断工具完全丧失区分度。

### F-N40-2（MEDIUM）— 跨决策引擎结论冲突
同一标的（601318/000651/688981）：`smart_stock_diagnosis=sell`，但 `get_unified_decision=watch`、`analyze_stock_workflow=watch`。`analyze_stock_product_workflow` 最终 watch 但内部 stock_context 子模块给 sell。三套决策路径无交叉一致性校验，对同一输入给相反结论且无分歧提示。

### F-N40-3（LOW）— 比亚迪 52周高点未复权
002594：`high_52w=416.98` vs 现价 96.18，`max_drawdown=78.5%`，疑似除权前价格未前复权，衍生指标失真，加重 risk 误判。

### F-N40-4（LOW）— 同标的跨工具价格/日期不对齐
688981：diagnosis 133.81@05-20 vs quick_scan 151.05@flat，相差约 13%，时点未统一（印证 F-N39-ROOT 写库滞后）。

## 正向亮点
- **★★★ analyze_stock_product_workflow 8 阶段协议化工作流** 工程质量最高：evidence 带 source_field 引用 + agent_review citation 验证 + integrity_gate + gap_report + HTML 报告 + artifact_ids 完整 lineage。
- **★★ get_unified_decision 系列 provenance 极完整**：分模块时间戳 + source_chain 23 项 + gate_flags + veto_reason + position_signal + raw_ai_output（bull/bear/uncertainties）。
- **★★ ai_workflow_artifact 产物注册表规范**：真实产物正确返回，不存在 id → NOT_FOUND + 审计字段。
- 000001 在诊断路径正确识别为平安银行（未与上证指数混淆，对照 N34/N36）。

## 备注
- 护栏：全程只读，工作流未触发写操作。
- unified_decision 对全标的 `veto_reason=indicative_order_blocked`（compliance 恒 blocked），疑与 N34/N36 的 000001 合规涨跌停 bug 同源副作用。
