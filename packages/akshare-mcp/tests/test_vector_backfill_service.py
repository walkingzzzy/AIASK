from __future__ import annotations

import pytest

from akshare_mcp.services.vector_backfill import backfill_market_document_vectors


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self):
        self.vector_documents = [
            {"id": 1, "stock_code": "600519", "doc_type": "news", "content": "茅台高增长新闻", "date": "2026-03-20"},
            {"id": 2, "stock_code": "000001", "doc_type": "notice", "content": "平安银行公告", "date": "2026-03-21"},
        ]
        self.research_reports = [
            {
                "id": 3,
                "code": "600519",
                "title": "贵州茅台研报",
                "institution": "测试券商",
                "analyst": "分析师A",
                "publish_date": "2026-03-22",
                "summary": "维持高增长判断",
                "pdf_url": "https://example.com/report.pdf",
            }
        ]
        self.existing_doc_uids = {"000001:notice:2026-03-21:平安银行公告:平安银行公告"}

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM vector_documents" in normalized:
            after_id = int(args[0])
            limit = int(args[-1])
            return [row for row in self.vector_documents if int(row["id"]) > after_id][:limit]
        if "FROM research_reports" in normalized:
            after_id = int(args[0])
            limit = int(args[-1])
            return [row for row in self.research_reports if int(row["id"]) > after_id][:limit]
        if "SELECT doc_uid FROM market_documents WHERE doc_uid = ANY($1::text[])" in normalized:
            doc_uids = set(args[0] or [])
            return [{"doc_uid": doc_uid} for doc_uid in self.existing_doc_uids if doc_uid in doc_uids]
        return []


class _Db:
    def __init__(self):
        self.conn = _Conn()
        self.save_calls: list[dict] = []

    def acquire(self):
        return _Acquire(self.conn)

    def _build_market_doc_uid(self, stock_code: str, doc_type: str, item: dict):
        title = str(item.get("title") or item.get("content") or "").strip()
        content = str(item.get("content") or item.get("summary") or "").strip()
        raw_date = str(item.get("date") or "").strip()
        return f"{stock_code}:{doc_type}:{raw_date}:{title}:{content[:120]}"

    async def save_market_documents(self, stock_code, doc_type, items, **kwargs):
        batch = [dict(item) for item in items]
        self.save_calls.append(
            {
                "stock_code": stock_code,
                "doc_type": doc_type,
                "items": batch,
                "kwargs": kwargs,
            }
        )
        return {
            "documents": len(batch),
            "chunks": len(batch) * 2,
            "embedded_chunks": len(batch) * 2 if kwargs.get("embed") else 0,
        }


@pytest.mark.asyncio
async def test_backfill_market_document_vectors_backfills_news_and_research_and_skips_existing_docs():
    db = _Db()

    result = await backfill_market_document_vectors(
        db,
        doc_types=["news", "notice", "research"],
        limit=10,
        batch_size=10,
        embed=False,
        version="mem_v2",
    )

    assert result["candidate_docs"] == 3
    assert result["skipped_existing_docs"] == 1
    assert result["saved_docs"] == 2
    assert result["saved_chunks"] == 4
    assert result["embedded_chunks"] == 0
    assert result["version"] == "mem_v2"
    assert len(db.save_calls) == 2
    assert db.save_calls[0]["stock_code"] == "600519"
    assert db.save_calls[0]["doc_type"] == "news"
    assert db.save_calls[0]["kwargs"]["version"] == "mem_v2"
    assert db.save_calls[1]["doc_type"] == "research"
