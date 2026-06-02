# N31 · 涨停板与每日报告

**工具**: limit_up_manager / get_limit_up_stocks / get_limit_up_statistics / generate_daily_report
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- get_limit_up_stocks：05-29/05-28/05-27/05-21/05-20/05-19 + 未来日期(2099) + 非法日期(baddate)
- get_limit_up_statistics：多日期 + 非法格式
- limit_up_manager：help/list/statistics(多日期) + 非法 action
- generate_daily_report：05-29 / 05-30

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N31-1 | **high** | get_limit_up_stocks(05-27) 把 000056(+5.04%)/000509(+9.92%) 非涨停股错纳入，涨停判定阈值失效，statistics 据此虚高 |
| F-N31-2 | **high** | generate_daily_report 指数 close=0 仍生成报告，highlights 自相矛盾("情绪偏冷"+"赚钱效应好") |
| F-N31-4 | medium | list 与 statistics 对同一空日期处理路径不一致(非交易日友好提示 vs tushare degraded) |
| F-N31-3 | low | get_limit_up_stocks 未来日期(2099)不拒绝，返回空与真实空无法区分 |
| F-N31-5 | low | limit_up_manager(list) reason 字段被错填为行业名 |

## 正向能力
- **★ tqcenter.tdx 历史涨停质量好**(05-20 兆易创新/05-21 京东方A)：真名+行业+~10%+连板+换手+市值。
- **★ statistics 连板分级完整**(first/second/third/higher + failed + limitDown + successRate)，与 list 一致。
- **★ generate_daily_report 质量标注规范**：quality_flags + degraded + fallback_reason 明确指出指数取数失败。
- **★ 边界优雅**：非法日期/非法 action 友好报错，离线空数据 success=true 不崩溃。
- 日期格式兼容 YYYYMMDD 与 YYYY-MM-DD。

## standing caveat
周末非交易 + 离线；Tushare 与 akshare.zt_pool 均不可用，仅 tqcenter.tdx 提供 05-20/05-21/05-27 历史涨停，多数日期全空；daily_report 指数取数失败(close=0)。
