from akshare_mcp.services.financial_schema import (
    financial_gap_summary,
    financial_payload_is_complete,
    financial_payload_needs_enrichment,
    merge_financial_payload,
    normalize_financial_payload,
)


def test_normalize_financial_payload_should_map_aliases_and_quality():
    payload = normalize_financial_payload(
        {
            "stock_code": "600519",
            "end_date": "20241231",
            "total_revenue": "123.45亿",
            "n_income": "45.67亿",
            "roe": "18.2",
            "debt_to_assets": "32.1",
            "eps": "12.34",
        },
        source_label="tushare",
    )

    assert payload["code"] == "600519"
    assert payload["reportDate"] == "2024-12-31"
    assert payload["revenue"] == 123.45 * 1e8
    assert payload["netProfit"] == 45.67 * 1e8
    assert payload["data_quality"]["normalized_from"]["revenue"] == "total_revenue"
    assert "currentRatio" in payload["data_quality"]["missing_fields"]


def test_merge_financial_payload_should_fill_gaps_from_fallback():
    primary = {
        "code": "600519",
        "reportDate": "2024-12-31",
        "revenue": 100.0,
        "netProfit": 20.0,
        "roe": None,
        "debtRatio": None,
        "source": "timescaledb",
    }
    fallback = {
        "code": "600519",
        "reportDate": "2024-12-31",
        "roe": 18.0,
        "debtRatio": 35.0,
        "eps": 12.0,
        "source": "tushare_pro",
    }

    merged = merge_financial_payload(primary, fallback)

    assert merged["roe"] == 18.0
    assert merged["debtRatio"] == 35.0
    assert merged["eps"] == 12.0
    assert financial_payload_is_complete(merged) is True
    assert financial_payload_needs_enrichment(merged) is False
    assert financial_gap_summary(merged) == "complete"
