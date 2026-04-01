from __future__ import annotations

from akshare_mcp.services.vector_search import VectorSearchEngine


def _build_rows(base: float) -> list[dict]:
    return [
        {
            "date": f"2026-03-{day:02d}",
            "open": base + day * 0.9,
            "close": base + day,
            "high": base + day * 1.1,
            "low": base + day * 0.8,
            "volume": 1000 + day * 10,
        }
        for day in range(1, 7)
    ]


def test_index_backend_reuses_cached_matrix_and_reports_candidate_count() -> None:
    engine = VectorSearchEngine(backend="index", allow_fallback=False)
    query = _build_rows(10.0)[-4:]
    candidates = {
        "AAA": _build_rows(10.0),
        "BBB": _build_rows(20.0),
        "CCC": _build_rows(30.0),
    }

    first = engine.find_similar_patterns(query, candidates, top_k=2, backend="index")
    second = engine.find_similar_patterns(query, candidates, top_k=2, backend="index")

    assert first
    assert second
    assert first[0]["source"] == "index"
    assert second[0]["source"] == "index"
    assert first[0]["candidate_count"] == 3
    assert second[0]["candidate_count"] == 3
    assert first[0]["index_reused"] is False
    assert second[0]["index_reused"] is True
