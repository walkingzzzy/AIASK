from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from akshare_mcp.services.financial_semantic_service import FinancialSemanticConfig, FinancialSemanticService


@pytest.mark.asyncio
async def test_financial_semantic_service_rule_based_extracts_events_and_risks():
    service = FinancialSemanticService(
        FinancialSemanticConfig(enabled=True, provider="rule_based", model="keyword_finance_baseline")
    )
    try:
        result = await service.analyze_documents(
            [
                {
                    "type": "notice",
                    "source": "notice",
                    "title": "公司回购并获批新产品",
                    "text": "公司公告回购股份，同时核心产品正式获批。",
                },
                {
                    "type": "news",
                    "source": "media",
                    "title": "子公司因违规被立案调查",
                    "text": "子公司因违规问题被立案调查，存在监管风险。",
                },
            ]
        )
    finally:
        await service.close()

    assert result["available"] is True
    assert result["provider"] == "rule_based"
    assert any(item["tag"] == "capital" for item in result["event_types"])
    assert any(item["tag"] == "regulation" for item in result["event_types"])
    assert any(item["tag"] == "regulation_risk" for item in result["risk_tags"])


@pytest.mark.asyncio
async def test_financial_semantic_service_remote_failure_falls_back_to_rule_based(monkeypatch):
    service = FinancialSemanticService(
        FinancialSemanticConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.test",
            api_key="sk-test",
            model="finance-semantic",
        )
    )
    monkeypatch.setattr(service, "_remote_documents", AsyncMock(side_effect=RuntimeError("upstream timeout")))

    try:
        result = await service.analyze_documents(
            [
                {
                    "type": "news",
                    "source": "news",
                    "title": "公司业绩超预期并宣布回购",
                    "text": "公司业绩超预期，并公告将实施股份回购。",
                }
            ]
        )
    finally:
        await service.close()

    assert result["available"] is True
    assert result["provider"] == "rule_based"
    assert result["remote_provider"] == "openai_compatible"
    assert result["fallback_used"] is True
    assert "upstream timeout" in str(result["fallback_reason"])
