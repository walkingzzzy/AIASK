# AIASK AKShare MCP 红队 v3 · 全量 Findings 汇总

- **Run ID**: `codex_conv_mcp_20260530`
- **完成时间**: 2026-05-30T20:10+08:00
- **场景**: 48/48 完成，总调用 **1471** 次（从各 status.json `tool_call_count` 精确汇总）
- **finding 条目**: **211** 个（HIGH 57 / MEDIUM 76 / LOW 78，跨48场景去重前的逐场景计数）
- **Fail-schema 工具调用行**: **106** 行（tool_status_rows 中 verdict=Fail-schema）
- **判定分布**: Pass 多数 / Degraded 常见(周末离线) / Fail-graceful 规范 / **Fail-schema 106 行（真 bug 级）**

> 注：211 个 finding 是逐场景计数，其中大量 HIGH 是 3 个系统级根因（000001污染/非法码坐标化/payload爆炸）在不同场景的重复出现。**去重后的不同根问题数量远少于 57**。

---

## 一、系统级根因（跨场景 ≥8 次复现）

> **⚠ 复测校验声明（2026-06-01 补充）**：报告主体观察基于 2026-05-30（周六）的工具响应。2026-06-01（周一）对核心根因 ROOT-1 做了复测，结论如下：
> - **根因持久成立（证据更强）**：`get_dead_letters()` 在 06-01 仍大量记录 000001 被 `index_close_out_of_range: expected [1000,30000]; possible cross-symbol contamination` 拒绝入库，并新增 `sh000001`（上证指数代码）K线被污染成平安银行价格（close=10.73）被拒的反向证据。校验器对个股 000001 套用指数价格区间这一**根因真实且持久**。
> - **但污染"表现"具有时点依赖性**：06-01 复测时 `get_batch_quotes(000001)=10.99`（正确平安银行）、`get_key_levels(000001)` current_price=10.99 / `calibrated=false` —— N46/N48 记录的 **4068 指数点位与 factor=377 校准不再复现**。说明 `db.stock_quotes` 快照在周末后已刷新，污染的具体数值表现取决于快照当时内容，非稳定可复现。
> - **修正措辞**：原报告把"凡直读 db.stock_quotes 的工具返回 4068"写成稳定结论并不准确，应表述为"当 db.stock_quotes 快照被指数数据占据时（如 05-30），直读该表的工具会继承污染；快照刷新后表现消失，但入库校验器的根因缺陷未修复，下次同样条件会复发"。

### ROOT-1: 000001 个股/指数双重语义污染（★★★ 最高优先级）

| 维度 | 详情 |
|---|---|
| **根因** | `sqlite.save_klines` 入库校验器把深市个股 000001（平安银行，股价≈11元）误判为指数，套用指数价格区间 `[1000,30000]` 将真实股价拒绝入库（dead-letter 持续证据，06-01 仍复现）。**根因持久** |
| **污染表现（时点性）** | 当 `db.stock_quotes` 快照被指数数据占据时（05-30 观察），直读该表的工具（`get_batch_quotes` / `get_key_levels` factor=377校准）返回 4068 指数点位；**快照刷新后表现消失（06-01 复测均返回正确 10.99），但根因未修复，同条件会复发** |
| **正确路径** | 走实时源/data_source/K线源的工具均用对平安银行：`get_realtime_quote`单查 / `get_kline`（+显式双重语义提示）/ `get_stock_info` / `calculate_factor` / `calculate_stop_levels` / `generate_trade_plan` |
| **正确范本** | `get_kline` 的处理：默认个股 + fallback_reason 显式提示「代码000001同时存在个股和指数语义，如需指数请用 sh000001/get_index_kline」 |
| **复现场景** | N34/N36/N38/N39/N46/N47/N48（7场景直接证据）+ N08(historical_valuation) |
| **修复建议** | (1)校验器按代码段+市场区分个股/指数; (2)清洗 db.stock_quotes 污染行; (3)推广 get_kline 的个股优先+双重语义提示到所有路径 |

### ROOT-2: 非法股票代码静默坐标化（★★ 高优先级）

| 维度 | 详情 |
|---|---|
| **表现** | 非法码（999999/BAD1/ZZZ999/INVALIDXX等）被提取数字+补零到6位，回退到上证指数或真实无关股票数据，success=true 零告警 |
| **复现场景** | N17/N18/N28/N30/N36/N41/N46/N47/N48（≥9场景） |
| **正确对照** | `search_stocks(999999)=not_found` / `get_realtime_quote(999999)=未找到` / `run_decision_gate(BADX)=代码格式无效` — 部分工具已正确拒绝 |
| **修复建议** | 在所有工具入口统一做股票代码白名单校验（6位数字+存在性检查），非法即拒绝 |

### ROOT-3: 巨型 payload 内嵌全量 factory run / overview（★★ 高优先级）

| 维度 | 详情 |
|---|---|
| **表现** | `strategy_manager`(submit/risk_events/promotion_reviews/factory_status/detail) 和 `strategy_review_workflow` 对单策略内嵌最近5个完整 factory run（每个≈110KB含10个stages），单响应数十万 token |
| **复现场景** | N16/N40/N41/N42/N44（5场景） |
| **修复建议** | 裁剪 factory.runs 仅摘要(run_id+status)，提供 lean 模式 |

---

## 二、HIGH 级 Findings（按类型聚类）

### 类型 A: 数据完整性/校验缺失

| ID | 场景 | 问题 |
|---|---|---|
| F-N18-1 | N18 | optimize_portfolio 含无数据代码时静默丢弃有效股、保留垃圾代码权重 |
| F-N32-1 | N32 | watchlist add_stocks 不校验代码合法性，任意字符串入库 |
| F-N34-2 | N34 | paper_trading 限价单不校验代码（市价单拒绝但限价单放行） |
| F-N46-5 | N46 | calculate_stop_levels 非正 entry_price(0/负)产出负止损价与负股数 |

### 类型 B: 决策逻辑/模型缺陷

| ID | 场景 | 问题 |
|---|---|---|
| F-N04-1 | N04 | RSI warmup 不足时输出 RSI=0 并给出「超卖买入」虚假信号 |
| F-N07-1 | N07 | valuation_consensus 内部 DCF/DDM 全失败但独立调用全成功（内部传参 bug） |
| F-N08-1 | N08 | scenario_dcf 蒙特卡洛产出负内在价值无护栏 |
| F-N22-1 | N22 | should_i_buy decision_probability 与历史实证严重失校准（ECE 0.5-0.75） |
| F-N22-2 | N22 | should_i_buy 'avoid' 结论与自身 offline_baseline 正收益证据矛盾 |
| F-N40-1 | N40 | smart_stock_diagnosis 对所有标的一律给 sell（证据归类系统性偏向 risk） |
| F-N43-2 | N43 | platt_a/platt_b 为死参数，用户传入的 Platt 系数被静默忽略 |
| F-N43-6 | N43 | governance crowding_score 恒为 0.85 常量占位（非真实相似度计算） |

### 类型 C: 未捕获异常/代码 bug

| ID | 场景 | 问题 |
|---|---|---|
| F-N11-1 | N11 | research_manager 全 action 崩溃: UnboundLocalError 'get_db' |
| F-N14-1 | N14 | calculate_factor_ic(turnover_20d/volume_ratio) 裸抛 IndexError |
| F-N15-1 | N15 | factor_robustness_check 100% 不可用: "'str' object has no attribute 'get'" |
| F-N26-2 | N26 | industry_chain_manager chain_id/code 路径泄露裸 SQL 错误 |
| F-N27-1 | N27 | parse_selection_query 把「连续3天上涨」误解析为 upn AND downn 矛盾条件 |
| F-N27-6 | N27 | screener_manager(run_strategy) 裸抛 TypeError |
| F-N38-2 | N38 | data_sync_manager(schedule) SQL 方言不兼容(array_to_string PostgreSQL→SQLite) |
| F-N47-1 | N47 | get_conditional_returns 对 MA 族字段裸抛 'DataFrame.tolist' |

### 类型 D: 质量门/护栏绕过

| ID | 场景 | 问题 |
|---|---|---|
| F-N01-1 | N01 | live_trading_manager 契约标注 read_only（运行时 CONFIRMATION_REQUIRED 兜底，N35验证） |
| F-N42-1 | N42 | publish 把零证据 draft 直接上架 listed（绕过 promotion_gate） |
| F-N43-4 | N43 | 数据质量子系统判定互斥（字段级 0.6 失败 vs GX 1.0 通过） |

---

## 三、MEDIUM 级 Findings 高频模式

1. **跨工具结论分歧无 reconcile**（N12情绪/N19压力测试/N22 buy vs baseline/N23/N30/N40 diagnosis vs unified）
2. **静默忽略非预期输入**（N22非法style/N29空indicators默认gdp/N43 model_drift未识别键/N44 runtime_control伪成功/N45缺task默认/N47未识别field）
3. **envelope 顶层与内层 degraded/fallback 标志不一致**（N01/N21/N24/N26/N28/N29 共6+场景）
4. **payload 重复/冗余**（N45 run_skill execution==result翻倍/N39 cache_stats双层冗余/N26 provider_contract 3-4重）
5. **write 操作无代码/类型校验**（N32 watchlist/N34 限价单/N42 strategy_type/N44 subscribe FK）

---

## 四、正向亮点（系统优势）

1. **get_kline 的 000001 双重语义处理是全系统正确范本**
2. **三大基线锚点 v3 全程稳定**（163工具/33分类/50因子+5分类+85别名，首尾复测零漂移）
3. **submit 质量门极严**（gate_a/b/c + research/incubation/live 三档 admission，与 publish 绕过形成鲜明对照）
4. **execution_reality 审计链完整**（fill_model/slippage/market_impact/commission/PIT/promotion_gate/4条警告）
5. **live_trading 三层纵深防御**（dry_run默认 → confirm_token → 网关只读）
6. **因子画像 get_factor_profile 决策证据极丰富**（current/series/percentile/trend/zscore/industry_rank/oversold_recovery）
7. **provider_contract/quality_gate 元数据体系完整**（6项 checks + reconciliation + provider_status 诊断）
8. **错误/降级路径普遍 graceful**（显式 error_code + degraded + fallback_reason，极少裸抛）

---

## 五、统计摘要

| 指标 | 数值 |
|---|---|
| 场景总数 | 48 |
| 总工具调用 | 1471（精确汇总） |
| finding 条目总数 | 211（逐场景计数） |
| HIGH findings | 57 |
| MEDIUM findings | 76 |
| LOW findings | 78 |
| Fail-schema 工具行 | 106 |
| 系统级根因 | 3（去重后） |
| 完全不可用工具 | 2（research_manager / factor_robustness_check） |
| 工具基线 | 163（稳定） |
| 零 Fail-schema 场景 | s01/s02/s05/s07/s09/s12/s21/s23/s35/s39（10个） |

> HIGH=57 的构成：约半数是 3 个系统级根因（000001污染≈9次、非法码坐标化≈9次、payload爆炸≈5次）在不同场景的复现实例，其余为各场景独有的代码 bug（research_manager崩/robustness崩/IC IndexError/MA字段崩等）与决策逻辑缺陷（diagnosis全sell/概率失校准/platt死参数/crowding常量等）。
