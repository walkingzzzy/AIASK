# TdxQuant Test Runner - Run all tests
# One-click run all test modules

import sys
import os
import io
import subprocess
from datetime import datetime

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_test(test_file):
    """Run a single test file"""
    print(f"\n{'='*70}")
    print(f"Running: {test_file}")
    print('='*70)

    result = subprocess.run(
        [sys.executable, '-B', test_file],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    print(result.stdout)
    if result.stderr:
        print(f"Stderr: {result.stderr}")

    return result.returncode == 0

def main():
    print("#" * 70)
    print("#  TdxQuant Complete Test Suite")
    print(f"#  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)

    test_dir = os.path.dirname(os.path.abspath(__file__))

    test_files = [
        'test_01_basic.py',
        'test_02_market.py',
        'test_03_sector.py',
        'test_04_finance.py',
        'test_05_formula.py',
        'test_06_common.py',
        'test_07_market_ext.py',
        'test_08_sector_ext.py',
        'test_09_finance_ext.py',
        'test_10_formula_ext.py',
    ]

    results = []
    for test_file in test_files:
        test_path = os.path.join(test_dir, test_file)
        if os.path.exists(test_path):
            success = run_test(test_path)
            results.append((test_file, success))
        else:
            print(f"[WARN] Test file not found: {test_file}")
            results.append((test_file, False))

    # Final summary
    print("\n" + "=" * 70)
    print("Complete Test Results Summary")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\n{'='*70}")
    print(f"Total: {passed} test files passed, {failed} test files failed")
    print("=" * 70)

    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

