/**
 * 发现与元数据工具
 * 帮助用户了解可用的工具和技能
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
// 注意：这里会有循环依赖风险如果直接导入 index.ts 中的 allTools
// 更好的做法是在 index.ts 中注册时注入到 registry，或者 discovery 动态读取 registry
// 为了简单，我们定义 handler 时不直接依赖 registry，而是由 index.ts 传递 context 或者 discovery 只是静态返回 categories
import { TOOL_CATEGORIES } from '../config/constants.js';
import { getToolDefinitions } from './registry.js';

function normalizeCategory(raw?: string): string | undefined {
    if (!raw) return undefined;
    return raw.toLowerCase().replace(/_/g, '-');
}

// ========== get_available_categories ==========

const getCategoriesSchema = z.object({});

const getCategoriesTool: ToolDefinition = {
    name: 'get_available_categories',
    description: '获取所有可用的工具分类及说明',
    category: 'discovery',
    inputSchema: getCategoriesSchema,
    tags: ['discovery', 'meta'],
    dataSource: 'static',
};

const getCategoriesHandler: ToolHandler<z.infer<typeof getCategoriesSchema>> = async () => {
    return {
        success: true,
        data: TOOL_CATEGORIES,
        source: 'config',
    };
};

// ========== search_tools ==========

const searchToolsSchema = z.object({
    keyword: z.string().describe('搜索关键词'),
    category: z.string().optional().describe('可选分类过滤'),
});

const searchToolsTool: ToolDefinition = {
    name: 'search_tools',
    description: '搜索所有可用的 MCP 工具',
    category: 'discovery',
    inputSchema: searchToolsSchema,
    tags: ['discovery', 'meta'],
    dataSource: 'static',
};

// 这里需要一种方式访问所有工具。
// 我们可以让 index.ts set 一个 global registry 或者 context
// 暂时我们返回一个 "请使用 MCP 客户端自带的 listTools 功能" 的提示，
// 或者 hardcode 一些核心工具。
// 为了演示，这里我们留一个 placeholder，真正逻辑在注册中心层实现更好。

const searchToolsHandler: ToolHandler<z.infer<typeof searchToolsSchema>> = async (params) => {
    const keyword = params.keyword?.trim().toLowerCase();
    const categoryFilter = normalizeCategory(params.category);
    const definitions = getToolDefinitions();

    const filtered = definitions.filter(def => {
        if (categoryFilter && normalizeCategory(def.category) !== categoryFilter) {
            return false;
        }
        if (!keyword) return true;
        const haystack = [
            def.name,
            def.description,
            def.category,
            ...(def.tags || []),
        ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase();
        return haystack.includes(keyword);
    });

    return {
        success: true,
        data: {
            total: filtered.length,
            tools: filtered,
            filter: {
                keyword: params.keyword,
                category: params.category || 'all',
            },
        },
        source: 'registry',
    };
};


// ========== available_tools ==========

const availableToolsSchema = z.object({
    category: z.string().optional().describe('可选分类过滤'),
});

const availableToolsTool: ToolDefinition = {
    name: 'available_tools',
    description: '列出所有可用的工具（可按分类过滤）',
    category: 'discovery',
    inputSchema: availableToolsSchema,
    tags: ['discovery', 'meta'],
    dataSource: 'static',
};

const availableToolsHandler: ToolHandler<z.infer<typeof availableToolsSchema>> = async (params) => {
    const categoryFilter = normalizeCategory(params.category);
    const definitions = getToolDefinitions();
    const filtered = categoryFilter
        ? definitions.filter(def => normalizeCategory(def.category) === categoryFilter)
        : definitions;

    return {
        success: true,
        data: {
            total: filtered.length,
            tools: filtered,
            categories: Object.keys(TOOL_CATEGORIES),
            filter: params.category || 'all',
        },
        source: 'registry',
    };
};

// ========== 注册导出 ==========

export const discoveryTools: ToolRegistryItem[] = [
    { definition: getCategoriesTool, handler: getCategoriesHandler },
    { definition: availableToolsTool, handler: availableToolsHandler },
    { definition: searchToolsTool, handler: searchToolsHandler },
];
