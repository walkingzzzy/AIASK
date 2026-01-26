/**
 * 研报分析工具
 * 通过 akshare-mcp 获取真实研报数据
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { callAkshareMcpTool } from '../adapters/akshare-mcp-client.js';

// 研报响应类型
interface ResearchReport {
    title: string;
    institution: string;
    author?: string;
    rating: string;
    targetPrice?: number;
    date: string;
}

interface ResearchResponse {
    stockCode: string;
    reports: ResearchReport[];
    total: number;
}

// ========== search_research ==========

const searchResearchSchema = z.object({
    keyword: z.string().optional().default('').describe('搜索关键词'),
    code: z.string().optional().describe('股票代码（6位）'),
    days: z.number().optional().default(30).describe('最近天数'),
});

const searchResearchTool: ToolDefinition = {
    name: 'search_research',
    description: '搜索研究报告（支持按关键词和股票代码筛选）',
    category: 'research',
    inputSchema: searchResearchSchema,
    tags: ['research', 'report', 'search'],
    dataSource: 'real',
};

const searchResearchHandler: ToolHandler<z.infer<typeof searchResearchSchema>> = async (params) => {
    const result = await callAkshareMcpTool<ResearchResponse>('search_research', {
        keyword: params.keyword || '',
        stock_code: params.code || '',
        days: params.days || 30,
    });

    if (!result.success) {
        return {
            success: false,
            error: result.error || '搜索研报失败',
        };
    }

    return {
        success: true,
        data: result.data,
        source: 'akshare',
    };
};

// ========== analyze_research_report ==========

const analyzeResearchReportSchema = z.object({
    code: z.string().describe('股票代码'),
    limit: z.number().optional().default(5).describe('获取研报数量'),
});

const analyzeResearchReportTool: ToolDefinition = {
    name: 'analyze_research_report',
    description: '分析个股研报内容（获取最新研报的评级、目标价等）',
    category: 'research',
    inputSchema: analyzeResearchReportSchema,
    tags: ['research', 'report', 'analysis'],
    dataSource: 'real',
};

const analyzeResearchReportHandler: ToolHandler<z.infer<typeof analyzeResearchReportSchema>> = async (params) => {
    const result = await callAkshareMcpTool<ResearchResponse>('get_stock_research', {
        stock_code: params.code,
        limit: params.limit || 5,
    });

    if (!result.success || !result.data) {
        return {
            success: false,
            error: result.error || `未找到股票 ${params.code} 的研报`,
        };
    }

    const reports = result.data.reports || [];

    // 统计分析
    const ratings = reports.map((r: any) => r.rating).filter(Boolean);
    const ratingCounts: Record<string, number> = {};
    for (const r of ratings) {
        ratingCounts[r] = (ratingCounts[r] || 0) + 1;
    }

    const targetPrices = reports.map((r: any) => r.targetPrice).filter((p): p is number => p !== undefined && p > 0);
    const avgTargetPrice = targetPrices.length > 0
        ? targetPrices.reduce((a: any, b: any) => a + b, 0) / targetPrices.length
        : null;

    const institutions = [...new Set(reports.map((r: any) => r.institution).filter(Boolean))];

    return {
        success: true,
        data: {
            stockCode: params.code,
            recentReports: reports.slice(0, 5).map((r: any) => ({
                title: r.title,
                institution: r.institution,
                rating: r.rating,
                targetPrice: r.targetPrice,
                date: r.date,
            })),
            analysis: {
                totalReports: reports.length,
                ratingDistribution: ratingCounts,
                averageTargetPrice: avgTargetPrice ? Math.round(avgTargetPrice * 100) / 100 : null,
                coveringInstitutions: institutions.slice(0, 10),
                latestDate: reports[0]?.date || null,
            },
        },
        source: 'akshare',
    };
};

// ========== get_research_summary ==========

const getResearchSummarySchema = z.object({
    code: z.string().describe('股票代码'),
    limit: z.number().optional().default(20).describe('获取研报数量'),
});

const getResearchSummaryTool: ToolDefinition = {
    name: 'get_research_summary',
    description: '获取个股研报汇总统计（评级分布、目标价区间、覆盖机构）',
    category: 'research',
    inputSchema: getResearchSummarySchema,
    tags: ['research', 'report', 'summary'],
    dataSource: 'real',
};

const getResearchSummaryHandler: ToolHandler<z.infer<typeof getResearchSummarySchema>> = async (params) => {
    const result = await callAkshareMcpTool<ResearchResponse>('get_stock_research', {
        stock_code: params.code,
        limit: params.limit || 20,
    });

    if (!result.success || !result.data) {
        return {
            success: false,
            error: result.error || `未找到股票 ${params.code} 的研报`,
        };
    }

    const reports = result.data.reports || [];

    // 评级统计
    const ratings = reports.map((r: any) => r.rating).filter(Boolean);
    const ratingCounts: Record<string, number> = {};
    for (const r of ratings) {
        ratingCounts[r] = (ratingCounts[r] || 0) + 1;
    }

    // 目标价统计
    const targetPrices = reports.map((r: any) => r.targetPrice).filter((p): p is number => p !== undefined && p > 0);
    const priceStats = targetPrices.length > 0 ? {
        min: Math.min(...targetPrices),
        max: Math.max(...targetPrices),
        avg: Math.round((targetPrices.reduce((a: any, b: any) => a + b, 0) / targetPrices.length) * 100) / 100,
        count: targetPrices.length,
    } : null;

    // 机构统计
    const institutionMap: Record<string, number> = {};
    for (const r of reports) {
        if (r.institution) {
            institutionMap[r.institution] = (institutionMap[r.institution] || 0) + 1;
        }
    }
    const topInstitutions = Object.entries(institutionMap)
        .sort((a: any, b: any) => b[1] - a[1])
        .slice(0, 10)
        .map(([name, count]) => ({ name, reports: count }));

    return {
        success: true,
        data: {
            stockCode: params.code,
            summary: {
                totalReports: reports.length,
                ratingDistribution: ratingCounts,
                targetPriceRange: priceStats,
                topInstitutions,
                dateRange: reports.length > 0 ? {
                    earliest: reports[reports.length - 1]?.date,
                    latest: reports[0]?.date,
                } : null,
            },
        },
        source: 'akshare',
    };
};

// ========== 注册导出 ==========

export const researchTools: ToolRegistryItem[] = [
    { definition: searchResearchTool, handler: searchResearchHandler },
    { definition: analyzeResearchReportTool, handler: analyzeResearchReportHandler },
    { definition: getResearchSummaryTool, handler: getResearchSummaryHandler },
];
