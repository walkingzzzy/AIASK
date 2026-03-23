# AI因子挖掘升级方案（LLM驱动版）

更新时间：2026-03-23  
位置：`/Users/mac/Desktop/股票/因子挖掘/AI因子挖掘升级方案.md`

## 0. 当前实施状态

截至 2026-03-21，代码侧的落地进度如下：

- P0 已完成
  - 已新增 `factor_llm_provider.py`
  - 已新增 `factor_prompt_builder.py`
  - 已新增 `factor_candidate.schema.json`
  - `quant_manager` 已支持 `llm_factor_mining`
  - 已支持真实 OpenAI-compatible `/chat/completions` 调用
  - 已保留 `llm_alpha.py` 作为 fallback

- P1 已完成
  - 已新增 `factor_candidate_compiler.py`
  - 已新增 `factor_validation_pipeline.py`
  - `quant_manager` 已支持 `validate_factor_candidate`
  - 已支持“直接传 candidate”与“从 `llm_factor_mining` artifact 继续验证”两条路径
  - 已完成 DSL 白名单编译与完整 `factor_validation_report`
  - 已接入横截面 IC / Rank IC、OOS、稳健性、相似度、换手、成本容量评估

- P2 增强版已完成
  - 已新增 `factor_candidate_storage.py`
  - 已新增 `factor_research_memory.py`
  - 已支持验证后自动写入研究记忆
  - 已支持生成前注入 `memory_context`
  - 已支持对新候选做历史相似度标注、相似边写回与去重惩罚排序
  - 已支持按策略切换重复阻断模式，而不是只做排序惩罚
  - `quant_manager` 已支持 `factor_candidate_registry`
  - `quant_manager` 已支持 `replay_factor_episode`
  - 已支持 `factor_candidate_registry.active_pool` 输出治理后候选池摘要
  - 已支持 `replay_factor_episode` 的 `list/get/summary` 查询
  - 已新增 `factor_research_memory` 查询动作（list/get/recall/stats）

- P3 主链版已完成
  - `strategy-factory` 的 `factor_research` 已接入治理后候选池 `active_pool`
  - `StrategySpawner` 已可从治理后候选池派生 family 偏好
  - `MarketOpportunityScanner` 已按 candidate family / regime / top_candidates 生成研究任务
  - `StrategyFactoryScheduler` 已输出 `factor_source_mode`、`active_candidate_count`、family/regime 摘要，并将候选因子 metadata 透传到自治任务摘要
  - 当 governed candidate pool 已激活时，旧 `factor_ic` freshness 不再直接把工厂硬阻断，而是降级为 warning
  - `FACTORY_RESEARCH_FACTORS` 已退化为 seed / fallback 角色

- P3 尾项及以后未完成
  - 多轮 Agent 化反馈迭代
  - 专表/向量索引级别的进一步持久化增强

### 0.1 运行验收补充（2026-03-22）

2026-03-22 已完成一轮真实运行验收，结论需要分成“代码验收”和“环境验收”两层：

- 代码验收通过
  - `packages/strategy-factory/tests` 已全量通过
  - 实测结果：`82 passed in 3.25s`
  - `StrategyFactoryScheduler.start()/stop()` 正常
  - `StrategyFactoryScheduler.run_once()` 可执行并返回 `status=success`
  - P3 尾项中关于 `candidate_provenance / source_candidate_artifact_id / candidate_family / expected_regime` 的提交链路留痕已补齐

- 当前机器环境验收未通过
  - 本机 `localhost:5432` 上的 TimescaleDB 未启动，`factor_research` 阶段会因 DB 连接失败降级
  - 当前宿主机 Docker daemon 未运行，无法直接通过 `docker-compose` 拉起 `timescaledb`
  - 实盘运行时外部行情抓取链路仍有问题，东财接口请求失败，导致市场快照存在 degraded 状态
  - 当前环境未配置 `FACTOR_LLM_*`，代码虽已支持真实大模型因子挖掘，但运行时尚未打开“因子专用 LLM provider”

本轮真实运行的关键结果：

- 调度器启动状态正常：`running=true`、`schedule_mode=continuous`、`runtime_enabled=true`
- 单次运行返回成功：`run_once_status=success`
- 但 governed candidate pool 未激活：
  - `factor_source_mode=error_fallback`
  - `governed_candidate_pool_active=false`
  - `active_candidate_count=0`
  - `active_family_count=0`
  - `active_regime_count=0`

因此，当前应明确区分两条结论：

- P3 代码改造已完成，主链行为与测试验收已达标
- 当前机器的“真实运行环境达标”尚未完成，还不能宣称 governed candidate pool 已在本机成功投入主链运行

### 0.2 数据底座补强与 DB-first 扩展（2026-03-22 第二轮）

为避免“底层已落库、上层仍绕回外部接口”，2026-03-22 又完成了一轮 DB-first 扩展，重点不再只是补数据，而是把业务读取链路真正切到库优先：

- 已新增数据库接口
  - `StrategyCrudMixin.get_north_fund_history(days, end_date)`
  - `get_recent_north_fund_summary()` 已支持按 `end_date` 回看

- 已改造的消费链路
  - `generate_daily_report()` 的 `capital_flow`
    - 先读 `north_fund_flow`
    - 按 `report_date` 回看最近交易日
    - 仅在 DB 无法提供可用数据时，才回退 `Tushare moneyflow_hsgt`
  - `_compute_alternative_factors_for_code()`
    - 北向资金分量先读 `db.get_north_fund_history`
    - 仅在 DB 无历史时才回退 `tools.fund_flow.get_north_fund`
  - `insight_manager`
    - 因直接复用 `generate_daily_report()`，已经自动继承这次 DB-first 行为

- 已完成测试与探针
  - 新增测试：
    - `tests/test_daily_report_db_first.py`
    - `tests/test_quant_mgr_helpers_db_first.py`
  - 联合回归：
    - `test_daily_report_db_first.py`
    - `test_quant_mgr_helpers_db_first.py`
    - `test_sentiment_db_first.py`
    - 结果：`5 passed`
  - 真实探针结果：
    - `generate_daily_report('2026-03-22')` 的 `capital_flow.north_fund.source = north_fund_flow`
    - 同次探针 `capital_flow.north_fund.trade_date = 2026-03-20`
    - `_compute_alternative_factors_for_code('600519')` 的 `source_chain` 已出现 `db.get_north_fund_history`

这一步的意义不是“多加一个 fallback”，而是把“历史已落库的数据必须由库驱动主流程”真正落到了日报与因子研究链路中。

### 0.3 fund_flow 工具层 DB-first 化（2026-03-22 第三轮）

第二轮解决的是“上层业务链路”优先读库，但 `fund_flow` 工具本身仍然主要走外部接口。  
第三轮补的是更底层的一步：把北向资金和融资融券工具自身改成 DB-first。

- 数据库接口补充
  - `StrategyCrudMixin.get_margin_market_history(days, end_date)`
  - `StrategyCrudMixin.get_margin_detail_latest(limit, ts_code, end_date)`
  - `StrategyCrudMixin._coerce_ts_code(...)`

- fund_flow 工具改造
  - `get_north_fund(days)`
    - source chain 最前面新增 `north_fund_flow`
    - 直接读取 `db.get_north_fund_history(...)`
    - 外部 `Tushare / HKEX / AkShare / EM summary` 改为后备源
  - `get_margin_data(stock_code, days)`
    - 无股票代码时优先读取 `margin_market_flow`
    - 指定股票时优先读取 `margin_detail`
    - 东财 / AkShare 市场汇总退居 fallback

- 验证结果
  - 新增测试：
    - `tests/test_fund_flow_db_first.py`
  - 联合回归：
    - `test_fund_flow_db_first.py`
    - `test_sentiment_db_first.py`
    - `test_daily_report_db_first.py`
    - `test_quant_mgr_helpers_db_first.py`
    - 结果：`9 passed`
  - 真实探针：
    - `get_north_fund(3)` 返回 `source = north_fund_flow`
    - `get_margin_data(days=3)` 返回 `source = margin_market_flow`
    - `get_margin_data('600519', days=3)` 返回 `source = margin_detail`

这意味着现在不仅 `daily_report` / `alternative_factors` 是 DB-first，连 `fund_flow` 这层基础工具也已经真正切到了“库优先、外部回退”。

### 0.4 融资融券排行 DB-first 化（2026-03-22 第四轮）

第三轮完成后，融资融券摘要、明细已经 DB-first，但排行接口 `get_margin_ranking()` 仍主要依赖东财。  
第四轮补的是这最后一块，让“摘要 / 明细 / 排行”三条融资融券链路全部库优先。

- 数据库接口新增
  - `StrategyCrudMixin.get_margin_ranking(top_n, sort_by, end_date)`
  - 基于 `margin_detail` 自动选择 `<= end_date` 的最新交易日
  - 支持 `balance / buy / sell` 三种排序口径

- 工具层改造
  - `get_margin_ranking()` 现在优先读取 `margin_detail_ranking`
  - 东财 datacenter 退为 fallback

- 测试与探针
  - `test_fund_flow_db_first.py` 已增加排行测试
  - 联合回归结果：`11 passed`
  - 真实探针：
    - `get_margin_ranking(top_n=5, sort_by='balance')`
      - `source = margin_detail_ranking`
    - `get_margin_ranking(top_n=5, sort_by='buy')`
      - `source = margin_detail_ranking`

- 当前残留
  - 个别排行样本 `name` 为空，说明名称映射表覆盖仍有缺口
  - 这是证券名称映射问题，不影响融资融券排行数据本身已经由数据库驱动

### 0.5 名称映射补齐与 core_market 同步入口打通（2026-03-22 第五轮）

第四轮之后，融资融券排行的主数据已 DB-first，但名称仍偶发缺失，尤其是 ETF/场内基金代码。  
同时，核心市场审查补数脚本仍主要靠手动执行，不利于纳入正式运维入口。

- 名称映射补齐
  - `market.helpers.get_stock_list_cached()` 现在会合并：
    - `stock_basic`
    - `fund_basic`
  - 因此 `get_name_map()` 不再只覆盖 A 股股票，也会覆盖场内基金/ETF
  - 真实探针中：
    - `511380 -> 可转债ETF博时`
    - `600519 -> 贵州茅台`
  - `get_margin_ranking(sort_by='buy')` 已实测能返回 ETF 名称，不再出现 `511380` 的空名

- core_market 同步入口
  - `data_sync_manager(action='sync', type='core_market')` 已正式支持
  - 内部会调用现有 [audit_sync_core_market_data.py](/Users/mac/Desktop/股票/scripts/audit_sync_core_market_data.py) 逻辑
  - 并返回：
    - `exit_code`
    - `market_aux` 当前库内状态
    - `stdout_tail` 摘要尾部
  - `data_sync_manager(action='schedule', type='core_market')` 也已放开，不再强制要求 `codes`

- 测试与真实验证
  - 新增测试：
    - `tests/test_market_name_map_fund_merge.py`
    - `tests/test_data_sync_manager_core_market.py`
  - 联合回归结果：`13 passed`
  - 真实小窗口同步探针：
    - `years=1`
    - `codes=['600519']`
    - `north_days=5`
    - `margin_days=5`
    - 结果：`exit_code=0`

- 当前边界
  - `core_market` 现在已经可以通过 `data_sync_manager(sync)` 正式触发
  - 但 `schedule` 仍是“登记型调度”，参数持久化能力较弱，尚未形成独立 worker 定时执行闭环

### 0.6 core_market 调度闭环落地（2026-03-22 第六轮）

第五轮之后，`core_market` 虽然已经能从 `data_sync_manager(sync)` 入口手动运行，但调度层仍停留在“只登记、不消费”的状态。  
这会导致数据库明明已经成为主数据底座，运维入口却还不能真正驱动补数闭环。

- 本轮完成的闭环改造
  - `sync_schedules` 的 `params JSONB` 已被正式接入业务层，不再只是 schema 上有字段
  - `data_sync_manager(action='schedule')` 现在会持久化：
    - `years`
    - `north_days`
    - `margin_days`
    - `calendar_year`
    - `stock_codes`
    - `priority`
  - 同时会在登记时写入 `next_run`
  - `data_sync_manager(action='run_due_schedules')` 已新增
    - 可执行真正到期的 schedule
    - 支持 `force=true`
    - 支持 `schedule_id` 定向执行，避免误触发其他历史调度
  - `data_sync_manager(action='list_schedules')` 已新增
  - `data_sync_manager(action='status')` 现在会返回：
    - `due_schedule_count`
    - `next_schedule_run`

- 代码层结果
  - `sync` 与 `schedule worker` 不再各走一套散乱执行逻辑
  - 统一收敛到 `_execute_sync_task(...)`
  - `run_due_schedules` 会在执行后回写：
    - `sync_schedules.last_run`
    - `sync_schedules.next_run`
  - 因此 `core_market` 已从“脚本可跑”升级为“正式调度入口可跑”

- 测试结果
  - `tests/test_data_sync_manager_core_market.py` 已扩展为 3 条闭环测试，覆盖：
    - `core_market sync` 无 `codes` 直接执行
    - `schedule` 写入 `params + next_run`
    - `run_due_schedules` 读取到期 schedule 并触发执行
  - 与前面 DB-first 回归联合执行结果：
    - `15 passed in 1.65s`

### 0.7 factor_context 正式同步入口与实库验收（2026-03-23）

第六轮完成后，`core_market` 已具备正式同步与调度闭环，但因子挖掘仍缺一块关键底座：
`factor_prompt_builder` 虽已改成 DB-first，新闻/公告/研报/个股资金流上下文却还没有标准化“入库预热入口”。

- 本轮完成
  - 新增脚本：
    - [audit_sync_factor_context_data.py](/Users/mac/Desktop/股票/scripts/audit_sync_factor_context_data.py)
  - 新增 TimescaleDB 持久化接口：
    - `save_vector_documents(...)`
    - `save_research_reports(...)`
    - `save_stock_fund_flow(...)`
  - `data_sync_manager` 已支持：
    - `action='sync', type='factor_context'`
    - `action='schedule', type='factor_context'`
    - `action='run_due_schedules', task_type='factor_context'`
  - 启动预热默认值已改为：
    - `quant_manager`: `core_market,factor_context`
    - `strategy-factory`: `core_market,factor_context`

- 工具链路调整
  - `get_stock_news(...)` / `get_stock_notices(...)` / `get_research_reports(...)` / `get_stock_fund_flow(...)`
    - 日常调用：默认 `prefer_db=True`，优先读库
    - 预热同步：显式 `prefer_db=False`，强制抓外部新数据
  - 个股资金流新增真实兜底链路：
    - `DB -> Tushare Pro moneyflow -> Eastmoney push2`
    - 这一步解决了“东财返回空 `klines` 时 `stock_fund_flow` 永远喂不起来”的问题

- 定向回归
  - `pytest packages/akshare-mcp/tests/test_fund_flow_db_first.py packages/akshare-mcp/tests/test_data_sync_manager_core_market.py packages/akshare-mcp/tests/test_factor_llm_p0.py -q`
    - `22 passed`
  - `pytest packages/strategy-factory/tests/test_factory_scheduler_readiness_controls.py -q`
    - `7 passed`
  - 额外回归：
    - `pytest packages/akshare-mcp/tests/test_factor_llm_p0.py packages/akshare-mcp/tests/test_quant_mgr_helpers_db_first.py packages/akshare-mcp/tests/test_unified_decision_builders.py -q`
    - `13 passed`

- 真实数据库验收
  - 先执行 7 日窗口同步：
    - 新闻与研报成功入库
    - 公告窗口过窄，`notice=0`
    - 当时东财个股资金流返回空，`stock_fund_flow=0`
  - 随后补上 `Tushare moneyflow` fallback，再执行同步：
    - `600519` / `000858` 个股资金流成功入库
  - 再将公告窗口扩到 30 日后执行：
    - `vector_documents_total=16`
    - `vector_documents_news=3`
    - `vector_documents_notice=3`
    - `vector_documents_research=10`
    - `research_reports=10`
    - `stock_fund_flow=2`

- 当前结论更新
  - 因子挖掘所需的“新闻 / 公告 / 研报 / 个股资金流”四类上下文，已经从“代码支持 DB-first”推进到“有正式预热入口 + 实库已填充样本”。
  - 当前 `FACTOR_LLM_ENABLED=1`，但专用 `FACTOR_LLM_PROVIDER / BASE_URL / MODEL` 仍未单独配置。
  - 按现有实现，因子挖掘 LLM 会优先读取 `FACTOR_LLM_*`；若未配置，则回退复用 `STRATEGY_LLM_*`。
  - 当前 `TUSHARE_TOKEN` 已配置，`EMBEDDING_*` 仍未单独配置，这不会阻塞本轮 `factor_context` 预热，但会影响后续独立 embedding 配置治理。

### 0.8 factor_context 范围扩展到 active_pool + representative + 工厂任务目标（2026-03-23）

0.7 之后，`factor_context` 已具备正式同步入口，但默认范围仍偏保守。  
这一轮的目标不是“再补两个固定代码”，而是把同步范围升级成真正贴近工厂运行态的动态股票池。

- 本轮完成
  - [audit_sync_factor_context_data.py](/Users/mac/Desktop/股票/scripts/audit_sync_factor_context_data.py)
    - 已新增动态范围解析：
      - `explicit`
      - `representative`
      - `active_pool`
      - `factory_targets`
    - 默认 `scope_sources=explicit,representative,active_pool,factory_targets`
  - `active_pool`
    - 从最新 `daily_snapshot.factor_research.active_candidate_pool.top_candidates` 读取 `artifact_id`
    - 再反查候选因子研究记忆中的 `codes`
  - `factory_targets`
    - 从 `strategy_task_runs(task_name='strategy_research_task', task_scope='strategy_factory')`
    - 读取当日研究任务中的 `research_task.target_symbols / event_context.target_symbols`
  - `representative`
    - 直接复用 `strategy_factory.domain.constants.REPRESENTATIVE_STOCKS`
  - `data_sync_manager`
    - `type='factor_context'` 已允许无 `codes` 执行
    - `schedule` 也允许无 `codes`，由运行时自动解析范围
    - 新增透传：
      - `scope_sources`
      - `active_pool_limit`
      - `task_run_limit`

- 测试结果
  - 新增：
    - [test_audit_sync_factor_context_data.py](/Users/mac/Desktop/股票/packages/akshare-mcp/tests/test_audit_sync_factor_context_data.py)
  - 扩展：
    - [test_data_sync_manager_core_market.py](/Users/mac/Desktop/股票/packages/akshare-mcp/tests/test_data_sync_manager_core_market.py)
  - 回归结果：
    - `test_audit_sync_factor_context_data.py + test_data_sync_manager_core_market.py`
      - `10 passed`
    - `test_factor_llm_p0.py + test_fund_flow_db_first.py`
      - `16 passed`
    - `test_factory_scheduler_readiness_controls.py`
      - `7 passed`

- 实库范围解析探针
  - 当前默认解析结果：
    - `representative_codes=10`
    - `active_pool.codes=0`
    - `factory_targets.codes=8`
    - 去重后 `resolved_codes=17`
  - 当前最新快照日期：
    - `active_pool.snapshot_date=2026-03-22`
    - `factory_targets.snapshot_date=2026-03-22`

- 最小窗口真实预热结果
  - 执行命令：
    - `python scripts/audit_sync_factor_context_data.py --news-days 1 --notice-days 1 --item-limit 1`
  - 同步范围：17 个代码
  - 结果：
    - `news_saved=15`
    - `research_saved=15`
    - `research_docs_saved=15`
    - `fund_flow_saved=17`
    - `error_count=0`

- 预热后库内状态
  - `vector_documents_total=46`
  - `vector_documents_news=18`
  - `vector_documents_notice=3`
  - `vector_documents_research=25`
  - `research_reports=25`
  - `stock_fund_flow=17`

- 当前结论更新
  - `factor_context` 默认同步范围已经从“固定两三只股票”升级成“代表池 + 工厂当日任务目标 + 可选治理候选池”。
  - 当前实库里 `active_pool.artifact_ids` 为空，因此本轮新增股票主要来自 `factory_targets`。
  - 一旦 governed candidate pool 在最新 snapshot 中稳定产出 `artifact_id`，脚本无需再改，会自动把这些候选对应股票并入同步范围。

### 0.9 启动预热自动补 schedule 与真实运行闭环（2026-03-23）

0.8 之后，`factor_context` 已支持动态股票池，但还有一个运行态缺口：
如果数据库里还没有任何 `sync_schedules`，那么 `run_runtime_data_warmup(...)` 仍可能直接返回 `status=skipped`。

- 本轮完成
  - `run_runtime_data_warmup(...)`
    - 已新增 `bootstrap_missing` 逻辑，默认开启
    - 当某个 `task_type` 没有任何启用中的 schedule 时，会自动：
      - 创建默认日调度
      - 立即进入正式 `run_due_schedules(...)` 执行路径
  - 自动登记的默认 schedule：
    - `schedule_runtime_core_market`
    - `schedule_runtime_factor_context`
  - `factor_context` 默认 schedule 参数已显式固化：
    - `scope_sources=explicit,representative,active_pool,factory_targets`
    - `active_pool_limit=12`
    - `task_run_limit=50`
    - `news_days=30`
    - `notice_days=30`
    - `item_limit=10`

- 测试结果
  - `test_run_runtime_data_warmup_bootstraps_missing_schedules` 已加入
  - 联合回归：
    - `test_data_sync_manager_core_market.py + test_audit_sync_factor_context_data.py`
      - `11 passed`
    - `test_factor_llm_p0.py + test_factory_scheduler_readiness_controls.py`
      - `15 passed`

- 真实运行探针
  - 当前库内已经存在：
    - `schedule_runtime_factor_context`
    - `schedule_runtime_core_market`
  - 强制执行探针：
    - `run_runtime_data_warmup(task_type='factor_context', force=True, source='runtime_probe_force')`
  - 返回结果：
    - `status=completed`
    - `matched=1`
    - `executed=1`
    - `executed_task_ids=['sync_factor_context_1774229360']`
    - 实际命中 schedule：
      - `schedule_runtime_factor_context`
  - 执行后统计：
    - `vector_documents=389`
    - `vector_documents_news=80`
    - `vector_documents_notice=139`
    - `vector_documents_research=170`
    - `research_reports=170`
    - `stock_fund_flow=17`

- 当前结论更新
  - `quant_manager` / `strategy_factory` 启动前的 `startup_warmup` 已不再依赖“必须人工先创建 schedule”。
  - 现在即使数据库最初没有预热调度，运行时也能自动补齐默认 schedule，并纳入正式日调度闭环。

### 0.7 因子 Prompt 上下文 DB-first 收敛（2026-03-23）

这一轮针对的不是“北向资金”这种已经落库并被上层消费的数据，而是 `factor_prompt_builder` 内仍可能直接触发外部请求的四类上下文：

- 个股新闻
- 个股公告
- 个股研报
- 个股资金流

本轮完成的改造如下：

- 新增统一 helper
  - `services/db_first_market_context.py`
  - 负责优先读取：
    - `vector_documents`
    - `research_reports`
    - `stock_fund_flow`
  - 当数据库没有可用内容时，才允许上层回退外部工具

- `factor_prompt_builder` 已改为库优先
  - `build_factor_mining_prompt()` 现在会先从数据库加载：
    - `news`
    - `notices`
    - `research`
    - `fund_flow`
  - 只有对应分量在 DB 中为空时，才回退：
    - `get_stock_news()`
    - `get_stock_notices()`
    - `get_research_reports()`
    - `get_stock_fund_flow()`

- prompt 内部的“替代因子”子链路也已一起收敛
  - `_compute_alternative_factors_for_code()` 现在复用同一套 `DB-first` helper
  - 不再出现“prompt builder 表层已经查库，但 sentiment/event/capital_flow 子链路还继续直接打外部接口”的分裂状态

- 工具层同步受益
  - `get_research_reports()` 已增加 `DB-first`
  - `get_stock_fund_flow()` 已增加 `DB-first`
  - `get_stock_news()` 已增加 per-stock `DB-first`
  - `get_stock_notices()` 已增加 per-stock `DB-first`

- schema 补齐
  - `schema_market.py` 已新增 `stock_fund_flow` 表定义
  - 本机数据库已完成初始化，`stock_fund_flow` 结构已创建

本轮真实数据库审查结果：

- `north_fund_flow`: `235` 行
- `vector_documents`: `0` 行
- `research_reports`: `0` 行
- `stock_fund_flow`: `0` 行

这说明当前代码层已经具备完整的 `DB-first + fallback` 能力，但文本与个股资金流数据底座还没有真正填充起来。  
换句话说，本轮解决的是“读取路径先查库”的问题，不是“新闻/公告/研报/个股资金流已经全部历史落库”的问题。

本轮测试结果：

- 直接回归通过：
  - `test_factor_llm_p0.py`
  - `test_quant_mgr_helpers_db_first.py`
  - `test_unified_decision_builders.py`
  - 结果：`13 passed in 10.68s`

- 新增覆盖点
  - 验证 `factor_prompt_builder` 在 DB 有内容时不会调用外部新闻/公告/研报/资金流工具
  - 验证 `_compute_alternative_factors_for_code()` 在 DB 有内容时优先消费：
    - `db.vector_documents.news`
    - `db.vector_documents.notice`
    - `db.research_reports`
    - `db.stock_fund_flow`

当前结论更新：

- 因子挖掘 prompt 构建链路已经不是“写死为外部接口驱动”。
- 现在的行为是：
  - 先读 DB
  - DB 有内容则完全由库驱动上下文
  - DB 没内容时才回退外部接口
- 下一步真正限制主链“完全不出网”的，不再是 prompt builder 代码，而是：
  - `vector_documents`
  - `research_reports`
  - `stock_fund_flow`
  这三类数据当前仍未完成持续入库。

- 真实验证
  - 实际登记一条 `core_market` 调度：
    - `schedule='daily'`
    - `stock_codes=['600519']`
    - `years=1`
    - `north_days=5`
    - `margin_days=5`
  - 再通过 `run_due_schedules(schedule_id=..., force=true)` 定向触发
  - 真实结果：
    - `matched=1`
    - `executed=1`
    - `sync_tasks.status=completed`
    - `results.exit_code=0`
    - `sync_schedules.last_run` 已回写
    - `sync_schedules.next_run` 已推进到下一日
  - 运行摘要尾部仍能看到：
    - `north_fund_rows=4`
    - `margin_market_rows=10`
    - `margin_detail_rows=14950`

- 结论更新
  - `core_market` 现在已经不只是“支持 schedule 创建”，而是具备了真正可执行的调度闭环
  - 数据库驱动的主流程进一步加强，外部接口只保留为补齐缺口时的 fallback

### 0.7 启动前 warmup 接入策略工厂与因子挖掘（2026-03-22 第七轮）

第六轮补完了 `core_market` 的调度闭环，但它还停留在“手动触发可用”。  
如果不把这个入口真正接到策略工厂和 AI 因子挖掘启动前，运行时仍然可能在数据未预热的情况下直接进入研究阶段。

- 本轮接入位置
  - 策略工厂：
    - `StrategyFactoryScheduler.run_once()` 现在会在 `collect` 之前先执行 `warmup` 阶段
    - 默认只消费 `task_type='core_market'` 的调度
  - AI 因子挖掘：
    - `quant_manager(action='llm_factor_mining')` 现在会在构建 prompt 前先跑 `startup_warmup`
    - 因此 LLM 候选生成之前会先尝试补齐市场底座

- 复用方式
  - 两条链路没有各自再实现一套预热逻辑
  - 统一复用 `data_sync_manager.run_runtime_data_warmup(...)`
  - 内部仍然走：
    - `run_due_schedules`
    - `core_market` schedule
    - `sync_tasks / sync_schedules` 状态回写

- 默认策略
  - 默认启用启动前 warmup
  - 默认只处理 `core_market`
  - 默认 `force=false`
  - 这意味着：
    - 有到期调度就执行
    - 没有到期调度就跳过，不会无条件每次重跑
  - 需要强制执行时：
    - 策略工厂可通过环境变量打开 `force`
    - `llm_factor_mining` 可通过参数显式传入 `startup_warmup_force=true`

- 运行时可观测性
  - 策略工厂运行结果新增：
    - `stages.warmup`
    - `summary.warmup_status`
    - `summary.warmup_matched`
    - `summary.warmup_executed`
    - `summary.warmup_failed`
  - `llm_factor_mining` 返回新增：
    - `startup_warmup`
    - `params.startup_warmup_*`

- 测试结果
  - 新增/扩展测试覆盖：
    - `test_factory_scheduler_readiness_controls.py`
    - `test_factor_llm_p0.py`
  - 定向回归：
    - `test_data_sync_manager_core_market.py`
    - `test_factor_llm_p0.py`
    - `test_factory_scheduler_readiness_controls.py`
  - 结果全部通过

- 真实探针
  - 实际创建一条 `core_market` 调度后，
    用 `quant_manager(action='llm_factor_mining', startup_warmup=true, startup_warmup_force=true)` 跑通了一次完整链路
  - 真实返回：
    - `startup_warmup.status = completed`
    - `startup_warmup.matched = 1`
    - `startup_warmup.executed = 1`
    - `generation_mode = local_rule_fallback`
    - `candidate_count = 2`

- 结论更新
  - `core_market` 调度已经从“可执行”升级为“会在关键研究链路启动前自动参与预热”
  - 策略工厂和 AI 因子挖掘都开始真正消费同一条 DB-first 调度底座

## 1. 方案调整结论

本次方案调整的核心结论是：

- 不再把项目的因子挖掘继续设计成“固定因子库 + 本地规则 + 轻量 AutoML”的增强版
- 将大模型放到“候选因子研究员”的位置，而不是只做解释或打标签
- 将程序化验证栈放到“审稿人 / 风控官”的位置，负责 IC、OOS、稳健性、去冗余、成本和容量约束
- 固定公式、关键词词典、本地规则模块保留，但只作为 seed pool 和 fallback，不再作为主引擎

新的主链应当是：

1. 构建研究上下文
2. 调用大模型生成候选因子
3. 将候选因子编译为可执行 DSL / AST
4. 用统一验证栈进行 IC / OOS / Robustness / Similarity / Cost-aware 验证
5. 将验证结果写入研究记忆
6. 把结果反馈给大模型继续迭代

因此，项目目标要从“固定因子验证平台”升级为“LLM 生成式因子发现 + 强验证 + 研究记忆闭环”。

## 2. 为什么必须调整

当前项目不是完全静态，但它的上限仍然被“手工定义的因子空间”锁住。

当前实现的真实问题不是因子值不更新，而是候选空间更新太慢：

- 行情、新闻、公告、资金流是动态的，但这些动态数据进入系统后，仍然主要被映射到固定规则和固定组合权重
- AutoML 能重新筛选特征，但只能在手工特征集合里选，不能自己发明新因子
- 文本理解仍以关键词词典为主，市场叙事变化后容易老化
- 策略工厂消费的主链因子集合仍偏固定，限制了新 alpha 进入核心流程

这会带来三个直接后果：

- 新风格、新题材、新交易结构出现时，系统很难自动提出新假设
- 因子研究越来越像“验证已有因子”，而不是“发现新因子”
- 整个项目会逐渐表现为“数据动态，但研究框架半写死”

所以，如果目标是真正的 AI 因子挖掘，就必须把“大模型生成候选因子”放进主链，而不是继续让本地规则担任主角色。

## 3. 联网技术验证：主流 AI 因子挖掘是如何实现的

### 3.1 成熟平台范式

以 Qlib 为代表，主流成熟平台会把以下能力打通：

- 统一数据层：行情、财务、文本、事件、行业、风险暴露
- 统一特征层：预定义 alpha、技术指标、基本面因子、衍生特征
- 模型层：截面排序、时序预测、组合模型
- 评估层：IC、Rank IC、分组收益、OOS、组合绩效、交易成本
- 工程层：实验管理、回测、调度、上线

代表资料：

- [Qlib 论文](https://arxiv.org/abs/2009.11189)
- [Qlib GitHub](https://github.com/microsoft/qlib)

Qlib 定义了一个重要基线：AI 因子研究必须是端到端、可复现、可回放的，而不是单次脚本。

### 3.2 公式因子搜索范式

这条路线的核心是：不要只在固定因子库里挑，而是在公式空间里生成新 alpha。

常见做法：

- 使用遗传编程或进化搜索生成表达式
- 使用强化学习或树搜索在算子空间中组合公式
- 对候选因子施加复杂度、相似度、稳定性、交易性约束
- 保留有效因子，淘汰冗余或脆弱因子

代表资料：

- [AutoAlpha](https://arxiv.org/abs/2002.08245)
- [Synergistic Formulaic Alpha Generation](https://arxiv.org/abs/2401.02710)

### 3.3 LLM / Agent 因子挖掘范式

2024-2026 的前沿路线，是把 LLM / Agent 放到“研究员”位置，而不只是“解释器”位置。

常见流程：

1. 从价格、财务、文本、事件、资金流等多模态数据中构建研究上下文
2. 由 LLM / Agent 生成候选因子、候选规则或组合信号
3. 通过程序化验证栈做 IC、OOS、稳健性、成本、冗余评估
4. 把验证结果反馈给 Agent，进入下一轮生成
5. 保留实验记忆，避免重复发明低质量信号

代表资料：

- [Automate Strategy Finding with LLM in Quant Investment](https://arxiv.org/abs/2409.06289)
- [AlphaAgent](https://arxiv.org/abs/2502.16789)
- [QuantaAlpha](https://arxiv.org/abs/2602.07085)
- [FactorMiner](https://arxiv.org/abs/2602.14670)

这一类系统的共同点不是“让模型直接交易”，而是：

- 让模型负责提出假设
- 让程序负责验证和治理
- 让记忆系统负责累积经验

### 3.4 因子与模型联合优化范式

最新方向不再把“因子挖掘”和“模型训练”完全拆开，而是联合优化：

- 先发现有信息量的因子
- 再训练最适合消费这些因子的模型
- 再根据模型表现反向淘汰、重组、增强因子

代表资料：

- [R&D-Agent-Quant](https://arxiv.org/abs/2505.15155)
- [RD-Agent GitHub](https://github.com/microsoft/RD-Agent)

### 3.5 深度联网技术验证结论

截至 2026 年 3 月 21 日，这一轮深度联网核验的结论是：

- 主流前沿方案已经明确把大模型放到“候选因子生成”位置，而不是只做解释、摘要或规则打分
- 主流工业化方案并没有取消规则系统，而是把规则系统降级为“执行边界与治理层”
- 因子挖掘是否属于真正的 AI 驱动，关键不在于系统里有没有模型，而在于“候选因子是否由模型主链生成”

按时间线看，外部证据非常一致：

- 2024-09-10 的 [Automate Strategy Finding with LLM in Quant Investment](https://arxiv.org/abs/2409.06289) 已经明确提出用 LLM 从多模态金融数据中挖掘 alpha factors，并通过多 agent 和动态 gating 形成自适应组合
- 2025-02-24 的 [AlphaAgent](https://arxiv.org/abs/2502.16789) 明确提出 LLM-driven alpha mining，同时加入 AST 相似度、语义一致性和复杂度控制，用来对抗 alpha decay
- 2025-05-16 的 [R&D-Agent-Quant](https://arxiv.org/abs/2505.15155) 将自动化量化研究推进到 factor-model co-optimization，不再停留在固定因子验证
- 2025-08-08 的 [Chain-of-Alpha](https://arxiv.org/abs/2508.06312) 使用双链式生成与优化流程，通过回测反馈和先验知识迭代改进因子
- 2026-02-06 的 [QuantaAlpha](https://arxiv.org/abs/2602.07085) 已经将多轮 evolutionary search 做成 trajectory 级别的 mutation / crossover，并约束 hypothesis、expression、code 的一致性
- 2026-02-17 的 [FactorMiner](https://arxiv.org/abs/2602.14670) 进一步走向 retrieve-generate-evaluate-distill 的自演化框架，把 experience memory 放到主链里
- 2026-03-17 的 [FactorEngine](https://arxiv.org/abs/2603.16365) 直接提出三层分离，其中包括“LLM-guided directional search vs. local computation”以及“LLM usage vs. local computation”

这些证据共同说明：

- 如果候选因子仍然主要来自手写规则池，那就仍然是“规则驱动因子研究”
- 如果大模型真正参与候选因子生成，而程序只负责编译、验证、约束和持久化，才属于当前主流意义上的“AI 因子挖掘”

因此，本项目在升级时必须坚持一个原则：

- 大模型负责扩大搜索空间
- 规则系统负责收缩执行边界

不能反过来。

## 4. 项目当前实现现状

### 4.1 已有基础能力

当前项目已经具备以下基础设施：

- 因子注册、计算、分析、OOS、稳健性
- 因子值 / IC 历史落库
- 因子调度与 artifact 体系
- 策略工厂对 `factor_research` 的消费链
- 外部大模型调用抽象
- embedding 调用抽象

相关实现位置：

- 因子主链：`packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`
- 另类因子：`packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_mgr_helpers.py`
- 轻量 AutoML：`packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_mgr_automl.py`
- 本地规则版“LLM”因子生成器：`packages/akshare-mcp/src/akshare_mcp/services/llm_alpha.py`
- 外部模型调用层：`packages/akshare-mcp/src/akshare_mcp/services/strategy_llm_provider.py`
- embedding 调用层：`packages/akshare-mcp/src/akshare_mcp/services/text_embedding.py`
- 策略工厂因子研究：`packages/strategy-factory/src/strategy_factory/application/factor_research.py`

### 4.2 当前主链的问题

当前主链更准确的描述是：

1. 在固定因子集合里计算核心因子
2. 用轻量统计方法和启发式规则做排序
3. 生成 `factor_research` artifact
4. 将结果提供给策略工厂使用

这条链路在工程上是通的，但它不是“LLM 驱动因子挖掘”。

其中最关键的问题有四个：

- `llm_alpha.py` 名字像 LLM，但当前本质是本地规则版，不调用外部模型
- 另类因子仍主要是固定权重聚合，不是模型驱动生成
- AutoML 仍然只是在手工特征空间里做筛选
- 策略工厂主链仍偏向消费固定标准因子集合

## 5. AI 能力应如何调用

### 5.1 结论

新的 AI 因子挖掘不应再依赖本地规则主导，而应当显式接入大模型调用。

推荐方式不是把实现绑死在某一家模型厂商，而是采用统一的 OpenAI-compatible 协议层。

也就是说：

- 可以接外部模型 API
- 也可以接自建模型服务
- 只要暴露标准 `/chat/completions` 和 `/embeddings` 接口即可

### 5.2 与当前项目的衔接方式

当前项目已经有两块可直接复用的能力：

- `strategy_llm_provider.py`
- `text_embedding.py`

这意味着 AI 因子挖掘完全可以沿用同一套接入模式，而不需要从零重写网络调用层。

建议新增两种实现方式中的一种：

方案 A：复用现有 provider，扩展为通用研究 provider

- 将 `StrategyLLMProvider` 抽象升级为通用 `ResearchLLMProvider`
- 策略工厂与因子挖掘共用一套 provider 基础设施

方案 B：单独新增因子研究 provider

- 新建 `factor_llm_provider.py`
- 内部沿用与 `StrategyLLMProvider` 相同的实现模式
- 通过独立环境变量控制模型、超时、并发、温度和输出结构

本项目更推荐方案 B。

原因：

- 因子挖掘与策略生成的 prompt、输出 schema、调用频率、温度要求都不同
- 后续更容易单独调优和灰度发布
- 避免把策略生成逻辑和因子研究逻辑耦合在一起

### 5.3 推荐的模型接入模式

推荐采用如下统一协议：

- 文本生成：`/chat/completions`
- 向量相似度：`/embeddings`

推荐支持三类部署：

- 外部 API：兼容 OpenAI 接口的云端模型服务
- 自建推理：vLLM / SGLang / TGI 暴露 OpenAI-compatible 接口
- 本地推理网关：Ollama 外挂兼容层后接入

这样设计的好处是：

- 上层业务不感知到底是外部模型还是内部模型
- 模型切换只改配置，不改业务代码
- 后续可以按成本、速度、稳定性分配不同任务给不同模型

### 5.4 推荐的环境变量

建议新增独立配置前缀：

- `FACTOR_LLM_ENABLED`
- `FACTOR_LLM_PROVIDER`
- `FACTOR_LLM_BASE_URL`
- `FACTOR_LLM_API_KEY`
- `FACTOR_LLM_MODEL`
- `FACTOR_LLM_TIMEOUT_SEC`
- `FACTOR_LLM_MAX_TOKENS`
- `FACTOR_LLM_TEMPERATURE`
- `FACTOR_LLM_MAX_CONCURRENCY`

embedding 侧：

- `FACTOR_EMBEDDING_ENABLED`
- `FACTOR_EMBEDDING_BASE_URL`
- `FACTOR_EMBEDDING_API_KEY`
- `FACTOR_EMBEDDING_MODEL`

### 5.5 角色分工

在新方案里，大模型与程序的职责必须清晰分离：

大模型负责：

- 从多模态上下文中提出研究假设
- 生成候选因子表达式
- 解释因子机制
- 根据失败记忆提出新变体

程序负责：

- 时间对齐和 PIT 数据查询
- DSL / AST 编译
- 因子计算
- IC / OOS / 稳健性验证
- 相似度去重
- 成本与容量约束
- artifact 持久化

这能避免“模型直接产出交易结论”带来的不可控风险。

### 5.6 模型接入方式的联网验证

这一点也已经通过官方资料核验过。

截至 2026 年 3 月 21 日，当前最适合本项目的模型接入方式，不是把代码绑死在某个云厂商 SDK 上，而是统一采用 OpenAI-compatible 协议层。

官方资料表明：

- [vLLM 官方文档](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) 明确支持 OpenAI-compatible server，可直接提供 `chat/completions`
- [Hugging Face TGI 官方文档](https://huggingface.co/docs/text-generation-inference/main/messages_api) 明确说明 Messages API 与 OpenAI Chat Completion API fully compatible
- [Ollama 官方 OpenAI compatibility 说明](https://ollama.com/blog/openai-compatibility) 明确说明其已支持 OpenAI Chat Completions API 兼容调用

这意味着项目可以采用统一上层接口，同时支持三种后端：

- 外部云端模型 API
- 自建 vLLM / TGI 推理服务
- 本地 Ollama 模型服务

因此，技术路线应当是：

- 业务侧统一走 `FactorLLMProvider`
- provider 统一走 OpenAI-compatible `chat/completions`
- embedding 统一走 OpenAI-compatible `embeddings`
- 具体使用 OpenAI、vLLM、TGI 还是 Ollama 由配置决定

这样做的价值在于：

- 不把项目锁死在单一模型供应商
- 允许云端与本地混合部署
- 允许后续按成本、速度、稳定性切换模型

### 5.7 什么情况下才能算“真正的 AI 因子挖掘”

为了避免未来再次把“规则增强版”误写成“AI 因子挖掘”，建议在方案中加入硬性验收标准。

只有同时满足以下条件，才可以把相关模块对外定义为“AI 因子挖掘”：

1. 因子挖掘主链存在真实的模型调用
   调用对象可以是云端 API、本地 Ollama、自建 vLLM/TGI，但必须是真实的模型推理，不是模拟器或规则替代

2. 模型输出的是结构化候选因子
   输出至少包含 hypothesis、inputs、expression_dsl、regime、holding_period 等字段，而不是只返回说明文本

3. 候选因子是由模型主导生成，而不是从固定规则池里简单重排
   固定规则池只能作为 bootstrap seed 或 fallback，不得继续承担主发现引擎角色

4. 所有候选因子都必须经过程序化治理
   包括 DSL 编译、字段白名单、算子白名单、复杂度约束、相似度去重、IC、OOS、稳健性和成本验证

5. 研究结果必须可回放、可审计
   必须记录 prompt、模型版本、候选因子、验证结果、淘汰原因和最终保留结果

如果不满足以上条件，那么该模块更准确的命名应该是：

- 规则驱动因子研究
- 统计增强因子筛选
- 轻量 AutoML 因子分析

而不应命名为“AI 因子挖掘”。

## 6. 新目标架构

建议将项目升级为七层架构。

### 6.1 Layer A：Research Data Fabric

统一研究数据底座：

- K 线 / 分钟线 / 财务
- 公告 / 新闻 / 研报
- 资金流 / 北向 / 龙虎榜 / 融资融券
- 行业 / 风格暴露 / 风险因子

要求：

- 支持 point-in-time 查询
- 支持统一时间对齐
- 支持实验重放

### 6.2 Layer B：Research Context Builder

新增研究上下文构建层，把多模态数据压缩成模型可消费的研究输入。

输出内容建议包括：

- 标的和股票池概览
- 近期收益结构和波动结构
- 财务变化摘要
- 文本事件摘要
- 资金流和风格暴露摘要
- 已有高相关因子列表
- 失败因子摘要

### 6.3 Layer C：LLM Factor Generator

新增真正的候选因子生成层，由大模型输出结构化候选因子。

候选因子建议统一 contract：

- `factor_id`
- `name`
- `hypothesis`
- `family`
- `inputs`
- `expression_dsl`
- `expected_holding_period`
- `expected_regime`
- `complexity_hint`
- `novelty_rationale`
- `generation_trace`
- `source_model`

推荐输出 JSON，不允许自由文本主导。

示意：

```json
{
  "name": "event_attention_reversal",
  "family": "event_reversal",
  "hypothesis": "事件密集但资金承接弱时，短期存在反转",
  "inputs": ["close", "volume", "notice_count_5d", "main_net_inflow_5d"],
  "expression_dsl": "zscore(notice_count_5d,20) * -zscore(main_net_inflow_5d,20) * -return_5d",
  "expected_holding_period": 5,
  "expected_regime": ["high_event_density", "weak_follow_through"]
}
```

### 6.4 Layer D：Compiler and Safe Executor

新增 DSL / AST 编译与安全执行层。

核心原则：

- 模型不能直接返回 Python 可执行代码
- 模型只能返回白名单 DSL
- 由系统把 DSL 编译成受控表达式

支持的基础能力：

- 算子白名单
- 字段白名单
- 窗口长度约束
- 复杂度评分
- 泄漏检查

### 6.5 Layer E：Validation and Governance

所有候选因子必须经过统一验证：

- IC / Rank IC
- 行业 / 市值 / Beta 中性化
- Walk-forward OOS
- Purged KFold
- Bootstrap 置信区间
- 参数敏感性
- Decay 检测
- Similarity / redundancy
- Cost-aware performance
- Turnover / capacity / tradability

这层不允许被模型绕过。

### 6.6 Layer F：Research Memory

新增研究记忆层：

- 候选因子注册表
- 历史实验记录
- 因子 embedding
- 与已有因子的相似度图谱
- 失败模式标签
- prompt 与结果轨迹

记忆层要解决的问题是：

- 避免重复发明
- 累积哪些方向有效
- 让下一轮生成更像“延续研究”，而不是“重新瞎猜”

### 6.7 Layer G：Strategy Factory Integration

最终不再让策略工厂只消费固定因子集合，而是消费“治理通过的候选因子池”。

可接入的下游包括：

- 单因子排序
- 多因子打分
- 事件 + 因子混合策略
- 因子子集驱动的模型训练

## 7. 主链工作流

建议的目标工作流如下：

1. `collect_context`
   从行情、财务、事件、文本、资金流、已有记忆中构建研究上下文

2. `generate_candidates`
   调用 `FactorLLMProvider` 一次生成多组候选因子 JSON

3. `compile_candidates`
   将 `expression_dsl` 编译为可执行受控表达式

4. `validate_candidates`
   统一跑 IC、OOS、稳健性、冗余、成本和容量

5. `write_memory`
   将成功和失败的候选统一写入研究记忆

6. `feedback_iteration`
   将最佳因子、失败因子、相似冲突因子反馈给模型再生成下一轮

7. `promote_to_factory`
   将通过治理的候选因子池写入 `factor_research`，交给策略工厂消费

## 8. 分阶段落地方案

### 8.1 P0：先把模型调用底座搭起来

目标：让因子挖掘拥有专用的大模型调用层，而不是继续依赖本地规则。

工作项：

- 新增 `factor_llm_provider.py`
- 新增 `factor_embedding_provider.py` 或复用 `text_embedding.py`
- 新增 `factor_prompt_builder.py`
- 新增统一输出 schema 和 JSON 解析器
- 为 provider 加入超时、重试、并发和降级逻辑

建议涉及模块：

- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_llm_provider.py`
- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_prompt_builder.py`
- 参考 `packages/akshare-mcp/src/akshare_mcp/services/strategy_llm_provider.py`
- 参考 `packages/akshare-mcp/src/akshare_mcp/services/text_embedding.py`

### 8.2 P1：让 LLM 正式进入因子挖掘主链

目标：实现“模型生成候选因子，程序验证候选因子”的第一版闭环。

工作项：

- 在 `quant_manager` 新增 `llm_factor_mining`
- 输出候选因子 JSON，而不是本地规则池
- 引入因子 DSL 和安全编译器
- 将验证结果封装成 `factor_validation_report`
- 保留本地规则版 `llm_alpha.py` 作为 fallback

建议涉及模块：

- `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`
- `packages/akshare-mcp/src/akshare_mcp/services/llm_alpha.py`
- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_candidate_compiler.py`
- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_validation_pipeline.py`

### 8.3 P2：引入研究记忆和 embedding 去重

目标：让系统具备“持续研究”的能力，而不是每次从零开始。

当前状态：基础版已完成

工作项：

- 保存候选因子文本描述和 DSL 的 embedding
- 保存历史验证结果、失败标签和相似度边
- 在生成前先召回相似成功 / 失败案例
- 对高相似候选设置惩罚或直接拦截

建议涉及模块：

- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_research_memory.py`
- 新增 `packages/akshare-mcp/src/akshare_mcp/services/factor_candidate_storage.py`
- 复用 `packages/akshare-mcp/src/akshare_mcp/services/text_embedding.py`

### 8.4 P3：把策略工厂从“固定因子消费”改成“治理后因子池消费”

目标：真正打通 LLM 因子挖掘与策略工厂。

工作项：

- `factor_research` 不再只围绕固定标准因子集合
- 将 `FACTORY_RESEARCH_FACTORS` 从“主消费集合”调整为“bootstrap seed set”
- 按 candidate family、validation score、regime tag 组织可消费因子池
- 让 `spawner` 根据治理后的候选池生成更匹配的策略类型

建议涉及模块：

- `packages/strategy-factory/src/strategy_factory/application/factor_research.py`
- `packages/strategy-factory/src/strategy_factory/application/opportunity.py`
- `packages/strategy-factory/src/strategy_factory/application/factory_scheduler.py`
- `packages/strategy-factory/src/strategy_factory/domain/constants.py`
- `packages/strategy-factory/src/strategy_factory/domain/spawner.py`

当前状态补充：

- 已完成 `factor_research -> opportunity -> scheduler -> spawner` 的主链打通
- `scanner` 生成的 snapshot 任务已可携带 `candidate_family`、`source_candidate_artifact_id`、`validation_score`、`expected_regime`
- run summary 已可区分 `governed_candidate_pool` 与 `seed_fallback`
- readiness 已对“governed pool active + legacy factor history stale”做差异化处理

### 8.5 P4：升级为多轮 Agent 化研究系统

目标：形成真正的“生成 -> 验证 -> 反馈 -> 再生成”多轮研究系统。

工作项：

- 一轮生成多个候选
- 自动挑选最优 / 最差样本反馈给模型
- 对 regime drift、相似失败、复杂度超限做定向提示
- 支持 generator / critic / reviewer 多角色协作

最终形态：

- 大模型不再只生成一次
- 因子研究变成持续迭代的 research episode

## 9. 对现有代码的具体调整建议

### 9.1 `llm_alpha.py`

当前文件名会造成误导。

建议调整为二选一：

- 改名为 `local_alpha_fallback.py`
- 保留文件名，但把类名和注释明确改成“本地规则 fallback”

不要再把它当成未来主引擎。

### 9.2 `quant_manager.py`

建议新增或重构以下 action：

- `llm_factor_mining`
- `validate_factor_candidate`
- `factor_candidate_registry`
- `replay_factor_episode`

让 `automl_discovery` 从“发现主入口”变成“验证辅助手段”。

当前状态补充：

- `factor_candidate_registry` 已落地，可按 grade / recommendation / family / codes 聚合治理后候选池
- `factor_candidate_registry.active_pool` 已落地，可输出 family / regime / score 维度的活跃候选池摘要
- `replay_factor_episode` 已落地，可对一轮 `llm_factor_mining` 结果做整批复验并输出晋级/淘汰摘要
- `replay_factor_episode` 已支持查询历史回放 episode，而不是只在执行当次返回结果

### 9.3 `factor_research.py`

建议让 `factor_research` 的输入从：

- 固定标准因子摘要

升级为：

- 已验证候选因子池
- family 分组摘要
- regime 适用摘要
- 去冗余和衰减摘要

### 9.4 `constants.py`

`FACTORY_RESEARCH_FACTORS` 不应再承担“主链唯一因子集合”的角色。

建议调整为：

- 启动期 seed set
- 回退模式默认集合
- 无候选因子时的兜底输入

## 10. 风险与治理要求

引入大模型之后，最大的风险不是“模型不够聪明”，而是“模型输出不可控”。

因此必须加四类硬约束：

### 10.1 输出约束

- 只允许 JSON 输出
- 只允许白名单 DSL
- 禁止直接执行模型生成代码

### 10.2 数据约束

- 全部使用 point-in-time 数据
- 必须做 look-ahead 检查
- 必须记录数据源和时间戳

### 10.3 研究约束

- 必须做相似度去重
- 必须做复杂度惩罚
- 必须做 OOS 和稳健性验证
- 不允许只看单次样本内 IC

### 10.4 运行约束

- 模型不可用时自动回退到本地规则 seed pool
- 所有 episode 可回放
- 所有验证摘要可审计

## 11. 推荐的实施优先级

这次调整后，优先级也要改变。

### 第一优先级

- 搭建专用 `FactorLLMProvider`
- 构建研究上下文层
- 定义候选因子 JSON schema 和 DSL

原因：

- 没有这层，就不可能真正变成 LLM 驱动因子挖掘

### 第二优先级

- 跑通 LLM 候选生成 + 统一验证闭环
- 将结果写入 candidate registry 和 memory

原因：

- 这是“AI 因子挖掘”第一次真正发生的地方

### 第三优先级

- 将通过治理的候选因子池接入策略工厂
- 逐步弱化固定标准因子集的主导地位

原因：

- 不接入策略工厂，AI 因子挖掘只能停留在实验层

## 12. 对项目的最终判断

如果项目目标只是“有个可解释、可验证的量化研究平台”，那当前方案已经够用。

但如果目标是“AI 因子挖掘”，那么当前主链确实不够。

真正需要的不是继续把本地规则做复杂，而是把架构改成：

- 大模型负责生成候选因子
- 程序负责验证和治理
- embedding 和记忆系统负责避免重复试错
- 策略工厂负责消费治理后的候选因子池

最终目标状态应当是：

- 当前状态：固定因子验证平台
- P1 后：LLM 候选生成平台
- P2 后：带记忆的 LLM 因子研究平台
- P3 后：LLM 因子研究与策略工厂打通
- P4 后：Agent 化因子研究系统

## 13. 参考资料

- [Qlib: An AI-oriented Quantitative Investment Platform](https://arxiv.org/abs/2009.11189)
- [Microsoft Qlib](https://github.com/microsoft/qlib)
- [AutoAlpha](https://arxiv.org/abs/2002.08245)
- [Synergistic Formulaic Alpha Generation](https://arxiv.org/abs/2401.02710)
- [Automate Strategy Finding with LLM in Quant Investment](https://arxiv.org/abs/2409.06289)
- [AlphaAgent](https://arxiv.org/abs/2502.16789)
- [R&D-Agent-Quant](https://arxiv.org/abs/2505.15155)
- [RD-Agent](https://github.com/microsoft/RD-Agent)
- [QuantaAlpha](https://arxiv.org/abs/2602.07085)
- [FactorMiner](https://arxiv.org/abs/2602.14670)

## 14. 项目实施清单

本节用于直接指导实施，不再停留在架构描述层。

### 14.1 第一阶段实施清单

目标：先让项目具备“真实调用大模型生成候选因子”的能力。

当前状态：已完成

必须完成：

- 新增 `FactorLLMProvider`
- 新增 `FactorPromptBuilder`
- 定义 `factor_candidate.schema.json`
- 在 `quant_manager` 中新增 `llm_factor_mining`
- 保证模型输出为 JSON 候选因子列表
- 保证本地规则版只作为 fallback

验收标准：

- 当 `FACTOR_LLM_ENABLED=1` 且 provider 可用时，主链实际发生外部或本地模型调用
- 返回结果中必须能看到 `source_model`、`provider`、`trace_id`、`candidate_count`
- 候选因子不再来自固定规则池排序，而是来自模型生成的 `expression_dsl`

### 14.2 第二阶段实施清单

目标：让 LLM 生成的候选因子真正进入可治理的研究闭环。

当前状态：已完成

必须完成：

- 新增 DSL 编译器
- 加入字段白名单和算子白名单
- 为每个候选生成 `factor_validation_report`
- 统一接入 IC / Rank IC / OOS / Robustness / Similarity / Cost-aware 验证
- 将验证结果持久化

验收标准：

- 模型不能返回 Python 代码直接执行
- 所有候选必须先过编译再验证
- 所有被淘汰候选都能追溯淘汰原因

### 14.3 第三阶段实施清单

目标：让系统具备“研究记忆”，避免重复低质量试错。

当前状态：增强版已完成（artifact-based memory + recall + similarity edges + optional blocking dedup）

必须完成：

- 保存候选因子的自然语言摘要与 DSL
- 保存 embedding
- 保存 success / fail / duplicate / unstable 等标签
- 支持按相似度召回历史成功和失败案例
- 支持将历史案例作为 prompt 上下文输入模型
- 支持把高相似历史失败样本升级为“可阻断信号”，而不是只做排序惩罚

验收标准：

- 第二次生成时能显式避开历史高相似失败因子
- 能标出“与已有候选重复”或“与历史失败模式相似”的原因
- 可通过 `dedup_mode` 选择 `penalty` 或 `block`，并在返回结果中看到 `blocked_candidates` 与阻断原因

### 14.4 第四阶段实施清单

目标：将 LLM 因子研究结果正式并入策略工厂主链。

当前状态：P3 主链版已完成（factor_research / opportunity / scheduler / spawner 已接入 governed candidate pool）

必须完成：

- `factor_research` 从固定因子摘要升级为治理后候选池摘要
- `FACTORY_RESEARCH_FACTORS` 退化为 seed set / fallback set
- `spawner` 能按 candidate family、regime、validation score 组织策略候选
- `strategy_factory` 能识别新 family，而不是只映射固定六类因子

本次已完成：

- `factor_research` 输出 active candidates、family summary、regime summary、factor_source_mode
- `opportunity` 已按 governed family / regime / top candidate 生成任务，而不是只按固定因子名派生任务
- `scheduler` 已把 governed pool 摘要写入 stage summary / run summary
- governed pool 激活时，legacy factor freshness 只产生 warning，不再直接把工厂误判为不可继续
- `submitter` / `quality_reporting` 已补齐 `candidate_provenance`、`source_candidate_artifact_id`、`candidate_family`、`expected_regime` 的提交链路留痕
- generated strategy 的 `params`、quality report、generation experiment 已可持续保留 candidate 级 provenance

验收标准：

- 策略工厂的候选策略能够消费 LLM 新生成并通过治理的因子
- 固定因子集合不再是唯一输入来源

### 14.5 风险控制清单

上线前必须确认：

- 模型输出 schema 已冻结并校验
- DSL 白名单已覆盖必要算子
- PIT 数据查询已验证无未来函数泄漏
- 相似度去重阈值已配置
- 回退模式可用
- 日志与审计字段可回放

## 15. 代码改造清单

本节给出建议的代码改造范围，按“新增文件”和“修改文件”拆分。

### 15.1 建议新增文件

- `packages/akshare-mcp/src/akshare_mcp/services/factor_llm_provider.py`
  作用：因子研究专用大模型调用层，复用 `strategy_llm_provider.py` 的调用模式，但使用独立配置前缀 `FACTOR_LLM_`

- `packages/akshare-mcp/src/akshare_mcp/services/factor_prompt_builder.py`
  作用：把行情、财务、事件、文本、资金流、历史记忆压缩成模型输入 prompt

- `packages/akshare-mcp/src/akshare_mcp/services/factor_candidate_compiler.py`
  作用：将 `expression_dsl` 编译成受控表达式或内部 AST，并执行安全检查

- `packages/akshare-mcp/src/akshare_mcp/services/factor_validation_pipeline.py`
  作用：统一跑 IC、OOS、稳健性、相似度、容量与成本验证

- `packages/akshare-mcp/src/akshare_mcp/services/factor_research_memory.py`
  作用：管理候选因子记忆、失败记忆、相似度召回与 prompt 反馈

- `packages/akshare-mcp/src/akshare_mcp/services/factor_candidate_storage.py`
  作用：落库存储候选因子、验证摘要、embedding metadata、episode 记录

- `packages/akshare-mcp/src/akshare_mcp/schemas/factor_candidate.schema.json`
  作用：约束模型返回结构，避免自由文本污染主链

### 15.2 建议修改文件

- `packages/akshare-mcp/src/akshare_mcp/services/llm_alpha.py`
  调整建议：
  - 重新命名或标注为 fallback
  - 不再作为主引擎
  - 保留本地候选池逻辑作为 provider 异常时的 seed/fallback

- `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`
  调整建议：
  - 新增 `llm_factor_mining`
  - 新增 `validate_factor_candidate`
  - 新增 `factor_candidate_registry`
  - 新增 `replay_factor_episode`
  - 将 `automl_discovery` 重新定位为“验证辅助手段”

- `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_mgr_helpers.py`
  调整建议：
  - 保留另类数据聚合逻辑
  - 将其升级为上下文构建器输入，而不是固定权重主输出
  - 输出更适合 prompt 使用的结构化摘要

- `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_mgr_automl.py`
  调整建议：
  - 保留特征筛选和验证价值
  - 不再把它视为“因子发现主引擎”
  - 支持对 LLM 候选因子做辅助排序和筛选

- `packages/strategy-factory/src/strategy_factory/application/factor_research.py`
  调整建议：
  - 输入从固定因子摘要升级为治理后候选池摘要
  - 输出 active candidates、family summary、regime summary、degraded reasons

- `packages/strategy-factory/src/strategy_factory/domain/constants.py`
  调整建议：
  - 将 `FACTORY_RESEARCH_FACTORS` 从唯一主链输入改成 seed / fallback 集合
  - 新增 candidate family 与 strategy type 的映射机制

- `packages/strategy-factory/src/strategy_factory/domain/spawner.py`
  调整建议：
  - 允许消费 LLM 新 family
  - 允许按 regime、holding_period、validation score 组织候选策略

### 15.3 推荐开发顺序

建议按下面顺序开发，避免返工：

1. `factor_llm_provider.py`
2. `factor_prompt_builder.py`
3. `factor_candidate.schema.json`
4. `quant_manager.py` 新增 `llm_factor_mining`
5. `factor_candidate_compiler.py`
6. `factor_validation_pipeline.py`
7. `factor_candidate_storage.py`
8. `factor_research_memory.py`
9. `factor_research.py`
10. `spawner.py` 与 `constants.py`

### 15.4 最小可用版本范围

如果要先落一个 MVP，建议只做下面这些：

- `FactorLLMProvider`
- `llm_factor_mining`
- JSON schema 校验
- 简版 DSL 编译
- IC + OOS + Similarity 三项治理
- artifact 持久化
- fallback 回退

先不要一次性做完：

- 多角色 agent
- 自动 prompt 优化
- factor-model co-optimization
- 多轮 evolutionary search

这样能更快拿到第一版真实可跑的 LLM 因子挖掘闭环。

## 16. 环境变量与配置样例

本节给出建议的环境变量清单和样例，方便后续直接落库到 `.env` 或部署配置中。

### 16.1 因子挖掘专用 LLM 配置

```bash
# 启用因子研究大模型
FACTOR_LLM_ENABLED=1

# 统一协议层，建议固定 openai_compatible
FACTOR_LLM_PROVIDER=openai_compatible

# 兼容 OpenAI / vLLM / TGI / Ollama 的服务地址
FACTOR_LLM_BASE_URL=http://127.0.0.1:8000/v1
FACTOR_LLM_API_KEY=your_api_key
FACTOR_LLM_MODEL=qwen2.5-72b-instruct

# 调用参数
FACTOR_LLM_TIMEOUT_SEC=45
FACTOR_LLM_CONNECT_TIMEOUT_SEC=8
FACTOR_LLM_WRITE_TIMEOUT_SEC=10
FACTOR_LLM_POOL_TIMEOUT_SEC=5
FACTOR_LLM_TEMPERATURE=0.2
FACTOR_LLM_MAX_TOKENS=1800
FACTOR_LLM_RETRY_COUNT=2
FACTOR_LLM_RETRY_BACKOFF_SEC=1.0
FACTOR_LLM_MAX_CONCURRENCY=3
FACTOR_LLM_STRICT_MODE=1
```

### 16.2 embedding 配置

```bash
FACTOR_EMBEDDING_ENABLED=1
FACTOR_EMBEDDING_PROVIDER=openai_compatible
FACTOR_EMBEDDING_BASE_URL=http://127.0.0.1:8000/v1
FACTOR_EMBEDDING_API_KEY=your_api_key
FACTOR_EMBEDDING_MODEL=text-embedding-3-small
FACTOR_EMBEDDING_TIMEOUT_SEC=20
FACTOR_EMBEDDING_MAX_TEXT_CHARS=6000
```

### 16.3 不同后端的推荐配置样例

外部云端 API：

```bash
FACTOR_LLM_BASE_URL=https://api.example.com/v1
FACTOR_LLM_MODEL=gpt-4.1
FACTOR_EMBEDDING_BASE_URL=https://api.example.com/v1
FACTOR_EMBEDDING_MODEL=text-embedding-3-small
```

自建 vLLM / TGI：

```bash
FACTOR_LLM_BASE_URL=http://llm-gateway.internal:8000/v1
FACTOR_LLM_MODEL=qwen2.5-72b-instruct
FACTOR_EMBEDDING_BASE_URL=http://embedding-gateway.internal:8000/v1
FACTOR_EMBEDDING_MODEL=bge-m3
```

本地 Ollama：

```bash
FACTOR_LLM_BASE_URL=http://127.0.0.1:11434/v1
FACTOR_LLM_MODEL=qwen2.5:72b
FACTOR_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
FACTOR_EMBEDDING_MODEL=nomic-embed-text
FACTOR_LLM_API_KEY=ollama
FACTOR_EMBEDDING_API_KEY=ollama
```

### 16.4 建议增加的运行开关

```bash
# 当 provider 不可用时是否回退本地规则
FACTOR_LLM_ALLOW_FALLBACK=1

# 一次生成多少个候选因子
FACTOR_LLM_CANDIDATE_COUNT=8

# 单个候选最大复杂度
FACTOR_DSL_MAX_COMPLEXITY=12

# 相似度阈值，高于该阈值视为重复
FACTOR_SIMILARITY_THRESHOLD=0.92

# 候选因子进入策略工厂前的最低验证分
FACTOR_PROMOTION_MIN_SCORE=0.60

# 单次研究 episode 最大轮数
FACTOR_RESEARCH_MAX_ROUNDS=3
```

### 16.5 配置设计原则

配置设计应遵循以下原则：

- 因子研究与策略生成分开配置
- LLM 与 embedding 分开配置
- provider 与 model 分开配置
- 研究主链与 fallback 主链分别可控
- 所有关键阈值必须可通过环境变量调整

如果后续代码实现严格遵守本节配置设计，那么无论底层接外部 API、vLLM、TGI 还是 Ollama，都不会改变上层因子挖掘主链。
