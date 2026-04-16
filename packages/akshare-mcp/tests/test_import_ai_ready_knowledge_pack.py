from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "import_ai_ready_knowledge_pack.py"
MODULE_SPEC = importlib.util.spec_from_file_location("import_ai_ready_knowledge_pack", SCRIPT_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
import_ai_ready = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = import_ai_ready
MODULE_SPEC.loader.exec_module(import_ai_ready)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "ai_ready"
    metadata_dir = pack_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    (metadata_dir / "knowledge_pack_manifest.json").write_text(
        json.dumps(
            {
                "asset_name": "原油",
                "asset_code": "SC",
                "generated_at": "2026-04-15T13:04:53",
                "document_count": 2,
                "chunk_count": 3,
                "dataset_count": 1,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        metadata_dir / "market_documents.jsonl",
        [
            {
                "doc_uid": "doc_1",
                "stock_code": "SC",
                "doc_type": "research",
                "source": "local_raw_materials",
                "title": "文档一",
                "summary": "摘要一",
                "body": "正文一",
                "url": "",
                "author": "",
                "published_at": "2026-04-15",
                "metadata": {"content_group": "strategy_notes"},
            },
            {
                "doc_uid": "doc_2",
                "stock_code": "SC",
                "doc_type": "research",
                "source": "local_raw_materials",
                "title": "文档二",
                "summary": "摘要二",
                "body": "正文二",
                "url": "",
                "author": "",
                "published_at": None,
                "metadata": {"content_group": "price_trend"},
            },
        ],
    )
    _write_jsonl(
        metadata_dir / "market_doc_chunks.jsonl",
        [
            {
                "doc_uid": "doc_1",
                "chunk_no": 1,
                "stock_code": "SC",
                "doc_type": "research",
                "source": "local_raw_materials",
                "title": "文档一",
                "chunk_text": "正文一-块1",
                "token_count": 10,
                "char_count": 6,
                "language": "zh",
                "published_at": "2026-04-15",
                "metadata": {"chunk_label": "a"},
            },
            {
                "doc_uid": "doc_1",
                "chunk_no": 2,
                "stock_code": "SC",
                "doc_type": "research",
                "source": "local_raw_materials",
                "title": "文档一",
                "chunk_text": "正文一-块2",
                "token_count": 10,
                "char_count": 6,
                "language": "zh",
                "published_at": "2026-04-15",
                "metadata": {"chunk_label": "b"},
            },
            {
                "doc_uid": "doc_2",
                "chunk_no": 1,
                "stock_code": "SC",
                "doc_type": "research",
                "source": "local_raw_materials",
                "title": "文档二",
                "chunk_text": "正文二-块1",
                "token_count": 10,
                "char_count": 6,
                "language": "zh",
                "published_at": None,
                "metadata": {"chunk_label": "c"},
            },
        ],
    )
    _write_jsonl(
        metadata_dir / "datasets.jsonl",
        [
            {
                "dataset_id": "set_1",
                "title": "dataset",
                "output_csv": "tables/data.csv",
            }
        ],
    )
    return pack_dir


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self):
        self.docs: list[dict] = []
        self.chunks: list[dict] = []

    def transaction(self):
        return _Tx()

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT doc_uid FROM market_documents" in normalized:
            requested = set(args[0] or [])
            return [{"doc_uid": row["doc_uid"]} for row in self.docs if row["doc_uid"] in requested]
        return []

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT COUNT(*) FROM market_doc_chunks" in normalized:
            doc_id = int(args[0])
            return sum(1 for row in self.chunks if row["doc_id"] == doc_id)
        return None

    async def fetchrow(self, query, *args):
        normalized = " ".join(str(query).split())
        if "INSERT INTO market_documents" in normalized:
            doc_uid = args[0]
            existing = next((row for row in self.docs if row["doc_uid"] == doc_uid), None)
            if existing is None:
                existing = {"id": len(self.docs) + 1, "doc_uid": doc_uid}
                self.docs.append(existing)
            existing.update(
                {
                    "stock_code": args[1],
                    "doc_type": args[2],
                    "source": args[3],
                    "title": args[4],
                    "summary": args[5],
                    "body": args[6],
                    "url": args[7],
                    "author": args[8],
                    "published_at": args[9],
                    "metadata": json.loads(args[10]),
                }
            )
            return dict(existing)
        if "INSERT INTO market_doc_chunks" in normalized:
            doc_id = int(args[0])
            chunk_no = int(args[1])
            existing = next((row for row in self.chunks if row["doc_id"] == doc_id and row["chunk_no"] == chunk_no), None)
            if existing is None:
                existing = {"id": len(self.chunks) + 1, "doc_id": doc_id, "chunk_no": chunk_no}
                self.chunks.append(existing)
            existing.update(
                {
                    "stock_code": args[2],
                    "doc_type": args[3],
                    "source": args[4],
                    "title": args[5],
                    "chunk_text": args[6],
                    "token_count": args[7],
                    "char_count": args[8],
                    "language": args[9],
                    "published_at": args[10],
                    "metadata": json.loads(args[11]),
                }
            )
            return {"id": existing["id"]}
        return None

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        if "DELETE FROM market_doc_chunks WHERE doc_id = $1" in normalized:
            doc_id = int(args[0])
            self.chunks = [row for row in self.chunks if row["doc_id"] != doc_id]
        return "OK"


class _Acquire:
    def __init__(self, conn: _Conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Db:
    def __init__(self):
        self.conn = _Conn()
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    def acquire(self):
        return _Acquire(self.conn)


def test_load_knowledge_pack_and_plan(tmp_path: Path):
    pack_dir = _build_pack(tmp_path)
    pack = import_ai_ready.load_knowledge_pack(pack_dir)
    plan = import_ai_ready.build_import_plan(pack)

    assert pack.manifest["asset_code"] == "SC"
    assert plan["document_count"] == 2
    assert plan["chunk_count"] == 3
    assert plan["doc_without_chunks"] == []


@pytest.mark.asyncio
async def test_import_knowledge_pack_upserts_documents_and_chunks(tmp_path: Path):
    pack_dir = _build_pack(tmp_path)
    pack = import_ai_ready.load_knowledge_pack(pack_dir)
    db = _Db()

    report = await import_ai_ready.import_knowledge_pack(
        db,
        pack,
        dry_run=False,
        rebuild_chunks=True,
        embed=False,
        vector_version="",
        set_active_version=False,
        stock_code_override="SC",
        source_override="local_ai_ready",
    )

    assert db.initialized is True
    assert report["inserted_documents"] == 2
    assert report["upserted_chunks"] == 3
    assert len(db.conn.docs) == 2
    assert len(db.conn.chunks) == 3
    assert db.conn.docs[0]["source"] == "local_ai_ready"
    assert db.conn.chunks[0]["metadata"]["chunk_label"] == "a"
