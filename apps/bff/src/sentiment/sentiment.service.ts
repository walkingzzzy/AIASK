import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { trustedDataQuality, unavailableDataQuality } from '../common/data-quality';

@Injectable()
export class SentimentService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async analyzeStock(code: string) {
    const payload = await this.callTool('analyze_stock_sentiment', { code }, {
      fallback: {
        code,
        degraded: true,
        fallbackReason: 'analyze_stock_sentiment_unavailable',
        updatedAt: new Date().toISOString(),
      },
    });
    const reason = this.extractDegradedReason(payload);
    const data = this.extractToolData(payload);
    const dataQuality = reason
      ? unavailableDataQuality('analyze_stock_sentiment', reason, {
        emptyReason: '个股情绪上游不可用，未返回可验证分数',
        qualityFlags: ['stock_sentiment_unavailable'],
      })
      : trustedDataQuality('analyze_stock_sentiment', 1, this.extractFreshness(data));
    return {
      sourceTool: 'analyze_stock_sentiment' as const,
      data: this.withDataQuality(data, dataQuality),
      result: payload,
      ...(reason ? { degraded: true, fallback_used: false, fallback_reason: reason } : {}),
      data_quality: dataQuality,
    };
  }

  async fearGreedIndex() {
    const payload = await this.callTool('calculate_fear_greed_index', {}, {
      fallback: {
        index: 50,
        value: 50,
        label: '中性',
        degraded: true,
        fallbackReason: 'calculate_fear_greed_index_unavailable',
        updatedAt: new Date().toISOString(),
      },
    });
    const reason = this.extractDegradedReason(payload);
    const data = this.extractToolData(payload);
    const dataQuality = reason
      ? unavailableDataQuality('calculate_fear_greed_index', reason, {
        emptyReason: '恐贪指数上游不可用，当前 50/中性仅为降级占位值',
        qualityFlags: ['fear_greed_fallback_default'],
      })
      : trustedDataQuality('calculate_fear_greed_index', 1, this.extractFreshness(data));
    return {
      sourceTool: 'calculate_fear_greed_index' as const,
      data: this.withDataQuality(data, dataQuality),
      result: payload,
      ...(reason ? { degraded: true, fallback_used: false, fallback_reason: reason } : {}),
      data_quality: dataQuality,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>, options?: { fallback?: Record<string, unknown> }) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      if (options?.fallback) {
        return {
          success: false,
          degraded: true,
          error: error instanceof Error ? error.message : String(error),
          data: options.fallback,
        };
      }
      throw new BadGatewayException({
        success: false, message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
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

  private withDataQuality(data: unknown, dataQuality: unknown): unknown {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return data;
    return { ...(data as Record<string, unknown>), data_quality: dataQuality };
  }

  private extractFreshness(data: unknown): string | null {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    const record = data as Record<string, unknown>;
    const value = record.updatedAt ?? record.timestamp ?? record.date;
    return typeof value === 'string' && value.trim() ? value : null;
  }

  private extractDegradedReason(payload: unknown): string | null {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
    const record = payload as Record<string, unknown>;
    if (record.success === false || record.degraded === true) {
      return String(record.error ?? record.fallbackReason ?? record.fallback_reason ?? 'sentiment_source_unavailable');
    }
    const data = record.data;
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      const dataRecord = data as Record<string, unknown>;
      if (dataRecord.degraded === true) {
        return String(dataRecord.error ?? dataRecord.fallbackReason ?? dataRecord.fallback_reason ?? 'sentiment_source_unavailable');
      }
    }
    return null;
  }
}
