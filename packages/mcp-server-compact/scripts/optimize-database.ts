#!/usr/bin/env tsx
/**
 * 数据库优化脚本
 * 执行索引创建和性能优化
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function main() {
    console.log('🚀 开始数据库优化...\n');

    try {
        // 1. 读取优化SQL脚本
        const sqlPath = join(__dirname, '../src/storage/db-optimization.sql');
        const sql = readFileSync(sqlPath, 'utf-8');

        console.log('📄 读取优化脚本: db-optimization.sql');
        console.log(`   脚本大小: ${(sql.length / 1024).toFixed(2)} KB\n`);

        // 2. 执行优化脚本
        console.log('⚙️  执行优化脚本...');
        const startTime = Date.now();

        await timescaleDB.query(sql);

        const executionTime = Date.now() - startTime;
        console.log(`✅ 优化脚本执行完成 (耗时: ${executionTime}ms)\n`);

        // 3. 验证索引创建
        console.log('🔍 验证索引创建...');
        const indexResult = await timescaleDB.query(`
            SELECT 
                schemaname,
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
        `);

        console.log(`   创建的索引数量: ${indexResult.rows.length}`);
        
        // 按表分组统计
        const indexByTable: Record<string, number> = {};
        indexResult.rows.forEach((row: any) => {
            indexByTable[row.tablename] = (indexByTable[row.tablename] || 0) + 1;
        });

        console.log('\n   各表索引数量:');
        Object.entries(indexByTable)
            .sort((a, b) => b[1] - a[1])
            .forEach(([table, count]) => {
                console.log(`   - ${table}: ${count}个索引`);
            });

        // 4. 获取表大小统计
        console.log('\n📊 表大小统计:');
        const sizeResult = await timescaleDB.query(`
            SELECT 
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
                pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 10
        `);

        sizeResult.rows.forEach((row: any) => {
            console.log(`   ${row.tablename.padEnd(25)} | 总计: ${row.total_size.padEnd(10)} | 表: ${row.table_size.padEnd(10)} | 索引: ${row.index_size}`);
        });

        // 5. 更新表统计信息
        console.log('\n📈 更新表统计信息...');
        const tables = [
            'kline_1d',
            'financials',
            'stocks',
            'positions',
            'watchlist',
            'backtest_results',
            'backtest_trades',
            'alerts',
            'alert_history',
            'stock_embeddings',
            'data_quality',
        ];

        for (const table of tables) {
            try {
                await timescaleDB.query(`ANALYZE ${table}`);
                console.log(`   ✓ ${table}`);
            } catch (error) {
                console.log(`   ✗ ${table} (表可能不存在)`);
            }
        }

        console.log('\n✨ 数据库优化完成！\n');
        console.log('📝 优化总结:');
        console.log(`   - 索引数量: ${indexResult.rows.length}`);
        console.log(`   - 执行时间: ${executionTime}ms`);
        console.log(`   - 优化表数: ${tables.length}`);
        console.log('\n💡 建议:');
        console.log('   1. 运行查询性能测试验证优化效果');
        console.log('   2. 监控慢查询日志');
        console.log('   3. 定期执行 VACUUM ANALYZE');

    } catch (error) {
        console.error('❌ 优化失败:', error);
        process.exit(1);
    }

    process.exit(0);
}

main();
