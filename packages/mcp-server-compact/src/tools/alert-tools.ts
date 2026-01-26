/**
 * 高级告警工具
 * 支持组合条件告警、技术指标告警等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { timescaleDB } from '../storage/timescaledb.js';

// 告警条件类型
interface AlertCondition {
    type: 'price' | 'indicator' | 'volume' | 'change';
    code?: string;
    operator: 'gt' | 'lt' | 'eq' | 'gte' | 'lte' | 'cross_above' | 'cross_below';
    value: number;
    indicator?: string;
}

// ========== create_combo_alert ==========

const normalizeComboOperator = (value: unknown) => {
    if (typeof value !== 'string') return value;
    const normalized = value.trim().toLowerCase();
    const map: Record<string, string> = {
        '>': 'gt',
        '<': 'lt',
        '>=': 'gte',
        '<=': 'lte',
        '=': 'eq',
        '==': 'eq',
    };
    return map[normalized] || normalized;
};

const normalizeLogic = (value: unknown) => {
    if (typeof value !== 'string') return value;
    const normalized = value.trim().toLowerCase();
    if (normalized === '&&') return 'and';
    if (normalized === '||') return 'or';
    return normalized;
};

const createComboAlertSchema = z.object({
    name: z.string().describe('告警名称'),
    conditions: z.array(z.object({
        type: z.enum(['price', 'indicator', 'volume', 'change']).describe('条件类型'),
        code: z.string().optional().describe('股票代码'),
        operator: z.preprocess(
            normalizeComboOperator,
            z.enum(['gt', 'lt', 'eq', 'gte', 'lte', 'cross_above', 'cross_below'])
        ).describe('比较运算符'),
        value: z.number().describe('阈值'),
        indicator: z.string().optional().describe('指标名称'),
    })).min(1).describe('告警条件列表'),
    logic: z.preprocess(normalizeLogic, z.enum(['and', 'or'])).optional().default('and').describe('条件逻辑关系'),
});

const createComboAlertTool: ToolDefinition = {
    name: 'create_combo_alert',
    description: '创建多条件组合告警（价格+指标+成交量等）',
    category: 'alerts',
    inputSchema: createComboAlertSchema,
    tags: ['alert', 'combo', 'condition'],
    dataSource: 'real',
};

const createComboAlertHandler: ToolHandler<z.infer<typeof createComboAlertSchema>> = async (params) => {
    try {
        const id = await timescaleDB.createComboAlert({
            name: params.name,
            conditions: params.conditions,
            logic: params.logic || 'and'
        });

        return {
            success: true,
            data: {
                alertId: id,
                name: params.name,
                conditions: params.conditions,
                logic: params.logic,
                status: 'active',
                message: `组合告警 "${params.name}" 创建成功`,
            },
            source: 'database',
        };
    } catch (error) {
        return {
            success: false,
            error: `创建告警失败: ${error}`,
        };
    }
};

// ========== create_indicator_alert ==========

const createIndicatorAlertSchema = z.object({
    code: z.string().describe('股票代码'),
    indicator: z.preprocess(
        (value) => typeof value === 'string' ? value.trim().toLowerCase() : value,
        z.enum(['rsi', 'macd', 'kdj', 'boll', 'ma5', 'ma10', 'ma20', 'ma60'])
    ).describe('技术指标'),
    condition: z.preprocess(
        (value) => typeof value === 'string' ? value.trim().toLowerCase() : value,
        z.enum(['oversold', 'overbought', 'golden_cross', 'death_cross', 'break_upper', 'break_lower', 'gt', 'lt'])
    ).describe('触发条件'),
    value: z.number().optional().describe('阈值（部分条件需要）'),
});

const createIndicatorAlertTool: ToolDefinition = {
    name: 'create_indicator_alert',
    description: '创建技术指标告警（RSI超卖、MACD金叉等）',
    category: 'alerts',
    inputSchema: createIndicatorAlertSchema,
    tags: ['alert', 'indicator', 'technical'],
    dataSource: 'real',
};

const indicatorConditionDescriptions: Record<string, string> = {
    oversold: '超卖（RSI<30 / KDJ<20）',
    overbought: '超买（RSI>70 / KDJ>80）',
    golden_cross: '金叉',
    death_cross: '死叉',
    break_upper: '突破上轨',
    break_lower: '突破下轨',
    gt: '大于阈值',
    lt: '小于阈值',
};

const createIndicatorAlertHandler: ToolHandler<z.infer<typeof createIndicatorAlertSchema>> = async (params) => {
    try {
        const id = await timescaleDB.createIndicatorAlert({
            code: params.code,
            indicator: params.indicator,
            condition: params.condition,
            value: params.value
        });

        return {
            success: true,
            data: {
                alertId: id,
                stockCode: params.code,
                indicator: params.indicator.toUpperCase(),
                condition: params.condition,
                conditionDescription: indicatorConditionDescriptions[params.condition] || params.condition,
                threshold: params.value,
                status: 'active',
                message: `指标告警创建成功：${params.code} ${params.indicator.toUpperCase()} ${indicatorConditionDescriptions[params.condition]}`,
            },
            source: 'database',
        };
    } catch (error) {
        return {
            success: false,
            error: `创建指标告警失败: ${error}`,
        };
    }
};

// ========== check_all_alerts ==========

const checkAllAlertsSchema = z.object({
    type: z.enum(['all', 'combo', 'indicator', 'price']).optional().default('all').describe('告警类型筛选'),
    status: z.enum(['all', 'active', 'triggered']).optional().default('active').describe('状态筛选'),
});

const checkAllAlertsTool: ToolDefinition = {
    name: 'check_all_alerts',
    description: '检查所有告警状态',
    category: 'alerts',
    inputSchema: checkAllAlertsSchema,
    tags: ['alert', 'check', 'status'],
    dataSource: 'real',
};

const checkAllAlertsHandler: ToolHandler<z.infer<typeof checkAllAlertsSchema>> = async (params) => {
    try {
        // Map param type to specific union values
        const type: 'all' | 'combo' | 'indicator' =
            (params.type === 'combo' || params.type === 'indicator')
                ? params.type
                : 'all';

        const rawAlerts = await timescaleDB.getAlerts(type, params.status as any);

        const alerts = rawAlerts.map((a: any) => ({
            type: a.type,
            id: a.id,
            name: a.name,
            stockCode: a.stock_code,
            indicator: a.indicator,
            condition: a.conditions || a.condition,
            status: a.status,
            createdAt: a.created_at instanceof Date ? a.created_at.toISOString() : a.created_at
        }));

        return {
            success: true,
            data: {
                filter: {
                    type: params.type,
                    status: params.status,
                },
                total: alerts.length,
                alerts,
                summary: {
                    combo: alerts.filter((a: any) => a.type === 'combo').length,
                    indicator: alerts.filter((a: any) => a.type === 'indicator').length,
                    active: alerts.filter((a: any) => a.status === 'active').length,
                    triggered: alerts.filter((a: any) => a.status === 'triggered').length,
                },
            },
            source: 'database',
        };
    } catch (error) {
        return {
            success: false,
            error: `查询告警失败: ${error}`,
        };
    }
};

// ========== 注册导出 ==========

export const alertTools: ToolRegistryItem[] = [
    { definition: createComboAlertTool, handler: createComboAlertHandler },
    { definition: createIndicatorAlertTool, handler: createIndicatorAlertHandler },
    { definition: checkAllAlertsTool, handler: checkAllAlertsHandler },
];

