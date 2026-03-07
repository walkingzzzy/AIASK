# 场景12：跨周期技术共振选股

## 用户故事

**As a** 趋势交易者
**I want** 在日线、周线、月线多个周期上同时满足技术条件的股票
**So that** 我可以找到多周期共振的强势股，提高交易胜率

## 业务流程

```
日线指标扫描 → 周线指标验证 → 月线趋势确认 → TDX条件选股 → 专家系统信号 → 创建自选股
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `tdx_calculate_macd` | 计算MACD（日/周/月线） |
| 2 | `tdx_calculate_rsi` | 计算RSI（日/周/月线） |
| 3 | `tdx_calculate_boll` | 计算布林带（日线） |
| 4 | `tdx_calculate_kdj` | 计算KDJ（日线） |
| 5 | `tdx_calculate_expma` | 计算EXPMA（日线） |
| 6 | `tdx_calculate_dmi` | 计算DMI趋势指标 |
| 7 | `tdx_screen_stocks` | TDX条件选股 |
| 8 | `tdx_get_expert_signals` | 获取专家系统买卖信号 |
| 9 | `tdx_get_formula_data` | 获取公式系统K线数据 |
| 10 | `create_watchlist` | 创建共振选股板块 |

## 测试步骤

### Step 1: 日线MACD筛选

```
调用: tdx_calculate_macd
参数: stock_code="600519", period="1d", count=50
预期: 返回日线MACD数据（DIF/DEA/MACD柱）
验证: 最新DIF > DEA 表示日线MACD金叉
      MACD柱由负转正表示趋势转多

调用: tdx_calculate_macd
参数: stock_code="000858", period="1d", count=50
预期: 返回五粮液日线MACD
验证: 对比两只股票的MACD状态
```

### Step 2: 周线MACD确认

```
调用: tdx_calculate_macd
参数: stock_code="600519", period="1w", count=30
预期: 返回周线MACD数据
验证: 周线DIF > DEA 表示中期趋势向上
      日线+周线同时金叉 = 双周期共振
```

### Step 3: 月线趋势验证

```
调用: tdx_calculate_macd
参数: stock_code="600519", period="1M", count=24
预期: 返回月线MACD数据
验证: 月线DIF > 0 表示长期趋势向上
      三周期共振（日+周+月MACD均多头）为最强信号
```

### Step 4: RSI多周期验证

```
调用: tdx_calculate_rsi
参数: stock_code="600519", period="1d", count=50
预期: 返回日线RSI（6/12/24日）
验证: RSI6 > RSI12 > RSI24 表示多头排列

调用: tdx_calculate_rsi
参数: stock_code="600519", period="1w", count=30
预期: 返回周线RSI
验证: 周线RSI在40-70之间（非超买超卖）
```

### Step 5: 布林带位置判断

```
调用: tdx_calculate_boll
参数: stock_code="600519", period="1d", count=50
预期: 返回布林带上轨/中轨/下轨
验证: 当前价在中轨上方表示偏强
      价格突破上轨需警惕回调
```

### Step 6: DMI趋势强度

```
调用: tdx_calculate_dmi
参数: stock_code="600519", period="1d", count=50
预期: 返回PDI/MDI/ADX/ADXR
验证: PDI > MDI 表示多头趋势
      ADX > 25 表示趋势明确
```

### Step 7: TDX条件选股

```
调用: tdx_screen_stocks
参数: formula_name="UPN", period="1d", count=100
预期: 返回符合放量上攻条件的股票
验证: 结果列表非空，每只股票有code/name

调用: tdx_screen_stocks
参数: formula_name="均线多头", period="1d", count=100
预期: 返回均线多头排列的股票
验证: 可与MACD筛选结果取交集
```

### Step 8: 专家系统信号

```
调用: tdx_get_expert_signals
参数: stock_code="600519", formula_name="CCI", period="1d", count=50
预期: 返回CCI专家系统的买卖信号
验证: latest_signal 字段表示最新信号（买入/卖出/无信号）

调用: tdx_get_expert_signals
参数: stock_code="600519", formula_name="BIAS", period="1d", count=50
预期: 返回BIAS乖离率信号
验证: 信号列表包含历史买卖点
⚠️ 已知限制: Python回退模式仅支持 MACD/KDJ/RSI/BOLL/CCI，不支持BIAS。需TdxQuant公式引擎可用时才能获取BIAS信号。
```

### Step 9: 获取公式K线数据

```
调用: tdx_get_formula_data
参数: stock_code="600519", period="1d", count=100, dividend_type=1
预期: 返回前复权日K线数据
验证: 包含 Date/Open/High/Low/Close/Volume/Amount 字段
      数据量等于请求的count
```

### Step 10: 创建共振选股板块

```
调用: create_watchlist
参数: block_code="MCP_RESONANCE", block_name="多周期共振", stock_codes=<筛选结果交集>
预期: success=true
验证: 通达信客户端出现"多周期共振"板块
```

## TDX 前端交互

- 通达信自选股面板出现"多周期共振"板块
- 用户可在通达信中切换日/周/月线验证共振状态
- 专家系统信号在通达信K线图上以箭头标记显示

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| TdxQuant不可用 | 所有tdx_*工具返回失败，提示需要通达信客户端 |
| 月线数据不足24根 | 使用可用数据，提示数据不足 |
| 条件选股结果为空 | 放宽条件或更换公式 |
| 多周期信号矛盾 | 以长周期为主，短周期为辅 |
| 专家系统公式不存在 | 返回错误，提示可用公式列表 |
| 共振股票数量过多 | 按ADX趋势强度排序取前20 |

## 已知限制

- 所有 `tdx_*` 工具依赖通达信客户端运行且TdxQuant可用
- `tdx_screen_stocks` 的公式名称依赖通达信内置公式库
- 月线数据量有限（24根=2年），长期趋势判断可能不够充分
- 专家系统信号为滞后指标，不能作为唯一交易依据
- 跨周期分析需要逐只股票逐周期计算，批量处理耗时较长
- `tdx_calculate_*` 系列工具每次只能计算一只股票，不支持批量

### 耗时基准参考

每只股票的多周期共振分析约需 7 次 TDX 调用（日/周/月 MACD + 日/周 RSI + BOLL + DMI），预估耗时：

| 股票数量 | 预估调用次数 | 预估耗时 |
|---------|------------|---------|
| 10只 | ~70次 | 10-15秒 |
| 50只 | ~350次 | 50-80秒 |
| 200只 | ~1400次 | 3-5分钟 |

建议：批量分析时先用 `tdx_screen_stocks` 缩小候选池（<20只），再逐只做多周期验证。

### 共振信号有效性说明

"多周期共振→胜率提升"是技术分析的经验假设，本场景仅验证工具链路的可执行性。
如需验证共振信号的实际有效性，建议：
- 使用 `run_batch_backtest` 对"共振信号股"和"非共振信号股"分别回测
- 对比两组的 total_return/max_drawdown/win_rate
- 样本期建议≥1年，避免短期偶然性
