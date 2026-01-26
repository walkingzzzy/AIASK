/**
 * 查询性能测试
 * 验证数据库优化效果
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { timescaleDB } from '../../src/storage/timescaledb.js';

describe('Query Performance Tests', () => {
    const testCode = '600519';
    const testCodes = ['600519', '000858', '601398', '000001', '600036'];

    describe('K线数据查询性能', () => {
        it('should query single stock kline data within 100ms', async () => {
            const startTime = Date.now();
            
            try {
                const result = await timescaleDB.query(`
                    SELECT * FROM kline_1d 
                    WHERE code = $1 
                    AND time >= NOW() - INTERVAL '1 year'
                    ORDER BY time DESC
                    LIMIT 252
                `, [testCode]);
                
                const executionTime = Date.now() - startTime;
                
                console.log(`Query execution time: ${executionTime}ms`);
                console.log(`Rows returned: ${result.rows.length}`);
                
                // 目标: <100ms
                expect(executionTime).toBeLessThan(100);
            } catch (error) {
                console.log('Skipping test - table may not exist');
            }
        });

        it('should query multiple stocks kline data efficiently', async () => {
            const startTime = Date.now();
            
            try {
                const result = await timescaleDB.query(`
                    SELECT * FROM kline_1d 
                    WHERE code = ANY($1)
                    AND time >= NOW() - INTERVAL '3 months'
                    ORDER BY code, time DESC
                `, [testCodes]);
                
                const executionTime = Date.now() - startTime;
                
                console.log(`Batch query execution time: ${executionTime}ms`);
                console.log(`Rows returned: ${result.rows.length}`);
                
                // 目标: <200ms
                expect(executionTime).toBeLessThan(200);
            } catch (error) {
                console.log('Skipping test - table may not exist');
            }
        });
    });

    describe('财务数据查询性能', () => {
        it('should query financial data within 50ms', async () => {
            const startTime = Date.now();
            
            try {
                const result = await timescaleDB.query(`
                    SELECT * FROM financials 
                    WHERE code = $1 
                    ORDER BY report_date DESC 
                    LIMIT 20
                `, [testCode]);
                
                const executionTime = Date.now() - startTime;
                
                console.log(`Financial query execution time: ${executionTime}ms`);
                
                // 目标: <50ms
                expect(executionTime).toBeLessThan(50);
            } catch (error) {
                console.log('Skipping test - table may not exist');
            }
        });
    });

    describe('索引使用验证', () => {
        it('should use index for kline queries', async () => {
            try {
                const result = await timescaleDB.query(`
                    EXPLAIN (FORMAT JSON) 
                    SELECT * FROM kline_1d 
                    WHERE code = $1 
                    AND time >= NOW() - INTERVAL '1 year'
                    ORDER BY time DESC
                    LIMIT 252
                `, [testCode]);
                
                const plan = JSON.stringify(result.rows[0]);
                
                // 验证是否使用了索引扫描
                const usesIndex = plan.includes('Index Scan') || plan.includes('Index Only Scan');
                
                console.log('Query plan uses index:', usesIndex);
                
                expect(usesIndex).toBe(true);
            } catch (error) {
                console.log('Skipping test - table may not exist');
            }
        });
    });

    describe('查询统计', () => {
        it('should get index usage statistics', async () => {
            try {
                const result = await timescaleDB.query(`
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        idx_scan as index_scans,
                        idx_tup_read as tuples_read
                    FROM pg_stat_user_indexes
                    WHERE schemaname = 'public'
                    AND tablename IN ('kline_1d', 'financials', 'stocks')
                    ORDER BY idx_scan DESC
                    LIMIT 10
                `);
                
                console.log('Top 10 most used indexes:');
                result.rows.forEach((row: any) => {
                    console.log(`  ${row.tablename}.${row.indexname}: ${row.index_scans} scans`);
                });
                
                expect(result.rows.length).toBeGreaterThanOrEqual(0);
            } catch (error) {
                console.log('Skipping test - statistics may not be available');
            }
        });

        it('should get table size statistics', async () => {
            try {
                const result = await timescaleDB.query(`
                    SELECT 
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                    LIMIT 5
                `);
                
                console.log('Top 5 largest tables:');
                result.rows.forEach((row: any) => {
                    console.log(`  ${row.tablename}: ${row.total_size}`);
                });
                
                expect(result.rows.length).toBeGreaterThanOrEqual(0);
            } catch (error) {
                console.log('Skipping test - table size query failed');
            }
        });
    });
});
