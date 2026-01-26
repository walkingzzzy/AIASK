/**
 * 兼容性层 - 路由分发器
 * 
 * 拦截工具调用，自动应用参数适配，并路由到新工具实现
 */

import { resolveToolName, adaptParams } from './param-adapter.js';

/**
 * 兼容性工具调用处理器
 * 
 * @param toolName 调用的工具名（可能是旧名）
 * @param params 参数对象
 * @param next 下一步处理函数（实际的工具执行器）
 */
export async function routeToolCall(
    toolName: string,
    params: Record<string, unknown>,
    next: (name: string, params: Record<string, unknown>) => Promise<any>
): Promise<any> {
    const newToolName = resolveToolName(toolName);
    const newParams = adaptParams(toolName, params);

    // 即使名称没变，也可能注入了参数（针对同名但需要注入 action 的情况，虽然目前 mapping 表中同名通常 direct）
    // mapping 表中同名基本都是 direct，但有了 param-adapter 统一处理更稳健

    if (newToolName !== toolName) {
        console.debug(`[Compat] Redirecting legacy tool '${toolName}' to '${newToolName}' with params:`, Object.keys(newParams));
    }

    return next(newToolName, newParams);
}
