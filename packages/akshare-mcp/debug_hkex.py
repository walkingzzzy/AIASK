
import sys
import os
import requests
import json
from datetime import datetime, timedelta

# Ensure src is in path to reuse logic
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from akshare_mcp.tools.fund_flow import _north_fund_from_hkex, _HKEX_DAILY_STAT_URL

def test_hkex_direct(date_str):
    print(f"Testing HKEX for {date_str}...")
    url = _HKEX_DAILY_STAT_URL.format(date=date_str)
    print(f"URL: {url}")
    try:
        resp = requests.get(url, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print("Response Length:", len(resp.text))
            # Clean up JS to get JSON
            payload = resp.text.strip()
            if payload.startswith("tabData ="):
                payload = payload[len("tabData =") :].strip()
            if payload.endswith(";"):
                payload = payload[:-1]
            import json
            import json
            try:
                data = json.loads(payload)
                print(f"TabData Count: {len(data)}")
                for idx, item in enumerate(data):
                    print(f"\n--- Item {idx}: {item.get('market')} ---")
                    content = item.get("content", [])
                    if content:
                        table = content[0].get("table", {})
                        print("Schema:", table.get("schema"))
                        tr = table.get("tr", [])
                        if tr:
                            print("Row 0:", tr[0])
            except:
                print("Raw Text (Failed to parse JSON):")
                print(resp.text[:1000])
        else:
            print("❌ Request failed")
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_wrapper(days=5):
    print(f"\nTesting _north_fund_from_hkex(days={days})...")
    res = _north_fund_from_hkex(days)
    print(f"Result count: {len(res)}")
    if res:
        print("Sample:", res[0])
    else:
        print("Empty result")

if __name__ == "__main__":
    # Try a known recent date (e.g. yesterday)
    # Note: user system time is 2026. Real world is 2025?
    # I should try a generic 'yesterday' based on system time first, 
    # but if system time is 2026, HKEX won't have it.
    # I will try a 2025 date manually just to see if scraper works.
    
    # Try 2025-01-20 (Recent Monday)
    test_hkex_direct("20250120")
    
    # Try System Time based (2026 - if mocked)
    d = datetime.now().strftime("%Y%m%d")
    print(f"\nSystem Time Date: {d}")
    test_hkex_direct(d)
    
    test_wrapper()
