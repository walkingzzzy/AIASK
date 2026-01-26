/**
 * 工具相关类型定义
 */

import { z } from 'zod';

/**
 * 数据来源类型
 * 
 * 新增 2026-01-14 (P0-2 修复):
 * - real: 真实市场数据（来自 API/数据库）
 * - simulated: 模拟/随机生成的数据（不可用于生产决策）
 * - fallback: 降级数据（部分真实，部分回退/缓存）
 */
export type DataSourceType = 'real' | 'simulated' | 'fallback' | 'static' | 'calculated' | 'calculated_estimate';

/**
 * 数据质量等级
 */
export type DataQualityLevel = 'high' | 'medium' | 'low' | 'unknown';

/**
 * 工具参数 Schema 基类
 */
export type ToolSchema = z.ZodObject<z.ZodRawShape>;

/**
 * 工具定义
 * 
 * 优化 2026-01-14:
 * - 添加 tags 支持工具标签/分组
 * - 添加 priority 支持快速分析模式
 * - 添加 dataSource 标记数据来源类型 (P0-2 修复)
 */
export interface ToolDefinition {
    name: string;
    description: string;
    category: string;
    inputSchema: ToolSchema;
    requiresConfirmation?: boolean;
    /** 工具标签，用于分组和筛选 (如: ['core', 'quick-analysis']) */
    tags?: string[];
    /** 工具优先级，用于快速分析模式 (1-10, 10最高) */
    priority?: number;
    /**
     * 数据来源类型，默认为 'real'
     * 使用 Math.random() 或模拟数据的工具应显式标记为 'simulated'
     * 快速分析模式将排除 'simulated' 类型的工具
     */
    dataSource?: DataSourceType;
    /**
     * 工具别名列表，用于支持常见的命名变体
     * 例如: ['calculate_var', 'calc_var'] 可以作为 'analyze_portfolio_risk' 的别名
     * 新增 2026-01-15: 支持工具别名机制
     */
    aliases?: string[];
}

/**
 * 工具调用结果
 * 
 * P1-2 修复 2026-01-14:
 * - 添加 source 属性用于透传真实数据源信息
 */
export interface ToolResult {
    success: boolean;
    data?: unknown;
    error?: string;
    /** Zod 校验错误详情（仅在参数校验失败时存在） */
    validationErrors?: Array<{
        code: string;
        message: string;
        path: (string | number)[];
    }>;
    /** 数据来源标识 (P1-2 修复: 从 adapter 透传) */
    source?: string;
    /** 数据质量等级 (P1-5 修复: 用于透传 adapter 质量信息) */
    quality?: DataQualityLevel;
    /** 是否为降级数据 (P1-5 修复) */
    degraded?: boolean;
}

/**
 * 工具处理器函数
 */
export type ToolHandler<T = any> = (params: T) => Promise<ToolResult>;

/**
 * 工具注册表项
 */
export interface ToolRegistryItem {
    definition: ToolDefinition;
    handler: ToolHandler<any>;
}

/**
 * MCP 资源定义
 */
export interface ResourceDefinition {
    uri: string;
    name: string;
    description: string;
    mimeType: string;
}

/**
 * MCP 提示定义
 */
export interface PromptDefinition {
    name: string;
    description: string;
    arguments?: Array<{
        name: string;
        description: string;
        required?: boolean;
    }>;
}
