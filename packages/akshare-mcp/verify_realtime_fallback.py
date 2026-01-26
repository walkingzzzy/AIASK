
import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from akshare_mcp.tools.market import _get_quote_sina, _get_quote_tencent, get_realtime_quote

def test_sina_direct():
    print("\n[Testing Sina Interface]")
    code = "600519"
    res = _get_quote_sina(code)
    if res:
        print(f"Success: {res['name']} Price: {res['price']} Source: {res['source']}")
    else:
        print("Sina failed.")

def test_tencent_direct():
    print("\n[Testing Tencent Interface]")
    code = "600519"
    res = _get_quote_tencent(code)
    if res:
        print(f"Success: {res['name']} Price: {res['price']} Source: {res['source']}")
    else:
        print("Tencent failed.")

def test_main_function():
    print("\n[Testing Main get_realtime_quote]")
    code = "600519"
    res = get_realtime_quote(code)
    if res.get("success"):
        data = res["data"]
        print(f"Success: {data['name']} Price: {data['price']} Source: {data.get('source', 'unknown')}")
    else:
        print(f"Failed: {res.get('error')}")

if __name__ == "__main__":
    try:
        test_sina_direct()
        test_tencent_direct()
        test_main_function()
    except Exception as e:
        print(f"Verification Error: {e}")
