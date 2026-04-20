import { Injectable, Logger, Optional } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PreferencesService } from '../auth/preferences.service';
import { CommonCacheService } from '../common/cache.service';

export type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';
export type NotificationLevel = 'info' | 'warn' | 'error';
export type NotificationDeliveryState = 'delivered' | 'failed' | 'disabled';

export interface NotificationDelivery {
    inApp: { status: 'delivered'; deliveredAt: string };
    webhook?: {
        status: NotificationDeliveryState;
        deliveredAt?: string;
        target?: string;
        source?: 'env' | 'user_preferences' | 'none';
        error?: string;
    };
}

export interface Notification {
    id: string;
    userId: string;
    type: NotificationType;
    level: NotificationLevel;
    title: string;
    body: string;
    source?: string;
    meta?: Record<string, unknown>;
    read: boolean;
    createdAt: string;
    delivery?: NotificationDelivery;
}

export type NotificationDeliveryStatus = {
    configured: boolean;
    source: 'env' | 'user_preferences' | 'none';
    attempted: number;
    delivered: number;
    failed: number;
    lastError: string | null;
    lastDeliveredAt: string | null;
    target: string | null;
};

@Injectable()
export class NotificationService {
    private static readonly CACHE_KEY_PREFIX = 'notifications';
    private static readonly MAX_ITEMS = 200;
    private static readonly WEBHOOK_TIMEOUT_MS = 4_000;
    private readonly logger = new Logger(NotificationService.name);
    private readonly deliveryStatus: NotificationDeliveryStatus = {
        configured: false,
        source: 'none',
        attempted: 0,
        delivered: 0,
        failed: 0,
        lastError: null,
        lastDeliveredAt: null,
        target: null,
    };

    constructor(
        private readonly cacheService: CommonCacheService,
        private readonly configService: ConfigService,
        @Optional() private readonly preferencesService?: PreferencesService,
    ) { }

    /** 创建通知 */
    async create(input: Omit<Notification, 'id' | 'read' | 'createdAt'>): Promise<Notification> {
        const createdAt = new Date().toISOString();
        const notification: Notification = {
            id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            ...input,
            read: false,
            createdAt,
            delivery: {
                inApp: { status: 'delivered', deliveredAt: createdAt },
            },
        };
        notification.delivery = await this.enrichDelivery(input.userId, notification);

        const items = await this.getAll(input.userId);
        items.unshift(notification);
        // Keep only the latest MAX_ITEMS
        const trimmed = items.slice(0, NotificationService.MAX_ITEMS);
        await this.cacheService.set(this.cacheKey(input.userId), trimmed, 86400 * 7); // 7 days
        return notification;
    }

    /** 列表查询 */
    async list(userId: string, options: {
        type?: NotificationType;
        read?: boolean;
        limit?: number;
        offset?: number;
    } = {}): Promise<{ items: Notification[]; total: number; unread: number }> {
        let items = await this.getAll(userId);
        const unread = items.filter((n) => !n.read).length;

        if (options.type) items = items.filter((n) => n.type === options.type);
        if (options.read !== undefined) items = items.filter((n) => n.read === options.read);

        const total = items.length;
        const offset = options.offset ?? 0;
        const limit = options.limit ?? 50;
        const paged = items.slice(offset, offset + limit);

        return { items: paged, total, unread };
    }

    /** 未读数 */
    async countUnread(userId: string): Promise<number> {
        const items = await this.getAll(userId);
        return items.filter((n) => !n.read).length;
    }

    /** 标记已读 */
    async markRead(userId: string, ids: string[]): Promise<number> {
        const items = await this.getAll(userId);
        let count = 0;
        for (const item of items) {
            if (ids.includes(item.id) && !item.read) {
                item.read = true;
                count++;
            }
        }
        await this.cacheService.set(this.cacheKey(userId), items, 86400 * 7);
        return count;
    }

    /** 全部已读 */
    async markAllRead(userId: string): Promise<number> {
        const items = await this.getAll(userId);
        let count = 0;
        for (const item of items) {
            if (!item.read) {
                item.read = true;
                count++;
            }
        }
        await this.cacheService.set(this.cacheKey(userId), items, 86400 * 7);
        return count;
    }

    /** 删除 */
    async remove(userId: string, ids: string[]): Promise<number> {
        const items = await this.getAll(userId);
        const filtered = items.filter((n) => !ids.includes(n.id));
        const removed = items.length - filtered.length;
        await this.cacheService.set(this.cacheKey(userId), filtered, 86400 * 7);
        return removed;
    }

    private async getAll(userId: string): Promise<Notification[]> {
        const cached = await this.cacheService.getWithMeta<Notification[]>(this.cacheKey(userId));
        return cached.value ?? [];
    }

    private cacheKey(userId: string): string {
        return `${NotificationService.CACHE_KEY_PREFIX}:${userId}`;
    }

    getDeliveryStatus(): NotificationDeliveryStatus {
        return { ...this.deliveryStatus };
    }

    private async enrichDelivery(userId: string, notification: Notification): Promise<NotificationDelivery> {
        const delivery: NotificationDelivery = {
            inApp: { status: 'delivered', deliveredAt: notification.createdAt },
        };
        const webhook = await this.resolveWebhookConfig(userId);
        this.deliveryStatus.configured = Boolean(webhook.url);
        this.deliveryStatus.source = webhook.source;
        this.deliveryStatus.target = webhook.url;

        if (!webhook.url) {
            delivery.webhook = { status: 'disabled', source: webhook.source };
            return delivery;
        }

        this.deliveryStatus.attempted += 1;
        try {
            await this.postWebhook(webhook.url, {
                event: 'notification.created',
                notification,
            });
            this.deliveryStatus.delivered += 1;
            this.deliveryStatus.lastError = null;
            this.deliveryStatus.lastDeliveredAt = new Date().toISOString();
            delivery.webhook = {
                status: 'delivered',
                deliveredAt: this.deliveryStatus.lastDeliveredAt,
                target: webhook.url,
                source: webhook.source,
            };
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this.deliveryStatus.failed += 1;
            this.deliveryStatus.lastError = message;
            this.logger.warn(`通知 webhook 交付失败，已保留站内通知: ${message}`);
            delivery.webhook = {
                status: 'failed',
                target: webhook.url,
                source: webhook.source,
                error: message,
            };
        }

        return delivery;
    }

    private async resolveWebhookConfig(userId: string): Promise<{ url: string | null; source: 'env' | 'user_preferences' | 'none' }> {
        const envUrl = this.configService.get<string>('NOTIFICATION_WEBHOOK_URL', '').trim();
        if (envUrl) {
            return { url: envUrl, source: 'env' };
        }
        if (!this.preferencesService) {
            return { url: null, source: 'none' };
        }
        try {
            const preferences = await this.preferencesService.getUserPreferences(userId);
            const channels = preferences.notificationChannels;
            if (channels && typeof channels === 'object') {
                const webhook = (channels as { webhook?: { url?: unknown } }).webhook;
                const url = typeof webhook?.url === 'string' ? webhook.url.trim() : '';
                if (url) {
                    return { url, source: 'user_preferences' };
                }
            }
        } catch {
            return { url: null, source: 'none' };
        }
        return { url: null, source: 'none' };
    }

    private async postWebhook(url: string, payload: Record<string, unknown>): Promise<void> {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), NotificationService.WEBHOOK_TIMEOUT_MS);
        try {
            const headers: Record<string, string> = {
                'content-type': 'application/json',
                'x-aiask-event': 'notification.created',
            };
            const token = this.configService.get<string>('NOTIFICATION_WEBHOOK_TOKEN', '').trim();
            if (token) {
                headers.authorization = `Bearer ${token}`;
            }
            const response = await fetch(url, {
                method: 'POST',
                headers,
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            if (!response.ok) {
                throw new Error(`webhook_status_${response.status}`);
            }
        } finally {
            clearTimeout(timer);
        }
    }
}
