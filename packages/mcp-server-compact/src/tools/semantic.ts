/**
 * 语义分析工具
 * 自然语言选股等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { nlpQueryParser } from '../services/nlp-query-parser.js';
import { adapterManager } from '../adapters/index.js';

// ========== parse_selection_query ==========


const parseSelectionQuerySchema = z.object({
    query: z.string().describe('自然语言选股查询，例如 "高股息低估值的银行股"'),
});

const parseSelectionQueryTool: ToolDefinition = {
    name: 'parse_selection_query',
    description: '解析自然语言选股条件',
    category: 'semantic',
    inputSchema: parseSelectionQuerySchema,
    tags: ['nlp', 'search'],
    dataSource: 'calculated',
};

const parseSelectionQueryHandler: ToolHandler<z.infer<typeof parseSelectionQuerySchema>> = async (params) => {
    const result = nlpQueryParser.parseQuery(params.query);

    return {
        success: true,
        data: result,
        source: 'nlp_parser',
    };
};

// ========== get_industry_chain ==========

const getIndustryChainSchema = z.object({
    keyword: z.string().optional().describe('搜索关键词'),
    chainId: z.string().optional().describe('产业链ID'),
});

const getIndustryChainTool: ToolDefinition = {
    name: 'get_industry_chain',
    description: '获取产业链数据（上下游关系）',
    category: 'semantic',
    inputSchema: getIndustryChainSchema,
    tags: ['industry', 'chain'],
    dataSource: 'static',
};

const getIndustryChainHandler: ToolHandler<z.infer<typeof getIndustryChainSchema>> = async (params) => {
    // 这里调用 services/industry-chain.js
    // 为了节省时间，直接 mock 调用
    // 实际应该 import * as ChainServices from '../services/industry-chain.js'

    const { getAllChains, searchChainByKeyword, getChainDetail } = await import('../services/industry-chain.js');

    if (params.chainId) {
        const detail = getChainDetail(params.chainId);
        return { success: true, data: detail, source: 'knowledge_base' };
    }

    if (params.keyword) {
        const results = searchChainByKeyword(params.keyword);
        return { success: true, data: results, source: 'knowledge_base' };
    }

    return {
        success: true,
        data: getAllChains(),
        source: 'knowledge_base',
    };
};


// ========== 智能诊股 ==========

const smartDiagnosisSchema = z.object({
    stock_code: z.string().describe('股票代码，如 000001'),
});

const smartDiagnosisTool: ToolDefinition = {
    name: 'smart_stock_diagnosis',
    description: '全方位分析个股基本面和技术面，提供综合诊断',
    category: 'semantic',
    inputSchema: smartDiagnosisSchema,
    tags: ['diagnosis', 'comprehensive'],
    dataSource: 'real',
};

const smartDiagnosisHandler: ToolHandler<z.infer<typeof smartDiagnosisSchema>> = async (params) => {
    const code = params.stock_code;

    // 1. 获取实时行情
    const quoteRes = await adapterManager.getRealtimeQuote(code);
    if (!quoteRes.success || !quoteRes.data) {
        return { success: false, error: `无法获取 ${code} 行情数据` };
    }
    const quote = quoteRes.data;

    // 2. 获取K线数据 (用于趋势分析)
    const klineRes = await adapterManager.getKline(code, '101', 60); // 近60日
    const klines = (klineRes.success && klineRes.data) ? klineRes.data : [];

    // 3. 生成诊断报告
    const scores: string[] = [];
    let signal = 'neutral';

    // 价格趋势分析
    let trend = '震荡';
    if (klines.length >= 20) {
        const closes = klines.map((k: any) => k.close);
        const lastClose = closes[closes.length - 1];
        const ma20 = closes.slice(-20).reduce((a: any, b: any) => a + b, 0) / 20;
        const ma60 = klines.length >= 60 ? closes.slice(-60).reduce((a: any, b: any) => a + b, 0) / 60 : ma20;

        if (lastClose > ma20 && ma20 > ma60) {
            trend = '上升趋势 (MA20 > MA60)';
            scores.push('✅ 技术面：短期均线呈多头排列，趋势向上');
            signal = 'buy';
        } else if (lastClose < ma20 && ma20 < ma60) {
            trend = '下降趋势 (MA20 < MA60)';
            scores.push('⚠️ 技术面：短期均线呈空头排列，趋势向下');
            signal = 'sell';
        } else {
            scores.push('➖ 技术面：均线纠缠，处于震荡区间');
        }
    }

    // 涨跌幅分析
    if ((quote.changePercent || 0) > 5) {
        scores.push('🔥 热度：今日大涨，市场关注度高');
    } else if ((quote.changePercent || 0) < -5) {
        scores.push('❄️ 热度：今日大跌，需警惕风险');
    }

    // 估值提示 (仅作为示例，实际需要 PE/PB 数据)
    // 假设 quote 中有 pe (实际上 standard quote 可能没有，这里做安全访问)
    const pe = (quote as any).pe || (quote as any).pe_ttm;
    if (pe) {
        if (pe < 10 && pe > 0) scores.push('💰 估值：PE较低，具备防御价值');
        else if (pe > 50) scores.push('⚠️ 估值：PE较高，需关注成长性是否匹配');
    }

    const report = `
【${quote.name} (${code}) 智能诊断报告】
当前价格: ${quote.price} (${quote.changePercent}%)
趋势判断: ${trend}

${scores.join('\n')}

综合建议: ${signal === 'buy' ? '偏向看多' : signal === 'sell' ? '偏向看空' : '观望为主'}
    `.trim();

    return {
        success: true,
        data: {
            stock_code: code,
            name: quote.name,
            diagnosis: report,
            details: {
                trend,
                scores
            }
        },
        source: 'rule_based_analysis_v1',
    };
};

// ========== 生成日报 ==========

const dailyReportSchema = z.object({
    date: z.string().optional().describe('日期 (默认今天)'),
});

const dailyReportTool: ToolDefinition = {
    name: 'generate_daily_report',
    description: '自动生成每日市场复盘报告',
    category: 'semantic',
    inputSchema: dailyReportSchema,
    tags: ['report', 'daily'],
    dataSource: 'real',
};

const dailyReportHandler: ToolHandler<z.infer<typeof dailyReportSchema>> = async (params) => {
    const reportDate = params.date || new Date().toISOString().split('T')[0];
    const [indicesRes, sectorRes, northRes, limitUpRes, dragonRes] = await Promise.all([
        adapterManager.getBatchQuotes(['000001', '399001', '399006']),
        adapterManager.getSectorFlow(10),
        adapterManager.getNorthFund(1),
        adapterManager.getLimitUpStatistics(reportDate),
        adapterManager.getDragonTiger(reportDate),
    ]);

    const indices = indicesRes.success && indicesRes.data ? indicesRes.data : [];
    const sectors = sectorRes.success && sectorRes.data ? sectorRes.data : [];
    const northItems = northRes.success && northRes.data ? northRes.data : [];
    const limitStats = limitUpRes.success && limitUpRes.data
        ? limitUpRes.data
        : { totalLimitUp: 0, limitDown: 0, successRate: null };
    const dragonTiger = dragonRes.success && dragonRes.data ? dragonRes.data : [];

    const indexSummary = indices.map((i: any) => ({
        code: i.code,
        name: i.name,
        changePercent: i.changePercent,
        price: i.price,
    }));

    const topInflow = sectors.slice(0, 5).map((s: any) => ({ name: s.name, netInflow: s.netInflow, changePercent: s.changePercent }));
    const topOutflow = [...sectors].sort((a: any, b: any) => (a.netInflow || 0) - (b.netInflow || 0)).slice(0, 5)
        .map((s: any) => ({ name: s.name, netInflow: s.netInflow, changePercent: s.changePercent }));

    const northFund = northItems.length > 0 ? northItems[0] : null;

    const summary = [
        `指数表现：${indexSummary.map((i: any) => `${i.name} ${i.changePercent?.toFixed?.(2) ?? i.changePercent}%`).join(' / ') || '缺少指数数据'}`,
        `板块资金：净流入前五 ${topInflow.map((s: any) => s.name).join('、') || '缺少数据'}`,
        `北向资金：${northFund ? `${northFund.total} 亿元` : '缺少数据'}`,
        `涨停统计：${limitStats.totalLimitUp ?? 0} 只涨停，${limitStats.limitDown ?? 0} 只跌停`,
    ].join('\n');

    return {
        success: true,
        data: {
            date: reportDate,
            summary,
            sections: {
                indices: indexSummary,
                sectorFlow: {
                    topInflow,
                    topOutflow,
                },
                northFund,
                limitUp: limitStats,
                dragonTiger: dragonTiger.slice(0, 10),
            },
        },
        source: 'aggregated',
    };
};

// ========== 注册导出 ==========

export const semanticTools: ToolRegistryItem[] = [
    { definition: parseSelectionQueryTool, handler: parseSelectionQueryHandler },
    { definition: getIndustryChainTool, handler: getIndustryChainHandler },
    { definition: smartDiagnosisTool, handler: smartDiagnosisHandler },
    { definition: dailyReportTool, handler: dailyReportHandler },
];
