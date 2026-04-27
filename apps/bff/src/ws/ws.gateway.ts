import {
  Inject,
  Logger,
  OnModuleDestroy,
  OnModuleInit,
  forwardRef,
} from '@nestjs/common';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { MarketScheduler } from '../market/market.scheduler';
import { AuthService } from '../auth/auth.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';

type WsUser = { id: string; username?: string; role?: string; jti?: string };
type AlertPushEvent = { userId: string | null; data: Record<string, unknown> };
type TradePushEvent = { accountId: string; data: Record<string, unknown> };
type AlertPushListener = (event: AlertPushEvent) => void | Promise<void>;
type TradePushListener = (event: TradePushEvent) => void | Promise<void>;

/**
 * 通用 WebSocket 网关 — 行情推送、告警推送、交易状态推送、策略 NAV 推送。
 * 频道体系：
 *   quote:*    — 实时行情（指数 / 个股 / 批量）
 *   alert      — 告警通知
 *   trade:*    — 模拟交易订单状态
 *   portfolio:* — 组合 NAV
 *   strategy:*  — 策略信号
 *   watchlist:* — 自选股变更
 *   system      — 系统级广播（心跳、公告）
 */
@WebSocketGateway({
  namespace: '/ws',
  cors: { origin: true, credentials: true },
})
export class WsGateway
  implements OnGatewayConnection, OnGatewayDisconnect, OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(WsGateway.name);
  private readonly rooms = new Map<string, Set<string>>(); // room -> clientIds
  private readonly alertListeners = new Set<AlertPushListener>();
  private readonly tradeListeners = new Set<TradePushListener>();
  private heartbeatTimer: NodeJS.Timeout | null = null;

  constructor(
    @Inject(forwardRef(() => MarketScheduler))
    private readonly marketScheduler: MarketScheduler,
    private readonly authService: AuthService,
    private readonly paperTradingService: PaperTradingService,
  ) {}

  @WebSocketServer()
  server!: Server;

  /* ── Lifecycle ────────────────────────────────────────────── */

  onModuleInit() {
    // 每 30 秒发送心跳
    this.heartbeatTimer = setInterval(() => {
      this.server?.emit('heartbeat', { ts: new Date().toISOString() });
    }, 30_000);
  }

  onModuleDestroy() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  async handleConnection(client: Socket) {
    const user = await this.authenticateClient(client);
    if (user) {
      client.data.user = user;
      this.logger.debug(`client connected: ${client.id}, user=${user.id}`);
    } else {
      this.logger.debug(`client connected: ${client.id}, anonymous`);
    }
    // 自动加入 system 频道
    void client.join('system');
  }

  handleDisconnect(client: Socket) {
    // 清理空房间
    for (const [room] of this.rooms.entries()) {
      const roomEmpty = this._untrack(room, client.id);
      if (roomEmpty) {
        this._removeTrackedQuoteCode(room);
      }
    }
    this.logger.debug(`client disconnected: ${client.id}`);
  }

  // ── 行情订阅 ─────────────────────────────────────────────

  @SubscribeMessage('subscribe:quote')
  handleQuoteSub(client: Socket, payload: { codes?: string[]; type?: string }) {
    // type: 'index' | 'stock' | 'batch'
    const roomType = payload.type || 'stock';
    const codes = (payload.codes || []).map((code) => String(code).trim()).filter(Boolean);
    if (codes.length === 0) {
      // 订阅全局行情广播
      const room = `quote:broadcast`;
      void client.join(room);
      this._track(room, client.id);
      this.logger.debug(`${client.id} joined ${room}`);
    } else {
      for (const code of codes) {
        const room = `quote:${roomType}:${code}`;
        void client.join(room);
        this._track(room, client.id);
      }
      this.logger.debug(`${client.id} subscribed to ${codes.length} ${roomType} quotes`);
      if (roomType === 'stock') {
        this.marketScheduler.addSubscribedCodes(codes);
      } else if (roomType === 'index') {
        this.marketScheduler.addSubscribedIndexCodes(codes);
      }
    }
  }

  @SubscribeMessage('unsubscribe:quote')
  handleQuoteUnsub(client: Socket, payload: { codes?: string[]; type?: string }) {
    const roomType = payload.type || 'stock';
    const codes = (payload.codes || []).map((code) => String(code).trim()).filter(Boolean);
    if (codes.length === 0) {
      this._untrack('quote:broadcast', client.id);
      void client.leave('quote:broadcast');
    } else {
      for (const code of codes) {
        const room = `quote:${roomType}:${code}`;
        const roomEmpty = this._untrack(room, client.id);
        if (roomEmpty) {
          this._removeTrackedQuoteCode(room);
        }
        void client.leave(room);
      }
    }
  }

  // ── 告警订阅 ─────────────────────────────────────────────

  @SubscribeMessage('subscribe:alert')
  handleAlertSub(client: Socket) {
    const user = this.requireAuthenticatedUser(client, '告警订阅需要登录');
    if (!user) return;

    const room = `alert:${user.id}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 交易订单订阅 ──────────────────────────────────────────

  @SubscribeMessage('subscribe:trade')
  async handleTradeSub(client: Socket, payload: { accountId?: string } = {}) {
    const accountId = await this.resolveAuthorizedAccountId(client, payload.accountId);
    if (!accountId) return;

    const room = `trade:${accountId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 组合订阅 ──────────────────────────────────────────────

  @SubscribeMessage('subscribe:portfolio')
  async handlePortfolioSub(client: Socket, payload: { accountId?: string } = {}) {
    const accountId = await this.resolveAuthorizedAccountId(client, payload.accountId);
    if (!accountId) return;

    const room = `portfolio:${accountId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 策略订阅 ──────────────────────────────────────────────

  @SubscribeMessage('subscribe:strategy')
  handleStrategySub(client: Socket, payload: { strategyId?: string | number } = {}) {
    const user = this.requireAuthenticatedUser(client, '策略订阅需要登录');
    if (!user) return;

    const strategyId = String(payload.strategyId ?? '').trim();
    if (!strategyId) {
      this.rejectSubscription(client, 'invalid_strategy_id', '缺少 strategyId');
      return;
    }

    const room = `strategy:${strategyId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 自选股订阅 ────────────────────────────────────────────

  @SubscribeMessage('subscribe:watchlist')
  handleWatchlistSub(client: Socket) {
    const user = this.requireAuthenticatedUser(client, '自选股订阅需要登录');
    if (!user) return;

    const room = `watchlist:${user.id}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ══════════════════════════════════════════════════════════
  //  服务端主动推送接口（供其他 BFF 模块注入后调用）
  // ══════════════════════════════════════════════════════════

  /** 广播行情数据到订阅者 */
  pushQuote(code: string, type: 'index' | 'stock', data: Record<string, unknown>) {
    // 推送到指定股票/指数频道
    this.server.to(`quote:${type}:${code}`).emit('quote:update', { code, type, ...data });
    // 同时推送到全局广播频道
    this.server.to('quote:broadcast').emit('quote:update', { code, type, ...data });
  }

  /** 批量推送行情 */
  pushBatchQuotes(data: Array<Record<string, unknown>>) {
    this.server.to('quote:broadcast').emit('quote:batch', { items: data, ts: new Date().toISOString() });
  }

  /** 推送告警通知 */
  pushAlert(userId: string | null, data: Record<string, unknown>) {
    const payload = { ...data, ts: new Date().toISOString() };
    if (userId) {
      this.server.to(`alert:${userId}`).emit('alert:triggered', payload);
    }
    // 同时广播（管理员可见）
    this.server.to('alert:broadcast').emit('alert:triggered', payload);
    this.emitAlertEvent({ userId, data: payload });
  }

  /** 推送告警警告（来自 MCP push_warn） */
  pushWarn(userId: string | null, message: string, level: 'info' | 'warn' | 'error' = 'warn') {
    const payload = { message, level, ts: new Date().toISOString() };
    if (userId) {
      this.server.to(`alert:${userId}`).emit('alert:warn', payload);
    }
    this.server.to('alert:broadcast').emit('alert:warn', payload);
  }

  /** 推送交易订单状态更新 */
  pushTradeUpdate(accountId: string, data: Record<string, unknown>) {
    const payload = {
      ...data,
      ts: new Date().toISOString(),
    };
    this.server.to(`trade:${accountId}`).emit('trade:update', payload);
    this.emitTradeEvent({ accountId, data: payload });
  }

  /** 推送组合 NAV 更新 */
  pushPortfolioUpdate(accountId: string, data: Record<string, unknown>) {
    this.server.to(`portfolio:${accountId}`).emit('portfolio:update', data);
  }

  /** 推送策略 NAV */
  pushStrategyNav(strategyId: string | number, data: Record<string, unknown>) {
    this.server.to(`strategy:${strategyId}`).emit('strategy:nav', data);
  }

  /** 推送自选股变更 */
  pushWatchlistUpdate(userId: string, data: Record<string, unknown>) {
    this.server.to(`watchlist:${userId}`).emit('watchlist:update', data);
  }

  /** 推送系统广播消息 */
  pushSystemMessage(message: string, level: 'info' | 'warn' | 'error' = 'info') {
    this.server.to('system').emit('system:message', {
      message,
      level,
      ts: new Date().toISOString(),
    });
  }

  onAlertPushed(listener: AlertPushListener): () => void {
    this.alertListeners.add(listener);
    return () => {
      this.alertListeners.delete(listener);
    };
  }

  onTradeUpdatePushed(listener: TradePushListener): () => void {
    this.tradeListeners.add(listener);
    return () => {
      this.tradeListeners.delete(listener);
    };
  }

  // ── 内部辅助 ──────────────────────────────────────────────

  private emitAlertEvent(event: AlertPushEvent) {
    for (const listener of this.alertListeners) {
      Promise.resolve()
        .then(() => listener(event))
        .catch((error) => {
          this.logger.error(`alert listener failed: ${String(error)}`);
        });
    }
  }

  private emitTradeEvent(event: TradePushEvent) {
    for (const listener of this.tradeListeners) {
      Promise.resolve()
        .then(() => listener(event))
        .catch((error) => {
          this.logger.error(`trade listener failed: ${String(error)}`);
        });
    }
  }

  private _track(room: string, clientId: string) {
    if (!this.rooms.has(room)) this.rooms.set(room, new Set());
    this.rooms.get(room)!.add(clientId);
  }

  private _untrack(room: string, clientId: string) {
    const clients = this.rooms.get(room);
    if (!clients) return false;
    clients.delete(clientId);
    if (clients.size === 0) {
      this.rooms.delete(room);
      return true;
    }
    return false;
  }

  private _removeTrackedQuoteCode(room: string) {
    const tracked = this._extractTrackedQuoteCode(room);
    if (tracked?.type === 'stock') {
      this.marketScheduler.removeSubscribedCodes([tracked.code]);
    } else if (tracked?.type === 'index') {
      this.marketScheduler.removeSubscribedIndexCodes([tracked.code]);
    }
  }

  private _extractTrackedQuoteCode(room: string): { type: 'stock' | 'index'; code: string } | null {
    const stockPrefix = 'quote:stock:';
    if (room.startsWith(stockPrefix)) {
      const code = room.slice(stockPrefix.length).trim();
      return code ? { type: 'stock', code } : null;
    }

    const indexPrefix = 'quote:index:';
    if (room.startsWith(indexPrefix)) {
      const code = room.slice(indexPrefix.length).trim();
      return code ? { type: 'index', code } : null;
    }

    return null;
  }

  private async authenticateClient(client: Socket): Promise<WsUser | null> {
    const token = this.extractAccessToken(client);
    if (!token) return null;

    try {
      return await this.authService.verifyAccessToken(token);
    } catch (error) {
      this.logger.debug(`ws auth failed for ${client.id}: ${String(error)}`);
      return null;
    }
  }

  private extractAccessToken(client: Socket): string | undefined {
    const authToken = client.handshake.auth?.token;
    if (typeof authToken === 'string' && authToken.trim()) {
      return authToken.trim();
    }

    const accessToken = client.handshake.auth?.accessToken;
    if (typeof accessToken === 'string' && accessToken.trim()) {
      return accessToken.trim();
    }

    const authorization = client.handshake.headers.authorization;
    const bearer = Array.isArray(authorization)
      ? this.extractBearer(authorization[0])
      : this.extractBearer(authorization);
    if (bearer) return bearer;

    const cookieHeader = client.handshake.headers.cookie;
    const rawCookie = Array.isArray(cookieHeader) ? cookieHeader.join('; ') : cookieHeader;
    if (!rawCookie) return undefined;

    return this.parseCookieHeader(rawCookie).access_token;
  }

  private extractBearer(authorization?: string): string | undefined {
    if (!authorization) return undefined;
    const [scheme, token] = authorization.split(' ');
    if (!scheme || !token || scheme.toLowerCase() !== 'bearer') return undefined;
    return token;
  }

  private parseCookieHeader(raw: string): Record<string, string> {
    return raw.split(';').reduce<Record<string, string>>((acc, item) => {
      const [name, ...value] = item.split('=');
      const key = name?.trim();
      if (!key) return acc;
      acc[key] = decodeURIComponent(value.join('=').trim());
      return acc;
    }, {});
  }

  private requireAuthenticatedUser(client: Socket, message: string): WsUser | null {
    const user = client.data.user as WsUser | undefined;
    if (user?.id) return user;
    this.rejectSubscription(client, 'unauthorized', message);
    return null;
  }

  private async resolveAuthorizedAccountId(client: Socket, requestedAccountId?: string): Promise<string | null> {
    const user = this.requireAuthenticatedUser(client, '账户订阅需要登录');
    if (!user) return null;

    const normalizedRequested = this.normalizeAccountId(requestedAccountId);

    try {
      const payload = await this.paperTradingService.listAccounts(user.id);
      const accountIds = this.extractAccountIds(payload);

      if (normalizedRequested) {
        if (!accountIds.includes(normalizedRequested)) {
          this.rejectSubscription(client, 'forbidden_account', '无权订阅该账户');
          return null;
        }
        return normalizedRequested;
      }

      if (accountIds.length > 0) {
        return accountIds[0];
      }

      const summary = await this.paperTradingService.summary(user.id);
      const fallbackAccountId = this.normalizeAccountId(
        (summary as Record<string, unknown> | null)?.account_id,
      );
      if (fallbackAccountId) {
        return fallbackAccountId;
      }
    } catch (error) {
      this.logger.warn(`account auth failed for ${client.id}: ${String(error)}`);
      this.rejectSubscription(client, 'account_auth_failed', '账户订阅鉴权失败');
      return null;
    }

    this.rejectSubscription(client, 'account_not_found', '未找到可订阅账户');
    return null;
  }

  private extractAccountIds(payload: unknown): string[] {
    const rows = Array.isArray((payload as { accounts?: unknown[] } | null)?.accounts)
      ? (payload as { accounts: unknown[] }).accounts
      : [];

    return rows
      .map((item) => {
        if (!item || typeof item !== 'object') return '';
        const row = item as Record<string, unknown>;
        return this.normalizeAccountId(row.id ?? row.account_id) ?? '';
      })
      .filter(Boolean);
  }

  private normalizeAccountId(value: unknown): string | undefined {
    const text = String(value ?? '').trim();
    if (!text || text === 'default') return undefined;
    return text;
  }

  private rejectSubscription(client: Socket, code: string, message: string) {
    client.emit('ws:error', {
      code,
      message,
      ts: new Date().toISOString(),
    });
  }

  /** 获取当前连接统计信息 */
  getStats() {
    return {
      rooms: this.rooms.size,
      clients: new Set([...this.rooms.values()].flatMap((s) => [...s])).size,
      roomDetails: Object.fromEntries(
        [...this.rooms.entries()].map(([room, clients]) => [room, clients.size]),
      ),
    };
  }
}
