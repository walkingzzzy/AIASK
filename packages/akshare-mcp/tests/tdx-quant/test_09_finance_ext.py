# TdxQuant Finance Extended Test
# Tests: get_financial_data_by_date, get_gpjy_value_by_date, 
#        get_bkjy_value_by_date, get_scjy_value_by_date

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_get_financial_data_by_date():
    """Test get_financial_data_by_date"""
    print("=" * 60)
    print("[Test 1] get_financial_data_by_date")
    print("=" * 60)
    
    try:
        result = tq.get_financial_data_by_date(
            stock_list=['688318.SH', '600519.SH'],
            field_list=['Fn193', 'Fn194', 'Fn195', 'Fn196', 'Fn197'],
            year=0,
            mmdd=0
        )
        print(f"[PASS] Get financial data by date success")
        print(f"   Type: {type(result)}")
        print(f"   Data: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Get financial data by date failed: {e}")
        return False

def test_get_gpjy_value_by_date():
    """Test get_gpjy_value_by_date"""
    print("\n" + "=" * 60)
    print("[Test 2] get_gpjy_value_by_date")
    print("=" * 60)
    
    try:
        result = tq.get_gpjy_value_by_date(
            stock_list=['688318.SH', '600519.SH'],
            field_list=['GP1', 'GP2', 'GP3', 'GP4', 'GP5'],
            year=0,
            mmdd=0
        )
        print(f"[PASS] Get gpjy value by date success")
        print(f"   Type: {type(result)}")
        print(f"   Data: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Get gpjy value by date failed: {e}")
        return False

def test_get_bkjy_value_by_date():
    """Test get_bkjy_value_by_date"""
    print("\n" + "=" * 60)
    print("[Test 3] get_bkjy_value_by_date")
    print("=" * 60)
    
    try:
        result = tq.get_bkjy_value_by_date(
            stock_list=['880471.SH'],  # Banking sector
            field_list=['BK9', 'BK10', 'BK11', 'BK12', 'BK13'],
            year=0,
            mmdd=0
        )
        print(f"[PASS] Get bkjy value by date success")
        print(f"   Type: {type(result)}")
        print(f"   Data: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Get bkjy value by date failed: {e}")
        return False

def test_get_scjy_value_by_date():
    """Test get_scjy_value_by_date"""
    print("\n" + "=" * 60)
    print("[Test 4] get_scjy_value_by_date")
    print("=" * 60)
    
    try:
        result = tq.get_scjy_value_by_date(
            field_list=['SC6', 'SC7', 'SC8', 'SC9', 'SC10'],
            year=0,
            mmdd=0
        )
        print(f"[PASS] Get scjy value by date success")
        print(f"   Type: {type(result)}")
        print(f"   Data: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Get scjy value by date failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Finance Extended Test")
    print("#" * 60 + "\n")

    results = []
    results.append(("get_financial_data_by_date", test_get_financial_data_by_date()))
    results.append(("get_gpjy_value_by_date", test_get_gpjy_value_by_date()))
    results.append(("get_bkjy_value_by_date", test_get_bkjy_value_by_date()))
    results.append(("get_scjy_value_by_date", test_get_scjy_value_by_date()))
    
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

