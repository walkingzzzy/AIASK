# N30 · 市场情绪上下文与恐贪

**工具**: get_market_sentiment_context / calculate_fear_greed_index / sentiment_manager / analyze_stock_sentiment
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- calculate_fear_greed_index × 4（一致性）
- get_market_sentiment_context × 5（north/margin/top_sector 多参数）
- sentiment_manager：help / market_sentiment / sector_sentiment(半导体/白酒/保险/电池/证券/医药/不存在) / stock_sentiment(6标的+非法码) / 非法 action
- analyze_stock_sentiment：600519 / 000001（交叉对照）

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N30-1 | **high** | get_market_sentiment_context cold_sectors 含半导体(+3%)/电池等上涨板块，冷热划分错误(实为 hot 逆序尾部，非真正下跌) |
| F-N30-4 | **high** | sentiment_manager(stock_sentiment) 非法码 ZZZ999→000999 静默坐标化(同 F-N28-1/F-N17-1) |
| F-N30-3 | medium | 两个个股情绪工具对同股结论不一致(600519: 45 vs 54；000001: bearish vs neutral) |
| F-N30-2 | medium | 板块 mainNetInflow 字段==changePercent(资金净流入错填为涨跌幅) |
| F-N30-5 | low | 三市场情绪工具口径不一致(恐贪52 neutral / sentiment 66.67 slightly_bullish / macro bullish) |

## 正向能力
- **★★ sentiment_manager(market_sentiment) 诚实降级典范**：reliable=false + low_sample_size warning(15<50 阈值，建议结合北向/恐贪)。
- **★★ analyze_stock_sentiment 证据极丰富**：三分量加权 + historical_validation + news_oos_validation(bucket_stats + alpha + signal_stability + decay_analysis 信号衰减反转)。
- **★ 恐贪指数稳定可复现**(4 次=52)，四组件分解透明。
- **★ 市场情绪上下文聚合全**：恐贪+指数+融资(真实 2.9 万亿)+板块+breadth，source_chain 6 源透明，北向 stale 诚实标注。
- 边界优雅：不存在板块/非法 action 友好处理。

## standing caveat
周末非交易；北向离线不可用(stale/null)；融资数据截至 05-27(stale_age=3d 真实可用)；板块来自 db.market_blocks；N12 已大量覆盖个股情绪，此处做交叉对照。
