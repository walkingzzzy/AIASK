# RFC-003:4 manager 强制 user_id 传递(P2-4.2.6 / P2-4.2.7)

- **状态**: Draft
- **日期**: 2026-05-24
- **诊断报告锚点**: [`docs/diagnostics/mcp/MCP服务诊断报告-2026-05-24.md`](../diagnostics/mcp/MCP服务诊断报告-2026-05-24.md) §4.2.6 / §4.2.7

## 问题

22 场景 S11-F06 / S16-F08 / S16-F09 / S11-F04 累计 4 次:

| Manager | 表现 |
|---|---|
| `alerts_manager` | user_id='codex_full_mcp_20260522' 传入 → db 写入 user_id='default' |
| `watchlist_manager.create_group` | 同上 |
| `screener_manager.save_strategy` | 同上(criteria 也被忽略) |
| `paper_trading_manager.list_accounts` | 不传 user_id 默认 'default' scope,看不到 codex 账户 |

对比:`user_manager.archive_account` 已 robust(USER_SCOPE_MISMATCH 拦截跨用户)。

## 根因(代码审计后修正诊断报告 §4.2.6 论断)

经 RFC 起草人代码审计,**alerts_manager 实际已正确接收并传递 user_id**(line 339):
```python
user_id = _safe_user_id(kwargs.get("user_id"))
```

诊断报告测试到的 "user_id silent ignore" 实为以下原因之一:
1. **MCP 客户端协议问题**:user_id 参数未正确传到工具(协议层 bug)
2. **缺省值是 'default'**:`_safe_user_id` 在空值时返回 'default',导致看似 silent ignore
3. **db 写入实际正确,但 list/get 默认 scope filter 是 'default'**(诊断报告 §4.2.7 指出)

## 实施方案

### 1. 工具入口校验 user_id

新增 `_require_user_id` 装饰器:

```python
# services/user_scope.py(新增)
from typing import Any

def require_user_id_or_warn(kwargs: dict, *, default_user_id: str | None = None) -> tuple[str, list[str]]:
    """检查 kwargs 中的 user_id,返回 (resolved_user_id, warnings)。

    Args:
        kwargs: tool 入参字典
        default_user_id: 当未提供时的回退,通常从环境变量或 user_context 读

    Returns:
        (user_id, warnings):若 user_id 缺失或为 'default',warnings 含说明
    """
    raw = kwargs.get("user_id") or kwargs.get("userId") or default_user_id
    warnings: list[str] = []
    if not raw or str(raw).strip() in ("", "default"):
        warnings.append(
            "user_id_not_provided_falling_back_to_default — "
            "建议显式传 user_id,避免数据落到全局 default scope"
        )
        raw = "default"
    return str(raw).strip(), warnings
```

### 2. 4 个 manager 接入

每个 manager `register_*` 入口:
```python
async def alerts_manager(action, kwargs, user_id=None, ...):
    kwargs = normalize_manager_payload(...)
    resolved_user_id, scope_warnings = require_user_id_or_warn(
        kwargs,
        default_user_id=os.getenv("AIASK_DEFAULT_USER_ID"),
    )
    # ... existing logic ...
    response_data["scope_warnings"] = scope_warnings
    response_data["resolved_user_id"] = resolved_user_id
```

### 3. list 类 action 默认 inherit context

`list_accounts` / `watchlist.list` 等查询类 action,
不传 user_id 时不再默认 'default',而是从 `os.getenv("AIASK_DEFAULT_USER_ID")` 读;
仍空则 emit warning 并查全部用户(显式标 `scope='all'`)。

### 4. 不变量回归测试

```python
def test_alerts_manager_user_id_persisted_to_db():
    """诊断报告 §4.2.6 锁:user_id 必须正确写入 db。"""
    result = await alerts_manager(
        action="create",
        user_id="test_user_xxx",
        kwargs={"code": "600519", "indicator": "rsi", "condition": ">", "value": 70},
    )
    db = get_db()
    rows = await db.fetch("SELECT user_id FROM alerts WHERE code='600519'")
    assert rows[-1]["user_id"] == "test_user_xxx"
```

## 工时

- Step 1 新模块:1 小时
- Step 2 4 manager 接入:2 小时
- Step 3 list 类 action inherit context:2 小时
- Step 4 测试 + 回归:2 小时
- 总计:**1 工作日**
