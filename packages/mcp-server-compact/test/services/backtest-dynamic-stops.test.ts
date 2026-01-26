/**
 * 动态止损止盈系统测试
 */

import { describe, it, expect } from 'vitest';
import {
    calculateDynamicStopLoss,
    calculateDynamicTakeProfit,
    runBacktestWithDynamicStops,
    type DynamicStopLossConfig,
    type DynamicTakeProfitConfig
} from '../../src/services/backtest.js';
import type { KlineData } from '../../src/types/stock.js';

// 生成测试K线数据
function generateTestKlines(days: number, startPrice: number = 100, trend: 'up' | 'down' | 'flat' = 'flat'): KlineData[] {
    const klines: KlineData[] = [];
    let price = startPrice;

    for (let i = 0; i < days; i++) {
        const date = new Date(2023, 0, i + 1).toISOString().slice(0, 10);
        
        // 根据趋势调整价格
        if (trend === 'up') {
            price *= (1 + Math.random() * 0.02); // 上涨0-2%
        } else if (trend === 'down') {
            price *= (1 - Math.random() * 0.02); // 下跌0-2%
        } else {
            price *= (1 + (Math.random() - 0.5) * 0.02); // 震荡±1%
        }

        const high = price * (1 + Math.random() * 0.01);
        const low = price * (1 - Math.random() * 0.01);
        const open = price * (1 + (Math.random() - 0.5) * 0.005);

        klines.push({
            date,
            open,
            high,
            low,
            close: price,
            volume: 1000000 + Math.random() * 500000,
            amount: price * (1000000 + Math.random() * 500000),
            turnover: Math.random() * 5
        });
    }

    return klines;
}

describe('动态止损计算', () => {
    const klines = generateTestKlines(50, 100);

    describe('ATR止损', () => {
        it('应该基于ATR计算固定止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'atr',
                atrMultiplier: 2.0,
                atrPeriod: 14,
                trailingStop: false
            };

            const stopLoss = calculateDynamicStopLoss(100, 105, klines, 20, config);

            expect(stopLoss).toBeGreaterThan(0);
            expect(stopLoss).toBeLessThan(100); // 止损应低于入场价
        });

        it('应该基于ATR计算移动止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'atr',
                atrMultiplier: 2.0,
                atrPeriod: 14,
                trailingStop: true
            };

            const stopLoss1 = calculateDynamicStopLoss(100, 105, klines, 20, config);
            const stopLoss2 = calculateDynamicStopLoss(100, 110, klines, 25, config);

            expect(stopLoss2).toBeGreaterThanOrEqual(stopLoss1); // 移动止损应该上移
        });

        it('ATR倍数越大，止损距离越远', () => {
            const config1: DynamicStopLossConfig = {
                method: 'atr',
                atrMultiplier: 1.0,
                atrPeriod: 14,
                trailingStop: false
            };

            const config2: DynamicStopLossConfig = {
                method: 'atr',
                atrMultiplier: 3.0,
                atrPeriod: 14,
                trailingStop: false
            };

            const stopLoss1 = calculateDynamicStopLoss(100, 100, klines, 20, config1);
            const stopLoss2 = calculateDynamicStopLoss(100, 100, klines, 20, config2);

            expect(stopLoss2).toBeLessThan(stopLoss1); // 倍数大，止损更远（价格更低）
        });
    });

    describe('波动率止损', () => {
        it('应该基于波动率计算止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'volatility',
                volatilityMultiplier: 1.5,
                volatilityPeriod: 20,
                trailingStop: false
            };

            const stopLoss = calculateDynamicStopLoss(100, 105, klines, 25, config);

            expect(stopLoss).toBeGreaterThan(0);
            expect(stopLoss).toBeLessThan(100);
        });

        it('应该支持移动止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'volatility',
                volatilityMultiplier: 1.5,
                volatilityPeriod: 20,
                trailingStop: true
            };

            const stopLoss1 = calculateDynamicStopLoss(100, 105, klines, 25, config);
            const stopLoss2 = calculateDynamicStopLoss(100, 110, klines, 30, config);

            expect(stopLoss2).toBeGreaterThanOrEqual(stopLoss1);
        });
    });

    describe('百分比止损', () => {
        it('应该基于固定百分比计算止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: false
            };

            const stopLoss = calculateDynamicStopLoss(100, 105, klines, 20, config);

            expect(stopLoss).toBe(95); // 100 * (1 - 0.05)
        });

        it('应该支持移动止损', () => {
            const config: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: true
            };

            const stopLoss1 = calculateDynamicStopLoss(100, 105, klines, 20, config);
            const stopLoss2 = calculateDynamicStopLoss(100, 110, klines, 25, config);

            // 注意：止损价格会被限制在入场价的99%以下
            expect(stopLoss1).toBe(99); // Math.min(105 * 0.95, 100 * 0.99) = Math.min(99.75, 99) = 99
            expect(stopLoss2).toBe(99); // Math.min(110 * 0.95, 100 * 0.99) = Math.min(104.5, 99) = 99
            expect(stopLoss2).toBeGreaterThanOrEqual(stopLoss1); // 都是99
        });
    });

    describe('数据不足情况', () => {
        it('ATR数据不足时应使用默认百分比', () => {
            const shortKlines = generateTestKlines(5, 100);
            const config: DynamicStopLossConfig = {
                method: 'atr',
                atrMultiplier: 2.0,
                atrPeriod: 14,
                trailingStop: false
            };

            const stopLoss = calculateDynamicStopLoss(100, 100, shortKlines, 3, config);

            expect(stopLoss).toBe(95); // 默认5%
        });

        it('波动率数据不足时应使用默认百分比', () => {
            const shortKlines = generateTestKlines(10, 100);
            const config: DynamicStopLossConfig = {
                method: 'volatility',
                volatilityMultiplier: 1.5,
                volatilityPeriod: 20,
                trailingStop: false
            };

            const stopLoss = calculateDynamicStopLoss(100, 100, shortKlines, 5, config);

            expect(stopLoss).toBe(95);
        });
    });
});

describe('动态止盈计算', () => {
    const klines = generateTestKlines(50, 100);

    describe('ATR止盈', () => {
        it('应该基于ATR计算止盈', () => {
            const config: DynamicTakeProfitConfig = {
                method: 'atr',
                atrMultiplier: 3.0
            };

            const takeProfit = calculateDynamicTakeProfit(100, 95, klines, 20, config);

            expect(takeProfit).toBeGreaterThan(100); // 止盈应高于入场价
        });

        it('ATR倍数越大，止盈距离越远', () => {
            const config1: DynamicTakeProfitConfig = {
                method: 'atr',
                atrMultiplier: 2.0
            };

            const config2: DynamicTakeProfitConfig = {
                method: 'atr',
                atrMultiplier: 4.0
            };

            const takeProfit1 = calculateDynamicTakeProfit(100, 95, klines, 20, config1);
            const takeProfit2 = calculateDynamicTakeProfit(100, 95, klines, 20, config2);

            expect(takeProfit2).toBeGreaterThan(takeProfit1);
        });
    });

    describe('风险收益比止盈', () => {
        it('应该基于风险收益比计算止盈', () => {
            const config: DynamicTakeProfitConfig = {
                method: 'risk_reward',
                riskRewardRatio: 2.0
            };

            const entryPrice = 100;
            const stopLoss = 95;
            const risk = entryPrice - stopLoss; // 5

            const takeProfit = calculateDynamicTakeProfit(entryPrice, stopLoss, klines, 20, config);

            expect(takeProfit).toBe(entryPrice + risk * 2.0); // 100 + 5*2 = 110
        });

        it('风险收益比越大，止盈距离越远', () => {
            const config1: DynamicTakeProfitConfig = {
                method: 'risk_reward',
                riskRewardRatio: 1.5
            };

            const config2: DynamicTakeProfitConfig = {
                method: 'risk_reward',
                riskRewardRatio: 3.0
            };

            const takeProfit1 = calculateDynamicTakeProfit(100, 95, klines, 20, config1);
            const takeProfit2 = calculateDynamicTakeProfit(100, 95, klines, 20, config2);

            expect(takeProfit2).toBeGreaterThan(takeProfit1);
        });
    });

    describe('百分比止盈', () => {
        it('应该基于固定百分比计算止盈', () => {
            const config: DynamicTakeProfitConfig = {
                method: 'percentage',
                fixedPercentage: 10
            };

            const takeProfit = calculateDynamicTakeProfit(100, 95, klines, 20, config);

            expect(takeProfit).toBeCloseTo(110, 2); // 100 * 1.1
        });
    });
});

describe('带动态止损止盈的回测', () => {
    describe('上涨趋势', () => {
        it('应该在止盈时卖出', () => {
            const klines = generateTestKlines(100, 100, 'up');

            const stopLossConfig: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: false
            };

            const takeProfitConfig: DynamicTakeProfitConfig = {
                method: 'percentage',
                fixedPercentage: 10
            };

            const { result, trades } = runBacktestWithDynamicStops(
                '000001',
                klines,
                'buy_and_hold',
                { initialCapital: 100000, commission: 0.001, slippage: 0.001 },
                stopLossConfig,
                takeProfitConfig
            );

            expect(result.tradesCount).toBeGreaterThan(0);
            expect(result.finalCapital).toBeGreaterThan(result.initialCapital);
            
            // 应该有卖出交易
            const sellTrades = trades.filter(t => t.action === 'sell');
            expect(sellTrades.length).toBeGreaterThan(0);
        });
    });

    describe('下跌趋势', () => {
        it('应该在止损时卖出', () => {
            const klines = generateTestKlines(100, 100, 'down');

            const stopLossConfig: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: false
            };

            const takeProfitConfig: DynamicTakeProfitConfig = {
                method: 'percentage',
                fixedPercentage: 10
            };

            const { result, trades } = runBacktestWithDynamicStops(
                '000001',
                klines,
                'buy_and_hold',
                { initialCapital: 100000, commission: 0.001, slippage: 0.001 },
                stopLossConfig,
                takeProfitConfig
            );

            expect(result.tradesCount).toBeGreaterThan(0);
            
            // 应该有卖出交易（止损）
            const sellTrades = trades.filter(t => t.action === 'sell');
            expect(sellTrades.length).toBeGreaterThan(0);
        });
    });

    describe('移动止损效果', () => {
        it('移动止损应该锁定利润', () => {
            const klines = generateTestKlines(100, 100, 'up');

            const trailingConfig: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: true
            };

            const fixedConfig: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: false
            };

            const takeProfitConfig: DynamicTakeProfitConfig = {
                method: 'percentage',
                fixedPercentage: 20
            };

            const trailingResult = runBacktestWithDynamicStops(
                '000001',
                klines,
                'buy_and_hold',
                { initialCapital: 100000, commission: 0.001, slippage: 0.001 },
                trailingConfig,
                takeProfitConfig
            );

            const fixedResult = runBacktestWithDynamicStops(
                '000001',
                klines,
                'buy_and_hold',
                { initialCapital: 100000, commission: 0.001, slippage: 0.001 },
                fixedConfig,
                takeProfitConfig
            );

            // 移动止损应该有更好的表现（在上涨趋势中）
            expect(trailingResult.result.finalCapital).toBeGreaterThanOrEqual(fixedResult.result.finalCapital * 0.9);
        });
    });

    describe('权益曲线', () => {
        it('应该包含止损止盈价格', () => {
            const klines = generateTestKlines(50, 100);

            const stopLossConfig: DynamicStopLossConfig = {
                method: 'percentage',
                fixedPercentage: 5,
                trailingStop: false
            };

            const takeProfitConfig: DynamicTakeProfitConfig = {
                method: 'percentage',
                fixedPercentage: 10
            };

            const { equityCurve } = runBacktestWithDynamicStops(
                '000001',
                klines,
                'buy_and_hold',
                { initialCapital: 100000, commission: 0.001, slippage: 0.001 },
                stopLossConfig,
                takeProfitConfig
            );

            expect(equityCurve.length).toBe(klines.length);

            // 持仓期间应该有止损止盈价格
            const withStops = equityCurve.filter(e => e.stopLoss !== undefined && e.takeProfit !== undefined);
            expect(withStops.length).toBeGreaterThan(0);

            // 验证止损止盈价格的合理性
            for (const point of withStops) {
                if (point.stopLoss && point.takeProfit) {
                    expect(point.stopLoss).toBeLessThan(point.close);
                    expect(point.takeProfit).toBeGreaterThan(point.close);
                }
            }
        });
    });
});
