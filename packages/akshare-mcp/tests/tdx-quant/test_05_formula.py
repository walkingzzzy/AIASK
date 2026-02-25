# TdxQuant Formula Test
# Tests: formula_zb, formula_xg, formula_exp, formula_set_data/formula_get_data
# Note: These APIs may not be available in all versions of tqcenter

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def check_method_exists(method_name):
    """Check if a method exists in tq"""
    return hasattr(tq, method_name) and callable(getattr(tq, method_name, None))

def test_formula_zb():
    """Test formula_zb (MACD indicator)"""
    print("=" * 60)
    print("[Test 1] formula_zb (MACD)")
    print("=" * 60)

    if not check_method_exists('formula_zb'):
        print("[SKIP] formula_zb not available in current version")
        return None

    try:
        result = tq.formula_zb(
            stock_code='688318.SH',
            formula_name='MACD',
            period='1d',
            count=10
        )

        print(f"[PASS] Call MACD indicator success")
        print(f"   Data type: {type(result)}")
        print(f"   Preview: {str(result)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Call indicator failed: {e}")
        return False

def test_formula_xg():
    """Test formula_xg (stock selection)"""
    print("\n" + "=" * 60)
    print("[Test 2] formula_xg")
    print("=" * 60)

    if not check_method_exists('formula_xg'):
        print("[SKIP] formula_xg not available in current version")
        return None

    try:
        result = tq.formula_xg(
            stock_list=['000001.SZ', '600519.SH', '688318.SH'],
            formula_name='涨停',
            period='1d'
        )

        print(f"[PASS] Call stock selection formula success")
        print(f"   Data type: {type(result)}")
        print(f"   Preview: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Call stock selection failed: {e}")
        return False

def test_formula_exp():
    """Test formula_exp (expression)"""
    print("\n" + "=" * 60)
    print("[Test 3] formula_exp")
    print("=" * 60)

    if not check_method_exists('formula_exp'):
        print("[SKIP] formula_exp not available in current version")
        return None

    try:
        result = tq.formula_exp(
            stock_code='688318.SH',
            expression='MA(CLOSE,5)',
            period='1d',
            count=10
        )

        print(f"[PASS] Call expression success")
        print(f"   Data type: {type(result)}")
        print(f"   Preview: {str(result)[:300]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Call expression failed: {e}")
        return False

def test_formula_set_get_data():
    """Test formula_set_data/formula_get_data"""
    print("\n" + "=" * 60)
    print("[Test 4] formula_set_data/formula_get_data")
    print("=" * 60)

    if not check_method_exists('formula_set_data'):
        print("[SKIP] formula_set_data not available in current version")
        return None

    try:
        print("   1. Setting formula data...")
        set_result = tq.formula_set_data(
            data_name='TEST_DATA',
            data_value=[1.0, 2.0, 3.0, 4.0, 5.0]
        )
        print(f"      Result: {set_result}")

        print("   2. Getting formula data...")
        get_result = tq.formula_get_data(data_name='TEST_DATA')
        print(f"      Result: {get_result}")

        print(f"\n[PASS] Formula data set/get success")
        return True
    except Exception as e:
        print(f"[FAIL] Formula data operation failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Formula Test")
    print("#" * 60 + "\n")

    results = []
    results.append(("formula_zb (MACD)", test_formula_zb()))
    results.append(("formula_xg", test_formula_xg()))
    results.append(("formula_exp", test_formula_exp()))
    results.append(("formula_set_get_data", test_formula_set_get_data()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)

    for name, result in results:
        if result is True:
            status = 'PASS'
        elif result is False:
            status = 'FAIL'
        else:
            status = 'SKIP'
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

