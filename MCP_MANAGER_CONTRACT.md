# MCP Manager 调用规范 (v1.0)

## 协议概述

本文档定义了所有 Manager 工具的统一调用协议，确保 MCP Host（如 Cursor、Claude Desktop）和 BFF 能可靠调用。

---

## 统一签名

所有 Manager 工具遵循以下标准签名：

```python
async def xxx_manager(
    action: str,                    # 必填 — 操作名称
    params: dict | None = None,     # 推荐 — 结构化参数（MCP Host 直传）
    kwargs: Any = None,             # 兼容 — BFF 传入的 JSON 字符串或 dict
    code: str | None = None,        # 可选 — 仅需要股票代码的 Manager 保留此参数
) -> dict:
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `str` | ✅ | 操作名称，如 `"help"`, `"list"`, `"analyze"` |
| `params` | `dict \| None` | ❌ | 结构化参数字典，MCP Host 直接传入 |
| `kwargs` | `Any` | ❌ | 兼容 BFF 传参，接受 JSON 字符串或 dict |
| `code` | `str \| None` | ❌ | 股票代码（仅部分 Manager 有此参数） |

### 合并优先级

参数通过 `normalize_manager_payload()` 统一合并，优先级如下（后者覆盖前者）：

```
kwargs → params → extra → explicit code
```

---

## 调用示例

### 推荐方式（params 模式）

MCP Host 直接传入结构化 `params`：

```json
{
  "action": "analyze",
  "params": {
    "code": "000001",
    "period": "daily",
    "limit": 30
  }
}
```

### 兼容方式（kwargs 模式）

BFF 通过 JSON 字符串传参：

```json
{
  "action": "analyze",
  "kwargs": "{\"code\":\"000001\",\"period\":\"daily\",\"limit\":30}"
}
```

### 最小调用（help）

所有 Manager 均支持 `action="help"` 无参调用：

```json
{
  "action": "help"
}
```

---

## 响应格式

### 成功响应

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "source": "akshare",
  "cached": false,
  "timestamp": "2026-03-30T12:00:00",
  "meta": {
    "trace_id": "alerts_manager:list:1711792800000",
    "tool_version": "v1.1",
    "data_timestamp": "2026-03-30",
    "source_chain": ["alerts_manager", "db.alerts"],
    "cached": false,
    "latency_ms": 42
  }
}
```

### 错误响应

```json
{
  "success": false,
  "data": null,
  "error": "描述信息",
  "error_code": "PARAM_ERROR",
  "source": "akshare",
  "cached": false,
  "timestamp": "2026-03-30T12:00:00",
  "meta": { ... }
}
```

### 标准错误码

| 错误码 | 含义 |
|--------|------|
| `PARAM_ERROR` | 参数缺失或格式错误 |
| `NOT_FOUND` | 请求的资源不存在 |
| `AUTH_ERROR` | 认证或权限不足 |
| `UPSTREAM_ERROR` | 上游数据源或服务不可用 |
| `INTERNAL_ERROR` | 服务内部异常 |

---

## 能力声明

当前 MCP 服务仅支持 **Tools** 能力：

- ✅ `tools/list` — 列出所有可用工具
- ✅ `tools/call` — 调用工具
- ❌ `resources/list` — 不提供（返回空数组）
- ❌ `prompts/list` — 不提供（返回空数组）

---

## Manager 列表

当前注册的 Manager 工具（31 个）：

| Manager | 用途 | 有 `code` 参数 |
|---------|------|----------------|
| `alerts_manager` | 告警管理 | ❌ |
| `backtest_manager` | 回测引擎 | ❌ |
| `benchmark_manager` | 基准对比分析 | ❌ |
| `compliance_manager` | 合规检查 | ❌ |
| `comprehensive_manager` | 综合分析 | ✅ |
| `data_sync_manager` | 数据同步管理 | ❌ |
| `decision_manager` | 决策引擎 | ❌ |
| `event_manager` | 事件管理 | ❌ |
| `execution_manager` | 执行引擎 | ❌ |
| `fundamental_analysis_manager` | 基本面分析 | ✅ |
| `industry_chain_manager` | 产业链分析 | ❌ |
| `insight_manager` | 洞察分析 | ❌ |
| `limit_up_manager` | 涨停分析 | ❌ |
| `live_trading_manager` | 实盘交易 | ❌ |
| `macro_manager` | 宏观经济 | ❌ |
| `market_insight_manager` | 市场洞察 | ❌ |
| `options_manager` | 期权分析 | ❌ |
| `paper_trading_manager` | 模拟交易 | ❌ |
| `performance_manager` | 绩效分析 | ❌ |
| `portfolio_manager` | 组合管理 | ❌ |
| `quant_manager` | 量化引擎 | ✅ |
| `research_manager` | 研究管理 | ✅ |
| `risk_manager` | 风险管理 | ❌ |
| `screener_manager` | 选股器 | ❌ |
| `sector_manager` | 板块轮动 | ❌ |
| `sentiment_manager` | 情绪分析 | ❌ |
| `strategy_manager` | 策略工厂 | ❌ |
| `technical_analysis_manager` | 技术分析 | ✅ |
| `trading_data_manager` | 交易数据 | ❌ |
| `user_manager` | 用户管理 | ❌ |
| `vector_search_manager` | 向量搜索 | ✅ |
| `watchlist_manager` | 自选股管理 | ❌ |

---

## 高风险操作

以下操作受 `risk_guard` 确认门禁保护：

| Manager | Action | 门禁要求 |
|---------|--------|----------|
| `live_trading_manager` | `submit_order` | `confirm_token` 或 `I_UNDERSTAND_THE_RISK` |
| `live_trading_manager` | `cancel_order` | `confirm_token` 或 `I_UNDERSTAND_THE_RISK` |

通过环境变量 `AKSHARE_REQUIRE_CONFIRMATION=true` 启用确认门禁。
审计日志写入 `logs/risk_audit.jsonl`。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-30 | 初始版本：统一签名协议、错误码、能力声明 |
