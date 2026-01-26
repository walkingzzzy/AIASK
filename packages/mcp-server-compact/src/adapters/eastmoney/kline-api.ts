/**
 * 东方财富K线数据 API
 */

import { EastMoneyBase, SOURCE, cache, CacheAdapter, rateLimiter, CACHE_TTL } from './base.js';
import type { KlineData, KlinePeriod } from '../../types/stock.js';

export class KlineAPI extends EastMoneyBase {
    /**
     * 获取K线数据
     */
    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        const cacheKey = CacheAdapter.generateKey('kline', SOURCE, code, period, limit.toString());
        const cached = cache.get<KlineData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const secId = this.convertToSecId(code);
            const klt = this.convertPeriodToKlt(period);
            const url = `https://push2his.eastmoney.com/api/qt/stock/kline/get`;

            const response = await this.client.get(url, {
                params: {
                    secid: secId,
                    klt,
                    fqt: 1,
                    lmt: limit,
                    end: '20500101',
                    fields1: 'f1,f2,f3,f4,f5,f6',
                    fields2: 'f51,f52,f53,f54,f55,f56,f57',
                },
            });

            const klines = response.data?.data?.klines || [];
            return klines.map((k: string) => this.parseKline(k));
        });

        cache.set(cacheKey, result, CACHE_TTL.KLINE);
        return result;
    }

    private convertPeriodToKlt(period: KlinePeriod): number {
        const map: Record<KlinePeriod, number> = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '60m': 60,
            'daily': 101,
            'weekly': 102,
            'monthly': 103,
            '101': 101,
            '102': 102,
            '103': 103,
        };
        return map[period] || 101;
    }

    private parseKline(klineStr: string): KlineData {
        const parts = klineStr.split(',');
        return {
            date: parts[0],
            open: parseFloat(parts[1]),
            close: parseFloat(parts[2]),
            high: parseFloat(parts[3]),
            low: parseFloat(parts[4]),
            volume: parseInt(parts[5], 10),
            amount: parseFloat(parts[6]),
        };
    }
}

export const klineAPI = new KlineAPI();
