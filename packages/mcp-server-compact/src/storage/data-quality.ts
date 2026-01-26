/**
 * 数据质量隔离记录
 */

import { timescaleDB } from './timescaledb.js';
import { logger } from '../logger.js';

export type DataQualityIssue = {
    dataset: string;
    code?: string;
    reason: string;
    source?: string;
    payload?: unknown;
};

export interface DataQualityStats {
    totalRecords: number;
    validRecords: number;
    invalidRecords: number;
    validityRate: number;
    issues: Array<{
        type: string;
        count: number;
        examples: string[];
    }>;
}

export async function recordDataQualityIssue(issue: DataQualityIssue): Promise<boolean> {
    try {
        await timescaleDB.recordDataQualityIssue(issue);
        logger.info('Data quality issue recorded', { 
            dataset: issue.dataset, 
            code: issue.code,
            reason: issue.reason 
        });
        return true;
    } catch (error) {
        logger.error('Failed to record data quality issue', { error });
        return false;
    }
}

/**
 * 验证数值数据
 */
export function validateNumericData(
    value: unknown,
    fieldName: string,
    options?: {
        min?: number;
        max?: number;
        allowZero?: boolean;
        allowNegative?: boolean;
    }
): { valid: boolean; error?: string } {
    if (value === null || value === undefined) {
        return { valid: false, error: `${fieldName} is null or undefined` };
    }

    const num = Number(value);
    if (!Number.isFinite(num)) {
        return { valid: false, error: `${fieldName} is not a finite number` };
    }

    if (!options?.allowZero && num === 0) {
        return { valid: false, error: `${fieldName} is zero` };
    }

    if (!options?.allowNegative && num < 0) {
        return { valid: false, error: `${fieldName} is negative` };
    }

    if (options?.min !== undefined && num < options.min) {
        return { valid: false, error: `${fieldName} is below minimum (${options.min})` };
    }

    if (options?.max !== undefined && num > options.max) {
        return { valid: false, error: `${fieldName} exceeds maximum (${options.max})` };
    }

    return { valid: true };
}

/**
 * 验证日期数据
 */
export function validateDateData(
    value: unknown,
    fieldName: string,
    options?: {
        minDate?: Date;
        maxDate?: Date;
        allowFuture?: boolean;
    }
): { valid: boolean; error?: string } {
    if (!value) {
        return { valid: false, error: `${fieldName} is empty` };
    }

    const date = new Date(value as string);
    if (isNaN(date.getTime())) {
        return { valid: false, error: `${fieldName} is not a valid date` };
    }

    const now = new Date();
    if (!options?.allowFuture && date > now) {
        return { valid: false, error: `${fieldName} is in the future` };
    }

    if (options?.minDate && date < options.minDate) {
        return { valid: false, error: `${fieldName} is before minimum date` };
    }

    if (options?.maxDate && date > options.maxDate) {
        return { valid: false, error: `${fieldName} is after maximum date` };
    }

    return { valid: true };
}

/**
 * 验证股票代码
 */
export function validateStockCode(code: unknown): { valid: boolean; error?: string } {
    if (typeof code !== 'string') {
        return { valid: false, error: 'Stock code must be a string' };
    }

    if (code.length !== 6) {
        return { valid: false, error: 'Stock code must be 6 characters' };
    }

    if (!/^\d{6}$/.test(code)) {
        return { valid: false, error: 'Stock code must contain only digits' };
    }

    return { valid: true };
}

/**
 * 批量验证数据
 */
export function validateBatchData<T>(
    data: T[],
    validator: (item: T) => { valid: boolean; error?: string }
): {
    valid: T[];
    invalid: Array<{ item: T; error: string }>;
    stats: {
        total: number;
        validCount: number;
        invalidCount: number;
        validityRate: number;
    };
} {
    const valid: T[] = [];
    const invalid: Array<{ item: T; error: string }> = [];

    for (const item of data) {
        const result = validator(item);
        if (result.valid) {
            valid.push(item);
        } else {
            invalid.push({ item, error: result.error || 'Unknown error' });
        }
    }

    return {
        valid,
        invalid,
        stats: {
            total: data.length,
            validCount: valid.length,
            invalidCount: invalid.length,
            validityRate: data.length > 0 ? valid.length / data.length : 0,
        },
    };
}

/**
 * 检测异常值（使用 IQR 方法）
 */
export function detectOutliers(
    values: number[],
    multiplier: number = 1.5
): {
    outliers: number[];
    outlierIndices: number[];
    lowerBound: number;
    upperBound: number;
} {
    if (values.length < 4) {
        return { outliers: [], outlierIndices: [], lowerBound: 0, upperBound: 0 };
    }

    const sorted = [...values].sort((a: any, b: any) => a - b);
    const q1Index = Math.floor(sorted.length * 0.25);
    const q3Index = Math.floor(sorted.length * 0.75);
    
    const q1 = sorted[q1Index];
    const q3 = sorted[q3Index];
    const iqr = q3 - q1;
    
    const lowerBound = q1 - multiplier * iqr;
    const upperBound = q3 + multiplier * iqr;
    
    const outliers: number[] = [];
    const outlierIndices: number[] = [];
    
    values.forEach((value: any, index: any) => {
        if (value < lowerBound || value > upperBound) {
            outliers.push(value);
            outlierIndices.push(index);
        }
    });
    
    return { outliers, outlierIndices, lowerBound, upperBound };
}

/**
 * 数据完整性检查
 */
export function checkDataCompleteness<T extends Record<string, any>>(
    data: T[],
    requiredFields: (keyof T)[]
): {
    complete: T[];
    incomplete: Array<{ item: T; missingFields: string[] }>;
    completenessRate: number;
} {
    const complete: T[] = [];
    const incomplete: Array<{ item: T; missingFields: string[] }> = [];

    for (const item of data) {
        const missingFields: string[] = [];
        
        for (const field of requiredFields) {
            const value = item[field];
            if (value === null || value === undefined || value === '') {
                missingFields.push(String(field));
            }
        }
        
        if (missingFields.length === 0) {
            complete.push(item);
        } else {
            incomplete.push({ item, missingFields });
        }
    }

    return {
        complete,
        incomplete,
        completenessRate: data.length > 0 ? complete.length / data.length : 0,
    };
}



/**
 * 数据修复：线性插值
 * 用于填补时间序列中的缺失值
 */
export function interpolateMissingValues(
    data: Array<{ date: string; value: number | null }>,
    field: string = 'value'
): Array<{ date: string; value: number }> {
    const result: Array<{ date: string; value: number }> = [];
    
    for (let i = 0; i < data.length; i++) {
        const current = data[i];
        
        if (current.value !== null && current.value !== undefined) {
            result.push({ date: current.date, value: current.value });
            continue;
        }
        
        // Find previous and next valid values
        let prevIndex = i - 1;
        while (prevIndex >= 0 && (data[prevIndex].value === null || data[prevIndex].value === undefined)) {
            prevIndex--;
        }
        
        let nextIndex = i + 1;
        while (nextIndex < data.length && (data[nextIndex].value === null || data[nextIndex].value === undefined)) {
            nextIndex++;
        }
        
        // Interpolate
        if (prevIndex >= 0 && nextIndex < data.length) {
            const prevValue = data[prevIndex].value!;
            const nextValue = data[nextIndex].value!;
            const steps = nextIndex - prevIndex;
            const currentStep = i - prevIndex;
            const interpolated = prevValue + (nextValue - prevValue) * (currentStep / steps);
            
            result.push({ date: current.date, value: interpolated });
            logger.info(`Interpolated missing value for ${current.date}: ${interpolated.toFixed(4)}`);
        } else if (prevIndex >= 0) {
            // Forward fill if no next value
            result.push({ date: current.date, value: data[prevIndex].value! });
            logger.info(`Forward filled missing value for ${current.date}`);
        } else if (nextIndex < data.length) {
            // Backward fill if no previous value
            result.push({ date: current.date, value: data[nextIndex].value! });
            logger.info(`Backward filled missing value for ${current.date}`);
        } else {
            // No valid values found, use 0 as fallback
            result.push({ date: current.date, value: 0 });
            logger.warn(`No valid values found for interpolation at ${current.date}, using 0`);
        }
    }
    
    return result;
}

/**
 * 数据修复：前向填充
 * 使用最近的有效值填充缺失值
 */
export function forwardFill<T extends Record<string, any>>(
    data: T[],
    fields: (keyof T)[]
): T[] {
    const result: T[] = [];
    const lastValid: Partial<T> = {};
    
    for (const item of data) {
        const filled = { ...item };
        
        for (const field of fields) {
            const value = item[field];
            
            if (value === null || value === undefined || value === '') {
                // Use last valid value if available
                if (lastValid[field] !== undefined) {
                    filled[field] = lastValid[field] as any;
                    logger.debug(`Forward filled ${String(field)} with last valid value`);
                }
            } else {
                // Update last valid value
                lastValid[field] = value;
            }
        }
        
        result.push(filled);
    }
    
    return result;
}

/**
 * 数据修复：移除异常值并替换
 * 使用中位数或平均值替换异常值
 */
export function removeOutliers(
    values: number[],
    method: 'median' | 'mean' = 'median',
    multiplier: number = 1.5
): number[] {
    const { outlierIndices, lowerBound, upperBound } = detectOutliers(values, multiplier);
    
    if (outlierIndices.length === 0) {
        return values;
    }
    
    // Calculate replacement value
    const validValues = values.filter((v, i) => !outlierIndices.includes(i));
    let replacement: number;
    
    if (method === 'median') {
        const sorted = [...validValues].sort((a, b) => a - b);
        replacement = sorted[Math.floor(sorted.length / 2)];
    } else {
        replacement = validValues.reduce((sum, v) => sum + v, 0) / validValues.length;
    }
    
    // Replace outliers
    const result = values.map((v, i) => {
        if (outlierIndices.includes(i)) {
            logger.info(`Replaced outlier ${v} with ${replacement} at index ${i}`);
            return replacement;
        }
        return v;
    });
    
    return result;
}

/**
 * 数据修复：平滑处理
 * 使用移动平均平滑数据
 */
export function smoothData(
    values: number[],
    windowSize: number = 3
): number[] {
    if (values.length < windowSize) {
        return values;
    }
    
    const result: number[] = [];
    const halfWindow = Math.floor(windowSize / 2);
    
    for (let i = 0; i < values.length; i++) {
        const start = Math.max(0, i - halfWindow);
        const end = Math.min(values.length, i + halfWindow + 1);
        const window = values.slice(start, end);
        const avg = window.reduce((sum, v) => sum + v, 0) / window.length;
        result.push(avg);
    }
    
    return result;
}

/**
 * 获取数据质量报告
 * Note: Requires timescaleDB methods getDataQualityIssues and getDatasetRecordCount to be implemented
 */
export async function getDataQualityReport(
    dataset: string,
    startDate?: Date,
    endDate?: Date
): Promise<DataQualityStats> {
    try {
        // TODO: Implement getDataQualityIssues and getDatasetRecordCount in timescaleDB
        // For now, return empty stats
        logger.warn('getDataQualityReport: timescaleDB methods not yet implemented');
        
        return {
            totalRecords: 0,
            validRecords: 0,
            invalidRecords: 0,
            validityRate: 1,
            issues: []
        };
    } catch (error) {
        logger.error('Failed to generate data quality report', { error });
        return {
            totalRecords: 0,
            validRecords: 0,
            invalidRecords: 0,
            validityRate: 0,
            issues: []
        };
    }
}
