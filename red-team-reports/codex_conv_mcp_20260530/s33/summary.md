# N33 · 告警 CRUD

**工具**: alerts_manager / create_indicator_alert / create_combo_alert / check_all_alerts
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- create_indicator_alert：price/rsi/macd/volume/ma5/change_pct + 非法 code/condition/indicator/重复
- create_combo_alert：AND / OR / 空 conditions
- check_all_alerts：indicator/combo/all × active/all/inactive
- alerts_manager：help/create/list/check/delete(真实+不存在)/非法 action

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N33-1 | **high** | 两套割裂存储：create_indicator_alert/check_all_alerts→memory_store，alerts_manager→DB(user_id隔离)；同一 alert_id `price_>` 阈值 2000 vs 1500 |
| F-N33-2 | medium | volume 告警阈值 1.5(量比?) vs current_value 731597710(绝对量)，量纲不一致永远触发 |
| F-N33-3 | low | indicator alert_id 不含 value，同条件不能建多阈值告警 |
| F-N33-4 | low | alerts_manager(check) 与 check_all_alerts 返回结构不一致 |

## 正向能力
- **★★ create_indicator_alert 参数校验优秀**：非法 code/condition/indicator 全部明确报错并列出支持值(与 N32 watchlist 完全无校验形成鲜明对比)。
- **★★ alerts_manager delete 正确**：删不存在告警→"告警不存在"(与 N32 watchlist remove 虚假成功对照)。
- **★★ check_all_alerts 触发逻辑正确**：indicator 比较 + combo AND/OR(sub_results) + current_value 实算(price/rsi/macd)。
- **★ alerts_manager DB 侧 user_id 隔离正确**(alert_id 含 user_id 前缀)。
- 边界优雅：非法 action 列出支持项、重复告警提示 update、空 conditions schema 校验。
- side_effect.level=stateful(create)/read_only(check) 正确标注。

## standing caveat
两套独立告警 store：memory_store(create_indicator/combo + check_all，跨 run 共享、无 user_id) vs DB(alerts_manager，按 user_id 隔离)。DB 侧 redteam 告警已清理；memory_store 告警无 user_id 无法按隔离清理(历史 run 残留)。
