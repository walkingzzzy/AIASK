import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type NormalizedScreenResult = { stocks: Array<{ code: string; name: string; matchScore: number | null }> };
export type NormalizedSignal = { name: string; type: string; value: string; direction: string };
type TdxActionResult = {
  success: boolean;
  message: string;
  diagnostics?: Record<string, unknown>;
  raw: unknown;
};

@Injectable()
export class TdxService {
  private static readonly SIGNALS_TTL_SECONDS = 300;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async pushMessage(body: { message: string; stock_code?: string }) {
    const text = body.stock_code?.trim()
      ? `${body.stock_code.trim()} ${body.message.trim()}`
      : body.message.trim();
    const payload = await this.mcp.callTool('push_message', { message: text });
    return { data: this.normalizeActionResult(payload, '消息发送成功') };
  }

  async pushWarn(body: { message: string; stock_code: string; price: number; bs_flag?: number }) {
    const payload = await this.mcp.callTool('push_warn', {
      stock_code: body.stock_code.trim(),
      price: body.price,
      reason: body.message.trim(),
      bs_flag: body.bs_flag ?? 2,
    });
    return { data: this.normalizeActionResult(payload, '预警信号发送成功') };
  }

  async createWatchlist(body: { name: string; stock_codes: string[] }) {
    const payload = await this.mcp.callTool('create_watchlist', {
      block_code: this.toBlockCode(body.name),
      block_name: body.name,
      stock_codes: body.stock_codes,
    });
    return { data: this.normalizeActionResult(payload, `板块 ${body.name} 创建成功`) };
  }

  async calculateIndicator(body: { code: string; indicator: string; params?: Record<string, unknown> }) {
    const payload = await this.mcp.callTool('tdx_calculate_indicator', {
      stock_code: body.code.trim(),
      formula_name: body.indicator.trim(),
      formula_args: this.serializeFormulaArgs(body.params),
    });
    return { data: this.normalizeIndicatorResult(payload) };
  }

  async screenStocks(body: { formula?: string; conditions?: Record<string, unknown> }) {
    const payload = await this.mcp.callTool('tdx_screen_stocks', {
      formula_name: String(body.formula ?? '').trim(),
      formula_args: this.serializeFormulaArgs(body.conditions),
    });
    return { data: this.normalizeScreenResult(payload) };
  }

  async getExpertSignals(code: string) {
    const stockCode = code.trim();
    const cacheKey = `tdx:signals:${stockCode}`;
    const ttlSeconds = this.cacheService.resolveTtl('tdx.signals', TdxService.SIGNALS_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode, formula_name: 'MACD' },
      { stock_code: stockCode, formula_name: 'KDJ' },
      { code: stockCode, formula_name: 'MACD' },
    ];

    const { payload } = await this.callWithArgs('tdx_get_expert_signals', attempts);
    const result = { data: { signals: this.normalizeSignals(payload) }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private normalizeScreenResult(payload: any): NormalizedScreenResult {
    const root = payload?.data ?? payload ?? {};
    const list = Array.isArray(root) ? root : Array.isArray(root?.stocks) ? root.stocks : Array.isArray(root?.data) ? root.data : [];
    return {
      stocks: list.map((s: any) => ({
        code: String(s.code ?? s.stock_code ?? s.symbol ?? ''),
        name: String(s.name ?? s.stock_name ?? ''),
        matchScore: this.toNum(s.score ?? s.match_score),
      })),
    };
  }

  private normalizeSignals(payload: any): NormalizedSignal[] {
    const root = payload?.data ?? payload ?? {};
    const list = Array.isArray(root)
      ? root
      : Array.isArray(root?.signals)
        ? root.signals
        : Array.isArray(root?.data)
          ? root.data
          : this.normalizeSignalMap(root?.signals ?? root?.data ?? root);
    return list.map((s: any) => ({
      name: String(s.name ?? s.signal_name ?? s.signal ?? ''),
      type: String(s.type ?? s.signal_type ?? ''),
      value: String(s.value ?? s.signal_value ?? ''),
      direction: String(s.direction ?? s.signal ?? ''),
    }));
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeActionResult(payload: unknown, successMessage: string): TdxActionResult {
    const error = this.extractToolError(payload);
    if (error) {
      return { success: false, message: error, raw: payload };
    }

    const root = payload && typeof payload === 'object' && !Array.isArray(payload)
      ? ((payload as Record<string, unknown>).data ?? payload)
      : payload;

    if (root && typeof root === 'object' && !Array.isArray(root)) {
      const record = root as Record<string, unknown>;
      const message = this.extractMessage(record) ?? successMessage;
      return {
        success: record.success !== false,
        message,
        diagnostics: record.diagnostics && typeof record.diagnostics === 'object'
          ? record.diagnostics as Record<string, unknown>
          : undefined,
        raw: payload,
      };
    }

    if (typeof root === 'string' && root.trim()) {
      return { success: true, message: root.trim(), raw: payload };
    }

    return { success: true, message: successMessage, raw: payload };
  }

  private async callWithArgs(primaryTool: string, attempts: Array<Record<string, unknown>>) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcp.callTool(primaryTool, args);
        return { payload, argsMatched: args };
      } catch (e) {
        lastError = e;
      }
    }
    throw new BadGatewayException({
      success: false,
      message: `MCP ${primaryTool} 调用失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }

  private normalizeIndicatorResult(payload: any) {
    const root = payload?.data ?? payload ?? {};
    const data = (root?.data && typeof root.data === 'object' && !Array.isArray(root.data)) ? root.data : root;
    const seriesKeys = Object.keys(data).filter((key) => Array.isArray(data[key]));
    const values = this.zipIndicatorSeries(data, seriesKeys);
    return {
      values,
      source: String(root?.source ?? payload?.source ?? ''),
      stock_code: String(root?.stock_code ?? payload?.stock_code ?? ''),
      formula_name: String(root?.formula_name ?? payload?.formula_name ?? ''),
    };
  }

  private zipIndicatorSeries(data: Record<string, unknown>, keys: string[]) {
    if (!keys.length) return [];
    const length = Math.max(...keys.map((key) => Array.isArray(data[key]) ? data[key].length : 0));
    return Array.from({ length }, (_, index) => {
      const row: Record<string, unknown> = { index };
      keys.forEach((key) => {
        const series = data[key];
        row[key] = Array.isArray(series) ? series[index] ?? null : null;
      });
      return row;
    });
  }

  private normalizeSignalMap(value: unknown): NormalizedSignal[] {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    return Object.entries(value as Record<string, unknown>).flatMap(([direction, series]) => {
      if (!Array.isArray(series)) return [];
      return series
        .map((item, index) => {
          if (item == null) return null;
          return {
            name: `${direction}-${index + 1}`,
            type: 'expert_signal',
            value: String(item),
            direction: direction.toLowerCase().includes('enter') ? 'up' : direction.toLowerCase().includes('exit') ? 'down' : direction,
          };
        })
        .filter((item): item is NormalizedSignal => item != null);
    });
  }

  private serializeFormulaArgs(params?: Record<string, unknown>) {
    if (!params || typeof params !== 'object') return '';
    return Object.values(params).map((value) => String(value ?? '')).join(',');
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      const text = payload.trim();
      return text ? text : null;
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return null;
    }

    const record = payload as Record<string, unknown>;
    if (record.success === false) {
      return this.extractMessage(record) ?? 'TDX 操作失败';
    }

    const nested = record.data;
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const nestedRecord = nested as Record<string, unknown>;
      if (nestedRecord.success === false) {
        return this.extractMessage(nestedRecord) ?? 'TDX 操作失败';
      }
    }

    return null;
  }

  private extractMessage(record: Record<string, unknown>): string | null {
    if (typeof record.message === 'string' && record.message.trim()) {
      return record.message.trim();
    }
    if (typeof record.error === 'string' && record.error.trim()) {
      return record.error.trim();
    }
    if (record.error && typeof record.error === 'object') {
      const nested = record.error as Record<string, unknown>;
      if (typeof nested.message === 'string' && nested.message.trim()) {
        return nested.message.trim();
      }
    }
    return null;
  }

  private toBlockCode(name: string) {
    const compact = name.replace(/\s+/g, '').slice(0, 6).toUpperCase();
    return `BLK${compact || 'AUTO'}`;
  }
}
