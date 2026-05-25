# S09 · 组合优化 + 风险分解 + 压力测试 + Barra 因子归因 + 绩效归因

- **判定**: ✅ 通过 (32/31 工具,Pass=13 / Degraded=17 / Fail-graceful=2 / Fail=0)
- **耗时**: 11:58:24 → 12:01:40 (约 196s)
- **持仓**: portfolio_id=3,5 sectors mix 600519(白酒)/601318(保险)/000001(银行)/000333(家电)/601857(石油)各 200K = 1M

## 🔥 本场景重大发现 — 组合优化 + 风险归因双崩盘(16 条 finding,8 条 high)

### 1. optimize_portfolio 4 大方法输出全有问题(S09-F01/F02/F03)

| 方法 | 关键权重 | sharpe | 致命问题 |
|---|---|---|---|
| `equal_weight` | 0.20 × 5 | - | ✅ 平凡解 |
| `risk_parity (252d)` | 000001=23.86% 最大 | - | 🚨 银行波动应当低于茅台,risk_parity 反而给最大 |
| `risk_parity (63d)` | 000001=22.26%,延长后 vol 不同 | - | 🚨 lookback 敏感性不警告 |
| `mean_variance` | **600519 ≈ 0 / 601857=63.9%** | - | 🚨🚨🚨 白酒龙头权重为 0,中石油 64% — 与基本面常识相反 |
| `max_sharpe (max_w=0.35)` | 601318/000333/601857 平均分 | **-2.67** | 🚨🚨🚨 sharpe 是负的还说是 'max_sharpe' |
| `black_litterman` | **600519=99.46% / 000001=-26.87%** | 4.21 | 🚨🚨🚨 极端集中 + 允许做空 + 不可执行 |
| `risk_budget [0.4,0.2,0.1,0.2,0.1]` | budget 严格匹配 | - | ✅ risk_contributions 误差<1e-4 |
| `risk_budget shape 5 vs 3` | numpy broadcast error | - | 🚨 shape 校验缺失,异常透出 |

### 2. stress_test 双工具两套模型 + 硬编码行业(S09-F04 / S09-F11)

```
stress_test_portfolio.sector_rotation:
  科技: -10%,  金融: +5%,  消费: -2%,  医药: -2%,  其他: -2%
  signed_return = -2.0%
持仓实际行业:
  酿酒/保险/全国性银行/白色家电/油气开采  ← 0% 科技!
```

**stress_test 不查持仓 sector,直接用固定字典,给出'-2.0% sector_rotation 损失'完全不基于持仓**。

```
risk_manager.stress_test.market_crash       = 21.00%(20% market + 1% vol penalty)
stress_test_portfolio.market_crash          = 20.00%(纯单层)
```

**两工具同名 scenario 给两个数,差异不显式**。

### 3. 平安银行 000001 流动性数据错误(S09-F05)

```
risk_manager.risk_exposure 输出:
  000001  avg_daily_amount = 122178   (12 万)        days_to_exit = 8.18 天   level=high
  601318  avg_daily_amount = 49.4 亿                   days_to_exit = 0.0 天    level=low
  000333  avg_daily_amount = 26.0 亿                   days_to_exit = 0.0 天    level=low
  601857  avg_daily_amount = 20.5 亿                   days_to_exit = 0.0 天    level=low
  600519  avg_daily_amount = 6.43 亿                   days_to_exit = 1.55 天   level=low
```

平安银行实际日成交几十亿,**单位转换 bug**(其他股是元,000001 单独是手或万元,差距 10000 倍)。AI 看到 days_to_exit=8.18 完全错误。

### 4. 沪深 300 全工具线不可用(S09-F07)

| 工具 | 沪深 300 状态 |
|---|---|
| `get_index_quote(000300)` | ❌ 三上游全跪 + name='??300' 编码乱码 |
| `get_realtime_quote(000300)` | ❌ validate.stock_code 拒绝 |
| `get_kline(000300)` | ❌ db + data_source + baostock 三层全跪,21s 超时 |
| `benchmark_comparison(000300)` | ❌ benchmark_series_days=0 degraded ✅(显式) |

**国内最重要基准沪深 300 在三工具线全跪**,backtest benchmark_return=null,所有需要基准对比的工具完全不可用。

### 5. Barra Risk 因子模型半瘫(S09-F08)

```
factor_names         = [momentum, volatility, size, value, quality]
portfolio_exposure   = [-0.0301,  0.0161,    0.0,  0.0,   0.0  ]
                                              ↑     ↑      ↑
                                              size/value/quality 全 0(没真正算)

factor_contribution  = 23.15%
specific_contribution = 76.85%   ← 个股特质风险占主导,因子模型几乎没解释力
```

5 因子里只有 momentum/volatility 有 exposure,**3 个核心因子 size/value/quality 全 0**。AI 看 Barra 以为做了多因子归因,实际半瘫。

### 6. performance_manager 三大问题(S09-F06 / S09-F10)

```
calculate_metrics:
  total_return         = 0.00%       ← 账户视角(无 paper trade)
  series_total_return  = 12.27%      ← 持仓估值视角
  annualized_return    = 13.31%
  sharpe_ratio         = 0.80
  trading_stats.total_trades = 0     ← 真没交易
  
  → total vs series 矛盾,口径不显式

attribution:
  stock_selection.return    = 0.00%        ← 全部 0!
  sector_allocation.return  = 8.98%        ← 全部 8.98% 算到 sector
  timing.return             = -0.68%
  
  attribution_by_stock.600519:
    stock_return    = -18.25%   ← 252d period
    lifetime_return = -29.40%   ← 从 cost_price 算
    delta = 11.15% — 两个口径混合,AI 看不出哪个是真正"组合表现"

benchmark_comparison(000300):
  benchmark_series_days = 0           ← 沪深 300 拿不到
  excess_return = null
  ✅ degraded=true fallback_used=true reason="insufficient aligned"  ← 这次降级路径正确
```



### 7. 单位/字段语义错误集中爆发

| 问题 | 工具 | 详情 |
|---|---|---|
| `volatility` 单位不标 | `calculate_var` | 0.61% 是 daily 还是 annual? |
| `pe` `pb` 指数错误概念 | (S07-F06 复现) | - |
| `change` = `shares` | `get_north_fund_holding` | **change 应当是 delta 不是 absolute**(语义错) |
| `mainNetInflow=0` 但 7/8 字段 null | `get_stock_fund_flow` | 数据完整性低 |
| `data_timestamp` 53 天前 | `get_north_fund_holding` | freshness_sla 没 fail(因为字段名 mismatch) |

## ✅ Positive evidence(4 条)

### S09-F14:VaR 三方法高度一致 ✅

```
99% VaR (1M, 252d):
  parametric    = 14005
  monte_carlo   = 14262    ← Δ=1.83% 在合理 noise
  cvar (all)    = 15025    ← 完全一致
```

VaR 数学层 robust ✅。

### S09-F15:run_simple_backtest 输出产品级回测包 ✅

```
600519 buy_and_hold 1Y:
  total_return=-15.72%  max_dd=17.03%  trades=1  turnover=1.84
  equity_curve = 251 天完整
  cost_assumptions = 8 bps (commission 3 + slippage 5)
  execution_reality.warnings = 3 条(收盘价/无市场冲击/不等于实盘)
  promotion_gate = 6 项完整(min_sharpe/min_win_rate/max_dd/min_trade_count/min_incubation_days/min_statistical_checks)
  implementation_shortfall_components = 6 子项(arrival/tradability/capacity/effective_slippage/market_impact)
```

这是回测工具最完整的产品级输出。

### S09-F16:portfolio CRUD 全链路 + data_validation GE 都 100%

```
portfolio.create(portfolio_id=3) → add_holding × 5 → get_holdings(count=5)  ✅
data_validation(GE)
  validation_id = val-e8933820055e
  evaluated     = 2  successful = 2  100% pass
```

状态管理工具是**最稳定的层**(S07/S08/S09 三场景全部一致 ✅)。

### risk_budget 严格匹配 budget ✅

```
risk_budgets = [0.4, 0.2, 0.1, 0.2, 0.1]
risk_contributions = [0.40000, 0.20001, 0.10002, 0.20005, 0.09992]
误差 < 0.0001  ← risk_budget 优化求解器精度 ✅
```

## 🚨 工具间数据不一致(本场景新增 16 条 finding,其中 high 8 条)

### 8 条 high

- **S09-F01**:black_litterman 99.46% + 000001=-26.87% 极端不可执行权重
- **S09-F02**:max_sharpe sharpe=-2.67 仍 success=true 不警告
- **S09-F03**:mean_variance 600519≈0 / 601857=63.9% 与基本面相反
- **S09-F04**:stress_test sector_rotation 硬编码不识别持仓行业
- **S09-F05**:平安银行 000001 流动性单位错误(122K vs 几十亿)
- **S09-F06**:attribution stock_selection 全 0 + lifetime / period 口径混合
- **S09-F07**:沪深 300 三工具线全跪(国内最重要基准失效)
- **S09-F08**:Barra size/value/quality 全 0(因子模型半瘫)

### 5 条 medium

- S09-F09:optimize_portfolio 接受 unknown_code + single stock + numpy shape 异常
- S09-F10:calculate_metrics total_return vs series_total_return 矛盾(0% vs 12.27%)
- S09-F11:stress_test_portfolio vs risk_manager.stress_test 双工具两套模型
- S09-F12:get_north_fund_holding change=shares 语义错 + 53 天前 stale
- S09-F13:experiment_tracker mlflow→builtin silent fallback(S08-F04 复现)

### 3 条 low(positive evidence)

- **S09-F14** ✅:VaR 三方法 99% 高度一致
- **S09-F15** ✅:run_simple_backtest 输出产品级回测包(equity_curve + execution_reality + promotion_gate)
- **S09-F16** ✅:portfolio CRUD + data_validation GE 全链路 100% 通过

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `portfolio_id=3` | **persist** | 5 sectors mix 持仓 stateful |
| `val-e8933820055e` | dataset_id | data_validation,GE backend,2/2 pass |
| `run-2ac7030cb63b` | experiment_run | builtin_fallback(in-memory,服务重启即丢) |
| `log_recommendation_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s09_audit action=hold |
| ~25 个 audit_event_id | read_only | optimize × 9 / risk × 6 / stress × 2 / barra / performance × 3 / portfolio × 7 + market 工具 |

## 🚨 Fail
无(S09 中 risk_budget shape mismatch 是 Fail-internal-error 但 success=false + error 显式;000300 三工具拒绝是 graceful 错误)。

## ➡ 进度

- 累计调用工具(去重): **~137/161**(S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6 + S07 +5 + S08 +14 + S09 +12)
- 已通过场景: **8/22**
- 累计 Fail: **0**
- 累计推荐 bug: **69 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16,其中 high 累计 **34 条**)

## 关键观察:S09 暴露了"组合优化数学边界 + 风险归因半瘫 + 基准不可用"三连击

**S07** 是金融数学边界 + ETF 代码识别;**S08** 是量化数学统计严谨 + 策略工厂闭环;**S09** 暴露的是**组合优化数学层 + 风险归因层的系统性缺陷**。

**核心问题模式**:

1. **优化方法不验证可执行性**(S09-F01/F02/F03):black_litterman 输出 99.46% 集中 + -26.87% 做空;max_sharpe 输出负 sharpe;mean_variance 与基本面常识反向 — 4 个方法都不验证 long_only / max_weight / sharpe>0 等基本约束
2. **stress_test 不基于实际持仓**(S09-F04):硬编码 '科技-10% / 金融+5%' 字典,不查 sector_exposure,给出"-2% rotation 损失"完全脱离持仓
3. **Barra 多因子半瘫**(S09-F08):5 因子里 3 个 (size/value/quality) 完全没算,specific_contribution=76.85% 因子模型基本失效
4. **基准缺失**(S09-F07):沪深 300 三工具线全跪,所有需要基准对比的工具(backtest / benchmark_comparison / attribution)都拿不到 baseline_return
5. **单位/字段语义错误集中**(S09-F05/F12):平安银行 avg_daily_amount 单位差 10000 倍;north_fund_holding change=shares 不是 delta;volatility 单位不标
6. **silent fallback 链复现**(S09-F13/S08-F04):mlflow→builtin / sector hardcode / 双工具两套 stress 模型
7. **attribution 半瘫**(S09-F06):stock_selection.return 全 0;period vs lifetime 两口径混合 AI 看不清
8. **优化求解器边界 + numpy 异常透出**(S09-F09):unknown_code 不警告 / single stock 不退化 / shape mismatch 异常透出(同 S07-F07 / S08 模式累计 3 次)

**positive 证据**(4 条):

- VaR 三方法在 99% 高度一致 ✅(数学层 robust)
- run_simple_backtest 是产品级回测最完整的输出(equity_curve / execution_reality / promotion_gate / cost_assumptions / implementation_shortfall 5 个子模块)
- portfolio CRUD 全链路 + data_validation GE 100%(状态管理层最稳定)
- risk_budget 严格匹配 budget(误差 <1e-4)

**关键洞察**:**数学核心层(VaR / BS Greeks / risk_budget)是 robust 的,但金融语义层(优化方法约束 / stress 模型 / 单位 / 字段语义 / 基准可用性)漏洞严重**。这是 S07-S09 一直在重复的核心模式。
