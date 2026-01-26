/**
 * 宏观经济工具
 * 宏观指标、经济日历等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { callAkshareMcpTool } from '../adapters/akshare-mcp-client.js';

// ========== get_macro_indicator ==========

const getMacroIndicatorSchema = z.object({
    indicator: z.enum([
        'gdp',           // GDP
        'cpi',           // CPI
        'ppi',           // PPI
        'pmi',           // PMI
        'm2',            // M2货币供应
        'social_finance', // 社会融资规模
        'interest_rate', // 利率
        'exchange_rate', // 汇率
        'employment',    // 就业数据
    ]).describe('宏观指标类型'),
    limit: z.number().optional().default(12).describe('返回数据条数'),
});

const getMacroIndicatorTool: ToolDefinition = {
    name: 'get_macro_indicator',
    description: '获取宏观经济指标（GDP、CPI、PMI等）',
    category: 'macro',
    inputSchema: getMacroIndicatorSchema,
    tags: ['macro', 'indicator', 'economy'],
    dataSource: 'real',
};

const indicatorMapping: Record<string, string> = {
    gdp: 'gdp',
    cpi: 'cpi',
    ppi: 'ppi',
    pmi: 'pmi',
    m2: 'm2',
    social_finance: 'social_finance',
    interest_rate: 'interest_rate',
    exchange_rate: 'exchange_rate',
    employment: 'employment',
};

const getMacroIndicatorHandler: ToolHandler<z.infer<typeof getMacroIndicatorSchema>> = async (params) => {
    // 调用 akshare-mcp 的 get_macro_indicator
    const result = await callAkshareMcpTool<{
        indicator: string;
        records: Array<{
            period: string;
            value: number | null;
            yoyChange?: number | null;
            momChange?: number | null;
            publishDate?: string | null;
        }>;
    }>('get_macro_indicator', {
        indicator: indicatorMapping[params.indicator] || params.indicator,
        limit: params.limit,
    });

    if (!result.success) {
        return {
            success: true,
            data: {
                indicator: indicatorMapping[params.indicator] || params.indicator,
                records: [],
            },
            error: result.error || `获取宏观指标 ${params.indicator} 失败`,
            degraded: true,
        };
    }

    return {
        success: true,
        data: result.data,
        source: 'akshare',
    };
};

// ========== get_economic_calendar ==========

const normalizeCountry = (value: unknown) => {
    if (typeof value !== 'string') return value;
    const normalized = value.trim().toLowerCase();
    if (['cn', 'china', 'zh', 'zh-cn', '中国'].includes(normalized)) return 'cn';
    if (['us', 'usa', '美国'].includes(normalized)) return 'us';
    if (['all', '全部'].includes(normalized)) return 'all';
    return normalized;
};

const normalizeImportance = (value: unknown) => {
    if (typeof value !== 'string') return value;
    const normalized = value.trim().toLowerCase();
    if (['high', '高', '重要', '重点'].includes(normalized)) return 'high';
    if (['medium', '中', '中等'].includes(normalized)) return 'medium';
    if (['all', '全部'].includes(normalized)) return 'all';
    return normalized;
};

const getEconomicCalendarSchema = z.object({
    days: z.number().optional().default(7).describe('未来天数'),
    country: z.preprocess(normalizeCountry, z.enum(['cn', 'us', 'all'])).optional().default('cn').describe('国家/地区'),
    importance: z.preprocess(normalizeImportance, z.enum(['all', 'high', 'medium'])).optional().default('all').describe('重要性筛选'),
});

const getEconomicCalendarTool: ToolDefinition = {
    name: 'get_economic_calendar',
    description: '获取经济日历（重要数据发布时间表）',
    category: 'macro',
    inputSchema: getEconomicCalendarSchema,
    tags: ['macro', 'calendar', 'events'],
    dataSource: 'real',
};

const getEconomicCalendarHandler: ToolHandler<z.infer<typeof getEconomicCalendarSchema>> = async (params) => {
    const today = new Date();
    const country = params.country;
    if (country !== 'cn' && country !== 'all') {
        return {
            success: true,
            data: {
                startDate: new Date(today.getTime() - params.days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
                endDate: today.toISOString().slice(0, 10),
                country,
                importance: params.importance,
                events: [],
                total: 0,
                note: '当前仅支持中国宏观发布记录，其他国家数据源未接入',
            },
            source: 'akshare',
        };
    }

    const indicatorEvents = [
        { indicator: 'pmi', name: 'PMI', importance: 'high' },
        { indicator: 'cpi', name: 'CPI', importance: 'high' },
        { indicator: 'ppi', name: 'PPI', importance: 'medium' },
        { indicator: 'gdp', name: 'GDP', importance: 'high' },
        { indicator: 'm2', name: 'M2', importance: 'medium' },
        { indicator: 'social_finance', name: '社会融资规模', importance: 'medium' },
    ];

    const parseDate = (value: string | null | undefined) => {
        if (!value) return null;
        const raw = String(value).trim();
        if (!raw) return null;
        const normalized = raw.length >= 10 ? raw.slice(0, 10) : raw;
        const date = new Date(normalized.replace(/\\./g, '-'));
        return Number.isNaN(date.getTime()) ? null : date;
    };

    const cutoff = new Date(today);
    cutoff.setDate(today.getDate() - params.days);

    const responses = await Promise.all(
        indicatorEvents.map(async item => ({
            item,
            res: await callAkshareMcpTool<{
                indicator: string;
                records: Array<{ period: string; value: number | null; publishDate?: string | null }>;
            }>('get_macro_indicator', { indicator: item.indicator, limit: 24 }),
        }))
    );

    const events: Array<Record<string, any>> = [];
    for (const { item, res } of responses) {
        if (!res.success || !res.data?.records?.length) {
            continue;
        }
        for (const record of res.data.records) {
            const date = parseDate(record.publishDate || record.period);
            if (!date) continue;
            if (date < cutoff || date > today) continue;
            if (params.importance !== 'all' && item.importance !== params.importance) continue;
            events.push({
                date: date.toISOString().slice(0, 10),
                name: item.name,
                country: '中国',
                importance: item.importance,
                value: record.value,
                indicator: item.indicator,
            });
        }
    }

    events.sort((a: any, b: any) => String(a.date).localeCompare(String(b.date)));

    return {
        success: true,
        data: {
            startDate: cutoff.toISOString().slice(0, 10),
            endDate: today.toISOString().slice(0, 10),
            country,
            importance: params.importance,
            events,
            total: events.length,
            note: '返回最近发布记录（未接入真实未来日历）',
        },
        source: 'akshare',
    };
};

// ========== 注册导出 ==========

export const macroTools: ToolRegistryItem[] = [
    { definition: getMacroIndicatorTool, handler: getMacroIndicatorHandler },
    { definition: getEconomicCalendarTool, handler: getEconomicCalendarHandler },
];
