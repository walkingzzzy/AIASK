import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import {
    buildResultContract,
    extractFreshness,
    extractPlatformMeta,
    toText,
    uniqueStrings,
} from '../common/result-contract';

@Injectable()
export class ScreenerService {
    private static readonly SCREENER_TTL_SECONDS = 300; // 5 mins cache for dynamic screens

    constructor(
        private readonly mcp: McpGatewayService,
        private readonly cacheService: CommonCacheService,
    ) { }

    async semanticSearch(query: string, limit = 20) {
        const cacheKey = `screener:semantic:${query}:${limit}`;
        const ttlSeconds = this.cacheService.resolveTtl('screener.semantic', ScreenerService.SCREENER_TTL_SECONDS);

        const cached = await this.cacheService.getWithMeta(cacheKey);
        if (cached.value) {
            return {
                ...cached.value as Record<string, unknown>,
                meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } }
            };
        }

        try {
            const payload = await this.callTool('semantic_stock_search', { query, limit });
            const items = this.extractItems(payload);
            const result = {
                data: {
                    query,
                    items,
                    count: items.length,
                    result: payload,
                    sourceTool: 'semantic_stock_search',
                },
                result_contract: this.buildScreenerResultContract({
                    payload,
                    items,
                    taskLabel: '语义选股',
                    queryLabel: query,
                    sourceTool: 'semantic_stock_search',
                    mode: 'semantic',
                }),
                meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } }
            };
            await this.cacheService.set(cacheKey, result, ttlSeconds);
            return result;
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP semantic_stock_search 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    async conditionScreen(conditions: string[], limit = 50) {
        try {
            const mode = this.resolveConditionMode(conditions);
            let payload: unknown;

            if (mode.kind === 'fundamental') {
                payload = await this.callManager('screen', {
                    criteria: mode.criteria,
                    limit,
                });
            } else if (mode.kind === 'technical') {
                payload = await this.callManager('technical_screen', {
                    conditions: mode.conditions,
                    limit,
                });
            } else {
                payload = await this.callManager('combined_screen', {
                    fundamental_criteria: mode.criteria,
                    tech_conditions: mode.conditions,
                    limit,
                });
            }

            const items = this.extractItems(payload);
            return {
                data: {
                    items,
                    count: items.length,
                    conditions,
                    mode: mode.kind,
                    result: payload,
                    sourceTool: 'screener_manager',
                },
                result_contract: this.buildScreenerResultContract({
                    payload,
                    items,
                    taskLabel: mode.kind === 'technical' ? '技术条件选股' : mode.kind === 'combined' ? '组合条件选股' : '基本面条件选股',
                    queryLabel: conditions.join('；'),
                    sourceTool: 'screener_manager',
                    mode: mode.kind,
                }),
            };
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP screener_manager 条件选股失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    async similarStocks(symbol: string, limit = 10) {
        try {
            const payload = await this.callTool('search_similar_stocks', {
                code: symbol,
                top_n: limit,
                similarity_type: 'both',
            });
            const items = this.extractItems(payload);
            return {
                data: payload,
                items,
                count: items.length,
                sourceTool: 'search_similar_stocks',
                result_contract: this.buildScreenerResultContract({
                    payload,
                    items,
                    taskLabel: '相似股票筛选',
                    queryLabel: symbol,
                    sourceTool: 'search_similar_stocks',
                    mode: 'similar',
                }),
            };
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP search_similar_stocks 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    private async callManager(action: string, payload: Record<string, unknown>) {
        return this.callTool('screener_manager', {
            action,
            params: payload,
        });
    }

    private async callTool(name: string, args: Record<string, unknown>) {
        try {
            const result = await this.mcp.callTool(name, args);
            const toolError = this.extractToolError(result);
            if (toolError) {
                throw new Error(toolError);
            }
            return result;
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: `调用 MCP ${name} 失败`,
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    private extractItems(payload: unknown) {
        const candidates = [
            this.readPath(payload, 'data.items'),
            this.readPath(payload, 'data.results'),
            this.readPath(payload, 'data.matched'),
            this.readPath(payload, 'data.stocks'),
            this.readPath(payload, 'items'),
            this.readPath(payload, 'results'),
            this.readPath(payload, 'matched'),
            this.readPath(payload, 'stocks'),
        ];
        const items = candidates.find(Array.isArray);
        if (!Array.isArray(items)) {
            return [];
        }

        return items.map((raw) => this.normalizeItem(raw)).filter((item) => item.code);
    }

    private normalizeItem(raw: unknown) {
        const record = this.asRecord(raw);
        return {
            ...record,
            code: String(record.code ?? record.stock_code ?? record.symbol ?? ''),
            name: String(record.name ?? record.stock_name ?? record.display_name ?? ''),
            industry: record.industry ?? record.sector ?? null,
            score: record.score ?? record.relevance_score ?? record.rank_score ?? null,
            market_cap: record.market_cap ?? record.marketCap ?? null,
            pe: record.pe ?? record.pe_ratio ?? record.peRatio ?? null,
        };
    }

    private resolveConditionMode(conditions: string[]) {
        const normalized = conditions.map((item) => item.trim()).filter(Boolean);
        const fundamentalCriteria: Record<string, number> = {};
        const technicalConditions: string[] = [];

        for (const condition of normalized) {
            const parsed = this.parseFundamentalCondition(condition);
            if (parsed.kind === 'criteria') {
                Object.assign(fundamentalCriteria, parsed.criteria);
                continue;
            }
            if (parsed.kind === 'technical') {
                technicalConditions.push(parsed.condition);
                continue;
            }
            throw new Error(parsed.message);
        }

        if (technicalConditions.length > 0 && Object.keys(fundamentalCriteria).length > 0) {
            return { kind: 'combined' as const, criteria: fundamentalCriteria, conditions: technicalConditions };
        }
        if (technicalConditions.length > 0) {
            return { kind: 'technical' as const, conditions: technicalConditions };
        }
        return { kind: 'fundamental' as const, criteria: fundamentalCriteria };
    }

    private parseFundamentalCondition(condition: string) {
        const normalized = condition.trim().toLowerCase();
        const match = normalized.match(/^([a-z_]+)\s*(<=|>=|==|=|<|>)\s*(-?\d+(?:\.\d+)?)$/);
        if (!match) {
            return {
                kind: 'technical' as const,
                condition: normalized,
            };
        }

        const [, field, operator, rawValue] = match;
        const value = Number(rawValue);
        if (!Number.isFinite(value)) {
            return {
                kind: 'error' as const,
                message: `无法解析条件数值：${condition}`,
            };
        }

        const criteria: Record<string, number> = {};
        const between = (minKey: string, maxKey: string) => {
            if (operator === '>' || operator === '>=') criteria[minKey] = value;
            else if (operator === '<' || operator === '<=') criteria[maxKey] = value;
            else {
                criteria[minKey] = value;
                criteria[maxKey] = value;
            }
        };

        if (field === 'roe') {
            between('min_roe', 'max_roe');
            return { kind: 'criteria' as const, criteria };
        }
        if (field === 'pe') {
            between('min_pe', 'max_pe');
            return { kind: 'criteria' as const, criteria };
        }
        if (field === 'pb') {
            between('min_pb', 'max_pb');
            return { kind: 'criteria' as const, criteria };
        }
        if (field === 'market_cap') {
            between('min_market_cap', 'max_market_cap');
            return { kind: 'criteria' as const, criteria };
        }
        if (field === 'revenue_growth' && (operator === '>' || operator === '>=' || operator === '=' || operator === '==')) {
            criteria.min_revenue_growth = value;
            return { kind: 'criteria' as const, criteria };
        }
        if (field === 'debt_ratio' && (operator === '<' || operator === '<=' || operator === '=' || operator === '==')) {
            criteria.max_debt_ratio = value;
            return { kind: 'criteria' as const, criteria };
        }

        return {
            kind: 'error' as const,
            message: `当前版本暂不支持条件：${condition}`,
        };
    }

    private extractToolError(payload: unknown): string | null {
        if (typeof payload === 'string') {
            return /error executing tool|validation error/i.test(payload) ? payload : null;
        }
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            return null;
        }
        const record = payload as Record<string, unknown>;
        if (record.success === false) {
            return String(record.error ?? record.message ?? 'screener tool error');
        }
        const nested = [record.data, record.result];
        for (const candidate of nested) {
            if (typeof candidate === 'string' && /error executing tool|validation error/i.test(candidate)) {
                return candidate;
            }
        }
        return null;
    }

    private buildScreenerResultContract(options: {
        payload: unknown;
        items: Array<Record<string, unknown>>;
        taskLabel: string;
        queryLabel: string;
        sourceTool: string;
        mode: 'semantic' | 'fundamental' | 'technical' | 'combined' | 'similar';
    }) {
        const primary = options.items[0] ?? {};
        const primaryCode = toText(primary.code ?? primary.stock_code ?? primary.symbol);
        const primaryName = toText(primary.name ?? primary.stock_name ?? primary.display_name);
        const primaryIndustry = toText(primary.industry ?? primary.sector);
        const followupQuery = primaryName || primaryCode || options.queryLabel;
        const industries = uniqueStrings(
            options.items.slice(0, 8).map((item) => toText(item.industry ?? item.sector)),
        );

        return buildResultContract({
            summary: options.items.length > 0
                ? `${options.taskLabel}“${options.queryLabel}”筛到 ${options.items.length} 只股票，优先结果 ${primaryName || primaryCode || '已命中候选标的'}。`
                : `${options.taskLabel}“${options.queryLabel}”当前没有命中结果，建议调整条件后重试。`,
            availableViews: [
                'summary',
                'next_step',
                ...(options.items.length > 1 ? (['compare'] as const) : []),
                ...(industries.length > 1 ? (['visual'] as const) : []),
            ],
            recommendedActions: [
                {
                    id: 'screener.open-copilot-followup',
                    actionId: 'screener.open-copilot-followup',
                    label: '打开 Copilot 解读筛选结果',
                    description: '把当前筛选结果继续转成研究和排序动作。',
                    payload: {
                        query: options.queryLabel,
                        primaryCode: primaryCode || null,
                    },
                },
            ],
            recommendedLinks: [
                primaryCode
                    ? {
                        id: 'screener-open-stock',
                        label: '个股详情',
                        href: `/stock?code=${encodeURIComponent(primaryCode)}`,
                    }
                    : {
                        id: 'screener-open-research',
                        label: '继续研究页',
                        href: '/research',
                    },
                {
                    id: 'screener-open-skills',
                    label: '去技能中心',
                    href: `/skills?skill=${encodeURIComponent('akshare-fundamental')}`,
                },
                {
                    id: 'screener-open-strategy-market',
                    label: '去策略超市',
                    href: `/strategy-market?from=screener&task=strategy_review&q=${encodeURIComponent(followupQuery)}${primaryIndustry ? `&category=${encodeURIComponent(primaryIndustry)}` : ''}`,
                },
                {
                    id: 'screener-open-factory',
                    label: '去工厂运行态',
                    href: `/strategy-market?from=screener&task=factory_cycle&q=${encodeURIComponent(followupQuery)}${primaryIndustry ? `&category=${encodeURIComponent(primaryIndustry)}` : ''}`,
                },
            ],
            evidence: [
                { label: '结果数', value: String(options.items.length) },
                { label: '模式', value: options.mode },
                primaryCode ? { label: '优先代码', value: primaryCode } : null,
                primaryName ? { label: '优先结果', value: primaryName } : null,
                primaryIndustry ? { label: '所属行业', value: primaryIndustry } : null,
            ].filter((item): item is NonNullable<typeof item> => item != null),
            riskNotes: options.items.length > 0 ? [] : ['当前筛选结果为空，建议缩短条件、降低约束或切换到语义选股。'],
            freshness: extractFreshness(options.payload, null, `${options.taskLabel}结果`),
            platformMeta: extractPlatformMeta(options.payload, {
                sourceTool: options.sourceTool,
                referencePath: '/data/tool-catalog',
            }),
            skillSuggestions: [
                {
                    skillId: 'akshare-fundamental',
                    label: '基本面快照',
                    reason: '继续补齐当前候选股票的基本面证据。',
                    supportedTask: 'fundamental_snapshot',
                },
                {
                    skillId: 'akshare-portfolio-manager-core',
                    label: '组合闭环评估',
                    reason: '把筛选结果继续转成组合候选池。',
                    supportedTask: 'closed_loop_plan',
                },
                {
                    skillId: 'akshare-strategy-factory',
                    label: '策略工厂联动',
                    reason: '把筛选结果带到策略工厂继续评审与跟踪。',
                    supportedTask: 'strategy_review',
                },
            ],
            strategySuggestions: [
                {
                    id: `${options.sourceTool}-strategy-followup`,
                    label: '去策略超市继续研究',
                    description: '把当前选股结果转到策略页继续筛选与跟踪。',
                    query: followupQuery,
                    category: primaryIndustry || undefined,
                    task: 'strategy_review',
                },
                {
                    id: `${options.sourceTool}-factory-followup`,
                    label: '去工厂看运行态',
                    description: '把当前选股结果带到策略工厂运行态继续跟踪。',
                    query: followupQuery,
                    category: primaryIndustry || undefined,
                    task: 'factory_cycle',
                },
            ],
            workbenchTask: {
                title: `${options.taskLabel}：${options.queryLabel}`,
                href: '/screener',
                kind: 'screener-result',
                payload: {
                    query: options.queryLabel,
                    sourceTool: options.sourceTool,
                    primaryCode: primaryCode || null,
                    primaryIndustry: primaryIndustry || null,
                },
            },
        });
    }

    private asRecord(value: unknown): Record<string, unknown> {
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            return {};
        }
        return value as Record<string, unknown>;
    }

    private readPath(value: unknown, path: string): unknown {
        return path.split('.').reduce<unknown>((acc, key) => {
            if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
                return undefined;
            }
            return (acc as Record<string, unknown>)[key];
        }, value);
    }
}
