# N37 · 用户画像与 KYC

**工具**: user_manager / get_user_profile / update_user_profile / log_recommendation_audit
**调用**: 30 次 · **结论**: pass

## 覆盖
- user_manager：help/get_profile/update_preferences/list/list_users/assess_kyc/非法 action/跨用户访问
- update_user_profile：大五人格 + 越界值 + 部分更新 + 衰减加权
- get_user_profile：多快照衰减加权 / 不存在用户 / 无 user_id
- log_recommendation_audit：buy/sell/hold + 非法代码

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N37-1 | medium | 用户存储双 store 割裂：user_manager(db.users，强身份校验) vs 画像(user_profile_snapshots，无校验)，list_users 看不到画像系统创建的用户 |
| F-N37-2 | low | update_user_profile 部分更新将未传字段重置为默认(非增量) |
| F-N37-3 | low | log_recommendation_audit 不校验股票代码 |
| F-N37-4 | low | assess_kyc 不纳入 update_preferences 的 risk_level 偏好 |

## 正向能力
- **★★ user_manager 强安全**：get_profile 跨用户→AUTH_ERROR，scope 字段标注 cross_user(对照 N32 watchlist 宽松)。
- **★★ update_user_profile 越界值裁剪优秀**：confidence 1.5→1.0、openness 5→1.0、greed_fear_axis -3→-1.0，clamp 到合法区间。
- **★★ KYC 评估完整**：composite_score + kyc_level(C2) + label + max_drawdown + 三分量分解。
- **★ get_user_profile 衰减加权画像**：weighted_profile(指数衰减半衰期 7 天) + snapshot_count。
- **★ 审计留痕完整**：action/emotion/cognitive_biases/risk_aversion/kyc_level/reasoning_chain。
- 边界优雅：非法 action→PARAM_ERROR、不存在用户→No profile data。

## standing caveat
两套用户存储割裂(user_manager db.users 强校验 vs 画像 snapshots 无校验)；redteam 用户经 update_user_profile upsert 到 snapshots 表但 list_users 看不到；default 偏好被改为 aggressive(测试残留)。
