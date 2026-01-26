import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';
import { buildManagerHelp } from './manager-help.js';

export const macroManagerTool: ToolDefinition = { name: 'macro_manager', description: '宏观经济管理', category: 'market_data', inputSchema: managerSchema, dataSource: 'real' };

export const macroManagerHandler: ToolHandler = async (params: any) => {
    const { action, indicator } = params;
    const help = buildManagerHelp(action, {
        actions: ['get_overview', 'overview', 'get_indicator', 'get_indicators'],
        description: '宏观经济管理入口，action 为空时返回可用动作。',
    });
    if (help) return help;

    const indicatorMap: Record<string, string> = {
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
    const overviewIndicators = [
        { id: 'gdp', name: 'GDP增速' },
        { id: 'cpi', name: 'CPI同比' },
        { id: 'pmi', name: '制造业PMI' },
        { id: 'm2', name: 'M2增速' },
        { id: 'social_finance', name: '社会融资规模' },
    ];

    const fetchIndicator = async (id: string, limit = 12) => {
        const target = indicatorMap[id] || id;
        return callAkshareMcpTool<{
            indicator: string;
            records: Array<{ period: string; value: number | null; yoyChange?: number | null; publishDate?: string | null }>;
        }>('get_macro_indicator', { indicator: target, limit });
    };

    if (action === 'get_overview' || action === 'overview') {
        const results = await Promise.all(
            overviewIndicators.map(async item => ({
                item,
                res: await fetchIndicator(item.id, 6),
            }))
        );
        const data: Record<string, any> = {};
        const missing: string[] = [];
        for (const { item, res } of results) {
            if (!res.success || !res.data?.records?.length) {
                missing.push(item.id);
                continue;
            }
            const record = res.data.records[res.data.records.length - 1];
            data[item.id] = {
                name: item.name,
                value: record.value,
                period: record.period,
                publishDate: record.publishDate || null,
            };
        }
        if (Object.keys(data).length === 0) {
            return { success: false, error: '未获取到宏观概览数据' };
        }
        return {
            success: true,
            data: {
                overview: data,
                partial: missing.length > 0,
                missing,
            },
            source: 'akshare',
        };
    }

    if (action === 'get_indicator' && indicator) {
        const res = await fetchIndicator(String(indicator).toLowerCase(), 24);
        if (!res.success || !res.data) {
            return { success: false, error: res.error || `获取指标失败: ${indicator}` };
        }
        return { success: true, data: res.data, source: 'akshare' };
    }

    if (action === 'get_indicators') {
        const results = await Promise.all(
            overviewIndicators.map(async item => ({
                item,
                res: await fetchIndicator(item.id, 6),
            }))
        );
        const indicators: Array<Record<string, any>> = [];
        const missing: string[] = [];
        for (const { item, res } of results) {
            if (!res.success || !res.data?.records?.length) {
                missing.push(item.id);
                continue;
            }
            const record = res.data.records[res.data.records.length - 1];
            indicators.push({
                id: item.id,
                name: item.name,
                value: record.value,
                period: record.period,
                publishDate: record.publishDate || null,
            });
        }
        if (!indicators.length) {
            return { success: false, error: '未获取到宏观指标列表' };
        }
        return {
            success: true,
            data: {
                indicators,
                partial: missing.length > 0,
                missing,
            },
            source: 'akshare',
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: overview, get_indicator, get_indicators` };
};
