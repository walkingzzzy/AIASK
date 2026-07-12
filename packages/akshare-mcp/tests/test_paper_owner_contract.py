from __future__ import annotations

import pytest

from akshare_mcp.services.incubation_factory.runner import IncubationFactoryRunner


def test_incubation_owner_contract_enables_the_single_paper_owner(monkeypatch) -> None:
    monkeypatch.setenv("AIASK_FACTORY_PAPER_OWNER", "incubation_factory")
    monkeypatch.setenv("INCUBATION_FACTORY_OWNS_PAPER_TRADING", "true")

    runner = IncubationFactoryRunner(dry_run=False)

    assert runner.owns_paper_trading is True


def test_quality_owner_contract_disables_paper_runtime(monkeypatch) -> None:
    monkeypatch.setenv("AIASK_FACTORY_PAPER_OWNER", "disabled")
    monkeypatch.setenv("INCUBATION_FACTORY_OWNS_PAPER_TRADING", "0")

    runner = IncubationFactoryRunner(dry_run=False)

    assert runner.owns_paper_trading is False


def test_conflicting_paper_owner_contract_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("AIASK_FACTORY_PAPER_OWNER", "incubation_factory")
    monkeypatch.setenv("INCUBATION_FACTORY_OWNS_PAPER_TRADING", "0")

    with pytest.raises(ValueError, match="paper ownership conflict"):
        IncubationFactoryRunner(dry_run=False)
