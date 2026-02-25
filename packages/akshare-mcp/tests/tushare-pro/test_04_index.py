# Tushare Pro API 指数数据测试
# Tests: index_basic, index_daily, index_weight

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import pandas as pd

# 配置
TUSHARE_TOKEN = '2ecc5201dcf93fff3ee466a622d40687b86ecfa6a69481aa8ff0b01ef02f'
TUSHARE_HTTP_URL = 'http://lianghua.nanyangqiankun.top'

def call_api(api_name, params=None, fields=''):
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

def test_index_basic():
    """Test index_basic - 指数基本信息"""
    print("=" * 60)
    print("[Test 1] index_basic - 指数基本信息")
    print("=" * 60)
    try:
        df = call_api('index_basic', {'market': 'SSE'})
        print(f"[PASS] index_basic success - {len(df)} indices")
        print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] index_basic failed: {e}")
        return False

def test_index_daily():
    """Test index_daily - 指数日线行情"""
    print("\n" + "=" * 60)
    print("[Test 2] index_daily - 指数日线行情")
    print("=" * 60)
    try:
        # 上证指数
        df = call_api('index_daily', {'ts_code': '000001.SH', 'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] index_daily success - {len(df)} records")
        print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] index_daily failed: {e}")
        return False

def test_index_weight():
    """Test index_weight - 指数成分和权重"""
    print("\n" + "=" * 60)
    print("[Test 3] index_weight - 指数成分和权重")
    print("=" * 60)
    try:
        # 沪深300成分股权重
        df = call_api('index_weight', {'index_code': '000300.SH', 'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] index_weight success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        else:
            print("   No weight data for this period")
        return True
    except Exception as e:
        print(f"[FAIL] index_weight failed: {e}")
        return False

def test_index_member():
    """Test index_member - 指数成分股"""
    print("\n" + "=" * 60)
    print("[Test 4] index_member - 指数成分股")
    print("=" * 60)
    try:
        df = call_api('index_member', {'index_code': '000300.SH'})
        print(f"[PASS] index_member success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] index_member failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  Tushare Pro - Index Data Test")
    print("#" * 60 + "\n")
    
    results = [
        ("index_basic", test_index_basic()),
        ("index_daily", test_index_daily()),
        ("index_weight", test_index_weight()),
        ("index_member", test_index_member()),
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

