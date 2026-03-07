# 场景06：组合风险管理

## 用户故事

**As a** 组合管理者
**I want** 对我的投资组合进行风险分析、权重优化和压力测试
**So that** 我可以在风险可控的前提下最大化组合收益

## 业务流程

```
组合构建 → 风险分析 → 权重优化 → 压力测试 → VaR计算 → 调仓建议
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `portfolio_manager` | 创建/管理投资组合 |
| 2 | `analyze_portfolio_risk` | 组合风险分析（波动率/相关性/Beta） |
| 3 | `optimize_portfolio` | 组合权重优化（6种方法） |
| 4 | `stress_test_portfolio` | 压力测试（市场崩盘/板块轮动） |
| 5 | `risk_manager` | VaR计算、风险敞口分析 |
| 6 | `get_batch_quotes` | 获取组合成分股行情 |

## 测试步骤

### Step 1: 构建投资组合

```
调用: analyze_portfolio_risk
参数: codes=["600519","601318","300750","600036","000858"], weights=[0.3,0.2,0.2,0.15,0.15], lookback_days=252
预期: 返回组合风险指标
验证: 返回 data 包含 var 和 risk 两个子结构
      data.var 包含 VaR/CVaR 等风险度量
      data.risk 包含波动率/相关性/Beta等组合风险指标
```

### Step 2: 等权重优化

```
调用: optimize_portfolio
参数: codes=["600519","601318","300750","600036","000858"], method="equal_weight"
预期: 返回等权重分配（各20%）
验证: 所有权重相等，总和为1.0
```

### Step 3: 风险平价优化

```
调用: optimize_portfolio
参数: codes=["600519","601318","300750","600036","000858"], method="risk_parity", lookback_days=252
预期: 返回风险贡献均等的权重
验证: 低波动股票权重更高，各资产风险贡献接近
```

### Step 4: 最大夏普比率优化

```
调用: optimize_portfolio
参数: codes=["600519","601318","300750","600036","000858"], method="max_sharpe", risk_free_rate=0.03
预期: 返回夏普比率最大化的权重
验证: 组合夏普比率 > 等权重组合的夏普比率
```

### Step 5: 均值方差优化

```
调用: optimize_portfolio
参数: codes=["600519","601318","300750","600036","000858"], method="mean_variance", risk_aversion=1
预期: 返回均值方差最优权重
验证: 权重总和为1.0，无负权重（无做空）
```

### Step 6: 压力测试

```
调用: stress_test_portfolio
参数: codes=["600519","601318","300750","600036","000858"], weights=[0.3,0.2,0.2,0.15,0.15], scenarios=["market_crash","sector_rotation"]
预期: 返回各压力场景下的组合损失
验证: market_crash 场景包含 portfolio_loss/impact/stock_details/method 字段
      sector_rotation 场景包含 avg_correlation/impact/recommendation/method 字段
      损失值为负向冲击（不做固定大小关系断言，因两种场景计算方法不同）
```

### Step 7: VaR风险计算

```
前置条件: risk_manager 的 calculate_var/stress_test/risk_exposure 均需要 portfolio_id 参数，
          必须先通过 portfolio_manager 创建组合并添加持仓。

调用: portfolio_manager
参数: action="create", kwargs='{"name":"测试组合"}'
预期: 返回 portfolio_id

调用: portfolio_manager
参数: action="add_holding", kwargs='{"portfolio_id":"<上一步返回的id>","code":"600519","shares":100}'
预期: 持仓添加成功（重复为每只股票添加）

调用: risk_manager
参数: action="calculate_var", kwargs='{"portfolio_id":"<组合id>","confidence":0.95,"method":"historical"}'
预期: 返回95%置信度的VaR和CVaR值
验证: 包含 var.percentage/var.amount/cvar.percentage/cvar.amount/volatility/max_drawdown 字段
      method 支持 historical/parametric/monte_carlo 三种方法

调用: risk_manager
参数: action="stress_test", kwargs='{"portfolio_id":"<组合id>","scenario":"market_crash"}'
预期: 返回市场暴跌场景下的组合损失
验证: 包含 current_value/stressed_value/loss/loss_percentage/severity/recommendation 字段
      scenario 支持: market_crash/black_swan/interest_rate_hike/sector_rotation/liquidity_crisis

调用: risk_manager
参数: action="risk_exposure", kwargs='{"portfolio_id":"<组合id>"}'
预期: 返回组合风险敞口和集中度分析
验证: 包含 stock_exposure/sector_exposure/concentration_risk/diversification 字段

注意: risk_manager 不接受 codes/weights 参数，只接受 portfolio_id。
      如需快速分析无需创建组合，使用 analyze_portfolio_risk 和 stress_test_portfolio 工具（直接接受 codes+weights）。
```

## TDX 前端交互

- 本场景不直接涉及TDX联动
- 优化后的组合可通过 `create_watchlist` 同步到通达信监控
- 压力测试结果可通过 `push_message` 推送到通达信

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 组合仅1只股票 | 退化为单股风险分析 |
| 股票数据不足252天 | 使用可用数据，提示数据不足 |
| 优化结果权重为0 | 表示该股票不应纳入组合 |
| 相关性矩阵不正定 | 使用最近正定矩阵近似 |
| 所有股票高度相关 | 风险平价退化为等权重 |
| 压力场景名称错误 | 返回支持的场景列表 |

## 已知限制

- 组合优化基于历史数据，不保证未来表现
- Black-Litterman模型需要用户提供主观观点（views参数）
- 风险预算优化需要用户指定各资产的风险预算比例
- 压力测试使用预设场景（market_crash/black_swan/interest_rate_hike/sector_rotation/liquidity_crisis），不支持自定义压力参数
- `risk_manager` 的 calculate_var/stress_test/risk_exposure 均需要 portfolio_id，必须先通过 portfolio_manager 创建组合并添加持仓
- 如需快速分析（不创建组合），使用 `analyze_portfolio_risk` 和 `stress_test_portfolio` 独立工具（直接接受 codes+weights 参数）
- VaR计算支持 historical/parametric/monte_carlo 三种方法，极端行情下可能低估风险
