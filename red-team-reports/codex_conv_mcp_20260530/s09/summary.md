# N09 · 资金流全维度

- **判定**: ✅ 通过 (Pass=9 / Degraded=16 / Fail-graceful=5 / Fail-schema=0)
- **真实工具调用数**: 30

## 核心成果

1. **北向资金 RFC-001 政策处理（亮点）**：`get_north_fund` 明确告知 EM 自 2024-08-19 停止公开北向日频净流入，items=[] 但给出 3 个可用替代方案（季度持股快照/排行/离线灌库），`non_blocking=true`。这是优秀的政策性降级。
2. **北向持股可用**：`get_north_fund_holding`/`get_north_fund_top` 数据完整（宁德 17.27%/茅台 4.69%/格力 3.23%），`change_semantics` 显式说明无前期数据。
3. **大宗交易**：含买卖双方营业部席位 + premium，当日无数据自动 backtrack 到最近交易日。
4. **板块资金流**：降级到 db.market_blocks 时显式标 degraded（半导体 +3.04% 居首）。

## ⚠ 关键发现

- **F-N09-1 [MEDIUM]**：`get_stock_fund_flow` 个股主力净流入**恒为 0.0**，super/large/medium/small 四档全 null，tradeDate 停留 05-21/05-18（数据陈旧）。tqcenter 不提供资金流分层。AI 看到"主力净流入=0"会误判为无主力动向（实为数据缺失），期望源 db.stock_fund_flow 未命中。
- **F-N09-2 [LOW]**：概念资金流 eastmoney push2 ProxyError、龙虎榜三源全跪、tushare token 无效——均 success=true 空数据 + 显式 fallback_reason，属环境网络/凭证限制，非代码 bug。

## 评价

资金流模块在多源不可用时的**降级处理与显式标注非常到位**（RFC-001 政策说明堪称范本）。唯一需关注的是个股资金流分层数据全空/恒零（F-N09-1），建议在主力净流入为 0 且分档全 null 时增加 `data_unavailable` 标志，避免 AI 误读为真实的"零主力流入"。
