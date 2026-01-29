#!/usr/bin/env node
/**
 * 修复 stock_quotes 表的唯一索引
 * 解决 ON CONFLICT (time, code) 无法工作的问题
 */

import { timescaleDB } from '../src/storage/timescaledb.js';

async function main() {
    console.log('='.repeat(50));
    console.log('修复 stock_quotes 唯一索引');
    console.log('='.repeat(50));

    try {
        await timescaleDB.initialize();
        console.log('✅ 数据库已连接\n');

        // 检查现有索引
        console.log('检查现有索引...');
        const indexResult = await timescaleDB.query(`
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'stock_quotes';
        `);
        
        console.log('现有索引:');
        if (indexResult.rows.length === 0) {
            console.log('  (无)');
        } else {
            indexResult.rows.forEach((row: any) => {
                console.log(`  - ${row.indexname}`);
            });
        }

        // 创建唯一索引
        console.log('\n创建唯一索引 idx_stock_quotes_time_code...');
        try {
            await timescaleDB.query(`
                CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code 
                ON stock_quotes (time, code);
            `);
            console.log('✅ 唯一索引创建成功！');
        } catch (e: any) {
            if (e.message.includes('already exists')) {
                console.log('✅ 索引已存在');
            } else {
                throw e;
            }
        }

        // 验证索引
        console.log('\n验证索引...');
        const verifyResult = await timescaleDB.query(`
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'stock_quotes' AND indexname = 'idx_stock_quotes_time_code';
        `);
        
        if (verifyResult.rows.length > 0) {
            console.log('✅ 索引验证成功:');
            console.log(`   ${verifyResult.rows[0].indexdef}`);
        } else {
            console.log('❌ 索引验证失败');
        }

        console.log('\n' + '='.repeat(50));
        console.log('修复完成！现在可以重新运行行情同步:');
        console.log('  npx tsx scripts/sync-missing-data.ts quotes 10000');
        console.log('='.repeat(50));

    } catch (error) {
        console.error('❌ 修复失败:', error);
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
