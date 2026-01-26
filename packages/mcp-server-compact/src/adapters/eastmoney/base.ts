/**
 * 东方财富适配器基础类
 * 
 * 数据质量修复 2026-01-13:
 * - 修复 000001 代码歧义问题：默认解析为平安银行
 * - 指数查询需要显式指定市场前缀（如 sh000001）
 */

import axios, { type AxiosInstance } from 'axios';
import http from 'http';
import https from 'https';
import { config } from '../../config/index.js';
import { cache, CacheAdapter } from '../cache-adapter.js';
import { rateLimiter } from '../rate-limiter.js';
import { CACHE_TTL } from '../../config/constants.js';
import { getTodayInShanghai } from '../../utils/date-utils.js';

export const SOURCE = 'eastmoney';

/**
 * 主要指数代码映射表
 */
export const INDEX_CODES: Record<string, { name: string; market: number }> = {
    // 上海指数
    '000002': { name: '上证A股', market: 1 },
    '000003': { name: '上证B股', market: 1 },
    '000016': { name: '上证50', market: 1 },
    '000300': { name: '沪深300', market: 1 },
    '000688': { name: '科创50', market: 1 },
    '000905': { name: '中证500', market: 1 },
    '000852': { name: '中证1000', market: 1 },
    // 深圳指数
    '399001': { name: '深证成指', market: 0 },
    '399006': { name: '创业板指', market: 0 },
    '399005': { name: '中小板指', market: 0 },
    '399673': { name: '创业板50', market: 0 },
    '399303': { name: '国证2000', market: 0 },
};

/**
 * 东方财富适配器基类
 */
export class EastMoneyBase {
    protected client: AxiosInstance;

    constructor() {
        this.client = axios.create({
            timeout: config.timeout,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://quote.eastmoney.com/',
                'Connection': 'keep-alive'
            },
            httpAgent: new http.Agent({ keepAlive: true }),
            httpsAgent: new https.Agent({ keepAlive: true }),
        });
    }

    async isAvailable(): Promise<boolean> {
        try {
            await this.client.get('https://push2.eastmoney.com/api/qt/ulist.np/get', {
                timeout: 5000,
            });
            return true;
        } catch {
            return false;
        }
    }

    /**
     * 判断代码是否为指数
     */
    protected isIndexCode(code: string): boolean {
        const lowerCode = code.toLowerCase();
        if (lowerCode.startsWith('sh') || lowerCode.startsWith('sz')) {
            const pureCode = lowerCode.slice(2);
            if (lowerCode === 'sh000001') return true;
            return !!INDEX_CODES[pureCode];
        }

        const pureCode = code.replace(/\.(SH|SZ|sh|sz)$/, '');

        if (INDEX_CODES[pureCode]) {
            return true;
        }

        if (pureCode.startsWith('399')) {
            return true;
        }

        return false;
    }

    /**
     * 获取指数信息
     */
    protected getIndexInfo(code: string): { name: string; market: number } | null {
        const lowerCode = code.toLowerCase();

        if (lowerCode === 'sh000001') {
            return { name: '上证指数', market: 1 };
        }

        const pureCode = code.replace(/\.(SH|SZ|sh|sz)$/, '').replace(/^(sh|sz)/i, '');
        return INDEX_CODES[pureCode] || null;
    }

    /**
     * 转换股票代码为东方财富格式
     */
    protected convertToSecId(code: string): string {
        const lowerCode = code.toLowerCase();

        if (lowerCode.startsWith('sh')) {
            const pureCode = code.slice(2);
            return `1.${pureCode}`;
        }
        if (lowerCode.startsWith('sz')) {
            const pureCode = code.slice(2);
            return `0.${pureCode}`;
        }

        const pureCode = code.replace(/\.(SH|SZ|sh|sz)$/, '');

        const indexInfo = this.getIndexInfo(pureCode);
        if (indexInfo) {
            return `${indexInfo.market}.${pureCode}`;
        }

        if (pureCode.startsWith('399')) {
            return `0.${pureCode}`;
        }

        if (pureCode.startsWith('6')) {
            return `1.${pureCode}`;
        } else if (pureCode.startsWith('0') || pureCode.startsWith('3')) {
            return `0.${pureCode}`;
        } else if (pureCode.startsWith('8') || pureCode.startsWith('4')) {
            return `0.${pureCode}`;
        }

        return `0.${pureCode}`;
    }

    /**
     * 获取今日日期字符串
     */
    protected getTodayStr(): string {
        return getTodayInShanghai();
    }

    /**
     * 带缓存的请求调度
     */
    protected async scheduleWithCache<T>(
        cacheKey: string,
        ttl: number,
        fetcher: () => Promise<T>
    ): Promise<T> {
        const cached = cache.get<T>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, fetcher);
        cache.set(cacheKey, result, ttl);
        return result;
    }
}

export { cache, CacheAdapter, rateLimiter, CACHE_TTL };
