from ._schema_market_common import *


async def init_market_tables_phase_1(conn) -> None:
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
        await conn.execute("""
            ALTER TABLE financials
            ADD COLUMN IF NOT EXISTS stock_code TEXT;
        """)
        await _run_market_migration_once(conn, "financials_rename_code_to_stock_code", """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'financials' AND column_name = 'code'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'financials' AND column_name = 'stock_code'
                ) THEN
                    EXECUTE 'ALTER TABLE financials RENAME COLUMN code TO stock_code';
                END IF;
            END $$;
        """)
        await _run_market_migration_once(conn, "financials_backfill_stock_code", """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'financials' AND column_name = 'code'
                ) THEN
                    EXECUTE $sql$
                        UPDATE financials
                        SET stock_code = COALESCE(NULLIF(stock_code, ''), code)
                        WHERE stock_code IS NULL OR stock_code = ''
                    $sql$;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_financials_stock_code_report_date
            ON financials (stock_code, report_date);
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
        await conn.execute("""
            ALTER TABLE stocks
            ADD COLUMN IF NOT EXISTS stock_code TEXT;
        """)
        await _run_market_migration_once(conn, "stocks_rename_code_to_stock_code", """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'stocks' AND column_name = 'code'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'stocks' AND column_name = 'stock_code'
                ) THEN
                    EXECUTE 'ALTER TABLE stocks RENAME COLUMN code TO stock_code';
                END IF;
            END $$;
        """)
        await _run_market_migration_once(conn, "stocks_backfill_stock_code", """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'stocks' AND column_name = 'code'
                ) THEN
                    EXECUTE $sql$
                        UPDATE stocks
                        SET stock_code = COALESCE(NULLIF(stock_code, ''), code)
                        WHERE stock_code IS NULL OR stock_code = ''
                    $sql$;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_stocks_stock_code
            ON stocks (stock_code);
        """)
