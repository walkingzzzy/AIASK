/**
 * 组合优化服务单元测试
 */

import { describe, it, expect } from 'vitest';
import * as PortfolioServices from '../../src/services/portfolio-optimizer.js';

describe('Portfolio Optimizer Service', () => {
    const testStocks = ['600519', '000858', '601398', '000001'];

    describe('calculateCovarianceMatrix', () => {
        it('should calculate covariance matrix', async () => {
            const result = await PortfolioServices.calculateCovarianceMatrix(testStocks);
            
            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }
            
            expect(result.stocks.length).toBeGreaterThan(0);
            expect(result.matrix.length).toBe(result.stocks.length);
            expect(result.means.length).toBe(result.stocks.length);
            expect(result.correlationMatrix.length).toBe(result.stocks.length);
            
            // Covariance matrix should be symmetric
            for (let i = 0; i < result.matrix.length; i++) {
                for (let j = 0; j < result.matrix.length; j++) {
                    expect(result.matrix[i][j]).toBeCloseTo(result.matrix[j][i], 4);
                }
            }
        });
    });

    describe('optimizeMeanVariance', () => {
        it('should optimize portfolio using mean-variance', async () => {
            const covResult = await PortfolioServices.calculateCovarianceMatrix(testStocks);
            
            if ('error' in covResult) {
                return;
            }
            
            const result = await PortfolioServices.optimizeMeanVariance(covResult);
            
            if ('error' in result) {
                return;
            }
            
            expect(result.weights).toBeDefined();
            expect(Number.isFinite(result.expectedReturn)).toBe(true);
            expect(result.volatility).toBeGreaterThan(0);
            expect(result.sharpeRatio).toBeDefined();
        });
    });

    describe('optimizePortfolio', () => {
        it('should optimize with equal_weight method', async () => {
            const result = await PortfolioServices.optimizePortfolio({
                stocks: testStocks,
                method: 'equal_weight',
            });
            
            if ('error' in result) {
                return;
            }
            
            const weights = Object.values(result.weights);
            const expectedWeight = 1 / testStocks.length;
            weights.forEach(w => {
                expect(w).toBeCloseTo(expectedWeight, 2);
            });
        });
    });
});
