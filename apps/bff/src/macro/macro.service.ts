import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

@Injectable()
export class MacroService {
    private static readonly MACRO_TTL_SECONDS = 3600 * 24; // 1 day cache for macro data

    constructor(
        private readonly mcp: McpGatewayService,
        private readonly cacheService: CommonCacheService,
    ) { }

    async getMacroIndicator(indicator: string) {
        const cacheKey = `macro:indicator:${indicator}`;
        const ttlSeconds = this.cacheService.resolveTtl('macro.indicator', MacroService.MACRO_TTL_SECONDS);

        const cached = await this.cacheService.getWithMeta(cacheKey);
        if (cached.value) {
            return {
                ...cached.value as Record<string, unknown>,
                meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } }
            };
        }

        try {
            const payload = await this.mcp.callTool('get_macro_indicator', { indicator });
            const result = {
                data: this.normalizeToolPayload(payload),
                meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } }
            };
            await this.cacheService.set(cacheKey, result, ttlSeconds);
            return result;
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: '调用 MCP get_macro_indicator 失败',
                detail: error instanceof Error ? error.message : String(error),
            });
        }
    }

    private normalizeToolPayload(payload: unknown): unknown {
        if (!this.isRecord(payload)) {
            return payload;
        }

        if (!Object.prototype.hasOwnProperty.call(payload, 'data')) {
            return payload;
        }

        const data = payload.data;
        const toolMeta = this.isRecord(payload.meta) ? payload.meta : null;
        if (this.isRecord(data)) {
            return toolMeta ? { ...data, meta: toolMeta } : data;
        }

        return data;
    }

    private isRecord(value: unknown): value is Record<string, unknown> {
        return !!value && typeof value === 'object' && !Array.isArray(value);
    }
}
