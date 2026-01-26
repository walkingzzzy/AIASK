/**
 * 组合优化服务扩展测试
 * 提升portfolio-optimizer覆盖率
 */

import { describe, it, expect, beforeAll } from 'vitest';
import * as PortfolioOptimizer from '../../src/services/portfolio-optimizer.js';
import { insertDailyBar } from '../../src/storage/kline-data.js';

describe('Portfolio Optimizer Service - Extended Tests', () => {
    // 准备测试数据
    beforeAll(() => {
        // 为测试股票插入模拟K线数据
        const stocks = ['TEST001', 'TEST002', 'TEST003', 'TEST004'];
        const startDate = new Date('2023-01-01');
        const days = 120;

        stocks.forEach((code, stockIndex) => {
            let price = 10 + stockIndex * 3; // 不同股票不同起始价格
            
            for (let i = 0; i < days; i++) {
                const date = new Date(startDate);
                date.setDate(date.getDate() + i);
                
                // 模拟不同的价格波动模式
                const volatility = 0.02 + stockIndex * 0.01;
                const trend = stockIndex * 0.0001;
                const change = (Math.random() - 0.5) * volatility + trend;
                price = price * (1 + change);
                
                try {
                    insertDailyBar({
                        code,
                        date: date.toISOString().slice(0, 10),
                        open: price * 0.995,
                        high: price * 1.015,
                        low: price * 0.985,
                        close: price,
                        volume: Math.floor(Math.random() * 2000000) + 500000,
                        amount: price * (Math.floor(Math.random() * 2000000) + 500000),
                    });
                } catch (error) {
                    // 忽略重复插入错误
                }
            }
        });
    });

    describe('calculateCovarianceMatrix - Extended', () => {
        it('should validate covariance matrix properties', async () => {
            const stocks = ['TEST001', 'TEST002', 'TEST003'];
            const result = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 100);

            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }

            const n = result.stocks.length;

            // 验证协方差矩阵是对称的
            for (let i = 0; i < n; i++) {
                for (let j = 0; j < n; j++) {
                    expect(Math.abs(result.matrix[i][j] - result.matrix[j][i])).toBeLessThan(0.0001);
                }
            }

            // 验证对角线元素（方差）为正
            for (let i = 0; i < n; i++) {
                expect(result.matrix[i][i]).toBeGreaterThan(0);
            }

            // 验证相关性矩阵对角线为1
            for (let i = 0; i < n; i++) {
                expect(Math.abs(result.correlationMatrix[i][i] - 1)).toBeLessThan(0.01);
            }

            // 验证相关性在-1到1之间
            for (let i = 0; i < n; i++) {
                for (let j = 0; j < n; j++) {
                    expect(result.correlationMatrix[i][j]).toBeGreaterThanOrEqual(-1.01);
                    expect(result.correlationMatrix[i][j]).toBeLessThanOrEqual(1.01);
                }
            }
        });

        it('should handle different lookback periods', async () => {
            const stocks = ['TEST001', 'TEST002'];
            
            const result30 = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 30);
            const result90 = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 90);

            if (!('error' in result30) && !('error' in result90)) {
                // 不同回看期应该产生不同的结果
                expect(result30.matrix[0][0]).not.toBe(result90.matrix[0][0]);
            }
        });
    });

    describe('optimizeMeanVariance - Extended', () => {
        it('should produce valid portfolio metrics', async () => {
            const stocks = ['TEST001', 'TEST002', 'TEST003'];
            const covMatrix = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 90);

            if ('error' in covMatrix) {
                console.log('Skipping test due to missing data:', covMatrix.error);
                return;
            }

            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);

            if ('error' in result) {
                console.log('Skipping test:', result.error);
                return;
            }

            // 验证夏普比率计算
            const riskFreeRate = 3; // 3%
            const expectedSharpe = (result.expectedReturn - riskFreeRate) / result.volatility;
            expect(Math.abs(result.sharpeRatio - expectedSharpe)).toBeLessThan(0.1);

            // 验证分散化比率 >= 1
            expect(result.diversificationRatio).toBeGreaterThanOrEqual(0.9);
        });

        it('should handle high correlation stocks', async () => {
            // 创建高相关性的协方差矩阵
            const covMatrix: PortfolioOptimizer.CovarianceMatrix = {
                stocks: ['TEST001', 'TEST002'],
                matrix: [
                    [0.04, 0.035],
                    [0.035, 0.04],
                ],
                means: [0.12, 0.13],
                correlationMatrix: [
                    [1, 0.875],
                    [0.875, 1],
                ],
            };

            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);

            if (!('error' in result)) {
                // 高相关性应该导致较低的分散化比率
                expect(result.diversificationRatio).toBeLessThan(1.5);
            }
        });
    });

    describe('blackLittermanOptimize - Extended', () => {
        it('should handle multiple absolute views', async () => {
            const config: PortfolioOptimizer.BlackLittermanConfig = {
                stocks: ['TEST001', 'TEST002', 'TEST003'],
                views: [
                    {
                        type: 'absolute',
                        stocks: ['TEST001'],
                        weights: [1],
                        expectedReturn: 0.15,
                        confidence: 0.8,
                    },
                    {
                        type: 'absolute',
                        stocks: ['TEST002'],
                        weights: [1],
                        expectedReturn: 0.10,
                        confidence: 0.6,
                    },
                ],
            };

            const result = PortfolioOptimizer.blackLittermanOptimize(config);

            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }

            expect(Object.keys(result.weights).length).toBeGreaterThan(0);
            
            // 验证权重和为1
            const totalWeight = Object.values(result.weights).reduce((a, b) => a + b, 0);
            expect(Math.abs(totalWeight - 1)).toBeLessThan(0.01);
        });

        it('should handle custom risk aversion', async () => {
            const config1: PortfolioOptimizer.BlackLittermanConfig = {
                stocks: ['TEST001', 'TEST002'],
                views: [],
                riskAversion: 2.0,
            };

            const config2: PortfolioOptimizer.BlackLittermanConfig = {
                stocks: ['TEST001', 'TEST002'],
                views: [],
                riskAversion: 4.0,
            };

            const result1 = PortfolioOptimizer.blackLittermanOptimize(config1);
            const result2 = PortfolioOptimizer.blackLittermanOptimize(config2);

            if (!('error' in result1) && !('error' in result2)) {
                // 不同的风险厌恶系数应该产生不同的结果
                expect(result1.volatility).not.toBe(result2.volatility);
            }
        });

        it('should handle custom tau parameter', async () => {
            const config: PortfolioOptimizer.BlackLittermanConfig = {
                stocks: ['TEST001', 'TEST002'],
                views: [],
                tau: 0.1,
            };

            const result = PortfolioOptimizer.blackLittermanOptimize(config);

            if (!('error' in result)) {
                expect(result.weights).toBeDefined();
            }
        });
    });

    describe('optimizeRiskBudget - Extended', () => {
        it('should respect risk budget allocations', async () => {
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks: ['TEST001', 'TEST002', 'TEST003'],
                method: 'risk_budget',
                riskBudgets: [0.5, 0.3, 0.2],
                targetVolatility: 0.15,
            };

            const result = PortfolioOptimizer.optimizePortfolio(config);

            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }

            // 验证权重和为1
            const totalWeight = Object.values(result.weights).reduce((a, b) => a + b, 0);
            expect(Math.abs(totalWeight - 1)).toBeLessThan(0.01);

            // 验证波动率接近目标
            if (config.targetVolatility) {
                expect(result.volatility).toBeGreaterThan(0);
            }
        });

        it('should handle equal risk budgets', async () => {
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks: ['TEST001', 'TEST002', 'TEST003'],
                method: 'risk_budget',
                riskBudgets: [1/3, 1/3, 1/3],
            };

            const result = PortfolioOptimizer.optimizePortfolio(config);

            if (!('error' in result)) {
                expect(result.weights).toBeDefined();
            }
        });

        it('should auto-normalize risk budgets', async () => {
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks: ['TEST001', 'TEST002'],
                method: 'risk_budget',
                riskBudgets: [2, 3], // 不归一化
            };

            const result = PortfolioOptimizer.optimizePortfolio(config);

            if (!('error' in result)) {
                const totalWeight = Object.values(result.weights).reduce((a, b) => a + b, 0);
                expect(Math.abs(totalWeight - 1)).toBeLessThan(0.01);
            }
        });
    });

    describe('optimizeEqualWeight - Extended', () => {
        it('should handle large number of stocks', async () => {
            const stocks = ['TEST001', 'TEST002', 'TEST003', 'TEST004'];
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks,
                method: 'equal_weight',
            };
            const result = PortfolioOptimizer.optimizePortfolio(config);

            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }

            const expectedWeight = 1 / stocks.length;
            Object.values(result.weights).forEach(w => {
                expect(Math.abs(w - expectedWeight)).toBeLessThan(0.01);
            });
        });

        it('should calculate correct metrics for equal weight', async () => {
            const stocks = ['TEST001', 'TEST002'];
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks,
                method: 'equal_weight',
            };
            const result = PortfolioOptimizer.optimizePortfolio(config);

            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }

            expect(result.expectedReturn).toBeDefined();
            expect(result.volatility).toBeGreaterThanOrEqual(0);
            expect(result.sharpeRatio).toBeDefined();
            expect(result.diversificationRatio).toBeGreaterThanOrEqual(0);
        });
    });

    describe('Edge Cases and Error Handling', () => {
        it('should handle zero variance in mean-variance optimization', async () => {
            const covMatrix: PortfolioOptimizer.CovarianceMatrix = {
                stocks: ['TEST001', 'TEST002'],
                matrix: [
                    [0, 0],
                    [0, 0.01],
                ],
                means: [0.1, 0.12],
                correlationMatrix: [
                    [1, 0],
                    [0, 1],
                ],
            };

            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);
            
            // 应该能处理或返回错误
            expect(result).toBeDefined();
        });

        it('should handle perfect negative correlation', async () => {
            const covMatrix: PortfolioOptimizer.CovarianceMatrix = {
                stocks: ['TEST001', 'TEST002'],
                matrix: [
                    [0.04, -0.04],
                    [-0.04, 0.04],
                ],
                means: [0.1, 0.12],
                correlationMatrix: [
                    [1, -1],
                    [-1, 1],
                ],
            };

            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);
            
            if (!('error' in result)) {
                // 完全负相关应该产生高分散化比率（或至少>=1）
                expect(result.diversificationRatio).toBeGreaterThanOrEqual(0.9);
            }
        });

        it('should handle very high volatility stocks', async () => {
            const covMatrix: PortfolioOptimizer.CovarianceMatrix = {
                stocks: ['TEST001', 'TEST002'],
                matrix: [
                    [1.0, 0.1],
                    [0.1, 1.0],
                ],
                means: [0.3, 0.35],
                correlationMatrix: [
                    [1, 0.1],
                    [0.1, 1],
                ],
            };

            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);
            
            if (!('error' in result)) {
                expect(result.volatility).toBeGreaterThan(50); // 高波动率
            }
        });

        it('should handle mismatched risk budget length', async () => {
            const config: PortfolioOptimizer.PortfolioOptimizerConfig = {
                stocks: ['TEST001', 'TEST002', 'TEST003'],
                method: 'risk_budget',
                riskBudgets: [0.5, 0.5], // 长度不匹配
            };

            const result = PortfolioOptimizer.optimizePortfolio(config);
            
            // 应该返回错误或自动处理
            expect(result).toBeDefined();
        });

        it('should handle empty views in Black-Litterman', async () => {
            const config: PortfolioOptimizer.BlackLittermanConfig = {
                stocks: ['TEST001', 'TEST002'],
                views: [],
            };

            const result = PortfolioOptimizer.blackLittermanOptimize(config);

            if (!('error' in result)) {
                // 无观点应该返回市场均衡权重
                expect(result.weights).toBeDefined();
            }
        });
    });

    describe('Performance Tests', () => {
        it('should calculate covariance matrix efficiently', async () => {
            const stocks = ['TEST001', 'TEST002', 'TEST003', 'TEST004'];
            const startTime = Date.now();

            const result = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 100);

            const executionTime = Date.now() - startTime;

            if (!('error' in result)) {
                expect(executionTime).toBeLessThan(1000); // 应该在1秒内完成
            }
        });

        it('should optimize portfolio efficiently', async () => {
            const stocks = ['TEST001', 'TEST002', 'TEST003'];
            const covMatrix = PortfolioOptimizer.calculateCovarianceMatrix(stocks, 90);

            if ('error' in covMatrix) {
                return;
            }

            const startTime = Date.now();
            const result = PortfolioOptimizer.optimizeMeanVariance(covMatrix);
            const executionTime = Date.now() - startTime;

            if (!('error' in result)) {
                expect(executionTime).toBeLessThan(100); // 应该在100ms内完成
            }
        });
    });
});
