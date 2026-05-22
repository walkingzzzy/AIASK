from __future__ import annotations

from aiask_agent.memory import FinancialMemoryStore
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.todo import FinancialTodoStore


def test_session_store_creates_history_and_responses(tmp_path) -> None:
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    session_id = store.create_session(user_id="u1", title="demo")
    store.append_message(session_id, {"role": "user", "content": "hello"})
    messages = store.get_messages(session_id)
    assert messages == [{"role": "user", "content": "hello"}]

    store.save_response("resp_1", session_id, {"response_id": "resp_1", "content": "ok"})
    assert store.get_response("resp_1")["content"] == "ok"
    assert store.delete_response("resp_1") is True
    assert store.get_response("resp_1") is None


def test_memory_is_scoped_by_financial_context(tmp_path) -> None:
    store = FinancialMemoryStore(tmp_path / "state.sqlite3")
    store.add(content="maotai margin note", user_id="u1", symbol="600519", research_topic="margin")
    store.add(content="pingan risk note", user_id="u1", symbol="601318", research_topic="risk")

    maotai = store.search(user_id="u1", symbol="600519")
    assert len(maotai) == 1
    assert maotai[0]["content"] == "maotai margin note"
    assert store.search(user_id="u1", symbol="000001") == []


def test_todo_tracks_financial_workflow_state(tmp_path) -> None:
    store = FinancialTodoStore(tmp_path / "state.sqlite3")
    items = store.set_items(
        session_id="s1",
        user_id="u1",
        items=[
            {"id": "1", "content": "collect evidence", "status": "completed"},
            {"id": "2", "content": "review strategy", "status": "in_progress"},
        ],
    )
    assert [item["status"] for item in items] == ["completed", "in_progress"]
    assert store.list_items(session_id="s1")[1]["content"] == "review strategy"
