# 场景10：期权策略分析

## 用户故事

**As a** 期权交易者
**I want** 查看ETF期权链数据，计算期权的Greeks和理论价格
**So that** 我可以选择合适的期权合约构建交易策略

## 业务流程

```
选择标的 → 获取期权链 → BS定价 → Greeks计算 → 策略构建 → 风险评估
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `get_option_chain` | 获取ETF期权链数据 |
| 2 | `options_manager` | 期权管理器（BS定价/Greeks计算） |
| 3 | `get_realtime_quote` | 获取标的ETF实时价格 |
| 4 | `get_kline` | 获取标的历史波动率数据 |

## 测试步骤

### Step 1: 获取标的ETF行情

```
调用: get_realtime_quote
参数: stock_code="510050"（50ETF）
预期: 返回50ETF最新价格
验证: price > 0，作为期权定价的标的价格
```

### Step 2: 获取期权链

```
调用: get_option_chain
参数: underlying="510050", limit=50
预期: 返回50ETF期权链（认购+认沽）
验证: 包含行权价/到期日/最新价/隐含波动率等字段
      认购和认沽合约数量基本对称

调用: get_option_chain
参数: underlying="510300", expiry_month="2026-03"
预期: 返回300ETF 2026年3月到期的期权合约
验证: 所有合约到期月份为2026-03
```

### Step 3: Black-Scholes定价

```
调用: options_manager
参数: action="calculate_price", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.2,"option_type":"call"}'
预期: 返回认购期权理论价格
验证: 理论价格 > 0，平值期权价格约为标的价格的5-10%
注意: action 为 "calculate_price"（非 "bs_price"）
      参数名使用规范名称: spot/strike/time_to_maturity/risk_free_rate/volatility/option_type
      也支持别名: S/K/T/r/sigma/type 等（内部自动映射）

调用: options_manager
参数: action="calculate_price", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.2,"option_type":"put"}'
预期: 返回认沽期权理论价格
验证: Put-Call Parity: C - P ≈ S - K*e^(-rT)
```

### Step 4: Greeks计算

```
调用: options_manager
参数: action="calculate_greeks", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.2,"option_type":"call"}'
预期: 返回Delta/Gamma/Theta/Vega/Rho
注意: action 为 "calculate_greeks"（非 "greeks"）
验证: 
  - Delta: 平值认购约0.5，范围[0,1]
  - Gamma: > 0，平值最大
  - Theta: < 0（时间价值衰减）
  - Vega: > 0（波动率敏感度）
  - Rho: 认购>0，认沽<0
```

### Step 5: 不同行权价对比

```
调用: options_manager
参数: action="calculate_greeks", kwargs='{"spot":3.5,"strike":3.0,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.2,"option_type":"call"}'
预期: 实值认购期权Greeks
验证: Delta > 0.5（实值期权Delta更高）

调用: options_manager
参数: action="calculate_greeks", kwargs='{"spot":3.5,"strike":4.0,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.2,"option_type":"call"}'
预期: 虚值认购期权Greeks
验证: Delta < 0.5（虚值期权Delta更低）
```

### Step 6: 历史波动率参考

```
调用: get_kline
参数: stock_code="510050", period="daily", limit=60
预期: 返回60日K线数据
验证: 可用于计算历史波动率（年化），作为BS模型sigma参数参考
```

## TDX 前端交互

- 本场景不直接涉及TDX联动
- 期权分析结果可通过 `push_message` 推送到通达信
- 通达信本身支持期权T型报价，MCP提供补充分析

### Step 7: 极端参数数值稳定性测试

```
调用: options_manager
参数: action="calculate_price", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.001,"risk_free_rate":0.03,"volatility":0.2,"option_type":"call"}'
预期: 临近到期（T≈0）期权价格接近内在价值
验证: 平值期权价格接近0（时间价值极小），不出现NaN或异常值

调用: options_manager
参数: action="calculate_greeks", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":1.5,"option_type":"call"}'
预期: 极端高波动率（150%）下的Greeks
验证: 各Greeks值为有限数值（非NaN/Inf），Delta仍在[0,1]范围内

调用: options_manager
参数: action="calculate_price", kwargs='{"spot":3.5,"strike":3.5,"time_to_maturity":0.25,"risk_free_rate":0.03,"volatility":0.01,"option_type":"call"}'
预期: 极低波动率下期权价格接近内在价值的折现
验证: 价格为正数，不出现数值异常
```

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 标的代码非ETF | 提示仅支持上交所ETF期权 |
| 到期月份无合约 | 返回空列表 |
| BS参数不合理（sigma=0） | 返回参数错误提示 |
| 深度虚值期权 | 理论价格接近0，Greeks极小 |
| 到期日为0（T=0） | 期权价值等于内在价值 |
| 极端高波动率（volatility>1） | 应返回有限数值，不出现NaN/Inf |
| time_to_maturity≈0 | 期权价格收敛到内在价值，Greeks可能出现极端值（Gamma极大） |
| 期权链数据延迟 | 使用最近可用数据 |

## 已知限制

- 仅支持上交所ETF期权（50ETF/300ETF），不支持个股期权
- BS模型为欧式期权定价模型（上交所ETF期权为欧式，适用）；美式期权不适用Black-Scholes闭式解，需使用二叉树或蒙特卡洛方法
- BS模型假设波动率恒定，实际市场存在波动率微笑
- Greeks为瞬时值，随标的价格和时间变化
- 期权链数据来源为新浪直连HTTP API → AkShare降级
- 不支持期权组合策略（如跨式/蝶式）的自动构建，需手动计算
- `options_manager` 支持的 action: `calculate_price`/`calculate_greeks`/`implied_volatility`/`help`/`list`
- 参数支持别名映射（如 S→spot, K→strike, T→time_to_maturity, r→risk_free_rate, sigma→volatility），但建议使用规范名称
