import {
  ExecutionContext,
  HttpException,
  Injectable,
  Logger,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import {
  InjectThrottlerOptions,
  InjectThrottlerStorage,
  ThrottlerGuard,
  ThrottlerModuleOptions,
  ThrottlerStorage,
} from '@nestjs/throttler';
import { CommonCacheService } from './cache.service';

/**
 * Redis-backed trading throttle guard.
 *
 * 交易级别限流（参照证监会程序化交易管理细则）：
 *   - 单账户每秒申报上限：10 笔
 *   - 单账户每日申报上限：500 笔
 *
 * 当 Redis 不可用时回退到 NestJS 内存 ThrottlerGuard。
 */
@Injectable()
export class TradingThrottleGuard extends ThrottlerGuard {
  private readonly logger = new Logger(TradingThrottleGuard.name);

  // 默认限流阈值（可通过 Redis config key 动态调整）
  private readonly PER_SECOND_LIMIT = 10;
  private readonly PER_DAY_LIMIT = 500;

  constructor(
    @InjectThrottlerOptions() options: ThrottlerModuleOptions,
    @InjectThrottlerStorage() storageService: ThrottlerStorage,
    reflector: Reflector,
    private readonly cache: CommonCacheService,
  ) {
    super(options, storageService, reflector);
  }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest();
    const path: string = request?.route?.path || request?.url || '';

    // 仅对交易下单路径做 Redis 限流
    if (!path.includes('paper-trading/order') && !path.includes('paper-trading/cancel')) {
      return super.canActivate(context);
    }

    const userId: string =
      request?.user?.id || request?.headers?.['x-user-id'] || 'anonymous';

    try {
      const passed = await this.checkRedisThrottle(this.cache, userId);
      if (!passed) {
        this.logger.warn(`Trading throttle exceeded for user ${userId}`);
        throw new HttpException(
          { success: false, message: '交易申报频率超限，请稍后再试' },
          429,
        );
      }
      return true;
    } catch (e) {
      if (e instanceof HttpException) throw e;
      // Redis 异常，回退内存限流
      this.logger.warn(`Redis throttle error, fallback to memory: ${e}`);
      return super.canActivate(context);
    }
  }

  private async checkRedisThrottle(
    cache: CommonCacheService,
    userId: string,
  ): Promise<boolean> {
    const now = new Date();
    const secKey = `throttle:trade:sec:${userId}:${Math.floor(now.getTime() / 1000)}`;
    const dayKey = `throttle:trade:day:${userId}:${now.toISOString().slice(0, 10)}`;

    // 每秒限流：使用原子 INCR 避免并发绕过
    const secCount = await cache.increment(secKey, 2);
    if (secCount > this.PER_SECOND_LIMIT) return false;

    // 每日限流：使用日期分片键，TTL 24h 即可
    const dayCount = await cache.increment(dayKey, 86400);
    if (dayCount > this.PER_DAY_LIMIT) return false;

    return true;
  }
}
