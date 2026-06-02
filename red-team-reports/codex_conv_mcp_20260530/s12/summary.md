# N12 · 情绪三件套 + 恐贪 + 市场情绪上下文

- 调用次数: 32 | 判定: pass_with_medium_finding
- 覆盖工具: sentiment_manager(stock/market/sector/help)、analyze_stock_sentiment、calculate_fear_greed_index、get_market_sentiment_context

## 关键发现

- **F-N12-1 (medium)**: 两个个股情绪工具结论分歧。`sentiment_manager.stock_sentiment(000001)=slightly_bearish 31.68`（涨跌天数+量比算法）vs `analyze_stock_sentiment(000001)=neutral 41.8`（三分量加权）。同一标的极性不一致，AI 同时引用会矛盾，建议提供 reconcile 字段或算法标注。
- **F-N12-2 (low)**: `get_market_sentiment_context` 在 `top_sector_n=8` 时 hot_sectors 与 cold_sectors 列表重叠（酿酒/能源金属/油气开采等同时出现在冷热两列表），逻辑矛盾。
- **F-N12-3 (low)**: `analyze_stock_sentiment` score 仍把降级的 news_sentiment(=50) 按权重 0.3 计入加权，与 `effective_components`（只声明 2 分量）口径不符，未按 effective 归一。

## 正向能力

- `market_sentiment` 的 `low_sample_size` 显式告警 + `reliable=false` + `sample_threshold=50` 是优秀置信度护栏（sample_size=15 时主动标注不可靠）。
- `analyze_stock_sentiment` 三分量透明度高：component_availability / effective_components / availability_warnings / news_oos_validation（含 decay_analysis 防过拟合）。
- `sector_sentiment` 非法板块名 degraded + fallback_reason 正确兜底。
- `get_market_sentiment_context` margin 新鲜度 stale_age_days=3 显式标注，source_chain 列出 fallback 路径；northbound 因 RFC-001 政策降级为 null（与历史一致）。

## 数据快照（2026-05-30，最近交易日 05-29）

- 恐贪指数: 52 neutral（momentum44/volatility66/volume47/breadth51）
- 上证: close 4091.07，5日 -0.53%，20日 +0.30%
- 融资余额: 2.91 万亿（05-27），5日 +1.09%
- 热板块: 半导体 +3.04% / 电池 +1.75% / 油气开采 +1.72%
- 市场情绪: bullish 73.33（但 sample_size=15 不可靠）
