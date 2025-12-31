"""
本地SQLite数据库适配器
从本地数据库读取股票数据
"""
import sqlite3
from typing import Optional, List, Any
from datetime import datetime
import logging
import os

from .base_adapter import BaseDataAdapter, StockQuote, DailyBar, FinancialData

logger = logging.getLogger(__name__)


class LocalDBAdapter(BaseDataAdapter):
    """
    本地SQLite数据库适配器
    
    从 data/stock_vectors.db 读取股票数据
    优先级最高，作为主数据源
    """
    
    def __init__(self, db_path: str = "data/stock_vectors.db"):
        super().__init__("LocalDB", priority=100)  # 最高优先级
        self.db_path = db_path
        self._check_database()
    
    def _check_database(self):
        """检查数据库是否存在"""
        if os.path.exists(self.db_path):
            self._is_available = True
            logger.info(f"本地数据库已连接: {self.db_path}")
        else:
            self._is_available = False
            logger.warning(f"本地数据库不存在: {self.db_path}")
    
    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """
        获取实时行情
        从本地数据库获取最新的日线数据作为"实时"数据
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 获取最新的日线数据
            cursor.execute("""
                SELECT d.stock_code, s.stock_name, d.date, d.open, d.high, d.low, d.close, 
                       d.volume, d.amount, d.change_percent, d.turnover
                FROM daily_bars d
                LEFT JOIN stocks s ON d.stock_code = s.stock_code
                WHERE d.stock_code = ?
                ORDER BY d.date DESC
                LIMIT 2
            """, (stock_code,))
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return None
            
            row = rows[0]
            prev_close = rows[1][6] if len(rows) > 1 else row[6]
            
            return StockQuote(
                stock_code=row[0],
                stock_name=row[1] or stock_code,
                current_price=row[6],  # close
                change_amount=row[6] - prev_close,
                change_percent=row[9] or 0,
                open_price=row[3],
                high_price=row[4],
                low_price=row[5],
                prev_close=prev_close,
                volume=row[7],
                amount=row[8] or 0,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"获取实时行情失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_daily_bars(self, stock_code: str, start_date: str, 
                       end_date: str) -> Optional[List[DailyBar]]:
        """获取日线数据"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 转换日期格式 (YYYYMMDD -> YYYY-MM-DD)
            if len(start_date) == 8:
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            if len(end_date) == 8:
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
            
            cursor.execute("""
                SELECT date, open, high, low, close, volume, amount, change_percent, turnover
                FROM daily_bars
                WHERE stock_code = ? AND date >= ? AND date <= ?
                ORDER BY date ASC
            """, (stock_code, start_date, end_date))
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                logger.warning(f"未找到 {stock_code} 在 {start_date} 到 {end_date} 的数据")
                return None
            
            bars = []
            for row in rows:
                bars.append(DailyBar(
                    date=row[0],
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                    amount=row[6] or 0,
                    change_percent=row[7] or 0,
                    turnover=row[8]
                ))
            
            logger.debug(f"从本地数据库获取 {stock_code} {len(bars)} 条日线数据")
            return bars
            
        except Exception as e:
            logger.error(f"获取日线数据失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """获取财务数据"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查financial_data表是否存在以及其结构
            cursor.execute("PRAGMA table_info(financial_data)")
            columns = [c[1] for c in cursor.fetchall()]
            
            if not columns:
                return None
            
            cursor.execute("""
                SELECT * FROM financial_data
                WHERE stock_code = ?
                ORDER BY report_date DESC
                LIMIT 1
            """, (stock_code,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            # 根据实际列构建FinancialData
            # 假设列顺序: id, stock_code, report_date, pe, pb, roe, ...
            return FinancialData(
                stock_code=stock_code,
                report_period=str(row[2]) if len(row) > 2 else "",
                roe=row[5] if len(row) > 5 else None,
                gross_margin=row[6] if len(row) > 6 else None,
                revenue_growth=row[8] if len(row) > 8 else None,
                profit_growth=row[10] if len(row) > 10 else None
            )
            
        except Exception as e:
            logger.error(f"获取财务数据失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_stock_list(self, market: str = 'all') -> Optional[List[dict]]:
        """获取股票列表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT code, name, market, industry
                FROM stocks
                ORDER BY code
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            stocks = []
            for row in rows:
                stocks.append({
                    'code': row[0],
                    'name': row[1],
                    'market': row[2],
                    'industry': row[3]
                })
            
            return stocks
            
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            self._last_error = str(e)
            return None
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            if not os.path.exists(self.db_path):
                self._is_available = False
                return False
            
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM daily_bars")
            count = cursor.fetchone()[0]
            conn.close()
            
            self._is_available = count > 0
            return self._is_available
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            self._is_available = False
            return False
