# 场景02：多因子量化选股

## 用户故事

**As a** 量化研究员
**I want** 使用多因子模型筛选出具有超额收益潜力的股票组合
**So that** 我可以构建基于因子暴露的量化投资组合

## 业务流程

```
因子库查询 → 单因子计算 → IC分析 → 因子回测 → 多因子选股 → 结果输出
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `get_factor_library` | 查看可用因子列表（8个因子） |
| 2 | `calculate_factor` | 计算单只股票的因子值 |
| 3 | `calculate_factor_ic` | 计算因子IC值（信息系数） |
| 4 | `backtest_factor` | 因子分组回测 |
| 5 | `parse_selection_query` | 自然语言选股条件解析 |
| 6 | `screener_manager` | 多因子选股器 |
| 7 | `get_batch_quotes` | 获取候选股实时行情 |

## 测试步骤

### Step 1: 查看因子库

```
调用: get_factor_library
参数: category="all"
预期: 返回8个基础因子类别（momentum, volatility, reversal, value, quality, growth, size, liquidity），每个类别下有多个细分因子（如 momentum 包含 mom_1d/5d/10d/20d/60d 等，共100+细分因子）
验证: 每个因子包含 name/description/category 字段
```

### Step 2: 计算单因子值

```
调用: calculate_factor
参数: code="600519", factor="momentum"
预期: 返回动量因子值（20日收益率）
验证: 因子值为浮点数，在合理范围内（-50% ~ +50%）

调用: calculate_factor
参数: code="600519", factor="quality"
预期: 返回质量因子值（ROE相关）
验证: 因子值为正数
```

### Step 3: 因子IC分析

```
调用: calculate_factor_ic
参数: codes=["600519","000858","300750","601318","600036","000001","002594","600887","600276","002049"], factor="momentum", period=20
预期: 返回IC值（Spearman相关系数）
验证: IC绝对值 < 1，|IC| > 0.03 表示因子有效
注意: 此处10只为快速验证，正式因子分析建议≥30只以确保统计意义；建议行业中性化后再算IC
```

### Step 4: 因子分组回测

```
调用: backtest_factor
参数: codes=["600519","000858","300750","601318","600036","000001","002594","600887","600276","002049"], factor="momentum", groups=5, holding_days=20
预期: 返回5组收益率，第1组（因子值最高）与第5组有显著差异
验证: 多空收益（第1组-第5组）为正表示因子有效
```

### Step 5: 自然语言选股

```
调用: parse_selection_query
参数: query="市盈率小于20且ROE大于15%"
预期: 解析为结构化筛选条件
验证: 返回包含 pe_ratio < 20 和 roe > 15 的条件
```

### Step 6: 多因子选股

```
调用: screener_manager
参数: action="screen", kwargs='{"criteria":{"max_pe":20,"min_roe":0.15,"max_debt_ratio":0.5}}'
预期: 返回符合基本面条件的股票列表（最多50只）
验证: 每只股票包含 stock_code/stock_name/pe_ratio/roe/debt_ratio/score/rating 字段
      score 为综合评分（0-100），rating 为 A/B/C/D 等级
注意: screener_manager 的 screen action 使用 criteria 字典（支持 min_pe/max_pe/min_pb/max_pb/min_roe/max_roe/min_revenue_growth/max_debt_ratio/sectors 等条件），
      不支持直接传入因子名称列表。多因子排名需结合 calculate_factor 逐只计算后手动排序。

扩展: 如需技术面+基本面组合选股，使用 combined_screen action:
调用: screener_manager
参数: action="combined_screen", kwargs='{"fundamental_criteria":{"max_pe":20,"min_roe":0.15},"tech_conditions":["macd_golden_cross","volume_breakout"],"logic":"AND"}'
预期: 返回同时满足基本面和技术面条件的股票
验证: 包含 matched 列表和 matched_count
```

## TDX 前端交互

- 本场景不涉及TDX联动
- 选股结果可通过场景01的 `create_watchlist` 同步到通达信

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 因子计算数据不足 | 返回 null 并提示最少需要250日K线 |
| IC值接近0 | 提示因子无效，建议更换因子 |
| 股票池过小（<10只） | 分组回测自动减少组数 |
| 因子名称拼写错误 | 返回支持的因子列表 |
| 财务数据缺失 | value/quality/growth因子降级为技术因子 |

## 已知限制

- 因子库当前接口暴露8个基础因子类别，底层 `factor_calculator.py` 实现了100+细分因子，不支持自定义因子表达式
- IC分析需要足够的股票样本（建议≥20只）才有统计意义
- 因子回测使用简单分组法，未考虑行业中性化
- `calculate_factor_ic` 和 `backtest_factor` 需要批量获取K线数据，耗时较长
- `screener_manager` 的 `screen` action 使用 `criteria` 字典进行基本面筛选（支持 max_pe/min_roe/max_debt_ratio 等），不支持直接传入因子名称列表做多因子排名
- 如需技术面选股，使用 `technical_screen` action（传入 conditions ID列表）；如需组合选股，使用 `combined_screen` action
- `parse_selection_query` 的 suggestion 字段会自动推荐正确的 screener_manager 调用方式
