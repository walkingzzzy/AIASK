/**
 * 兼容性层 - 参数适配器
 * 
 * 负责将旧工具的参数转换为新工具请求所需的参数格式
 */

import { LEGACY_ALIASES } from './alias-registry.js';

/**
 * 适配旧参数到新参数
 * 
 * @param oldToolName 旧工具名
 * @param oldParams 旧参数对象
 * @returns 新参数对象（包含注入的 action/type 等）
 */
export function adaptParams(oldToolName: string, oldParams: Record<string, unknown>): Record<string, unknown> {
    const alias = LEGACY_ALIASES[oldToolName];
    if (!alias) {
        // 如果没有别名映射，原样返回（假定是新工具或未映射工具）
        return oldParams;
    }

    const newParams = { ...oldParams };

    // 注入预定义参数 (action, type, etc.)
    if (alias.injectedParams) {
        Object.assign(newParams, alias.injectedParams);
    }

    // 处理特殊转换逻辑（如果有）
    // 目前主要是直接注入，暂无复杂的字段名映射需求
    // 如果将来有字段重命名需求，可以在这里添加 switch case

    return newParams;
}

/**
 * 获取工具的映射名称
 * @param toolName 可能的旧工具名
 * @returns 新工具名（如果没有映射则返回原名）
 */
export function resolveToolName(toolName: string): string {
    const alias = LEGACY_ALIASES[toolName];
    return alias ? alias.newTool : toolName;
}
