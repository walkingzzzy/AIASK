/**
 * 向量搜索工具
 * 基于 stock_vectors.db 提供股票相似度搜索功能
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import {
    searchSimilarStocks as dbSearchSimilar,
    searchByKline as dbSearchByKline,
    semanticStockSearch as dbSemanticSearch,
    getVectorDbStats,
    getAvailablePatternWindows,
} from '../storage/vector-db.js';

// ========== search_similar_stocks ==========

const searchSimilarStocksSchema = z.object({
    code: z.string().describe('目标股票代码'),
    top_n: z.number().optional().default(10).describe('返回结果数量，默认10'),
    similarity_type: z.enum(['fundamental', 'technical', 'both']).optional().default('both')
        .describe('相似度类型：fundamental(基本面), technical(技术面), both(综合)'),
});

const searchSimilarStocksTool: ToolDefinition = {
    name: 'search_similar_stocks',
    description: '基于向量相似度搜索与目标股票相似的股票（基于基本面、技术面特征）',
    category: 'vector_search',
    inputSchema: searchSimilarStocksSchema,
    tags: ['vector', 'search', 'similarity'],
    dataSource: 'real',
};

const searchSimilarStocksHandler: ToolHandler<z.infer<typeof searchSimilarStocksSchema>> = async (params) => {
    const results = await dbSearchSimilar(params.code, params.top_n, params.similarity_type);

    if (results.length === 0) {
        // 获取统计信息用于诊断
        const stats = await getVectorDbStats();
        return {
            success: false,
            error: stats.stockEmbeddings === 0
                ? '向量数据库为空，请先同步股票向量数据'
                : `未找到股票 ${params.code} 的向量数据`,
            data: { stats },
        };
    }

    return {
        success: true,
        data: {
            targetCode: params.code,
            similarityType: params.similarity_type,
            results: results.map((r: any) => ({
                code: r.code,
                name: r.name,
                similarity: `${(r.similarity * 100).toFixed(2)}%`,
                similarityScore: r.similarity,
            })),
            total: results.length,
        },
        source: 'vector_database',
    };
};

// ========== search_by_kline ==========

const searchByKlineSchema = z.object({
    code: z.string().describe('目标股票代码'),
    days: z.number().optional().default(20).describe('K线窗口大小（天数），默认20'),
    top_n: z.number().optional().default(10).describe('返回结果数量，默认10'),
});

const searchByKlineTool: ToolDefinition = {
    name: 'search_by_kline',
    description: '按K线形态搜索相似走势的股票（基于历史K线模式匹配）',
    category: 'vector_search',
    inputSchema: searchByKlineSchema,
    tags: ['vector', 'search', 'kline', 'pattern'],
    dataSource: 'real',
};

const searchByKlineHandler: ToolHandler<z.infer<typeof searchByKlineSchema>> = async (params) => {
    const results = await dbSearchByKline(params.code, params.days, params.top_n);

    if (results.length === 0) {
        const availableWindows = await getAvailablePatternWindows(params.code);
        if (availableWindows.length > 0) {
            const fallback = availableWindows.reduce((closest: number, current: number) => {
                const closestDiff = Math.abs(closest - params.days);
                const currentDiff = Math.abs(current - params.days);
                return currentDiff < closestDiff ? current : closest;
            }, availableWindows[0]);
            if (fallback !== params.days) {
                const fallbackResults = await dbSearchByKline(params.code, fallback, params.top_n);
                if (fallbackResults.length > 0) {
                    return {
                        success: true,
                        data: {
                            targetCode: params.code,
                            windowDays: fallback,
                            requestedDays: params.days,
                            results: fallbackResults.map((r: any) => ({
                                code: r.code,
                                name: r.name,
                                patternType: r.patternType,
                                period: `${r.startDate} ~ ${r.endDate}`,
                                similarity: `${(r.similarity * 100).toFixed(2)}%`,
                                similarityScore: r.similarity,
                            })),
                            total: fallbackResults.length,
                            note: `未找到 ${params.days} 天窗口的形态向量，已自动切换为 ${fallback} 天`,
                        },
                        source: 'pattern_vectors',
                    };
                }
            }
        }
        const stats = await getVectorDbStats();
        return {
            success: false,
            error: stats.patternVectors === 0
                ? '形态向量数据库为空，请先同步K线形态数据'
                : `未找到股票 ${params.code} 窗口=${params.days}天的形态向量`,
            data: { stats },
        };
    }

    return {
        success: true,
        data: {
            targetCode: params.code,
            windowDays: params.days,
            results: results.map((r: any) => ({
                code: r.code,
                name: r.name,
                patternType: r.patternType,
                period: `${r.startDate} ~ ${r.endDate}`,
                similarity: `${(r.similarity * 100).toFixed(2)}%`,
                similarityScore: r.similarity,
            })),
            total: results.length,
            note: '相似度 > 50% 才会被返回',
        },
        source: 'pattern_vectors',
    };
};

// ========== semantic_stock_search ==========

const semanticStockSearchSchema = z.object({
    query: z.string().describe('搜索查询文本（支持自然语言）'),
    limit: z.number().optional().default(20).describe('返回结果数量，默认20'),
});

const semanticStockSearchTool: ToolDefinition = {
    name: 'semantic_stock_search',
    description: '语义化股票搜索（基于研报、公告、新闻的全文检索）',
    category: 'vector_search',
    inputSchema: semanticStockSearchSchema,
    tags: ['vector', 'search', 'semantic', 'fts'],
    dataSource: 'real',
};

const semanticStockSearchHandler: ToolHandler<z.infer<typeof semanticStockSearchSchema>> = async (params) => {
    const results = await dbSemanticSearch(params.query, params.limit);

    if (results.length === 0) {
        const stats = await getVectorDbStats();
        return {
            success: true, // 空结果也是成功
            source: 'documents_fts',
            data: {
                query: params.query,
                results: [],
                total: 0,
                message: stats.documents === 0
                    ? '文档库为空。请先使用 data_sync_manager 工具 (action=sync_vectors) 同步研报与新闻数据。'
                    : `未找到包含 "${params.query}" 的相关文档。尝试简化关键词或扩大搜索范围。`,
            },
        };
    }

    // 按股票代码聚合结果
    const codeMap = new Map<string, typeof results>();
    for (const r of results) {
        const existing = codeMap.get(r.code) || [];
        existing.push(r);
        codeMap.set(r.code, existing);
    }

    return {
        success: true,
        data: {
            query: params.query,
            results: results.map((r: any) => ({
                code: r.code,
                docType: r.docType,
                date: r.date,
                content: r.content,
                relevanceScore: r.score.toFixed(4),
            })),
            total: results.length,
            stocksFound: codeMap.size,
        },
        source: 'documents_fts',
    };
};

// ========== 注册导出 ==========

export const vectorTools: ToolRegistryItem[] = [
    { definition: searchSimilarStocksTool, handler: searchSimilarStocksHandler },
    { definition: searchByKlineTool, handler: searchByKlineHandler },
    { definition: semanticStockSearchTool, handler: semanticStockSearchHandler },
];
