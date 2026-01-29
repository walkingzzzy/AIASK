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
const REQUEST_TIMEOUT_MS = parseInt(process.env.AKSHARE_MCP_REQUEST_TIMEOUT_MS || '60000', 10);
const PROXY_ENV_KEYS = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'];
const DEBUG = ['1', 'true', 'yes', 'y'].includes(String(process.env.AKSHARE_MCP_DEBUG || '').trim().toLowerCase());

type ProxyMode = 'inherit' | 'disable' | 'auto';

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

function safeStringify(value: unknown): string {
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
}

function debugLog(message: string, data?: Record<string, unknown>): void {
    if (!DEBUG) return;
    const payload = data ? safeStringify(data) : '';
    const snippet = payload && payload.length > 800 ? `${payload.slice(0, 800)}...` : payload;
    const suffix = snippet ? ` ${snippet}` : '';
    console.log(`[akshare-mcp] ${message}${suffix}`);
}

function resolveProxyMode(): ProxyMode {
    const directFlag = String(process.env.AKSHARE_MCP_DISABLE_PROXY || '').trim().toLowerCase();
    if (['1', 'true', 'yes', 'y'].includes(directFlag)) return 'disable';
    const mode = String(process.env.AKSHARE_MCP_PROXY_MODE || '').trim().toLowerCase();
    if (mode === 'disable') return 'disable';
    if (mode === 'inherit') return 'inherit';
    return 'auto';
}

function isLocalProxy(value: string | undefined): boolean {
    if (!value) return false;
    try {
        const url = new URL(value);
        const host = url.hostname.toLowerCase();
        return host === '127.0.0.1' || host === 'localhost' || host === '::1';
    } catch {
        return false;
    }
}

function shouldDisableProxy(env: Record<string, string>): boolean {
    const mode = resolveProxyMode();
    if (mode === 'disable') return true;
    if (mode === 'inherit') return false;
    return PROXY_ENV_KEYS.some(key => isLocalProxy(env[key]));
}

function buildChildEnv(): Record<string, string> {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) {
        if (typeof value === 'string') {
            env[key] = value;
        }
    }
    if (shouldDisableProxy(env)) {
        for (const key of PROXY_ENV_KEYS) {
            delete env[key];
        }
        env.NO_PROXY = '*';
        env.no_proxy = '*';
    }
    return env;
}

function resolveLocalAksharePython(): string | null {
    // config.projectRoot 指向项目根目录（包含 packages/ 的那一层）
    // akshare-mcp 在 packages/akshare-mcp 目录下
    const venvRoot = path.join(config.projectRoot, 'packages', 'akshare-mcp', '.venv');
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
    // akshare-mcp 在 packages/akshare-mcp 目录下
    const akshareMcpPath = path.join(config.projectRoot, 'packages', 'akshare-mcp');
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
        const localSrc = path.join(config.projectRoot, 'packages', 'akshare-mcp', 'src');
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

    const serverParams = getServerParams();
    const nextClient = new Client({ name: 'aiask-akshare-bridge', version: '1.0.0' });
    const nextTransport = new StdioClientTransport(serverParams);
    const connectStart = Date.now();
    debugLog('准备连接 akshare-mcp', {
        command: serverParams.command,
        args: serverParams.args,
        cwd: serverParams.cwd,
    });

    connecting = nextClient.connect(nextTransport).then(() => {
        client = nextClient;
        transport = nextTransport;
        connecting = null;
        debugLog('连接 akshare-mcp 成功', { elapsedMs: Date.now() - connectStart });
    }).catch(error => {
        connecting = null;
        debugLog('连接 akshare-mcp 失败', { elapsedMs: Date.now() - connectStart, error: String(error) });
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
    debugLog('重置 akshare-mcp 连接');
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
    const healthStart = Date.now();
    try {
        const mcpClient = await ensureClient();
        await mcpClient.listTools();
        lastHealthOk = true;
        debugLog('健康检查成功', { elapsedMs: Date.now() - healthStart });
        return true;
    } catch {
        lastHealthOk = false;
        debugLog('健康检查失败', { elapsedMs: Date.now() - healthStart });
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

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            reject(new Error(`akshare-mcp 请求超时(${timeoutMs}ms)`));
        }, timeoutMs);
        promise.then(
            value => {
                clearTimeout(timer);
                resolve(value);
            },
            error => {
                clearTimeout(timer);
                reject(error);
            }
        );
    });
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

    const requestStart = Date.now();
    debugLog(`调用工具 ${name}`, { args });
    const healthy = await checkAkshareMcpHealth();
    if (!healthy) {
        noteFailure();
        debugLog(`工具 ${name} 健康检查失败`, { elapsedMs: Date.now() - requestStart });
        return { success: false, error: 'akshare-mcp 健康检查失败，已触发重连' };
    }

    try {
        const mcpClient = await ensureClient();
        const result = await withTimeout(
            mcpClient.request(
                {
                    method: 'tools/call',
                    params: {
                        name,
                        arguments: args,
                    },
                },
                CallToolResultSchema
            ),
            REQUEST_TIMEOUT_MS
        );
        noteSuccess();
        const parsed = parseToolResult<T>(result);
        debugLog(`工具 ${name} 返回`, {
            elapsedMs: Date.now() - requestStart,
            success: parsed.success,
            source: parsed.source,
            cached: parsed.cached,
        });
        if (!parsed.success && parsed.error) {
            return { ...parsed, error: toFriendlyError('akshare', parsed.error, parsed.error) };
        }
        return parsed;
    } catch (error) {
        debugLog(`工具 ${name} 异常`, {
            elapsedMs: Date.now() - requestStart,
            error: String(error),
        });
        await resetClient();
        noteFailure();
        return { success: false, error: toFriendlyError('akshare', error, 'AKShare 服务暂不可用，请稍后再试。') };
    }
}
