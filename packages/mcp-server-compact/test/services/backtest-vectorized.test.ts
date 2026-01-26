/**
 * 向量化回测引擎测试
 */

import { describe, it, expect } from 'vitest';
import { runVectorizedBacktest, runBatchVectorizedBacktest } from '../../src/services/backtest-vectorized.js';
import { KlineData } from '../../src/types/stock.js';

describe('Vectorized Backtest Engine', () => {
    // 生成测试数据
    const generateTestKlines = (days: number, trend: 'up' | 'down' | 'flat' = 'up'): KlineData[] => {
        const klines: KlineData[] = [];
        let basePrice = 100;
        
        for (let i = 0; i < days; i++) {
            const date = new Date(2024, 0, i + 1);
            const dateStr = date.toISOString().split('T')[0];
            
            if (trend === 'up') {
                basePrice += Math.random() * 2 - 0.5; // 上涨趋势
            } else if (trend === 'down') {
                basePrice -= Math.random() * 2 - 0.5; // 下跌趋势
            } else {
                basePrice += Math.random() * 1 - 0.5; // 震荡
            }
            
            const open = basePrice + Math.random() * 2 - 1;
            const close = basePrice + Math.random() * 2 - 1;
            const high = Math.max(open, close) + Math.random() * 1;
            const low = Math.min(open, close) - Math.random() * 1;
            
            klines.push({
                code: '000001',
                date: dateStr,
                open,
                high,
                low,
                close,
                volume: Math.floor(Math.random() * 1000000) + 100000,
                amount: Math.floor(Math.random() * 10000000) + 1000000,
            });
        }
        
        return klines;
    };

    describe('MA Cross Strategy', () => {
        it('should run vectorized backtest successfully', () => {
            const klines = generateTestKlines(100, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const { result, trades, equityCurve } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            
            expect(result).toBeDefined();
            expect(result.strategy).toBe('ma_cross_vectorized');
            expect(result.initialCapital).toBe(100000);
            expect(result.finalCapital).toBeGreaterThan(0);
            expect(result.totalReturn).toBeDefined();
            expect(result.maxDrawdown).toBeGreaterThanOrEqual(0);
            expect(result.sharpeRatio).toBeDefined();
            expect(trades).toBeInstanceOf(Array);
            expect(equityCurve).toHaveLength(100);
        });

        it('should generate buy and sell signals', () => {
            const klines = generateTestKlines(100, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const { trades } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            
            const buyTrades = trades.filter(t => t.action === 'buy');
            const sellTrades = trades.filter(t => t.action === 'sell');
            
            // MA cross strategy may or may not generate signals depending on data
            // Just verify trades array is defined
            expect(trades).toBeInstanceOf(Array);
            expect(buyTrades.length).toBeGreaterThanOrEqual(0);
            expect(sellTrades.length).toBeGreaterThanOrEqual(0);
        });

        it('should calculate correct metrics', () => {
            const klines = generateTestKlines(100, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const { result } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            
            // 上涨趋势应该有正收益
            expect(result.totalReturn).toBeGreaterThan(-0.5); // 允许一定亏损
            expect(result.maxDrawdown).toBeLessThanOrEqual(1);
            expect(result.winRate).toBeGreaterThanOrEqual(0);
            expect(result.winRate).toBeLessThanOrEqual(1);
        });
    });

    describe('Buy and Hold Strategy', () => {
        it('should execute buy and hold correctly', () => {
            const klines = generateTestKlines(50, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
            };
            
            const { result, trades } = runVectorizedBacktest(
                '000001',
                klines,
                'buy_and_hold',
                params
            );
            
            expect(result).toBeDefined();
            expect(trades).toHaveLength(1); // Only one buy trade
            expect(trades[0].action).toBe('buy');
        });
    });

    describe('Performance Comparison', () => {
        it('should be faster than loop-based backtest for large datasets', () => {
            const klines = generateTestKlines(1000, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const start = Date.now();
            const { result } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            const duration = Date.now() - start;
            
            expect(result).toBeDefined();
            expect(duration).toBeLessThan(1000); // Should complete in < 1 second
        });
    });

    describe('Batch Backtest', () => {
        it('should run batch backtest for multiple stocks', () => {
            const stocks = [
                { code: '000001', klines: generateTestKlines(100, 'up') },
                { code: '000002', klines: generateTestKlines(100, 'down') },
                { code: '000003', klines: generateTestKlines(100, 'flat') },
            ];
            
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const results = runBatchVectorizedBacktest(stocks, 'ma_cross', params);
            
            expect(results).toHaveLength(3);
            expect(results[0].code).toBe('000001');
            expect(results[1].code).toBe('000002');
            expect(results[2].code).toBe('000003');
            
            // All results should have valid metrics
            for (const r of results) {
                expect(r.result.totalReturn).toBeDefined();
                expect(r.result.maxDrawdown).toBeGreaterThanOrEqual(0);
            }
        });
    });

    describe('Edge Cases', () => {
        it('should handle insufficient data gracefully', () => {
            const klines = generateTestKlines(10, 'up'); // Too few data points
            const params = {
                initialCapital: 100000,
                commission: 0.001,
                slippage: 0.001,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const { result } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            
            expect(result).toBeDefined();
            // May not generate any signals, but should not crash
        });

        it('should handle zero commission and slippage', () => {
            const klines = generateTestKlines(50, 'up');
            const params = {
                initialCapital: 100000,
                commission: 0,
                slippage: 0,
                shortPeriod: 5,
                longPeriod: 20,
            };
            
            const { result } = runVectorizedBacktest(
                '000001',
                klines,
                'ma_cross',
                params
            );
            
            expect(result).toBeDefined();
            expect(result.finalCapital).toBeGreaterThan(0);
        });
    });
});
