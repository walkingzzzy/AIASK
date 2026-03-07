# 场景11：新股申购与可转债监控

## 用户故事

**As a** 打新投资者
**I want** 及时获取新股和可转债的申购信息，并设置价格告警监控可转债
**So that** 我不会错过申购机会，并能在可转债达到目标价时及时卖出

## 业务流程

```
查询新股/新债 → 筛选申购标的 → 可转债信息查询 → 设置价格告警 → TDX预警推送
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `get_ipo_info` | 获取新股/新债申购信息 |
| 2 | `get_cb_info` | 获取可转债基础信息 |
| 3 | `get_realtime_quote` | 获取可转债/正股实时价格 |
| 4 | `get_stock_info` | 获取正股基本信息 |
| 5 | `create_indicator_alert` | 创建可转债价格告警 |
| 6 | `check_all_alerts` | 检查告警触发状态 |
| 7 | `push_warn` | 推送申购/卖出预警到TDX |

## 测试步骤

### Step 1: 查询新股申购

```
调用: get_ipo_info
参数: ipo_type=0, include_future=true
预期: 返回近期新股申购信息
验证: 返回 ipo_list 列表和 count 字段
      数据来源为 TdxQuant（需要通达信客户端运行）
      如无数据返回空列表和 message 提示
```

### Step 2: 查询新债申购

```
调用: get_ipo_info
参数: ipo_type=1, include_future=true
预期: 返回近期可转债申购信息
验证: 包含可转债代码/名称/申购日期/正股代码

调用: get_ipo_info
参数: ipo_type=2, include_future=true
预期: 返回新股+新债全部申购信息
验证: 结果数量 >= 仅新股 + 仅新债的数量
```

### Step 3: 可转债信息查询

```
调用: get_cb_info
参数: code="123039"
预期: 返回可转债详细信息
验证: 包含以下字段:
  - KZZCode: 可转债代码
  - HSCode: 正股代码
  - ZGPrice: 转股价格
  - ZGDate: 转股日期
  - EndDate: 到期日期
  - RestScope: 剩余规模
```

### Step 4: 正股与转债价格

```
调用: get_realtime_quote
参数: stock_code="<正股代码>"
预期: 返回正股实时价格
验证: 可计算转股溢价率:
      转股价值 = 正股现价 × 100 / 转股价
      转股溢价率 = (转债现价 - 转股价值) / 转股价值
      注: 转债价格按100面值口径

调用: get_stock_info
参数: stock_code="<正股代码>"
预期: 返回正股基本信息
验证: 包含行业/市值等信息，辅助判断转债质量
```

### Step 5: 创建可转债价格告警

```
调用: create_indicator_alert
参数: code="123039", indicator="price", condition=">", value=130
预期: 创建转债止盈告警（130元以上卖出）
验证: alert_id 非空

调用: create_indicator_alert
参数: code="123039", indicator="price", condition="<", value=95
预期: 创建转债止损告警（跌破95元）
验证: alert_id 非空
```

### Step 6: 检查告警

```
调用: check_all_alerts
参数: status="active", alert_type="indicator"
预期: 返回所有活跃的指标告警
验证: 包含前面创建的转债告警
      ⚠️ triggered 字段当前始终为 False（同场景04，无实际触发检测逻辑）
```

### Step 7: TDX预警推送

```
调用: push_warn
参数: stock_code="123039", price=131.5, reason="转债突破130 建议止盈", bs_flag=1
预期: success=true
验证: 通达信客户端收到卖出预警

调用: push_warn
参数: stock_code="<新股代码>", price=0, reason="明日新股申购 记得打新", bs_flag=0
预期: success=true
验证: 通达信客户端收到申购提醒
```

## TDX 前端交互

- 通达信预警窗口显示新股申购提醒（bs_flag=0，买入信号）
- 通达信预警窗口显示可转债止盈信号（bs_flag=1，卖出信号）
- 用户可点击预警信号跳转到对应证券的K线图

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 近期无新股/新债申购 | 返回空列表 |
| 可转债代码不存在 | get_cb_info 返回错误 |
| 可转债已到期 | 返回到期信息，提示不可交易 |
| 正股停牌 | 转股溢价率计算使用最后交易价 |
| 转股价变更（下修/上修） | 需重新获取 get_cb_info 确认最新转股价 |
| 转债价格低于面值(100) | 可能触发回售条款，需关注 |
| TDX客户端未启动 | push_warn 返回失败 |

## 已知限制

- `get_ipo_info` 数据来源为TdxQuant，需要通达信客户端运行
- `get_cb_info` 返回的是基础信息，不包含实时价格和溢价率
- 可转债告警使用通用的 `create_indicator_alert`，不支持转股溢价率告警
- 新股申购提醒需要用户手动设置，不支持自动定时提醒
- 可转债的强赎/回售条款判断需要人工分析
