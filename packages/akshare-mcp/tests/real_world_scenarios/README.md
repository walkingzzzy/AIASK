# 实际应用场景深度测试方案

> 版本: v1.1
> 日期: 2026-02-09
> 目标: 验证 AKShare MCP 服务在真实量化交易场景下的端到端能力
> 源码核实: 已完成全部12个场景涉及的源码文件核实与修正

---

## 源码核实状态

所有场景中引用的 MCP 工具均已对照源码逐一验证参数名、action名、返回字段。

| 源码文件 | 核实状态 | 涉及场景 |
|----------|---------|---------|
| `quant.py` | ✅ 8因子/calculate_factor/calculate_factor_ic/backtest_factor | 02 |
| `decision.py` | ✅ should_i_buy/should_i_sell 返回字段 | 03,04 |
| `valuation.py` | ✅ get_valuation_metrics/dcf/ddm/relative/historical | 03,06 |
| `alerts.py` | ✅ create_indicator_alert/create_combo_alert/check_all_alerts（内存存储） | 04,11 |
| `backtest.py` | ✅ 4种策略/run_simple_backtest/run_batch_backtest/run_backtest_with_trades | 05 |
| `portfolio.py` | ✅ optimize_portfolio(6方法)/analyze_portfolio_risk/stress_test_portfolio | 06 |
| `options.py` | ✅ get_option_chain(510050/510300) | 10 |
| `options_manager.py` | ✅ calculate_price/calculate_greeks/implied_volatility（非bs_price/greeks） | 10 |
| `sentiment.py` | ✅ analyze_stock_sentiment/calculate_fear_greed_index | 03,08 |
| `tdx_integration.py` | ✅ send_backtest_result(_SIGNAL_MAP)/send_backtest_trades(4条最低) | 05 |
| `tdx_formula.py` | ✅ calculate_macd/kdj/rsi/boll/trix/dma/expma/dmi/cr/vr/screen_stocks/get_expert_signals | 03,12 |
| `basic_data.py` | ✅ get_ipo_info/get_cb_info/get_trading_dates/get_stock_capital | 11 |
| `fund_flow.py` | ✅ get_dragon_tiger(AkShare降级)/get_sector_fund_flow/get_concept_fund_flow/get_stock_fund_flow/get_north_fund | 07 |
| `news.py` | ✅ get_stock_news/get_market_news/get_stock_research/get_profit_forecast/get_stock_notices | 08,09 |
| `technical.py` | ✅ calculate_technical_indicators/check_candlestick_patterns | 01 |
| `macro.py` | ✅ get_macro_indicator(支持cpi/ppi/m2/pmi/gdp/shibor) | 08 |
| `semantic.py` | ✅ parse_selection_query/get_industry_chain/smart_stock_diagnosis/generate_daily_report | 02,03,08,09 |
| `vector.py` | ✅ search_similar_stocks/search_by_kline/semantic_stock_search | 09 |
| `market/quote.py` | ✅ get_realtime_quote/get_batch_quotes/get_index_quote | 01,04,08 |
| `market/limit_up.py` | ✅ get_limit_up_stocks(stk_limit+daily组合)/get_limit_up_statistics | 07 |
| `managers/screener_manager.py` | ✅ screen(criteria字典)/technical_screen/combined_screen/list_conditions | 02 |
| `managers/risk_manager.py` | ✅ calculate_var/stress_test/risk_exposure（均需portfolio_id） | 06 |
| `managers/options_manager.py` | ✅ calculate_price/calculate_greeks/implied_volatility/help/list | 10 |
| `managers/industry_chain_manager.py` | ✅ get_chain/related_stocks/help | 09 |
| `managers/trading_data_manager.py` | ✅ dragon_tiger/block_trades/institutional_flow | 07 |
| `managers/limit_up_manager.py` | ✅ list/statistics/help | 07 |
| `managers/market_insight_manager.py` | ✅ market_trend/sector_analysis（返回硬编码数据） | 08 |
| `search.py` | ✅ search_stocks/available_tools/get_available_categories | 全局 |

---

## 场景清单

| 编号 | 场景名称 | 用户角色 | 核心能力域 | TDX联动 |
|------|---------|---------|-----------|---------|
| 01 | [盘前选股与自选股同步](scenario_01_morning_stock_screening.md) | 短线交易者 | 技术面选股 + TDX条件选股 | ✅ 自选股同步 |
| 02 | [多因子量化选股](scenario_02_multi_factor_screening.md) | 量化研究员 | 因子计算 + IC分析 + 因子回测 | ❌ |
| 03 | [买入决策全流程](scenario_03_buy_decision_workflow.md) | 个人投资者 | 诊断 + 估值 + 技术 + 情绪 | ✅ 预警推送 |
| 04 | [持仓止盈止损监控](scenario_04_position_monitor_stoploss.md) | 持仓管理者 | 卖出建议 + 告警 + 实时监控 | ✅ 预警信号 |
| 05 | [策略回测与TDX可视化](scenario_05_backtest_tdx_visualization.md) | 策略开发者 | 回测 + 交易明细 + TDX联动 | ✅ 回测数据发送 |
| 06 | [组合风险管理](scenario_06_portfolio_risk_management.md) | 组合管理者 | 组合优化 + VaR + 压力测试 | ❌ |
| 07 | [涨停板复盘与龙虎榜追踪](scenario_07_limit_up_dragon_tiger.md) | 游资跟踪者 | 涨停统计 + 龙虎榜 + 资金流向 | ✅ 消息推送 |
| 08 | [每日市场全景报告](scenario_08_daily_market_report.md) | 基金经理 | 日报 + 宏观 + 北向 + 板块轮动 | ✅ 消息推送 |
| 09 | [产业链深度研究](scenario_09_industry_chain_research.md) | 行业研究员 | 产业链 + 研报 + 相似股票 | ✅ 自选股同步 |
| 10 | [期权策略分析](scenario_10_option_strategy_analysis.md) | 期权交易者 | 期权链 + Greeks + BS定价 | ❌ |
| 11 | [新股申购与可转债监控](scenario_11_ipo_convertible_bond.md) | 打新投资者 | IPO信息 + 可转债 + 告警 | ✅ 预警推送 |
| 12 | [跨周期技术共振选股](scenario_12_multi_timeframe_resonance.md) | 趋势交易者 | TDX公式 + 多周期指标 + 条件选股 | ✅ 自选股同步 |

---

## 使用说明

### 测试方式

所有场景均通过 **对话式 MCP 工具调用** 执行，不使用脚本或终端命令。

### 测试股票池

参考 `P2_OPTIMIZATION_GUIDE.md` 中的标准测试池：

```
超大盘: 600519(茅台), 601318(平安), 600036(招行)
大  盘: 000858(五粮液), 300750(宁德), 601398(工行)
中  盘: 600887(伊利), 002594(比亚迪), 600276(恒瑞)
小  盘: 002049(紫光国微), 603259(药明康德), 300274(阳光电源)
```

### 性能基准

| 操作 | 目标耗时 |
|------|---------|
| 单股实时行情 | < 500ms |
| 单股K线(100根) | < 1s |
| 单股回测(1年) | < 1s |
| 批量回测(5只) | < 5s |
| 组合优化(5只) | < 3s |
| TDX消息推送 | < 200ms |
| 多周期共振分析(单只) | < 3s |
| 多周期共振分析(10只) | < 15s |
| 每日市场全景报告生成 | < 10s |

### 数据源降级链验证

每个场景需记录实际命中的数据源，验证各工具各自的降级路径：

```
注意：降级链是工具级差异化的，非全局统一。不同工具有各自的降级路径：

K线/行情:  TDX(本地) → Tushare Pro → 东财直连 → AkShare → Baostock
龙虎榜:    Tushare → AkShare(stock_lhb_detail_em) → Sina
研报:      Tushare report_rc → 东财 datacenter → AkShare
期权链:    新浪直连 → AkShare
涨停板:    stk_limit + daily 组合判断
宏观数据:  Tushare Pro → AkShare
IPO/可转债: TdxQuant（单一数据源）
公式计算:  TdxQuant（有fallback实现）
```

---

## 覆盖矩阵

### MCP 工具覆盖

| 工具类别 | 涉及场景 | 工具数 |
|---------|---------|--------|
| 行情/K线 | 01,03,04,07,08 | 8 |
| 技术分析 | 01,03,05,12 | 16 |
| 基本面/财务 | 02,03,06,09 | 5 |
| 资金流向 | 07,08 | 5 |
| 回测系统 | 05,06 | 4 |
| 因子分析 | 02 | 4 |
| 估值分析 | 03,06 | 4 |
| 智能诊断 | 03,04 | 6 |
| 告警系统 | 04,11 | 3 |
| TDX联动 | 01,04,05,07,08,09,12 | 8 |
| 管理器 | 全部 | 29 |
| 期权/宏观 | 08,10 | 2 |
| 研报/新闻 | 08,09 | 5 |

### TDX 前端交互覆盖

| TDX 功能 | 涉及场景 |
|----------|---------|
| push_message | 07,08 |
| push_warn | 03,04,11 |
| create_watchlist / add_stocks | 01,09,12 |
| send_backtest_result | 05 |
| send_backtest_trades | 05 |
| tdx_screen_stocks | 01,12 |
| tdx_calculate_* | 03,12 |
| tdx_get_expert_signals | 12 |

---

## v1.1 修正记录（基于源码核实）

| 场景 | 修正内容 | 原因 |
|------|---------|------|
| 02 | Step 6: `screener_manager` 参数从 `factors` 列表改为 `criteria` 字典 | 源码 `screen` action 使用 criteria 字典（max_pe/min_roe等），不支持因子名称列表 |
| 02 | Step 6: 新增 `combined_screen` action 示例 | 源码支持基本面+技术面组合选股 |
| 03 | Step 1: `smart_stock_diagnosis` 返回字段细化 | 源码返回 overall_score/recommendation/scores/analysis/risks |
| 04 | Step 1: `should_i_sell` 返回字段修正 | 源码返回 recommendation/action_text/score/profit_pct/target_sell_price/reasons/risks，非 stop_loss/take_profit |
| 05 | Step 4: `send_backtest_trades` 字段修正 | 源码要求 time/price/signal/shares/profit 字段，非 date/action |
| 06 | Step 7: `risk_manager` 参数修正 | 源码 calculate_var/stress_test/risk_exposure 均需 portfolio_id，不接受 codes/weights |
| 07 | Step 2: `get_limit_up_stocks` 返回字段细化 | 源码返回 code/name/price/changePercent/limitUpPrice/continuousDays |
| 08 | Step 1: `generate_daily_report` 返回字段细化 | 源码返回 market_summary/stats/hot_sectors/capital_flow/sentiment/highlights/outlook |
| 09 | Step 1: `get_industry_chain` 返回字段修正 | 源码返回 chains 列表（id/name/upstream/midstream/downstream），非直接返回上中下游 |
| 09 | Step 2: `get_profit_forecast` 返回字段细化 | 源码返回 items 列表（date/institution/researcher/rating/eps_forecast等） |
| 09 | Step 4: `search_similar_stocks`/`search_by_kline` 返回字段细化 | 源码返回 similar_stocks/results 列表含 similarity/correlation 字段 |
| 10 | Step 3: action 从 `bs_price` 改为 `calculate_price` | 源码 options_manager 实际 action 名称 |
| 10 | Step 4-5: action 从 `greeks` 改为 `calculate_greeks` | 源码 options_manager 实际 action 名称 |
| 10 | Step 3-5: 参数名从 `S/K/T/r/sigma` 改为 `spot/strike/time_to_maturity/risk_free_rate/volatility` | 源码规范参数名（别名仍可用但不推荐） |
| 11 | Step 1: `get_ipo_info` 返回字段修正 | 源码返回 ipo_list/count/source |
