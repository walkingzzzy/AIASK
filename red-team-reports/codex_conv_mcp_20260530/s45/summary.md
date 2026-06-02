# N45 · 技能系统 (list_skills / search_skills / run_skill)

- **运行**: 2026-05-30 17:59 · 31 次真实调用
- **判定**: Pass 19 / Degraded 4 / Fail-graceful 4 / Fail-schema 4
- **verdict**: `fail_schema_payload_duplication_and_cjk_search_gap_and_missing_param_default_but_executable_split_and_boundaries_robust`

## 场景说明
覆盖技能注册表三件套：list_skills（注册表审计 + 21 executable/16 registered-only 拆分）、search_skills（多关键词含中文/英文/空/不存在）、run_skill（smoke_test + 真实 task 执行 + 边界：registered-only/nonexistent/invalid_task/空 params）。注册表 backend 降级为 codex_registry（主 skills_registry 不可用）。

## 关键发现

### ★ F-N45-1（MED）search_skills 中文关键词全失效
`search_skills('技术')`/`('估值')` → count=0，而英文 `quant`/`market`/`portfolio`/`akshare` 均正常命中。技能描述全英文，全中文交互场景下中文搜索零命中。

### ★ F-N45-2（MED）run_skill 响应 execution 与 result 完全重复（payload 翻倍）
每次 run_skill 的 `data.execution` 与 `data.result` 逐字相同。含子工具完整 provider_contract/quality_gate 的执行（如 market smoke）整份大 payload 复制两遍。

### ★ F-N45-5（MED）run_skill 缺必填 task 静默默认
`run_skill(akshare-fundamental, params={})` → 静默以 `fundamental_snapshot` 执行并拉真实数据，未报 PARAM_ERROR。与全局"静默处理非预期输入"模式同源。

### F-N45-3（LOW）registry 元数据矛盾
`runtime_contract_count=0` 但 21 个 skill `source=runtime_contract`；注册表已 `stale_meta_detected=true` 自检出 meta_conflicts（自检诚实，计数器口径 bug）。

### F-N45-4（LOW）search/list 每次内联全量摘要 + 每条完整 schema
每次 search 重复内联 16 条 execution_gap + available_handlers + 命中项完整 input_schema（strategy-factory schema 极大）。高频发现操作 payload 与命中数无关地膨胀。

### F-N45-6（LOW）step success 掩盖内部 degraded
macro-options skill 的 get_macro_indicator/get_option_chain 上游不可用返回空+degraded，但 step.success=true / summary.failed_count=0，alert_blueprint 基于空数据照常生成。

## 正向亮点

- **★★ executable/registered_only 拆分（P1-3.7）优秀**：顶层 `executable_count=21 / registered_only_count=16 / executor_coverage_ratio=0.5676` + executable_skill_ids + execution_gap 逐条 + available_handlers，AI 一眼看清"37 注册中仅 21 真能跑"。
- **★★ run_skill 边界三态清晰**：registered-only→`SKILL_NOT_EXECUTABLE`、nonexistent→`SKILL_NOT_FOUND`、invalid_task→`unsupported_task`（列 supported_tasks），均带 available_handlers 引导。
- ★ executable skill 编排真实调底层工具（quote/kline/financials/backtest），内嵌完整 provider_contract/quality_gate/argument_contract（含 stock_code 别名废弃告警）；数据真实（600519=1326 元/茅台财务/factor_count=50 与基线锚一致）。
- ★ 合规类 skill 话术规范（明示正常亏损不受保护/不保证盈利 + behavior_rules + retention_rule）；quant/ml skill 方法论严谨（IS/OOS 分离、drift、成本后回测、promotion_gate）。
- ★ 注册表 stale_meta 自检诚实；backend fallback 透明标注。

## 护栏遵守
全只读 + advisory 类 skill；未触发任何写/破坏性操作。run_skill 的底层工具调用复用真实 DB（约 250 根日线/8 标的），无副作用。
