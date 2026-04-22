import { BadGatewayException, HttpException, Injectable, Logger, UnprocessableEntityException } from '@nestjs/common';
import { CommonCacheService } from '../common/cache.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { PaperTradingIdempotencyService } from './paper-trading-idempotency.service';

@Injectable()
export class PaperTradingService {
  private static readonly SUMMARY_TTL_SECONDS = 30;
  private readonly logger = new Logger(PaperTradingService.name);

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly idempotency: PaperTradingIdempotencyService,
    private readonly cacheService: CommonCacheService,
  ) { }

  private async call(action: string, params: Record<string, unknown> = {}) {
    try {
      const result = await this.mcp.callTool('paper_trading_manager', {
        action,
        params,
      });
      return this.unwrapManagerResult(action, result);
    } catch (error) {
      if (error instanceof HttpException) throw error;
      if (error instanceof BadGatewayException) throw error;
      throw new BadGatewayException({
        success: false,
        message: `调用 paper_trading_manager.${action} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  async listAccounts(userId: string) {
    return this.call('list_accounts', { user_id: userId });
  }

  async summary(userId: string, accountId?: string) {
    const cacheKey = `paper-trading:summary:${userId}:${accountId?.trim() || 'default'}`;
    const ttlSeconds = this.cacheService.resolveTtl('paper-trading.summary', PaperTradingService.SUMMARY_TTL_SECONDS);
    const data = await this.call('summary', { user_id: userId, account_id: accountId });
    if (data && typeof data === 'object') {
      await this.cacheService.set(cacheKey, data, ttlSeconds);
    }
    return data;
  }

  async positions(userId: string, accountId?: string) {
    return this.call('positions', { user_id: userId, account_id: accountId });
  }

  async orders(userId: string, accountId?: string) {
    return this.call('orders', { user_id: userId, account_id: accountId });
  }

  async orderEvents(userId: string, params: {
    order_id?: string; account_id?: string; limit?: number;
  } = {}) {
    return this.call('order_events', { user_id: userId, ...params });
  }

  async pendingOrders(userId: string, accountId?: string) {
    return this.call('pending_orders', { user_id: userId, account_id: accountId });
  }

  async placeOrder(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; order_type?: string; stop_price?: number;
    account_id?: string;
  }, idempotencyKey?: string) {
    const request = { user_id: userId, ...params, shares: params.quantity };
    return this.idempotency.execute({
      userId,
      scope: 'order',
      idempotencyKey,
      operation: () => this.call('place_order', request),
    });
  }

  async cancelOrder(userId: string, orderId: string, idempotencyKey?: string) {
    return this.idempotency.execute({
      userId,
      scope: 'cancel',
      idempotencyKey,
      operation: () => this.call('cancel_order', { user_id: userId, order_id: orderId }),
    });
  }

  async updatePrices(userId: string, accountId?: string) {
    return this.call('update_prices', { user_id: userId, account_id: accountId });
  }

  async navHistory(userId: string, accountId?: string, limit?: number) {
    return this.call('nav_history', { user_id: userId, account_id: accountId, limit: limit ?? 90 });
  }

  async performance(userId: string, accountId?: string, days = 30) {
    const [navResult, orderResult] = await Promise.allSettled([
      this.navHistory(userId, accountId, days > 0 ? Math.max(days, 30) : 365),
      this.orders(userId, accountId),
    ]);
    const navPayload = navResult.status === 'fulfilled' ? navResult.value : null;
    const orderPayload = orderResult.status === 'fulfilled' ? orderResult.value : null;
    const warnings = [
      navResult.status === 'rejected'
        ? this.toPerformanceWarning('nav_history', navResult.reason)
        : null,
      orderResult.status === 'rejected'
        ? this.toPerformanceWarning('orders', orderResult.reason)
        : null,
    ].filter((item): item is string => Boolean(item));

    const nav = Array.isArray((navPayload as Record<string, unknown>)?.nav)
      ? ((navPayload as Record<string, unknown>).nav as Record<string, unknown>[])
      : Array.isArray(navPayload) ? (navPayload as Record<string, unknown>[]) : [];
    const series = (days > 0 ? nav.slice(-days) : nav).map((item) => ({
      date: String(item.nav_date ?? item.date ?? ''),
      totalValue: Number(item.total_value ?? item.value ?? 0),
      dailyReturn: Number(item.daily_return ?? 0),
    }));

    const equityCurve = series.map((item) => item.totalValue);
    const dailyReturns = series.map((item) => item.dailyReturn);
    const totalReturn = equityCurve.length >= 2 && equityCurve[0] > 0
      ? (equityCurve[equityCurve.length - 1] - equityCurve[0]) / equityCurve[0]
      : 0;
    const mean = dailyReturns.length ? dailyReturns.reduce((sum, item) => sum + item, 0) / dailyReturns.length : 0;
    const variance = dailyReturns.length > 1
      ? dailyReturns.reduce((sum, item) => sum + (item - mean) ** 2, 0) / (dailyReturns.length - 1)
      : 0;
    const std = Math.sqrt(Math.max(variance, 0));
    const sharpe = std > 0 ? mean / std * Math.sqrt(252) : 0;

    let peak = equityCurve[0] ?? 0;
    let maxDrawdown = 0;
    equityCurve.forEach((value) => {
      peak = Math.max(peak, value);
      if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (value - peak) / peak);
    });

    const positiveDays = dailyReturns.filter((item) => item > 0).length;
    const winRate = dailyReturns.length ? positiveDays / dailyReturns.length : 0;

    const orders = Array.isArray((orderPayload as Record<string, unknown>)?.orders)
      ? ((orderPayload as Record<string, unknown>).orders as Record<string, unknown>[])
      : Array.isArray(orderPayload) ? (orderPayload as Record<string, unknown>[]) : [];
    const avgHoldDays = this.estimateAverageHoldDays(orders);

    return {
      dailyReturns: series,
      metrics: { totalReturn, sharpe, maxDrawdown, winRate, avgHoldDays },
      warnings,
    };
  }

  async matchingStatus() {
    return this.call('matching_status');
  }

  async navStatus() {
    return this.call('nav_status');
  }

  async realtimeSnapshot(userId: string, accountId?: string) {
    const [summary, positions, pendingOrders] = await Promise.all([
      this.summary(userId, accountId),
      this.positions(userId, accountId),
      this.pendingOrders(userId, accountId),
    ]);

    return {
      ts: new Date().toISOString(),
      account_id: accountId || (summary as Record<string, unknown>)?.account_id,
      summary,
      positions,
      pending_orders: pendingOrders,
    };
  }

  async setRiskRules(userId: string, params: {
    account_id?: string; max_position_pct?: number;
    max_drawdown_pct?: number; stop_loss_pct?: number;
  }) {
    return this.call('set_risk_rules', { user_id: userId, ...params });
  }

  // MCP Compliance Manager Integration
  async checkCompliance(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; account_id?: string;
  }) {
    try {
      const payload = this.unwrapToolEnvelope('compliance_manager.check_order', await this.mcp.callTool('compliance_manager', {
        action: 'check_order',
        params: { user_id: userId, ...params },
      }));
      const blocked = payload.blocked === true || payload.passed === false;
      const violations = this.toStringArray(payload.violations);
      const warnings = this.toStringArray(payload.warnings);
      return {
        success: !blocked,
        data: {
          status: blocked ? 'blocked' : 'passed',
          reason: blocked ? (violations[0] ?? '触发风控限制') : null,
          passed: !blocked,
          blocked,
          checks: payload.checks ?? {},
          violations,
          warnings,
        },
      };
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP compliance_manager (check_order) 失败',
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  // MCP Execution Manager Integration
  async routeExecution(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; urgency?: string; order_type?: string; stop_price?: number; account_id?: string;
    artifact_id?: string; output_artifact_id?: string;
  }, idempotencyKey?: string) {
    return this.idempotency.execute({
      userId,
      scope: 'route-execution',
      idempotencyKey,
      operation: async () => {
        try {
          const execution = this.unwrapToolEnvelope('execution_manager.vwap', await this.mcp.callTool('execution_manager', {
            action: params.urgency === 'high' ? 'vwap' : 'twap',
            params: {
              user_id: userId,
              code: params.code,
              direction: params.direction,
              total_quantity: params.quantity,
              duration_minutes: params.urgency === 'high' ? 5 : 15,
              slices: params.urgency === 'high' ? 1 : 3,
              reference_price: params.price ?? params.stop_price,
              artifact_id: params.artifact_id ?? params.output_artifact_id,
            },
          }));
          const order = await this.call('place_order', {
            user_id: userId,
            code: params.code,
            direction: params.direction,
            quantity: params.quantity,
            shares: params.quantity,
            price: params.price,
            order_type: params.order_type,
            stop_price: params.stop_price,
            account_id: params.account_id,
          });
          return { execution, order };
        } catch (error) {
          if (error instanceof HttpException) throw error;
          throw new BadGatewayException({
            success: false,
            message: '调用 MCP execution_manager (route_order) 失败',
            detail: String(error instanceof Error ? error.message : error),
          });
        }
      },
    });
  }

  async executionStatus(userId: string, executionId: string) {
    try {
      return this.unwrapToolEnvelope('execution_manager.summary', await this.mcp.callTool('execution_manager', {
        action: 'summary',
        params: { user_id: userId, task_id: executionId },
      }));
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP execution_manager (execution_status) 失败',
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private unwrapManagerResult(action: string, result: unknown) {
    if (typeof result === 'string' && /error executing tool|validation error/i.test(result)) {
      throw new Error(result);
    }
    if (result && typeof result === 'object') {
      const obj = result as Record<string, unknown>;
      if (obj.success === false) {
        const message = String(obj.error || obj.message || `${action} 操作失败`);
        throw new UnprocessableEntityException({
          success: false,
          code: 'PAPER_TRADING_REJECTED',
          error: message,
          message,
          detail: {
            action,
            upstream: obj,
          },
        });
      }
      if ('data' in obj) {
        const data = obj.data;
        if (typeof data === 'string' && /error executing tool|validation error/i.test(data)) {
          throw new Error(data);
        }
        return data;
      }
    }
    return result;
  }

  private unwrapToolEnvelope(action: string, result: unknown): Record<string, unknown> {
    if (typeof result === 'string' && /error executing tool|validation error/i.test(result)) {
      throw new Error(result);
    }
    if (!result || typeof result !== 'object') {
      return {};
    }
    const obj = result as Record<string, unknown>;
    if (obj.success === false) {
      throw new Error(String(obj.error || obj.message || `${action} 操作失败`));
    }
    const data = obj.data;
    if (typeof data === 'string' && /error executing tool|validation error/i.test(data)) {
      throw new Error(data);
    }
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      return data as Record<string, unknown>;
    }
    return {};
  }

  private toStringArray(value: unknown) {
    return Array.isArray(value)
      ? value.map((item) => String(item)).filter((item) => item.trim().length > 0)
      : [];
  }

  private estimateAverageHoldDays(orders: Record<string, unknown>[]) {
    const buyQueues = new Map<string, number[]>();
    const holdDays: number[] = [];

    orders.forEach((item) => {
      const code = String(item.stock_code ?? item.code ?? '');
      const tradeType = String(item.trade_type ?? item.direction ?? '').toLowerCase();
      const tradeTime = new Date(String(item.trade_time ?? item.created_at ?? '')).getTime();
      if (!code || !Number.isFinite(tradeTime)) return;
      if (tradeType.includes('buy') || tradeType.includes('买')) {
        const queue = buyQueues.get(code) ?? [];
        queue.push(tradeTime);
        buyQueues.set(code, queue);
        return;
      }
      if (tradeType.includes('sell') || tradeType.includes('卖')) {
        const queue = buyQueues.get(code) ?? [];
        const openedAt = queue.shift();
        if (openedAt) holdDays.push(Math.max(1, (tradeTime - openedAt) / 86400000));
        buyQueues.set(code, queue);
      }
    });

    if (!holdDays.length) return 0;
    return holdDays.reduce((sum, item) => sum + item, 0) / holdDays.length;
  }

  private toPerformanceWarning(scope: 'nav_history' | 'orders', error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    return `performance.${scope} degraded: ${detail}`;
  }

  private errorMessage(error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }
}
