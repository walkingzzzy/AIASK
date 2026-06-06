# SQLite 存储膨胀修复方案

> **触发**：`data/db/akshare_mcp.sqlite3` 在 35 小时内从 0 涨到 **129.6 GB**，期间只跑了 65 轮工厂、生成 354 条策略、所有正常表数据加起来不到 500 MB。
>
> **真正根因**：策略生命周期相关的 **3 张表把"完整工厂运行 snapshot"反复原样存进了 SQLite**，每行 ~130 MB；322 条已提交策略 × 130 MB × 3 张表 ≈ 125 GB。文件膨胀绝大部分来自这里。
>
> **不是**：`auto_vacuum=0` 导致 freelist 不回收（这是次要因素，删除前 freelist 才 11 page，删除后才涨到 31.5M page）。也不是 kline_1d / stock_quotes / strategy_factory_full_market_scores 这些大行数表（dbstat 显示加起来 < 500 MB）。
>
> **范围**：本方案聚焦"为什么 3 张表会把完整 snapshot 反复存进去"，并给出"裁剪 → 引用化 → retention → 一次性回收"四步治理。`auto_vacuum / VACUUM` 是配套手段，不是修复主线。

---

## 0. TL;DR

实测 3 张主犯表（数据来自用户独立审查）：

| 表 | 行数 | 平均每行 | 总占用 |
|---|---:|---:|---:|
| `strategy_execution_audit_snapshots.snapshot` | 326 | 130,868,228 字符 | ~39.7 GiB |
| `strategy_closure_snapshots.snapshot` | 325 | ~130.9 MB | ~39.6 GiB |
| `strategy_lineage.birth_regime` | 323 | 130,868,228 字符 | ~39.4 GiB |
| **合计** | — | — | **~118.7 GiB** |

每条已提交的策略会同时写 3 张表，每张表存几乎同一份 ~130 MB 的工厂 cycle 全量 snapshot。

| 阶段 | 目标 | 验收 |
|---|---|---|
| **S0** | `strategy_lineage.birth_regime` 不再存 cycle 全量 snapshot | 单行 ≤ 50 KB（恢复原始语义：fear_greed/regime/sector 字典） |
| **S1** | `strategy_execution_audit_snapshots.snapshot` 入库前裁剪 | 单行 ≤ 200 KB（保留 verdict/audit_summary，丢弃工厂 cycle 大字段） |
| **S2** | `strategy_closure_snapshots.snapshot` 不再嵌套 audit_snapshot 也不再 inline 整 cycle 结果 | 单行 ≤ 200 KB |
| **S3** | 3 张表加 retention（保留 N 条/策略） | 跑 50 条策略，3 张表合计 ≤ 100 MB |
| **S4** | 现有 121 GB 文件一次性回收 | `du -sh` ≤ 1 GB |
| **S5** | 配套：连接初始化加 `auto_vacuum=INCREMENTAL`、cycle 后 `wal_checkpoint(TRUNCATE)` | 跑 50 轮文件不再涨 |
| **S6** | 监控：3 张表 row 平均字节告警；DB 文件大小面板 | 单行 > 1 MB 告警；DB > 5 GB 告警 |

修复顺序：**S0 → S1 → S2 → S3 → S4 → S5 → S6**。S0–S3 是**治本**（写入端裁剪），S4 回收历史污染，S5 是**配套**（防止小膨胀慢慢累积），S6 是兜底监控。

---

## 0.5 当前实施状态

| 阶段 | 完成度 | 关键判断 |
|---|---|---|
| S0 strategy_lineage.birth_regime 裁剪 | ⏳ 待落地 | — |
| S1 execution_audit_snapshot 裁剪 | ⏳ 待落地 | — |
| S2 closure_snapshot 反嵌套 + 裁剪 | ⏳ 待落地 | — |
| S3 3 张表 retention | ⏳ 待落地 | — |
| S4 现有 DB 一次性回收 | ⏳ 待落地 | — |
| S5 auto_vacuum + wal_checkpoint | ⏳ 待落地 | — |
| S6 监控告警 | ⏳ 待落地 | — |

---

## 1. 现状证据

> 数据采集时间：2026-05-18 00:30
> 数据库路径：`data/db/akshare_mcp.sqlite3`

### 1.1 文件状态

```text
文件创建时间                  2026-05-16 12:53:48
文件最后修改时间              2026-05-18 00:11:48
跨度                           ~35 小时
工厂运行轮次                   65 轮
已提交策略                     354 条
文件大小                       129.6 GB
```

### 1.2 三张主犯表

```text
strategy_execution_audit_snapshots
  rows                        326
  avg LENGTH(snapshot)        130,868,228 字符 (~125 MB / 行)
  total                       ~39.7 GiB

strategy_closure_snapshots
  rows                        325
  avg LENGTH(snapshot)        ~130.9 MB / 行
  total                       ~39.6 GiB

strategy_lineage
  rows                        323
  avg LENGTH(birth_regime)    130,868,228 字符 (~125 MB / 行)
  total                       ~39.4 GiB

3 张表合计                   ~118.7 GiB（占文件 91.7%）
```

### 1.3 普通业务表（不是元凶）

```text
表                              行数         dbstat 占用
kline_1d                       1,289,611    143 MB
stock_quotes                     159,216     13 MB
strategy_factory_full_market_scores  138,240   ~37 MB
factor_values                     31,164    1 MB
所有正常表合计                                 < 500 MB
```

### 1.4 写入频率

每条**已提交的策略**会触发：
- 1 次 `save_strategy_lineage(strategy_id, parent_id, reason, snapshot)` → `strategy_lineage` 写 1 行 ~125 MB
- 1 次 `build_execution_audit_snapshot_payload(...)` + upsert → `strategy_execution_audit_snapshots` 写/更新 1 行 ~125 MB
- 多次 `upsert_strategy_closure_snapshot(snapshot=result)` → `strategy_closure_snapshots` 每 strategy_id × snapshot_type 1 行 ~131 MB

---

## 2. 根因分析

### 2.1 第一层：`strategy_lineage.birth_regime` 字段语义错位

**写入端调用**（`packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner_parts/submission_flow.py:46-48`）：

```python
result = (
    save_lineage(strategy_id, parent_strategy_id, reason, snapshot, metadata=lineage_metadata)
    if accepts_metadata
    else save_lineage(strategy_id, parent_strategy_id, reason, snapshot)
)
```

第 4 个位置参数传的是 **完整工厂 cycle snapshot**（包含 stages、quality_gate、backtest_report、execution_audit 等）。

**落地端实现**（`packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_strategy_crud_core.py:389-397`）：

```python
async def save_strategy_lineage(self, strategy_id: str, parent_id: Optional[str],
                                 spawn_reason: str, birth_regime: dict) -> None:
    async with self.acquire() as conn:
        await conn.execute(
            """INSERT INTO strategy_lineage (strategy_id, parent_id, spawn_reason, birth_regime)
               VALUES ($1, $2, $3, $4)""",
            strategy_id, parent_id, spawn_reason,
            json.dumps(birth_regime, ensure_ascii=False, default=str),  # ← 整坨序列化
        )
```

字段名叫 `birth_regime`（"出生市场环境"，原意应该是 ~10 KB 的 fear_greed/sector/regime 字典），但调用方传进来的是 **整个 cycle snapshot ~125 MB**。`json.dumps` 不做任何裁剪。

字段语义随业务演化漂移、调用层换了对象、底层字段名没改，CI 没拦——**这是 storage 端的语义合约破裂**。

### 2.2 第二层：`build_execution_audit_snapshot_payload` 不裁剪

`packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/execution_audit_snapshot.py:160-251`：

```python
def build_execution_audit_snapshot_payload(
    *, strategy_id, gate, audit, verification, acceptance,
    snapshot, ...,
) -> dict[str, Any]:
    ...
    snapshot_payload = dict(snapshot or {})   # ← 只是 shallow copy
    ...
    dto = ExecutionAuditSnapshot(
        ...
        verification=verification_payload,
        acceptance=acceptance_payload,
        audit_summary={ "audit_ready_for_hard_gate": resolved_hard_gate },
        snapshot=snapshot_payload,             # ← 整坨 cycle snapshot 当 snapshot 字段
        metadata=dict(metadata or {}),
    )
```

`ExecutionAuditSnapshot` 设计本意是"执行审计快照"——只保留 verdict、audit_summary、verification、acceptance 这些**审计结论**就够了。但代码里 **额外塞了一个 `snapshot` 字段把 cycle 整坨原文留下**，落到 `strategy_execution_audit_snapshots.snapshot` 列时整坨 JSON 写进去。

这是 **DTO 字段冗余**——审计结论需要的字段（verdict/acceptance）已经独立提取，但还多塞了"原始 snapshot"这一项。

### 2.3 第三层：`overview.py` 双重嵌套放大

`packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py`：

```python
# Line 803-805: 在构建 result 时，把已经 ~125 MB 的 audit_snapshot 嵌进 result
result = {
    ...
    "execution_quality_snapshot": execution_quality_snapshot,
    "execution_audit_snapshot": execution_audit_snapshot,   # ← 完整 audit_snapshot 嵌进来
    ...
}

# Line 943-957: 然后又把 result 整体当 snapshot 存到 closure_snapshots
closure_snapshot = await upsert_strategy_closure_snapshot({
    "strategy_id": strategy_id,
    "snapshot_type": "incubation_overview",
    ...,
    "snapshot": result,                                       # ← result 整体进 snapshot 列
    "metadata": { ... },
})
```

**双重嵌套**：
1. `execution_audit_snapshot` 已经包含 ~125 MB cycle 全量
2. `result["execution_audit_snapshot"] = execution_audit_snapshot` —— result 里嵌进 audit_snapshot
3. `upsert(... "snapshot": result ...)` —— closure_snapshots 又存了 result

落到 DB：`strategy_closure_snapshots.snapshot` 单行 ~131 MB，几乎全部是 `execution_audit_snapshot` 的复制品。**和 `strategy_execution_audit_snapshots.snapshot` 同一份数据，但因为是 result 的子字段，没人共享**。

### 2.4 第四层：3 张表的 ON DELETE CASCADE 让它们随 strategies 寿命绑定

```sql
strategy_execution_audit_snapshots: REFERENCES strategies(id) ON DELETE CASCADE
strategy_closure_snapshots:         REFERENCES strategies(id) ON DELETE CASCADE
strategy_lineage:                   strategy_id (无 FK，但通过 strategy_id 关联)
```

CASCADE 是好事，但**这 3 张表本身没有 retention 机制**——每条 strategies 行只要不被删，3 张表的对应行就一直存在。354 条 submitted 全部累积。

### 2.5 第五层（次要）：SQLite freelist 不回收

`auto_vacuum=0` + 工厂从未调用 `VACUUM` / `incremental_vacuum`：
- `S0–S3` 修了 → 历史 121 GB 仍然不会自动缩
- 这是 **配套问题**，不是膨胀的主因

主因是写入端**每行 130 MB**，配套问题是**已写入的数据删不掉空间**。即使配套问题不解决，只要 S0–S3 修好，新 DB 不会再涨；老 DB 通过 S4（dump-and-restore）一次性回收。

### 2.6 综合：膨胀路径

```
单条已提交的策略
  └── save_strategy_lineage(strategy_id, parent_id, reason, snapshot)
       → strategy_lineage.birth_regime = json.dumps(整坨 cycle snapshot ~125 MB)
       → 1 行 ~125 MB

  └── build_execution_audit_snapshot_payload(snapshot=cycle snapshot)
       → ExecutionAuditSnapshot.snapshot = 整坨 cycle snapshot
       → upsert → strategy_execution_audit_snapshots.snapshot = ~125 MB
       → 1 行 ~125 MB

  └── _assemble_overview_result(...) 包含 execution_audit_snapshot
       → result["execution_audit_snapshot"] = 整坨 cycle snapshot 副本
       → upsert_strategy_closure_snapshot(snapshot=result)
       → strategy_closure_snapshots.snapshot = ~131 MB
       → 1 行 ~131 MB（其中 ~125 MB 是 audit_snapshot 的复制）

每条策略累积 ~381 MB
322 条策略 ≈ 122 GB
```

---

## 3. 修复方案

### S0 ｜ `strategy_lineage.birth_regime` 恢复字段语义

#### S0.1 问题精确定位

调用方传 `snapshot`（整 cycle），但字段名叫 `birth_regime`（出生市场环境）。语义错位，必须任选其一对齐：
- 方案 A：调用方裁剪——只传 `{fear_greed, regime, hot_sectors, factor_research}` 之类的轻量 dict
- 方案 B：落地端裁剪——`save_strategy_lineage` 内部对 birth_regime 做 size guard

**推荐 A**：从语义上看，`strategy_lineage` 关心的是"这条策略出生时的市场状态"，cycle 全量根本不属于谱系信息。

#### S0.2 改动方案

```python
# packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner_parts/submission_flow.py
# _save_strategy_lineage_record 中，传给 save_lineage 的不再是 snapshot 整体

@classmethod
async def _save_strategy_lineage_record(
    cls, db, *, strategy_id, parent_strategy_id, reason, snapshot, candidate=None,
) -> None:
    save_lineage = cls._get_optional_db_method(db, "save_strategy_lineage")
    if save_lineage is None:
        return
    # PR-S0: 只把市场状态字段提取出来，不再传整 cycle snapshot
    birth_regime = cls._extract_birth_regime(snapshot)
    ...
    result = save_lineage(strategy_id, parent_strategy_id, reason, birth_regime, metadata=lineage_metadata)
    ...

@classmethod
def _extract_birth_regime(cls, snapshot: dict) -> dict:
    """从 cycle snapshot 抽取 ~10 KB 的市场状态字典。"""
    snap = dict(snapshot or {})
    return {
        "fg_level": snap.get("fg_level"),
        "fear_greed_index": snap.get("fear_greed_index"),
        "hot_sectors": list(snap.get("hot_sectors") or [])[:8],
        "cold_sectors": list(snap.get("cold_sectors") or [])[:8],
        "factor_research": dict(snap.get("factor_research") or {}).get("summary", {}),
        "active_factors": list(dict(snap.get("factor_research") or {}).get("active_factors") or [])[:6],
        "regime_summary": dict(snap.get("regime_summary") or {}),
        "as_of": snap.get("as_of") or snap.get("date"),
    }
```

#### S0.3 改动文件

| 文件 | 改动 |
|---|---|
| `packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner_parts/submission_flow.py` | `_save_strategy_lineage_record` 加 `_extract_birth_regime` |
| `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_strategy_crud_core.py` | `save_strategy_lineage` 加 size guard 兜底（≤ 50 KB；超过截断告警） |
| `packages/strategy-factory/tests/test_strategy_lineage_birth_regime.py` | 新增。验证传入 cycle snapshot 时落地的 birth_regime ≤ 50 KB 且字段为预期子集 |

#### S0.4 验收

- 新提交策略的 `strategy_lineage.birth_regime` 单行 ≤ 50 KB
- 落地端 size guard 触发警告 = 0（说明调用方都裁剪好了）
- `birth_regime` JSON 包含 fg_level / hot_sectors / factor_research 等核心字段

---

### S1 ｜ `strategy_execution_audit_snapshots.snapshot` 入库前裁剪

#### S1.1 问题精确定位

`ExecutionAuditSnapshot` DTO 同时持有：
- 已结构化的字段（verdict / verification / acceptance / audit_summary）
- 一个冗余的 `snapshot` 字段（整 cycle 副本）

`snapshot` 字段是**冗余的**——审计结论已经在结构化字段里。

#### S1.2 改动方案

**改动 1**：`ExecutionAuditSnapshot.snapshot` 入库前裁剪。

```python
# packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/execution_audit_snapshot.py

# 在 build_execution_audit_snapshot_payload 末尾追加：

snapshot_payload = _trim_audit_snapshot(snapshot_payload)
```

```python
def _trim_audit_snapshot(snapshot: dict) -> dict:
    """裁剪 cycle snapshot，只保留审计相关字段。"""
    if not snapshot:
        return {}
    return {
        # 必要的 trace / 标识
        "snapshot_id": snapshot.get("snapshot_id"),
        "as_of": snapshot.get("as_of") or snapshot.get("date"),
        "factory_run_id": snapshot.get("factory_run_id"),
        "correlation_id": snapshot.get("correlation_id"),
        "trace_id": snapshot.get("trace_id"),

        # 审计判定结果
        "execution_audit_gate_status": snapshot.get("execution_audit_gate_status"),
        "execution_audit_gate_reasons": list(snapshot.get("execution_audit_gate_reasons") or [])[:20],
        "execution_hard_gate_passed": snapshot.get("execution_hard_gate_passed"),
        "audit_ready_for_hard_gate": snapshot.get("audit_ready_for_hard_gate"),
        "verdict": dict(snapshot.get("verdict") or {}),

        # 不要 stages / quality_gate / backtest_report 等大字段
    }
```

**改动 2**：写入端 size guard 兜底。

```python
# packages/akshare-mcp/src/akshare_mcp/storage/sqlite/strategy_execution_audit_snapshots queries

# upsert 时给 snapshot 字段加 _encode_inline_json_with_guard，max=200 KB，超过 fallback summary
```

#### S1.3 改动文件

| 文件 | 改动 |
|---|---|
| `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/execution_audit_snapshot.py` | `build_execution_audit_snapshot_payload` 末尾调用 `_trim_audit_snapshot`；新增 `_trim_audit_snapshot` |
| `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/<execution_audit_writes>.py` | upsert 时对 `snapshot` 列加 200 KB size guard |
| `packages/akshare-mcp/tests/test_execution_audit_snapshot_trimming.py` | 新增。验证 snapshot 仅保留审计字段、不含 stages / quality_gate |

#### S1.4 验收

- `strategy_execution_audit_snapshots.snapshot` 单行 ≤ 200 KB
- 审计字段（verdict / gate_status / hard_gate_passed）完整
- 不再包含 `stages` / `quality_gate` / `backtest_report` / `factory_run_summary` 这些 cycle 大字段

---

### S2 ｜ `strategy_closure_snapshots.snapshot` 反嵌套 + 裁剪

#### S2.1 问题精确定位

```python
# overview.py:803  在 result 里嵌入完整 audit_snapshot
result = { ..., "execution_audit_snapshot": execution_audit_snapshot, ... }

# overview.py:957  又把整个 result 当 snapshot 存
upsert_strategy_closure_snapshot({ ..., "snapshot": result, ... })
```

closure_snapshot 应该是 **生命周期 closure 视图**（incubation overview / promotion overview 之类），关心的是"当前策略生命周期处于哪个阶段、各 quality 维度状态"，不需要把 audit_snapshot 整坨复制进来。

#### S2.2 改动方案

**改动 1**：`result` 里只保留 audit_snapshot 的 ID 和必要 metadata。

```python
# packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py

# 修改 _assemble_overview_result（line ~775）
result = {
    ...
    "execution_quality_snapshot": execution_quality_snapshot,
    # PR-S2: 只引用 audit_snapshot 的 ID，不嵌入完整对象
    "execution_audit_snapshot_ref": {
        "snapshot_id": (execution_audit_snapshot or {}).get("snapshot_id"),
        "as_of": (execution_audit_snapshot or {}).get("as_of"),
        "verdict_status": (execution_audit_snapshot or {}).get("verdict_status"),
        "execution_hard_gate_passed": (execution_audit_snapshot or {}).get("execution_hard_gate_passed"),
    },
    # 删除原 "execution_audit_snapshot": execution_audit_snapshot
    ...
}
```

**改动 2**：upsert 时再裁剪一次（兜底）。

```python
# overview.py:line 943
closure_snapshot = await upsert_strategy_closure_snapshot({
    ...
    "snapshot": _trim_closure_snapshot(result),   # PR-S2: 入库前裁剪
    "metadata": { ... },
})

def _trim_closure_snapshot(result: dict) -> dict:
    """裁剪 closure snapshot，去掉嵌套的大对象。"""
    snap = dict(result or {})
    # 已经引用化的字段保留 _ref，删除原字段
    for big_field in ("execution_audit_snapshot", "quality_report", "backtest_report"):
        snap.pop(big_field, None)
    return snap
```

**改动 3**：读取端反向解引用（按需 join 拉 audit_snapshot）。

```python
# overview.py 读取 cached closure 时
def _resolve_audit_snapshot_ref(result, db):
    ref = result.get("execution_audit_snapshot_ref") or {}
    if ref.get("snapshot_id") and db:
        full = await db.get_execution_audit_snapshot_by_id(ref["snapshot_id"])
        if full:
            result["execution_audit_snapshot"] = full
    return result
```

#### S2.3 改动文件

| 文件 | 改动 |
|---|---|
| `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py` | line 803 改 `execution_audit_snapshot_ref`；line 957 用 `_trim_closure_snapshot`；新增 `_resolve_audit_snapshot_ref` |
| `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/<closure_snapshot_writes>.py` | upsert 时对 `snapshot` 列加 200 KB size guard |
| `packages/akshare-mcp/tests/test_closure_snapshot_trimming.py` | 新增。验证 cached closure 不含 audit_snapshot 整体 + 读取时正确解引用 |

#### S2.4 验收

- `strategy_closure_snapshots.snapshot` 单行 ≤ 200 KB
- 读取端通过 `_ref` 拉到完整 audit_snapshot（功能不退化）
- 不再有 `result["execution_audit_snapshot"]` 完整副本

---

### S3 ｜ 3 张表加 retention

S0–S2 修了**新数据**不会涨，但**已 submitted 的策略累积**仍会让 3 张表行数无限涨。需要 retention。

#### S3.1 改动方案

每张表保留每个 `strategy_id` 的最近 N 条；超过的删除。

```sql
-- strategy_lineage：每个 strategy_id 只保留 1 条（lineage 是 spawn 时唯一记录，本来就该 1:1）
DELETE FROM strategy_lineage
WHERE id NOT IN (
    SELECT MAX(id) FROM strategy_lineage GROUP BY strategy_id
);

-- strategy_execution_audit_snapshots：通过 PRIMARY KEY (strategy_id) 已经 1:1
-- 无需额外 retention

-- strategy_closure_snapshots：PRIMARY KEY (strategy_id, snapshot_type) 已经 1:1 per type
-- 无需额外 retention

-- 但需要：当 strategies 表本身做 archival/cleanup 时，CASCADE 自动清掉对应 3 张表行
-- → 加 strategies 表 retention 策略
```

实际上 `strategy_execution_audit_snapshots` PK 是 `strategy_id`、`strategy_closure_snapshots` PK 是 `(strategy_id, snapshot_type)`——本来就是 1:1。问题不是行数太多，是**单行太大**。所以 S3 主要是给 `strategies` 表加 retention，让 CASCADE 触发清理。

```python
# packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_loop_parts/policy.py

async def _post_cycle_strategy_retention(self, db) -> None:
    """每轮工厂后清理过老的 rejected/eliminated 策略。"""
    days_to_keep = int(os.getenv("STRATEGY_FACTORY_REJECTED_RETENTION_DAYS", "7"))
    if days_to_keep <= 0:
        return
    async with db.acquire() as conn:
        # 删除 7 天前的 rejected 策略（CASCADE 会自动清 audit/closure/lineage）
        await conn.execute(f"""
            DELETE FROM strategies
            WHERE status IN ('rejected', 'eliminated')
              AND datetime(created_at) < datetime('now', '-{days_to_keep} days')
        """)
```

#### S3.2 改动文件

| 文件 | 改动 |
|---|---|
| `packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_loop_parts/policy.py` | 新增 `_post_cycle_strategy_retention`，cycle 结束后调用 |
| `.env.example` | 新增 `STRATEGY_FACTORY_REJECTED_RETENTION_DAYS=7` |
| `packages/strategy-factory/tests/test_strategy_retention.py` | 新增。验证 7 天前 rejected 策略被清，对应 3 张表 CASCADE 清掉 |

#### S3.3 验收

- 跑 50 条 submitted + 100 条 rejected + 等 7 天后回来跑一轮，rejected 全部 CASCADE 清掉
- 3 张主犯表合计行数稳定（每条 submitted 1 行）

---

### S4 ｜ 现有 121 GB 文件一次性回收

**前提**：当前磁盘只剩 187 MB，无法在原盘做 VACUUM。

#### S4.1 改动方案

由于 S0–S2 已经把新写入裁剪到 ≤ 200 KB / 行，但**历史的 322 行 × 130 MB = 122 GB 仍然在表里**，这部分必须显式 DELETE 或 TRUNCATE。

**方案 A（推荐）**：直接 `DELETE FROM` 历史大行 → backup API 导出（只复制活跃 page，不带 freelist）→ 替换原文件。

```bash
# 1. 大胆删除（只删那 3 张表的历史污染数据；保留 strategies 表）
sqlite3 data/db/akshare_mcp.sqlite3 "
  DELETE FROM strategy_lineage;
  DELETE FROM strategy_execution_audit_snapshots;
  DELETE FROM strategy_closure_snapshots;
"

# 2. backup API 写到外部盘（需要 ~500 MB 临时空间）
sqlite3 data/db/akshare_mcp.sqlite3 ".backup /external_disk/clean.sqlite3"

# 3. 替换
mv data/db/akshare_mcp.sqlite3 /external_disk/old_huge.sqlite3
mv /external_disk/clean.sqlite3 data/db/akshare_mcp.sqlite3

# 4. 验证
ls -lh data/db/akshare_mcp.sqlite3   # < 1 GB
sqlite3 data/db/akshare_mcp.sqlite3 "SELECT COUNT(*) FROM strategies;"  # 应该 = 354
```

> **注意**：S0–S2 必须先做完，否则下次工厂跑又会把那 3 张表写满。

#### S4.2 改动文件

| 文件 | 改动 |
|---|---|
| `scripts/db_compact.py` | 新增。封装方案 A：删除 3 张表 + backup → 替换 |
| `Makefile` | 新增 target `make db-compact` |
| `docs/runbooks/sqlite_bloat_recovery.md` | 新增运维手册 |

#### S4.3 验收

- 文件大小 < 1 GB
- `strategies` / `kline_1d` 等业务表行数完全一致
- 3 张主犯表行数 = 0（待重新写入）

---

### S5 ｜ 配套：`auto_vacuum=INCREMENTAL` + WAL truncate

S0–S3 修完后，新 DB 不会再涨。但**为了防止小膨胀慢慢累积**，加配套。

#### S5.1 改动方案

**改动 1**：连接初始化加 `auto_vacuum=INCREMENTAL`。

```python
# packages/akshare-mcp/src/akshare_mcp/storage/sqlite/schema_base.py:449

conn = sqlite3.connect(str(self.path), ...)
conn.row_factory = sqlite3.Row
conn.execute(f"PRAGMA busy_timeout = {_busy_timeout_ms()}")
conn.execute(f"PRAGMA journal_mode = {_journal_mode()}")
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA synchronous = NORMAL")
# PR-S5
conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # 仅对新 DB 或 VACUUM 后生效
```

**改动 2**：cycle 结束后 `wal_checkpoint(TRUNCATE)` + `incremental_vacuum`。

```python
# policy.py:_post_cycle_maintenance
async def _post_cycle_maintenance(self, db) -> None:
    pages = int(os.getenv("STRATEGY_FACTORY_VACUUM_PAGES_PER_CYCLE", "1000"))
    async with db.acquire() as conn:
        await conn.execute(f"PRAGMA incremental_vacuum({pages})")
        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

#### S5.2 改动文件

| 文件 | 改动 |
|---|---|
| `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/schema_base.py` | `_open_connection` 加 `PRAGMA auto_vacuum = INCREMENTAL` |
| `packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_loop_parts/policy.py` | `_post_cycle_maintenance` |
| `.env.example` | `STRATEGY_FACTORY_VACUUM_PAGES_PER_CYCLE=1000` |

#### S5.3 验收

- `PRAGMA auto_vacuum` 返回 2 (INCREMENTAL)
- 跑 50 轮工厂，文件不增长超过 100 MB
- WAL 文件每轮 < 4 MB

---

### S6 ｜ 监控告警

#### S6.1 SQL view

```sql
CREATE VIEW IF NOT EXISTS view_db_health AS
SELECT
    (SELECT COUNT(*) FROM strategies) AS strategy_count,
    (SELECT AVG(LENGTH(birth_regime)) FROM strategy_lineage) AS avg_lineage_bytes,
    (SELECT MAX(LENGTH(birth_regime)) FROM strategy_lineage) AS max_lineage_bytes,
    (SELECT AVG(LENGTH(snapshot)) FROM strategy_execution_audit_snapshots) AS avg_audit_bytes,
    (SELECT MAX(LENGTH(snapshot)) FROM strategy_execution_audit_snapshots) AS max_audit_bytes,
    (SELECT AVG(LENGTH(snapshot)) FROM strategy_closure_snapshots) AS avg_closure_bytes,
    (SELECT MAX(LENGTH(snapshot)) FROM strategy_closure_snapshots) AS max_closure_bytes;
```

#### S6.2 desktop 面板 + 告警

```python
# _post_cycle_maintenance 加告警
file_size_gb = os.path.getsize(db_path) / 1024**3
if file_size_gb > 5:
    logger.error("DB file %.1f GB > 5 GB", file_size_gb)

row = await conn.fetchrow("SELECT * FROM view_db_health")
for col in ("max_lineage_bytes", "max_audit_bytes", "max_closure_bytes"):
    if row[col] and row[col] > 1_000_000:
        logger.error("3 主犯表单行 %s = %s bytes（应 ≤ 200 KB），可能有写入端没接入裁剪", col, row[col])
```

#### S6.3 改动文件

| 文件 | 改动 |
|---|---|
| `packages/akshare-mcp/src/akshare_mcp/storage/sqlite/migrations/0xxx_db_health_view.sql` | 新增 view |
| `desktop/src/components/DbHealthPanel.tsx` | 新增面板 |
| `policy.py:_post_cycle_maintenance` | 加 3 张表行 size 告警 |

#### S6.4 验收

- view 可查
- 单行 > 1 MB 触发 ERROR 日志
- 面板 60s 刷新

---

## 4. 优先级与实施顺序

### 4.1 依赖关系

```
S0 (lineage)            独立
S1 (audit)              独立
S2 (closure)            依赖 S1（_trim_audit_snapshot 会被 S2 引用）
S3 (retention)          独立；和 S0–S2 互补：S0–S2 治新写入，S3 治历史累积
S4 (现有 DB 回收)        依赖 S0/S1/S2（否则下次写入又把 3 张表填满）
S5 (auto_vacuum 配套)    独立
S6 (监控)               依赖 S0/S1/S2（这样监控指标才有意义）
```

最优 DAG：

```
S0 (lineage 字段语义)     ┐
S1 (audit 裁剪)           ├─→ S2 (closure 反嵌套) ─→ S4 (一次性回收) ─→ S6 (监控)
                          │                          │
S3 (retention)            │                          │
S5 (auto_vacuum)          ┘                          │
                                                     ↓
                                              生产连续运行验收
```

### 4.2 推进切分

| 里程碑 | 时间 | 内容 | 验收 |
|---|---|---|---|
| **DB-M1：止血新写入** | Day 1 | S0 + S1 + S2 三个裁剪 + 单测 | 跑 1 轮工厂，3 张表新写入行 ≤ 200 KB |
| **DB-M2：回收历史** | Day 2 上午 | S4 dump-and-rebuild | DB 文件 ≤ 1 GB |
| **DB-M3：retention + 配套** | Day 2 下午 | S3 + S5 | 跑 50 轮文件不增长 > 100 MB |
| **DB-M4：监控** | Day 3 | S6 view + 面板 + 告警 | 单行 > 1 MB 告警可触发 |

总计：**必做 DB-M1+DB-M2 = 1.5 天；全套 3 天**。

### 4.3 上线门禁

- DB-M1 必须先于 DB-M2：否则 S4 后下次工厂运行又会把 3 张表填满
- DB-M2 在离线维护窗口做：需要 dump 到外部盘；维护期间工厂不能跑
- 单测覆盖：`pytest packages/strategy-factory/tests packages/akshare-mcp/tests` 全绿
- 上线前用 `stage` 环境跑 6 小时，确认 DB 文件 < 100 MB（相比 121 GB 是 1000× 改善）

---

## 5. 验收清单

### 5.1 S0 验收

| 指标 | 基线 | 首轮目标 | 稳态目标 |
|---|---|---|---|
| `strategy_lineage` 单行 max bytes | 130,868,228 | ≤ 50 KB | ≤ 50 KB |
| `strategy_lineage` 单行 avg bytes | 130,868,228 | ≤ 20 KB | ≤ 20 KB |
| 落地端 size guard 触发警告 | N/A | 0 | 0 |
| `birth_regime` 包含核心字段（fg_level/regime/factor_research） | 不可读（太大） | ✅ | ✅ |

### 5.2 S1 验收

| 指标 | 基线 | 首轮目标 | 稳态目标 |
|---|---|---|---|
| `strategy_execution_audit_snapshots.snapshot` max bytes | 130,868,228 | ≤ 200 KB | ≤ 100 KB |
| 单行 avg bytes | 130,868,228 | ≤ 100 KB | ≤ 50 KB |
| `verdict / gate_status / hard_gate_passed` 完整 | ✅（被淹没） | ✅ | ✅ |
| 不含 `stages / quality_gate / backtest_report` | 包含 | 不含 | 不含 |

### 5.3 S2 验收

| 指标 | 基线 | 首轮目标 | 稳态目标 |
|---|---|---|---|
| `strategy_closure_snapshots.snapshot` max bytes | 130.9 MB | ≤ 200 KB | ≤ 100 KB |
| 包含 `execution_audit_snapshot` 完整对象 | 是 | 否（仅 _ref） | 否 |
| 通过 `_ref` 解引用拉到完整 audit | N/A | 成功 | 成功 |

### 5.4 S3 验收

| 指标 | 基线 | 首轮目标 | 稳态目标 |
|---|---|---|---|
| `strategies WHERE status='rejected' AND created_at < 7d ago` 行数 | 累积 | 自动清 | 自动清 |
| 3 张主犯表行数 | 累积 | 1:1 with active strategies | 1:1 |
| retention sweep 单次耗时 | N/A | ≤ 200 ms | ≤ 100 ms |

### 5.5 S4 验收

| 指标 | 基线 | 完成后目标 |
|---|---|---|
| DB 文件大小 | 129.6 GB | ≤ 1 GB |
| 业务表 COUNT(\*)（kline_1d / strategies / vector_profiles 等） | 同 §1.3 | 完全一致 |
| 3 张主犯表 | 326/325/323 行 × ~130 MB | 0 行（待重新写入） |
| 工厂跑 1 轮的功能验证 | 工作 | 工作 |

### 5.6 S5 验收

| 指标 | 基线 | 首轮目标 | 稳态目标 |
|---|---|---|---|
| `PRAGMA auto_vacuum` | 0 | 2 | 2 |
| 跑 50 轮总膨胀 | ~100 GB | ≤ 100 MB | ≤ 50 MB |
| WAL 文件大小 | 80+ MB | ≤ 4 MB | ≤ 1 MB |

### 5.7 S6 验收

| 指标 | 基线 | 目标 |
|---|---|---|
| `view_db_health` 可查 | ❌ | ✅ |
| 单行 > 1 MB 触发告警 | ❌ | ✅ |
| desktop 面板 60s 刷新 | ❌ | ✅ |

### 5.8 全套验收（DB-M1–M4 完成后）

- 连续运行工厂 24 小时（生产连续模式），DB 文件大小稳定在 < 1 GB
- 3 张主犯表平均行 < 200 KB，最大行 < 1 MB
- 提交流程功能完全不退化（quality_gate / submission / lifecycle 全过）
- 监控告警可触发

---

## 6. 这次"131 GB 膨胀"的复盘要点

### 6.1 诊断演变（4 次错误，1 次正确）

1. **第一次错误**：以为是数据真的写了 121 GB。但 SUM(LENGTH(\*)) 的常用统计 ~500 MB，量级对不上。
2. **第二次错误**：以为是 SQLite freelist 不回收。`auto_vacuum=0 + freelist_count=11` 的状态读成"几乎没废 page"——其实那是 DELETE 之前的状态。
3. **第三次错误**：以为是 `strategy_factory_run_artifacts.payload_json` 平均 1.2 MB 导致。1.2 MB × 514 行 = 617 MB，量级又对不上。
4. **第四次错误**：以为是 `replace_full_market_scores` 每轮 5,120 行周转 + `_encode_factory_run_json` 21MB→2MB 中间态。这些写入模式确实有膨胀，但量级 < 5 GB / 65 轮，远不到 121 GB。
5. **第五次正确（用户独立审查发现）**：3 张表 `strategy_lineage / strategy_execution_audit_snapshots / strategy_closure_snapshots` 各存了 322–326 条 ~130 MB 的工厂 cycle 全量 snapshot。3 × 322 × 130 MB ≈ 122 GB，完美对上。

### 6.2 为什么前 4 次都看不到这 3 张表

- 我前期用 `SUM(LENGTH(*))` 这种聚合，但因为这 3 张表用了 `LENGTH(*)` 这种不存在的语法（`*` 不能作为 LENGTH 参数），SQL 静默 ERR'd 跳过了
- `dbstat` 因为磁盘满跑不动
- `.tables` 列了 127 张表但我没逐张点
- 需要"按列名一个个测 LENGTH"或者"专门查这 3 张表"才能命中

### 6.3 SQLite 文件膨胀诊断标准流程（修正版）

```
1. 看文件大小：du -sh DB
2. 看 page 状态：PRAGMA page_count; PRAGMA freelist_count;
3. 列出所有 TEXT/BLOB 列：
   SELECT m.name AS table_name, p.name AS col_name
   FROM sqlite_master m, pragma_table_info(m.name) p
   WHERE m.type='table' AND p.type IN ('TEXT', 'BLOB');
4. 对每个 TEXT/BLOB 列单独查：
   SELECT COUNT(*), AVG(LENGTH(<col>)), MAX(LENGTH(<col>)) FROM <table>;
5. 找单行 > 1 MB 的列 = 膨胀元凶
6. 看 auto_vacuum / VACUUM 历史 = 配套问题
```

第 3 步是关键：**枚举所有 TEXT/BLOB 列，逐个测 LENGTH**。这次错过 3 张主犯表就是因为我没做这一步。

### 6.4 不变量

- 任何**写入端 → 落地端**的字段名/语义都必须一致；如果字段名叫 `birth_regime`，调用方就不能传 cycle snapshot 整体
- 任何 TEXT 列写入必须有 size guard（200 KB 是合理上限，超过 fallback summary）
- 任何"嵌套对象 + 整体 upsert"的模式都要避免（S2 的 closure 反嵌套就是这个例子）
- DTO 设计时要分清"结构化字段" vs "原始 raw"，不要两者并存

任意一项不满足，都可能让某张表的单行涨到 100 MB+。

---

> _本文档随各 PR 落地随时更新；§0 表是当前状态唯一真实来源。_
