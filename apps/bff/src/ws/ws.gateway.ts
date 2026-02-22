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
 * 通用 WebSocket 网关 — 策略 NAV 推送、组合更新推送。
 * 与 paper-trading.gateway.ts（/paper-trading 命名空间）独立运行。
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
  }

  handleDisconnect(client: Socket) {
    // 清理空房间
    for (const [room, clients] of this.rooms.entries()) {
      clients.delete(client.id);
      if (clients.size === 0) this.rooms.delete(room);
    }
    this.logger.debug(`client disconnected: ${client.id}`);
  }

  // ── 订阅消息 ──────────────────────────────────────────────

  @SubscribeMessage('subscribe:portfolio')
  handlePortfolioSub(client: Socket, payload: { accountId: string }) {
    const room = `portfolio:${payload.accountId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  @SubscribeMessage('subscribe:strategy')
  handleStrategySub(client: Socket, payload: { strategyId: string | number }) {
    const room = `strategy:${payload.strategyId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  @SubscribeMessage('subscribe:watchlist')
  handleWatchlistSub(client: Socket, payload: { userId: string }) {
    const room = `watchlist:${payload.userId}`;
    void client.join(room);
    this._track(room, client.id);
    this.logger.debug(`${client.id} joined ${room}`);
  }

  // ── 服务端主动推送接口（供其他模块调用） ──────────────────

  pushPortfolioUpdate(accountId: string, data: Record<string, unknown>) {
    this.server.to(`portfolio:${accountId}`).emit('portfolio:update', data);
  }

  pushStrategyNav(strategyId: string | number, data: Record<string, unknown>) {
    this.server.to(`strategy:${strategyId}`).emit('strategy:nav', data);
  }

  pushWatchlistUpdate(userId: string, data: Record<string, unknown>) {
    this.server.to(`watchlist:${userId}`).emit('watchlist:update', data);
  }

  // ── 内部辅助 ──────────────────────────────────────────────

  private _track(room: string, clientId: string) {
    if (!this.rooms.has(room)) this.rooms.set(room, new Set());
    this.rooms.get(room)!.add(clientId);
  }
}
