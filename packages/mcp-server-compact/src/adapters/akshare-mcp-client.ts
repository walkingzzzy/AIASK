/**
 * akshare-mcp 客户端（stdio）
 * 用于在本地通过 MCP 调用 Python 版 AKShare 服务
 */

import fs from 'fs';
import path from 'path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import {
    StdioClientTransport,
    type StdioServerParameters,
} from '@modelcontextprotocol/sdk/client/stdio.js';
import { CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';
import { config } from '../config/index.js';
import { toFriendlyError } from '../services/error-mapper.js';

type AkshareMcpResponse<T> = {
    success: boolean;
    data?: T;
    error?: string;
    source?: string;
    cached?: boolean;
    timestamp?: string;
};

let client: Client | null = null;
let transport: StdioClientTransport | null = null;
let connecting: Promise<void> | null = null;
let consecutiveFailures = 0;
let lastHealthCheckAt = 0;
let lastHealthOk = false;
let cooldownUntil = 0;

const HEALTH_CHECK_TTL_MS = parseInt(process.env.AKSHARE_MCP_HEALTH_TTL_MS || '10000', 10);
const FAILURE_THRESHOLD = parseInt(process.env.AKSHARE_MCP_FAILURE_THRESHOLD || '3', 10);
const COOLDOWN_MS = parseInt(process.env.AKSHARE_MCP_COOLDOWN_MS || '5000', 10);

function parseArgs(raw?: string): string[] | null {
    if (!raw) return null;
    const trimmed = raw.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith('[')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (Array.isArray(parsed) && parsed.every(item => typeof item === 'string')) {
                return parsed;
            }
        } catch {
            return null;
        }
    }
    return trimmed.split(/\s+/).filter(Boolean);
}

function buildChildEnv(): Record<string, string> {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) {
        if (typeof value === 'string') {
            env[key] = value;
        }
    }
    return env;
}

function resolveLocalAksharePython(): string | null {
    // config.projectRoot 指向项目根目录（包含 packages/ 的那一层）
    const venvRoot = path.join(config.projectRoot, 'akshare-mcp', '.venv');
    const candidate = process.platform === 'win32'
        ? path.join(venvRoot, 'Scripts', 'python.exe')
        : path.join(venvRoot, 'bin', 'python');
    return fs.existsSync(candidate) ? candidate : null;
}

function buildDefaultServerParams(): { command: string; args: string[]; useLocalSource: boolean } {
    const localPython = resolveLocalAksharePython();
    if (localPython) {
        return {
            command: localPython,
            args: ['-m', 'akshare_mcp.server'],
            useLocalSource: true,
        };
    }
    // config.projectRoot 已经指向项目根目录，不需要再加 packages
    const akshareMcpPath = path.join(config.projectRoot, 'akshare-mcp');
    return {
        command: 'uvx',
        args: [
            '--from',
            akshareMcpPath,
            'akshare-mcp',
        ],
        useLocalSource: false,
    };
}

function getServerParams(): StdioServerParameters {
    const defaultParams = buildDefaultServerParams();
    const envArgs = parseArgs(process.env.AKSHARE_MCP_ARGS);
    const env = buildChildEnv();
    if (defaultParams.useLocalSource) {
        const localSrc = path.join(config.projectRoot, 'akshare-mcp', 'src');
        if (fs.existsSync(localSrc)) {
            const current = env.PYTHONPATH ? [env.PYTHONPATH, localSrc] : [localSrc];
            env.PYTHONPATH = current.join(path.delimiter);
        }
    }
    return {
        command: process.env.AKSHARE_MCP_COMMAND || defaultParams.command,
        args: envArgs ?? defaultParams.args,
        env,
        cwd: process.env.AKSHARE_MCP_CWD || config.projectRoot,
    };
}

async function ensureClient(): Promise<Client> {
    if (client) return client;
    if (connecting) {
        await connecting;
        return client!;
    }

    const nextClient = new Client({ name: 'aiask-akshare-bridge', version: '1.0.0' });
    const nextTransport = new StdioClientTransport(getServerParams());

    connecting = nextClient.connect(nextTransport).then(() => {
        client = nextClient;
        transport = nextTransport;
        connecting = null;
    }).catch(error => {
        connecting = null;
        throw error;
    });

    await connecting;
    return client!;
}

async function resetClient(): Promise<void> {
    const currentTransport = transport;
    client = null;
    transport = null;
    connecting = null;
    if (currentTransport) {
        await currentTransport.close().catch(() => { });
    }
}

function noteSuccess(): void {
    consecutiveFailures = 0;
}

function noteFailure(): void {
    consecutiveFailures += 1;
    if (consecutiveFailures >= FAILURE_THRESHOLD) {
        cooldownUntil = Date.now() + COOLDOWN_MS;
        consecutiveFailures = 0;
    }
}

async function checkAkshareMcpHealth(force: boolean = false): Promise<boolean> {
    const now = Date.now();
    if (!force && (now - lastHealthCheckAt) < HEALTH_CHECK_TTL_MS) {
        return lastHealthOk;
    }

    lastHealthCheckAt = now;
    try {
        const mcpClient = await ensureClient();
        await mcpClient.listTools();
        lastHealthOk = true;
        return true;
    } catch {
        lastHealthOk = false;
        await resetClient();
        return false;
    }
}

function parseToolResult<T>(result: { content?: Array<{ type: string; text?: string }> }): AkshareMcpResponse<T> {
    const textBlock = result.content?.find(item => item.type === 'text' && typeof item.text === 'string');
    if (!textBlock?.text) {
        return { success: false, error: 'akshare-mcp 返回内容为空或格式不支持' };
    }

    const rawText = textBlock.text.trim();

    // 检测明显的非 JSON 错误文本
    const lowerText = rawText.toLowerCase();
    if (lowerText.startsWith('unknown tool') ||
        lowerText.startsWith('error:') ||
        lowerText.startsWith('exception:') ||
        (lowerText.startsWith('unknown') && !rawText.startsWith('{'))) {
        return { success: false, error: rawText.slice(0, 200) };
    }

    const candidate = extractJsonPayload(rawText) ?? rawText;

    try {
        const parsed = JSON.parse(candidate) as AkshareMcpResponse<T>;
        if (typeof parsed.success !== 'boolean') {
            // 尝试将整个解析结果作为 data 返回
            return { success: true, data: parsed as T, source: 'akshare' };
        }
        return parsed;
    } catch (error) {
        // 如果不是 JSON，返回更友好的错误信息
        const snippet = rawText.slice(0, 150);
        return { success: false, error: `akshare-mcp 返回非 JSON 格式: ${snippet}` };
    }
}

function extractJsonPayload(rawText: string): string | null {
    const trimmed = rawText.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
        return trimmed;
    }
    const first = trimmed.indexOf('{');
    const last = trimmed.lastIndexOf('}');
    if (first < 0 || last <= first) {
        return null;
    }
    return trimmed.slice(first, last + 1);
}

export async function callAkshareMcpTool<T>(
    name: string,
    args: Record<string, unknown> = {}
): Promise<AkshareMcpResponse<T>> {
    const now = Date.now();
    if (cooldownUntil > now) {
        const remaining = Math.ceil((cooldownUntil - now) / 1000);
        return { success: false, error: `akshare-mcp 冷却中，请在 ${remaining}s 后重试` };
    }

    const healthy = await checkAkshareMcpHealth();
    if (!healthy) {
        noteFailure();
        return { success: false, error: 'akshare-mcp 健康检查失败，已触发重连' };
    }

    try {
        const mcpClient = await ensureClient();
        const result = await mcpClient.request(
            {
                method: 'tools/call',
                params: {
                    name,
                    arguments: args,
                },
            },
            CallToolResultSchema
        );
        noteSuccess();
        const parsed = parseToolResult<T>(result);
        if (!parsed.success && parsed.error) {
            return { ...parsed, error: toFriendlyError('akshare', parsed.error, parsed.error) };
        }
        return parsed;
    } catch (error) {
        await resetClient();
        noteFailure();
        return { success: false, error: toFriendlyError('akshare', error, 'AKShare 服务暂不可用，请稍后再试。') };
    }
}
