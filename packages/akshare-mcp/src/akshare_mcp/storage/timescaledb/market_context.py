"""TimescaleDB adapter mixin for factor/decision text context storage."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional


class MarketContextMixin:
    """DB persistence helpers for news/notices/research/fund-flow context."""

    @staticmethod
    def _coerce_context_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            pass
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 8:
            try:
                return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
            except Exception:
                return None
        return None

    @staticmethod
    def _coerce_context_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_context_text(value: Any, *, max_len: int = 4000) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text[:max_len]

    @classmethod
    def _pick_document_content(cls, item: dict[str, Any]) -> str:
        for key in ("content", "text", "summary", "title", "headline", "name"):
            text = cls._clean_context_text(item.get(key))
            if text:
                return text
        return ""

    async def save_vector_documents(self, stock_code: str, doc_type: str, items: Iterable[dict[str, Any]]) -> int:
        code = str(stock_code or "").strip()
        normalized_doc_type = str(doc_type or "").strip().lower()
        rows = []
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            content = self._pick_document_content(item)
            if not content:
                continue
            rows.append(
                (
                    code,
                    normalized_doc_type,
                    content,
                    self._coerce_context_date(item.get("date") or item.get("time")),
                )
            )

        if not code or not normalized_doc_type or not rows:
            return 0

        inserted = 0
        async with self.acquire() as conn:
            for row in rows:
                result = await conn.fetchval(
                    """
                    INSERT INTO vector_documents (stock_code, doc_type, content, date, created_at)
                    SELECT $1, $2, $3, $4, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM vector_documents
                        WHERE stock_code = $1
                          AND doc_type = $2
                          AND content = $3
                          AND COALESCE(date, DATE '1970-01-01') = COALESCE($4::date, DATE '1970-01-01')
                    )
                    RETURNING 1
                    """,
                    *row,
                )
                if result:
                    inserted += 1
        return inserted

    async def save_research_reports(self, stock_code: str, reports: Iterable[dict[str, Any]]) -> int:
        code = str(stock_code or "").strip()
        rows = []
        for item in list(reports or []):
            if not isinstance(item, dict):
                continue
            title = self._clean_context_text(item.get("title"), max_len=500)
            institution = self._clean_context_text(item.get("institution"), max_len=200)
            publish_date = self._coerce_context_date(item.get("date") or item.get("publish_date"))
            summary = self._clean_context_text(item.get("summary") or item.get("content") or item.get("text"))
            if not title and not summary:
                continue
            rows.append(
                (
                    code,
                    title,
                    self._clean_context_text(item.get("rating"), max_len=120),
                    self._coerce_context_float(item.get("targetPrice") or item.get("target_price")),
                    institution,
                    self._clean_context_text(item.get("author") or item.get("analyst"), max_len=200),
                    publish_date,
                    summary,
                    self._clean_context_text(item.get("url") or item.get("pdf_url"), max_len=1000),
                )
            )

        if not code or not rows:
            return 0

        inserted = 0
        async with self.acquire() as conn:
            for row in rows:
                result = await conn.fetchval(
                    """
                    INSERT INTO research_reports (
                        code, title, rating, target_price, institution, analyst, publish_date, summary, pdf_url, created_at
                    )
                    SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM research_reports
                        WHERE code = $1
                          AND COALESCE(title, '') = COALESCE($2, '')
                          AND COALESCE(institution, '') = COALESCE($5, '')
                          AND COALESCE(publish_date, DATE '1970-01-01') = COALESCE($7::date, DATE '1970-01-01')
                    )
                    RETURNING 1
                    """,
                    *row,
                )
                if result:
                    inserted += 1
        return inserted

    async def save_stock_fund_flow(
        self,
        stock_code: str,
        payload: dict[str, Any],
        *,
        trade_date: Any = None,
    ) -> int:
        code = str(stock_code or payload.get("code") or "").strip()
        if not code or not isinstance(payload, dict):
            return 0

        resolved_trade_date = self._coerce_context_date(trade_date or payload.get("tradeDate") or payload.get("trade_date")) or date.today()
        row = (
            code,
            resolved_trade_date,
            self._clean_context_text(payload.get("name"), max_len=200),
            self._coerce_context_float(payload.get("mainNetInflow") or payload.get("main_net_inflow") or payload.get("net_inflow")),
            self._coerce_context_float(payload.get("mainInflowPercent") or payload.get("main_inflow_percent")),
            self._coerce_context_float(payload.get("superLargeNetInflow") or payload.get("super_large_net_inflow")),
            self._coerce_context_float(payload.get("largeNetInflow") or payload.get("large_net_inflow")),
            self._coerce_context_float(payload.get("middleNetInflow") or payload.get("middle_net_inflow")),
            self._coerce_context_float(payload.get("smallNetInflow") or payload.get("small_net_inflow") or payload.get("retail_net_inflow")),
            self._clean_context_text(payload.get("source"), max_len=120),
        )

        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stock_fund_flow (
                    code, trade_date, name, main_net_inflow, main_inflow_percent,
                    super_large_net_inflow, large_net_inflow, middle_net_inflow,
                    small_net_inflow, source, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    name = EXCLUDED.name,
                    main_net_inflow = EXCLUDED.main_net_inflow,
                    main_inflow_percent = EXCLUDED.main_inflow_percent,
                    super_large_net_inflow = EXCLUDED.super_large_net_inflow,
                    large_net_inflow = EXCLUDED.large_net_inflow,
                    middle_net_inflow = EXCLUDED.middle_net_inflow,
                    small_net_inflow = EXCLUDED.small_net_inflow,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                """,
                *row,
            )
        return 1
