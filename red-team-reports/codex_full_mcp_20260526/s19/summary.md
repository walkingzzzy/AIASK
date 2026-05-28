# S19 · 用户/auth/paper-orders

- **判定**: ✅ 通过 (Pass=4 / Degraded=0 / Fail=0)
- **关键修复验证**: 🎯 **§B7 user_profile schema 修复完美**

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `user_manager(list)` | ✅ Pass | 1 个 user(default created_at=2026-05-17),source_chain=[user_manager, db.users],schema 正常 |
| `update_user_profile(codex_full_mcp_20260526)` | ✅ Pass | **§B7 完美修复确认** — recorded=true / user_upserted=true,**v1 累计 3 次 finding `'str' object has no attribute 'tzinfo'` v2 完全消失**,users 表 schema(id/username/email/settings/created_at/updated_at)兼容 INSERT OR REPLACE |
| `get_user_profile(codex_full_mcp_20260526)` | ✅ Pass | weighted_profile 完整(neuroticism=0.5/openness=0.6/herd_tendency=0.4/greed_fear=-0.2/confidence=0.7),latest_snapshot+snapshot_count=1 |
| `log_recommendation_audit(buy 600519)` | ✅ Pass | logged=true,完整记录 cognitive_biases=overconfidence,recency / emotion(0.4/0.6) / kyc_level=moderate / risk_aversion=2.5 / reasoning_chain |

## v1 → v2 Delta
- ✅ **§B7 完美修复确认** — v1 累计 3 次 `'str' object has no attribute 'tzinfo'` finding(S19/S20/S21),v2 update_user_profile + get_user_profile 全部 pass(0 次复现)
- ✅ users 表 schema 改造为 (id, username, email, settings, created_at, updated_at) 兼容 update_user_profile 的 INSERT OR REPLACE 语义
- ✅ log_recommendation_audit 完整 cognitive_biases / kyc 审计字段
