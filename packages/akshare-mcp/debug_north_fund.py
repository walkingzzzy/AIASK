
import akshare as ak
import pandas as pd

def test_raw_akshare():
    print("Fetching North Fund History (EM)...")
    try:
        sh_df = ak.stock_hsgt_hist_em(symbol="沪股通")
        print("SH DF shape:", sh_df.shape if sh_df is not None else "None")
        if sh_df is not None and not sh_df.empty:
            print("Columns:", sh_df.columns.tolist())
            pd.set_option('display.max_columns', None)
            valid_df = sh_df.dropna(subset=['当日成交净买额'])
            if not valid_df.empty:
                print("\nLast valid row:")
                print(valid_df.tail(1))
            else:
                print("\nNo valid rows found!")
            
            # Check row 0 types
            print("\nRow 0 types:")
            print(sh_df.dtypes)
            
    except Exception as e:
        print(f"Error fetching SH: {e}")

if __name__ == "__main__":
    test_raw_akshare()
