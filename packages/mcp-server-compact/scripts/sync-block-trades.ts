#!/usr/bin/env node
/**
 * 大宗交易数据同步脚本
 * 使用 AdapterManager 从东方财富获取大宗交易数据并存入数据库
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { AdapterManager } from '../src/adapters/index.js';

interface SyncProgress {
    total: number;
    processed: number;
    success: number;
    failed: string[];
    startTime: number;
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 格式化日期为 YYYY-MM-DD
 */
function formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
}

/**
 * 检查是否为交易日（简单判断：排除周末）
 */
function isTradingDay(date: Date): boolean {
    const dayOfWeek = date.getDay();
    return dayOfWeek !== 0 && dayOfWeek !== 6;
}

/**
 * 同步指定日期的大宗交易数据
 */
async function syncBlockTradesForDate(date: string, adapterManager: AdapterManager): Promise<number> {
    try {
        // 检查是否已有数据
        const existing = await timescaleDB.query(
            'SELECT COUNT(*) as c FROM block_trades WHERE date = $1',
            [date]
        );
        const existingCount = parseInt(existing.rows[0]?.c || '0');
        
        if (existingCount > 0) {
            console.log(`  ⏭️  ${date}: 已有 ${existingCount} 条数据，跳过`);
            return 0;
        }

        // 使用 AdapterManager 获取大宗交易数据
        const res = await adapterManager.getBlockTrades(date);

        if (!res.success || !res.data || res.data.length === 0) {
            console.log(`  ⚠️  ${date}: ${res.error || '无数据'}`);
            return 0;
        }

        // 批量插入数据
        let inserted = 0;
        for (const item of res.data) {
            try {
                await timescaleDB.query(
                    `INSERT INTO block_trades (date, code, name, price, volume, amount, buyer, seller, premium_rate)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                     ON CONFLICT (date, code, buyer, seller) DO NOTHING`,
                    [
                        date,
                        item.code,
                        item.name,
                        item.price,
                        item.volume,
                        item.amount,
                        item.buyer || '',
                        item.seller || '',
                        item.premium || 0
                    ]
                );
                inserted++;
            } catch (e: any) {
                console.log(`    ❌ 插入失败 ${item.code}: ${e.message}`);
            }
        }

        console.log(`  ✅ ${date}: 成功插入 ${inserted} 条数据`);
        return inserted;

    } catch (error: any) {
        console.log(`  ❌ ${date}: ${error.message || error}`);
        return 0;
    }
}

/**
 * 主函数
 */
async function main() {
    console.log('='.repeat(70));
    console.log('大宗交易数据同步脚本');
    console.log('='.repeat(70));

    const args = process.argv.slice(2);
    const days = parseInt(args[0] || '30', 10); // 默认同步最近30天
    const delayBetweenDays = 1000; // 每天之间延迟1秒

    try {
        // 初始化数据库
        await timescaleDB.initialize();
        console.log('✅ 数据库已连接\n');

        // 确保 block_trades 表存在
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
        console.log('✅ block_trades 表已确认\n');

        // 初始化 AdapterManager
        const adapterManager = new AdapterManager();
        console.log('✅ AdapterManager 已初始化\n');

        // 生成日期列表（从今天往前推）
        const today = new Date();
        const dates: string[] = [];
        
        for (let i = 0; i < days; i++) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            
            // 只处理交易日
            if (isTradingDay(date)) {
                dates.push(formatDate(date));
            }
        }

        console.log(`📦 开始同步大宗交易数据 (${dates.length} 个交易日)...`);
        console.log(`   日期范围: ${dates[dates.length - 1]} 至 ${dates[0]}`);
        console.log(`   数据源: akshare-mcp (统一数据出口)\n`);

        const progress: SyncProgress = {
            total: dates.length,
            processed: 0,
            success: 0,
            failed: [],
            startTime: Date.now()
        };

        // 逐日同步
        for (const date of dates) {
            const inserted = await syncBlockTradesForDate(date, adapterManager);
            
            if (inserted > 0) {
                progress.success += inserted;
            } else if (inserted === 0) {
                // 检查是否真的失败还是只是没有数据
                const existing = await timescaleDB.query(
                    'SELECT COUNT(*) as c FROM block_trades WHERE date = $1',
                    [date]
                );
                if (parseInt(existing.rows[0]?.c || '0') === 0) {
                    progress.failed.push(date);
                }
            }

            progress.processed++;

            // 显示进度
            const percent = ((progress.processed / progress.total) * 100).toFixed(1);
            const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(0);
            console.log(`进度: ${progress.processed}/${progress.total} (${percent}%), 成功插入: ${progress.success} 条, 耗时: ${elapsed}s\n`);

            // 延迟以避免请求过快
            if (progress.processed < progress.total) {
                await sleep(delayBetweenDays);
            }
        }

        // 最终统计
        console.log('\n' + '='.repeat(70));
        console.log('同步完成！');
        
        const finalStats = await timescaleDB.query(`
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT date) as trading_days,
                COUNT(DISTINCT code) as unique_stocks,
                MIN(date) as earliest_date,
                MAX(date) as latest_date
            FROM block_trades
        `);
        const stats = finalStats.rows[0];
        
        console.log(`\n当前数据库状态:`);
        console.log(`  大宗交易记录总数: ${stats.total_records}`);
        console.log(`  覆盖交易日: ${stats.trading_days} 天`);
        console.log(`  涉及股票: ${stats.unique_stocks} 只`);
        console.log(`  日期范围: ${stats.earliest_date} 至 ${stats.latest_date}`);
        
        if (progress.failed.length > 0) {
            console.log(`\n⚠️  失败/无数据的日期 (${progress.failed.length} 天):`);
            console.log(`  ${progress.failed.slice(0, 10).join(', ')}${progress.failed.length > 10 ? '...' : ''}`);
        }
        
        console.log('='.repeat(70));

    } catch (error) {
        console.error('❌ 同步失败:', error);
        process.exit(1);
    } finally {
        await timescaleDB.close();
        process.exit(0);
    }
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
