# 股票 MCP 失败工具测试报告

> 说明：本报告只记录在本轮持续对话式测试中仍然失败、无法成功使用，或返回结果足以判定为逻辑失效的工具。
> 测试方式以真实 MCP 调用为主；由于本线程内置 `akshare-mcp` 连接在重启旧进程后进入 `Transport closed`，最终确认采用“fresh stdio MCP client + 当前源码服务”继续逐条人工调用，不使用批量脚本跑全量。
> 最后更新：2026-03-19

## 当前结论

本轮修复与复测后，之前保留在失败清单中的工具已恢复，当前**没有仍然成立的失败工具项**。

## 已移除的历史失败项

### 1. `screener_manager(action="technical_screen")`

- 历史问题：
  - 曾报 `attempted relative import beyond top-level package`
  - 后续又出现默认池 `success_count=0 / error_count≈pool_size`
- 本轮修复：
  - 修复 manager 内部绝对导入
  - 修复 `formula_fallback` 的同步 K 线回退链
  - 修复 BaoStock 并发访问稳定性
- 最新真实回归：
  - 小池子：`stock_pool=["600519","000858","000001"]`，`conditions=["upn"]`
    - 返回 `success=true`
    - `diagnostics.success_count=3`
    - `diagnostics.error_count=0`
  - 默认池：`conditions=["macd_golden_cross","volume_breakout"]`
    - 返回 `success=true`
    - `diagnostics.success_count=50`
    - `diagnostics.error_count=0`
- 判定：**已恢复**

### 2. `screener_manager(action="combined_screen")`

- 历史问题：
  - `technical_conditions` 被静默清空
  - 实际命中结果退化成纯基本面结果
  - 名称字段大量为空
- 本轮修复：
  - 修复 `technical_conditions / tech_conditions / conditions` 归一化
  - 修复组合筛选里名称回填
  - 修复技术面股票池 K 线获取稳定性
- 最新真实回归：
  - 小池子：`stock_pool=["600519","000858","000001"]`
    - 返回 `success=true`
    - `tech_conditions=["upn"]`
    - `technical_conditions=["upn"]`
    - `diagnostics.success_count=3`
    - `diagnostics.error_count=0`
  - 默认池：`fundamental_criteria={"max_pe":20.0,"min_roe":0.15}`，`technical_conditions=["macd_golden_cross"]`
    - 返回 `success=true`
    - `tech_conditions` 与 `technical_conditions` 正常回显
    - `diagnostics.success_count=10`
    - `diagnostics.error_count=0`
- 判定：**已恢复**

## 本轮额外修复但不计入“失败工具项”的问题

- 冷启动问题：
  - 修复 `strategy_factory` 兼容层循环导入，恢复 `python -m akshare_mcp.server` 冷启动能力
- 启动调度问题：
  - 修复 `StartupValidator` 在同步启动入口中错误使用 `asyncio.ensure_future` 的问题，改为后台守护线程执行异步校验

## 备注

- `screener_manager(action="screen", kwargs={"criteria":{"max_pe":20.0,"min_roe":0.15},"limit":10})`
  - 最新真实回归返回 `count=10`
  - `stocks` 与 `top_picks` 均为 10 条，之前关于 `limit` 不生效的现象本轮未再复现

- 本线程内置 MCP 连接之所以不可继续复用，是因为清理旧服务进程后客户端没有自动重连。
  - 这属于当前桌面线程的连接状态问题，不代表修复后的 `akshare-mcp` 服务仍然失败。
