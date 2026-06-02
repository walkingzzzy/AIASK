# N32 · 自选股 CRUD

**工具**: watchlist_manager(help/list/create_group/delete_group/add_stocks/remove_stock/reorder/add/remove)
**调用**: 33 次 · **结论**: pass_with_high_finding

## 覆盖
- 完整 CRUD 闭环：create_group → add_stocks → list → reorder → remove_stock → delete_group
- 边界：重复 group_id / 非法代码 / 重复代码 / 空 codes / 不存在分组 / 删不存在股票 / 默认分组保护 / 跨用户隔离 / 非法 action
- 隔离 user_id=redteam_conv_20260530，测试后已清理

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N32-1 | **high** | add_stocks 不校验代码合法性，ZZZ999/BADCODE 任意字符串真实入库 |
| F-N32-5 | **high** | delete_group 不级联删除组内股票，孤儿成员回落 default(幽灵填充) |
| F-N32-2 | medium | create_group 重复 group_id 静默覆盖 name/color(未拒绝) |
| F-N32-6 | medium | 分组 name 字段在操作间不稳定(回落为 group_id) |
| F-N32-3 | low | add_stocks count 反映入参数量而非实际新增(重复 600519 count=2 实际 1) |
| F-N32-4 | low | add_stocks 到不存在分组隐式自动创建 |
| F-N32-7 | low | items.name 字段为空(无股票真名) |
| F-N32-8 | low | remove_stock 删不存在股票返回 removed=true |

## 正向能力
- **★★ 跨用户隔离正确**：不同 user_id 只见自己分组(对照 N27 无 user_id 泄露警告)。
- **★★ 默认分组保护**：delete_group(default) 被拒绝。
- **★ CRUD 主流程完整**：9 个 action(含 add/remove 别名)闭环可用。
- **★ 边界优雅**：空 codes 报错、非法 action 列出支持项。
- items 结构完整(code/group_id/added_at/sort_order/note)。

## standing caveat
隔离 user_id=redteam_conv_20260530；测试后已清理所有创建的分组与股票，仅保留系统默认分组(空)；default 分组为持久共享(created 2026-05-17)。
