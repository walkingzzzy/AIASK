import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';

type MemoryEntry = { payload: string; expiresAt: number };
type CacheBackend = 'redis' | 'memory' | 'none';

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
  private redis: Redis | null = null;
  private redisReady = false;

  constructor(private readonly configService: ConfigService) {
    this.ttlDefaultSeconds = this.readDefaultTtl();
    this.ttlOverrides = this.readTtlOverrides();
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
        if (!raw) {
          this.stats.misses += 1;
          return { value: null, meta: { hit: false, backend: 'none' } };
        }
        this.stats.hits += 1;
        this.stats.redisHits += 1;
        return { value: JSON.parse(raw) as T, meta: { hit: true, backend: 'redis' } };
      } catch (error) {
        this.stats.errors += 1;
        this.logger.warn(`Redis 读取失败，降级内存缓存: ${this.errMsg(error)}`);
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
        this.stats.redisSets += 1;
        return;
      } catch (error) {
        this.stats.errors += 1;
        this.logger.warn(`Redis 写入失败，降级内存缓存: ${this.errMsg(error)}`);
      }
    }

    this.stats.memorySets += 1;
    this.memory.set(normalizedKey, {
      payload,
      expiresAt: Date.now() + safeTtl * 1000,
    });
  }

  async del(key: string): Promise<void> {
    const normalizedKey = this.normalizeKey(key);
    if (this.redisReady && this.redis) {
      try {
        await this.redis.del(normalizedKey);
      } catch (error) {
        this.stats.errors += 1;
        this.logger.warn(`Redis 删除失败，降级内存缓存: ${this.errMsg(error)}`);
      }
    }
    this.memory.delete(normalizedKey);
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
      redisReady: this.redisReady,
      memorySize: this.memory.size,
      ttl: {
        defaultSeconds: this.ttlDefaultSeconds,
        overrides: this.ttlOverrides,
      },
    };
  }

  private initRedis() {
    const redisUrl = this.configService.get<string>('REDIS_URL');
    if (!redisUrl) {
      this.logger.log('未配置 REDIS_URL，启用内存缓存');
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
        this.logger.log('Redis 缓存已连接');
      });

      client.on('error', (error) => {
        this.redisReady = false;
        this.logger.warn(`Redis 错误，回退内存缓存: ${this.errMsg(error)}`);
      });

      client.connect().catch((error) => {
        this.redisReady = false;
        this.logger.warn(`Redis 连接失败，回退内存缓存: ${this.errMsg(error)}`);
      });

      this.redis = client;
    } catch (error) {
      this.redisReady = false;
      this.redis = null;
      this.logger.warn(`Redis 初始化失败，回退内存缓存: ${this.errMsg(error)}`);
    }
  }

  private normalizeKey(key: string): string {
    return `${this.keyPrefix}${key.trim()}`;
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
}

