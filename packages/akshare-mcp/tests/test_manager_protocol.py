from akshare_mcp.services.document_index import build_document_index
from akshare_mcp.services.event_extraction import extract_events
from akshare_mcp.services.retrieval_eval import summarize_ranked_results
from akshare_mcp.tools.manager_protocol import (
    extract_common_meta,
    normalize_manager_code,
    normalize_manager_kwargs,
    ok_with_meta,
)


def test_normalize_manager_kwargs_should_merge_kwargs_and_params_payloads():
    kwargs = normalize_manager_kwargs(
        {
            "kwargs": '{"code":"600519","limit":5}',
            "params": {"top_n": 3},
            "Codes": ["000001", "600036"],
        }
    )

    code, merged = normalize_manager_code(None, kwargs)

    assert code == "600519"
    assert merged["limit"] == 5
    assert merged["top_n"] == 3
    assert merged["codes"] == ["000001", "600036"]


def test_ok_with_meta_should_attach_trace_and_common_meta():
    response = ok_with_meta(
        {"hello": "world"},
        tool_name="research_manager",
        action="get_reports",
        started_at=0.0,
        source_chain=["research_manager", "tushare.report_rc"],
        extra_meta=extract_common_meta({"as_of": "2026-03-19", "explain": True}),
    )

    assert response["success"] is True
    assert response["meta"]["source_chain"] == ["research_manager", "tushare.report_rc"]
    assert response["meta"]["as_of"] == "2026-03-19"
    assert response["meta"]["explain"] is True


def test_text_and_retrieval_services_should_return_summary_structures():
    merged_items = [
        {"type": "news", "date": "2026-03-18", "title": "业绩预增", "source": "news", "text": "公司业绩超预期，签约大额订单"},
        {"type": "research", "date": "2026-03-17", "title": "买入评级", "source": "broker", "text": "维持买入评级，目标价上调 15%"},
    ]

    document_index = build_document_index(merged_items)
    extraction = extract_events(document_index["documents"])
    retrieval_quality = summarize_ranked_results(
        [{"code": "600519", "similarity": 0.92}, {"code": "000858", "similarity": 0.87}],
        score_key="similarity",
        backend_requested="index",
        backend_used="python",
        fallback_used=True,
        fallback_reason="index_unavailable",
    )

    assert document_index["stats"]["total_documents"] == 2
    assert extraction["summary_counts"]["matched_documents"] >= 1
    assert extraction["event_tags"]
    assert retrieval_quality["fallback_used"] is True
    assert retrieval_quality["score_mean"] is not None
