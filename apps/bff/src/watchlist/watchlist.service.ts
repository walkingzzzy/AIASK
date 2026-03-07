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
            kwargs: JSON.stringify({ user_id: userId }),
        });

        const groups = this.extractGroups(payload);
        await this.cacheService.set(cacheKey, groups, WatchlistService.CACHE_TTL);
        return groups;
    }

    async createGroup(userId: string, name: string, color = '#6366f1') {
        const payload = await this.callTool('create_watchlist', {
            name,
            user_id: userId,
            color,
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async addStocks(userId: string, group: string, codes: string[]) {
        const payload = await this.callTool('add_stocks_to_watchlist', {
            watchlist_name: group,
            user_id: userId,
            codes: codes.join(','),
        });

        await this.invalidateCache(userId);
        return { success: true, addedCount: codes.length, result: payload };
    }

    async removeStock(userId: string, group: string, code: string) {
        // Use watchlist_manager with remove action
        const payload = await this.callTool('watchlist_manager', {
            action: 'remove_stock',
            kwargs: JSON.stringify({ user_id: userId, watchlist_name: group, code }),
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async deleteGroup(userId: string, name: string) {
        const payload = await this.callTool('delete_watchlist', {
            name,
            user_id: userId,
        });

        await this.invalidateCache(userId);
        return { success: true, result: payload };
    }

    async reorderStocks(userId: string, group: string, codes: string[]) {
        const payload = await this.callTool('watchlist_manager', {
            action: 'reorder',
            kwargs: JSON.stringify({ user_id: userId, watchlist_name: group, codes }),
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

    private extractGroups(payload: any): WatchlistGroup[] {
        const data = this.readPath(payload, 'data') ?? payload;
        if (Array.isArray(data)) {
            return data.map((g: any) => this.normalizeGroup(g));
        }
        // Single group or items
        const items = this.readPath(data, 'items') ?? this.readPath(data, 'stocks') ?? [];
        if (Array.isArray(items)) {
            return [{
                id: 'default',
                name: '我的自选',
                color: '#6366f1',
                items: items.map((item: any) => this.normalizeItem(item)),
                createdAt: new Date().toISOString(),
            }];
        }
        return [];
    }

    private normalizeGroup(raw: any): WatchlistGroup {
        return {
            id: String(raw.id ?? raw.name ?? 'default'),
            name: String(raw.name ?? raw.watchlist_name ?? '我的自选'),
            color: String(raw.color ?? '#6366f1'),
            items: Array.isArray(raw.items ?? raw.stocks)
                ? (raw.items ?? raw.stocks).map((i: any) => this.normalizeItem(i))
                : [],
            createdAt: String(raw.createdAt ?? raw.created_at ?? new Date().toISOString()),
        };
    }

    private normalizeItem(raw: any): WatchlistItem {
        return {
            code: String(raw.code ?? raw.stock_code ?? ''),
            name: String(raw.name ?? raw.stock_name ?? ''),
            group: String(raw.group ?? raw.watchlist_name ?? 'default'),
            addedAt: String(raw.addedAt ?? raw.added_at ?? new Date().toISOString()),
            sortOrder: Number(raw.sortOrder ?? raw.sort_order ?? 0),
        };
    }

    private readPath(obj: any, path: string): unknown {
        return path.split('.').reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), obj);
    }
}
