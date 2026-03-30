# MCP Manager 调用规范

> 版本: v1.0 | 更新日期: 2026-03-30

## 1. 统一签名规范

所有 Manager 工具统一使用以下签名模式：

```python
async def xxx_manager(
    action: str,                    # 必填：操作类型
    params: dict | None = None,     # 推荐：结构化参数
    kwargs: Any = None,             # 兼容：JSON 字符串或 dict
    code: str | None = None,        # 可选：股票代码快捷参数
):
```

### 参数优先级

合并优先级（后者覆盖前者）：`kwargs` → `params` → `code`

### 调用方式

**推荐方式（MCP 结构化调用）：**
```json
{
  "action": "run",
  "params": {"code": "600519", "strategy": "ma_cross"}
}
```

**兼容方式（BFF 旧调用）：**
```json
{
  "action": "run",
  "kwargs": "{\"code\":\"600519\",\"strategy\":\"ma_cross\"}"
}
```

## 2. 必须支持的 Action

所有 Manager 必须支持 `action="help"`，返回：
```json
{
  "success": true,
  "data": {
    "supported_actions": {
      "help": "显示帮助信息",
      "...": "..."
    }
  }
}
```

## 3. 错误模型

### 错误码分类

| error_code | 含义 |
|-----------|------|
| `PARAM_ERROR` | 参数错误 |
| `NOT_FOUND` | 资源不存在 |
| `AUTH_ERROR` | 权限错误 |
| `UPSTREAM_ERROR` | 后端依赖错误 |
| `INTERNAL_ERROR` | 未知内部错误 |

### 返回格式
```json
{
  "success": false,
  "error": "错误描述",
  "error_code": "PARAM_ERROR",
  "meta": {
    "trace_id": "tool_name:action:timestamp",
    "latency_ms": 42
  }
}
```

## 4. 高风险操作门禁

`live_trading_manager` 的 `submit_order` / `cancel_order` 操作：
- 受 `AKSHARE_REQUIRE_CONFIRMATION` 环境变量控制
- 启用后需提供 `confirm_token` 参数
- 所有写操作记录审计日志到 `logs/risk_audit.jsonl`

## 5. 当前能力声明

- ✅ **Tools**: 完整支持
- ❌ **Resources**: 未实现（`list_resources` 返回空）
- ❌ **Prompts**: 未实现（`list_prompts` 返回空）

## 6. 安全配置

### 环境变量

| 变量 | 说明 |
|------|------|
| `MCP_TRANSPORT` | 传输模式：stdio/sse/streamable-http |
| `MCP_HOST` | HTTP 绑定地址（仅 127.0.0.1/localhost/::1） |
| `MCP_PORT` | HTTP 端口（默认 8000） |
| `MCP_AUTH_MODE` | 认证模式（HTTP 传输必配） |
| `MCP_ALLOWED_ORIGINS` | 允许的 Origin（HTTP 传输必配） |
| `AKSHARE_REQUIRE_CONFIRMATION` | 是否启用写操作确认门禁 |
| `AKSHARE_CONFIRM_TOKEN` | 确认 token 值 |
| `AKSHARE_AUDIT_LOG` | 审计日志路径（默认 logs/risk_audit.jsonl） |
