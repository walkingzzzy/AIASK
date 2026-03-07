import { Injectable } from '@nestjs/common';
import { CommonCacheService } from '../common/cache.service';

export type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';
export type NotificationLevel = 'info' | 'warn' | 'error';

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
}

@Injectable()
export class NotificationService {
    private static readonly CACHE_KEY_PREFIX = 'notifications';
    private static readonly MAX_ITEMS = 200;

    constructor(private readonly cacheService: CommonCacheService) { }

    /** 创建通知 */
    async create(input: Omit<Notification, 'id' | 'read' | 'createdAt'>): Promise<Notification> {
        const notification: Notification = {
            id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            ...input,
            read: false,
            createdAt: new Date().toISOString(),
        };

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
}
