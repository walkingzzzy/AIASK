# TdxQuant Finance Data Test
# Tests: financial data, stock trading data, sector trading data, market trading data

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

# 初始化
tq.initialize(__file__)

def test_get_financial_data():
    """Test get_financial_data"""
    print("=" * 60)
    print("[Test 1] get_financial_data")
    print("=" * 60)

    try:
        data = tq.get_financial_data(
            stock_list=['000001.SZ', '600519.SH'],
            field_list=['F001', 'F002', 'F003', 'F004', 'F005'],
            start_time='20240101',
            end_time='20241231'
        )

        print(f"[PASS] Get financial data success")
        print(f"   Data type: {type(data)}")
        print(f"   Preview: {str(data)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get financial data failed: {e}")
        return False

def test_get_gpjy_value():
    """Test get_gpjy_value"""
    print("\n" + "=" * 60)
    print("[Test 2] get_gpjy_value")
    print("=" * 60)

    try:
        data = tq.get_gpjy_value(
            stock_list=['000001.SZ', '600519.SH'],
            field_list=['GP1', 'GP2', 'GP3', 'GP4', 'GP5'],
            start_time='20250101',
            end_time='20250201'
        )

        print(f"[PASS] Get stock trading data success")
        print(f"   Data type: {type(data)}")
        print(f"   Preview: {str(data)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get stock trading data failed: {e}")
        return False

def test_get_bkjy_value():
    """Test get_bkjy_value"""
    print("\n" + "=" * 60)
    print("[Test 3] get_bkjy_value")
    print("=" * 60)

    try:
        data = tq.get_bkjy_value(
            stock_list=['880471.SH'],
            field_list=['BK1', 'BK2', 'BK3'],
            start_time='20250101',
            end_time='20250201'
        )

        print(f"[PASS] Get sector trading data success")
        print(f"   Data type: {type(data)}")
        print(f"   Preview: {str(data)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get sector trading data failed: {e}")
        return False

def test_get_scjy_value():
    """Test get_scjy_value"""
    print("\n" + "=" * 60)
    print("[Test 4] get_scjy_value")
    print("=" * 60)

    try:
        data = tq.get_scjy_value(
            field_list=['SC1', 'SC2', 'SC3', 'SC4', 'SC5'],
            start_time='20250101',
            end_time='20250201'
        )

        print(f"[PASS] Get market trading data success")
        print(f"   Data type: {type(data)}")
        print(f"   Preview: {str(data)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Get market trading data failed: {e}")
        return False

def test_get_gp_one_data():
    """Test get_gp_one_data"""
    print("\n" + "=" * 60)
    print("[Test 5] get_gp_one_data")
    print("=" * 60)

    try:
        data = tq.get_gp_one_data(
            stock_list=['000001.SZ', '600519.SH'],
            field_list=['GO1', 'GO2', 'GO33', 'GO34']
        )

        print(f"[PASS] Get stock one data success")
        print(f"   Data type: {type(data)}")
        if isinstance(data, dict):
            for stock, info in list(data.items())[:2]:
                print(f"\n   {stock}:")
                for key, value in list(info.items())[:5]:
                    print(f"     {key}: {value}")
        return True
    except Exception as e:
        print(f"[FAIL] Get stock one data failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Finance Data Test")
    print("#" * 60 + "\n")

    results = []
    results.append(("get_financial_data", test_get_financial_data()))
    results.append(("get_gpjy_value", test_get_gpjy_value()))
    results.append(("get_bkjy_value", test_get_bkjy_value()))
    results.append(("get_scjy_value", test_get_scjy_value()))
    results.append(("get_gp_one_data", test_get_gp_one_data()))

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

