# 场景04：持仓止盈止损监控

## 用户故事

**As a** 持仓管理者
**I want** 对已持有的股票设置止盈止损告警，并实时监控卖出时机
**So that** 我可以在通达信客户端及时收到预警信号，避免错过最佳卖出点

## 业务流程

```
持仓录入 → 卖出建议分析 → 创建价格告警 → 创建指标告警 → 组合告警 → 检查告警 → TDX预警推送
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `should_i_sell` | 综合卖出建议（止盈止损+技术信号） |
| 2 | `get_realtime_quote` | 获取当前价格 |
| 3 | `create_indicator_alert` | 创建单指标告警（价格/RSI/MACD） |
| 4 | `create_combo_alert` | 创建组合告警（多条件联合触发） |
| 5 | `check_all_alerts` | 检查所有告警状态 |
| 6 | `alerts_manager` | 告警管理（查询/更新/删除） |
| 7 | `push_warn` | 推送卖出预警到TDX |

## 测试步骤

### Step 1: 卖出建议分析

```
调用: should_i_sell
参数: code="600519", buy_price=1800, holding_days=30
预期: 返回卖出/持有/加仓建议，包含目标卖出价位
验证: 建议包含 recommendation/action_text/score/profit_pct/target_sell_price/reasons/risks 字段
      recommendation 为 sell/reduce/consider_sell/hold/strong_hold 之一
      映射: sell=强烈建议卖出, reduce=建议减仓, consider_sell=可考虑卖出, hold=继续持有, strong_hold=坚定持有

调用: should_i_sell
参数: code="300750", buy_price=250, holding_days=60
预期: 返回针对不同持仓的差异化建议
验证: 持仓天数和买入价格影响建议结果
```

### Step 2: 获取当前价格

```
调用: get_realtime_quote
参数: stock_code="600519"
预期: 返回最新价格
验证: price > 0，数据源字段存在
```

### Step 3: 创建价格告警

```
调用: create_indicator_alert
参数: code="600519", indicator="price", condition=">", value=2000
预期: 创建止盈告警，返回 alert_id
验证: alert_id 非空

调用: create_indicator_alert
参数: code="600519", indicator="price", condition="<", value=1700
预期: 创建止损告警，返回 alert_id
验证: alert_id 非空
```

### Step 4: 创建技术指标告警

```
调用: create_indicator_alert
参数: code="600519", indicator="rsi", condition=">", value=80
预期: RSI超买告警
验证: 告警创建成功

调用: create_indicator_alert
参数: code="600519", indicator="macd", condition="<", value=0
预期: MACD死叉告警
验证: 告警创建成功
```

### Step 5: 创建组合告警

```
调用: create_combo_alert
参数: name="茅台止盈信号", conditions=[{"code":"600519","indicator":"price","condition":">","value":2000},{"code":"600519","indicator":"rsi","condition":">","value":70}], logic="AND"
预期: 价格突破2000且RSI>70时触发
验证: 组合告警创建成功，返回 combo_alert_id
```

### Step 6: 检查告警状态

```
调用: check_all_alerts
参数: status="active", alert_type="all"
预期: 返回所有活跃告警及其当前状态
验证: 包含前面创建的所有告警，每个告警有 triggered 字段
      ⚠️ 当前实现中 triggered 始终为 False（无实际触发检测逻辑，不会获取实时价格与阈值比较）
      触发检测需通过外部逻辑实现，此步骤仅验证告警注册与字段完整性
```

### Step 7: 告警管理

```
调用: alerts_manager
参数: action="list", kwargs='{}'
预期: 列出所有告警

调用: alerts_manager
参数: action="delete", kwargs='{"alert_id":"<某个alert_id>"}'
预期: 删除指定告警
验证: 再次list时该告警不存在
```

### Step 8: TDX预警推送（模拟告警触发）

> ⚠️ 由于 check_all_alerts 不执行实际触发检测，以下为手动模拟触发后的推送流程。

```
调用: push_warn
参数: stock_code="600519", price=2010, reason="突破止盈价2000 建议减仓", bs_flag=1
预期: success=true
验证: 通达信客户端收到卖出预警信号（bs_flag=1为卖出）
```

## TDX 前端交互

- 通达信预警窗口弹出卖出信号（蓝色/绿色箭头）
- 信号包含：股票代码、触发价格、预警原因
- 用户可在通达信中直接点击信号跳转到对应股票K线图

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 买入价为0或负数 | should_i_sell 返回参数错误 |
| 持仓天数为0 | 视为当日买入，建议观望 |
| 告警阈值不合理（止损>止盈） | 创建时提示警告 |
| 同一股票重复创建告警 | 允许多个告警共存（注意：同一 code+indicator+condition 不同 value 的告警会因 alert_id 冲突而互相覆盖） |
| 非交易时段检查告警 | 使用最近收盘数据判断 |
| 告警数量超过上限 | 提示清理过期告警 |

## 已知限制

- 告警系统为内存存储，MCP服务重启后告警丢失
- `check_all_alerts` 是即时检查，不是持续监控（需定期调用）
- 组合告警的 `logic="OR"` 模式下任一条件触发即告警
- `push_warn` 的 reason 字段最多25个汉字，需精简描述
