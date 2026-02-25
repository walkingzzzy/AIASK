# TdxQuant Common Functions Test
# Tests: subscribe_hq, unsubscribe_hq, get_subscribe_hq_stock_list,
#        refresh_cache, refresh_kline, send_message, send_warn,
#        send_file, send_bt_data, download_file

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\new_tdx_test\PYPlugins\user')

from tqcenter import tq

tq.initialize(__file__)

def test_subscribe_hq():
    """Test subscribe_hq and related functions"""
    print("=" * 60)
    print("[Test 1] subscribe_hq / unsubscribe_hq / get_subscribe_hq_stock_list")
    print("=" * 60)

    try:
        # Define callback function
        def my_callback(data_str):
            print(f"   Callback received: {data_str}")
            return None

        # Subscribe
        sub_res = tq.subscribe_hq(stock_list=['688318.SH'], callback=my_callback)
        print(f"   Subscribe result: {sub_res}")

        # Get subscribed list
        sub_list = tq.get_subscribe_hq_stock_list()
        print(f"   Subscribed list: {sub_list}")

        # Unsubscribe
        unsub_res = tq.unsubscribe_hq(stock_list=['688318.SH'])
        print(f"   Unsubscribe result: {unsub_res}")

        # Verify unsubscribed
        sub_list_after = tq.get_subscribe_hq_stock_list()
        print(f"   List after unsubscribe: {sub_list_after}")

        print("[PASS] Subscribe/Unsubscribe test success")
        return True
    except Exception as e:
        print(f"[FAIL] Subscribe test failed: {e}")
        return False

def test_refresh_cache():
    """Test refresh_cache"""
    print("\n" + "=" * 60)
    print("[Test 2] refresh_cache")
    print("=" * 60)

    try:
        # Note: This will trigger a loading dialog in TDX client
        # Try without parameters first (default behavior)
        result = tq.refresh_cache()
        print(f"   Result: {result}")
        print("[PASS] refresh_cache success")
        return True
    except Exception as e:
        print(f"[FAIL] refresh_cache failed: {e}")
        return False

def test_refresh_kline():
    """Test refresh_kline"""
    print("\n" + "=" * 60)
    print("[Test 3] refresh_kline")
    print("=" * 60)

    try:
        result = tq.refresh_kline(stock_list=['688318.SH'], period='1d')
        print(f"   Result: {result}")
        print("[PASS] refresh_kline success")
        return True
    except Exception as e:
        print(f"[FAIL] refresh_kline failed: {e}")
        return False

def test_send_message():
    """Test send_message"""
    print("\n" + "=" * 60)
    print("[Test 4] send_message")
    print("=" * 60)

    try:
        result = tq.send_message("TdxQuant API Test | Line 2 of message")
        print(f"   Result: {result}")
        print("[PASS] send_message success")
        return True
    except Exception as e:
        print(f"[FAIL] send_message failed: {e}")
        return False

def test_send_warn():
    """Test send_warn"""
    print("\n" + "=" * 60)
    print("[Test 5] send_warn")
    print("=" * 60)

    try:
        result = tq.send_warn(
            stock_list=['688318.SH'],
            time_list=['20260203150000'],
            price_list=['135.97'],
            close_list=['132.32'],
            volum_list=['23740'],
            bs_flag_list=['0'],
            warn_type_list=['0'],
            reason_list=['API Test Warning'],
            count=1
        )
        print(f"   Result: {result}")
        print("[PASS] send_warn success")
        return True
    except Exception as e:
        print(f"[FAIL] send_warn failed: {e}")
        return False

def test_send_bt_data():
    """Test send_bt_data"""
    print("\n" + "=" * 60)
    print("[Test 6] send_bt_data")
    print("=" * 60)

    try:
        result = tq.send_bt_data(
            stock_code='688318.SH',
            time_list=['20260203150000'],
            data_list=[['100', '200', '300']],
            count=1
        )
        print(f"   Result: {result}")
        print("[PASS] send_bt_data success")
        return True
    except Exception as e:
        print(f"[FAIL] send_bt_data failed: {e}")
        return False

def test_download_file():
    """Test download_file"""
    print("\n" + "=" * 60)
    print("[Test 7] download_file")
    print("=" * 60)

    try:
        # Download top 10 shareholders data
        result = tq.download_file(stock_code='688318.SH', down_time='20250101', down_type=1)
        print(f"   Top 10 shareholders: {result}")
        print("[PASS] download_file success")
        return True
    except Exception as e:
        print(f"[FAIL] download_file failed: {e}")
        return False


def test_send_file():
    """Test send_file"""
    print("\n" + "=" * 60)
    print("[Test 8] send_file")
    print("=" * 60)

    try:
        # Create a test file first
        import os
        test_file = os.path.join(os.path.dirname(__file__), 'test_output.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("TdxQuant API Test File\nThis is a test.")

        result = tq.send_file(test_file)
        print(f"   Result: {result}")

        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)

        print("[PASS] send_file success")
        return True
    except Exception as e:
        print(f"[FAIL] send_file failed: {e}")
        return False

def main():
    print("\n" + "#" * 60)
    print("#  TdxQuant Common Functions Test")
    print("#" * 60 + "\n")

    results = []
    results.append(("subscribe_hq", test_subscribe_hq()))
    results.append(("refresh_cache", test_refresh_cache()))
    results.append(("refresh_kline", test_refresh_kline()))
    results.append(("send_message", test_send_message()))
    results.append(("send_warn", test_send_warn()))
    results.append(("send_bt_data", test_send_bt_data()))
    results.append(("download_file", test_download_file()))
    results.append(("send_file", test_send_file()))

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

