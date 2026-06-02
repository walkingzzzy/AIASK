# N29 · 宏观指标

**工具**: macro_manager(help/get_indicators/market_overview) / get_macro_indicator
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- get_macro_indicator：gdp/cpi/pmi/ppi/m2 × limit(0/-5/1/120)
- macro_manager(get_indicators)：多指标/大小写/trim/去重/不支持/空列表/中文同义词
- macro_manager(market_overview)：两次一致性
- 非法 action / 单vs多指标 schema

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N29-5 | **high** | market_overview 深证成指 value=155.75(实际~12000)、sentiment 恒 bullish 与指数涨跌脱钩、breadth 仅 12 只样本、market_cap=0；二次调用指数全 null 但仍 bullish |
| F-N29-3 | medium | get_indicators(indicators=[]) 空列表静默默认成 gdp |
| F-N29-4 | medium | get_indicators 单指标 vs 多指标 response schema 不一致(data 结构不同) |
| F-N29-1 | low | provider_status available=true 与运行时 provider_used=none 矛盾(local_only 诊断不准) |
| F-N29-2 | low | get_indicators 顶层 degraded=false 掩盖内层全 degraded |

## 正向能力
- **★ 降级路径规范**：records=[]+degraded=true+fallback_reason 明确指出不可用 provider；provider_contract + quality_gate(6 项 checks) + reconciliation 元数据极完整。
- **★ 输入清洗健壮**：大小写归一、空格 trim、去重。
- **★ 不支持指标优雅**：unsupported_indicators + supported_indicators(仅 5 个) + message 引导。
- 非法 action 优雅报错并列出支持 action。

## standing caveat
周末非交易 + 离线环境；所有宏观 provider(tushare_pro/akshare/curl.mofcom)本地不可用 → records 全空 + degraded；仅支持 gdp/cpi/pmi/ppi/m2 五个指标。
