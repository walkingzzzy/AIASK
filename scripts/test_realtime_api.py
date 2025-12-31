#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试实时数据接口
验证五档盘口和成交明细是否能获取真实数据
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sina_orderbook():
    """测试新浪五档盘口数据"""
    print("\n=== 测试新浪五档盘口数据 ===")
    try:
        from packages.core.realtime.data_source.sina_realtime import SinaRealtimeAdapter
        
        sina = SinaRealtimeAdapter()
        
        # 测试贵州茅台
        stock_code = "600519"
        quote = sina.get_realtime_quote(stock_code)
        
        if quote:
            print(f"股票: {quote.get('name')} ({stock_code})")
            print(f"当前价: {quote.get('current')}")
            print(f"涨跌幅: {quote.get('change_pct'):.2f}%")
            print("\n买盘五档:")
            for i in range(1, 6):
                price = quote.get(f'bid{i}_price', 0)
                volume = quote.get(f'bid{i}_volume', 0)
                print(f"  买{i}: {price:.2f} x {volume}")
            print("\n卖盘五档:")
            for i in range(1, 6):
                price = quote.get(f'ask{i}_price', 0)
                volume = quote.get(f'ask{i}_volume', 0)
                print(f"  卖{i}: {price:.2f} x {volume}")
            return True
        else:
            print("获取数据失败")
            return False
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tencent_orderbook():
    """测试腾讯五档盘口数据"""
    print("\n=== 测试腾讯五档盘口数据 ===")
    try:
        from packages.core.realtime.data_source.tencent_realtime import TencentRealtimeAdapter
        
        tencent = TencentRealtimeAdapter()
        
        # 测试平安银行
        stock_code = "000001"
        quote = tencent.get_realtime_quote(stock_code)
        
        if quote:
            print(f"股票: {quote.get('name')} ({stock_code})")
            print(f"当前价: {quote.get('current')}")
            print(f"涨跌幅: {quote.get('change_pct'):.2f}%")
            print("\n买盘五档:")
            for i in range(1, 6):
                price = quote.get(f'bid{i}_price', 0)
                volume = quote.get(f'bid{i}_volume', 0)
                print(f"  买{i}: {price:.2f} x {volume}")
            print("\n卖盘五档:")
            for i in range(1, 6):
                price = quote.get(f'ask{i}_price', 0)
                volume = quote.get(f'ask{i}_volume', 0)
                print(f"  卖{i}: {price:.2f} x {volume}")
            return True
        else:
            print("获取数据失败")
            return False
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_minute_data():
    """测试分钟级数据"""
    print("\n=== 测试AKShare分钟数据 ===")
    try:
        import akshare as ak
        
        # 测试贵州茅台
        symbol = "sh600519"
        df = ak.stock_zh_a_minute(symbol=symbol, period='1')
        
        if df is not None and not df.empty:
            print(f"获取到 {len(df)} 条分钟数据")
            print("\n最近5条记录:")
            print(df.tail(5).to_string())
            return True
        else:
            print("获取数据失败")
            return False
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("实时数据接口测试")
    print("=" * 50)
    
    results = {
        "新浪五档": test_sina_orderbook(),
        "腾讯五档": test_tencent_orderbook(),
        "AKShare分钟": test_minute_data()
    }
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("全部测试通过!" if all_passed else "部分测试失败"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
