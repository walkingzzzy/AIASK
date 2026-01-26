import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import {
    searchSimilarStocks,
    searchByKline,
    semanticStockSearch,
    getVectorDbStats,
} from '../../storage/vector-db.js';

export const vectorSearchManagerTool: ToolDefinition = {
    name: 'vector_search_manager',
    description: '向量搜索管理（相似股票、K线形态、语义搜索）',
    category: 'search',
    inputSchema: managerSchema,
    tags: ['vector', 'search', 'similarity'],
    dataSource: 'real',
};

export const vectorSearchManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, query, topN = 10, days = 20, similarityType = 'both' } = params;

    // 检查向量数据库状态
    const stats = await getVectorDbStats();
    const dbAvailable = stats.stockEmbeddings > 0 || stats.patternVectors > 0 || stats.documents > 0;

    // ===== 数据库状态 =====
    if (action === 'status' || action === 'stats') {
        return {
            success: true,
            data: {
                available: dbAvailable,
                statistics: stats,
                features: {
                    similarStocks: stats.stockEmbeddings > 0,
                    klinePatterns: stats.patternVectors > 0,
                    semanticSearch: stats.documents > 0,
                },
            },
        };
    }

    // ===== 相似股票搜索 =====
    if (action === 'search_similar' || action === 'similar') {
        if (!code) return { success: false, error: '需要股票代码 code' };

        if (stats.stockEmbeddings === 0) {
            return {
                success: false,
                error: '股票向量数据库为空，请先同步数据',
                data: { stats },
            };
        }

        const results = await searchSimilarStocks(code, topN, similarityType as 'fundamental' | 'technical' | 'both');

        if (results.length === 0) {
            return {
                success: false,
                error: `未找到股票 ${code} 的向量数据`,
            };
        }

        return {
            success: true,
            data: {
                targetCode: code,
                similarityType,
                results: results.map((r: any) => ({
                    code: r.code,
                    name: r.name,
                    similarity: `${(r.similarity * 100).toFixed(2)}%`,
                })),
                count: results.length,
            },
        };
    }

    // ===== K线形态搜索 =====
    if (action === 'search_kline' || action === 'kline_pattern') {
        if (!code) return { success: false, error: '需要股票代码 code' };

        if (stats.patternVectors === 0) {
            return {
                success: false,
                error: 'K线形态向量数据库为空，请先同步数据',
                data: { stats },
            };
        }

        const results = await searchByKline(code, days, topN);

        if (results.length === 0) {
            return {
                success: true,
                data: {
                    targetCode: code,
                    windowDays: days,
                    results: [],
                    message: `未找到与 ${code} 近${days}日走势相似的股票（相似度>50%）`,
                },
            };
        }

        return {
            success: true,
            data: {
                targetCode: code,
                windowDays: days,
                results: results.map((r: any) => ({
                    code: r.code,
                    name: r.name,
                    period: `${r.startDate} ~ ${r.endDate}`,
                    patternType: r.patternType,
                    similarity: `${(r.similarity * 100).toFixed(2)}%`,
                })),
                count: results.length,
            },
        };
    }

    // ===== 语义搜索 =====
    if (action === 'semantic_search' || action === 'semantic') {
        if (!query) return { success: false, error: '需要搜索查询 query' };

        if (stats.documents === 0) {
            return {
                success: false,
                error: '文档库为空，请先同步研报/公告数据',
                data: { stats },
            };
        }

        const searchResults = await semanticStockSearch(query, topN);

        return {
            success: true,
            data: {
                query,
                results: searchResults.map((r: any) => ({
                    code: r.code,
                    docType: r.docType,
                    date: r.date,
                    content: r.content,
                    relevance: r.score.toFixed(4),
                })),
                count: searchResults.length,
                message: searchResults.length === 0 ? `未找到包含 "${query}" 的相关文档` : undefined,
            },
        };
    }

    // ===== 增强搜索（组合多种搜索）=====
    if (action === 'search_enhanced' || action === 'enhanced') {
        if (!code && !query) return { success: false, error: '需要股票代码 code 或搜索查询 query' };

        const results: any = {};

        // 如果有 code，搜索相似股票和形态
        if (code) {
            if (stats.stockEmbeddings > 0) {
                results.similarStocks = searchSimilarStocks(code, 5, 'both');
            }
            if (stats.patternVectors > 0) {
                results.klineMatches = searchByKline(code, days, 5);
            }
        }

        // 如果有 query，进行语义搜索
        if (query && stats.documents > 0) {
            results.semanticResults = semanticStockSearch(query, 10);
        }

        return {
            success: true,
            data: {
                code,
                query,
                ...results,
            },
        };
    }

    // ===== 索引K线数据 =====
    if (action === 'index_kline') {
        // 这个功能需要后台任务支持
        return {
            success: true,
            data: {
                message: 'K线形态索引功能',
                currentPatterns: stats.patternVectors,
                note: '批量索引需要后台任务支持',
            },
            degraded: true,
        };
    }

    // ===== 批量索引 =====
    if (action === 'index_batch') {
        return {
            success: true,
            data: {
                message: '批量向量索引功能',
                features: ['批量计算股票特征向量', '批量提取K线形态', '批量索引研报文档'],
                note: '批量操作需要后台任务支持',
            },
            degraded: true,
        };
    }

    // 默认返回状态
    if (!action) {
        return {
            success: true,
            data: {
                available: dbAvailable,
                statistics: stats,
                supportedActions: ['status', 'similar', 'kline_pattern', 'semantic', 'enhanced'],
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: status, similar, kline_pattern, semantic, enhanced` };
};
