# RFC-004:mkt_cap 单位统一(P2-4.2.4)

- **状态**: Draft
- **日期**: 2026-05-24
- **诊断报告锚点**: [`docs/diagnostics/mcp/MCP服务诊断报告-2026-05-24.md`](../diagnostics/mcp/MCP服务诊断报告-2026-05-24.md) §4.2.4

## 问题

22 场景 S06-F04:同股 601318 中国平安市值字段:
- `get_realtime_quote(601318).mkt_cap = 5722.32` (亿元?元?)
- `get_north_fund_top(601318).marketCap = 286.68 亿元` (元单位)
- `get_stock_info(000001).totalMarketCap = 2091.96 亿元` (元单位)

AI 调用三个工具拿到 5722 / 286 / 2091,如果误以为同单位,会以 20× 偏差做决策。

## 根因

| 工具 | 字段 | 单位 | 含义 |
|---|---|---|---|
| `get_realtime_quote` | `mkt_cap` | 亿元 | 实时总市值(估算) |
| `get_north_fund_top` | `marketCap` | 元 | 北向资金持仓股票的市值 |
| `get_stock_info` | `totalMarketCap` | 亿元 | 静态总市值(daily snapshot) |

相同概念三种字段名 + 两种单位 = 混乱。

## 实施方案

### 1. 统一字段命名约定

```python
# services/marketcap_format.py(新增)
def normalize_market_cap(
    value: float | int | None,
    *,
    input_unit: str = "yuan",  # yuan / yi_yuan / million_yuan
    output_unit: str = "yuan",
) -> dict:
    """标准化市值字段,所有工具响应必须用此辅助打包市值。

    Returns:
        {
            'market_cap_yuan': float,     # 元(canonical)
            'market_cap_yi': float,       # 亿元(显示用)
            'market_cap_unit': 'yuan',
            'market_cap_value_in_unit': float,  # 调用方便利字段
        }
    """
    if value is None:
        return {'market_cap_yuan': None, 'market_cap_yi': None, ...}

    # 输入归一化到 yuan
    multipliers = {
        'yuan': 1.0, 'cny': 1.0, 'rmb': 1.0,
        'yi_yuan': 1e8, '亿元': 1e8,
        'million_yuan': 1e6, '万元': 1e4,
    }
    yuan = float(value) * multipliers.get(input_unit, 1.0)
    return {
        'market_cap_yuan': yuan,
        'market_cap_yi': round(yuan / 1e8, 4),
        'market_cap_unit': 'yuan',
        'market_cap_value_in_unit': yuan if output_unit == 'yuan' else yuan / 1e8,
    }
```

### 2. 工具响应字段重构(向后兼容)

3 个工具响应同时保留旧字段 + 增加标准字段:

```python
# get_realtime_quote 响应
{
    "mkt_cap": 5722.32,            # 旧字段(deprecated 但保留)
    "market_cap_yuan": 572232000000,
    "market_cap_yi": 5722.32,
    "market_cap_unit": "yuan",
    ...
}
```

### 3. 文档警告

在 deprecated 字段 docstring 标注:
```
mkt_cap: deprecated since 2026-05; use market_cap_yuan or market_cap_yi.
         retained for backward compat. Unit is 亿元 (Yi Yuan).
```

### 4. 验收测试

```python
def test_market_cap_unit_unified():
    q = get_realtime_quote(code="601318")
    info = get_stock_info(code="601318")
    nf = get_north_fund_top(top_n=5)

    target = next(x for x in nf['data']['items'] if x.get('code') == '601318')

    # 三个工具的 yuan 单位市值偏差 < 5%(intra-day fluctuation)
    cap_q = q['data'].get('market_cap_yuan')
    cap_info = info['data'].get('market_cap_yuan')
    cap_nf = target.get('market_cap_yuan')

    if cap_q and cap_info:
        assert abs(cap_q - cap_info) / max(cap_q, cap_info) < 0.05
```

## 工时

- Step 1 新模块:1 小时
- Step 2 3 个工具响应字段:2 小时
- Step 3 文档:1 小时
- Step 4 测试:2 小时
- 总计:**1 工作日**
