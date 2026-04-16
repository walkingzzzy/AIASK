# SC 原油跨月价差全量回测报告

- 数据源：`/Users/mac/Desktop/股票/原油/ai_ready/tables/timeseries/dataset_18_sc_spread_timeseries_all_daily.csv`
- 窗口：2018-07-26 至 2025-02-19
- regime 口径：`spread_1_2 > 0 -> backwardation`，其余归入 `contango_or_flat`。
- 交割保护：front roll 前 3 日禁止持仓。

## 候选排序
| Family | Rank | Code | Ann.Return | Post Sharpe | Max DD | Trades | Alpha Decay |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trend | 1 | trend_m4_carry1p0_vol0p03_stop0p05 | 10.49% | 0.78 | -29.92% | 10 | 0.00 |
| trend | 2 | trend_m4_carry1p0_vol0p03_stop0p07 | 10.49% | 0.78 | -29.92% | 10 | 0.00 |
| trend | 3 | trend_m4_carry1p0_vol0p04_stop0p05 | 10.49% | 0.78 | -29.92% | 10 | 0.00 |
| trend | 4 | trend_m4_carry1p0_vol0p04_stop0p07 | 10.49% | 0.78 | -29.92% | 10 | 0.00 |
| trend | 5 | trend_m4_carry1p0_vol0p05_stop0p05 | 10.49% | 0.78 | -29.92% | 10 | 0.00 |
| spread | 1 | spread_1_2_bandn0p75_to_0p25_exit1p25_stop3p0_hold30_trend | 0.51% | 0.29 | -2.94% | 3 | 0.00 |
| spread | 2 | spread_1_2_bandn0p75_to_0p25_exit1p25_stop3p0_hold45_trend | 0.51% | 0.29 | -2.94% | 3 | 0.00 |
| spread | 3 | spread_1_2_bandn0p75_to_0p25_exit1p25_stop3p0_hold30_trend | 0.51% | 0.29 | -2.94% | 3 | 0.00 |
| spread | 4 | spread_1_2_bandn0p75_to_0p25_exit1p25_stop3p0_hold45_trend | 0.51% | 0.29 | -2.94% | 3 | 0.00 |
| spread | 5 | spread_1_2_bandn0p75_to_0p25_exit1p25_stop5p0_hold30_trend | 0.51% | 0.29 | -2.94% | 3 | 0.00 |

## 门槛筛选
- 趋势策略通过 `annualized_return>10% & trade_count>=6` 的候选数：72
- 套利策略通过 `annualized_return>10% & trade_count>=6` 的候选数：0
- 若某一策略族无达标候选，本报告保留保守成本/容量假设下的最优备选，不强行把未达标结果包装成通过门槛。

## 趋势策略冠军
- 名称：`SC Trend Carry M4`
- 年化：10.49%
- Post-cost Sharpe：0.78
- 最大回撤：-29.92%
- 交易数：10

## 套利策略冠军
- 名称：`SC Spread 1-2`
- 年化：0.51%
- Post-cost Sharpe：0.29
- 最大回撤：-2.94%
- 交易数：3

## 研究上下文
- research_context blocks：strategy_context, backtest_summary, regime_panel, capacity_panel, generalization_seed
- LLM enrichment status：`provider_timeout`
- LLM note：StrategyLLMProvider did not respond within 8.0s; fallback to baseline candidates.
