# 回测指标契约（Metrics Contract）

本文档定义回测引擎输出的核心指标计算公式、数据口径和一致性要求。
所有 JIT 路径（`strategies.py`）和 mask 路径（`engine.py`）必须遵守同一契约。

## 核心指标

### 1. sharpe_ratio（夏普比率）

```
daily_returns[i] = (equity[i+1] - equity[i]) / equity[i]  (仅 equity[i] > 0 时计入)
sharpe = mean(daily_returns) × 252 / (std(daily_returns) × √252)
```

- 包含零收益日（不过滤 `returns == 0`）
- 仅排除 equity 为零的无效日（`equity[i] > 0` 过滤）
- 年化因子：252 个交易日

### 2. win_rate（胜率）

```
win_rate = profitable_round_trips / total_round_trips
```

- 一买一卖为一个 round-trip
- 仅计算已平仓的 round-trip（末尾强制平仓也计入）
- JIT 路径中 `trades` 计数买+卖两侧时：`win_rate = wins / max(1, trades // 2)`
- JIT 路径中 `trades` 仅计买入时：`win_rate = wins / trades`（如 ma_cross）

### 3. max_drawdown（最大回撤）

```
peak = running_max(equity[start:])
drawdown[i] = (peak[i] - equity[i]) / peak[i]  (peak > 0)
max_drawdown = max(drawdown)
```

- start 为策略生效起始 bar（如 `long_period`、`lookback`、`rsi_period`）
- 使用 mark-to-market equity（当日收盘价计算持仓市值）

### 4. total_return（总收益率）

```
total_return = (final_capital - initial_capital) / initial_capital
```

- `final_capital` 为全部持仓按末日收盘价强制平仓后的现金
- 包含交易成本（佣金 + 滑点）

### 5. trades_count（交易次数）

- 统计口径：round-trip 数（一买一卖为 1 次）
- JIT 路径返回值中 `trades` 可能是单边计数，由 engine.py 层统一转换

### 6. equity_curve（权益曲线）

- 降采样至最多 500 个点：`step = max(1, len(equity) // 500)`
- 每个点为当日 mark-to-market 值：`cash + shares × close[i]`
- 附带 `slippage_model_note` 说明滑点模型局限性

### 7. annual_return（年化收益率）

```
annual_return = (final_capital / initial_capital) ^ (252 / valid_return_days) - 1
```

- `valid_return_days` 为权益曲线中可计算日收益的有效天数
- 仅在 `initial_capital > 0` 且存在有效收益序列时计算

### 8. annual_volatility（年化波动率）

```
annual_volatility = std(daily_returns) × √252
```

### 9. sortino_ratio（索提诺比率）

```
sortino = (annual_return - risk_free_rate) / downside_volatility
```

- `risk_free_rate` 当前固定为年化 `2%`
- `downside_volatility` 仅使用负收益日计算

### 10. calmar_ratio（卡玛比率）

```
calmar = annual_return / max_drawdown
```

### 11. omega_ratio（Omega 比率）

```
omega = sum(max(daily_returns, 0)) / sum(max(-daily_returns, 0))
```

### 12. benchmark_return / excess_return（可选）

- 若 `params` 中提供 `benchmark_returns` 或 `benchmark_klines`，则输出：
  - `benchmark_return`
  - `excess_return`
  - `information_ratio`
- 若未提供基准数据，上述字段允许为 `null`

## 信号执行规则

- 信号在 bar[i] 产生 → 以 bar[i+1] 的 close 价格执行
- 循环范围：`range(start, n - 1)`（预留 i+1 执行空间）
- 循环后补充：`equity[n-1] = cash + shares × closes[n-1]`
- 权益标记仍用当日 close（mark-to-market）

## 一致性要求

| 指标 | JIT 路径 | Mask 路径 | 允许差异 |
|------|---------|----------|---------|
| sharpe_ratio | `equity > 0` 过滤 | `eq_prev > 0` 过滤 | < 0.01 |
| win_rate | `wins / max(1, trades//2)` | `wins / max(1, trades//2)` | 0 |
| max_drawdown | 逐 bar 遍历 | 逐 bar 遍历 | < 0.001 |
| total_return | 强制平仓后计算 | 强制平仓后计算 | < 0.001 |
| annual_return | 由同一权益曲线推导 | 由同一权益曲线推导 | < 0.01 |
| calmar_ratio | 由同一收益/回撤推导 | 由同一收益/回撤推导 | < 0.05 |

## 回归基线

对同一股票（如 600519）、同一策略（ma_cross, short=5, long=20）、同一时间段：
- JIT 路径和 mask 路径的 sharpe_ratio 差异 < 0.01
- win_rate 完全一致
- total_return 差异 < 0.1%
