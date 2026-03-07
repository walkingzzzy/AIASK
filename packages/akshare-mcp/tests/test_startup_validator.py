"""StartupValidator 单元测试

测试内容:
1. DB 不可达时降级运行
2. 核心表缺失时返回正确校验结果
3. K线新鲜度判断逻辑
4. 覆盖率阈值判断逻辑
5. 校验报告格式完整性
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date, timedelta

# get_db 在 startup_validator 内部通过 from ..storage import get_db 导入
# 但是是在方法内部 lazy import，所以需要 patch storage 模块
PATCH_GET_DB = "akshare_mcp.storage.get_db"


# ============================================================================
# Helpers
# ============================================================================

def _make_validator(**kwargs):
    """创建 StartupValidator 实例（绕过全局单例）"""
    from akshare_mcp.services.startup_validator import StartupValidator
    return StartupValidator(**kwargs)


def _make_healthy_mock_db(stock_count=500, latest_kline_date=None):
    """创建一个模拟的健康 DB 实例"""
    if latest_kline_date is None:
        latest_kline_date = datetime.now() - timedelta(days=1)

    mock_conn = AsyncMock()

    async def fake_fetchval(query, *args):
        if "MAX(time)" in query:
            return latest_kline_date
        if "information_schema" in query:
            return True
        if "COUNT" in query:
            return stock_count
        return 1

    mock_conn.fetchval = fake_fetchval
    mock_conn.execute = AsyncMock()

    mock_db = MagicMock()
    mock_db.initialize = AsyncMock()
    mock_db._init_tables = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=mock_ctx)

    return mock_db


# ============================================================================
# Test 1: DB 不可达
# ============================================================================

@pytest.mark.asyncio
async def test_db_unreachable_returns_degraded():
    """DB 连接失败时应返回 status=degraded，db_available=false"""
    validator = _make_validator(retry_count=1, retry_delay=0.1)

    mock_db = MagicMock()
    mock_db.initialize = AsyncMock(side_effect=ConnectionRefusedError("refused"))

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["db_available"] is False
    assert report["status"] == "degraded"
    assert report["details"]["db_connectivity"]["success"] is False


# ============================================================================
# Test 2: 核心表缺失时自动创建
# ============================================================================

@pytest.mark.asyncio
async def test_missing_tables_triggers_init():
    """缺失核心表时应尝试自动创建"""
    validator = _make_validator()

    mock_conn = AsyncMock()
    table_check_count = 0

    async def fake_fetchval(query, *args):
        nonlocal table_check_count
        if "information_schema" in query:
            table_check_count += 1
            # 前两张表存在，后两张不存在
            return table_check_count <= 2
        if "MAX(time)" in query:
            return datetime.now()
        if "COUNT" in query:
            return 500
        return 1

    mock_conn.fetchval = fake_fetchval
    mock_conn.execute = AsyncMock()

    mock_db = MagicMock()
    mock_db.initialize = AsyncMock()
    mock_db._init_tables = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.acquire = MagicMock(return_value=mock_ctx)

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["db_available"] is True
    # _init_tables 应被调用（因为有缺失表）
    mock_db._init_tables.assert_called_once()


# ============================================================================
# Test 3: K线新鲜度 — 数据过期
# ============================================================================

@pytest.mark.asyncio
async def test_stale_kline_data():
    """K线最新数据超过阈值天数则 data_stale=true"""
    validator = _make_validator(freshness_threshold_days=3)

    old_date = datetime.now() - timedelta(days=10)
    mock_db = _make_healthy_mock_db(latest_kline_date=old_date)

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["data_stale"] is True
    assert report["details"]["data_freshness"]["days_since_latest"] == 10


# ============================================================================
# Test 4: K线新鲜度 — 数据新鲜
# ============================================================================

@pytest.mark.asyncio
async def test_fresh_kline_data():
    """K线最新数据在阈值内则 data_stale=false"""
    validator = _make_validator(freshness_threshold_days=5)

    recent_date = datetime.now() - timedelta(days=1)
    mock_db = _make_healthy_mock_db(latest_kline_date=recent_date)

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["data_stale"] is False


# ============================================================================
# Test 5: 覆盖率不足
# ============================================================================

@pytest.mark.asyncio
async def test_low_coverage():
    """stocks 表记录数低于阈值时 coverage_low=true"""
    validator = _make_validator(coverage_min_stocks=100)

    mock_db = _make_healthy_mock_db(stock_count=50)

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["coverage_low"] is True
    assert report["details"]["coverage"]["stock_count"] == 50


# ============================================================================
# Test 6: 全部通过 → healthy
# ============================================================================

@pytest.mark.asyncio
async def test_all_checks_pass():
    """所有检查通过时 status=healthy"""
    validator = _make_validator(freshness_threshold_days=5, coverage_min_stocks=100)

    mock_db = _make_healthy_mock_db(stock_count=500)

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    assert report["status"] == "healthy"
    assert report["db_available"] is True
    assert report["tables_ok"] is True
    assert report["data_stale"] is False
    assert report["coverage_low"] is False


# ============================================================================
# Test 7: 校验报告格式
# ============================================================================

@pytest.mark.asyncio
async def test_report_has_required_fields():
    """校验报告必须包含所有必需字段"""
    validator = _make_validator(retry_count=1, retry_delay=0.1)

    mock_db = MagicMock()
    mock_db.initialize = AsyncMock(side_effect=Exception("test error"))

    with patch(PATCH_GET_DB, return_value=mock_db):
        report = await validator._run_all_checks()

    required_keys = {"timestamp", "db_available", "tables_ok", "data_stale", "coverage_low", "details", "status"}
    assert required_keys.issubset(report.keys()), f"Missing keys: {required_keys - report.keys()}"
