"""Tests for the unified decision summary/details vertical slice."""

from __future__ import annotations

import asyncio

import pytest


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def test_fuse_unified_decision_applies_veto():
    from akshare_mcp.services.decision_fusion import fuse_unified_decision

    result = fuse_unified_decision(
        stock_context={
            "recommendation": "buy",
            "score": 82.0,
            "highlights": ["估值偏低", "ROE 较高"],
            "risks": ["波动率上升"],
        },
        quant_context={"score": 70.0, "reasons": ["动量为正"], "risks": []},
        event_context={"score": 35.0, "reasons": [], "risks": ["监管风险"]},
        user_context={"risk_level": "moderate"},
        gate={
            "blocked": True,
            "veto_reason": "event_risk_veto",
            "flags": [{"name": "event_risk", "status": "blocked", "message": "事件风险"}],
            "position_cap_pct": 0.2,
            "requested_style": "balanced",
            "user_risk_level": "moderate",
            "gate_adjustment": -20.0,
        },
    )

    assert result["action"] == "watch"
    assert result["veto_reason"] == "event_risk_veto"
    assert result["position_signal"]["suggested_position_pct"] == 0.0
    assert result["summary"]


@pytest.mark.asyncio
async def test_unified_decision_summary_payload_contract(monkeypatch):
    from akshare_mcp.services import decision_contracts

    async def _fake_stock_context(code):
        return {
            "code": code,
            "name": "测试股份",
            "recommendation": "buy",
            "score": 78.0,
            "highlights": ["估值相对行业偏低", "盈利能力稳定"],
            "risks": ["短线波动仍在"],
            "warnings": [],
            "timestamp": "2026-03-19T10:00:00",
        }

    async def _fake_quant_context(code):
        return {
            "code": code,
            "score": 72.0,
            "reasons": ["20 日动量为正"],
            "risks": [],
            "warnings": [],
            "timestamp": "2026-03-19T10:00:01",
        }

    async def _fake_event_context(code):
        return {
            "code": code,
            "score": 55.0,
            "reasons": ["文本信号整体中性偏多"],
            "risks": ["需跟踪公告节奏"],
            "warnings": [],
            "timestamp": "2026-03-19T10:00:02",
        }

    async def _fake_user_context(user_id):
        return {
            "user_id": user_id,
            "risk_level": "moderate",
            "risk_bucket": "moderate",
            "warnings": [],
            "timestamp": "2026-03-19T10:00:03",
        }

    def _fake_gate(**kwargs):
        return {
            "blocked": False,
            "veto_reason": None,
            "flags": [{"name": "baseline", "status": "pass", "severity": "low", "blocking": False, "message": "ok"}],
            "gate_adjustment": -2.0,
            "position_cap_pct": 0.2,
            "requested_style": "balanced",
            "user_risk_level": "moderate",
        }

    def _fake_fusion(**kwargs):
        return {
            "action": "buy",
            "confidence": 0.74,
            "final_score": 71.5,
            "summary": "多维证据整体偏正面。",
            "reasons": ["估值相对行业偏低", "20 日动量为正"],
            "risks": ["需跟踪公告节奏"],
            "veto_reason": None,
            "position_signal": {
                "label": "小仓试探",
                "suggested_position_pct": 0.12,
                "position_cap_pct": 0.2,
                "requested_style": "balanced",
                "user_risk_level": "moderate",
            },
            "score_breakdown": {
                "stock_context": 78.0,
                "quant": 72.0,
                "event": 55.0,
                "gate_adjustment": -2.0,
            },
            "weights": {"stock_context": 0.55, "quant": 0.25, "event": 0.20},
        }

    monkeypatch.setattr(decision_contracts, "build_stock_context", _fake_stock_context)
    monkeypatch.setattr(decision_contracts, "build_quant_context", _fake_quant_context)
    monkeypatch.setattr(decision_contracts, "build_event_context", _fake_event_context)
    monkeypatch.setattr(decision_contracts, "build_user_context", _fake_user_context)
    monkeypatch.setattr(decision_contracts, "build_rule_gates", _fake_gate)
    monkeypatch.setattr(decision_contracts, "fuse_unified_decision", _fake_fusion)

    payload = await decision_contracts.get_unified_decision_summary_payload(
        code="600519",
        investment_style="balanced",
        user_id="u_demo",
    )

    assert payload["version"] == "unified-decision.v1"
    assert payload["scene"] == "unified_decision"
    assert payload["action"] == "buy"
    assert payload["details_available"] is True
    assert payload["position_signal"]["label"] == "小仓试探"
    assert payload["data_provenance"][0]["dataset"] == "investment_analysis+market_snapshot"
    assert "data_quality" in payload
    assert "updated_at" in payload


@pytest.mark.asyncio
async def test_decision_registers_unified_decision_tools(monkeypatch):
    from akshare_mcp.tools import decision

    async def _fake_summary_payload(**kwargs):
        return {
            "version": "unified-decision.v1",
            "scene": "unified_decision",
            "code": kwargs["code"],
            "name": "测试股份",
            "action": "buy",
            "confidence": 0.7,
            "final_score": 70.0,
            "summary": "多维证据整体偏正面。",
            "reasons": ["估值与动量同时支持"],
            "risks": ["仍需控制节奏"],
            "gate_flags": [],
            "veto_reason": None,
            "position_signal": {"label": "小仓试探", "suggested_position_pct": 0.1, "position_cap_pct": 0.2},
            "data_provenance": [],
            "compliance_notice": "仅供研究参考。",
            "details_available": True,
            "details_hint": {"tool": "get_unified_decision_details", "args": {"code": kwargs["code"]}},
            "diagnostics": {},
            "warnings": [],
        }

    async def _fake_details_payload(**kwargs):
        summary = await _fake_summary_payload(**kwargs)
        return {**summary, "details": {"requested": {"code": kwargs["code"]}}}

    monkeypatch.setattr(decision, "get_unified_decision_summary_payload", _fake_summary_payload)
    monkeypatch.setattr(decision, "get_unified_decision_details_payload", _fake_details_payload)

    mcp = _DummyMCP()
    decision.register(mcp)

    summary_result = await mcp.get_unified_decision_summary(code="600519")
    details_result = await mcp.get_unified_decision_details(code="600519")
    wrapper_result = await mcp.get_unified_decision(code="600519", detail_level="details")
    assert hasattr(mcp, "build_stock_context")
    assert hasattr(mcp, "build_quant_context")
    assert hasattr(mcp, "build_event_context")
    assert hasattr(mcp, "run_decision_gate")
    assert hasattr(mcp, "fuse_decision_payload")

    assert summary_result["success"] is True
    assert summary_result["data"]["scene"] == "unified_decision"
    assert details_result["success"] is True
    assert "details" in details_result["data"]
    assert wrapper_result["success"] is True
    assert wrapper_result["data"]["details"]["requested"]["code"] == "600519"


@pytest.mark.asyncio
async def test_unified_decision_summary_payload_builds_contexts_concurrently(monkeypatch):
    from akshare_mcp.services import decision_contracts

    started: set[str] = set()
    ready = asyncio.Event()

    def _make_builder(name, payload):
        async def _builder(*_args, **_kwargs):
            started.add(name)
            if len(started) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=0.2)
            return payload

        return _builder

    monkeypatch.setattr(
        decision_contracts,
        "build_stock_context",
        _make_builder("stock", {"code": "600519", "name": "测试股份", "warnings": []}),
    )
    monkeypatch.setattr(
        decision_contracts,
        "build_quant_context",
        _make_builder("quant", {"code": "600519", "score": 68.0, "warnings": []}),
    )
    monkeypatch.setattr(
        decision_contracts,
        "build_event_context",
        _make_builder("event", {"code": "600519", "score": 52.0, "warnings": []}),
    )
    monkeypatch.setattr(
        decision_contracts,
        "build_user_context",
        _make_builder("user", {"user_id": "u_demo", "risk_level": "moderate", "warnings": []}),
    )
    monkeypatch.setattr(
        decision_contracts,
        "build_rule_gates",
        lambda **kwargs: {
            "blocked": False,
            "veto_reason": None,
            "flags": [],
            "gate_adjustment": 0.0,
            "position_cap_pct": 0.2,
            "requested_style": kwargs["investment_style"],
            "user_risk_level": "moderate",
        },
    )
    monkeypatch.setattr(
        decision_contracts,
        "fuse_unified_decision",
        lambda **kwargs: {
            "action": "hold",
            "confidence": 0.6,
            "final_score": 60.0,
            "summary": "并发构建上下文成功。",
            "reasons": [],
            "risks": [],
            "veto_reason": None,
            "position_signal": {"label": "观察", "suggested_position_pct": 0.0, "position_cap_pct": 0.2},
            "score_breakdown": {},
            "weights": {},
        },
    )

    payload = await asyncio.wait_for(
        decision_contracts.get_unified_decision_summary_payload(code="600519", investment_style="balanced", user_id="u_demo"),
        timeout=0.3,
    )

    assert payload["action"] == "hold"
    assert started == {"stock", "quant", "event", "user"}


@pytest.mark.asyncio
async def test_run_decision_gate_builds_missing_contexts_concurrently(monkeypatch):
    from akshare_mcp.tools import _decision_unified as unified

    started: set[str] = set()
    ready = asyncio.Event()

    def _make_builder(name, payload):
        async def _builder(*_args, **_kwargs):
            started.add(name)
            if len(started) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=0.2)
            return payload

        return _builder

    monkeypatch.setattr(unified, "_build_stock_context", _make_builder("stock", {"code": "600519"}))
    monkeypatch.setattr(unified, "_build_quant_context", _make_builder("quant", {"code": "600519"}))
    monkeypatch.setattr(unified, "_build_event_context", _make_builder("event", {"code": "600519"}))
    monkeypatch.setattr(unified, "_build_user_context", _make_builder("user", {"risk_level": "moderate"}))
    monkeypatch.setattr(
        unified,
        "_build_rule_gates",
        lambda **kwargs: {"blocked": False, "flags": [], "requested_style": kwargs["investment_style"]},
    )

    result = await asyncio.wait_for(
        unified.run_decision_gate(code="600519", investment_style="balanced", user_id="u_demo"),
        timeout=0.3,
    )

    assert result["success"] is True
    assert result["data"]["blocked"] is False
    assert started == {"stock", "quant", "event", "user"}
