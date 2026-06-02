# N26 · 板块与产业链

**工具**: sector_manager / get_market_blocks / get_block_stocks / industry_chain_manager / get_industry_chain
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- sector_manager：list_sectors(industry/concept) / sector_rotation(5/30d) / sector_performance / sector_correlation(空/单/多)
- get_industry_chain：keyword(新能源汽车/锂矿/半导体/光伏/白酒/医药/储能/AI/机器人/军工) + chain_id + 空/不存在
- industry_chain_manager：get_chain/related_stocks × keyword/chain_id/code
- get_market_blocks(concept/region) / get_block_stocks(酿酒)

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N26-2 | **high** | `industry_chain_manager` 的 chain_id/code 参数 + 部分 keyword(军工) 泄露裸 SQL 错误 `no such column: code`；仅部分 keyword 路径可用 |
| F-N26-1 | medium | sector_rotation 普跌行情下仍把负收益板块标注为"强势/overweight"(相对强弱排序对，但绝对化措辞误导) |
| F-N26-3 | low | get_industry_chain 未匹配关键字回退全量，顶层 fallback_used=false 与 data.fallback_used=true 不一致 |
| F-N26-5 | low | get_market_blocks/get_block_stocks 巨型 provider_contract 元数据重复 3-4 次(payload 膨胀) |
| F-N26-4 | low | concept/region 板块无数据(DB 仅 industry 板块) |

## 正向能力
- **★ sector_manager 完整高质量**：list_sectors(136 行业)/sector_rotation(强弱 + 轮动建议 + market_style)/sector_performance/sector_correlation(相关矩阵 + interpretation)，均基于 db_kline 实算。
- **★ get_industry_chain 17 条预置产业链**结构规范(上中下游)，keyword 模糊 + chain_id 精确匹配，覆盖主流赛道。
- get_block_stocks 成分股 code+name 正确，total_count/truncated 分页透明。
- provider_contract 诊断极完整(provider_status 逐源 + quality_gate 6 项检查 report_only)。
- 边界优雅：correlation<2 拒绝；不存在产业链回退全量；数据源全失败 degraded 透明。

## standing caveat
周末非交易时段，板块实时行情(price/changePct)为 0；DB 仅有 industry 板块(136 个)，concept/region 源全失败；产业链为 17 条预置静态数据。
