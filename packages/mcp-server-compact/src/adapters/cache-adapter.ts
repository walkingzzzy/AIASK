/**
 * 缓存适配器
 * 基于 node-cache 的多级缓存实现
 */

import NodeCache from 'node-cache';
import { config } from '../config/index.js';
import type { CacheAdapter as ICacheAdapter } from '../types/adapters.js';

// 缓存分级配置
const CACHE_TIERS = {
    HOT: 60,        // 热点数据：1分钟
    WARM: 300,      // 温数据：5分钟
    COLD: 3600,     // 冷数据：1小时
} as const;

export class CacheAdapter implements ICacheAdapter {
    private cache: NodeCache;
    private hotKeys: Set<string>;
    private accessCount: Map<string, number>;

    constructor(defaultTTL?: number) {
        this.cache = new NodeCache({
            stdTTL: defaultTTL ?? config.cache.ttl,
            checkperiod: 60,
            useClones: true,
            deleteOnExpire: true,
        });
        this.hotKeys = new Set();
        this.accessCount = new Map();

        // 定期清理访问计数
        setInterval(() => this.cleanupAccessCount(), 300000); // 5分钟
    }

    get<T>(key: string): T | undefined {
        if (!config.cache.enabled) {
            return undefined;
        }

        // 记录访问
        this.recordAccess(key);

        return this.cache.get<T>(key);
    }

    set<T>(key: string, value: T, ttl?: number): void {
        if (!config.cache.enabled) {
            return;
        }

        // 根据访问频率动态调整TTL
        const adjustedTTL = this.getAdjustedTTL(key, ttl);

        if (adjustedTTL !== undefined) {
            this.cache.set(key, value, adjustedTTL);
        } else {
            this.cache.set(key, value);
        }
    }

    has(key: string): boolean {
        if (!config.cache.enabled) {
            return false;
        }
        return this.cache.has(key);
    }

    delete(key: string): void {
        this.cache.del(key);
        this.hotKeys.delete(key);
        this.accessCount.delete(key);
    }

    clear(): void {
        this.cache.flushAll();
        this.hotKeys.clear();
        this.accessCount.clear();
    }

    /**
     * 获取缓存统计信息
     */
    getStats(): { hits: number; misses: number; keys: number; hitRate: string } {
        const stats = this.cache.getStats();
        const total = stats.hits + stats.misses;
        const hitRate = total > 0 ? ((stats.hits / total) * 100).toFixed(2) + '%' : '0%';

        return {
            hits: stats.hits,
            misses: stats.misses,
            keys: this.cache.keys().length,
            hitRate,
        };
    }

    /**
     * 批量获取
     */
    mget<T>(keys: string[]): Map<string, T> {
        const result = new Map<string, T>();
        for (const key of keys) {
            const value = this.get<T>(key);
            if (value !== undefined) {
                result.set(key, value);
            }
        }
        return result;
    }

    /**
     * 批量设置
     */
    mset<T>(entries: Array<{ key: string; value: T; ttl?: number }>): void {
        for (const entry of entries) {
            this.set(entry.key, entry.value, entry.ttl);
        }
    }

    /**
     * 获取或设置 (缓存穿透保护)
     */
    async getOrSet<T>(
        key: string,
        fetcher: () => Promise<T>,
        ttl?: number
    ): Promise<T> {
        const cached = this.get<T>(key);
        if (cached !== undefined) {
            return cached;
        }

        const value = await fetcher();
        this.set(key, value, ttl);
        return value;
    }

    /**
     * 预热缓存
     */
    async warmup<T>(
        keys: string[],
        fetcher: (key: string) => Promise<T>,
        ttl?: number
    ): Promise<void> {
        const promises = keys.map(async (key) => {
            if (!this.has(key)) {
                try {
                    const value = await fetcher(key);
                    this.set(key, value, ttl);
                } catch (error) {
                    console.warn(`[Cache] Warmup failed for key ${key}:`, error);
                }
            }
        });

        await Promise.allSettled(promises);
    }

    /**
     * 生成缓存键
     */
    static generateKey(prefix: string, ...parts: (string | number | undefined)[]): string {
        return [prefix, ...parts.filter((p: any) => p !== undefined)].join(':');
    }

    // ========== 私有方法 ==========

    private recordAccess(key: string): void {
        const count = (this.accessCount.get(key) || 0) + 1;
        this.accessCount.set(key, count);

        // 高频访问的key标记为热点
        if (count > 10) {
            this.hotKeys.add(key);
        }
    }

    private getAdjustedTTL(key: string, baseTTL?: number): number | undefined {
        if (baseTTL === undefined) return undefined;

        // 热点数据延长TTL
        if (this.hotKeys.has(key)) {
            return Math.min(baseTTL * 2, CACHE_TIERS.COLD);
        }

        return baseTTL;
    }

    private cleanupAccessCount(): void {
        // 清理低频访问的计数
        for (const [key, count] of this.accessCount) {
            if (count < 5) {
                this.accessCount.delete(key);
                this.hotKeys.delete(key);
            } else {
                // 衰减计数
                this.accessCount.set(key, Math.floor(count / 2));
            }
        }
    }
}

// 导出默认缓存实例
export const cache = new CacheAdapter();
