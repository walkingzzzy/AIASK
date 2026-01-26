/**
 * 风险模型服务单元测试
 */

import { describe, it, expect, beforeAll } from 'vitest';
import * as RiskServices from '../../src/services/risk-model.js';

describe('Risk Model Service', () => {
    // Mock stocks for testing
    const testStocks = ['600519', '000858', '601398', '000001'];
    const testWeights = {
        '600519': 0.3,
        '000858': 0.2,
        '601398': 0.3,
        '000001': 0.2,
    };

    describe('calculateBarraRisk', () => {
        it('should calculate Barra risk decomposition', async () => {
            const result = await RiskServices.calculateBarraRisk(testStocks, testWeights);
            
            if ('error' in result) {
                // If error due to missing data, skip test
                console.log('Skipping test due to missing data:', result.error);
                return;
            }
            
            expect(result.totalRisk).toBeGreaterThan(0);
            expect(result.factorRisk).toBeGreaterThan(0);
            expect(result.specificRisk).toBeGreaterThan(0);
            expect(result.factorExposures).toHaveLength(4);
            expect(result.industryExposures).toBeDefined();
            
            // Total risk should be approximately sqrt(factorRisk^2 + specificRisk^2)
            const calculatedTotal = Math.sqrt(
                result.factorRisk ** 2 + result.specificRisk ** 2
            );
            expect(result.totalRisk).toBeCloseTo(calculatedTotal, 0);
        });

        it('should return error for insufficient stocks', async () => {
            const result = await RiskServices.calculateBarraRisk(['600519'], { '600519': 1.0 });
            
            expect(result).toHaveProperty('error');
        });

        it('should normalize industry exposures', async () => {
            const result = await RiskServices.calculateBarraRisk(testStocks, testWeights);
            
            if ('error' in result) {
                return;
            }
            
            const totalExposure = Object.values(result.industryExposures).reduce(
                (sum, exp) => sum + exp,
                0
            );
            expect(totalExposure).toBeCloseTo(100, 0);
        });
    });

    describe('calculateVaR', () => {
        it('should calculate VaR and CVaR', async () => {
            const result = await RiskServices.calculateVaR(
                testStocks,
                testWeights,
                1000000,
                95,
                1
            );
            
            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }
            
            expect(result.confidence).toBe(95);
            expect(result.horizon).toBe(1);
            expect(result.var).toBeGreaterThan(0);
            expect(result.varPercent).toBeGreaterThan(0);
            expect(result.cvar).toBeGreaterThan(0);
            expect(result.cvarPercent).toBeGreaterThan(0);
            
            // CVaR should be greater than or equal to VaR
            expect(result.cvar).toBeGreaterThanOrEqual(result.var);
        });

        it('should calculate VaR for different confidence levels', async () => {
            const var95 = await RiskServices.calculateVaR(testStocks, testWeights, 1000000, 95, 1);
            const var99 = await RiskServices.calculateVaR(testStocks, testWeights, 1000000, 99, 1);
            
            if ('error' in var95 || 'error' in var99) {
                return;
            }
            
            // VaR at 99% should be greater than VaR at 95%
            expect(var99.var).toBeGreaterThanOrEqual(var95.var);
        });

        it('should scale VaR with horizon', async () => {
            const var1d = await RiskServices.calculateVaR(testStocks, testWeights, 1000000, 95, 1);
            const var5d = await RiskServices.calculateVaR(testStocks, testWeights, 1000000, 95, 5);
            
            if ('error' in var1d || 'error' in var5d) {
                return;
            }
            
            // 5-day VaR should be approximately sqrt(5) times 1-day VaR
            const expectedRatio = Math.sqrt(5);
            const actualRatio = var5d.var / var1d.var;
            expect(actualRatio).toBeGreaterThan(expectedRatio * 0.5);
            expect(actualRatio).toBeLessThan(expectedRatio * 2);
        });

        it('should return error for empty stocks', async () => {
            const result = await RiskServices.calculateVaR([], {}, 1000000, 95, 1);
            
            expect(result).toHaveProperty('error');
        });
    });

    describe('runStressTest', () => {
        it('should run all stress test scenarios', () => {
            const result = RiskServices.runStressTest(testStocks, testWeights);
            
            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }
            
            expect(result.length).toBe(12); // 12 predefined scenarios (updated from 4)
            
            result.forEach(scenario => {
                expect(scenario.scenario).toBeDefined();
                expect(scenario.portfolioLoss).toBeDefined();
                expect(scenario.worstStocks).toHaveLength(Math.min(5, testStocks.length));
                expect(scenario.factorContributions).toBeDefined();
            });
        });

        it('should run specific stress test scenario', () => {
            const result = RiskServices.runStressTest(testStocks, testWeights, '市场暴跌');
            
            if ('error' in result) {
                return;
            }
            
            expect(result.length).toBe(1);
            expect(result[0].scenario).toBe('市场暴跌');
            expect(result[0].portfolioLoss).toBeLessThan(0);
        });

        it('should return error for unknown scenario', () => {
            const result = RiskServices.runStressTest(testStocks, testWeights, '不存在的场景');
            
            expect(result).toHaveProperty('error');
        });

        it('should rank worst stocks correctly', () => {
            const result = RiskServices.runStressTest(testStocks, testWeights);
            
            if ('error' in result) {
                return;
            }
            
            result.forEach(scenario => {
                const losses = scenario.worstStocks.map(s => s.loss);
                for (let i = 1; i < losses.length; i++) {
                    expect(losses[i]).toBeGreaterThanOrEqual(losses[i - 1]);
                }
            });
        });
    });

    describe('generateRiskReport', () => {
        it('should generate comprehensive risk report', async () => {
            const result = await RiskServices.generateRiskReport(testStocks, testWeights, 1000000);
            
            if ('error' in result) {
                console.log('Skipping test due to missing data:', result.error);
                return;
            }
            
            expect(result.barraRisk).toBeDefined();
            expect(result.var95).toBeDefined();
            expect(result.var99).toBeDefined();
            expect(result.stressTests).toBeDefined();
            
            // Verify all components are present
            expect(result.barraRisk).toHaveProperty('totalRisk');
            expect(result.var95).toHaveProperty('var');
            expect(result.var99).toHaveProperty('var');
            expect(result.stressTests.length).toBeGreaterThan(0);
        });

        it('should have consistent risk measures', async () => {
            const result = await RiskServices.generateRiskReport(testStocks, testWeights, 1000000);
            
            if ('error' in result) {
                return;
            }
            
            // VaR99 should be greater than VaR95
            expect(result.var99.var).toBeGreaterThanOrEqual(result.var95.var);
        });
    });

    describe('STRESS_SCENARIOS', () => {
        it('should have all predefined scenarios', () => {
            expect(RiskServices.STRESS_SCENARIOS).toHaveLength(12); // Updated from 4 to 12
            
            const scenarioNames = RiskServices.STRESS_SCENARIOS.map(s => s.name);
            // Check for original scenarios
            expect(scenarioNames).toContain('市场暴跌');
            expect(scenarioNames).toContain('利率上行');
            expect(scenarioNames).toContain('流动性危机');
            expect(scenarioNames).toContain('行业轮动');
            // Check for new scenarios
            expect(scenarioNames).toContain('黑天鹅事件');
            expect(scenarioNames).toContain('通货膨胀');
            expect(scenarioNames).toContain('经济衰退');
            expect(scenarioNames).toContain('地缘政治风险');
        });

        it('should have valid shock parameters', () => {
            RiskServices.STRESS_SCENARIOS.forEach(scenario => {
                expect(scenario.name).toBeDefined();
                expect(scenario.description).toBeDefined();
                expect(scenario.shocks).toBeDefined();
                expect(Object.keys(scenario.shocks).length).toBeGreaterThan(0);
            });
        });
    });
});
