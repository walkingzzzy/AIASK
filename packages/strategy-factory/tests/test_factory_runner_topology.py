from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_supervisor_keeps_four_runtime_topology_and_excludes_sidecar() -> None:
    text = (ROOT / "scripts" / "factories" / "run_three_factories.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert '"run_strategy_factory.py"' in text
    assert '"run_factor_mining_factory.py"' in text
    assert '"run_incubation_factory.py"' in text
    assert '"run_market_event_ingest.py"' in text
    assert '"run_signal_tracker.py"' not in text


def test_run_all_factories_remains_compat_wrapper_and_mentions_sidecar() -> None:
    text = (ROOT / "scripts" / "factories" / "run_all_factories.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "run_three_factories.py" in text
    assert "SignalTracker" in text
    assert "run_signal_tracker.py" in text
