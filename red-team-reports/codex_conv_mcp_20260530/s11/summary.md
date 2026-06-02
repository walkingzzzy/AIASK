# N11 · 新闻公告研报聚合 + 盈利预测 + 事件 + 文本信号

- **判定**: ⚠ 通过（含 1 项 HIGH 级代码 bug）(Pass=17 / Degraded=6 / Fail-graceful=5 / Fail-schema=3)
- **真实工具调用数**: 31

## 核心成果

1. **文本信号（亮点）**：`get_stock_text_signals` 是高质量 LLM 文本管道——signal_score 0.2833 + 关键词证据贡献（增长 0.9/增持 0.8）+ 事件标签（业绩景气/资本运作）+ 6 文档索引 + 评级汇总，多源聚合（news/notice/research）。
2. **研报聚合**：`analyze_research_report` 输出 rating_distribution{买入1,增持1} + institutions + avg_target_price；`search_research_db('增长')` 返回 6 篇真实研报（隆基/格力/农行/茅台/工行/宁德）。
3. **事件聚合**：`event_manager` 多源聚合去重（raw 4 → dedup 2），event_type 分类。
4. **降级显式**：profit_forecast/analyst_ranking/stock_research 数据源限制时显式 degraded + 原因。

## ⚠ 关键发现

- **F-N11-1 [HIGH / 确凿代码 bug]**：`research_manager` **全部 action 崩溃**（get_ratings / get_reports / 甚至 help）——`error="cannot access local variable 'get_db' where it is not associated with a value"`。这是 Python **UnboundLocalError**（变量作用域错误），连 `help` 都崩说明 manager 入口某分支引用了未赋值的 `get_db`。该 manager 完全不可用。注意底层独立工具（get_research_reports/analyze_research_report）均正常，仅 manager 封装层有 bug。
- **F-N11-2 [LOW]**：`search_research`（在线源）与 `search_research_db`（本地库）结果不一致——本地库有数据而在线源空。建议在线源空时回退 db。

## 评价

研报/新闻/文本信号的**底层工具质量很高**（文本信号管道尤为出色），但 `research_manager` 这个 manager 封装层存在确凿的 UnboundLocalError 代码 bug，导致整个 manager 不可用，建议优先修复（对照 N06 的 fundamental_analysis_manager 等其他 manager 是否有同类问题）。
