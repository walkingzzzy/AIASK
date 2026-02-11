# TdxQuant Market Extended Test
# Tests: get_more_info, get_gb_info

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_get_more_info():
    """Test get_more_info"""
    print("=" * 60)
    print("[Test 1] get_more_info")
    print("=" * 60)

    try:
        # Check if API exists
        if not hasattr(tq, 'get_more_info'):
            print("[SKIP] get_more_info not available in current version")
            return None

        info = tq.get_more_info(stock_code='688318.SH')
        print(f"[PASS] Get more info success")
        print(f"   Type: {type(info)}")

        # Print key fields
        key_fields = ['Name', 'HqDate', 'HisHigh', 'HisLow', 'IPO_Price',
                      'J_Syl', 'J_ltgb', 'J_ltsz', 'J_mgjzc', 'J_mgsy',
                      'J_zgb', 'J_zsz', 'PB_MRQ', 'StaticPE_TTM', 'ZAF']
        print(f"\n   Key fields:")
        for field in key_fields:
            if field in info:
                print(f"     {field}: {info[field]}")
        return True
    except Exception as e:
        print(f"[FAIL] Get more info failed: {e}")
        return False

def test_get_gb_info():
    """Test get_gb_info"""
    print("\n" + "=" * 60)
    print("[Test 2] get_gb_info")
    print("=" * 60)

    try:
        # Check if API exists
        if not hasattr(tq, 'get_gb_info'):
            print("[SKIP] get_gb_info not available in current version")
            return None

        gb_info = tq.get_gb_info(
            stock_code='688318.SH',
            date_list=['20250101', '20250601', '20260101'],
            count=3
        )
        print(f"[PASS] Get GB info success")
        print(f"   Type: {type(gb_info)}")
        print(f"   Data: {gb_info}")
        return True
    except Exception as e:
        print(f"[FAIL] Get GB info failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Market Extended Test")
    print("#" * 60 + "\n")

    results = []

    r1 = test_get_more_info()
    if r1 is None:
        results.append(("get_more_info", "SKIP"))
    else:
        results.append(("get_more_info", r1))

    r2 = test_get_gb_info()
    if r2 is None:
        results.append(("get_gb_info", "SKIP"))
    else:
        results.append(("get_gb_info", r2))

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

