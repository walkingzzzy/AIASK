# sc_sprd (1) 时序数据摘要

## 工作簿概览
- 输出数据表：13 个
- 时间覆盖：2018-07-26 至 2025-02-19
- 主要用途：逐日价差回溯、横向比较不同 ContNo 腿、构造回测输入

## 输出 CSV 清单
| 工作表 | 行数 | 列数 | 起始日期 | 结束日期 | CSV |
| --- | --- | --- | --- | --- | --- |
| 1-2 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_06_sc_spread_timeseries_1_2.csv |
| 2-3 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_07_sc_spread_timeseries_2_3.csv |
| 3-4 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_08_sc_spread_timeseries_3_4.csv |
| 4-5 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_09_sc_spread_timeseries_4_5.csv |
| 5-6 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_10_sc_spread_timeseries_5_6.csv |
| 6-7 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_11_sc_spread_timeseries_6_7.csv |
| 7-8 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_12_sc_spread_timeseries_7_8.csv |
| 8-9 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_13_sc_spread_timeseries_8_9.csv |
| 9-10 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_14_sc_spread_timeseries_9_10.csv |
| 10-11 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_15_sc_spread_timeseries_10_11.csv |
| 11-12 | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_16_sc_spread_timeseries_11_12.csv |
| all | 17479 | 6 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_17_sc_spread_timeseries_all.csv |
| all_daily | 1589 | 14 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_18_sc_spread_timeseries_all_daily.csv |

## AI 调用提示
- `all_daily` 是最适合程序消费的宽表，可直接读成多列价差因子矩阵。
- 单腿工作表适合做局部分析、绘图复刻和异常日期回放。
