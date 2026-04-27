import { Inject, Injectable, Logger, OnModuleDestroy, OnModuleInit, forwardRef } from '@nestjs/common';
import { MarketService } from './market.service';
import { WsGateway } from '../ws/ws.gateway';

const FALSE_VALUES = new Set(['0', 'false', 'no']);

function normalizeEnv(value: string | undefined | null) {
    return String(value ?? '').trim().toLowerCase();
}

function isHttpMcpTransport(env: NodeJS.ProcessEnv = process.env) {
    const transport = normalizeEnv(env.MCP_TRANSPORT);
    return transport === 'streamable-http' || transport === 'streamable_http' || transport === 'http' || transport === 'sse';
}

function readPositiveInt(value: string | undefined, fallback: number) {
    const parsed = Number.parseInt(value ?? '', 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function readOptionalNumber(value: string | undefined | null) {
    const normalized = String(value ?? '').trim();
    if (!normalized) return null;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
}

export function resolveMarketSchedulerEnabled(env: NodeJS.ProcessEnv = process.env) {
    const explicit = normalizeEnv(env.MARKET_SCHEDULER_ENABLED);
    if (explicit) {
        return !FALSE_VALUES.has(explicit);
    }

    if (isHttpMcpTransport(env)) {
        return true;
    }

    const startupProfile = normalizeEnv(env.MCP_STDIO_STARTUP_PROFILE);
    if (startupProfile === 'tool-only' || startupProfile === 'tool_only') {
        return false;
    }

    const fullProfilePoolSlots = readOptionalNumber(env.MCP_FULL_PROFILE_POOL_SLOTS);
    if (fullProfilePoolSlots != null && fullProfilePoolSlots <= 0) {
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

    if (!explicit && !isHttpMcpTransport(env)) {
        const startupProfile = normalizeEnv(env.MCP_STDIO_STARTUP_PROFILE);
        if (startupProfile === 'tool-only' || startupProfile === 'tool_only') {
            return 'MCP_STDIO_STARTUP_PROFILE=tool-only';
        }

        const fullProfilePoolSlots = readOptionalNumber(env.MCP_FULL_PROFILE_POOL_SLOTS);
        if (fullProfilePoolSlots != null && fullProfilePoolSlots <= 0) {
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
    private static readonly QUOTE_INTERVAL_MS = readPositiveInt(process.env.MARKET_QUOTE_PUSH_INTERVAL_MS, 2_000);
    private static readonly INDEX_INTERVAL_MS = readPositiveInt(process.env.MARKET_INDEX_PUSH_INTERVAL_MS, 5_000);
    private static readonly INDEX_FAILURE_BACKOFF_MS = readPositiveInt(process.env.MARKET_INDEX_FAILURE_BACKOFF_MS, 30_000);
    private static readonly INDEX_FAILURE_MAX_BACKOFF_MS = readPositiveInt(process.env.MARKET_INDEX_FAILURE_MAX_BACKOFF_MS, 120_000);
    private quoteTimer: NodeJS.Timeout | null = null;
    private indexTimer: NodeJS.Timeout | null = null;
    private quoteKickTimer: NodeJS.Timeout | null = null;
    private indexKickTimer: NodeJS.Timeout | null = null;
    private nextQuoteCursor = 0;

    /** 当前订阅的股票代码（可通过 WS 连接动态收集） */
    private subscribedCodes = new Set<string>();
    private subscribedIndexCodes = new Set<string>();
    private indexFailureState = new Map<string, { failures: number; nextAttemptAt: number }>();

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

        // 短周期推送批量行情，服务层负责短 TTL 与 in-flight 去重，避免压垮 MCP。
        this.quoteTimer = setInterval(() => {
            void this.pushBatchQuotes();
        }, MarketScheduler.QUOTE_INTERVAL_MS);

        this.indexTimer = setInterval(() => {
            void this.pushIndexQuotes();
        }, MarketScheduler.INDEX_INTERVAL_MS);

        this.logger.log(`行情推送调度器已启动 — 批量 ${MarketScheduler.QUOTE_INTERVAL_MS}ms / 指数 ${MarketScheduler.INDEX_INTERVAL_MS}ms`);
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
        if (this.quoteKickTimer) {
            clearTimeout(this.quoteKickTimer);
            this.quoteKickTimer = null;
        }
        if (this.indexKickTimer) {
            clearTimeout(this.indexKickTimer);
            this.indexKickTimer = null;
        }
    }

    /** 接受前端订阅的代码，供定时推送使用 */
    addSubscribedCodes(codes: string[]) {
        const before = this.subscribedCodes.size;
        codes
            .map((c) => String(c).trim())
            .filter(Boolean)
            .forEach((c) => this.subscribedCodes.add(c));
        if (this.subscribedCodes.size > before) {
            this.scheduleQuotePushSoon();
        }
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

    addSubscribedIndexCodes(codes: string[]) {
        const before = this.subscribedIndexCodes.size;
        codes
            .map((c) => String(c).trim())
            .filter(Boolean)
            .forEach((c) => this.subscribedIndexCodes.add(c));
        if (this.subscribedIndexCodes.size > before) {
            this.scheduleIndexPushSoon();
        }
    }

    removeSubscribedIndexCodes(codes: string[]) {
        codes
            .map((c) => String(c).trim())
            .filter(Boolean)
            .forEach((c) => {
                this.subscribedIndexCodes.delete(c);
                this.indexFailureState.delete(c);
            });
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
        const indexCodes = [...this.subscribedIndexCodes];
        if (indexCodes.length === 0) return;

        const now = Date.now();
        for (const indexCode of indexCodes) {
            if (this.shouldSkipIndexCode(indexCode, now)) continue;

            try {
                const data = await this.marketService.getIndexQuote(indexCode);
                const quote = data?.quote && typeof data.quote === 'object' ? data.quote as Record<string, unknown> : {};
                this.wsGateway.pushQuote(indexCode, 'index', quote);
                this.indexFailureState.delete(indexCode);
            } catch (err) {
                this.recordIndexFailure(indexCode, err);
            }
        }
    }

    private scheduleQuotePushSoon() {
        if (!MarketScheduler.ENABLED || this.quoteKickTimer) return;
        this.quoteKickTimer = setTimeout(() => {
            this.quoteKickTimer = null;
            void this.pushBatchQuotes();
        }, 0);
    }

    private scheduleIndexPushSoon() {
        if (!MarketScheduler.ENABLED || this.indexKickTimer) return;
        this.indexKickTimer = setTimeout(() => {
            this.indexKickTimer = null;
            void this.pushIndexQuotes();
        }, 0);
    }

    private shouldSkipIndexCode(indexCode: string, now: number) {
        const state = this.indexFailureState.get(indexCode);
        return Boolean(state && now < state.nextAttemptAt);
    }

    private recordIndexFailure(indexCode: string, err: unknown) {
        const previous = this.indexFailureState.get(indexCode);
        const failures = (previous?.failures ?? 0) + 1;
        const backoffMs = Math.min(
            MarketScheduler.INDEX_FAILURE_MAX_BACKOFF_MS,
            MarketScheduler.INDEX_FAILURE_BACKOFF_MS * (2 ** Math.min(failures - 1, 4)),
        );
        this.indexFailureState.set(indexCode, {
            failures,
            nextAttemptAt: Date.now() + backoffMs,
        });
        this.logger.debug(
            `指数 ${indexCode} 推送失败: ${err instanceof Error ? err.message : err}，${backoffMs}ms 后重试`,
        );
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
