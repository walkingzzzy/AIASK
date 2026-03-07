# 场景01：盘前选股与自选股同步

## 用户故事

**As a** 短线交易者
**I want** 每天开盘前通过技术面条件筛选出当日潜力股，并自动同步到通达信自选股
**So that** 我可以在通达信客户端直接监控这些股票的盘中走势

## 业务流程

```
盘前(9:00) → TDX条件选股 → 技术指标验证 → 创建自选股板块 → 通达信监控
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `tdx_screen_stocks` | TDX公式条件选股（如"UPN"放量上攻） |
| 2 | `calculate_technical_indicators` | 验证RSI/MACD/KDJ信号 |
| 3 | `get_batch_quotes` | 批量获取候选股实时行情 |
| 4 | `get_stock_info` | 获取基本面快照（排除ST/退市） |
| 5 | `create_watchlist` | 创建TDX自选股板块 |
| 6 | `add_stocks_to_watchlist` | 添加筛选结果到板块 |

## 测试步骤

### Step 1: TDX 条件选股

```
调用: tdx_screen_stocks
参数: formula_name="UPN", period="1d", count=100
预期: 返回符合条件的股票列表（10-50只）
验证: 每只股票有 code/name 字段
```

### Step 2: 技术指标二次筛选

```
调用: calculate_technical_indicators
参数: code=<选股结果前5只>, indicators=["RSI","MACD","KDJ"]
预期: RSI<70（非超买）, MACD金叉或即将金叉, KDJ-J<80
验证: 指标值在合理范围内
```

### Step 3: 批量行情确认

```
调用: get_batch_quotes
参数: stock_codes=<二次筛选结果>
预期: 返回最新价/涨跌幅/成交量
验证: 数据源为 tdxquant 或 tushare
```

### Step 4: 基本面与流动性过滤

```
调用: get_stock_info
参数: stock_code=<每只候选股>
预期: 排除 ST/*ST 股票、停牌股票
验证: 返回行业/总股本/流通股本

流动性过滤（基于 Step 3 行情数据）:
- 成交额 > 5000万（排除低流动性标的）
- 换手率 > 1%（排除冷门股）
- 非停牌状态（涨跌幅≠0 或有成交量）
注意: 流动性阈值可根据市场环境调整，此处为参考值
```

### Step 5: 同步到通达信

```
调用: create_watchlist
参数: block_code="MCP_MORNING", block_name="盘前选股", stock_codes=<最终结果>
预期: success=true
验证: 通达信客户端可见新板块
```

## TDX 前端交互

- 通达信自选股面板出现"盘前选股"板块
- 板块内包含筛选出的股票列表
- 用户可在通达信中直接查看这些股票的分时/K线

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 选股结果为空 | 返回空列表，不创建板块 |
| 选股结果超过50只 | 取前20只（按涨幅排序） |
| 部分股票停牌 | 在基本面排除步骤过滤 |
| TDX客户端未启动 | push/watchlist 返回失败提示 |
| TdxQuant不可用（tdx_screen_stocks失败） | 降级到 `screener_manager`(action="technical_screen") 或 `search_stocks` 进行条件筛选 |
| 非交易日执行 | 使用最近交易日数据 |

## 已知限制

- `tdx_screen_stocks` 需要通达信客户端运行且 TdxQuant 可用；不可用时可降级到 `screener_manager` 或 `search_stocks`，但筛选精度和公式丰富度会下降
- 条件选股公式依赖通达信内置公式库，自定义公式需提前导入
- 盘前数据为前一日收盘数据，开盘后需刷新
- 流动性过滤阈值（成交额5000万、换手率1%）为经验参考值，不同市值区间可适当调整
