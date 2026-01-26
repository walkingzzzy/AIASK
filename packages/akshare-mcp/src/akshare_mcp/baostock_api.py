
import baostock as bs
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

class BaostockClient:
    _instance = None
    _logged_in = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BaostockClient, cls).__new__(cls)
        return cls._instance

    def login(self):
        if not self._logged_in:
            lg = bs.login()
            if lg.error_code == '0':
                self._logged_in = True
            else:
                import sys
                print(f"Baostock login failed: {lg.error_msg}", file=sys.stderr)
        return self._logged_in

    def logout(self):
        if self._logged_in:
            bs.logout()
            self._logged_in = False

    def normalize_code(self, code: str) -> str:
        """Ensure code is in sh.XXXXXX or sz.XXXXXX format"""
        if code.startswith(('sh.', 'sz.')):
            return code
        if code.startswith('6'):
            return f"sh.{code}"
        else:
            return f"sz.{code}"

    def get_balance_sheet(self, code: str, year: str, quarter: str) -> pd.DataFrame:
        """获取资产负债表"""
        self.login()
        bs_code = self.normalize_code(code)
        rs = bs.query_balance_data(code=bs_code, year=year, quarter=quarter)
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            return pd.DataFrame()
            
        return pd.DataFrame(data_list, columns=rs.fields)

    def get_profit_statement(self, code: str, year: str, quarter: str) -> pd.DataFrame:
        """获取利润表"""
        self.login()
        bs_code = self.normalize_code(code)
        rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
            
        if not data_list:
            return pd.DataFrame()
            
        return pd.DataFrame(data_list, columns=rs.fields)

    def get_history_k_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取历史K线"""
        self.login()
        bs_code = self.normalize_code(code)
        # frequency: d=日k, w=周, m=月
        rs = bs.query_history_k_data_plus(bs_code,
            "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3") # 3=默认不复权，建议客户端处理，或者这里用2前复权

        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
            
        if not data_list:
            return pd.DataFrame()
            
        return pd.DataFrame(data_list, columns=rs.fields)

# Global instance
baostock_client = BaostockClient()
