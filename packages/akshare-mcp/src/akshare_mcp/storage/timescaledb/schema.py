"""
TimescaleDB 适配器 — 连接管理与表结构初始化

SchemaBase 提供连接池管理、事件循环检测、DDL 初始化。
其他 Mixin 通过 self.acquire() 获取连接执行查询。
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None


class SchemaBase:
    """TimescaleDB 连接管理与表结构初始化

    关键设计：asyncpg.Pool 绑定到创建它的事件循环。
    如果 FastMCP 回收/重建事件循环，旧 pool 会报 "Event loop is closed"。
    因此每次 acquire() 时检测当前事件循环是否与 pool 创建时一致，
    不一致则自动重建 pool。
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._init_lock: Optional[asyncio.Lock] = None
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_init_lock(self) -> asyncio.Lock:
        """懒加载初始化锁，确保在当前事件循环中创建"""
        loop = asyncio.get_running_loop()
        if self._init_lock is None or self._bound_loop is not loop:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    async def initialize(self) -> None:
        """初始化数据库连接池"""
        current_loop = asyncio.get_running_loop()

        # 如果 pool 已存在但绑定的事件循环已变更，需要重建
        if self._initialized and self._bound_loop is not current_loop:
            logger.info("Event loop changed, recreating connection pool")
            self.pool = None
            self._initialized = False

        if self._initialized:
            return

        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg not installed. Run: pip install asyncpg")

        # 若未设置 DB_PASSWORD/DB_NAME，尝试从 .env 加载
        if not os.getenv('DB_PASSWORD') or os.getenv('DB_PASSWORD') == 'password':
            _env_from_var = os.getenv('AKSHARE_MCP_ENV', '').strip()
            _candidates = [
                Path(__file__).resolve().parent.parent.parent.parent.parent / '.env',
                Path.cwd() / 'packages' / 'akshare-mcp' / '.env',
                Path.cwd() / '.env',
            ]
            if _env_from_var:
                _candidates.insert(0, Path(_env_from_var))
            for _env in _candidates:
                if not _env.exists() or not _env.is_file():
                    continue
                for line in _env.read_text(encoding='utf-8', errors='replace').splitlines():
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k, v = k.strip(), v.strip()
                        if k.startswith('DB_'):
                            os.environ[k] = v
                break

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
            self._bound_loop = asyncio.get_running_loop()
            logger.info("Connected to %s:%s/%s", db_config['host'], db_config['port'], db_config['database'])
            await self._init_tables()
        except Exception as e:
            logger.error("Connection failed: %s", e)
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

            # 2. 创建财务数据表
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

            # 3. 创建股票信息表
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

            # 4.1 兼容旧库：补齐 stock_quotes 历史缺失列（CREATE TABLE IF NOT EXISTS 不会为已有表自动补列）
            await conn.execute("""
                ALTER TABLE stock_quotes
                ADD COLUMN IF NOT EXISTS name TEXT;
            """)
            await conn.execute("""
                ALTER TABLE stock_quotes
                ADD COLUMN IF NOT EXISTS prev_close DOUBLE PRECISION;
            """)
            await conn.execute("""
                ALTER TABLE stock_quotes
                ADD COLUMN IF NOT EXISTS change_amt DOUBLE PRECISION;
            """)
            await conn.execute("""
                ALTER TABLE stock_quotes
                ADD COLUMN IF NOT EXISTS mkt_cap DOUBLE PRECISION;
            """)

            # 4.2 兼容旧库：若历史表未建唯一索引，补齐后确保 UPSERT 可用
            await conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code
                ON stock_quotes (time, code);
            """)

            # 4.3 兼容旧库：将 change 列历史数据回填到标准列 change_amt（仅当存在 change 列时执行）
            await conn.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'change'
                    ) THEN
                        EXECUTE 'UPDATE stock_quotes
                                 SET change_amt = COALESCE(change_amt, "change")
                                 WHERE change_amt IS NULL';
                    END IF;
                END $$;
            """)

            # 4.4 兼容旧库：将 pre_close/market_cap 历史数据回填到标准列
            await conn.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'pre_close'
                    ) THEN
                        EXECUTE 'UPDATE stock_quotes
                                 SET prev_close = COALESCE(prev_close, pre_close)
                                 WHERE prev_close IS NULL';
                    END IF;
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'market_cap'
                    ) THEN
                        EXECUTE 'UPDATE stock_quotes
                                 SET mkt_cap = COALESCE(mkt_cap, market_cap)
                                 WHERE mkt_cap IS NULL';
                    END IF;
                END $$;
            """)

            # 4.5 兼容旧库：补齐 updated_at 列并回填（避免下游排序/统计字段为空）
            await conn.execute("""
                ALTER TABLE stock_quotes
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
            """)
            await conn.execute("""
                UPDATE stock_quotes
                SET updated_at = COALESCE(updated_at, NOW())
                WHERE updated_at IS NULL;
            """)

            # 4.6 兼容旧库：幂等列重命名（若历史列存在且标准列不存在，执行 rename）
            await conn.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'pre_close'
                    ) AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'prev_close'
                    ) THEN
                        EXECUTE 'ALTER TABLE stock_quotes RENAME COLUMN pre_close TO prev_close';
                    END IF;
                END $$;
            """)
            await conn.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'market_cap'
                    ) AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'mkt_cap'
                    ) THEN
                        EXECUTE 'ALTER TABLE stock_quotes RENAME COLUMN market_cap TO mkt_cap';
                    END IF;
                END $$;
            """)
            await conn.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'change'
                    ) AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'stock_quotes' AND column_name = 'change_amt'
                    ) THEN
                        EXECUTE 'ALTER TABLE stock_quotes RENAME COLUMN "change" TO change_amt';
                    END IF;
                END $$;
            """)


            # 5. 创建组合管理表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
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

            # 5.1 兼容旧库：补齐 portfolios.description（CREATE TABLE IF NOT EXISTS 不会自动补列）
            await conn.execute("""
                ALTER TABLE portfolios
                ADD COLUMN IF NOT EXISTS description TEXT;
            """)

            # 6. 创建模拟交易表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_accounts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
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
                    code TEXT,
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

                CREATE INDEX IF NOT EXISTS idx_backtest_results_code ON backtest_results(code);

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
                    user_id TEXT DEFAULT 'default',
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

            # 8.1 兼容旧库：补齐 alerts.user_id
            await conn.execute("""
                ALTER TABLE alerts
                ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default';
            """)

            # 9. 创建自选股表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default',
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                INSERT INTO watchlist_groups (id, name, sort_order)
                VALUES ('default', '默认分组', 0) ON CONFLICT DO NOTHING;

                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    code TEXT NOT NULL,
                    name TEXT,
                    group_id TEXT DEFAULT 'default',
                    tags JSONB DEFAULT '[]'::jsonb,
                    notes TEXT,
                    note TEXT,
                    added_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, code)
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

            # 16. 创建事件表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_date DATE NOT NULL,
                    title TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
                CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            """)

            # 17. 创建用户表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    settings JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                INSERT INTO users (id, username)
                VALUES ('default', 'default') ON CONFLICT DO NOTHING;
            """)

            # 18. 创建选股策略表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS screener_strategies (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    name TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_screener_strategies_user ON screener_strategies(user_id);
            """)

            # 19. 创建龙虎榜数据表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS dragon_tiger (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    reason TEXT,
                    buy_amount DOUBLE PRECISION,
                    sell_amount DOUBLE PRECISION,
                    net_buy DOUBLE PRECISION,
                    buyer_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(code, trade_date, reason)
                );

                CREATE INDEX IF NOT EXISTS idx_dragon_tiger_date ON dragon_tiger(trade_date);
                CREATE INDEX IF NOT EXISTS idx_dragon_tiger_code ON dragon_tiger(code);
            """)

            # 20. 创建大宗交易表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS block_trades (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    trade_price DOUBLE PRECISION,
                    trade_amount DOUBLE PRECISION,
                    buyer TEXT,
                    seller TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_block_trades_date ON block_trades(trade_date);
                CREATE INDEX IF NOT EXISTS idx_block_trades_code ON block_trades(code);
            """)

            # 21. 创建研究报告表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS research_reports (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    title TEXT,
                    rating TEXT,
                    target_price DOUBLE PRECISION,
                    institution TEXT,
                    analyst TEXT,
                    publish_date DATE,
                    summary TEXT,
                    pdf_url TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_research_reports_code ON research_reports(code);
                CREATE INDEX IF NOT EXISTS idx_research_reports_date ON research_reports(publish_date);
            """)

            # 22. 创建模拟交易订单表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id SERIAL PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    shares INTEGER NOT NULL,
                    price DOUBLE PRECISION,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_paper_orders_account ON paper_orders(account_id);
                CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status);
            """)

            # 23. 创建策略工件表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    strategy TEXT,
                    strategy_version TEXT,
                    code TEXT,
                    payload JSONB,
                    registered_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_strategy_artifacts_strategy
                    ON strategy_artifacts(strategy);
                CREATE INDEX IF NOT EXISTS idx_strategy_artifacts_updated
                    ON strategy_artifacts(updated_at DESC);
            """)

            # 24. 策略超市表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    author_id TEXT DEFAULT 'default',
                    strategy_type TEXT NOT NULL,
                    params JSONB DEFAULT '{}'::jsonb,
                    factor_weights JSONB DEFAULT '{}'::jsonb,
                    status TEXT DEFAULT 'draft',
                    tags TEXT[] DEFAULT '{}',
                    backtest_artifact_id TEXT,
                    subscriber_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
                CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies(strategy_type);
                CREATE INDEX IF NOT EXISTS idx_strategies_author ON strategies(author_id);

                CREATE TABLE IF NOT EXISTS strategy_metrics (
                    id SERIAL PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    period TEXT DEFAULT 'all',
                    total_return DOUBLE PRECISION,
                    annual_return DOUBLE PRECISION,
                    sharpe_ratio DOUBLE PRECISION,
                    max_drawdown DOUBLE PRECISION,
                    win_rate DOUBLE PRECISION,
                    calmar_ratio DOUBLE PRECISION,
                    trade_count INTEGER,
                    computed_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(strategy_id, period)
                );

                CREATE TABLE IF NOT EXISTS strategy_reviews (
                    id SERIAL PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(strategy_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_reviews_strategy ON strategy_reviews(strategy_id);

                CREATE TABLE IF NOT EXISTS strategy_subscriptions (
                    id SERIAL PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    subscribed_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(strategy_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_subs_user ON strategy_subscriptions(user_id);
            """)

            # 25. 因子持久化表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS factor_values (
                    stock_code TEXT NOT NULL,
                    factor_date DATE NOT NULL,
                    factor_name TEXT NOT NULL,
                    factor_value DOUBLE PRECISION,
                    computed_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (stock_code, factor_date, factor_name)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_values_date ON factor_values(factor_date);
                CREATE INDEX IF NOT EXISTS idx_factor_values_factor ON factor_values(factor_name);

                CREATE TABLE IF NOT EXISTS factor_ic_history (
                    id SERIAL PRIMARY KEY,
                    factor_name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    ic_date DATE NOT NULL,
                    ic_value DOUBLE PRECISION,
                    rank_ic DOUBLE PRECISION,
                    stock_count INTEGER,
                    computed_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(factor_name, period, ic_date)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_ic_date ON factor_ic_history(ic_date);
            """)

            logger.info("All tables initialized successfully (aligned with Node version)")

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            try:
                await self.pool.close()
            except Exception:
                pass
            self.pool = None
            self._initialized = False
            self._bound_loop = None
            self._init_lock = None
            logger.info("Connection closed")

    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接（自动处理事件循环变更和连接池重建）"""
        lock = self._get_init_lock()

        if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
            async with lock:
                if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
                    await self.initialize()

        try:
            async with self.pool.acquire() as conn:
                yield conn
        except Exception as e:
            err_msg = str(e).lower()
            if 'event loop is closed' in err_msg or 'pool is closed' in err_msg or 'not running' in err_msg:
                logger.warning("Pool error detected (%s), rebuilding...", e)
                async with lock:
                    self.pool = None
                    self._initialized = False
                    await self.initialize()
                async with self.pool.acquire() as conn:
                    yield conn
            else:
                raise
