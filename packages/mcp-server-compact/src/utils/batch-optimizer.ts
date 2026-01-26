/**
 * 批量操作优化器
 * 针对常见的批量操作场景提供优化方案
 */

import { parallelExecute, batchExecute, chunkExecute } from './parallel-executor.js';
import { adapterManager } from '../adapters/index.js';

/**
 * 批量获取股票行情（优化版）
 */
export async function getBatchQuotesOptimized(codes: string[]): Promise<Array<{
    code: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
}>> {
    if (codes.length === 0) return [];

    // 使用并行执行，每次最多5个并发
    const results = await parallelExecute(
        codes,
        async (code) => {
            const result = await adapterManager.getRealtimeQuote(code);
            if (result.success && result.data) {
                return {
                    code: result.data.code,
                    name: result.data.name,
                    price: result.data.price,
                    change: result.data.change,
                    changePercent: result.data.changePercent,
                };
            }
            throw new Error(`Failed to get quote for ${code}`);
        },
        {
            concurrency: 5,
            timeout: 5000,
            retryCount: 2,
            retryDelay: 500,
        }
    );

    return results
        .filter((r: any) => r.success && r.data)
        .map((r: any) => r.data!);
}

/**
 * 批量获取K线数据（优化版）
 */
export async function getBatchKlineDataOptimized(
    codes: string[],
    period: string = '101',
    limit: number = 100
): Promise<Map<string, any[]>> {
    if (codes.length === 0) return new Map();

    const resultMap = new Map<string, any[]>();

    // 分块执行，每块10个股票
    const results = await parallelExecute(
        codes,
        async (code) => {
            const result = await adapterManager.getKline(code, period as any, limit);
            if (result.success && result.data) {
                return { code, data: result.data };
            }
            throw new Error(`Failed to get kline for ${code}`);
        },
        {
            concurrency: 3,  // K线数据较大，降低并发数
            timeout: 10000,
            retryCount: 1,
        }
    );

    results.forEach((result: any) => {
        if (result.success && result.data) {
            resultMap.set(result.data.code, result.data.data);
        }
    });

    return resultMap;
}

/**
 * 批量获取财务数据（优化版）
 */
export async function getBatchFinancialDataOptimized(
    codes: string[]
): Promise<Map<string, any>> {
    if (codes.length === 0) return new Map();

    const resultMap = new Map<string, any>();

    const results = await parallelExecute(
        codes,
        async (code) => {
            const result = await adapterManager.getFinancials(code);
            if (result.success && result.data) {
                return { code, data: result.data };
            }
            throw new Error(`Failed to get financial data for ${code}`);
        },
        {
            concurrency: 5,
            timeout: 5000,
            retryCount: 2,
        }
    );

    results.forEach((result: any) => {
        if (result.success && result.data) {
            resultMap.set(result.data.code, result.data.data);
        }
    });

    return resultMap;
}

/**
 * 批量计算技术指标（优化版）
 */
export async function calculateBatchIndicatorsOptimized(
    dataMap: Map<string, any[]>,
    indicators: string[]
): Promise<Map<string, any>> {
    const codes = Array.from(dataMap.keys());
    const resultMap = new Map<string, any>();

    // 技术指标计算是CPU密集型，使用较高并发
    const results = await parallelExecute(
        codes,
        async (code) => {
            const klines = dataMap.get(code);
            if (!klines || klines.length === 0) {
                throw new Error(`No kline data for ${code}`);
            }

            // 这里应该调用实际的技术指标计算函数
            // 简化示例
            const closes = klines.map((k: any) => k.close);
            const result: any = { code };

            // 计算各种指标
            if (indicators.includes('sma')) {
                result.sma = closes.slice(-20).reduce((a: number, b: number) => a + b, 0) / 20;
            }
            if (indicators.includes('ema')) {
                result.ema = closes[closes.length - 1]; // 简化
            }

            return result;
        },
        {
            concurrency: 10,  // CPU密集型，可以更高并发
            timeout: 3000,
        }
    );

    results.forEach((result: any) => {
        if (result.success && result.data) {
            resultMap.set(result.data.code, result.data);
        }
    });

    return resultMap;
}

/**
 * 批量筛选股票（优化版）
 */
export async function batchScreenStocksOptimized(
    codes: string[],
    filters: {
        minPrice?: number;
        maxPrice?: number;
        minVolume?: number;
        minChangePercent?: number;
        maxChangePercent?: number;
    }
): Promise<string[]> {
    if (codes.length === 0) return [];

    // 分批获取行情数据
    const chunkSize = 50;
    const chunks: string[][] = [];
    for (let i = 0; i < codes.length; i += chunkSize) {
        chunks.push(codes.slice(i, i + chunkSize));
    }

    const allQuotes: any[] = [];

    // 并行处理每个批次
    const results = await parallelExecute(
        chunks,
        async (chunk) => {
            return await getBatchQuotesOptimized(chunk);
        },
        {
            concurrency: 3,
            timeout: 15000,
        }
    );

    results.forEach((result: any) => {
        if (result.success && result.data) {
            allQuotes.push(...result.data);
        }
    });

    // 应用过滤条件
    const filtered = allQuotes.filter(quote => {
        if (filters.minPrice && quote.price < filters.minPrice) return false;
        if (filters.maxPrice && quote.price > filters.maxPrice) return false;
        if (filters.minVolume && quote.volume < filters.minVolume) return false;
        if (filters.minChangePercent && quote.changePercent < filters.minChangePercent) return false;
        if (filters.maxChangePercent && quote.changePercent > filters.maxChangePercent) return false;
        return true;
    });

    return filtered.map((q: any) => q.code);
}

/**
 * 批量更新数据库（优化版）
 */
export async function batchUpdateDatabaseOptimized<T>(
    items: T[],
    updateFn: (item: T) => Promise<void>,
    options: {
        batchSize?: number;
        concurrency?: number;
    } = {}
): Promise<{
    succeeded: number;
    failed: number;
    errors: Array<{ item: T; error: string }>;
}> {
    const { batchSize = 100, concurrency = 5 } = options;

    // 分批处理
    const batches: T[][] = [];
    for (let i = 0; i < items.length; i += batchSize) {
        batches.push(items.slice(i, i + batchSize));
    }

    let succeeded = 0;
    let failed = 0;
    const errors: Array<{ item: T; error: string }> = [];

    // 并行处理每个批次
    for (const batch of batches) {
        const results = await parallelExecute(
            batch,
            updateFn,
            {
                concurrency,
                timeout: 10000,
                retryCount: 2,
            }
        );

        results.forEach((result, index) => {
            if (result.success) {
                succeeded++;
            } else {
                failed++;
                errors.push({
                    item: batch[index],
                    error: result.error || 'Unknown error',
                });
            }
        });
    }

    return { succeeded, failed, errors };
}
