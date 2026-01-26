/**
 * 因子分析框架测试
 */

import { describe, it, expect, vi } from 'vitest';
import {
    buildFactorMatrix,
    orthogonalizeFactors,
    calculateFactorCorrelation,
    type FactorMatrix
} from '../../src/services/factor-analysis.js';

// Mock因子计算函数
vi.mock('../../src/services/factor-calculator.js', () => ({
    calculateFactor: vi.fn((code: string, factorName: string) => {
        // 模拟因子值
        const factorValues: Record<string, Record<string, number>> = {
            '000001': { ep: 0.05, bp: 0.8, momentum_20d: 0.03, volatility: 0.25 },
            '600519': { ep: 0.02, bp: 0.3, momentum_20d: 0.10, volatility: 0.30 },
            '000858': { ep: 0.04, bp: 0.6, momentum_20d: -0.02, volatility: 0.28 }
        };

        const value = factorValues[code]?.[factorName];
        if (value !== undefined) {
            return Promise.resolve({
                success: true,
                data: {
                    code,
                    factorName,
                    value,
                    date: '2023-12-31',
                    dataSource: 'calculated' as const
                }
            });
        }

        return Promise.resolve({
            success: false,
            error: '因子数据不存在'
        });
    }),
    SUPPORTED_FACTORS: ['ep', 'bp', 'momentum_20d', 'volatility']
}));

describe('因子矩阵构建', () => {
    it('应该成功构建因子矩阵', async () => {
        const result = await buildFactorMatrix(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d', 'volatility']
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.stocks).toHaveLength(3);
        expect(result.factors).toHaveLength(4);
        expect(result.values).toHaveLength(3);
        expect(result.values[0]).toHaveLength(4);
    });

    it('空股票列表应返回错误', async () => {
        const result = await buildFactorMatrix([], ['ep', 'bp']);

        expect(result).toHaveProperty('error');
        if ('error' in result) {
            expect(result.error).toContain('股票列表为空');
        }
    });

    it('空因子列表应返回错误', async () => {
        const result = await buildFactorMatrix(['000001'], []);

        expect(result).toHaveProperty('error');
        if ('error' in result) {
            expect(result.error).toContain('因子列表为空');
        }
    });

    it('应该过滤掉无效数据的股票', async () => {
        const result = await buildFactorMatrix(
            ['000001', '600519', '000858', '999999'], // 999999不存在
            ['ep', 'bp']
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.stocks).toHaveLength(3); // 只有3只有效
        expect(result.stocks).not.toContain('999999');
    });
});

describe('Gram-Schmidt正交化', () => {
    it('应该成功正交化因子', async () => {
        const matrix = await buildFactorMatrix(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d', 'volatility']
        );

        if ('error' in matrix) {
            throw new Error('构建因子矩阵失败');
        }

        const result = orthogonalizeFactors(matrix);

        expect(result.original).toBe(matrix);
        expect(result.orthogonalized.stocks).toEqual(matrix.stocks);
        expect(result.orthogonalized.factors).toHaveLength(matrix.factors.length);
        expect(result.transformMatrix).toHaveLength(matrix.factors.length);
    });

    it('正交化后的因子应该相互正交', async () => {
        const matrix = await buildFactorMatrix(
            ['000001', '600519', '000858'],
            ['ep', 'bp']
        );

        if ('error' in matrix) {
            throw new Error('构建因子矩阵失败');
        }

        const result = orthogonalizeFactors(matrix);
        const orthValues = result.orthogonalized.values;

        // 提取两个正交因子
        const factor1 = orthValues.map(row => row[0]);
        const factor2 = orthValues.map(row => row[1]);

        // 计算点积（应该接近0）
        const dotProduct = factor1.reduce((sum, val, i) => sum + val * factor2[i], 0);

        expect(Math.abs(dotProduct)).toBeLessThan(0.01); // 允许小误差
    });

    it('正交化后的因子应该是单位向量', async () => {
        const matrix = await buildFactorMatrix(
            ['000001', '600519', '000858'],
            ['ep', 'bp']
        );

        if ('error' in matrix) {
            throw new Error('构建因子矩阵失败');
        }

        const result = orthogonalizeFactors(matrix);
        const orthValues = result.orthogonalized.values;

        // 检查每个因子的范数
        for (let j = 0; j < result.orthogonalized.factors.length; j++) {
            const factor = orthValues.map(row => row[j]);
            const norm = Math.sqrt(factor.reduce((sum, val) => sum + val * val, 0));

            expect(Math.abs(norm - 1.0)).toBeLessThan(0.01); // 应该接近1
        }
    });

    it('变换矩阵应该是上三角矩阵', async () => {
        const matrix = await buildFactorMatrix(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d']
        );

        if ('error' in matrix) {
            throw new Error('构建因子矩阵失败');
        }

        const result = orthogonalizeFactors(matrix);
        const transform = result.transformMatrix;

        // 检查下三角元素是否为0
        for (let i = 0; i < transform.length; i++) {
            for (let j = i + 1; j < transform[i].length; j++) {
                expect(transform[i][j]).toBe(0);
            }
        }
    });
});

describe('因子相关性分析', () => {
    it('应该计算因子相关性矩阵', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d', 'volatility'],
            0.7
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.factors).toHaveLength(4);
        expect(result.correlationMatrix).toHaveLength(4);
        expect(result.correlationMatrix[0]).toHaveLength(4);
    });

    it('对角线元素应该为1', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp'],
            0.7
        );

        if ('error' in result) {
            throw new Error('计算相关性失败');
        }

        expect(result.correlationMatrix[0][0]).toBe(1.0);
        expect(result.correlationMatrix[1][1]).toBe(1.0);
    });

    it('相关性矩阵应该对称', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d'],
            0.7
        );

        if ('error' in result) {
            throw new Error('计算相关性失败');
        }

        const matrix = result.correlationMatrix;

        for (let i = 0; i < matrix.length; i++) {
            for (let j = 0; j < matrix.length; j++) {
                expect(Math.abs(matrix[i][j] - matrix[j][i])).toBeLessThan(0.01);
            }
        }
    });

    it('应该识别高相关性因子对', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d', 'volatility'],
            0.5 // 降低阈值以便测试
        );

        if ('error' in result) {
            throw new Error('计算相关性失败');
        }

        expect(result.highlyCorrelated).toBeDefined();
        expect(Array.isArray(result.highlyCorrelated)).toBe(true);

        // 验证高相关因子对的格式
        for (const pair of result.highlyCorrelated) {
            expect(pair).toHaveProperty('factor1');
            expect(pair).toHaveProperty('factor2');
            expect(pair).toHaveProperty('correlation');
            expect(Math.abs(pair.correlation)).toBeGreaterThanOrEqual(0.5);
        }
    });

    it('高相关因子对应该按相关性降序排列', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d', 'volatility'],
            0.3
        );

        if ('error' in result) {
            throw new Error('计算相关性失败');
        }

        const correlations = result.highlyCorrelated.map(p => Math.abs(p.correlation));

        for (let i = 1; i < correlations.length; i++) {
            expect(correlations[i]).toBeLessThanOrEqual(correlations[i - 1]);
        }
    });

    it('相关性值应该在[-1, 1]范围内', async () => {
        const result = await calculateFactorCorrelation(
            ['000001', '600519', '000858'],
            ['ep', 'bp', 'momentum_20d'],
            0.7
        );

        if ('error' in result) {
            throw new Error('计算相关性失败');
        }

        const matrix = result.correlationMatrix;

        for (let i = 0; i < matrix.length; i++) {
            for (let j = 0; j < matrix.length; j++) {
                expect(matrix[i][j]).toBeGreaterThanOrEqual(-1);
                expect(matrix[i][j]).toBeLessThanOrEqual(1);
            }
        }
    });
});

describe('辅助函数测试', () => {
    describe('向量运算', () => {
        it('点积计算应该正确', () => {
            // 这些是内部函数，通过正交化结果间接测试
            const matrix: FactorMatrix = {
                stocks: ['A', 'B', 'C'],
                factors: ['f1', 'f2'],
                values: [
                    [1, 2],
                    [3, 4],
                    [5, 6]
                ],
                date: '2023-12-31'
            };

            const result = orthogonalizeFactors(matrix);

            // 验证正交化结果的合理性
            expect(result.orthogonalized.values).toHaveLength(3);
            expect(result.orthogonalized.values[0]).toHaveLength(2);
        });
    });

    describe('Spearman相关系数', () => {
        it('完全正相关应该接近1', async () => {
            // 通过相关性分析间接测试
            const result = await calculateFactorCorrelation(
                ['000001', '600519', '000858'],
                ['ep', 'bp'],
                0.5
            );

            if ('error' in result) return;

            // 自相关应该为1
            expect(result.correlationMatrix[0][0]).toBe(1.0);
            expect(result.correlationMatrix[1][1]).toBe(1.0);
        });
    });
});

describe('边界情况', () => {
    it('单个股票应该能构建矩阵', async () => {
        const result = await buildFactorMatrix(
            ['000001'],
            ['ep', 'bp']
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.stocks).toHaveLength(1);
        expect(result.values).toHaveLength(1);
    });

    it('单个因子应该能构建矩阵', async () => {
        const result = await buildFactorMatrix(
            ['000001', '600519'],
            ['ep']
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.factors).toHaveLength(1);
        expect(result.values[0]).toHaveLength(1);
    });

    it('大量股票应该能正常处理', async () => {
        const stocks = Array.from({ length: 100 }, (_, i) => `00000${i % 3 + 1}`);

        const result = await buildFactorMatrix(
            stocks,
            ['ep', 'bp']
        );

        expect(result).not.toHaveProperty('error');
        if ('error' in result) return;

        expect(result.stocks.length).toBeGreaterThan(0);
    });
});
