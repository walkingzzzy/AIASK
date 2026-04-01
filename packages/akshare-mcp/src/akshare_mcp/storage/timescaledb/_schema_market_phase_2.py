from ._schema_market_common import *


async def init_market_tables_phase_2(conn) -> None:
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
    await _create_hypertable_if_supported(conn, "north_fund_flow", "trade_date")
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
    await _create_hypertable_if_supported(conn, "stock_fund_flow", "trade_date")

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
