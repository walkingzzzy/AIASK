/**
 * 主应用组件 - 集成会话管理和对话历史
 */

import React, { useState, useEffect, useRef } from 'react';
import ChatPanel from './components/chat/ChatPanel';
import SessionSidebar from './components/chat/SessionSidebar';
import VisualizationRenderer from './components/visualization/VisualizationRenderer';
import SettingsModal from './components/settings/SettingsModal';
import WorkbenchModal from './components/workbench/WorkbenchModal';
import { ChatMessage, Visualization } from '../shared/types';

type ToolResult = {
    success: boolean;
    data?: unknown;
    error?: string;
    source?: string;
    quality?: string;
    degraded?: boolean;
    validationErrors?: unknown;
    requiresConfirmation?: boolean;
    confirmation?: {
        toolName: string;
        arguments?: Record<string, unknown>;
        message?: string;
    };
};

type ToolStep = {
    name: string;
    args: Record<string, unknown>;
    label: string;
    visualizationType?: Visualization['type'];
    executor?: 'mcp' | 'local';
    collectKey?: string;
    silent?: boolean;
};

type ToolPlan = {
    title?: string;
    steps: ToolStep[];
    combineId?: 'fundFlow';
    deepAnalysis?: boolean;
};

type MCPToolSchema = {
    properties?: Record<string, { type?: string; description?: string }>;
    required?: string[];
};

type MCPToolDefinition = {
    name: string;
    description?: string;
    inputSchema?: MCPToolSchema;
    category?: string;
    requiresConfirmation?: boolean;
};

type MCPSkillDefinition = {
    id: string;
    name: string;
    description?: string;
    inputSchema?: MCPToolSchema;
    category?: string;
    capabilities?: string[];
    requiresConfirmation?: boolean;
};

type BehaviorSummary = {
    topTools?: Array<{ name: string; count: number }>;
};

type QuickAction = {
    label: string;
    command: string;
    toolName?: string;
};

const safeParseJson = (value: unknown): unknown => {
    if (!value) return undefined;
    if (typeof value === 'string') {
        try {
            return JSON.parse(value);
        } catch {
            return undefined;
        }
    }
    return value;
};

const parseToolCommand = (input: string): { name: string; args?: Record<string, unknown> } | null => {
    const trimmed = input.trim();
    const match = trimmed.match(/^(?:\/tool|tool:|tool)\s+([^\s]+)(?:\s+(.+))?$/i);
    if (!match) return null;
    const name = match[1];
    const rawArgs = match[2];
    if (!rawArgs) return { name };
    try {
        const parsed = JSON.parse(rawArgs);
        if (parsed && typeof parsed === 'object') {
            return { name, args: parsed as Record<string, unknown> };
        }
    } catch {
        // ignore parse errors
    }
    return { name };
};

const parseSkillCommand = (input: string): { id: string; args?: Record<string, unknown> } | null => {
    const trimmed = input.trim();
    const match = trimmed.match(/^(?:\/skill|skill:|skill)\s+([^\s]+)(?:\s+(.+))?$/i);
    if (!match) return null;
    const id = match[1];
    const rawArgs = match[2];
    if (!rawArgs) return { id };
    try {
        const parsed = JSON.parse(rawArgs);
        if (parsed && typeof parsed === 'object') {
            return { id, args: parsed as Record<string, unknown> };
        }
    } catch {
        // ignore parse errors
    }
    return { id };
};

const extractStockCodes = (input: string): string[] => {
    const matches = input.match(/\d{6}/g);
    return matches ? Array.from(new Set(matches)) : [];
};

const inferArgsFromInput = (schema: MCPToolSchema | undefined, input: string): Record<string, unknown> => {
    const args: Record<string, unknown> = {};
    if (!schema?.properties) {
        return args;
    }

    const properties = schema.properties;
    const codes = extractStockCodes(input);

    if ('stock_code' in properties && codes.length > 0) {
        args.stock_code = codes[0];
    }
    if ('stock_codes' in properties && codes.length > 0) {
        args.stock_codes = codes;
    }

    const daysMatch = input.match(/(\d+)\s*天/);
    if ('days' in properties && daysMatch) {
        args.days = Number(daysMatch[1]);
    }

    const topMatch = input.match(/(\d+)\s*(只|个|条|家|股|板块)/);
    if (('top_n' in properties || 'limit' in properties) && topMatch) {
        const value = Number(topMatch[1]);
        if ('top_n' in properties) {
            args.top_n = value;
        } else if ('limit' in properties) {
            args.limit = value;
        }
    }

    const industryMatch = input.match(/行业趋势\s*([^\s]+)/);
    if ('industry' in properties && industryMatch) {
        args.industry = industryMatch[1];
    }

    if ('query' in properties) {
        args.query = input.trim();
    }

    return args;
};

const getMissingRequired = (schema: MCPToolSchema | undefined, args: Record<string, unknown>): string[] => {
    if (!schema?.required || schema.required.length === 0) return [];
    return schema.required.filter(key => typeof args[key] === 'undefined');
};

const buildQuickActions = (mode: 'market' | 'stock' | 'portfolio', summary?: BehaviorSummary | null): QuickAction[] => {
    const actionsByMode: Record<typeof mode, QuickAction[]> = {
        market: [
            { label: '📈 今日市场', command: '今日市场', toolName: 'get_market_report' },
            { label: '🔥 热门概念', command: '热门概念', toolName: 'get_hot_concepts' },
            { label: '💰 北向资金', command: '北向资金流向', toolName: 'get_north_fund_flow' },
            { label: '🧭 资金流向', command: '资金流向', toolName: 'get_north_fund_flow' },
            { label: '🧠 今日洞察', command: '今日洞察', toolName: 'generate_daily_insight' },
            { label: '🏭 行业趋势', command: '行业趋势 银行', toolName: 'get_industry_trends' },
            { label: '🏷️ 板块行情', command: '板块行情', toolName: 'get_sector_realtime' },
        ],
        stock: [
            { label: '📊 分析茅台', command: '分析 600519', toolName: 'get_realtime_quote' },
            { label: '📊 分析平安', command: '分析 000001', toolName: 'get_realtime_quote' },
            { label: '📊 分析招商', command: '分析 600036', toolName: 'get_realtime_quote' },
            { label: '🧠 综合分析', command: '综合分析', toolName: 'run_skill' },
            { label: '🏭 行业趋势', command: '行业趋势 白酒', toolName: 'get_industry_trends' },
            { label: '🔍 智能选股', command: '帮我选一些低估值高ROE的股票', toolName: 'search_by_query_enhanced' },
        ],
        portfolio: [
            { label: '💼 我的持仓', command: '查看持仓', toolName: 'get_positions' },
            { label: '📈 AI准确率', command: 'AI准确率', toolName: 'analyze_ai_accuracy' },
            { label: '🧾 交易决策', command: '交易决策', toolName: 'get_decision_history' },
            { label: '📝 生成复盘', command: '生成复盘', toolName: 'analyze_trades' },
            { label: '⭐ 自选股', command: '自选股', toolName: 'get_watchlist' },
            { label: '👤 我的画像', command: '我的画像', toolName: 'get_user_profile' },
            { label: '⚙️ 我的偏好', command: '我的偏好', toolName: 'get_investment_preferences' },
        ],
    };

    const actions = actionsByMode[mode];
    if (!summary?.topTools || summary.topTools.length === 0) return actions;

    const orderMap = new Map<string, number>();
    summary.topTools.forEach((tool, index) => {
        orderMap.set(tool.name, index);
    });

    return [...actions].sort((a, b) => {
        const aIndex = a.toolName ? orderMap.get(a.toolName) : undefined;
        const bIndex = b.toolName ? orderMap.get(b.toolName) : undefined;
        if (aIndex === undefined && bIndex === undefined) return 0;
        if (aIndex === undefined) return 1;
        if (bIndex === undefined) return -1;
        return aIndex - bIndex;
    });
};

const buildClarification = (input: string): { prompt: string; suggestions: string[] } | null => {
    const text = input.trim();
    const hasCode = /\d{6}/.test(text);
    if (hasCode) return null;
    if (/行业趋势|板块行情|板块资金|资金流向|今日市场|热门概念|北向资金|选股|分析|持仓|洞察|复盘|记录决策|交易决策|准确率|自选/.test(text)) {
        return null;
    }

    const sectorMap: Array<{ keyword: string; industry: string }> = [
        { keyword: '银行', industry: '银行' },
        { keyword: '券商', industry: '证券' },
        { keyword: '医药', industry: '医药' },
        { keyword: '白酒', industry: '白酒' },
        { keyword: '半导体', industry: '半导体' },
        { keyword: '芯片', industry: '芯片' },
        { keyword: '新能源', industry: '新能源' },
        { keyword: '光伏', industry: '光伏' },
        { keyword: '汽车', industry: '汽车' },
        { keyword: '消费', industry: '消费' },
        { keyword: '保险', industry: '保险' },
    ];

    const matched = sectorMap.find(item => text.includes(item.keyword));
    if (!matched) return null;

    return {
        prompt: `你想看「${matched.industry}」的哪个维度？`,
        suggestions: [
            `行业趋势 ${matched.industry}`,
            '板块行情',
            '推荐个股',
        ],
    };
};

const buildToolPlan = (
    input: string,
    toolCatalog?: Map<string, MCPToolDefinition>,
    skillCatalog?: Map<string, MCPSkillDefinition>
): ToolPlan | null => {
    const text = input.trim();
    const skillCommand = parseSkillCommand(text);
    if (skillCommand) {
        const skillDef = skillCatalog?.get(skillCommand.id);
        const inferredArgs = skillCommand.args
            ? skillCommand.args
            : inferArgsFromInput(skillDef?.inputSchema, text);
        return {
            title: `执行技能 ${skillDef?.name || skillCommand.id}`,
            deepAnalysis: true,
            steps: [
                {
                    name: 'run_skill',
                    args: { skill_id: skillCommand.id, args: inferredArgs },
                    label: skillDef?.description || skillDef?.name || skillCommand.id,
                },
            ],
        };
    }
    const toolCommand = parseToolCommand(text);
    if (toolCommand) {
        const toolDef = toolCatalog?.get(toolCommand.name);
        const inferredArgs = toolCommand.args
            ? toolCommand.args
            : inferArgsFromInput(toolDef?.inputSchema, text);

        const deepAnalysis = toolCommand.name === 'run_skill';
        return {
            title: `调用 ${toolCommand.name}`,
            deepAnalysis,
            steps: [
                {
                    name: toolCommand.name,
                    args: inferredArgs,
                    label: toolDef?.description || toolCommand.name,
                },
            ],
        };
    }
    const skillKeywordMatch = text.match(/(综合分析|技术分析|基本面分析|深度研究|深度分析|快速查看)\s*(\d{6})/);
    if (skillKeywordMatch) {
        const keyword = skillKeywordMatch[1];
        const code = skillKeywordMatch[2];
        const skillMap: Record<string, string> = {
            '综合分析': 'stock_comprehensive_analysis',
            '技术分析': 'stock_technical_analysis',
            '基本面分析': 'stock_fundamental_analysis',
            '深度研究': 'stock_deep_research',
            '深度分析': 'stock_deep_research',
            '快速查看': 'stock_quick_view',
        };
        const skillId = skillMap[keyword];
        if (skillId) {
            const skillDef = skillCatalog?.get(skillId);
            return {
                title: `${skillDef?.name || keyword} ${code}`,
                deepAnalysis: true,
                steps: [
                    {
                        name: 'run_skill',
                        args: { skill_id: skillId, args: { stock_code: code } },
                        label: skillDef?.description || skillDef?.name || keyword,
                    },
                ],
            };
        }
    }

    const analysisMatch = text.match(/分析\s*(\d{6})/);
    const directCodeMatch = text.match(/^(\d{6})$/);
    const code = analysisMatch?.[1] || directCodeMatch?.[1];

    if (code) {
        return {
            title: `分析 ${code}`,
            deepAnalysis: true,
            steps: [
                {
                    name: 'get_realtime_quote',
                    args: { stock_code: code },
                    label: '实时行情',
                    visualizationType: 'stock',
                },
                {
                    name: 'get_kline',
                    args: { stock_code: code, period: 'daily', limit: 60 },
                    label: '日K线',
                    visualizationType: 'kline',
                },
                // FE-003: 新增技术指标分析
                {
                    name: 'calculate_indicators',
                    args: { stock_code: code, indicators: ['macd'], period: 'daily', timeperiod: 14 },
                    label: '技术指标(MACD)',
                    visualizationType: 'table',
                },
                // FE-003: 新增财务数据
                {
                    name: 'get_financials',
                    args: { stock_code: code, statement_types: ['income', 'balance'] },
                    label: '财务摘要',
                    visualizationType: 'table',
                },
                // FE-003: 新增资金流向
                {
                    name: 'get_north_fund_flow',
                    args: { days: 5 },
                    label: '北向资金流向',
                    visualizationType: 'chart',
                },
                {
                    name: 'get_sector_fund_flow',
                    args: { top_n: 10, sort_by: 'net' },
                    label: '板块资金流向',
                    visualizationType: 'chart',
                },
            ],
        };
    }

    // FE-011: 五档盘口/成交明细
    if (/五档|盘口|成交明细/.test(text)) {
        const match = text.match(/(\d{6})/);
        const code = match?.[1] || '600519';
        return {
            title: `${code} 盘口数据`,
            steps: [
                {
                    name: 'get_orderbook',
                    args: { stock_code: code },
                    label: '五档盘口',
                    visualizationType: 'table',
                },
                {
                    name: 'get_trades',
                    args: { stock_code: code, limit: 50 },
                    label: '成交明细',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-012: 批量行情
    if (/批量行情|多股行情|批量查询/.test(text)) {
        const matches = text.match(/\d{6}/g);
        const codes = matches && matches.length > 0 ? matches : ['600519', '000001', '000858'];
        return {
            title: '批量行情',
            steps: [
                {
                    name: 'get_batch_quotes',
                    args: { stock_codes: codes },
                    label: '批量行情',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-013: 因子库/因子分析
    if (/因子库|因子分析|因子研究|IC分析/.test(text)) {
        const isIC = /IC/.test(text);
        return {
            title: isIC ? '因子IC分析' : '因子库',
            steps: [
                {
                    name: isIC ? 'calculate_factor_ic' : 'get_factor_library',
                    args: isIC ? {} : {},
                    label: isIC ? '因子IC分析' : '因子库列表',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-014: 智能监控
    if (/智能监控|异动监控|自动监控/.test(text)) {
        return {
            title: '智能监控',
            steps: [
                {
                    name: 'smart_monitor_stocks',
                    args: {},
                    label: '智能监控结果',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-015: 个股研究报告
    if (/个股报告|研究报告|生成报告/.test(text)) {
        const match = text.match(/(\d{6})/);
        const code = match?.[1] || '600519';
        return {
            title: `${code}研究报告`,
            steps: [
                {
                    name: 'generate_stock_report',
                    args: { stock_code: code },
                    label: '个股研究报告',
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/今日市场|市场报告|市场概况/.test(text)) {
        return {
            title: '今日市场',
            steps: [
                {
                    name: 'get_market_report',
                    args: {},
                    label: '市场综合报告',
                },
            ],
        };
    }

    if (/我的持仓|查看持仓|持仓/.test(text)) {
        return {
            title: '我的持仓',
            steps: [
                {
                    name: 'get_positions',
                    args: {},
                    label: '持仓列表',
                    visualizationType: 'portfolio',
                },
            ],
        };
    }

    // FE-001/FE-016: 统一为MCP调用
    if (/我的画像|用户画像/.test(text)) {
        return {
            title: '用户画像',
            steps: [
                {
                    name: 'get_user_profile',
                    args: {},
                    label: '用户画像',
                    visualizationType: 'profile',
                },
            ],
        };
    }

    if (/行为总结|行为画像/.test(text)) {
        return {
            title: '行为画像',
            steps: [
                {
                    name: 'get_behavior_summary',
                    args: { days: 30 },
                    label: '行为画像摘要',
                    visualizationType: 'profile',
                },
            ],
        };
    }

    // FE-001/FE-016: 统一为MCP调用
    if (/我的偏好|个人偏好|我的配置/.test(text)) {
        return {
            title: '个人偏好',
            steps: [
                {
                    name: 'get_investment_preferences',
                    args: {},
                    label: '个人偏好设置',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/我的自选|自选股/.test(text)) {
        return {
            title: '自选股',
            steps: [
                {
                    name: 'get_watchlist',
                    args: {},
                    label: '自选股列表',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/加入自选/.test(text)) {
        const match = text.match(/加入自选\s*(\d{6})/);
        const stockCode = match?.[1];
        if (!stockCode) {
            return {
                title: '自选股',
                steps: [
                    {
                        name: 'get_watchlist',
                        args: {},
                        label: '自选股列表',
                        visualizationType: 'table',
                    },
                ],
            };
        }
        return {
            title: '加入自选',
            steps: [
                {
                    name: 'add_to_watchlist',
                    args: { code: stockCode },
                    label: `已加入自选 ${stockCode}`,
                },
                {
                    name: 'get_watchlist',
                    args: {},
                    label: '自选股列表',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/移除自选/.test(text)) {
        const match = text.match(/移除自选\s*(\d{6})/);
        const stockCode = match?.[1];
        if (!stockCode) {
            return null;
        }
        return {
            title: '移除自选',
            steps: [
                {
                    name: 'remove_from_watchlist',
                    args: { code: stockCode },
                    label: `已移除自选 ${stockCode}`,
                },
                {
                    name: 'get_watchlist',
                    args: {},
                    label: '自选股列表',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/AI准确率|准确率/.test(text)) {
        return {
            title: 'AI准确率',
            steps: [
                {
                    name: 'analyze_ai_accuracy',
                    args: { days: 30, min_holding_days: 5 },
                    label: 'AI准确率统计',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/交易决策|决策记录/.test(text)) {
        return {
            title: '交易决策',
            steps: [
                {
                    name: 'get_decision_history',
                    args: { limit: 20 },
                    label: '交易决策记录',
                    visualizationType: 'decision',
                },
            ],
        };
    }

    // FE-005: 高级选股功能
    if (/高级选股|智能选股|条件选股/.test(text)) {
        // 解析可能的条件
        const peMatch = text.match(/市盈率(?:低于|小于|<)\s*(\d+)/);
        const pbMatch = text.match(/市净率(?:低于|小于|<)\s*(\d+\.?\d*)/);
        const roeMatch = text.match(/ROE(?:高于|大于|>=?)\s*(\d+\.?\d*)/i);
        const filters: Record<string, unknown> = {};
        if (peMatch) filters.pe_range = [0, parseFloat(peMatch[1])];
        if (pbMatch) filters.pb_range = [0, parseFloat(pbMatch[1])];
        if (roeMatch) filters.roe_min = parseFloat(roeMatch[1]);

        return {
            title: '高级选股',
            steps: [
                {
                    name: 'screen_stocks_advanced',
                    args: Object.keys(filters).length > 0
                        ? { filters, order_by: 'market_cap', limit: 20 }
                        : { strategy: 'value', limit: 20 },
                    label: '高级选股结果',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-006: K线形态选股
    if (/形态选股|K线形态|看涨形态|看跌形态/.test(text)) {
        const isBullish = /看涨|底部/.test(text);
        const isBearish = /看跌|顶部/.test(text);

        return {
            title: isBearish ? '看跌形态选股' : '看涨形态选股',
            steps: [
                {
                    name: isBearish ? 'scan_bearish_patterns' : 'scan_bullish_patterns',
                    args: { min_reliability: 'medium' },
                    label: isBearish ? '看跌形态股票' : '看涨形态股票',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-006: 特定形态选股
    if (/双底|头肩底|W底|M头|头肩顶/.test(text)) {
        const patternMatch = text.match(/(双底|头肩底|W底|M头|头肩顶)/);
        const pattern = patternMatch?.[1] || 'double_bottom';
        const patternMap: Record<string, string> = {
            '双底': 'double_bottom',
            'W底': 'double_bottom',
            '头肩底': 'head_shoulders_bottom',
            'M头': 'double_top',
            '头肩顶': 'head_shoulders_top',
        };

        return {
            title: `${pattern}形态选股`,
            steps: [
                {
                    name: 'screen_by_pattern',
                    args: { pattern: patternMap[pattern] || pattern },
                    label: `${pattern}形态股票`,
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/热门概念/.test(text)) {
        return {
            title: '热门概念',
            steps: [
                {
                    name: 'get_hot_concepts',
                    args: {},
                    label: '热门概念追踪',
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/行业趋势/.test(text)) {
        const match = text.match(/行业趋势\s*(.+)/);
        const industry = match?.[1]?.trim() || '银行';
        return {
            title: `${industry} 行业趋势`,
            steps: [
                {
                    name: 'get_industry_trends',
                    args: { industry, include_stocks: true },
                    label: '行业趋势',
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/板块行情/.test(text)) {
        return {
            title: '板块行情',
            steps: [
                {
                    name: 'get_sector_realtime',
                    args: { type: 'industry', top_n: 20 },
                    label: '板块行情',
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/板块资金/.test(text)) {
        return {
            title: '板块资金',
            steps: [
                {
                    name: 'get_sector_fund_flow',
                    args: { top_n: 20, sort_by: 'net' },
                    label: '板块资金流向',
                    visualizationType: 'chart',
                },
            ],
        };
    }

    // FE-009: 风险高级功能
    if (/CVaR|条件风险|压力测试|情景分析/.test(text)) {
        const isStress = /压力测试|情景/.test(text);
        return {
            title: isStress ? '压力测试' : 'CVaR分析',
            steps: [
                {
                    name: isStress ? 'stress_test' : 'calculate_cvar',
                    args: isStress ? { scenario: 'market_crash' } : { confidence: 0.95 },
                    label: isStress ? '压力测试结果' : 'CVaR计算结果',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-010: 研报观点提取
    if (/提取观点|研报观点|观点提取/.test(text)) {
        const codes = extractStockCodes(text);
        return {
            title: '研报观点提取',
            steps: [
                {
                    name: 'extract_report_opinions',
                    args: codes.length > 0 ? { stock_code: codes[0] } : {},
                    label: '研报观点',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-010: 行业研报汇总
    if (/行业研报汇总|行业报告汇总/.test(text)) {
        const match = text.match(/(?:行业研报汇总|行业报告汇总)\s*(.+)/);
        const industry = match?.[1]?.trim() || '科技';
        return {
            title: `${industry}行业研报汇总`,
            steps: [
                {
                    name: 'summarize_industry_reports',
                    args: { industry },
                    label: '行业研报汇总',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-017: 向量搜索 - 相似股票
    if (/相似股票|类似股票|形态匹配|向量搜索/.test(text)) {
        const match = text.match(/(\d{6})/);
        const code = match?.[1] || '600519';
        return {
            title: `${code}相似股票`,
            steps: [
                {
                    name: 'search_similar_stocks',
                    args: { stock_code: code, top_n: 10 },
                    label: '相似股票',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-018: 期权策略分析
    if (/期权策略|期权组合|牛市价差|熊市价差|跨式|蝶式/.test(text)) {
        const strategyMatch = text.match(/(牛市价差|熊市价差|跨式|蝶式)/);
        const strategy = strategyMatch?.[1] || 'bull_spread';
        const strategyMap: Record<string, string> = {
            '牛市价差': 'bull_call_spread',
            '熊市价差': 'bear_put_spread',
            '跨式': 'straddle',
            '蝶式': 'iron_condor',
        };
        const priceMatch = text.match(/价格\s*(\d+\.?\d*)/);
        const underlyingPrice = priceMatch ? Number(priceMatch[1]) : undefined;
        return {
            title: `${strategy || '期权'}策略分析`,
            steps: [
                {
                    name: 'analyze_option_strategy',
                    args: {
                        strategy_type: strategyMap[strategy] || 'bull_call_spread',
                        ...(underlyingPrice ? { underlying_price: underlyingPrice } : {}),
                    },
                    label: '期权策略分析',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-019: 多周期K线
    if (/多周期|周期切换|周线|月线|分钟线/.test(text)) {
        const match = text.match(/(\d{6})/);
        const code = match?.[1] || '600519';
        const periodMatch = text.match(/(周线|月线|5分钟|15分钟|30分钟|60分钟)/);
        const period = periodMatch?.[1] || 'weekly';
        const periodMap: Record<string, string> = {
            '周线': 'weekly',
            '月线': 'monthly',
            '5分钟': '5m',
            '15分钟': '15m',
            '30分钟': '30m',
            '60分钟': '60m',
        };
        return {
            title: `${code} ${period || '多'}周期K线`,
            steps: [
                {
                    name: 'get_multi_period_data',
                    args: { stock_code: code, periods: [periodMap[period] || 'weekly', 'daily'] },
                    label: '多周期K线',
                    visualizationType: 'kline',
                },
            ],
        };
    }

    // FE-020: 增强自然语言选股
    if (/帮我选股|推荐股票|选出|筛选.*股票/.test(text)) {
        return {
            title: '智能选股',
            steps: [
                {
                    name: 'search_by_query_enhanced',
                    args: { query: text },
                    label: '智能选股结果',
                    visualizationType: 'table',
                },
            ],
        };
    }

    if (/北向资金/.test(text)) {
        return {
            title: '北向资金',
            steps: [
                {
                    name: 'get_north_fund_flow',
                    args: { days: 10 },
                    label: '北向资金流向',
                    visualizationType: 'chart',
                },
            ],
        };
    }

    if (/资金流向/.test(text) && !/北向资金/.test(text)) {
        return {
            title: '资金流向',
            combineId: 'fundFlow',
            steps: [
                {
                    name: 'get_north_fund_flow',
                    args: { days: 10 },
                    label: '北向资金流向',
                    visualizationType: 'chart',
                    collectKey: 'north',
                    silent: true,
                },
                {
                    name: 'get_sector_fund_flow',
                    args: { top_n: 20, sort_by: 'net' },
                    label: '板块资金流向',
                    visualizationType: 'chart',
                    collectKey: 'sector',
                    silent: true,
                },
            ],
        };
    }

    if (/今日洞察|每日洞察|洞察/.test(text)) {
        return {
            title: '今日洞察',
            steps: [
                {
                    name: 'generate_daily_insight',
                    args: {},
                    label: '每日智能洞察',
                },
            ],
        };
    }

    if (/选股|筛选|帮我选|推荐个股/.test(text)) {
        const queryParts: string[] = [];
        if (/低估值|低市盈率|PE/.test(text)) {
            queryParts.push('市盈率低于15');
        }
        if (/高ROE|ROE/.test(text)) {
            queryParts.push('ROE大于15');
        }
        const query = queryParts.length > 0 ? queryParts.join('且') : text.trim();

        return {
            title: '智能选股',
            steps: [
                {
                    name: 'search_by_query_enhanced',
                    args: { query },
                    label: '筛选结果',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/复盘|生成复盘/.test(text)) {
        const endDate = Date.now();
        const startDate = endDate - 30 * 24 * 60 * 60 * 1000;
        return {
            title: '复盘报告',
            steps: [
                {
                    name: 'analyze_trades',
                    args: {
                        date_range: {
                            start: new Date(startDate).toISOString().split('T')[0],
                            end: new Date(endDate).toISOString().split('T')[0],
                        },
                        analysis_type: 'all',
                    },
                    label: '复盘报告',
                    visualizationType: 'table',
                },
            ],
        };
    }

    // FE-001: 统一为MCP调用
    if (/记录决策/.test(text)) {
        const decisionMatch = text.match(/记录决策\s*(\d{6})?\s*(买入|卖出|持有|观望)?\s*([\d.]+)?/);
        const stockCode = decisionMatch?.[1];
        const action = decisionMatch?.[2] || '观望';
        const price = decisionMatch?.[3] ? Number(decisionMatch?.[3]) : undefined;
        const reason = text.replace(decisionMatch?.[0] || '', '').trim() || '手动记录';

        if (!stockCode) {
            return {
                title: '记录决策',
                steps: [
                    {
                        name: 'get_behavior_summary',
                        args: { days: 7 },
                        label: '缺少股票代码，请补充后再记录',
                        visualizationType: 'profile',
                    },
                ],
            };
        }

        const decisionMap: Record<string, 'buy' | 'sell' | 'hold'> = {
            '买入': 'buy',
            '卖出': 'sell',
            '持有': 'hold',
            '观望': 'hold',
        };

        return {
            title: '记录决策',
            steps: [
                {
                    name: 'record_decision',
                    args: {
                        stock_code: stockCode,
                        action: decisionMap[action] || 'hold',
                        reason,
                        target_price: price,
                    },
                    label: '记录决策',
                },
                {
                    name: 'get_decision_history',
                    args: { stock_code: stockCode, limit: 10 },
                    label: '决策记录',
                    visualizationType: 'decision',
                },
            ],
        };
    }

    return null;
};

const buildChartData = (toolName: string, toolData: unknown): unknown => {
    if (!toolData || typeof toolData !== 'object') return toolData;
    if (toolName === 'fund_flow_combo') {
        return toolData;
    }
    if (toolName === 'get_north_fund_flow') {
        const data = toolData as { daily?: Array<{ date: string; total?: number }> };
        if (Array.isArray(data.daily)) {
            return data;
        }
    }
    if (toolName === 'get_sector_fund_flow') {
        return toolData;
    }
    return toolData;
};

const buildVisualization = (step: ToolStep, toolData: unknown): Visualization | undefined => {
    const resolvedType = step.visualizationType
        ?? (['run_simple_backtest', 'get_backtest_detail', 'render_backtest_chart'].includes(step.name)
            ? 'backtest'
            : undefined);
    if (!resolvedType) return undefined;
    let data = resolvedType === 'chart'
        ? buildChartData(step.name, toolData)
        : toolData;

    if (step.name === 'behavior:summary' && toolData && typeof toolData === 'object') {
        return {
            type: 'profile',
            title: step.label,
            data: toolData,
        };
    }

    return {
        type: resolvedType,
        title: step.label,
        data,
    };
};

function buildStructuredSummary(step: ToolStep, toolResult: ToolResult): string {
    const data = toolResult.data as Record<string, unknown> | undefined;
    if (step.name === 'run_skill' && data) {
        const skill = data.skill as { name?: string; id?: string } | undefined;
        const partial = data.partialSuccess ? '（部分成功）' : '';
        const toolCount = Array.isArray(data.toolResults) ? data.toolResults.length : 0;
        return [
            `结论: 技能 ${skill?.name || skill?.id || '未知'} 执行完成${partial}`,
            `要点: 共编排 ${toolCount} 个工具调用`,
            '风险: 请结合实时行情与个人策略判断',
            '下一步: 查看深度分析报告或继续追问',
        ].join('\n');
    }
    if (step.name === 'get_realtime_quote' && data) {
        const quote = data as {
            price?: number;
            change?: number;
            changePercent?: number;
            low?: number;
            high?: number;
            asOf?: string | null;
            stale?: boolean;
        };
        const price = quote.price ?? '--';
        const change = quote.change ?? '--';
        const changePercent = quote.changePercent ?? '--';
        const freshness = quote.asOf
            ? `时效: ${quote.asOf}${quote.stale ? ' (可能过期)' : ''}`
            : '时效: 未提供';
        return [
            `结论: 当前价格 ${price} (${change} / ${changePercent}%)`,
            `要点: 今日区间 ${quote.low ?? '--'} ~ ${quote.high ?? '--'}`,
            freshness,
            '风险: 行情数据可能有延迟',
            '下一步: 查看K线或加入自选',
        ].join('\n');
    }

    if (step.name === 'get_kline' && data) {
        const kline = data as { period?: string; count?: number; asOf?: string | null; stale?: boolean };
        const freshness = kline.asOf
            ? `时效: ${kline.asOf}${kline.stale ? ' (可能过期)' : ''}`
            : '时效: 未提供';
        return [
            `结论: ${kline.period || 'daily'} K线 ${kline.count ?? 0} 条`,
            freshness,
            '风险: 历史行情存在滞后',
            '下一步: 结合技术指标分析',
        ].join('\n');
    }

    if (step.name === 'get_positions' && data) {
        const portfolio = data as { count?: number; totalMarketValue?: number; totalProfit?: number };
        return [
            `结论: 共 ${portfolio.count ?? 0} 只持仓`,
            `要点: 总市值 ${portfolio.totalMarketValue ?? '--'}，总盈亏 ${portfolio.totalProfit ?? '--'}`,
            '风险: 持仓盈亏为估算',
            '下一步: 查看单股详情或调整仓位',
        ].join('\n');
    }

    if ((step.name === 'screen_stocks' || step.name === 'search_by_query_enhanced') && data) {
        const screener = data as { count?: number; conditions?: unknown };
        return [
            `结论: 共筛选 ${screener.count ?? 0} 只股票`,
            `要点: 条件 ${JSON.stringify(screener.conditions || {})}`,
            '风险: 仅基于历史财务数据',
            '下一步: 选择个股进一步分析',
        ].join('\n');
    }

    if (step.name === 'get_north_fund_flow' && data) {
        const flow = data as { days?: number; totalFlowFormatted?: string; trend?: string };
        return [
            `结论: 近${flow.days ?? '--'}日净流入 ${flow.totalFlowFormatted ?? '--'}`,
            `要点: 趋势 ${flow.trend === 'inflow' ? '净流入' : '净流出'}`,
            '风险: 资金流向波动较大',
            '下一步: 结合板块行情交叉验证',
        ].join('\n');
    }

    if (step.name === 'get_sector_fund_flow' && data) {
        const sectorFlow = data as { count?: number; sortBy?: string };
        return [
            `结论: 板块资金流向更新 (${sectorFlow.count ?? 0} 个板块)`,
            `要点: 排序维度 ${sectorFlow.sortBy || 'net'}`,
            '风险: 资金流向短期波动明显',
            '下一步: 结合行业趋势筛选龙头',
        ].join('\n');
    }

    if (step.name === 'fund_flow_combo') {
        return [
            '结论: 资金流向总览已生成',
            '要点: 支持切换北向/板块资金',
            '风险: 资金流向波动明显',
            '下一步: 进一步查看板块行情',
        ].join('\n');
    }

    if (step.name === 'get_market_report') {
        return [
            '结论: 市场综合报告已生成',
            '要点: 请查看报告详情',
            '风险: 市场波动不确定',
            '下一步: 查看板块或个股分析',
        ].join('\n');
    }

    if (step.name === 'generate_daily_insight') {
        return [
            '结论: 今日洞察已生成',
            '要点: 请查看洞察内容',
            '风险: 建议结合自有判断',
            '下一步: 进一步筛选或分析个股',
        ].join('\n');
    }

    if (step.name === 'analyze_ai_accuracy' && data && typeof data === 'object') {
        const stats = data as { summary?: { overallAccuracy?: string; decisionsWithAi?: number } };
        return [
            `结论: 已统计 AI 准确率 ${stats.summary?.overallAccuracy ?? '--'}`,
            `要点: 统计样本 ${stats.summary?.decisionsWithAi ?? '--'} 条`,
            '风险: 样本量不足时波动较大',
            '下一步: 查看复盘报告或记录更多决策',
        ].join('\n');
    }

    if (step.name === 'analyze_trades') {
        return [
            '结论: 复盘报告已生成',
            '要点: 请查看报告摘要与洞察',
            '风险: 历史结果不代表未来',
            '下一步: 调整策略或完善记录',
        ].join('\n');
    }

    if (step.name === 'get_behavior_summary') {
        return [
            '结论: 行为画像已生成',
            '要点: 查看常用工具与关注股票',
            '风险: 画像随行为变化',
            '下一步: 优化快捷指令或偏好设置',
        ].join('\n');
    }

    if (step.name === 'get_user_profile') {
        return [
            '结论: 用户画像已获取',
            '要点: 关注风险偏好与投资期限',
            '风险: 画像需持续更新',
            '下一步: 更新偏好或完善问卷',
        ].join('\n');
    }

    return [
        `结论: ${step.label}完成`,
        '要点: 请查看结果详情',
        '风险: 数据仅供参考',
        '下一步: 继续深挖或执行操作',
    ].join('\n');
}

const formatToolText = (step: ToolStep, toolResult: ToolResult): string => {
    if (toolResult.requiresConfirmation) {
        const message = toolResult.confirmation?.message || toolResult.error || '该操作需要确认';
        return `⚠️ ${message}`;
    }
    if (!toolResult.success) {
        return `❌ ${step.label}失败：${toolResult.error || '未知错误'}`;
    }

    const summary = buildStructuredSummary(step, toolResult);
    if (step.visualizationType) {
        return summary;
    }

    return summary + `\n\`\`\`json\n${JSON.stringify(toolResult.data, null, 2)}\n\`\`\``;
};

const buildToolSuggestions = (step: ToolStep, toolResult: ToolResult): string[] | undefined => {
    if (toolResult.requiresConfirmation) {
        return undefined;
    }
    if (!toolResult.success) {
        return ['今日市场'];
    }

    if (step.name === 'run_skill') {
        return ['记录决策', '生成复盘'];
    }

    if (step.name === 'get_realtime_quote') {
        const quote = toolResult.data as { code?: string };
        const code = quote?.code;
        if (code) {
            return [`分析 ${code}`, `加入自选 ${code}`];
        }
        return ['查看K线'];
    }

    if (step.name === 'get_north_fund_flow') {
        return ['板块资金', '板块行情'];
    }

    if (step.name === 'get_sector_fund_flow') {
        return ['北向资金', '行业趋势 银行'];
    }

    if (step.name === 'fund_flow_combo') {
        return ['北向资金', '板块资金'];
    }

    if (step.name === 'get_decision_history' && toolResult.data && typeof toolResult.data === 'object') {
        const decisions = (toolResult.data as { decisions?: unknown[] }).decisions || [];
        const now = Date.now();
        const due = decisions.filter(item => {
            const decision = item as { createdAt?: string; result?: string | null };
            const createdAt = decision.createdAt ? new Date(decision.createdAt).getTime() : undefined;
            return decision.result == null && createdAt && now - createdAt > 7 * 24 * 60 * 60 * 1000;
        });
        if (due.length > 0) {
            return ['生成复盘', 'AI准确率'];
        }
    }

    if (step.name === 'search_by_query_enhanced') {
        return ['分析 600519', '行业趋势 银行'];
    }

    return undefined;
};

const buildAIMessages = (history: ChatMessage[], userContent: string): Array<{ role: 'user' | 'assistant' | 'system'; content: string }> => {
    const base = history
        .filter(message => message.role !== 'tool')
        .map(message => ({
            role: (message.role === 'assistant' ? 'assistant' : 'user') as 'user' | 'assistant' | 'system',
            content: message.content,
        }));
    return [...base, { role: 'user' as const, content: userContent }];
};

const normalizeToolResult = (
    result: { success: boolean; data?: unknown; error?: string },
    executor: 'mcp' | 'local'
): ToolResult => {
    if (!result.success) {
        const enriched = result as ToolResult;
        return {
            success: false,
            error: result.error || '请求失败',
            requiresConfirmation: enriched.requiresConfirmation,
            confirmation: enriched.confirmation,
            validationErrors: enriched.validationErrors,
        };
    }

    if (executor === 'mcp') {
        if (result.data && typeof result.data === 'object' && 'success' in result.data) {
            return result.data as ToolResult;
        }
        return { success: true, data: result.data };
    }

    return { success: true, data: result.data, source: 'local', quality: 'internal' };
};

const executeToolStep = async (step: ToolStep): Promise<{ success: boolean; data?: unknown; error?: string }> => {
    if (step.executor === 'local') {
        switch (step.name) {
            case 'config:get':
                return window.electronAPI.config.get();
            case 'watchlist:get':
                return window.electronAPI.watchlist.get();
            case 'watchlist:add':
                return window.electronAPI.watchlist.add(step.args.stockCode as string);
            case 'watchlist:remove':
                return window.electronAPI.watchlist.remove(step.args.stockCode as string);
            case 'behavior:summary':
                return window.electronAPI.behavior.summary(step.args.days as number | undefined);
            case 'trading:logDecision':
                return window.electronAPI.trading.logDecision(step.args);
            case 'trading:getAccuracyStats':
                return window.electronAPI.trading.getAccuracyStats(step.args);
            case 'trading:getDecisions':
                return window.electronAPI.trading.getDecisions(step.args);
            case 'trading:generateReport':
                return window.electronAPI.trading.generateReport(step.args);
            default:
                return { success: false, error: `不支持的本地指令: ${step.name}` };
        }
    }

    return window.electronAPI.mcp.callTool(step.name, step.args);
};

const resolveExecutor = (toolName: string): 'local' | 'mcp' => {
    if (toolName.includes(':')) {
        return 'local';
    }
    return 'mcp';
};

const App: React.FC = () => {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(true);
    const [showSettings, setShowSettings] = useState(false);
    const [showWorkbench, setShowWorkbench] = useState(false);
    const [progress, setProgress] = useState<{ label: string; percent?: number } | null>(null);
    const [pinnedVisualization, setPinnedVisualization] = useState<Visualization | null>(null);
    const [layoutMode, setLayoutMode] = useState<'single' | 'split'>('split');
    const [activeMode, setActiveMode] = useState<'market' | 'stock' | 'portfolio'>('market');
    const [behaviorSummary, setBehaviorSummary] = useState<BehaviorSummary | null>(null);
    const activeStreamIdRef = useRef<string | null>(null);
    const streamBufferRef = useRef<string>('');
    const streamMessageIdRef = useRef<string | null>(null);
    const streamSessionIdRef = useRef<string | null>(null);
    const toolCatalogRef = useRef<Map<string, MCPToolDefinition>>(new Map());
    const skillCatalogRef = useRef<Map<string, MCPSkillDefinition>>(new Map());
    const mcpInitializedRef = useRef(false);

    useEffect(() => {
        const offChunk = window.electronAPI.ai.onChunk(({ streamId, delta }) => {
            if (streamId !== activeStreamIdRef.current) return;
            streamBufferRef.current += delta;
            const messageId = streamMessageIdRef.current;
            if (!messageId) return;
            setMessages(prev => prev.map(message => (
                message.id === messageId
                    ? { ...message, content: streamBufferRef.current }
                    : message
            )));
        });

        const offDone = window.electronAPI.ai.onDone(async ({ streamId }) => {
            if (streamId !== activeStreamIdRef.current) return;
            // 改进空响应提示，提供更友好的反馈
            const finalContent = streamBufferRef.current.trim()
                ? streamBufferRef.current
                : '⚠️ AI 未生成有效回复。\n\n可能原因：\n• 输入内容不够明确\n• 模型处于思考状态但未输出结果\n\n建议：请尝试更具体的问题，如 "分析 600519" 或 "今日市场概况"';
            const sessionId = streamSessionIdRef.current;
            const messageId = streamMessageIdRef.current;

            if (messageId) {
                setMessages(prev => prev.map(message => (
                    message.id === messageId
                        ? { ...message, content: finalContent }
                        : message
                )));
            }

            if (sessionId) {
                await window.electronAPI.db.saveMessage(sessionId, 'assistant', finalContent);
            }
            await refreshBehaviorSummary();

            activeStreamIdRef.current = null;
            streamMessageIdRef.current = null;
            streamSessionIdRef.current = null;
            streamBufferRef.current = '';
            setIsLoading(false);
            setProgress(null);
        });

        const offError = window.electronAPI.ai.onError(async ({ streamId, error }) => {
            if (streamId !== activeStreamIdRef.current) return;
            const messageId = streamMessageIdRef.current;
            const sessionId = streamSessionIdRef.current;
            const errorContent = `❌ AI 响应失败：${error}`;

            if (messageId) {
                setMessages(prev => prev.map(message => (
                    message.id === messageId
                        ? { ...message, content: errorContent }
                        : message
                )));
            } else {
                setMessages(prev => [...prev, {
                    id: (Date.now() + Math.random()).toString(),
                    role: 'assistant',
                    content: errorContent,
                    createdAt: new Date(),
                }]);
            }

            if (sessionId) {
                await window.electronAPI.db.saveMessage(sessionId, 'assistant', errorContent);
            }
            await refreshBehaviorSummary();

            activeStreamIdRef.current = null;
            streamMessageIdRef.current = null;
            streamSessionIdRef.current = null;
            streamBufferRef.current = '';
            setIsLoading(false);
            setProgress(null);
        });

        return () => {
            offChunk();
            offDone();
            offError();
        };
    }, []);

    // 初始化 MCP 连接
    useEffect(() => {
        const initMCP = async () => {
            // 防止重复初始化
            if (mcpInitializedRef.current) {
                console.log('[App] MCP already initialized, skipping');
                return;
            }
            mcpInitializedRef.current = true;

            try {
                const result = await window.electronAPI.mcp.init();
                if (result.success) {
                    const connected = result.data && typeof result.data === 'object' && 'connected' in result.data
                        ? Boolean((result.data as { connected?: boolean }).connected)
                        : true;
                    setIsConnected(connected);
                    if (connected) {
                        console.log('[App] MCP connected');
                    }
                } else {
                    setIsConnected(false);
                }
                const toolsResult = await window.electronAPI.mcp.listTools();
                if (toolsResult.success && toolsResult.data && typeof toolsResult.data === 'object' && 'tools' in toolsResult.data) {
                    const toolList = (toolsResult.data as { tools: MCPToolDefinition[] }).tools;
                    const nextMap = new Map<string, MCPToolDefinition>();
                    toolList.forEach(tool => {
                        nextMap.set(tool.name, tool);
                    });
                    toolCatalogRef.current = nextMap;
                }

                const skillsResult = await window.electronAPI.mcp.callTool('list_skills', {});
                if (skillsResult.success && skillsResult.data && typeof skillsResult.data === 'object' && 'skills' in skillsResult.data) {
                    const skillList = (skillsResult.data as { skills: MCPSkillDefinition[] }).skills;
                    const nextSkillMap = new Map<string, MCPSkillDefinition>();
                    skillList.forEach(skill => {
                        nextSkillMap.set(skill.id, skill);
                    });
                    skillCatalogRef.current = nextSkillMap;
                }
            } catch (error) {
                console.error('[App] MCP init error:', error);
            }
        };
        initMCP();
    }, []);

    const refreshBehaviorSummary = async () => {
        try {
            const result = await window.electronAPI.behavior.summary(30);
            if (result.success && result.data) {
                setBehaviorSummary(result.data as BehaviorSummary);
            }
        } catch (error) {
            console.error('[App] Behavior summary error:', error);
        }
    };

    // 加载或创建初始会话
    useEffect(() => {
        const initSession = async () => {
            const sessionsResult = await window.electronAPI.db.getSessions();
            if (sessionsResult.success && sessionsResult.data && sessionsResult.data.length > 0) {
                // 加载最近的会话
                const latestSession = sessionsResult.data[0];
                await loadSession(latestSession.id);
            }
            await refreshBehaviorSummary();
        };
        initSession();
    }, []);

    // 加载会话消息
    const loadSession = async (sessionId: string) => {
        setCurrentSessionId(sessionId);
        const result = await window.electronAPI.db.getMessages(sessionId);
        if (result.success && result.data) {
            const rawMessages = result.data as Array<ChatMessage & { toolCalls?: unknown; metadata?: unknown }>;
            setMessages(rawMessages.map(msg => {
                const toolCallRaw = safeParseJson(msg.toolCalls);
                const metadata = safeParseJson(msg.metadata) as { visualization?: Visualization; suggestions?: string[] } | undefined;
                // 确保 toolCall 符合类型定义，必须有 name 和 args 属性
                const toolCall = toolCallRaw && typeof toolCallRaw === 'object' && 'name' in toolCallRaw && 'args' in toolCallRaw
                    ? toolCallRaw as ChatMessage['toolCall']
                    : undefined;
                return {
                    ...msg,
                    toolCall,
                    visualization: metadata?.visualization,
                    suggestions: metadata?.suggestions,
                    createdAt: new Date(msg.createdAt),
                };
            }));
        }
    };

    const buildToolClarification = (toolName: string, missing: string[], input: string) => {
        const exampleArgs: Record<string, unknown> = {};
        if (missing.includes('stock_code')) {
            exampleArgs.stock_code = '600519';
        }
        if (missing.includes('stock_codes')) {
            exampleArgs.stock_codes = ['600519', '000001'];
        }
        if (missing.includes('days')) {
            exampleArgs.days = 5;
        }
        if (missing.includes('top_n')) {
            exampleArgs.top_n = 20;
        }
        if (missing.includes('limit')) {
            exampleArgs.limit = 20;
        }
        if (missing.includes('industry')) {
            exampleArgs.industry = '银行';
        }
        if (missing.includes('query')) {
            exampleArgs.query = input.trim();
        }
        if (missing.includes('strategy_type')) {
            exampleArgs.strategy_type = 'straddle';
        }
        if (missing.includes('underlying_price')) {
            exampleArgs.underlying_price = 2.5;
        }
        if (toolName === 'analyze_option_strategy' && !('strategy_type' in exampleArgs)) {
            exampleArgs.strategy_type = 'straddle';
        }
        if (missing.includes('factor_values') || missing.includes('forward_returns')) {
            exampleArgs.factor_values = [
                { stock_code: '600519', factor_value: 1.2 },
                { stock_code: '000001', factor_value: 0.9 },
                { stock_code: '600036', factor_value: 1.1 },
                { stock_code: '000858', factor_value: 0.8 },
                { stock_code: '300750', factor_value: 1.3 },
                { stock_code: '601318', factor_value: 0.95 },
                { stock_code: '000333', factor_value: 1.05 },
                { stock_code: '601166', factor_value: 0.85 },
                { stock_code: '600030', factor_value: 0.88 },
                { stock_code: '600009', factor_value: 0.92 },
            ];
            exampleArgs.forward_returns = [
                { stock_code: '600519', return_rate: 0.05 },
                { stock_code: '000001', return_rate: -0.02 },
                { stock_code: '600036', return_rate: 0.03 },
                { stock_code: '000858', return_rate: -0.01 },
                { stock_code: '300750', return_rate: 0.06 },
                { stock_code: '601318', return_rate: 0.01 },
                { stock_code: '000333', return_rate: 0.02 },
                { stock_code: '601166', return_rate: -0.03 },
                { stock_code: '600030', return_rate: 0.015 },
                { stock_code: '600009', return_rate: 0.01 },
            ];
        }

        return {
            prompt: `检测到可能的工具 "${toolName}"，缺少参数: ${missing.join('、')}`,
            suggestions: Object.keys(exampleArgs).length > 0
                ? [`tool ${toolName} ${JSON.stringify(exampleArgs)}`]
                : undefined,
        };
    };

    const buildSkillClarification = (skillId: string, missing: string[], input: string) => {
        const exampleArgs: Record<string, unknown> = {};
        if (missing.includes('stock_code')) {
            exampleArgs.stock_code = '600519';
        }
        if (missing.includes('stock_codes')) {
            exampleArgs.stock_codes = ['600519', '000001'];
        }
        if (missing.includes('days')) {
            exampleArgs.days = 5;
        }
        if (missing.includes('industry')) {
            exampleArgs.industry = '银行';
        }
        if (missing.includes('query')) {
            exampleArgs.query = input.trim();
        }

        return {
            prompt: `检测到可能的技能 "${skillId}"，缺少参数: ${missing.join('、')}`,
            suggestions: Object.keys(exampleArgs).length > 0
                ? [`skill ${skillId} ${JSON.stringify(exampleArgs)}`]
                : undefined,
        };
    };

    /**
     * 优化后的合并搜索函数
     * 1. 并行搜索 skills 和 tools
     * 2. 合并候选列表后只调用一次 AI planTool
     * 3. 单个候选直接使用，不调用 AI
     */
    const resolvePlanFromCombinedSearch = async (input: string): Promise<{ plan?: ToolPlan; clarification?: { prompt: string; suggestions?: string[] } } | null> => {
        try {
            // 并行搜索技能和工具
            const [skillsResult, toolsResult] = await Promise.all([
                window.electronAPI.mcp.callTool('search_skills', { query: input }),
                window.electronAPI.mcp.callTool('search_tools', { query: input }),
            ]);

            const normalizedSkills = normalizeToolResult(skillsResult, 'mcp');
            const normalizedTools = normalizeToolResult(toolsResult, 'mcp');

            // 提取技能列表
            const skills = (normalizedSkills.success && normalizedSkills.data && typeof normalizedSkills.data === 'object')
                ? ((normalizedSkills.data as { skills?: MCPSkillDefinition[] }).skills || [])
                : [];

            // 提取工具列表
            const tools = (normalizedTools.success && normalizedTools.data && typeof normalizedTools.data === 'object')
                ? ((normalizedTools.data as { tools?: Array<{ name: string; description?: string }> }).tools || [])
                : [];

            // 构建候选列表：技能标记为 isSkill，工具为普通候选
            type CandidateItem = {
                name: string;
                description?: string;
                inputSchema?: unknown;
                isSkill?: boolean;
                skillDef?: MCPSkillDefinition;
                toolDef?: MCPToolDefinition;
            };

            const candidates: CandidateItem[] = [];

            // 添加技能候选
            skills.slice(0, 4).forEach(skill => {
                const skillDef = skillCatalogRef.current.get(skill.id) || skill;
                candidates.push({
                    name: skill.id,
                    description: skill.description || skill.name,
                    inputSchema: skillDef?.inputSchema,
                    isSkill: true,
                    skillDef: skillDef as MCPSkillDefinition,
                });
            });

            // 添加工具候选
            tools.slice(0, 4).forEach(tool => {
                // 避免重复（技能和工具可能有同名）
                if (candidates.some(c => c.name === tool.name)) return;
                const toolDef = toolCatalogRef.current.get(tool.name);
                candidates.push({
                    name: tool.name,
                    description: toolDef?.description || tool.description,
                    inputSchema: toolDef?.inputSchema,
                    isSkill: false,
                    toolDef,
                });
            });

            // 无候选结果
            if (candidates.length === 0) {
                return null;
            }

            // 单个候选：直接使用，无需 AI 调用
            if (candidates.length === 1) {
                const candidate = candidates[0];
                if (candidate.isSkill) {
                    const skillId = candidate.name;
                    const skillDef = candidate.skillDef;
                    const args = inferArgsFromInput(skillDef?.inputSchema, input);
                    const missing = getMissingRequired(skillDef?.inputSchema, args);
                    if (missing.length > 0) {
                        return { clarification: buildSkillClarification(skillId, missing, input) };
                    }
                    return {
                        plan: {
                            title: `执行技能 ${skillDef?.name || skillId}`,
                            deepAnalysis: true,
                            steps: [{
                                name: 'run_skill',
                                args: { skill_id: skillId, args },
                                label: skillDef?.description || skillDef?.name || skillId,
                            }],
                        },
                    };
                } else {
                    const toolName = candidate.name;
                    const toolDef = candidate.toolDef;
                    const args = inferArgsFromInput(toolDef?.inputSchema, input);
                    const missing = getMissingRequired(toolDef?.inputSchema, args);
                    if (missing.length > 0) {
                        return { clarification: buildToolClarification(toolName, missing, input) };
                    }
                    const deepAnalysis = /analysis|research|insight|report|valuation|risk|sentiment|screen/i.test(toolName);
                    return {
                        plan: {
                            title: `调用 ${toolName}`,
                            deepAnalysis,
                            steps: [{
                                name: toolName,
                                args,
                                label: toolDef?.description || toolName,
                            }],
                        },
                    };
                }
            }

            // 多个候选：调用一次 AI planTool 选择最佳
            const planResult = await window.electronAPI.ai.planTool({
                query: input,
                tools: candidates.map(c => ({
                    name: c.name,
                    description: c.description,
                    inputSchema: c.inputSchema,
                })),
            });

            if (planResult.success && planResult.data?.toolName) {
                const selectedName = planResult.data.toolName;
                const selected = candidates.find(c => c.name === selectedName);

                if (!selected) {
                    // AI 选择的候选不在列表中
                    return {
                        clarification: {
                            prompt: `未找到 "${selectedName}"，请从以下选项中选择：`,
                            suggestions: candidates.slice(0, 5).map(c =>
                                c.isSkill ? `skill ${c.name}` : `tool ${c.name}`
                            ),
                        },
                    };
                }

                const args = (planResult.data.args && typeof planResult.data.args === 'object')
                    ? planResult.data.args
                    : inferArgsFromInput(selected.inputSchema, input);

                if (selected.isSkill) {
                    const skillId = selected.name;
                    const skillDef = selected.skillDef;
                    const missing = getMissingRequired(skillDef?.inputSchema, args);
                    if (missing.length > 0) {
                        return { clarification: buildSkillClarification(skillId, missing, input) };
                    }
                    return {
                        plan: {
                            title: `执行技能 ${skillDef?.name || skillId}`,
                            deepAnalysis: true,
                            steps: [{
                                name: 'run_skill',
                                args: { skill_id: skillId, args },
                                label: skillDef?.description || skillDef?.name || skillId,
                            }],
                        },
                    };
                } else {
                    const toolName = selected.name;
                    const toolDef = selected.toolDef;
                    const missing = getMissingRequired(toolDef?.inputSchema, args);
                    if (missing.length > 0) {
                        return { clarification: buildToolClarification(toolName, missing, input) };
                    }
                    const deepAnalysis = /analysis|research|insight|report|valuation|risk|sentiment|screen/i.test(toolName);
                    return {
                        plan: {
                            title: `调用 ${toolName}`,
                            deepAnalysis,
                            steps: [{
                                name: toolName,
                                args,
                                label: toolDef?.description || toolName,
                            }],
                        },
                    };
                }
            }

            // AI 未选择任何工具，返回多选提示
            return {
                clarification: {
                    prompt: '检测到多个可能匹配，请选择后继续：',
                    suggestions: candidates.slice(0, 5).map(c =>
                        c.isSkill ? `skill ${c.name}` : `tool ${c.name}`
                    ),
                },
            };
        } catch (error) {
            console.error('[App] Combined search error:', error);
            return null;
        }
    };

    // 创建新会话
    const handleNewSession = async () => {
        const result = await window.electronAPI.db.createSession('新对话');
        if (result.success && result.data) {
            setCurrentSessionId(result.data.id);
            setMessages([]);
        }
    };

    const handleSuggestion = async (command: string) => {
        await handleSendMessage(command);
    };

    const handleRetryTool = async (toolCall?: ChatMessage['toolCall']) => {
        if (!toolCall) return;
        if (!currentSessionId) return;

        if (toolCall.name === 'fund_flow_combo') {
            setIsLoading(true);
            setProgress({ label: '重试：资金流向', percent: 20 });

            const steps = ((toolCall.args as { steps?: Array<{ name: string; args: Record<string, unknown> }> })?.steps || [
                { name: 'get_north_fund_flow', args: { days: 10 } },
                { name: 'get_sector_fund_flow', args: { top_n: 20, sort_by: 'net' } },
            ]) as Array<{ name: string; args: Record<string, unknown> }>;

            const collected: Record<string, { name: string; args: Record<string, unknown>; result: ToolResult; durationMs: number }> = {};

            try {
                for (let index = 0; index < steps.length; index += 1) {
                    const step = steps[index];
                    setProgress({ label: `获取数据：${step.name}`, percent: 30 + index * 20 });
                    const startAt = Date.now();
                    const raw = await executeToolStep({
                        name: step.name,
                        args: step.args,
                        label: step.name,
                        executor: resolveExecutor(step.name),
                    });
                    const result = normalizeToolResult(raw, resolveExecutor(step.name));
                    collected[step.name] = { ...step, result, durationMs: Date.now() - startAt };
                }

                const north = collected.get_north_fund_flow?.result;
                const sector = collected.get_sector_fund_flow?.result;
                const failed = north && !north.success
                    ? north
                    : sector && !sector.success
                        ? sector
                        : undefined;

                if (failed) {
                    const step: ToolStep = {
                        name: 'fund_flow_combo',
                        args: {},
                        label: '资金流向',
                    };
                    const assistantContent = formatToolText(step, failed);
                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: assistantContent,
                        createdAt: new Date(),
                    };
                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(currentSessionId, 'assistant', assistantContent);
                } else if (north && sector && north.success && sector.success) {
                    setProgress({ label: '生成总结：资金流向', percent: 100 });
                    const combinedData = {
                        variants: {
                            north: { label: '北向资金', data: north.data },
                            sector: { label: '板块资金', data: sector.data },
                        },
                        defaultView: 'north',
                    };
                    const comboStep: ToolStep = {
                        name: 'fund_flow_combo',
                        args: { steps },
                        label: '资金流向总览',
                        visualizationType: 'chart',
                    };
                    const toolResult: ToolResult = { success: true, data: combinedData, source: 'mcp' };
                    const visualization = buildVisualization(comboStep, toolResult.data);
                    const assistantContent = formatToolText(comboStep, toolResult);
                    const suggestions = buildToolSuggestions(comboStep, toolResult);

                    const toolCallPayload = {
                        name: comboStep.name,
                        args: comboStep.args,
                        result: toolResult,
                        meta: {
                            durationMs: (collected.get_north_fund_flow?.durationMs || 0)
                                + (collected.get_sector_fund_flow?.durationMs || 0),
                            source: 'mcp',
                            visualizationType: comboStep.visualizationType,
                        },
                    };

                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: assistantContent,
                        toolCall: toolCallPayload,
                        visualization,
                        suggestions,
                        createdAt: new Date(),
                    };

                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(
                        currentSessionId,
                        'assistant',
                        assistantContent,
                        toolCallPayload,
                        { visualization, suggestions }
                    );
                }
                await refreshBehaviorSummary();
            } finally {
                setIsLoading(false);
                setProgress(null);
            }
            return;
        }

        setIsLoading(true);
        setProgress({ label: `重试：${toolCall.name}`, percent: 20 });

        const step: ToolStep = {
            name: toolCall.name,
            args: toolCall.args || {},
            label: `重试 ${toolCall.name}`,
            visualizationType: toolCall.meta?.visualizationType,
            executor: resolveExecutor(toolCall.name),
        };

        try {
            const startAt = Date.now();
            const rawResult = await executeToolStep(step);
            const toolResult = normalizeToolResult(rawResult, step.executor || 'mcp');
            const durationMs = Date.now() - startAt;
            const visualization = toolResult.success ? buildVisualization(step, toolResult.data) : undefined;
            const assistantContent = formatToolText(step, toolResult);
            const source = toolResult.source || (toolResult.data as { source?: string } | undefined)?.source;

            const retryMessage: ChatMessage = {
                id: (Date.now() + Math.random()).toString(),
                role: 'assistant',
                content: assistantContent,
                toolCall: {
                    name: step.name,
                    args: step.args,
                    result: toolResult,
                    meta: {
                        durationMs,
                        source,
                        quality: toolResult.quality,
                        degraded: toolResult.degraded,
                        visualizationType: step.visualizationType,
                        requiresConfirmation: toolResult.requiresConfirmation,
                        confirmArgs: toolResult.requiresConfirmation
                            ? { ...(toolResult.confirmation?.arguments || step.args), _confirmed: true }
                            : undefined,
                        confirmMessage: toolResult.confirmation?.message || toolResult.error,
                    },
                },
                visualization,
                createdAt: new Date(),
            };

            setMessages(prev => [...prev, retryMessage]);
            await window.electronAPI.db.saveMessage(
                currentSessionId,
                'assistant',
                assistantContent,
                retryMessage.toolCall,
                { visualization }
            );
            await refreshBehaviorSummary();
        } finally {
            setIsLoading(false);
            setProgress(null);
        }
    };

    const handleConfirmTool = async (toolCall?: ChatMessage['toolCall']) => {
        if (!toolCall || !currentSessionId) return;

        const confirmArgs = toolCall.meta?.confirmArgs || { ...toolCall.args, _confirmed: true };

        setIsLoading(true);
        setProgress({ label: `确认执行：${toolCall.name}`, percent: 20 });

        const step: ToolStep = {
            name: toolCall.name,
            args: confirmArgs,
            label: `确认 ${toolCall.name}`,
            visualizationType: toolCall.meta?.visualizationType,
            executor: resolveExecutor(toolCall.name),
        };

        try {
            const startAt = Date.now();
            const rawResult = await executeToolStep(step);
            const toolResult = normalizeToolResult(rawResult, step.executor || 'mcp');
            const durationMs = Date.now() - startAt;
            const visualization = toolResult.success ? buildVisualization(step, toolResult.data) : undefined;
            const assistantContent = formatToolText(step, toolResult);
            const source = toolResult.source || (toolResult.data as { source?: string } | undefined)?.source;

            const confirmMessage: ChatMessage = {
                id: (Date.now() + Math.random()).toString(),
                role: 'assistant',
                content: assistantContent,
                toolCall: {
                    name: step.name,
                    args: step.args,
                    result: toolResult,
                    meta: {
                        durationMs,
                        source,
                        quality: toolResult.quality,
                        degraded: toolResult.degraded,
                        visualizationType: step.visualizationType,
                    },
                },
                visualization,
                createdAt: new Date(),
            };

            setMessages(prev => [...prev, confirmMessage]);
            await window.electronAPI.db.saveMessage(
                currentSessionId,
                'assistant',
                assistantContent,
                confirmMessage.toolCall,
                { visualization }
            );
            await refreshBehaviorSummary();
        } finally {
            setIsLoading(false);
            setProgress(null);
        }
    };

    const runDeepAnalysis = async (
        sessionId: string,
        query: string,
        planTitle: string | undefined,
        results: Array<{ name: string; args: Record<string, unknown>; result: ToolResult }>
    ) => {
        if (results.length === 0) return;
        try {
            setProgress({ label: '生成深度分析...', percent: 95 });
            const response = await window.electronAPI.ai.deepAnalysis({
                query,
                planTitle,
                toolResults: results.map(item => ({
                    name: item.name,
                    args: item.args,
                    result: item.result,
                })),
            });
            if (response.success && response.data?.content) {
                const message: ChatMessage = {
                    id: (Date.now() + Math.random()).toString(),
                    role: 'assistant',
                    content: response.data.content,
                    createdAt: new Date(),
                };
                setMessages(prev => [...prev, message]);
                await window.electronAPI.db.saveMessage(sessionId, 'assistant', message.content);
            } else if (response.error) {
                const message: ChatMessage = {
                    id: (Date.now() + Math.random()).toString(),
                    role: 'assistant',
                    content: `⚠️ 深度分析未生成：${response.error}`,
                    createdAt: new Date(),
                };
                setMessages(prev => [...prev, message]);
                await window.electronAPI.db.saveMessage(sessionId, 'assistant', message.content);
            }
        } catch (error) {
            console.error('[App] Deep analysis error:', error);
        }
    };

    // 发送消息
    const handleSendMessage = async (content: string) => {
        if (!content.trim()) return;
        const isFirstMessage = messages.length === 0;
        const stockMatch = content.match(/(\d{6})/);
        let shouldClearLoading = true;

        if (activeStreamIdRef.current) {
            await window.electronAPI.ai.cancel(activeStreamIdRef.current);
            activeStreamIdRef.current = null;
            streamMessageIdRef.current = null;
            streamSessionIdRef.current = null;
            streamBufferRef.current = '';
        }

        setProgress({ label: '解析意图中...', percent: 10 });

        // 确保有会话
        let sessionId = currentSessionId;
        if (!sessionId) {
            const result = await window.electronAPI.db.createSession('新对话');
            if (result.success && result.data) {
                sessionId = result.data.id;
                setCurrentSessionId(sessionId);
            } else {
                setProgress(null);
                setIsLoading(false);
                return;
            }
        }

        // 添加用户消息
        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content,
            createdAt: new Date(),
        };
        setMessages(prev => [...prev, userMessage]);
        setIsLoading(true);

        // 保存用户消息到数据库
        await window.electronAPI.db.saveMessage(sessionId, 'user', content);
        window.electronAPI.behavior.record({
            eventType: 'query',
            query: content,
            stockCode: stockMatch?.[1],
        }).catch(() => { });

        try {
            const clarification = buildClarification(content);
            if (clarification) {
                const assistantMessage: ChatMessage = {
                    id: (Date.now() + Math.random()).toString(),
                    role: 'assistant',
                    content: clarification.prompt,
                    suggestions: clarification.suggestions,
                    createdAt: new Date(),
                };
                setMessages(prev => [...prev, assistantMessage]);
                await window.electronAPI.db.saveMessage(
                    sessionId,
                    'assistant',
                    clarification.prompt,
                    undefined,
                    { suggestions: clarification.suggestions }
                );
                setProgress(null);
                return;
            }

            let plan = buildToolPlan(content, toolCatalogRef.current, skillCatalogRef.current);
            if (!plan) {
                // 使用优化后的合并搜索，只调用一次 AI planTool
                const combinedResolution = await resolvePlanFromCombinedSearch(content);
                if (combinedResolution?.clarification) {
                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: combinedResolution.clarification.prompt,
                        suggestions: combinedResolution.clarification.suggestions,
                        createdAt: new Date(),
                    };
                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(
                        sessionId,
                        'assistant',
                        combinedResolution.clarification.prompt,
                        undefined,
                        { suggestions: combinedResolution.clarification.suggestions }
                    );
                    setProgress(null);
                    return;
                }
                if (combinedResolution?.plan) {
                    plan = combinedResolution.plan;
                }
            }

            if (plan) {
                const missing = plan.steps
                    .filter(step => (step.executor || resolveExecutor(step.name)) === 'mcp')
                    .map(step => {
                        if (step.name === 'run_skill') {
                            const skillId = (step.args as { skill_id?: string }).skill_id;
                            const skillDef = skillId ? skillCatalogRef.current.get(skillId) : undefined;
                            const skillArgs = (step.args as { args?: Record<string, unknown> }).args || {};
                            return {
                                step,
                                missing: getMissingRequired(skillDef?.inputSchema, skillArgs),
                            };
                        }
                        const toolDef = toolCatalogRef.current.get(step.name);
                        return {
                            step,
                            missing: getMissingRequired(toolDef?.inputSchema, step.args),
                        };
                    })
                    .find(entry => entry.missing.length > 0);

                if (missing) {
                    const clarification = missing.step.name === 'run_skill'
                        ? buildSkillClarification(
                            (missing.step.args as { skill_id?: string }).skill_id || 'unknown_skill',
                            missing.missing,
                            content
                        )
                        : buildToolClarification(missing.step.name, missing.missing, content);
                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: clarification.prompt,
                        suggestions: clarification.suggestions,
                        createdAt: new Date(),
                    };
                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(
                        sessionId,
                        'assistant',
                        clarification.prompt,
                        undefined,
                        { suggestions: clarification.suggestions }
                    );
                    setProgress(null);
                    return;
                }
            }

            if (!plan) {
                setProgress({ label: 'AI 生成中...', percent: 60 });
                if (isFirstMessage) {
                    await window.electronAPI.db.updateSessionTitle(sessionId, content.slice(0, 20));
                }
                const assistantId = (Date.now() + Math.random()).toString();
                const assistantMessage: ChatMessage = {
                    id: assistantId,
                    role: 'assistant',
                    content: '',
                    createdAt: new Date(),
                };
                setMessages(prev => [...prev, assistantMessage]);

                streamBufferRef.current = '';
                streamMessageIdRef.current = assistantId;
                streamSessionIdRef.current = sessionId;

                const aiMessages = buildAIMessages(messages, content);
                const streamResult = await window.electronAPI.ai.stream(aiMessages);

                if (!streamResult.success || !streamResult.data) {
                    const errorContent = `❌ AI 响应失败：${streamResult.error || '无法启动流式响应'}`;
                    setMessages(prev => prev.map(message => (
                        message.id === assistantId ? { ...message, content: errorContent } : message
                    )));
                    await window.electronAPI.db.saveMessage(sessionId, 'assistant', errorContent);
                    setProgress(null);
                    return;
                }

                activeStreamIdRef.current = streamResult.data.streamId;
                shouldClearLoading = false;
                return;
            }

            if (isFirstMessage && plan.title) {
                await window.electronAPI.db.updateSessionTitle(sessionId, plan.title);
            }

            const totalSteps = plan.steps.length;
            const collectedResults: Record<string, { step: ToolStep; result: ToolResult; durationMs: number }> = {};
            const analysisResults: Array<{ name: string; args: Record<string, unknown>; result: ToolResult }> = [];
            for (let index = 0; index < totalSteps; index += 1) {
                const step = plan.steps[index];
                const executor = step.executor || resolveExecutor(step.name);
                setProgress({
                    label: `获取数据：${step.label} (${index + 1}/${totalSteps})`,
                    percent: Math.round(((index + 1) / totalSteps) * 100),
                });

                const startAt = Date.now();
                const rawResult = await executeToolStep({ ...step, executor });
                if (step.visualizationType) {
                    setProgress({
                        label: `渲染图表：${step.label}`,
                        percent: Math.min(100, Math.round(((index + 1) / totalSteps) * 100)),
                    });
                }
                const toolResult = normalizeToolResult(rawResult, executor);
                const durationMs = Date.now() - startAt;
                if (step.collectKey) {
                    collectedResults[step.collectKey] = { step, result: toolResult, durationMs };
                }
                analysisResults.push({ name: step.name, args: step.args, result: toolResult });

                const shouldRender = !step.silent || !toolResult.success;
                if (shouldRender) {
                    setProgress({
                        label: `生成总结：${step.label}`,
                        percent: Math.min(100, Math.round(((index + 1) / totalSteps) * 100)),
                    });

                    const visualization = toolResult.success ? buildVisualization(step, toolResult.data) : undefined;
                    const assistantContent = formatToolText(step, toolResult);
                    const suggestions = buildToolSuggestions(step, toolResult);
                    const source = toolResult.source
                        || (toolResult.data as { source?: string } | undefined)?.source
                        || (executor === 'local' ? 'local' : undefined);
                    const toolCall = {
                        name: step.name,
                        args: step.args,
                        result: toolResult,
                        meta: {
                            durationMs,
                            source,
                            quality: toolResult.quality,
                            degraded: toolResult.degraded,
                            visualizationType: step.visualizationType,
                            requiresConfirmation: toolResult.requiresConfirmation,
                            confirmArgs: toolResult.requiresConfirmation
                                ? { ...(toolResult.confirmation?.arguments || step.args), _confirmed: true }
                                : undefined,
                            confirmMessage: toolResult.confirmation?.message || toolResult.error,
                        },
                    };

                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: assistantContent,
                        toolCall,
                        visualization,
                        suggestions,
                        createdAt: new Date(),
                    };

                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(
                        sessionId,
                        'assistant',
                        assistantContent,
                        toolCall,
                        { visualization, suggestions }
                    );

                    if (toolResult.requiresConfirmation) {
                        setProgress(null);
                        await refreshBehaviorSummary();
                        return;
                    }
                }

                const stepStockCode = step.name === 'run_skill'
                    ? (step.args as { args?: { stock_code?: unknown } }).args?.stock_code
                    : (step.args as { stock_code?: unknown }).stock_code;
                window.electronAPI.behavior.record({
                    eventType: 'tool_call',
                    toolName: step.name,
                    stockCode: typeof stepStockCode === 'string' ? stepStockCode : undefined,
                }).catch(() => { });
            }

            if (plan.combineId === 'fundFlow') {
                const northEntry = collectedResults.north;
                const sectorEntry = collectedResults.sector;

                if (northEntry && sectorEntry && northEntry.result.success && sectorEntry.result.success) {
                    const north = northEntry.result;
                    const sector = sectorEntry.result;
                    setProgress({ label: '生成总结：资金流向', percent: 100 });
                    const combinedData = {
                        variants: {
                            north: { label: '北向资金', data: north.data },
                            sector: { label: '板块资金', data: sector.data },
                        },
                        defaultView: 'north',
                    };

                    const comboStep: ToolStep = {
                        name: 'fund_flow_combo',
                        args: {
                            steps: [
                                {
                                    name: northEntry.step.name,
                                    args: northEntry.step.args,
                                    durationMs: northEntry.durationMs,
                                },
                                {
                                    name: sectorEntry.step.name,
                                    args: sectorEntry.step.args,
                                    durationMs: sectorEntry.durationMs,
                                },
                            ],
                        },
                        label: '资金流向总览',
                        visualizationType: 'chart',
                    };

                    const toolResult: ToolResult = { success: true, data: combinedData, source: 'mcp' };
                    const visualization = buildVisualization(comboStep, toolResult.data);
                    const assistantContent = formatToolText(comboStep, toolResult);
                    const suggestions = buildToolSuggestions(comboStep, toolResult);
                    const totalDuration = northEntry.durationMs + sectorEntry.durationMs;

                    const toolCall = {
                        name: comboStep.name,
                        args: comboStep.args,
                        result: toolResult,
                        meta: {
                            durationMs: totalDuration,
                            source: 'mcp',
                            visualizationType: comboStep.visualizationType,
                        },
                    };

                    const assistantMessage: ChatMessage = {
                        id: (Date.now() + Math.random()).toString(),
                        role: 'assistant',
                        content: assistantContent,
                        toolCall,
                        visualization,
                        suggestions,
                        createdAt: new Date(),
                    };

                    setMessages(prev => [...prev, assistantMessage]);
                    await window.electronAPI.db.saveMessage(
                        sessionId,
                        'assistant',
                        assistantContent,
                        toolCall,
                        { visualization, suggestions }
                    );
                }
            }

            if (plan.deepAnalysis && analysisResults.some(item => item.result.success)) {
                await runDeepAnalysis(sessionId, content, plan.title, analysisResults);
            }
            setProgress(null);
            await refreshBehaviorSummary();
        } catch (error) {
            console.error('[App] Error:', error);
            setProgress(null);
        } finally {
            if (shouldClearLoading) {
                setIsLoading(false);
            }
        }
    };

    const quickActions = buildQuickActions(activeMode, behaviorSummary);

    return (
        <div className="app">
            <header className="app-header">
                <div className="header-left">
                    <button
                        className="sidebar-toggle"
                        onClick={() => setShowSidebar(!showSidebar)}
                        title={showSidebar ? '隐藏侧边栏' : '显示侧边栏'}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                            <line x1="9" y1="3" x2="9" y2="21" />
                        </svg>
                    </button>
                    <h1>
                        <svg width="32" height="32" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="logo-icon">
                            <defs>
                                {/* 主渐变：紫→蓝 */}
                                <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stopColor="#8B5CF6" />
                                    <stop offset="50%" stopColor="#667EEA" />
                                    <stop offset="100%" stopColor="#5E8AFA" />
                                </linearGradient>
                                {/* 外发光滤镜 - 增强版 */}
                                <filter id="outerGlow" x="-100%" y="-100%" width="300%" height="300%">
                                    <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="blur1" />
                                    <feGaussianBlur in="SourceAlpha" stdDeviation="6" result="blur2" />
                                    <feFlood floodColor="#8B5CF6" floodOpacity="0.8" result="color1" />
                                    <feFlood floodColor="#667EEA" floodOpacity="0.4" result="color2" />
                                    <feComposite in="color1" in2="blur1" operator="in" result="glow1" />
                                    <feComposite in="color2" in2="blur2" operator="in" result="glow2" />
                                    <feMerge>
                                        <feMergeNode in="glow2" />
                                        <feMergeNode in="glow1" />
                                        <feMergeNode in="SourceGraphic" />
                                    </feMerge>
                                </filter>
                                {/* 3D阴影效果 */}
                                <filter id="shadow3D" x="-50%" y="-50%" width="200%" height="200%">
                                    <feGaussianBlur in="SourceAlpha" stdDeviation="2" />
                                    <feOffset dx="2" dy="3" result="offsetblur" />
                                    <feComponentTransfer>
                                        <feFuncA type="linear" slope="0.5" />
                                    </feComponentTransfer>
                                    <feMerge>
                                        <feMergeNode />
                                        <feMergeNode in="SourceGraphic" />
                                    </feMerge>
                                </filter>
                            </defs>

                            {/* 3D阴影层 */}
                            <path
                                d="M 50 12 L 83 78 L 70 78 L 50 37 L 30 78 L 17 78 Z"
                                fill="#000000"
                                opacity="0.3"
                                filter="url(#shadow3D)"
                            />

                            {/* 等腰三角形外轮廓 - 字母A的形状 */}
                            <path
                                d="M 50 10 L 83 76 L 70 76 L 50 35 L 30 76 L 17 76 Z"
                                fill="url(#logoGradient)"
                                filter="url(#outerGlow)"
                                className="logo-triangle"
                            />

                            {/* 负空间创造向上箭头 - 中间的横杠 */}
                            <path
                                d="M 38 58 L 62 58 L 59 66 L 41 66 Z"
                                fill="#0F1419"
                                opacity="0.95"
                                className="logo-arrow"
                            />

                            {/* 顶部高光效果 - 增强 */}
                            <path
                                d="M 50 10 L 58 28 L 50 24 L 42 28 Z"
                                fill="white"
                                opacity="0.3"
                            />

                            {/* 边缘高光 */}
                            <path
                                d="M 50 10 L 83 76 L 80 76 L 50 13 Z"
                                fill="white"
                                opacity="0.1"
                            />
                        </svg>
                        AetherTrade
                    </h1>
                </div>

                <div className="header-right">
                    <div className="mode-switch">
                        <button
                            className={activeMode === 'market' ? 'active' : ''}
                            onClick={() => setActiveMode('market')}
                        >
                            市场
                        </button>
                        <button
                            className={activeMode === 'stock' ? 'active' : ''}
                            onClick={() => setActiveMode('stock')}
                        >
                            个股
                        </button>
                        <button
                            className={activeMode === 'portfolio' ? 'active' : ''}
                            onClick={() => setActiveMode('portfolio')}
                        >
                            组合
                        </button>
                    </div>
                    <button
                        className="layout-toggle"
                        onClick={() => setLayoutMode(prev => (prev === 'split' ? 'single' : 'split'))}
                        title={layoutMode === 'split' ? '切换单栏' : '切换分栏'}
                    >
                        {layoutMode === 'split' ? '分栏' : '单栏'}
                    </button>
                    <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
                        <span className="status-dot"></span>
                        {isConnected ? 'Connected' : 'Disconnected'}
                    </span>
                    <button className="workbench-btn" title="功能工作台" onClick={() => setShowWorkbench(true)}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="3" />
                            <path d="M3 9h18M9 9v12" />
                        </svg>
                    </button>
                    <button className="settings-btn" title="设置" onClick={() => setShowSettings(true)}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="3" />
                            <path d="M12 1v6m0 6v6M5.64 5.64l4.24 4.24m4.24 4.24l4.24 4.24M1 12h6m6 0h6M5.64 18.36l4.24-4.24m4.24-4.24l4.24-4.24" />
                        </svg>
                    </button>
                </div>
            </header>
            <div className="app-body">
                {showSidebar && (
                    <SessionSidebar
                        currentSessionId={currentSessionId}
                        onSelectSession={loadSession}
                        onNewSession={handleNewSession}
                        onToggleSidebar={() => setShowSidebar(prev => !prev)}
                    />
                )}
                <main className="app-main">
                    <div className="chat-area">
                        <ChatPanel
                            messages={messages}
                            isLoading={isLoading}
                            actions={quickActions}
                            progress={progress}
                            onSendMessage={handleSendMessage}
                            onSuggestion={handleSuggestion}
                            onRetryTool={handleRetryTool}
                            onConfirmTool={handleConfirmTool}
                            onPinVisualization={setPinnedVisualization}
                        />
                    </div>
                    {(layoutMode === 'split' || pinnedVisualization) && (
                        <aside className="pinned-panel">
                            <div className="pinned-header">
                                <span>📌 固定面板</span>
                                <button
                                    className="tool-action-btn"
                                    onClick={() => setPinnedVisualization(null)}
                                    disabled={!pinnedVisualization}
                                >
                                    清空
                                </button>
                            </div>
                            <div className="pinned-content">
                                {pinnedVisualization ? (
                                    <VisualizationRenderer visualization={pinnedVisualization} />
                                ) : (
                                    <div className="empty-text">暂无固定图表，可在对话中点击“固定图表”。</div>
                                )}
                            </div>
                        </aside>
                    )}
                </main>
            </div>

            {/* 设置弹窗 */}
            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSave={(config) => {
                    console.log('[App] API config saved:', config);
                    // 配置保存后可以更新连接状态
                    setIsConnected(config.isValid);
                }}
            />
            <WorkbenchModal
                isOpen={showWorkbench}
                onClose={() => setShowWorkbench(false)}
            />
        </div>
    );
};

export default App;
