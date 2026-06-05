from __future__ import annotations

from pathlib import Path

import pytest

from strategy_factory.application.candidate_contract import apply_resolved_candidate_envelope
from strategy_factory.application.trade_prediction_contract import (
    DERIVED_FROM_LEGACY_CONTRACT,
    TRADE_PREDICTION_CONTRACT_READY,
    TRADE_PREDICTION_CONTRACT_REJECTED,
    TRADE_PREDICTION_CONTRACT_VERSION,
    freeze_trade_prediction_contract,
)


def _explicit_contract() -> dict:
    return {
        "strategy_id": "strategy-1",
        "stock_code": "600000",
        "prediction_as_of": "2026-06-05T09:30:00+08:00",
        "target_trading_date": "2026-06-08",
        "direction": "up",
        "confidence": 0.71,
        "horizon": "next_day",
        "evidence_refs": ["ev-1", {"id": "ev-2", "source": "headline"}],
    }


def test_freeze_trade_prediction_contract_has_stable_hash() -> None:
    first = freeze_trade_prediction_contract(_explicit_contract())
    second = freeze_trade_prediction_contract({**_explicit_contract(), "contract_version": TRADE_PREDICTION_CONTRACT_VERSION})

    assert first["status"] == TRADE_PREDICTION_CONTRACT_READY
    assert first["contract_hash"]
    assert first["contract_hash"] == second["contract_hash"]
    assert first["contract"]["contract_version"] == TRADE_PREDICTION_CONTRACT_VERSION
    assert first["contract"]["stock_code"] == "600000.SH"


@pytest.mark.parametrize(
    ("field_name", "reason"),
    [
        ("stock_code", "missing:stock_code"),
        ("target_trading_date", "missing:target_trading_date"),
        ("evidence_refs", "missing:evidence_refs"),
    ],
)
def test_trade_prediction_contract_rejects_missing_required_fields(field_name: str, reason: str) -> None:
    payload = _explicit_contract()
    payload.pop(field_name)

    frozen = freeze_trade_prediction_contract(payload)

    assert frozen["status"] == TRADE_PREDICTION_CONTRACT_REJECTED
    assert frozen["contract_hash"] is None
    assert reason in frozen["reject_reasons"]


def test_trade_prediction_contract_rejects_invalid_direction_and_confidence() -> None:
    frozen = freeze_trade_prediction_contract(
        {
            **_explicit_contract(),
            "direction": "moon",
            "confidence": 1.5,
        }
    )

    assert frozen["status"] == TRADE_PREDICTION_CONTRACT_REJECTED
    assert "invalid:direction" in frozen["reject_reasons"]
    assert "invalid:confidence" in frozen["reject_reasons"]


def test_trade_prediction_contract_can_be_derived_from_legacy_candidate() -> None:
    candidate = {
        "id": "legacy-strategy",
        "strategy_id": "legacy-strategy",
        "params": {
            "target_symbols": ["000001"],
            "as_of_date": "2026-06-05",
            "prediction_contract": {
                "claims": [
                    {
                        "id": "claim-1",
                        "direction": "bullish",
                        "confidence": 0.64,
                        "target_trading_date": "2026-06-08",
                        "horizon": "next_day",
                        "evidence_ids": ["ev-1"],
                    }
                ]
            },
            "evidence_chain": {"evidences": [{"id": "ev-1", "source": "test"}]},
        },
    }

    frozen = freeze_trade_prediction_contract(candidate)

    assert frozen["status"] == TRADE_PREDICTION_CONTRACT_READY
    assert frozen["contract"]["contract_source"] == DERIVED_FROM_LEGACY_CONTRACT
    assert frozen["contract"]["stock_code"] == "000001.SZ"
    assert frozen["contract"]["direction"] == "up"


def test_apply_resolved_candidate_envelope_attaches_trade_prediction_fields() -> None:
    from strategy_factory.application.candidate_contract import build_logic_signature

    candidate = {
        "id": "candidate-1",
        "name": "candidate",
        "strategy_type": "momentum",
        "params": {
            "trade_prediction_contract": _explicit_contract(),
            "evidence_chain": {"evidences": [{"id": "ev-1"}]},
            "prediction_contract": {"claims": [{"id": "claim-1", "evidence_ids": ["ev-1"]}]},
            "confidence_contract": {"probability": 0.71},
        },
    }
    before_signature = build_logic_signature(candidate)

    resolved = apply_resolved_candidate_envelope(candidate)

    assert resolved["trade_prediction_contract_status"] == TRADE_PREDICTION_CONTRACT_READY
    assert resolved["trade_prediction_contract_hash"]
    assert resolved["params"]["trade_prediction_contract_hash"] == resolved["trade_prediction_contract_hash"]
    assert build_logic_signature(resolved) == before_signature


def test_submission_runtime_context_hard_fails_missing_trade_prediction_contract() -> None:
    from strategy_factory.application.submission_gate import runner

    context = runner._resolve_semantic_runtime_context(
        {
            "id": "candidate-without-trade-prediction",
            "strategy_type": "custom_rule",
            "params": {
                "evidence_chain": {"evidences": [{"evidence_id": "ev-1"}]},
                "prediction_contract": {"claims": [{"claim_id": "claim-1", "evidence_ids": ["ev-1"]}]},
                "confidence_contract": {"probability": 0.61},
            },
        }
    )

    assert context["trade_prediction_contract_status"] == "missing"
    assert "trade_prediction_contract_not_ready" in context["hard_fail_reasons"]


@pytest.mark.asyncio
async def test_submission_quality_gate_hard_rejects_missing_trade_prediction_contract(monkeypatch) -> None:
    from strategy_factory.application.submission_gate import runner

    async def _passing_statistical_gate(*_args, **_kwargs) -> dict:
        return {
            "passed": True,
            "passed_strict": True,
            "profile": "factor_rank_validation",
            "validation_focus": "target_plus_representative",
            "reasons": [],
        }

    monkeypatch.setattr(runner, "get_strategy_registry", lambda: {"custom_rule": object})
    monkeypatch.setattr(runner, "_run_statistical_gate", _passing_statistical_gate)
    monkeypatch.setattr(
        runner,
        "_resolve_validation_profile",
        lambda _strategy: {"profile": "factor_rank_validation", "validation_focus": "target_plus_representative"},
    )
    monkeypatch.setattr(runner, "_build_multiple_testing_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "_inject_run_correction_metrics", lambda *_args, **_kwargs: {})

    result = await runner.run_submission_quality_gate(
        None,
        {
            "id": "candidate-without-ready-trade-prediction",
            "strategy_type": "custom_rule",
            "params": {
                "evidence_chain": {"evidences": [{"evidence_id": "ev-1"}]},
                "prediction_contract": {"claims": [{"claim_id": "claim-1", "evidence_ids": ["ev-1"]}]},
                "confidence_contract": {"probability": 0.61},
            },
        },
    )

    assert result["passed"] is False
    assert result["passed_strict"] is False
    assert result["provisional_pass"] is False
    assert "trade_prediction_contract_not_ready" in result["reasons"]
    assert "trade_prediction_contract_not_ready" in result["hard_fail_reasons"]


def test_submitter_build_strategy_data_refreezes_contract_with_final_strategy_id() -> None:
    from strategy_factory.application.submitter import StrategySubmitter

    candidate = {
        "id": "candidate-temp-id",
        "name": "trade prediction candidate",
        "strategy_type": "momentum",
        "target_symbols": ["600000"],
        "params": {
            "trade_prediction_contract": _explicit_contract(),
            "evidence_chain": {"evidences": [{"evidence_id": "ev-1"}]},
            "prediction_contract": {"claims": [{"claim_id": "claim-1", "evidence_ids": ["ev-1"]}]},
            "confidence_contract": {"probability": 0.71},
        },
    }

    data = StrategySubmitter._build_strategy_data(
        "strategy-final-id",
        "trade prediction candidate",
        candidate,
        metrics={},
    )

    contract = data["params"]["trade_prediction_contract"]
    assert data["params"]["trade_prediction_contract_status"] == TRADE_PREDICTION_CONTRACT_READY
    assert data["params"]["trade_prediction_contract_hash"]
    assert contract["strategy_id"] == "strategy-final-id"
    assert contract["contract_hash"] == data["params"]["trade_prediction_contract_hash"]


def test_llm_prompt_requires_trade_prediction_contract() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    prompt_source = (
        repo_root
        / "packages"
        / "akshare-mcp"
        / "src"
        / "akshare_mcp"
        / "services"
        / "_strategy_llm_provider_prompt.py"
    ).read_text(encoding="utf-8")

    assert "trade_prediction_contract" in prompt_source
    assert prompt_source.count("trade_prediction_contract_required_fields") >= 2
    for field_name in (
        "stock_code",
        "prediction_as_of",
        "target_trading_date",
        "direction",
        "confidence",
        "horizon",
        "evidence_refs",
    ):
        assert field_name in prompt_source
    assert "direction must be up|down|neutral" in prompt_source
