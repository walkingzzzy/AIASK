import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import { ObservabilityService } from '../observability/observability.service';

type MemoryEntry = { payload: string; expiresAt: number };
type CacheBackend = 'redis' | 'memory' | 'none';
type CacheFailureStage =
  | 'redis_not_configured'
  | 'redis_init_failed'
  | 'redis_connect_failed'
  | 'redis_runtime_error'
  | 'redis_read_failed'
  | 'redis_write_failed'
  | 'redis_delete_failed'
  | 'redis_increment_failed'
  | 'redis_clear_failed';

type CacheStats = {
  requests: number;
  hits: number;
  misses: number;
  sets: number;
  redisHits: number;
  memoryHits: number;
  redisSets: number;
  memorySets: number;
  errors: number;
};

export type CacheReadMeta = { hit: boolean; backend: CacheBackend };
export type CacheReadResult<T> = { value: T | null; meta: CacheReadMeta };

@Injectable()
export class CommonCacheService implements OnModuleDestroy {
  private readonly logger = new Logger(CommonCacheService.name);
  private readonly memory = new Map<string, MemoryEntry>();
  private readonly keyPrefix = 'bff:cache:';
  private readonly stats: CacheStats = {
    requests: 0,
    hits: 0,
    misses: 0,
    sets: 0,
    redisHits: 0,
    memoryHits: 0,
    redisSets: 0,
    memorySets: 0,
    errors: 0,
  };
  private readonly ttlDefaultSeconds: number;
  private readonly ttlOverrides: Record<string, number>;
  private readonly memoryMaxEntries: number;
  private readonly redisConfigured: boolean;
  private redis: Redis | null = null;
  private redisReady = false;
  private fallbackActive = false;
  private lastError: string | null = null;
  private lastErrorAt: string | null = null;
  private lastFailureStage: CacheFailureStage | null = null;

  constructor(
    private readonly configService: ConfigService,
    private readonly observability: ObservabilityService,
  ) {
    this.ttlDefaultSeconds = this.readDefaultTtl();
    this.ttlOverrides = this.readTtlOverrides();
    this.memoryMaxEntries = Math.max(100, Number(this.configService.get('CACHE_MEMORY_MAX_ENTRIES', '5000')) || 5000);
    this.redisConfigured = Boolean(this.configService.get<string>('REDIS_URL', '').trim());
    this.initRedis();
  }

  async onModuleDestroy(): Promise<void> {
    if (!this.redis) return;
    try {
      await this.redis.quit();
    } catch {
      this.redis.disconnect(false);
    }
  }

  async get<T>(key: string): Promise<T | null> {
    const { value } = await this.getWithMeta<T>(key);
    return value;
  }

  async getWithMeta<T>(key: string): Promise<CacheReadResult<T>> {
    this.stats.requests += 1;
    const normalizedKey = this.normalizeKey(key);

    if (this.redisReady && this.redis) {
      try {
        const raw = await this.redis.get(normalizedKey);
        this.clearRedisFailure();
        if (!raw) {
          this.stats.misses += 1;
          return { value: null, meta: { hit: false, backend: 'none' } };
        }
        this.stats.hits += 1;
        this.stats.redisHits += 1;
        return { value: JSON.parse(raw) as T, meta: { hit: true, backend: 'redis' } };
      } catch (error) {
        this.stats.errors += 1;
        this.recordRedisError(error, 'Redis 读取失败，降级内存缓存', 'redis_read_failed');
      }
    }

    const entry = this.memory.get(normalizedKey);
    if (!entry) {
      this.stats.misses += 1;
      return { value: null, meta: { hit: false, backend: 'none' } };
    }
    if (Date.now() > entry.expiresAt) {
      this.memory.delete(normalizedKey);
      this.stats.misses += 1;
      return { value: null, meta: { hit: false, backend: 'none' } };
    }

    try {
      this.stats.hits += 1;
      this.stats.memoryHits += 1;
      return { value: JSON.parse(entry.payload) as T, meta: { hit: true, backend: 'memory' } };
    } catch {
      this.memory.delete(normalizedKey);
      this.stats.errors += 1;
      this.stats.misses += 1;
      return { value: null, meta: { hit: false, backend: 'none' } };
    }
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    this.stats.sets += 1;
    const normalizedKey = this.normalizeKey(key);
    const safeTtl = Math.max(1, Math.floor(ttlSeconds));
    const payload = JSON.stringify(value);

    if (this.redisReady && this.redis) {
      try {
        await this.redis.set(normalizedKey, payload, 'EX', safeTtl);
        this.clearRedisFailure();
        this.stats.redisSets += 1;
        return;
      } catch (error) {
        this.stats.errors += 1;
        this.recordRedisError(error, 'Redis 写入失败，降级内存缓存', 'redis_write_failed');
      }
    }

    this.stats.memorySets += 1;
    if (this.memory.size >= this.memoryMaxEntries) {
      this.evictExpiredOrOldest();
    }
    this.memory.set(normalizedKey, {
      payload,
      expiresAt: Date.now() + safeTtl * 1000,
    });
  }

  private evictExpiredOrOldest(): void {
    const now = Date.now();
    for (const [k, v] of this.memory) {
      if (v.expiresAt <= now) {
        this.memory.delete(k);
      }
    }
    if (this.memory.size >= this.memoryMaxEntries) {
      const toRemove = Math.max(1, Math.floor(this.memoryMaxEntries * 0.1));
      const iter = this.memory.keys();
      for (let i = 0; i < toRemove; i++) {
        const next = iter.next();
        if (next.done) break;
        this.memory.delete(next.value);
      }
    }
  }

  async del(key: string): Promise<void> {
    const normalizedKey = this.normalizeKey(key);
    if (this.redisReady && this.redis) {
      try {
        await this.redis.del(normalizedKey);
        this.clearRedisFailure();
      } catch (error) {
        this.stats.errors += 1;
        this.recordRedisError(error, 'Redis 删除失败，降级内存缓存', 'redis_delete_failed');
      }
    }
    this.memory.delete(normalizedKey);
  }

  async increment(key: string, ttlSeconds: number): Promise<number> {
    const normalizedKey = this.normalizeKey(key);
    const safeTtl = Math.max(1, Math.floor(ttlSeconds));

    if (this.redisReady && this.redis) {
      try {
        const pipeline = this.redis.multi();
        pipeline.incr(normalizedKey);
        pipeline.expire(normalizedKey, safeTtl);
        const results = await pipeline.exec();
        this.clearRedisFailure();
        const count = Number(results?.[0]?.[1] ?? 0);
        if (Number.isFinite(count) && count > 0) {
          return count;
        }
      } catch (error) {
        this.stats.errors += 1;
        this.recordRedisError(error, 'Redis 计数失败，降级内存缓存', 'redis_increment_failed');
      }
    }

    const existing = this.memory.get(normalizedKey);
    let base = 0;
    if (existing && Date.now() <= existing.expiresAt) {
      try {
        base = Number(JSON.parse(existing.payload) ?? 0);
      } catch {
        base = 0;
      }
    }
    const next = Math.max(0, base) + 1;
    this.memory.set(normalizedKey, {
      payload: JSON.stringify(next),
      expiresAt: Date.now() + safeTtl * 1000,
    });
    return next;
  }

  resolveTtl(scope: string, fallbackSeconds: number): number {
    const scoped = this.ttlOverrides[scope];
    if (Number.isFinite(scoped) && scoped > 0) return Math.floor(scoped);
    if (Number.isFinite(this.ttlDefaultSeconds) && this.ttlDefaultSeconds > 0) {
      return Math.floor(this.ttlDefaultSeconds);
    }
    return Math.max(1, Math.floor(fallbackSeconds));
  }

  getStats() {
    const hitRate = this.stats.requests > 0 ? Number((this.stats.hits / this.stats.requests).toFixed(4)) : 0;
    return {
      ...this.stats,
      hitRate,
      configured: this.redisConfigured,
      redisReady: this.redisReady,
      fallbackActive: this.fallbackActive,
      memorySize: this.memory.size,
      lastError: this.lastError,
      lastErrorAt: this.lastErrorAt,
      lastFailureStage: this.lastFailureStage,
      ttl: {
        defaultSeconds: this.ttlDefaultSeconds,
        overrides: this.ttlOverrides,
      },
    };
  }

  /**
   * Clear cache entries. If prefix is provided, only keys matching the prefix are cleared.
   * Returns the number of keys cleared.
   */
  async clear(prefix?: string): Promise<number> {
    let cleared = 0;
    const fullPrefix = prefix ? `${this.keyPrefix}${prefix}` : this.keyPrefix;

    if (this.redisReady && this.redis) {
      try {
        const pattern = prefix ? `${fullPrefix}*` : `${this.keyPrefix}*`;
        const keys = await this.scanKeys(pattern);
        if (keys.length > 0) {
          const chunkSize = 500;
          for (let index = 0; index < keys.length; index += chunkSize) {
            const chunk = keys.slice(index, index + chunkSize);
            await this.redis.del(...chunk);
            cleared += chunk.length;
          }
        }
      } catch (error) {
        this.stats.errors += 1;
        this.recordRedisError(error, 'Redis 清除失败', 'redis_clear_failed');
      }
    }

    const memKeys = Array.from(this.memory.keys()).filter((k) =>
      prefix ? k.startsWith(fullPrefix) : k.startsWith(this.keyPrefix),
    );
    for (const k of memKeys) {
      this.memory.delete(k);
      cleared += 1;
    }

    return cleared;
  }

  private initRedis() {
    const redisUrl = this.configService.get<string>('REDIS_URL');
    if (!redisUrl) {
      this.logger.log('未配置 REDIS_URL，启用内存缓存');
      this.fallbackActive = true;
      this.lastFailureStage = 'redis_not_configured';
      this.observability.setDependencyState('cache', 'degraded');
      return;
    }

    try {
      const client = new Redis(redisUrl, {
        lazyConnect: true,
        maxRetriesPerRequest: 1,
        enableReadyCheck: true,
      });

      client.on('ready', () => {
        this.redisReady = true;
        this.clearRedisFailure();
        this.observability.setDependencyState('cache', 'normal');
        this.logger.log('Redis 缓存已连接');
      });

      client.on('error', (error) => {
        this.redisReady = false;
        this.recordRedisError(error, 'Redis 错误，回退内存缓存', 'redis_runtime_error');
      });

      client.connect().catch((error) => {
        this.redisReady = false;
        this.recordRedisError(error, 'Redis 连接失败，回退内存缓存', 'redis_connect_failed');
      });

      this.redis = client;
    } catch (error) {
      this.redisReady = false;
      this.redis = null;
      this.recordRedisError(error, 'Redis 初始化失败，回退内存缓存', 'redis_init_failed');
    }
  }

  private normalizeKey(key: string): string {
    return `${this.keyPrefix}${key.trim()}`;
  }

  private async scanKeys(pattern: string): Promise<string[]> {
    if (!this.redisReady || !this.redis) return [];
    const keys: string[] = [];
    let cursor = '0';
    do {
      const [nextCursor, batch] = await this.redis.scan(cursor, 'MATCH', pattern, 'COUNT', 200);
      cursor = nextCursor;
      if (Array.isArray(batch) && batch.length > 0) {
        keys.push(...batch);
      }
    } while (cursor !== '0');
    return keys;
  }

  private readDefaultTtl(): number {
    const value = Number(this.configService.get<string>('CACHE_TTL_DEFAULT_SECONDS', '0'));
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
  }

  private readTtlOverrides(): Record<string, number> {
    const raw = (this.configService.get<string>('CACHE_TTL_OVERRIDES', '{}') || '{}').trim();
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const normalized: Record<string, number> = {};
      for (const [k, v] of Object.entries(parsed)) {
        const n = Number(v);
        if (Number.isFinite(n) && n > 0) normalized[k] = Math.floor(n);
      }
      return normalized;
    } catch {
      this.logger.warn('CACHE_TTL_OVERRIDES 解析失败，已忽略覆盖配置');
      return {};
    }
  }

  private errMsg(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }

  private clearRedisFailure(): void {
    this.fallbackActive = false;
    this.lastError = null;
    this.lastErrorAt = null;
    this.lastFailureStage = null;
  }

  private recordRedisError(error: unknown, message: string, stage: CacheFailureStage): void {
    this.fallbackActive = true;
    this.lastError = this.errMsg(error);
    this.lastErrorAt = new Date().toISOString();
    this.lastFailureStage = stage;
    this.observability.setDependencyState('cache', 'degraded');
    this.logger.warn(`${message}: ${this.lastError}`);
  }
}
