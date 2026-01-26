/**
 * AIASK MCP Server Config Management
 */

import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// Project Root (../../../../)
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..', '..');

export interface ServerConfig {
    dataDir: string;
    projectRoot: string;
    timeout: number;
    cache: {
        enabled: boolean;
        ttl: number;
    };
    rateLimit: {
        enabled: boolean;
        perSecond: number;
    };
    logLevel: 'debug' | 'info' | 'warn' | 'error';
    transport: 'stdio' | 'http';
    port: number;
    tushareToken?: string;
}

function resolveDataDir(): string {
    const envDataDir = process.env.DATA_DIR;

    if (envDataDir) {
        if (path.isAbsolute(envDataDir)) {
            return envDataDir;
        }
        return path.resolve(PROJECT_ROOT, envDataDir);
    }

    return path.resolve(PROJECT_ROOT, 'data');
}

export function loadConfig(): ServerConfig {
    const dataDir = resolveDataDir();

    return {
        dataDir,
        projectRoot: PROJECT_ROOT,
        timeout: parseInt(process.env.API_TIMEOUT || '45000', 10),
        cache: {
            enabled: process.env.CACHE_ENABLED !== 'false',
            ttl: parseInt(process.env.CACHE_TTL || '600', 10),
        },
        rateLimit: {
            enabled: process.env.RATE_LIMIT_ENABLED !== 'false',
            perSecond: parseInt(process.env.RATE_LIMIT_PER_SECOND || '6', 10),
        },
        logLevel: (process.env.LOG_LEVEL as ServerConfig['logLevel']) || 'info',
        transport: (process.env.MCP_TRANSPORT as ServerConfig['transport']) || 'stdio',
        port: parseInt(process.env.MCP_PORT || '9898', 10),
        tushareToken: process.env.TUSHARE_TOKEN,
    };
}

export const config = loadConfig();

export function resolveDataPath(relativePath: string): string {
    return path.resolve(config.dataDir, relativePath);
}

export const DB_PATHS = {
    get STOCK_VECTORS() { return resolveDataPath('stock_vectors.db'); },
    get AIASK() { return resolveDataPath('aiask.db'); },
} as const;

export * from './constants.js';
export * from './industry-mapping.js';
export * from './market-indices.js';
export * from './trading-config.js';
