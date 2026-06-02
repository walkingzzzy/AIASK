# N02 · 个股全景行情链

- **判定**: ✅ 通过 (Pass=8 / Degraded=17 / Fail-graceful=5 / Fail-schema=0)
- **真实工具调用数**: 30

## 核心成果

1. **指数行情**：上证(4068.57)/深证(155.75)/创业板(4037.95) 三大指数成功，**中文名称完整无 GBK 乱码**（v2 §4.5.1 本次未复现）。
2. **K线全周期**：600519 日/周/月线、ETF 510050 日线、000651 日线均成功；`get_kline_data` 区间+qfq 复权过滤生效。
3. **个股/指数消歧**：`get_kline_data(000001)` 显式提示「000001 同时存在个股与指数语义，如需指数请用 sh000001/sz000001」——优秀的歧义处理。
4. **逐笔成交**：`get_trade_details` 经 tencent_direct 返回带 buy/sell/neutral 方向的明细。
5. **错误路径**：非法代码 ABCDEF（格式校验）、999999（未找到）均 Fail-graceful。

## ⚠ 关键发现

- **F-N02-1 [HIGH]**：`get_index_quote` 对**沪深300(000300)/中证500(000905) 返回全 null**，fallback 链暴露 `tushare_index_daily失败: 您的token不对`。宽基指数行情不可用，且 **TUSHARE token 配置失效**会波及所有 tushare 兜底路径（后续场景需关注）。
- **F-N02-2 [MEDIUM]**：ETF 510050 在 `get_realtime_quote` 被拒（"未找到股票"），但 `get_kline(510050)` 成功。**工具间 ETF 支持不一致**。
- **F-N02-3 [MEDIUM]**：实时/批量报价 `name` 字段持续为空（tqcenter 不带名称），复现 v2 §4.5.9。
- **F-N02-4 [LOW]**：盘口 L2 深度恒 `depth_degraded`（db 快照无 level2），非交易时段已知限制，显式标注正确。

## 亮点

`deprecation_warnings` 全程提示 `stock_code` 别名已废弃应改用 `code`；envelope 的 source_chain / fallback_reason / quality_flags 标注一致且详尽。
