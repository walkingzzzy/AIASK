
import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from akshare_mcp.baostock_api import baostock_client
from akshare_mcp.tools.finance import get_financials
from akshare_mcp.tools.market import get_kline

def test_baostock_connectivity():
    print("Testing Baostock Connectivity...")
    if baostock_client.login():
        print("Login Success")
        df = baostock_client.get_history_k_data("sh.600519", "2024-01-01", "2024-01-05")
        print(f"Fetch K-Data: {len(df)} rows")
        baostock_client.logout()
    else:
        print("Login Failed")

def test_fallback_logic():
    print("\nTesting Fallback Logic (Mocking or calling tools directly)...")
    # This will likely hit AkShare first. 
    # To test fallback specifically, we'd need to mock AkShare failure, but for now just ensuring imports work and function runs is good.
    
    print("Fetching Financials for 600519...")
    res = get_financials("600519")
    print(f"Result keys: {res.keys()}")
    
    print("Fetching Kline for 600519...")
    res_k = get_kline("600519", limit=5)
    print(f"Result (first item): {res_k[0] if res_k else 'None'}")

if __name__ == "__main__":
    try:
        test_baostock_connectivity()
        test_fallback_logic()
    except Exception as e:
        print(f"Verification Failed: {e}")
