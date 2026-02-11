# -*- coding: utf-8 -*-
"""
TdxQuant 集成测试脚本

测试 akshare-mcp 项目中 TdxQuant 数据源的集成功能

运行前提：
1. 通达信客户端已启动
2. TDX_PLUGIN_PATH 配置正确
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'akshare-mcp', 'src'))

# 手动加载 .env 文件
def load_env_file(env_path):
    """简单的 .env 文件加载器"""
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'akshare-mcp', '.env')
load_env_file(env_path)


def test_tdx_availability():
    """测试1: TdxQuant 可用性检查"""
    print("\n" + "="*60)
    print("测试1: TdxQuant 可用性检查")
    print("="*60)
    
    from akshare_mcp.data_source import data_source
    
    available = data_source.is_tdx_available()
    print(f"TdxQuant 可用: {available}")
    
    if available:
        tq = data_source.get_tdxquant()
        print(f"TdxQuant 模块: {tq}")
        print("✅ TdxQuant 初始化成功")
    else:
        print("❌ TdxQuant 不可用，请检查通达信客户端是否启动")
    
    return available


def test_realtime_quote():
    """测试2: 实时行情获取"""
    print("\n" + "="*60)
    print("测试2: 实时行情获取 (TdxQuant 优先)")
    print("="*60)
    
    from akshare_mcp.data_source import data_source
    
    test_codes = ["600519", "000001", "300750"]
    
    for code in test_codes:
        print(f"\n--- 获取 {code} 实时行情 ---")
        result = data_source.get_realtime_quote(code)
        if result:
            print(f"  代码: {result.get('code')}")
            print(f"  名称: {result.get('name')}")
            print(f"  价格: {result.get('price')}")
            print(f"  涨跌: {result.get('change')}")
            print(f"  涨跌幅: {result.get('changePercent')}%")
            print(f"  数据源: {result.get('source')}")
            if result.get('source') == 'tdxquant':
                print("  ✅ 使用 TdxQuant 数据源")
            else:
                print(f"  ⚠️ 降级到 {result.get('source')} 数据源")
        else:
            print(f"  ❌ 获取失败")


def test_kline_data():
    """测试3: K线数据获取"""
    print("\n" + "="*60)
    print("测试3: K线数据获取 (TdxQuant 支持分钟级)")
    print("="*60)
    
    from akshare_mcp.data_source import data_source
    
    test_cases = [
        ("600519", "daily", 5),
        ("600519", "5m", 10),
        ("000001", "1m", 10),
    ]
    
    for code, period, limit in test_cases:
        print(f"\n--- 获取 {code} {period} K线 (最近{limit}条) ---")
        result = data_source.get_kline(code, period, limit)
        if result:
            print(f"  获取到 {len(result)} 条数据")
            if result:
                first = result[0]
                last = result[-1]
                print(f"  首条: {first.get('date')} 收盘:{first.get('close')} 来源:{first.get('source')}")
                print(f"  末条: {last.get('date')} 收盘:{last.get('close')} 来源:{last.get('source')}")
                if first.get('source') == 'tdxquant':
                    print("  ✅ 使用 TdxQuant 数据源")
        else:
            print(f"  ❌ 获取失败")


def test_order_book():
    """测试4: 五档盘口获取"""
    print("\n" + "="*60)
    print("测试4: 五档盘口获取 (TdxQuant 优先)")
    print("="*60)
    
    from akshare_mcp.tools.market.order_book import get_order_book
    
    test_codes = ["600519", "000001"]
    
    for code in test_codes:
        print(f"\n--- 获取 {code} 五档盘口 ---")
        result = get_order_book(code)
        if result.get("success"):
            data = result.get("data", {})
            print(f"  代码: {data.get('code')}")
            print(f"  数据源: {data.get('source', 'unknown')}")
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            print(f"  买盘: {len(bids)} 档")
            for i, bid in enumerate(bids[:3]):
                print(f"    买{i+1}: 价格={bid.get('price')} 数量={bid.get('volume')}")
            print(f"  卖盘: {len(asks)} 档")
            for i, ask in enumerate(asks[:3]):
                print(f"    卖{i+1}: 价格={ask.get('price')} 数量={ask.get('volume')}")
            if data.get('source') == 'tdxquant':
                print("  ✅ 使用 TdxQuant 数据源")
        else:
            print(f"  ❌ 获取失败: {result.get('error')}")


def test_message_push():
    """测试5: 消息推送"""
    print("\n" + "="*60)
    print("测试5: 消息推送到通达信客户端")
    print("="*60)
    
    from akshare_mcp.tools.tdx_integration import push_message, is_tdx_available
    
    if not is_tdx_available():
        print("❌ TdxQuant 不可用，跳过消息推送测试")
        return
    
    message = "akshare-mcp 集成测试|TdxQuant 数据源已启用|测试时间: 2024"
    result = push_message(message)
    print(f"  发送结果: {result}")
    if result.get("success"):
        print("  ✅ 消息发送成功，请检查通达信客户端")
    else:
        print(f"  ❌ 消息发送失败: {result.get('message')}")


def test_financial_data():
    """测试6: 财务数据获取 (TdxQuant 584指标)"""
    print("\n" + "="*60)
    print("测试6: 财务数据获取 (TdxQuant 优先)")
    print("="*60)

    from akshare_mcp.tools.finance import get_financials

    test_codes = ["600519", "000001"]

    for code in test_codes:
        print(f"\n--- 获取 {code} 财务数据 ---")
        result = get_financials(code)
        if result.get("success"):
            data = result.get("data", {})
            print(f"  代码: {data.get('code')}")
            print(f"  报告期: {data.get('reportDate')}")
            print(f"  每股收益(EPS): {data.get('eps')}")
            print(f"  每股净资产(BVPS): {data.get('bvps')}")
            print(f"  净资产收益率(ROE): {data.get('roe')}%")
            print(f"  销售净利率: {data.get('netProfitMargin')}%")
            print(f"  资产负债率: {data.get('debtRatio')}%")
            print(f"  数据源: {data.get('source')}")
            if data.get('source') == 'tdxquant':
                print("  ✅ 使用 TdxQuant 数据源")
            else:
                print(f"  ⚠️ 降级到 {data.get('source')} 数据源")
        else:
            print(f"  ❌ 获取失败: {result.get('error')}")


def test_stock_info():
    """测试7: 股票基本信息获取"""
    print("\n" + "="*60)
    print("测试7: 股票基本信息获取 (TdxQuant)")
    print("="*60)

    from akshare_mcp.data_source import data_source

    if not data_source.is_tdx_available():
        print("❌ TdxQuant 不可用，跳过测试")
        return

    test_codes = ["600519", "000001"]

    for code in test_codes:
        print(f"\n--- 获取 {code} 基本信息 ---")
        result = data_source.get_stock_info_tdxquant(code)
        if result:
            print(f"  代码: {result.get('code')}")
            print(f"  名称: {result.get('name')}")
            print(f"  行业: {result.get('industry')}")
            print(f"  上市日期: {result.get('listDate')}")
            print(f"  总股本: {result.get('totalShares')}")
            print(f"  流通股本: {result.get('floatShares')}")
            print(f"  所属省份: {result.get('province')}")
            print(f"  是否沪深300: {result.get('belongHS300')}")
            print(f"  是否陆股通: {result.get('belongHSGT')}")
            print(f"  数据源: {result.get('source')}")
            print("  ✅ 获取成功")
        else:
            print(f"  ❌ 获取失败")


def test_sector_query():
    """测试8: 板块查询"""
    print("\n" + "="*60)
    print("测试8: 板块查询 (TdxQuant)")
    print("="*60)

    from akshare_mcp.data_source import data_source

    if not data_source.is_tdx_available():
        print("❌ TdxQuant 不可用，跳过测试")
        return

    # 测试获取板块列表
    print("\n--- 获取板块列表 ---")
    sector_list = data_source.get_sector_list_tdxquant()
    if sector_list:
        print(f"  获取到 {len(sector_list)} 个板块")
        print(f"  前5个板块: {sector_list[:5]}")
        print("  ✅ 获取成功")

        # 测试获取板块成分股
        if len(sector_list) > 0:
            test_sector = sector_list[0]
            print(f"\n--- 获取板块 {test_sector} 成分股 ---")
            stocks = data_source.get_stock_list_in_sector_tdxquant(test_sector)
            if stocks:
                print(f"  获取到 {len(stocks)} 只成分股")
                print(f"  前5只: {stocks[:5]}")
                print("  ✅ 获取成功")
            else:
                print("  ⚠️ 该板块无成分股或获取失败")
    else:
        print("  ❌ 获取板块列表失败")


def test_divid_factors():
    """测试9: 除权除息因子"""
    print("\n" + "="*60)
    print("测试9: 除权除息因子 (TdxQuant)")
    print("="*60)

    from akshare_mcp.data_source import data_source

    if not data_source.is_tdx_available():
        print("❌ TdxQuant 不可用，跳过测试")
        return

    test_codes = ["600519"]

    for code in test_codes:
        print(f"\n--- 获取 {code} 除权除息数据 ---")
        result = data_source.get_divid_factors_tdxquant(code)
        if result:
            print(f"  获取到 {len(result)} 条记录")
            for i, item in enumerate(result[:3]):
                print(f"  [{i+1}] 日期:{item.get('date')} 分红:{item.get('bonus')} 送股:{item.get('shareBonus')}")
            print("  ✅ 获取成功")
        else:
            print("  ⚠️ 无除权除息记录或获取失败")


def test_watchlist_management():
    """测试10: 自选股管理"""
    print("\n" + "="*60)
    print("测试10: 自选股管理 (TdxQuant)")
    print("="*60)

    from akshare_mcp.tools.tdx_integration import (
        is_tdx_available, create_watchlist, add_stocks_to_watchlist,
        delete_watchlist, get_user_sectors
    )

    if not is_tdx_available():
        print("❌ TdxQuant 不可用，跳过测试")
        return

    test_block_code = "TEST_MCP"
    test_block_name = "MCP测试板块"
    test_stocks = ["600519", "000001", "300750"]

    # 测试创建板块
    print(f"\n--- 创建板块 {test_block_name} ---")
    result = create_watchlist(test_block_code, test_block_name, test_stocks)
    print(f"  结果: {result}")
    if result.get("success"):
        print("  ✅ 创建成功")
    else:
        print(f"  ⚠️ 创建失败: {result.get('message')}")

    # 测试获取用户板块列表
    print("\n--- 获取用户板块列表 ---")
    result = get_user_sectors()
    print(f"  结果: {result}")
    if result.get("success"):
        print(f"  ✅ 获取到 {len(result.get('data', []))} 个板块")

    # 测试添加股票
    print(f"\n--- 向板块添加股票 ---")
    result = add_stocks_to_watchlist(test_block_code, ["002594", "601318"])
    print(f"  结果: {result}")
    if result.get("success"):
        print("  ✅ 添加成功")

    # 测试删除板块
    print(f"\n--- 删除测试板块 ---")
    result = delete_watchlist(test_block_code)
    print(f"  结果: {result}")
    if result.get("success"):
        print("  ✅ 删除成功")


def test_warn_push():
    """测试11: 预警推送"""
    print("\n" + "="*60)
    print("测试11: 预警推送 (TdxQuant)")
    print("="*60)

    from akshare_mcp.tools.tdx_integration import push_warn, is_tdx_available

    if not is_tdx_available():
        print("❌ TdxQuant 不可用，跳过测试")
        return

    print("\n--- 发送预警信号 ---")
    result = push_warn(
        stock_code="600519",
        price=1500.00,
        reason="MCP集成测试预警",
        bs_flag=2  # 未知
    )
    print(f"  结果: {result}")
    if result.get("success"):
        print("  ✅ 预警发送成功，请检查通达信客户端")
    else:
        print(f"  ❌ 预警发送失败: {result.get('message')}")


def main():
    """运行所有测试"""
    print("="*60)
    print("TdxQuant 集成测试 (完整版)")
    print("="*60)

    # 测试1: 可用性检查
    available = test_tdx_availability()

    if not available:
        print("\n⚠️ TdxQuant 不可用，部分测试将使用降级数据源")

    # 测试2: 实时行情
    test_realtime_quote()

    # 测试3: K线数据
    test_kline_data()

    # 测试4: 五档盘口
    test_order_book()

    # 测试5: 消息推送
    test_message_push()

    # 测试6: 财务数据 (新增)
    test_financial_data()

    # 测试7: 股票基本信息 (新增)
    test_stock_info()

    # 测试8: 板块查询 (新增)
    test_sector_query()

    # 测试9: 除权除息因子 (新增)
    test_divid_factors()

    # 测试10: 自选股管理 (新增)
    test_watchlist_management()

    # 测试11: 预警推送 (新增)
    test_warn_push()

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    main()

