"""
用户数据库
存储自选股、决策记录、回测结果等用户数据
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class UserDataDB:
    """用户数据存储"""
    
    def __init__(self, db_path: str = "data/user_data.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 自选股表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default',
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    group_id TEXT DEFAULT 'default',
                    notes TEXT,
                    tags TEXT,
                    alert_price_high REAL,
                    alert_price_low REAL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, stock_code)
                )
            """)
            
            # 自选股分组表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_groups (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    name TEXT NOT NULL,
                    description TEXT,
                    color TEXT DEFAULT '#1890ff',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 决策记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decision_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default',
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    action TEXT NOT NULL,
                    reason TEXT,
                    price_at_decision REAL,
                    current_price REAL,
                    ai_suggested BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 回测结果表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT NOT NULL,
                    stock_codes TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    initial_capital REAL,
                    final_capital REAL,
                    total_return REAL,
                    annual_return REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    win_rate REAL,
                    total_trades INTEGER,
                    config_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 回测交易记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backtest_id INTEGER NOT NULL,
                    stock_code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    shares INTEGER,
                    amount REAL,
                    commission REAL,
                    pnl REAL,
                    FOREIGN KEY (backtest_id) REFERENCES backtest_results(id)
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_user ON decision_records(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtest_trades_id ON backtest_trades(backtest_id)")
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # ========== 自选股方法 ==========
    
    def add_watchlist_item(self, stock_code: str, stock_name: str = None,
                           group_id: str = 'default', user_id: str = 'default',
                           notes: str = None, tags: str = None,
                           alert_price_high: float = None, alert_price_low: float = None) -> bool:
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO watchlist 
                    (user_id, stock_code, stock_name, group_id, notes, tags, alert_price_high, alert_price_low)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, stock_code, stock_name, group_id, notes, tags, alert_price_high, alert_price_low))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"添加自选股失败: {e}")
                return False
    
    def remove_watchlist_item(self, stock_code: str, user_id: str = 'default') -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM watchlist WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
            conn.commit()
            return True
    
    def get_watchlist(self, user_id: str = 'default', group_id: str = None) -> List[Dict]:
        with self._get_connection() as conn:
            if group_id:
                rows = conn.execute(
                    "SELECT * FROM watchlist WHERE user_id = ? AND group_id = ? ORDER BY added_at DESC",
                    (user_id, group_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM watchlist WHERE user_id = ? ORDER BY added_at DESC",
                    (user_id,)
                ).fetchall()
            return [dict(row) for row in rows]
    
    def update_watchlist_item(self, stock_code: str, user_id: str = 'default', **kwargs) -> bool:
        allowed = ['stock_name', 'group_id', 'notes', 'tags', 'alert_price_high', 'alert_price_low']
        fields = [(k, v) for k, v in kwargs.items() if k in allowed]
        if not fields:
            return False
        with self._get_connection() as conn:
            sql = f"UPDATE watchlist SET {', '.join(f'{k}=?' for k, _ in fields)} WHERE user_id = ? AND stock_code = ?"
            conn.execute(sql, [v for _, v in fields] + [user_id, stock_code])
            conn.commit()
            return True
    
    # ========== 分组方法 ==========
    
    def create_group(self, group_id: str, name: str, user_id: str = 'default',
                     description: str = None, color: str = '#1890ff') -> bool:
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO watchlist_groups (id, user_id, name, description, color)
                    VALUES (?, ?, ?, ?, ?)
                """, (group_id, user_id, name, description, color))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"创建分组失败: {e}")
                return False
    
    def delete_group(self, group_id: str, user_id: str = 'default') -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM watchlist_groups WHERE id = ? AND user_id = ?", (group_id, user_id))
            conn.execute("UPDATE watchlist SET group_id = 'default' WHERE group_id = ? AND user_id = ?", (group_id, user_id))
            conn.commit()
            return True
    
    def get_groups(self, user_id: str = 'default') -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist_groups WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]
    
    def update_group(self, group_id: str, user_id: str = 'default', **kwargs) -> bool:
        allowed = ['name', 'description', 'color']
        fields = [(k, v) for k, v in kwargs.items() if k in allowed]
        if not fields:
            return False
        with self._get_connection() as conn:
            sql = f"UPDATE watchlist_groups SET {', '.join(f'{k}=?' for k, _ in fields)} WHERE id = ? AND user_id = ?"
            conn.execute(sql, [v for _, v in fields] + [group_id, user_id])
            conn.commit()
            return True
    
    # ========== 决策记录方法 ==========
    
    def add_decision_record(self, stock_code: str, action: str, user_id: str = 'default',
                            stock_name: str = None, reason: str = None,
                            price_at_decision: float = None, current_price: float = None,
                            ai_suggested: bool = False) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO decision_records 
                (user_id, stock_code, stock_name, action, reason, price_at_decision, current_price, ai_suggested)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, stock_code, stock_name, action, reason, price_at_decision, current_price, ai_suggested))
            conn.commit()
            return cursor.lastrowid
    
    def get_decision_records(self, user_id: str = 'default', stock_code: str = None, limit: int = 100) -> List[Dict]:
        with self._get_connection() as conn:
            if stock_code:
                rows = conn.execute(
                    "SELECT * FROM decision_records WHERE user_id = ? AND stock_code = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, stock_code, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM decision_records WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
            return [dict(row) for row in rows]
    
    def delete_decision_record(self, record_id: int) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM decision_records WHERE id = ?", (record_id,))
            conn.commit()
            return True
    
    # ========== 回测结果方法 ==========
    
    def save_backtest_result(self, strategy: str, result: Dict, trades: List[Dict] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO backtest_results 
                (strategy, stock_codes, start_date, end_date, initial_capital, final_capital,
                 total_return, annual_return, sharpe_ratio, max_drawdown, win_rate, total_trades, config_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy,
                result.get('stock_codes'),
                result.get('start_date'),
                result.get('end_date'),
                result.get('initial_capital'),
                result.get('final_capital'),
                result.get('total_return'),
                result.get('annual_return'),
                result.get('sharpe_ratio'),
                result.get('max_drawdown'),
                result.get('win_rate'),
                result.get('total_trades'),
                json.dumps(result.get('config', {}))
            ))
            backtest_id = cursor.lastrowid
            
            if trades:
                for t in trades:
                    conn.execute("""
                        INSERT INTO backtest_trades 
                        (backtest_id, stock_code, trade_date, action, price, shares, amount, commission, pnl)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (backtest_id, t.get('stock_code'), t.get('trade_date'), t.get('action'),
                          t.get('price'), t.get('shares'), t.get('amount'), t.get('commission'), t.get('pnl')))
            
            conn.commit()
            return backtest_id
    
    def get_backtest_results(self, strategy: str = None, limit: int = 50) -> List[Dict]:
        with self._get_connection() as conn:
            if strategy:
                rows = conn.execute(
                    "SELECT * FROM backtest_results WHERE strategy = ? ORDER BY created_at DESC LIMIT ?",
                    (strategy, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]
    
    def get_backtest_detail(self, backtest_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM backtest_results WHERE id = ?", (backtest_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            trades = conn.execute(
                "SELECT * FROM backtest_trades WHERE backtest_id = ? ORDER BY trade_date",
                (backtest_id,)
            ).fetchall()
            result['trades'] = [dict(t) for t in trades]
            return result
