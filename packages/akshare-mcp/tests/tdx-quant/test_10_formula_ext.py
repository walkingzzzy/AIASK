# TdxQuant Formula Extended Test
# Tests: formula_format_data, formula_set_data_info

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_formula_format_data():
    """Test formula_format_data"""
    print("=" * 60)
    print("[Test 1] formula_format_data")
    print("=" * 60)
    
    try:
        # Check if API exists
        if not hasattr(tq, 'formula_format_data'):
            print("[SKIP] formula_format_data not available in current version")
            return None
        
        # Get market data first
        test_md = tq.get_market_data(stock_list=['688318.SH'], count=5, period='1d')
        print(f"   Raw market data keys: {list(test_md.keys())}")
        
        # Format the data
        format_md = tq.formula_format_data(test_md)
        print(f"[PASS] formula_format_data success")
        print(f"   Type: {type(format_md)}")
        print(f"   Preview: {str(format_md)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] formula_format_data failed: {e}")
        return False

def test_formula_set_data_info():
    """Test formula_set_data_info"""
    print("\n" + "=" * 60)
    print("[Test 2] formula_set_data_info")
    print("=" * 60)
    
    try:
        # Check if API exists
        if not hasattr(tq, 'formula_set_data_info'):
            print("[SKIP] formula_set_data_info not available in current version")
            return None
        
        result = tq.formula_set_data_info(
            stock_code='688318.SH',
            stock_period='1d',
            count=100,
            dividend_type=1
        )
        print(f"[PASS] formula_set_data_info success")
        print(f"   Result: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] formula_set_data_info failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Formula Extended Test")
    print("#" * 60 + "\n")

    results = []
    
    r1 = test_formula_format_data()
    if r1 is None:
        results.append(("formula_format_data", "SKIP"))
    else:
        results.append(("formula_format_data", r1))
    
    r2 = test_formula_set_data_info()
    if r2 is None:
        results.append(("formula_set_data_info", "SKIP"))
    else:
        results.append(("formula_set_data_info", r2))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r == True)
    failed = sum(1 for _, r in results if r == False)
    skipped = sum(1 for _, r in results if r == "SKIP")
    
    for name, result in results:
        if result == "SKIP":
            status = "SKIP"
        else:
            status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

