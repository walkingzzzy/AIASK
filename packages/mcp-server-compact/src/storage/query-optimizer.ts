/**
 * 查询优化器
 * 提供查询性能监控和优化建议
 */

import { timescaleDB } from './timescaledb.js';
import winston from 'winston';

const logger = winston.createLogger({
    level: 'info',
    format: winston.format.json(),
    transports: [
        new winston.transports.File({ filename: 'logs/query-performance.log' }),
    ],
});

export interface QueryPerformance {
    query: string;
    executionTime: number;
    rowsReturned: number;
    timestamp: Date;
}

export interface SlowQuery {
    queryText: string;
    executionTime: number;
    rowsReturned: number;
    timestamp: Date;
}

/**
 * 慢查询阈值（毫秒）
 */
const SLOW_QUERY_THRESHOLD = 100;

/**
 * 查询性能监控装饰器
 */
export function monitorQuery(target: any, propertyKey: string, descriptor: PropertyDescriptor) {
    const originalMethod = descriptor.value;

    descriptor.value = async function (...args: any[]) {
        const startTime = Date.now();
        
        try {
            const result = await originalMethod.apply(this, args);
            const executionTime = Date.now() - startTime;
            
            // 记录查询性能
            const performance: QueryPerformance = {
                query: propertyKey,
                executionTime,
                rowsReturned: Array.isArray(result) ? result.length : 1,
                timestamp: new Date(),
            };
            
            // 如果是慢查询，记录到日志和数据库
            if (executionTime > SLOW_QUERY_THRESHOLD) {
                logger.warn('Slow query detected', performance);
                await logSlowQuery(performance);
            }
            
            return result;
        } catch (error) {
            const executionTime = Date.now() - startTime;
            logger.error('Query failed', {
                query: propertyKey,
                executionTime,
                error: error instanceof Error ? error.message : String(error),
            });
            throw error;
        }
    };

    return descriptor;
}

/**
 * 记录慢查询到数据库
 */
async function logSlowQuery(performance: QueryPerformance): Promise<void> {
    try {
        const pool = (timescaleDB as any).pool;
        if (!pool) return;
        
        await pool.query(`
            INSERT INTO slow_query_log (query_text, execution_time, rows_returned, timestamp)
            VALUES ($1, $2, $3, $4)
        `, [
            performance.query,
            performance.executionTime,
            performance.rowsReturned,
            performance.timestamp,
        ]);
    } catch (error) {
        logger.error('Failed to log slow query', { error });
    }
}

/**
 * 获取慢查询统计
 */
export async function getSlowQueryStats(limit: number = 10): Promise<SlowQuery[]> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return [];
    
    const result = await pool.query(`
        SELECT 
            query_text,
            execution_time,
            rows_returned,
            timestamp
        FROM slow_query_log
        ORDER BY execution_time DESC
        LIMIT $1
    `, [limit]);

    return result.rows.map((row: any) => ({
        queryText: row.query_text,
        executionTime: row.execution_time,
        rowsReturned: row.rows_returned,
        timestamp: row.timestamp,
    }));
}

/**
 * 获取查询性能统计
 */
export async function getQueryPerformanceStats(): Promise<{
    totalQueries: number;
    slowQueries: number;
    avgExecutionTime: number;
    maxExecutionTime: number;
}> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return { totalQueries: 0, slowQueries: 0, avgExecutionTime: 0, maxExecutionTime: 0 };
    
    const result = await pool.query(`
        SELECT 
            COUNT(*) as total_queries,
            COUNT(*) FILTER (WHERE execution_time > $1) as slow_queries,
            AVG(execution_time) as avg_execution_time,
            MAX(execution_time) as max_execution_time
        FROM slow_query_log
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    `, [SLOW_QUERY_THRESHOLD]);

    const row = result.rows[0];
    return {
        totalQueries: parseInt(row.total_queries) || 0,
        slowQueries: parseInt(row.slow_queries) || 0,
        avgExecutionTime: parseFloat(row.avg_execution_time) || 0,
        maxExecutionTime: parseFloat(row.max_execution_time) || 0,
    };
}

/**
 * 清理旧的慢查询日志（保留最近30天）
 */
export async function cleanupSlowQueryLog(): Promise<number> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return 0;
    
    const result = await pool.query(`
        DELETE FROM slow_query_log
        WHERE timestamp < NOW() - INTERVAL '30 days'
    `);

    return result.rowCount || 0;
}

/**
 * 获取索引使用情况
 */
export async function getIndexUsageStats(): Promise<Array<{
    tableName: string;
    indexName: string;
    indexScans: number;
    tuplesRead: number;
    tuplesFetched: number;
}>> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return [];
    
    const result = await pool.query(`
        SELECT 
            schemaname,
            tablename,
            indexname,
            idx_scan as index_scans,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
        ORDER BY idx_scan DESC
        LIMIT 20
    `);

    return result.rows.map((row: any) => ({
        tableName: row.tablename,
        indexName: row.indexname,
        indexScans: parseInt(row.index_scans) || 0,
        tuplesRead: parseInt(row.tuples_read) || 0,
        tuplesFetched: parseInt(row.tuples_fetched) || 0,
    }));
}

/**
 * 获取表大小统计
 */
export async function getTableSizeStats(): Promise<Array<{
    tableName: string;
    totalSize: string;
    tableSize: string;
    indexSize: string;
}>> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return [];
    
    const result = await pool.query(`
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

    return result.rows.map((row: any) => ({
        tableName: row.tablename,
        totalSize: row.total_size,
        tableSize: row.table_size,
        indexSize: row.index_size,
    }));
}

/**
 * 分析表并更新统计信息
 */
export async function analyzeTable(tableName: string): Promise<void> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return;
    
    await pool.query(`ANALYZE ${tableName}`);
    logger.info(`Analyzed table: ${tableName}`);
}

/**
 * 分析所有表
 */
export async function analyzeAllTables(): Promise<void> {
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
            await analyzeTable(table);
        } catch (error) {
            logger.error(`Failed to analyze table ${table}`, { error });
        }
    }
}

/**
 * 获取查询计划
 */
export async function explainQuery(query: string, params: any[] = []): Promise<string> {
    const pool = (timescaleDB as any).pool;
    if (!pool) return '';
    
    const result = await pool.query(`EXPLAIN ANALYZE ${query}`, params);
    return result.rows.map((row: any) => row['QUERY PLAN']).join('\n');
}
