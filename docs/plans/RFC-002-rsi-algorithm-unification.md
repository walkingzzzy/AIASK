# RFC-002:RSI 算法统一(P2-4.2.5)

- **状态**: Draft
- **日期**: 2026-05-24
- **诊断报告锚点**: `MCP服务诊断报告-2026-05-24.md` §4.2.5

## 问题

22 场景 S11-F07:同股 600519 同 10 分钟时间窗口:
- `get_factor_profile.rsi.current = 22.5864`(RSI(14) Wilder's smoothing)
- `alerts.check.rsi = 2.7586`(其他算法/窗口)
- 偏差 8 倍 / 87.7%

AI Agent 看到两个 RSI 值不知道哪个对,直接误用风险高。

## 根因

- `services/technical_analysis.py:calculate_rsi` 用 talib(若有)/ pandas_ta,默认 RSI(14) Wilder's
- `tools/alerts._evaluate_indicator` 走另一路径,可能用 SMA(14) 或不同 smoothing

## 实施方案

### 1. 全工具走 Wilder's RSI(14)

```python
# 新增统一接口 services/rsi_unified.py
from typing import List

def calculate_rsi_wilder(closes: List[float], period: int = 14) -> List[float | None]:
    """Wilder's smoothing RSI(14),与 talib/pandas_ta 默认一致。

    AIASK 内全部 RSI 调用统一走此接口,确保跨工具一致性。
    """
    if len(closes) <= period:
        return [None] * len(closes)
    gains, losses = [0.0], [0.0]
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    rsi: list[float | None] = [None] * period
    if avg_loss == 0:
        rsi.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100.0 - 100.0 / (1.0 + rs))
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - 100.0 / (1.0 + rs))
    return rsi
```

### 2. 替换点(grep 现有 RSI 调用)

需要审计的调用方:
- `services/technical_analysis.py:calculate_rsi`(已是 Wilder ✓)
- `services/technical_analysis.py:calculate_rsi_series`(待审计)
- `tools/alerts.py:_evaluate_indicator`(待审计 — 主要嫌疑点)
- `tools/factor_profile.py:get_factor_profile.rsi`(走 calculate_rsi)
- `tools/quant_engine.py` 内 momentum/rsi factor

### 3. 顶层标 `rsi_method`

每个返回 RSI 的工具响应增加:
```python
{
    "rsi": 22.59,
    "rsi_method": "wilder_smoothing",
    "rsi_period": 14,
    "rsi_calculation_source": "services.rsi_unified"
}
```

### 4. 验收测试

```python
def test_rsi_cross_tool_consistency():
    """诊断报告 §4.2.5 锁:同股同时间窗口 RSI 偏差 < 1%。"""
    from akshare_mcp.tools.alerts import _evaluate_indicator
    from akshare_mcp.tools.factor_profile import get_factor_profile

    # 给定相同 closes,两路径返回的 RSI 必须一致
    closes = [...]  # 30 个收盘价
    rsi_alerts = _evaluate_indicator(closes, "rsi", ...)
    rsi_factor = get_factor_profile_rsi(closes)

    assert abs(rsi_alerts - rsi_factor) < 0.5  # tolerance 0.5
```

## 工时

- Step 1 新模块:1 小时
- Step 2 替换调用:2 小时(7 个调用方)
- Step 3 标注响应:1 小时
- Step 4 测试 + 回归:2 小时
- 总计:**1 工作日**
