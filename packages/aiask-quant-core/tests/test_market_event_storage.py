from __future__ import annotations

import asyncio
import json
import sqlite3

from aiask_quant_core.storage.sqlite import SQLiteAdapter


def test_market_event_schema_initializes_event_tables_and_provenance_columns(tmp_path) -> None:
    db_path = tmp_path / "market_event_schema.sqlite3"
    db = SQLiteAdapter(path=db_path)

    async def _run() -> None:
        try:
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(_run())

    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            ).fetchall()
        }
        document_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(market_documents)").fetchall()
        }
        event_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(market_events_normalized)").fetchall()
        }
    finally:
        conn.close()

    assert "market_documents" in names
    assert "market_events_normalized" in names
    assert "idx_market_documents_provenance" in names
    assert "idx_market_events_normalized_status" in names
    assert "idx_market_events_normalized_tier" in names
    assert {
        "source_tier",
        "provider",
        "original_id",
        "fetched_at",
        "checksum",
        "reliability_score",
        "crawl_status",
    }.issubset(document_columns)
    assert {
        "event_id",
        "event_type",
        "entity_codes",
        "source_doc_uids",
        "source_tier",
        "provider_chain",
        "reliability_score",
        "status",
        "reject_reason",
    }.issubset(event_columns)


def test_market_documents_persist_event_source_provenance(tmp_path) -> None:
    db = SQLiteAdapter(path=tmp_path / "market_documents_provenance.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            summary = await db.save_market_documents(
                "600000.SH",
                "notice",
                [
                    {
                        "doc_uid": "cninfo-notice-1",
                        "title": "Major contract announcement",
                        "summary": "Company signed a material sales contract.",
                        "body": "Company signed a material sales contract with verified disclosure details.",
                        "source": "cninfo",
                        "source_tier": "official",
                        "provider": "cninfo",
                        "original_id": "1200000001",
                        "published_at": "2026-06-05",
                        "fetched_at": "2026-06-06T08:00:00+00:00",
                        "checksum": "checksum-cninfo-1",
                        "reliability_score": 0.97,
                        "crawl_status": "ok",
                    }
                ],
                embed=False,
            )

            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT doc_uid, source_tier, provider, original_id, fetched_at, checksum,
                           reliability_score, crawl_status, metadata
                    FROM market_documents
                    WHERE doc_uid = $1
                    """,
                    "cninfo-notice-1",
                )
                chunk = await conn.fetchrow(
                    """
                    SELECT metadata
                    FROM market_doc_chunks
                    WHERE stock_code = $1 AND source = $2
                    """,
                    "600000.SH",
                    "cninfo",
                )

            assert summary["documents"] == 1
            assert row is not None
            assert row["source_tier"] == "tier_a"
            assert row["provider"] == "cninfo"
            assert row["original_id"] == "1200000001"
            assert str(row["fetched_at"]).startswith("2026-06-06T08:00:00")
            assert row["checksum"] == "checksum-cninfo-1"
            assert float(row["reliability_score"]) == 0.97
            assert row["crawl_status"] == "ok"
            metadata = json.loads(row["metadata"])
            assert metadata["source_tier"] == "tier_a"
            assert metadata["original_id"] == "1200000001"
            chunk_metadata = json.loads(chunk["metadata"])
            assert chunk_metadata["source_tier"] == "tier_a"
            assert chunk_metadata["provider"] == "cninfo"
            assert chunk_metadata["checksum"] == "checksum-cninfo-1"
        finally:
            await db.close()

    asyncio.run(_run())


def test_market_events_normalized_round_trips_and_counts(tmp_path) -> None:
    db = SQLiteAdapter(path=tmp_path / "market_events_round_trip.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            saved = await db.upsert_market_event_normalized(
                {
                    "event_id": "mevt-cninfo-contract-1",
                    "event_type": "major_contract",
                    "event_name": "Material contract disclosure",
                    "summary": "Official announcement anchors a positive order catalyst.",
                    "entity_codes": ["600000.SH"],
                    "theme_codes": ["major_contract"],
                    "direction": "up",
                    "event_time": "2026-06-05T00:00:00+08:00",
                    "publish_time": "2026-06-05T18:30:00+08:00",
                    "evidence_time": "2026-06-05T18:30:00+08:00",
                    "source_doc_uids": ["cninfo-notice-1"],
                    "source_tier": "tier_a",
                    "source_types": ["cninfo", "official_disclosure"],
                    "provider_chain": ["cninfo"],
                    "reliability_score": 0.94,
                    "cross_source_count": 1,
                    "status": "verified",
                    "freshness_status": "fresh",
                    "event_anchor_id": "mevt-cninfo-contract-1",
                    "checksum": "event-checksum-1",
                    "metadata": {"taxonomy": "order_contract", "event_signature": "sig-cninfo-contract-1"},
                }
            )
            await db.upsert_market_event_normalized(
                {
                    "event_id": "mevt-news-only-1",
                    "event_type": "media_news",
                    "event_name": "News-only rumor",
                    "entity_codes": ["000001.SZ"],
                    "source_doc_uids": ["eastmoney-news-1"],
                    "source_tier": "tier_c",
                    "source_types": ["eastmoney"],
                    "provider_chain": ["eastmoney"],
                    "status": "provisional",
                    "reject_reason": "news_only_requires_official_anchor",
                }
            )

            verified = await db.list_market_events_normalized(status="verified")
            tier_c = await db.list_market_events_normalized(source_tier="tier_c")
            signature_rows = await db.list_market_events_normalized(event_signature="sig-cninfo-contract-1")
            counts = await db.count_market_events_normalized()

            assert saved["event_id"] == "mevt-cninfo-contract-1"
            assert saved["entity_codes"] == ["600000.SH"]
            assert saved["source_doc_uids"] == ["cninfo-notice-1"]
            assert saved["provider_chain"] == ["cninfo"]
            assert saved["metadata"] == {"taxonomy": "order_contract", "event_signature": "sig-cninfo-contract-1"}
            assert [row["event_id"] for row in verified] == ["mevt-cninfo-contract-1"]
            assert [row["event_id"] for row in signature_rows] == ["mevt-cninfo-contract-1"]
            assert tier_c[0]["reject_reason"] == "news_only_requires_official_anchor"
            assert counts["total"] == 2
            assert counts["by_status"] == {"provisional": 1, "verified": 1}
            assert counts["by_source_tier"] == {"tier_a": 1, "tier_c": 1}
        finally:
            await db.close()

    asyncio.run(_run())
