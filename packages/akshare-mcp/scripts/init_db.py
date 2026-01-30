"""初始化TimescaleDB数据库"""

import asyncio
import asyncpg
import os


async def init_database():
    """初始化数据库表结构"""
    
    conn = await asyncpg.connect(
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'password'),
        database=os.getenv('DB_NAME', 'postgres'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    
    try:
        # 启用TimescaleDB扩展
        await conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;')
        print('✓ TimescaleDB extension enabled')
        
        # 创建股票信息表
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                code TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL,
                industry TEXT,
                market_cap DOUBLE PRECISION,
                pe_ratio DOUBLE PRECISION,
                pb_ratio DOUBLE PRECISION,
                list_date DATE,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        print('✓ stocks table created')
        
        # 创建K线表
        await conn.execute('''
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
        ''')
        print('✓ kline_1d table created')
        
        # 转换为Hypertable
        try:
            await conn.execute("SELECT create_hypertable('kline_1d', 'time', if_not_exists => TRUE);")
            print('✓ kline_1d converted to hypertable')
        except Exception as e:
            print(f'  kline_1d already a hypertable: {e}')
        
        # 创建财务数据表
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS financials (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL,
                report_date DATE NOT NULL,
                revenue DOUBLE PRECISION,
                net_profit DOUBLE PRECISION,
                roe DOUBLE PRECISION,
                debt_ratio DOUBLE PRECISION,
                revenue_growth DOUBLE PRECISION,
                profit_growth DOUBLE PRECISION,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(code, report_date)
            );
        ''')
        print('✓ financials table created')
        
        # 创建实时行情表
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS stock_quotes (
                time TIMESTAMPTZ NOT NULL,
                code TEXT NOT NULL,
                price DOUBLE PRECISION,
                change DOUBLE PRECISION,
                change_pct DOUBLE PRECISION,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                pre_close DOUBLE PRECISION,
                volume BIGINT,
                amount DOUBLE PRECISION,
                PRIMARY KEY (time, code)
            );
        ''')
        print('✓ stock_quotes table created')
        
        # 创建索引
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_kline_code ON kline_1d(code);')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_financials_code ON financials(code);')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(stock_name);')
        print('✓ Indexes created')
        
        print('\n✅ Database initialization completed!')
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(init_database())
