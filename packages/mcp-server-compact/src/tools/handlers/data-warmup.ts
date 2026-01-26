/**
 * 数据预热工具处理器
 */

import { warmupCoreStocks, incrementalUpdate, startWarmupScheduler } from '../../services/data-warmup.js';

export async function handleDataWarmup(args: any) {
    const {
        action = 'warmup',
        stocks,
        lookbackDays = 250,
        forceUpdate = false,
        includeFinancials = true,
        hoursOld = 24,
        intervalHours = 24,
    } = args;

    // ===== 预热核心股票 =====
    if (action === 'warmup' || action === 'warmup_core') {
        const result = await warmupCoreStocks({
            stocks,
            lookbackDays,
            forceUpdate,
            includeFinancials,
        });

        return {
            success: result.success,
            data: {
                stocksProcessed: result.stocksProcessed,
                stocksFailed: result.stocksFailed,
                klineRecords: result.klineRecords,
                financialRecords: result.financialRecords,
                duration: `${(result.duration / 1000).toFixed(2)}s`,
                errors: result.errors.length > 0 ? result.errors : undefined,
            },
            message: result.success
                ? `成功预热 ${result.stocksProcessed} 只股票，写入 ${result.klineRecords} 条K线数据`
                : `预热完成，但有 ${result.stocksFailed.length} 只股票失败`,
        };
    }

    // ===== 增量更新 =====
    if (action === 'incremental_update' || action === 'update') {
        const result = await incrementalUpdate(hoursOld);

        return {
            success: result.success,
            data: {
                stocksProcessed: result.stocksProcessed,
                stocksFailed: result.stocksFailed,
                klineRecords: result.klineRecords,
                duration: `${(result.duration / 1000).toFixed(2)}s`,
                errors: result.errors.length > 0 ? result.errors : undefined,
            },
            message: result.success
                ? `成功更新 ${result.stocksProcessed} 只股票`
                : `更新完成，但有 ${result.stocksFailed.length} 只股票失败`,
        };
    }

    // ===== 启动定时任务 =====
    if (action === 'start_scheduler' || action === 'schedule') {
        try {
            startWarmupScheduler(intervalHours);
            return {
                success: true,
                message: `已启动数据预热定时任务，间隔 ${intervalHours} 小时`,
            };
        } catch (error) {
            return {
                success: false,
                error: `启动定时任务失败: ${error instanceof Error ? error.message : String(error)}`,
            };
        }
    }

    return {
        success: false,
        error: `未知操作: ${action}`,
    };
}
