# Tushare Pro API 行情数据测试
# Tests: daily, weekly, monthly, adj_factor, daily_basic

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import pandas as pd

from _config import TUSHARE_HTTP_URL, TUSHARE_TOKEN, ensure_tushare_token

def call_api(api_name, params=None, fields=''):
    """通过HTTP调用Tushare代理API"""
    ensure_tushare_token()
    payload = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params or {},
        'fields': fields
    }
    response = requests.post(TUSHARE_HTTP_URL, json=payload, timeout=30)
    result = response.json()
    if result.get('code') != 0:
        raise Exception(result.get('msg', 'Unknown error'))
    data = result.get('data', {})
    if data:
        return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
    return pd.DataFrame()

def test_daily():
    """Test daily - 日线行情"""
    print("=" * 60)
    print("[Test 1] daily - 日线行情")
    print("=" * 60)
    try:
        df = call_api('daily', {'ts_code': '600519.SH', 'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] daily success - {len(df)} records")
        print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] daily failed: {e}")
        return False

def test_weekly():
    """Test weekly - 周线行情"""
    print("\n" + "=" * 60)
    print("[Test 2] weekly - 周线行情")
    print("=" * 60)
    try:
        df = call_api('weekly', {'ts_code': '600519.SH', 'start_date': '20250101', 'end_date': '20260203'})
        print(f"[PASS] weekly success - {len(df)} records")
        print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] weekly failed: {e}")
        return False

def test_monthly():
    """Test monthly - 月线行情"""
    print("\n" + "=" * 60)
    print("[Test 3] monthly - 月线行情")
    print("=" * 60)
    try:
        df = call_api('monthly', {'ts_code': '600519.SH', 'start_date': '20250101', 'end_date': '20260203'})
        print(f"[PASS] monthly success - {len(df)} records")
        print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] monthly failed: {e}")
        return False

def test_adj_factor():
    """Test adj_factor - 复权因子"""
    print("\n" + "=" * 60)
    print("[Test 4] adj_factor - 复权因子")
    print("=" * 60)
    try:
        df = call_api('adj_factor', {'ts_code': '000001.SZ', 'start_date': '20250101', 'end_date': '20260203'})
        print(f"[PASS] adj_factor success - {len(df)} records")
        print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] adj_factor failed: {e}")
        return False

def test_daily_basic():
    """Test daily_basic - 每日指标"""
    print("\n" + "=" * 60)
    print("[Test 5] daily_basic - 每日指标")
    print("=" * 60)
    try:
        df = call_api('daily_basic', {'ts_code': '000001.SZ', 'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] daily_basic success - {len(df)} records")
        print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] daily_basic failed: {e}")
        return False

def test_suspend_d():
    """Test suspend_d - 停复牌信息"""
    print("\n" + "=" * 60)
    print("[Test 6] suspend_d - 停复牌信息")
    print("=" * 60)
    try:
        df = call_api('suspend_d', {'suspend_type': 'S', 'trade_date': '20260203'})
        print(f"[PASS] suspend_d success - {len(df)} records")
        if len(df) > 0:
            print(df.head(5).to_string(index=False))
        else:
            print("   No suspended stocks on this date")
        return True
    except Exception as e:
        print(f"[FAIL] suspend_d failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  Tushare Pro - Market Data Test")
    print("#" * 60 + "\n")
    
    results = [
        ("daily", test_daily()),
        ("weekly", test_weekly()),
        ("monthly", test_monthly()),
        ("adj_factor", test_adj_factor()),
        ("daily_basic", test_daily_basic()),
        ("suspend_d", test_suspend_d()),
    ]
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        print(f"  {name}: {'PASS' if result else 'FAIL'}")
    print(f"\nTotal: {passed} passed, {len(results)-passed} failed")
    return passed == len(results)

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
