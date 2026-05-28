# AIASK AKShare MCP 红队复测 v2 · 22 场景对话式全量复测

- **Run ID**: `codex_full_mcp_20260526`
- **基准时间**: 2026-05-26 周二 09:45 Asia/Shanghai(非交易时段)
- **目标日**: 2026-05-22(最近交易日) / 2026-05-26(当日)
- **基线锚点**:
  - 工具基线: 163 (原 161 + valuation_consensus + decision_consensus 两个 meta-tool)
  - 分类基线: 33
- **状态前缀**: `codex_full_mcp_20260526_sXX_*`
- **user_id**: `codex_full_mcp_20260526`
- **资金**: 100 万 / 组合
- **护栏**: live_trading 全部 dry_run / 不带 confirm_token,绝不传真实令牌

## 与 v1(2026-05-22)对比基线

- v1 基线: 161 工具 / 33 分类 / Fail=0 / 累计 high finding 117
- v2 验证目标: 76 项 finding + 8 项 B1-B8 修复 = 84 项是否运行时落地

## v2 Round 2 — 5 项政策性 finding 修复(2026-05-26 10:30)

详情见 `final/fixes_round2.md`。一键验证:

```powershell
$env:PYTHONPATH = "C:\Users\walking\Desktop\aiask\packages\akshare-mcp\src;C:\Users\walking\Desktop\aiask\packages\aiask-quant-core\src"
python -X utf8 packages\akshare-mcp\_verify_v2_fixes.py
# Total: 7/7 PASS
```

| Fix | 章节 | 一句话 |
|---|---|---|
| Fix 1 | §4.5.1 | GBK 乱码静态名表 + 启发式兜底 |
| Fix 2 | §2.5 | 指数数值合理性护栏(拒绝 close<1000 写入 sh000001) |
| Fix 3 | §S13 | governance not_applicable / partial_input / inconsistent 三态 |
| Fix 4 | §2.5 | 删除 506 行污染数据(snapshot 备份) |
| Fix 5 | §2.1 | RFC-001 显式标记 + alternatives 替代方案 |
| Fix 6 | §5.5 | tushare_top_list 第三 source 兜底 |
| Fix 7 | §S19-F12 | AKSHARE_QUALITY_PROFILE strict/lite/minimum 三档 |

## 测试方法

每场景调用 5 个**核心代表工具**(覆盖该场景主题 + 验证原 high finding 修复点),每场景独立 status.json + summary.md。

## 判定规则

- **Pass**: success=true,fallback_used=false 或 fallback_chain 完整,数据合理
- **Degraded**: success=true,fallback_used=true 或 quality_flags 含 stale/partial,但 source_chain 显式
- **Fail-graceful**: success=false,但 error_code 显式 + degraded=true(正确错误路径)
- **Fail-schema**: schema 异常 / 异常抛栈 / 护栏绕过

## 目录

- `sXX/` — 每场景一个目录,内含 status.json + summary.md
- `final/` — 收尾时生成 coverage_matrix_v2.md + delta_v1_v2.md
