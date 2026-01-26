/**
 * 限流器
 * 基于 bottleneck 实现 API 限流
 */

import Bottleneck from 'bottleneck';
import { config } from '../config/index.js';
import type { RateLimiterConfig } from '../types/adapters.js';

/**
 * 创建限流器实例
 */
export function createRateLimiter(customConfig?: Partial<RateLimiterConfig>): Bottleneck {
    const defaultConfig: RateLimiterConfig = {
        maxConcurrent: 5,
        minTime: Math.floor(1000 / config.rateLimit.perSecond),
    };

    const mergedConfig = { ...defaultConfig, ...customConfig };

    return new Bottleneck({
        maxConcurrent: mergedConfig.maxConcurrent,
        minTime: mergedConfig.minTime,
        reservoir: mergedConfig.reservoir,
        reservoirRefreshAmount: mergedConfig.reservoirRefreshAmount,
        reservoirRefreshInterval: mergedConfig.reservoirRefreshInterval,
    });
}

/**
 * 限流器管理器
 * 为不同数据源提供独立的限流器
 */
export class RateLimiterManager {
    private limiters: Map<string, Bottleneck> = new Map();

    /**
     * 获取指定数据源的限流器
     */
    getLimiter(source: string): Bottleneck {
        if (!config.rateLimit.enabled) {
            // 如果禁用限流，返回一个不做任何限制的 limiter
            return new Bottleneck();
        }

        if (!this.limiters.has(source)) {
            // 根据数据源设置不同的限流配置
            const limiterConfig = this.getConfigForSource(source);
            this.limiters.set(source, createRateLimiter(limiterConfig));
        }

        return this.limiters.get(source)!;
    }

    /**
     * 根据数据源获取限流配置
     */
    private getConfigForSource(source: string): Partial<RateLimiterConfig> {
        switch (source) {
            case 'eastmoney':
                return { maxConcurrent: 2, minTime: 300 };
            case 'sina':
                return { maxConcurrent: 3, minTime: 200 };
            case 'akshare':
                return { maxConcurrent: 1, minTime: 800 };
            case 'xueqiu':
                return { maxConcurrent: 2, minTime: 300 };
            case 'tushare':
                return { maxConcurrent: 1, minTime: 1000 };
            case 'baostock':
                return { maxConcurrent: 2, minTime: 500 };
            case 'wind':
                return { maxConcurrent: 1, minTime: 800 };
            default:
                return { maxConcurrent: 5, minTime: 100 };
        }
    }

    /**
     * 通过限流器执行函数
     */
    async schedule<T>(source: string, fn: () => Promise<T>): Promise<T> {
        const limiter = this.getLimiter(source);
        return limiter.schedule(fn);
    }

    /**
     * 获取所有限流器的统计信息
     */
    getStats(): Record<string, { running: number; queued: number }> {
        const stats: Record<string, { running: number; queued: number }> = {};

        for (const [source, limiter] of this.limiters) {
            const counts = limiter.counts();
            stats[source] = {
                running: counts.RUNNING,
                queued: counts.QUEUED,
            };
        }

        return stats;
    }
}

// 导出默认限流管理器实例
export const rateLimiter = new RateLimiterManager();
