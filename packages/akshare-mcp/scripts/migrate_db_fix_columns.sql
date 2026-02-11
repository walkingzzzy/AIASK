-- 数据库迁移脚本：修复字段名不一致问题
-- 运行方式: psql -U postgres -d your_database -f migrate_db_fix_columns.sql

-- 1. 为 watchlist 表添加 user_id 字段（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'watchlist' AND column_name = 'user_id') THEN
        ALTER TABLE watchlist ADD COLUMN user_id TEXT DEFAULT 'default';
    END IF;
END $$;

-- 2. 为 watchlist 表添加 note 字段（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'watchlist' AND column_name = 'note') THEN
        ALTER TABLE watchlist ADD COLUMN note TEXT;
    END IF;
END $$;

-- 3. 为 paper_accounts 表添加 user_id 字段（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'paper_accounts' AND column_name = 'user_id') THEN
        ALTER TABLE paper_accounts ADD COLUMN user_id TEXT DEFAULT 'default';
    END IF;
END $$;

-- 4. 为 backtest_results 表添加 code 字段（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'backtest_results' AND column_name = 'code') THEN
        ALTER TABLE backtest_results ADD COLUMN code TEXT;
        CREATE INDEX IF NOT EXISTS idx_backtest_results_code ON backtest_results(code);
    END IF;
END $$;

-- 5. 创建 events 表（如果不存在）
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

-- 6. 创建 users 表（如果不存在）
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

-- 7. 创建 screener_strategies 表（如果不存在）
CREATE TABLE IF NOT EXISTS screener_strategies (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    name TEXT NOT NULL,
    criteria TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_screener_strategies_user ON screener_strategies(user_id);

-- 完成
SELECT 'Migration completed successfully' as status;
