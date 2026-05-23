from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from strategy_factory.application.factory_task_board import FactoryTaskBoard

JSON_LIMIT = 64 * 1024


def _large_board_payload() -> dict:
    return {
        "resolved_candidate_envelope": {
            "records": [
                {"symbol": f"{idx:06d}", "features": list(range(80))}
                for idx in range(900)
            ]
        },
        "quality_gate": {
            "passed_candidates": [
                {
                    "strategy_type": "momentum",
                    "equity_curve": list(range(800)),
                    "trades": [{"i": i, "price": i * 0.1} for i in range(120)],
                }
                for _ in range(30)
            ]
        },
        "research_task": {
            "task_id": "task-board-heavy",
            "target_symbols": [f"{idx:06d}" for idx in range(2000)],
        },
    }


def _json_len(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def test_factory_task_board_claim_heartbeat_complete(tmp_path) -> None:
    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    task = board.create_task(task_type="research", title="Research task", payload={"symbol": "600519"})

    claimed = board.claim_task(task["task_id"], worker_id="worker-a", ttl_seconds=60)
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert claimed["claim_token"]

    heartbeat = board.heartbeat(task["task_id"], claimed["claim_token"], ttl_seconds=120)
    assert heartbeat is not None
    assert heartbeat["status"] == "running"
    assert heartbeat["last_heartbeat_at"]

    completed = board.complete_task(
        task["task_id"],
        claim_token=claimed["claim_token"],
        artifact_refs=[{"artifact_type": "report", "artifact_id": "r1"}],
        result={"ok": True},
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["artifact_refs"][0]["artifact_id"] == "r1"


def test_factory_task_board_reclaims_stale_tasks(tmp_path) -> None:
    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    task = board.create_task(task_type="backtest", title="Backtest task", max_attempts=2)
    claimed = board.claim_task(task["task_id"], worker_id="worker-a", ttl_seconds=1)
    assert claimed is not None

    reclaimed = board.reclaim_stale(now=datetime.now(timezone.utc) + timedelta(seconds=2))
    assert len(reclaimed) == 1
    assert reclaimed[0]["status"] == "ready"

    second = board.claim_task(task["task_id"], worker_id="worker-b", ttl_seconds=1)
    assert second is not None
    board.reclaim_stale(now=datetime.now(timezone.utc) + timedelta(seconds=2))
    final = board.get_task(task["task_id"])
    assert final is not None
    assert final["status"] == "blocked"


def test_factory_task_board_can_block_one_shot_stale_tasks(tmp_path) -> None:
    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    task = board.create_task(task_type="research", title="Strategy factory run")
    claimed = board.claim_task(task["task_id"], worker_id="worker-a", ttl_seconds=1)
    assert claimed is not None

    reclaimed = board.reclaim_stale(
        now=datetime.now(timezone.utc) + timedelta(seconds=2),
        block_task_types=("research",),
        block_reason="stale one-shot run",
    )

    assert len(reclaimed) == 1
    assert reclaimed[0]["status"] == "blocked"
    assert reclaimed[0]["blocked_reason"] == "stale one-shot run"


def test_factory_task_board_lists_active_tasks(tmp_path) -> None:
    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    research = board.create_task(
        task_type="research",
        title="Strategy factory run_once",
        payload={"owner_pid": 123},
    )
    backtest = board.create_task(task_type="backtest", title="Backtest")
    claimed = board.claim_task(research["task_id"], worker_id="worker-a", ttl_seconds=60)
    assert claimed is not None
    board.claim_task(backtest["task_id"], worker_id="worker-a", ttl_seconds=60)

    active_research = board.list_tasks(
        statuses=("ready", "running"),
        task_type="research",
        title="Strategy factory run_once",
    )

    assert [item["task_id"] for item in active_research] == [research["task_id"]]
    assert active_research[0]["payload"]["owner_pid"] == 123


def test_factory_task_board_caps_large_payload_and_result_json(tmp_path) -> None:
    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    task = board.create_task(
        task_type="research",
        title="Heavy task board payload",
        payload=_large_board_payload(),
        artifact_refs=[{"artifact_type": "raw", "payload": _large_board_payload()}],
    )
    assert _json_len(task["payload"]) < JSON_LIMIT
    assert "resolved_candidate_envelope" not in task["payload"]
    assert "resolved_candidate_envelope_summary" in task["payload"]

    claimed = board.claim_task(task["task_id"], worker_id="worker-heavy", ttl_seconds=60)
    assert claimed is not None
    completed = board.complete_task(
        task["task_id"],
        claim_token=claimed["claim_token"],
        artifact_refs=[{"artifact_type": "result", "payload": _large_board_payload()}],
        result={"result": _large_board_payload()},
    )
    assert completed is not None
    assert _json_len(completed["artifact_refs"]) < JSON_LIMIT

    conn = sqlite3.connect(board.path)
    try:
        payload_json, artifact_refs_json = conn.execute(
            "SELECT payload_json, artifact_refs_json FROM factory_tasks WHERE task_id = ?",
            (task["task_id"],),
        ).fetchone()
        (result_json,) = conn.execute(
            "SELECT result_json FROM factory_task_attempts WHERE task_id = ? AND status = 'completed'",
            (task["task_id"],),
        ).fetchone()
    finally:
        conn.close()

    payload = json.loads(payload_json)
    artifact_refs = json.loads(artifact_refs_json)
    result = json.loads(result_json)
    assert _json_len(payload) < JSON_LIMIT
    assert _json_len(artifact_refs) < JSON_LIMIT
    assert _json_len(result) < JSON_LIMIT
    assert "resolved_candidate_envelope" not in payload
    assert "resolved_candidate_envelope_summary" in payload
    result_payload = result.get("result") if isinstance(result.get("result"), dict) else result
    assert "resolved_candidate_envelope" not in result_payload
    assert "resolved_candidate_envelope_summary" in result_payload
