
from datetime import datetime, timedelta, date
import akshare as ak

_latest_trade_date_cache: date = None
_latest_trade_date_ts: float = 0

def get_latest_trading_date() -> str:
    """
    Get the latest confirmed trading date (YYYYMMDD).
    Uses caching to avoid frequent API calls.
    """
    global _latest_trade_date_cache, _latest_trade_date_ts
    
    # Cache for 1 hour
    if _latest_trade_date_cache and (datetime.now().timestamp() - _latest_trade_date_ts < 3600):
        return _latest_trade_date_cache.strftime("%Y%m%d")

    try:
        # Use Sina's trade date interface as anchor
        df = ak.tool_trade_date_hist_sina()
        if df is not None and not df.empty:
            today = date.today()
            # Ensure trade_date column is date type
            if not isinstance(df.iloc[0]["trade_date"], (date, datetime)):
                 df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            
            # Filter for past/today only
            df = df[df["trade_date"] <= today]
            
            if not df.empty:
                last_date = df.iloc[-1]["trade_date"]
                _latest_trade_date_cache = last_date
                _latest_trade_date_ts = datetime.now().timestamp()
                return last_date.strftime("%Y%m%d")
    except Exception:
        pass
    
    # Fallback: Today if weekday, else previous Friday
    # Simple logic (not perfect for holidays but better than crashing)
    d = date.today()
    if d.weekday() == 5: # Sat
        d = d - timedelta(days=1)
    elif d.weekday() == 6: # Sun
        d = d - timedelta(days=2)
    
    return d.strftime("%Y%m%d")

def format_date_dash(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD"""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str
