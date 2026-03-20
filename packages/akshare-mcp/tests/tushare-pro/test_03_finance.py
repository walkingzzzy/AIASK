# Tushare Pro API 财务数据测试
# Tests: income, balancesheet, cashflow, fina_indicator

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import pandas as pd

from _config import TUSHARE_HTTP_URL, TUSHARE_TOKEN, ensure_tushare_token

def call_api(api_name, params=None, fields=''):
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

def test_income():
    """Test income - 利润表"""
    print("=" * 60)
    print("[Test 1] income - 利润表")
    print("=" * 60)
    try:
        df = call_api('income', {'ts_code': '600519.SH', 'period': '20240930'})
        print(f"[PASS] income success - {len(df)} records")
        if len(df) > 0:
            key_cols = ['ts_code', 'ann_date', 'end_date', 'revenue', 'operate_profit', 'n_income']
            available_cols = [c for c in key_cols if c in df.columns]
            print(df[available_cols].head().to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] income failed: {e}")
        return False

def test_balancesheet():
    """Test balancesheet - 资产负债表"""
    print("\n" + "=" * 60)
    print("[Test 2] balancesheet - 资产负债表")
    print("=" * 60)
    try:
        df = call_api('balancesheet', {'ts_code': '600519.SH', 'period': '20240930'})
        print(f"[PASS] balancesheet success - {len(df)} records")
        if len(df) > 0:
            key_cols = ['ts_code', 'ann_date', 'end_date', 'total_assets', 'total_liab', 'total_hldr_eqy_exc_min_int']
            available_cols = [c for c in key_cols if c in df.columns]
            print(df[available_cols].head().to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] balancesheet failed: {e}")
        return False

def test_cashflow():
    """Test cashflow - 现金流量表"""
    print("\n" + "=" * 60)
    print("[Test 3] cashflow - 现金流量表")
    print("=" * 60)
    try:
        df = call_api('cashflow', {'ts_code': '600519.SH', 'period': '20240930'})
        print(f"[PASS] cashflow success - {len(df)} records")
        if len(df) > 0:
            key_cols = ['ts_code', 'ann_date', 'end_date', 'n_cashflow_act', 'n_cashflow_inv_act']
            available_cols = [c for c in key_cols if c in df.columns]
            print(df[available_cols].head().to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] cashflow failed: {e}")
        return False

def test_fina_indicator():
    """Test fina_indicator - 财务指标"""
    print("\n" + "=" * 60)
    print("[Test 4] fina_indicator - 财务指标")
    print("=" * 60)
    try:
        df = call_api('fina_indicator', {'ts_code': '600519.SH', 'period': '20240930'})
        print(f"[PASS] fina_indicator success - {len(df)} records")
        if len(df) > 0:
            key_cols = ['ts_code', 'ann_date', 'end_date', 'eps', 'roe', 'grossprofit_margin']
            available_cols = [c for c in key_cols if c in df.columns]
            print(df[available_cols].head().to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] fina_indicator failed: {e}")
        return False

def test_dividend():
    """Test dividend - 分红送股"""
    print("\n" + "=" * 60)
    print("[Test 5] dividend - 分红送股")
    print("=" * 60)
    try:
        df = call_api('dividend', {'ts_code': '600519.SH'})
        print(f"[PASS] dividend success - {len(df)} records")
        if len(df) > 0:
            key_cols = ['ts_code', 'end_date', 'ann_date', 'div_proc', 'stk_div', 'cash_div']
            available_cols = [c for c in key_cols if c in df.columns]
            print(df[available_cols].head(5).to_string(index=False))
        return True
    except Exception as e:
        print(f"[FAIL] dividend failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  Tushare Pro - Finance Data Test")
    print("#" * 60 + "\n")
    
    results = [
        ("income", test_income()),
        ("balancesheet", test_balancesheet()),
        ("cashflow", test_cashflow()),
        ("fina_indicator", test_fina_indicator()),
        ("dividend", test_dividend()),
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
