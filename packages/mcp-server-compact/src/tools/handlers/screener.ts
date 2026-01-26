import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { screenStocks } from '../../storage/screener-data.js';
import { NLPQueryParser } from '../../services/nlp-query-parser.js';

const nlpParser = new NLPQueryParser();

export const screenerManagerTool: ToolDefinition = {
    name: 'screener_manager',
    description: '选股器管理（NLP解析、数据库筛选、实时行情筛选）',
    category: 'screener',
    inputSchema: managerSchema,
    tags: ['screener', 'filter', 'nlp'],
    dataSource: 'real'
};

export const screenerManagerHandler: ToolHandler = async (params: any) => {
    const { action, query, conditions, limit = 10 } = params; // 默认从20降到10
    // 数据库筛选条件
    const { peMin, peMax, pbMin, pbMax, roeMin, roeMax, grossMarginMin, netMarginMin, revenueGrowthMin, profitGrowthMin, marketCapMin, marketCapMax, sector } = params;

    // ===== 解析自然语言 =====
    if (action === 'parse_query' || action === 'parse') {
        if (!query) return { success: false, error: '缺少查询语句' };
        const parsed = nlpParser.parseQuery(query);
        return { success: true, data: parsed };
    }

    // ===== 数据库筛选（基于财务/估值数据） =====
    if (action === 'db_screen' || action === 'fundamental_screen') {
        const criteria: any = {};
        if (peMin !== undefined) criteria.peMin = peMin;
        if (peMax !== undefined) criteria.peMax = peMax;
        if (pbMin !== undefined) criteria.pbMin = pbMin;
        if (pbMax !== undefined) criteria.pbMax = pbMax;
        if (roeMin !== undefined) criteria.roeMin = roeMin;
        if (roeMax !== undefined) criteria.roeMax = roeMax;
        if (grossMarginMin !== undefined) criteria.grossMarginMin = grossMarginMin;
        if (netMarginMin !== undefined) criteria.netMarginMin = netMarginMin;
        if (revenueGrowthMin !== undefined) criteria.revenueGrowthMin = revenueGrowthMin;
        if (profitGrowthMin !== undefined) criteria.profitGrowthMin = profitGrowthMin;
        if (marketCapMin !== undefined) criteria.marketCapMin = marketCapMin;
        if (marketCapMax !== undefined) criteria.marketCapMax = marketCapMax;
        if (sector) criteria.sector = sector;

        if (Object.keys(criteria).length === 0) {
            return { success: false, error: '请提供至少一个筛选条件: peMin, peMax, pbMin, pbMax, roeMin, roeMax, grossMarginMin, netMarginMin, revenueGrowthMin, profitGrowthMin, marketCapMin, marketCapMax, sector' };
        }

        const results = await screenStocks(criteria, limit);
        return {
            success: true,
            data: {
                results,
                total: results.length,
                criteria,
                source: 'database',
            }
        };
    }

    // ===== 实时行情筛选 =====
    if (action === 'screen' || action === 'filter' || action === 'screening') {
        // 使用 NLP 解析自然语言查询
        let parsedConditions = conditions;
        let nlpDbCriteria: any = {};
        let nlpSector: string | undefined;

        if (query && !conditions) {
            const parsed = nlpParser.parseQuery(query);
            parsedConditions = parsed.conditions;

            // 从NLP解析结果中提取数据库筛选条件
            for (const cond of parsed.conditions) {
                if (cond.category === 'fundamental') {
                    const field = cond.field;
                    const value = cond.value as number;

                    // 映射NLP字段到数据库筛选参数
                    if (field === 'pe') {
                        if (cond.operator === '<' || cond.operator === '<=') nlpDbCriteria.peMax = value;
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.peMin = value;
                    }
                    if (field === 'pb') {
                        if (cond.operator === '<' || cond.operator === '<=') nlpDbCriteria.pbMax = value;
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.pbMin = value;
                    }
                    if (field === 'roe') {
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.roeMin = value;
                        if (cond.operator === '<' || cond.operator === '<=') nlpDbCriteria.roeMax = value;
                    }
                    if (field === 'gross_margin') {
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.grossMarginMin = value;
                    }
                    if (field === 'net_margin') {
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.netMarginMin = value;
                    }
                    if (field === 'revenue_growth') {
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.revenueGrowthMin = value / 100;
                    }
                    if (field === 'profit_growth') {
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.profitGrowthMin = value / 100;
                    }
                    if (field === 'market_cap') {
                        if (cond.operator === '<' || cond.operator === '<=') nlpDbCriteria.marketCapMax = value * 100000000;
                        if (cond.operator === '>' || cond.operator === '>=') nlpDbCriteria.marketCapMin = value * 100000000;
                    }
                    if (field === 'sector' && cond.operator === 'in') {
                        nlpSector = (cond.value as string[])[0];
                    }
                }
            }
        }

        // 合并用户直接提供的条件和NLP解析出的条件
        const finalCriteria = {
            peMin: peMin ?? nlpDbCriteria.peMin,
            peMax: peMax ?? nlpDbCriteria.peMax,
            pbMin: pbMin ?? nlpDbCriteria.pbMin,
            pbMax: pbMax ?? nlpDbCriteria.pbMax,
            roeMin: roeMin ?? nlpDbCriteria.roeMin,
            roeMax: roeMax ?? nlpDbCriteria.roeMax,
            grossMarginMin: grossMarginMin ?? nlpDbCriteria.grossMarginMin,
            netMarginMin: netMarginMin ?? nlpDbCriteria.netMarginMin,
            revenueGrowthMin: revenueGrowthMin ?? nlpDbCriteria.revenueGrowthMin,
            profitGrowthMin: profitGrowthMin ?? nlpDbCriteria.profitGrowthMin,
            marketCapMin: marketCapMin ?? nlpDbCriteria.marketCapMin,
            marketCapMax: marketCapMax ?? nlpDbCriteria.marketCapMax,
            sector: sector ?? nlpSector,
        };

        // 清除undefined值
        Object.keys(finalCriteria).forEach((key: any) => {
            if ((finalCriteria as any)[key] === undefined) {
                delete (finalCriteria as any)[key];
            }
        });

        // 检查是否有任何有效的筛选条件
        const hasFundamentalCriteria = Object.keys(finalCriteria).length > 0;

        let candidateCodes: string[] = [];

        if (hasFundamentalCriteria) {
            // 使用数据库筛选
            const dbResults = await screenStocks(finalCriteria, 100);
            candidateCodes = dbResults.map((r: any) => r.code);

            // 如果数据库有结果，直接返回
            if (dbResults.length > 0) {
                return {
                    success: true,
                    data: {
                        results: dbResults.slice(0, limit).map((r: any) => ({
                            code: r.code,
                            name: r.name,
                            pe: r.pe,
                            pb: r.pb,
                            roe: r.roe,
                            sector: r.sector,
                        })),
                        total: dbResults.length,
                        displayed: Math.min(dbResults.length, limit),
                        criteria: finalCriteria,
                        parsedConditions,
                        source: 'database',
                    }
                };
            }
        } else {
            // 没有fundamental条件时，从涨停板/龙虎榜获取候选（仅用于技术面筛选）
            const [limitUp, dragon] = await Promise.all([
                adapterManager.getLimitUpStocks(),
                adapterManager.getDragonTiger()
            ]);
            const candidates = new Set<string>();
            if (limitUp.success && limitUp.data) limitUp.data.forEach((s: any) => candidates.add(s.code));
            if (dragon.success && dragon.data) dragon.data.forEach((s: any) => candidates.add(s.code));
            candidateCodes = Array.from(candidates).slice(0, 100);
        }

        if (candidateCodes.length === 0) {
            return { success: true, data: { results: [], message: '未找到符合条件的股票', criteria: finalCriteria, parsedConditions } };
        }

        // 获取实时行情
        const quotesRes = await adapterManager.getBatchQuotes(candidateCodes);
        if (!quotesRes.success || !quotesRes.data) {
            return { success: false, error: '获取行情数据失败' };
        }

        // 根据技术条件筛选
        let results = quotesRes.data;
        if (parsedConditions && parsedConditions.length > 0) {
            for (const cond of parsedConditions) {
                results = results.filter((q: any) => {
                    const fieldValue = q[cond.field] ?? q.changePercent ?? q.turnoverRate;
                    if (fieldValue === undefined) return true;
                    if (cond.operator === '>') return fieldValue > cond.value;
                    if (cond.operator === '<') return fieldValue < cond.value;
                    if (cond.operator === '>=') return fieldValue >= cond.value;
                    if (cond.operator === '<=') return fieldValue <= cond.value;
                    if (cond.operator === '=') return fieldValue === cond.value;
                    return true;
                });
            }
        }

        return {
            success: true,
            data: {
                results: results.slice(0, limit).map((q: any) => ({
                    code: q.code,
                    name: q.name,
                    price: parseFloat(q.price?.toFixed(2) || 0),
                    changePercent: parseFloat(q.changePercent?.toFixed(2) || 0),
                    turnoverRate: parseFloat(q.turnoverRate?.toFixed(2) || 0),
                })),
                total: results.length,
                displayed: Math.min(results.length, limit),
                parsedConditions,
                source: hasFundamentalCriteria ? 'database+realtime' : 'realtime',
            }
        };
    }

    // ===== 预设策略筛选 =====
    if (action === 'preset' || action === 'strategy' || action === 'list') {
        const presetName = params.preset || params.strategy;
        const presets: Record<string, any> = {
            'value': { peMax: 15, pbMax: 2, roeMin: 10, description: '价值股：低PE低PB高ROE' },
            'growth': { revenueGrowthMin: 20, profitGrowthMin: 20, roeMin: 15, description: '成长股：高增长高ROE' },
            'dividend': { peMax: 20, roeMin: 10, description: '高股息：低估值稳定盈利' },
            'small_cap': { marketCapMax: 10000000000, roeMin: 10, description: '小盘股：市值小于100亿' },
            'large_cap': { marketCapMin: 100000000000, description: '大盘蓝筹：市值大于1000亿' },
        };
        if (!presetName || !presets[presetName]) {
            return { success: true, data: { presets: Object.entries(presets).map(([k, v]) => ({ name: k, ...v })) } };
        }
        const criteria = presets[presetName];
        const results = await screenStocks(criteria, limit);
        return { success: true, data: { results, total: results.length, preset: presetName, criteria, source: 'database' } };
    }

    if (action === 'suggestions' || action === 'help') {
        const suggestions = nlpParser.generateSuggestions(query || '');
        return { success: true, data: { suggestions } };
    }

    return { success: false, error: `未知操作: ${action}` };
};
