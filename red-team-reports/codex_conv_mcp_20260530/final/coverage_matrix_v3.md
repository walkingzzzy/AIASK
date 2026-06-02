# 工具覆盖矩阵 v3（163 工具 × 48 场景）

> 由于 163×48 完整矩阵过大，此处按分类汇总覆盖情况。每个分类标注：工具数 / 主要测试场景 / Fail-schema 近似数。
>
> **说明**：下表 Fail-schema 列为按分类的**近似归类**（人工估算），因单场景的 Fail-schema 行常跨多个工具与分类，故列和不精确等于实测总数 106。精确的 Fail-schema 行数请以各 `sNN/status.json` 的 `tool_status_rows` verdict 为准。

| 分类 (33) | 工具数 | 主覆盖场景 | Fail-schema |
|---|---|---|---|
| market (行情/K线/盘口) | 14 | N02/N03/N48 | 2 (batch_quotes 000001污染) |
| finance (财务/估值) | 10 | N06/N07/N08 | 3 (杜邦/consensus/负估值) |
| technical (技术指标/形态) | 8 | N04/N05/N46/N47 | 3 (RSI warmup/MA崩/形态) |
| decision (投资决策) | 12 | N21/N22/N23/N40 | 4 (概率失校准/diagnosis全sell) |
| quant (量化/因子) | 11 | N13/N14/N15/N41 | 6 (alias/IC IndexError/robustness崩) |
| factor (因子计算) | 8 | N13/N14/N15/N48 | 2 (alias不一致/pe失败) |
| fund_flow (资金流) | 9 | N09/N10 | 0 |
| news (新闻/研报) | 9 | N11 | 3 (research_manager崩) |
| sentiment (情绪) | 8 | N12/N30 | 2 (坐标化/冷热分类错) |
| portfolio (组合管理) | 5 | N18/N19/N20/N32 | 5 (权重错位/BL病态/watchlist无校验) |
| risk (风险分析) | 6 | N19/N20 | 2 (场景替换/Barra因子未实现) |
| backtest (回测) | 5 | N16/N17 | 4 (坐标化/payload/sharpe=0) |
| strategy (策略超市) | 15+ | N42/N44 | 11 (publish绕过/payload/FK泄露) |
| screening (选股) | 4 | N27 | 3 (NLP矛盾/run_strategy崩) |
| search (搜索/发现) | 5 | N01/N27/N48 | 1 (中文行业词失效) |
| sector (板块) | 5 | N26 | 1 (SQL列错误) |
| options (期权) | 4 | N10/N24 | 3 (类型静默误判/NaN/默认替换) |
| paper_trading (模拟交易) | 8 | N34 | 3 (涨跌停基准错/限价单无校验) |
| execution (执行拆单) | 4 | N35 | 0 (三层护栏验证通过) |
| compliance (合规) | 4 | N36 | 3 (000001基准错/坐标化) |
| user (用户画像) | 4 | N37 | 1 (双store割裂) |
| data_sync (数据同步) | 8 | N38/N39 | 2 (双重序列化/SQL方言) |
| alerts (告警) | 4 | N33 | 2 (双store/FK泄露) |
| watchlist (自选股) | 3 | N32 | 3 (无校验/级联/覆盖) |
| skills (技能) | 3 | N45 | 4 (中文/payload翻倍/默认) |
| vector (向量检索) | 4 | N05/N28 | 3 (坐标化) |
| macro (宏观) | 3 | N29 | 3 (深成指错/sentiment脱钩/空默认) |
| semantic (语义/日报) | 3 | N31 | 3 (非涨停纳入/highlights矛盾) |
| basic_data (基础数据) | 3 | N25/N48 | 1 (零股本无校验) |
| industry_chain (产业链) | 2 | N26/N48 | 0 |
| performance (绩效) | 3 | N16 | 0 |
| general | 2 | N43 | 0 |
| live_trading (实盘) | 3 | N35 | 0 ✓ (护栏验证通过) |

## 覆盖统计

- **33/33 分类全覆盖**（每个分类至少 1 个工具被调用）
- **163 工具中大部分被覆盖**：48 场景按分类系统性遍历，但**未逐一显式调用全部 163 个工具**（部分同类工具通过代表性抽样覆盖）。"163/163" 是覆盖目标而非已证实的逐工具调用计数。
- **Fail-schema 工具行总计 106**（按 tool_status_rows 的 verdict 精确统计；下表按分类的 Fail-schema 列为近似归类，因单场景的 Fail-schema 行常跨多个工具/分类，列和不精确等于 106）
- **Fail-schema 高发分类**: strategy > quant > portfolio > decision/skills/backtest
- **零 Fail-schema 场景（10个）**: s01/s02/s05/s07/s09/s12/s21/s23/s35/s39
- **零 Fail-schema 分类（近似）**: fund_flow / execution / industry_chain / performance / general / live_trading（live_trading 三层护栏验证通过 ✓）
