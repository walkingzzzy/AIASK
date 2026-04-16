# 原油 资料 AI 就绪索引

## 扫描概览
- 源目录：`/Users/mac/Desktop/股票/原油`
- 识别源文件：7 个
- 生成 Markdown 文档：7 份
- 生成 CSV 数据集：18 份
- 生成 market_doc_chunks：17 个

## 输出目录
- `strategy_notes/`：研究备忘、数据口径和交易框架。
- `price_trend/`：图像 OCR、HTML 图册整理和图表说明。
- `spread_statistics/`：Excel 工作簿摘要与结构化说明。
- `tables/`：标准化 CSV。
- `metadata/`：知识库注入清单、chunk、文件索引。

## 交易策略与研究框架
### 原油跨月价差交易备忘
- 输出文件：`strategy_notes/doc_05_crude_oil_strategy_memo.md`
- 来源：`/Users/mac/Desktop/股票/原油/原油.docx`
- 摘要：将原始 Word 备忘整理为结构化研究笔记，提炼选品原则、SC 近远月关系观察、趋势与套利策略以及风险收益要点。
- 建议用途：strategy_framework

### SC 价差数据说明与换月规则
- 输出文件：`strategy_notes/doc_07_sc_spread_data_notes.md`
- 来源：`/Users/mac/Desktop/股票/原油/策略.md`
- 摘要：整理换月规则、分钟中间价口径、图表说明和 Excel 字段定义，可作为时序与统计数据的口径说明文档。
- 建议用途：data_definition

## 价格走势与图表 OCR
### sc basis vs conto_price
- 输出文件：`price_trend/doc_01_sc_basis_vs_cont0_price.md`
- 来源：`/Users/mac/Desktop/股票/原油/1-2vs3-4.png`
- 摘要：图像显示 SC 主力价格与两组跨月价差的叠加走势：蓝线对应 cont1-cont2，橙线对应 cont3-cont4。 OCR 识别到横轴大致覆盖 2023-01 至 2025-01，左轴价差约 -60 到 60，右轴价格约 500 到 750。
- 建议用途：price_trend

### cal_diff_sc2 HTML 图册整理
- 输出文件：`price_trend/doc_04_sc_spread_notebook.md`
- 来源：`/Users/mac/Desktop/股票/原油/sc_价差图with01.html`
- 摘要：HTML 文件中提取出 11 张嵌入图像。结合 `sc_sprd` 工作簿包含 11 组月差数据这一事实，这里推断这些图像大概率对应单腿价差或其派生可视化。 主要 OCR 标题包括：1-2; 2-3; 3-4。
- 建议用途：price_trend_gallery

### 不同ContNo组合的价格差值及ContNo为1的价格随时间变化
- 输出文件：`price_trend/doc_06_sc_multileg_spreads_vs_cont1_price.md`
- 来源：`/Users/mac/Desktop/股票/原油/各月份差.jpg`
- 摘要：图像将 1-2、2-3、3-4、4-5 四组价差与 ContNo1 价格放在双轴图中共同展示，横轴覆盖约 2022-11 至 2024-12，可用于观察近端价差与主力价格共振。
- 建议用途：price_trend

## 统计与结构化数据
### sc1-5统计(1)
- 输出文件：`spread_statistics/doc_02_sc_spread_statistics.md`
- 来源：`/Users/mac/Desktop/股票/原油/sc1-5统计(1).xlsx`
- 摘要：sc1-5统计(1).xlsx 已拆成 5 个 CSV。ALL 行显示 1-2 组合波动最大，当前自动识别的最高标准差腿为 1-2。
- 建议用途：spread_statistics

### sc_sprd (1)
- 输出文件：`spread_statistics/doc_03_sc_spread_timeseries.md`
- 来源：`/Users/mac/Desktop/股票/原油/sc_sprd (1).xlsx`
- 摘要：sc_sprd (1).xlsx 已拆成 13 个时序 CSV，整体覆盖 2018-07-26 至 2025-02-19。
- 建议用途：price_timeseries

## 结构化数据表
| 数据集 | 分组 | 行数 | 列数 | 起始日期 | 结束日期 | CSV |
| --- | --- | --- | --- | --- | --- | --- |
| sc1-5统计(1) / 1-2 | statistics | 25 | 17 | 2022-11-26 | 2024-11-25 | tables/statistics/dataset_01_sc_spread_statistics_1_2.csv |
| sc1-5统计(1) / 2-3 | statistics | 25 | 17 | 2022-11-26 | 2024-11-25 | tables/statistics/dataset_02_sc_spread_statistics_2_3.csv |
| sc1-5统计(1) / 3-4 | statistics | 25 | 17 | 2022-11-26 | 2024-11-25 | tables/statistics/dataset_03_sc_spread_statistics_3_4.csv |
| sc1-5统计(1) / 4-5 | statistics | 172 | 17 | 2022-11-26 | 2024-11-25 | tables/statistics/dataset_04_sc_spread_statistics_4_5.csv |
| sc1-5统计(1) / 全部 | statistics | 100 | 18 | 2022-11-26 | 2024-11-25 | tables/statistics/dataset_05_sc_spread_statistics_all.csv |
| sc_sprd (1) / 1-2 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_06_sc_spread_timeseries_1_2.csv |
| sc_sprd (1) / 2-3 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_07_sc_spread_timeseries_2_3.csv |
| sc_sprd (1) / 3-4 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_08_sc_spread_timeseries_3_4.csv |
| sc_sprd (1) / 4-5 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_09_sc_spread_timeseries_4_5.csv |
| sc_sprd (1) / 5-6 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_10_sc_spread_timeseries_5_6.csv |
| sc_sprd (1) / 6-7 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_11_sc_spread_timeseries_6_7.csv |
| sc_sprd (1) / 7-8 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_12_sc_spread_timeseries_7_8.csv |
| sc_sprd (1) / 8-9 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_13_sc_spread_timeseries_8_9.csv |
| sc_sprd (1) / 9-10 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_14_sc_spread_timeseries_9_10.csv |
| sc_sprd (1) / 10-11 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_15_sc_spread_timeseries_10_11.csv |
| sc_sprd (1) / 11-12 | timeseries | 1589 | 5 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_16_sc_spread_timeseries_11_12.csv |
| sc_sprd (1) / all | timeseries | 17479 | 6 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_17_sc_spread_timeseries_all.csv |
| sc_sprd (1) / all_daily | timeseries | 1589 | 14 | 2018-07-26 | 2025-02-19 | tables/timeseries/dataset_18_sc_spread_timeseries_all_daily.csv |

## 缺失维度提示
- 宏观背景：未检测到专门的宏观报告或宏观数据表。
- 供需基本面：未检测到库存/产量/进口/炼厂开工等直接原始资料。
- 库存统计：当前目录无库存日报或库存表，仅有价差统计与价格序列。

## 注入建议
- Narrative 文档：使用 `metadata/market_documents.jsonl` 与 `metadata/market_doc_chunks.jsonl`，`doc_type` 统一按 `research` 注入。
- 结构化表：优先消费 `metadata/datasets.jsonl` 中登记的 CSV，不建议把整张表直接塞进 chunk 文本。
- 策略工厂：建议把 `content_group`、`content_dimension`、`dataset_refs`、`instrument_type='futures'` 一并写入 metadata，便于后续过滤。
- 若走 `akshare-mcp` 的 DB-first 路径，可将这里的 narrative 文档视作 `research` 类型市场文档，并保留 `stock_code='SC'` 作为兼容字段。

## 核验建议
- 先用 `metadata/file_inventory.csv` 检查源文件是否全部落盘。
- 再抽查 `tables/timeseries/dataset_*_all_daily.csv` 与 `spread_statistics/doc_*.md` 是否和原始口径一致。
- 最后再将 narrative 文档 chunk 化写入向量集合 `market_doc_chunks`。
