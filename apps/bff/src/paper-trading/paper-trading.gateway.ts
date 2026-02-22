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

function roomOf(userId: string, accountId?: string): string {
  return `paper:${userId}:${accountId || 'default'}`;
}

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

  constructor(private readonly svc: PaperTradingService) {}

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
    const userId = String(
      client.handshake.auth?.user_id || client.handshake.query?.user_id || 'default',
    );
    const accountIdRaw = client.handshake.auth?.account_id || client.handshake.query?.account_id;
    const accountId = accountIdRaw ? String(accountIdRaw) : undefined;
    const room = roomOf(userId, accountId);

    await client.join(room);
    this.roomCtx.set(room, { userId, accountId });

    this.logger.debug(`client connected: ${client.id}, room=${room}`);

    const snapshot = await this.svc.realtimeSnapshot(userId, accountId);
    client.emit('paper.snapshot', snapshot);
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
}

