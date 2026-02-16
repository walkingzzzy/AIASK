---
name: akshare-tdx-front-sync
description: TDX 前端联动与结果同步流程；适用于“预警推送、回测可视化、文件下发、板块同步”场景。
---

# 目标
把策略结果稳定同步到 TDX 客户端，形成“分析 -> 推送 -> 可视化 -> 跟踪”的前端闭环。

# 使用流程
- 预警推送：文本通知用 `push_message`，交易信号用 `push_warn`。
- 回测可视化：
  - 一键回测并推送：`run_backtest_and_send_to_tdx`
  - 时序结果用 `send_backtest_result`
  - 交易记录用 `send_backtest_trades`
- 文件下发：分析报告/说明文档用 `tdx_send_file` 推送至客户端。
- 板块联动：
  - 新建板块：`create_watchlist`
  - 增量更新：`add_stocks_to_watchlist`
  - 清空/重命名：`tdx_clear_sector`、`tdx_rename_sector`
  - 生命周期管理：`get_user_sectors`、`delete_watchlist`
- 场景模板：按 `references/scenario_templates.md` 选择场景并填写参数后执行。

# 失败与兜底
- 客户端未连接：提示先启动并登录通达信客户端，再重试推送。
- 回测记录不足：先补齐最小记录要求后再发送交易记录。
- 文件格式不支持：仅使用 txt/pdf/html 并校验路径。
- 工具分流：推送失败时先落地到 `watchlist_manager` 与 `alerts_manager` 维持跟踪，再等待客户端恢复后补发。

# 参考
- 前端交互工具：`push_message`、`push_warn`、`run_backtest_and_send_to_tdx`、`send_backtest_result`、`send_backtest_trades`、`tdx_send_file`。
- 场景模板：`references/scenario_templates.md`。
