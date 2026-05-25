# S16 · 选股器 + 多因子打分 + 自然语言解析 + 行业筛选 + 自选股管理 + factor IC + 候选注册表

- **判定**: ✅ 通过 (31/31 工具,Pass=16 / Degraded=9 / Fail-graceful=6 / Fail=0)
- **耗时**: 13:00:00 → 13:06:37 (约 6 分 37 秒)
- **覆盖**: screener_manager(8 actions)/ watchlist_manager(7 actions)/ quant_manager(8 actions:multi_factor / calculate_factors / factor_ic × 2 / factor_research_memory / batch_compute_factors / factor_candidate_registry / scheduler_status)/ parse_selection_query(2 次:正常+乱码)/ get_stock_list(2 次:正常+边界)/ data_validation / log_recommendation_audit

## 🔥 本场景重大发现 — 选股链路 + 量化命名空间四破口(15 条 finding,7 high / 4 medium / 4 positive)

### 1. screener_manager.screen industry filter 完全失效(S16-F01)

```
screen(industry="酿酒", max_pe=20, min_roe=10)
  → matched=12

12 stocks 中:
  ✅ 真酿酒/白酒:  1 个(山西汾酒)
  ❌ 跨行业:       11 个(休闲食品 / 航空 / 工业金属 / 通用设备 / ...)

industry_match_ratio: 1/12 = 8.3%   ← 91.7% 跨行业!
top_level.success: true             ← 但 success=true 不警告
```

**底层 db.stocks join 失效** — AI 调用 industry='酿酒' 拿到 11/12 跨行业 stocks 直接做错误投资决策;industry filter 形同虚设。

### 2. screener_manager.save_strategy criteria 被忽略 → run_strategy TypeError(S16-F02)

```python
# 第一步: save 时 criteria 被忽略但 success=true
save_strategy(criteria={"max_pe": 20, "min_roe": 10}):
  → success: true                            ← 但 db 存 "{}"!
  → strategy_id: "..._s16_strategy_xxx"

list:
  user_strategy.criteria: "{}"              ← 确认 db 没存 criteria

# 第二步: run 时直接抛栈
run_strategy(strategy_id):
  → TypeError: unexpected keyword argument 'criteria'
```

**两阶段隐式失败**:save 时静默丢失,run 时 Python 栈透出 — major bug。

### 3. 同股两 quant 工具评分差 5 倍(S16-F03)

| 工具 | 总分 | 评级 | 推荐 |
|---|---|---|---|
| `quant_manager.multi_factor_score(600519)` | **0.61** | B | **buy** |
| `quant_manager.calculate_factors(600519)` | **0.124** | (低) | **avoid** |

**delta_ratio = 0.61 / 0.124 = 4.92×**;`calculate_factors` 中 ps_ratio / roa / revenue_growth / profit_growth **4 项 null** 但仍 success=true。AI 看两工具同股完全相反信号。

### 4. screener_manager.technical_screen pool 严重不足(S16-F04)

```
technical_screen(rsi_oversold AND macd_golden_cross):
  matched_count:   0
  pool_size:      50            ← only 50 stocks!
  total_market:   5529          ← 全市场
  pool_coverage:  0.9%          ← 只看了 0.9%!
```

**0.9% 覆盖率严重 sample**。AI 拿到 matched=0 以为'今日无超卖+金叉股票',实际剩下 5479 stocks 完全没看。

### 5. multi_factor_score volatility 占 84%(累计 3 次复现 S08/S09/S16)

```
total_score: 0.61
factors:
  - volatility:        weighted_score=0.51   ← 84% 占比!
  - momentum:          weighted_score=0.04
  - value:             weighted_score=0.03
  - quality:           weighted_score=0.02
  - growth:            weighted_score=0.01
  - reversal:          weighted_score=0.00
  ─────────────────────────────────────────
  其它 5 因子总和:     0.10                  ← 16% 共占
```

S08-F08 / S09-F08 / S16-F05 **累计 3 次复现** — 因子归一化 + 权重 imbalance 累积病灶。

### 6. parse_selection_query ROE 阈值 0.1 vs db 10.06 单位不一(累计 5 次 naming inconsistency)

```python
parse_selection_query("市盈率小于20且ROE大于10%"):
  parsed.roe.threshold: 0.1                 ← decimal

vs db.financials.roe:    10.06              ← integer 尺度
vs calculate_factor(roe_ttm).value: 10.06   ← integer 尺度

scale_mismatch:         100×
```

5 次累计:S07-F09 / S15-F09 (×2) / S16-F06 / S16-F07 — **整个工具集 factor naming 系统性 inconsistency**。

### 7. quant_manager 内部 4 个 factor 命名空间割裂(S16-F07)

| Action | Naming Style | Example | Total Names |
|---|---|---|---|
| `factor_ic` | mom_Nd / momentum | `mom_60d` ✅ | 6 |
| `batch_compute_factors` | 6 大类 only | `[growth/momentum/quality/reversal/value/volatility]` | 6 |
| `list_factors` | 50 specific + aliases | `momentum / mom_5d / rsi_14 / macd_signal / ...` | **50** |
| `calculate_factor` | _ttm suffix | `roe_ttm / pe_ttm` | 11 fundamental |

**4 个不同命名空间** — AI 学了 list_factors 的 50 个名字后:

- 调 `batch_compute_factors([mom_60d, rsi_14])` → reject(supported=6 大类)
- 调 `factor_ic(momentum_20d)` → reject(用 mom_60d)
- 调 `calculate_factor(roe)` → reject(用 roe_ttm)

## ✅ Positive evidence(4 条)

### S16-F12 ✅:list_conditions 66 条件 / 6 categories 完整

```
total_conditions: 66
categories(6):
  - fundamental: 20 (pe/pb/roe/roa/eps/market_cap/...)
  - technical:   18 (rsi/macd/kdj/boll/ma_cross/...)
  - market:      12 (turnover/volatility/beta/...)
  - industry:     8 (sector/industry_chain/...)
  - concept:      5 (热门概念/themes/...)
  - custom:       3 (user-defined/...)
```

✅ **screener_manager 比 quant_manager 多 16 条 condition**(66 vs 50);6 categories 覆盖全。

### S16-F13 ✅:parse_selection_query 三层解析极完整

```
正常 query "市盈率小于20且ROE大于10%":
  fundamental: [{field=pe_ratio, op=<, value=20}, {field=roe, op=>, value=0.1}]
  technical:   []
  semantic:    []
  industry:    null
  theme:       null
  suggestion:  "可调用 screener_manager.screen 执行筛选"

乱码 query "$$@@!!不可解析的乱码 ROE>>":
  fundamental: []   technical: []   semantic: []
  parsed:      true                 ← graceful 不抛栈
  suggestion:  "未能解析出有效条件,请尝试更具体的描述"
```

✅ 三层解析(fundamental/technical/semantic + industry/theme + suggestion)极完整,乱码 input **graceful** 处理。

### S16-F14 ✅:watchlist 状态管理 + factor governance 极完整

```
watchlist 链路:
  create_group → add_stocks(3) → list(codex,2) → add(default,601857) →
  remove_stock(000333) → reorder → list(codex,2)
  全 robust ✅

factor_research_memory(5 items):
  每项: candidate + rating + metrics + similarity_edges + embedding(1536-dim) + memory_document
  embedding model: openai_compatible / text-embedding-3-small  ← 1536 维向量!

factor_candidate_registry(5 items):
  avg_total_score:  77.94
  max_total_score:  97.79
  family:           {momentum: 3, mean_reversion: 1, microstructure: 1}
  lookahead_risk:   {low: 3, medium: 2}
  multiple_testing: {low: 4, high: 1}
  governance_grade: {C: 5}  ← 全 watch
```

✅ **量化 governance 层最 robust** — embedding(1536) + similarity_edges + 双重风险评估(lookahead + multiple_testing) + admission_blocked 显式。

### S16-F15 ✅:data_validation(GE)累计 9 场景 42/42 stable

```
S07 → 7/7    S08 → 7/7    S09 → 2/2    S10 → 3/3
S11 → 5/5    S12 → 5/5    S13 → (skipped)  S14 → 3/3
S15 → 3/3    S16 → val-6bde653578d8 7/7
─────────────────────────────────────────────────
                     total=42  pass=42  100%
```

**S07-S16 9 场景累计 42/42 expectations 全 pass**。

## 🚨 工具间数据不一致(本场景新增 15 条 finding,其中 high 7 条)

### 7 条 high

- **S16-F01**:screener.screen industry filter 完全失效(12 stocks 1 真酿酒)
- **S16-F02**:save_strategy criteria 被忽略 → run TypeError(silent save fail + Python stack)
- **S16-F03**:同股两 quant 工具评分差 5×(multi_factor 0.61 vs calculate_factors 0.124)
- **S16-F04**:technical_screen pool 0.9% 覆盖率(50/5529)
- **S16-F05**:volatility weighted_score 84% 占比(累计 3 次 S08/S09/S16)
- **S16-F06**:parse_selection_query ROE 单位不一(0.1 vs 10.06,naming 累计 5 次)
- **S16-F07**:quant_manager 内部 4 个 factor 命名空间割裂

### 4 条 medium

- S16-F08:watchlist scope filter 不一致(累计 3 次 S11/S14/S16)
- S16-F09:save_strategy user_id=default(累计 4 次)
- S16-F10:alternative_factors sentiment/capital_flow 全 0.5(累计 4 次)
- S16-F11:get_stock_list PE 极端负值不警告(numeric_sanity 累计 5 次)

### 4 条 low(positive evidence)

- **S16-F12** ✅:list_conditions 66 条件 / 6 categories 完整
- **S16-F13** ✅:parse_selection_query 三层解析(fundamental/technical/semantic)+ 乱码 graceful
- **S16-F14** ✅:watchlist 状态管理 robust + factor_research_memory(1536-dim embedding)+ candidate_registry(双重风险评估)
- **S16-F15** ✅:data_validation(GE)累计 9 场景 42/42 stable

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-6bde653578d8` | dataset_id | data_validation,GE backend,7/7 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s16_screener_audit |
| `watchlist s16_high_quality` | **persist** | user_id=codex_full_mcp_20260522,3 stocks 经 add/remove/reorder |
| `screener_manager save_strategy` | **persist (broken)** | strategy_id=...,**criteria stored as "{}"** ⚠ |
| ~25 audit_event_id | read_only | screener × 8 / watchlist × 7 / quant × 8 / parse × 2 / get_stock_list × 2 / data_validation / log_audit |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **16/22**
- 累计 Fail: **0**
- 累计推荐 bug: **173 条**(S02-S15 累计 158 + S16 新增 15,其中 high 累计 **80 条**)

## 关键观察:S16 验证了"选股链路四大失效 + 量化命名空间系统性割裂"

**S07-S15** 反复发现"工具间数据不一致 + silent fallback";**S16 在选股 / 量化层达到峰值**:

**核心问题模式**:

1. **行业 filter 完全失效**(F01):12 stocks 1 真酿酒 — db.stocks join 失败但 success=true
2. **save_strategy 双阶段隐式失败**(F02):criteria 被忽略 → run 时 Python 栈透出
3. **同股两 quant 工具差 5 倍**(F03):multi_factor_score 0.61 buy vs calculate_factors 0.124 avoid — 完全相反信号
4. **池覆盖率 0.9%**(F04):technical_screen 默认只扫 50/5529 stocks
5. **单因子主导 84%**(F05):volatility weighted_score 84% 累计 3 次复现
6. **factor naming 系统性割裂**(F06/F07):
   - parse_selection_query ROE 0.1 vs db 10.06(F06)
   - quant_manager 内部 4 个命名空间(factor_ic / batch_compute_factors / list_factors / calculate_factor)— **AI 学了 list 50 个名字后调 batch 全 reject**
7. **scope filter 不一致**(F08/F09)累计 3-4 次

**positive 证据**(4 条):

- list_conditions 66 条件 / 6 categories 完整(比 quant_manager list_factors 50 多 16)
- parse_selection_query 三层解析 + 乱码 graceful
- watchlist 状态管理 robust + factor_research_memory(embedding 1536-dim)+ factor_candidate_registry(双重风险评估)
- data_validation 累计 9 场景 42/42 stable

**关键洞察**:

S16 暴露**选股 / 量化层四大破口**:

- **screener filter 失效**(F01:industry / F04:pool 0.9%)
- **隐式 save 失败**(F02:silent + Python TypeError 双错)
- **同概念多工具 5× 差距**(F03:multi_factor vs calculate_factors)
- **factor 命名空间系统性割裂**(F06+F07:5+ 累计 → 命名 inconsistency 是工具集**最大系统性硬伤**)

但 **screener_manager.list_conditions(66 条件)/ parse_selection_query(三层 + graceful)/ watchlist 状态管理 / factor governance(embedding+registry+双重风险评估)** 是**选股+量化层最 robust 部分**;**governance 层 robust 度 > scoring/screening 层一致性**。

**累计 16/22 场景全部 ≥31 工具,工具(去重)161/161**,Fail=0,累计 bug 173 条(其中 high 80 条),22 场景红队复测进入收尾阶段(剩 6 场景 S17-S22)。
