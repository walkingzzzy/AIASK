# 交易决策核心工具参考

## 1. generate_trade_plan

**位置**：`akshare_mcp/tools/trade_plan.py`

### 参数

| 参数 | 类型 | 必选 | 默认值 | 说明 |
|------|------|------|--------|------|
| code | str | 是 | - | 股票代码（如 000988） |
| capital | float | 否 | 1000000 | 总资金（元） |
| risk_per_trade | float | 否 | 0.02 | 单笔风险比例 |
| style | str | 否 | "swing" | 交易风格：swing/short/trend |

### 返回结构

```json
{
  "code": "000988",
  "name": "华工科技",
  "current_price": 45.20,
  "regime": "bullish",
  "direction": "buy",
  "confidence": 0.72,
  "signal_summary": {
    "trend": {"signal": "MACD 多头", "detail": "..."},
    "trigger": {"signal": "RSI 回到 40", "detail": "..."},
    "confirmation": {"signal": "成交量放大 1.5x", "detail": "..."},
    "conflicts": "无"
  },
  "scenarios": [
    {
      "name": "回调买入",
      "condition": "价格回落至 44.00 支撑位企稳",
      "entry_price": 44.00,
      "stop_loss": 42.50,
      "take_profit": [46.80, 48.50],
      "position_shares": 400,
      "position_amount": 17600,
      "risk_reward": "1:1.87",
      "if_wrong": "跌破 42.50 止损离场，亏损 ≤ 600 元"
    }
  ],
  "key_levels": [...],
  "stop_levels": {...}
}
```

### 内部调用链

```
generate_trade_plan
  ├── get_stock_klines_data     → K 线数据
  ├── calculate_technical_indicators → MA/MACD/RSI/KDJ/BOLL/ATR
  ├── identify_candlestick_patterns  → K 线形态
  ├── get_stock_fund_flow            → 资金流（可降级）
  ├── compute_key_levels             → 关键价位
  └── compute_stop_levels            → 止损止盈与仓位
```

---

## 2. get_key_levels

**位置**：`akshare_mcp/tools/key_levels.py`

### 参数

| 参数 | 类型 | 必选 | 默认值 | 说明 |
|------|------|------|--------|------|
| code | str | 是 | - | 股票代码 |
| lookback_days | int | 否 | 120 | 回看天数 |

### 算法来源（多方法投票）

1. **经典枢轴点**：PP = (H+L+C)/3, 上下各 2 级
2. **成交密集区**：简化 Volume Profile，取成交量最密集价格区
3. **斐波那契回撤**：0.236 / 0.382 / 0.5 / 0.618 / 0.786
4. **波段高低点**：Zigzag 识别 + 聚类
5. **均线价位**：MA5 / MA10 / MA20 / MA60 当前值

### 合并与强度

- 多方法在 ±1% 容差内收敛的价位获得更高 strength（1-5）
- 每个价位附带 `confirmation` 和 `breach_action`

---

## 3. calculate_stop_levels

**位置**：`akshare_mcp/tools/stop_levels.py`

### 参数

| 参数 | 类型 | 必选 | 默认值 | 说明 |
|------|------|------|--------|------|
| code | str | 是 | - | 股票代码 |
| entry_price | float | 是 | - | 入场价 |
| direction | str | 否 | "long" | 方向（long/short） |
| atr_multiplier | float | 否 | 2.0 | ATR 止损倍数 |
| capital | float | 否 | 1000000 | 总资金 |
| risk_per_trade | float | 否 | 0.02 | 单笔风险比例 |

### 返回

```json
{
  "atr_stop": 42.80,
  "structural_stop": 43.10,
  "recommended_stop": 42.80,
  "take_profit_1": 46.00,
  "take_profit_2": 48.40,
  "take_profit_3": 50.80,
  "position_shares": 800,
  "position_amount": 36160,
  "max_loss": 1920,
  "trailing_stop_trigger": "最高价回撤 ATR×1.5"
}
```

### A 股特殊处理

- 仓位对齐到 100 股整数倍
- 结构止损 = 入场价下方最近支撑位 × 0.99
- 推荐止损 = min(ATR止损, 结构止损)
