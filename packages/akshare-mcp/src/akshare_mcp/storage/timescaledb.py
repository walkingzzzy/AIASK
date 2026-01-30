"""
TimescaleDB 适配器
对齐 Node 版本的 timescaledb.ts，提供统一的数据库访问接口
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from contextlib import asynccontextmanager

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None


class TimescaleDBAdapter:
    """TimescaleDB 异步适配器"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """初始化数据库连接池"""
        if self._initialized:
            return
            
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg not installed. Run: pip install asyncpg")
        
        # 从环境变量读取配置
        db_config = {
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'min_size': 10,
            'max_size': 20,
            'command_timeout': int(os.getenv('DB_CONNECT_TIMEOUT_MS', '10000')) / 1000,
        }
        
        try:
            self.pool = await asyncpg.create_pool(**db_config)
            self._initialized = True
            print(f"[TimescaleDB] Connected to {db_config['host']}:{db_config['port']}/{db_config['database']}")
            
            # 初始化数据库表
            await self._init_tables()
        except Exception as e:
            print(f"[TimescaleDB] Connection failed: {e}")
            raise
    
    async def _init_tables(self) -> None:
        """初始化数据库表结构（对齐Node版本）"""
        async with self.acquire() as conn:
            # 1. 创建K线表（Hypertable）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS kline_1d (
                    time TIMESTAMPTZ NOT NULL,
                    code TEXT NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume BIGINT NOT NULL,
                    amount DOUBLE PRECISION,
                    turnover DOUBLE PRECISION,
                    change_pct DOUBLE PRECISION,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (time, code)
                );
            """)
            
            # 2. 创建财务数据表（与Node.js版本对齐，使用stock_code字段）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS financials (
                    stock_code TEXT NOT NULL,
                    report_date DATE NOT NULL,
                    revenue DOUBLE PRECISION,
                    net_profit DOUBLE PRECISION,
                    gross_margin DOUBLE PRECISION,
                    net_margin DOUBLE PRECISION,
                    debt_ratio DOUBLE PRECISION,
                    current_ratio DOUBLE PRECISION,
                    eps DOUBLE PRECISION,
                    roe DOUBLE PRECISION,
                    bvps DOUBLE PRECISION,
                    roa DOUBLE PRECISION,
                    revenue_growth DOUBLE PRECISION,
                    profit_growth DOUBLE PRECISION,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (stock_code, report_date)
                );
            """)
            
            # 3. 创建股票信息表（与Node.js版本对齐，使用stock_code字段）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stocks (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    market TEXT,
                    sector TEXT,
                    industry TEXT,
                    list_date DATE,
                    market_cap DOUBLE PRECISION,
                    pe_ratio DOUBLE PRECISION,
                    pb_ratio DOUBLE PRECISION,
                    kline_sync_attempted TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            
            # 4. 创建实时行情表（Hypertable）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_quotes (
                    time TIMESTAMPTZ NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT,
                    price DOUBLE PRECISION,
                    change_pct DOUBLE PRECISION,
                    change_amt DOUBLE PRECISION,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    prev_close DOUBLE PRECISION,
                    volume BIGINT,
                    amount DOUBLE PRECISION,
                    pe DOUBLE PRECISION,
                    pb DOUBLE PRECISION,
                    mkt_cap DOUBLE PRECISION,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code 
                ON stock_quotes (time, code);
            """)
            
            # 5. 创建组合管理表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default',
                    initial_capital DOUBLE PRECISION NOT NULL,
                    current_value DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS holdings (
                    id SERIAL PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    shares INTEGER NOT NULL,
                    cost_price DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(portfolio_id, code)
                );
            """)
            
            # 6. 创建模拟交易表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    initial_capital DOUBLE PRECISION NOT NULL,
                    current_capital DOUBLE PRECISION NOT NULL,
                    total_value DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id SERIAL PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    cost_price DOUBLE PRECISION NOT NULL,
                    current_price DOUBLE PRECISION,
                    market_value DOUBLE PRECISION,
                    profit_rate DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(account_id, stock_code)
                );
                
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    quantity INTEGER NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    commission DOUBLE PRECISION DEFAULT 0,
                    trade_time TIMESTAMPTZ NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_paper_trades_account 
                ON paper_trades(account_id, trade_time DESC);
            """)
            
            # 7. 创建回测结果表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    params TEXT,
                    stocks TEXT,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    initial_capital DOUBLE PRECISION NOT NULL,
                    final_capital DOUBLE PRECISION NOT NULL,
                    total_return DOUBLE PRECISION,
                    annual_return DOUBLE PRECISION,
                    max_drawdown DOUBLE PRECISION,
                    sharpe_ratio DOUBLE PRECISION,
                    sortino_ratio DOUBLE PRECISION,
                    win_rate DOUBLE PRECISION,
                    profit_factor DOUBLE PRECISION,
                    avg_win DOUBLE PRECISION,
                    avg_loss DOUBLE PRECISION,
                    expectancy DOUBLE PRECISION,
                    avg_holding_days DOUBLE PRECISION,
                    exposure_rate DOUBLE PRECISION,
                    max_consecutive_loss INTEGER,
                    trades_count INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id TEXT PRIMARY KEY,
                    backtest_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    shares INTEGER NOT NULL,
                    gross_value DOUBLE PRECISION NOT NULL,
                    fee DOUBLE PRECISION DEFAULT 0,
                    slippage DOUBLE PRECISION DEFAULT 0,
                    net_value DOUBLE PRECISION NOT NULL,
                    cash_balance DOUBLE PRECISION NOT NULL,
                    equity DOUBLE PRECISION NOT NULL,
                    trade_date DATE NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS backtest_equity (
                    id SERIAL PRIMARY KEY,
                    backtest_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    close DOUBLE PRECISION,
                    cash DOUBLE PRECISION NOT NULL,
                    shares INTEGER,
                    equity DOUBLE PRECISION NOT NULL,
                    daily_return DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(backtest_id, date)
                );
                
                CREATE INDEX IF NOT EXISTS idx_backtest_trades_id 
                ON backtest_trades(backtest_id, trade_date);
                
                CREATE INDEX IF NOT EXISTS idx_backtest_equity_id 
                ON backtest_equity(backtest_id, date);
            """)
            
            # 8. 创建告警表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    code TEXT,
                    indicator TEXT,
                    condition TEXT,
                    value DOUBLE PRECISION,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT NOT NULL,
                    target_price DOUBLE PRECISION,
                    condition TEXT,
                    status TEXT DEFAULT 'active',
                    triggered_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS combo_alerts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    logic TEXT NOT NULL DEFAULT 'and',
                    status TEXT DEFAULT 'active',
                    triggered_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS indicator_alerts (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT NOT NULL,
                    indicator TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    threshold DOUBLE PRECISION,
                    status TEXT DEFAULT 'active',
                    triggered_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            
            # 9. 创建自选股表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                INSERT INTO watchlist_groups (id, name, sort_order) 
                VALUES ('default', '默认分组', 0) ON CONFLICT DO NOTHING;
                
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    group_id TEXT DEFAULT 'default',
                    tags JSONB DEFAULT '[]'::jsonb,
                    notes TEXT,
                    added_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(code, group_id)
                );
            """)
            
            # 10. 创建向量检索表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_embeddings (
                    stock_code TEXT PRIMARY KEY,
                    embedding REAL[],
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS pattern_vectors (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT,
                    window_size INTEGER,
                    embedding REAL[],
                    start_date DATE,
                    end_date DATE,
                    pattern_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS vector_documents (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT,
                    doc_type TEXT,
                    content TEXT,
                    date DATE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_vector_doc_content 
                ON vector_documents USING GIN(to_tsvector('simple', content));
            """)
            
            # 11. 创建市场板块表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_blocks (
                    id SERIAL PRIMARY KEY,
                    block_code VARCHAR(50) NOT NULL,
                    block_name VARCHAR(100) NOT NULL,
                    block_type VARCHAR(20) NOT NULL,
                    stock_count INTEGER DEFAULT 0,
                    avg_change_pct DECIMAL(10, 4),
                    total_amount DECIMAL(20, 2),
                    leader_code VARCHAR(20),
                    leader_name VARCHAR(50),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(block_code, block_type)
                );
                
                CREATE INDEX IF NOT EXISTS idx_market_blocks_type 
                ON market_blocks(block_type);
                
                CREATE INDEX IF NOT EXISTS idx_market_blocks_updated 
                ON market_blocks(updated_at DESC);
            """)
            
            # 12. 创建板块成分股表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS block_stocks (
                    id SERIAL PRIMARY KEY,
                    block_code VARCHAR(50) NOT NULL,
                    stock_code VARCHAR(20) NOT NULL,
                    stock_name VARCHAR(50),
                    weight DECIMAL(10, 4),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(block_code, stock_code)
                );
                
                CREATE INDEX IF NOT EXISTS idx_block_stocks_block 
                ON block_stocks(block_code);
                
                CREATE INDEX IF NOT EXISTS idx_block_stocks_stock 
                ON block_stocks(stock_code);
            """)
            
            # 13. 创建数据质量表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    id SERIAL PRIMARY KEY,
                    dataset TEXT,
                    stock_code TEXT,
                    reason TEXT,
                    source TEXT,
                    payload TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            
            # 14. 创建数据同步任务表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_tasks (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT UNIQUE NOT NULL,
                    task_type TEXT NOT NULL,
                    codes TEXT[],
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                );
                
                CREATE INDEX IF NOT EXISTS idx_sync_tasks_status ON sync_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_sync_tasks_created ON sync_tasks(created_at DESC);
            """)
            
            # 15. 创建数据同步调度表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_schedules (
                    id SERIAL PRIMARY KEY,
                    schedule_id TEXT UNIQUE NOT NULL,
                    task_type TEXT NOT NULL,
                    codes TEXT[],
                    schedule TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT true,
                    last_run TIMESTAMPTZ,
                    next_run TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_sync_schedules_enabled ON sync_schedules(enabled);
                CREATE INDEX IF NOT EXISTS idx_sync_schedules_next_run ON sync_schedules(next_run);
            """)
            
            print("[TimescaleDB] All tables initialized successfully (aligned with Node version)")
    
    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            print("[TimescaleDB] Connection closed")
    
    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接"""
        if not self._initialized:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            yield conn
    
    # ========== K线数据 ==========
    
    async def get_klines(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        查询K线数据
        
        Args:
            code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD 或 YYYY)
            end_date: 结束日期 (YYYY-MM-DD 或 YYYY)
            limit: 限制返回条数
        
        Returns:
            K线数据列表
        """
        from datetime import datetime
        
        async with self.acquire() as conn:
            query = """
                SELECT 
                    time, code, open, high, low, close, 
                    volume, amount, turnover, change_pct
                FROM kline_1d
                WHERE code = $1
            """
            params = [code]
            param_idx = 2
            
            if start_date:
                # 确保日期格式正确，支持多种格式
                if isinstance(start_date, str):
                    # 如果是年份，转换为年初日期
                    if len(start_date) == 4:
                        start_date = f"{start_date}-01-01"
                    # 转换为datetime对象
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    query += f" AND time >= ${param_idx}::date"
                    params.append(start_date_obj)
                    param_idx += 1
            
            if end_date:
                # 确保日期格式正确
                if isinstance(end_date, str):
                    # 如果是年份，转换为年末日期
                    if len(end_date) == 4:
                        end_date = f"{end_date}-12-31"
                    # 转换为datetime对象
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    query += f" AND time <= ${param_idx}::date"
                    params.append(end_date_obj)
                    param_idx += 1
            
            query += " ORDER BY time DESC"
            
            if limit:
                query += f" LIMIT ${param_idx}"
                params.append(limit)
            
            rows = await conn.fetch(query, *params)
            
            return [
                {
                    'date': row['time'].strftime('%Y-%m-%d') if isinstance(row['time'], (datetime, date)) else str(row['time']),
                    'code': row['code'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume']),
                    'amount': float(row['amount']) if row['amount'] else None,
                    'turnover': float(row['turnover']) if row['turnover'] else None,
                    'change_pct': float(row['change_pct']) if row['change_pct'] else None,
                }
                for row in rows
            ]
    
    async def save_klines(self, klines: List[Dict[str, Any]]) -> int:
        """
        批量保存K线数据
        
        Args:
            klines: K线数据列表
        
        Returns:
            插入/更新的行数
        """
        if not klines:
            return 0
        
        async with self.acquire() as conn:
            # 使用 UPSERT (ON CONFLICT DO UPDATE)
            query = """
                INSERT INTO kline_1d (
                    time, code, open, high, low, close, 
                    volume, amount, turnover, change_pct, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (time, code) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    turnover = EXCLUDED.turnover,
                    change_pct = EXCLUDED.change_pct,
                    updated_at = NOW()
            """
            
            # 批量执行
            await conn.executemany(
                query,
                [
                    (
                        k['date'], k['code'], k['open'], k['high'], k['low'], k['close'],
                        k['volume'], k.get('amount'), k.get('turnover'), k.get('change_pct')
                    )
                    for k in klines
                ]
            )
            
            return len(klines)
    
    # ========== 股票信息 ==========
    
    async def get_stock_info(self, code: str) -> Optional[Dict[str, Any]]:
        """查询股票基本信息"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    stock_code, stock_name, industry, market_cap, 
                    pe_ratio, pb_ratio, list_date
                FROM stocks
                WHERE stock_code = $1
                """,
                code
            )
            
            if not row:
                return None
            
            return {
                'code': row['stock_code'],
                'name': row['stock_name'],
                'industry': row['industry'],
                'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                'pe_ratio': float(row['pe_ratio']) if row['pe_ratio'] else None,
                'pb_ratio': float(row['pb_ratio']) if row['pb_ratio'] else None,
                'list_date': row['list_date'].strftime('%Y-%m-%d') if row['list_date'] else None,
            }
    
    async def search_stocks(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索股票（支持代码和名称）"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT stock_code, stock_name, industry, market_cap
                FROM stocks
                WHERE stock_code LIKE $1 OR stock_name LIKE $2
                ORDER BY market_cap DESC NULLS LAST
                LIMIT $3
                """,
                f'%{keyword}%', f'%{keyword}%', limit
            )
            
            return [
                {
                    'code': row['stock_code'],
                    'name': row['stock_name'],
                    'industry': row['industry'],
                    'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                }
                for row in rows
            ]
    
    # ========== 财务数据 ==========
    
    async def get_financials(
        self,
        code: str,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """查询财务数据"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    stock_code, report_date, revenue, net_profit, 
                    roe, debt_ratio, revenue_growth, profit_growth
                FROM financials
                WHERE stock_code = $1
                ORDER BY report_date DESC
                LIMIT $2
                """,
                code, limit
            )
            
            return [
                {
                    'code': row['stock_code'],
                    'report_date': row['report_date'].strftime('%Y-%m-%d') if row['report_date'] else None,
                    'revenue': float(row['revenue']) if row['revenue'] else None,
                    'net_profit': float(row['net_profit']) if row['net_profit'] else None,
                    'roe': float(row['roe']) if row['roe'] else None,
                    'debt_ratio': float(row['debt_ratio']) if row['debt_ratio'] else None,
                    'revenue_growth': float(row['revenue_growth']) if row['revenue_growth'] else None,
                    'profit_growth': float(row['profit_growth']) if row['profit_growth'] else None,
                }
                for row in rows
            ]
    
    # ========== 实时行情 ==========
    
    async def save_quote(self, quote: Dict[str, Any]) -> None:
        """
        保存实时行情（统一字段映射）
        
        字段映射规则（对齐Node版本）：
        - prev_close（标准） ← pre_close（兼容）
        - change_amt（标准） ← change（兼容）
        - mkt_cap（标准） ← market_cap（兼容）
        """
        async with self.acquire() as conn:
            # 统一字段映射
            normalized_quote = {
                'code': quote.get('code'),
                'name': quote.get('name'),
                'price': quote.get('price'),
                'change_amt': quote.get('change_amt') or quote.get('change'),
                'change_pct': quote.get('change_pct'),
                'open': quote.get('open'),
                'high': quote.get('high'),
                'low': quote.get('low'),
                'prev_close': quote.get('prev_close') or quote.get('pre_close'),
                'volume': quote.get('volume'),
                'amount': quote.get('amount'),
                'pe': quote.get('pe'),
                'pb': quote.get('pb'),
                'mkt_cap': quote.get('mkt_cap') or quote.get('market_cap'),
            }
            
            await conn.execute(
                """
                INSERT INTO stock_quotes (
                    time, code, name, price, change_amt, change_pct, 
                    open, high, low, prev_close, volume, amount,
                    pe, pb, mkt_cap
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (time, code) DO UPDATE SET
                    name = EXCLUDED.name,
                    price = EXCLUDED.price,
                    change_amt = EXCLUDED.change_amt,
                    change_pct = EXCLUDED.change_pct,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    prev_close = EXCLUDED.prev_close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    pe = EXCLUDED.pe,
                    pb = EXCLUDED.pb,
                    mkt_cap = EXCLUDED.mkt_cap
                """,
                datetime.now(), 
                normalized_quote['code'],
                normalized_quote['name'],
                normalized_quote['price'],
                normalized_quote['change_amt'],
                normalized_quote['change_pct'],
                normalized_quote['open'],
                normalized_quote['high'],
                normalized_quote['low'],
                normalized_quote['prev_close'],
                normalized_quote['volume'],
                normalized_quote['amount'],
                normalized_quote['pe'],
                normalized_quote['pb'],
                normalized_quote['mkt_cap']
            )
    
    # ========== 统计信息 ==========
    
    async def get_stats(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        async with self.acquire() as conn:
            stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks")
            kline_count = await conn.fetchval("SELECT COUNT(*) FROM kline_1d")
            financial_count = await conn.fetchval("SELECT COUNT(*) FROM financials")
            quote_count = await conn.fetchval("SELECT COUNT(*) FROM stock_quotes")
            
            return {
                'stock_count': stock_count or 0,
                'kline_count': kline_count or 0,
                'financial_count': financial_count or 0,
                'quote_count': quote_count or 0,
            }


# 全局单例
_db_instance: Optional[TimescaleDBAdapter] = None


def get_db() -> TimescaleDBAdapter:
    """获取数据库实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = TimescaleDBAdapter()
    return _db_instance
