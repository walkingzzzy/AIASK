# SC 原油跨月价差全量回测报告

- 数据源：`/Users/mac/Desktop/股票/原油/ai_ready/tables/timeseries/dataset_18_sc_spread_timeseries_all_daily.csv`
- 窗口：2018-07-26 至 2025-02-19
- regime 口径：`spread_1_2 > 0 -> backwardation`，其余归入 `contango_or_flat`。
- 交割保护：front roll 前 3 日禁止持仓。

## 候选排序
| Family | Rank | Code | Ann.Return | Post Sharpe | Max DD | Trades | Alpha Decay |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trend | 1 | trend_m4_carry0p0_vol0p03_stop0p05 | 5.18% | 0.92 | -4.60% | 5 | 0.00 |
| trend | 2 | trend_m4_carry0p0_vol0p03_stop0p07 | 5.18% | 0.92 | -4.60% | 5 | 0.00 |
| trend | 3 | trend_m4_carry0p0_vol0p04_stop0p05 | 5.18% | 0.92 | -4.60% | 5 | 0.00 |
| trend | 4 | trend_m4_carry0p0_vol0p04_stop0p07 | 5.18% | 0.92 | -4.60% | 5 | 0.00 |
| trend | 5 | trend_m4_carry0p5_vol0p03_stop0p05 | 5.18% | 0.92 | -4.60% | 5 | 0.00 |
| spread | 1 | spread_2_3_entryn0p75_exit0p0_stop2p0 | 0.96% | 0.36 | -1.37% | 6 | 0.00 |
| spread | 2 | spread_2_3_entryn0p75_exit0p0_stop2p0 | 0.96% | 0.36 | -1.37% | 6 | 0.00 |
| spread | 3 | spread_2_3_entryn0p75_exit0p0_stop4p0 | 0.96% | 0.36 | -1.37% | 6 | 0.00 |
| spread | 4 | spread_2_3_entryn0p75_exit0p0_stop4p0 | 0.96% | 0.36 | -1.37% | 6 | 0.00 |
| spread | 5 | spread_2_3_entryn0p75_exit0p0_stop6p0 | 0.96% | 0.36 | -1.37% | 6 | 0.00 |

## 趋势策略冠军
- 名称：`SC Trend Carry M4`
- 年化：5.18%
- Post-cost Sharpe：0.92
- 最大回撤：-4.60%
- 交易数：5

## 套利策略冠军
- 名称：`SC Spread 2-3`
- 年化：0.96%
- Post-cost Sharpe：0.36
- 最大回撤：-1.37%
- 交易数：6

## 研究上下文
- research_context blocks：strategy_context, backtest_summary, regime_panel, capacity_panel, generalization_seed
- LLM enrichment status：`provider_empty`
- LLM note：provider returned optimized candidates.
