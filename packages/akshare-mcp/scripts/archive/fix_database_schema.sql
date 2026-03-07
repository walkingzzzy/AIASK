-- ============================================
-- 数据库结构修复脚本
-- ============================================

-- 1. 修复stocks表：统一使用stock_code
DO $$ 
BEGIN
    -- 如果存在code字段但不存在stock_code字段
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'code'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'stock_code'
    ) THEN
        -- 添加stock_code字段
        ALTER TABLE stocks ADD COLUMN stock_code TEXT;
        -- 复制code的值到stock_code
        UPDATE stocks SET stock_code = code WHERE stock_code IS NULL;
        -- 设置NOT NULL约束
        ALTER TABLE stocks ALTER COLUMN stock_code SET NOT NULL;
        -- 删除原主键约束
        ALTER TABLE stocks DROP CONSTRAINT IF EXISTS stocks_pkey;
        -- 设置stock_code为主键
        ALTER TABLE stocks ADD PRIMARY KEY (stock_code);
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_stocks_stock_code ON stocks(stock_code);
        RAISE NOTICE '已添加stock_code字段并设为主键';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'stock_code'
    ) THEN
        RAISE NOTICE 'stock_code字段已存在';
    ELSE
        RAISE NOTICE 'stocks表不存在或字段结构异常';
    END IF;
END $$;

-- 2. 修复financials表：确保有eps字段
ALTER TABLE financials 
ADD COLUMN IF NOT EXISTS eps DOUBLE PRECISION;

-- 3. 修复sync_tasks表：确保有updated_at字段
ALTER TABLE sync_tasks 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 4. 修复watchlist表：确保code字段不允许null
-- 注意：实际检查显示已经是NOT NULL，此段脚本为了防卫性编程保留，自动跳过
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'watchlist' 
        AND column_name = 'code' 
        AND is_nullable = 'YES'
    ) THEN
        -- 先清理null值
        DELETE FROM watchlist WHERE code IS NULL;
        -- 设置NOT NULL约束
        ALTER TABLE watchlist ALTER COLUMN code SET NOT NULL;
        RAISE NOTICE '已修复watchlist.code字段的NOT NULL约束';
    END IF;
END $$;

-- 5. 创建valuation表（如果不存在）
CREATE TABLE IF NOT EXISTS valuation_history (
    id SERIAL PRIMARY KEY,
    stock_code TEXT NOT NULL,
    date DATE NOT NULL,
    pe DOUBLE PRECISION,
    pb DOUBLE PRECISION,
    ps DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, date)
);

CREATE INDEX IF NOT EXISTS idx_valuation_history_stock_code 
ON valuation_history(stock_code, date DESC);

-- 6. 创建backtest_results表（如果不存在）
CREATE TABLE IF NOT EXISTS backtest_results (
    id TEXT PRIMARY KEY,
    code TEXT,
    strategy TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    initial_capital DOUBLE PRECISION DEFAULT 100000,
    final_value DOUBLE PRECISION,
    total_return DOUBLE PRECISION,
    annual_return DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    win_rate DOUBLE PRECISION,
    total_trades INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. 验证修复结果
DO $$ 
DECLARE
    stocks_has_stock_code BOOLEAN;
    financials_has_eps BOOLEAN;
    sync_tasks_has_updated_at BOOLEAN;
BEGIN
    -- 检查stocks表
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'stock_code'
    ) INTO stocks_has_stock_code;
    
    -- 检查financials表
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'financials' AND column_name = 'eps'
    ) INTO financials_has_eps;
    
    -- 检查sync_tasks表
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sync_tasks' AND column_name = 'updated_at'
    ) INTO sync_tasks_has_updated_at;
    
    RAISE NOTICE '修复结果：';
    RAISE NOTICE '  stocks.stock_code: %', stocks_has_stock_code;
    RAISE NOTICE '  financials.eps: %', financials_has_eps;
    RAISE NOTICE '  sync_tasks.updated_at: %', sync_tasks_has_updated_at;
END $$;
