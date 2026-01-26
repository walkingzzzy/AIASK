/**
 * 工具注册表访问器
 * 避免 discovery 直接依赖 index.ts 造成循环引用
 */

import type { ToolDefinition, ToolRegistryItem } from '../types/tools.js';

let toolRegistry: ToolRegistryItem[] = [];

export function setToolRegistry(items: ToolRegistryItem[]): void {
    toolRegistry = items;
}

export function getToolRegistry(): ToolRegistryItem[] {
    return toolRegistry;
}

export function getToolDefinitions(): ToolDefinition[] {
    return toolRegistry.map(item => item.definition);
}
