from ._schema_market_common import (
    _ensure_foreign_key,
    _run_market_migration_once,
    logger,
)


async def init_market_tables_phase_4(conn) -> None:
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
    # paper_nav has SERIAL PK + UNIQUE(account_id, nav_date) — incompatible with
    # hypertable partitioning on nav_date unless we restructure the PK.
    # Skipping hypertable for now; data volume is manageable with a regular table.
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

    # 24. 交易日历表（供 DataSyncScheduler 判断交易日）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_dates (
            trade_date DATE PRIMARY KEY,
            exchange TEXT DEFAULT 'SSE',
            is_open BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_trading_dates_exchange
        ON trading_dates (exchange, trade_date DESC);
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
