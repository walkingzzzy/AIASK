#!/usr/bin/env python3
"""Shadow validation harness for trade prediction scoring.

The harness runs the P1-P5 trade-prediction soak plan against an isolated
SQLite copy. It never writes to the production database and it forces live
broker writes off in every child process environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW_DB = REPO_ROOT / "data" / "validation" / "trade_prediction_shadow.sqlite3"
DEFAULT_REPORT_ROOT = REPO_ROOT / "reports" / "ops" / "trade_prediction_shadow"
DEFAULT_BATCH_ID = f"trade_prediction_soak_{date.today().isoformat().replace('-', '_')}"
DEFAULT_AGENT_BASE_URL = "http://127.0.0.1:8767"
REQUIRED_TABLES = (
    "kline_intraday",
    "strategy_trade_predictions",
    "strategy_trade_prediction_outcomes",
)
SAFETY_ENV = {
    "LIVE_TRADING_ENABLED": "0",
    "LIVE_TRADING_ALLOW_WRITE": "0",
    "BROKER_ALLOW_WRITE": "0",
    "LIVE_TRADING_READ_ONLY": "1",
    "BROKER_READ_ONLY": "1",
}
TOGGLE_KEYS = (
    "STRATEGY_TRADE_PREDICTION_PROMOTION_GATE_ENABLED",
    "STRATEGY_TRADE_PREDICTION_BUDGET_FEEDBACK_ENABLED",
    "STRATEGY_TRADE_PREDICTION_FACTOR_DECAY_ENABLED",
)
PARTIAL_STATUSES = {
    "partial_daily_only",
    "partial_intraday_missing",
    "insufficient_samples",
    "post_hoc_rejected",
}
DATA_GAP_STATUSES = {
    "daily_bar_missing",
    "intraday_missing",
    "partial_gap",
    "invalid_ohlc",
}


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path = REPO_ROOT
    timeout_seconds: int = 900


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def append_pythonpath(env: dict[str, str]) -> None:
    paths = [
        REPO_ROOT / "packages" / "aiask-quant-core" / "src",
        REPO_ROOT / "packages" / "akshare-mcp" / "src",
        REPO_ROOT / "packages" / "strategy-factory" / "src",
        REPO_ROOT / "packages" / "agent" / "src",
    ]
    existing = [item for item in str(env.get("PYTHONPATH") or "").split(os.pathsep) if item]
    for path in paths:
        token = str(path)
        if path.exists() and token not in existing:
            existing.insert(0, token)
    env["PYTHONPATH"] = os.pathsep.join(existing)


def resolve_source_db(explicit: str | None = None) -> Path:
    raw = (
        explicit
        or os.getenv("AKSHARE_MCP_SQLITE_PATH")
        or os.getenv("AIASK_SQLITE_PATH")
        or str(Path.home() / ".aiask" / "akshare_mcp.sqlite3")
    )
    return Path(raw).expanduser().resolve()


def resolve_shadow_db(explicit: str | None = None) -> Path:
    return Path(explicit or DEFAULT_SHADOW_DB).expanduser().resolve()


def shadow_report_dir(report_root: str | None, batch_id: str) -> Path:
    return Path(report_root or DEFAULT_REPORT_ROOT).expanduser().resolve() / batch_id


def manifest_path(report_dir: Path) -> Path:
    return report_dir / "manifest.json"


def snapshot_path(report_dir: Path, label: str) -> Path:
    return report_dir / "snapshots" / f"{label}.json"


def command_report_path(report_dir: Path, label: str) -> Path:
    return report_dir / "commands" / f"{label}.json"


def build_shadow_env(
    shadow_db: Path,
    *,
    toggles_enabled: bool = False,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    append_pythonpath(env)
    env.update(SAFETY_ENV)
    env["AKSHARE_MCP_SQLITE_PATH"] = str(shadow_db)
    env["AIASK_SQLITE_PATH"] = str(shadow_db)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    for key in TOGGLE_KEYS:
        env[key] = "1" if toggles_enabled else "0"
    if extra:
        env.update(extra)
    return env


def toggle_phase_for_day(day_index: int | None, explicit_phase: str = "auto") -> bool:
    if explicit_phase == "enabled":
        return True
    if explicit_phase == "disabled":
        return False
    if day_index is None:
        return False
    return int(day_index) >= 11


def copy_shadow_database(source_db: Path, shadow_db: Path, *, overwrite: bool = False) -> dict[str, Any]:
    source = source_db.expanduser().resolve()
    target = shadow_db.expanduser().resolve()
    if source == target:
        raise ValueError("source database and shadow database must be different")
    if not source.exists():
        raise FileNotFoundError(f"source database not found: {source}")
    if target.exists() and not overwrite:
        return {
            "status": "exists",
            "source_db": str(source),
            "shadow_db": str(target),
            "copied": False,
            "size_bytes": target.stat().st_size,
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    source_uri = f"file:{source.as_posix()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True, timeout=30)) as src:
        with closing(sqlite3.connect(str(target), timeout=60)) as dst:
            src.backup(dst)
    for suffix in ("-wal", "-shm"):
        stale = Path(str(target) + suffix)
        if stale.exists():
            stale.unlink()
    return {
        "status": "copied",
        "source_db": str(source),
        "shadow_db": str(target),
        "copied": True,
        "size_bytes": target.stat().st_size,
    }


def check_shadow_schema(shadow_db: Path) -> dict[str, Any]:
    if not shadow_db.exists():
        return {
            "status": "failed",
            "shadow_db": str(shadow_db),
            "missing_tables": list(REQUIRED_TABLES),
            "tables": [],
        }
    with closing(sqlite3.connect(f"file:{shadow_db.as_posix()}?mode=ro", uri=True, timeout=30)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [str(row[0]) for row in rows]
        columns = {
            table: [str(col[1]) for col in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            for table in REQUIRED_TABLES
            if table in names
        }
    missing = [name for name in REQUIRED_TABLES if name not in names]
    required_columns = {
        "kline_intraday": {"code", "period", "timestamp", "adjust", "open", "high", "low", "close", "data_quality_status"},
        "strategy_trade_predictions": {"prediction_id", "contract_hash", "target_trading_date", "prediction_status"},
        "strategy_trade_prediction_outcomes": {"outcome_id", "prediction_id", "score_version", "score_status", "data_quality_status"},
    }
    missing_columns: dict[str, list[str]] = {}
    for table, expected in required_columns.items():
        if table not in columns:
            continue
        actual = set(columns[table])
        miss = sorted(expected - actual)
        if miss:
            missing_columns[table] = miss
    return {
        "status": "ok" if not missing and not missing_columns else "failed",
        "shadow_db": str(shadow_db),
        "tables": names,
        "missing_tables": missing,
        "columns": columns,
        "missing_columns": missing_columns,
    }


def _fetch_pairs(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, count in conn.execute(sql, params).fetchall():
        token = str(key or "unknown")
        result[token] = int(count or 0)
    return result


def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _decode_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return {}
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _dimension_values(prediction: dict[str, Any], outcome: dict[str, Any], dimension: str) -> list[str]:
    aliases = {
        "family": ("family", "strategy_family", "strategy_type"),
        "stage": ("stage", "incubation_stage", "pipeline_stage"),
        "regime": ("regime", "market_regime", "profile_regime"),
        "event": ("event", "event_family", "event_type", "theme_event"),
        "factor": ("factor", "factor_family", "factor_name"),
    }
    sources = [
        _decode_json(prediction.get("metadata")),
        _decode_json(prediction.get("contract_json")),
        _decode_json(outcome.get("metadata")),
        _decode_json(outcome.get("outcome_json")),
    ]
    values: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in aliases.get(dimension, (dimension,)):
            value = source.get(key)
            if value in (None, "", []):
                continue
            if isinstance(value, (list, tuple, set)):
                values.extend(_string(item) for item in value if _string(item))
            else:
                values.append(_string(value))
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique or ["unknown"]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _matrix_rows(
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    dimensions: tuple[str, ...] = ("family", "regime", "event", "factor"),
) -> list[dict[str, Any]]:
    predictions_by_id = {_string(item.get("prediction_id")): item for item in predictions}
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for outcome in outcomes:
        prediction = predictions_by_id.get(_string(outcome.get("prediction_id"))) or {}
        outcome_json = _decode_json(outcome.get("outcome_json"))
        score = _safe_float(outcome.get("trade_prediction_score"))
        for dimension in dimensions:
            for value in _dimension_values(prediction, outcome, dimension):
                key = (dimension, value)
                cell = cells.setdefault(
                    key,
                    {
                        "dimension": dimension,
                        "value": value,
                        "sample_n": 0,
                        "score_sum": 0.0,
                        "score_n": 0,
                        "direction_hit_n": 0,
                        "target_touch_n": 0,
                        "status_counts": {},
                        "data_quality_status_counts": {},
                    },
                )
                cell["sample_n"] += 1
                if score is not None:
                    cell["score_sum"] += score
                    cell["score_n"] += 1
                if outcome_json.get("direction_hit") is True:
                    cell["direction_hit_n"] += 1
                if outcome_json.get("target_touch") is True:
                    cell["target_touch_n"] += 1
                status = _string(outcome.get("score_status")) or "unknown"
                quality = _string(outcome.get("data_quality_status")) or "unknown"
                cell["status_counts"][status] = cell["status_counts"].get(status, 0) + 1
                cell["data_quality_status_counts"][quality] = cell["data_quality_status_counts"].get(quality, 0) + 1
    rows: list[dict[str, Any]] = []
    for cell in cells.values():
        sample_n = int(cell["sample_n"])
        score_n = int(cell["score_n"])
        rows.append(
            {
                "dimension": cell["dimension"],
                "value": cell["value"],
                "sample_n": sample_n,
                "score_avg": round(cell["score_sum"] / score_n, 6) if score_n else None,
                "direction_hit_rate": round(cell["direction_hit_n"] / sample_n, 6) if sample_n else None,
                "target_touch_rate": round(cell["target_touch_n"] / sample_n, 6) if sample_n else None,
                "status_counts": cell["status_counts"],
                "data_quality_status_counts": cell["data_quality_status_counts"],
            }
        )
    rows.sort(key=lambda row: (row["dimension"], -int(row["sample_n"]), row["value"]))
    return rows


def collect_local_snapshot(shadow_db: Path, *, previous_contract_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    if not shadow_db.exists():
        return {
            "object": "trade_prediction.shadow.local_snapshot",
            "status": "degraded",
            "reason": "shadow_db_missing",
            "shadow_db": str(shadow_db),
        }
    with closing(sqlite3.connect(f"file:{shadow_db.as_posix()}?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        schema = check_shadow_schema(shadow_db)
        if schema["status"] != "ok":
            return {
                "object": "trade_prediction.shadow.local_snapshot",
                "status": "degraded",
                "reason": "schema_missing",
                "schema": schema,
                "shadow_db": str(shadow_db),
            }
        prediction_rows = [dict(row) for row in conn.execute("SELECT * FROM strategy_trade_predictions").fetchall()]
        outcome_rows = [
            dict(row)
            for row in conn.execute("SELECT * FROM strategy_trade_prediction_outcomes").fetchall()
        ]
        prediction_count = len(prediction_rows)
        outcome_count = len(outcome_rows)
        evaluated_count = int(
            _fetch_one(
                conn,
                "SELECT COUNT(DISTINCT prediction_id) FROM strategy_trade_prediction_outcomes",
            )
            or 0
        )
        duplicate_rows = [
            {
                "prediction_id": row[0],
                "score_version": row[1],
                "count": int(row[2]),
            }
            for row in conn.execute(
                """
                SELECT prediction_id, score_version, COUNT(*) AS n
                FROM strategy_trade_prediction_outcomes
                GROUP BY prediction_id, score_version
                HAVING COUNT(*) > 1
                ORDER BY n DESC
                LIMIT 50
                """
            ).fetchall()
        ]
        current_hashes = {
            _string(row.get("prediction_id")): _string(row.get("contract_hash"))
            for row in prediction_rows
            if _string(row.get("prediction_id"))
        }
        hash_mutations: list[dict[str, str]] = []
        for prediction_id, old_hash in (previous_contract_hashes or {}).items():
            new_hash = current_hashes.get(prediction_id)
            if new_hash and old_hash and new_hash != old_hash:
                hash_mutations.append(
                    {
                        "prediction_id": prediction_id,
                        "previous_contract_hash": old_hash,
                        "current_contract_hash": new_hash,
                    }
                )
        intraday_count = int(_fetch_one(conn, "SELECT COUNT(*) FROM kline_intraday") or 0)
        intraday_quality = _fetch_pairs(
            conn,
            """
            SELECT COALESCE(data_quality_status, 'unknown'), COUNT(*)
            FROM kline_intraday
            GROUP BY COALESCE(data_quality_status, 'unknown')
            """,
        )
    status_counts = _counter(row.get("score_status") for row in outcome_rows)
    quality_counts = _counter(row.get("data_quality_status") for row in outcome_rows)
    score_version_counts = _counter(row.get("score_version") for row in outcome_rows)
    prediction_status_counts = _counter(row.get("prediction_status") for row in prediction_rows)
    partial_count = sum(count for status, count in status_counts.items() if status in PARTIAL_STATUSES)
    data_gap_count = sum(count for status, count in quality_counts.items() if status in DATA_GAP_STATUSES)
    v2_ok_count = sum(
        1
        for row in outcome_rows
        if _string(row.get("score_version")) == "trade_prediction_score_v2"
        and _string(row.get("score_status")) == "ok"
    )
    return {
        "object": "trade_prediction.shadow.local_snapshot",
        "status": "ready",
        "generated_at": utc_now(),
        "shadow_db": str(shadow_db),
        "schema": schema,
        "prediction_count": prediction_count,
        "outcome_count": outcome_count,
        "sample_n": evaluated_count,
        "pending_count": max(0, prediction_count - evaluated_count),
        "evaluated_count": evaluated_count,
        "partial_count": partial_count,
        "data_gap_count": data_gap_count,
        "v2_ok_count": v2_ok_count,
        "prediction_status_counts": prediction_status_counts,
        "score_status_counts": status_counts,
        "score_version_counts": score_version_counts,
        "data_quality_status_counts": quality_counts,
        "intraday_bar_count": intraday_count,
        "intraday_data_quality_status_counts": intraday_quality,
        "duplicate_outcomes": duplicate_rows,
        "duplicate_outcome_count": len(duplicate_rows),
        "contract_hash_mutations": hash_mutations,
        "contract_hash_mutation_count": len(hash_mutations),
        "contract_hashes": current_hashes,
        "matrix": {
            "rows": _matrix_rows(prediction_rows, outcome_rows),
            "row_count": len(_matrix_rows(prediction_rows, outcome_rows)),
        },
    }


def _counter(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        token = _string(value) or "unknown"
        counts[token] = counts.get(token, 0) + 1
    return counts


def collect_agent_snapshot(
    base_url: str | None,
    *,
    token: str | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    if not base_url:
        return {
            "object": "trade_prediction.shadow.agent_snapshot",
            "status": "degraded",
            "reason": "agent_base_url_not_configured",
            "routes": {},
        }
    routes = {
        "status": "/v1/desktop/trade-predictions/status",
        "outcomes": "/v1/desktop/trade-predictions/outcomes",
        "matrix": "/v1/desktop/trade-predictions/matrix",
    }
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload: dict[str, Any] = {
        "object": "trade_prediction.shadow.agent_snapshot",
        "status": "ready",
        "generated_at": utc_now(),
        "base_url": base_url,
        "routes": {},
    }
    for name, route in routes.items():
        url = parse.urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))
        try:
            req = request.Request(url, headers=headers, method="GET")
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                payload["routes"][name] = {
                    "status": "ok",
                    "http_status": resp.status,
                    "data": json.loads(body),
                }
        except error.HTTPError as exc:
            payload["status"] = "degraded"
            payload["routes"][name] = {
                "status": "error",
                "http_status": exc.code,
                "error": _redact(str(exc)),
            }
        except Exception as exc:
            payload["status"] = "degraded"
            payload["routes"][name] = {
                "status": "error",
                "error": _redact(str(exc)),
            }
    return payload


SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(token\s*[:=]\s*)([A-Za-z0-9_\-\.]{4,})"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([A-Za-z0-9_\-\.]{4,})"),
    re.compile(r"(?i)(secret\s*[:=]\s*)([A-Za-z0-9_\-\.]{4,})"),
)


def _redact(text: str, *, max_chars: int = 20000) -> str:
    sanitized = str(text or "")
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(lambda m: (m.group(1) if len(m.groups()) > 1 else "") + "[redacted]", sanitized)
    if len(sanitized) > max_chars:
        return sanitized[:max_chars] + "\n...[truncated]"
    return sanitized


def _npm_command(command: str, *args: str) -> tuple[str, ...]:
    exe = "npm.cmd" if os.name == "nt" else "npm"
    return (exe, command, *args)


def regression_commands(py: str = sys.executable) -> list[CommandSpec]:
    return [
        CommandSpec(
            "pytest_quant_core_trade_prediction",
            (
                py,
                "-m",
                "pytest",
                "packages/aiask-quant-core/tests/test_strategy_trade_prediction_p0.py",
                "-q",
            ),
            timeout_seconds=300,
        ),
        CommandSpec(
            "pytest_akshare_trade_prediction",
            (
                py,
                "-m",
                "pytest",
                "packages/akshare-mcp/tests/test_trade_prediction_verifier_p1_p2.py",
                "packages/akshare-mcp/tests/test_hit_rate_reporter_matrix_p3_1.py",
                "-q",
            ),
            timeout_seconds=300,
        ),
        CommandSpec(
            "pytest_strategy_factory_trade_prediction",
            (
                py,
                "-m",
                "pytest",
                "packages/strategy-factory/tests/test_trade_prediction_promotion_gate_p4.py",
                "packages/strategy-factory/tests/test_runtime_toggles.py",
                "packages/strategy-factory/tests/test_trade_prediction_contract_p0.py",
                "-q",
            ),
            timeout_seconds=600,
        ),
        CommandSpec(
            "pytest_agent_trade_prediction",
            (
                py,
                "-m",
                "pytest",
                "packages/agent/tests/test_tool_registry.py",
                "packages/agent/tests/test_strategy_factory_adapter_ownership.py",
                "packages/agent/tests/test_desktop_ops_api.py",
                "-q",
            ),
            timeout_seconds=300,
        ),
        CommandSpec(
            "desktop_typecheck",
            _npm_command("run", "typecheck"),
            cwd=REPO_ROOT / "desktop",
            timeout_seconds=300,
        ),
        CommandSpec(
            "desktop_tests",
            _npm_command("test", "--", "--run"),
            cwd=REPO_ROOT / "desktop",
            timeout_seconds=600,
        ),
    ]


def preflight_commands(py: str = sys.executable, universe_size: int = 300) -> list[CommandSpec]:
    return [
        CommandSpec(
            "tdx_sync_preflight",
            (py, "scripts/run_tdx_sync.py", "--universe-size", str(universe_size)),
            timeout_seconds=3600,
        ),
        CommandSpec(
            "data_freshness_preflight",
            (py, "scripts/ops/run_p0_1_data_freshness.py"),
            timeout_seconds=1800,
        ),
    ]


def incubation_command(py: str = sys.executable, *, dry_run: bool) -> CommandSpec:
    command = [
        py,
        "packages/akshare-mcp/scripts/run_incubation_factory.py",
        "--json",
    ]
    if dry_run:
        command.insert(2, "--dry-run")
    return CommandSpec(
        "incubation_factory_dry_run" if dry_run else "incubation_factory_shadow_write",
        tuple(command),
        timeout_seconds=1800,
    )


def sync_command(py: str = sys.executable, universe_size: int = 300) -> CommandSpec:
    return CommandSpec(
        "daily_tdx_sync",
        (py, "scripts/run_tdx_sync.py", "--universe-size", str(universe_size)),
        timeout_seconds=3600,
    )


def run_command(spec: CommandSpec, env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    started_at = utc_now()
    try:
        completed = subprocess.run(
            list(spec.command),
            cwd=str(spec.cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
        elapsed = round(time.monotonic() - started, 3)
        return {
            "name": spec.name,
            "command": list(spec.command),
            "cwd": str(spec.cwd),
            "started_at": started_at,
            "elapsed_seconds": elapsed,
            "returncode": completed.returncode,
            "success": completed.returncode == 0,
            "stdout": _redact(completed.stdout),
            "stderr": _redact(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": spec.name,
            "command": list(spec.command),
            "cwd": str(spec.cwd),
            "started_at": started_at,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "returncode": None,
            "success": False,
            "timeout": True,
            "stdout": _redact(exc.stdout or ""),
            "stderr": _redact(exc.stderr or ""),
        }


def run_commands(
    specs: list[CommandSpec],
    *,
    env: dict[str, str],
    report_dir: Path,
    label: str,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for spec in specs:
        result = run_command(spec, env)
        results.append(result)
        write_json(command_report_path(report_dir, f"{label}_{spec.name}"), result)
        if not result.get("success") and not continue_on_error:
            break
    payload = {
        "object": "trade_prediction.shadow.command_batch",
        "label": label,
        "generated_at": utc_now(),
        "success": all(bool(item.get("success")) for item in results),
        "commands": results,
    }
    write_json(command_report_path(report_dir, label), payload)
    return payload


def load_manifest(report_dir: Path) -> dict[str, Any]:
    return read_json(manifest_path(report_dir), {})


def save_manifest(report_dir: Path, payload: dict[str, Any]) -> None:
    write_json(manifest_path(report_dir), payload)


def update_manifest(report_dir: Path, **updates: Any) -> dict[str, Any]:
    manifest = load_manifest(report_dir)
    manifest.update(updates)
    manifest.setdefault("updated_at", utc_now())
    manifest["updated_at"] = utc_now()
    save_manifest(report_dir, manifest)
    return manifest


def create_or_update_manifest(
    *,
    report_dir: Path,
    batch_id: str,
    source_db: Path,
    shadow_db: Path,
    validation_days: int,
) -> dict[str, Any]:
    manifest = load_manifest(report_dir)
    manifest.setdefault("object", "trade_prediction.shadow.manifest")
    manifest.setdefault("created_at", utc_now())
    manifest.update(
        {
            "batch_id": batch_id,
            "source_db": str(source_db),
            "shadow_db": str(shadow_db),
            "report_dir": str(report_dir),
            "validation_days": validation_days,
            "safety_env": SAFETY_ENV,
            "toggle_keys": list(TOGGLE_KEYS),
            "updated_at": utc_now(),
        }
    )
    manifest.setdefault("snapshots", [])
    save_manifest(report_dir, manifest)
    return manifest


def record_snapshot(report_dir: Path, label: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    path = snapshot_path(report_dir, label)
    write_json(path, snapshot)
    manifest = load_manifest(report_dir)
    items = list(manifest.get("snapshots") or [])
    items = [item for item in items if item.get("label") != label]
    local = snapshot.get("local") if isinstance(snapshot.get("local"), dict) else snapshot
    items.append(
        {
            "label": label,
            "path": str(path),
            "generated_at": snapshot.get("generated_at") or utc_now(),
            "sample_n": local.get("sample_n") if isinstance(local, dict) else None,
            "v2_ok_count": local.get("v2_ok_count") if isinstance(local, dict) else None,
            "partial_count": local.get("partial_count") if isinstance(local, dict) else None,
            "data_gap_count": local.get("data_gap_count") if isinstance(local, dict) else None,
        }
    )
    manifest["snapshots"] = sorted(items, key=lambda item: str(item.get("label") or ""))
    manifest["latest_contract_hashes"] = local.get("contract_hashes", {}) if isinstance(local, dict) else {}
    manifest["updated_at"] = utc_now()
    save_manifest(report_dir, manifest)
    return snapshot


def collect_snapshot_bundle(
    *,
    shadow_db: Path,
    report_dir: Path,
    label: str,
    agent_base_url: str | None,
    agent_token: str | None,
) -> dict[str, Any]:
    manifest = load_manifest(report_dir)
    previous_hashes = dict(manifest.get("latest_contract_hashes") or {})
    local = collect_local_snapshot(shadow_db, previous_contract_hashes=previous_hashes)
    agent = collect_agent_snapshot(agent_base_url, token=agent_token)
    bundle = {
        "object": "trade_prediction.shadow.snapshot_bundle",
        "label": label,
        "generated_at": utc_now(),
        "local": local,
        "agent": agent,
    }
    return record_snapshot(report_dir, label, bundle)


def cmd_init(args: argparse.Namespace) -> int:
    source_db = resolve_source_db(args.source_db)
    shadow_db = resolve_shadow_db(args.shadow_db)
    report_dir = shadow_report_dir(args.report_root, args.batch_id)
    create_or_update_manifest(
        report_dir=report_dir,
        batch_id=args.batch_id,
        source_db=source_db,
        shadow_db=shadow_db,
        validation_days=args.validation_days,
    )
    copy_result = copy_shadow_database(source_db, shadow_db, overwrite=args.overwrite)
    schema = check_shadow_schema(shadow_db)
    payload = {
        "object": "trade_prediction.shadow.init",
        "generated_at": utc_now(),
        "copy": copy_result,
        "schema": schema,
    }
    write_json(report_dir / "init.json", payload)
    update_manifest(report_dir, init=payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if schema.get("status") == "ok" else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    source_db = resolve_source_db(args.source_db)
    shadow_db = resolve_shadow_db(args.shadow_db)
    report_dir = shadow_report_dir(args.report_root, args.batch_id)
    create_or_update_manifest(
        report_dir=report_dir,
        batch_id=args.batch_id,
        source_db=source_db,
        shadow_db=shadow_db,
        validation_days=args.validation_days,
    )
    if not shadow_db.exists() or args.overwrite:
        copy_shadow_database(source_db, shadow_db, overwrite=args.overwrite)
    env = build_shadow_env(shadow_db, toggles_enabled=False)
    results: dict[str, Any] = {}
    if not args.skip_tests:
        results["regression"] = run_commands(
            regression_commands(args.python),
            env=env,
            report_dir=report_dir,
            label="baseline_regression",
            continue_on_error=True,
        )
    if not args.skip_sync:
        results["preflight"] = run_commands(
            preflight_commands(args.python, args.universe_size),
            env=env,
            report_dir=report_dir,
            label="baseline_preflight",
            continue_on_error=True,
        )
    if not args.skip_incubation_dry_run:
        results["incubation_dry_run"] = run_commands(
            [incubation_command(args.python, dry_run=True)],
            env=env,
            report_dir=report_dir,
            label="baseline_incubation",
            continue_on_error=True,
        )
    token = os.getenv(args.agent_token_env, "") if args.agent_token_env else None
    snapshot = collect_snapshot_bundle(
        shadow_db=shadow_db,
        report_dir=report_dir,
        label="day_00_baseline",
        agent_base_url=None if args.skip_agent else args.agent_base_url,
        agent_token=token,
    )
    payload = {
        "object": "trade_prediction.shadow.baseline",
        "generated_at": utc_now(),
        "schema": check_shadow_schema(shadow_db),
        "commands": results,
        "snapshot": snapshot,
    }
    write_json(report_dir / "baseline.json", payload)
    update_manifest(report_dir, baseline=payload)
    print(json.dumps(_baseline_console_summary(payload), ensure_ascii=False, indent=2))
    failed_batches = [
        name
        for name, result in results.items()
        if isinstance(result, dict) and result.get("success") is False
    ]
    return 1 if failed_batches and not args.allow_failures else 0


def _baseline_console_summary(payload: dict[str, Any]) -> dict[str, Any]:
    local = ((payload.get("snapshot") or {}).get("local") or {})
    return {
        "status": "completed",
        "schema_status": (payload.get("schema") or {}).get("status"),
        "sample_n": local.get("sample_n"),
        "pending_count": local.get("pending_count"),
        "partial_count": local.get("partial_count"),
        "v2_ok_count": local.get("v2_ok_count"),
        "report": "baseline.json",
    }


def cmd_daily(args: argparse.Namespace) -> int:
    shadow_db = resolve_shadow_db(args.shadow_db)
    report_dir = shadow_report_dir(args.report_root, args.batch_id)
    if not shadow_db.exists():
        raise FileNotFoundError(f"shadow database not found: {shadow_db}; run init first")
    toggles_enabled = toggle_phase_for_day(args.day_index, args.toggle_phase)
    env = build_shadow_env(shadow_db, toggles_enabled=toggles_enabled)
    label = f"day_{int(args.day_index):02d}" if args.day_index is not None else "daily_manual"
    command_results: dict[str, Any] = {}
    if not args.skip_sync:
        command_results["sync"] = run_commands(
            [sync_command(args.python, args.universe_size)],
            env=env,
            report_dir=report_dir,
            label=f"{label}_sync",
            continue_on_error=True,
        )
    if not args.skip_incubation:
        command_results["incubation"] = run_commands(
            [incubation_command(args.python, dry_run=False)],
            env=env,
            report_dir=report_dir,
            label=f"{label}_incubation",
            continue_on_error=True,
        )
    token = os.getenv(args.agent_token_env, "") if args.agent_token_env else None
    snapshot = collect_snapshot_bundle(
        shadow_db=shadow_db,
        report_dir=report_dir,
        label=label,
        agent_base_url=None if args.skip_agent else args.agent_base_url,
        agent_token=token,
    )
    alerts = evaluate_snapshot_alerts(snapshot)
    payload = {
        "object": "trade_prediction.shadow.daily_run",
        "generated_at": utc_now(),
        "day_index": args.day_index,
        "label": label,
        "toggles_enabled": toggles_enabled,
        "toggle_env": {key: env.get(key) for key in TOGGLE_KEYS},
        "commands": command_results,
        "snapshot": snapshot,
        "alerts": alerts,
    }
    write_json(report_dir / f"{label}.json", payload)
    manifest = load_manifest(report_dir)
    daily_runs = [item for item in list(manifest.get("daily_runs") or []) if item.get("label") != label]
    daily_runs.append(
        {
            "label": label,
            "day_index": args.day_index,
            "path": str(report_dir / f"{label}.json"),
            "toggles_enabled": toggles_enabled,
            "alert_count": len(alerts),
        }
    )
    manifest["daily_runs"] = sorted(daily_runs, key=lambda item: int(item.get("day_index") or 0))
    manifest["updated_at"] = utc_now()
    save_manifest(report_dir, manifest)
    print(json.dumps(_daily_console_summary(payload), ensure_ascii=False, indent=2))
    failed = [
        name
        for name, result in command_results.items()
        if isinstance(result, dict) and result.get("success") is False
    ]
    if alerts and not args.allow_alerts:
        return 1
    return 1 if failed and not args.allow_failures else 0


def evaluate_snapshot_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    local = snapshot.get("local") if isinstance(snapshot.get("local"), dict) else {}
    alerts: list[dict[str, Any]] = []
    if local.get("duplicate_outcome_count"):
        alerts.append(
            {
                "severity": "high",
                "code": "duplicate_outcomes",
                "count": local.get("duplicate_outcome_count"),
            }
        )
    if local.get("contract_hash_mutation_count"):
        alerts.append(
            {
                "severity": "critical",
                "code": "frozen_contract_hash_mutation",
                "count": local.get("contract_hash_mutation_count"),
            }
        )
    quality_counts = local.get("data_quality_status_counts") or {}
    for status in sorted(DATA_GAP_STATUSES):
        count = int(quality_counts.get(status) or 0)
        if count:
            alerts.append(
                {
                    "severity": "medium",
                    "code": f"data_quality_{status}",
                    "count": count,
                }
            )
    score_status_counts = local.get("score_status_counts") or {}
    if int(score_status_counts.get("post_hoc_rejected") or 0):
        alerts.append(
            {
                "severity": "medium",
                "code": "post_hoc_rejected_present",
                "count": int(score_status_counts.get("post_hoc_rejected") or 0),
            }
        )
    return alerts


def _daily_console_summary(payload: dict[str, Any]) -> dict[str, Any]:
    local = (((payload.get("snapshot") or {}).get("local") or {}))
    return {
        "status": "completed",
        "label": payload.get("label"),
        "toggles_enabled": payload.get("toggles_enabled"),
        "sample_n": local.get("sample_n"),
        "pending_count": local.get("pending_count"),
        "partial_count": local.get("partial_count"),
        "v2_ok_count": local.get("v2_ok_count"),
        "alert_count": len(payload.get("alerts") or []),
    }


def load_snapshot_files(report_dir: Path) -> list[dict[str, Any]]:
    snapshot_dir = report_dir / "snapshots"
    if not snapshot_dir.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for path in sorted(snapshot_dir.glob("day_*.json")):
        payload = read_json(path, {})
        if isinstance(payload, dict):
            payload["_path"] = str(path)
            snapshots.append(payload)
    return snapshots


def summarize_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    daily = [item for item in snapshots if str(item.get("label") or "").startswith("day_") and item.get("label") != "day_00_baseline"]
    latest = daily[-1] if daily else (snapshots[-1] if snapshots else {})
    latest_local = latest.get("local") if isinstance(latest.get("local"), dict) else {}
    baseline = next((item for item in snapshots if item.get("label") == "day_00_baseline"), None)
    baseline_local = baseline.get("local") if isinstance((baseline or {}).get("local"), dict) else {}
    max_sample_n = max((int(((item.get("local") or {}).get("sample_n") or 0)) for item in snapshots), default=0)
    max_v2_ok = max((int(((item.get("local") or {}).get("v2_ok_count") or 0)) for item in snapshots), default=0)
    total_alerts = sum(len(evaluate_snapshot_alerts(item)) for item in snapshots)
    data_quality_rollup: dict[str, int] = {}
    score_status_rollup: dict[str, int] = {}
    for item in snapshots:
        local = item.get("local") if isinstance(item.get("local"), dict) else {}
        for key, value in (local.get("data_quality_status_counts") or {}).items():
            data_quality_rollup[key] = data_quality_rollup.get(key, 0) + int(value or 0)
        for key, value in (local.get("score_status_counts") or {}).items():
            score_status_rollup[key] = score_status_rollup.get(key, 0) + int(value or 0)
    intraday_v2_verified = max_v2_ok > 0
    high_risk = any(
        (item.get("local") or {}).get("contract_hash_mutation_count")
        for item in snapshots
        if isinstance(item.get("local"), dict)
    )
    duplicate_count = max(
        (int(((item.get("local") or {}).get("duplicate_outcome_count") or 0)) for item in snapshots),
        default=0,
    )
    conclusion = "ready_for_production_gray"
    blockers: list[str] = []
    warnings: list[str] = []
    if len(daily) < 20:
        conclusion = "not_ready_continue_soak"
        warnings.append(f"only_{len(daily)}_daily_snapshots_collected")
    if high_risk:
        conclusion = "blocked"
        blockers.append("frozen_contract_hash_mutation_detected")
    if duplicate_count:
        conclusion = "blocked"
        blockers.append("duplicate_prediction_outcomes_detected")
    if not intraday_v2_verified:
        if conclusion == "ready_for_production_gray":
            conclusion = "daily_loop_ok_intraday_v2_unverified"
        warnings.append("no_ok_trade_prediction_score_v2_samples")
    return {
        "snapshot_count": len(snapshots),
        "daily_snapshot_count": len(daily),
        "baseline_sample_n": baseline_local.get("sample_n"),
        "latest_sample_n": latest_local.get("sample_n"),
        "max_sample_n": max_sample_n,
        "max_v2_ok_count": max_v2_ok,
        "latest_score_status_counts": latest_local.get("score_status_counts") or {},
        "latest_score_version_counts": latest_local.get("score_version_counts") or {},
        "latest_data_quality_status_counts": latest_local.get("data_quality_status_counts") or {},
        "data_quality_rollup": data_quality_rollup,
        "score_status_rollup": score_status_rollup,
        "total_alert_count": total_alerts,
        "intraday_v2_verified": intraday_v2_verified,
        "conclusion": conclusion,
        "blockers": blockers,
        "warnings": warnings,
    }


def render_markdown_report(batch_id: str, manifest: dict[str, Any], summary: dict[str, Any]) -> str:
    lines = [
        f"# Trade Prediction Shadow Validation Report: {batch_id}",
        "",
        f"- Generated at: {utc_now()}",
        f"- Shadow DB: `{manifest.get('shadow_db')}`",
        f"- Validation days target: `{manifest.get('validation_days')}`",
        f"- Daily snapshots collected: `{summary.get('daily_snapshot_count')}`",
        f"- Conclusion: `{summary.get('conclusion')}`",
        "",
        "## Coverage",
        "",
        f"- Baseline sample_n: `{summary.get('baseline_sample_n')}`",
        f"- Latest sample_n: `{summary.get('latest_sample_n')}`",
        f"- Max sample_n: `{summary.get('max_sample_n')}`",
        f"- Max v2 ok count: `{summary.get('max_v2_ok_count')}`",
        f"- Intraday v2 verified: `{summary.get('intraday_v2_verified')}`",
        "",
        "## Latest Status",
        "",
        f"- score_status_counts: `{json.dumps(summary.get('latest_score_status_counts') or {}, ensure_ascii=False)}`",
        f"- score_version_counts: `{json.dumps(summary.get('latest_score_version_counts') or {}, ensure_ascii=False)}`",
        f"- data_quality_status_counts: `{json.dumps(summary.get('latest_data_quality_status_counts') or {}, ensure_ascii=False)}`",
        "",
        "## Alerts",
        "",
        f"- Total alert count: `{summary.get('total_alert_count')}`",
        f"- Blockers: `{json.dumps(summary.get('blockers') or [], ensure_ascii=False)}`",
        f"- Warnings: `{json.dumps(summary.get('warnings') or [], ensure_ascii=False)}`",
        "",
        "## Toggle Drill",
        "",
        "- Days 1-10: prediction promotion gate, budget feedback, and factor decay disabled.",
        "- Days 11-20: the three toggles are enabled only in the shadow environment.",
        "- Production control surfaces remain unaffected because this report is generated from the shadow DB.",
    ]
    if not summary.get("intraday_v2_verified"):
        lines.extend(
            [
                "",
                "## Intraday Caveat",
                "",
                "Daily outcome validation may be usable, but intraday v2 is not sufficiently verified because no ok `trade_prediction_score_v2` sample was observed.",
            ]
        )
    return "\n".join(lines) + "\n"


def cmd_final(args: argparse.Namespace) -> int:
    report_dir = shadow_report_dir(args.report_root, args.batch_id)
    manifest = load_manifest(report_dir)
    snapshots = load_snapshot_files(report_dir)
    summary = summarize_snapshots(snapshots)
    payload = {
        "object": "trade_prediction.shadow.final_report",
        "batch_id": args.batch_id,
        "generated_at": utc_now(),
        "manifest": manifest,
        "summary": summary,
        "snapshots": [
            {
                "label": item.get("label"),
                "path": item.get("_path"),
                "sample_n": (item.get("local") or {}).get("sample_n") if isinstance(item.get("local"), dict) else None,
                "v2_ok_count": (item.get("local") or {}).get("v2_ok_count") if isinstance(item.get("local"), dict) else None,
            }
            for item in snapshots
        ],
    }
    write_json(report_dir / "final_report.json", payload)
    markdown = render_markdown_report(args.batch_id, manifest, summary)
    (report_dir / "final_report.md").write_text(markdown, encoding="utf-8")
    update_manifest(report_dir, final_report={"json": str(report_dir / "final_report.json"), "markdown": str(report_dir / "final_report.md")})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("conclusion") in {"ready_for_production_gray", "daily_loop_ok_intraday_v2_unverified", "not_ready_continue_soak"} else 1


def cmd_status(args: argparse.Namespace) -> int:
    shadow_db = resolve_shadow_db(args.shadow_db)
    report_dir = shadow_report_dir(args.report_root, args.batch_id)
    manifest = load_manifest(report_dir)
    schema = check_shadow_schema(shadow_db)
    local = collect_local_snapshot(
        shadow_db,
        previous_contract_hashes=dict(manifest.get("latest_contract_hashes") or {}),
    )
    payload = {
        "object": "trade_prediction.shadow.status",
        "generated_at": utc_now(),
        "manifest": manifest,
        "schema": schema,
        "local": local,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if schema.get("status") == "ok" else 1


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--shadow-db", default=str(DEFAULT_SHADOW_DB))
    parser.add_argument("--report-root", default=str(DEFAULT_REPORT_ROOT))
    parser.add_argument("--validation-days", type=int, default=20)
    parser.add_argument("--python", default=sys.executable)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trade prediction shadow validation harness")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="copy production SQLite into the shadow database")
    add_common_args(init)
    init.add_argument("--source-db", default=None)
    init.add_argument("--overwrite", action="store_true")
    init.set_defaults(func=cmd_init)

    baseline = sub.add_parser("baseline", help="run day-0 baseline validation")
    add_common_args(baseline)
    baseline.add_argument("--source-db", default=None)
    baseline.add_argument("--overwrite", action="store_true")
    baseline.add_argument("--universe-size", type=int, default=300)
    baseline.add_argument("--agent-base-url", default=DEFAULT_AGENT_BASE_URL)
    baseline.add_argument("--agent-token-env", default="AIASK_AGENT_CONTROL_TOKEN")
    baseline.add_argument("--skip-tests", action="store_true")
    baseline.add_argument("--skip-sync", action="store_true")
    baseline.add_argument("--skip-incubation-dry-run", action="store_true")
    baseline.add_argument("--skip-agent", action="store_true")
    baseline.add_argument("--allow-failures", action="store_true")
    baseline.set_defaults(func=cmd_baseline)

    daily = sub.add_parser("daily", help="run one daily shadow validation cycle")
    add_common_args(daily)
    daily.add_argument("--day-index", type=int, required=True)
    daily.add_argument("--toggle-phase", choices=("auto", "disabled", "enabled"), default="auto")
    daily.add_argument("--universe-size", type=int, default=300)
    daily.add_argument("--agent-base-url", default=DEFAULT_AGENT_BASE_URL)
    daily.add_argument("--agent-token-env", default="AIASK_AGENT_CONTROL_TOKEN")
    daily.add_argument("--skip-sync", action="store_true")
    daily.add_argument("--skip-incubation", action="store_true")
    daily.add_argument("--skip-agent", action="store_true")
    daily.add_argument("--allow-alerts", action="store_true")
    daily.add_argument("--allow-failures", action="store_true")
    daily.set_defaults(func=cmd_daily)

    final = sub.add_parser("final", help="generate the final soak report")
    add_common_args(final)
    final.set_defaults(func=cmd_final)

    status = sub.add_parser("status", help="read shadow DB status")
    add_common_args(status)
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
