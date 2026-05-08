from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from akshare_mcp.storage.timescaledb._strategy_crud_utils import _StrategyCrudUtilsMixin
from akshare_mcp.storage.timescaledb.strategy_ai import StrategyAIMixin


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TaskRunConn:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1

    async def fetchrow(self, query: str, *args, **kwargs):
        if "INSERT INTO strategy_task_runs" in query:
            row = {
                "id": self.next_id,
                "strategy_id": args[0],
                "task_name": args[1],
                "task_scope": args[2],
                "task_key": args[3],
                "status": args[4],
                "trace_id": args[5],
                "payload": args[6],
                "result": args[7],
                "error": args[8],
                "lease_owner": args[9],
                "lease_until": args[10],
                "heartbeat_at": args[11],
                "attempt_count": args[12],
                "max_attempts": args[13],
                "last_claimed_at": args[14],
                "started_at": args[15] or datetime.now(timezone.utc),
                "completed_at": args[16],
            }
            self.next_id += 1
            self.rows.append(row)
            return dict(row)
        if "WITH next_run AS" in query and "UPDATE strategy_task_runs target" in query:
            task_scope, task_names, owner, lease_seconds = args
            now = datetime.now(timezone.utc)
            names = set(task_names or [])
            candidates = []
            for row in self.rows:
                if row["task_scope"] != task_scope:
                    continue
                if names and row["task_name"] not in names:
                    continue
                attempts = int(row.get("attempt_count") or 0)
                max_attempts = int(row.get("max_attempts") or 3)
                if attempts >= max_attempts:
                    continue
                status = row.get("status")
                expired = (row.get("lease_until") or row.get("started_at") or now) < now
                if status in {"queued", "retryable_timeout", "retryable_failure"} or (status == "running" and expired):
                    candidates.append(row)
            if not candidates:
                return None
            row = sorted(candidates, key=lambda item: (item.get("started_at"), item.get("id")))[0]
            row["status"] = "running"
            row["started_at"] = now
            row["completed_at"] = None
            row["error"] = None
            row["lease_owner"] = owner
            row["lease_until"] = now + timedelta(seconds=int(lease_seconds))
            row["heartbeat_at"] = now
            row["last_claimed_at"] = now
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
            return dict(row)
        if "UPDATE strategy_task_runs" in query and "heartbeat_at = NOW()" in query:
            run_id, owner, lease_seconds = args
            row = next((item for item in self.rows if item["id"] == run_id), None)
            if not row or row.get("status") != "running":
                return None
            if owner and row.get("lease_owner") not in (None, owner):
                return None
            now = datetime.now(timezone.utc)
            row["heartbeat_at"] = now
            row["lease_owner"] = owner or row.get("lease_owner")
            row["lease_until"] = now + timedelta(seconds=int(lease_seconds))
            return dict(row)
        if "UPDATE strategy_task_runs" in query:
            (
                run_id,
                status,
                result_json,
                error,
                completed_at,
                lease_owner,
                lease_until,
                heartbeat_at,
                attempt_count,
                max_attempts,
                last_claimed_at,
                clear_lease,
                completed_statuses,
            ) = args[:13]
            row = next((item for item in self.rows if item["id"] == run_id), None)
            if not row:
                return None
            if status is not None:
                row["status"] = status
            if result_json is not None:
                row["result"] = result_json
            if error is not None:
                row["error"] = error
            if completed_at is not None:
                row["completed_at"] = completed_at
            elif status in set(completed_statuses or []):
                row["completed_at"] = row.get("completed_at") or datetime.now(timezone.utc)
            if clear_lease:
                row["lease_owner"] = None
                row["lease_until"] = None
            else:
                row["lease_owner"] = lease_owner or row.get("lease_owner")
                row["lease_until"] = lease_until or row.get("lease_until")
            row["heartbeat_at"] = heartbeat_at or row.get("heartbeat_at")
            row["attempt_count"] = attempt_count if attempt_count is not None else row.get("attempt_count")
            row["max_attempts"] = max_attempts if max_attempts is not None else row.get("max_attempts")
            row["last_claimed_at"] = last_claimed_at or row.get("last_claimed_at")
            return dict(row)
        return None

    async def fetch(self, query: str, *args):
        if "GROUP BY task_name, status" in query:
            task_scope, task_names = args
            names = set(task_names or [])
            counts: dict[tuple[str, str], int] = {}
            for row in self.rows:
                if task_scope and row["task_scope"] != task_scope:
                    continue
                if names and row["task_name"] not in names:
                    continue
                if row["status"] not in {"queued", "running"}:
                    continue
                key = (row["task_name"], row["status"])
                counts[key] = counts.get(key, 0) + 1
            return [
                {"task_name": task_name, "status": status, "count": count, "max_age_seconds": 0.0}
                for (task_name, status), count in counts.items()
            ]
        if "GROUP BY task_name" in query:
            task_scope, task_names = args
            names = set(task_names or [])
            now = datetime.now(timezone.utc)
            counts: dict[str, int] = {}
            for row in self.rows:
                if task_scope and row["task_scope"] != task_scope:
                    continue
                if names and row["task_name"] not in names:
                    continue
                if row["status"] == "running" and (row.get("lease_until") or now) < now:
                    counts[row["task_name"]] = counts.get(row["task_name"], 0) + 1
            return [{"task_name": task_name, "count": count} for task_name, count in counts.items()]
        return []


class _TaskRunDb(StrategyAIMixin, _StrategyCrudUtilsMixin):
    def __init__(self):
        self._conn = _TaskRunConn()

    def acquire(self):
        return _FakeAcquire(self._conn)


def test_claim_strategy_task_run_uses_lease_and_recovers_expired_running():
    async def run():
        db = _TaskRunDb()
        queued = await db.save_strategy_task_run(
            {
                "task_name": "factory_dispatch_run",
                "task_scope": "strategy_factory.worker",
                "status": "queued",
                "payload": {"source": "unit"},
            }
        )
        claimed = await db.claim_strategy_task_run(
            task_scope="strategy_factory.worker",
            task_names=["factory_dispatch_run"],
            lease_owner="worker-a",
            lease_seconds=90,
        )
        assert claimed["id"] == queued["id"]
        assert claimed["status"] == "running"
        assert claimed["lease_owner"] == "worker-a"
        assert claimed["attempt_count"] == 1

        blocked = await db.claim_strategy_task_run(
            task_scope="strategy_factory.worker",
            task_names=["factory_dispatch_run"],
            lease_owner="worker-b",
            lease_seconds=90,
        )
        assert blocked is None

        db._conn.rows[0]["lease_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        reclaimed = await db.claim_strategy_task_run(
            task_scope="strategy_factory.worker",
            task_names=["factory_dispatch_run"],
            lease_owner="worker-b",
            lease_seconds=90,
        )
        assert reclaimed["id"] == queued["id"]
        assert reclaimed["lease_owner"] == "worker-b"
        assert reclaimed["attempt_count"] == 2

    asyncio.run(run())


def test_task_queue_stats_reports_depth_and_stale_running():
    async def run():
        db = _TaskRunDb()
        await db.save_strategy_task_run(
            {
                "task_name": "runtime_cycle_run",
                "task_scope": "strategy_factory.worker",
                "status": "queued",
                "payload": {"source": "unit"},
            }
        )
        await db.save_strategy_task_run(
            {
                "task_name": "runtime_cycle_run",
                "task_scope": "strategy_factory.worker",
                "status": "running",
                "payload": {"source": "unit"},
                "lease_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            }
        )
        stats = await db.get_strategy_task_queue_stats(
            task_scope="strategy_factory.worker",
            task_names=["runtime_cycle_run"],
        )
        assert stats["queue_depth_by_task"]["runtime_cycle_run"]["queued"] == 1
        assert stats["queue_depth_by_task"]["runtime_cycle_run"]["running"] == 1
        assert stats["stale_running_by_task"]["runtime_cycle_run"] == 1

    asyncio.run(run())


def test_claim_strategy_task_run_recovers_retryable_timeout():
    async def run():
        db = _TaskRunDb()
        row = await db.save_strategy_task_run(
            {
                "task_name": "incubation_pipeline_run",
                "task_scope": "strategy_factory.worker",
                "status": "retryable_timeout",
                "payload": {"source": "unit"},
                "attempt_count": 1,
                "max_attempts": 3,
            }
        )
        claimed = await db.claim_strategy_task_run(
            task_scope="strategy_factory.worker",
            task_names=["incubation_pipeline_run"],
            lease_owner="worker-c",
            lease_seconds=60,
        )
        assert claimed["id"] == row["id"]
        assert claimed["status"] == "running"
        assert claimed["attempt_count"] == 2

    asyncio.run(run())
