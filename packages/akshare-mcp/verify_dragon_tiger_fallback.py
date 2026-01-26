
import sys
import os
from datetime import datetime, timedelta

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from akshare_mcp.tools.fund_flow import get_dragon_tiger

def test_dragon_tiger_fallback():
    print("Testing Dragon Tiger Fallback...")
    
    # Try getting data
    res = get_dragon_tiger()
    if res.get("success"):
        data = res["data"]
        count = len(data)
        source = data[0].get("source") if count > 0 else "N/A"
        print(f"Fetch Success. Count: {count}. Source: {source}")
        if count > 0:
            print(f"Sample: {data[0]}")
    else:
        print(f"Fetch Failed: {res.get('error')}")

if __name__ == "__main__":
    try:
        test_dragon_tiger_fallback()
    except Exception as e:
        print(f"Verification Error: {e}")
