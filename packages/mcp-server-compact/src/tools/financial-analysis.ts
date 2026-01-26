/**
 * 财务分析工具
 * 包含财务报表、估值数据、业绩预告等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { getLatestFinancialData, getFinancialHistory } from '../storage/financial-data.js';
import { getValuationData, getValuationHistory } from '../storage/valuation-data.js';
import { adapterManager } from '../adapters/index.js';

// ========== get_financial_summary ==========

const getFinancialSummarySchema = z.object({
    code: z.string().describe('股票代码'),
});

const getFinancialSummaryTool: ToolDefinition = {
    name: 'get_financial_summary',
    description: '获取股票的最新财务摘要（营收、利润、ROE等）',
    category: 'financial_analysis',
    inputSchema: getFinancialSummarySchema,
    tags: ['financial', 'summary'],
    dataSource: 'real',
};

const getFinancialSummaryHandler: ToolHandler<z.infer<typeof getFinancialSummarySchema>> = async (params) => {
    // 优先读库
    let data = getLatestFinancialData(params.code);

    if (!data) {
        // 尝试从 API 拉取并缓存
        // 需要 Adapter 支持 getFinancialData
        // 暂时返回空或错误
        return {
            success: false,
            error: `暂无 ${params.code} 的财务数据`,
        };
    }

    return {
        success: true,
        data,
        source: 'database',
    };
};

// ========== get_valuation_metrics ==========

const getValuationMetricsSchema = z.object({
    code: z.string().describe('股票代码'),
});

const getValuationMetricsTool: ToolDefinition = {
    name: 'get_valuation_metrics',
    description: '获取股票的实时估值指标（PE, PB, PS, 股息率等）',
    category: 'financial_analysis',
    inputSchema: getValuationMetricsSchema,
    tags: ['financial', 'valuation'],
    dataSource: 'real',
};

const getValuationMetricsHandler: ToolHandler<z.infer<typeof getValuationMetricsSchema>> = async (params) => {
    // 优先读库
    let data = getValuationData(params.code);

    if (!data) {
        return {
            success: false,
            error: `暂无 ${params.code} 的估值数据`,
        };
    }

    return {
        success: true,
        data,
        source: 'database',
    };
};

// ========== get_historical_financials ==========

const getHistoricalFinancialsSchema = z.object({
    code: z.string().describe('股票代码'),
    limit: z.number().optional().default(3).describe('返回最近几期的财报数据（默认3期，避免上下文过长）'),
});

const getHistoricalFinancialsTool: ToolDefinition = {
    name: 'get_historical_financials',
    description: '获取股票的历史财务报表数据',
    category: 'financial_analysis',
    inputSchema: getHistoricalFinancialsSchema,
    tags: ['financial', 'history'],
    dataSource: 'real',
};

const getHistoricalFinancialsHandler: ToolHandler<z.infer<typeof getHistoricalFinancialsSchema>> = async (params) => {
    const data = getFinancialHistory(params.code, params.limit);

    return {
        success: true,
        data,
        source: 'database',
    };
};

// ========== get_historical_valuation ==========

const getHistoricalValuationSchema = z.object({
    code: z.string().describe('股票代码'),
    days: z.number().optional().default(30).describe('返回最近多少天的估值历史（默认30天，避免上下文过长）'),
});

const getHistoricalValuationTool: ToolDefinition = {
    name: 'get_historical_valuation',
    description: '获取股票的历史估值走势',
    category: 'financial_analysis',
    inputSchema: getHistoricalValuationSchema,
    tags: ['financial', 'history'],
    dataSource: 'real',
};

const getHistoricalValuationHandler: ToolHandler<z.infer<typeof getHistoricalValuationSchema>> = async (params) => {
    const data = getValuationHistory(params.code, params.days);

    return {
        success: true,
        data,
        source: 'database',
    };
};


// ========== 注册导出 ==========

export const financialAnalysisTools: ToolRegistryItem[] = [
    { definition: getFinancialSummaryTool, handler: getFinancialSummaryHandler },
    { definition: getValuationMetricsTool, handler: getValuationMetricsHandler },
    { definition: getHistoricalFinancialsTool, handler: getHistoricalFinancialsHandler },
    { definition: getHistoricalValuationTool, handler: getHistoricalValuationHandler },
];
