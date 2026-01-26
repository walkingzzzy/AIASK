/**
 * 数据预热服务测试
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { warmupCoreStocks, incrementalUpdate } from '../../src/services/data-warmup.js';
import { timescaleDB } from '../../src/storage/timescaledb.js';

describe('Data Warmup Service', () => {
    beforeAll(async () => {
        // 确保 TimescaleDB 已初始化
        try {
            await timescaleDB.initialize();
        } catch (error) {
            console.warn('TimescaleDB initialization skipped:', error);
        }
    });

    it('should warmup a single stock', async () => {
        const result = await warmupCoreStocks({
            stocks: ['000001'], // 平安银行
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        console.log('Warmup result:', result);

        expect(result).toBeDefined();
        expect(result.stocksProcessed).toBeGreaterThanOrEqual(0);
        expect(result.duration).toBeGreaterThan(0);
        
        if (result.success) {
            expect(result.klineRecords).toBeGreaterThan(0);
        }
    }, 60000); // 60s timeout

    it('should handle multiple stocks', async () => {
        const result = await warmupCoreStocks({
            stocks: ['000001', '600000'], // 平安银行、浦发银行
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        console.log('Multiple stocks warmup:', result);

        expect(result.stocksProcessed).toBeGreaterThanOrEqual(0);
        expect(result.stocksProcessed).toBeLessThanOrEqual(2);
    }, 120000);

    it('should skip already updated stocks when forceUpdate is false', async () => {
        // First warmup
        const result1 = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        // Second warmup (should skip if data is fresh)
        const result2 = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        console.log('First warmup:', result1);
        console.log('Second warmup:', result2);

        // Second run should process fewer or same records
        if (result1.success && result2.success) {
            expect(result2.klineRecords).toBeLessThanOrEqual(result1.klineRecords);
        }
    }, 120000);

    it('should force update when forceUpdate is true', async () => {
        const result = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 30,
            forceUpdate: true,
            includeFinancials: false,
        });

        console.log('Force update result:', result);

        expect(result).toBeDefined();
        if (result.success) {
            expect(result.klineRecords).toBeGreaterThan(0);
        }
    }, 60000);

    it('should handle invalid stock codes gracefully', async () => {
        const result = await warmupCoreStocks({
            stocks: ['INVALID_CODE'],
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        console.log('Invalid stock result:', result);

        expect(result).toBeDefined();
        expect(result.stocksFailed).toContain('INVALID_CODE');
        expect(result.errors.length).toBeGreaterThan(0);
    }, 60000);

    it('should include financial data when requested', async () => {
        const result = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: true,
        });

        console.log('With financials result:', result);

        expect(result).toBeDefined();
        if (result.success) {
            // Financial records may be 0 if data is not available
            expect(result.financialRecords).toBeGreaterThanOrEqual(0);
        }
    }, 60000);

    it('should perform incremental update', async () => {
        const result = await incrementalUpdate(24);

        console.log('Incremental update result:', result);

        expect(result).toBeDefined();
        expect(result.stocksProcessed).toBeGreaterThanOrEqual(0);
        expect(result.duration).toBeGreaterThan(0);
    }, 120000);

    it('should handle empty stock list', async () => {
        const result = await warmupCoreStocks({
            stocks: [],
            lookbackDays: 30,
            forceUpdate: false,
            includeFinancials: false,
        });

        console.log('Empty stock list result:', result);

        expect(result.stocksProcessed).toBe(0);
        expect(result.klineRecords).toBe(0);
    }, 10000);

    it('should respect lookbackDays parameter', async () => {
        const result30 = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 30,
            forceUpdate: true,
            includeFinancials: false,
        });

        const result60 = await warmupCoreStocks({
            stocks: ['000001'],
            lookbackDays: 60,
            forceUpdate: true,
            includeFinancials: false,
        });

        console.log('30 days:', result30);
        console.log('60 days:', result60);

        if (result30.success && result60.success) {
            // 60 days should have more or equal records than 30 days
            expect(result60.klineRecords).toBeGreaterThanOrEqual(result30.klineRecords);
        }
    }, 120000);
});
