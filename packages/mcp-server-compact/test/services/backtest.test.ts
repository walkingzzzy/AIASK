/**
 * 回测服务单元测试
 */

import { describe, it, expect } from 'vitest';
import * as BacktestService from '../../src/services/backtest.js';
import { KlineData } from '../../src/types/stock.js';

// 生成模拟K线数据
function generateMockKlines(days: number, startPrice: number = 100): KlineData[] {
    const klines: KlineData[] = [];
    let price = startPrice;
    const startDate = new Date('2023-01-01');
    
    for (let i = 0; i < days; i++) {
        const date = new Date(startDate);
        date.setDate(date.getDate() + i);
        
        // 随机波动 ±2%
        const change = (Math.random() - 0.5) * 0.04;
        price = price * (1 + change);
        
        const open = price * (1 + (Math.random() - 0.5) * 0.01);
        const high = Math.max(open, price) * (1 + Math.random() * 0.01);
        const low = Math.min(open, price) * (1 - Math.random() * 0.01);
        
        klines.push({
            code: '000001',
            date: date.toISOString().slice(0, 10),
            open,
            high,
            low,
            close: price,
            volume: Math.floor(1000000 + Math.random() * 500000),
            amount: price * (1000000 + Math.random() * 500000),
        });
    }
    
    return klines;
}

function generateTrendKlines(days: number): KlineData[] {
    const klines: KlineData[] = [];
    const startDate = new Date('2023-01-01');
    let price = 100;

    for (let i = 0; i < days; i++) {
        const date = new Date(startDate);
        date.setDate(date.getDate() + i);
        price += 1;
        const close = price;
        klines.push({
            code: '000001',
            date: date.toISOString().slice(0, 10),
            open: close,
            high: close,
            low: close * 0.98,
            close,
            volume: 1000000,
            amount: close * 1000000,
        });
    }

    return klines;
}

describe('Backtest Service', () => {
    const mockKlines = generateMockKlines(100);
    const baseParams: BacktestService.BacktestParams = {
        initialCapital: 100000,
        commission: 0.001,
        slippage: 0.001,
    };

    describe('runBacktest', () => {
        it('should run buy_and_hold strategy', () => {
            const { result, trades, equityCurve } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'buy_and_hold',
                baseParams
            );
            
            expect(result).toBeDefined();
            expect(result.strategy).toBe('buy_and_hold');
            expect(result.initialCapital).toBe(100000);
            expect(result.finalCapital).toBeGreaterThan(0);
            expect(trades.length).toBeGreaterThanOrEqual(1);
            expect(equityCurve.length).toBe(mockKlines.length);
        });

        it('should run ma_cross strategy', () => {
            const { result, trades } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'ma_cross',
                { ...baseParams, shortPeriod: 5, longPeriod: 20 }
            );
            
            expect(result).toBeDefined();
            expect(result.strategy).toBe('ma_cross');
            expect(trades.length).toBeGreaterThanOrEqual(0);
        });

        it('should run momentum strategy', () => {
            const { result, trades } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'momentum',
                { ...baseParams, lookback: 20, threshold: 0.02 }
            );
            
            expect(result).toBeDefined();
            expect(result.strategy).toBe('momentum');
            expect(trades.length).toBeGreaterThanOrEqual(0);
        });

        it('should run rsi strategy', () => {
            const { result, trades } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'rsi',
                baseParams
            );
            
            expect(result).toBeDefined();
            expect(result.strategy).toBe('rsi');
            expect(trades.length).toBeGreaterThanOrEqual(0);
        });

        it('should calculate performance metrics correctly', () => {
            const { result } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'buy_and_hold',
                baseParams
            );
            
            expect(result.totalReturn).toBeDefined();
            expect(result.maxDrawdown).toBeGreaterThanOrEqual(0);
            expect(result.maxDrawdown).toBeLessThanOrEqual(1);
            expect(result.sharpeRatio).toBeDefined();
            expect(result.winRate).toBeGreaterThanOrEqual(0);
            expect(result.winRate).toBeLessThanOrEqual(1);
            expect(result.profitFactor).toBeGreaterThanOrEqual(0);
        });

        it('should force sell by max holding days', () => {
            const trendKlines = generateTrendKlines(10);
            const { trades } = BacktestService.runBacktest(
                '000001',
                trendKlines,
                'buy_and_hold',
                { ...baseParams, maxHoldingDays: 5 }
            );

            const sellTrades = trades.filter(t => t.action === 'sell');
            expect(sellTrades.length).toBe(1);
            expect(sellTrades[0].date).toBe(trendKlines[5].date);
        });

        it('should sell when KDJ is overbought', () => {
            const trendKlines = generateTrendKlines(30);
            const { trades } = BacktestService.runBacktest(
                '000001',
                trendKlines,
                'buy_and_hold',
                { ...baseParams, sellSignal: 'kdj_overbought' }
            );

            const sellTrades = trades.filter(t => t.action === 'sell');
            expect(sellTrades.length).toBeGreaterThan(0);
        });
    });

    describe('optimizeParameters', () => {
        it('should optimize MA cross parameters', () => {
            const paramRanges = {
                shortPeriod: [3, 7, 2],  // [start, end, step]
                longPeriod: [15, 25, 5],
            };
            
            const { bestParams, bestResult, allResults } = BacktestService.optimizeParameters(
                '000001',
                mockKlines,
                'ma_cross',
                baseParams,
                paramRanges
            );
            
            expect(bestParams).toBeDefined();
            expect(bestParams.shortPeriod).toBeGreaterThanOrEqual(3);
            expect(bestParams.shortPeriod).toBeLessThanOrEqual(7);
            expect(bestParams.longPeriod).toBeGreaterThanOrEqual(15);
            expect(bestParams.longPeriod).toBeLessThanOrEqual(25);
            expect(bestResult).toBeDefined();
            expect(allResults.length).toBeGreaterThan(0);
        });

        it('should return base params when no ranges provided', () => {
            const { bestParams, bestResult } = BacktestService.optimizeParameters(
                '000001',
                mockKlines,
                'buy_and_hold',
                baseParams,
                {}
            );
            
            expect(bestParams).toEqual(baseParams);
            expect(bestResult).toBeDefined();
        });
    });

    describe('monteCarloSimulation', () => {
        it('should run Monte Carlo simulation', () => {
            const { trades } = BacktestService.runBacktest(
                '000001',
                mockKlines,
                'ma_cross',
                { ...baseParams, shortPeriod: 5, longPeriod: 20 }
            );
            
            if (trades.filter(t => t.action === 'sell').length < 2) {
                // Skip if not enough trades
                return;
            }
            
            const result = BacktestService.monteCarloSimulation(
                trades,
                baseParams.initialCapital,
                100
            );
            
            expect(result.runs).toBe(100);
            expect(result.bestCase).toBeGreaterThanOrEqual(result.worstCase);
            expect(result.average).toBeDefined();
            expect(result.median).toBeDefined();
            expect(result.confidence95).toBeDefined();
            expect(result.drawdowns.length).toBe(100);
        });

        it('should handle empty trades', () => {
            const result = BacktestService.monteCarloSimulation(
                [],
                baseParams.initialCapital,
                100
            );
            
            expect(result.runs).toBe(100);
            expect(result.bestCase).toBe(0);
            expect(result.worstCase).toBe(0);
        });
    });

    describe('walkForwardAnalysis', () => {
        it('should run walk forward analysis', () => {
            const longKlines = generateMockKlines(400);
            const paramRanges = {
                shortPeriod: [3, 7, 2],
                longPeriod: [15, 25, 5],
            };
            
            const result = BacktestService.walkForwardAnalysis(
                '000001',
                longKlines,
                'ma_cross',
                baseParams,
                paramRanges,
                250,  // train window
                60    // test window
            );
            
            expect(result.results.length).toBeGreaterThan(0);
            expect(result.overallReturn).toBeDefined();
            
            result.results.forEach(segment => {
                expect(segment.period).toBeDefined();
                expect(segment.params).toBeDefined();
                expect(segment.return).toBeDefined();
            });
        });

        it('should throw error for insufficient data', () => {
            const shortKlines = generateMockKlines(50);
            const paramRanges = {
                shortPeriod: [3, 7, 2],
            };
            
            expect(() => {
                BacktestService.walkForwardAnalysis(
                    '000001',
                    shortKlines,
                    'ma_cross',
                    baseParams,
                    paramRanges,
                    250,
                    60
                );
            }).toThrow('Data length insufficient');
        });
    });
});
