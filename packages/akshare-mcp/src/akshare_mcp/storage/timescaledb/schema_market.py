"""
Market data table DDL — kline, financials, portfolios, alerts, etc.

All ~30 market-data tables are created via a single entry point:

    await init_market_tables(conn)

The function is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
"""

import logging

logger = logging.getLogger(__name__)
_MARKET_SCHEMA_MIGRATION_TABLE = "market_schema_migrations"


async def _create_hypertable_if_supported(conn, table_name: str, time_column: str = "time") -> None:
    """Best-effort Timescale hypertable promotion."""
    try:
        enabled = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_extension
                WHERE extname = 'timescaledb'
            )
            """
        )
        if not enabled:
            return
        await conn.execute(
            f"""
            SELECT create_hypertable(
                '{table_name}',
                '{time_column}',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
            """
        )
    except Exception as exc:
        logger.warning("create_hypertable skipped for %s: %s", table_name, exc)


async def _ensure_foreign_key(
    conn,
    *,
    table_name: str,
    constraint_name: str,
    definition: str,
) -> None:
    """Install NOT VALID foreign keys without breaking historical dirty data."""
    await conn.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                {definition}
                NOT VALID;
            END IF;
        END $$;
        """
    )


async def _ensure_market_schema_migration_table(conn) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_MARKET_SCHEMA_MIGRATION_TABLE} (
            migration_key TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )


async def _run_market_migration_once(conn, migration_key: str, statement: str) -> bool:
    await _ensure_market_schema_migration_table(conn)
    already_applied = await conn.fetchval(
        f"SELECT 1 FROM {_MARKET_SCHEMA_MIGRATION_TABLE} WHERE migration_key = $1",
        migration_key,
    )
    if already_applied:
        return False
    await conn.execute(statement)
    await conn.execute(
        f"""
        INSERT INTO {_MARKET_SCHEMA_MIGRATION_TABLE} (migration_key, applied_at)
        VALUES ($1, NOW())
        ON CONFLICT (migration_key) DO NOTHING
        """,
        migration_key,
    )
    return True


async def init_market_tables(conn) -> None:
    """Create / migrate all market-data tables.

    Args:
        conn: an asyncpg connection (already acquired from the pool).
    """

    # 1. K线表（Hypertable）
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

        CREATE INDEX IF NOT EXISTS idx_kline_1d_code_time_desc
        ON kline_1d (code, time DESC);

        CREATE INDEX IF NOT EXISTS idx_kline_1d_code_updated_desc
        ON kline_1d (code, updated_at DESC);
    """)
    await _create_hypertable_if_supported(conn, "kline_1d", "time")

    # 2. 财务数据表
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

        CREATE INDEX IF NOT EXISTS idx_financials_report_date_desc
        ON financials (report_date DESC);

        CREATE INDEX IF NOT EXISTS idx_financials_updated_desc
        ON financials (updated_at DESC);
    """)

    # 3. 股票信息表
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

    # 4. 实时行情表（Hypertable）
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

        CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_time_desc
        ON stock_quotes (code, time DESC);
    """)
    await _create_hypertable_if_supported(conn, "stock_quotes", "time")
    await _ensure_market_schema_migration_table(conn)

    # 4.1 北向资金日汇总
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS north_fund_flow (
            trade_date DATE PRIMARY KEY,
            north_money DOUBLE PRECISION,
            south_money DOUBLE PRECISION,
            net_amount DOUBLE PRECISION,
            ggt_ss DOUBLE PRECISION,
            ggt_sz DOUBLE PRECISION,
            hgt DOUBLE PRECISION,
            sgt DOUBLE PRECISION,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_north_fund_flow_trade_date_desc
        ON north_fund_flow (trade_date DESC);
    """)
    await conn.execute("""
        ALTER TABLE north_fund_flow
        ADD COLUMN IF NOT EXISTS ggt_ss DOUBLE PRECISION;
    """)
    await conn.execute("""
        ALTER TABLE north_fund_flow
        ADD COLUMN IF NOT EXISTS ggt_sz DOUBLE PRECISION;
    """)
    await conn.execute("""
        ALTER TABLE north_fund_flow
        ADD COLUMN IF NOT EXISTS hgt DOUBLE PRECISION;
    """)
    await conn.execute("""
        ALTER TABLE north_fund_flow
        ADD COLUMN IF NOT EXISTS sgt DOUBLE PRECISION;
    """)
    await conn.execute("""
        ALTER TABLE north_fund_flow
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
    """)

    # 4.1.1 个股资金流快照
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_fund_flow (
            code TEXT NOT NULL,
            trade_date DATE NOT NULL,
            name TEXT,
            main_net_inflow DOUBLE PRECISION,
            main_inflow_percent DOUBLE PRECISION,
            super_large_net_inflow DOUBLE PRECISION,
            large_net_inflow DOUBLE PRECISION,
            middle_net_inflow DOUBLE PRECISION,
            small_net_inflow DOUBLE PRECISION,
            source TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (code, trade_date)
        );

        CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_code_trade_date_desc
        ON stock_fund_flow (code, trade_date DESC);
    """)

    # 4.2 融资融券市场汇总
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_market_flow (
            trade_date DATE NOT NULL,
            exchange_id TEXT NOT NULL DEFAULT 'SSE',
            rzye DOUBLE PRECISION,
            rzmre DOUBLE PRECISION,
            rzche DOUBLE PRECISION,
            rqye DOUBLE PRECISION,
            rqmcl DOUBLE PRECISION,
            rqyl DOUBLE PRECISION,
            rzrqye DOUBLE PRECISION,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (trade_date, exchange_id)
        );

        CREATE INDEX IF NOT EXISTS idx_margin_market_flow_trade_date_desc
        ON margin_market_flow (trade_date DESC, exchange_id);
    """)

    # 4.3 融资融券个股明细
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_detail (
            trade_date DATE NOT NULL,
            ts_code TEXT NOT NULL,
            rzye DOUBLE PRECISION,
            rqye DOUBLE PRECISION,
            rzmre DOUBLE PRECISION,
            rqyl DOUBLE PRECISION,
            rzche DOUBLE PRECISION,
            rqchl DOUBLE PRECISION,
            rqmcl DOUBLE PRECISION,
            rzrqye DOUBLE PRECISION,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (trade_date, ts_code)
        );

        CREATE INDEX IF NOT EXISTS idx_margin_detail_ts_code_trade_date_desc
        ON margin_detail (ts_code, trade_date DESC);
    """)

    # 4.1 兼容旧库：补齐 stock_quotes 历史缺失列
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
    await conn.execute("""
        ALTER TABLE stock_quotes
        ADD COLUMN IF NOT EXISTS pe DOUBLE PRECISION;
    """)
    await conn.execute("""
        ALTER TABLE stock_quotes
        ADD COLUMN IF NOT EXISTS pb DOUBLE PRECISION;
    """)

    # 4.2 兼容旧库：若历史表未建唯一索引，补齐后确保 UPSERT 可用
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code
        ON stock_quotes (time, code);

        CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_time_desc
        ON stock_quotes (code, time DESC);
    """)

    # 4.3 兼容旧库：将 change 列历史数据回填到标准列 change_amt
    await _run_market_migration_once(conn, "stock_quotes_backfill_change_amt", """
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
    await _run_market_migration_once(conn, "stock_quotes_backfill_prev_close_mkt_cap", """
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

    # 4.5 兼容旧库：补齐 updated_at 列并回填
    await conn.execute("""
        ALTER TABLE stock_quotes
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
    """)
    await _run_market_migration_once(conn, "stock_quotes_backfill_updated_at", """
        UPDATE stock_quotes
        SET updated_at = COALESCE(updated_at, NOW())
        WHERE updated_at IS NULL;
    """)

    # 4.6 兼容旧库：幂等列重命名
    await _run_market_migration_once(conn, "stock_quotes_rename_legacy_columns", """
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

    # 5. 组合管理表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
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

    # 5.1 兼容旧库：补齐 portfolios.description
    await conn.execute("""
        ALTER TABLE portfolios
        ADD COLUMN IF NOT EXISTS description TEXT;
    """)

    await conn.execute("""
        ALTER TABLE portfolios
        ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
    """)
    await _ensure_foreign_key(
        conn,
        table_name="holdings",
        constraint_name="fk_holdings_portfolio_id",
        definition="FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE",
    )

    # 6. 模拟交易表
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

    # 19. 龙虎榜数据表
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

    # 20. 大宗交易表
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

    # 21. 研究报告表
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

    # 22. 模拟交易订单表
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

    # 22.1 兼容旧库：补齐 paper_orders 新增列
    await conn.execute("""
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS order_type TEXT DEFAULT 'market';
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS stop_price DOUBLE PRECISION;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS filled_at TIMESTAMPTZ;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS commission DOUBLE PRECISION DEFAULT 0;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS reason TEXT;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS strategy_id TEXT;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS signal_date DATE;
        ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';
    """)

    # 22.1.1 复合索引优化
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_paper_orders_acct_status ON paper_orders(account_id, status);
        CREATE INDEX IF NOT EXISTS idx_paper_positions_acct_code ON paper_positions(account_id, stock_code);
    """)

    # 22.2 兼容旧库：补齐 paper_accounts 新增列
    await conn.execute("""
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS risk_rules JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS strategy_id TEXT;
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'manual';
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS incubation_stage TEXT DEFAULT 'warmup';
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS promotion_candidate BOOLEAN DEFAULT FALSE;
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS archived_reason TEXT;
        ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
    """)
    await conn.execute("""
        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strategy_id TEXT;
        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS source_order_id TEXT;
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_paper_accounts_strategy ON paper_accounts(strategy_id);
        CREATE INDEX IF NOT EXISTS idx_paper_accounts_type ON paper_accounts(account_type, status);
        CREATE INDEX IF NOT EXISTS idx_paper_orders_strategy ON paper_orders(strategy_id, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy ON paper_trades(strategy_id, created_at DESC);
    """)
    await _ensure_foreign_key(
        conn,
        table_name="paper_positions",
        constraint_name="fk_paper_positions_account_id",
        definition="FOREIGN KEY (account_id) REFERENCES paper_accounts(id) ON DELETE CASCADE",
    )
    await _ensure_foreign_key(
        conn,
        table_name="paper_trades",
        constraint_name="fk_paper_trades_account_id",
        definition="FOREIGN KEY (account_id) REFERENCES paper_accounts(id) ON DELETE CASCADE",
    )
    await _ensure_foreign_key(
        conn,
        table_name="paper_orders",
        constraint_name="fk_paper_orders_account_id",
        definition="FOREIGN KEY (account_id) REFERENCES paper_accounts(id) ON DELETE CASCADE",
    )

    # 22.3 模拟交易 NAV 快照表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_nav (
            id SERIAL PRIMARY KEY,
            account_id TEXT NOT NULL,
            nav_date DATE NOT NULL,
            total_value DOUBLE PRECISION NOT NULL,
            cash DOUBLE PRECISION NOT NULL,
            market_value DOUBLE PRECISION NOT NULL,
            daily_return DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(account_id, nav_date)
        );
        CREATE INDEX IF NOT EXISTS idx_paper_nav_account ON paper_nav(account_id, nav_date);
    """)
    await _ensure_foreign_key(
        conn,
        table_name="paper_nav",
        constraint_name="fk_paper_nav_account_id",
        definition="FOREIGN KEY (account_id) REFERENCES paper_accounts(id) ON DELETE CASCADE",
    )

    # 23. 策略工件表
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
        CREATE INDEX IF NOT EXISTS idx_factor_values_name_date_code ON factor_values(factor_name, factor_date DESC, stock_code);

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

    # 26. 用户画像快照表（AI推断的大五人格）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profile_snapshots (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            neuroticism DOUBLE PRECISION DEFAULT 0.5,
            openness DOUBLE PRECISION DEFAULT 0.5,
            herd_tendency DOUBLE PRECISION DEFAULT 0.5,
            greed_fear_axis DOUBLE PRECISION DEFAULT 0.0,
            confidence DOUBLE PRECISION DEFAULT 0.5,
            source TEXT DEFAULT 'ai_inference',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_user_profile_user
            ON user_profile_snapshots(user_id, created_at DESC);
    """)

    # 27. 推荐审计日志表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_audit_log (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            strategy_id TEXT,
            stock_code TEXT,
            action TEXT,
            emotion_polarity DOUBLE PRECISION,
            emotion_intensity DOUBLE PRECISION,
            cognitive_biases TEXT[],
            risk_aversion DOUBLE PRECISION,
            kyc_level TEXT,
            profile_snapshot JSONB,
            reasoning_chain TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_rec_audit_user
            ON recommendation_audit_log(user_id, created_at DESC);
    """)

    logger.info("Market tables initialized")
