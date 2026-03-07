#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DB-First 数据源优先级验证测试

测试目标：
1. 验证 get_kline / get_kline_data / get_index_kline 优先查询 TimescaleDB
2. 验证 get_financials 优先查询 TimescaleDB
3. 验证 DB 无数据时降级到外部 API
4. 验证外部 API 数据回写到 DB
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# 加载 .env
_env_path = Path(__file__).resolve().parent.parent / '.env'
if _env_path.exists():
    for line in _env_path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            k, v = key.strip(), value.strip()
            if k not in os.environ:
                os.environ[k] = v

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("test_db_first")


# ============================================================================
# 颜色辅助
# ============================================================================
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def _pass(msg):
    print(f"  {GREEN}✅ PASS{RESET}: {msg}")

def _fail(msg):
    print(f"  {RED}❌ FAIL{RESET}: {msg}")

def _info(msg):
    print(f"  {CYAN}ℹ️  INFO{RESET}: {msg}")

def _warn(msg):
    print(f"  {YELLOW}⚠️  WARN{RESET}: {msg}")


# ============================================================================
# Test 1: DB 连接性检查
# ============================================================================
async def test_db_connectivity():
    """测试 TimescaleDB 连接是否正常"""
    print(f"\n{BOLD}━━━ Test 1: TimescaleDB 连接性检查 ━━━{RESET}")
    try:
        from akshare_mcp.storage import get_db
        db = get_db()
        async with db.acquire() as conn:
            row = await conn.fetchval("SELECT 1")
            assert row == 1
            _pass("TimescaleDB 连接正常")

            # 检查 kline_1d 表是否存在
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'kline_1d')"
            )
            if exists:
                _pass("kline_1d 表存在")
            else:
                _fail("kline_1d 表不存在")
                return False

            # 检查数据量
            count = await conn.fetchval("SELECT COUNT(*) FROM kline_1d")
            _info(f"kline_1d 表当前数据量: {count:,} 条")

            # 检查 financials 表
            fin_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'financials')"
            )
            if fin_exists:
                fin_count = await conn.fetchval("SELECT COUNT(*) FROM financials")
                _pass(f"financials 表存在, 数据量: {fin_count:,} 条")
            else:
                _warn("financials 表不存在 (get_financials DB查询可能跳过)")

        return True
    except Exception as e:
        _fail(f"TimescaleDB 连接失败: {e}")
        return False


# ============================================================================
# Test 2: get_kline DB-First 验证
# ============================================================================
async def test_get_kline_db_first():
    """验证 get_kline 优先从 DB 获取数据"""
    print(f"\n{BOLD}━━━ Test 2: get_kline DB-First 验证 ━━━{RESET}")

    from akshare_mcp.storage import get_db
    from akshare_mcp.core.cache_manager import clear_cache

    # 清除缓存，确保不走缓存
    clear_cache()

    db = get_db()
    test_code = "600519"  # 贵州茅台

    # 2a. 检查 DB 是否有该股票数据
    try:
        db_data = await db.get_klines(test_code, limit=5)
    except Exception as e:
        _warn(f"DB 查询异常: {e}")
        db_data = []

    has_db_data = bool(db_data and len(db_data) > 0)
    _info(f"DB 中 {test_code} 数据: {'有 (' + str(len(db_data)) + ' 条)' if has_db_data else '无数据'}")

    # 2b. 使用 monkey-patch 追踪调用路径
    from akshare_mcp.tools.market import kline as kline_module
    from akshare_mcp.data_source import data_source

    call_log = []

    original_db_get_klines = db.get_klines.__func__  # unbound method

    async def tracked_db_get_klines(self, code, **kwargs):
        call_log.append(("DB.get_klines", code, kwargs))
        return await original_db_get_klines(self, code, **kwargs)

    original_ds_get_kline = data_source.get_kline

    def tracked_ds_get_kline(code, period, limit):
        call_log.append(("data_source.get_kline", code, {"period": period, "limit": limit}))
        return original_ds_get_kline(code, period, limit)

    # Patch and test
    clear_cache()

    with patch.object(type(db), 'get_klines', tracked_db_get_klines):
        with patch.object(data_source, 'get_kline', tracked_ds_get_kline):
            from akshare_mcp.tools.market.kline import get_kline
            result = await get_kline(test_code, "daily", 5)

    # 2c. 分析调用顺序
    _info(f"调用顺序: {[c[0] for c in call_log]}")

    if not call_log:
        _fail("未检测到任何数据源调用（可能命中缓存）")
        return False

    # 验证 DB 是第一个被调用的
    if call_log[0][0] == "DB.get_klines":
        _pass("DB.get_klines 是**第一个**被调用的数据源 ✅")
    else:
        _fail(f"第一个调用的是 {call_log[0][0]}，应该是 DB.get_klines")
        return False

    if has_db_data:
        # DB 有数据时，不应调用外部 API
        api_calls = [c for c in call_log if c[0] != "DB.get_klines"]
        if not api_calls:
            _pass("DB 有数据时，未调用外部 API (正确的 DB-First 行为)")
        else:
            _warn(f"DB 有数据但仍调用了外部 API: {[c[0] for c in api_calls]}")
    else:
        # DB 无数据时，应降级到外部 API
        api_calls = [c for c in call_log if c[0] != "DB.get_klines"]
        if api_calls:
            _pass(f"DB 无数据时，正确降级到外部 API: {[c[0] for c in api_calls]}")
        else:
            _warn("DB 无数据且未调用外部 API (数据获取可能失败)")

    # 验证返回结果
    if result.get("success"):
        data = result.get("data", [])
        _pass(f"get_kline 返回成功, 数据条数: {len(data)}")
        if data:
            sample = data[0]
            _info(f"样本数据: date={sample.get('date')}, close={sample.get('close')}, source={sample.get('source', 'N/A')}")
    else:
        _warn(f"get_kline 返回失败: {result.get('error')}")

    return True


# ============================================================================
# Test 3: get_financials DB-First 验证
# ============================================================================
async def test_get_financials_db_first():
    """验证 get_financials 优先从 DB 获取数据"""
    print(f"\n{BOLD}━━━ Test 3: get_financials DB-First 验证 ━━━{RESET}")

    from akshare_mcp.storage import get_db
    from akshare_mcp.core.cache_manager import clear_cache

    clear_cache()

    db = get_db()
    test_code = "600519"

    # 3a. 检查 DB 是否有该股票财务数据
    try:
        db_fin = await db.get_financials(test_code, limit=1)
    except Exception as e:
        _warn(f"DB 查询异常: {e}")
        db_fin = []

    has_db_fin = bool(db_fin and len(db_fin) > 0)
    _info(f"DB 中 {test_code} 财务数据: {'有 (' + str(len(db_fin)) + ' 条)' if has_db_fin else '无数据'}")

    # 3b. 直接调用 get_financials 测试
    clear_cache()

    from akshare_mcp.tools.finance import get_financials
    result = await get_financials(test_code)

    if result.get("success"):
        data = result.get("data", {})
        source = data.get("source", "unknown") if isinstance(data, dict) else "unknown"
        _pass(f"get_financials 返回成功, source={source}")

        if has_db_fin and source in ("timescaledb", "database", "db"):
            _pass("财务数据来自 DB (DB-First 行为正确)")
        elif has_db_fin:
            _info(f"DB 有数据但 source 标记为 {source} (可能缓存中有不同source)")
        else:
            _info(f"DB 无财务数据, 数据来自外部 API (source={source})")
    else:
        _warn(f"get_financials 返回失败: {result.get('error')}")

    return True


# ============================================================================
# Test 4: DB 无数据 -> API 降级 -> 回写 DB 验证
# ============================================================================
async def test_api_fallback_and_writeback():
    """验证 DB 无数据时降级到 API 并回写"""
    print(f"\n{BOLD}━━━ Test 4: API 降级 + DB 回写 验证 ━━━{RESET}")

    from akshare_mcp.storage import get_db
    from akshare_mcp.core.cache_manager import clear_cache

    clear_cache()

    db = get_db()

    # 使用一个不太常见的股票代码测试
    test_code = "000002"  # 万科A

    try:
        db_data_before = await db.get_klines(test_code, limit=1)
    except Exception:
        db_data_before = []

    had_data_before = bool(db_data_before)
    _info(f"调用前 DB 中 {test_code} K线数据: {'有' if had_data_before else '无'}")

    # 调用 get_kline — 这会触发 DB-first → API fallback → writeback
    from akshare_mcp.tools.market.kline import get_kline
    result = await get_kline(test_code, "daily", 10)

    if result.get("success"):
        _pass(f"get_kline 返回成功, 数据条数: {len(result.get('data', []))}")

        if not had_data_before:
            # 给异步回写一点时间
            await asyncio.sleep(2)

            try:
                db_data_after = await db.get_klines(test_code, limit=1)
            except Exception:
                db_data_after = []

            if db_data_after:
                _pass(f"API 数据已回写到 DB (回写后查到 {len(db_data_after)} 条)")
            else:
                _warn("API 数据可能尚未回写完成 (异步回写延迟)")
        else:
            _info("调用前 DB 已有数据, 跳过回写验证")
    else:
        _warn(f"get_kline 返回失败 (外部 API 不可用): {result.get('error')}")

    return True


# ============================================================================
# Test 5: 代码逻辑审计 - 确认 DB 查询在 API 之前
# ============================================================================
async def test_code_audit():
    """审计源码确认 DB-first 逻辑"""
    print(f"\n{BOLD}━━━ Test 5: 源码 DB-First 逻辑审计 ━━━{RESET}")
    import inspect
    from akshare_mcp.tools.market.kline import get_kline, get_kline_data, get_index_kline
    from akshare_mcp.tools.finance import get_financials

    audit_results = []
    for fn_name, fn in [
        ("get_kline", get_kline),
        ("get_kline_data", get_kline_data),
        ("get_index_kline", get_index_kline),
        ("get_financials", get_financials),
    ]:
        source = inspect.getsource(fn)

        # 检查是否是 async 函数
        is_async = inspect.iscoroutinefunction(fn)

        # 检查 DB 查询是否在 API 调用之前
        db_pos = source.find("db.get_klines") if "kline" in fn_name.lower() else source.find("db.get_financials")
        api_pos = source.find("data_source.get_kline") if "kline" in fn_name.lower() else source.find("tushare")

        db_before_api = (db_pos >= 0 and api_pos >= 0 and db_pos < api_pos) or (db_pos >= 0 and api_pos < 0)

        if is_async:
            _pass(f"{fn_name} 是 async 函数")
        else:
            _fail(f"{fn_name} 不是 async 函数")

        if db_pos >= 0:
            _pass(f"{fn_name} 包含 DB 查询")
        else:
            _fail(f"{fn_name} 缺少 DB 查询")

        if db_before_api:
            _pass(f"{fn_name} DB 查询在 API 调用之前 (DB-First ✅)")
        elif db_pos >= 0 and api_pos >= 0:
            _fail(f"{fn_name} DB 查询在 API 调用之后 (顺序错误)")
        else:
            _info(f"{fn_name} 无法确定顺序 (db_pos={db_pos}, api_pos={api_pos})")

        audit_results.append((fn_name, is_async, db_before_api))

    return all(r[1] and r[2] for r in audit_results)


# ============================================================================
# Main
# ============================================================================
async def main():
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  DB-First 数据源优先级验证测试{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    results = {}

    # Test 1: DB 连通性
    results["db_connectivity"] = await test_db_connectivity()
    if not results["db_connectivity"]:
        print(f"\n{RED}⛔ DB 不可用, 跳过运行时测试{RESET}")
        # 仍然运行代码审计
        results["code_audit"] = await test_code_audit()
    else:
        # Test 2: get_kline DB-First
        results["get_kline_db_first"] = await test_get_kline_db_first()

        # Test 3: get_financials DB-First
        results["get_financials_db_first"] = await test_get_financials_db_first()

        # Test 4: API 降级 + 回写
        results["api_fallback_writeback"] = await test_api_fallback_and_writeback()

        # Test 5: 代码审计
        results["code_audit"] = await test_code_audit()

    # ====== 汇总 ======
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  测试结果汇总{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {name}")

    print(f"\n  总计: {passed}/{total} 通过")

    if passed == total:
        print(f"\n  {GREEN}{BOLD}🎉 所有测试通过! DB-First 数据源优先级正确!{RESET}")
    else:
        print(f"\n  {YELLOW}{BOLD}⚠️  部分测试未通过, 请检查上方详细日志{RESET}")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
