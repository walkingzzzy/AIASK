/**
 * 数据同步服务
 * 协调 Adapter 获取数据与 Storage 存储数据
 */

import { adapterManager } from '../adapters/index.js';
import * as KlineStorage from '../storage/kline-data.js';
import * as FinancialStorage from '../storage/financial-data.js';
import { timescaleDB } from '../storage/timescaledb.js';
import { 
    validateNumericData, 
    validateDateData, 
    validateStockCode, 
    validateBatchData,
    checkDataCompleteness,
    recordDataQualityIssue 
} from '../storage/data-quality.js';
import { logger } from '../logger.js';

export interface SyncResult {
    success: boolean;
    syncedCount: number;
    failedCount: number;
    errors: string[];
}

/**
 * 同步K线数据
 * @param codes 股票代码列表，为空则自动查找需要更新的股票
 * @param period K线周期 (目前仅支持 'daily' / '101')
 * @param days 回溯天数
 */
export async function syncKline(
    codes: string[] | null,
    period: string = '101',
    days: number = 250
): Promise<SyncResult> {
    const targetCodes = codes && codes.length > 0
        ? codes
        : await KlineStorage.getStocksNeedingKlineUpdate(1, 100);

    const result: SyncResult = { success: true, syncedCount: 0, failedCount: 0, errors: [] };

    // 标记尝试同步
    KlineStorage.markKlineSyncAttempted(targetCodes);

    for (const code of targetCodes) {
        try {
            // Validate stock code first
            const codeValidation = validateStockCode(code);
            if (!codeValidation.valid) {
                result.failedCount++;
                result.errors.push(`${code}: ${codeValidation.error}`);
                await recordDataQualityIssue({
                    dataset: 'kline',
                    code,
                    reason: codeValidation.error || 'Invalid stock code',
                    source: 'data-sync'
                });
                continue;
            }

            const res = await adapterManager.getKline(code, period as any, days);

            if (res.success && res.data && res.data.length > 0) {
                // Validate each kline bar
                const validationResult = validateBatchData(res.data, (k: any) => {
                    // Validate date
                    const dateCheck = validateDateData(k.date, 'date', { allowFuture: false });
                    if (!dateCheck.valid) return dateCheck;

                    // Validate OHLC prices
                    const openCheck = validateNumericData(k.open, 'open', { min: 0, allowZero: false });
                    if (!openCheck.valid) return openCheck;

                    const highCheck = validateNumericData(k.high, 'high', { min: 0, allowZero: false });
                    if (!highCheck.valid) return highCheck;

                    const lowCheck = validateNumericData(k.low, 'low', { min: 0, allowZero: false });
                    if (!lowCheck.valid) return lowCheck;

                    const closeCheck = validateNumericData(k.close, 'close', { min: 0, allowZero: false });
                    if (!closeCheck.valid) return closeCheck;

                    // Validate volume
                    const volumeCheck = validateNumericData(k.volume, 'volume', { min: 0, allowZero: true });
                    if (!volumeCheck.valid) return volumeCheck;

                    // Validate OHLC relationship: low <= open,close <= high
                    if (k.low > k.open || k.low > k.close || k.high < k.open || k.high < k.close) {
                        return { valid: false, error: 'Invalid OHLC relationship' };
                    }

                    return { valid: true };
                });

                // Log validation stats
                if (validationResult.invalid.length > 0) {
                    logger.warn(`Kline validation for ${code}: ${validationResult.stats.validCount}/${validationResult.stats.total} valid (${(validationResult.stats.validityRate * 100).toFixed(1)}%)`);
                    
                    // Record quality issues
                    for (const inv of validationResult.invalid.slice(0, 5)) { // Log first 5 issues
                        await recordDataQualityIssue({
                            dataset: 'kline',
                            code,
                            reason: inv.error,
                            source: 'data-sync',
                            payload: inv.item
                        });
                    }
                }

                // Only insert valid data
                if (validationResult.valid.length > 0) {
                    const bars = validationResult.valid.map((k: any) => ({
                        code,
                        date: k.date,
                        open: k.open,
                        high: k.high,
                        low: k.low,
                        close: k.close,
                        volume: k.volume,
                        amount: k.amount,
                        changePercent: undefined,
                        turnover: undefined
                    }));

                    try {
                        const stats = await timescaleDB.batchUpsertKline(bars.map((b: any) => ({
                            code: b.code,
                            date: new Date(b.date),
                            open: b.open,
                            high: b.high,
                            low: b.low,
                            close: b.close,
                            volume: b.volume,
                            amount: b.amount || 0,
                            turnover: b.turnover,
                            change_percent: b.changePercent
                        })));

                        if (stats.inserted > 0 || stats.updated > 0) {
                            result.syncedCount++;
                            logger.info(`Synced ${code}: ${stats.inserted} inserted, ${stats.updated} updated`);
                        } else {
                            result.syncedCount++;
                        }
                    } catch (dbErr) {
                        result.failedCount++;
                        result.errors.push(`${code}: DB error ${dbErr}`);
                        await recordDataQualityIssue({
                            dataset: 'kline',
                            code,
                            reason: `Database error: ${dbErr}`,
                            source: 'data-sync'
                        });
                    }
                } else {
                    result.failedCount++;
                    result.errors.push(`${code}: All data invalid`);
                }
            } else {
                result.failedCount++;
                result.errors.push(`${code}: Fetch failed or empty (${res.error || 'No data'})`);
                await recordDataQualityIssue({
                    dataset: 'kline',
                    code,
                    reason: res.error || 'No data returned',
                    source: 'data-sync'
                });
            }
        } catch (e) {
            result.failedCount++;
            result.errors.push(`${code}: ${String(e)}`);
            await recordDataQualityIssue({
                dataset: 'kline',
                code,
                reason: String(e),
                source: 'data-sync'
            });
        }
    }

    return result;
}

/**
 * 同步财务数据
 */
export async function syncFinancials(codes: string[] | null): Promise<SyncResult> {
    const targetCodes = codes && codes.length > 0
        ? codes
        : await FinancialStorage.getStocksNeedingFinancialUpdate(30, 20); // Limit to avoid rate limits

    const result: SyncResult = { success: true, syncedCount: 0, failedCount: 0, errors: [] };

    for (const code of targetCodes) {
        try {
            // Validate stock code
            const codeValidation = validateStockCode(code);
            if (!codeValidation.valid) {
                result.failedCount++;
                result.errors.push(`${code}: ${codeValidation.error}`);
                await recordDataQualityIssue({
                    dataset: 'financials',
                    code,
                    reason: codeValidation.error || 'Invalid stock code',
                    source: 'data-sync'
                });
                continue;
            }

            const res = await adapterManager.getFinancials(code);

            if (res.success && res.data) {
                const data = res.data;

                // Validate financial data completeness
                const completenessCheck = checkDataCompleteness([data], [
                    'code', 'reportDate', 'eps', 'roe'
                ]);

                if (completenessCheck.completenessRate < 1) {
                    logger.warn(`Financial data incomplete for ${code}: missing ${completenessCheck.incomplete[0]?.missingFields.join(', ')}`);
                    await recordDataQualityIssue({
                        dataset: 'financials',
                        code,
                        reason: `Missing fields: ${completenessCheck.incomplete[0]?.missingFields.join(', ')}`,
                        source: 'data-sync',
                        payload: data
                    });
                }

                // Validate numeric fields
                const optionalValidation = (value: number | null | undefined, field: string, options: any) => {
                    if (value === null || value === undefined) return null;
                    return validateNumericData(value, field, options);
                };

                const validations = [
                    validateNumericData(data.eps, 'eps', { min: -100, max: 100, allowNegative: true, allowZero: true }),
                    validateNumericData(data.roe, 'roe', { min: -100, max: 100, allowNegative: true, allowZero: true }),
                    optionalValidation(data.grossProfitMargin, 'grossProfitMargin', { min: -100, max: 100, allowNegative: true }),
                    optionalValidation(data.netProfitMargin, 'netProfitMargin', { min: -100, max: 100, allowNegative: true }),
                    optionalValidation(data.debtRatio, 'debtRatio', { min: 0, max: 1000, allowNegative: false }),
                    optionalValidation(data.currentRatio, 'currentRatio', { min: 0, max: 100, allowNegative: false }),
                ].filter(Boolean) as Array<{ valid: boolean; error?: string }>;

                const invalidFields = validations.filter(v => !v.valid);
                if (invalidFields.length > 0) {
                    logger.warn(`Financial data validation failed for ${code}: ${invalidFields.map(v => v.error).join('; ')}`);
                    await recordDataQualityIssue({
                        dataset: 'financials',
                        code,
                        reason: invalidFields.map(v => v.error).join('; '),
                        source: 'data-sync',
                        payload: data
                    });
                }

                // Insert even if some validations fail (partial data is better than no data)
                const success = await timescaleDB.upsertFinancials({
                    code: data.code,
                    report_date: data.reportDate,
                    eps: data.eps ?? null,
                    roe: data.roe ?? null,
                    bvps: data.bvps ?? null,
                    roa: data.roa ?? null,
                    gross_margin: data.grossProfitMargin ?? null,
                    net_margin: data.netProfitMargin ?? null,
                    debt_ratio: data.debtRatio ?? null,
                    current_ratio: data.currentRatio ?? null,
                    revenue: data.revenue ?? null,
                    net_profit: data.netProfit ?? null,
                    revenue_growth: data.revenueGrowth ?? null,
                    profit_growth: data.netProfitGrowth ?? null
                });

                if (success) {
                    result.syncedCount++;
                    logger.info(`Synced financials for ${code}`);
                } else {
                    result.failedCount++;
                    result.errors.push(`${code}: Storage upsert failed`);
                    await recordDataQualityIssue({
                        dataset: 'financials',
                        code,
                        reason: 'Database upsert failed',
                        source: 'data-sync'
                    });
                }
            } else {
                result.failedCount++;
                result.errors.push(`${code}: Fetch failed (${res.error || 'No data'})`);
                await recordDataQualityIssue({
                    dataset: 'financials',
                    code,
                    reason: res.error || 'No data returned',
                    source: 'data-sync'
                });
            }
        } catch (e: any) {
            result.failedCount++;
            result.errors.push(`${code}: ${typeof e === 'string' ? e : e.message}`);
            await recordDataQualityIssue({
                dataset: 'financials',
                code,
                reason: typeof e === 'string' ? e : e.message,
                source: 'data-sync'
            });
        }
    }

    return result;
}

/**
 * 修复数据缺口
 * 查找所有数据过期的股票并同步
 */
export async function fixDataGaps(): Promise<SyncResult> {
    const klineResult = await syncKline(null, '101', 365); // Sync last year for outdated stocks
    // Can logic be more complex? finding holes.
    // implementation relies on getStocksNeedingKlineUpdate logic
    return klineResult;
}

/**
 * 全量同步
 */
export async function fullSync(): Promise<SyncResult> {
    // 优先同步自选股（如果有）
    // 注意：Watchlist功能可以在TimescaleDB中实现，也可以保留在SQLite中
    // 这里暂时跳过watchlist，直接同步需要更新的股票
    
    // 同步K线数据
    const klineRes = await syncKline(null);
    
    // 同步财务数据
    const finRes = await syncFinancials(null);

    return {
        success: klineRes.success && finRes.success,
        syncedCount: klineRes.syncedCount + finRes.syncedCount,
        failedCount: klineRes.failedCount + finRes.failedCount,
        errors: [...klineRes.errors, ...finRes.errors]
    };
}
