from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

from akshare_mcp.services import research_510300_v3 as research_mod


def _load_renderer_module():
    renderer_path = Path(__file__).resolve().parents[3] / "scripts" / "render_510300_pdf_report.py"
    spec = importlib.util.spec_from_file_location("render_510300_pdf_report_test", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load renderer from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_summary(bundle_dir: Path) -> dict:
    return {
        "research_protocol": {
            "end_date": "2026-04-10",
            "baseline_slippage_bps": 5.0,
            "stress_slippage_bps": 10.0,
            "train_months": 60,
            "test_months": 12,
            "step_months": 12,
            "enable_cash_sleeves": True,
            "enable_enhancements": True,
            "baseline_reference": str(bundle_dir / "baseline.json"),
        },
        "instrument_resolution": {
            "resolved": {
                "risk_core": {
                    "code": "510300",
                    "name": "沪深300ETF华泰柏瑞",
                    "history_rows": 1000,
                    "first_trade_date": "2012-05-04",
                    "last_trade_date": "2026-04-10",
                    "median_amount_60d": 1000000.0,
                }
            }
        },
        "cost_scenarios": [
            {
                "scenario": "main",
                "slippage_bps": 5.0,
                "strategy_metrics": {
                    "scheme1": {"cagr": 0.08, "max_drawdown": 0.22},
                    "scheme2": {"cagr": 0.09, "max_drawdown": 0.18},
                    "optimized_regime": {"cagr": 0.10, "max_drawdown": 0.15},
                },
            }
        ],
        "oos_folds": [],
        "cash_sleeve_results": [],
        "enhancement_results": [],
        "selection_gate": [
            {
                "family": "family_b",
                "passed": True,
                "oos_cagr": 0.18,
                "benchmark_oos_cagr": 0.08,
                "oos_max_drawdown": 0.15,
                "benchmark_oos_max_drawdown": 0.22,
            }
        ],
        "final_recommendation": {
            "decision": "single_candidate",
            "selected_family": "family_b",
            "selected_candidate": {"candidate_id": "lb6_ma100"},
            "summary": "推荐 family_b 作为唯一通过门槛的候选。",
            "passed_gate": True,
        },
        "artifacts": {
            "bundle_dir": str(bundle_dir),
            "csv_inventory": ["main_scheme1_equity_curve.csv"],
        },
    }


def test_build_monthly_windows_aligns_month_boundaries():
    dates = pd.bdate_range("2020-01-02", "2022-12-30")
    windows = research_mod.build_monthly_windows(
        dates,
        train_months=12,
        test_months=6,
        step_months=6,
    )
    assert len(windows) == 4
    assert windows[0]["train_start"] == pd.Timestamp("2020-01-02")
    assert windows[0]["train_end"].month == 12
    assert windows[0]["test_start"].month == 1
    assert windows[0]["test_end"].month == 6
    assert windows[-1]["test_end"] == pd.Timestamp("2022-12-30")


def test_cash_sleeve_scheduler_preserves_pre_listing_idle_cash_and_rebuilds():
    cash_price_df = pd.DataFrame(
        [
            {"date": "2024-01-03", "open": 1.0, "close": 1.0},
            {"date": "2024-01-04", "open": 1.0, "close": 1.0},
        ]
    )
    cash_price_df["date"] = pd.to_datetime(cash_price_df["date"])
    result = research_mod.simulate_cash_sleeve_scheduler(
        cash_price_df=cash_price_df,
        funding_needs={pd.Timestamp("2024-01-03"): 120.0},
        idle_cash_by_date={
            pd.Timestamp("2024-01-01"): 80.0,
            pd.Timestamp("2024-01-02"): 80.0,
            pd.Timestamp("2024-01-03"): 80.0,
        },
    )
    assert result["pre_listing_idle_days"] == 2
    assert result["open_redemption_days"] == 0
    assert result["close_rebuild_days"] >= 1
    assert result["ending_shares"] >= 100


def test_resolve_etf_instrument_respects_locked_code(monkeypatch):
    universe = pd.DataFrame(
        [
            {"基金代码": "510300", "基金简称": "沪深300ETF华泰柏瑞", "基金类型": "指数型-股票"},
            {"基金代码": "160706", "基金简称": "嘉实沪深300ETF联接A", "基金类型": "指数型-股票"},
        ]
    )
    history_510300 = pd.DataFrame(
        [
            {"date": "2024-01-02", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1000, "amount": 1000},
            {"date": "2024-01-03", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1000, "amount": 1000},
            {"date": "2024-04-01", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1000, "amount": 1000},
            {"date": "2024-04-02", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1000, "amount": 1000},
        ]
    )
    history_510300 = pd.concat([history_510300] * 20, ignore_index=True)
    history_510300["date"] = pd.bdate_range("2024-01-02", periods=len(history_510300))
    history_160706 = history_510300.copy()
    history_160706["amount"] = 10_000_000

    monkeypatch.setattr(research_mod, "_load_fund_universe", lambda: universe)

    def fake_history(code: str, *, end_date: str):
        return history_510300.copy() if code == "510300" else history_160706.copy()

    monkeypatch.setattr(research_mod, "_fetch_etf_history", fake_history)
    monkeypatch.setattr(research_mod, "_fetch_etf_dividends", lambda code, *, end_date: pd.DataFrame())

    instrument, history, dividends = research_mod.resolve_etf_instrument(
        category="risk_core",
        keyword_group="hs300",
        keywords=["沪深300ETF"],
        code_hints=["510300", "160706"],
        end_date="2024-12-31",
        locked_code="510300",
    )

    assert instrument.code == "510300"
    assert instrument.name == "沪深300ETF华泰柏瑞"
    assert instrument.source == "locked_code+fund_etf_hist_sina"
    assert len(history) == len(history_510300)
    assert dividends.empty


def test_bundle_validation_and_promotion_copy_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(research_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(research_mod, "V3_REPORT_ROOT", tmp_path / "reports" / "backtests" / "510300_v3")
    monkeypatch.setattr(research_mod, "V3_RUNS_ROOT", research_mod.V3_REPORT_ROOT / "runs")

    bundle = research_mod.create_bundle_artifacts(timestamp="20260414T120000Z")
    summary = _minimal_summary(bundle.bundle_dir)
    markdown_text = "# demo\n\n推荐 family_b 作为唯一通过门槛的候选。\n"
    curve = pd.DataFrame(
        [
            {"date": "2024-01-02", "tw_nav": 1.0, "total_asset": 100000.0, "exposure": 0.0},
            {"date": "2024-01-03", "tw_nav": 1.02, "total_asset": 102000.0, "exposure": 0.8},
        ]
    )
    research_mod.write_bundle(
        bundle=bundle,
        summary=summary,
        markdown_text=markdown_text,
        csv_frames={"main_scheme1_equity_curve": curve},
    )
    pdf_path = bundle.bundle_dir / "formal_report_charted.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test\n")

    promotion = research_mod.finalize_bundle_outputs(bundle.bundle_dir, pdf_path)
    assert promotion["promotion_ready"] is True
    assert promotion["applied"] is True
    assert (research_mod.V3_REPORT_ROOT / "latest.json").exists()
    assert (tmp_path / research_mod.ROOT_REPORT_MD).exists()
    assert (tmp_path / research_mod.ROOT_REPORT_PDF).exists()

    refreshed = json.loads((bundle.bundle_dir / "summary.json").read_text(encoding="utf-8"))
    assert refreshed["promotion"]["promotion_ready"] is True


def test_renderer_uses_bundle_and_latest_pointer(tmp_path, monkeypatch):
    renderer = _load_renderer_module()
    bundle_dir = tmp_path / "reports" / "backtests" / "510300_v3" / "runs" / "20260414T120000Z"
    csv_dir = bundle_dir / "csv"
    csv_dir.mkdir(parents=True)
    summary = _minimal_summary(bundle_dir)
    (bundle_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (bundle_dir / "formal_report.md").write_text("# demo\n\n推荐 family_b 作为唯一通过门槛的候选。\n", encoding="utf-8")
    pd.DataFrame(
        [
            {"date": "2024-01-02", "tw_nav": 1.0, "total_asset": 100000.0, "exposure": 0.0},
            {"date": "2024-01-03", "tw_nav": 1.01, "total_asset": 101000.0, "exposure": 0.6},
        ]
    ).to_csv(csv_dir / "main_scheme1_equity_curve.csv", index=False)
    latest_root = tmp_path / "reports" / "backtests" / "510300_v3"
    latest_root.mkdir(parents=True, exist_ok=True)
    (latest_root / "latest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(renderer, "V3_REPORT_ROOT", latest_root)

    resolved_bundle = renderer.resolve_bundle_dir()
    assert resolved_bundle == bundle_dir.resolve()
    output = renderer.render_pdf_report(bundle_dir=resolved_bundle)
    assert output.exists()
    assert output.stat().st_size > 0
