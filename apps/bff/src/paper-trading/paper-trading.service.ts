import { BadGatewayException, BadRequestException, HttpException, Injectable, Logger, UnprocessableEntityException } from '@nestjs/common';
import type { PaperTradingTrustLevel, PaperTradingTrustState, PaperTradingTrustStatus } from '@aiask/shared-types';
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

  private async call(action: string, params: Record<string, unknown> = {}, options: { retryOnTransportError?: boolean } = {}) {
    try {
      const result = await this.mcp.callTool('paper_trading_manager', {
        action,
        params,
      }, { retryOnTransportError: options.retryOnTransportError });
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
    const data = await this.call('summary', { user_id: userId, account_id: accountId }, { retryOnTransportError: true });
    if (data && typeof data === 'object') {
      await this.cacheService.set(cacheKey, data, ttlSeconds);
    }
    return data;
  }

  async positions(userId: string, accountId?: string) {
    return this.call('positions', { user_id: userId, account_id: accountId }, { retryOnTransportError: true });
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

  async reconcile(userId: string, params: {
    account_id?: string;
    refresh_prices?: boolean;
    force?: boolean;
  } = {}) {
    const data = await this.call('reconcile', { user_id: userId, ...params });
    const cacheKey = `paper-trading:summary:${userId}:${params.account_id?.trim() || 'default'}`;
    await this.cacheService.del(cacheKey);
    return data;
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

  async testCleanup(userId: string, params: { account_id?: string; test_run_id?: string } = {}) {
    const accountId = String(params.account_id ?? '').trim();
    if (!this.isSandboxAccount(accountId)) {
      throw new BadRequestException({
        success: false,
        code: 'PAPER_TRADING_CLEANUP_FORBIDDEN',
        message: '测试清理只允许 sandbox/test/demo 模拟账户，不能作用于真实或默认账户',
        detail: { account_id: accountId || null },
      });
    }

    const pendingPayload = await this.pendingOrders(userId, accountId);
    const pendingOrders = this.asRecordArray(this.asRecord(pendingPayload)?.orders ?? pendingPayload)
      .filter((order) => this.matchesTestRun(order, params.test_run_id));
    const cancelled: Array<{ order_id: string; result: unknown }> = [];
    const failed: Array<{ order_id: string; error: string }> = [];

    for (const order of pendingOrders) {
      const orderId = String(order.order_id ?? order.id ?? '').trim();
      if (!orderId) continue;
      try {
        const result = await this.cancelOrder(userId, orderId, `test-cleanup:${accountId}:${orderId}`);
        cancelled.push({ order_id: orderId, result });
      } catch (error) {
        failed.push({ order_id: orderId, error: error instanceof Error ? error.message : String(error) });
      }
    }

    let reconcile: unknown = null;
    try {
      reconcile = await this.reconcile(userId, { account_id: accountId, force: true, refresh_prices: true });
    } catch (error) {
      failed.push({ order_id: 'reconcile', error: error instanceof Error ? error.message : String(error) });
    }

    return {
      account_id: accountId,
      test_run_id: params.test_run_id ?? null,
      cancelled_count: cancelled.length,
      failed_count: failed.length,
      cancelled,
      failed,
      reconcile,
      limitations: [
        'cleanup 只取消测试账户未成交挂单并刷新对账',
        '已成交订单不绕过 T+1、持仓可卖数量或真实账本规则',
      ],
    };
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

  async trustStatus(userId: string, accountId?: string): Promise<PaperTradingTrustStatus> {
    const [
      summary,
      positionsPayload,
      ordersPayload,
      pendingPayload,
      navPayload,
      matchingStatusPayload,
      navStatusPayload,
    ] = await Promise.all([
      this.summary(userId, accountId),
      this.positions(userId, accountId),
      this.orders(userId, accountId),
      this.pendingOrders(userId, accountId),
      this.navHistory(userId, accountId, 2),
      this.matchingStatus(),
      this.navStatus(),
    ]);

    const now = new Date();
    const summaryRecord = this.asRecord(summary) ?? {};
    const positionsRecord = this.asRecord(positionsPayload) ?? {};
    const ordersRecord = this.asRecord(ordersPayload) ?? {};
    const pendingRecord = this.asRecord(pendingPayload) ?? {};
    const navRecord = this.asRecord(navPayload) ?? {};
    const matchingStatus = this.asRecord(matchingStatusPayload) ?? {};
    const navStatus = this.asRecord(navStatusPayload) ?? {};
    const accountRecord = this.asRecord(summaryRecord.account) ?? {};
    const reconciliation = this.asRecord(summaryRecord.reconciliation ?? positionsRecord.reconciliation);

    const positions = this.asRecordArray(positionsRecord.positions);
    const orders = this.asRecordArray(ordersRecord.orders);
    const pendingOrders = this.asRecordArray(pendingRecord.orders);
    const nav = this.asRecordArray(navRecord.nav);
    const latestNav = nav.length > 0 ? nav[nav.length - 1] : null;

    const resolvedAccountId = String(
      summaryRecord.account_id
      ?? positionsRecord.account_id
      ?? ordersRecord.account_id
      ?? pendingRecord.account_id
      ?? accountId
      ?? '',
    ).trim() || undefined;

    const marketPhase = this.isTradingHoursShanghai(now) ? 'trading' : 'offhours';
    const matchingRunning = this.isProbeRunning(matchingStatus);
    const navRunning = this.isProbeRunning(navStatus);
    const scanIntervalSeconds = this.toPositiveNumber(matchingStatus.scan_interval) ?? 30;

    const matchingAt = this.latestTimestamp([matchingStatus.last_scan]);
    const priceRefreshAt = this.latestTimestamp([
      accountRecord.updated_at,
      ...positions.flatMap((item) => [item.updated_at, item.created_at]),
    ]);
    const latestPendingOrderAt = this.latestTimestamp(
      pendingOrders.flatMap((item) => [item.updated_at, item.created_at]),
    );
    const latestOrderAt = this.latestTimestamp([
      ...pendingOrders.flatMap((item) => [item.updated_at, item.created_at]),
      ...orders.flatMap((item) => [item.filled_at, item.trade_time, item.updated_at, item.created_at]),
    ]);
    const navSnapshotAt = latestNav
      ? this.normalizeNavSnapshotTimestamp(latestNav)
      : this.latestTimestamp([navStatus.last_run]);

    const matchingAgeSeconds = this.ageSeconds(matchingAt, now);
    const priceAgeSeconds = this.ageSeconds(priceRefreshAt, now);
    const navAgeSeconds = this.ageSeconds(navSnapshotAt, now);
    const orderAgeSeconds = this.ageSeconds(latestOrderAt, now);

    const matchingFresh = pendingOrders.length === 0
      ? true
      : matchingRunning
        && matchingAgeSeconds != null
        && matchingAgeSeconds <= Math.max(scanIntervalSeconds * 3, 90);
    const pricesFresh = positions.length === 0
      ? true
      : priceAgeSeconds != null
        && priceAgeSeconds <= (marketPhase === 'trading' ? 90 : 24 * 60 * 60);

    const latestNavDate = String(latestNav?.nav_date ?? '').trim() || null;
    const expectedNavDate = this.expectedNavDate(now);
    const navFresh = latestNavDate != null && latestNavDate >= expectedNavDate;

    const positionsReconciled = reconciliation != null;
    const positionsDriftDetected = reconciliation?.drift_detected === true;

    const matchingMs = this.parseTimestamp(matchingAt);
    const latestPendingMs = this.parseTimestamp(latestPendingOrderAt);
    const ordersReconciled = pendingOrders.length === 0
      ? true
      : matchingMs != null && latestPendingMs != null && matchingMs >= latestPendingMs;

    const hasActivity = positions.length > 0 || pendingOrders.length > 0 || orders.length > 0 || nav.length > 0;
    const latest = hasActivity && positionsReconciled && ordersReconciled && pricesFresh && matchingFresh;

    let level: PaperTradingTrustLevel = 'blocked';
    let headline = '数据待刷新，先别用于演示';
    if (!hasActivity) {
      headline = '账户还没有交易轨迹，先做首笔模拟委托';
    } else if (latest && navFresh) {
      level = 'ready';
      headline = '交易链路最新，可直接演示';
    } else if (latest) {
      level = 'caution';
      headline = '交易链路已最新，但 NAV 快照待补齐';
    }

    const reasons: string[] = [];
    if (!hasActivity) {
      reasons.push('账户还没有持仓、挂单、成交或 NAV 轨迹');
    }
    if (!pricesFresh && positions.length > 0) {
      reasons.push('持仓价格刷新时间偏旧');
    }
    if (!matchingFresh && pendingOrders.length > 0) {
      reasons.push(matchingRunning ? '最近一次撮合扫描偏旧，挂单状态可能不是最新' : '撮合引擎未运行');
    }
    if (!ordersReconciled && pendingOrders.length > 0) {
      reasons.push('存在挂单尚未被最近一次撮合扫描覆盖');
    }
    if (!positionsReconciled) {
      reasons.push('持仓账本状态未返回 reconcile 结果');
    } else if (positionsDriftDetected) {
      reasons.push('最近一次检查检测到持仓漂移，系统已自动修正');
    }
    if (!navFresh) {
      reasons.push(`NAV 快照停留在 ${latestNavDate ?? '暂无快照'}，当前预期日期为 ${expectedNavDate}`);
    } else if (!navRunning && latestNavDate == null) {
      reasons.push('NAV 引擎未运行且暂无可用快照');
    }

    return {
      account_id: resolvedAccountId,
      checked_at: now.toISOString(),
      market_phase: marketPhase,
      has_activity: hasActivity,
      latest,
      demo_ready: level !== 'blocked',
      level,
      headline,
      reasons,
      environment: {
        mode: 'paper',
        simulated_only: true,
        dry_run: false,
        live_trading: false,
        label: '仅模拟环境 · 非 dry-run',
      },
      timestamps: {
        matching: {
          at: matchingAt,
          age_seconds: matchingAgeSeconds,
          fresh: matchingFresh,
          status: this.resolveTimestampState(matchingFresh, pendingOrders.length > 0),
          detail: pendingOrders.length === 0
            ? '当前无挂单待撮合'
            : matchingFresh
              ? '最近一次撮合扫描已覆盖当前挂单'
              : matchingRunning
                ? '最近一次撮合扫描偏旧'
                : '撮合引擎未运行',
        },
        prices: {
          at: priceRefreshAt,
          age_seconds: priceAgeSeconds,
          fresh: pricesFresh,
          status: this.resolveTimestampState(pricesFresh, positions.length > 0),
          detail: positions.length === 0
            ? '当前无持仓，不需要刷新价格'
            : pricesFresh
              ? '持仓价格仍在新鲜窗口内'
              : '持仓价格刷新时间偏旧',
        },
        nav: {
          at: navSnapshotAt,
          age_seconds: navAgeSeconds,
          fresh: navFresh,
          status: latestNavDate == null ? 'blocked' : navFresh ? 'ok' : 'warning',
          detail: latestNavDate == null
            ? '暂无 NAV 快照'
            : navFresh
              ? `最新 NAV 日期 ${latestNavDate}，符合当前时段预期`
              : `最新 NAV 日期 ${latestNavDate}，尚未追上预期日期 ${expectedNavDate}`,
        },
        orders: {
          at: latestOrderAt,
          age_seconds: orderAgeSeconds,
          fresh: ordersReconciled,
          status: pendingOrders.length === 0 ? 'ok' : ordersReconciled ? 'ok' : matchingRunning ? 'warning' : 'blocked',
          detail: pendingOrders.length === 0
            ? '当前无挂单待撮合'
            : ordersReconciled
              ? '挂单已被最近一次撮合扫描覆盖'
              : '挂单更新时间晚于最近一次撮合扫描',
        },
      },
      reconcile: {
        positions: {
          reconciled: positionsReconciled,
          status: positionsReconciled ? (positionsDriftDetected ? 'warning' : 'ok') : 'blocked',
          detail: !positionsReconciled
            ? '未收到持仓 reconcile 结果'
            : positionsDriftDetected
              ? '检测到持仓/账户漂移，但本次已自动校准'
              : '账本与持仓一致',
          drift_detected: positionsDriftDetected,
          reference_at: priceRefreshAt,
        },
        orders: {
          reconciled: ordersReconciled,
          status: pendingOrders.length === 0 ? 'ok' : ordersReconciled ? 'ok' : matchingRunning ? 'warning' : 'blocked',
          detail: pendingOrders.length === 0
            ? '当前无挂单，订单账本稳定'
            : ordersReconciled
              ? '订单状态与最近一次撮合扫描一致'
              : '请等待下一次撮合扫描或手动刷新状态',
          drift_detected: false,
          reference_at: latestPendingOrderAt ?? latestOrderAt,
        },
        nav: {
          reconciled: navFresh,
          status: latestNavDate == null ? 'blocked' : navFresh ? 'ok' : 'warning',
          detail: latestNavDate == null
            ? '暂无 NAV 快照'
            : navFresh
              ? 'NAV 快照已对齐到当前预期交易日'
              : `NAV 快照仍停留在 ${latestNavDate}`,
          drift_detected: false,
          reference_at: navSnapshotAt,
        },
      },
    };
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

  private asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null;
  }

  private asRecordArray(value: unknown): Record<string, unknown>[] {
    return Array.isArray(value)
      ? value.filter((item): item is Record<string, unknown> => Boolean(this.asRecord(item)))
      : [];
  }

  private toPositiveNumber(value: unknown) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
  }

  private parseTimestamp(value: unknown) {
    if (typeof value !== 'string' || value.trim().length === 0) {
      return null;
    }
    const raw = value.trim();
    const direct = Date.parse(raw);
    if (Number.isFinite(direct)) {
      return direct;
    }
    const normalized = raw.includes(' ') ? raw.replace(' ', 'T') : raw;
    const fallback = Date.parse(normalized);
    return Number.isFinite(fallback) ? fallback : null;
  }

  private normalizeTimestamp(value: unknown) {
    const parsed = this.parseTimestamp(value);
    return parsed == null ? null : new Date(parsed).toISOString();
  }

  private latestTimestamp(values: unknown[]) {
    let bestMs: number | null = null;
    let bestValue: string | null = null;
    values.forEach((candidate) => {
      const normalized = this.normalizeTimestamp(candidate);
      const parsed = normalized == null ? null : this.parseTimestamp(normalized);
      if (normalized == null || parsed == null) {
        return;
      }
      if (bestMs == null || parsed > bestMs) {
        bestMs = parsed;
        bestValue = normalized;
      }
    });
    return bestValue;
  }

  private ageSeconds(value: string | null, reference = new Date()) {
    const parsed = value == null ? null : this.parseTimestamp(value);
    if (parsed == null) {
      return null;
    }
    return Math.max(0, Math.round((reference.getTime() - parsed) / 1000));
  }

  private isProbeRunning(payload: Record<string, unknown> | null) {
    if (!payload) {
      return false;
    }
    if (payload.running === true || payload.ok === true) {
      return true;
    }
    return String(payload.status ?? '').trim().toLowerCase() === 'running';
  }

  private resolveTimestampState(fresh: boolean, expected: boolean): PaperTradingTrustState {
    if (!expected) {
      return 'ok';
    }
    return fresh ? 'ok' : 'warning';
  }

  private getShanghaiParts(reference = new Date()) {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      weekday: 'short',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
    const parts = formatter.formatToParts(reference);
    const lookup = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
    return {
      weekday: lookup('weekday'),
      date: `${lookup('year')}-${lookup('month')}-${lookup('day')}`,
      hour: Number(lookup('hour') || 0),
      minute: Number(lookup('minute') || 0),
      second: Number(lookup('second') || 0),
    };
  }

  private formatShanghaiDate(reference: Date) {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const parts = formatter.formatToParts(reference);
    const lookup = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
    return `${lookup('year')}-${lookup('month')}-${lookup('day')}`;
  }

  private isTradingHoursShanghai(reference = new Date()) {
    const parts = this.getShanghaiParts(reference);
    if (parts.weekday === 'Sat' || parts.weekday === 'Sun') {
      return false;
    }
    const hhmm = parts.hour * 100 + parts.minute;
    return (hhmm >= 925 && hhmm <= 1131) || (hhmm >= 1255 && hhmm <= 1501);
  }

  private expectedNavDate(reference = new Date()) {
    const parts = this.getShanghaiParts(reference);
    let probe = new Date(`${parts.date}T12:00:00+08:00`);
    if (parts.weekday === 'Sat' || parts.weekday === 'Sun' || (parts.hour * 100 + parts.minute) < 1530) {
      probe.setUTCDate(probe.getUTCDate() - 1);
    }
    while (true) {
      const weekday = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', weekday: 'short' }).format(probe);
      if (weekday !== 'Sat' && weekday !== 'Sun') {
        break;
      }
      probe.setUTCDate(probe.getUTCDate() - 1);
    }
    return this.formatShanghaiDate(probe);
  }

  private normalizeNavSnapshotTimestamp(payload: Record<string, unknown>) {
    const createdAt = this.normalizeTimestamp(payload.created_at);
    if (createdAt) {
      return createdAt;
    }
    const navDate = String(payload.nav_date ?? '').trim();
    if (!navDate) {
      return null;
    }
    return this.normalizeTimestamp(`${navDate}T15:30:00+08:00`);
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

  private isSandboxAccount(accountId: string) {
    return /(sandbox|test|demo|paper-audit|playwright|qa)/i.test(accountId);
  }

  private matchesTestRun(order: Record<string, unknown>, testRunId?: string) {
    const normalized = String(testRunId ?? '').trim();
    if (!normalized) return true;
    return [
      order.test_run_id,
      order.testRunId,
      order.client_order_id,
      order.clientOrderId,
      order.idempotency_key,
      order.idempotencyKey,
      order.remark,
      order.note,
    ].some((value) => String(value ?? '').includes(normalized));
  }

  private toPerformanceWarning(scope: 'nav_history' | 'orders', error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    return `performance.${scope} degraded: ${detail}`;
  }

  private errorMessage(error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }
}
