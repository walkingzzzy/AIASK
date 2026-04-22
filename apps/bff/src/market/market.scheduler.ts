import { Inject, Injectable, Logger, OnModuleDestroy, OnModuleInit, forwardRef } from '@nestjs/common';
import { MarketService } from './market.service';
import { WsGateway } from '../ws/ws.gateway';

const FALSE_VALUES = new Set(['0', 'false', 'no']);

function normalizeEnv(value: string | undefined | null) {
    return String(value ?? '').trim().toLowerCase();
}

export function resolveMarketSchedulerEnabled(env: NodeJS.ProcessEnv = process.env) {
    const explicit = normalizeEnv(env.MARKET_SCHEDULER_ENABLED);
    if (explicit) {
        return !FALSE_VALUES.has(explicit);
    }

    const startupProfile = normalizeEnv(env.MCP_STDIO_STARTUP_PROFILE);
    if (startupProfile === 'tool-only' || startupProfile === 'tool_only') {
        return false;
    }

    const fullProfilePoolSlots = Number(env.MCP_FULL_PROFILE_POOL_SLOTS ?? '');
    if (Number.isFinite(fullProfilePoolSlots) && fullProfilePoolSlots <= 0) {
        return false;
    }

    return !(
        env.NODE_ENV !== 'production'
        && Number(env.MCP_POOL_SIZE ?? '8') <= 1
    );
}

export function resolveMarketSchedulerDisabledReason(env: NodeJS.ProcessEnv = process.env) {
    const explicit = normalizeEnv(env.MARKET_SCHEDULER_ENABLED);
    if (explicit && FALSE_VALUES.has(explicit)) {
        return 'MARKET_SCHEDULER_ENABLED=false';
    }

    if (!explicit) {
        const startupProfile = normalizeEnv(env.MCP_STDIO_STARTUP_PROFILE);
        if (startupProfile === 'tool-only' || startupProfile === 'tool_only') {
            return 'MCP_STDIO_STARTUP_PROFILE=tool-only';
        }

        const fullProfilePoolSlots = Number(env.MCP_FULL_PROFILE_POOL_SLOTS ?? '');
        if (Number.isFinite(fullProfilePoolSlots) && fullProfilePoolSlots <= 0) {
            return 'MCP_FULL_PROFILE_POOL_SLOTS=0';
        }

        if (env.NODE_ENV !== 'production' && Number(env.MCP_POOL_SIZE ?? '8') <= 1) {
            return 'MCP_POOL_SIZE<=1 in non-production';
        }
    }

    return null;
}

/**
 * 行情推送调度器 — 定时拉取行情数据并通过 WebSocket 推送到前端。
 *
 * 推送频率：
 * - 批量行情：每 10 秒（仅交易时间段）
 * - 主要指数：每 30 秒
 */
@Injectable()
export class MarketScheduler implements OnModuleInit, OnModuleDestroy {
    private readonly logger = new Logger(MarketScheduler.name);
    private static readonly QUOTE_BATCH_SIZE = 50;
    private static readonly ENABLED = resolveMarketSchedulerEnabled();
    private quoteTimer: NodeJS.Timeout | null = null;
    private indexTimer: NodeJS.Timeout | null = null;
    private nextQuoteCursor = 0;

    /** 常用指数代码 */
    private readonly INDEX_CODES = ['000001', '399001', '399006'];

    /** 当前订阅的股票代码（可通过 WS 连接动态收集） */
    private subscribedCodes = new Set<string>();

    constructor(
        private readonly marketService: MarketService,
        @Inject(forwardRef(() => WsGateway))
        private readonly wsGateway: WsGateway,
    ) { }

    onModuleInit() {
        if (!MarketScheduler.ENABLED) {
            const reason = resolveMarketSchedulerDisabledReason();
            this.logger.log(`行情推送调度器已禁用${reason ? `（${reason}）` : ''}`);
            return;
        }

        // 每 10 秒推送批量行情
        this.quoteTimer = setInterval(() => {
            void this.pushBatchQuotes();
        }, 10_000);

        // 每 30 秒推送主要指数
        this.indexTimer = setInterval(() => {
            void this.pushIndexQuotes();
        }, 30_000);

        this.logger.log('行情推送调度器已启动 — 批量 10s / 指数 30s');
    }

    onModuleDestroy() {
        if (this.quoteTimer) {
            clearInterval(this.quoteTimer);
            this.quoteTimer = null;
        }
        if (this.indexTimer) {
            clearInterval(this.indexTimer);
            this.indexTimer = null;
        }
    }

    /** 接受前端订阅的代码，供定时推送使用 */
    addSubscribedCodes(codes: string[]) {
        codes
            .map((c) => String(c).trim())
            .filter(Boolean)
            .forEach((c) => this.subscribedCodes.add(c));
    }

    removeSubscribedCodes(codes: string[]) {
        codes
            .map((c) => String(c).trim())
            .filter(Boolean)
            .forEach((c) => this.subscribedCodes.delete(c));
        if (this.subscribedCodes.size === 0) {
            this.nextQuoteCursor = 0;
        } else {
            this.nextQuoteCursor %= this.subscribedCodes.size;
        }
    }

    private async pushBatchQuotes() {
        const codes = [...this.subscribedCodes];
        if (codes.length === 0) return;

        try {
            const batchCodes = this.selectBatchCodes(codes);
            const data = await this.marketService.getBatchQuotes(batchCodes);
            const items = this.extractQuoteItems(data);
            if (items.length > 0) {
                for (const item of items) {
                    const code = typeof item.code === 'string' ? item.code.trim() : '';
                    if (!code) continue;
                    this.wsGateway.pushQuote(code, 'stock', item);
                }
                this.wsGateway.pushBatchQuotes(items);
            }
        } catch (err) {
            this.logger.debug(`批量行情推送失败: ${err instanceof Error ? err.message : err}`);
        }
    }

    private async pushIndexQuotes() {
        for (const indexCode of this.INDEX_CODES) {
            try {
                const data = await this.marketService.getIndexQuote(indexCode);
                const quote = data && typeof data === 'object' ? (data as Record<string, unknown>) : {};
                this.wsGateway.pushQuote(indexCode, 'index', quote);
            } catch (err) {
                this.logger.debug(`指数 ${indexCode} 推送失败: ${err instanceof Error ? err.message : err}`);
            }
        }
    }

    private extractQuoteItems(data: unknown): Array<Record<string, unknown>> {
        if (!data || typeof data !== 'object') return [];
        const d = data as Record<string, unknown>;
        // MarketService.getBatchQuotes returns { quotes: [...] }
        const arr = d.quotes ?? d.items ?? d.data;
        if (Array.isArray(arr)) return arr as Array<Record<string, unknown>>;
        return [];
    }

    private selectBatchCodes(codes: string[]): string[] {
        if (codes.length <= MarketScheduler.QUOTE_BATCH_SIZE) {
            this.nextQuoteCursor = 0;
            return codes;
        }

        const batchSize = Math.min(MarketScheduler.QUOTE_BATCH_SIZE, codes.length);
        const start = this.nextQuoteCursor % codes.length;
        const window: string[] = [];
        for (let offset = 0; offset < batchSize; offset += 1) {
            window.push(codes[(start + offset) % codes.length]);
        }
        this.nextQuoteCursor = (start + batchSize) % codes.length;
        return window;
    }
}
