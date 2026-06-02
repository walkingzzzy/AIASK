# N28 · 向量相似检索

**工具**: search_by_kline / search_similar_stocks / vector_search_manager / find_similar_patterns
**调用**: 33 次 · **结论**: pass_with_high_finding

## 覆盖
- search_by_kline：7 只标的 × days(10/30/60) × top_n + 非法码 + allow_fallback=false
- search_similar_stocks：both/technical/fundamental × 多标的 + 非法码
- vector_search_manager：market_docs(hybrid + doc_types 过滤) / similar_stocks / similar_patterns / help + 非法码
- find_similar_patterns：自相似历史窗口 + forward_returns

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N28-1 | **high** | vector_search_manager 非法代码静默坐标化：INVALID1→000001、XYZ7→000007、ABC519→000519(抽数字补零)，返回无关股票零告警(同 F-N17-1 类缺陷) |
| F-N28-2 | medium | search_by_kline(allow_fallback=false) 顶层 envelope fallback_used=true 与 data 内层 fallback_used=false 矛盾 |
| F-N28-3 | low | K线/画像向量索引库为空(db_empty_result)，全部回退 python 余弦(已知架构限制) |

## 正向能力
- **★★ find_similar_patterns 真正可用**：fallback_used=false，返回 forward_returns(5d/10d/20d) + aggregate_prediction(hit_rate/avg_return) + market_regime，提供条件概率证据。
- **★ market_docs 混合检索**：retrieval_mode=hybrid，dense+fts+lexical 三路融合，研报/公告命中精准，doc_types 过滤生效(lexical=1.0)。
- **★ 行业聚类全部正确**：白酒/家电/保险/整车各自聚类，相似度排序合理。
- similarity_type 维度分流清晰(technical/fundamental/both 各自 features)。
- ST/退市股质量过滤(excluded_st_count + quality_filter)。
- vector_search_manager meta 治理完整(trace_id/audit_event_id/side_effect/retrieval_quality)。

## 三向量工具非法代码处理不一致
- search_by_kline → **正确报错** `Insufficient kline data`
- search_similar_stocks → **正确** target_missing/空
- vector_search_manager → **错误** 静默坐标化(F-N28-1)

## standing caveat
周末非交易；K线/画像向量索引库为空，全部回退 python 余弦；market_docs 与 find_similar_patterns 走真正检索；DB 约 250 根日线/8 只核心标的 + 50 只热门池。
