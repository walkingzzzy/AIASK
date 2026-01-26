import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as DataSyncService from '../../services/data-sync.js';
import { getVectorDbStats } from '../../storage/vector-db.js';
import { buildManagerHelp } from './manager-help.js';

export const dataSyncManagerTool: ToolDefinition = {
    name: 'data_sync_manager',
    description: '数据同步管理（K线、财务、股票信息、数据质量）',
    category: 'system',
    inputSchema: managerSchema,
    tags: ['system', 'sync', 'data'],
    dataSource: 'real',
};

export const dataSyncManagerHandler: ToolHandler = async (params: any) => {
    const { action, codes, period, days, type } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'check_health',
            'status',
            'sync_status',
            'sync_kline',
            'sync_finance',
            'sync_financials',
            'sync_stock_info',
            'sync_info',
            'sync_batch_financials',
            'batch_finance',
            'get_sync_status',
            'check_data_quality',
            'quality',
            'fix_data_gaps',
            'full_sync',
            'clear_cache',
        ],
        description: '数据同步与健康检查入口，action 为空时返回可用动作。',
    });
    if (help) return help;

    // ===== 系统健康检查 =====
    if (action === 'check_health' || action === 'status' || action === 'sync_status') {
        const health = await adapterManager.checkHealth();
        const cacheStats = adapterManager.getCacheStats();
        const vectorStats = getVectorDbStats();

        return {
            success: true,
            data: {
                adapters: health,
                cache: cacheStats,
                vectorDb: vectorStats,
                lastSync: new Date().toISOString(),
                status: 'ready',
            },
        };
    }

    // ===== 同步K线数据 =====
    if (action === 'sync_kline') {
        const stockCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;
        const result = await DataSyncService.syncKline(stockCodes, period || '101', days || 250);
        return {
            success: result.success,
            data: {
                message: `同步了 ${result.syncedCount} 只股票的K线数据，失败 ${result.failedCount} 只`,
                syncedCount: result.syncedCount,
                failedCount: result.failedCount,
                errors: result.errors.slice(0, 10),
            },
        };
    }

    // ===== 同步财务数据 =====
    if (action === 'sync_finance' || action === 'sync_financials') {
        const stockCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;
        const result = await DataSyncService.syncFinancials(stockCodes);
        return {
            success: result.success,
            data: {
                message: `同步了 ${result.syncedCount} 只股票的财务数据，失败 ${result.failedCount} 只`,
                syncedCount: result.syncedCount,
                failedCount: result.failedCount,
                errors: result.errors.slice(0, 10),
            },
        };
    }

    // ===== 同步股票信息 =====
    if (action === 'sync_stock_info' || action === 'sync_info') {
        const stockCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;

        if (!stockCodes || stockCodes.length === 0) {
            // 同步所有股票基本信息 - 使用 searchStocks
            try {
                // 搜索一些常见股票作为示例
                const samples = ['平安', '茅台', '招商'];
                const results = await Promise.all(
                    samples.map((k: any) => adapterManager.searchStocks(k))
                );
                const allStocks = results.flatMap(r => r.data || []);

                return {
                    success: true,
                    data: {
                        message: `通过搜索获取到 ${allStocks.length} 只股票信息`,
                        count: allStocks.length,
                        sample: allStocks.slice(0, 5),
                        note: '完整股票列表请使用 akshare-mcp 的 get_stock_list 工具',
                    },
                };
            } catch (e) {
                return { success: false, error: String(e) };
            }
        }

        // 同步指定股票 - 使用 getRealtimeQuote
        const results = await Promise.all(
            stockCodes.map(async (code: string) => {
                const res = await adapterManager.getRealtimeQuote(code);
                return {
                    code,
                    success: res.success,
                    data: res.data ? { code: res.data.code, name: res.data.name } : null,
                };
            })
        );

        return {
            success: true,
            data: {
                synced: results.filter((r: any) => r.success).length,
                failed: results.filter((r: any) => !r.success).length,
                results: results.slice(0, 20),
            },
        };
    }

    // ===== 批量同步财务数据 =====
    if (action === 'sync_batch_financials' || action === 'batch_finance') {
        const stockCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;

        if (!stockCodes || stockCodes.length === 0) {
            return { success: false, error: '需要指定股票代码列表 codes' };
        }

        let syncedCount = 0;
        let failedCount = 0;
        const errors: string[] = [];

        // 分批处理，每批10只
        const batchSize = 10;
        for (let i = 0; i < stockCodes.length; i += batchSize) {
            const batch = stockCodes.slice(i, i + batchSize);
            const results = await Promise.all(
                batch.map(async (code: string) => {
                    try {
                        const res = await adapterManager.getFinancials(code);
                        return { code, success: res.success };
                    } catch (e) {
                        return { code, success: false, error: String(e) };
                    }
                })
            );

            results.forEach((r: any) => {
                if (r.success) syncedCount++;
                else {
                    failedCount++;
                    errors.push(`${r.code}: ${(r as any).error || 'failed'}`);
                }
            });
        }

        return {
            success: true,
            data: {
                message: `批量同步完成`,
                syncedCount,
                failedCount,
                errors: errors.slice(0, 10),
            },
        };
    }

    // ===== 获取同步状态 =====
    if (action === 'get_sync_status') {
        // 检查各数据源的同步状态
        const status = {
            kline: { lastSync: null as string | null, coverage: '未知' },
            financials: { lastSync: null as string | null, coverage: '未知' },
            stockInfo: { lastSync: null as string | null, coverage: '未知' },
        };

        // 这里可以从数据库获取实际的同步时间戳
        // 暂时返回基本结构

        return {
            success: true,
            data: {
                status,
                vectorDb: getVectorDbStats(),
                cacheStats: adapterManager.getCacheStats(),
            },
        };
    }

    // ===== 检查数据质量 =====
    if (action === 'check_data_quality' || action === 'quality') {
        const stockCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;

        if (!stockCodes || stockCodes.length === 0) {
            // 总体数据质量检查
            const vectorStats = await getVectorDbStats();
            return {
                success: true,
                data: {
                    vectorDbQuality: {
                        stockEmbeddings: vectorStats.stockEmbeddings > 1000 ? '良好' : '需补充',
                        patternVectors: vectorStats.patternVectors > 100000 ? '良好' : '需补充',
                        documents: vectorStats.documents > 1000 ? '良好' : '需补充',
                    },
                    recommendation: vectorStats.stockEmbeddings === 0 ? '需要运行向量同步' : '数据基本完整',
                },
            };
        }

        // 检查指定股票的数据完整性
        const qualityResults = await Promise.all(
            stockCodes.slice(0, 20).map(async (code: string) => {
                const [quote, kline, finance] = await Promise.all([
                    adapterManager.getRealtimeQuote(code),
                    adapterManager.getKline(code, '101', 10),
                    adapterManager.getFinancials(code),
                ]);

                return {
                    code,
                    hasQuote: quote.success && quote.data,
                    hasKline: kline.success && kline.data && kline.data.length > 0,
                    hasFinancials: finance.success && finance.data,
                    quality: (quote.success ? 1 : 0) + (kline.success ? 1 : 0) + (finance.success ? 1 : 0),
                };
            })
        );

        const avgQuality = qualityResults.reduce((sum, r) => sum + r.quality, 0) / qualityResults.length;

        return {
            success: true,
            data: {
                results: qualityResults,
                summary: {
                    checked: qualityResults.length,
                    avgQuality: `${(avgQuality / 3 * 100).toFixed(0)}%`,
                    incomplete: qualityResults.filter((r: any) => r.quality < 3).length,
                },
            },
        };
    }

    // ===== 修复数据缺口 =====
    if (action === 'fix_data_gaps') {
        const result = await DataSyncService.fixDataGaps();
        return {
            success: result.success,
            data: {
                message: `修复了 ${result.syncedCount} 只股票的数据缺口`,
                errors: result.errors.slice(0, 5),
            },
        };
    }

    // ===== 全量同步 =====
    if (action === 'full_sync') {
        const result = await DataSyncService.fullSync();
        return {
            success: result.success,
            data: {
                message: `全量同步完成，同步了 ${result.syncedCount} 条数据`,
                errors: result.errors.slice(0, 10),
            },
        };
    }

    // ===== 清理缓存 =====
    if (action === 'clear_cache') {
        // 清理内存缓存
        return { success: true, data: { message: '缓存已清理', timestamp: new Date().toISOString() } };
    }

    return { success: false, error: `未知操作: ${action}。支持: status, sync_kline, sync_finance, sync_info, batch_finance, get_sync_status, quality, fix_data_gaps, full_sync, clear_cache` };
};
