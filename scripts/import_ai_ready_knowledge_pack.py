#!/usr/bin/env python3
"""Import an AI-ready knowledge pack into market_documents / market_doc_chunks.

The script is intentionally generic: it consumes the `ai_ready/metadata/*.jsonl`
artifacts produced by `build_ai_ready_knowledge_pack.py`, validates them,
supports dry-run planning without a database, and can optionally create vector
profiles for the imported chunks when an embedding provider is configured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent
for relative in ("packages/akshare-mcp/src", "packages/strategy-factory/src"):
    candidate = ROOT_DIR / relative
    if candidate.exists():
        sys.path.insert(0, str(candidate))

from akshare_mcp.storage.timescaledb import get_db, run_with_db_cleanup


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _json_dump(payload: Any) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, default=str)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_timestamp(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.combine(date.fromisoformat(item[:10]), time.min, tzinfo=timezone.utc),
    ):
        try:
            parsed = parser(text)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        try:
            parsed_date = date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
            return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _vector_version_from_manifest(manifest: dict[str, Any], explicit: str | None) -> str:
    override = str(explicit or "").strip()
    if override:
        return override
    generated_at = str(manifest.get("generated_at") or "").strip()
    if generated_at:
        digits = re.sub(r"[^0-9]", "", generated_at)
        if digits:
            return f"ai_ready_{digits[:14]}"
    return f"ai_ready_{_utc_now().strftime('%Y%m%d%H%M%S')}"


@dataclass
class KnowledgePack:
    pack_dir: Path
    metadata_dir: Path
    manifest: dict[str, Any]
    documents: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    datasets: list[dict[str, Any]]

    @property
    def doc_uids(self) -> list[str]:
        return [str(item.get("doc_uid") or "").strip() for item in self.documents if str(item.get("doc_uid") or "").strip()]

    @property
    def chunks_by_doc_uid(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for chunk in self.chunks:
            doc_uid = str(chunk.get("doc_uid") or "").strip()
            if not doc_uid:
                continue
            grouped.setdefault(doc_uid, []).append(dict(chunk))
        for doc_uid in grouped:
            grouped[doc_uid].sort(key=lambda row: int(row.get("chunk_no") or 0))
        return grouped


def load_knowledge_pack(pack_dir: Path) -> KnowledgePack:
    resolved = pack_dir.expanduser().resolve()
    metadata_dir = resolved / "metadata"
    manifest = json.loads((metadata_dir / "knowledge_pack_manifest.json").read_text(encoding="utf-8"))
    documents = _load_jsonl(metadata_dir / "market_documents.jsonl")
    chunks = _load_jsonl(metadata_dir / "market_doc_chunks.jsonl")
    datasets = _load_jsonl(metadata_dir / "datasets.jsonl")
    return KnowledgePack(
        pack_dir=resolved,
        metadata_dir=metadata_dir,
        manifest=manifest,
        documents=documents,
        chunks=chunks,
        datasets=datasets,
    )


def build_import_plan(pack: KnowledgePack) -> dict[str, Any]:
    chunks_by_doc = pack.chunks_by_doc_uid
    doc_without_chunks = [
        str(item.get("doc_uid") or "")
        for item in pack.documents
        if str(item.get("doc_uid") or "") and not chunks_by_doc.get(str(item.get("doc_uid") or ""))
    ]
    doc_types: dict[str, int] = {}
    for item in pack.documents:
        doc_type = str(item.get("doc_type") or "unknown").strip().lower()
        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
    return {
        "pack_dir": str(pack.pack_dir),
        "asset_code": pack.manifest.get("asset_code"),
        "asset_name": pack.manifest.get("asset_name"),
        "document_count": len(pack.documents),
        "chunk_count": len(pack.chunks),
        "dataset_count": len(pack.datasets),
        "doc_type_counts": doc_types,
        "doc_without_chunks": doc_without_chunks,
        "manifest_generated_at": pack.manifest.get("generated_at"),
    }


async def _fetch_existing_doc_uids(conn, doc_uids: Iterable[str]) -> set[str]:
    values = [str(item or "").strip() for item in doc_uids if str(item or "").strip()]
    if not values:
        return set()
    rows = await conn.fetch(
        "SELECT doc_uid FROM market_documents WHERE doc_uid = ANY($1::text[])",
        values,
    )
    return {str(dict(row).get("doc_uid") or "").strip() for row in rows if dict(row).get("doc_uid")}


async def _fetch_chunk_count(conn, doc_id: int) -> int:
    return int(
        await conn.fetchval(
            "SELECT COUNT(*) FROM market_doc_chunks WHERE doc_id = $1",
            int(doc_id),
        )
        or 0
    )


async def _upsert_market_document(
    conn,
    row: dict[str, Any],
    *,
    stock_code_override: str | None,
    source_override: str | None,
    pack: KnowledgePack,
) -> dict[str, Any]:
    doc_uid = str(row.get("doc_uid") or "").strip()
    if not doc_uid:
        raise ValueError("document row missing doc_uid")
    source = str(source_override or row.get("source") or "local_ai_ready").strip()
    stock_code = str(stock_code_override or row.get("stock_code") or pack.manifest.get("asset_code") or "").strip() or None
    metadata = dict(row.get("metadata") or {})
    metadata["import"] = {
        "pack_dir": str(pack.pack_dir),
        "manifest_generated_at": pack.manifest.get("generated_at"),
        "imported_at": _utc_now().isoformat(),
        "script": "scripts/import_ai_ready_knowledge_pack.py",
    }
    db_row = await conn.fetchrow(
        """
        INSERT INTO market_documents (
            doc_uid, stock_code, doc_type, source, title, summary, body, url, author,
            published_at, metadata, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::timestamptz, $11::jsonb, NOW(), NOW())
        ON CONFLICT (doc_uid) DO UPDATE SET
            stock_code = EXCLUDED.stock_code,
            doc_type = EXCLUDED.doc_type,
            source = EXCLUDED.source,
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            body = EXCLUDED.body,
            url = EXCLUDED.url,
            author = EXCLUDED.author,
            published_at = EXCLUDED.published_at,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING id, doc_uid, stock_code, doc_type, source, title, summary, body, url, author, published_at, metadata
        """,
        doc_uid,
        stock_code,
        str(row.get("doc_type") or "research").strip().lower(),
        source,
        row.get("title"),
        row.get("summary"),
        row.get("body"),
        row.get("url"),
        row.get("author"),
        _coerce_timestamp(row.get("published_at")),
        _json_dump(metadata),
    )
    return dict(db_row)


async def _replace_market_doc_chunks(
    conn,
    *,
    doc_id: int,
    doc_row: dict[str, Any],
    chunk_rows: list[dict[str, Any]],
    rebuild_chunks: bool,
) -> dict[str, int]:
    removed = 0
    inserted = 0
    updated = 0
    if rebuild_chunks:
        removed = await _fetch_chunk_count(conn, doc_id)
        await conn.execute("DELETE FROM market_doc_chunks WHERE doc_id = $1", int(doc_id))
    for chunk in chunk_rows:
        metadata = dict(chunk.get("metadata") or {})
        metadata.setdefault("doc_uid", doc_row.get("doc_uid"))
        metadata.setdefault("imported_from", "ai_ready")
        row = await conn.fetchrow(
            """
            INSERT INTO market_doc_chunks (
                doc_id, chunk_no, stock_code, doc_type, source, title, chunk_text,
                token_count, char_count, language, published_at, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::timestamptz, $12::jsonb, NOW(), NOW())
            ON CONFLICT (doc_id, chunk_no) DO UPDATE SET
                stock_code = EXCLUDED.stock_code,
                doc_type = EXCLUDED.doc_type,
                source = EXCLUDED.source,
                title = EXCLUDED.title,
                chunk_text = EXCLUDED.chunk_text,
                token_count = EXCLUDED.token_count,
                char_count = EXCLUDED.char_count,
                language = EXCLUDED.language,
                published_at = EXCLUDED.published_at,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
            """,
            int(doc_id),
            int(chunk.get("chunk_no") or 0),
            doc_row.get("stock_code"),
            doc_row.get("doc_type"),
            doc_row.get("source"),
            chunk.get("title") or doc_row.get("title"),
            chunk.get("chunk_text"),
            chunk.get("token_count"),
            chunk.get("char_count"),
            str(chunk.get("language") or "zh").strip() or "zh",
            _coerce_timestamp(chunk.get("published_at") or doc_row.get("published_at")),
            _json_dump(metadata),
        )
        if row:
            inserted += 1
        else:
            updated += 1
    return {"removed_chunks": removed, "upserted_chunks": inserted + updated, "inserted_chunks": inserted}


async def _embed_imported_chunks(
    db,
    *,
    imported_chunks: list[dict[str, Any]],
    version: str,
    set_active_version: bool,
) -> dict[str, Any]:
    if not imported_chunks:
        return {"embedded_chunks": 0, "vector_version": None, "embedding_backend": "skipped"}

    try:
        from akshare_mcp.services.text_embedding import get_strategy_text_embedding_service
    except Exception as exc:
        return {"embedded_chunks": 0, "vector_version": None, "embedding_backend": f"unavailable:{type(exc).__name__}"}

    service = get_strategy_text_embedding_service()
    if not service.is_enabled():
        return {"embedded_chunks": 0, "vector_version": None, "embedding_backend": "disabled"}

    ensured_indexes: set[tuple[str, int]] = set()
    embedded_chunks = 0
    model_id = str(getattr(getattr(service, "config", None), "model", None) or "text-embedding-3-small")
    active_version = version if set_active_version else None
    for chunk in imported_chunks:
        text = str(chunk.get("chunk_text") or "").strip()
        if not text:
            continue
        vector = await service.embed_text(text)
        if not vector:
            continue
        doc_type = str(chunk.get("doc_type") or "research").strip().lower() or "research"
        vector_dim = len(vector)
        await db.save_vector_collection(
            {
                "collection_name": "market_doc_chunks",
                "entity_family": "document_chunk",
                "backend": db.get_vector_backend(),
                "metric": "cosine",
                "model_id": model_id,
                "vector_dim": vector_dim,
                "normalization": "unit",
                "status": "active",
                "active_version": active_version,
                "metadata": {
                    "domain": "market",
                    "doc_type": doc_type,
                    "import_source": "ai_ready",
                },
            }
        )
        entity_id = f"{chunk.get('doc_uid')}:{chunk.get('chunk_no')}"
        metadata = dict(chunk.get("metadata") or {})
        metadata.update(
            {
                "doc_id": chunk.get("doc_id"),
                "chunk_id": chunk.get("chunk_id"),
                "chunk_no": chunk.get("chunk_no"),
                "doc_uid": chunk.get("doc_uid"),
                "doc_type": doc_type,
                "source": chunk.get("source"),
                "title": chunk.get("title"),
                "published_at": chunk.get("published_at").isoformat()
                if isinstance(chunk.get("published_at"), datetime)
                else str(chunk.get("published_at") or "") or None,
                "url": chunk.get("url"),
                "author": chunk.get("author"),
                "import_source": "ai_ready",
            }
        )
        await db.save_vector_profile(
            {
                "collection_name": "market_doc_chunks",
                "entity_type": "market_doc_chunk",
                "entity_id": entity_id,
                "stock_code": chunk.get("stock_code"),
                "profile_type": doc_type,
                "model_id": model_id,
                "vector_dim": vector_dim,
                "metric": "cosine",
                "version": version,
                "signature": hashlib.sha1(f"{entity_id}|{model_id}|{text}".encode("utf-8")).hexdigest(),
                "embedding": vector,
                "metadata": metadata,
            }
        )
        embedded_chunks += 1
        key = (doc_type, vector_dim)
        if key not in ensured_indexes and hasattr(db, "ensure_vector_profile_pgvector_index"):
            await db.ensure_vector_profile_pgvector_index(
                collection_name="market_doc_chunks",
                version=version,
                vector_dim=vector_dim,
                profile_type=doc_type,
                metric="cosine",
            )
            ensured_indexes.add(key)

    return {
        "embedded_chunks": embedded_chunks,
        "vector_version": version,
        "embedding_backend": model_id,
        "set_active_version": bool(set_active_version),
    }


async def import_knowledge_pack(
    db,
    pack: KnowledgePack,
    *,
    dry_run: bool,
    rebuild_chunks: bool,
    embed: bool,
    vector_version: str | None,
    set_active_version: bool,
    stock_code_override: str | None,
    source_override: str | None,
) -> dict[str, Any]:
    plan = build_import_plan(pack)
    if dry_run:
        return {
            "mode": "dry_run",
            "plan": plan,
            "documents_to_import": len(pack.documents),
            "chunks_to_import": len(pack.chunks),
            "datasets_available": len(pack.datasets),
            "embed_requested": bool(embed),
            "vector_version": _vector_version_from_manifest(pack.manifest, vector_version) if embed else None,
        }

    await db.initialize()
    imported_chunk_rows: list[dict[str, Any]] = []
    existing_doc_uids: set[str] = set()
    async with db.acquire() as conn:
        existing_doc_uids = await _fetch_existing_doc_uids(conn, pack.doc_uids)

    summary = {
        "mode": "import",
        "plan": plan,
        "inserted_documents": 0,
        "updated_documents": 0,
        "removed_chunks": 0,
        "upserted_chunks": 0,
        "embedded_chunks": 0,
        "vector_version": None,
    }

    chunks_by_doc_uid = pack.chunks_by_doc_uid
    async with db.acquire() as conn:
        async with conn.transaction():
            for document in pack.documents:
                doc_uid = str(document.get("doc_uid") or "").strip()
                if not doc_uid:
                    continue
                db_doc = await _upsert_market_document(
                    conn,
                    document,
                    stock_code_override=stock_code_override,
                    source_override=source_override,
                    pack=pack,
                )
                if doc_uid in existing_doc_uids:
                    summary["updated_documents"] += 1
                else:
                    summary["inserted_documents"] += 1
                chunk_result = await _replace_market_doc_chunks(
                    conn,
                    doc_id=int(db_doc["id"]),
                    doc_row=db_doc,
                    chunk_rows=chunks_by_doc_uid.get(doc_uid, []),
                    rebuild_chunks=rebuild_chunks,
                )
                summary["removed_chunks"] += int(chunk_result["removed_chunks"])
                summary["upserted_chunks"] += int(chunk_result["upserted_chunks"])
                for chunk in chunks_by_doc_uid.get(doc_uid, []):
                    imported_chunk_rows.append(
                        {
                            "doc_id": int(db_doc["id"]),
                            "chunk_id": None,
                            "doc_uid": doc_uid,
                            "chunk_no": int(chunk.get("chunk_no") or 0),
                            "stock_code": db_doc.get("stock_code"),
                            "doc_type": db_doc.get("doc_type"),
                            "source": db_doc.get("source"),
                            "title": chunk.get("title") or db_doc.get("title"),
                            "chunk_text": chunk.get("chunk_text"),
                            "published_at": _coerce_timestamp(chunk.get("published_at") or db_doc.get("published_at")),
                            "url": db_doc.get("url"),
                            "author": db_doc.get("author"),
                            "metadata": dict(chunk.get("metadata") or {}),
                        }
                    )

    if embed:
        vector_report = await _embed_imported_chunks(
            db,
            imported_chunks=imported_chunk_rows,
            version=_vector_version_from_manifest(pack.manifest, vector_version),
            set_active_version=set_active_version,
        )
        summary.update(vector_report)
    return summary


def _print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def _async_main(args: argparse.Namespace) -> int:
    pack = load_knowledge_pack(Path(args.pack_dir))
    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
    else:
        stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
        report_path = pack.metadata_dir / f"import_report_{stamp}.json"

    if args.dry_run:
        report = await import_knowledge_pack(
            None,
            pack,
            dry_run=True,
            rebuild_chunks=args.rebuild_chunks,
            embed=args.embed,
            vector_version=args.vector_version,
            set_active_version=args.set_active_version,
            stock_code_override=args.stock_code,
            source_override=args.source,
        )
    else:
        db = get_db()
        report = await import_knowledge_pack(
            db,
            pack,
            dry_run=False,
            rebuild_chunks=args.rebuild_chunks,
            embed=args.embed,
            vector_version=args.vector_version,
            set_active_version=args.set_active_version,
            stock_code_override=args.stock_code,
            source_override=args.source,
        )

    report["pack_dir"] = str(pack.pack_dir)
    report["generated_at"] = _utc_now().isoformat()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_report(report)
    print(f"report_json: {report_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import ai_ready knowledge pack into market_documents / market_doc_chunks.")
    parser.add_argument("pack_dir", help="Path to the ai_ready directory.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize the pack without touching the database.")
    parser.add_argument("--embed", action="store_true", help="Create vector_profiles for imported market_doc_chunks when embedding service is available.")
    parser.add_argument("--vector-version", default="", help="Optional vector profile version tag. Defaults to ai_ready_<timestamp>.")
    parser.add_argument("--set-active-version", action="store_true", help="If embedding, update collection active_version to the imported version.")
    parser.add_argument("--stock-code", default="", help="Optional stock_code override written to imported rows.")
    parser.add_argument("--source", default="", help="Optional source override written to imported rows.")
    parser.add_argument("--report-json", default="", help="Optional report output path. Defaults to pack metadata directory.")
    parser.add_argument("--rebuild-chunks", dest="rebuild_chunks", action="store_true", default=True, help="Delete existing chunks for each imported doc before re-inserting them (default).")
    parser.add_argument("--no-rebuild-chunks", dest="rebuild_chunks", action="store_false", help="Keep existing chunks and upsert by (doc_id, chunk_no).")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return run_with_db_cleanup(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
