import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { buildDataQuality, trustedDataQuality } from '../common/data-quality';

@Injectable()
export class TechnicalService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async calculateIndicators(params: { code: string; indicators: string[]; period?: string; limit?: number }) {
    const sourceTool = 'calculate_technical_indicators' as const;
    const payload = await this.callTool(sourceTool, {
      code: params.code, indicators: params.indicators,
      period: params.period ?? 'daily', limit: params.limit ?? 100,
    });
    const data = this.extractToolData(payload);
    return {
      sourceTool,
      data,
      result: payload,
      data_quality: this.buildTechnicalQuality(sourceTool, data),
    };
  }

  async checkPatterns(params: { code: string; period?: string; limit?: number }) {
    const sourceTool = 'check_candlestick_patterns' as const;
    const payload = await this.callTool(sourceTool, {
      code: params.code, period: params.period ?? 'daily', limit: params.limit ?? 100,
    });
    const data = this.extractToolData(payload);
    return {
      sourceTool,
      data,
      result: payload,
      data_quality: this.buildTechnicalQuality(sourceTool, data),
    };
  }

  async getAvailablePatterns() {
    const sourceTool = 'get_available_patterns' as const;
    let payload: unknown;
    try {
      payload = await this.callTool(sourceTool, {});
    } catch (error) {
      return this.buildUnavailableResult(sourceTool, error);
    }
    const data = this.extractToolData(payload);
    return {
      sourceTool,
      data,
      result: payload,
      data_quality: this.buildTechnicalQuality(sourceTool, data),
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args, { retryOnTransportError: true });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: reason,
        acceptanceStatus: 'degraded',
      });
    }
  }

  private extractToolData(payload: unknown): unknown {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload;
    }
    const record = payload as Record<string, unknown>;
    return Object.prototype.hasOwnProperty.call(record, 'data') ? record.data : payload;
  }

  private buildTechnicalQuality(sourceTool: string, data: unknown) {
    const count = this.sampleCount(data);
    if (count > 0 || this.hasBusinessValue(data)) {
      return trustedDataQuality(sourceTool, count || null);
    }
    return buildDataQuality({
      status: 'empty',
      reasons: [`${sourceTool}_empty_result`],
      emptyReason: `${sourceTool} 返回空结果`,
      sources: [{ name: sourceTool, status: 'empty', sampleCount: 0 }],
    });
  }

  private buildUnavailableResult(sourceTool: string, error: unknown) {
    const reason = this.formatError(error);
    return {
      sourceTool,
      data: null,
      result: {
        success: false,
        degraded: true,
        message: `调用 MCP ${sourceTool} 失败`,
        detail: reason,
      },
      degraded: true,
      fallback_used: true,
      fallback_reason: [`${sourceTool}_unavailable`, reason],
      data_quality: buildDataQuality({
        status: 'unavailable',
        reasons: [`${sourceTool}_unavailable`, reason],
        qualityFlags: ['technical_source_unavailable'],
        emptyReason: `${sourceTool} 暂时不可用`,
        sources: [{ name: sourceTool, status: 'failed', error: reason, sampleCount: 0 }],
      }),
    };
  }

  private formatError(error: unknown): string {
    if (error && typeof error === 'object' && typeof (error as { getResponse?: () => unknown }).getResponse === 'function') {
      const response = (error as { getResponse: () => unknown }).getResponse();
      if (response && typeof response === 'object') {
        const record = response as Record<string, unknown>;
        const detail = record.detail;
        if (typeof detail === 'string' && detail.trim()) return detail.trim();
        const message = record.message;
        if (typeof message === 'string' && message.trim()) return message.trim();
      }
    }
    return error instanceof Error ? error.message : String(error);
  }

  private sampleCount(value: unknown): number {
    if (Array.isArray(value)) return value.length;
    if (!value || typeof value !== 'object') return 0;
    const record = value as Record<string, unknown>;
    for (const key of ['items', 'records', 'patterns', 'signals', 'indicators', 'data', 'result']) {
      const nested = record[key];
      if (Array.isArray(nested)) return nested.length;
    }
    return 0;
  }

  private hasBusinessValue(value: unknown): boolean {
    if (value == null || value === '') return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value !== 'object') return true;
    const record = value as Record<string, unknown>;
    return Object.entries(record).some(([key, nested]) => {
      if (['success', 'ok', 'message', 'error', 'meta', 'result_contract', 'data_quality'].includes(key)) {
        return false;
      }
      return this.hasBusinessValue(nested);
    });
  }
}
