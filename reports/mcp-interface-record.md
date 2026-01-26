# MCP 接口测试记录（对话内实测）

测试时间：2026-01-16
范围：aiask-stock MCP + akshare MCP
方法：在当前对话中直接调用 MCP 工具，覆盖基金经理日常工作流；先做同步（行情/K线/向量），再复测情绪与北向资金；扩展多股票与指数做抽样一致性校验。

## 执行摘要
- 总调用数：113
- 成功：91
- 失败：19
- 待确认：3（需要二次确认执行）
- 主要失败集中：北向资金流、市场情绪、向量同步、akshare 实时/批量行情超时、宏观指标 publishDate、概念资金流解析。

## 同步与复测
- sync_stock_quotes {"force":true,"limit":50} -> 成功；同步39只
- sync_stock_kline {"stock_code":"600519","days":120} -> 成功；120条
- sync_batch_kline {"days":120,"limit":50} -> 失败；days>100
- sync_batch_kline {"days":100,"limit":50} -> 成功；50只/5000条
- sync_pattern_vectors {"stock_code":"600519","window_size":20} -> 失败；无法连接数据库
- sync_batch_financials {"limit":50} -> 成功；syncedStocks=0
- sync_market_sentiment {} -> 失败；缺少当日K线
- get_market_sentiment {} -> 失败；缺少市场日线数据
- get_north_fund_flow {"days":30} -> 失败；全0校验不通过

## aiask-stock 接口测试记录
市场/板块/热点
- get_market_overview {} -> 成功；northFund=0
- get_market_report {} -> 成功
- get_sector_realtime {"type":"industry","top_n":5} -> 成功
- get_sector_fund_flow {"top_n":5} -> 成功
- analyze_sector_rotation {"days":30} -> 成功；建议轻仓
- get_hot_concepts {"top_n":5} -> 成功

北向资金
- get_north_fund_flow {"days":30} -> 失败；全0
- get_north_fund_holding {"stock_code":"600519"} -> 成功
- get_north_fund_top {"top_n":10} -> 成功

行情/K线/盘口/异动
- get_realtime_quote {"stock_code":"600519"} -> 成功
- get_batch_quotes {"stock_codes":["600519","000001","300750","000333","000858"]} -> 成功
- get_kline {"stock_code":"600519","period":"daily","limit":60} -> 成功
- get_kline {"stock_code":"600519","period":"weekly","limit":60} -> 成功
- get_multi_period_data {"stock_code":"600519","periods":["daily","weekly","monthly"],"limit":60,"indicators":["ma5","ma20","macd"]} -> 成功
- get_orderbook {"stock_code":"600519"} -> 成功；买卖盘全0
- get_trades {"stock_code":"600519","limit":10} -> 成功
- get_stock_anomalies {"stock_code":"600519","days":7} -> 成功
- get_realtime_anomalies {"limit":5} -> 成功；count=0

技术面/信号
- calculate_indicators {"stock_code":"600519","period":"daily","indicators":["rsi","macd","kdj"],"timeperiod":14} -> 成功
- detect_patterns {"stock_code":"600519","lookback_days":30} -> 成功；detected=0
- detect_patterns_extended {"stock_code":"600519","lookback_days":30,"min_reliability":"medium"} -> 成功；检测到双顶
- get_support_resistance {"stock_code":"600519"} -> 成功
- generate_trading_signal {"stock_code":"600519","strategy":"multi_indicator"} -> 失败；枚举不匹配
- generate_trading_signal {"stock_code":"600519","strategy":"default"} -> 成功
- get_trend_analysis {"stock_code":"600519"} -> 成功；downtrend
- get_momentum_analysis {"stock_code":"600519"} -> 成功；weak
- get_volatility_analysis {"stock_code":"600519"} -> 成功；low
- calculate_dmi {"stock_code":"600519","data_days":120,"period":14} -> 成功
- williams_combo {"stock_code":"600519","data_days":200} -> 成功；oversold
- analyze_cross_period_signals {"stock_code":"600519","periods":["daily","weekly","monthly"],"signal_type":"trend_alignment"} -> 成功

基本面/估值/机构
- get_financials {"stock_code":"600519","statement_types":["income","balance","cashflow"]} -> 成功；多字段未披露
- get_valuation_metrics {"stock_code":"600519"} -> 成功；pe/pb/ps缺失
- compare_valuations {"stock_codes":["600519","000858","000333"]} -> 成功；count=0
- calculate_health_score {"stock_code":"600519"} -> 成功；score=65
- get_dcf_valuation {"stock_code":"600519"} -> 成功；intrinsicValue=0
- ddm_valuation {"stock_code":"600519","current_dividend":30} -> 成功
- moat_proxy {"stock_code":"600519"} -> 成功
- get_institutional_holders {"stock_code":"600519"} -> 成功；仅北向
- get_asset_info {"stock_code":"600519"} -> 成功；pe/pb/marketCap为空

宏观/行业
- get_macro_indicator {"indicator":"cpi","periods":5} -> 失败；缺 publishDate
- search_macro_indicators {"keyword":"物价"} -> 成功；total=0
- analyze_macro_impact {"indicator":"cpi","impact_on":"sector","target":"白酒"} -> 成功
- get_industry_trends {"industry":"白酒","include_stocks":true} -> 成功；recentChange=undefined%
- track_policy_changes {"sector":"消费","policy_keywords":["税收","白酒"]} -> 成功；无结果

新闻/情绪/研报
- get_stock_news {"stock_code":"600519","limit":5} -> 成功
- get_news_sentiment {"stock_code":"600519","days":7} -> 成功
- analyze_social_sentiment {"stock_code":"600519","sources":["xueqiu","eastmoney"],"time_filter":"7d"} -> 成功；仅新闻源
- get_stock_sentiment {"stock_code":"600519"} -> 成功
- analyze_news_impact {"stock_code":"600519","news_title":"贵州茅台公告：推进市场化运营方案"} -> 成功
- get_research_summary {} -> 成功
- get_recent_research {"days":7,"limit":5} -> 成功
- get_stock_research {"stock_code":"600519","limit":5} -> 成功
- summarize_research_report {"stock_code":"600519","summary_type":"brief","report_count":3} -> 成功

组合/风险/交易
- add_position {"stock_code":"600519","quantity":100,"cost_price":1350} -> 待确认
- add_position {"stock_code":"600519","quantity":100,"cost_price":1350,"_confirmed":true} -> 成功
- add_position {"stock_code":"000333","quantity":200,"cost_price":75,"_confirmed":true} -> 成功
- get_positions {} -> 成功；count=6
- get_portfolio_summary {} -> 成功
- get_portfolio_risk {} -> 成功
- get_var {"confidence":0.95,"holding_period":5} -> 成功
- monitor_drawdown {"threshold":0.1} -> 成功
- generate_portfolio_report {"positions":[...],"total_capital":1000000} -> 成功
- optimize_equal_weight {"stock_codes":["600519","000333","300750","000858"],"total_amount":1000000} -> 成功
- optimize_risk_parity {"stock_codes":["600519","000333","300750","000858"]} -> 成功；仅提示需历史波动率
- optimize_mean_variance {"stock_codes":["600519","000333","300750","000858"],"target_return":0.12} -> 成功；仅提示需协方差
- add_trade_record {"trade_type":"买入"} -> 失败；枚举要求 buy/sell
- add_trade_record {"trade_type":"卖出"} -> 失败；枚举要求 buy/sell
- add_trade_record {"trade_type":"buy"} -> 成功
- add_trade_record {"trade_type":"sell"} -> 成功
- get_trade_records {"stock_code":"600519","limit":5} -> 成功
- evaluate_trade {"trade_id":"...","evaluation_aspects":["timing","position_size","stop_loss"]} -> 成功
- analyze_trades {"analysis_type":"summary"} -> 失败；枚举要求 pnl/timing/strategy/behavior/all
- analyze_trades {"analysis_type":"all","date_range":{"start":"2026-01-09","end":"2026-01-16"}} -> 成功
- get_trading_statistics {"days":30} -> 成功；total_trades=0
- record_daily_pnl {} -> 成功
- get_pnl_history {"days":30} -> 成功；recordCount=2
- analyze_pnl_trend {"days":30} -> 失败；记录不足7天

自选/数据质量
- add_to_watchlist {"code":"600519","name":"贵州茅台"} -> 待确认
- add_to_watchlist {"code":"600519","name":"贵州茅台","_confirmed":true} -> 成功
- add_to_watchlist {"code":"000333","name":"美的集团","_confirmed":true} -> 成功
- get_watchlist {} -> 成功；count=2
- remove_from_watchlist {"code":"600519","_confirmed":true} -> 成功
- remove_from_watchlist {"code":"000333","_confirmed":true} -> 成功
- get_watchlist_groups {} -> 成功
- check_data_quality {} -> 成功；north_fund 检查失败
- check_data_source_health {} -> 成功

## akshare MCP 接口测试记录
行情/指数
- get_realtime_quote {"stock_code":"600519"} -> 失败；timeout
- get_batch_quotes {"stock_codes":["600519","000001","300750","000333","000858"]} -> 失败；timeout
- get_kline {"stock_code":"600519","period":"daily","limit":60} -> 成功
- get_stock_info {"stock_code":"600519"} -> 成功
- get_index_quote {"index_code":"000001"} -> 成功
- get_index_quote {"index_code":"399001"} -> 失败；未找到指数
- get_index_quote {"index_code":"399006"} -> 失败；未找到指数

资金/研判
- get_financials {"stock_code":"600519"} -> 失败；未找到财务数据
- get_margin_data {} -> 成功；日期=20171024
- get_sector_fund_flow {"top_n":5} -> 成功；mainNetInflow 为 null
- get_concept_fund_flow {"top_n":5} -> 失败；错误 "即时"
- get_dragon_tiger {} -> 成功；buy/sell/net 为空
- get_north_fund {"days":30} -> 成功
- get_stock_list {} -> 成功；列表巨大（已截断）

## 抽样一致性校验
- 600519 日线K线：aiask-stock 与 akshare 收盘价一致（2026-01-16 close=1382）
- 指数行情：akshare 000001 正常；399001/399006 未找到
- 即时行情：akshare realtime/batch 超时，无法与 aiask-stock 对比

## akshare 北向资金报表（30日）

| 日期 | 沪股通(亿) | 深股通(亿) | 合计(亿) | 累计(亿) |
| --- | --- | --- | --- | --- |
| 2024-07-08 | 10.09 | -32.09 | -22.00 | 17,907.32 |
| 2024-07-09 | 89.33 | 51.78 | 141.11 | 18,048.43 |
| 2024-07-10 | 5.72 | -23.55 | -17.83 | 18,030.60 |
| 2024-07-11 | 12.83 | 17.63 | 30.46 | 18,061.06 |
| 2024-07-12 | 33.01 | -5.67 | 27.34 | 18,088.39 |
| 2024-07-15 | 9.24 | -38.64 | -29.40 | 18,059.00 |
| 2024-07-16 | -3.13 | -25.63 | -28.76 | 18,030.24 |
| 2024-07-17 | -45.41 | -43.40 | -88.80 | 17,941.43 |
| 2024-07-18 | 17.14 | -3.62 | 13.52 | 17,954.95 |
| 2024-07-19 | -20.29 | -39.50 | -59.79 | 17,895.16 |
| 2024-07-22 | 45.02 | -25.29 | 19.73 | 17,914.89 |
| 2024-07-23 | -10.30 | -31.53 | -41.83 | 17,873.06 |
| 2024-07-24 | -6.95 | -15.82 | -22.76 | 17,850.30 |
| 2024-07-25 | -44.86 | -20.96 | -65.82 | 17,784.48 |
| 2024-07-26 | -4.43 | 0.95 | -3.49 | 17,780.99 |
| 2024-07-29 | -18.45 | -31.40 | -49.85 | 17,731.14 |
| 2024-07-30 | -18.16 | -6.29 | -24.45 | 17,706.70 |
| 2024-07-31 | 113.63 | 82.17 | 195.80 | 17,902.49 |
| 2024-08-01 | -9.59 | -47.42 | -57.01 | 17,845.48 |
| 2024-08-02 | -24.35 | -7.95 | -32.30 | 17,813.18 |
| 2024-08-05 | -3.94 | 6.82 | 2.88 | 17,816.06 |
| 2024-08-06 | -28.85 | -33.65 | -62.51 | 17,753.56 |
| 2024-08-07 | 4.17 | -25.53 | -21.36 | 17,732.20 |
| 2024-08-08 | 8.00 | 3.04 | 11.03 | 17,743.23 |
| 2024-08-09 | -31.35 | -46.30 | -77.65 | 17,665.58 |
| 2024-08-12 | -2.89 | -4.84 | -7.73 | 17,657.85 |
| 2024-08-13 | -8.62 | -16.65 | -25.27 | 17,632.58 |
| 2024-08-14 | -30.61 | -41.06 | -71.66 | 17,560.92 |
| 2024-08-15 | 88.65 | 33.41 | 122.06 | 17,682.97 |
| 2024-08-16 | -25.68 | -42.07 | -67.75 | 17,615.22 |

汇总：净额 -314.10 亿；净流入天数=9；净流出天数=21；最大净流入=2024-07-31 195.80 亿；最大净流出=2024-07-17 -88.80 亿；最新累计=17,615.22 亿
