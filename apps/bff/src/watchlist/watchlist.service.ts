import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type WatchlistItem = {
    code: string;
    name: string;
    group: string;
    addedAt: string;
    sortOrder: number;
};

export type WatchlistGroup = {
    id: string;
    name: string;
    color: string;
    items: WatchlistItem[];
    createdAt: string;
};

@Injectable()
export class WatchlistService {
    private static readonly CACHE_TTL = 60;

    constructor(
        private readonly mcpGatewayService: McpGatewayService,
        private readonly cacheService: CommonCacheService,
    ) { }

    async listGroups(userId: string): Promise<WatchlistGroup[]> {
        const cacheKey = `watchlist:${userId}:groups`;
        const cached = await this.cacheService.getWithMeta<WatchlistGroup[]>(cacheKey);
        if (cached.value) return cached.value;

        const payload = await this.callTool('watchlist_manager', {
            action: 'list',
            params: { user_id: userId },
        });

        const groups = this.extractGroups(payload);
        await this.cacheService.set(cacheKey, groups, WatchlistService.CACHE_TTL);
        return groups;
    }

    async createGroup(userId: string, groupId: string | undefined, name: string, color = '#6366f1') {
        const payload = await this.callTool('watchlist_manager', {
            action: 'create_group',
            params: {
                user_id: userId,
                group_id: groupId,
                name,
                color,
            },
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async addStocks(userId: string, group: string, codes: string[], groupName?: string) {
        const payload = await this.callTool('watchlist_manager', {
            action: 'add_stocks',
            params: {
                user_id: userId,
                group_id: group,
                group_name: groupName,
                codes,
            },
        });

        await this.invalidateCache(userId);
        return { success: true, addedCount: codes.length, result: payload };
    }

    async removeStock(userId: string, group: string, code: string) {
        const payload = await this.callTool('watchlist_manager', {
            action: 'remove_stock',
            params: { user_id: userId, group_id: group, code },
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async deleteGroup(userId: string, groupId?: string, name?: string) {
        const payload = await this.callTool('watchlist_manager', {
            action: 'delete_group',
            params: {
                user_id: userId,
                group_id: groupId,
                name,
            },
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async reorderStocks(userId: string, group: string, codes: string[]) {
        const payload = await this.callTool('watchlist_manager', {
            action: 'reorder',
            params: { user_id: userId, group_id: group, codes },
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    private async invalidateCache(userId: string) {
        await this.cacheService.del(`watchlist:${userId}:groups`);
    }

    private async callTool(name: string, args: Record<string, unknown>) {
        try {
            return await this.mcpGatewayService.callTool(name, args);
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: `调用 MCP ${name} 失败`,
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    private extractGroups(payload: unknown): WatchlistGroup[] {
        const data = this.readPath(payload, 'data') ?? payload;
        const groupsPayload = this.readPath(data, 'groups');
        if (Array.isArray(groupsPayload)) {
            return groupsPayload.map((group) => this.normalizeGroup(group));
        }
        if (Array.isArray(data)) {
            return data.map((group) => this.normalizeGroup(group));
        }
        // Single group or items
        const items = this.readPath(data, 'items') ?? this.readPath(data, 'stocks') ?? [];
        if (Array.isArray(items)) {
            return [{
                id: 'default',
                name: '我的自选',
                color: '#6366f1',
                items: items.map((item) => this.normalizeItem(item)),
                createdAt: new Date().toISOString(),
            }];
        }
        return [];
    }

    private normalizeGroup(raw: unknown): WatchlistGroup {
        const record = this.asRecord(raw);
        const items = record.items ?? record.stocks;
        return {
            id: String(record.id ?? record.name ?? 'default'),
            name: String(record.name ?? record.watchlist_name ?? '我的自选'),
            color: String(record.color ?? '#6366f1'),
            items: Array.isArray(items)
                ? items.map((item) => this.normalizeItem(item))
                : [],
            createdAt: String(record.createdAt ?? record.created_at ?? new Date().toISOString()),
        };
    }

    private normalizeItem(raw: unknown): WatchlistItem {
        const record = this.asRecord(raw);
        return {
            code: String(record.code ?? record.stock_code ?? ''),
            name: String(record.name ?? record.stock_name ?? ''),
            group: String(record.group ?? record.group_id ?? record.watchlist_name ?? 'default'),
            addedAt: String(record.addedAt ?? record.added_at ?? new Date().toISOString()),
            sortOrder: Number(record.sortOrder ?? record.sort_order ?? 0),
        };
    }

    private asRecord(value: unknown): Record<string, unknown> {
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            return {};
        }
        return value as Record<string, unknown>;
    }

    private readPath(obj: unknown, path: string): unknown {
        return path.split('.').reduce<unknown>((acc, key) => {
            if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
                return undefined;
            }
            return (acc as Record<string, unknown>)[key];
        }, obj);
    }
}
