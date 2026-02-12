# TDX 前端联动场景模板

## 场景 1：盘中预警联动（轻量）
- 触发条件：价格突破/跌破阈值，或技术指标触发。
- 执行工具：
  - `push_warn`
  - `push_message`
  - `alerts_manager(action=create)`
  - `check_all_alerts`
- 模板参数：
  - `stock_code`: 6 位代码
  - `price`: 当前价格
  - `reason`: 预警原因（建议 25 字以内）
  - `bs_flag`: 0/1/2
- 最小闭环：
  - 发送 `push_warn`。
  - 再发 `push_message` 给出行动建议和风控位。
  - 创建 `alerts_manager` 告警，定期用 `check_all_alerts` 复核。

## 场景 2：回测结果可视化（研究转展示）
- 触发条件：策略回测完成，需要在 TDX 客户端查看时序和交易点。
- 执行工具：
  - `send_backtest_result`
  - `send_backtest_trades`
  - `push_message`
- 模板参数：
  - `stock_code`
  - `time_list`: 时间序列（YYYYMMDDHHMMSS 或 YYYY-MM-DD）
  - `data_list`: 每个时间点对应的信号列
  - `trades`: 交易记录（time/price/signal/shares/profit）
- 最小闭环：
  - 先发 `send_backtest_result`。
  - 再发 `send_backtest_trades`。
  - `push_message` 通知“已同步，可在客户端查看”。

## 场景 3：报告下发（投研交付）
- 触发条件：日报/周报/月报已生成并需要在客户端查看。
- 执行工具：
  - `tdx_send_file`
  - `push_message`
- 模板参数：
  - `file_path`: txt/pdf/html 文件路径
  - `message`: 报告主题 + 日期 + 关键结论
- 最小闭环：
  - 先执行 `tdx_send_file`。
  - 成功后发送 `push_message`，说明文件名称与解读要点。

## 场景 4：板块同步（选股转跟踪）
- 触发条件：当日或当周候选池形成，需要同步到 TDX 自定义板块。
- 执行工具：
  - `create_watchlist`
  - `add_stocks_to_watchlist`
  - `tdx_clear_sector`
  - `tdx_rename_sector`
  - `get_user_sectors`
  - `delete_watchlist`
- 模板参数：
  - `block_code`
  - `block_name`
  - `stock_codes`
- 最小闭环：
  - 首次创建：`create_watchlist`。
  - 增量更新：`add_stocks_to_watchlist`。
  - 全量重算：`tdx_clear_sector` 后重新灌入。
  - 用 `get_user_sectors` 检查结果。

## 场景 5：不可用时的补偿路径（必备）
- 触发条件：TDX 未连接、初始化失败、文件格式不支持。
- 执行工具：
  - `watchlist_manager(action=add)`
  - `alerts_manager(action=create)`
  - `push_message`（可用时补发）
- 最小闭环：
  - 保留最小监控：自选 + 告警。
  - 记录待补发清单，客户端恢复后重放推送。
