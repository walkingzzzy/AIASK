# Tushare Pro API 测试 - 使用代理服务
# 直接通过HTTP请求调用代理API

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json
import pandas as pd

from _config import TUSHARE_HTTP_URL, TUSHARE_TOKEN, ensure_tushare_token

def call_tushare_api(api_name, params=None, fields=''):
    """通过HTTP调用Tushare代理API"""
    ensure_tushare_token()
    payload = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params or {},
        'fields': fields
    }
    
    try:
        response = requests.post(TUSHARE_HTTP_URL, json=payload, timeout=30)
        result = response.json()
        
        if result.get('code') != 0:
            raise Exception(result.get('msg', 'Unknown error'))
        
        data = result.get('data', {})
        if data:
            df = pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
            return df
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        raise Exception(f"HTTP request failed: {e}")

def test_connection():
    """Test API connection"""
    print("=" * 60)
    print("[Test 1] API Connection Test")
    print("=" * 60)
    
    try:
        response = requests.get(TUSHARE_HTTP_URL, timeout=10)
        print(f"[PASS] Connection successful")
        print(f"   URL: {TUSHARE_HTTP_URL}")
        print(f"   Status: {response.status_code}")
        return True
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return False

def test_stock_basic():
    """Test stock_basic - 获取股票列表"""
    print("\n" + "=" * 60)
    print("[Test 2] stock_basic - 股票列表")
    print("=" * 60)
    
    try:
        df = call_tushare_api(
            'stock_basic',
            params={'exchange': '', 'list_status': 'L'},
            fields='ts_code,symbol,name,area,industry,list_date'
        )
        print(f"[PASS] stock_basic success")
        print(f"   Total stocks: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
        print(f"\n   Sample data (first 5):")
        print(df.head().to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] stock_basic failed: {e}")
        return False

def test_trade_cal():
    """Test trade_cal - 获取交易日历"""
    print("\n" + "=" * 60)
    print("[Test 3] trade_cal - 交易日历")
    print("=" * 60)
    
    try:
        df = call_tushare_api(
            'trade_cal',
            params={'exchange': 'SSE', 'start_date': '20260101', 'end_date': '20260228'}
        )
        print(f"[PASS] trade_cal success")
        print(f"   Total days: {len(df)}")
        print(f"\n   Sample data:")
        print(df.head(10).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] trade_cal failed: {e}")
        return False

def test_daily():
    """Test daily - 获取日线行情"""
    print("\n" + "=" * 60)
    print("[Test 4] daily - 日线行情")
    print("=" * 60)
    
    try:
        df = call_tushare_api(
            'daily',
            params={'ts_code': '000001.SZ', 'start_date': '20260101', 'end_date': '20260203'}
        )
        print(f"[PASS] daily success")
        print(f"   Total records: {len(df)}")
        print(f"\n   Data:")
        print(df.to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] daily failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  Tushare Pro API Test (via Proxy)")
    print("#" * 60 + "\n")
    
    results = []
    results.append(("connection", test_connection()))
    results.append(("stock_basic", test_stock_basic()))
    results.append(("trade_cal", test_trade_cal()))
    results.append(("daily", test_daily()))
    
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
