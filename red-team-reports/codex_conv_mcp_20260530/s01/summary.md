# N01 · 工具发现与契约审计

- **判定**: ✅ 通过 (Pass=19 / Degraded=12 / Fail-graceful=1 / Fail-schema=0)
- **真实工具调用数**: 32（达标 ≥30）

## 核心成果

1. **基线锚定**: `available_tools=163` / `get_available_categories=33`，与 v2(20260526) 完全一致，`fallback_used=false`。
2. **分类计数自洽**: 逐分类查询 decision=12 / quant=11 / finance=10 / market=14 / news=9 / fund_flow=9 / sentiment=8 / data_sync=10 / portfolio=5，各分类计数与全量目录一致。
3. **契约分层验证**: catalog 内工具（get_kline / get_realtime_quote）返回完整 provider-contract（source_policy 多源优先级 + provider_status 诊断 + reconciliation + quality_gate report_only）；runtime-inferred 工具仅返回基础 schema 并标 `degraded=true`。
4. **错误路径正确**: `get_tool_contract(nonexistent_tool_xyz)` → `success=false` + `error_code=NOT_FOUND` + `degraded=true`，标准 Fail-graceful。
5. **中文/代码搜索健壮**: search_stocks 对「茅台/平安/格力」中文与「600519」代码均正确命中；semantic_stock_search 对行业语义查询返回带 match_type/score 的合理结果。

## ⚠ 关键发现

- **F-N01-1 [HIGH]**: `live_trading_manager`（实盘）契约 `side_effect.level="read_only"` / `confirmation_required=false`，而 `paper_trading_manager`（模拟）与 `compliance_manager` 都正确标为 `"trade_risk"` + `confirmation_required=true`。**实盘工具的契约副作用等级反而比模拟交易宽松**，是 AI 仅凭契约判断确认需求时的护栏盲区。将在 N35 验证运行时是否仍有 CONFIRMATION_REQUIRED 兜底。
- **F-N01-2 [MEDIUM]**: `list_skills`/`search_skills` 顶层 `fallback_used=false`，但 `data` 内层 `fallback_used=true`（skills_registry_unavailable → codex_registry）。顶层 envelope 掩盖内层降级。
- **F-N01-3 [LOW]**: skills 注册表 `stale_meta_detected=true`，37 技能仅 21 executable（ratio 0.5676）。已知架构选择。

## Degraded 说明

12 项 Degraded 主要来自：runtime-inferred 契约的预期 `degraded` 标注（5 项）、技能注册表降级（3 项），均为 envelope 显式标注、非 bug。
