import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

@Injectable()
export class OptionsService {
  private static readonly OPTIONS_TTL_SECONDS = 300; // 5 mins cache for options

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getOptionChain(symbol: string) {
    const cacheKey = `options:chain:${symbol}`;
    const ttlSeconds = this.cacheService.resolveTtl('options.chain', OptionsService.OPTIONS_TTL_SECONDS);
    
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { 
        ...cached.value as Record<string, unknown>, 
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } 
      };
    }

    try {
      const payload = await this.mcp.callTool('get_option_chain', { symbol });
      const result = { 
        data: payload, 
        meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } 
      };
      await this.cacheService.set(cacheKey, result, ttlSeconds);
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP get_option_chain 失败',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async getOptionGreeks(symbol: string) {
    const cacheKey = `options:greeks:${symbol}`;
    const ttlSeconds = this.cacheService.resolveTtl('options.greeks', OptionsService.OPTIONS_TTL_SECONDS);
    
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { 
        ...cached.value as Record<string, unknown>, 
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } 
      };
    }

    try {
      const payload = await this.mcp.callTool('options_manager', {
        action: 'calculate_greeks',
        kwargs: JSON.stringify({ underlying_symbol: symbol }),
      });
      const result = { 
        data: payload, 
        meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } 
      };
      await this.cacheService.set(cacheKey, result, ttlSeconds);
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP options_manager (calculate_greeks) 失败',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async getVolatilitySmirk(symbol: string) {
    try {
      const payload = await this.mcp.callTool('options_manager', {
        action: 'volatility_smirk',
        kwargs: JSON.stringify({ underlying_symbol: symbol })
      });
      return { data: payload };
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP options_manager (volatility_smirk) 失败',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }
}
