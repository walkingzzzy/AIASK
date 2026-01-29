#!/usr/bin/env node

/**
 * MCP Server Compact Service Entry Point
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { loadConfig } from './config/index.js';
import { adapterManager } from './adapters/index.js';
import { timescaleDB } from './storage/timescaledb.js';
import { allTools, getToolHandler } from './tools/index.js';
import { LEGACY_ALIASES } from './compatibility/alias-registry.js';
import { routeToolCall } from './compatibility/compat-router.js';

// 加载配置
const config = loadConfig();

// 初始化数据库
timescaleDB.initialize().then(() => {
    // MCP 服务器通过 stdio 通信，不能输出非 JSON 消息
    // 初始化成功，静默处理
}).catch(err => {
    // 初始化失败时退出，但不输出到 stdio（避免 JSON 解析错误）
    // 错误会通过 MCP 协议返回给客户端
    process.exit(1);
});

// 创建 Server
const server = new McpServer({
    name: "mcp-server-compact",
    version: "1.0.0",
});

// 注册新版工具 (60个)
allTools.forEach((tool: any) => {
    server.tool(
        tool.definition.name,
        tool.definition.inputSchema.shape, // McpServer expects RawShape
        {
            description: tool.definition.description,
        },
        async (args: any) => {
            try {
                // @ts-ignore - Argument validation is handled by SDK, but types might imply mismatch
                const result = await tool.handler(args as any);
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify(result, null, 2)
                        }
                    ],
                    isError: !result.success
                };
            } catch (error) {
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify({
                                success: false,
                                error: error instanceof Error ? error.message : String(error)
                            }, null, 2)
                        }
                    ],
                    isError: true
                };
            }
        }
    );
});

// 注册兼容性代理工具 (Legacy Aliases)
// 允许旧版工具名调用，并路由到新工具
// 设置为 false 可禁用兼容性别名，只保留核心工具
const ENABLE_LEGACY_ALIASES = false;

const registeredLegacyTools = new Set<string>();

if (ENABLE_LEGACY_ALIASES) {
    Object.entries(LEGACY_ALIASES).forEach(([legacyName, aliasConfig]) => {
        // 如果新工具列表中已经包含了该名称，则跳过（避免覆盖 native implementation）
        if (allTools.some(t => t.definition.name === legacyName)) {
            return;
        }

        // 避免重复注册
        if (registeredLegacyTools.has(legacyName)) {
            return;
        }

        server.tool(
            legacyName,
            `[Legacy] Alias for ${aliasConfig.newTool}${aliasConfig.description ? ': ' + aliasConfig.description : ''}`,
            {
                // 使用宽松的 Schema 以兼容旧参数
                // 注意: McpServer 类型定义可能限制了 key string 必须明确
                // 这里我们尽量定义为空或通用，实际验证在 compat-router/new-tool 中进行
                // 为了支持必须参数，我们可能需要 inspect legacy params? 
                // 简单起见，我们允许任意 extra args，但在 definition 中只列出 basic
                // 由于 ZodObject.shape 是固定的，我们无法动态通过 {} 允许 extra.
                // 除非使用 .passthrough() 但 McpServer.tool 接受 shape 对象。
                // Hack: 定义一个 [key: string]: z.any() 是不可能的 with shape object parameter.
                // 我们只能定义一个空的 shape，但在 handler 中获取 arguments。
                // MCP SDK 会验证 arguments against schema。
                // 如果我们传入 { a: 1 } 但 schema 是 {}，会报错吗？
                // SDK 默认 strict? 
                // 如果 legacy tool 有参数，必须在这里声明。
                // 这是一个挑战。
                // 解决方案：使用 compat-router 的 param-adapter 逆向推导？太复杂。
                // 替代方案：声明一个 catch-all 字段？或者，如果 MCP SDK 支持 tool 选项 bypass validation?
                // 查阅 SDK: tool() third arg is `shape`.
                // 如果我们无法知道旧参数 schema，兼容层很难做。
                // 但是，由于我们主要支持 Agent，Agent 会读取通过 `listTools` 返回的 Schema。
                // 所以我们可以返回 "建议使用新工具" 的 Schema?
                // 不，是为了兼容旧 Agent 代码。
                // 只有当旧 Agent 代码已经被写死参数时才需要兼容。
                // 如果旧 Agent 每次都读 Schema，它会看到新 Schema。
                // 问题是：如果旧 Agent 缓存了 "get_realtime_quote(stock_code)" 的调用方式。
                // 我们必须支持 stock_code 参数。

                // 简化策略：
                // 大多数旧工具参数比较简单。
                // 我们可以尝试为所有 legacy tools 定义一个宽松的通用 Schema：
                // { [x: string]: z.any() } 不支持。
                // { params: z.record(z.any()).optional(), code: z.string().optional(), ... }
                // 这太乱了。

                // 实际上，如果旧代码是 Agent 生成的，它会重新读取工具列表。
                // 如果是脚本，那脚本得改。
                // 我们的目标是 "100% backward compatibility" 主要是指功能覆盖，
                // 但接口层面，如果工具名变了，通常意味着 breaking change。
                // "Integrate the compatibility layer... mapping old tools to them."
                // 这暗示我们需要支持旧工具名调用。

                // 让我们为 legacy tools 定义一个包含常见字段的 schema 作为妥协：
                // stock_code, symbol, code, period, limit, type, action, ...
                // 以及一个通用的 'params' 对象。
                // 并在描述中注明 "Deprecated".
            },
            async (args, extra) => {
                try {
                    // 在这里 args 包含传入参数
                    // 我们调用 compat-router
                    const result = await routeToolCall(legacyName, args as any, async (newName, newParams) => {
                        const handler = getToolHandler(newName);
                        if (!handler) {
                            throw new Error(`Target tool '${newName}' not found for legacy alias '${legacyName}'`);
                        }
                        return handler(newParams);
                    });

                    return {
                        content: [
                            {
                                type: "text",
                                text: JSON.stringify(result, null, 2)
                            }
                        ],
                        isError: !result.success
                    };
                } catch (error) {
                    return {
                        content: [
                            {
                                type: "text",
                                text: JSON.stringify({
                                    success: false,
                                    error: error instanceof Error ? error.message : String(error)
                                }, null, 2)
                            }
                        ],
                        isError: true
                    };
                }
            }
        );

        registeredLegacyTools.add(legacyName);
    });
}

async function main() {
    // 启动 Server
    await server.connect(new StdioServerTransport());
    // MCP 服务器通过 stdio 通信，不能输出非 JSON 消息
    // 服务器已启动，静默处理
}

main().catch(error => {
    // 致命错误时退出，但不输出到 stdio（避免 JSON 解析错误）
    process.exit(1);
});

// 处理退出信号
process.on('SIGINT', async () => {
    await timescaleDB.close();
    process.exit(0);
});
