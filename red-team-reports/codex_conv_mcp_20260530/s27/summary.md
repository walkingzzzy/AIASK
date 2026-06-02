# N27 · 选股器与语义搜索

**工具**: screener_manager / parse_selection_query / semantic_stock_search / search_stocks
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- parse_selection_query：基本面/技术面/混合/OR 逻辑/毛利率/乱码/连续上涨
- screener_manager：screen / technical_screen / list / list_conditions / run_strategy / bogus 条件
- semantic_stock_search：行业/名称/代码/不存在
- search_stocks：中文/代码

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N27-1 | **high** | parse_selection_query 将"连续3天上涨"误解析为 `upn` AND `downn`(连涨+连跌)矛盾条件，AND 下永远命中 0 |
| F-N27-6 | **high** | screener_manager(run_strategy) 预置策略运行裸 TypeError `unexpected keyword argument 'criteria'`，所有策略无法运行 |
| F-N27-2 | medium | parse_selection_query 丢弃"毛利率>80%"数值条件(gross_margin 不支持，静默丢弃) |
| F-N27-4 | medium | technical_screen 结果 name=code(无真名)且疑似重复行(000938=000963、000333=000338 数据逐位相同) |
| F-N27-3 | low | screen 纳入数据缺失标的(market_cap=0/name 空)并打分 |
| F-N27-5 | low | technical_screen ma_bull 命中跌停股(语义存疑，非 bug) |

## 正向能力
- **★ parse_selection_query 中文 NLP 强**：正确分流基本面/技术面/语义条件，识别 AND/OR，单位转换(15%→15、100 亿→1e10)，给出 screener 调用建议。
- **★ semantic_stock_search 多维匹配**：name_exact/code_exact/industry/sector_seed/name_partial + score，行业/名称/代码均准确。
- screener_manager(screen) 完整多因子打分(score 0-80 + rating A-D + top_picks)。
- list_conditions 66 个条件分 6 类，含 default_params 与 composite sub_conditions。
- **★ 安全意识**：list 动作 scope_warnings 提示跨用户数据泄露风险。
- 边界优雅：乱码/不存在/非法条件均友好处理。

## standing caveat
周末非交易；screener 股票池固定 50 只(DB 热门股)，technical_screen 基于 db_kline。
