# Tushare Pro 测试运行器

import sys
import io
import os
import subprocess
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_test_file(filepath):
    """运行单个测试文件"""
    print(f"\n{'='*70}")
    print(f"Running: {filepath}")
    print('='*70)
    
    try:
        result = subprocess.run(
            ['python', '-B', filepath],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120
        )
        print(result.stdout)
        if result.stderr:
            print(f"Stderr: {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] Test file timed out: {filepath}")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run test: {e}")
        return False

def main():
    print("#" * 70)
    print("#  Tushare Pro Complete Test Suite")
    print(f"#  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    test_files = [
        'test_proxy_api.py',
        'test_02_market.py',
        'test_03_finance.py',
        'test_04_index.py',
        'test_05_moneyflow.py',
    ]
    
    results = []
    for test_file in test_files:
        filepath = os.path.join(test_dir, test_file)
        if os.path.exists(filepath):
            success = run_test_file(filepath)
            results.append((test_file, success))
        else:
            print(f"[SKIP] File not found: {test_file}")
            results.append((test_file, None))
    
    print("\n" + "=" * 70)
    print("Complete Test Results Summary")
    print("=" * 70)
    
    for name, result in results:
        if result is None:
            status = "SKIP"
        elif result:
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  {name}: {status}")
    
    passed = sum(1 for _, r in results if r == True)
    failed = sum(1 for _, r in results if r == False)
    skipped = sum(1 for _, r in results if r is None)
    
    print("=" * 70)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

