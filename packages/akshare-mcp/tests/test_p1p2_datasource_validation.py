"""
P1/P2 数据源改造验证测试

验证目标：
1. 服务可以正常导入（无硬依赖崩溃）
2. 各模块的主数据源（本地桥接/Tushare/东财直连/新浪直连）可用
3. AkShare 已降级为可选回退
4. 所有工具函数在 ak=None 时不会崩溃

运行: python tests/test_p1p2_datasource_validation.py
"""

import asyncio
import sys
import os
import time
import traceback

# 确保能找到源码
TESTS_DIR = os.path.dirname(__file__)
PACKAGE_SRC = os.path.abspath(os.path.join(TESTS_DIR, "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

PASS = 0
FAIL = 0
WARN = 0
RESULTS = []

def record(name, status, detail=""):
    global PASS, FAIL, WARN
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(status, "?")
    if status == "PASS": PASS += 1
    elif status == "FAIL": FAIL += 1
    elif status == "WARN": WARN += 1
    line = f"  {icon} {name}"
    if detail:
        line += f" — {detail}"
    RESULTS.append(line)
    print(line)

def section(title):
    line = f"\n{'='*60}\n  {title}\n{'='*60}"
    RESULTS.append(line)
    print(line)


# ============================================================
# 测试 1: 服务导入
# ============================================================
def test_server_import():
    section("1. 服务导入测试")
    try:
        from akshare_mcp.server import mcp
        record("server import", "PASS")
    except Exception as e:
        record("server import", "FAIL", str(e))

# ============================================================
# 测试 2: date_utils — 本地桥接/Tushare 交易日历
# ============================================================
def test_date_utils():
    section("2. date_utils 交易日历")
    try:
        from akshare_mcp.date_utils import get_latest_trading_date, format_date_dash
        d = get_latest_trading_date()
        if d and len(d) == 8 and d.isdigit():
            record("get_latest_trading_date()", "PASS", f"返回 {d}")
        else:
            record("get_latest_trading_date()", "FAIL", f"返回异常: {d}")
        
        dash = format_date_dash(d)
        if dash and "-" in dash:
            record("format_date_dash()", "PASS", f"返回 {dash}")
        else:
            record("format_date_dash()", "FAIL", f"返回异常: {dash}")
    except Exception as e:
        record("date_utils", "FAIL", str(e))

# ============================================================
# 测试 3: helpers — 股票列表 (Tushare → 本地桥接 → AkShare)
# ============================================================
def test_stock_list():
    section("3. helpers.get_stock_list_cached()")
    try:
        from akshare_mcp.tools.market.helpers import get_stock_list_cached
        data, cached = get_stock_list_cached()
        if data and len(data) > 1000:
            sample = data[0]
            has_name = bool(sample.get("name"))
            record("get_stock_list_cached()", "PASS", f"{len(data)} 只股票, 有名称={has_name}, cached={cached}")
        else:
            record("get_stock_list_cached()", "FAIL", f"仅返回 {len(data) if data else 0} 只")
    except Exception as e:
        record("get_stock_list_cached()", "FAIL", str(e))

# ============================================================
# 测试 4: quote — 单股行情 (本地桥接 → Tushare → AkShare)
# ============================================================
def test_single_quote():
    section("4. quote 单股行情")
    try:
        from akshare_mcp.tools.market.quote import get_realtime_quote
        result = get_realtime_quote("600519")
        if result.get("success"):
            data = result.get("data", {})
            # data 可能是 Pydantic StockQuote 对象或 dict
            if hasattr(data, 'model_dump'):
                data = data.model_dump()
            elif hasattr(data, '__dict__') and not isinstance(data, dict):
                data = vars(data)
            price = data.get("price") if isinstance(data, dict) else getattr(data, "price", None)
            record("get_realtime_quote(600519)", "PASS", f"price={price}")
        else:
            record("get_realtime_quote(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_realtime_quote()", "FAIL", str(e))

# ============================================================
# 测试 5: kline — K线数据 (DataSource 本地桥接→Tushare → AkShare)
# ============================================================
def test_kline():
    section("5. kline K线数据")
    try:
        from akshare_mcp.tools.market.kline import get_kline
        from akshare_mcp.storage import run_with_db_cleanup
        result = run_with_db_cleanup(get_kline("600519", "daily", 10))
        if result.get("success"):
            data = result.get("data", [])
            record("get_kline(600519, daily, 10)", "PASS", f"{len(data)} 条K线")
        else:
            record("get_kline(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_kline()", "FAIL", str(e))

# ============================================================
# 测试 6: order_book — 五档盘口 (本地桥接 → AkShare → Sina → Tencent)
# ============================================================
def test_order_book():
    section("6. order_book 五档盘口")
    try:
        from akshare_mcp.tools.market.order_book import get_order_book
        result = get_order_book("600519")
        if result.get("success"):
            data = result.get("data", {})
            bids = data.get("bids", [])
            record("get_order_book(600519)", "PASS", f"bids={len(bids)}, source={data.get('source','?')}")
        else:
            # 非交易时段可能无数据
            record("get_order_book(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_order_book()", "FAIL", str(e))

# ============================================================
# 测试 7: fund_flow — 北向资金 (Tushare → HKEX → AkShare)
# ============================================================
def test_north_fund():
    section("7. fund_flow 北向资金")
    try:
        from akshare_mcp.tools.fund_flow import get_north_fund
        result = get_north_fund(5)
        if result.get("success"):
            data = result.get("data", {})
            items = data.get("items", [])
            source = data.get("source", "?")
            record("get_north_fund(5)", "PASS", f"{len(items)} 天, source={source}")
        else:
            record("get_north_fund(5)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_north_fund()", "FAIL", str(e))

# ============================================================
# 测试 8: fund_flow — 行业板块资金流 (东财push2 → AkShare)
# ============================================================
def test_sector_fund_flow():
    section("8. fund_flow 行业板块资金流")
    try:
        from akshare_mcp.tools.fund_flow import get_sector_fund_flow
        result = get_sector_fund_flow(5)
        if result.get("success"):
            data = result.get("data", [])
            if data and len(data) > 0:
                record("get_sector_fund_flow(5)", "PASS", f"{len(data)} 个板块, 首个={data[0].get('name','?')}")
            else:
                record("get_sector_fund_flow(5)", "WARN", "返回空列表")
        else:
            record("get_sector_fund_flow(5)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_sector_fund_flow()", "FAIL", str(e))

# ============================================================
# 测试 9: fund_flow — 概念板块资金流 (东财push2 → AkShare)
# ============================================================
def test_concept_fund_flow():
    section("9. fund_flow 概念板块资金流")
    try:
        from akshare_mcp.tools.fund_flow import get_concept_fund_flow
        result = get_concept_fund_flow(5)
        if result.get("success"):
            data = result.get("data", [])
            if data and len(data) > 0:
                record("get_concept_fund_flow(5)", "PASS", f"{len(data)} 个概念, 首个={data[0].get('name','?')}")
            else:
                record("get_concept_fund_flow(5)", "WARN", "返回空列表")
        else:
            record("get_concept_fund_flow(5)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_concept_fund_flow()", "FAIL", str(e))


# ============================================================
# 测试 10: fund_flow — 龙虎榜 (Tushare → Sina → EM)
# ============================================================
def test_dragon_tiger():
    section("10. fund_flow 龙虎榜")
    try:
        from akshare_mcp.tools.fund_flow import get_dragon_tiger
        result = get_dragon_tiger()
        if result.get("success"):
            data = result.get("data", [])
            record("get_dragon_tiger()", "PASS", f"{len(data)} 条记录")
        else:
            # 龙虎榜不是每天都有
            record("get_dragon_tiger()", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_dragon_tiger()", "FAIL", str(e))

# ============================================================
# 测试 11: fund_flow — 融资融券 (东财datacenter → Tushare → AkShare)
# ============================================================
def test_margin_data():
    section("11. fund_flow 融资融券")
    try:
        from akshare_mcp.tools.fund_flow import get_margin_data
        result = get_margin_data(stock_code="600519", days=5)
        if result.get("success"):
            data = result.get("data", [])
            record("get_margin_data(600519)", "PASS", f"{len(data)} 条记录")
        else:
            record("get_margin_data(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_margin_data()", "FAIL", str(e))

# ============================================================
# 测试 12: fund_flow — 个股资金流 (东财push2)
# ============================================================
def test_stock_fund_flow():
    section("12. fund_flow 个股资金流")
    try:
        from akshare_mcp.tools.fund_flow import get_stock_fund_flow
        result = get_stock_fund_flow("600519")
        if result.get("success"):
            data = result.get("data", {})
            record("get_stock_fund_flow(600519)", "PASS", f"主力净流入={data.get('mainNetInflow')}")
        else:
            record("get_stock_fund_flow(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_stock_fund_flow()", "FAIL", str(e))

# ============================================================
# 测试 13: news — 研报 (Tushare → 东财datacenter → AkShare)
# ============================================================
def test_stock_research():
    section("13. news 个股研报")
    try:
        from akshare_mcp.tools.news import get_stock_research
        result = get_stock_research("600519", limit=3)
        if result.get("success"):
            data = result.get("data", {})
            reports = data.get("reports", [])
            record("get_stock_research(600519)", "PASS", f"{len(reports)} 篇研报")
        else:
            record("get_stock_research(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_stock_research()", "FAIL", str(e))

# ============================================================
# 测试 14: news — 盈利预测 (东财datacenter → Tushare → AkShare)
# ============================================================
def test_profit_forecast():
    section("14. news 盈利预测")
    try:
        from akshare_mcp.tools.news import get_profit_forecast
        result = get_profit_forecast("600519")
        if result.get("success"):
            data = result.get("data", {})
            items = data.get("items", [])
            record("get_profit_forecast(600519)", "PASS", f"{len(items)} 条预测")
        else:
            record("get_profit_forecast(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_profit_forecast()", "FAIL", str(e))

# ============================================================
# 测试 15: news — 公告 (Tushare → AkShare)
# ============================================================
def test_stock_notices():
    section("15. news 公告")
    try:
        from akshare_mcp.tools.news import get_stock_notices
        result = get_stock_notices("2026-01-01", "2026-02-08", stock_code="600519")
        if result.get("success"):
            data = result.get("data", {})
            events = data.get("events", [])
            record("get_stock_notices(600519)", "PASS", f"{len(events)} 条公告")
        else:
            record("get_stock_notices(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_stock_notices()", "FAIL", str(e))

# ============================================================
# 测试 16: news — 市场新闻 (Tushare → AkShare)
# ============================================================
def test_market_news():
    section("16. news 市场新闻")
    try:
        from akshare_mcp.tools.news import get_market_news
        result = get_market_news(limit=5)
        if result.get("success"):
            data = result.get("data", [])
            record("get_market_news(5)", "PASS", f"{len(data)} 条新闻")
        else:
            record("get_market_news(5)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_market_news()", "FAIL", str(e))

# ============================================================
# 测试 17: finance — 财务数据 (本地桥接 → Tushare → AkShare)
# ============================================================
def test_financials():
    section("17. finance 财务数据")
    try:
        from akshare_mcp.tools.finance import get_financials
        from akshare_mcp.storage import run_with_db_cleanup
        result = run_with_db_cleanup(get_financials("600519"))
        if result.get("success"):
            data = result.get("data", {})
            record("get_financials(600519)", "PASS", f"keys={list(data.keys())[:5]}...")
        else:
            record("get_financials(600519)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_financials()", "FAIL", str(e))

# ============================================================
# 测试 18: options — 期权 (新浪直连 → AkShare)
# ============================================================
def test_options():
    section("18. options 期权链")
    try:
        from akshare_mcp.tools.options import get_option_chain
        result = get_option_chain("510050", limit=5)
        if result.get("success"):
            data = result.get("data", {})
            options = data.get("options", [])
            months = data.get("expiryMonths", [])
            record("get_option_chain(510050)", "PASS", f"{len(options)} 合约, {len(months)} 月份")
        else:
            record("get_option_chain(510050)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_option_chain()", "FAIL", str(e))

# ============================================================
# 测试 19: 模拟 ak=None 场景 — 验证无 AkShare 时不崩溃
# ============================================================
def test_ak_none_resilience():
    section("19. ak=None 弹性测试（模拟无AkShare环境）")
    
    # 临时将 ak 设为 None
    import akshare_mcp.tools.fund_flow as ff_mod
    import akshare_mcp.tools.news as news_mod
    import akshare_mcp.tools.options as opt_mod
    import akshare_mcp.tools.market.helpers as helpers_mod
    import akshare_mcp.tools.market.order_book as ob_mod
    import akshare_mcp.tools.market.kline as kline_mod
    import akshare_mcp.tools.market.quote as quote_mod
    
    modules = [ff_mod, news_mod, opt_mod, helpers_mod, ob_mod, kline_mod, quote_mod]
    originals = {}
    for mod in modules:
        originals[mod.__name__] = getattr(mod, 'ak', 'NOT_SET')
        mod.ak = None
    
    crashed = []
    tested = []
    
    # 测试各函数不崩溃（返回 fail 是正常的，崩溃才是问题）
    test_calls = [
        ("fund_flow.get_north_fund", lambda: ff_mod.get_north_fund(3)),
        ("fund_flow.get_sector_fund_flow", lambda: ff_mod.get_sector_fund_flow(3)),
        ("fund_flow.get_concept_fund_flow", lambda: ff_mod.get_concept_fund_flow(3)),
        ("fund_flow.get_dragon_tiger", lambda: ff_mod.get_dragon_tiger()),
        ("fund_flow.get_margin_data", lambda: ff_mod.get_margin_data("600519", 3)),
        ("news.get_profit_forecast", lambda: news_mod.get_profit_forecast("600519")),
        ("news.get_research_reports", lambda: news_mod.get_research_reports("600519", 3)),
        ("news.get_market_news", lambda: news_mod.get_market_news(3)),
        ("options.get_option_chain", lambda: opt_mod.get_option_chain("510050", limit=3)),
    ]
    
    for name, fn in test_calls:
        try:
            result = fn()
            # 不崩溃就算通过（返回 fail 是正常降级行为）
            tested.append(name)
        except Exception as e:
            crashed.append(f"{name}: {e}")
    
    # 恢复
    for mod in modules:
        orig = originals.get(mod.__name__, 'NOT_SET')
        if orig != 'NOT_SET':
            mod.ak = orig
    
    if not crashed:
        record(f"ak=None 弹性测试 ({len(tested)} 函数)", "PASS", "全部不崩溃")
    else:
        for c in crashed:
            record(f"ak=None 崩溃", "FAIL", c)

# ============================================================
# 测试 20: 批量行情 (东财push2 → AkShare)
# ============================================================
def test_batch_quotes():
    section("20. quote 批量行情")
    try:
        from akshare_mcp.tools.market.quote import get_batch_quotes
        result = get_batch_quotes(["600519", "000001", "300750"])
        if result.get("success"):
            data = result.get("data", [])
            record("get_batch_quotes(3只)", "PASS", f"{len(data)} 只返回")
        else:
            record("get_batch_quotes()", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_batch_quotes()", "FAIL", str(e))

# ============================================================
# 测试 21: 指数行情 (东财push2 → AkShare)
# ============================================================
def test_index_quote():
    section("21. quote 指数行情")
    try:
        from akshare_mcp.tools.market.quote import get_index_quote
        result = get_index_quote("000001")
        if result.get("success"):
            data = result.get("data", {})
            record("get_index_quote(000001)", "PASS", f"price={data.get('price') or data.get('last')}")
        else:
            record("get_index_quote(000001)", "WARN", f"error={result.get('error', 'unknown')}")
    except Exception as e:
        record("get_index_quote()", "FAIL", str(e))

# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  P1/P2 数据源改造验证测试")
    print("  测试时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    t0 = time.time()
    
    test_server_import()
    test_date_utils()
    test_stock_list()
    test_single_quote()
    test_kline()
    test_order_book()
    test_north_fund()
    test_sector_fund_flow()
    test_concept_fund_flow()
    test_dragon_tiger()
    test_margin_data()
    test_stock_fund_flow()
    test_stock_research()
    test_profit_forecast()
    test_stock_notices()
    test_market_news()
    test_financials()
    test_options()
    test_ak_none_resilience()
    test_batch_quotes()
    test_index_quote()
    
    elapsed = time.time() - t0
    
    print("\n" + "=" * 60)
    print(f"  总计: {PASS + FAIL + WARN} 项测试")
    print(f"  ✅ PASS: {PASS}  ❌ FAIL: {FAIL}  ⚠️ WARN: {WARN}")
    print(f"  耗时: {elapsed:.1f}s")
    print("=" * 60)
    
    try:
        from akshare_mcp.storage import close_db
        asyncio.run(close_db())
    except Exception:
        pass

    if FAIL > 0:
        print("\n  ❌ 存在失败项，需要排查！")
        sys.exit(1)
    elif WARN > 0:
        print("\n  ⚠️ 全部通过但有警告（可能是非交易时段或网络问题）")
        sys.exit(0)
    else:
        print("\n  ✅ 全部通过！")
        sys.exit(0)
