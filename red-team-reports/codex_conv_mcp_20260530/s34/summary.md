# N34 · 模拟交易全流程

**工具**: paper_trading_manager(全 20 action)
**调用**: 31 次 · **结论**: pass_with_high_finding

## 覆盖
- 全流程：create_account → place_order(market/limit, buy/sell) → get_positions → orders → pending_orders → cancel_order → order_events → summary
- 运维：nav_status/nav_history/matching_status/update_prices/reconcile/set_risk_rules/archive_account/list_accounts
- 边界：T+1 / 卖空未持有 / 负数量 / 非整百 / 超额(风控) / 非法代码(市价 vs 限价) / 涨跌停 / 不存在账户 / 非法 action
- 隔离 user_id=redteam_conv_20260530，挂单已清

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N34-1 | **high** | 涨跌停参考价取错：000001@11.5(真实价)被拒"超范围[3688,4508]"(误用 sh000001 指数点位)，@4000 反而放行 |
| F-N34-2 | **high** | 限价单不校验代码合法性，INVALIDXX@50 挂单成功(市价单拒但限价单放行) |
| F-N34-3 | medium | set_risk_rules 传入规则未生效，返回系统默认值 |

## 正向能力
- **★★ A股交易规则完整正确**：T+1(sellable=0)、持仓不足拒绝、整手 100、负数量拒绝、单股仓位 30% 风控。
- **★★ engine_warnings 诚实透明**：明确告知撮合/NAV 引擎未运行。
- **★★ 资金/持仓/账本精确一致**：扣减 1000000-132600-39.78=867360.22，reconcile drift=false。
- **★★ 订单生命周期完整**：created→filled/pending→cancelled 事件链(schema_version/transition/by_type)。
- **★★ 市价单非法代码正确拒绝**(未坐标化，对照 N28/N30/N32)。
- archive_account 有持仓保护、不存在账户/非法 action 优雅报错。

## standing caveat
隔离 user_id=redteam_conv_20260530，account_id=1d36a1c1；挂单已撤销；600519 持仓因 T+1 当日不可卖+账户有持仓不可归档，隔离账户残留下个交易日可清；撮合/NAV 引擎未运行。
