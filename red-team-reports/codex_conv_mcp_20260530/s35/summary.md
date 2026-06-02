# N35 · 实盘 dry_run 护栏（重点验证 F-N01-1 兜底）

**工具**: live_trading_manager(全 15 action)
**调用**: 30 次 · **结论**: pass（护栏可靠，无 Fail-schema）

## 覆盖
- 只读：gateway_status/monitor/account/positions/orders/fills/order_status/order_events/broker_receipts
- 写（全 dry_run 或被拦截）：submit_order(market/limit, buy/sell, qty/notional) / cancel_order / mirror_to_paper / sync_order_events
- 护栏：dry_run 预览 / execute 无 token / 错误 token / 正确 token+只读网关 / 参数缺失 / 非法 action

## 关键结论（F-N01-1 兜底验证）
**N01 发现 live_trading_manager 契约 side_effect 误标 read_only。N35 运行时验证：护栏可靠。**
三层纵深防御，任一即可阻止误下单：
1. **写操作默认 dry_run=true** → 仅返回预览(submitted=false)
2. **execute=true 必须配 confirm_token** → 否则 `error_code=CONFIRMATION_REQUIRED`，且运行时 meta.side_effect 正确标 `level=trade_risk/confirmation_required=true`（纠正契约缺陷）
3. **网关 write_enabled=false** → 即便 token 正确，仍 mode=read_only 只返回预览，绝不下单

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N35-1 | low | submit_order dry_run 预览不校验负数量(qty=-50 仅提示 lot_size，未提示负数) |

## 正向能力
- **★★★ F-N01-1 运行时兜底成功**：契约虽标 read_only，运行时 risk_guard 拦截并正确标 trade_risk/confirmation_required。
- **★★★ 三层护栏纵深防御**：dry_run → confirm_token → 只读网关。
- **★★ confirm_token 校验**：错误 token 被拒。
- **★★ dry_run 预览完整**(submitted=false/cancelled=false)，不触达 broker。
- 参数校验完整、gateway_status 暴露完整能力矩阵、非法 action 列出支持项。

## standing caveat
护栏铁律遵守：全程仅 dry_run 预览或被护栏拦截，无任何真实下单(gateway not configured + read_only + write_enabled=false 三层保证)；confirm_token 即使提供也因网关只读不会成交。
