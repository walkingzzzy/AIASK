import {
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';

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
  private heartbeatTimer: NodeJS.Timeout | null = null;

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

  handleConnection(client: Socket) {
    this.logger.debug(`client connected: ${client.id}`);
    // 自动加入 system 频道
    void client.join('system');
  }

  handleDisconnect(client: Socket) {
    // 清理空房间
    for (const [room, clients] of this.rooms.entries()) {
      clients.delete(client.id);
      if (clients.size === 0) this.rooms.delete(room);
    }
    this.logger.debug(`client disconnected: ${client.id}`);
  }

  // ── 行情订阅 ─────────────────────────────────────────────

  @SubscribeMessage('subscribe:quote')
  handleQuoteSub(client: Socket, payload: { codes?: string[]; type?: string }) {
    // type: 'index' | 'stock' | 'batch'
    const roomType = payload.type || 'stock';
    const codes = payload.codes || [];
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
    }
  }

  @SubscribeMessage('unsubscribe:quote')
  handleQuoteUnsub(client: Socket, payload: { codes?: string[]; type?: string }) {
    const roomType = payload.type || 'stock';
    const codes = payload.codes || [];
    if (codes.length === 0) {
      void client.leave('quote:broadcast');
    } else {
      for (const code of codes) {
        void client.leave(`quote:${roomType}:${code}`);
      }
    }
  }

  // ── 告警订阅 ─────────────────────────────────────────────

  @SubscribeMessage('subscribe:alert')
  handleAlertSub(client: Socket, payload: { userId?: string }) {
    const room = payload.userId ? `alert:${payload.userId}` : 'alert:broadcast';
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 交易订单订阅 ──────────────────────────────────────────

  @SubscribeMessage('subscribe:trade')
  handleTradeSub(client: Socket, payload: { accountId: string }) {
    const room = `trade:${payload.accountId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 组合订阅 ──────────────────────────────────────────────

  @SubscribeMessage('subscribe:portfolio')
  handlePortfolioSub(client: Socket, payload: { accountId: string }) {
    const room = `portfolio:${payload.accountId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 策略订阅 ──────────────────────────────────────────────

  @SubscribeMessage('subscribe:strategy')
  handleStrategySub(client: Socket, payload: { strategyId: string | number }) {
    const room = `strategy:${payload.strategyId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 自选股订阅 ────────────────────────────────────────────

  @SubscribeMessage('subscribe:watchlist')
  handleWatchlistSub(client: Socket, payload: { userId: string }) {
    const room = `watchlist:${payload.userId}`;
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
    this.server.to(`trade:${accountId}`).emit('trade:update', {
      ...data,
      ts: new Date().toISOString(),
    });
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

  // ── 内部辅助 ──────────────────────────────────────────────

  private _track(room: string, clientId: string) {
    if (!this.rooms.has(room)) this.rooms.set(room, new Set());
    this.rooms.get(room)!.add(clientId);
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

