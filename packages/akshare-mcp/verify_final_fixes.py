
import sys
import os
from datetime import datetime

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from akshare_mcp.tools.finance import get_financials
from akshare_mcp.tools.fund_flow import get_north_fund
from akshare_mcp.date_utils import get_latest_trading_date

def test_financials():
    print("\n--- Testing get_financials (000001) ---")
    try:
        res = get_financials("000001")
        if res.get("success"):
            data = res.get("data", {})
            print(f"✅ Success! Source: {data.get('source')}")
            print(f"EPS: {data.get('eps')}, ROE: {data.get('roe')}")
        else:
            print(f"❌ Failed: {res.get('error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_north_fund():
    print("\n--- Testing get_north_fund (days=5) ---")
    print(f"Latest Trading Date (Calculated): {get_latest_trading_date()}")
    try:
        res = get_north_fund(days=5)
        if res.get("success"):
            data = res.get("data", [])
            print(f"✅ Success! Rows: {len(data)}")
            if data:
                print(f"Latest Valid Date: {data[-1].get('date')}")
                print(f"Total Flow: {data[-1].get('total')}")
        else:
            print(f"❌ Failed: {res.get('error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_financials()
    test_north_fund()
