# TdxQuant Custom Sector Extended Test
# Tests: rename_sector

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_rename_sector():
    """Test rename_sector"""
    print("=" * 60)
    print("[Test 1] rename_sector")
    print("=" * 60)

    try:
        # Check if API exists
        if not hasattr(tq, 'rename_sector'):
            print("[SKIP] rename_sector not available in current version")
            return None

        # Step 1: Create a test sector
        print("   1. Creating test sector...")
        create_res = tq.create_sector(block_code='PYTEST02', block_name='PyTest Rename')
        print(f"      Create result: {create_res}")

        # Step 2: Rename the sector
        print("   2. Renaming sector...")
        rename_res = tq.rename_sector(block_code='PYTEST02', block_name='PyTest Renamed')
        print(f"      Rename result: {rename_res}")

        # Step 3: Delete the test sector
        print("   3. Deleting test sector...")
        delete_res = tq.delete_sector(block_code='PYTEST02')
        print(f"      Delete result: {delete_res}")

        print("\n[PASS] rename_sector success")
        return True
    except Exception as e:
        # Clean up on failure
        try:
            tq.delete_sector(block_code='PYTEST02')
        except:
            pass
        print(f"[FAIL] rename_sector failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Custom Sector Extended Test")
    print("#" * 60 + "\n")

    results = []

    r1 = test_rename_sector()
    if r1 is None:
        results.append(("rename_sector", "SKIP"))
    else:
        results.append(("rename_sector", r1))

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

