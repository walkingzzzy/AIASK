
import akshare as ak
import pandas as pd
from datetime import datetime

# Adjust display
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def test_sina_cols():
    try:
        # yesterday
        d = "2025-01-22" # Fixed date that likely has data (or today if trading)
        # Try today
        d_today = datetime.now().strftime("%Y-%m-%d")
        print(f"Fetching Sina LHB for {d_today}...")
        df = ak.stock_lhb_detail_daily_sina(date=d_today)
        
        if df is None or df.empty:
            print("Today empty, trying known recent date 20241018 (random guess) or just verify method")
            # Try to get *some* data. akshare usually documents standard columns.
            # Let's try to search recent days until we get data
            from datetime import timedelta
            for i in range(10):
                d_check = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                print(f"Checking {d_check}...")
                try:
                    df = ak.stock_lhb_detail_daily_sina(date=d_check)
                    if df is not None and not df.empty:
                        print(f"Found data for {d_check}")
                        print("Columns:", df.columns.tolist())
                        print("First row:", df.iloc[0].to_dict())
                        return
                except:
                    pass
        else:
             print("Columns:", df.columns.tolist())
             print("First row:", df.iloc[0].to_dict())

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_sina_cols()
