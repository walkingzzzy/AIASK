# 共启证据链（四工厂 + SignalTracker）

SignalTracker **不在** `run_three_factories.py` supervisor 内，但是 evidence loop 必需 sidecar。

## 推荐顺序

```powershell
# 1) 生产四运行体
uv run python scripts/factories/run_three_factories.py

# 2) 证据 sidecar（另开终端）
uv run python scripts/factories/run_signal_tracker.py --daemon
# 或单轮
uv run python scripts/factories/run_signal_tracker.py --once
```

## 环境要点

- `AIASK_SQLITE_PATH` / `AKSHARE_MCP_SQLITE_PATH` 指向同一可写库
- `INCUBATION_FAIL_CLOSED_SIGNAL_ID=1`（默认 ON）
- 非 mock AI（否则 readiness 永不 `production_ready`）

## 日报

```powershell
uv run python scripts/ops/runtime_formal_daily.py --db data/db/akshare_mcp.sqlite3 --out reports/ops
```

关注字段：`formal_count` / `signals_total` / `orders_total` / `signal_tracker` / `next_actions`。

## 禁止

- 不把 quality session 当生产 supervisor
- 不因 formal=0 降低 hard gate
- 不宣称 Live，除非 readiness `maturity_level=L4` 且 evidence 非空
