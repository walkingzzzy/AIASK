from __future__ import annotations

from datetime import datetime, timedelta, timezone

from strategy_factory.application.factory_task_board import FactoryTaskBoard


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
