from strategy_factory.application.opportunity import MarketOpportunityScanner
import pytest


def _row(code: str, industry: str, market_cap: float, *, pe: float, pb: float) -> dict:
    return {
        "code": code,
        "name": f"name_{code}",
        "industry": industry,
        "sector": industry,
        "market_cap": market_cap,
        "pe_ratio": pe,
        "pb_ratio": pb,
    }


def test_build_snapshot_tasks_diversifies_targets_across_factor_and_regime_tasks():
    scanner = MarketOpportunityScanner()
    rows = [
        _row("601288", "高股息金融", 180_000_000_000, pe=6.0, pb=0.7),
        _row("601398", "高股息金融", 178_000_000_000, pe=6.2, pb=0.72),
        _row("601318", "高股息金融", 176_000_000_000, pe=7.0, pb=0.9),
        _row("600941", "高股息金融", 174_000_000_000, pe=7.8, pb=1.0),
        _row("601919", "高股息金融", 172_000_000_000, pe=7.6, pb=0.95),
        _row("600027", "高股息金融", 170_000_000_000, pe=7.2, pb=0.88),
        _row("601117", "高股息金融", 168_000_000_000, pe=7.4, pb=0.91),
        _row("601607", "高股息金融", 166_000_000_000, pe=7.1, pb=0.86),
        _row("000725", "电子", 110_000_000_000, pe=24.0, pb=2.8),
        _row("688036", "电子", 108_000_000_000, pe=23.0, pb=2.6),
        _row("600570", "电子", 106_000_000_000, pe=21.0, pb=2.4),
        _row("688188", "电子", 104_000_000_000, pe=22.0, pb=2.5),
        _row("688375", "电子", 102_000_000_000, pe=20.0, pb=2.2),
        _row("600879", "电子", 100_000_000_000, pe=19.5, pb=2.1),
        _row("601138", "电子", 98_000_000_000, pe=18.0, pb=2.0),
        _row("002475", "电子", 96_000_000_000, pe=17.0, pb=1.9),
        _row("601857", "上游油气", 88_000_000_000, pe=9.0, pb=1.1),
        _row("600938", "上游油气", 86_000_000_000, pe=8.5, pb=1.0),
        _row("600028", "上游油气", 84_000_000_000, pe=8.0, pb=0.95),
        _row("601808", "上游油气", 82_000_000_000, pe=7.8, pb=0.92),
        _row("600777", "上游油气", 80_000_000_000, pe=8.8, pb=1.02),
        _row("600888", "上游油气", 78_000_000_000, pe=9.2, pb=1.08),
        _row("600999", "上游油气", 76_000_000_000, pe=9.6, pb=1.12),
        _row("601000", "上游油气", 74_000_000_000, pe=9.9, pb=1.16),
    ]
    snapshot = {
        "date": "2026-04-03",
        "fear_greed_index": 45,
        "hot_sectors": ["高股息金融", "电子"],
        "cold_sectors": ["上游油气"],
        "factor_ic_trend": {"reversal": "rising", "volatility": "rising"},
    }

    tasks = scanner._build_snapshot_tasks(snapshot, rows)
    signatures = {
        task["task_id"]: tuple(task.get("target_symbols") or [])
        for task in tasks
        if task.get("task_id") in {
            "regime_2026-04-03_45",
            "factor_1_reversal",
            "factor_2_volatility",
            "cold_1_上游油气",
        }
    }

    assert len(signatures) == 4
    assert len(set(signatures.values())) >= 3
    assert signatures["regime_2026-04-03_45"] != signatures["factor_1_reversal"]


@pytest.mark.asyncio
async def test_market_opportunity_scanner_paginates_universe_before_selecting_tasks():
    scanner = MarketOpportunityScanner()
    rows = [
        _row(f"{idx:06d}", "银行", 1_000_000_000 + idx, pe=7.0, pb=0.8)
        for idx in range(1, 1001)
    ] + [
        _row(f"{200000 + idx:06d}", "电子", 200_000_000_000 + idx, pe=25.0, pb=2.5)
        for idx in range(1, 201)
    ]

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            return rows[offset : offset + limit]

    report = await scanner.scan(
        _DB(),
        {
            "date": "2026-04-03",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["电子"],
            "cold_sectors": ["银行"],
            "factor_ic_trend": {"growth": "rising"},
        },
    )

    assert report["summary"]["universe_pages_loaded"] == 2
    assert report["summary"]["universe_row_count"] == 1200
    assert any(
        str(code).startswith("200")
        for task in report["tasks"]
        for code in list(task.get("target_symbols") or [])
    )
