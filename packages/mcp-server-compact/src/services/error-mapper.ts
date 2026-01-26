import type { DataSource } from '../types/adapters.js';

const FREE_SOURCES = new Set<DataSource>(['eastmoney', 'sina', 'akshare', 'baostock']);

const SOURCE_LABELS: Record<DataSource, string> = {
    akshare: 'AKShare',
    eastmoney: '东方财富',
    sina: '新浪财经',
    xueqiu: '雪球',
    tushare: 'Tushare',
    baostock: 'Baostock',
    wind: 'Wind',
    tencent: '腾讯财经',
};

const NETWORK_PATTERNS = [
    /socket hang up/i,
    /econnreset/i,
    /econnrefused/i,
    /etimedout/i,
    /timeout/i,
    /enotfound/i,
    /getaddrinfo/i,
    /remote disconnected/i,
    /transport closed/i,
    /network error/i,
];

const RATE_LIMIT_PATTERNS = [
    /429/i,
    /rate limit/i,
    /too many requests/i,
];

function normalizeMessage(error: unknown): string {
    if (error instanceof Error) {
        return error.message || String(error);
    }
    if (typeof error === 'string') {
        return error;
    }
    if (error && typeof error === 'object' && 'message' in error) {
        const value = (error as { message?: unknown }).message;
        if (typeof value === 'string') {
            return value;
        }
    }
    return error ? String(error) : '';
}

function matchesAny(message: string, patterns: RegExp[]): boolean {
    return patterns.some(pattern => pattern.test(message));
}

export function toFriendlyError(source: DataSource, error: unknown, fallback?: string): string {
    const raw = normalizeMessage(error);
    const sourceName = SOURCE_LABELS[source] || source;

    if (matchesAny(raw, RATE_LIMIT_PATTERNS)) {
        return `免费数据源${sourceName}触发限流，请稍后再试。`;
    }

    if (FREE_SOURCES.has(source) && matchesAny(raw, NETWORK_PATTERNS)) {
        return `免费数据源${sourceName}连接不稳定，请稍后再试。`;
    }

    if (FREE_SOURCES.has(source)) {
        return fallback || `免费数据源${sourceName}暂不可用，请稍后再试。`;
    }

    return fallback || raw || '服务暂不可用，请稍后再试。';
}
