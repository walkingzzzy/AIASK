#!/usr/bin/env node
/**
 * 数据库迁移脚本 - 添加高级数据表
 * 
 * 创建以下表：
 * 1. 分钟K线表：kline_1m, kline_5m, kline_15m, kline_30m, kline_60m
 * 2. 龙虎榜表：dragon_tiger
 * 3. 北向资金表：north_fund
 * 4. 融资融券表：margin_data
 * 5. 大宗交易表：block_trades
 * 6. 新闻表：stock_news
 */

import { timescaleDB } from '../src/storage/timescaledb.js';

async function migrateAdvancedTables() {
    console.log('='.repeat(80));
    console.log('数据库迁移 - 添加高级数据表');
    console.log('='.repeat(80));
    console.log();

    try {
        // 1. 创建分钟K线表
        console.log('📊 创建分钟K线表...');
        const periods = ['1m', '5m', '15m', '30m', '60m'];
        
        for (const period of periods) {
            const tableName = `kline_${period}`;
            
            await timescaleDB.query(`
                CREATE TABLE IF NOT EXISTS ${tableName} (
                    time        TIMESTAMPTZ       NOT NULL,
                    code        TEXT              NOT NULL,
                    open        DOUBLE PRECISION  NOT NULL,
                    high        DOUBLE PRECISION  NOT NULL,
                    low         DOUBLE PRECISION  NOT NULL,
                    close       DOUBLE PRECISION  NOT NULL,
                    volume      BIGINT            NOT NULL,
                    amount      DOUBLE PRECISION,
                    turnover    DOUBLE PRECISION,
                    change_percent DOUBLE PRECISION,
                    updated_at  TIMESTAMPTZ       DEFAULT NOW(),
                    PRIMARY KEY (time, code)
                );
            `);
            
            // 检查是否已是 Hypertable
            const checkHyper = await timescaleDB.query(`
                SELECT * FROM timescaledb_information.hypertables 
                WHERE hypertable_name = '${tableName}';
            `);
            
            if (checkHyper.rowCount === 0) {
                await timescaleDB.query(`SELECT create_hypertable('${tableName}', 'time');`);
                console.log(`  ✅ 创建 Hypertable: ${tableName}`);
            } else {
                console.log(`  ℹ️  ${tableName} 已存在`);
            }
        }

        // 2. 创建龙虎榜表
        console.log('\n🐉 创建龙虎榜表...');
        await timescaleDB.query(`
            CREATE TABLE IF NOT EXISTS dragon_tiger (
                date        DATE              NOT NULL,
                code        TEXT              NOT NULL,
                name        TEXT              NOT NULL,
                reason      TEXT,
                buy_amount  DOUBLE PRECISION  NOT NULL,
                sell_amount DOUBLE PRECISION  NOT NULL,
                net_amount  DOUBLE PRECISION  NOT NULL,
                total_amount DOUBLE PRECISION NOT NULL,
                created_at  TIMESTAMPTZ       DEFAULT NOW(),
                PRIMARY KEY (date, code)
            );
            
            CREATE INDEX IF NOT EXISTS idx_dragon_tiger_date ON dragon_tiger(date DESC);
            CREATE INDEX IF NOT EXISTS idx_dragon_tiger_code ON dragon_tiger(code);
        `);
        console.log('  ✅ 龙虎榜表创建完成');

        // 3. 创建北向资金表
        console.log('\n💰 创建北向资金表...');
        await timescaleDB.query(`
            CREATE TABLE IF NOT EXISTS north_fund (
                date                DATE              NOT NULL PRIMARY KEY,
                hk_to_sh            DOUBLE PRECISION  NOT NULL,
                hk_to_sz            DOUBLE PRECISION  NOT NULL,
                total               DOUBLE PRECISION  NOT NULL,
                hk_to_sh_balance    DOUBLE PRECISION,
                hk_to_sz_balance    DOUBLE PRECISION,
                created_at          TIMESTAMPTZ       DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_north_fund_date ON north_fund(date DESC);
        `);
        console.log('  ✅ 北向资金表创建完成');

        // 4. 创建融资融券表
        console.log('\n📈 创建融资融券表...');
        await timescaleDB.query(`
            CREATE TABLE IF NOT EXISTS margin_data (
                date            DATE              NOT NULL,
                code            TEXT              NOT NULL,
                margin_balance  DOUBLE PRECISION  NOT NULL,
                margin_buy      DOUBLE PRECISION  NOT NULL,
                margin_sell     DOUBLE PRECISION  NOT NULL,
                short_balance   DOUBLE PRECISION  NOT NULL,
                short_sell      DOUBLE PRECISION  NOT NULL,
                short_cover     DOUBLE PRECISION  NOT NULL,
                total_balance   DOUBLE PRECISION  NOT NULL,
                created_at      TIMESTAMPTZ       DEFAULT NOW(),
                PRIMARY KEY (date, code)
            );
            
            CREATE INDEX IF NOT EXISTS idx_margin_data_date ON margin_data(date DESC);
            CREATE INDEX IF NOT EXISTS idx_margin_data_code ON margin_data(code);
        `);
        console.log('  ✅ 融资融券表创建完成');

        // 5. 创建大宗交易表
        console.log('\n📦 创建大宗交易表...');
        await timescaleDB.query(`
            CREATE TABLE IF NOT EXISTS block_trades (
                date            DATE              NOT NULL,
                code            TEXT              NOT NULL,
                name            TEXT              NOT NULL,
                price           DOUBLE PRECISION  NOT NULL,
                volume          BIGINT            NOT NULL,
                amount          DOUBLE PRECISION  NOT NULL,
                buyer           TEXT              NOT NULL,
                seller          TEXT              NOT NULL,
                premium_rate    DOUBLE PRECISION,
                created_at      TIMESTAMPTZ       DEFAULT NOW(),
                PRIMARY KEY (date, code, buyer, seller)
            );
            
            CREATE INDEX IF NOT EXISTS idx_block_trades_date ON block_trades(date DESC);
            CREATE INDEX IF NOT EXISTS idx_block_trades_code ON block_trades(code);
        `);
        console.log('  ✅ 大宗交易表创建完成');

        // 6. 创建新闻表
        console.log('\n📰 创建新闻表...');
        await timescaleDB.query(`
            CREATE TABLE IF NOT EXISTS stock_news (
                code        TEXT              NOT NULL,
                title       TEXT              NOT NULL,
                time        TEXT              NOT NULL,
                source      TEXT              NOT NULL,
                url         TEXT              NOT NULL,
                content     TEXT,
                created_at  TIMESTAMPTZ       DEFAULT NOW(),
                PRIMARY KEY (code, title, time)
            );
            
            CREATE INDEX IF NOT EXISTS idx_stock_news_code ON stock_news(code);
            CREATE INDEX IF NOT EXISTS idx_stock_news_time ON stock_news(time DESC);
            
            -- 全文搜索索引
            CREATE INDEX IF NOT EXISTS idx_stock_news_title_fts 
            ON stock_news USING GIN(to_tsvector('simple', title));
        `);
        console.log('  ✅ 新闻表创建完成');

        // 7. 验证表创建
        console.log('\n🔍 验证表创建...');
        const tables = [
            'kline_1m', 'kline_5m', 'kline_15m', 'kline_30m', 'kline_60m',
            'dragon_tiger', 'north_fund', 'margin_data', 'block_trades', 'stock_news'
        ];
        
        for (const table of tables) {
            const result = await timescaleDB.query(`
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '${table}'
                );
            `);
            
            if (result.rows[0].exists) {
                console.log(`  ✅ ${table}`);
            } else {
                console.log(`  ❌ ${table} - 创建失败`);
            }
        }

        console.log();
        console.log('='.repeat(80));
        console.log('✨ 数据库迁移完成！');
        console.log('='.repeat(80));
        console.log();
        console.log('已创建的表：');
        console.log('  - 分钟K线表：kline_1m, kline_5m, kline_15m, kline_30m, kline_60m');
        console.log('  - 龙虎榜表：dragon_tiger');
        console.log('  - 北向资金表：north_fund');
        console.log('  - 融资融券表：margin_data');
        console.log('  - 大宗交易表：block_trades');
        console.log('  - 新闻表：stock_news');
        console.log();
        console.log('下一步：运行 init-database-full.ts 下载高级数据');
        console.log();

    } catch (error) {
        console.error();
        console.error('❌ 迁移失败:', error);
        console.error();
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

// 运行迁移
migrateAdvancedTables().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
