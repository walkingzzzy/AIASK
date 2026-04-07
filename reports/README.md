# 报告导读

`reports/` 现在按“当前入口优先、历史快照归档”整理。

## 现行入口

以下文件可以直接视为当前报告入口：

- [`tool_registry/latest.md`](./tool_registry/latest.md)
  当前运行时工具注册表导出。
- [`mcp_deep_tool_test_smoke/latest.md`](./mcp_deep_tool_test_smoke/latest.md)
  当前轻量 smoke 套件最近一次结果。
- [`mcp_deep_tool_test_smoke2/latest.md`](./mcp_deep_tool_test_smoke2/latest.md)
  当前 smoke 重跑结果，适合和 `smoke` 对照。
- [`mcp_deep_tool_test_heavy_smoke/latest.md`](./mcp_deep_tool_test_heavy_smoke/latest.md)
  当前 heavy smoke 套件最近一次结果。
- [`mcp_deep_tool_test_heavy_smoke2/latest.md`](./mcp_deep_tool_test_heavy_smoke2/latest.md)
  当前 heavy smoke 重跑结果，适合和 `heavy_smoke` 对照。
- [`mcp_deep_tool_test_full/latest.md`](./mcp_deep_tool_test_full/latest.md)
  当前全量深度对话式测试最近一次结果。
- [`strategy_factory/latest.md`](./strategy_factory/latest.md)
  当前保留的策略工厂吞吐结果入口。
- [`vector-acceptance/latest.md`](./vector-acceptance/latest.md)
  当前保留的向量 P0-P4 验收入口。

## 历史但仍有参考价值

- `latest.md` 系列本身也是时点产物，适合做“最近一次基线”参考，不适合作为长期事实文档。
- `smoke/smoke2`、`heavy_smoke/heavy_smoke2` 这类成对目录，本质上是同类测试的重跑对照面。
- `strategy_factory/latest.md` 和 `vector-acceptance/latest.md` 是从对应历史快照中提取出的当前入口副本。

## 已归档

历史快照、重复导出和重跑记录已迁入：

- [`archive/README.md`](./archive/README.md)

## 使用原则

1. 想看“当前最近一次结果”时，优先读各目录下的 `latest.md`。
2. 想追溯某次失败、重跑或修复链路时，再进入 `archive/`。
3. 新生成的报告如仍属于运行产物，优先覆盖或新增 `latest.*`，不要把根目录重新铺满 dated 文件。
