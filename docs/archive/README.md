# 归档文档索引

`docs/archive/` 保存历史方案、阶段性诊断、审计报告、截图快照和已被当前实现取代的计划。归档文档可以作为溯源证据，但不能直接当作当前实现依据。

## 归档分区

| 目录 | 内容 |
|---|---|
| `architecture/legacy-plans/` | 旧系统级 Agent、Hermes 集成、外部应用绑定等历史方案 |
| `data/legacy-plans/` | 旧数据源、SQLite 膨胀治理、TDX 测试报告等阶段性方案 |
| `desktop/snapshots/` | Desktop 旧 UI 截图和 Playwright 文本快照 |
| `diagnostics/mcp/` | MCP 服务诊断、修复执行清单和复测报告 |
| `event-driven/` | 已被 2026-05-24 当前方案取代的事件驱动旧方案 |
| `factor-mining/` | 因子挖掘历史诊断报告 |
| `incubation-factory/` | 孵化工厂旧独立运行方案 |
| `plans/` | RFC、OpenBB、TDX 迁移、源码卫生等阶段性计划 |
| `strategy-factory/legacy-plans/` | 2026-05 策略工厂旧修复、优化、验证体系方案 |
| `strategy-factory/module-audit/` | 策略工厂模块级历史审计 |

## 使用规则

- 引用归档文档时，必须同时核对当前代码和测试。
- 发现归档文档仍被 README 或当前 runbook 当作当前事实引用时，应改成归档链接或移除。
- 新文档不要默认放入归档；只有明确过时、被替代或仅用于复盘的材料才进入这里。
