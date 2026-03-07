# 场景08：每日市场全景报告

## 用户故事

**As a** 基金经理
**I want** 每日收盘后自动生成包含指数、板块、资金、宏观数据的全景报告
**So that** 我可以快速掌握市场全貌，为次日投资决策提供依据

## 业务流程

```
指数行情 → 板块轮动 → 北向资金 → 宏观数据 → 市场新闻 → 生成日报 → TDX推送
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `generate_daily_report` | 一键生成每日市场报告 |
| 2 | `get_index_quote` | 获取主要指数行情 |
| 3 | `get_sector_fund_flow` | 行业板块资金流向 |
| 4 | `get_concept_fund_flow` | 概念板块资金流向 |
| 5 | `get_north_fund` | 北向资金数据 |
| 6 | `get_macro_indicator` | 宏观经济指标 |
| 7 | `get_market_news` | 市场新闻 |
| 8 | `calculate_fear_greed_index` | 恐惧贪婪指数 |
| 9 | `market_insight_manager` | 市场洞察分析 |
| 10 | `push_message` | 推送日报摘要到TDX |

## 测试步骤

### Step 1: 一键生成日报

```
调用: generate_daily_report
参数: date=null（默认当日）
预期: 返回聚合的市场全景报告
验证: 包含以下字段:
  - market_summary: 三大指数行情（上证/深证/创业板）
  - stats: 涨跌统计（up_count/down_count/limit_up_count/limit_down_count）
  - hot_sectors: 热门板块（涨幅前5）
  - capital_flow: 资金流向（north_fund/main_fund）
  - sentiment: 市场情绪（bullish/neutral/bearish）
  - highlights: 市场要点列表
  - outlook: 后市展望
  - generated_at: 生成时间
```

### Step 2: 主要指数行情

```
调用: get_index_quote
参数: index_code="000001"（上证指数）
预期: 返回上证指数实时/收盘行情
验证: 包含 price/change/changePercent/volume 字段

调用: get_index_quote
参数: index_code="399001"（深证成指）
预期: 返回深证成指行情

调用: get_index_quote
参数: index_code="399006"（创业板指）
预期: 返回创业板指行情
```

### Step 3: 板块轮动分析

```
调用: get_sector_fund_flow
参数: top_n=20
预期: 返回行业板块资金流向排名
验证: 前5为资金净流入板块，后5为净流出板块

调用: get_concept_fund_flow
参数: top_n=20
预期: 返回概念板块资金流向排名
验证: 可识别当日市场热点概念
```

### Step 4: 北向资金

```
调用: get_north_fund
参数: days=5
预期: 返回最近5个交易日的北向资金数据
验证: 包含沪股通/深股通净买入金额
      判断北向资金连续流入/流出趋势
```

### Step 5: 宏观经济指标

```
调用: get_macro_indicator
参数: indicator="pmi", limit=3
预期: 返回最近3期PMI数据
验证: PMI值在30-70之间，>50为扩张
      检查数据发布日期，确认是否为最近发布期（PMI为月度数据）

调用: get_macro_indicator
参数: indicator="cpi", limit=3
预期: 返回最近3期CPI数据
验证: CPI为同比增速百分比
      检查数据发布日期，确认是否为最近发布期（CPI为月度数据）
```

### Step 6: 市场情绪

> ⚠️ `calculate_fear_greed_index` 当前返回固定演示值（index=50, level='neutral'，所有组件均为50）。此步骤仅校验返回结构正确性，不校验市场真实性。

```
调用: calculate_fear_greed_index
参数: （无参数）
预期: 返回恐惧贪婪指数（0-100）
验证: 返回结构包含 index/level/components 字段
      分级标准: 0-25极度恐惧，25-45恐惧，45-55中性，55-75贪婪，75-100极度贪婪
      ⚠️ 当前实现固定返回 index=50（中性），仅验证格式
```

### Step 7: 市场新闻

```
调用: get_market_news
参数: limit=10
预期: 返回最新10条市场新闻
验证: 每条新闻包含 title/content/datetime 字段
```

### Step 8: TDX推送日报摘要

```
调用: push_message
参数: message="【市场日报】上证3250.5↑1.2%|深证10850↑0.8%|创业板2150↑1.5%|北向净买入32亿|热点:AI+半导体|恐贪指数62(贪婪)"
预期: success=true
验证: 通达信客户端收到日报摘要
```

## TDX 前端交互

- 通达信消息窗口显示日报摘要
- 使用 `|` 分隔实现结构化多行显示
- 摘要包含：三大指数涨跌、北向资金、热点板块、市场情绪

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 非交易日生成日报 | 使用最近交易日数据，标注日期 |
| 宏观数据未更新 | 返回最近可用数据，标注发布日期 |
| 北向资金数据缺失 | 跳过该部分，不影响其他内容 |
| 市场新闻接口不可用 | 降级为公告/研报替代 |
| 指数代码错误 | 返回错误提示 |
| 恐惧贪婪指数计算失败 | 当前返回固定演示值（index=50），标注为预设数据 |

## 已知限制

- `generate_daily_report` 是聚合工具，内部调用多个子工具，耗时5-10秒
- 宏观数据（GDP/CPI/PMI）更新频率为月度/季度，非每日更新
- 北向资金数据在15:30后才完整
- 市场新闻依赖AkShare接口，可能因网络问题返回空
- `push_message` 单条消息长度有限，完整日报需分多条推送或精简
- ⚠️ `calculate_fear_greed_index` 当前返回固定演示值（index=50），不反映真实市场情绪
- 🔴 **BUG**: `market_insight_manager` 的 `market_trend` 调用 `get_kline_data(code="000001")` 获取K线，但 000001 被解析为**平安银行**（股价~11元），而非上证指数（~4123点），导致 support/resistance/MA 值全部错误（偏差约370倍）。需修复为使用指数专用K线接口。
- ⚠️ `market_insight_manager` 的 `sector_analysis` 在非交易时间返回 net_inflow=0.0，为预期行为
