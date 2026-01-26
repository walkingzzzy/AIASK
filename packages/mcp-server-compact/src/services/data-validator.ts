/**
 * 数据校验服务
 * 提供数据完整性、一致性、时效性校验
 * 
 * 数据质量保证核心模块
 */

import { DATA_VALIDATION } from '../config/constants.js';
import type { RealtimeQuote, KlineData, NorthFund, SectorData } from '../types/stock.js';

export interface ValidationResult {
    valid: boolean;
    errors: string[];
    warnings: string[];
}

export interface DataQualityScore {
    overall: number;
    completeness: number;
    accuracy: number;
    timeliness: number;
    consistency: number;
}

function isFiniteNumber(value: number): boolean {
    return typeof value === 'number' && Number.isFinite(value);
}

function ensureFinite(value: number, field: string, errors: string[]): boolean {
    if (!isFiniteNumber(value)) {
        errors.push(`${field}缺失或非数值`);
        return false;
    }
    return true;
}

/**
 * 数据校验器
 */
export class DataValidator {
    /**
     * 校验实时行情数据
     */
    validateQuote(quote: RealtimeQuote): ValidationResult {
        const errors: string[] = [];
        const warnings: string[] = [];

        // 必填字段检查
        if (!quote.code) errors.push('股票代码缺失');
        if (!quote.name) warnings.push('股票名称缺失');

        const priceOk = ensureFinite(quote.price, '价格', errors);
        const changeOk = ensureFinite(quote.change, '涨跌额', errors);
        const changePercentOk = ensureFinite(quote.changePercent, '涨跌幅', errors);
        const openOk = ensureFinite(quote.open, '开盘价', errors);
        const highOk = ensureFinite(quote.high, '最高价', errors);
        const lowOk = ensureFinite(quote.low, '最低价', errors);
        const preCloseOk = ensureFinite(quote.preClose, '昨收价', errors);
        const volumeOk = ensureFinite(quote.volume, '成交量', errors);
        const amountOk = ensureFinite(quote.amount, '成交额', errors);

        if (!isFiniteNumber(quote.turnoverRate)) {
            warnings.push('换手率缺失或非数值');
        }

        // 价格合理性检查
        if (priceOk && quote.price <= 0) {
            errors.push(`价格异常: ${quote.price}`);
        } else if (priceOk && (quote.price < DATA_VALIDATION.PRICE_RANGE.min ||
            quote.price > DATA_VALIDATION.PRICE_RANGE.max)) {
            warnings.push(`价格超出正常范围: ${quote.price}`);
        }

        // 涨跌幅检查
        if (changePercentOk) {
            const isSTStock = quote.name?.includes('ST') || quote.name?.includes('*ST');
            const changeRange = isSTStock ? DATA_VALIDATION.ST_CHANGE_RANGE : DATA_VALIDATION.CHANGE_RANGE;

            if (quote.changePercent < changeRange.min || quote.changePercent > changeRange.max) {
                warnings.push(`涨跌幅超出范围: ${quote.changePercent}%`);
            }
        }

        // 成交量检查
        if (volumeOk && quote.volume < DATA_VALIDATION.VOLUME_MIN) {
            warnings.push(`成交量异常: ${quote.volume}`);
        }

        if (amountOk && quote.amount < 0) {
            warnings.push(`成交额异常: ${quote.amount}`);
        }

        // 时效性检查
        if (!isFiniteNumber(quote.timestamp)) {
            warnings.push('时间戳缺失或非数值');
        } else if (quote.timestamp) {
            const delay = Date.now() - quote.timestamp;
            if (delay > DATA_VALIDATION.TIMESTAMP_MAX_DELAY) {
                warnings.push(`数据延迟过大: ${Math.round(delay / 1000)}秒`);
            }
        }

        // 价格逻辑一致性检查
        if (highOk && lowOk && quote.high > 0 && quote.low > 0) {
            if (quote.high < quote.low) {
                errors.push(`最高价(${quote.high})低于最低价(${quote.low})`);
            }
            if (priceOk && (quote.price > quote.high || quote.price < quote.low)) {
                warnings.push(`当前价格超出日内高低范围`);
            }
        }

        if (openOk && highOk && lowOk && quote.high > 0 && quote.low > 0) {
            if (quote.open > quote.high || quote.open < quote.low) {
                warnings.push(`开盘价超出日内高低范围`);
            }
        }

        if (preCloseOk && priceOk && quote.preClose > 0 && quote.price > 0 && !changeOk) {
            warnings.push('涨跌额缺失，无法核对昨收价一致性');
        }

        return {
            valid: errors.length === 0,
            errors,
            warnings,
        };
    }

    /**
     * 校验K线数据
     */
    validateKline(klines: KlineData[]): ValidationResult {
        const errors: string[] = [];
        const warnings: string[] = [];

        if (!klines || klines.length === 0) {
            errors.push('K线数据为空');
            return { valid: false, errors, warnings };
        }

        // 检查日期连续性
        let prevDate: string | null = null;
        for (const kline of klines) {
            if (!kline.date) {
                errors.push('K线日期缺失');
                continue;
            }

            const openOk = ensureFinite(kline.open, `${kline.date}: 开盘价`, errors);
            const closeOk = ensureFinite(kline.close, `${kline.date}: 收盘价`, errors);
            const highOk = ensureFinite(kline.high, `${kline.date}: 最高价`, errors);
            const lowOk = ensureFinite(kline.low, `${kline.date}: 最低价`, errors);
            const volumeOk = ensureFinite(kline.volume, `${kline.date}: 成交量`, errors);

            // 价格逻辑检查
            if (highOk && lowOk && kline.high < kline.low) {
                errors.push(`${kline.date}: 最高价低于最低价`);
            }
            if (openOk && highOk && lowOk && (kline.open > kline.high || kline.open < kline.low)) {
                warnings.push(`${kline.date}: 开盘价超出高低范围`);
            }
            if (closeOk && highOk && lowOk && (kline.close > kline.high || kline.close < kline.low)) {
                warnings.push(`${kline.date}: 收盘价超出高低范围`);
            }

            // 成交量检查
            if (volumeOk && kline.volume < 0) {
                errors.push(`${kline.date}: 成交量为负`);
            }

            // 日期顺序检查
            if (prevDate && kline.date < prevDate) {
                warnings.push(`日期顺序异常: ${prevDate} -> ${kline.date}`);
            }
            prevDate = kline.date;
        }

        return {
            valid: errors.length === 0,
            errors,
            warnings,
        };
    }

    /**
     * 校验北向资金数据
     */
    validateNorthFund(data: NorthFund[]): ValidationResult {
        const errors: string[] = [];
        const warnings: string[] = [];

        if (!data || data.length === 0) {
            errors.push('北向资金数据为空');
            return { valid: false, errors, warnings };
        }

        // 检查是否所有数据都为0
        const allZero = data.every(item =>
            item.total === 0 && item.shConnect === 0 && item.szConnect === 0
        );
        if (allZero) {
            errors.push('所有北向资金数据均为0，数据可能无效');
        }

        // 检查数据一致性
        for (const item of data) {
            if (!item.date) {
                errors.push('北向资金日期缺失');
                continue;
            }
            const totalOk = ensureFinite(item.total, `${item.date}: 总额`, errors);
            const shOk = ensureFinite(item.shConnect, `${item.date}: 沪股通`, errors);
            const szOk = ensureFinite(item.szConnect, `${item.date}: 深股通`, errors);

            const calculatedTotal = item.shConnect + item.szConnect;
            if (totalOk && shOk && szOk && Math.abs(calculatedTotal - item.total) > 1) { // 允许1元误差
                warnings.push(`${item.date}: 沪深股通合计与总计不一致`);
            }
        }

        // 检查日期连续性
        const dates = data.map((d: any) => d.date).sort();
        for (let i = 1; i < dates.length; i++) {
            const prev = new Date(dates[i - 1]);
            const curr = new Date(dates[i]);
            const diffDays = (curr.getTime() - prev.getTime()) / (1000 * 60 * 60 * 24);

            if (diffDays > 5) {
                warnings.push(`日期间隔过大: ${dates[i - 1]} -> ${dates[i]}`);
            }
        }

        return {
            valid: errors.length === 0,
            errors,
            warnings,
        };
    }

    /**
     * 校验板块资金流向数据
     */
    validateSectorFlow(data: SectorData[]): ValidationResult {
        const errors: string[] = [];
        const warnings: string[] = [];

        if (!data || data.length === 0) {
            errors.push('板块资金数据为空');
            return { valid: false, errors, warnings };
        }

        let hasName = false;
        let hasChange = false;
        let hasFlow = false;
        let missingCodeCount = 0;

        for (const item of data) {
            if (item.name) {
                hasName = true;
            }
            if (!item.code) {
                missingCodeCount += 1;
            }
            if (isFiniteNumber(item.changePercent)) {
                hasChange = true;
                if (item.changePercent < -100 || item.changePercent > 100) {
                    warnings.push(`板块涨跌幅异常: ${item.name || item.code}`);
                }
            }
            if (isFiniteNumber(item.netInflow) || isFiniteNumber(item.amount)) {
                hasFlow = true;
            }
        }

        if (!hasName) {
            errors.push('板块名称缺失');
        }
        if (missingCodeCount === data.length) {
            warnings.push('板块代码缺失');
        }
        if (!hasChange) {
            warnings.push('板块涨跌幅缺失');
        }
        if (!hasFlow) {
            errors.push('板块资金流向缺失');
        }

        const allZero = data.every(item =>
            (item.netInflow ?? 0) === 0 &&
            (item.amount ?? 0) === 0
        );
        if (allZero) {
            errors.push('板块资金净流入全为 0，数据可能无效');
        }

        return {
            valid: errors.length === 0,
            errors,
            warnings,
        };
    }

    /**
     * 跨源数据比对
     */
    compareQuotes(quote1: RealtimeQuote, quote2: RealtimeQuote, source1: string, source2: string): ValidationResult {
        const errors: string[] = [];
        const warnings: string[] = [];

        if (quote1.code !== quote2.code) {
            errors.push('股票代码不匹配');
            return { valid: false, errors, warnings };
        }

        if (quote1.price > 0 && quote2.price > 0) {
            const priceDiff = Math.abs(quote1.price - quote2.price) / quote1.price;
            if (priceDiff > DATA_VALIDATION.CROSS_SOURCE_PRICE_DIFF) {
                warnings.push(
                    `价格偏差过大: ${source1}=${quote1.price}, ${source2}=${quote2.price}, 偏差=${(priceDiff * 100).toFixed(2)}%`
                );
            }
        }

        if (quote1.volume > 0 && quote2.volume > 0) {
            const volumeDiff = Math.abs(quote1.volume - quote2.volume) / quote1.volume;
            if (volumeDiff > 0.1) {
                warnings.push(
                    `成交量偏差较大: ${source1}=${quote1.volume}, ${source2}=${quote2.volume}`
                );
            }
        }

        return {
            valid: errors.length === 0,
            errors,
            warnings,
        };
    }

    /**
     * 计算数据质量评分
     */
    calculateQualityScore(
        quotes: RealtimeQuote[],
        klines: KlineData[],
        northFund: NorthFund[]
    ): DataQualityScore {
        let completeness = 100;
        let accuracy = 100;
        let timeliness = 100;
        let consistency = 100;

        const totalExpected = quotes.length + klines.length + northFund.length;
        const totalValid =
            quotes.filter((q: any) => q.price > 0).length +
            klines.filter((k: any) => k.close > 0).length +
            northFund.filter((n: any) => n.date).length;

        if (totalExpected > 0) {
            completeness = (totalValid / totalExpected) * 100;
        }

        let errorCount = 0;
        for (const quote of quotes) {
            const result = this.validateQuote(quote);
            errorCount += result.errors.length;
        }
        accuracy = Math.max(0, 100 - errorCount * 10);

        const now = Date.now();
        let delayedCount = 0;
        for (const quote of quotes) {
            if (quote.timestamp && (now - quote.timestamp) > DATA_VALIDATION.TIMESTAMP_MAX_DELAY) {
                delayedCount++;
            }
        }
        if (quotes.length > 0) {
            timeliness = ((quotes.length - delayedCount) / quotes.length) * 100;
        }

        const klineResult = this.validateKline(klines);
        consistency = Math.max(0, 100 - klineResult.warnings.length * 5);

        const overall = (completeness * 0.25 + accuracy * 0.30 + timeliness * 0.25 + consistency * 0.20);

        return {
            overall: Math.round(overall),
            completeness: Math.round(completeness),
            accuracy: Math.round(accuracy),
            timeliness: Math.round(timeliness),
            consistency: Math.round(consistency),
        };
    }
}

export const dataValidator = new DataValidator();
