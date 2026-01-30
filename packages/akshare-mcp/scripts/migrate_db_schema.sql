-- 数据库架构迁移脚本
-- 用于统一Node.js和Python版本的表结构

-- 1. 修改 stock_quotes 表，添加缺失字段
ALTER TABLE IF EXISTS stock_quotes 
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS change_amt DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pe DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pb DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS mkt_cap DOUBLE PRECISION;

-- 重命名字段以统一命名（如果存在旧字段）
DO $$ 
BEGIN
    -- 将 pre_close 重命名为 prev_close
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stock_quotes' AND column_name = 'pre_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stock_quotes' AND column_name = 'prev_close'
    ) THEN
        ALTER TABLE stock_quotes RENAME COLUMN pre_close TO prev_close;
    END IF;
    
    -- 将 change 重命名为 change_amt（如果没有change_amt）
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stock_quotes' AND column_name = 'change'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stock_quotes' AND column_name = 'change_amt'
    ) THEN
        ALTER TABLE stock_quotes RENAME COLUMN change TO change_amt;
    END IF;
END $$;

-- 2. 确保 stocks 表使用统一的列名
-- 注意：这里假设表已经使用 code 和 stock_name
-- 如果使用的是 stock_code，需要重命名
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'stock_code'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'code'
    ) THEN
        ALTER TABLE stocks RENAME COLUMN stock_code TO code;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'name'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'stocks' AND column_name = 'stock_name'
    ) THEN
        ALTER TABLE stocks RENAME COLUMN name TO stock_name;
    END IF;
END $$;

-- 3. 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_time ON stock_quotes(code, time DESC);
CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code);
CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(stock_name);
CREATE INDEX IF NOT EXISTS idx_stocks_market_cap ON stocks(market_cap DESC NULLS LAST);

-- 4. 添加注释
COMMENT ON COLUMN stock_quotes.name IS '股票名称';
COMMENT ON COLUMN stock_quotes.change_amt IS '涨跌额';
COMMENT ON COLUMN stock_quotes.prev_close IS '昨收价';
COMMENT ON COLUMN stock_quotes.pe IS '市盈率';
COMMENT ON COLUMN stock_quotes.pb IS '市净率';
COMMENT ON COLUMN stock_quotes.mkt_cap IS '市值';


-- 5. 创建 market_blocks 表（如果不存在）
CREATE TABLE IF NOT EXISTS market_blocks (
    block_code TEXT NOT NULL,
    block_name TEXT NOT NULL,
    block_type TEXT NOT NULL,
    stock_count INTEGER DEFAULT 0,
    avg_change_pct DOUBLE PRECISION,
    total_amount DOUBLE PRECISION,
    leader_code TEXT,
    leader_name TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (block_code, block_type)
);

CREATE INDEX IF NOT EXISTS idx_market_blocks_type ON market_blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_market_blocks_updated ON market_blocks(updated_at DESC);

COMMENT ON TABLE market_blocks IS '市场板块数据';
COMMENT ON COLUMN market_blocks.block_code IS '板块代码';
COMMENT ON COLUMN market_blocks.block_name IS '板块名称';
COMMENT ON COLUMN market_blocks.block_type IS '板块类型(industry/concept/region)';
COMMENT ON COLUMN market_blocks.stock_count IS '成分股数量';
COMMENT ON COLUMN market_blocks.avg_change_pct IS '平均涨跌幅';
COMMENT ON COLUMN market_blocks.total_amount IS '总成交额';
COMMENT ON COLUMN market_blocks.leader_code IS '领涨股代码';
COMMENT ON COLUMN market_blocks.leader_name IS '领涨股名称';
