# TdxQuant Basic Test
# Tests: initialize, get_trading_dates, get_market_data, get_market_snapshot

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

def test_initialize():
    """Test initialize"""
    print("=" * 60)
    print("[Test 1] initialize")
    print("=" * 60)

    try:
        result = tq.initialize(__file__)
        print(f"[PASS] Initialize success")
        print(f"   Result: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Initialize failed: {e}")
        return False

def test_get_trading_dates():
    """Test get_trading_dates"""
    print("\n" + "=" * 60)
    print("[Test 2] get_trading_dates")
    print("=" * 60)

    try:
        trading_dates = tq.get_trading_dates(
            market='SH',
            start_time='20250101',
            end_time='',
            count=10
        )

        print(f"[PASS] Get trading dates success")
        print(f"   Count: {len(trading_dates)}")
        print(f"   Dates: {trading_dates}")
        return True
    except Exception as e:
        print(f"[FAIL] Get trading dates failed: {e}")
        return False

def test_get_market_data():
    """Test get_market_data"""
    print("\n" + "=" * 60)
    print("[Test 3] get_market_data")
    print("=" * 60)

    try:
        df = tq.get_market_data(
            field_list=[],
            stock_list=['688318.SH'],
            period='1d',
            start_time='20250101',
            end_time='',
            count=5,
            dividend_type='none',
            fill_data=True
        )

        print(f"[PASS] Get market data success")
        print(f"   Fields: {list(df.keys())}")
        if 'Close' in df:
            print(f"\n   Close prices:")
            print(f"   {df['Close']}")
        return True
    except Exception as e:
        print(f"[FAIL] Get market data failed: {e}")
        return False

def test_get_market_snapshot():
    """Test get_market_snapshot"""
    print("\n" + "=" * 60)
    print("[Test 4] get_market_snapshot")
    print("=" * 60)

    try:
        snapshot = tq.get_market_snapshot(stock_code='688318.SH')

        print(f"[PASS] Get snapshot success")
        print(f"   Now: {snapshot.get('Now', 'N/A')}")
        print(f"   Open: {snapshot.get('Open', 'N/A')}")
        print(f"   Max: {snapshot.get('Max', 'N/A')}")
        print(f"   Min: {snapshot.get('Min', 'N/A')}")
        print(f"   LastClose: {snapshot.get('LastClose', 'N/A')}")
        return True
    except Exception as e:
        print(f"[FAIL] Get snapshot failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Basic Test")
    print("#  Make sure TDX client is running")
    print("#" * 60 + "\n")

    results = []
    results.append(("initialize", test_initialize()))
    results.append(("get_trading_dates", test_get_trading_dates()))
    results.append(("get_market_data", test_get_market_data()))
    results.append(("get_market_snapshot", test_get_market_snapshot()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    for name, result in results:
        print(f"  {name}: {'PASS' if result else 'FAIL'}")

    print(f"\nTotal: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

