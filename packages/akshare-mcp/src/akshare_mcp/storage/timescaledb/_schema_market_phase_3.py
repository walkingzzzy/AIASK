from ._schema_market_common import *


async def init_market_tables_phase_3(conn) -> None:
    # 7. 回测结果表
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
    await _ensure_foreign_key(
        conn,
        table_name="backtest_trades",
        constraint_name="fk_backtest_trades_backtest_id",
        definition="FOREIGN KEY (backtest_id) REFERENCES backtest_results(id) ON DELETE CASCADE",
    )
    await _ensure_foreign_key(
        conn,
        table_name="backtest_equity",
        constraint_name="fk_backtest_equity_backtest_id",
        definition="FOREIGN KEY (backtest_id) REFERENCES backtest_results(id) ON DELETE CASCADE",
    )

    # 8. 告警表
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

    # 8.2 事件审计表（告警/订单）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_events (
            id SERIAL PRIMARY KEY,
            alert_id TEXT,
            event_type TEXT NOT NULL,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_alert_events_alert ON alert_events(alert_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS order_events (
            id SERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            account_id TEXT,
            code TEXT,
            event_type TEXT NOT NULL,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_order_events_account ON order_events(account_id, created_at DESC);
    """)

    # 9. 自选股表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_groups (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            user_id TEXT DEFAULT 'default',
            color TEXT DEFAULT '#6366f1',
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
            sort_order INTEGER DEFAULT 0,
            tags JSONB DEFAULT '[]'::jsonb,
            notes TEXT,
            note TEXT,
            added_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, code)
        );

        ALTER TABLE watchlist_groups
        ADD COLUMN IF NOT EXISTS color TEXT DEFAULT '#6366f1';

        ALTER TABLE watchlist
        ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;
    """)

    # 10. 向量检索表（基础，非 pgvector）
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

    # 11. 市场板块表
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

    # 12. 板块成分股表
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

    # 13. 数据质量表
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

    # 14. 数据同步任务表
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

    # 15. 数据同步调度表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_schedules (
            id SERIAL PRIMARY KEY,
            schedule_id TEXT UNIQUE NOT NULL,
            task_type TEXT NOT NULL,
            codes TEXT[],
            schedule TEXT NOT NULL,
            params JSONB DEFAULT '{}'::jsonb,
            enabled BOOLEAN DEFAULT true,
            last_run TIMESTAMPTZ,
            next_run TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_sync_schedules_enabled ON sync_schedules(enabled);
        CREATE INDEX IF NOT EXISTS idx_sync_schedules_next_run ON sync_schedules(next_run);
    """)
    await conn.execute("""
        ALTER TABLE sync_schedules
        ADD COLUMN IF NOT EXISTS params JSONB DEFAULT '{}'::jsonb
    """)

    # 16. 事件表
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

    # 17. 用户表
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

    # 18. 选股策略表
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
