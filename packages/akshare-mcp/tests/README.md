# akshare-mcp tests 文档导读

`packages/akshare-mcp/tests/` 下的 Markdown 现在按“当前套件说明 / 历史报告归档”整理。

## 现行入口

- [`data-quality/README.md`](./data-quality/README.md)
  当前仍有效的数据质量测试套件说明。

## 历史但保留索引

- [`real_world_scenarios/README.md`](./real_world_scenarios/README.md)
  legacy 场景目录说明，只保留人工复盘与历史审计价值，不再代表当前运行时能力清单。

## 已归档

历史执行报告已迁入：

- [`archive/README.md`](./archive/README.md)

## 使用原则

1. 需要运行当前测试时，先看 `data-quality/README.md` 和对应 `pytest`/脚本。
2. 需要追溯旧场景、旧环境或旧代理链路时，再进入 `archive/`。
3. 新的测试结果若只是一次性运行产物，优先进入 `archive/` 或独立 `reports/`，不要继续堆在测试目录主路径。
