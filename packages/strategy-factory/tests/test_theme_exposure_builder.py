"""Tests for theme exposure builder (PR-4)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from strategy_factory.application.research.theme_exposure_builder import ThemeExposureBuilder


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.list_theme_nodes = AsyncMock(return_value=[
        {"theme_code": "upstream_oil_gas", "theme_name": "上游油气",
         "aliases": '["石油","原油"]', "industry_tags": '["石油开采"]'},
    ])
    db.list_stock_universe = AsyncMock(return_value=[
        {"code": "600028", "name": "中国石化", "industry": "石油化工"},
        {"code": "601857", "name": "中国石油", "industry": "石油开采"},
        {"code": "600519", "name": "贵州茅台", "industry": "白酒"},
    ])
    db.list_company_mainbz = AsyncMock(return_value=[
        {"symbol": "600028", "bz_item": "石油化工产品", "bz_sales_ratio": 0.6},
        {"symbol": "601857", "bz_item": "原油及天然气", "bz_sales_ratio": 0.8},
    ])
    db.upsert_theme_exposure = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_builder_basic(mock_db):
    builder = ThemeExposureBuilder()
    report = await builder.build(mock_db)
    assert report["status"] == "completed"
    assert report["theme_count"] == 1
    assert report["stock_count"] == 3
    # Oil stocks should have exposure, liquor should not
    assert report["rows_written"] >= 1


@pytest.mark.asyncio
async def test_builder_no_themes():
    db = MagicMock()
    db.list_theme_nodes = AsyncMock(return_value=[])
    builder = ThemeExposureBuilder()
    report = await builder.build(db)
    assert report["status"] == "skipped"


@pytest.mark.asyncio
async def test_builder_no_stocks():
    db = MagicMock()
    db.list_theme_nodes = AsyncMock(return_value=[{"theme_code": "test", "theme_name": "Test"}])
    db.list_stock_universe = AsyncMock(return_value=[])
    db.list_company_mainbz = AsyncMock(return_value=[])
    builder = ThemeExposureBuilder()
    report = await builder.build(db)
    assert report["status"] == "skipped"


def test_keyword_match():
    from strategy_factory.application.research.theme_exposure_builder import _keyword_match_score
    assert _keyword_match_score("中国石油天然气", ["石油", "天然气"]) == 1.0
    assert _keyword_match_score("贵州茅台", ["石油", "天然气"]) == 0.0
    assert _keyword_match_score("", ["石油"]) == 0.0
