"""拆分自 test_strategy_factory_and_marketplace 的 strategy_manager 集成测试。"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import akshare_mcp.tools.managers.strategy_manager as sm_mod

from ._strategy_factory_test_support import _DummyMCP, _StrategyDB


class TestStrategyManager:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_help_action(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="help")
        assert r["success"] is True
        assert "create" in r["data"]["actions"]
        assert "review_report_recheck" in r["data"]["actions"]

    @pytest.mark.asyncio
    async def test_create_strategy(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "测试动量", "strategy_type": "momentum",
            "params": {"lookback": 20}, "author_id": "user1",
        }))
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert sid.startswith("strat_")
        assert db._strategies[sid]["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_strategy_accepts_structured_params(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", params={
            "name": "结构化参数策略",
            "strategy_type": "momentum",
            "params": {"lookback": 10},
            "author_id": "user2",
        })
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert db._strategies[sid]["author_id"] == "user2"

    @pytest.mark.asyncio
    async def test_create_strategy_accepts_dict_kwargs(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs={
            "name": "字典 kwargs 策略",
            "strategy_type": "momentum",
            "author_id": "user3",
        })
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert db._strategies[sid]["author_id"] == "user3"

    @pytest.mark.asyncio
    async def test_create_requires_name(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs="{}")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_publish_and_archive(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        pub = await mcp.strategy_manager(action="publish", kwargs=json.dumps({"strategy_id": sid}))
        assert pub["success"] is True
        assert pub["data"]["status"] == "listed"
        assert db._strategies[sid]["status"] == "listed"

        arc = await mcp.strategy_manager(action="archive", kwargs=json.dumps({"strategy_id": sid}))
        assert arc["success"] is True
        assert db._strategies[sid]["status"] == "archived"

    @pytest.mark.asyncio
    async def test_list_and_rank_keep_published_alias_compatible(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "alias-test",
            "strategy_type": "momentum",
        }))
        sid = cr["data"]["strategy_id"]

        await mcp.strategy_manager(action="publish", kwargs=json.dumps({"strategy_id": sid}))
        await db.save_strategy_metrics(sid, "all", {
            "total_return": 0.12,
            "annual_return": 0.10,
            "sharpe_ratio": 1.1,
            "max_drawdown": 0.08,
            "win_rate": 0.6,
            "calmar_ratio": 1.2,
        })

        listed_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({}))
        published_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({"status": "published"}))
        rank_resp = await mcp.strategy_manager(action="rank", kwargs=json.dumps({"status": "published"}))

        assert listed_resp["success"] is True
        assert listed_resp["data"]["count"] == 1
        assert listed_resp["data"]["strategies"][0]["status"] == "listed"
        assert published_resp["data"]["count"] == 1
        assert published_resp["data"]["strategies"][0]["id"] == sid
        assert rank_resp["data"]["count"] == 1
        assert rank_resp["data"]["strategies"][0]["id"] == sid

    @pytest.mark.asyncio
    async def test_list_and_rank_default_visible_include_incubating(self, setup):
        mcp, db = setup
        incubating = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "incubating-test",
            "strategy_type": "momentum",
        }))
        listed = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "listed-test",
            "strategy_type": "momentum",
        }))
        archived = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "archived-test",
            "strategy_type": "momentum",
        }))

        incubating_id = incubating["data"]["strategy_id"]
        listed_id = listed["data"]["strategy_id"]
        archived_id = archived["data"]["strategy_id"]

        await db.update_strategy_status(incubating_id, "incubating")
        await db.update_strategy_status(listed_id, "listed")
        await db.update_strategy_status(archived_id, "archived")
        await db.save_strategy_metrics(incubating_id, "all", {
            "total_return": 0.08,
            "annual_return": 0.07,
            "sharpe_ratio": 0.9,
            "max_drawdown": 0.05,
            "win_rate": 0.58,
            "calmar_ratio": 1.0,
        })
        await db.save_strategy_metrics(listed_id, "all", {
            "total_return": 0.11,
            "annual_return": 0.09,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.06,
            "win_rate": 0.61,
            "calmar_ratio": 1.1,
        })

        listed_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({}))
        rank_resp = await mcp.strategy_manager(action="rank", kwargs=json.dumps({"limit": 10}))

        listed_ids = {item["id"] for item in listed_resp["data"]["strategies"]}
        ranked_ids = {item["id"] for item in rank_resp["data"]["strategies"]}

        assert listed_resp["success"] is True
        assert listed_ids == {incubating_id, listed_id}
        assert archived_id not in listed_ids
        assert rank_resp["success"] is True
        assert ranked_ids == {incubating_id, listed_id}

    @pytest.mark.asyncio
    async def test_list_status_all_includes_archived(self, setup):
        mcp, db = setup
        incubating = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "all-inc"}))
        archived = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "all-arch"}))
        await db.update_strategy_status(incubating["data"]["strategy_id"], "incubating")
        await db.update_strategy_status(archived["data"]["strategy_id"], "archived")

        all_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({"status": "all", "limit": 10}))
        all_ids = {item["id"] for item in all_resp["data"]["strategies"]}

        assert all_resp["success"] is True
        assert incubating["data"]["strategy_id"] in all_ids
        assert archived["data"]["strategy_id"] in all_ids

    @pytest.mark.asyncio
    async def test_list_and_rank_strip_heavy_marketplace_payloads(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "lean-payload-test",
            "strategy_type": "multi_factor",
            "description": "用于验证榜单返回摘要数据",
            "params": {
                "sample_start_date": "2024-01-01",
                "sample_end_date": "2024-12-31",
                "capacity": 2_500_000,
            },
            "factor_weights": {"mom_20": 0.6, "quality": 0.4},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, "listed")
        await db.save_strategy_metrics(sid, "all", {
            "total_return": 0.15,
            "annual_return": 0.12,
            "sharpe_ratio": 1.35,
            "max_drawdown": 0.07,
            "win_rate": 0.62,
        })

        listed_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({"status": "all"}))
        rank_resp = await mcp.strategy_manager(action="rank", kwargs=json.dumps({"status": "all"}))

        listed = next(item for item in listed_resp["data"]["strategies"] if item["id"] == sid)
        ranked = next(item for item in rank_resp["data"]["strategies"] if item["id"] == sid)

        assert "params" not in listed
        assert "factor_weights" not in listed
        assert listed["sample_start_date"] == "2024-01-01"
        assert listed["capacity"] == 2_500_000
        assert "nav_series" not in ranked
        assert ranked["metrics"]["annual_return"] == 0.12
        assert ranked["sharpe_ratio"] == 1.35

    @pytest.mark.asyncio
    async def test_review_rating_validation(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        r = await mcp.strategy_manager(action="review", kwargs=json.dumps({
            "strategy_id": sid, "rating": 6,
        }))
        assert r["success"] is False

        r = await mcp.strategy_manager(action="review", kwargs=json.dumps({
            "strategy_id": sid, "rating": 4, "comment": "不错",
        }))
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        sub = await mcp.strategy_manager(action="subscribe", kwargs=json.dumps({
            "strategy_id": sid, "user_id": "u1",
        }))
        assert sub["success"] is True

        subs = await mcp.strategy_manager(action="my_subscriptions", kwargs=json.dumps({
            "user_id": "u1",
        }))
        assert subs["data"]["count"] == 1

        unsub = await mcp.strategy_manager(action="unsubscribe", kwargs=json.dumps({
            "strategy_id": sid, "user_id": "u1",
        }))
        assert unsub["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="nonexistent_action")
        assert r["success"] is False
        assert "Unknown action" in r["error"]

    @pytest.mark.asyncio
    async def test_review_report_events_and_incubation_overview(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "孵化策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "status_after_review": "incubating",
                "committee_decision": "revise",
                "committee_final_score": 0.6842,
            },
            "quality_gate": {"passed": True, "wf_ic_ir": 0.41, "reasons": []},
            "validation_report": {},
            "risk_report": {},
            "dedup_report": {"match_type": None},
            "backtest_metrics": {},
            "committee_review": {
                "decision": "revise",
                "final_score": 0.6842,
                "execution_score": 0.48,
                "capacity_score": 0.55,
                "task_alignment_score": 0.44,
                "accept_blockers": [
                    "execution_floor_failed",
                    "task_alignment_floor_failed",
                ],
            },
            "snapshot": {},
        })
        await db.update_strategy_status(
            sid,
            "incubating",
            actor_id="seed-bot",
            reason="seed",
            metadata={"source": "submission", "batch": "A1"},
        )
        await db.update_strategy_status(
            sid,
            "listed",
            actor_id="reviewer",
            reason="promote",
            metadata={"source": "review", "score": 91},
        )
        now = datetime.now(timezone.utc)
        db._events[sid][0]["created_at"] = (now - timedelta(days=2)).isoformat()
        db._events[sid][1]["created_at"] = now.isoformat()
        await db.save_strategy_metrics(sid, "all", {"sharpe_ratio": 0.8, "max_drawdown": 0.12})
        db._signal_stats[sid] = {
            "hit_rate": {1: 0.51, 5: 0.52, 10: 0.50, 20: 0.49},
            "forward_ic": {1: 0.01, 5: 0.08, 10: 0.04, 20: 0.02},
            "forward_sharpe": {1: 0.12, 5: 0.66, 10: 0.41, 20: 0.20},
            "total_signals": 18,
        }

        review = await mcp.strategy_manager(action="review_report", kwargs=json.dumps({"strategy_id": sid}))
        events = await mcp.strategy_manager(action="events", kwargs=json.dumps({"strategy_id": sid}))
        filtered_events = await mcp.strategy_manager(action="events", kwargs=json.dumps({
            "strategy_id": sid,
            "event_type": "status_change",
            "from_status": "incubating",
            "to_status": "listed",
            "actor_id": "reviewer",
            "start_time": now.date().isoformat(),
            "end_time": now.date().isoformat(),
            "limit": 10,
        }))
        incubation = await mcp.strategy_manager(action="incubation_overview", kwargs=json.dumps({"strategy_id": sid}))

        assert review["success"] is True
        assert review["data"]["passed"] is True
        assert review["data"]["reports"][0]["report_type"] == "submission"
        assert review["data"]["summary"]["committee_decision"] == "revise"
        assert review["data"]["summary"]["committee_final_score"] == pytest.approx(0.6842)
        assert review["data"]["committee_review"]["execution_score"] == pytest.approx(0.48)
        assert review["data"]["committee_review"]["capacity_score"] == pytest.approx(0.55)
        assert review["data"]["committee_review"]["task_alignment_score"] == pytest.approx(0.44)
        assert review["data"]["committee_review"]["accept_blockers"] == [
            "execution_floor_failed",
            "task_alignment_floor_failed",
        ]
        assert review["data"]["constraint_check"] == {}
        assert review["data"]["attempt_adjustment"] == {}
        assert review["data"]["validation_profile"]["primary_validation_layer"] is None
        assert events["data"]["count"] == 2
        assert events["data"]["events"][0]["event_type"] == "status_change"
        assert events["data"]["events"][0]["metadata"]["source"] == "review"
        assert filtered_events["success"] is True
        assert filtered_events["data"]["count"] == 1
        assert filtered_events["data"]["events"][0]["from_status"] == "incubating"
        assert filtered_events["data"]["events"][0]["to_status"] == "listed"
        assert filtered_events["data"]["events"][0]["actor_id"] == "reviewer"
        assert filtered_events["data"]["events"][0]["metadata"]["score"] == 91
        assert incubation["data"]["promotion_ready"] is True
        assert incubation["data"]["observed_forward_days"] == [1, 5, 10, 20]
        assert incubation["data"]["missing_forward_days"] == []
        assert len(incubation["data"]["forward_returns"]) == 4
        assert incubation["data"]["blockers_by_period"] == {}
        assert incubation["data"]["risk_flags_by_period"] == {}

    @pytest.mark.asyncio
    async def test_incubation_overview_surfaces_multi_period_blockers(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期阻塞策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.update_strategy_status(sid, "incubating", actor_id="test", reason="seed")
        await db.save_strategy_metrics(sid, "all", {"sharpe_ratio": 0.9, "max_drawdown": 0.10})
        db._signal_stats[sid] = {
            "hit_rate": {1: 0.51, 5: 0.50, 10: 0.47, 20: 0.40},
            "forward_ic": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
            "forward_sharpe": {1: 0.10, 5: 0.55, 10: 0.21, 20: 0.05},
            "total_signals": 14,
        }

        incubation = await mcp.strategy_manager(action="incubation_overview", kwargs=json.dumps({"strategy_id": sid}))

        assert incubation["success"] is True
        assert incubation["data"]["promotion_ready"] is False
        assert incubation["data"]["deprecation_risk"] is False
        assert "20D" in incubation["data"]["blockers_by_period"]
        assert any("20D命中率" in item for item in incubation["data"]["blockers_by_period"]["20D"])
        assert incubation["data"]["risk_flags_by_period"] == {}

    @pytest.mark.asyncio
    async def test_incubation_overview_and_promotion_review_block_grade_d_and_live_gate_gap(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "D级阻断策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.update_strategy_status(sid, "incubating", actor_id="test", reason="seed")
        await db.save_strategy_metrics(sid, "all", {"sharpe_ratio": 1.15, "max_drawdown": 0.06})
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "D",
                "strict_incubation_ready": False,
                "strict_incubation_blocked": True,
                "admission_stage": "research",
                "incubation_pass_mode": "failed",
            },
            "quality_gate": {
                "strict_incubation_ready": False,
                "strict_incubation_blocked": True,
                "incubation_candidate_ready": False,
                "live_candidate_ready": False,
                "admission_stage": "research",
                "incubation_pass_mode": "failed",
                "admission_block_reasons": [
                    "validation_grade_d_not_allowed_for_incubation",
                    "formal_multiple_testing_mode_required_for_live_admission",
                ],
            },
        })
        db._signal_stats[sid] = {
            "hit_rate": {1: 0.54, 5: 0.58, 10: 0.55, 20: 0.51},
            "forward_ic": {1: 0.03, 5: 0.08, 10: 0.06, 20: 0.04},
            "forward_sharpe": {1: 0.10, 5: 0.70, 10: 0.46, 20: 0.18},
            "total_signals": 24,
        }

        incubation = await mcp.strategy_manager(action="incubation_overview", kwargs=json.dumps({"strategy_id": sid}))
        review = await mcp.strategy_manager(action="promotion_review_run", kwargs=json.dumps({"strategy_id": sid}))

        assert incubation["success"] is True
        assert incubation["data"]["promotion_ready"] is False
        assert incubation["data"]["validation_grade"] == "D"
        assert incubation["data"]["strict_incubation_ready"] is False
        assert incubation["data"]["live_candidate_ready"] is False
        assert incubation["data"]["strict_live_alignment_status"] == "aligned_blocked"
        assert "validation_grade_d_not_allowed_for_promotion" in incubation["data"]["blockers"]
        assert "strict_incubation_gate_not_ready" in incubation["data"]["blockers"]
        assert "live_gate_not_ready" in incubation["data"]["blockers"]
        assert review["success"] is True
        assert review["data"]["review"]["recommendation"] != "promote"
        assert review["data"]["review"]["summary"]["promotion_ready"] is False
        assert review["data"]["review"]["summary"]["validation_grade"] == "D"
        assert review["data"]["review"]["summary"]["strict_incubation_ready"] is False
        assert review["data"]["review"]["summary"]["live_candidate_ready"] is False

    @pytest.mark.asyncio
    async def test_lifecycle_scan_uses_multi_period_forward_returns(self, setup):
        mcp, db = setup

        good = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期晋级策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        good_id = good["data"]["strategy_id"]
        await db.update_strategy_status(good_id, "incubating", actor_id="test", reason="seed")
        await db.save_strategy_metrics(good_id, "all", {"sharpe_ratio": 0.85, "max_drawdown": 0.11})
        db._signal_stats[good_id] = {
            "hit_rate": {1: 0.52, 5: 0.54, 10: 0.51, 20: 0.47},
            "forward_ic": {1: 0.01, 5: 0.07, 10: 0.05, 20: 0.03},
            "forward_sharpe": {1: 0.08, 5: 0.61, 10: 0.33, 20: 0.12},
            "total_signals": 18,
        }

        bad = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期淘汰策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        bad_id = bad["data"]["strategy_id"]
        await db.update_strategy_status(bad_id, "listed", actor_id="test", reason="seed")
        await db.save_strategy_metrics(bad_id, "all", {"sharpe_ratio": 0.72, "max_drawdown": 0.14})
        db._signal_stats[bad_id] = {
            "hit_rate": {1: 0.48, 5: 0.41, 10: 0.38, 20: 0.22},
            "forward_ic": {1: 0.01, 5: 0.02, 10: -0.01, 20: -0.08},
            "forward_sharpe": {1: 0.05, 5: 0.12, 10: -0.05, 20: -0.31},
            "total_signals": 16,
        }
        await db.save_strategy_incubation_metric(bad_id, '2026-03-08', {
            'account_id': 'acct_bad', 'stage': 'candidate', 'decision': 'halt', 'nav': 0.97,
            'total_orders': 3, 'total_trades': 2,
        })
        await db.save_strategy_incubation_metric(bad_id, '2026-03-07', {
            'account_id': 'acct_bad', 'stage': 'candidate', 'decision': 'halt', 'nav': 0.96,
            'total_orders': 2, 'total_trades': 1,
        })

        result = await sm_mod._lifecycle_scan(db)

        assert result["scanned"] >= 2
        assert db._strategies[good_id]["status"] == "listed"
        assert db._strategies[bad_id]["status"] == "deprecated"
        assert any(item["id"] == good_id and item["reason"] == "incubation_promoted" for item in result["transitions"])
        assert any(item["id"] == bad_id and item["reason"] == "listed_degraded" for item in result["transitions"])

    @pytest.mark.asyncio
    async def test_review_report_recheck_persists_latest_report(self, setup, monkeypatch):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "复检策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "status_after_review": "incubating",
                "review_source": "strategy_factory_submit",
            },
            "quality_gate": {"passed": True, "reasons": []},
            "validation_report": {"rating": {"grade": "B"}},
            "risk_report": {},
            "dedup_report": {},
            "backtest_metrics": {"sharpe_ratio": 1.1},
            "committee_review": {
                "decision": "revise",
                "final_score": 0.6123,
                "execution_score": 0.42,
                "capacity_score": 0.58,
                "task_alignment_score": 0.43,
                "accept_blockers": [
                    "execution_floor_failed",
                    "task_alignment_floor_failed",
                ],
            },
            "snapshot": {"date": "2026-03-06"},
        })

        monkeypatch.setattr(
            "akshare_mcp.tools.managers.strategy_mgr_lifecycle.run_quality_gate",
            AsyncMock(return_value={
                "passed": False,
                "reason": "Insufficient kline data for quality gate",
                "attempt_adjustment": {
                    "attempt_count": "12",
                    "selected_count": "2",
                    "penalty": "0.03",
                },
            }),
        )

        recheck = await mcp.strategy_manager(action="review_report_recheck", kwargs=json.dumps({"strategy_id": sid}))
        review = await mcp.strategy_manager(action="review_report", kwargs=json.dumps({"strategy_id": sid}))

        assert recheck["success"] is True
        assert recheck["data"]["summary"]["review_source"] == "review_report_recheck"
        assert recheck["data"]["quality_gate"]["reason_codes"] == ["insufficient_kline_data"]
        assert recheck["data"]["attempt_adjustment"]["attempt_count"] == 12
        assert recheck["data"]["attempt_adjustment"]["selection_ratio"] == pytest.approx(0.1667, abs=1e-4)
        assert recheck["data"]["summary"]["committee_decision"] == "revise"
        assert recheck["data"]["summary"]["committee_final_score"] == pytest.approx(0.6123)
        assert recheck["data"]["committee_review"]["accept_blockers"] == [
            "execution_floor_failed",
            "task_alignment_floor_failed",
        ]
        assert recheck["data"]["constraint_check"] == {}
        assert recheck["data"]["validation_profile"]["primary_validation_layer"] is None
        assert review["data"]["summary"]["review_source"] == "review_report_recheck"
        assert review["data"]["reports"][0]["report_type"].startswith("recheck:")
        assert review["data"]["reports"][1]["report_type"] == "submission"
        assert review["data"]["committee_review"]["decision"] == "revise"
        assert review["data"]["committee_review"]["accept_blockers"] == [
            "execution_floor_failed",
            "task_alignment_floor_failed",
        ]

    @pytest.mark.asyncio
    async def test_factory_status_and_run_once_actions(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_hist_1",
            "status": "success",
            "started_at": "2026-03-06T10:00:00",
            "completed_at": "2026-03-06T10:00:05",
            "elapsed_seconds": 5.0,
            "summary": {
                "candidates_spawned": 2,
                "submitted": 1,
                "event_task_count": 1,
                "snapshot_task_count": 1,
                "bulk_stock_matrix_enabled": True,
                "bulk_stock_matrix_universe_limit": 500,
                "bulk_stock_matrix_requested_universe_offset": 500,
                "bulk_stock_matrix_effective_universe_offset": 500,
                "bulk_stock_matrix_universe_offset_fallback": False,
                "bulk_stock_matrix_eligible_stock_count": 500,
                "bulk_stock_matrix_next_universe_offset": 1000,
                "bulk_stock_matrix_cursor_wrapped": False,
                "stock_family_allocation_count": 5485,
                "family_preference_order": ["mean_reversion_short", "momentum", "ma_cross"],
                "family_preference_source_mode": "stock_family_allocation",
                "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                "governed_pending_candidate_count": 0,
                "external_llm_provider_health_status": "degraded",
                "external_llm_provider_control_mode": "suppress",
                "candidate_local_attempt_count": 6,
                "task_local_attempt_count": 4,
                "cohort_effective_trials": 9.5,
                "refresh_existing_count": 1,
                "spawn_revision_from_existing_count": 1,
                "unique_family_holding_universe_count": 4,
                "economic_semantics_missing_count": 1,
                "research_only_count": 1,
                "deferred_submission_count": 1,
                "validation_grade_distribution": {"D": 1},
                "raw_validation_grade_distribution": {"D": 1},
                "effective_validation_grade_distribution": {"D": 1},
                "raw_validation_total_score_mean": 38.0,
                "raw_validation_total_score_p50": 38.0,
                "raw_validation_total_score_p90": 38.0,
                "raw_validation_a_rate": 0.0,
                "raw_validation_b_rate": 0.0,
                "raw_validation_c_rate": 0.0,
                "raw_validation_d_rate": 1.0,
                "validation_family_quality_panel": [
                    {
                        "strategy_family": "momentum",
                        "holding_period_bucket": "swing",
                        "validation_focus": "event_target_only",
                        "strategy_count": 1,
                        "raw_validation_grade_distribution": {"D": 1},
                    }
                ],
                "task_source_counts": {"event_driven": 1, "snapshot": 1},
                "scanner_task_types": {"sector_breakout": 1, "rotation_balanced": 1},
                "event_snapshot_mixed": True,
                "research_summary": {"research_plane_contract_version": "strategy_factory.research_plane.v1"},
                "feedback_summary": {"family_count": 2, "feedback_available": True},
                "incubation_summary": {"gate_3_passed": 1},
                "live_ready_summary": {"live_review_ready_count": 1},
                "autonomy_task_briefs": [
                    {
                        "task_id": "event_demo_1",
                        "task_source": "event_driven",
                        "opportunity_type": "sector_breakout",
                        "generation_limit": 6,
                        "generated_count": 6,
                    }
                ],
            },
            "factor_research": {
                "summary": {
                    "factor_source_mode": "governed_candidate_pool",
                    "active_factor_count": 2,
                    "family_preference_order": [
                        "mean_reversion_short",
                        "momentum",
                        "ma_cross",
                    ],
                    "family_preference_source_mode": "stock_family_allocation",
                    "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                    "governed_candidate_pool_strict_shortfall_count": 3,
                    "stock_family_allocation_count": 5485,
                    "stock_family_allocation_source_mode": "stock_universe_projection",
                },
                "source_chain": ["snapshot.factor_ic", "artifact_v2"],
            },
            "quality_gate": {
                "gate_0": {"passed_count": 2, "failed_count": 0},
                "pre_gate": {"passed_count": 2, "failed_count": 0},
                "gate_1": {"passed_count": 2, "failed_count": 0},
                "gate_2": {"input_count": 2, "passed_count": 2, "failed_count": 0},
                "gate_3": {
                    "input_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "failure_reason_topn": [],
                },
            },
            "stages": {
                "factor_research": {
                    "status": "completed",
                    "ok": True,
                    "research_artifact": {
                        "contract_version": "strategy_factory.research_artifact.v1",
                        "available": True,
                        "active_factor_count": 2,
                    },
                },
                "autonomy": {
                    "status": "completed",
                    "ok": True,
                    "task_artifact": {
                        "contract_version": "strategy_factory.task_artifact.v1",
                        "available": True,
                        "planned_task_count": 2,
                    },
                    "candidate_artifact": {
                        "contract_version": "strategy_factory.candidate_artifact.v1",
                        "available": True,
                        "candidate_count": 2,
                    },
                    "evidence_artifact": {
                        "contract_version": "strategy_factory.research_evidence_artifact.v1",
                        "available": True,
                        "experiment_count": 1,
                    },
                },
                "backtest": {
                    "status": "completed",
                    "ok": True,
                    "summary": {
                        "input_count": 2,
                        "passed_count": 2,
                        "failed_count": 0,
                        "failed_reason_counts": {},
                    },
                },
                "deduplicate": {
                    "status": "completed",
                    "ok": True,
                    "summary": {
                        "input_count": 2,
                        "kept_count": 1,
                        "dropped_count": 1,
                        "refreshed_existing_count": 1,
                    },
                    "kept": [
                        {
                            "strategy_type": "momentum",
                            "target_symbols": ["600519"],
                            "dedup_result": {
                                "duplicate": False,
                                "refresh_existing": True,
                                "refresh_mode": "refresh_metrics_only",
                            },
                        }
                    ],
                },
                "submit": {
                    "status": "completed",
                    "ok": True,
                    "submitted": 1,
                    "gate_3_passed": 1,
                    "strategies": [
                        {
                            "strategy_id": "sid_factory_1",
                            "name": "工厂治理策略",
                            "strategy_type": "momentum",
                            "candidate_family": "momentum",
                            "status": "submitted",
                            "submission_lane": "deferred_submission",
                            "submission_action_type": "create",
                            "primary_validation_layer": "target",
                            "refresh_mode": "refresh_metrics_only",
                            "task_signature": "event_driven|event_demo_1|ai||event_target_only|600519",
                            "validation_profile": {
                                "profile": "event_trade_validation",
                                "validation_focus": "event_target_only",
                                "primary_validation_layer": "target",
                            },
                            "constraint_check": {
                                "constraint_violation": "strict_intersection_trimmed",
                                "intersection_ratio": 0.5,
                            },
                            "committee_review": {
                                "decision": "revise",
                                "final_score": 0.6842,
                                "execution_score": 0.48,
                                "capacity_score": 0.55,
                                "task_alignment_score": 0.44,
                                "accept_blockers": [
                                    "execution_floor_failed",
                                    "task_alignment_floor_failed",
                                ],
                            },
                            "event_window_config": {"lookback_days": 3, "forward_days": 5},
                            "position_assumption": "single_name_full_notional",
                            "attempt_adjustment": {"attempt_count": 4, "selection_ratio": 0.25, "penalty": 0.03},
                            "task_local_attempt_count": 4,
                            "cohort_effective_trials": 9.5,
                            "validation_grade": "D",
                            "raw_validation_grade": "D",
                            "effective_validation_grade": "D",
                            "raw_validation_total_score": 38.0,
                            "validation_total_score": 38.0,
                            "vector_profile_id": "vp_factory_1",
                            "multiple_testing_registry": {"available": True, "task_attempt_count": 4},
                            "multiple_testing_registry_record_id": "mt_factory_1",
                            "candidate_lineage_contract": {"lineage_id": "lineage_factory_1"},
                            "cost_assumptions": {"commission_bps": 8},
                            "explicit_cost_breakdown": {"commission_cost": 120.0},
                            "implicit_cost_breakdown": {"slippage_cost": 36.0},
                            "execution_reality": {"tradability_filter": True},
                            "quality_summary": {"validation_grade": "D"},
                            "research_candidate_ready": True,
                            "incubation_candidate_ready": False,
                            "run_correction": {"deflated_sharpe_effective_trials": 9.5},
                        }
                    ],
                },
                "truncated": True,
                "field_name": "stages",
                "stage_count": 5,
                "stage_names": [
                    "factor_research",
                    "autonomy",
                    "backtest",
                    "deduplicate",
                    "submit",
                ],
            },
            "snapshot_summary": {},
            "error": None,
        })
        await db.save_daily_snapshot("2026-03-06", {
            "date": "2026-03-06",
            "summary": {"listed_count": 12, "degraded": True},
            "completeness": {"completion_ratio": 0.67, "missing_sources": ["north_fund"]},
            "sources": {"north_fund": {"status": "fallback"}},
            "failure_reasons": [{"source": "north_fund", "reason": "network error"}],
            "missing_fields": ["north_fund_3d_net"],
            "degraded": True,
        })

        class _DummyScheduler:
            def status(self):
                return {"running": True, "last_run": None, "last_result": None, "last_summary": None}

            async def run_once(self, db=None):
                return {"run_id": "run_live_1", "status": "success", "summary": {"candidates_spawned": 3}}

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
                "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": 3,
                "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK": 1,
                "STOCK_STRATEGY_MATRIX_RUN_WINDOW": "off_hours",
                "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD": 24,
                "FACTORY_PRE_GATE_ENABLED": True,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")
        run_resp = await mcp.strategy_manager(action="factory_run_once")
        capabilities_resp = await mcp.strategy_manager(action="capabilities")
        runs_resp = await mcp.strategy_manager(action="factory_runs", kwargs=json.dumps({"limit": 1}))
        detail_resp = await mcp.strategy_manager(action="factory_run_detail", kwargs=json.dumps({"run_id": "run_hist_1"}))
        snapshots_resp = await mcp.strategy_manager(action="daily_snapshots", kwargs=json.dumps({"limit": 1}))
        snapshot_resp = await mcp.strategy_manager(action="daily_snapshot", kwargs=json.dumps({"snapshot_date": "2026-03-06"}))
        assert status_resp["data"]["running"] is True
        assert status_resp["data"]["last_summary"]["candidates_spawned"] == 2
        assert status_resp["data"]["last_summary"]["snapshot_task_count"] == 1
        assert status_resp["data"]["last_summary"]["task_source_counts"]["snapshot"] == 1
        assert status_resp["data"]["last_summary"]["event_snapshot_mixed"] is True
        assert status_resp["data"]["last_result"]["family_preference_source_mode"] == "stock_family_allocation"
        assert status_resp["data"]["last_result"]["governed_candidate_pool_provisional_spillover_policy_status"] == "spillover_applied"
        assert status_resp["data"]["last_result"]["stock_family_allocation_count"] == 5485
        assert status_resp["data"]["last_status"] == "success"
        assert status_resp["data"]["last_stock_family_allocation_count"] == 5485
        assert status_resp["data"]["last_family_preference_order"][:2] == ["mean_reversion_short", "momentum"]
        assert status_resp["data"]["last_family_preference_source_mode"] == "stock_family_allocation"
        assert (
            status_resp["data"]["last_governed_candidate_pool_provisional_spillover_policy_status"]
            == "spillover_applied"
        )
        assert status_resp["data"]["last_governed_pending_candidate_count"] == 0
        assert status_resp["data"]["last_external_llm_provider_health_status"] == "degraded"
        assert status_resp["data"]["last_external_llm_provider_control_mode"] == "suppress"
        assert status_resp["data"]["last_candidate_local_attempt_count"] == 6
        assert status_resp["data"]["last_task_local_attempt_count"] == 4
        assert status_resp["data"]["last_cohort_effective_trials"] == 9.5
        assert status_resp["data"]["last_refresh_existing_count"] == 1
        assert status_resp["data"]["last_spawn_revision_from_existing_count"] == 1
        assert status_resp["data"]["last_unique_family_holding_universe_count"] == 4
        assert status_resp["data"]["last_economic_semantics_missing_count"] == 1
        assert status_resp["data"]["last_research_only_count"] == 1
        assert status_resp["data"]["last_deferred_submission_count"] == 1
        assert status_resp["data"]["last_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_raw_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_effective_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_raw_validation_total_score_mean"] == 38.0
        assert status_resp["data"]["last_validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert status_resp["data"]["last_summary"]["candidate_local_attempt_count"] == 6
        assert status_resp["data"]["last_summary"]["validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_summary"]["raw_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_summary"]["autonomy_task_briefs"][0]["task_id"] == "event_demo_1"
        assert status_resp["data"]["bulk_stock_matrix_config"]["enabled"] is True
        assert status_resp["data"]["bulk_stock_matrix_config"]["families_per_stock"] == 3
        assert status_resp["data"]["bulk_stock_matrix_config"]["pre_gate_enabled"] is True
        assert status_resp["data"]["bulk_stock_matrix_config"]["run_window"] == "off_hours"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["source"] == "persisted_run"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["resume_from_run_id"] == "run_hist_1"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["next_universe_offset"] == 1000
        assert run_resp["data"]["status"] == "success"
        assert capabilities_resp["data"]["factory_runs"] is True
        assert capabilities_resp["data"]["factory_bulk_lane"] is True
        assert capabilities_resp["data"]["factory_bulk_lane_enabled"] is True
        assert capabilities_resp["data"]["factory_pre_gate_enabled"] is True
        assert runs_resp["data"]["count"] == 1
        assert runs_resp["data"]["items"][0]["run_id"] == "run_hist_1"
        assert runs_resp["data"]["items"][0]["candidates_spawned"] == 2
        assert runs_resp["data"]["items"][0]["family_preference_order"][:2] == ["mean_reversion_short", "momentum"]
        assert runs_resp["data"]["items"][0]["family_preference_source_mode"] == "stock_family_allocation"
        assert runs_resp["data"]["items"][0]["candidate_local_attempt_count"] == 6
        assert runs_resp["data"]["items"][0]["validation_grade_distribution"] == {"D": 1}
        assert runs_resp["data"]["items"][0]["raw_validation_grade_distribution"] == {"D": 1}
        assert runs_resp["data"]["items"][0]["raw_validation_total_score_mean"] == 38.0
        assert runs_resp["data"]["items"][0]["summary"]["event_task_count"] == 1
        assert runs_resp["data"]["items"][0]["summary"]["event_snapshot_mixed"] is True
        assert detail_resp["data"]["run_id"] == "run_hist_1"
        assert detail_resp["data"]["candidate_local_attempt_count"] == 6
        assert detail_resp["data"]["task_local_attempt_count"] == 4
        assert detail_resp["data"]["cohort_effective_trials"] == 9.5
        assert detail_resp["data"]["refresh_existing_count"] == 1
        assert detail_resp["data"]["spawn_revision_from_existing_count"] == 1
        assert detail_resp["data"]["unique_family_holding_universe_count"] == 4
        assert detail_resp["data"]["economic_semantics_missing_count"] == 1
        assert detail_resp["data"]["research_only_count"] == 1
        assert detail_resp["data"]["deferred_submission_count"] == 1
        assert detail_resp["data"]["validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["raw_validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["raw_validation_total_score_mean"] == 38.0
        assert detail_resp["data"]["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert detail_resp["data"]["summary"]["candidate_local_attempt_count"] == 6
        assert detail_resp["data"]["summary"]["validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["summary"]["raw_validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["summary"]["snapshot_task_count"] == 1
        assert detail_resp["data"]["summary"]["autonomy_task_briefs"][0]["task_source"] == "event_driven"
        assert detail_resp["data"]["research_summary"]["research_plane_contract_version"] == "strategy_factory.research_plane.v1"
        assert detail_resp["data"]["research_plane"]["contract_version"] == "strategy_factory.research_plane.v1"
        assert detail_resp["data"]["research_artifact"]["contract_version"] == "strategy_factory.research_artifact.v1"
        assert detail_resp["data"]["research_artifact"]["family_preference_source_mode"] == "stock_family_allocation"
        assert detail_resp["data"]["research_artifact"]["family_preference_order"][:2] == [
            "mean_reversion_short",
            "momentum",
        ]
        assert (
            detail_resp["data"]["research_artifact"]["governed_candidate_pool_provisional_spillover_policy_status"]
            == "spillover_applied"
        )
        assert detail_resp["data"]["task_artifact"]["planned_task_count"] == 2
        assert detail_resp["data"]["candidate_artifact"]["candidate_count"] == 2
        assert detail_resp["data"]["evidence_artifact"]["experiment_count"] == 1
        assert "truncated" not in detail_resp["data"]["stages"]
        assert detail_resp["data"]["stage_storage_meta"]["truncated"] is True
        assert detail_resp["data"]["stage_storage_meta"]["field_name"] == "stages"
        assert detail_resp["data"]["governance_plane"]["contract_version"] == "strategy_factory.governance_plane.v1"
        assert detail_resp["data"]["gate_artifact"]["contract_version"] == "strategy_factory.gate_artifact.v1"
        assert detail_resp["data"]["gate_artifact"]["gate_3_passed"] == 1
        assert detail_resp["data"]["dedup_artifact"]["kept_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["strategy_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["committee_review_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["committee_decision_counts"]["revise"] == 1
        assert detail_resp["data"]["submission_artifact"]["constraint_check_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["research_only_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["deferred_submission_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["submission_artifact"]["raw_validation_grade_distribution"] == {"D": 1}
        assert detail_resp["data"]["submission_artifact"]["raw_validation_total_score_mean"] == 38.0
        assert detail_resp["data"]["submission_artifact"]["candidate_local_attempt_count"] == 4
        assert detail_resp["data"]["submission_artifact"]["task_local_attempt_count"] == 4
        assert detail_resp["data"]["submission_artifact"]["cohort_effective_trials"] == 9.5
        assert detail_resp["data"]["submission_artifact"]["economic_semantics_missing_count"] == 1
        assert (
            detail_resp["data"]["submission_artifact"]["validation_family_quality_panel"][0]["strategy_family"]
            == "momentum"
        )
        assert detail_resp["data"]["submission_artifact"]["primary_validation_layer_counts"]["target"] == 1
        assert (
            detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["validation_profile"]["profile"]
            == "event_trade_validation"
        )
        assert detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["validation_grade"] == "D"
        assert (
            detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["committee_review"]["decision"]
            == "revise"
        )
        assert (
            detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["committee_review"]["accept_blockers"]
            == ["execution_floor_failed", "task_alignment_floor_failed"]
        )
        assert detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["has_committee_review"] is True
        assert (
            detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["constraint_check"]["constraint_violation"]
            == "strict_intersection_trimmed"
        )
        assert detail_resp["data"]["governance_evidence_artifact"]["multiple_testing_registry_record_count"] == 1
        assert detail_resp["data"]["governance_evidence_artifact"]["committee_review_count"] == 1
        assert detail_resp["data"]["governance_evidence_artifact"]["constraint_check_count"] == 1
        assert detail_resp["data"]["feedback_summary"]["family_count"] == 2
        assert detail_resp["data"]["incubation_summary"]["gate_3_passed"] == 1
        assert detail_resp["data"]["live_ready_summary"]["live_review_ready_count"] == 1
        assert snapshots_resp["data"]["count"] == 1
        assert snapshots_resp["data"]["items"][0]["snapshot_date"] == "2026-03-06"
        assert snapshot_resp["data"]["degraded"] is True

    @pytest.mark.asyncio
    async def test_factory_run_detail_refreshes_run_level_quality_panel_from_latest_reports(self, setup):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_refresh_quality_1",
            "status": "success",
            "started_at": "2026-03-08T10:00:00Z",
            "completed_at": "2026-03-08T10:00:12Z",
            "elapsed_seconds": 12.0,
            "summary": {
                "submitted": 1,
                "validation_grade_distribution": {"C": 1},
                "raw_validation_grade_distribution": {"C": 1},
                "effective_validation_grade_distribution": {"C": 1},
                "raw_validation_total_score_mean": 45.0,
                "raw_validation_total_score_p50": 45.0,
                "raw_validation_total_score_p90": 45.0,
                "raw_validation_a_rate": 0.0,
                "raw_validation_b_rate": 0.0,
                "raw_validation_c_rate": 1.0,
                "raw_validation_d_rate": 0.0,
                "validation_family_quality_panel": [
                    {
                        "strategy_family": "momentum",
                        "holding_period_bucket": "swing",
                        "validation_focus": "target_only",
                        "strategy_count": 1,
                        "raw_validation_grade_distribution": {"C": 1},
                    }
                ],
            },
            "submission_artifact": {
                "strategy_briefs": [
                    {
                        "strategy_id": "factory_momentum_refresh_1",
                        "strategy_name": "Momentum Refresh Candidate",
                        "candidate_family": "momentum",
                        "strategy_type": "momentum",
                        "holding_period_bucket": "swing",
                        "target_pool_id": "explicit:300442",
                        "validation_focus": "target_only",
                        "validation_grade": "C",
                        "raw_validation_grade": "C",
                        "effective_validation_grade": "C",
                        "raw_validation_total_score": 45.0,
                        "strict_incubation_ready": False,
                        "live_candidate_ready": False,
                        "trade_density": 0.72,
                        "post_cost_sharpe": 1.18,
                        "deflated_sharpe_ratio": 0.14,
                        "pbo": 0.22,
                    }
                ],
            },
        })
        await db.save_strategy_quality_report("factory_momentum_refresh_1", "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 55.0,
                "validation_total_score": 55.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
                "strict_incubation_ready": True,
                "live_candidate_ready": False,
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {
                "trade_density": 0.72,
                "post_cost_sharpe": 1.18,
                "deflated_sharpe_ratio": 0.14,
                "pbo": 0.22,
            },
        })

        detail_resp = await mcp.strategy_manager(
            action="factory_run_detail",
            kwargs=json.dumps({"run_id": "run_refresh_quality_1"}),
        )
        runs_resp = await mcp.strategy_manager(
            action="factory_runs",
            kwargs=json.dumps({"limit": 1}),
        )

        assert detail_resp["success"] is True
        assert detail_resp["data"]["raw_validation_grade_distribution"] == {"B": 1}
        assert detail_resp["data"]["validation_grade_distribution"] == {"B": 1}
        assert detail_resp["data"]["effective_validation_grade_distribution"] == {"B": 1}
        assert detail_resp["data"]["raw_validation_total_score_mean"] == 55.0
        assert detail_resp["data"]["summary"]["raw_validation_grade_distribution"] == {"B": 1}
        assert detail_resp["data"]["summary"]["raw_validation_total_score_mean"] == 55.0
        assert detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["raw_validation_grade"] == "B"
        assert detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["raw_validation_total_score"] == 55.0
        assert detail_resp["data"]["unique_family_holding_universe_count"] == 1
        assert detail_resp["data"]["summary"]["unique_family_holding_universe_count"] == 1
        assert detail_resp["data"]["strict_live_alignment_gap_count"] == 1
        assert detail_resp["data"]["strict_live_alignment_gap_rate"] == pytest.approx(1.0)
        assert detail_resp["data"]["summary"]["strict_live_alignment_gap_count"] == 1
        assert detail_resp["data"]["summary"]["strict_live_alignment_status_counts"] == {
            "strict_only_gap": 1,
        }
        assert detail_resp["data"]["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert detail_resp["data"]["validation_family_quality_panel"][0]["raw_validation_grade_distribution"] == {"B": 1}
        assert detail_resp["data"]["validation_family_quality_panel"][0]["raw_validation_b_rate"] == 1.0
        assert runs_resp["success"] is True
        assert runs_resp["data"]["items"][0]["raw_validation_grade_distribution"] == {"B": 1}
        assert runs_resp["data"]["items"][0]["raw_validation_total_score_mean"] == 55.0
        assert runs_resp["data"]["items"][0]["unique_family_holding_universe_count"] == 1
        assert runs_resp["data"]["items"][0]["strict_live_alignment_gap_count"] == 1
        assert runs_resp["data"]["items"][0]["strict_live_alignment_gap_rate"] == pytest.approx(1.0)
        assert runs_resp["data"]["items"][0]["validation_family_quality_panel"][0]["raw_validation_b_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_factory_status_surfaces_quality_baseline_for_factory_generated_cohort(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_baseline_1",
            "status": "success",
            "started_at": "2026-03-07T10:00:00",
            "completed_at": "2026-03-07T10:00:08",
            "elapsed_seconds": 8.0,
            "summary": {
                "candidates_spawned": 6,
                "submitted": 2,
                "research_only_count": 1,
                "deferred_submission_count": 1,
                "validation_grade_distribution": {"D": 1, "B": 1},
                "raw_validation_grade_distribution": {"D": 1, "B": 1},
                "effective_validation_grade_distribution": {"D": 1, "B": 1},
                "raw_validation_total_score_mean": 56.0,
                "raw_validation_total_score_p50": 56.0,
                "raw_validation_total_score_p90": 61.0,
                "raw_validation_a_rate": 0.0,
                "raw_validation_b_rate": 0.5,
                "raw_validation_c_rate": 0.0,
                "raw_validation_d_rate": 0.5,
                "external_llm_provider_health_status": "degraded",
                "external_llm_provider_control_mode": "limited",
            },
        })
        await db.save_strategy({
            "id": "factory_zero_signal",
            "name": "零信号工厂策略",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "submitted",
            "tags": ["factory", "auto_generated"],
            "params": {"lookback": 20},
        })
        await db.save_strategy_quality_report("factory_zero_signal", "submission", {
            "passed": False,
            "summary": {
                "validation_grade": "D",
                "raw_validation_grade": "D",
                "effective_validation_grade": "D",
                "raw_validation_total_score": 34.0,
                "validation_total_score": 34.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {"trade_density": 1.1, "post_cost_sharpe": 0.4, "deflated_sharpe_ratio": 0.0, "pbo": 0.9},
        })
        db._signal_stats["factory_zero_signal"] = {
            "hit_rate": {},
            "forward_ic": {},
            "forward_sharpe": {},
            "total_signals": 0,
        }

        await db.save_strategy({
            "id": "factory_promotion_ready",
            "name": "晋级工厂策略",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "incubating",
            "tags": ["factory", "auto_generated"],
            "params": {"lookback": 30},
        })
        await db.save_strategy_quality_report("factory_promotion_ready", "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 78.0,
                "validation_total_score": 78.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
                "strict_incubation_ready": True,
                "live_candidate_ready": True,
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {"trade_density": 0.72, "post_cost_sharpe": 1.25, "deflated_sharpe_ratio": 0.18, "pbo": 0.32},
        })
        await db.save_strategy_metrics("factory_promotion_ready", "all", {
            "sharpe_ratio": 1.25,
            "max_drawdown": 0.06,
        })
        db._signal_stats["factory_promotion_ready"] = {
            "hit_rate": {1: 0.53, 5: 0.56, 10: 0.54, 20: 0.5},
            "forward_ic": {1: 0.02, 5: 0.08, 10: 0.06, 20: 0.03},
            "forward_sharpe": {1: 0.11, 5: 0.72, 10: 0.44, 20: 0.16},
            "total_signals": 18,
        }

        await db.save_strategy({
            "id": "manual_strategy",
            "name": "人工策略",
            "author_id": "analyst",
            "strategy_type": "momentum",
            "status": "submitted",
            "tags": [],
            "params": {"lookback": 10},
        })
        await db.save_strategy_quality_report("manual_strategy", "submission", {
            "passed": True,
            "summary": {"validation_grade": "A"},
        })
        db._signal_stats["manual_strategy"] = {
            "hit_rate": {1: 0.6, 5: 0.6, 10: 0.6, 20: 0.6},
            "forward_ic": {1: 0.1, 5: 0.1, 10: 0.1, 20: 0.1},
            "forward_sharpe": {1: 1.0, 5: 1.0, 10: 1.0, 20: 1.0},
            "total_signals": 25,
        }

        class _DummyScheduler:
            def status(self):
                return {"running": False, "last_run": None, "last_result": None, "last_summary": None}

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
                "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": 3,
                "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK": 1,
                "STOCK_STRATEGY_MATRIX_RUN_WINDOW": "always",
                "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD": 24,
                "FACTORY_PRE_GATE_ENABLED": True,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        baseline = status_resp["data"]["quality_baseline"]
        assert baseline["contract_version"] == "strategy_factory.quality_baseline.v1"
        assert baseline["latest_run"]["run_id"] == "run_baseline_1"
        assert baseline["latest_run"]["validation_grade_distribution"] == {"D": 1, "B": 1}
        assert baseline["latest_run"]["raw_validation_grade_distribution"] == {"D": 1, "B": 1}
        assert baseline["latest_run"]["raw_validation_b_rate"] == 0.5
        assert baseline["latest_run"]["external_llm_provider_control_mode"] == "limited"
        cohort = baseline["submitted_strategy_cohort"]
        assert cohort["statuses"] == ["submitted", "incubating", "listed"]
        assert cohort["factory_strategy_count"] == 2
        assert cohort["status_counts"] == {"submitted": 1, "incubating": 1}
        assert cohort["validation_grade_distribution"] == {"D": 1, "B": 1}
        assert cohort["raw_validation_grade_distribution"] == {"D": 1, "B": 1}
        assert cohort["raw_validation_total_score_mean"] == pytest.approx(56.0)
        assert cohort["raw_validation_total_score_p50"] == pytest.approx(56.0)
        assert cohort["raw_validation_total_score_p90"] == pytest.approx(73.6)
        assert cohort["raw_validation_b_rate"] == pytest.approx(0.5)
        assert cohort["raw_b_or_above_count"] == 1
        assert cohort["raw_b_or_above_rate"] == pytest.approx(0.5)
        assert cohort["strict_ready_given_raw_b_rate"] == pytest.approx(1.0)
        assert cohort["live_ready_given_raw_b_rate"] == pytest.approx(1.0)
        assert cohort["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert cohort["validation_family_quality_panel"][0]["family_raw_b_rate"] == pytest.approx(0.5)
        assert cohort["zero_signal_count"] == 1
        assert cohort["zero_signal_rate"] == 0.5
        assert cohort["forward_coverage_count"] == 1
        assert cohort["forward_coverage_rate"] == 0.5
        assert cohort["promotion_ready_count"] == 1
        assert cohort["promotion_ready_rate"] == 0.5
        assert cohort["quality_passed_count"] == 1
        assert cohort["quality_pass_rate"] == 0.5
        assert cohort["quality_report_missing_count"] == 0
        assert cohort["baseline_forward_days"] == [1, 5, 10, 20]

    @pytest.mark.asyncio
    async def test_factory_status_quality_baseline_exposes_generation_lane_comparison(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_lane_baseline_1",
            "status": "success",
            "started_at": "2026-03-07T11:00:00Z",
            "completed_at": "2026-03-07T11:00:08Z",
            "elapsed_seconds": 8.0,
            "summary": {
                "submitted": 3,
                "validation_grade_distribution": {"B": 2, "D": 1},
                "raw_validation_grade_distribution": {"B": 2, "D": 1},
                "effective_validation_grade_distribution": {"B": 2, "D": 1},
            },
            "submission_artifact": {
                "strategy_briefs": [
                    {
                        "strategy_id": "run_local_rule_1",
                        "strategy_type": "momentum",
                        "candidate_family": "momentum",
                        "generator_mode": "rule",
                        "raw_validation_grade": "B",
                        "effective_validation_grade": "B",
                        "raw_validation_total_score": 62.0,
                        "strict_incubation_ready": True,
                    },
                    {
                        "strategy_id": "run_hypothesis_1",
                        "strategy_type": "momentum",
                        "candidate_family": "momentum",
                        "generator_mode": "llm_hypothesis_compiler",
                        "candidate_lane": "l2_hypothesis_lowering",
                        "raw_validation_grade": "B",
                        "effective_validation_grade": "B",
                        "raw_validation_total_score": 74.0,
                        "strict_incubation_ready": True,
                        "live_candidate_ready": True,
                    },
                    {
                        "strategy_id": "run_open_dsl_1",
                        "strategy_type": "dsl_rule",
                        "candidate_family": "capital_flow",
                        "generator_mode": "llm_defined",
                        "candidate_lane": "l3_open_dsl",
                        "raw_validation_grade": "D",
                        "effective_validation_grade": "D",
                        "raw_validation_total_score": 39.0,
                    },
                ],
            },
        })

        strategy_rows = [
            {
                "id": "factory_lane_l0",
                "name": "规则层策略",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "status": "submitted",
                "tags": ["factory", "auto_generated", "rule"],
                "params": {"lookback": 20, "generator_mode": "rule"},
            },
            {
                "id": "factory_lane_l1",
                "name": "历史引导策略",
                "author_id": "strategy_factory",
                "strategy_type": "mean_reversion",
                "status": "submitted",
                "tags": ["factory", "auto_generated"],
                "params": {
                    "lookback": 12,
                    "quota_fill": {
                        "fill_source_mode": "historical_guided",
                        "parameter_source": "historical_distribution",
                    },
                },
            },
            {
                "id": "factory_lane_l2",
                "name": "Hypothesis 编译策略",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "status": "incubating",
                "tags": ["factory", "auto_generated", "external_llm"],
                "params": {
                    "generator_mode": "llm_hypothesis_compiler",
                    "candidate_lane": "l2_hypothesis_lowering",
                    "candidate_provenance": {"generator_mode": "llm_hypothesis_compiler"},
                },
            },
            {
                "id": "factory_lane_l3",
                "name": "Open DSL 策略",
                "author_id": "strategy_factory",
                "strategy_type": "dsl_rule",
                "status": "listed",
                "tags": ["factory", "auto_generated", "external_llm", "open_dsl", "llm_defined"],
                "params": {
                    "generator_mode": "llm_defined",
                    "candidate_lane": "l3_open_dsl",
                    "candidate_provenance": {"generator_mode": "llm_defined"},
                },
            },
        ]
        quality_reports = {
            "factory_lane_l0": {
                "passed": True,
                "summary": {
                    "validation_grade": "B",
                    "raw_validation_grade": "B",
                    "effective_validation_grade": "B",
                    "raw_validation_total_score": 66.0,
                    "validation_total_score": 66.0,
                    "candidate_family": "momentum",
                    "holding_period_bucket": "swing",
                    "strict_incubation_ready": True,
                },
                "validation_profile": {"validation_focus": "target_only"},
            },
            "factory_lane_l1": {
                "passed": False,
                "summary": {
                    "validation_grade": "C",
                    "raw_validation_grade": "C",
                    "effective_validation_grade": "C",
                    "raw_validation_total_score": 57.0,
                    "validation_total_score": 57.0,
                    "candidate_family": "mean_reversion",
                    "holding_period_bucket": "short",
                },
                "validation_profile": {"validation_focus": "target_only"},
            },
            "factory_lane_l2": {
                "passed": True,
                "summary": {
                    "validation_grade": "B",
                    "raw_validation_grade": "B",
                    "effective_validation_grade": "B",
                    "raw_validation_total_score": 78.0,
                    "validation_total_score": 78.0,
                    "candidate_family": "momentum",
                    "holding_period_bucket": "swing",
                    "strict_incubation_ready": True,
                    "live_candidate_ready": True,
                },
                "validation_profile": {"validation_focus": "target_only"},
            },
            "factory_lane_l3": {
                "passed": False,
                "summary": {
                    "validation_grade": "D",
                    "raw_validation_grade": "D",
                    "effective_validation_grade": "D",
                    "raw_validation_total_score": 41.0,
                    "validation_total_score": 41.0,
                    "candidate_family": "capital_flow",
                    "holding_period_bucket": "medium",
                },
                "validation_profile": {"validation_focus": "target_only"},
            },
        }
        for row in strategy_rows:
            await db.save_strategy(row)
            await db.save_strategy_metrics(row["id"], "all", {"sharpe_ratio": 1.1, "max_drawdown": 0.08})
            await db.save_strategy_quality_report(row["id"], "submission", quality_reports[row["id"]])
            db._signal_stats[row["id"]] = {
                "hit_rate": {1: 0.52, 5: 0.55, 10: 0.53, 20: 0.51},
                "forward_ic": {1: 0.02, 5: 0.05, 10: 0.04, 20: 0.03},
                "forward_sharpe": {1: 0.08, 5: 0.40, 10: 0.25, 20: 0.12},
                "total_signals": 16,
            }

        class _DummyScheduler:
            def status(self):
                return {"running": False, "last_run": None, "last_result": None, "last_summary": None}

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
                "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": 3,
                "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK": 1,
                "STOCK_STRATEGY_MATRIX_RUN_WINDOW": "always",
                "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD": 24,
                "FACTORY_PRE_GATE_ENABLED": True,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        baseline = status_resp["data"]["quality_baseline"]
        cohort = baseline["submitted_strategy_cohort"]
        assert cohort["generation_lane_definition"].startswith("按持久化的 generator_mode")
        assert cohort["generation_mode_counts"] == {
            "rule": 2,
            "llm_hypothesis_compiler": 1,
            "llm_defined": 1,
        }
        lane_panel = {
            item["lane_key"]: item
            for item in cohort["generation_lane_quality_panel"]
        }
        assert lane_panel["l0_local_rule"]["strategy_count"] == 1
        assert lane_panel["l1_historical_guided"]["strategy_count"] == 1
        assert lane_panel["l2_hypothesis_lowering"]["strategy_count"] == 1
        assert lane_panel["l2_hypothesis_lowering"]["raw_validation_b_rate"] == pytest.approx(1.0)
        assert lane_panel["l2_hypothesis_lowering"]["live_candidate_ready_rate"] == pytest.approx(1.0)
        assert lane_panel["l3_open_dsl"]["generation_tier"] == "L3"
        assert lane_panel["l3_open_dsl"]["raw_validation_grade_distribution"] == {"D": 1}

        latest_lane_panel = {
            item["lane_key"]: item
            for item in baseline["latest_run"]["generation_lane_quality_panel"]
        }
        assert baseline["latest_run"]["generation_mode_counts"] == {
            "rule": 1,
            "llm_hypothesis_compiler": 1,
            "llm_defined": 1,
        }
        assert latest_lane_panel["l0_local_rule"]["strategy_count"] == 1
        assert latest_lane_panel["l2_hypothesis_lowering"]["strategy_count"] == 1
        assert latest_lane_panel["l3_open_dsl"]["strategy_count"] == 1

    @pytest.mark.asyncio
    async def test_factory_status_quality_baseline_tracks_strict_live_alignment_and_grade_d_pass_rates(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_gate3_acceptance_1",
            "status": "success",
            "started_at": "2026-03-05T10:00:00Z",
            "completed_at": "2026-03-05T10:00:08Z",
            "elapsed_seconds": 8.0,
            "summary": {
                "candidates_spawned": 3,
                "submitted": 1,
                "validation_grade_distribution": {"D": 1, "B": 2},
                "raw_validation_grade_distribution": {"D": 1, "B": 2},
                "effective_validation_grade_distribution": {"D": 1, "B": 2},
                "external_llm_provider_health_status": "degraded",
                "external_llm_provider_control_mode": "limited",
            },
        })

        strategy_rows = [
            {
                "id": "factory_grade_d_blocked",
                "name": "D级阻断工厂策略",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "status": "submitted",
                "tags": ["factory", "auto_generated"],
                "params": {"lookback": 10},
            },
            {
                "id": "factory_strict_only_gap",
                "name": "仅严格孵化工厂策略",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "status": "incubating",
                "tags": ["factory", "auto_generated"],
                "params": {"lookback": 20},
            },
            {
                "id": "factory_live_ready",
                "name": "Live就绪工厂策略",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "status": "incubating",
                "tags": ["factory", "auto_generated"],
                "params": {"lookback": 30},
            },
        ]
        for row in strategy_rows:
            await db.save_strategy(row)
            await db.save_strategy_metrics(row["id"], "all", {"sharpe_ratio": 1.2, "max_drawdown": 0.06})
            db._signal_stats[row["id"]] = {
                "hit_rate": {1: 0.54, 5: 0.58, 10: 0.55, 20: 0.51},
                "forward_ic": {1: 0.03, 5: 0.08, 10: 0.06, 20: 0.04},
                "forward_sharpe": {1: 0.10, 5: 0.70, 10: 0.46, 20: 0.18},
                "total_signals": 24,
            }

        await db.save_strategy_quality_report("factory_grade_d_blocked", "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "D",
                "raw_validation_grade": "D",
                "effective_validation_grade": "D",
                "raw_validation_total_score": 36.0,
                "validation_total_score": 36.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {
                "strict_incubation_ready": False,
                "strict_incubation_blocked": True,
                "incubation_candidate_ready": False,
                "live_candidate_ready": False,
                "admission_stage": "research",
                "incubation_pass_mode": "failed",
                "admission_block_reasons": ["validation_grade_d_not_allowed_for_incubation"],
                "trade_density": 1.3,
                "post_cost_sharpe": 0.55,
                "deflated_sharpe_ratio": 0.0,
                "pbo": 0.91,
            },
        })
        await db.save_strategy_quality_report("factory_strict_only_gap", "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 63.0,
                "validation_total_score": 63.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {
                "strict_incubation_ready": True,
                "strict_incubation_blocked": False,
                "incubation_candidate_ready": True,
                "live_candidate_ready": False,
                "admission_stage": "incubation",
                "incubation_pass_mode": "strict",
                "admission_block_reasons": ["formal_multiple_testing_mode_required_for_live_admission"],
                "trade_density": 0.82,
                "post_cost_sharpe": 1.08,
                "deflated_sharpe_ratio": 0.14,
                "pbo": 0.34,
            },
        })
        await db.save_strategy_quality_report("factory_live_ready", "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 68.0,
                "validation_total_score": 68.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
            "quality_gate": {
                "strict_incubation_ready": True,
                "strict_incubation_blocked": False,
                "incubation_candidate_ready": True,
                "live_candidate_ready": True,
                "admission_stage": "live",
                "incubation_pass_mode": "strict",
                "admission_block_reasons": [],
                "trade_density": 0.64,
                "post_cost_sharpe": 1.21,
                "deflated_sharpe_ratio": 0.18,
                "pbo": 0.28,
            },
        })

        class _DummyScheduler:
            def status(self):
                return {"running": False, "last_run": None, "last_result": None, "last_summary": None}

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
                "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": 3,
                "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN": 180,
                "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK": 1,
                "STOCK_STRATEGY_MATRIX_RUN_WINDOW": "always",
                "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD": 24,
                "FACTORY_PRE_GATE_ENABLED": True,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        cohort = status_resp["data"]["quality_baseline"]["submitted_strategy_cohort"]
        assert cohort["factory_strategy_count"] == 3
        assert cohort["promotion_ready_count"] == 1
        assert cohort["promotion_ready_rate"] == pytest.approx(0.3333)
        assert cohort["raw_validation_grade_distribution"] == {"D": 1, "B": 2}
        assert cohort["raw_validation_total_score_mean"] == pytest.approx(55.6667)
        assert cohort["raw_validation_b_rate"] == pytest.approx(0.6667)
        assert cohort["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert cohort["strict_incubation_ready_count"] == 2
        assert cohort["strict_incubation_ready_rate"] == pytest.approx(0.6667)
        assert cohort["live_candidate_ready_count"] == 1
        assert cohort["live_candidate_ready_rate"] == pytest.approx(0.3333)
        assert cohort["live_gate_ready_count"] == 1
        assert cohort["live_gate_ready_rate"] == pytest.approx(0.3333)
        assert cohort["raw_b_or_above_count"] == 2
        assert cohort["raw_b_or_above_rate"] == pytest.approx(0.6667)
        assert cohort["strict_ready_given_raw_b_count"] == 2
        assert cohort["strict_ready_given_raw_b_rate"] == pytest.approx(1.0)
        assert cohort["live_ready_given_raw_b_count"] == 1
        assert cohort["live_ready_given_raw_b_rate"] == pytest.approx(0.5)
        assert cohort["strict_live_alignment_gap_count"] == 1
        assert cohort["strict_live_alignment_gap_rate"] == pytest.approx(0.3333)
        assert cohort["strict_live_alignment_status_counts"] == {
            "aligned_blocked": 1,
            "strict_only_gap": 1,
            "aligned_live_ready": 1,
        }
        assert cohort["validation_grade_d_strict_incubation_pass_count"] == 0
        assert cohort["validation_grade_d_strict_incubation_pass_rate"] == 0.0
        assert cohort["validation_grade_d_promotion_ready_count"] == 0
        assert cohort["validation_grade_d_promotion_ready_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_factory_status_exposes_recent_run_diagnostics_for_readiness_and_quality_trends(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_diag_success_gap",
            "status": "success",
            "started_at": "2026-03-04T10:00:00Z",
            "completed_at": "2026-03-04T10:00:10Z",
            "elapsed_seconds": 10.0,
            "summary": {
                "factory_readiness_decision": "proceed",
                "factory_readiness_can_proceed": True,
                "factory_readiness_score": 0.78,
                "submitted": 1,
                "deferred_submission_count": 1,
                "raw_b_or_above_rate": 1.0,
                "strict_ready_given_raw_b_rate": 1.0,
                "live_ready_given_raw_b_rate": 0.0,
                "strict_live_alignment_gap_count": 1,
                "strict_live_alignment_gap_rate": 1.0,
            },
            "stages": {
                "readiness": {
                    "status": "partial",
                    "decision": "proceed",
                    "can_proceed": True,
                    "warnings": ["budget_feedback_evidence_debt_elevated"],
                },
                "submit": {"status": "completed", "ok": True},
            },
        })
        await db.save_strategy_factory_run({
            "run_id": "run_diag_blocked",
            "status": "skipped",
            "started_at": "2026-03-05T10:00:00Z",
            "completed_at": "2026-03-05T10:00:03Z",
            "elapsed_seconds": 3.0,
            "summary": {
                "factory_readiness_decision": "blocked",
                "factory_readiness_can_proceed": False,
                "factory_readiness_score": 0.34,
                "skip_reason": "readiness_blocked",
            },
            "stages": {
                "readiness": {
                    "status": "failed",
                    "decision": "blocked",
                    "can_proceed": False,
                    "blockers": ["governed_candidate_pool_missing_after_scheduler_success"],
                    "warnings": ["factor_scheduler_recent_success_without_governed_pool"],
                    "skip_reason": "readiness_blocked",
                },
            },
        })
        await db.save_strategy_factory_run({
            "run_id": "run_diag_success_latest",
            "status": "success",
            "started_at": "2026-03-06T10:00:00Z",
            "completed_at": "2026-03-06T10:00:08Z",
            "elapsed_seconds": 8.0,
            "summary": {
                "factory_readiness_decision": "proceed",
                "factory_readiness_can_proceed": True,
                "factory_readiness_score": 0.91,
                "submitted": 1,
                "raw_b_or_above_rate": 0.5,
                "strict_ready_given_raw_b_rate": 0.5,
                "live_ready_given_raw_b_rate": 0.5,
                "strict_live_alignment_gap_count": 0,
                "strict_live_alignment_gap_rate": 0.0,
            },
            "stages": {
                "readiness": {
                    "status": "completed",
                    "decision": "proceed",
                    "can_proceed": True,
                    "warnings": ["budget_feedback_evidence_debt_elevated"],
                },
                "submit": {"status": "completed", "ok": True},
            },
        })

        class _DummyScheduler:
            def status(self):
                return {"running": False, "last_run": None, "last_result": None, "last_summary": None}

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
                "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": 3,
                "FACTORY_PRE_GATE_ENABLED": True,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        diagnostics = status_resp["data"]["recent_run_diagnostics"]
        assert diagnostics["contract_version"] == "strategy_factory.recent_run_diagnostics.v1"
        assert diagnostics["analyzed_run_count"] == 3
        assert diagnostics["status_counts"] == {"success": 2, "skipped": 1}
        assert diagnostics["readiness_decision_counts"] == {"proceed": 2, "blocked": 1}
        assert diagnostics["readiness_blocked_count"] == 1
        assert diagnostics["readiness_blocked_rate"] == pytest.approx(0.3333)
        assert diagnostics["submit_stage_entered_count"] == 2
        assert diagnostics["submit_stage_entered_rate"] == pytest.approx(0.6667)
        assert diagnostics["submitted_positive_count"] == 2
        assert diagnostics["submitted_positive_rate"] == pytest.approx(0.6667)
        assert diagnostics["blocker_reason_topn"] == [
            {
                "reason_code": "governed_candidate_pool_missing_after_scheduler_success",
                "count": 1,
            }
        ]
        assert diagnostics["warning_reason_topn"][0] == {
            "reason_code": "budget_feedback_evidence_debt_elevated",
            "count": 2,
        }
        quality_progress = diagnostics["quality_progress"]
        assert quality_progress["quality_measurement_run_count"] == 2
        assert quality_progress["latest_raw_b_or_above_rate"] == pytest.approx(0.5)
        assert quality_progress["recent_raw_b_or_above_rate_mean"] == pytest.approx(0.75)
        assert quality_progress["recent_strict_ready_given_raw_b_rate_mean"] == pytest.approx(0.75)
        assert quality_progress["recent_live_ready_given_raw_b_rate_mean"] == pytest.approx(0.25)
        assert quality_progress["strict_live_gap_measurement_run_count"] == 2
        assert quality_progress["strict_live_gap_run_count"] == 1
        assert quality_progress["strict_live_gap_run_rate"] == pytest.approx(0.5)
        assert diagnostics["recent_runs"][0]["run_id"] == "run_diag_success_latest"
        assert diagnostics["recent_runs"][0]["readiness_decision"] == "proceed"
        assert diagnostics["recent_runs"][1]["blocking_reason_codes"] == [
            "governed_candidate_pool_missing_after_scheduler_success",
        ]
        assert (
            status_resp["data"]["quality_baseline"]["recent_run_diagnostics"]["readiness_blocked_count"]
            == 1
        )

    @pytest.mark.asyncio
    async def test_factory_status_prefers_newer_persisted_run_over_stale_scheduler_snapshot(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_hist_new",
            "status": "success",
            "started_at": "2026-03-06T10:00:00Z",
            "completed_at": "2026-03-06T10:00:08Z",
            "elapsed_seconds": 8.0,
            "summary": {
                "candidates_spawned": 4,
                "submitted": 2,
                "scheduler_slo": {"status": "healthy", "alert_count": 0},
                "bulk_stock_matrix_enabled": True,
                "bulk_stock_matrix_universe_limit": 500,
                "bulk_stock_matrix_requested_task_offset": 20,
                "bulk_stock_matrix_effective_task_offset": 20,
                "bulk_stock_matrix_next_task_offset": 40,
                "bulk_stock_matrix_planned_task_count": 20,
            },
        })

        class _DummyScheduler:
            def status(self):
                return {
                    "running": False,
                    "last_run": "2026-03-05T09:00:03Z",
                    "last_result": {
                        "run_id": "run_mem_old",
                        "status": "success",
                        "started_at": "2026-03-05T09:00:00Z",
                        "completed_at": "2026-03-05T09:00:03Z",
                        "summary": {"candidates_spawned": 1},
                    },
                    "last_summary": {"candidates_spawned": 1},
                }

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        assert status_resp["data"]["last_run"] == "2026-03-06T10:00:08Z"
        assert status_resp["data"]["last_result"]["run_id"] == "run_hist_new"
        assert status_resp["data"]["last_result"]["summary"]["scheduler_slo"]["status"] == "healthy"
        assert status_resp["data"]["last_summary"]["candidates_spawned"] == 4
        assert status_resp["data"]["last_status"] == "success"
        assert status_resp["data"]["last_persisted_run"]["run_id"] == "run_hist_new"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["source"] == "persisted_run"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["resume_from_run_id"] == "run_hist_new"
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["available"] is True
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["requested_task_offset"] == 20
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["effective_task_offset"] == 20
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["next_task_offset"] == 40
        assert status_resp["data"]["bulk_stock_matrix_cursor"]["cursor_mode"] == "task_offset"

    @pytest.mark.asyncio
    async def test_factory_status_normalizes_scheduler_last_result_contract(self, setup, monkeypatch):
        mcp, _db = setup

        class _DummyScheduler:
            def status(self):
                return {
                    "running": False,
                    "last_run": "2026-03-07T09:00:03Z",
                    "last_result": {
                        "run_id": "run_mem_latest",
                        "status": "success",
                        "started_at": "2026-03-07T09:00:00Z",
                        "completed_at": "2026-03-07T09:00:03Z",
                    },
                    "last_summary": {
                        "candidates_spawned": 5,
                    "stock_family_allocation_count": 1024,
                    "family_preference_order": ["momentum", "quality_factor"],
                    "family_preference_source_mode": "stock_family_allocation",
                    "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                    "governed_pending_candidate_count": 0,
                    "candidate_local_attempt_count": 5,
                    "validation_grade_distribution": {"C": 1},
                    "raw_validation_grade_distribution": {"D": 1},
                    "effective_validation_grade_distribution": {"C": 1},
                    "raw_validation_total_score_mean": 44.0,
                    "raw_validation_total_score_p50": 44.0,
                    "raw_validation_total_score_p90": 44.0,
                    "raw_validation_a_rate": 0.0,
                    "raw_validation_b_rate": 0.0,
                    "raw_validation_c_rate": 0.0,
                    "raw_validation_d_rate": 1.0,
                },
            }

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        assert status_resp["data"]["last_result"]["run_id"] == "run_mem_latest"
        assert status_resp["data"]["last_result"]["family_preference_source_mode"] == "stock_family_allocation"
        assert (
            status_resp["data"]["last_result"]["governed_candidate_pool_provisional_spillover_policy_status"]
            == "spillover_applied"
        )
        assert status_resp["data"]["last_result"]["stock_family_allocation_count"] == 1024
        assert status_resp["data"]["last_summary"]["family_preference_order"] == ["momentum", "quality_factor"]
        assert status_resp["data"]["last_status"] == "success"
        assert status_resp["data"]["last_stock_family_allocation_count"] == 1024
        assert status_resp["data"]["last_family_preference_order"] == ["momentum", "quality_factor"]
        assert status_resp["data"]["last_family_preference_source_mode"] == "stock_family_allocation"
        assert status_resp["data"]["last_candidate_local_attempt_count"] == 5
        assert status_resp["data"]["last_validation_grade_distribution"] == {"C": 1}
        assert status_resp["data"]["last_raw_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_effective_validation_grade_distribution"] == {"C": 1}
        assert status_resp["data"]["last_raw_validation_total_score_mean"] == 44.0
        assert (
            status_resp["data"]["last_governed_candidate_pool_provisional_spillover_policy_status"]
            == "spillover_applied"
        )
        assert status_resp["data"]["last_governed_pending_candidate_count"] == 0

    @pytest.mark.asyncio
    async def test_factory_status_falls_back_to_last_result_submission_artifact_for_raw_panel(self, setup, monkeypatch):
        mcp, _db = setup

        class _DummyScheduler:
            def status(self):
                return {
                    "running": False,
                    "last_run": "2026-03-08T09:00:03Z",
                    "last_result": {
                        "run_id": "run_mem_submission_artifact",
                        "status": "success",
                        "started_at": "2026-03-08T09:00:00Z",
                        "completed_at": "2026-03-08T09:00:03Z",
                        "governance_plane": {
                            "submission_artifact": {
                                "raw_validation_grade_distribution": {"D": 1},
                                "validation_family_quality_panel": [
                                    {
                                        "strategy_family": "momentum",
                                        "holding_period_bucket": "medium",
                                        "validation_focus": "candidate_target_only",
                                        "strategy_count": 1,
                                        "raw_validation_grade_distribution": {"D": 1},
                                    }
                                ],
                            }
                        },
                    },
                    "last_summary": {
                        "candidates_spawned": 3,
                    },
                }

        monkeypatch.setattr(
            "strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )
        monkeypatch.setattr(
            "strategy_factory.get_factory_constants",
            lambda: {
                "STOCK_STRATEGY_MATRIX_ENABLED": True,
                "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": 500,
            },
        )

        status_resp = await mcp.strategy_manager(action="factory_status")

        assert status_resp["success"] is True
        assert status_resp["data"]["last_result"]["run_id"] == "run_mem_submission_artifact"
        assert status_resp["data"]["last_raw_validation_grade_distribution"] == {"D": 1}
        assert status_resp["data"]["last_validation_family_quality_panel"][0]["strategy_family"] == "momentum"

    @pytest.mark.asyncio
    async def test_submit_allows_provisional_incubation_for_factory_ai_strategy(self, setup, monkeypatch):
        mcp, db = setup
        sid = 'sid_provisional_submit'
        await db.save_strategy({
            'id': sid,
            'name': 'AI原型策略',
            'strategy_type': 'dsl_rule',
            'params': {
                'dsl': {
                    'version': '1.0',
                    'timeframe': 'daily',
                    'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 20}}]},
                    'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 20}}]},
                },
            },
            'status': 'draft',
            'tags': ['factory', 'auto_generated', 'external_llm'],
        })
        await db.save_strategy_metrics(sid, 'backtest', {'sharpe_ratio': 0.21, 'max_drawdown': 0.12, 'trade_count': 2})
        await db.save_strategy_quality_report(sid, 'submission', {
            'passed': False,
            'summary': {
                'validation_grade': 'D',
                'status_after_review': 'submitted',
                'review_source': 'seed_report',
            },
            'quality_gate': {'passed': False, 'reasons': []},
            'validation_report': {'rating': {'grade': 'D'}},
            'risk_report': {'var_percent': 1.8, 'cvar_percent': 2.6, 'stress_loss_percent': -18.0},
            'dedup_report': {},
            'backtest_metrics': {'sharpe_ratio': 0.21, 'max_drawdown': 0.12, 'trade_count': 2},
            'snapshot': {'date': '2026-03-08'},
        })

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": True,
                "passed_strict": False,
                "provisional_pass": True,
                "reasons": [],
                "warnings": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
                "warning_codes": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
            }),
        )

        resp = await mcp.strategy_manager(action='submit', kwargs=json.dumps({'strategy_id': sid}))

        assert resp['success'] is True
        assert resp['data']['status'] == 'incubating'
        assert resp['data']['details']['provisional_pass'] is True

    @pytest.mark.asyncio
    async def test_run_quality_gate_forwards_context_to_shared_submission_gate(self, monkeypatch):
        from akshare_mcp.tools.managers import strategy_mgr_lifecycle as lifecycle_mod

        gate_mock = AsyncMock(return_value={"passed": True, "reasons": []})
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            gate_mock,
        )

        result = await lifecycle_mod.run_quality_gate(
            MagicMock(),
            {"id": "sid_ctx_gate", "strategy_type": "momentum", "params": {}},
            validation_report={"rating": {"grade": "A"}},
            risk_report={"var_percent": 0.9},
            backtest_metrics={"sharpe_ratio": 0.42},
        )

        assert result["passed"] is True
        assert gate_mock.await_count == 1
        gate_kwargs = gate_mock.await_args.kwargs
        assert gate_kwargs["validation_report"]["rating"]["grade"] == "A"
        assert gate_kwargs["risk_report"]["var_percent"] == 0.9
        assert gate_kwargs["backtest_metrics"]["sharpe_ratio"] == 0.42

    @pytest.mark.asyncio
    async def test_review_report_recheck_recomputes_validation_risk_and_backtest_inputs(self, setup, monkeypatch):
        from akshare_mcp.tools.managers import strategy_mgr_lifecycle as lifecycle_mod

        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "复检重算策略",
            "strategy_type": "momentum",
            "params": {"lookback": 30, "threshold": 0.03},
        }))
        sid = created["data"]["strategy_id"]
        await db.save_strategy_metrics(sid, "backtest", {"sharpe_ratio": 1.23, "max_drawdown": 0.08, "trade_count": 9})
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "C",
                "status_after_review": "incubating",
                "review_source": "strategy_factory_submit",
            },
            "quality_gate": {"passed": True, "reasons": []},
            "validation_report": {"rating": {"grade": "C"}},
            "risk_report": {"var_percent": 9.9},
            "dedup_report": {},
            "backtest_metrics": {
                "sharpe_ratio": 0.21,
                "max_drawdown": 0.22,
                "trade_count": 2,
                "post_cost_sharpe": 0.67,
                "target_layer_oos_return": 0.11,
                "target_layer_abnormal_return": 0.07,
                "event_window_hit_ratio": 0.71,
                "post_event_decay": -0.12,
                "trade_density": 0.42,
                "parameter_perturbation_trade_stability": 0.74,
                "primary_validation_layer": "target",
            },
            "snapshot": {"date": "2026-03-09"},
        })
        await db.save_strategy_quality_report(sid, "recheck:latest_skinny", {
            "passed": True,
            "summary": {
                "validation_grade": "C",
                "status_after_review": "submitted",
                "review_source": "review_report_recheck",
            },
            "quality_gate": {"passed": True, "reasons": [], "gate_protocol": "trade_rule_validation:statistical_fallback_research_only"},
            "validation_report": {"rating": {"grade": "C"}},
            "risk_report": {"var_percent": 8.8},
            "dedup_report": {},
            "backtest_metrics": {
                "sharpe_ratio": 0.33,
                "max_drawdown": 0.18,
                "trade_count": 3,
            },
            "snapshot": {"date": "2026-03-10"},
        })

        validation_mock = AsyncMock(return_value={
            "rating": {"grade": "B", "total_score": 61.0},
            "validation_focus": "target_only",
            "validation_focus_layer": "family_peer",
        })
        risk_mock = AsyncMock(return_value={"var_percent": 0.12, "stress_loss_percent": 0.18})
        gate_mock = AsyncMock(return_value={"passed": True, "reasons": []})

        monkeypatch.setattr(lifecycle_mod, "_run_recheck_validation_report", validation_mock)
        monkeypatch.setattr(lifecycle_mod, "_run_recheck_risk_report", risk_mock)
        monkeypatch.setattr(lifecycle_mod, "run_quality_gate", gate_mock)

        recheck = await mcp.strategy_manager(action="review_report_recheck", kwargs=json.dumps({"strategy_id": sid}))

        assert recheck["success"] is True
        assert validation_mock.await_count == 1
        assert risk_mock.await_count == 1
        gate_kwargs = gate_mock.await_args.kwargs
        assert gate_kwargs["validation_report"]["rating"]["grade"] == "B"
        assert gate_kwargs["risk_report"]["var_percent"] == pytest.approx(0.12)
        assert gate_kwargs["backtest_metrics"]["sharpe_ratio"] == pytest.approx(1.23)
        assert gate_kwargs["backtest_metrics"]["post_cost_sharpe"] == pytest.approx(0.67)
        assert gate_kwargs["backtest_metrics"]["trade_density"] == pytest.approx(0.42)
        assert gate_kwargs["backtest_metrics"]["primary_validation_layer"] == "target"
        assert recheck["data"]["validation_report"]["rating"]["grade"] == "B"
        assert recheck["data"]["risk_report"]["var_percent"] == pytest.approx(0.12)
        assert recheck["data"]["backtest_metrics"]["sharpe_ratio"] == pytest.approx(1.23)
        assert recheck["data"]["backtest_metrics"]["post_cost_sharpe"] == pytest.approx(0.67)
        assert recheck["data"]["summary"]["validation_grade"] == "B"

    @pytest.mark.asyncio
    async def test_submit_binds_incubation_account(self, setup, monkeypatch):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "AI提交策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]

        monkeypatch.setattr(
            "akshare_mcp.tools.managers.strategy_mgr_lifecycle.run_quality_gate",
            AsyncMock(return_value={"passed": True, "reasons": []}),
        )

        resp = await mcp.strategy_manager(action="submit", kwargs=json.dumps({"strategy_id": sid}))
        assert resp["success"] is True
        assert resp["data"]["status"] == "incubating"
        assert resp["data"]["incubation_account_id"] is not None

        accounts = await db.list_strategy_incubation_accounts(strategy_id=sid, limit=10)
        assert len(accounts) == 1
        assert accounts[0]["strategy_id"] == sid

    @pytest.mark.asyncio
    async def test_new_capability_and_query_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "扩展动作策略", "strategy_type": "momentum",
        }))
        sid = created["data"]["strategy_id"]

        await db.save_strategy_incubation_account(sid, "acct_1", metadata={"owner": "factory"})
        await db.save_strategy_incubation_metric(sid, "2026-03-06", {
            "account_id": "acct_1",
            "stage": "warmup",
            "decision": "observe",
            "total_value": 101000,
            "max_drawdown": 0.08,
        })
        await db.save_strategy_runtime_risk_event({
            "strategy_id": sid,
            "account_id": "acct_1",
            "severity": "medium",
            "event_type": "alpha_decay",
            "status": "open",
        })
        await db.save_strategy_vector_profile({
            "strategy_id": sid,
            "profile_type": "behavior",
            "vector_method": "price_volume",
            "embedding": [0.1, 0.2, 0.3],
        })
        await db.save_vector_index_registry({
            "index_name": "strategy_behavior",
            "index_version": "v1",
            "status": "active",
        })
        await db.save_strategy_generation_experiment({
            "experiment_id": "exp_test_1",
            "strategy_id": sid,
            "source": "strategy_manager",
            "generator_type": "llm_proxy",
            "status": "generated",
        })
        await db.save_strategy_task_run({
            "task_name": "strategy_ai_cycle",
            "task_scope": "strategy_manager",
            "status": "completed",
        })

        capabilities = await mcp.strategy_manager(action="capabilities")
        incubation_accounts = await mcp.strategy_manager(action="incubation_accounts", kwargs=json.dumps({"strategy_id": sid}))
        incubation_metrics = await mcp.strategy_manager(action="incubation_metrics", kwargs=json.dumps({"strategy_id": sid}))
        risk_events = await mcp.strategy_manager(action="risk_events", kwargs=json.dumps({"strategy_id": sid}))
        vector_profiles = await mcp.strategy_manager(action="vector_profiles", kwargs=json.dumps({"strategy_id": sid}))
        vector_indexes = await mcp.strategy_manager(action="vector_indexes")
        ai_experiments = await mcp.strategy_manager(action="ai_experiments", kwargs=json.dumps({"strategy_id": sid}))
        task_runs = await mcp.strategy_manager(action="task_runs")
        resolve_risk = await mcp.strategy_manager(action="resolve_risk_event", kwargs=json.dumps({"event_id": 1, "resolution": "manual"}))

        assert capabilities["success"] is True
        assert capabilities["data"]["ai_generation"] is True
        assert incubation_accounts["data"]["count"] == 1
        assert incubation_metrics["data"]["latest"]["decision"] == "observe"
        assert risk_events["data"]["count"] == 1
        assert vector_profiles["data"]["count"] == 1
        assert vector_indexes["data"]["count"] == 1
        assert ai_experiments["data"]["count"] == 1
        assert task_runs["data"]["count"] == 1
        assert resolve_risk["data"]["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_ai_generate_action(self, setup, monkeypatch):
        mcp, db = setup

        class _DummyAutonomy:
            async def run_cycle(self, *_args, **_kwargs):
                return {
                    "task_run": {"id": 1, "status": "completed"},
                    "generation": {
                        "count": 2,
                        "stats": {"rule_count": 1},
                        "llm_generation": {},
                        "candidates": [{"strategy_type": "momentum"}],
                    },
                    "review": {
                        "reviewed_count": 2,
                        "rejected_count": 0,
                        "committee_reviews": [],
                        "champion": None,
                    },
                    "experiments": {
                        "count": 1,
                        "items": [{"experiment_id": "exp_dummy_1"}],
                        "status_counts": {"generated": 1},
                    },
                    "submission": {
                        "auto_submit": False,
                        "attempted": False,
                        "submitted_count": 0,
                        "passed_count": 0,
                        "failed_count": 0,
                        "provisional_passed_count": 0,
                        "failure_reason_topn": [],
                        "items": [],
                        "result": None,
                    },
                    "task_run_id": 1,
                    "generated_count": 2,
                    "candidates": [{"strategy_type": "momentum"}],
                    "experiment_records": [{"experiment_id": "exp_dummy_1"}],
                    "submitted": None,
                }

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
            lambda: _DummyAutonomy(),
        )

        resp = await mcp.strategy_manager(action="ai_generate", kwargs=json.dumps({"limit": 2}))
        assert resp["success"] is True
        assert resp["data"]["generated_count"] == 2
        assert resp["data"]["generation"]["count"] == 2
        assert resp["data"]["experiments"]["items"][0]["experiment_id"] == "exp_dummy_1"
        assert resp["data"]["submission"]["result"] is None

    @pytest.mark.asyncio
    async def test_incubation_sync_run_creates_paper_orders_and_nav(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "模拟盘闭环策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.0, 'max_drawdown': -0.08})
        db._signal_stats[sid] = {
            'total_signals': 20,
            'hit_rate': {1: 0.53, 5: 0.58, 10: 0.55, 20: 0.54},
            'forward_ic': {1: 0.01, 5: 0.02, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.08, 5: 0.55, 10: 0.42, 20: 0.35},
        }

        async def _signals(_sid, start_date=None, end_date=None, limit=100):
            return [
                {'code': '600519', 'signal': 1, 'signal_date': str(start_date or '2026-03-08')}
            ]

        db.get_signals = _signals

        sync = await mcp.strategy_manager(action='incubation_sync_run', kwargs=json.dumps({'strategy_id': sid, 'signal_date': '2026-03-08'}))
        paper_account = await mcp.strategy_manager(action='paper_account', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        paper_orders = await mcp.strategy_manager(action='paper_orders', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        paper_nav = await mcp.strategy_manager(action='paper_nav', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        latest_metric = await db.get_latest_strategy_incubation_metric(sid)
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert sync['success'] is True
        assert sync['data']['orders_created'] == 1
        assert sync['data']['orders_filled'] == 1
        assert sync['data']['nav_snapshots'] == 1
        assert paper_account['data']['account']['strategy_id'] == sid
        assert paper_account['data']['order_summary']['total_orders'] == 1
        assert paper_account['data']['order_summary']['total_trades'] == 1
        assert len(paper_account['data']['positions']) == 1
        assert paper_orders['data']['items'][0]['status'] == 'filled'
        assert paper_nav['data']['latest']['total_value'] > 0
        assert latest_metric['total_orders'] == 1
        assert latest_metric['total_trades'] == 1
        assert len(detail['data']['nav_series']) >= 1
        assert capabilities['data']['paper_trading'] is True

    @pytest.mark.asyncio
    async def test_domain_events_vector_governance_and_runtime_cycle_actions(self, setup, monkeypatch):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "治理策略", "strategy_type": "momentum",
        }))
        sid = created["data"]["strategy_id"]
        await db.save_strategy_domain_event({
            "strategy_id": sid,
            "aggregate_type": "strategy",
            "aggregate_id": sid,
            "event_type": "incubation.metric_recorded",
            "source": "incubation",
            "payload": {"decision": "observe"},
        })

        class _DummyVectorGovernance:
            async def reconcile_registry(self, *_args, **_kwargs):
                return {"registry_updated": 1, "stale_marked": 0, "active_indexes": 1, "items": [{"index_name": "strategy_behavior"}]}

            async def rebuild_index(self, *_args, **_kwargs):
                return {"task_run_id": 99, "index_name": "strategy_behavior", "built_profiles": 2}

        class _DummyTracker:
            def status(self):
                return {"running": False, "last_result": {"risk_actions": 1}}

            async def run_once(self):
                return {"task_run_id": 11, "signals_generated": 3, "risk_actions": 1, "vector_registry_updates": 1}

        monkeypatch.setattr(
            "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
            lambda: _DummyVectorGovernance(),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.signal_tracker.get_signal_tracker",
            lambda: _DummyTracker(),
        )

        capabilities = await mcp.strategy_manager(action="capabilities")
        domain_events = await mcp.strategy_manager(action="domain_events", kwargs=json.dumps({"strategy_id": sid}))
        reconcile = await mcp.strategy_manager(action="vector_reconcile")
        rebuild = await mcp.strategy_manager(action="vector_rebuild", kwargs=json.dumps({"statuses": ["draft"], "limit": 5}))
        runtime_status = await mcp.strategy_manager(action="runtime_cycle_status")
        runtime_run = await mcp.strategy_manager(action="runtime_cycle_run")
        detail = await mcp.strategy_manager(action="detail", kwargs=json.dumps({"strategy_id": sid}))

        assert capabilities["data"]["domain_events"] is True
        assert capabilities["data"]["vector_governance"] is True
        assert capabilities["data"]["runtime_cycle"] is True
        assert domain_events["data"]["count"] == 1
        assert reconcile["data"]["registry_updated"] == 1
        assert rebuild["data"]["built_profiles"] == 2
        assert runtime_status["data"]["last_result"]["risk_actions"] == 1
        assert runtime_run["data"]["vector_registry_updates"] == 1
        assert detail["data"]["domain_events"][0]["event_type"] == "incubation.metric_recorded"

    @pytest.mark.asyncio
    async def test_runtime_control_promotion_and_projection_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "晋级策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.2, 'max_drawdown': -0.12})
        db._signal_stats[sid] = {
            'total_signals': 18,
            'hit_rate': {1: 0.55, 5: 0.62, 10: 0.58, 20: 0.56},
            'forward_ic': {1: 0.01, 5: 0.03, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.12, 5: 0.8, 10: 0.5, 20: 0.3},
        }
        await db.save_strategy_incubation_account(sid, 'acct_promote', stage='candidate', status='active')
        await db.save_strategy_incubation_metric(sid, '2026-03-08', {
            'account_id': 'acct_promote',
            'stage': 'candidate',
            'decision': 'promote',
            'nav': 1.08,
            'sharpe_ratio': 1.2,
            'max_drawdown': 0.12,
            'hit_rate_5d': 0.62,
            'forward_sharpe_5d': 0.8,
            'total_signals': 18,
        })

        review = await mcp.strategy_manager(action='promotion_review_run', kwargs=json.dumps({'strategy_id': sid, 'auto_apply': True}))
        control = await mcp.strategy_manager(action='runtime_control_set', kwargs=json.dumps({'strategy_id': sid, 'control_mode': 'manual_stop', 'reason': 'operator_halt'}))
        projection = await mcp.strategy_manager(action='domain_projection', kwargs=json.dumps({'strategy_id': sid}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert review['success'] is True
        assert review['data']['review']['status'] == 'approved'
        assert review['data']['applied_transition']['to'] == 'listed'
        assert control['data']['control_mode'] == 'manual_stop'
        assert projection['data']['runtime_control_mode'] == 'manual_stop'
        assert projection['data']['latest_promotion_status'] == 'approved'
        assert detail['data']['runtime_control']['control_mode'] == 'manual_stop'
        assert detail['data']['latest_promotion_review']['status'] == 'approved'
        assert capabilities['data']['runtime_controls'] is True
        assert capabilities['data']['promotion_pipeline'] is True
        assert capabilities['data']['domain_projection'] is True

    @pytest.mark.asyncio
    async def test_domain_projection_rebuild_snapshot_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "投影策略", "strategy_type": "momentum", "params": {"lookback": 10},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_domain_event({
            'strategy_id': sid,
            'aggregate_type': 'strategy',
            'aggregate_id': sid,
            'event_type': 'custom.domain_marker',
            'source': 'test',
            'payload': {'step': 'marker'},
        })

        rebuilt = await mcp.strategy_manager(action='domain_projection_rebuild', kwargs=json.dumps({'strategy_id': sid}))
        snapshot = await mcp.strategy_manager(action='domain_projection_snapshot', kwargs=json.dumps({'strategy_id': sid}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))

        assert rebuilt['success'] is True
        assert rebuilt['data']['snapshot']['strategy_id'] == sid
        assert snapshot['data']['latest']['strategy_id'] == sid
        assert snapshot['data']['count'] >= 1
        assert detail['data']['latest_projection_snapshot']['strategy_id'] == sid
