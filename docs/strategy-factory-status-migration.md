# Strategy Factory Cycle Status Migration

This document accompanies the P2 work in
`.kiro/specs/strategy-factory-governance/`. It explains how the
`factory_runs.status` taxonomy is evolving, what the new values mean, and
what each downstream consumer should do.

## TL;DR

Old status (3 buckets):

```
success | partial | failed | skipped
```

New status (6 buckets, plus `partial` kept for read-path compatibility):

```
success
success_no_submission
success_no_strategy
partial_infra
partial_llm
partial            # legacy — write path no longer emits this
failed
skipped
```

The legacy `partial` value will keep showing up in **historical rows**
indefinitely. The new write path
(`run_models.resolve_run_status(...)` with the `summary=` keyword)
never emits `partial`; it always picks one of the more specific values
above.

## Status definitions

| Status | Meaning | Operator action |
|---|---|---|
| `success` | All stages OK; at least one strategy passed Gate-3 *and* was submitted. | None — green path. |
| `success_no_submission` | Gate-3 passed strategies exist, but submission was blocked by dedup / quota / governance. | Inspect `submitted=0` reasons in `summary`. Not infra-degraded. |
| `success_no_strategy` | Cycle ran clean; no candidate passed Gate-3. | Look at `gate_3_failure_topn` and `statistical_metric_missing_counts`. Not infra-degraded. |
| `partial_infra` | warmup / collect / persistence / readiness reported failures. | Page on-call infra. Inspect `warmup_error_topn`. |
| `partial_llm` | LLM timeout ratio > 30% or no-spec ratio > 50%. | Inspect `llm_status_counts`, possibly bump bulk timeout. |
| `partial` | **Legacy.** Only present in historical data. | Treat as "needs reclassification" — usually map to `partial_infra` based on `warmup_failed` / `sync_task_failed_count` summary fields. |
| `failed` | Unrecoverable scheduler / DB / main-flow failure. | Page on-call. |
| `skipped` | Runtime disabled or scheduler short-circuit. | Usually expected during disabled windows. |

## Priority order

When multiple conditions are true, the resolver picks the highest-priority
bucket:

```
failed > skipped > partial_infra > partial_llm
       > success_no_strategy > success_no_submission > success
```

## Backward compatibility for callers

### Read path (dashboards, monitoring)

Existing dashboards that filter on `status = 'partial'` will still match
historical rows but will see fewer of them going forward. To migrate:

1. Treat any of `partial`, `partial_infra`, `partial_llm` as "degraded" if
   you only need a binary signal.
2. If you want the new resolution, group by status and show
   `partial_infra` and `partial_llm` separately.
3. Health dashboards should **not** alert on `success_no_strategy` or
   `success_no_submission`. Those are normal outcomes.

### Write path (`resolve_run_status`)

Callers that already pass `summary=` to `resolve_run_status` get the new
classification automatically. Callers that don't pass `summary=` (legacy
test fixtures, old call sites) get the old `partial` value to avoid a
flag-day breakage. The `cycle_runner` analysis path was updated to pass
`summary=`.

### Compat period

Two-week soft-deprecation window: `partial` keeps being a valid value in
the read path. After that window, ops can grep `status = 'partial'` and
investigate the remaining rows.

## Alert rule changes

Old rule: `alert if status != 'success'`.

New rule:

```
alert if status in {'failed', 'partial_infra'}
warn  if status == 'partial_llm'
ok    otherwise (including success_no_strategy / success_no_submission)
```

## Validating the migration

`packages/strategy-factory/tests/test_cycle_status_resolution.py` covers:

- All six new statuses with their trigger conditions.
- Priority ordering (`failed` > `skipped` > `partial_infra` > `partial_llm`
  > `success_no_strategy` > `success_no_submission` > `success`).
- Property 6: write path never emits the legacy `partial` value.
- Backward compatibility: when `summary=` is omitted, the resolver still
  returns the old `partial`/`success` values.

## Where the new fields live

The resolver inspects `summary` (the `factory_runs.summary` JSON) for:

| Field | Source | Used for |
|---|---|---|
| `gate_3_passed` | already aggregated in `_cycle_success_summary` | `success_no_strategy` decision |
| `submitted` | already aggregated | `success_no_submission` decision |
| `warmup_failed` / `sync_task_failed_count` | added by P0 (cycle_runner_parts/normalizers.py) | `partial_infra` detection |
| `autonomy_task_count` / `task_timeout_skip_count` | already aggregated | `partial_llm` detection (timeout ratio) |
| `llm_status_counts` | already aggregated | `partial_llm` detection (no-spec ratio) |

No schema changes. All fields are strings/ints inside the JSON `summary`
column.
