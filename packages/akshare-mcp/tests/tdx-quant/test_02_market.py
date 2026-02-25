# TdxQuant Market Data Test
# Tests: K-line data, snapshot, stock info, dividend factors, IPO info, CB info

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_get_market_data():
    """Test get_market_data"""
    print("=" * 60)
    print("[Test 1] get_market_data")
    print("=" * 60)

    try:
        df = tq.get_market_data(
            field_list=[],
            stock_list=['000001.SZ', '600519.SH', '688318.SH'],
            period='1d',
            start_time='20250101',
            end_time='',
            count=3,
            dividend_type='none',
            fill_data=True
        )

        print(f"[PASS] Get market data success")
        print(f"   Fields: {list(df.keys())}")
        if 'Close' in df:
            print(f"\n   Close prices:")
            print(df['Close'])
        return True
    except Exception as e:
        print(f"[FAIL] Get market data failed: {e}")
        return False

def test_get_market_data_periods():
    """Test different periods"""
    print("\n" + "=" * 60)
    print("[Test 2] Different periods K-line")
    print("=" * 60)

    periods = ['1m', '5m', '15m', '30m', '1h', '1d', '1w']
    results = []
    
    for period in periods:
        try:
            df = tq.get_market_data(
                stock_list=['688318.SH'],
                period=period,
                count=2
            )
            if df and 'Close' in df:
                results.append((period, True))
                print(f"   [OK] {period}: success")
            else:
                results.append((period, False))
                print(f"   [--] {period}: no data")
        except Exception as e:
            results.append((period, False))
            print(f"   [--] {period}: {e}")

    return all(r[1] for r in results)

def test_get_market_snapshot():
    """Test get_market_snapshot"""
    print("\n" + "=" * 60)
    print("[Test 3] get_market_snapshot")
    print("=" * 60)

    try:
        stocks = ['000001.SZ', '600519.SH', '688318.SH']
        for stock in stocks:
            snapshot = tq.get_market_snapshot(stock_code=stock)
            print(f"\n   {stock}:")
            print(f"     Now: {snapshot.get('Now', 'N/A')}")
            print(f"     Change: {float(snapshot.get('Now', 0)) - float(snapshot.get('LastClose', 0)):.2f}")

        print(f"\n[PASS] Get snapshot success")
        return True
    except Exception as e:
        print(f"[FAIL] Get snapshot failed: {e}")
        return False

def test_get_stock_info():
    """Test get_stock_info"""
    print("\n" + "=" * 60)
    print("[Test 4] get_stock_info")
    print("=" * 60)

    try:
        info = tq.get_stock_info(stock_code='000001.SZ', field_list=[])

        print(f"[PASS] Get stock info success")
        print(f"   Name: {info.get('Name', 'N/A')}")
        print(f"   ListDate: {info.get('J_start', 'N/A')}")
        print(f"   TotalShares: {info.get('J_zgb', 'N/A')}")
        print(f"   FloatShares: {info.get('ActiveCapital', 'N/A')}")
        print(f"   EPS: {info.get('J_mgsy', 'N/A')}")
        print(f"   BVPS: {info.get('J_mgjzc', 'N/A')}")
        print(f"   InHS300: {info.get('BelongHS300', 'N/A')}")
        return True
    except Exception as e:
        print(f"[FAIL] Get stock info failed: {e}")
        return False

def test_get_divid_factors():
    """Test get_divid_factors"""
    print("\n" + "=" * 60)
    print("[Test 5] get_divid_factors")
    print("=" * 60)

    try:
        divid = tq.get_divid_factors(stock_code='000001.SZ', start_time='', end_time='')

        print(f"[PASS] Get dividend factors success")
        print(f"   Type: {type(divid)}")
        if hasattr(divid, '__len__'):
            print(f"   Count: {len(divid)}")
        print(f"   Preview: {str(divid)[:200]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get dividend factors failed: {e}")
        return False

def test_get_ipo_info():
    """Test get_ipo_info"""
    print("\n" + "=" * 60)
    print("[Test 6] get_ipo_info")
    print("=" * 60)

    try:
        ipo_info = tq.get_ipo_info()

        print(f"[PASS] Get IPO info success")
        print(f"   Type: {type(ipo_info)}")
        if hasattr(ipo_info, '__len__'):
            print(f"   Count: {len(ipo_info)}")
        print(f"   Preview: {str(ipo_info)[:200]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get IPO info failed: {e}")
        return False

def test_get_cb_info():
    """Test get_cb_info"""
    print("\n" + "=" * 60)
    print("[Test 7] get_cb_info")
    print("=" * 60)

    try:
        cb_info = tq.get_cb_info(stock_code='127063.SZ')

        print(f"[PASS] Get CB info success")
        print(f"   Type: {type(cb_info)}")
        print(f"   Preview: {str(cb_info)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get CB info failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Market Data Test")
    print("#" * 60 + "\n")

    results = []
    results.append(("get_market_data", test_get_market_data()))
    results.append(("periods_kline", test_get_market_data_periods()))
    results.append(("get_market_snapshot", test_get_market_snapshot()))
    results.append(("get_stock_info", test_get_stock_info()))
    results.append(("get_divid_factors", test_get_divid_factors()))
    results.append(("get_ipo_info", test_get_ipo_info()))
    results.append(("get_cb_info", test_get_cb_info()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    for name, result in results:
        print(f"  {name}: {'PASS' if result else 'FAIL'}")

    print(f"\nTotal: {passed} passed, {failed} failed")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

