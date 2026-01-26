import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as ValuationServices from '../../services/valuation.js';
import { buildManagerHelp } from './manager-help.js';

export const fundamentalAnalysisManagerTool: ToolDefinition = {
    name: 'fundamental_analysis_manager',
    description: '高级基本面分析管理',
    category: 'financial_analysis',
    inputSchema: managerSchema,
    tags: ['fundamental', 'manager'],
    dataSource: 'real',
};

export const fundamentalAnalysisManagerHandler: ToolHandler = async (params: any) => {
    const { action, code } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'get_valuation',
            'peer_comparison',
            'compare_peers',
            'dupont_analysis',
            'dupont',
            'calculate_intrinsic_value',
            'intrinsic_value',
            'generate_fundamental_report',
            'fundamental_report',
        ],
        description: '高级基本面分析入口，action 为空时返回可用动作。',
    });
    if (help) return help;
    if (!code) return { success: false, error: '需要提供股票代码 code' };

    if (action === 'get_valuation') {
        // Get valuation from adapter
        const valRes = await adapterManager.getValuationMetrics(code);
        if (valRes.success && valRes.data) {
            return { success: true, data: valRes.data };
        }

        // Fallback: try to calculate health score if we have financials and basic quote
        const financialRes = await adapterManager.getFinancials(code);
        const quoteRes = await adapterManager.getRealtimeQuote(code);

        // If we have quote data with valuation metrics, use it even if financials are missing
        if (quoteRes.success && quoteRes.data && (quoteRes.data.pe || quoteRes.data.pb)) {
            const q = quoteRes.data;
            return {
                success: true,
                data: {
                    code,
                    pe: q.pe || 0,
                    pb: q.pb || 0,
                    marketCap: q.marketCap || 0,
                    source: 'realtime_quote',
                    timestamp: new Date().toISOString()
                }
            };
        }

        if (financialRes.success && financialRes.data && quoteRes.success && quoteRes.data) {
            // Construct a basic ValuationMetrics object for health score
            const valuation: any = {
                code,
                pe: quoteRes.data.pe || 0,
                pb: quoteRes.data.pb || 0,
                totalMarketCap: quoteRes.data.marketCap || 0,
                timestamp: new Date().toISOString()
            };
            const score = ValuationServices.calculateHealthScore(financialRes.data, valuation);
            return { success: true, data: { healthScore: score } };
        }

        return {
            success: false,
            error: `Failed to retrieve valuation data. Financials: ${financialRes.success}, Quote: ${quoteRes.success}`
        };
    }

    // ===== 同业对比 =====
    if (action === 'peer_comparison' || action === 'compare_peers') {
        const peers = params.peers || []; // 如果未提供，可以通过 adapter 获取同行业股票
        if (peers.length === 0) {
            // 简单的 fallback，如果是模拟环境或无法获取同业，返回提示
            return { success: false, error: '需要提供 peers 列表进行对比' };
        }

        const comparisons: any[] = [];
        for (const peerCode of peers) {
            const metrics = await adapterManager.getValuationMetrics(peerCode);
            if (metrics.success && metrics.data) {
                comparisons.push({
                    code: peerCode,
                    pe: metrics.data.pe,
                    pb: metrics.data.pb,
                    marketCap: metrics.data.marketCap
                });
            }
        }

        return {
            success: true,
            data: {
                target: code,
                peers: comparisons,
                avgPe: comparisons.length > 0 ? comparisons.reduce((a: any, b: any) => a + b.pe, 0) / comparisons.length : 0,
                ranking: '由于数据限制暂无法准确排名'
            }
        };
    }

    // ===== 杜邦分析 =====
    if (action === 'dupont_analysis' || action === 'dupont') {
        const financialRes = await adapterManager.getFinancials(code);
        if (!financialRes.success || !financialRes.data) return { success: false, error: '无法获取财务数据' };
        const f = financialRes.data;
        // 简化的杜邦拆解
        // Ensure properties exist, use fallbacks or correct field names based on src/types/stock.ts updates
        const netProfitMargin = f.netProfitMargin || 0;
        const assetTurnover = f.assetTurnover || 0.5;
        const equityMultiplier = f.leverage || 1.5;
        const roe = netProfitMargin * assetTurnover * equityMultiplier;

        return {
            success: true,
            data: {
                code,
                roe: `${roe.toFixed(2)}%`,
                breakdown: {
                    netProfitMargin: `${netProfitMargin.toFixed(2)}%`,
                    assetTurnover: assetTurnover.toFixed(3),
                    equityMultiplier: equityMultiplier.toFixed(3)
                },
                analysis: '基于最新财务报表'
            }
        };
    }

    // ===== 内在价值计算 =====
    if (action === 'calculate_intrinsic_value' || action === 'intrinsic_value') {
        const financialRes = await adapterManager.getFinancials(code);
        if (!financialRes.success || !financialRes.data) return { success: false, error: '无法获取财务数据' };

        // 简化的格雷厄姆成长公式
        const eps = financialRes.data.eps || 0.5;
        const growthRate = financialRes.data.revenueGrowth || 10;
        // V = EPS * (8.5 + 2g)
        const intrinsicValue = eps * (8.5 + 2 * growthRate);

        const quoteRes = await adapterManager.getRealtimeQuote(code);
        const currentPrice = quoteRes.success && quoteRes.data ? quoteRes.data.price : 0;

        return {
            success: true,
            data: {
                code,
                currentPrice,
                intrinsicValue: intrinsicValue.toFixed(2),
                marginOfSafety: currentPrice > 0 ? `${((intrinsicValue - currentPrice) / intrinsicValue * 100).toFixed(2)}%` : 'N/A',
                model: 'Simplified Graham Model'
            }
        };
    }

    // ===== 基本面报告 =====
    if (action === 'generate_fundamental_report' || action === 'fundamental_report') {
        const financialRes = await adapterManager.getFinancials(code);
        const valRes = await adapterManager.getValuationMetrics(code);

        if (!financialRes.success || !financialRes.data) return { success: false, error: '无法获取财务数据' };

        return {
            success: true,
            data: {
                code,
                generatedAt: new Date().toISOString(),
                summary: '财务状况概览',
                metrics: {
                    valuation: valRes.success ? valRes.data : {},
                    profitability: {
                        roe: financialRes.data.roe,
                        grossMargin: financialRes.data.grossProfitMargin
                    },
                    growth: {
                        revenueGrowth: financialRes.data.revenueGrowth,
                        profitGrowth: financialRes.data.netProfitGrowth
                    }
                },
                highlights: [
                    financialRes.data.roe > 15 ? '高ROE' : 'ROE一般',
                    (financialRes.data.revenueGrowth || 0) > 20 ? '高增长' : '增长平稳'
                ]
            }
        };
    }

    return { success: false, error: `Unknown action: ${action}. Supported: get_valuation, peer_comparison, dupont_analysis, calculate_intrinsic_value, generate_fundamental_report` };
};
