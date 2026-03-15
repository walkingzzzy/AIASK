/**
 * T-014: Notification Bridge
 * Subscribes to WsGateway push events and persists them as notifications.
 */
import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { WsGateway } from '../ws/ws.gateway';
import { NotificationLevel, NotificationService, NotificationType } from './notification.service';

@Injectable()
export class NotificationBridgeService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(NotificationBridgeService.name);
  private stopAlertBridge?: () => void;
  private stopTradeBridge?: () => void;

  constructor(
    private readonly wsGateway: WsGateway,
    private readonly notificationService: NotificationService,
  ) {}

  onModuleInit() {
    this.hookAlerts();
    this.hookTrades();
  }

  onModuleDestroy() {
    this.stopAlertBridge?.();
    this.stopTradeBridge?.();
    this.stopAlertBridge = undefined;
    this.stopTradeBridge = undefined;
  }

  /** Create a notification and push WS system message */
  async createAndPush(input: {
    userId: string;
    type: NotificationType;
    level: NotificationLevel;
    title: string;
    body: string;
    source?: string;
    meta?: Record<string, unknown>;
  }) {
    const notification = await this.notificationService.create(input);
    this.wsGateway.pushSystemMessage(`新通知: ${input.title}`, input.level);
    return notification;
  }

  /** Alert push -> alert notification */
  private hookAlerts() {
    this.stopAlertBridge?.();
    this.stopAlertBridge = this.wsGateway.onAlertPushed(async ({ userId, data }) => {
      if (!userId) return;
      await this.notificationService.create({
        userId,
        type: 'alert',
        level: (data.level as NotificationLevel) || 'warn',
        title: `告警: ${String(data.code ?? '')} ${String(data.indicator ?? '')}`.trim(),
        body: String(data.message ?? `${data.indicator} ${data.condition} ${data.value}`),
        source: 'alert-engine',
        meta: data,
      });
    });
  }

  /** Trade updates -> trade notification */
  private hookTrades() {
    this.stopTradeBridge?.();
    this.stopTradeBridge = this.wsGateway.onTradeUpdatePushed(async ({ data }) => {
      const status = String(data.status ?? '');
      if (!['filled', 'partial', 'rejected'].includes(status)) return;

      const userId = String(data.user_id ?? data.userId ?? '').trim();
      if (!userId) {
        this.logger.warn(`skip trade notification without user_id, status=${status}`);
        return;
      }

      await this.notificationService.create({
        userId,
        type: 'trade',
        level: status === 'rejected' ? 'error' : 'info',
        title: `交易${status === 'filled' ? '成交' : status === 'partial' ? '部分成交' : '拒单'}`,
        body: `${data.code ?? ''} ${data.direction ?? ''} ${data.quantity ?? ''} 股`,
        source: 'paper-trading',
        meta: data,
      });
    });
  }
}
