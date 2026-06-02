# N41 · AI 工作流-因子候选

**调用数**: 30 | **判定**: fail_schema_alias_and_coordinatization（4 个 Fail-schema）

## 测试工具
`factor_candidate_workflow`（help/generate/scheduler_status）/ `quant_manager`（factor_candidate_registry/factor_research_memory/factory_pool_status/model_registry/help）/ `get_factor_library` / `list_factors` / `calculate_factor`

## 核心发现

### F-N41-2（HIGH）— 非法代码 ZZZ999 → 000999 坐标化（再现）
`factor_candidate_workflow(generate, codes=['ZZZ999'])` 返回 `codes=['000999']`，据此生成因子候选，无任何校验告警。与 N28/N30/N36/N40 同源的坐标化 bug 在因子工作流再次复现。

### F-N41-4（HIGH）— calculate_factor 别名契约不一致（= F-N13-1 复现）
`get_factor_library` 的 `alias_canonical_map` 含 `pb_ratio→pb_ttm`，且 `naming_note` 明确声称 "All 4 actions accept any name in aliases"。但 `calculate_factor(factor='pb_ratio')` 报 `Unsupported factor: pb_ratio`。`macd` 别名却能解析。别名解析部分生效、部分失效，契约与实际 resolver 不符。

### F-N41-1（MEDIUM）— help 语义错误 + side_effect 误标
`task='help'` 不返回文档，而是实际执行 `scheduler_status`。只读查询 `meta.side_effect.level='stateful'`（应为 read_only）。

### F-N41-3（MEDIUM）— factor_research_memory 默认返回全量 1536 维 embedding 向量
记忆查询每条候选内联完整 embedding 向量，20 条 → 数十万 token 级 payload，严重消耗上下文。应默认裁剪。

## 正向亮点
- **★★ 因子治理体系工程质量高**：`factor_candidate_registry`（grade/recommendation/risk_audit/governance/admission_blocked）+ `factory_pool_status`（质量漏斗 + by_engine + by_blueprint）+ `model_registry`。18/20 候选因 `avg_cross_section_n`/`multiple_testing_risk` 被 `admission_blocked`，风控严格。
- **★★ 因子候选生成 lineage 完整**：novelty_score / memory_similarity_edges / episode_id / generation_trace / schema_path，且 fallback/degraded 标注诚实（local_rule_fallback + artifact_not_persisted）。
- **★ 50 因子/5 分类/85 别名**与基线一致；技术因子计算正确。
- **★ 错误路径规范**：非法因子名/category/action 均 success=false + 列出支持项。

## 备注
- LLM provider 配置 gpt-5.5 但 workflow_fast_mode 强制 local_rule_fallback（degraded=true）。
- 隔离护栏：persist_artifact=false + write_memory=false，未污染因子记忆库。
