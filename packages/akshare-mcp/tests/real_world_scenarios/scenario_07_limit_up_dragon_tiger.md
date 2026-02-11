# 场景07：涨停板复盘与龙虎榜追踪

## 用户故事

**As a** 游资跟踪者
**I want** 每日收盘后复盘涨停板数据，追踪龙虎榜席位和资金流向
**So that** 我可以发现游资动向和市场热点，为次日交易提供参考

## 业务流程

```
涨停统计 → 涨停板详情 → 龙虎榜数据 → 个股资金流向 → 板块资金流向 → TDX消息推送
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `get_limit_up_statistics` | 涨停板统计数据（涨停数/跌停数/炸板数） |
| 2 | `get_limit_up_stocks` | 涨停板个股列表 |
| 3 | `get_dragon_tiger` | 龙虎榜数据（买卖金额/席位） |
| 4 | `get_stock_fund_flow` | 个股资金流向（主力/大单/中单/小单） |
| 5 | `get_sector_fund_flow` | 行业板块资金流向 |
| 6 | `get_concept_fund_flow` | 概念板块资金流向 |
| 7 | `push_message` | 推送复盘摘要到TDX |
| 8 | `limit_up_manager` | 涨停板管理器 |
| 9 | `trading_data_manager` | 交易数据管理器 |

## 测试步骤

### Step 1: 涨停板统计

```
调用: get_limit_up_statistics
参数: date=""（默认最近交易日）
预期: 返回涨停数/跌停数/炸板数/连板数统计
验证: 涨停数 > 0，各统计项为非负整数
```

### Step 2: 涨停板个股

```
调用: get_limit_up_stocks
参数: date=""（默认最近交易日）
预期: 返回涨停股票列表
验证: 每只股票包含 code/name/price/changePercent/limitUpPrice/continuousDays 字段
      列表数量与统计数据中的涨停数基本一致（允许±5%偏差，因两个接口数据源/时间点可能不同）
      数据源: Tushare stk_limit + daily 组合判断（close >= up_limit）
```

### Step 3: 龙虎榜数据

```
调用: get_dragon_tiger
参数: date=""（默认最近交易日）
预期: 返回龙虎榜股票列表及买卖明细
验证: 包含 buyAmount/sellAmount 字段（非null）
      降级链: Tushare → AkShare(stock_lhb_detail_em) → Sina

调用: get_dragon_tiger
参数: stock_code="<涨停板中某只股票>"
预期: 返回该股票的龙虎榜席位详情
验证: 包含买入/卖出前5席位的营业部名称和金额
```

### Step 4: 个股资金流向

```
调用: get_stock_fund_flow
参数: stock_code="<龙虎榜中某只股票>"
预期: 返回主力/大单/中单/小单资金流向
验证: 主力净流入 = 大单净流入 + 超大单净流入
      各项金额为浮点数
```

### Step 5: 板块资金流向

```
调用: get_sector_fund_flow
参数: top_n=10
预期: 返回资金净流入前10的行业板块
验证: 按净流入金额降序排列

调用: get_concept_fund_flow
参数: top_n=10
预期: 返回资金净流入前10的概念板块
验证: 包含板块名称和净流入金额
```

### Step 6: TDX消息推送

```
调用: push_message
参数: message="【涨停复盘】涨停42家|跌停5家|炸板8家|连板最高3板|主力净流入板块:半导体+新能源|龙虎榜净买入:XXX 1.2亿"
预期: success=true
验证: 通达信客户端收到复盘消息（使用|分隔多行显示）
```

## TDX 前端交互

- 通达信消息窗口显示涨停复盘摘要
- 消息使用 `|` 分隔实现多行显示
- 用户可根据消息内容在通达信中查看对应股票

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 当日无涨停股 | 返回空列表，推送"今日无涨停" |
| 龙虎榜数据T+1延迟 | 当日查询返回Sina实时数据（可能不完整） |
| 历史日期无龙虎榜 | 返回空列表 |
| 板块资金流向全部为负 | 正常返回，表示市场整体流出 |
| 非交易日查询 | 自动使用最近交易日数据 |
| push_message 内容过长 | 自动截断或分多次推送 |

## 已知限制

- 龙虎榜数据存在T+1延迟，当日数据通过Sina获取可能不完整
- `get_dragon_tiger` 降级链: Tushare → AkShare(stock_lhb_detail_em) → Sina
- 涨停板数据依赖收盘价与涨停价的比较，盘中数据可能不准确
- 资金流向数据来源不同（东财/AkShare），口径可能有差异
- `push_message` 单条消息长度有限，复杂复盘需分多条推送
