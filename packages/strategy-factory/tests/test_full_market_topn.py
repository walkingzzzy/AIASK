from __future__ import annotations

from collections import Counter

from strategy_factory.application.factory_market_views import (
    build_full_market_topn_payload,
    build_portfolio_candidate_from_topn,
    build_research_window_status,
)
from strategy_factory.application.stock_strategy_matrix import StockStrategyMatrixPlanner


def test_build_research_window_status_normalizes_bulk_window_fields():
    payload = {
        "planned_bulk_task_count": 20,
        "bulk_stock_matrix_loaded_stock_count": 5505,
        "bulk_stock_matrix_eligible_stock_count": 5167,
        "bulk_stock_matrix_planned_task_count": 11704,
        "bulk_stock_task_count": 20,
        "bulk_stock_matrix_effective_task_budget": 20,
        "bulk_stock_matrix_requested_task_offset": 0,
        "bulk_stock_matrix_effective_task_offset": 0,
        "bulk_stock_matrix_next_task_offset": 20,
        "bulk_stock_matrix_batch_count": 586,
        "bulk_stock_matrix_selected_batch_count": 1,
        "bulk_stock_matrix_shard_count": 147,
        "bulk_stock_matrix_selected_shard_ids": [1, 2],
        "bulk_stock_matrix_stock_coverage_ratio": 0.9386,
    }

    result = build_research_window_status(payload)

    assert result["available"] is True
    assert result["loaded_stock_count"] == 5505
    assert result["eligible_stock_count"] == 5167
    assert result["planned_bulk_task_count"] == 11704
    assert result["selected_bulk_task_count"] == 20
    assert result["next_task_offset"] == 20
    assert result["selected_shard_ids"] == [1, 2]


def test_build_full_market_topn_payload_enforces_industry_cap():
    score_rows = []
    for idx in range(40):
        score_rows.append(
            {
                "rank": idx + 1,
                "code": f"{600000 + idx}",
                "name": f"股票{idx + 1}",
                "industry": f"行业{idx % 12}",
                "market_cap": 10_000_000_000 + idx,
                "composite_score": round(100 - idx * 0.5, 4),
                "component_scores": {
                    "size_score": round(12 - idx * 0.05, 4),
                    "valuation_score": round((idx % 5) * 0.7, 4),
                    "sector_regime_score": 0.0,
                    "factor_alignment_score": round((idx % 4) * 0.5, 4),
                    "allocation_score": round(((idx % 3) - 1) * 0.4, 4),
                },
                "family_candidates": ["momentum", "value_factor"],
                "eligible": True,
            }
        )

    payload = build_full_market_topn_payload(
        as_of_date="2026-04-22",
        universe_count=5505,
        eligible_count=5167,
        score_rows=score_rows,
        score_contract_version="strategy_factory.full_market_topn.v2",
        active_factors=["value", "quality"],
        hot_sectors=["行业1"],
        cold_sectors=["行业2"],
        stock_family_allocation_source_mode="factor_research_stock_family_allocation",
        stock_family_allocation_avg_priority=0.61,
    )

    constituents = payload["constituents"]
    industry_counts = Counter(item["industry"] for item in constituents)

    assert payload["available"] is True
    assert payload["score_row_count"] == 40
    assert len(constituents) == 20
    assert all(count <= 2 for count in industry_counts.values())
    assert payload["selection_rules"]["max_per_industry"] == 2
    assert payload["score_contract_version"] == "strategy_factory.full_market_topn.v2"
    assert payload["score_quality"] == "healthy"
    assert payload["tie_cluster_summary"]["top10_distinct_score_count"] >= 3
    assert payload["component_activation_summary"]["size_score"] > 0.9
    assert payload["constituents"][0]["selection_rank"] == 1


def test_build_portfolio_candidate_from_topn_creates_multi_stock_candidate():
    topn_payload = build_full_market_topn_payload(
        as_of_date="2026-04-22",
        universe_count=100,
        eligible_count=90,
        score_rows=[
            {
                "rank": index + 1,
                "code": f"{688000 + index}",
                "name": f"组合股{index + 1}",
                "industry": f"行业{index % 10}",
                "market_cap": 1_000_000_000 + index,
                "composite_score": 99 - index,
                "component_scores": {
                    "size_score": 8.0,
                    "valuation_score": 4.0,
                    "sector_regime_score": 0.0,
                    "factor_alignment_score": 2.0,
                    "allocation_score": 0.5,
                },
                "family_candidates": ["quality_factor"],
                "eligible": True,
            }
            for index in range(20)
        ],
        score_contract_version="strategy_factory.full_market_topn.v2",
        active_factors=["quality"],
    )
    topn_payload["snapshot_id"] = "fmt_factory_run_1"
    topn_payload["portfolio_candidate_id"] = "factory_topn_factory_run_1"

    strategy = build_portfolio_candidate_from_topn(
        topn_payload,
        run_id="factory_run_1",
        trace_id="trace-1",
    )

    weights = dict(strategy["params"]["target_weights"] or {})

    assert strategy["strategy_type"] == "topn_equity_portfolio"
    assert len(strategy["params"]["target_symbols"]) == 20
    assert abs(sum(weights.values()) - 1.0) < 1e-8
    assert strategy["params"]["validation_focus"] == "target_plus_representative"
    assert strategy["params"]["validation_profile"]["primary_validation_layer"] == "combined"
    assert strategy["params"]["metadata"]["selection_source"] == "full_market_topn"
    assert strategy["params"]["metadata"]["score_contract_version"] == "strategy_factory.full_market_topn.v2"
    assert "selection_diagnostics_summary" in strategy["params"]["metadata"]


def test_build_full_market_topn_payload_marks_degraded_when_scores_do_not_separate():
    score_rows = [
        {
            "rank": idx + 1,
            "code": f"{601000 + idx}",
            "name": f"同分股{idx + 1}",
            "industry": "银行" if idx < 10 else "石油石化",
            "market_cap": 10_000_000_000_000 - idx,
            "composite_score": 57.5015,
            "component_scores": {
                "size_score": 12.0,
                "valuation_score": 0.0,
                "sector_regime_score": 0.0,
                "factor_alignment_score": 0.0,
                "allocation_score": 0.0,
            },
            "family_candidates": ["quality_factor"],
            "eligible": True,
        }
        for idx in range(20)
    ]

    payload = build_full_market_topn_payload(
        as_of_date="2026-04-22",
        universe_count=5505,
        eligible_count=5167,
        score_rows=score_rows,
        score_contract_version="strategy_factory.full_market_topn.v2",
        active_factors=[],
        hot_sectors=[],
        cold_sectors=[],
    )

    assert payload["score_quality"] == "degraded"
    assert "low_top10_score_separation" in payload["degraded_reasons"]
    assert payload["tie_cluster_summary"]["largest_tie_size"] == 20
    assert payload["metadata"]["score_quality"] == "degraded"


def test_v2_priority_components_separate_large_cap_bank_names_by_valuation():
    rows = [
        {"code": "601398", "name": "工商银行", "industry": "银行", "market_cap": 2.3e12, "pe_ratio": 5.2, "pb_ratio": 0.62},
        {"code": "601939", "name": "建设银行", "industry": "银行", "market_cap": 2.1e12, "pe_ratio": 5.6, "pb_ratio": 0.67},
        {"code": "601288", "name": "农业银行", "industry": "银行", "market_cap": 1.8e12, "pe_ratio": 6.1, "pb_ratio": 0.72},
        {"code": "601988", "name": "中国银行", "industry": "银行", "market_cap": 1.6e12, "pe_ratio": 6.6, "pb_ratio": 0.78},
        {"code": "600036", "name": "招商银行", "industry": "银行", "market_cap": 1.1e12, "pe_ratio": 7.4, "pb_ratio": 0.95},
        {"code": "601857", "name": "中国石油", "industry": "石油石化", "market_cap": 1.5e12, "pe_ratio": 8.3, "pb_ratio": 1.08},
        {"code": "600941", "name": "中国移动", "industry": "通信", "market_cap": 1.8e12, "pe_ratio": 15.2, "pb_ratio": 1.36},
    ]
    active_factors = ["short_term_reversal", "quality"]
    hot_sectors = {"银行"}
    cold_sectors = set()
    planner = StockStrategyMatrixPlanner()
    scoring_context = planner._build_priority_scoring_context(
        rows,
        snapshot={"date": "2026-04-22"},
        hot_sectors=hot_sectors,
        cold_sectors=cold_sectors,
        active_factors=active_factors,
        stock_family_allocation={},
    )

    scored = []
    for row in rows:
        components = planner._row_priority_components(
            row,
            snapshot={"date": "2026-04-22"},
            hot_sectors=hot_sectors,
            cold_sectors=cold_sectors,
            active_factors=active_factors,
            allocation_item=None,
            scoring_context=scoring_context,
        )
        scored.append(
            {
                "code": row["code"],
                "components": components,
                "composite": round(sum(components.values()), 4),
            }
        )

    bank_scores = {item["code"]: item for item in scored if item["code"].startswith("60")}
    distinct_scores = {item["composite"] for item in scored}

    assert len(distinct_scores) >= 3
    assert bank_scores["601398"]["components"]["valuation_score"] > bank_scores["601939"]["components"]["valuation_score"]
    assert bank_scores["601939"]["components"]["valuation_score"] > bank_scores["601288"]["components"]["valuation_score"]
    assert bank_scores["601288"]["components"]["valuation_score"] > bank_scores["601988"]["components"]["valuation_score"]
    assert bank_scores["601398"]["components"]["factor_alignment_score"] < 8.0


def test_priority_components_use_midrank_percentiles_for_duplicate_allocation_clusters():
    planner = StockStrategyMatrixPlanner()
    scoring_context = {
        "allocation_priorities": [0.2, 0.5, 0.9, 0.9, 0.9],
        "normalized_active_factors": ["momentum"],
        "preferred_families": ["momentum", "ma_cross"],
        "size_logs": [1.0, 2.0, 3.0],
        "hot_sectors": set(),
        "cold_sectors": set(),
    }

    components = planner._row_priority_components(
        {"code": "600000", "name": "测试股", "industry": "银行", "market_cap": 1_000_000_000},
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=["momentum"],
        allocation_item={"priority": 0.9},
        scoring_context=scoring_context,
    )

    assert components["allocation_score"] < 4.0


def test_factor_alignment_uses_intrinsic_families_instead_of_allocation_override():
    planner = StockStrategyMatrixPlanner()
    active_factors = ["momentum", "short_term_reversal"]
    scoring_context = planner._build_priority_scoring_context(
        [
            {"code": "000001", "name": "低估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 5.0, "pb_ratio": 0.6},
            {"code": "000002", "name": "高估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 50.0, "pb_ratio": 5.0},
        ],
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=active_factors,
        stock_family_allocation={},
    )
    same_allocation = {
        "priority": 0.8,
        "families": ["momentum", "ma_cross", "mean_reversion_short"],
    }

    low_value_components = planner._row_priority_components(
        {"code": "000001", "name": "低估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 5.0, "pb_ratio": 0.6},
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=active_factors,
        allocation_item=same_allocation,
        scoring_context=scoring_context,
    )
    high_value_components = planner._row_priority_components(
        {"code": "000002", "name": "高估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 50.0, "pb_ratio": 5.0},
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=active_factors,
        allocation_item=same_allocation,
        scoring_context=scoring_context,
    )
    low_value_no_allocation = planner._row_priority_components(
        {"code": "000001", "name": "低估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 5.0, "pb_ratio": 0.6},
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=active_factors,
        allocation_item=None,
        scoring_context=scoring_context,
    )
    low_value_families = planner._families_for_row(
        {"code": "000001", "name": "低估值股", "industry": "银行", "market_cap": 2_000_000_000, "pe_ratio": 5.0, "pb_ratio": 0.6},
        snapshot={"date": "2026-04-22"},
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=active_factors,
        allocation_item=None,
    )

    assert low_value_components["factor_alignment_score"] == low_value_no_allocation["factor_alignment_score"]
    assert low_value_families[0] in {"value_factor", "mean_reversion_short"}


def test_sector_regime_matches_canonical_taxonomy_instead_of_raw_string_equality():
    planner = StockStrategyMatrixPlanner()
    rows = [
        {"code": "601398", "name": "工商银行", "industry": "银行", "market_cap": 2.3e12, "pe_ratio": 5.2, "pb_ratio": 0.62},
        {"code": "603993", "name": "洛阳钼业", "industry": "铜", "market_cap": 1.2e11, "pe_ratio": 12.4, "pb_ratio": 1.46},
        {"code": "688981", "name": "中芯国际", "industry": "半导体", "market_cap": 2.1e11, "pe_ratio": 51.0, "pb_ratio": 3.9},
    ]
    hot_sectors = {"高股息金融"}
    cold_sectors = {"上游油气"}
    scoring_context = planner._build_priority_scoring_context(
        rows,
        snapshot={"date": "2026-04-22"},
        hot_sectors=hot_sectors,
        cold_sectors=cold_sectors,
        active_factors=[],
        stock_family_allocation={},
    )

    bank_components = planner._row_priority_components(
        rows[0],
        snapshot={"date": "2026-04-22"},
        hot_sectors=hot_sectors,
        cold_sectors=cold_sectors,
        active_factors=[],
        allocation_item=None,
        scoring_context=scoring_context,
    )
    copper_components = planner._row_priority_components(
        rows[1],
        snapshot={"date": "2026-04-22"},
        hot_sectors=hot_sectors,
        cold_sectors=cold_sectors,
        active_factors=[],
        allocation_item=None,
        scoring_context=scoring_context,
    )
    chip_components = planner._row_priority_components(
        rows[2],
        snapshot={"date": "2026-04-22"},
        hot_sectors=hot_sectors,
        cold_sectors=cold_sectors,
        active_factors=[],
        allocation_item=None,
        scoring_context=scoring_context,
    )

    assert bank_components["sector_regime_score"] > 0.0
    assert copper_components["sector_regime_score"] < 0.0
    assert chip_components["sector_regime_score"] == 0.0


def test_sector_regime_penalizes_broad_parent_theme_more_than_direct_industry_label():
    planner = StockStrategyMatrixPlanner()
    rows = [
        {"code": "600015", "name": "银行股", "industry": "银行", "market_cap": 1.1e11, "pe_ratio": 5.2, "pb_ratio": 0.62},
        {"code": "601318", "name": "保险股", "industry": "保险", "market_cap": 1.8e11, "pe_ratio": 9.1, "pb_ratio": 1.02},
        {"code": "600050", "name": "运营商", "industry": "电信运营", "market_cap": 2.1e11, "pe_ratio": 14.0, "pb_ratio": 1.31},
        {"code": "000063", "name": "通信设备", "industry": "通信设备", "market_cap": 1.2e11, "pe_ratio": 21.0, "pb_ratio": 2.2},
    ]
    broad_context = planner._build_priority_scoring_context(
        rows,
        snapshot={"date": "2026-04-22"},
        hot_sectors={"高股息金融"},
        cold_sectors=set(),
        active_factors=[],
        stock_family_allocation={},
    )
    direct_context = planner._build_priority_scoring_context(
        rows,
        snapshot={"date": "2026-04-22"},
        hot_sectors={"银行"},
        cold_sectors=set(),
        active_factors=[],
        stock_family_allocation={},
    )

    broad_components = planner._row_priority_components(
        rows[0],
        snapshot={"date": "2026-04-22"},
        hot_sectors={"高股息金融"},
        cold_sectors=set(),
        active_factors=[],
        allocation_item=None,
        scoring_context=broad_context,
    )
    direct_components = planner._row_priority_components(
        rows[0],
        snapshot={"date": "2026-04-22"},
        hot_sectors={"银行"},
        cold_sectors=set(),
        active_factors=[],
        allocation_item=None,
        scoring_context=direct_context,
    )

    assert broad_components["sector_regime_score"] > 0.0
    assert direct_components["sector_regime_score"] > broad_components["sector_regime_score"]


def test_projection_allocation_keeps_sector_specific_family_anchor():
    planner = StockStrategyMatrixPlanner()
    same_allocation = {
        "priority": 0.82,
        "source_mode": "stock_universe_projection",
        "families": ["momentum", "ma_cross", "mean_reversion_short"],
    }
    snapshot = {"date": "2026-04-22", "fear_greed_index": 62}

    chip_families = planner._families_for_row(
        {"code": "688981", "name": "中芯国际", "industry": "半导体", "market_cap": 2.1e11, "pe_ratio": 51.0, "pb_ratio": 3.9},
        snapshot=snapshot,
        hot_sectors={"芯片半导体"},
        cold_sectors=set(),
        active_factors=["momentum", "short_term_reversal"],
        allocation_item=same_allocation,
    )
    bank_families = planner._families_for_row(
        {"code": "601398", "name": "工商银行", "industry": "银行", "market_cap": 2.3e12, "pe_ratio": 5.2, "pb_ratio": 0.62},
        snapshot=snapshot,
        hot_sectors={"高股息金融"},
        cold_sectors=set(),
        active_factors=["momentum", "short_term_reversal"],
        allocation_item=same_allocation,
    )
    resource_families = planner._families_for_row(
        {"code": "603993", "name": "洛阳钼业", "industry": "铜", "market_cap": 1.2e11, "pe_ratio": 12.4, "pb_ratio": 1.46},
        snapshot=snapshot,
        hot_sectors=set(),
        cold_sectors={"上游油气"},
        active_factors=["momentum", "short_term_reversal"],
        allocation_item=same_allocation,
    )

    assert chip_families != bank_families
    assert bank_families != resource_families
    assert chip_families[0] in {"growth_factor", "volatility_breakout", "momentum"}
    assert bank_families[0] in {"quality_factor", "value_factor", "ma_cross"}
    assert resource_families[0] in {"sector_rotation", "momentum", "value_factor"}


def test_technology_subclusters_do_not_share_the_same_family_trio():
    planner = StockStrategyMatrixPlanner()
    same_allocation = {
        "priority": 0.84,
        "source_mode": "stock_universe_projection",
        "families": ["momentum", "ma_cross", "growth_factor"],
    }
    snapshot = {"date": "2026-04-22", "fear_greed_index": 64}

    comm_families = planner._families_for_row(
        {"code": "000063", "name": "中兴通讯", "industry": "通信设备", "market_cap": 1.8e11, "pe_ratio": 19.0, "pb_ratio": 2.1},
        snapshot=snapshot,
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=["momentum", "growth"],
        allocation_item=same_allocation,
    )
    internet_families = planner._families_for_row(
        {"code": "601360", "name": "三六零", "industry": "互联网", "market_cap": 1.2e11, "pe_ratio": 26.0, "pb_ratio": 2.8},
        snapshot=snapshot,
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=["momentum", "growth"],
        allocation_item=same_allocation,
    )
    software_families = planner._families_for_row(
        {"code": "000034", "name": "神州数码", "industry": "软件服务", "market_cap": 9.0e10, "pe_ratio": 31.0, "pb_ratio": 3.6},
        snapshot=snapshot,
        hot_sectors=set(),
        cold_sectors=set(),
        active_factors=["momentum", "growth"],
        allocation_item=same_allocation,
    )

    assert comm_families != internet_families
    assert internet_families != software_families
    assert comm_families[0] in {"momentum", "volatility_breakout", "growth_factor"}
    assert internet_families[0] in {"momentum", "ma_cross", "multi_factor"}
    assert software_families[0] in {"growth_factor", "quality_factor", "ma_cross"}
