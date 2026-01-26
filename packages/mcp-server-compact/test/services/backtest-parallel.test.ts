/**
 * 并行参数优化测试
 */

import { describe, it, expect } from 'vitest';
import { optimizeParametersParallel } from '../../src/services/backtest.js';
import type { KlineData, BacktestParams } from '../../src/types/stock.js';

// 生成模拟 K 线数据
function generateMockKlines(days: number): KlineData[] {
    const klines: KlineData[] = [];
    const basePrice = 10;
    let price = basePrice;

    for (let i = 0; i < days; i++) {
        const change = (Math.random() - 0.5) * 0.5;
        price = price * (1 + change);
        
        const open = price * (1 + (Math.random() - 0.5) * 0.02);
        const close = price * (1 + (Math.random() - 0.5) * 0.02);
        const high = Math.max(open, close) * (1 + Math.random() * 0.02);
        const low = Math.min(open, close) * (1 - Math.random() * 0.02);

        klines.push({
            date: new Date(Date.now() - (days - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
            open,
            high,
            low,
            close,
            volume: Math.floor(Math.random() * 1000000) + 100000,
            amount: 0,
            turnover: 0,
            changePercent: change * 100,
        });
    }

    return klines;
}

describe('Parallel Parameter Optimization', () => {
    const mockKlines = generateMockKlines(250);
    const baseParams: BacktestParams = {
        initialCapital: 100000,
        commission: 0.001,
        slippage: 0.001,
    };

    it('should optimize MA cross parameters in parallel', async () => {
        const paramRanges = {
            shortPeriod: [3, 7, 2],  // [start, end, step] -> 3, 5, 7
            longPeriod: [15, 25, 5], // 15, 20, 25
        };
        // Total combinations: 3 * 3 = 9

        const startTime = Date.now();
        const { bestParams, bestResult, allResults } = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'ma_cross',
            baseParams,
            paramRanges
        );
        const duration = Date.now() - startTime;

        console.log(`Parallel optimization completed in ${duration}ms`);
        console.log(`Best params:`, bestParams);
        console.log(`Best result:`, bestResult);

        expect(bestParams).toBeDefined();
        expect(bestParams.shortPeriod).toBeGreaterThanOrEqual(3);
        expect(bestParams.shortPeriod).toBeLessThanOrEqual(7);
        expect(bestParams.longPeriod).toBeGreaterThanOrEqual(15);
        expect(bestParams.longPeriod).toBeLessThanOrEqual(25);
        expect(bestResult).toBeDefined();
        expect(allResults.length).toBe(9);
    }, 30000); // 30s timeout

    it('should handle large parameter space efficiently', async () => {
        const paramRanges = {
            shortPeriod: [3, 10, 1],  // 8 values
            longPeriod: [15, 30, 3],  // 6 values
        };
        // Total combinations: 8 * 6 = 48

        const startTime = Date.now();
        const { bestParams, bestResult, allResults } = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'ma_cross',
            baseParams,
            paramRanges
        );
        const duration = Date.now() - startTime;

        console.log(`Large space optimization completed in ${duration}ms`);
        console.log(`Processed ${allResults.length} combinations`);

        expect(allResults.length).toBe(48);
        expect(duration).toBeLessThan(15000); // Should complete in < 15s
    }, 30000);

    it('should fallback to single-thread for small parameter space', async () => {
        const paramRanges = {
            shortPeriod: [5, 7, 2],  // 2 values
            longPeriod: [20, 20, 1], // 1 value
        };
        // Total combinations: 2 * 1 = 2 (< 10, should use single-thread)

        const startTime = Date.now();
        const { bestParams, bestResult, allResults } = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'ma_cross',
            baseParams,
            paramRanges
        );
        const duration = Date.now() - startTime;

        console.log(`Small space optimization completed in ${duration}ms (single-thread)`);

        expect(allResults.length).toBe(2);
        expect(bestParams).toBeDefined();
    }, 10000);

    it('should handle RSI strategy optimization', async () => {
        const paramRanges = {
            threshold: [25, 35, 5], // 25, 30, 35
        };

        const { bestParams, bestResult, allResults } = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'rsi',
            baseParams,
            paramRanges
        );

        expect(allResults.length).toBe(3);
        expect(bestParams.threshold).toBeGreaterThanOrEqual(25);
        expect(bestParams.threshold).toBeLessThanOrEqual(35);
    }, 15000);

    it('should return consistent results across runs', async () => {
        const paramRanges = {
            shortPeriod: [5, 5, 1],
            longPeriod: [20, 20, 1],
        };

        const result1 = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'ma_cross',
            baseParams,
            paramRanges
        );

        const result2 = await optimizeParametersParallel(
            '000001',
            mockKlines,
            'ma_cross',
            baseParams,
            paramRanges
        );

        expect(result1.bestResult.totalReturn).toBeCloseTo(result2.bestResult.totalReturn, 6);
        expect(result1.bestResult.sharpeRatio).toBeCloseTo(result2.bestResult.sharpeRatio, 6);
    }, 15000);
});
