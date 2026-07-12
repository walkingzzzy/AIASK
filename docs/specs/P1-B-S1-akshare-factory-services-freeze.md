# P1-B / S1：冻结 `akshare-mcp/services/*factory*` 新功能

> 状态：生效（文档级冻结）  
> 日期：2026-07-11  
> 对齐：`docs/specs/四工厂独立化与MCP瘦身拆分开发方案-2026-06-23.md`、`docs/specs/五大生产缺陷闭环开发方案-2026-07-11.md`

## 冻结范围

以下路径 **禁止新增业务功能 / 新 phase / 新 hard-gate 语义**，除非同时满足：

1. 缺陷修复或 P0 证据闭环必要修补；
2. 有 fixture 前后 verdict 对比（不改 hard gate 数值语义）；
3. PR 描述标明“S1 冻结例外”与回滚方式。

路径（示例，含子树）：

- `packages/akshare-mcp/src/akshare_mcp/services/*factory*`
- 尤其：incubation / strategy lifecycle 编排型 service、matching / promotion 评估实现（在迁出前）

允许：

- 只读诊断扩展（如 `factory_diagnostics.py` 证据字段）
- fail-closed / 日志 / 测试补强
- adapter 薄封装（真正逻辑上移到 `strategy-factory` / contracts）

## 评审规则（CODEOWNERS + 文档）

- 已落地：`.github/CODEOWNERS`（factory services / lifecycle_shared / SF contracts）


- 触及上述路径的 PR：必须在描述中声明 **S1 freeze impact**。
- 优先评审：是否可放到 `strategy-factory` 或 shared contracts。
- 禁止：在 akshare 宿主内继续堆“正式晋级/撮合/晋升”新状态机。

## 下一阶段（S2）— 已完成核心

- [x] hard gate / evidence gap / promotion_ready schema 上移 `strategy_factory.contracts.*`
- [x] 同 fixture 对比 migration 前后 verdict（host re-export identity + status matrix）
- [x] **未改变** hard gate 数值语义（floor=20 等）
- 下一步：S3 matching / promotion 评估迁 SF infrastructure，AK 留 adapter

## 与 P1-A 关系

P1-A 运维产品化（诊断面板 + Intent run-once）已完成，运维入口在 Agent/Desktop；
后续瘦身不得破坏 `agent_factory_formal_diagnostics` 契约字段。
