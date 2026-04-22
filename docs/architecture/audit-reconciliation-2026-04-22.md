# AIASK 审计修订表（2026-04-22）

本修订表仅校准代码实证审计里的偏差结论，不重写原始报告。

## 重分类

| 原条目 | 原结论 | 修订后分类 | 代码校准说明 |
|---|---|---|---|
| `F1` | 治理监控前端面板缺失 | 已有弱能力 | 现有前端已通过 `/data/governance-report`、`/data/strategy-governance` 和策略超市治理平面承接治理信息，问题在于持久化与统一入口体验仍偏弱，而不是完全缺页。 |
| `A3` | `ResultContract` 覆盖不完整导致前端无法统一承接 | 契约下沉 | 前端长期存在本地 `buildLocalResultContract()` 适配层，核心问题是 BFF 未统一输出 `result_contract` 与 `contract_meta`，前端在补位，不是前端完全无法承接。 |
| `A1` | MCP 参数名不统一主要体现在 `research` | 问题范围扩大 | 参数别名兼容已扩散到 `research`、`market`、`fundamental`、`fund-flow`、`assistant` 等多个 BFF 服务，需要统一 registry 收口，不能继续按单模块修补。 |

## 冻结约束

- 冻结新增 BFF SQL migration。BFF 仅保留数据库连接与 MCP schema readiness 检查，不再执行 schema 变更。
- 冻结页面级 ad-hoc `ResultContract` 拼装扩散。新增页面或接口优先走共享 `resolveResultContract(serverContract, localFallback)`。
- 冻结服务内散落的 `callWithArgs` 参数名回退逻辑。新增别名适配统一进入 BFF `tool-contracts` registry，MCP 侧同步接入 canonical 参数入口。
