/**
 * 数据预热服务
 * 主动预加载核心股票数据到 TimescaleDB
 */

import { timescaleDB } from '../storage/timescaledb.js';
import { AdapterManager } from '../adapters/index.js';
import { logger } from '../logger.js';

// 核心股票池（沪深300成分股代表）
const CORE_STOCKS = [
    '000001', // 平安银行
    '000002', // 万科A
    '000333', // 美的集团
    '000858', // 五粮液
    '600000', // 浦发银行
    '600036', // 招商银行
    '600519', // 贵州茅台
    '600887', // 伊利股份
    '601318', // 中国平安
    '601398', // 工商银行
];

// 热门板块股票
const SECTOR_STOCKS = [
    '300750', // 宁德时代（新能源）
    '688981', // 中芯国际（半导体）
    '002594', // 比亚迪（新能源汽车）
    '300059', // 东方财富（互联网金融）
];

export interface WarmupConfig {
    stocks?: string[];
    lookbackDays?: number;
    forceUpdate?: boolean;
    includeFinancials?: boolean;
}

export interface WarmupResult {
    success: boolean;
    stocksProcessed: number;
    stocksFailed: string[];
    klineRecords: number;
    financialRecords: number;
    duration: number;
    errors: string[];
}

/**
 * 预热核心股票数据
 */
export async function warmupCoreStocks(config: WarmupConfig = {}): Promise<WarmupResult> {
    const startTime = Date.now();
    const {
        stocks = [...CORE_STOCKS, ...SECTOR_STOCKS],
        lookbackDays = 250,
        forceUpdate = false,
        includeFinancials = true,
    } = config;

    const adapterManager = new AdapterManager();
    const result: WarmupResult = {
        success: true,
        stocksProcessed: 0,
        stocksFailed: [],
        klineRecords: 0,
        financialRecords: 0,
        duration: 0,
        errors: [],
    };

    logger.info(`开始预热 ${stocks.length} 只股票数据，回溯 ${lookbackDays} 天`);

    for (const code of stocks) {
        try {
            // 检查是否需要更新
            if (!forceUpdate) {
                const latestDate = await timescaleDB.getLatestBarDate(code);
                const today = new Date().toISOString().split('T')[0];
                
                if (latestDate && latestDate >= today) {
                    logger.info(`${code} 数据已是最新，跳过`);
                    result.stocksProcessed++;
                    continue;
                }
            }

            // 获取 K 线数据
            const klineResponse = await adapterManager.getKline(code, 'daily', lookbackDays);
            
            if (!klineResponse.success || !klineResponse.data || klineResponse.data.length === 0) {
                const error = `${code}: 获取K线数据失败 - ${klineResponse.error || '无数据'}`;
                logger.warn(error);
                result.stocksFailed.push(code);
                result.errors.push(error);
                continue;
            }

            // 批量写入 K 线数据
            const klineRows = klineResponse.data.map(k => ({
                code,
                date: new Date(k.date),
                open: k.open,
                high: k.high,
                low: k.low,
                close: k.close,
                volume: k.volume,
                amount: k.amount || 0,
                turnover: 0,
                change_percent: 0,
            }));

            const { inserted, updated } = await timescaleDB.batchUpsertKline(klineRows);
            result.klineRecords += inserted + updated;
            
            logger.info(`${code}: 写入 ${inserted} 条新数据，更新 ${updated} 条数据`);

            // 获取财务数据（可选）
            if (includeFinancials) {
                try {
                    const financialResponse = await adapterManager.getFinancials(code);
                    
                    if (financialResponse.success && financialResponse.data) {
                        await timescaleDB.upsertFinancials({
                            code,
                            report_date: financialResponse.data.reportDate,
                            revenue: financialResponse.data.revenue,
                            net_profit: financialResponse.data.netProfit,
                            gross_margin: financialResponse.data.grossProfitMargin,
                            net_margin: financialResponse.data.netProfitMargin,
                            debt_ratio: financialResponse.data.debtRatio,
                            current_ratio: financialResponse.data.currentRatio,
                            eps: financialResponse.data.eps,
                            roe: financialResponse.data.roe,
                            revenue_growth: financialResponse.data.revenueGrowth,
                            profit_growth: financialResponse.data.netProfitGrowth,
                        });
                        result.financialRecords++;
                        logger.info(`${code}: 写入财务数据`);
                    }
                } catch (error) {
                    logger.warn(`${code}: 获取财务数据失败 - ${error}`);
                }
            }

            result.stocksProcessed++;

            // 避免请求过快
            await sleep(100);

        } catch (error) {
            const errorMsg = `${code}: 处理失败 - ${error instanceof Error ? error.message : String(error)}`;
            logger.error(errorMsg);
            result.stocksFailed.push(code);
            result.errors.push(errorMsg);
        }
    }

    result.duration = Date.now() - startTime;
    result.success = result.stocksFailed.length === 0;

    logger.info(`数据预热完成: 成功 ${result.stocksProcessed}/${stocks.length}, ` +
        `K线记录 ${result.klineRecords}, 财务记录 ${result.financialRecords}, ` +
        `耗时 ${(result.duration / 1000).toFixed(2)}s`);

    return result;
}

/**
 * 增量更新：仅更新过期数据
 */
export async function incrementalUpdate(hoursOld: number = 24): Promise<WarmupResult> {
    const startTime = Date.now();
    
    logger.info(`开始增量更新，查找 ${hoursOld} 小时前的数据`);

    // 获取需要更新的股票列表
    const stocksToUpdate = await timescaleDB.getStocksNeedingKlineUpdate(100);
    
    if (stocksToUpdate.length === 0) {
        logger.info('所有数据都是最新的，无需更新');
        return {
            success: true,
            stocksProcessed: 0,
            stocksFailed: [],
            klineRecords: 0,
            financialRecords: 0,
            duration: Date.now() - startTime,
            errors: [],
        };
    }

    logger.info(`找到 ${stocksToUpdate.length} 只股票需要更新`);

    return warmupCoreStocks({
        stocks: stocksToUpdate,
        lookbackDays: 30, // 增量更新只需要最近30天
        forceUpdate: true,
        includeFinancials: false, // 增量更新不包含财务数据
    });
}

/**
 * 定时任务：每日收盘后更新
 */
export async function scheduledDailyUpdate(): Promise<void> {
    const now = new Date();
    const hour = now.getHours();

    // 仅在交易日收盘后（15:30-23:59）执行
    if (hour < 15 || hour > 23) {
        logger.info('非更新时间段，跳过定时更新');
        return;
    }

    logger.info('开始定时日更新');

    try {
        const result = await incrementalUpdate(24);
        
        if (result.success) {
            logger.info('定时更新成功');
        } else {
            logger.warn(`定时更新部分失败: ${result.stocksFailed.length} 只股票失败`);
        }
    } catch (error) {
        logger.error(`定时更新失败: ${error}`);
    }
}

/**
 * 启动定时任务
 */
export function startWarmupScheduler(intervalHours: number = 24): NodeJS.Timeout {
    logger.info(`启动数据预热定时任务，间隔 ${intervalHours} 小时`);

    // 立即执行一次
    scheduledDailyUpdate().catch(error => {
        logger.error(`初始预热失败: ${error}`);
    });

    // 定时执行
    return setInterval(() => {
        scheduledDailyUpdate().catch(error => {
            logger.error(`定时预热失败: ${error}`);
        });
    }, intervalHours * 60 * 60 * 1000);
}

/**
 * 辅助函数：延迟
 */
function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}
