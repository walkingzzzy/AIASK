/**
 * MCP 客户端 - 连接本地 MCP 服务器
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { app } from 'electron';
import path from 'path';

let mcpClient: Client | null = null;

type MCPTextContent = {
  type: 'text';
  text: string;
};

type MCPContent = Array<MCPTextContent | { type: string; text?: string }>;

type MCPCallResult = {
  content?: MCPContent;
  isError?: boolean;
};

const extractTextContent = (content?: MCPContent): string[] => {
  if (!content) return [];
  return content
    .filter(item => item?.type === 'text' && typeof item.text === 'string')
    .map(item => (item as MCPTextContent).text);
};

const parseContent = (content?: MCPContent): unknown => {
  const texts = extractTextContent(content);
  if (texts.length === 0) return undefined;

  for (const text of texts) {
    try {
      return JSON.parse(text);
    } catch {
      // continue trying other chunks
    }
  }

  return texts.join('\n');
};

/**
 * 获取 MCP 服务器路径
 */
function getMCPServerPath(): string {
  // 开发环境: app.getAppPath() 返回 /path/to/packages/chat-client
  // 向上1级到 packages 目录，然后进入 mcp-server/dist
  const devPath = path.join(app.getAppPath(), '..', 'mcp-server/dist/index.js');
  // 生产环境: 相对于应用资源目录
  const prodPath = path.join(process.resourcesPath, 'mcp-server/dist/index.js');

  return app.isPackaged ? prodPath : devPath;
}

/**
 * 初始化 MCP 客户端
 */
export async function initMCPClient(): Promise<Client> {
  if (mcpClient) {
    return mcpClient;
  }

  const mcpServerPath = getMCPServerPath();
  console.log('[MCP] Connecting to server:', mcpServerPath);

  // 使用系统 node 而不是 Electron 的 Node 来运行 mcp-server
  // 这避免了 better-sqlite3 等原生模块的版本不兼容问题
  // Electron 内置的 Node 版本可能与系统 Node 不同，导致原生模块编译版本不匹配
  const transport = new StdioClientTransport({
    command: 'node',
    args: [mcpServerPath],
    env: {
      ...process.env,
    },
  });

  mcpClient = new Client({
    name: 'stock-ai-chat',
    version: '1.0.0',
  });

  await mcpClient.connect(transport);
  console.log('[MCP] Client connected successfully');

  return mcpClient;
}

/**
 * 获取 MCP 客户端实例
 */
export function getMCPClient(): Client | null {
  return mcpClient;
}

/**
 * 调用 MCP 工具
 */
export async function callMCPTool(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
  if (!mcpClient) {
    throw new Error('MCP Client not initialized');
  }

  console.log(`[MCP] Calling tool: ${name}`, args);

  const result = await mcpClient.callTool({
    name,
    arguments: args,
  }) as MCPCallResult;

  const parsed = parseContent(result.content);

  if (result.isError) {
    if (parsed && typeof parsed === 'object') {
      const errorPayload = parsed as { error?: string; validationErrors?: unknown };
      return {
        success: false,
        error: errorPayload.error || '工具执行失败',
        validationErrors: errorPayload.validationErrors,
      };
    }
    return {
      success: false,
      error: typeof parsed === 'string' ? parsed : '工具执行失败',
    };
  }

  if (parsed && typeof parsed === 'object') {
    const confirmationPayload = parsed as { requiresConfirmation?: boolean; message?: string; toolName?: string; arguments?: unknown };
    if (confirmationPayload.requiresConfirmation) {
      return {
        success: false,
        error: confirmationPayload.message || '需要用户确认后才能执行',
        requiresConfirmation: true,
        confirmation: {
          toolName: confirmationPayload.toolName || name,
          arguments: confirmationPayload.arguments || args,
          message: confirmationPayload.message,
        },
      };
    }
  }

  return {
    success: true,
    data: parsed,
  };
}

/**
 * 列出所有可用工具
 */
export async function listMCPTools(): Promise<unknown> {
  if (!mcpClient) {
    throw new Error('MCP Client not initialized');
  }

  const result = await mcpClient.listTools();
  return {
    success: true,
    data: result,
  };
}

/**
 * 关闭 MCP 客户端连接
 */
export async function closeMCPClient(): Promise<void> {
  if (mcpClient) {
    await mcpClient.close();
    mcpClient = null;
    console.log('[MCP] Client closed');
  }
}
