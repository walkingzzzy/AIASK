from __future__ import annotations

import asyncio


class _UniverseDb:
    def __init__(self):
        self.rows = [
            {
                "code": "600519",
                "name": "Kweichow Moutai",
                "industry": "consumer",
                "market_cap": 2_000_000_000_000,
                "pe_ratio": 25,
                "pb_ratio": 8,
            },
            {
                "code": "000001",
                "name": "Ping An Bank",
                "industry": "bank",
                "market_cap": 300_000_000_000,
                "pe_ratio": 6,
                "pb_ratio": 0.8,
            },
            {
                "code": "300750",
                "name": "CATL",
                "industry": "new energy",
                "market_cap": 900_000_000_000,
                "pe_ratio": 30,
                "pb_ratio": 5,
            },
        ]

    def list_stock_universe(self, *, limit: int, offset: int = 0):
        return self.rows[offset : offset + limit]


def _targeted_snapshot() -> dict:
    return {
        "date": "2026-05-19",
        "candidate_codes": ["600519", "000001"],
        "fear_greed_index": 55,
        "fg_level": "neutral",
        "hot_sectors": ["consumer"],
        "cold_sectors": [],
        "factor_ic_trend": {},
        "factor_research": {},
    }


def _task_codes(report: dict) -> set[str]:
    codes: set[str] = set()
    for task in list(report.get("tasks") or []):
        codes.update(str(code) for code in list(task.get("target_symbols") or []) if str(code))
    return codes


def test_opportunity_scanner_respects_explicit_candidate_codes():
    from strategy_factory.application.opportunity import MarketOpportunityScanner

    report = asyncio.run(MarketOpportunityScanner().scan(_UniverseDb(), _targeted_snapshot()))

    summary = dict(report.get("summary") or {})
    assert summary["target_code_filter_applied"] is True
    assert summary["requested_target_codes"] == ["600519", "000001"]
    assert summary["universe_row_count"] == 2
    assert _task_codes(report) <= {"600519", "000001"}


def test_stock_strategy_matrix_respects_explicit_candidate_codes(monkeypatch):
    import strategy_factory.application.stock_strategy_matrix as matrix_module

    monkeypatch.setattr(matrix_module, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_module, "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT", 10)
    monkeypatch.setattr(matrix_module, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 20)
    monkeypatch.setattr(matrix_module, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 20)
    monkeypatch.setattr(matrix_module, "STRATEGY_FACTORY_VECTOR_REUSE_ENABLED", False)
    monkeypatch.setattr(matrix_module, "STRATEGY_FACTORY_VECTOR_SIMILAR_PROFILE_ENABLED", False)

    report = asyncio.run(
        matrix_module.StockStrategyMatrixPlanner().plan(_UniverseDb(), _targeted_snapshot())
    )

    summary = dict(report.get("summary") or {})
    assert summary["target_code_filter_applied"] is True
    assert summary["requested_target_codes"] == ["600519", "000001"]
    assert summary["loaded_stock_count"] == 2
    assert _task_codes(report) <= {"600519", "000001"}
