# MCP 问题报告（对话内实测）

测试时间：2026-01-16
范围：aiask-stock MCP + akshare MCP
方法：对话内直接调用工具，覆盖基金经理工作流并同步后复测

## 关键问题（按影响排序）
1) 北向资金流失效（aiask-stock）
- 表现：get_north_fund_flow 全0校验失败；check_data_quality north_fund 失败；市场总览 northFund=0。
- 影响：资金面核心指标不可用，影响情绪、宏观判断与风控。

2) 市场情绪不可用（aiask-stock）
- 表现：sync_market_sentiment 与 get_market_sentiment 均报缺少市场日线数据。
- 影响：无法给出市场情绪与风险偏好判断。

3) 向量同步失败（aiask-stock）
- 表现：sync_pattern_vectors 无法连接数据库。
- 影响：形态向量/相似股票相关能力不稳定。

4) akshare 即时行情超时
- 表现：get_realtime_quote、get_batch_quotes 超时。
- 影响：实时行情一致性校验无法完成。

5) akshare 概念资金流解析失败
- 表现：get_concept_fund_flow 返回错误 “即时”。
- 影响：概念热点资金监测无法使用。

## 重要问题
- akshare 财务数据缺失：get_financials 未找到 600519。
- akshare 指数映射异常：get_index_quote 399001/399006 未找到。
- akshare 龙虎榜与板块资金字段缺失：buy/sell/net 为空；sector mainNetInflow 全 null。
- 宏观指标输出被拒：get_macro_indicator 缺 publishDate。
- 行业趋势字段异常：get_industry_trends recentChange=undefined%。
- 估值缺失：get_valuation_metrics pe/pb/ps/marketCap 为空；compare_valuations 为空；get_dcf_valuation intrinsicValue=0。
- 盘口数据全0：get_orderbook 买卖盘均为0。
- 交易统计与交易记录不一致：get_trading_statistics 仍为 0（已写入交易记录）。
- PnL 趋势分析失败：analyze_pnl_trend 需要≥7天记录。

## 影响范围
- 资金流/情绪/宏观/估值四大模块出现缺口。
- akshare MCP 实时行情与部分资金流接口不稳定，影响跨源对比与实时监控。

## 修复建议（按优先级）
1) 北向资金链路
- 明确 aiask-stock 北向资金优先走 akshare-mcp；当 eastmoney 返回全0时直接降级到 akshare-mcp 并通过校验。

2) 市场情绪链路
- 确认 sync_stock_kline 写入的日线数据与情绪计算读取的数据源一致；必要时在同步后补全市场级日线统计表。

3) 向量库
- 修复向量库连接与路径/权限；确保 sync_pattern_vectors 可写。

4) akshare 即时行情
- 增加超时/重试或拆分批量请求；必要时启用缓存。

5) akshare 数据字段
- 概念资金流解析适配 “即时” 字段结构；龙虎榜/板块资金字段缺失需补充映射。

6) 估值与财务
- 对接真实估值字段；修复 600519 财务接口映射；避免 DCF=0 的占位行为。

7) 交易统计
- 统一交易记录与统计口径；确保统计能读取新写入记录。

