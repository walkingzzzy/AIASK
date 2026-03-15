import {
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { PaperTradingService } from './paper-trading.service';
import { AuthService } from '../auth/auth.service';

function roomOf(userId: string, accountId?: string): string {
  return `paper:${userId}:${accountId || 'default'}`;
}

type WsUser = { id: string; username?: string; role?: string; jti?: string };

@WebSocketGateway({
  namespace: '/paper-trading',
  cors: { origin: true, credentials: true },
})
export class PaperTradingGateway
  implements OnGatewayConnection, OnGatewayDisconnect, OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(PaperTradingGateway.name);
  private readonly roomCtx = new Map<string, { userId: string; accountId?: string }>();
  private timer: NodeJS.Timeout | null = null;

  @WebSocketServer()
  server!: Server;

  constructor(
    private readonly svc: PaperTradingService,
    private readonly authService: AuthService,
  ) {}

  onModuleInit() {
    this.timer = setInterval(() => {
      void this.pushSnapshots();
    }, 3000);
  }

  onModuleDestroy() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async handleConnection(client: Socket) {
    const user = await this.authenticateClient(client);
    if (!user) {
      this.rejectClient(client, 'unauthorized', '模拟交易实时通道需要登录');
      return;
    }

    const accountId = await this.resolveAuthorizedAccountId(
      user.id,
      client.handshake.auth?.account_id ?? client.handshake.query?.account_id,
    );
    if (!accountId) {
      this.rejectClient(client, 'forbidden_account', '无权访问该模拟交易账户');
      return;
    }

    const userId = user.id;
    const room = roomOf(userId, accountId);

    await client.join(room);
    this.roomCtx.set(room, { userId, accountId });

    this.logger.debug(`client connected: ${client.id}, room=${room}`);

    try {
      const snapshot = await this.svc.realtimeSnapshot(userId, accountId);
      client.emit('paper.snapshot', snapshot);
    } catch (error) {
      this.logger.warn(`paper snapshot bootstrap failed for ${client.id}: ${String(error)}`);
      this.rejectClient(client, 'snapshot_bootstrap_failed', '初始化模拟盘快照失败');
    }
  }

  handleDisconnect(client: Socket) {
    for (const room of client.rooms) {
      if (!room.startsWith('paper:')) continue;
      const size = this.server.sockets.adapter.rooms.get(room)?.size || 0;
      if (size <= 1) this.roomCtx.delete(room);
    }
    this.logger.debug(`client disconnected: ${client.id}`);
  }

  private async pushSnapshots() {
    if (!this.server || this.roomCtx.size === 0) return;

    for (const [room, ctx] of this.roomCtx.entries()) {
      try {
        const snapshot = await this.svc.realtimeSnapshot(ctx.userId, ctx.accountId);
        this.server.to(room).emit('paper.snapshot', snapshot);
      } catch (e) {
        this.server.to(room).emit('paper.snapshot.error', {
          message: String(e),
          ts: new Date().toISOString(),
        });
      }
    }
  }

  private async authenticateClient(client: Socket): Promise<WsUser | null> {
    const token = this.extractAccessToken(client);
    if (!token) return null;

    try {
      return await this.authService.verifyAccessToken(token);
    } catch (error) {
      this.logger.debug(`paper trading ws auth failed for ${client.id}: ${String(error)}`);
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

  private async resolveAuthorizedAccountId(userId: string, requestedAccountId?: unknown): Promise<string | undefined> {
    const normalizedRequested = this.normalizeAccountId(requestedAccountId);

    const payload = await this.svc.listAccounts(userId);
    const accountIds = this.extractAccountIds(payload);

    if (normalizedRequested) {
      return accountIds.includes(normalizedRequested) ? normalizedRequested : undefined;
    }

    if (accountIds.length > 0) {
      return accountIds[0];
    }

    const summary = await this.svc.summary(userId);
    return this.normalizeAccountId((summary as Record<string, unknown> | null)?.account_id);
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

  private rejectClient(client: Socket, code: string, message: string) {
    client.emit('paper.snapshot.error', {
      code,
      message,
      ts: new Date().toISOString(),
    });
    client.disconnect(true);
  }
}
