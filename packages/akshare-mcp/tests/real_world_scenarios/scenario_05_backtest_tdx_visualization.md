# 场景05：策略回测与TDX可视化

## 用户故事

**As a** 策略开发者
**I want** 对均线交叉策略进行回测，并将买卖信号发送到通达信客户端可视化展示
**So that** 我可以在通达信K线图上直观看到策略的买卖点和收益曲线

## 业务流程

```
选择策略 → 单股回测 → 查看交易明细 → 发送回测数据到TDX → 批量回测对比 → TDX可视化
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `run_simple_backtest` | 运行简单回测（获取绩效指标） |
| 2 | `run_backtest_with_trades` | 运行回测并返回交易明细 |
| 3 | `send_backtest_result` | 发送回测信号数据到TDX |
| 4 | `send_backtest_trades` | 发送交易记录到TDX |
| 5 | `run_batch_backtest` | 批量回测多只股票 |
| 6 | `run_backtest_and_send_to_tdx` | 一键回测+TDX可视化 |
| 7 | `backtest_manager` | 回测管理（保存/查询历史） |

## 测试步骤

### Step 1: 单股简单回测

```
调用: run_simple_backtest
参数: code="600519", strategy="ma_cross", start_date="2025-01-01", end_date="2025-12-31", initial_capital=100000, short_period=5, long_period=20
预期: 返回回测绩效指标
验证: 包含 total_return/max_drawdown/sharpe_ratio/win_rate/trades_count 字段
      total_return 为浮点数，max_drawdown < 0
注意: 默认 commission=0.0003 偏低于A股实际交易成本（佣金约万2.5+印花税千1≈万3.5单边），
      如需贴近实际，建议设置 commission=0.001
```

### Step 2: 回测含交易明细

```
调用: run_backtest_with_trades
参数: code="600519", strategy="ma_cross", start_date="2025-01-01", end_date="2025-12-31", short_period=5, long_period=20
预期: 返回绩效指标 + trades 交易明细列表
验证: trades 列表非空，每条记录包含 date/action(buy/sell)/price/shares
      买入和卖出交易数量基本匹配
```

### Step 3: 发送回测信号到TDX

```
调用: send_backtest_result
参数: stock_code="600519", time_list=["20250115","20250320","20250610","20250901"], data_list=[["B"],["S"],["买入"],["HOLD"]], count=1
预期: success=true，信号自动转换（B→"1", S→"-1", 买入→"1", HOLD→"0"）
验证: 通达信K线图上显示买卖标记
```

### Step 4: 发送交易记录到TDX

```
调用: send_backtest_trades
参数: stock_code="600519", trades=[{"time":"20250115","price":1800,"signal":"buy","shares":100,"profit":0},{"time":"20250320","price":1950,"signal":"sell","shares":100,"profit":150},{"time":"20250610","price":1850,"signal":"buy","shares":100,"profit":0},{"time":"20250901","price":2000,"signal":"sell","shares":100,"profit":150}]
预期: success=true
验证: 通达信客户端显示交易记录（至少4条满足TDX最低要求）
注意: trades 每条记录需包含 time/price/signal/shares/profit 字段
      如不足4条，系统自动用空记录填充
```

### Step 5: 批量回测

```
调用: run_batch_backtest
参数: codes=["600519","000858","300750","601318","600036"], strategy="ma_cross", start_date="2025-01-01", end_date="2025-12-31", short_period=5, long_period=20
预期: 返回5只股票的回测结果
验证: 每只股票有独立的绩效指标，可按 sharpe_ratio 排序
      批量回测耗时 < 5秒
```

### Step 6: 一键回测+TDX可视化

```
调用: run_backtest_and_send_to_tdx
参数: code="000858", strategy="ma_cross", start_date="2025-01-01", end_date="2025-12-31", short_period=5, long_period=20
预期: 回测完成并自动发送到TDX
验证: 返回回测结果 + tdx_send_result 字段
      tdx_send_result.success=true 表示TDX发送成功
      如 trades 为空，tdx_send_result.success=false 且 message="No trades to send"
```

## TDX 前端交互

- 通达信K线图上叠加显示买卖信号标记
- 买入信号：红色向上箭头（data_list中的"1"）
- 卖出信号：绿色向下箭头（data_list中的"-1"）
- 持有信号：无标记（data_list中的"0"）
- 交易记录在通达信的回测面板中展示

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 回测区间无交易信号 | 返回空trades列表，绩效为0 |
| 交易记录不足4条 | send_backtest_trades 自动填充空记录 |
| 信号格式非标准 | _SIGNAL_MAP 自动转换（B/BUY/买入→"1"） |
| 起止日期格式错误 | 支持 YYYY-MM-DD 和 YYYY 两种格式 |
| 股票在回测期间停牌 | 跳过停牌日，使用复牌后价格 |
| TDX客户端未启动 | 回测正常完成，TDX发送失败 |

## 已知限制

- 当前仅支持 `ma_cross`（均线交叉）、`buy_and_hold`（买入持有）、`momentum`（动量）、`rsi` 四种内置策略
- 不支持自定义策略代码，需通过修改源码添加
- 批量回测使用Ray并行加速，需安装ray包；未安装时自动降级为顺序执行，耗时可能超过5秒基准
- `send_backtest_result` 的 time_list 格式必须为 YYYYMMDD
- TDX客户端要求至少4条时间记录才能正常显示
- 回测使用当前存在的股票数据，未考虑历史退市股票（幸存者偏差），回测收益可能偏乐观
