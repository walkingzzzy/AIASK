/**
 * T-014: Notification Bridge
 * Hooks into WsGateway push methods to persist events as notifications.
 */
import { Injectable, OnModuleInit } from '@nestjs/common';
import { WsGateway } from '../ws/ws.gateway';
import { NotificationService, NotificationType, NotificationLevel } from './notification.service';

@Injectable()
export class NotificationBridgeService implements OnModuleInit {
    constructor(
        private readonly wsGateway: WsGateway,
        private readonly notificationService: NotificationService,
    ) { }

    onModuleInit() {
        this.hookAlerts();
        this.hookTrades();
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

    /** Hook: alert triggers → alert notification */
    private hookAlerts() {
        const origPush = this.wsGateway.pushAlert.bind(this.wsGateway);
        this.wsGateway.pushAlert = (userId: string, data: Record<string, unknown>) => {
            origPush(userId, data);
            if (!userId) return;
            this.notificationService.create({
                userId,
                type: 'alert',
                level: (data.level as NotificationLevel) || 'warn',
                title: `告警: ${String(data.code ?? '')} ${String(data.indicator ?? '')}`,
                body: String(data.message ?? `${data.indicator} ${data.condition} ${data.value}`),
                source: 'alert-engine',
                meta: data,
            }).catch(() => { /* fire-and-forget */ });
        };
    }

    /** Hook: trade updates → trade notification */
    private hookTrades() {
        const origPush = this.wsGateway.pushTradeUpdate.bind(this.wsGateway);
        this.wsGateway.pushTradeUpdate = (accountId: string, data: Record<string, unknown>) => {
            origPush(accountId, data);
            const status = String(data.status ?? '');
            const userId = String(data.user_id ?? data.userId ?? '');
            if (['filled', 'partial', 'rejected'].includes(status)) {
                if (!userId) return;
                this.notificationService.create({
                    userId,
                    type: 'trade',
                    level: status === 'rejected' ? 'error' : 'info',
                    title: `交易${status === 'filled' ? '成交' : status === 'partial' ? '部分成交' : '拒单'}`,
                    body: `${data.code ?? ''} ${data.direction ?? ''} ${data.quantity ?? ''} 股`,
                    source: 'paper-trading',
                    meta: data,
                }).catch(() => { /* fire-and-forget */ });
            }
        };
    }
}
