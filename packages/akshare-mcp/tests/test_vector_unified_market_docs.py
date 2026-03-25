from __future__ import annotations

from types import SimpleNamespace

import pytest

from akshare_mcp.services.db_first_market_context import load_db_first_document_context
from akshare_mcp.storage.timescaledb.market_context import MarketContextMixin
from akshare_mcp.storage.timescaledb.vector_unified import VectorUnifiedMixin


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self):
        self.vector_documents: list[dict] = []
        self.market_documents: list[dict] = []
        self.market_doc_chunks: list[dict] = []

    def transaction(self):
        return _Tx()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split())
        if "INSERT INTO vector_documents" in normalized:
            stock_code, doc_type, content, doc_date = args
            exists = any(
                row["stock_code"] == stock_code
                and row["doc_type"] == doc_type
                and row["content"] == content
                and row["date"] == doc_date
                for row in self.vector_documents
            )
            if exists:
                return None
            self.vector_documents.append(
                {
                    "id": len(self.vector_documents) + 1,
                    "stock_code": stock_code,
                    "doc_type": doc_type,
                    "content": content,
                    "date": doc_date,
                }
            )
            return 1
        return None

    async def fetchrow(self, query, *args):
        normalized = " ".join(str(query).split())
        if "INSERT INTO market_documents" in normalized:
            doc_uid = args[0]
            existing = next((row for row in self.market_documents if row["doc_uid"] == doc_uid), None)
            if existing is None:
                existing = {"id": len(self.market_documents) + 1, "doc_uid": doc_uid}
                self.market_documents.append(existing)
            return dict(existing)
        if "INSERT INTO market_doc_chunks" in normalized:
            row = {
                "id": len(self.market_doc_chunks) + 1,
                "doc_id": args[0],
                "chunk_no": args[1],
                "stock_code": args[2],
                "doc_type": args[3],
                "source": args[4],
                "title": args[5],
                "chunk_text": args[6],
            }
            self.market_doc_chunks.append(row)
            return {"id": row["id"]}
        return None

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        if "DELETE FROM market_doc_chunks WHERE doc_id = $1" in normalized:
            doc_id = args[0]
            self.market_doc_chunks = [row for row in self.market_doc_chunks if row["doc_id"] != doc_id]
        return "OK"

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM market_doc_chunks c JOIN market_documents d ON d.id = c.doc_id" in normalized:
            stock_code = args[0]
            aliases = set(args[1] or [])
            limit = int(args[-1])
            rows = []
            for chunk in self.market_doc_chunks:
                if chunk["stock_code"] != stock_code or chunk["doc_type"] not in aliases:
                    continue
                doc = next((item for item in self.market_documents if item["id"] == chunk["doc_id"]), {})
                rows.append(
                    {
                        "id": chunk["id"],
                        "doc_uid": doc.get("doc_uid"),
                        "doc_id": chunk.get("doc_id"),
                        "chunk_no": chunk.get("chunk_no"),
                        "title": chunk["title"],
                        "chunk_text": chunk["chunk_text"],
                        "published_at": None,
                        "source": chunk["source"],
                        "summary": doc.get("summary", ""),
                        "url": doc.get("url", ""),
                        "author": doc.get("author"),
                        "entity_id": f"{doc.get('doc_uid')}:{chunk.get('chunk_no')}",
                    }
                )
            return rows[:limit]
        if "FROM vector_documents" in normalized:
            stock_code = args[0]
            aliases = set(args[1] or [])
            limit = int(args[-1])
            rows = []
            for row in self.vector_documents:
                if row["stock_code"] != stock_code or row["doc_type"] not in aliases:
                    continue
                rows.append(dict(row))
            rows.sort(key=lambda row: (str(row.get("date") or ""), int(row.get("id") or 0)), reverse=True)
            return rows[:limit]
        return []


class _Acquire:
    def __init__(self, conn: _Conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Adapter(MarketContextMixin):
    def __init__(self, conn: _Conn):
        self._conn = conn
        self.saved_collections: list[dict] = []
        self.saved_profiles: list[dict] = []
        self.ensured_indexes: list[dict] = []

    def acquire(self):
        return _Acquire(self._conn)

    def get_vector_backend(self):
        return "pgvector"

    async def save_vector_collection(self, payload: dict) -> dict:
        item = dict(payload)
        self.saved_collections.append(item)
        return item

    async def save_vector_profile(self, payload: dict) -> dict:
        item = dict(payload)
        self.saved_profiles.append(item)
        return item

    async def ensure_vector_profile_pgvector_index(self, **kwargs):
        self.ensured_indexes.append(dict(kwargs))
        return "idx_test"


class _DocOnlyDb:
    def __init__(self, conn: _Conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _SearchAdapter(VectorUnifiedMixin):
    def __init__(self, conn: _Conn, dense_rows: list[dict] | None = None):
        self._conn = conn
        self._dense_rows = list(dense_rows or [])
        self.search_vector_collection_calls: list[dict] = []

    def acquire(self):
        return _Acquire(self._conn)

    @staticmethod
    def _decode_json_field(value, default):
        if value is None:
            return default
        return value

    async def search_vector_collection(self, **kwargs):
        self.search_vector_collection_calls.append(dict(kwargs))
        return {
            "items": list(self._dense_rows),
            "backend_used": "pgvector",
            "fallback_used": False,
            "fallback_reason": None,
            "active_version": "snap_v1",
            "index_version": "snap_v1",
            "profile_version": "v1",
        }

    async def search_vector_profiles_by_embedding(self, **_kwargs):
        raise AssertionError("search_market_doc_chunks should use search_vector_collection")


@pytest.mark.asyncio
async def test_save_vector_documents_should_backfill_market_doc_chunks(monkeypatch):
    conn = _Conn()
    adapter = _Adapter(conn)

    class _EmbeddingService:
        def __init__(self):
            self.config = SimpleNamespace(model="text-embedding-3-small")

        def is_enabled(self):
            return True

        async def embed_text(self, text: str):
            assert text
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
        "akshare_mcp.services.text_embedding.get_strategy_text_embedding_service",
        lambda: _EmbeddingService(),
    )

    payload = [
        {
            "title": "贵州茅台业绩点评",
            "content": "贵州茅台发布最新公告，营收和利润延续高增长。" * 80,
            "date": "2026-03-24",
            "url": "https://example.com/report/1",
            "source": "news_feed",
        }
    ]

    inserted = await adapter.save_vector_documents("600519", "news", payload)

    assert inserted == 1
    assert len(conn.vector_documents) == 1
    assert len(conn.market_documents) == 1
    assert len(conn.market_doc_chunks) >= 2
    assert adapter.saved_collections
    assert adapter.saved_profiles
    assert adapter.saved_profiles[0]["collection_name"] == "market_doc_chunks"
    assert adapter.saved_profiles[0]["entity_type"] == "market_doc_chunk"
    assert adapter.saved_profiles[0]["profile_type"] == "news"
    assert adapter.ensured_indexes[0]["collection_name"] == "market_doc_chunks"


@pytest.mark.asyncio
async def test_load_db_first_document_context_prefers_market_doc_chunks():
    conn = _Conn()
    conn.market_documents.append(
        {
            "id": 1,
            "doc_uid": "doc_1",
            "summary": "chunked summary",
            "url": "https://example.com/doc/1",
        }
    )
    conn.market_doc_chunks.append(
        {
            "id": 1,
            "doc_id": 1,
            "chunk_no": 0,
            "stock_code": "600519",
            "doc_type": "news",
            "source": "market_news",
            "title": "茅台新闻标题",
            "chunk_text": "这是已经 chunk 化后的新闻正文。",
        }
    )

    context, source_chain = await load_db_first_document_context(
        _DocOnlyDb(conn),
        "600519",
        news_limit=3,
    )

    assert source_chain == ["db.market_doc_chunks.news"]
    assert context["news"]
    assert context["news"][0]["title"] == "茅台新闻标题"
    assert context["news"][0]["content"] == "这是已经 chunk 化后的新闻正文。"


@pytest.mark.asyncio
async def test_load_db_first_document_context_falls_back_to_legacy_vector_documents():
    conn = _Conn()
    conn.vector_documents.append(
        {
            "id": 1,
            "stock_code": "600519",
            "doc_type": "news",
            "content": "这是 legacy vector_documents 中的新闻正文。",
            "date": "2026-03-24",
        }
    )

    context, source_chain = await load_db_first_document_context(
        _DocOnlyDb(conn),
        "600519",
        news_limit=3,
    )

    assert source_chain == ["db.vector_documents_legacy.news"]
    assert context["news"]
    assert context["news"][0]["source"] == "vector_documents_legacy.news"
    assert context["news"][0]["content"] == "这是 legacy vector_documents 中的新闻正文。"


@pytest.mark.asyncio
async def test_search_market_doc_chunks_hybrid_scores_and_orders_results():
    conn = _Conn()
    conn.market_documents.extend(
        [
            {"id": 1, "doc_uid": "doc_1", "summary": "summary 1", "url": "https://example.com/doc/1", "author": "A"},
            {"id": 2, "doc_uid": "doc_2", "summary": "summary 2", "url": "https://example.com/doc/2", "author": "B"},
        ]
    )
    conn.market_doc_chunks.extend(
        [
            {
                "id": 1,
                "doc_id": 1,
                "chunk_no": 0,
                "stock_code": "600519",
                "doc_type": "news",
                "source": "market_news",
                "title": "茅台业绩高增长点评",
                "chunk_text": "贵州茅台营收和利润延续高增长，盈利质量继续改善。",
            },
            {
                "id": 2,
                "doc_id": 2,
                "chunk_no": 0,
                "stock_code": "600519",
                "doc_type": "news",
                "source": "market_news",
                "title": "白酒行业周报",
                "chunk_text": "本周板块整体震荡，市场继续等待催化。",
            },
        ]
    )
    adapter = _SearchAdapter(
        conn,
        dense_rows=[
            {"entity_id": "doc_1:0", "similarity": 0.72},
            {"entity_id": "doc_2:0", "similarity": 0.81},
        ],
    )

    rows = await adapter.search_market_doc_chunks(
        query_text="高增长",
        query_embedding=[0.1, 0.2, 0.3],
        stock_code="600519",
        doc_types=["news"],
        limit=5,
    )

    assert len(rows) == 2
    assert rows[0]["entity_id"] == "doc_1:0"
    assert rows[0]["dense_score"] == 0.72
    assert rows[0]["lexical_score"] > 0
    assert rows[0]["hybrid_score"] > rows[1]["hybrid_score"]
    assert adapter.search_vector_collection_calls[0]["collection_name"] == "market_doc_chunks"
    assert adapter.search_vector_collection_calls[0]["stock_code"] == "600519"
    assert adapter.search_vector_collection_calls[0]["profile_type"] == "news"
