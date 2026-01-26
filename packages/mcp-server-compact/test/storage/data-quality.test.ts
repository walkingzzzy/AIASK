/**
 * 数据质量模块测试
 */

import { describe, it, expect } from 'vitest';
import {
    validateNumericData,
    validateDateData,
    validateStockCode,
    validateBatchData,
    detectOutliers,
    checkDataCompleteness,
    interpolateMissingValues,
    forwardFill,
    removeOutliers,
    smoothData
} from '../../src/storage/data-quality.js';

describe('Data Quality Module', () => {
    describe('validateNumericData', () => {
        it('should validate valid numbers', () => {
            const result = validateNumericData(100, 'price');
            expect(result.valid).toBe(true);
            expect(result.error).toBeUndefined();
        });

        it('should reject null/undefined', () => {
            expect(validateNumericData(null, 'price').valid).toBe(false);
            expect(validateNumericData(undefined, 'price').valid).toBe(false);
        });

        it('should reject non-finite numbers', () => {
            expect(validateNumericData(NaN, 'price').valid).toBe(false);
            expect(validateNumericData(Infinity, 'price').valid).toBe(false);
        });

        it('should check min/max bounds', () => {
            expect(validateNumericData(50, 'price', { min: 0, max: 100 }).valid).toBe(true);
            expect(validateNumericData(-10, 'price', { min: 0 }).valid).toBe(false);
            expect(validateNumericData(150, 'price', { max: 100 }).valid).toBe(false);
        });

        it('should check zero and negative', () => {
            expect(validateNumericData(0, 'price', { allowZero: false }).valid).toBe(false);
            expect(validateNumericData(-5, 'price', { allowNegative: false }).valid).toBe(false);
            expect(validateNumericData(0, 'price', { allowZero: true }).valid).toBe(true);
        });
    });

    describe('validateDateData', () => {
        it('should validate valid dates', () => {
            const result = validateDateData('2024-01-01', 'date');
            expect(result.valid).toBe(true);
        });

        it('should reject invalid dates', () => {
            expect(validateDateData('invalid', 'date').valid).toBe(false);
            expect(validateDateData('', 'date').valid).toBe(false);
        });

        it('should check future dates', () => {
            const futureDate = new Date();
            futureDate.setFullYear(futureDate.getFullYear() + 1);
            expect(validateDateData(futureDate.toISOString(), 'date', { allowFuture: false }).valid).toBe(false);
            expect(validateDateData(futureDate.toISOString(), 'date', { allowFuture: true }).valid).toBe(true);
        });
    });

    describe('validateStockCode', () => {
        it('should validate valid stock codes', () => {
            expect(validateStockCode('600519').valid).toBe(true);
            expect(validateStockCode('000001').valid).toBe(true);
            expect(validateStockCode('300750').valid).toBe(true);
        });

        it('should reject invalid codes', () => {
            expect(validateStockCode('12345').valid).toBe(false); // Too short
            expect(validateStockCode('1234567').valid).toBe(false); // Too long
            expect(validateStockCode('ABC123').valid).toBe(false); // Contains letters
            expect(validateStockCode(123456).valid).toBe(false); // Not a string
        });
    });

    describe('validateBatchData', () => {
        it('should validate batch of data', () => {
            const data = [
                { code: '600519', price: 100 },
                { code: '000001', price: 200 },
                { code: 'INVALID', price: 300 }
            ];
            
            const result = validateBatchData(data, (item) => validateStockCode(item.code));
            
            expect(result.valid.length).toBe(2);
            expect(result.invalid.length).toBe(1);
            expect(result.stats.validityRate).toBeCloseTo(2/3);
        });

        it('should handle empty array', () => {
            const result = validateBatchData([], () => ({ valid: true }));
            expect(result.stats.validityRate).toBe(0);
        });
    });

    describe('detectOutliers', () => {
        it('should detect outliers using IQR method', () => {
            const values = [1, 2, 3, 4, 5, 100]; // 100 is outlier
            const result = detectOutliers(values);
            
            expect(result.outliers.length).toBeGreaterThan(0);
            expect(result.outliers).toContain(100);
        });

        it('should handle small datasets', () => {
            const values = [1, 2];
            const result = detectOutliers(values);
            expect(result.outliers.length).toBe(0);
        });

        it('should handle no outliers', () => {
            const values = [1, 2, 3, 4, 5];
            const result = detectOutliers(values);
            expect(result.outliers.length).toBe(0);
        });
    });

    describe('checkDataCompleteness', () => {
        it('should check for missing fields', () => {
            const data = [
                { name: 'A', value: 1, date: '2024-01-01' },
                { name: 'B', value: null, date: '2024-01-02' },
                { name: '', value: 3, date: '2024-01-03' }
            ];
            
            const result = checkDataCompleteness(data, ['name', 'value', 'date']);
            
            expect(result.complete.length).toBe(1);
            expect(result.incomplete.length).toBe(2);
            expect(result.completenessRate).toBeCloseTo(1/3);
        });
    });

    describe('interpolateMissingValues', () => {
        it('should interpolate missing values', () => {
            const data = [
                { date: '2024-01-01', value: 100 },
                { date: '2024-01-02', value: null },
                { date: '2024-01-03', value: 120 }
            ];
            
            const result = interpolateMissingValues(data);
            
            expect(result.length).toBe(3);
            expect(result[1].value).toBe(110); // Linear interpolation
        });

        it('should forward fill when no next value', () => {
            const data = [
                { date: '2024-01-01', value: 100 },
                { date: '2024-01-02', value: null }
            ];
            
            const result = interpolateMissingValues(data);
            expect(result[1].value).toBe(100);
        });
    });

    describe('forwardFill', () => {
        it('should forward fill missing values', () => {
            const data = [
                { name: 'A', value: 100 },
                { name: 'B', value: null },
                { name: 'C', value: null }
            ];
            
            const result = forwardFill(data, ['value']);
            
            expect(result[1].value).toBe(100);
            expect(result[2].value).toBe(100);
        });

        it('should handle multiple fields', () => {
            const data = [
                { a: 1, b: 2 },
                { a: null, b: null },
                { a: 3, b: null }
            ];
            
            const result = forwardFill(data, ['a', 'b']);
            
            expect(result[1].a).toBe(1);
            expect(result[1].b).toBe(2);
            expect(result[2].b).toBe(2);
        });
    });

    describe('removeOutliers', () => {
        it('should replace outliers with median', () => {
            const values = [1, 2, 3, 4, 5, 100];
            const result = removeOutliers(values, 'median');
            
            expect(result[5]).not.toBe(100);
            expect(result[5]).toBeCloseTo(3, 0);
        });

        it('should replace outliers with mean', () => {
            const values = [1, 2, 3, 4, 5, 100];
            const result = removeOutliers(values, 'mean');
            
            expect(result[5]).not.toBe(100);
            expect(result[5]).toBeGreaterThan(0);
        });

        it('should handle no outliers', () => {
            const values = [1, 2, 3, 4, 5];
            const result = removeOutliers(values);
            expect(result).toEqual(values);
        });
    });

    describe('smoothData', () => {
        it('should smooth data with moving average', () => {
            const values = [1, 10, 1, 10, 1];
            const result = smoothData(values, 3);
            
            expect(result.length).toBe(5);
            // Middle values should be smoothed
            expect(result[2]).toBeGreaterThan(1);
            expect(result[2]).toBeLessThan(10);
        });

        it('should handle small datasets', () => {
            const values = [1, 2];
            const result = smoothData(values, 5);
            expect(result).toEqual(values);
        });
    });
});
