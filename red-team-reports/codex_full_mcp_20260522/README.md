# AIASK AKShare MCP 红队复测 · 22 场景全量矩阵

- **Run ID**: `codex_full_mcp_20260522`
- **基准时间**: 系统时钟 `2026-05-24 周日 11:14 Asia/Shanghai`(非交易时段)
- **目标日**: `2026-05-22`(最近交易日)/ `2026-05-20`(稳定历史日)
- **验收锚点**:
  - 工具基线: `161/161` (`available_tools` 实测 161 ✅)
  - 分类基线: `33/33` (`get_available_categories` 实测 33 ✅)
- **状态前缀**: `codex_full_mcp_20260522_sXX_*`
- **user_id**: `codex_full_mcp_20260522`
- **资金**: 100 万 / 组合
- **护栏**: live_trading 全部 dry_run 或不带 confirm_token,绝不传真实令牌

## 目录

- `baseline.json` — 基线锚定快照(`available_tools` + `get_available_categories`)
- `sXX/` — 每场景一个目录,内含每次工具调用的简化 JSON
- `sXX/summary.md` — 该场景状态行表 + Fail/Degraded 解释
- `final/coverage_matrix.md` — 收尾时生成,场景×工具 + 工具×首次通过场景

## 判定规则(同你给的 Acceptance Criteria)

- **Pass**: success=true,fallback_used=false 或 fallback_chain 完整且数据合理
- **Degraded**: success=true,fallback_used=true 或 quality_flags 含 stale/partial,但 source_chain 显式
- **Fail**: schema 异常 / 异常抛出 / 护栏绕过 / 重任务无 status/detail 回查 / true 上游全跪且无降级路径
