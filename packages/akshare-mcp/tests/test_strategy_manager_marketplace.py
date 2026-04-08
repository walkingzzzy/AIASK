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
                            "status": "submitted",
                            "submission_lane": "paper",
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
                            "vector_profile_id": "vp_factory_1",
                            "multiple_testing_registry": {"available": True},
                            "multiple_testing_registry_record_id": "mt_factory_1",
                            "candidate_lineage_contract": {"lineage_id": "lineage_factory_1"},
                            "cost_assumptions": {"commission_bps": 8},
                            "explicit_cost_breakdown": {"commission_cost": 120.0},
                            "implicit_cost_breakdown": {"slippage_cost": 36.0},
                            "execution_reality": {"tradability_filter": True},
                        }
                    ],
                },
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
        assert runs_resp["data"]["items"][0]["summary"]["event_task_count"] == 1
        assert runs_resp["data"]["items"][0]["summary"]["event_snapshot_mixed"] is True
        assert detail_resp["data"]["run_id"] == "run_hist_1"
        assert detail_resp["data"]["summary"]["snapshot_task_count"] == 1
        assert detail_resp["data"]["summary"]["autonomy_task_briefs"][0]["task_source"] == "event_driven"
        assert detail_resp["data"]["research_summary"]["research_plane_contract_version"] == "strategy_factory.research_plane.v1"
        assert detail_resp["data"]["research_plane"]["contract_version"] == "strategy_factory.research_plane.v1"
        assert detail_resp["data"]["research_artifact"]["contract_version"] == "strategy_factory.research_artifact.v1"
        assert detail_resp["data"]["task_artifact"]["planned_task_count"] == 2
        assert detail_resp["data"]["candidate_artifact"]["candidate_count"] == 2
        assert detail_resp["data"]["evidence_artifact"]["experiment_count"] == 1
        assert detail_resp["data"]["governance_plane"]["contract_version"] == "strategy_factory.governance_plane.v1"
        assert detail_resp["data"]["gate_artifact"]["contract_version"] == "strategy_factory.gate_artifact.v1"
        assert detail_resp["data"]["gate_artifact"]["gate_3_passed"] == 1
        assert detail_resp["data"]["dedup_artifact"]["kept_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["strategy_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["committee_review_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["committee_decision_counts"]["revise"] == 1
        assert detail_resp["data"]["submission_artifact"]["constraint_check_count"] == 1
        assert detail_resp["data"]["submission_artifact"]["primary_validation_layer_counts"]["target"] == 1
        assert (
            detail_resp["data"]["submission_artifact"]["strategy_briefs"][0]["validation_profile"]["profile"]
            == "event_trade_validation"
        )
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
        assert snapshot_resp["data"]["completeness"]["completion_ratio"] == 0.67

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
