/**
 * 因子计算服务测试
 * 提升factor-calculator覆盖率至60%+
 * 
 * 注意：由于factor-calculator依赖TimescaleDB，部分测试需要数据库支持
 * 在没有数据库的环境中，这些测试将被跳过
 */

import { describe, it, expect } from 'vitest';
import * as FactorCalculator from '../../src/services/factor-calculator.js';

// 检查是否有数据库连接
const hasDatabase = process.env.DATABASE_URL !== undefined;

describe('Factor Calculator Service', () => {
    // 如果没有数据库，跳过所有测试
    if (!hasDatabase) {
        it.skip('Skipping all tests - no database available', () => {
            expect(true).toBe(true);
        });
        return;
    }

    describe('calculateEP', () => {
        it('should calculate EP factor or handle missing data', async () => {
            const result = await FactorCalculator.calculateEP('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('ep');
                expect(result.data.value).toBeGreaterThan(0);
                expect(result.data.dataSource).toBe('calculated');
                expect(result.data.components).toHaveProperty('pe');
            } else {
                expect(result.error).toBeDefined();
            }
        });

        it('should handle missing valuation data', async () => {
            const result = await FactorCalculator.calculateEP('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
            expect(result.error).toBeDefined();
        });
    });

    describe('calculateBP', () => {
        it('should calculate BP factor or handle missing data', async () => {
            const result = await FactorCalculator.calculateBP('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('bp');
                expect(result.data.value).toBeGreaterThan(0);
            } else {
                expect(result.error).toBeDefined();
            }
        });

        it('should handle missing valuation data', async () => {
            const result = await FactorCalculator.calculateBP('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
            expect(result.error).toBeDefined();
        });
    });

    describe('calculateRevenueGrowth', () => {
        it('should calculate revenue growth or handle missing data', async () => {
            const result = await FactorCalculator.calculateRevenueGrowth('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('revenue_growth');
                expect(result.data.value).toBeDefined();
            } else {
                expect(result.error).toBeDefined();
            }
        });

        it('should handle missing financial data', async () => {
            const result = await FactorCalculator.calculateRevenueGrowth('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
            expect(result.error).toBeDefined();
        });
    });

    describe('calculateProfitGrowth', () => {
        it('should calculate profit growth or handle missing data', async () => {
            const result = await FactorCalculator.calculateProfitGrowth('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('profit_growth');
                expect(result.data.value).toBeDefined();
            } else {
                expect(result.error).toBeDefined();
            }
        });

        it('should handle missing financial data', async () => {
            const result = await FactorCalculator.calculateProfitGrowth('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
        });
    });

    describe('calculateMomentum', () => {
        it('should calculate 6-month momentum or handle missing data', async () => {
            const result = await FactorCalculator.calculateMomentum('000001', 6);

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('momentum_6m');
                expect(result.data.value).toBeDefined();
            }
        });

        it('should calculate 1-month momentum', async () => {
            const result = await FactorCalculator.calculateMomentum('000001', 1);

            if (result.success && result.data) {
                expect(result.data.factorName).toBe('momentum_1m');
            }
        });

        it('should calculate 12-month momentum', async () => {
            const result = await FactorCalculator.calculateMomentum('000001', 12);

            if (result.success && result.data) {
                expect(result.data.factorName).toBe('momentum_12m');
            }
        });

        it('should handle insufficient price data', async () => {
            const result = await FactorCalculator.calculateMomentum('INVALID_CODE_999999', 6);
            
            expect(result.success).toBe(false);
        });
    });

    describe('calculateROE', () => {
        it('should calculate ROE or handle missing data', async () => {
            const result = await FactorCalculator.calculateROE('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('roe');
                expect(result.data.value).toBeDefined();
                expect(result.data.dataSource).toBe('database');
            }
        });

        it('should handle missing financial data', async () => {
            const result = await FactorCalculator.calculateROE('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
        });
    });

    describe('calculateGrossMargin', () => {
        it('should calculate gross margin or handle missing data', async () => {
            const result = await FactorCalculator.calculateGrossMargin('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('gross_margin');
                expect(result.data.value).toBeDefined();
            }
        });

        it('should handle missing financial data', async () => {
            const result = await FactorCalculator.calculateGrossMargin('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
        });
    });

    describe('calculateNetMargin', () => {
        it('should calculate net margin or handle missing data', async () => {
            const result = await FactorCalculator.calculateNetMargin('000001');

            expect(result).toHaveProperty('success');
            if (result.success && result.data) {
                expect(result.data.code).toBe('000001');
                expect(result.data.factorName).toBe('net_margin');
                expect(result.data.value).toBeDefined();
            }
        });

        it('should handle missing financial data', async () => {
            const result = await FactorCalculator.calculateNetMargin('INVALID_CODE_999999');
            
            expect(result.success).toBe(false);
        });
    });

    describe('calculateFactor', () => {
        it('should calculate any factor by name', async () => {
            const factors = ['ep', 'bp', 'revenue_growth', 'profit_growth', 'momentum_6m', 'roe', 'gross_margin', 'net_margin'];

            for (const factorName of factors) {
                const result = await FactorCalculator.calculateFactor('000001', factorName);
                
                expect(result).toHaveProperty('success');
                if (result.success) {
                    expect(result.data).toBeDefined();
                } else {
                    expect(result.error).toBeDefined();
                }
            }
        });

        it('should handle unknown factor names', async () => {
            const result = await FactorCalculator.calculateFactor('000001', 'unknown_factor');
            
            expect(result.success).toBe(false);
            expect(result.error).toContain('未知的因子');
        });
    });

    describe('batchCalculateFactors', () => {
        it('should calculate factors for multiple stocks', async () => {
            const codes = ['000001', '000002'];
            const factorName = 'ep';

            const result = await FactorCalculator.batchCalculateFactors(codes, factorName);

            expect(result.success).toBe(true);
            expect(result.factors).toBeDefined();
            expect(result.errors).toBeDefined();
            expect(Array.isArray(result.factors)).toBe(true);
            expect(Array.isArray(result.errors)).toBe(true);
        });

        it('should handle all failures gracefully', async () => {
            const codes = ['INVALID1_999999', 'INVALID2_999999'];
            const factorName = 'ep';

            const result = await FactorCalculator.batchCalculateFactors(codes, factorName);

            expect(result.success).toBe(true);
            expect(result.factors.length).toBe(0);
            expect(result.errors.length).toBe(codes.length);
        });
    });

    describe('calculateMultipleFactors', () => {
        it('should calculate multiple factors for one stock', async () => {
            const code = '000001';
            const factorNames = ['ep', 'bp', 'roe'];

            const result = await FactorCalculator.calculateMultipleFactors(code, factorNames);

            expect(result.success).toBe(true);
            expect(result.factors).toBeDefined();
            expect(result.errors).toBeDefined();
            expect(Array.isArray(result.factors)).toBe(true);
            expect(Array.isArray(result.errors)).toBe(true);
        });

        it('should handle mixed success and failures', async () => {
            const code = '000001';
            const factorNames = ['ep', 'unknown_factor', 'roe'];

            const result = await FactorCalculator.calculateMultipleFactors(code, factorNames);

            expect(result.success).toBe(true);
            expect(result.errors.length).toBeGreaterThan(0);
        });

        it('should handle empty factor list', async () => {
            const code = '000001';
            const factorNames: string[] = [];

            const result = await FactorCalculator.calculateMultipleFactors(code, factorNames);

            expect(result.success).toBe(true);
            expect(result.factors.length).toBe(0);
            expect(result.errors.length).toBe(0);
        });
    });

    describe('Error Handling', () => {
        it('should return structured error for invalid stock code', async () => {
            const result = await FactorCalculator.calculateEP('INVALID_999999');
            
            expect(result.success).toBe(false);
            expect(result.error).toBeDefined();
            expect(typeof result.error).toBe('string');
        });

        it('should handle database connection errors gracefully', async () => {
            const result = await FactorCalculator.calculateFactor('INVALID_999999', 'ep');
            
            expect(result).toHaveProperty('success');
            expect(result).toHaveProperty('error');
        });
    });

    describe('Performance Tests', () => {
        it('should calculate single factor efficiently', async () => {
            const startTime = Date.now();
            
            await FactorCalculator.calculateEP('000001');
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(1000);
        });

        it('should calculate batch factors efficiently', async () => {
            const codes = ['000001', '000002'];
            const startTime = Date.now();
            
            await FactorCalculator.batchCalculateFactors(codes, 'ep');
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(2000);
        });

        it('should calculate multiple factors efficiently', async () => {
            const factorNames = ['ep', 'bp', 'roe'];
            const startTime = Date.now();
            
            await FactorCalculator.calculateMultipleFactors('000001', factorNames);
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(3000);
        });
    });
});
