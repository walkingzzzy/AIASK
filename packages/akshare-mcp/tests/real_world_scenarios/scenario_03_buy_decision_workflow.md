# 场景03：买入决策全流程

## 用户故事

**As a** 个人投资者
**I want** 在买入一只股票前获得全方位的诊断分析（技术面+基本面+估值+情绪）
**So that** 我可以做出有数据支撑的买入决策，并在通达信收到预警提醒

## 业务流程

```
目标股票 → 智能诊断 → 估值分析 → 技术指标 → 情绪分析 → 买入建议 → TDX预警推送
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `smart_stock_diagnosis` | 综合诊断（一键分析） |
| 2 | `get_valuation_metrics` | 当前估值指标（PE/PB/PS） |
| 3 | `relative_valuation` | 同行业相对估值对比 |
| 4 | `dcf_valuation` | DCF内在价值估算 |
| 5 | `tdx_calculate_macd` | MACD技术指标 |
| 6 | `tdx_calculate_kdj` | KDJ技术指标 |
| 7 | `tdx_calculate_boll` | 布林带指标 |
| 8 | `analyze_stock_sentiment` | 个股情绪分析 |
| 9 | `should_i_buy` | 综合买入建议 |
| 10 | `push_warn` | 推送买入预警到TDX |

## 测试步骤

### Step 1: 智能诊断

```
调用: smart_stock_diagnosis
参数: stock_code="600519"
预期: 返回技术面/基本面/估值/情绪四维评分
验证: 包含 overall_score(0-100)/recommendation(buy/hold/wait/sell)/recommendation_text 字段
      scores 包含 technical/fundamental/valuation/sentiment 四个维度评分
      analysis 包含各维度的具体信号列表
      risks 包含风险提示列表
```

### Step 2: 估值分析

```
调用: get_valuation_metrics
参数: code="600519"
预期: 返回PE/PB/PS/市值等估值指标
验证: PE>0（盈利公司），PB>0

调用: relative_valuation
参数: code="600519"
预期: 返回与白酒行业同行的估值对比
验证: 包含peers列表和各指标的行业分位数

调用: dcf_valuation
参数: code="600519", discount_rate=0.1, growth_rate=0.05, years=5
预期: 返回DCF估算的内在价值
验证: 内在价值为正数，与当前股价偏差在合理范围

敏感性网格验证（建议补充调用）:
  - discount_rate=0.09, growth_rate=0.04 → 乐观估值
  - discount_rate=0.10, growth_rate=0.05 → 基准估值（上方调用）
  - discount_rate=0.11, growth_rate=0.06 → 悲观估值
  验证: 三组估值形成合理区间，乐观 > 基准 > 悲观
  注意: 敏感性网格用于展示估值区间而非单点值，帮助用户理解假设变化对估值的影响
```

### Step 3: 技术指标确认

```
调用: tdx_calculate_macd
参数: stock_code="600519", count=50
预期: 返回DIF/DEA/MACD柱状图数据
验证: 最新一根MACD柱值存在，判断金叉/死叉状态

调用: tdx_calculate_kdj
参数: stock_code="600519", count=50
预期: 返回K/D/J值
验证: K/D值在0-100之间，J值可超出

调用: tdx_calculate_boll
参数: stock_code="600519", count=50
预期: 返回上轨/中轨/下轨
验证: 上轨>中轨>下轨，当前价在三轨之间
```

### Step 4: 情绪分析

```
调用: analyze_stock_sentiment
参数: code="600519"
预期: 返回情绪评分和情绪标签
验证: 评分在合理范围，标签为 bullish/neutral/bearish 之一
```

### Step 5: 综合买入建议

```
调用: should_i_buy
参数: code="600519", investment_style="balanced"
预期: 返回买入/观望/回避建议及理由
验证: 建议与前述分析结果逻辑一致

信号冲突优先级说明:
  should_i_buy 内部综合技术面、基本面、估值、情绪四维评分，当信号冲突时：
  - 估值极度高估（PE/PB远超行业均值）→ 即使技术面看多，建议偏保守
  - 技术面强势（MACD金叉+RSI适中）但估值偏高 → 建议"观望"或"少量试仓"
  - 情绪极端恐慌但基本面良好 → 可能给出"逢低关注"建议
  注意: 具体权重由 should_i_buy 内部逻辑决定，此处仅说明信号冲突时的一般倾向
```

### Step 6: TDX预警推送

```
调用: push_warn
参数: stock_code="600519", price=<当前价>, reason="综合评分85分 建议关注", bs_flag=0
预期: success=true
验证: 通达信客户端收到买入预警信号
```

## TDX 前端交互

- 通达信预警窗口弹出买入信号
- 信号包含：股票代码、当前价格、预警原因（最多25个汉字）
- bs_flag=0 表示买入信号，客户端显示为红色箭头

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 股票代码不存在 | 返回错误提示 |
| ST/*ST股票 | should_i_buy 自动标记高风险 |
| 停牌股票 | 技术指标使用最后交易日数据 |
| DCF估值为负 | 提示公司现金流为负，DCF不适用 |
| TDX客户端未启动 | push_warn 返回失败，不影响分析结果 |
| 新股上市不足1年 | 部分估值指标缺失，降级处理 |

## 已知限制

- `smart_stock_diagnosis` 是聚合工具，内部调用多个子工具，耗时较长（3-5秒）
- `relative_valuation` 自动查找同行业公司，可能因行业分类不同导致对比不精确
- `dcf_valuation` 使用简化模型，对周期性行业估值偏差较大
- 情绪分析基于有限的新闻/公告数据，不包含社交媒体情绪
