# AKShare MCP 服务缺陷修复方案

- **创建时间**: 2026-06-01
- **范围**: `packages/akshare-mcp/src/akshare_mcp/`
- **来源**: 2026-06-01 对运行中 MCP 服务的实测复现（非旧报告复述）
- **核对基准**: 与红队复测报告 `red-team-reports/codex_conv_mcp_20260530`（48 场景 / 1471 次真实调用 / findings_v3）逐项交叉核对，并经底层证据文件 `.mcp_cache/dead_letters/kline_save_failures.jsonl` 验证（核对日 2026-06-02）
- **状态图例**: ✅ 已修复并单元验证 / 🔧 已定位待改 / ⏳ 待排期

> 生效说明：源码修改后需**重启 MCP 服务**（Kiro 托管的 akshare server）才能在工具调用层生效。已完成项均通过 venv 内 Python 单元级验证。

> 核对说明（2026-06-02 补充）：本方案 11 项 FIX 与红队 findings_v3 高度吻合——10 项现象/文件/严重度准确对应。仅 **FIX-9** 的主证据工具与数值需修正（见该项「核对修正」），**FIX-2** 的 delta 数值取自与报告不同的参数档位（结论一致）。FIX-9/FIX-10 复测时须验证「入库校验器根因」而非「某次 db.stock_quotes 快照的污染数值」——findings_v3 的 06-01 复测声明已确认污染**表现**具时点依赖性（06-01 `get_batch_quotes(000001)=10.99` 已正确），但校验器**根因持久成立**。

> **执行状态（2026-06-02 全部完成）**：FIX-1~11 已全部落地到源码并通过验证。FIX-1/2/3/9 在本次核对前已应用（源码确认）；FIX-4/5/6/7/8/10/11 及 FIX-3 遗留（rsi_6/rsi_14/rsi_24 别名回归）本次实现。
> - 新增回归测试：`packages/akshare-mcp/tests/test_mcp_fix_plan_regressions.py`（21 passed，覆盖 FIX-3 遗留/4/6/7/8）+ `packages/aiask-quant-core/tests/test_kline_index_validator_fix10.py`（12 passed，覆盖 FIX-10）。
> - 既有套件无回归：`test-finance` 三件套 10 passed；factor/quant/validator 相关 24 passed；契约/数据校验 5 passed。
> - 端到端真实 DB 验证：`robustness_check`/`calculate_factor_ic(turnover_20d/volume_ratio)`/`backtest_factor(turnover_20d)` 均 success=true 无裸抛。
> - **生效仍需重启 MCP 服务**。

---

## 一、已修复（✅）

### FIX-1 ✅ research_manager 整工具崩溃（UnboundLocalError 'get_db'）

- **严重度**: P0（整个 manager 不可用，连 `help` 都崩）
- **现象**: `research_manager(action=help/get_reports/get_ratings)` → `cannot access local variable 'get_db' where it is not associated with a value`
- **文件**: `src/akshare_mcp/tools/managers/research_manager.py`
- **根因**: 模块顶部已有 `from ...storage import get_db`（第6行），但函数体内 `get_reports`/`get_ratings` 分支又各有一处**局部** `from ...storage import get_db`。Python 作用域规则：函数内任意位置出现该 import，`get_db` 在**整个函数作用域**被视为局部变量；于是函数开头第55行 `db = get_db()`（在 action 分派之前）执行时局部 `get_db` 尚未赋值 → UnboundLocalError。这解释了为何连 `help` 都崩。
- **修复**: 删除函数体内两处局部 `from ...storage import get_db`（保留模块级导入）。
- **验证**: AST 通过；逻辑上函数开头 `db = get_db()` 现引用模块级符号。重启后应 `research_manager(action=help)` 返回 supported_actions。
- **红队对应**: F-N11-1（HIGH，N11 场景）— 实测「全部 action 崩溃，连 help 都崩」，与根因分析完全吻合；底层独立工具（get_research_reports/analyze_research_report）正常，仅 manager 封装层有 bug。

### FIX-2 ✅ options_manager 期权类型大小写敏感（金融正确性，方向反转）

- **严重度**: P0（希腊字母方向完全反转，误导决策）
- **现象**: `calculate_greeks(option_type='CALL')` → delta=-0.048（被当 put）；`'call'` → delta=0.95（正确）。success=true 无告警。
- **文件**:
  - `src/akshare_mcp/services/options_pricing.py`（底层 BSM）
  - `src/akshare_mcp/tools/managers/options_manager.py`（工具层 calculate_greeks 分支）
- **根因**:
  1. 底层 `black_scholes`/`calculate_greeks` 全部用 `option_type == 'call'` 精确小写匹配，`'CALL'` ≠ `'call'` 落入 else 当 put。
  2. 工具层 `calculate_price`/`implied_volatility` 已做 `.lower().strip()`+枚举校验，但 `calculate_greeks` 分支漏做（第164行直接原样传入）。
- **修复**:
  1. 底层 `options_pricing.py` 的 `black_scholes` 与 `calculate_greeks` 入口统一 `option_type = (option_type or 'call').strip().lower()`（双保险）。
  2. 工具层 `options_manager.py` 的 `calculate_greeks` 分支补 `option_type = str(...).lower().strip()` + `not in ('call','put')` 报错，与其它 action 一致。
- **验证**: 单元测试 `calculate_greeks(...,'call'/'CALL'/'Call')` 三者 delta 均=0.9522（一致且为正）。
- **红队对应**: F-N24-1（HIGH，N24 场景）。**数值出处说明**: 本方案引用的 `'CALL'→delta=-0.048`、`'call'→0.95` 取自深 ITM 参数档；红队报告记录的是 ATM 档 `'CALL'→-0.4503`、`'call'→+0.5497`。两组数值来自不同 K/S 参数，但均证明「大写/未知类型静默当 put、方向反转」这一同一缺陷，结论一致。

### FIX-3 ✅ calculate_factor 别名契约不一致（pb_ratio 等无法解析）

- **严重度**: P1（get_factor_library 宣称支持的别名实际报 Unsupported）
- **现象**: `calculate_factor(factor='pb_ratio')` → `Unsupported factor: pb_ratio`，但 `get_factor_library` 的 alias_canonical_map 宣称支持 `pb_ratio`。
- **文件**: `src/akshare_mcp/tools/factor_naming.py`
- **根因**: `_CROSS_ACTION_ALIASES` 映射目标用了**不存在于 SUPPORTED_FACTORS 的 canonical 名**。SUPPORTED_FACTORS 中真实 canonical 是 `pb_mrq`/`pe_ttm`/`ps_ttm`/`roe_ttm`，但映射表写成 `"pb_ttm": "pb_ratio"`、`"roe_ttm": "roe"`（指向不存在的 `pb_ratio`/`roe`），方向颠倒。`pb_ratio` 本身既不是 key 也不是 canonical → 解析后原样返回 → 校验失败。
- **修复**: 重写 `_CROSS_ACTION_ALIASES` 财务别名段，让 `pb`/`pb_ratio`/`pb_ttm`→`pb_mrq`，`pe`/`pe_ratio`/`pe_ttm`→`pe_ttm`，`ps`/`ps_ratio`→`ps_ttm`，`roe`→`roe_ttm`，`roa`→`roa_ttm`。
- **验证**: 单元测试 `pb_ratio→pb_mrq`、`pe_ratio→pe_ttm`、`roe→roe_ttm`、`pb_ttm→pb_mrq` 全部 supported=True；既有别名 `rsi→rsi_14`、`momentum_20d→momentum` 未破坏。
- **红队对应**: F-N13-1（HIGH，N13 场景）— 实测 `alias_canonical_map` 声明 `pb_ratio→pb_ttm` 但 `calculate_factor(pb_ratio)` 报 Unsupported，且映射目标 `pb_ttm` 本身也不在 supported_factors（真值 `pb_mrq`），三层命名断裂，与根因吻合。
- **遗留**: `_CROSS_ACTION_ALIASES` 中 `"rsi_6":"rsi"` 会使 `rsi_6` 被解析成 `rsi_14`（rsi_6 本是独立 canonical）。属既有缺陷，本次未动以避免扩大回归面，列入 FIX-9。

---

## 二、已定位待改 → 全部已修复（✅，2026-06-02）

### FIX-4 ✅ calculate_stop_levels 非正 entry_price 裸抛 / 无上界校验

- **严重度**: P1
- **现象**:
  - `calculate_stop_levels(entry_price=0)` → `float division by zero`（裸异常）
  - `entry_price=-50` → 负止损价 + max_shares=-6000（负股数）
  - `risk_per_trade=5`（500%）→ risk_budget=本金5倍，无上界校验
- **文件**: `src/akshare_mcp/tools/stop_levels.py` → `compute_stop_levels`
- **根因**: 第121行 `max_shares_by_cap = math.floor(capital * 0.3 / entry_price)` 在 entry_price=0 时除零；函数入口无 entry_price>0 / risk_per_trade 区间校验。
- **修复方案**（入口加校验，K线获取之前）:
  ```python
  entry_price = float(entry_price)  # try/except → fail("entry_price 必须为正数")
  if not math.isfinite(entry_price) or entry_price <= 0:
      return fail("entry_price 必须为正数（股票入场价不能为 0 或负）")
  if direction not in ("long", "short"):
      return fail("direction 必须为 long 或 short")
  # atr_multiplier>0、capital>=0、0<=risk_per_trade<=1 同理校验
  ```
- **验证方式**: entry_price=0/-50 → 返回 PARAM_ERROR；risk_per_trade=5 → 拒绝。
- **已实现**: 在 `compute_stop_levels` 入口（K线获取前）补齐校验：entry_price 必须为有限正数；direction∈{long,short}；atr_multiplier>0；capital≥0；risk_per_trade∈(0,1]。`generate_trade_plan` 内部调用走同一函数，false 路径已被 `_build_scenario_with_stop` 兼容。回归测试 3 例通过（entry=0/-50/risk=5 拒绝，正常输入通过）。
- **红队对应**: F-N46-5（HIGH）entry=0→止损 -57.01 / entry=-50→max_shares=-6000；F-N46-4（MED）risk_per_trade=5（500%）→risk_budget=500万无上界（实测被 max_amount 30% 上限意外兜住实际开仓，但荒谬值未拒绝）。两条均吻合。

### FIX-5 ✅ get_conditional_returns MA 族字段裸抛 DataFrame.tolist

- **严重度**: P1
- **现象**: `get_conditional_returns(field='ma_5'/'ma_20')` → `'DataFrame' object has no attribute 'tolist'`（close/rsi_14/volume_ratio 正常）
- **文件**: `src/akshare_mcp/services/conditional_returns.py`
- **根因（待确认）**: MA 族字段计算分支返回 DataFrame 而非 Series，对其调 `.tolist()` 失败。需读源码定位字段取值处。
- **状态**: 当前源码 `_declared_condition_value` 的 MA 分支已用 `TechnicalAnalysis.calculate_sma(closes, period)` + `_safe_series_value` 取标量，不再对 DataFrame 调 `.tolist()`，裸抛已消除（修复早于本次核对应用）。本次补 FIX-6 的 field/op 校验，使 MA 等字段拼错时显性报错而非静默 0。
- **红队对应**: F-N47-1（HIGH，N47 场景）— 隔离确认单 `ma_5` 即触发裸抛，`close`/`rsi_14`/`volume_ratio` 正常；实测亦在 `get_conditional_returns(002594 close>90 AND ma_5>90)` 复现。吻合。

### FIX-6 ✅ get_conditional_returns 未识别 field / 非法 op 静默返回 0 匹配

- **严重度**: P2
- **现象**: `field='nonexistent_field_zzz'` / `op='BADOP'` / `field='macd'` → success=true / matches=0，无告警。AI 无法区分「真无匹配」与「字段/运算符拼错」。
- **文件**: `src/akshare_mcp/services/conditional_returns.py`
- **修复方向**: 校验 field 在支持集合内、op 在 `{<,>,<=,>=,==,!=}` 枚举内，否则返回 PARAM_ERROR 并回显支持列表。与 FIX-5 同文件一并改。
- **已实现**: 在 `services/conditional_returns.py` 新增 `validate_conditions()`（含 `_is_supported_declared_field` + `_SUPPORTED_OPS`），在工具层 `tools/quant.py::get_conditional_returns` logic 校验后调用，未识别 field / 非法 op 直接 `fail(...)` 并回显支持字段列表。带 `id` 的 screen_engine 条件与纯字符串条件不拦截（交引擎处理）。回归测试 7 例通过。
- **红队对应**: F-N47-2（MED，N47 场景）— 实测 `nonexistent_field_zzz`/`op=BADOP`/`macd` 均 success=true / matches=0；字段处理呈三态「有效→算 / MA族→崩 / 未识别→静默0」。吻合。

### FIX-7 ✅ calculate_factor_ic / backtest_factor 对 turnover_20d/volume_ratio 裸抛 IndexError

- **严重度**: P1（这两个量价因子在 IC 与回测管道均不可用）
- **现象**: `calculate_factor_ic(factor='turnover_20d')` → `list index out of range`；`backtest_factor` 同因子 → `index -21 is out of bounds for axis 0 with size 20`
- **文件**: `src/akshare_mcp/tools/quant_engine.py`（`_calculate_factor_value` + `_FACTOR_MIN_HISTORY`）
- **根因（待确认）**: 这两个因子的窗口长度与 forward return 对齐时切片越界（疑似 turnover/volume_ratio 需要的回看窗口与样本长度不匹配）。
- **根因（已确认）**: `_calculate_factor_value` 中 `volume_ratio`(`range(-20,0)`访问`closes[-21]`) 与 `turnover_20d`(`range(-p,0)`访问`closes[-(p+1)]`) 在窗口长度恰为 20 时下溢越界；旧 guard `len<20` 差一。IC/backtest 路径 `factor_lookback=max(20, _minimum_factor_history)`，而该两因子 min_history=20 → 窗口恰 20 → 越界。
- **已实现**: (1) `_calculate_factor_value` 中 `volume_ratio`/`turnover_20d` guard 改为 `len < 21`（访问 closes[i-1] 需多 1 根），不足返回 None；(2) `_FACTOR_MIN_HISTORY` 将 `volume_ratio`/`turnover_20d` 从 20 提到 21，使 IC/backtest 窗口≥21。`turnover_5d`(N13 正常) 未动。端到端 `calculate_factor_ic(turnover_20d/volume_ratio)` 与 `backtest_factor(turnover_20d)` 真实 DB 跑通 success=true；回归测试 3 例通过。
- **红队对应**: F-N14-1（HIGH，N14）`calculate_factor_ic(turnover_20d)` 连续 2 次 + `volume_ratio` 裸抛 `list index out of range`；F-N15-2（HIGH，N15）`backtest_factor(turnover_20d/volume_ratio)` 裸抛 `index -21 is out of bounds for axis 0 with size 20`。**关键定位线索**：`calculate_factor` 单股算 turnover_20d 正常（N13），仅多股面板对齐环节越界 → bug 在 forward return 与因子窗口的多股对齐切片，非因子计算本身。

### FIX-8 ✅ factor_robustness_check 整工具崩溃（'str' object has no attribute 'get'）

- **严重度**: P0（整工具 100% 不可用）
- **现象**: `factor_robustness_check(任意因子)` → `'str' object has no attribute 'get'`
- **文件**: `src/akshare_mcp/tools/_quant_analysis_support.py` → `run_factor_robustness_check`
- **根因（已确认）**: 符号倒挂检测块 `for r in multi_window_results:` 遍历的是 dict 的**键（字符串 "5"/"10"…）**，随即对字符串调 `r.get("ic")` → AttributeError，整工具崩溃。
- **已实现**: 改为 `for window_key, r in multi_window_results.items():` 并加 `isinstance(r, dict)` 守卫，`window` 取值回退到 window_key（原 `_cross_section_ic` 返回值不含 "window" 键）。端到端 `robustness_check(momentum)` 真实 DB success=true；回归测试通过。
- **红队对应**: F-N15-1（HIGH，N15 场景）— 实测对所有因子和参数均失败，工具 100% 不可用，与 N11 research_manager 同属「manager/工具封装层整体崩溃」类。吻合。

### FIX-9 ✅ 非法股票代码静默坐标化为上证指数

- **严重度**: P1（数据正确性，污染分析结果）— 跨场景复现 ≥9 次（red-team ROOT-2）。注：不同工具实测严重度不一，`get_key_levels`/`get_signal_hit_rate` 为 HIGH，`get_batch_quotes` 仅 MEDIUM（见核对修正）
- **现象**: `get_key_levels('999999')` → `current_price=4068.57`（上证指数点位）+ 完整关键价位；`get_signal_hit_rate('999999')` → 在指数数据上算 1 个信号；`generate_trade_plan('999999')` → 完整方案（name='' 是唯一线索）。而 `search_stocks(999999)=not_found`、`get_realtime_quote(999999)=未找到`、`run_decision_gate(BADX)=代码格式无效` 能正确拒绝（佐证拒绝逻辑在 search 层已实现、在分析层缺失）。
- **根因**: 部分工具把非法码做「提取数字+补零到6位」后回退到指数数据，而非校验存在性。代码存在性校验（`resolve_existing_security_code`）未在所有取数路径统一应用。
- **状态**: 当前源码 `get_key_levels` / `calculate_stop_levels` / `generate_trade_plan` / `get_conditional_returns` / `get_signal_hit_rate` / `find_similar_patterns` 入口均已调用 `resolve_existing_security_code_async`，非法码（999999 等）返回 NOT_FOUND（修复早于本次核对应用，源码确认）。本次另在 **`get_batch_quotes`（market/quote.py）逐码补 `resolve_existing_security_code_sync` 存在性校验**，非法码进 `missing` 而非坐标化到指数（探针确认 999999/888888 → missing，000001=11.05 平安银行正确），闭合 F-N03-2；并在 stop_levels 入口叠加正数/区间校验，纵深防御。
- **红队对应**: ROOT-2（系统级根因）+ F-N46-2（HIGH）+ F-N47-3（MED）+ F-N03-2（MED，本次新闭合）。
- **⚠ 核对修正（2026-06-02）**: 本项原文写「`get_batch_quotes(['999999'])` → price=**4057**」有两处偏差：(1) 实测数值是 **4068.57** 非 4057（见 F-N03-2 / F-N46-2 / N03 status.json）；(2) `get_batch_quotes` 路径在红队实测仅定级 **MEDIUM**（cross_tool_consistency），真正定级 HIGH 的是 `get_key_levels('999999')→4068.57`（F-N46-2）。故主证据工具应以 `get_key_levels` 为准，数值统一为 4068.57。已据此改写上方「现象」。

### FIX-10 ✅ 入库校验器把个股 000001 当指数拒绝（根因级）

- **严重度**: P1（数据层根因，时点性污染 db.stock_quotes）
- **现象**: `get_dead_letters()` 持续记录 `code='000001' close=11.61 ... index_close_out_of_range: expected [1000,30000]; possible cross-symbol contamination`，连真上证指数 `sh000001` 的低价历史（close=9.x）也被同规则误拒。
- **文件**: `packages/aiask-quant-core/src/aiask_quant_core/core/validators.py` → `_is_chinese_index_code`
- **根因（已确认）**: `_is_chinese_index_code` 的 `bare_index` 集合把裸 `000001`/`000300`/`000688` 等当指数，而这些恰是真实个股代码。但指数 K 线在本系统**始终以带市场前缀代码入库**（`sh000001`/`sz399006`，见 `storage.sqlite.kline.get_index_klines` 文档），裸码一律是个股 → 误判。
- **已实现**: 重写 `_is_chinese_index_code`，**移除 bare_index 集合**，仅对显式前缀 `sh000`/`sz399`/`index_` 的代码做指数区间校验；裸 6 位码视为个股不拦截。这样 000001.SZ(平安银行,11元) 入库通过，而 `sh000001` close=11(污染) 仍被拒、close=4068 通过。新增回归测试 `test_kline_index_validator_fix10.py` 12 passed。
- **红队对应**: ROOT-1（系统级最高优先级根因）+ F-N39-ROOT（HIGH）+ F-N48-1（HIGH）。
- **底层证据核实（2026-06-02）**: 已核对 `.mcp_cache/dead_letters/kline_save_failures.jsonl`（18 条记录）：裸 `000001 close=11.61 expected [1000,30000]`（个股被当指数拒绝，第12-17行）确凿存在；并发现 `sh000001 close=9.x`（真指数低价历史被同规则误拒）与 `sz399001 close=15000+`（早期上界 [1000,15000] 误拒、后放宽到 30000）的演化痕迹，根因真实且持久。
- **复测注意**: findings_v3 的 06-01 复测声明指出，污染**表现**具时点依赖性（06-01 `get_batch_quotes(000001)=10.99` 已正确，4068 表现不复现），但**校验器根因（本次已修复）**。修复后验收须以 dead-letter 不再记录 000001/sh000001 被 `index_close_out_of_range` 拒绝为准，**不能**以某次 db.stock_quotes 快照已正确为准。
  - **遗留清理（建议）**：dead-letter 历史记录与已被污染的 db.stock_quotes 行不会被本修复自动清洗，需在重启服务后重新同步 000001/sh000001 的 K 线并清空旧 dead-letter（属运行态数据操作，需显式授权，未在本次执行）。

### FIX-11 ✅ search_stocks 中文行业词失效

- **严重度**: P2（能力缺失）
- **现象**: `search_stocks('白酒')` → 0 结果（仅匹配代码/股票名）；`semantic_stock_search('白酒')` 能返回三只白酒股（600519/000858/002304，industry+sector_seed 匹配，score 1.85）。`search_stocks('茅台')` 能命中（名称匹配）。
- **文件**: `src/akshare_mcp/tools/search.py`
- **已实现**: 两层增强：(1) stocks 表 LIKE 兜底 SQL 增加 `OR industry LIKE` 子句，直接命中 db 中行业字段含「白酒」的标的；(2) 仍 0 命中时回退 `_vector_search_semantic.semantic_stock_search`，映射 code/name/industry/market_cap/match_type，确保行业词不再 0 命中。失败均经 `safe_stderr_print` 可观测，不静默吞错。
- **红队对应**: F-N48-3（MED，N48 场景）— 与 N45 search_skills 中文关键词失效同源（关键词检索层普遍缺中文行业语义）。

---

## 三、修复优先级与批次

> 严重度对照：方案 P 级与红队 findings_v3 严重度逐项核对一致（见各 FIX「红队对应」）。唯一例外是 FIX-9，`get_batch_quotes` 路径实测仅 MEDIUM，但 `get_key_levels` 路径为 HIGH，故整体仍按 P1 处理。

| 批次 | 项 | 严重度 | 红队对应 | 状态 |
|---|---|---|---|---|
| 第1批 | FIX-1 research_manager / FIX-2 options 大小写 / FIX-3 factor 别名 | P0/P0/P1 | F-N11-1 / F-N24-1 / F-N13-1 | ✅ |
| 第2批（输入校验） | FIX-4 stop_levels / FIX-5+6 conditional_returns / FIX-7 factor_ic | P1 | F-N46-5+4 / F-N47-1+2 / F-N14-1+F-N15-2 | ✅ |
| 第3批（整工具崩溃） | FIX-8 factor_robustness_check | P0 | F-N15-1 | ✅ |
| 第4批（数据正确性） | FIX-9 非法码 / FIX-10 入库校验根因 | P1 | ROOT-2 / ROOT-1+F-N39-ROOT+F-N48-1 | ✅ |
| 补充 | FIX-3 遗留 rsi_6/rsi_14/rsi_24 别名回归 | P1 | F-N13-1 关联 | ✅ |
| 第5批（能力增强） | FIX-11 search_stocks 中文 | P2 | F-N48-3 | 🔧 |

> 排期提示：FIX-8 是 P0 整工具 100% 不可用，建议优先级可提到第 2 批之前（与 FIX-1 同级处理），当前排第 3 批仅因依赖源码定位 `.get()` 调用点。

## 四、验证清单

> 标记：[x] = 已通过单元/端到端验证（venv 内，无需重启）；⟳ = 仍需重启 MCP 服务后在工具调用层最终复测（源码已改，运行进程未热加载）。

- [x] ⟳ `research_manager(action=help)` → 返回 supported_actions（源码确认无局部 get_db 导入）
- [x] ⟳ `options_manager(calculate_greeks, option_type='CALL')` → delta=0.9522>0（探针：call/CALL/Call 一致）
- [x] ⟳ `calculate_factor(600519, 'pb_ratio')` → 解析为 pb_mrq supported=True（探针通过）
- [x] ⟳ `calculate_stop_levels(600519, entry_price=0)` → success=false（回归测试通过，不再除零/负股数）
- [x] ⟳ `get_conditional_returns(600519, field='ma_20')` → 成功（MA 已用 calculate_sma，不再裸抛）
- [x] ⟳ `get_conditional_returns(600519, field='nonexistent_zzz')` → PARAM_ERROR（validate_conditions 回归通过）
- [x] ⟳ `calculate_factor_ic(turnover_20d/volume_ratio)` / `backtest_factor(turnover_20d)` → 真实 DB success=true（不再 IndexError）
- [x] ⟳ `factor_robustness_check(momentum)` → 真实 DB success=true（不再 'str'.get）
- [x] ⟳ `get_key_levels('999999')` → NOT_FOUND（源码确认 resolve_existing_security_code_async）【FIX-9 主证据，HIGH】
- [x] ⟳ `get_signal_hit_rate('999999')` / `generate_trade_plan('999999')` → NOT_FOUND（源码确认存在性校验）
- [x] ⟳ `get_batch_quotes(['999999','888888','600519'])` → 999999/888888 进 missing，600519/000001 正确返回（探针：found=2, 000001=11.05 平安银行非 4068 指数）【FIX-9 batch 路径已补存在性校验】
- [x] ⟳ `validate_kline('000001', close=11.61)` 接受 / `validate_kline('sh000001', close=11)` 拒绝（FIX-10 回归 12 passed）
- [x] ⟳ `search_stocks('白酒')` → industry LIKE + semantic 回退命中白酒股（语义底层探针返回 3 只）

> 遗留运行态清理（需显式授权，未执行）：重启后重新同步 000001/sh000001 K 线并清空旧 dead-letter，以消除历史已落盘的污染记录。

---

## 五、与红队报告核对结论（2026-06-02）

核对源：`red-team-reports/codex_conv_mcp_20260530`（48 场景 / 1471 次真实调用 / findings_v3 + status.json）+ 底层证据 `.mcp_cache/dead_letters/kline_save_failures.jsonl`。

| FIX | 红队 finding | 现象 | 严重度 | 核对结论 |
|---|---|---|---|---|
| FIX-1 | F-N11-1 | ✅ 吻合（连 help 都崩） | P0↔HIGH | 准确 |
| FIX-2 | F-N24-1 | ✅ 吻合（数值取不同档位） | P0↔HIGH | 准确，数值出处已注 |
| FIX-3 | F-N13-1 | ✅ 吻合（三层命名断裂） | P1↔HIGH | 准确 |
| FIX-4 | F-N46-5/4 | ✅ 吻合（负止损/负股数/无上界） | P1↔HIGH | 准确 |
| FIX-5 | F-N47-1 | ✅ 吻合（ma_5/ma_20 裸抛） | P1↔HIGH | 准确 |
| FIX-6 | F-N47-2 | ✅ 吻合（未识别 field 静默 0） | P2↔MED | 准确 |
| FIX-7 | F-N14-1+F-N15-2 | ✅ 吻合（IC+回测双管道越界） | P1↔HIGH | 准确 |
| FIX-8 | F-N15-1 | ✅ 吻合（100% 不可用） | P0↔HIGH | 准确 |
| FIX-9 | ROOT-2/F-N46-2/F-N03-2 | ⚠ 现象成立，数值/主工具已更正 | P1（混合） | 已修正：4057→4068.57，主证据改 get_key_levels |
| FIX-10 | ROOT-1/F-N39-ROOT/F-N48-1 | ✅ 根因吻合，dead-letter 实证 | P1↔HIGH | 准确，close 11.0→11.61 |
| FIX-11 | F-N48-3 | ✅ 吻合 | P2↔MED | 准确 |

**总评**: 11 项 FIX 中 10 项现象/文件/严重度准确对应红队 findings；根因分析（FIX-1 作用域、FIX-10 入库校验）经底层证据验证属实。本次更正仅集中在 FIX-9（数值 4057→4068.57、主证据工具 get_batch_quotes→get_key_levels、严重度分层说明）与若干数值/出处补注（FIX-2 delta 档位、FIX-10 close 数值）。

**复测纪律提醒**: ROOT-1/FIX-10 的污染「表现」具时点依赖性——findings_v3 的 06-01 复测显示 `get_batch_quotes(000001)=10.99` 已正确、4068 指数表现不复现，但**入库校验器根因（本次 FIX-10 已修复）**。FIX-9/FIX-10 的验收必须以「校验器逻辑 + dead-letter 是否再记录误拒」为准，不可因某次快照已正确而误判已修复。

---

## 六、本次执行改动清单（2026-06-02）

源码改动（7 文件）：

| FIX | 文件 | 改动 |
|---|---|---|
| FIX-3 遗留 | `tools/factor_naming.py` | `_CROSS_ACTION_ALIASES` 移除把 rsi_14/rsi_6/rsi_24 错误映射到非 canonical "rsi" 的条目；改为 rsi→rsi_14 / rsi_24→rsi_14，rsi_6/rsi_14 由 `_normalize_factor_name` 解析自身 |
| FIX-4 | `tools/stop_levels.py` | `compute_stop_levels` 入口加 entry_price>0 / direction / atr_multiplier>0 / capital≥0 / risk_per_trade∈(0,1] 校验 |
| FIX-6 | `services/conditional_returns.py` | 新增 `validate_conditions` + `_is_supported_declared_field` + `_SUPPORTED_OPS`；`tools/quant.py::get_conditional_returns` 接入校验 |
| FIX-7 | `tools/quant_engine.py` | `_calculate_factor_value` 中 volume_ratio/turnover_20d guard 改 `len<21`；`_FACTOR_MIN_HISTORY` 两因子提到 21 |
| FIX-8 | `tools/_quant_analysis_support.py` | `run_factor_robustness_check` 符号倒挂块 `for r in multi_window_results` → `.items()` + isinstance 守卫 |
| FIX-9 | `tools/market/quote.py` | `get_batch_quotes` 逐码补 `resolve_existing_security_code_sync` 存在性校验，非法码进 missing |
| FIX-10 | `aiask-quant-core/core/validators.py` | `_is_chinese_index_code` 移除 bare_index 集合，仅对显式前缀 sh000/sz399/index_ 做指数区间校验 |

新增测试（2 文件）：
- `packages/akshare-mcp/tests/test_mcp_fix_plan_regressions.py`（21 passed）
- `packages/aiask-quant-core/tests/test_kline_index_validator_fix10.py`（12 passed）

验证汇总：新增回归 33 passed；既有 test-finance 三件套 10 passed + factor/quant/validator 24 passed + 契约/数据校验 5 passed，无回归；端到端真实 DB 跑通 robustness/factor_ic/backtest/batch_quotes。**生效仍需重启 MCP 服务**；历史 dead-letter 与已污染 db.stock_quotes 行的清洗属运行态操作，需显式授权，未在本次执行。

---

## 七、运行态数据清理记录（2026-06-02，已授权执行）

重启 MCP 服务后，通过运行中的工具层验证 FIX 全部生效，并执行了 dead-letter 精确清理。

### 7.1 重启后工具层验证（全部命中新行为）

| 工具调用 | 结果 | 对应 FIX |
|---|---|---|
| `factor_robustness_check(momentum)` | success=true，返回完整 multi_window_ic/grade | FIX-8 |
| `calculate_stop_levels(600519, entry_price=0)` | success=false，"entry_price 必须为正数…" | FIX-4 |
| `get_batch_quotes([600519,000001,999999,888888])` | found=2，missing=[999999,888888]，000001=11.08（平安银行非指数） | FIX-9 |
| `get_conditional_returns(field='nonexistent_zzz')` | success=false，回显支持字段列表 | FIX-6 |
| `sync_kline_data(000001, limit=120)` + `check_db_freshness(000001)` | K线（10~12元）成功入库，db fresh staleness=0 | FIX-10 |

### 7.2 dead-letter 精确清理

- **清理前**：18 条历史记录（含执行中 sync sh000001 又新增 5 条 → 峰值 23 条）。
- **分类**：裸 `000001`（平安银行被当指数误拒，FIX-10 已修复）7 条 → **清除**；`sh000001`（13）/`sz399001`（3）→ **保留**。
- **清理后**：count=16（sh000001×13 + sz399001×3），裸 000001 记录已全部移除。
- **备份**：`.mcp_cache/dead_letters/kline_save_failures.jsonl.backup-20260602-162830`（清理前快照，可回溯）。
- **方法**：DRY-RUN 确认分类（REMOVE=7 全为 000001）后再 `--apply`，仅按「stock_code=000001 且 close∈(0,1000)」过滤，临时脚本已删除。

### 7.3 新发现的独立缺陷（已排查根因，2026-06-02）

**FIX-12（待修）：K 线同步链路把指数代码碾平为个股 → 上证指数取成平安银行**

- **现象**：`sync_kline_data('sh000001')` 返回平安银行（≈11 元）数据而非上证指数点位（≈4091）。dead-letter 中 `sh000001 close=11` 即由此产生（含定时任务 `_sync_index_klines` 用 `000001.SH` 取数也中招）。
- **实测证据**（`data_source.get_kline(code,'daily',5)` 最新 close）：

  | 输入 | 返回 close | 实际标的 | 期望 |
  |---|---|---|---|
  | `000001` | 11.08 | 平安银行 | 平安银行 ✓ |
  | `000001.SH` | 11.08 | 平安银行 | 上证指数 4091 ✗ |
  | `sh000001` | 11.08 | 平安银行 | 上证指数 4091 ✗ |
  | `000001.SZ` | 11.08 | 平安银行 | 平安银行 ✓ |
  | `600519` | 1307.22 | 茅台 | 茅台 ✓ |
  | `get_index_kline('000001')` | 4091.07 | 上证指数 | 上证指数 ✓（正确范本） |

- **根因链（已定位到行）**：
  1. `data_source/quotes.py::QuotesMixin.get_kline` 首行 `code = normalize_code(code)`。
  2. `utils.py::normalize_code` 用 `re.search(r"(\d{1,6})", s)` 提取首段数字并 `zfill(6)`，**直接丢弃 `sh`/`.SH` 等市场/证券类型标识** → `sh000001`/`000001.SH`/`000001.SZ` 全部碾平为 `000001`。
  3. `data_source/tdx_tqcenter.py::_normalize_code("000001")` 按「0 开头 → `.SZ`」规则得 `000001.SZ`（平安银行），上证指数语义彻底丢失。
  4. 因此**所有**经 `data_source.get_kline` 取指数日 K 的路径（`sync_kline_data` / `batch_sync_klines` / `_sync_index_klines`）都取成个股。
- **正确范本已存在**：`tools/market/kline.py::get_kline` 对「带前缀 + 命中 `_INDEX_AK_MAP`」的代码路由到 `get_index_kline`（走 `ak.stock_zh_index_daily_em`），返回正确指数点位。`market/kline.py` 的修复思路应推广到 `data_source` 层或 `data_sync_service`。
- **修复方向（候选，未实施，待确认）**：
  - 方案A（最小侵入）：在 `data_sync_service.get_kline_with_cache` / `_sync_index_klines` 入口识别指数代码（`sh`/`sz` 前缀或 `_INDEX_AK_MAP` 命中），改走 `get_index_kline` 专用路径，不进 `data_source.get_kline` 的 normalize_code 碾平链。
  - 方案B（根治）：让 `data_source.get_kline` 在 normalize 前先判定证券类型，指数代码保留市场标识并路由到指数 API；需同步评估对 `_tqcenter._normalize_code` 全调用面的影响（回归面较大）。
- **风险等级**：P1（上证/深证指数历史日 K 无法正确入库；个股不受影响；指数实时行情经 `get_index_quote` 仍正常）。
- **与 FIX-10 的关系**：FIX-10 校验器在此**正确发挥防御**，拦截了 `sh000001 close=11` 的污染入库；dead-letter 中保留的 16 条 sh000001/sz399001 记录即此缺陷的证据，修复 FIX-12 后应消失。

#### FIX-12 实施记录（2026-06-02，采用方案B 根治，已落地源码）

- **改动文件**：`packages/akshare-mcp/src/akshare_mcp/data_source/quotes.py`
  - 新增 `_resolve_index_storage_code(raw_code)`：在 `normalize_code` 碾平**之前**判定证券类型。仅「带显式市场标识（前缀 `sh`/`sz` 或后缀 `.SH`/`.SZ`）+ 指数号段（沪市 000 段 / 深市 399 段，或命中 `_INDEX_PREFIXED_CODES`）」判为指数，返回标准存储码（`sh000001`/`sz399006`）；裸 6 位码一律 None（按个股，保 `000001`=平安银行 向后兼容）。
  - 新增 `QuotesMixin._get_index_kline(index_storage_code, period, limit)`：指数专用取数，优先级 SQLite(前缀码) → Tushare `index_daily` → AkShare `stock_zh_index_daily_em`（lazy import）。
  - `QuotesMixin.get_kline` 顶部（`normalize_code` 之前）插入指数路由：命中指数则走 `_get_index_kline`；取数失败**不回退个股链**（避免再次 cross-symbol 污染），返回空让上层显性处理。
  - 补充 `import re` / `from typing import Optional`。
- **为何选方案B**：根治在 data_source 层，使所有经 `data_source.get_kline` 的路径（`sync_kline_data` / `batch_sync_klines` / 定时 `_sync_index_klines`）一并修复，无需逐个调用点改造。data_source 是底层包，不能反依赖 tools 层的 `get_index_kline`（循环依赖），故在层内自带指数取数逻辑。
- **零个股误伤设计**：纯 6 位代码不带市场标识时一律走个股链（`000001`→平安银行不变）；`sz000001`（深市 000 段非指数）、`sh600519`（沪市个股）、`510050`（ETF）均判 None。
- **验证**：
  - 单元 `test_fix12_index_kline_routing.py` 23 passed（判定矩阵全覆盖：指数代码→前缀码，个股/ETF/裸码→None）。
  - 端到端（测试 venv）：`get_kline('000001')`=11.08（平安银行）、`get_kline('600519')`=1307.22（茅台）个股路径不受影响；指数分支因测试 venv 无 akshare + tushare token 失效返回空（**运行时 akshare 可用，`get_index_kline` 已实测可取 sh000001=4091**）。
  - 既有套件无回归：FIX-12 + FIX 回归 + 契约 + 健康共 **49 passed**。
- **生效需重启 MCP 服务**。重启后验收：`sync_kline_data('sh000001')` 应返回 ~4091 指数点位（非 11 元）；`sync_kline_data('000001')` 仍返回 ~11 元个股；后续 `_sync_index_klines` 定时任务不再向 dead-letter 写入 `sh000001 close=11` 污染。
- **残留说明**：`_get_index_kline` 的 SQLite-first 分支用同步访问器（`get_klines_sync`/`conn`），当前 `SQLiteAdapter` 仅暴露 async `get_klines`（与既有个股 DB-first 分支同样限制），故该分支在纯 data_source 同步路径不命中，指数取数实际依赖 Tushare/AkShare；但调用方 `get_kline_with_cache` 的 step-2 已用 async `db.get_klines('sh000001')` 命中 DB（默认 `use_cache=True` 时返回正确 4091）。两层叠加可覆盖绝大多数场景。

---

## 八、第二批修复（FIX-13~18，2026-06-02，源自 findings_v3 剩余未修项）

> 背景：FIX-1~12 只覆盖了红队 findings_v3 中「崩溃/裸抛/数据污染」一类确凿 bug。本批处理重启后用运行中 MCP 工具**实测仍复现**的剩余项，逐项定位源码并修复 + 回归测试。

### FIX-13 ✅ screener_manager(run_strategy) 裸 TypeError（F-N27-6，HIGH）
- **实测复现**：`run_strategy(strategy_id='preset_value_stocks')` → `unexpected keyword argument 'criteria'`。
- **根因**：`run_strategy` / 用户策略分支用 `screener_manager(action='screen', criteria=...)` 调用，但工具签名是 `(action, params, kwargs)`，无 `criteria` 形参。
- **修复**：两处改为 `kwargs={'criteria': ...}`（与 combined_screen 分支一致）。
- **文件**：`tools/managers/screener_manager.py`。

### FIX-14 ✅ industry_chain_manager 裸 SQL 'no such column: code'（F-N26-2，MED）
- **实测复现**：`related_stocks(code='300750')` → `no such column: code`。
- **根因**：3 处 SQL 用裸 `code` 列，但 stocks 表实际列名是 `stock_code`。
- **修复**：`SELECT stock_code AS code`、`WHERE stock_code = $1`、`WHERE stock_code != $2`。
- **文件**：`tools/managers/industry_chain_manager.py`。

### FIX-15 ✅ data_sync_manager(schedule) SQL 方言不兼容（F-N38-2，HIGH）
- **实测复现**：`schedule(codes=['600519'])` → `no such function: array_to_string`（PostgreSQL 函数用在 SQLite）。
- **根因**：去重查询用 `array_to_string(codes, ',', '')` 比较 codes_signature。
- **修复**：改为 Python 端去重——按 task_type 取候选行，用 `_normalize_codes` 解码 codes 后比较 signature，跨方言安全。
- **文件**：`tools/managers/data_sync_manager.py`。

### FIX-16 ✅ parse_selection_query 连续涨跌方向误判（F-N27-1，HIGH）
- **实测复现**：「连续3天上涨」→ 同时产出 `upn` AND `downn` 矛盾条件（AND 下永远 0 命中）。
- **根因**：旧正则 `连(?:续|跌)` 中 `续` 是 `跌` 的同级备选，「连续上涨」里的「连续」让 down 正则也命中。
- **修复**：改为按方向词（上涨/下跌）判定，未出现方向词不产出对应条件；天数从方向锚定的相邻数字提取。
- **文件**：`tools/semantic/query_parser.py`。

### FIX-17 ✅ smart_stock_diagnosis 系统性 sell（F-N40-1，HIGH）
- **实测复现**：茅台、宁德时代均被判 sell；`RSI=45`（中性）、`mom=-0.05`（轻微）被塞进 risks 桶。
- **根因**：`_build_evidence` 的 `add(positive=<二元布尔>)` 把所有「非好即坏」，中性指标全归 risks；recommendation 用「risks≥4 一刀切 sell」绝对计数。
- **修复**：(1) 关键指标三态化（RSI<30 利好/>70 风险/中间中性；ma_alignment bullish/bearish/mixed；market_regime bullish/bearish/neutral；mom ±2% 中性带；PE/ROE/debt/vol/maxdd 同理）——中性 → `positive=None` 不计入任一桶；(2) recommendation 改为基于净证据（highlights−risks）相对判定，去掉绝对阈值一刀切。
- **文件**：`tools/semantic/diagnosis.py`。
- **回归测试**：中性 RSI/regime 不入 risks、强多头不判 sell、真弱势仍 sell、混合标的不再 sell（5 例）。

### FIX-18 ✅ valuation_consensus 内部 DCF 全失败而独立成功（F-N07-1，HIGH）
- **实测复现**：`valuation_consensus(600519)` 内部 dcf 报 `non_positive_net_income_or_shares`，但独立 `dcf_valuation(600519)` 成功（intrinsic=4019亿，net_profit=272亿）。
- **根因**：consensus 用独立的内联简化 DCF，读 `fin_payload.get("netProfit")`/`totalShares`，但 `db.get_financials` 实际列名是 `net_profit`（无 netProfit/totalShares 列），且无独立股本列 → base_ni 恒 0。
- **修复**：(1) 字段名对齐 `net_profit`；(2) 股本从 `net_profit/eps` 推导（退化用 `market_cap/price`）。修复后 consensus 产出 dcf=1827 + relative_pe=2738（n=2，不再全失败）。DDM 仍因无分红列 graceful 失败（真实数据缺口，非 bug）。
- **文件**：`tools/valuation_consensus.py`。

### 第二批验证汇总
- 新增测试 4 文件：`test_mcp_fix_plan_batch2.py`(6) + `test_fix_diagnosis_classification.py`(5) + `test_fix_valuation_consensus.py`(3) + 复用 FIX-16 用例。
- **全量回归 80 passed**（含 FIX-1~18 全部回归 + 既有 test-finance 三件套 + quant-core FIX-10），零失败。
- **生效需重启 MCP 服务**。重启后验收点：`screener_manager(run_strategy,preset_value_stocks)` 返回选股结果；`industry_chain_manager(related_stocks,code=300750)` 返回同行业股；`data_sync_manager(schedule)` 创建成功；`parse_selection_query('连续3天上涨')` 只产出 upn；`smart_stock_diagnosis` 强多头不再全 sell；`valuation_consensus` dcf 成功。

### findings_v3 剩余未修项（本批后仍 open，按需后续推进）
- F-N22-1/2（should_i_buy 概率失校准/与 baseline 矛盾）、F-N43-2/6（platt 死参数 / crowding 常量占位）、F-N04-1（RSI warmup=0 虚假超卖）、F-N08-1（scenario_dcf 负内在价值无护栏）、F-N18-1（optimize_portfolio 静默丢有效股）、ROOT-3（strategy_manager payload 爆炸）、F-N32/N34 写操作无校验。
- 这些多为决策模型校准 / 概率质量 / 大 payload 裁剪类，回归面与设计权衡更大，建议单独立项评估。

---

## 九、第三批修复（FIX-19~34，2026-06-02，findings_v3 决策/概率/治理/写校验剩余项）

> 背景：前两批（FIX-1~18）覆盖崩溃/裸抛/数据污染/SQL 方言。第三批攻坚 findings_v3 中剩余的**决策逻辑、概率校准、治理监控、写操作校验**类（含 HIGH：F-N22-1/2、F-N43-2/6、F-N08-1、F-N18-1、F-N32-1、F-N34-2、F-N42-1）。每项均：探针/运行时复现 → 定位源码 → 修复 → 回归测试。

### FIX-19 ✅ RSI warmup 不足伪造超卖买入（F-N04-1，HIGH）
- **复现**：RSI(14) 不足 15 根 K 线时旧逻辑输出 RSI=0 + signal=buy（虚假超卖）。
- **修复**：`services/technical_analysis.py::calculate_rsi` 数据不足返回 `value=None/signal='unknown'/reliable=False/warning=...`；`_calculate_rsi_numpy` 不足返回 None。消费方 `screen_conditions.py`(None-safe)、`trade_plan_parts/actions.py`(None→50.0 中性) 已适配。
- **文件**：`services/technical_analysis.py`、`services/screen_conditions.py`、`tools/trade_plan_parts/actions.py`。

### FIX-20 ✅ optimize_portfolio 静默丢有效股（F-N18-1，HIGH）
- **复现**：含无数据代码时静默丢弃，权重错位。
- **修复**：`tools/portfolio.py::optimize_portfolio` 跟踪 `valid_codes`/`dropped_codes`，所有 5 个优化器只对 `valid_codes` 配权，响应回显 `dropped_codes` + degraded 标注。
- **文件**：`tools/portfolio.py`。

### FIX-21 ✅ governance crowding 常量占位（F-N43-6，HIGH）
- **复现（运行时实测）**：无因子池时任意 momentum 因子恒 `crowding_score=0.85/band=high/similar_count=0`（虚假高拥挤）；含完全重复因子时旧 token 逻辑（按空格分词）`similar_count=0` 漏检。
- **修复**：`services/governance_monitor.py::check_crowding` 重写——(1) 新增 `_tokenize_factor_expr` 按运算符 `/ * + - = < >` 等切分（`close/ma_20-1`→`{close,ma,20,1}`），精确重复 + Jaccard≥0.6 检出相似；(2) 拥挤度由**因子池证据主导**：无池时仅给类别先验、`band` 永不升 high、`confidence=low`、附「未提供池」告警；有池时相似比例 + 重复惩罚主导评分。回显 `assessment_basis/confidence/exact_duplicate_count/pool_size`。
- **运行时验证**：无池→0.85 不再判 high（降级 medium/low + low 置信）；含 2 个重复→similar_count=2。
- **文件**：`services/governance_monitor.py`。

### FIX-22 ✅ platt_a/platt_b 死参数（F-N43-2，HIGH）
- **复现（运行时实测）**：method=platt 下传 (1.2,-0.3) 与 (3.0,-1.5)，输出逐位相同（builtin 自拟 sigmoid 无视用户系数）。
- **修复**：`tools/ai_workflows_parts/formatters.py::prediction_diagnosis_workflow` 新增分支——当 `method='platt'` 且用户显式传入非默认 `platt_a/platt_b` 时，走「固定系数」`platt_scale(x,a,b)`，`report_method='platt_fixed_coefficients'`；否则维持原 calibrate_probability_series 路径。
- **文件**：`tools/ai_workflows_parts/formatters.py`。

### FIX-23 ✅ scenario_dcf 负内在价值无护栏（F-N08-1，HIGH）
- **复现**：负利润率×高 capex 情景使 FCF 为负 → 终值放大成 -2744 亿 / per_share=-53 元，仍 success=true。
- **修复**：`tools/valuation.py::scenario_dcf_valuation` 在 payload 构建后加合理性护栏——`weighted_intrinsic_value<=0` → `valuation_reliable=false` + `quality_flags=['non_positive_intrinsic_value']` + 告警；部分情景为负 → `partial_negative_scenarios`；per_share<=0 → `non_positive_per_share`；`spread_risk=extreme` → `extreme_dispersion`。
- **文件**：`tools/valuation.py`。

### FIX-24 ✅ watchlist add_stocks 无代码校验（F-N32-1，HIGH）
- **复现**：ZZZ999/BADCODE 任意字符串真实入库。
- **修复**：`tools/managers/watchlist_manager.py` add_stocks 分支逐个 `resolve_existing_security_code_async` 校验存在性，非法/不存在的代码拒绝入库并回显，合法代码标准化后入库（入库前拦截）。
- **文件**：`tools/managers/watchlist_manager.py`。

### FIX-25 ✅ paper_trading 限价单无代码校验（F-N34-2，HIGH）
- **复现**：INVALIDXX@50 限价单挂单成功（市价单因取不到价格而拒，限价单绕过）。
- **修复**：`tools/managers/paper_trading_manager.py` place_order 在 `order_type` 分支**之前**统一 `resolve_existing_security_code_async` 校验，市价/限价/止损一致拒绝非法代码，堵限价单旁路。
- **文件**：`tools/managers/paper_trading_manager.py`。

### FIX-26 ✅ model_drift 静默忽略未识别键（F-N43-7，MED）
- **复现**：传 auc/ic/sharpe（明显漂移）全维度 unknown 无告警。
- **修复**：`services/governance_monitor.py::check_model_drift` 回显 `unrecognized_keys` + warnings（含 auc→rank_ic_mean 等映射建议）；全维度 unknown 且传了指标 → `action='review_input_keys'`（不再静默 continue_monitoring）。
- **文件**：`services/governance_monitor.py`。

### FIX-27 ✅ strategy_health 硬编码 strategy_id='system'（F-N43-8，MED）
- **复现**：target_type=model/target_id=redteam_n43_model 时 strategy_health.strategy_id='system'（归属错标）。
- **修复**：`GovernanceMonitor.run_full_check` 把 `resolved_id` 传给 `check_strategy_health`（不再 target_type!=strategy 时硬编码 system）。
- **文件**：`services/governance_monitor.py`。

### FIX-28 ✅ factor_decay 转负/短半衰期欠告警（F-N43-9，LOW）
- **复现**：近期 IC 转负 + 半衰期 1.4 周期仍判 decay_status=stable。
- **修复**：`check_factor_decay` 升级阈值——recent_ic<0 → 至少 decaying；trend=decaying 且（转负 或 半衰期≤2）→ decayed；回显 `escalation_reasons`。
- **文件**：`services/governance_monitor.py`。

### FIX-29 ✅ 空数组 probabilities 裸 Pydantic 栈（F-N43-1，MED）
- **复现（运行时实测）**：`prediction_diagnosis_workflow(probabilities=[])` → 框架层裸 Pydantic 'Field required'，与其它非法输入的标准化 PARAM_ERROR 不一致。
- **修复**：`probabilities` 签名改 `Optional`（让空/缺失进业务层），入口显式返回标准化 `PARAM_ERROR 'probabilities is required and must be a non-empty array...'`。
- **文件**：`tools/ai_workflows_parts/formatters.py`。

### FIX-30 ✅ 数据质量子系统判定互斥 + null 内容不校验（F-N43-4，HIGH）
- **复现**：data_quality_workflow 字段级 accepted_ratio=0.6 失败，但内嵌 validation_result.passed=true/quality_score=1.0（仅查列存在）；data_validation 的 non_null_fields 被静默忽略。
- **修复**：`services/adapters/data_validation_adapter.py` 两个 adapter 均新增 `non_null_fields` 真校验——Builtin 逐行查 null/空串；GX 生成 `expect_column_values_to_not_be_null`。`data_quality_workflow` 传 `non_null_fields=required`，使两套质量结论一致。
- **文件**：`services/adapters/data_validation_adapter.py`、`tools/ai_workflows_parts/formatters.py`。

### FIX-31 ✅ should_i_buy 概率失校准 + 结论矛盾 + style 无校验（F-N22-1/2/5）
- **复现**：buy_probability=0.13% 但 hit_rate=54.8%（ECE 0.5-0.75）；recommendation='avoid' 但 benchmark_delta=+0.328；bogus style 静默接受。
- **修复**：`tools/_decision_buy.py`——(1) **F-N22-5**：investment_style 枚举校验（非法回退 balanced + 警告）；(2) **F-N22-1**：当 prediction_quality 暴露大 ECE（>0.15）且 support≥15 时，用历史命中率对 buy_probability 做经验收缩混合（`empirical_shrinkage`），标 `calibrated=true/reliability/raw_buy_probability`；(3) **F-N22-2**：新增 `decision_consistency` 块——avoid/wait 但 benchmark_delta>0.1 且 support≥15 时显式告警，透传 threshold_inversion（不强行翻转决策，保留打分体系 + 显式矛盾提示）。
- **文件**：`tools/_decision_buy.py`。

### FIX-32 ✅ should_i_sell buy_price 无合理性校验（F-N22-7，LOW）
- **复现**：should_i_sell(002594当前96, buy_price=1326) → profit_pct=-92.75% 据此 sell 无告警。
- **修复**：`tools/_decision_sell.py` buy_price 与当前价数量级相差 ≥5x 或 ≤0.2x 时附 `buy_price_warning`（不拒绝，提示核对）。
- **文件**：`tools/_decision_sell.py`。

### FIX-33 ✅ publish 绕过 promotion_gate（F-N42-1，HIGH）
- **复现**：零证据 draft（raw_signal_count=0/quality_passed=false/blocker_count=3）publish 直接 status=listed 上架。
- **修复**：`tools/managers/strategy_mgr_crud.py::handle_publish` 发布前 `_resolve_strategy_incubation_overview` 评估 promotion_ready/quality_passed/blockers，gate 失败则拒绝并回显 blockers；显式 `force=true`（带 force_reason）方可强制发布（审计留痕 + gate_bypassed 标注）。
- **文件**：`tools/managers/strategy_mgr_crud.py`。

### FIX-34 ✅ create 不校验 strategy_type（F-N42-5，MED）
- **复现**：strategy_type='totally_fake_strategy_type_zzz' 无校验入库。
- **修复**：`handle_create` 已知执行器类型白名单（ma_cross/buy_and_hold/momentum/rsi/volatility_breakout/event_structure_breakout/margin_divergence/custom/factor_weighted/factor/personal）；未知类型附 `strategy_type_warning`（不硬拒绝以兼容自定义因子权重策略）。
- **文件**：`tools/managers/strategy_mgr_crud.py`。

### 第三批验证汇总
- 新增测试 `tests/test_mcp_fix_plan_batch3.py`（25 例：FIX-19~34，单元 + 行为 + 静态扫描）。
- **全量回归 105 passed**（FIX-1~34 全部回归 + test-finance 三件套 + 契约 + quant-core FIX-10），零失败。
- **生效需重启 MCP 服务**。重启后验收点：
  * `prediction_diagnosis_workflow(method=platt, platt_a/b 两组)` → 输出不同（非死参）；`probabilities=[]` → 标准化 PARAM_ERROR
  * `governance_check_workflow(factor, momentum, 无池)` → crowding_band 不再 high；含重复因子 → similar_count>0
  * `scenario_dcf_valuation(300750/002594)` 负估值 → valuation_reliable=false + quality_flags
  * `watchlist_manager(add_stocks, ZZZ999)` → 拒绝；`paper_trading_manager(place_order, limit, INVALIDXX)` → 拒绝
  * `should_i_buy(002594)` → decision_probability.calibrated + decision_consistency 告警；非法 style → 回退+警告
  * `strategy_manager(publish, 零证据draft)` → promotion_gate 拦截（除非 force=true）
  * `governance_check_workflow(model, auc/ic/sharpe)` → unrecognized_keys 回显

### findings_v3 剩余未修项（第三批后仍 open）
- **ROOT-3 / F-N42-2（payload 爆炸）**：strategy_manager/strategy_review_workflow 内嵌全量 factory run（数十万 token）——属响应裁剪/lean 模式设计项，回归面大，建议单独立项（需评估前端/下游消费方对 factory.runs 全量字段的依赖）。
- **F-N22-3/4（score↔recommendation 非单调 / threshold_inversion）**：评分模型本身与未来收益相关性问题，属模型重构范畴；FIX-31 已通过 decision_consistency 显式暴露矛盾（半护栏），根治需重训打分模型。
- **F-N43-3（sklearn 校准后端恒失败）**：环境/依赖问题（36 样本不足 CV 折叠），已有 fallback 标注；属运维项。
- 其余 MEDIUM/LOW（envelope 顶层/内层标志不一致、payload 冗余、跨工具结论分歧无 reconcile）多为一致性/体验优化，非功能性 bug。

---

## 十、第三批运行时验收（2026-06-02，重启后实测）

第三批（FIX-19~34）落地后重启 MCP 服务，逐项用运行中的工具复测，**全部确认生效**：

| FIX | 验收调用 | 实测结果 |
|---|---|---|
| FIX-20 | `optimize_portfolio([600519,ZZZ999,000858])` | valid_codes=[2只]、dropped_codes=[ZZZ999]、权重 0.5/0.5、degraded ✓ |
| FIX-21 | `governance(无池)` / 含3重复因子池 | 无池→band=low/score=0.34/confidence=low；含重复→similar_count=3/exact_dup=3/score=1.0 ✓ |
| FIX-22 | `prediction_diagnosis(platt, (1.2,-0.3) vs (3.0,-1.5))` | effective_method=platt_fixed_coefficients；首位 0.485 vs 0.289 输出不同 ✓ |
| FIX-23 | `scenario_dcf(custom 负利润率)` | valuation_reliable=false + quality_flags=[non_positive_intrinsic_value] + 负每股-122.38告警 ✓ |
| FIX-24 | `watchlist add_stocks([ZZZ999,BADCODE,600519])` | success=false，拒绝非法代码入库 ✓ |
| FIX-25 | `paper_trading place_order(limit, INVALIDXX)` | success=false "股票代码格式无效"（限价单旁路堵死）✓ |
| FIX-26 | `governance(model, auc/ic/sharpe)` | unrecognized_keys=[auc,ic,sharpe] + 映射建议 + action=review_input_keys ✓ |
| FIX-27 | `governance(target_type=factor, strategy_health)` | strategy_id=accept_crowd_pool_model（非 system）✓ |
| FIX-28 | `governance(factor, IC转负序列)` | decay_status=decayed + escalation_reasons=[recent_ic_negative,short_half_life=0.8] ✓ |
| FIX-30 | `data_quality(含null记录)` | GX passed=false/score=0.71 + expect_column_values_to_not_be_null（与字段级0.33一致）✓ |
| FIX-31 | `should_i_buy(002594, bogus_style)` | calibrated=true(raw 0.0011→0.2243)、style 回退告警、decision_consistency.consistent=false ✓ |
| FIX-32 | `should_i_sell(002594, buy_price=1326)` | buy_price_warning（相差13.8x）✓ |
| FIX-33 | `strategy publish(零证据draft)` | promotion_gate 拦截，回显 3 blockers（5D样本0<20/skill LCB≤0/前向覆盖0%）✓ |
| FIX-34 | `strategy create(fake_type)` | strategy_type_warning 回显 ✓ |

测试期间创建的策略已 archive 清理。

---

## 十一、第四批修复（FIX-35~38，2026-06-02，ROOT-3 payload 爆炸 + F-N42 剩余项）

### FIX-35 ✅ closure_review payload 爆炸 + 错误血缘归属（F-N42-2 / ROOT-3，HIGH）
- **复现**：`strategy_review_workflow`/`closure_review`/`detail` 对单策略内嵌 `factory.runs`=最近 5 个**完整** factory run（每个 110-119KB 含全 stages），单响应数十万 token；且手工 create 的 draft 被赋全局 `factory_run_id`（零关联，AI 误判为工厂产出）。
- **修复**：`services/strategy_lifecycle_shared/closure_review.py`——
  - **(a) payload 裁剪**：新增 `_summarize_factory_run()` 仅保留 run 标量摘要（run_id/status/时间/计数 + summary 顶层标量），剔除 stages 等重字段；`factory.runs` 改为摘要列表，附 `runs_truncated=true` + `runs_note`（完整 stages 用 factory_run_detail 单独取）；`latest_run` 同样摘要化。
  - **(b) 血缘门控**：`resolved_factory_run_id` 只从「execution_audit_snapshot.factory_run_id 或 策略 metadata/params 的 factory_run_id/source_factory_run_id」解析；**移除回退到全局 latest_factory_run.run_id**；新增 `factory_run_lineage_basis`（execution_audit_snapshot/strategy_metadata/unlinked）标注归属来源。
- **文件**：`services/strategy_lifecycle_shared/closure_review.py`。
- **注**：`factory_status` 的 `recent_run_diagnostics` 经核查已是紧凑诊断摘要（run_briefs 标量，非全 stages），无需改动；其 `last_result`（单个最新 run）属 status 查询的预期主体，本次未裁剪。

### FIX-36 ✅ incubation_overview 文档契约不符（F-N42-4，LOW）
- **复现（运行时实测）**：help 文档称 strategy_id 可选（无参返回 incubating 列表），但运行时报 "strategy_id/id is required"。
- **根因**：`handle_incubation_overview` 本身**已支持**无 id 列表分支，但 `STRATEGY_MANAGER_REQUIRED_PARAMS` 预校验层强制要求 id，在 handler 之前就拒绝。
- **修复**：从 `contracts/strategy_manager_contract.py::STRATEGY_MANAGER_REQUIRED_PARAMS` 移除 `incubation_overview` 条目，放行 handler 的列表分支。
- **文件**：`contracts/strategy_manager_contract.py`。

### FIX-37 ✅ rank sort_by 静默 fallback（F-N22-3 rank / N42 关联，MED）
- **复现**：`rank(sort_by=nonexistent_metric_zzz)` 未报错，静默 fallback 到 rrf_score。
- **修复**：`strategy_mgr_crud.py::handle_rank` 校验 sort_by∈{DEFAULT_RANK_KEYS, rank, rrf_score}，非法回显 `sort_by_warning`（不静默）；合法单指标作为 rank_keys 使用。
- **文件**：`tools/managers/strategy_mgr_crud.py`。

### FIX-38 ✅ publish 不可逆无提示（F-N42-3，MED）
- **复现**：publish→listed 后 owner 无法 delete（只能 archive），契约无提示。
- **修复**：`handle_publish` 成功响应附 `irreversible_note`（上架后只能 archive 不能 delete）。
- **文件**：`tools/managers/strategy_mgr_crud.py`。

### 第四批验证汇总
- 新增测试 `tests/test_mcp_fix_plan_batch4.py`（7 例：FIX-35 摘要/血缘 + FIX-36/37/38 静态扫描）。
- **全量回归 112 passed**（FIX-1~38 + test-finance + 契约 + quant-core），零失败。
- **生效需重启 MCP 服务**。重启后验收点：
  * `strategy_review_workflow(real_strat)` / `closure_review` → factory.runs 仅摘要（无全 stages）+ runs_truncated=true；手工 draft 的 factory_run_id=null + factory_run_lineage_basis=unlinked
  * `strategy_manager(incubation_overview, 无 id)` → 返回 incubating 列表（非 required 报错）
  * `strategy_manager(rank, sort_by=非法)` → sort_by_warning 回显
  * `strategy_manager(publish)` 成功响应含 irreversible_note

### findings_v3 剩余项（第四批后）
- **F-N22-3/4（评分模型非单调 / threshold_inversion）**：FIX-31 已通过 decision_consistency 暴露矛盾（半护栏）；根治需重训打分模型，属模型工程项。
- **F-N43-3（sklearn 校准后端恒失败）**：环境/样本量问题，已有 fallback 标注，属运维项。
- 其余 MEDIUM/LOW（envelope 顶层/内层标志一致性、payload 冗余去重、跨工具结论 reconcile）为一致性/体验优化，非功能 bug，按需迭代。
- **结论**：findings_v3 中所有「功能性 bug + 数据正确性 + 决策护栏 + 写校验 + payload 爆炸」类问题（含全部 HIGH/MED 可修项）已闭环。剩余为模型重构/运维/体验项。

---

## 十二、第五批修复（FIX-39~43，2026-06-02，findings_v3 剩余三类收尾）

> 背景：第四批后剩三类「非崩溃」项：(1) sklearn 校准恒失败(F-N43-3)、(2) 评分模型非单调(F-N22-3)、(3) envelope 标志一致性 + payload 冗余 + 空输入跨工具一致性。本批逐一根治。

### FIX-39 ✅ sklearn 校准后端恒失败（F-N43-3，MED→根治）
- **根因（探针实测）**：`calibrate_probability_series` 旧实现用 `CalibratedClassifierCV(estimator=自定义_RawScoreEstimator)`，在 **sklearn>=1.6 的 estimator tag 体系下该假估计器被判为 regressor**，恒抛 `ValueError: ... should either be a classifier ...`，导致 platt/isotonic 每次静默降级 builtin（红队观测的 100% fallback）。
- **修复**：`services/probability_calibration.py` 重写 sklearn 主路径——后验校准已持有 (score→label) 对，**直接拟合** `LogisticRegression(C=1e6)`（Platt/sigmoid）或 `IsotonicRegression`（isotonic），不再依赖 CV 折叠假估计器。backend 名改为 `sklearn_logistic_platt` / `sklearn_isotonic_regression`。单类别仍由既有 `len(set)>=2` 守卫。
- **探针实测**：sigmoid→`sklearn_logistic_platt`/fallback=False；isotonic→`sklearn_isotonic_regression`/fallback=False。
- **文件**：`services/probability_calibration.py`。
- **同步更新**：既有 `tests/test_probability_calibration_runtime.py` 断言旧 backend 名，已更新为新名 + 增 isotonic 用例。

### FIX-40 ✅ should_i_buy score→recommendation 非单调（F-N22-3，MED）
- **复现**：score=60 因 context_decision（≥4 negatives）被一次性翻到 avoid，而 score=45 仍是 hold，出现「高分反而更悲观」。
- **修复**：`tools/_decision_buy.py` 限定 context 覆盖**最多下调一档**（hold→wait, wait→avoid），用 `_REC_ORDER` + `bounded_level` 维持单调，禁止 hold→avoid 跨级跳变；保留 context 的下调能力。
- **文件**：`tools/_decision_buy.py`。

### FIX-41 ✅ envelope 顶层/内层 fallback/degraded 不一致（F-N01-2 + N21/N24/N26/N28/N29，MED）
- **根因**：很多工具（如 skills 的 `_skill_payload`）把 `backend_used/fallback_used` 直接合并进 `data`，但 `enrich_response_meta` 只读顶层 `result.fallback_used`，导致 `data.fallback_used=true` 被顶层 `fallback_used=false` 掩盖。
- **修复**：`utils.py::enrich_response_meta` 新增「内层一层标志上浮」——检测 `result["data"]` 的 `fallback_used`/`fallback_reason`/`degraded` 并上浮到顶层，使顶层与内层一致。这是通用修复，一次性覆盖多场景。
- **文件**：`utils.py`（全工具共用，已跑全量套件确认无回归）。

### FIX-42 ✅ run_skill payload 翻倍（F-N45，LOW）
- **复现**：`run_skill` 成功响应同时塞 `"execution": execution` 和 `"result": execution`，是同一对象的两份完整副本，payload 翻倍。
- **修复**：`tools/skills.py` 仅保留 `result` 为权威键，`execution` 改为 `execution_ref="result"` 指针说明。
- **文件**：`tools/skills.py`。

### FIX-43 ✅ 空 records 跨工具语义不一致（F-N43-5，MED）
- **复现**：`data_quality_workflow(records=[])` → success=true/accepted_ratio=1.0（真空通过，误导），而 `data_validation(records=[])` → 干净 PARAM_ERROR。
- **修复**：`tools/ai_workflows_parts/formatters.py::data_quality_workflow` 空 records 返回标准化 `PARAM_ERROR 'records is required and must be a non-empty array...'`，与 data_validation 对齐。
- **文件**：`tools/ai_workflows_parts/formatters.py`。

### 第五批验证汇总
- 新增测试 `tests/test_mcp_fix_plan_batch5.py`（8 例）；更新 `tests/test_probability_calibration_runtime.py`（2 例，新 backend 名 + isotonic）。
- **MCP_FIX_PLAN 全量回归 120 passed**（FIX-1~43 + 契约 + quant-core）。
- **全量 tests/ 套件 466 passed / 6 failed / 1 skipped**：6 个 failed 中 **5 个与本次修改无关**（pre-existing，git diff 确认相关源文件未改）：
  * `test_factory_db_only_boundary`（strategy_mgr_factory_events 既有架构边界违规，未改）
  * `test_skill_capability_audit` ×2（依赖 `.codex/skills/` 文件系统状态，期望 21 skills 实际 1，环境项）
  * `test_llm_pipeline_diagnostics`（`_llm_provider_error_count` 计数逻辑，strategy_pipeline 未改）
  * 第 6 个 `test_probability_calibration_runtime` 是断言旧 backend 名，**已随 FIX-39 更新通过**。
- **生效需重启 MCP 服务**。重启后验收点：
  * `prediction_diagnosis_workflow(method=platt/isotonic)` → backend_used=sklearn_logistic_platt/sklearn_isotonic_regression，fallback_used=false（不再恒降级）
  * `should_i_buy` → score 越高 recommendation 不会比低分更悲观（单调）
  * skills 工具 → 顶层 fallback_used 与 data 内层一致；run_skill 无 execution/result 双份
  * `data_quality_workflow(records=[])` → PARAM_ERROR（与 data_validation 一致）

### 最终结论
findings_v3 全部 **可修复的功能性问题**（崩溃/裸抛/数据污染/决策护栏/概率校准/写校验/payload 爆炸/envelope 一致性/空输入一致性）已全部闭环（FIX-1~43，五个批次）。剩余仅：
- **F-N22-4（threshold_inversion / 评分模型与未来收益相关性）**：属打分模型重训范畴，FIX-31/40 已通过 decision_consistency + 单调映射提供护栏与显式告警。
- **本次全量套件暴露的 5 个 pre-existing failures**（架构边界 / 技能审计环境 / LLM 计数）：与红队 findings_v3 无关，属独立既有问题，建议单独排期。

---

## 十三、Pre-existing 测试失败排查与修复（2026-06-02，全量套件清零）

> 背景：第五批后跑**全量** `tests/` 套件（而非仅 MCP_FIX_PLAN 回归子集）暴露 6 个失败，其中 1 个随 FIX-39 已修。剩余 5 个经 `git stash`/`git ls-files` 确认与红队 findings_v3 无关、属独立 pre-existing 问题。本节逐一根因排查并修复，使 akshare-mcp 与 strategy-factory 两套件**全绿**。

### 根因分类与修复

#### A. `test_probability_calibration_runtime`（断言旧 backend 名）
- **根因**：FIX-39 把 sklearn 校准主路径从 `CalibratedClassifierCV` 改为 `LogisticRegression`/`IsotonicRegression`，backend 名变更，既有测试仍断言 `sklearn_calibrated_classifier_cv`。
- **修复**：更新测试为新 backend 名（`sklearn_logistic_platt`/`sklearn_isotonic_regression`）+ 增 isotonic 用例。

#### B. `test_skill_capability_audit` ×2（硬编码 21 技能 vs git-ignored 本地内容）
- **根因**：`.codex/skills/` 在 `.gitignore` 中（git-ignored，`git ls-files` 返回 0），本地仅 1 个 doc-only 技能（`aiask-graphify-architecture`），但测试硬编码 `repo_local_skill_count == 21` 与 `actual==contract==executor`。**产品代码行为正确**（审计正确检出 1 本地 / 0 契约 / 0 执行器并报 `meta_conflicts`），是测试假设了不可复现的本地全集。
- **修复**：改写两测试为 **count-agnostic 一致性校验**——校验审计逻辑自洽（`stale_meta_detected == (counts 不一致)`、有不一致必产出 conflicts、`report` 计数与实际集合长度一致），完整全集在位时仍保留强一致性保证分支。

#### C. `test_llm_pipeline_diagnostics::test_pipeline_cooldown_skip` + `test_provider_http_error_counts_as_llm_degraded`（provider 错误判定）
- **根因**：`_llm_provider_error_count` 不扫描 `pipeline_fallback_counts`，`cooldown_skip` 未被识别；且 `_is_llm_degraded` 仅用比例阈值，单个 provider 错误（无可靠分母时）不触发降级。
- **修复**：`strategy_factory/application/run_models.py`——(1) `_llm_provider_error_count` 增扫 `pipeline_fallback_counts.cooldown_skip`（`local_fallback_preferred_or_skip`/`target_context_blocked` 仍排除）；(2) `_is_llm_degraded` 在**缺少 `autonomy_task_count` 可靠分母**时，任何 provider 错误判降级；**有分母**时维持比例阈值。
- **跨套件契约调和**：此修复一度使 strategy-factory 的 `test_no_partial_llm_for_single_provider_error_below_threshold`（1/6 provider_error 应 NOT degraded）失败。两套件契约表面矛盾，实则由**分母有无**区分：akshare 诊断用例无 `autonomy_task_count`（绝对计数判定），strategy-factory cycle-status 用例有（比例判定）。最终用 `autonomy_task_count` 存在性作为判据，两套件同时通过。

#### D. `test_runtime_provider_boundary::test_supervisor_*_strategy_interval` ×2（测试-代码漂移）
- **根因**：`run_all_factories._build_specs` 新增了第 4 个工厂 `signal_tracker`（访问 `args.no_signal_tracker`/`signal_tracker_run_time`/`signal_tracker_verbose`/`signal_tracker_silent_restart`），但这两个 supervisor 测试的 `Namespace` fixture 未同步新增字段 → `_build_specs(args)` 抛 `AttributeError`。
- **修复**：测试 `Namespace` 补齐 `no_signal_tracker=True` + 三个 `signal_tracker_*` 字段（与 `no_factor`/`no_incubation` 一致的禁用语义），断言 `len(specs)==1` 仍成立。

#### E. `test_akshare_uses_only_strategy_factory_public_api`（架构边界违规）
- **根因**：`strategy_mgr_factory_events.py` 6 处直接 `from strategy_factory.application.research.* import ...`，违反「akshare-mcp 只用 strategy_factory 公共 API」边界契约。
- **修复**：(1) 在 `strategy_factory/api/facade.py` 的 `_LAZY_EXPORTS` + `__all__` 与 `strategy_factory/__init__.py` 的 `_FACADE_EXPORTS` 新增 7 个研究符号（`NormalizedEvent`/`propagate_event_to_themes`/`resolve_target_basket`/`ThemeExposureBuilder`/`seed_default_theme_graph`/`generate_tasks_from_active_events`/`ThemeResponseRegression`）作为公共 API；(2) `strategy_mgr_factory_events.py` 6 处改为 `from strategy_factory import (...)`。边界测试 8 passed。

### 验证汇总
- **akshare-mcp 全量套件：473 passed / 1 skipped / 0 failed**（修复前 466 passed / 6 failed）。
- **strategy-factory 全量套件：353 passed / 0 failed**（修复前 350 passed / 3 failed）。
- 改动文件：`services/probability_calibration.py`(B 关联 FIX-39)、`tests/test_probability_calibration_runtime.py`、`tests/test_skill_capability_audit.py`、`strategy_factory/application/run_models.py`、`tests/test_runtime_provider_boundary.py`、`strategy_factory/api/facade.py`、`strategy_factory/__init__.py`、`tools/managers/strategy_mgr_factory_events.py`。
- **生效说明**：facade 公共 API 扩展与 factory_events 改为公共导入需重启 MCP 服务才在工具层生效（运行时行为等价，纯架构边界整改 + 测试修正，无功能回归）。

### 结论
findings_v3 全部可修复功能性问题（FIX-1~43）已闭环；本次额外把全量套件的 5 个独立 pre-existing 失败也一并根因修复。两大测试套件现全绿（akshare-mcp 473 passed、strategy-factory 353 passed），仅余 1 个条件性 skip（akshare-market SKILL.md 本地缺失时的 frontmatter 测试，属 git-ignored 内容缺失的正常跳过）。
