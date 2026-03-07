import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

@Injectable()
export class ScreenerService {
    private static readonly SCREENER_TTL_SECONDS = 300; // 5 mins cache for dynamic screens

    constructor(
        private readonly mcp: McpGatewayService,
        private readonly cacheService: CommonCacheService,
    ) { }

    async semanticSearch(query: string, limit = 20) {
        const cacheKey = `screener:semantic:${query}:${limit}`;
        const ttlSeconds = this.cacheService.resolveTtl('screener.semantic', ScreenerService.SCREENER_TTL_SECONDS);

        const cached = await this.cacheService.getWithMeta(cacheKey);
        if (cached.value) {
            return {
                ...cached.value as Record<string, unknown>,
                meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } }
            };
        }

        try {
            const payload = await this.mcp.callTool('semantic_stock_search', { query, k: limit });
            const result = {
                data: payload,
                meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } }
            };
            await this.cacheService.set(cacheKey, result, ttlSeconds);
            return result;
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP semantic_stock_search 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    async conditionScreen(conditions: string[], limit = 50) {
        try {
            const payload = await this.mcp.callTool('screener_manager', {
                action: 'screen',
                kwargs: JSON.stringify({ conditions, limit })
            });
            return { data: payload };
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP screener_manager (screen) 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    async similarStocks(symbol: string, limit = 10) {
        try {
            const payload = await this.mcp.callTool('search_similar_stocks', { symbol, limit });
            return { data: payload };
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP search_similar_stocks 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }
}
