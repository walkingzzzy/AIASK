# Tushare Pro API 资金流向测试
# Tests: moneyflow, moneyflow_hsgt, hsgt_top10

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

def test_moneyflow():
    """Test moneyflow - 个股资金流向"""
    print("=" * 60)
    print("[Test 1] moneyflow - 个股资金流向")
    print("=" * 60)
    try:
        df = call_api('moneyflow', {'ts_code': '000001.SZ', 'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] moneyflow success - {len(df)} records")
        if len(df) > 0:
            print(df.head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] moneyflow failed: {e}")
        return False

def test_moneyflow_hsgt():
    """Test moneyflow_hsgt - 沪深港通资金流向"""
    print("\n" + "=" * 60)
    print("[Test 2] moneyflow_hsgt - 沪深港通资金流向")
    print("=" * 60)
    try:
        df = call_api('moneyflow_hsgt', {'start_date': '20260101', 'end_date': '20260203'})
        print(f"[PASS] moneyflow_hsgt success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] moneyflow_hsgt failed: {e}")
        return False

def test_hsgt_top10():
    """Test hsgt_top10 - 沪深港通十大成交股"""
    print("\n" + "=" * 60)
    print("[Test 3] hsgt_top10 - 沪深港通十大成交股")
    print("=" * 60)
    try:
        df = call_api('hsgt_top10', {'trade_date': '20260203', 'market_type': '1'})
        print(f"[PASS] hsgt_top10 success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] hsgt_top10 failed: {e}")
        return False

def test_margin():
    """Test margin - 融资融券交易汇总"""
    print("\n" + "=" * 60)
    print("[Test 4] margin - 融资融券交易汇总")
    print("=" * 60)
    try:
        df = call_api('margin', {'trade_date': '20260203'})
        print(f"[PASS] margin success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] margin failed: {e}")
        return False

def test_margin_detail():
    """Test margin_detail - 融资融券交易明细"""
    print("\n" + "=" * 60)
    print("[Test 5] margin_detail - 融资融券交易明细")
    print("=" * 60)
    try:
        df = call_api('margin_detail', {'trade_date': '20260203'})
        print(f"[PASS] margin_detail success - {len(df)} records")
        if len(df) > 0:
            print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] margin_detail failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  Tushare Pro - Money Flow Test")
    print("#" * 60 + "\n")
    
    results = [
        ("moneyflow", test_moneyflow()),
        ("moneyflow_hsgt", test_moneyflow_hsgt()),
        ("hsgt_top10", test_hsgt_top10()),
        ("margin", test_margin()),
        ("margin_detail", test_margin_detail()),
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

