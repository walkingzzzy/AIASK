"""Theme exposure matrix builder (PR-4).

Computes exposure_score for each (stock, theme) pair using:
  - Industry match (申万行业 / 概念板块)
  - Name/alias keyword match
  - Main business composition match (fina_mainbz)
  - Historical beta (K-line correlation with theme index)

Designed to run as an off-hours daily job via factory_scheduler.
Reads from local SQLite tables (no real-time API calls).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _normalize_text(text: Any) -> str:
    return str(text or "").strip().lower()


def _keyword_match_score(text: str, keywords: list[str]) -> float:
    """Score how many keywords appear in text. Returns 0-1."""
    if not text or not keywords:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(1.0, matches / max(len(keywords), 1))


class ThemeExposureBuilder:
    """Builds the theme exposure matrix for all active stocks × themes.

    Usage:
        builder = ThemeExposureBuilder()
        report = await builder.build(db)
    """

    # Weights for exposure_score components (§8.1)
    W_INDUSTRY = 0.40
    W_NAME = 0.25
    W_MAINBZ = 0.20
    W_BETA = 0.15

    async def build(self, db: Any) -> dict[str, Any]:
        """Compute and persist theme exposure matrix.

        Args:
            db: Database adapter with access to stocks, theme_nodes, mainbz data.

        Returns:
            Report dict with counts and timing.
        """
        import time
        start = time.time()

        # Load theme nodes
        theme_nodes = []
        if hasattr(db, "list_theme_nodes"):
            theme_nodes = await db.list_theme_nodes(is_active=True, limit=200)
        if not theme_nodes:
            return {"status": "skipped", "reason": "no_active_theme_nodes"}

        # Load stock universe
        stocks = []
        if hasattr(db, "list_stock_universe"):
            stocks = await db.list_stock_universe(limit=6000, offset=0)
        if not stocks:
            return {"status": "skipped", "reason": "no_stocks_in_universe"}

        # Load mainbz data (cached locally)
        mainbz_map = await self._load_mainbz_map(db)

        # Compute exposures
        rows_written = 0
        errors = 0

        for theme in theme_nodes:
            theme_code = str(theme.get("theme_code") or "").strip()
            if not theme_code:
                continue

            aliases = theme.get("aliases") or []
            if isinstance(aliases, str):
                try:
                    aliases = json.loads(aliases)
                except Exception:
                    aliases = []

            industry_tags = theme.get("industry_tags") or []
            if isinstance(industry_tags, str):
                try:
                    industry_tags = json.loads(industry_tags)
                except Exception:
                    industry_tags = []

            keywords = [theme.get("theme_name", ""), *aliases, *industry_tags]
            keywords = [k.lower() for k in keywords if k]

            for stock in stocks:
                symbol = str(stock.get("code") or stock.get("symbol") or "").strip()
                if not symbol:
                    continue

                try:
                    score = self._compute_exposure(
                        stock=stock,
                        theme_code=theme_code,
                        keywords=keywords,
                        industry_tags=industry_tags,
                        mainbz=mainbz_map.get(symbol, []),
                    )

                    if score["total"] < 0.1:
                        continue  # Skip negligible exposures

                    if hasattr(db, "upsert_theme_exposure"):
                        await db.upsert_theme_exposure({
                            "symbol": symbol,
                            "theme_code": theme_code,
                            "exposure_score": score["total"],
                            "industry_match_level": score["industry_level"],
                            "name_match_score": score["name_score"],
                            "mainbz_match_score": score["mainbz_score"],
                            "historical_beta": score["beta"],
                        })
                    rows_written += 1
                except Exception as exc:
                    errors += 1
                    if errors <= 5:
                        logger.debug("ThemeExposureBuilder: error for %s/%s: %s", symbol, theme_code, exc)

        elapsed = time.time() - start
        return {
            "status": "completed",
            "theme_count": len(theme_nodes),
            "stock_count": len(stocks),
            "rows_written": rows_written,
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
            "mainbz_coverage": len(mainbz_map),
        }

    def _compute_exposure(
        self,
        *,
        stock: dict[str, Any],
        theme_code: str,
        keywords: list[str],
        industry_tags: list[str],
        mainbz: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute exposure score components for a single (stock, theme) pair."""

        # 1. Industry match (0.40)
        stock_industry = _normalize_text(stock.get("industry") or stock.get("sector"))
        industry_level = 0
        if industry_tags:
            for tag in industry_tags:
                if tag.lower() in stock_industry or stock_industry in tag.lower():
                    industry_level = 2  # Direct match
                    break
            if industry_level == 0:
                # Partial match via keywords
                if any(kw in stock_industry for kw in keywords if len(kw) >= 2):
                    industry_level = 1
        industry_score = {0: 0.0, 1: 0.5, 2: 1.0}[industry_level]

        # 2. Name/alias match (0.25)
        stock_name = _normalize_text(stock.get("name") or stock.get("stock_name"))
        name_score = _keyword_match_score(stock_name, keywords)

        # 3. Main business match (0.20)
        mainbz_score = 0.0
        if mainbz:
            biz_text = " ".join(
                _normalize_text(item.get("bz_item") or item.get("business_name") or "")
                for item in mainbz
            )
            mainbz_score = _keyword_match_score(biz_text, keywords)
            # Boost if revenue share is high
            for item in mainbz:
                ratio = _safe_float(item.get("bz_sales_ratio") or item.get("revenue_ratio"), 0)
                if ratio > 0.3 and any(kw in _normalize_text(item.get("bz_item", "")) for kw in keywords):
                    mainbz_score = min(1.0, mainbz_score + 0.3)
                    break

        # 4. Historical beta (0.15) — placeholder, requires K-line correlation
        # Will be filled by PR-7 regression model
        beta = 0.0

        total = (
            self.W_INDUSTRY * industry_score
            + self.W_NAME * name_score
            + self.W_MAINBZ * mainbz_score
            + self.W_BETA * beta
        )

        return {
            "total": round(total, 4),
            "industry_level": industry_level,
            "industry_score": round(industry_score, 4),
            "name_score": round(name_score, 4),
            "mainbz_score": round(mainbz_score, 4),
            "beta": round(beta, 4),
        }

    async def _load_mainbz_map(self, db: Any) -> dict[str, list[dict[str, Any]]]:
        """Load main business composition data grouped by symbol."""
        result: dict[str, list[dict[str, Any]]] = {}

        # Try to load from local cache table
        if hasattr(db, "list_company_mainbz"):
            try:
                rows = await db.list_company_mainbz(limit=50000)
                for row in rows:
                    symbol = str(row.get("symbol") or row.get("ts_code", "")[:6]).strip()
                    if symbol:
                        result.setdefault(symbol, []).append(row)
                return result
            except Exception as exc:
                logger.debug("ThemeExposureBuilder: list_company_mainbz failed: %s", exc)

        return result


__all__ = ["ThemeExposureBuilder"]
