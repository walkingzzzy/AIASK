"""
时序数据库
基于SQLite的轻量级时序数据存储
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class TimeSeriesDB:
    """
    时序数据库
    
    用于存储股票历史行情数据，支持：
    - 日线/周线/月线数据存储
    - 按时间范围查询
    - 数据压缩和归档
    """
    
    def __init__(self, db_path: str = "data/timeseries.db"):
        """
        初始化时序数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 日线数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    change_pct REAL,
                    turnover REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, trade_date)
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_code_date 
                ON daily_bars(stock_code, trade_date)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_date 
                ON daily_bars(trade_date)
            """)
            
            # 周线数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weekly_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    change_pct REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, week_start)
                )
            """)
            
            # 元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT,
                    market TEXT,
                    industry TEXT,
                    list_date TEXT,
                    last_update TEXT,
                    data_start TEXT,
                    data_end TEXT,
                    extra_info TEXT
                )
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def save_daily_bars(self, stock_code: str, bars: List[Dict]) -> int:
        """
        保存日线数据
        
        Args:
            stock_code: 股票代码
            bars: 日线数据列表 [{'date', 'open', 'high', 'low', 'close', 'volume', ...}]
            
        Returns:
            保存的记录数
        """
        if not bars:
            return 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            saved = 0
            for bar in bars:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO daily_bars 
                        (stock_code, trade_date, open, high, low, close, 
                         volume, amount, change_pct, turnover)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        stock_code,
                        bar.get('date') or bar.get('trade_date'),
                        bar.get('open'),
                        bar.get('high'),
                        bar.get('low'),
                        bar.get('close'),
                        bar.get('volume'),
                        bar.get('amount'),
                        bar.get('change_pct') or bar.get('change_percent'),
                        bar.get('turnover')
                    ))
                    saved += 1
                except Exception as e:
                    logger.error(f"保存日线数据失败 {stock_code}: {e}")
            
            conn.commit()
            
            # 更新元数据
            self._update_metadata(cursor, stock_code, bars)
            conn.commit()
            
            return saved
    
    def get_daily_bars(self, stock_code: str, 
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       limit: int = 1000) -> List[Dict]:
        """
        获取日线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            limit: 返回数量限制
            
        Returns:
            日线数据列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM daily_bars WHERE stock_code = ?"
            params = [stock_code]
            
            if start_date:
                query += " AND trade_date >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND trade_date <= ?"
                params.append(end_date)
            
            query += " ORDER BY trade_date DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    def get_latest_bar(self, stock_code: str) -> Optional[Dict]:
        """获取最新一条日线数据"""
        bars = self.get_daily_bars(stock_code, limit=1)
        return bars[0] if bars else None
    
    def _update_metadata(self, cursor, stock_code: str, bars: List[Dict]):
        """更新元数据"""
        if not bars:
            return
        
        dates = [b.get('date') or b.get('trade_date') for b in bars if b.get('date') or b.get('trade_date')]
        if not dates:
            return
        
        data_start = min(dates)
        data_end = max(dates)
        
        cursor.execute("""
            INSERT OR REPLACE INTO metadata 
            (stock_code, last_update, data_start, data_end)
            VALUES (?, ?, 
                    COALESCE((SELECT data_start FROM metadata WHERE stock_code = ?), ?),
                    ?)
        """, (stock_code, datetime.now().isoformat(), stock_code, data_start, data_end))
    
    def get_metadata(self, stock_code: str) -> Optional[Dict]:
        """获取股票元数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metadata WHERE stock_code = ?", (stock_code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_metadata(self, stock_code: str, **kwargs):
        """更新股票元数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 构建更新语句
            fields = []
            values = []
            for key, value in kwargs.items():
                if key in ['stock_name', 'market', 'industry', 'list_date', 'extra_info']:
                    fields.append(f"{key} = ?")
                    values.append(value)
            
            if fields:
                values.append(stock_code)
                cursor.execute(f"""
                    UPDATE metadata SET {', '.join(fields)}
                    WHERE stock_code = ?
                """, values)
                conn.commit()
    
    def get_stock_list(self) -> List[str]:
        """获取所有有数据的股票代码"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT stock_code FROM daily_bars")
            return [row[0] for row in cursor.fetchall()]
    
    def delete_old_data(self, days: int = 365 * 5) -> int:
        """
        删除旧数据
        
        Args:
            days: 保留最近多少天的数据
            
        Returns:
            删除的记录数
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM daily_bars WHERE trade_date < ?", 
                (cutoff_date,)
            )
            deleted = cursor.rowcount
            conn.commit()
            
            # 清理空间
            cursor.execute("VACUUM")
            
            return deleted
    
    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM daily_bars")
            daily_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT stock_code) FROM daily_bars")
            stock_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_bars")
            date_range = cursor.fetchone()
            
            return {
                'daily_records': daily_count,
                'stock_count': stock_count,
                'date_range': f"{date_range[0]} ~ {date_range[1]}" if date_range[0] else 'N/A',
                'db_path': self.db_path
            }
