# TdxQuant Sector Data Test
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')
from tqcenter import tq
tq.initialize(__file__)

def test_get_sector_list():
    print("=" * 60)
    print("[Test 1] get_sector_list")
    print("=" * 60)
    try:
        sector_list = tq.get_sector_list()
        print(f"[PASS] Total sectors: {len(sector_list)}")
        print(f"   First 10: {sector_list[:10]}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_get_stock_list():
    print("\n" + "=" * 60)
    print("[Test 2] get_stock_list")
    print("=" * 60)
    try:
        test_cases = [('5', 'All A-shares'), ('23', 'CSI 300'), ('51', 'ChiNext'), ('52', 'STAR')]
        for market, desc in test_cases:
            stock_list = tq.get_stock_list(market)
            print(f"   {desc}(market={market}): {len(stock_list)} stocks")
        print(f"\n[PASS] Get stock list success")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_get_stock_list_in_sector():
    print("\n" + "=" * 60)
    print("[Test 3] get_stock_list_in_sector")
    print("=" * 60)
    try:
        sectors = [('880471.SH', 'Banking'), ('880472.SH', 'Insurance')]
        for code, name in sectors:
            stock_list = tq.get_stock_list_in_sector(code)
            print(f"   {name}({code}): {len(stock_list)} stocks")
        print(f"\n[PASS] Get sector stocks success")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_get_user_sector():
    print("\n" + "=" * 60)
    print("[Test 4] get_user_sector")
    print("=" * 60)
    try:
        user_sectors = tq.get_user_sector()
        print(f"[PASS] User sectors count: {len(user_sectors)}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_custom_sector_ops():
    print("\n" + "=" * 60)
    print("[Test 5] Custom sector operations")
    print("=" * 60)
    test_block = 'PYTEST01'
    try:
        print(f"   1. Creating sector...")
        r1 = tq.create_sector(block_code=test_block, block_name='TestBlock')
        print(f"      {r1}")
        print(f"   2. Adding stocks...")
        r2 = tq.send_user_block(block_code=test_block, stocks=['000001.SZ', '600519.SH'])
        print(f"      {r2}")
        print(f"   3. Clearing stocks...")
        r3 = tq.clear_sector(block_code=test_block)
        print(f"      {r3}")
        print(f"   4. Deleting sector...")
        r4 = tq.delete_sector(block_code=test_block)
        print(f"      {r4}")
        print(f"\n[PASS] Custom sector operations success")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        try: tq.delete_sector(block_code=test_block)
        except: pass
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Sector Data Test")
    print("#" * 60 + "\n")
    results = []
    results.append(("get_sector_list", test_get_sector_list()))
    results.append(("get_stock_list", test_get_stock_list()))
    results.append(("get_stock_list_in_sector", test_get_stock_list_in_sector()))
    results.append(("get_user_sector", test_get_user_sector()))
    results.append(("custom_sector_ops", test_custom_sector_ops()))
    
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
