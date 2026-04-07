# 历史测试报告归档

`packages/akshare-mcp/tests/archive/` 存放已不适合作为当前测试入口、但仍可用于历史复盘的 Markdown 报告。

## 当前归档内容

### 1. legacy 场景执行与评估

目录：`archive/real_world_scenarios/`

- [`real_world_scenarios/MCP_TOOL_TEST_RESULTS.md`](./real_world_scenarios/MCP_TOOL_TEST_RESULTS.md)
- [`real_world_scenarios/EVALUATION_REPORT.md`](./real_world_scenarios/EVALUATION_REPORT.md)

### 2. Tushare Pro 历史测试报告

目录：`archive/tushare-pro/`

- [`tushare-pro/TEST_REPORT.md`](./tushare-pro/TEST_REPORT.md)

## 使用边界

1. 这些报告描述的是特定时间点、特定环境下的运行结果。
2. 若报告里的工具数、通过率、代理配置或依赖前提与当前代码冲突，应以后者为准。
3. 当前若新增一次性测试结果，默认继续放入 `archive/`，除非它已经成为稳定维护的套件说明。
