# sc1-5统计(1) 统计摘要

## 工作簿概览
- 输出数据表：5 个
- 统计覆盖：2022-11-26 至 2024-11-25
- 主要用途：近远月价差分位、波动区间、建仓风险参考
- 综合汇总表：tables/statistics/dataset_05_sc_spread_statistics_all.csv

## ALL 行关键统计
| 组合 | 样本数 | 均值 | 标准差 | 1% | 25% | 75% | 99% | CSV |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1-2 | 483 | 2.303106 | 7.464753 | -7.6 | -2.45 | 4.2 | 35.344 | tables/statistics/dataset_01_sc_spread_statistics_1_2.csv |
| 2-3 | 483 | 2.501656 | 3.886272 | -5.6 | -0.35 | 4.4 | 13.0 | tables/statistics/dataset_02_sc_spread_statistics_2_3.csv |
| 3-4 | 483 | 2.747412 | 3.111978 | -3.2 | 0.5 | 4.3 | 10.4 | tables/statistics/dataset_03_sc_spread_statistics_3_4.csv |
| 4-5 | 483 | 2.780952 | 2.661663 | -1.1 | 0.5 | 4.5 | 9.236 | tables/statistics/dataset_04_sc_spread_statistics_4_5.csv |

## AI 调用提示
- 可先读本摘要，再下钻到具体组合 CSV，例如 `1-2` 或 `3-4` 的分位区间。
- 若要进入策略工厂，可把 1%、25%、75%、99% 视为建仓/风控阈值候选特征。
