/**
 * 新浪财经适配器
 * 用于实时行情备用数据源
 */

import axios, { type AxiosInstance } from 'axios';
import { config } from '../config/index.js';
import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import { CACHE_TTL } from '../config/constants.js';
import type { RealtimeQuote, KlineData, KlinePeriod } from '../types/stock.js';
import type { QuoteAdapter } from '../types/adapters.js';

const SOURCE = 'sina';

export class SinaAdapter implements QuoteAdapter {
    readonly name: 'sina' = 'sina';
    private client: AxiosInstance;

    constructor() {
        this.client = axios.create({
            timeout: config.timeout,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            },
            responseType: 'arraybuffer',
        });
    }

    async isAvailable(): Promise<boolean> {
        try {
            const response = await this.client.get('https://hq.sinajs.cn/list=sh000001', {
                timeout: 5000,
            });
            const text = this.decodeGBK(response.data);
            return text.includes('hq_str_sh000001');
        } catch (error) {
            console.warn('[SinaAdapter] Health check failed:', error);
            return false;
        }
    }

    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
        const cached = cache.get<RealtimeQuote>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const sinaCode = this.convertToSinaCode(code);
            const url = `https://hq.sinajs.cn/list=${sinaCode}`;

            const response = await this.client.get(url);
            const text = this.decodeGBK(response.data);

            return this.parseQuote(code, text);
        });

        cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE);
        return result;
    }

    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        const uncached: string[] = [];
        const results: RealtimeQuote[] = [];

        for (const code of codes) {
            const key = CacheAdapter.generateKey('quote', SOURCE, code);
            const cached = cache.get<RealtimeQuote>(key);
            if (cached) {
                results.push(cached);
            } else {
                uncached.push(code);
            }
        }

        if (uncached.length === 0) {
            return results;
        }

        const batchResults = await rateLimiter.schedule(SOURCE, async () => {
            const sinaCodes = uncached.map((c: any) => this.convertToSinaCode(c)).join(',');
            const url = `https://hq.sinajs.cn/list=${sinaCodes}`;

            const response = await this.client.get(url);
            const text = this.decodeGBK(response.data);

            const lines = text.trim().split('\n');
            const quotes: RealtimeQuote[] = [];

            for (let i = 0; i < lines.length; i++) {
                try {
                    const quote = this.parseQuote(uncached[i], lines[i]);
                    quotes.push(quote);

                    const key = CacheAdapter.generateKey('quote', SOURCE, uncached[i]);
                    cache.set(key, quote, CACHE_TTL.REALTIME_QUOTE);
                } catch {
                    // Skip failed parse
                }
            }

            return quotes;
        });

        return [...results, ...batchResults];
    }

    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        const cacheKey = CacheAdapter.generateKey('kline', SOURCE, code, period, limit.toString());
        const cached = cache.get<KlineData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const symbol = this.convertToSinaCode(code);
            const scale = this.periodToScale(period);

            const url = `https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData`;

            const response = await axios.get(url, {
                params: {
                    symbol,
                    scale,
                    ma: 'no',
                    datalen: limit,
                },
                timeout: config.timeout,
            });

            const data = response.data || [];
            return data.map((item: Record<string, string>) => ({
                date: item.day,
                open: parseFloat(item.open),
                close: parseFloat(item.close),
                high: parseFloat(item.high),
                low: parseFloat(item.low),
                volume: parseInt(item.volume, 10),
                amount: 0,
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.KLINE);
        return result;
    }

    private convertToSinaCode(code: string): string {
        const trimmed = code.trim();
        const lower = trimmed.toLowerCase();

        if (/^(sh|sz)\d{6}$/.test(lower)) {
            return lower;
        }

        const suffixMatch = lower.match(/^(\d{6})\.(sh|sz)$/);
        if (suffixMatch) {
            const pureCode = suffixMatch[1] || '';
            const market = suffixMatch[2] || 'sz';
            return `${market}${pureCode}`;
        }

        const indexMarket: Record<string, 'sh' | 'sz'> = {
            '000300': 'sh',
            '000016': 'sh',
            '000688': 'sh',
            '000905': 'sh',
            '000852': 'sh',
            '399001': 'sz',
            '399006': 'sz',
            '399005': 'sz',
        };
        if (indexMarket[lower]) {
            return `${indexMarket[lower]}${lower}`;
        }

        if (lower.startsWith('6')) {
            return `sh${lower}`;
        }
        if (lower.startsWith('0') || lower.startsWith('3')) {
            return `sz${lower}`;
        }

        return `sz${lower}`;
    }

    private periodToScale(period: KlinePeriod): number {
        const map: Record<KlinePeriod, number> = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '60m': 60,
            'daily': 240,
            'weekly': 1200,
            'monthly': 7200,
            '101': 240,
            '102': 1200,
            '103': 7200,
        };
        return map[period] || 240;
    }

    private decodeGBK(buffer: ArrayBuffer): string {
        try {
            const decoder = new TextDecoder('gbk');
            return decoder.decode(buffer);
        } catch {
            const decoder = new TextDecoder('utf-8');
            return decoder.decode(buffer);
        }
    }

    private parseQuote(code: string, line: string): RealtimeQuote {
        const match = line.match(/="([^"]+)"/);
        if (!match) {
            throw new Error(`解析 ${code} 的行情数据失败：返回数据格式异常`);
        }

        const parts = match[1].split(',');
        if (parts.length < 32) {
            throw new Error(`${code} 的行情数据无效：数据字段不完整`);
        }

        return {
            code,
            name: parts[0],
            price: parseFloat(parts[3]) || 0,
            change: parseFloat(parts[3]) - parseFloat(parts[2]),
            changePercent: parseFloat(parts[2]) > 0
                ? (parseFloat(parts[3]) / parseFloat(parts[2]) - 1) * 100
                : 0,
            open: parseFloat(parts[1]) || 0,
            high: parseFloat(parts[4]) || 0,
            low: parseFloat(parts[5]) || 0,
            preClose: parseFloat(parts[2]) || 0,
            volume: parseInt(parts[8], 10) || 0,
            amount: parseFloat(parts[9]) || 0,
            turnoverRate: 0,
            timestamp: Date.now(),
        };
    }
}

export const sinaAdapter = new SinaAdapter();
