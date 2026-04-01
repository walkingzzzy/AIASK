import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

type OptionGreeksInput = {
  optionType?: 'call' | 'put';
  strike?: string;
  spot?: string;
  volatility?: string;
  riskFreeRate?: string;
  timeToMaturity?: string;
  dividendYield?: string;
  expiryDate?: string;
};

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
    if (cached.value && !this.hasToolError(cached.value)) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: this.buildMeta('', true, cached.meta.backend, cacheKey, ttlSeconds),
      };
    }
    if (cached.value) await this.cacheService.del(cacheKey);

    try {
      const payload = await this.mcp.callTool('get_option_chain', { underlying: symbol });
      if (this.hasToolError(payload)) {
        throw new Error(this.extractToolError(payload) ?? 'get_option_chain 返回异常');
      }
      const result = {
        ...this.unwrapToolRecord(payload),
        sourceTool: 'get_option_chain' as const,
        meta: this.buildMeta(new Date().toISOString(), false, 'none', cacheKey, ttlSeconds),
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

  async getOptionGreeks(symbol: string, input: OptionGreeksInput = {}) {
    const normalizedInput = {
      optionType: input.optionType === 'put' ? 'put' : 'call',
      strike: input.strike?.trim() || '',
      spot: input.spot?.trim() || '',
      volatility: input.volatility?.trim() || '',
      riskFreeRate: input.riskFreeRate?.trim() || '',
      timeToMaturity: input.timeToMaturity?.trim() || '',
      dividendYield: input.dividendYield?.trim() || '',
      expiryDate: input.expiryDate?.trim() || '',
    };
    const cacheKey = `options:greeks:${symbol}:${JSON.stringify(normalizedInput)}`;
    const ttlSeconds = this.cacheService.resolveTtl('options.greeks', OptionsService.OPTIONS_TTL_SECONDS);
    
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value && !this.hasToolError(cached.value)) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: this.buildMeta('', true, cached.meta.backend, cacheKey, ttlSeconds),
      };
    }
    if (cached.value) await this.cacheService.del(cacheKey);

    try {
      const payload = await this.callManager('calculate_greeks', {
        code: symbol,
        option_type: normalizedInput.optionType,
        ...(normalizedInput.strike ? { strike: Number(normalizedInput.strike) } : {}),
        ...(normalizedInput.spot ? { spot: Number(normalizedInput.spot) } : {}),
        ...(normalizedInput.volatility ? { volatility: Number(normalizedInput.volatility) } : {}),
        ...(normalizedInput.riskFreeRate ? { risk_free_rate: Number(normalizedInput.riskFreeRate) } : {}),
        ...(normalizedInput.timeToMaturity ? { time_to_maturity: Number(normalizedInput.timeToMaturity) } : {}),
        ...(normalizedInput.dividendYield ? { dividend_yield: Number(normalizedInput.dividendYield) } : {}),
        ...(normalizedInput.expiryDate ? { expiry_date: normalizedInput.expiryDate } : {}),
      });
      if (this.hasToolError(payload)) {
        throw new Error(this.extractToolError(payload) ?? 'calculate_greeks 返回异常');
      }
      const result = {
        ...this.unwrapToolRecord(payload),
        sourceTool: 'options_manager.calculate_greeks' as const,
        meta: this.buildMeta(new Date().toISOString(), false, 'none', cacheKey, ttlSeconds),
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
    const cacheKey = `options:smirk:${symbol}`;
    const ttlSeconds = this.cacheService.resolveTtl('options.smirk', OptionsService.OPTIONS_TTL_SECONDS);

    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value && !this.hasToolError(cached.value)) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: this.buildMeta('', true, cached.meta.backend, cacheKey, ttlSeconds),
      };
    }
    if (cached.value) await this.cacheService.del(cacheKey);

    try {
      const payload = await this.callManager('volatility_smirk', {
        underlying: symbol,
      });
      if (this.hasToolError(payload)) {
        throw new Error(this.extractToolError(payload) ?? 'volatility_smirk 返回异常');
      }
      const result = {
        ...this.unwrapToolRecord(payload),
        sourceTool: 'options_manager.volatility_smirk' as const,
        meta: this.buildMeta(new Date().toISOString(), false, 'none', cacheKey, ttlSeconds),
      };
      await this.cacheService.set(cacheKey, result, ttlSeconds);
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP options_manager (volatility_smirk) 失败',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private hasToolError(payload: unknown): boolean {
    return this.extractToolError(payload) != null;
  }

  private async callManager(action: string, payload: Record<string, unknown>) {
    return this.mcp.callTool('options_manager', {
      action,
      kwargs: JSON.stringify(payload),
    });
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      return /error executing tool|validation error/i.test(payload) ? payload : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.data && typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    if (record.success === false) {
      return String(record.error ?? record.message ?? 'options tool error');
    }
    return null;
  }

  private unwrapToolRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return { value: payload };
    }

    const record = payload as Record<string, unknown>;
    const data = record.data;
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      return data as Record<string, unknown>;
    }
    return record;
  }

  private buildMeta(
    fetchedAt: string,
    hit: boolean,
    backend: 'redis' | 'memory' | 'none',
    key: string,
    ttlSeconds: number,
  ) {
    return {
      fetchedAt,
      cache: { hit, backend, key, ttlSeconds },
    };
  }
}
