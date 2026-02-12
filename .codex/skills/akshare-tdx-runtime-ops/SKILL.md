---
name: akshare-tdx-runtime-ops
description: TDX 运行时预检、能力探测、订阅与缓存刷新编排；适用于“先诊断环境再执行TDX工具”场景。
---

# 目标
在调用 TDX 相关工具前先完成环境预检与能力分流，降低初始化失败和误调用风险。

# 使用流程
- 环境预检：先用 `tdx_refresh_data`（`refresh_type=cache`）验证基础可用性。
- 能力探测：用 `tdx_manage_subscription(action=list)` 查看订阅状态，并据此决定是否进入订阅路径。
- 数据前置：按需调用 `tdx_refresh_data(refresh_type=kline)` 刷新指定标的与周期的缓存。
- 数据包能力：用 `tdx_list_available_fields` 确认 GP/BK/SC 字段覆盖，再决定是否调用交易数据工具。
- 交易数据读取：
  - 个股维度：`tdx_get_stock_trading_data`
  - 板块维度：`tdx_get_sector_trading_data`
  - 全市场维度：`tdx_get_market_trading_data`
- 运营监控：用 `get_sync_status` 观察同步/失败状态，并将失败场景切换到非 TDX 兜底链路。

# 失败与兜底
- TDX 初始化失败：先提示检查 `TDX_PLUGIN_PATH`、客户端登录状态与数据包下载状态。
- 订阅不可用：改用轮询快照（行情/分钟线/日线）路径。
- 字段不支持：先用 `tdx_list_available_fields` 回退到已支持字段集合。
- 工具分流：全部 TDX 路径不可用时，市场数据改用 `get_realtime_quote` / `get_kline_data`，并明确标注“非 TDX 数据源”。

# 参考
- 运行时与缓存相关工具：`tdx_refresh_data`、`tdx_manage_subscription`、`get_sync_status`。
