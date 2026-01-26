/**
 * 共享类型定义
 */

// MCP 结果类型
export interface MCPResult<T = unknown> {
    success: boolean;
    data?: T;
    error?: string;
    requiresConfirmation?: boolean;
    confirmation?: {
        toolName: string;
        arguments?: Record<string, unknown>;
        message?: string;
    };
    validationErrors?: unknown;
}

export type TradePlanStatus = 'planned' | 'executed' | 'cancelled';

export interface TradePlan {
    id: string;
    stockCode: string;
    action: 'buy' | 'sell';
    targetPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    quantity?: number;
    note?: string;
    status: TradePlanStatus;
    createdAt: number;
    updatedAt: number;
}

export interface WatchlistMeta {
    stockCode: string;
    costPrice?: number | null;
    targetPrice?: number | null;
    stopLoss?: number | null;
    note?: string | null;
    updatedAt: number;
}

// 聊天消息类型
export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant' | 'system' | 'tool';
    content: string;
    suggestions?: string[];
    toolCall?: {
        name: string;
        args: Record<string, unknown>;
        result?: unknown;
        meta?: {
            durationMs?: number;
            source?: string;
            quality?: string;
            degraded?: boolean;
            visualizationType?: Visualization['type'];
            requiresConfirmation?: boolean;
            confirmArgs?: Record<string, unknown>;
            confirmMessage?: string;
        };
    };
    visualization?: Visualization;
    createdAt: Date;
}

// 可视化数据
export interface Visualization {
    type: 'stock' | 'kline' | 'table' | 'chart' | 'profile' | 'portfolio' | 'decision' | 'card' | 'backtest';
    title?: string;
    data: unknown;
}

// 聊天会话类型
export interface ChatSession {
    id: string;
    title: string;
    summary?: string;
    tags?: string;
    createdAt: number;
    updatedAt: number;
}

// 股票行情类型
export interface StockQuote {
    code: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    volume: number;
    amount: number;
    open?: number;
    high?: number;
    low?: number;
    preClose?: number;
}

// 用户偏好
export interface UserConfig {
    aiModel: 'claude' | 'gpt-4' | 'local';
    apiKey?: string;
    apiBaseUrl?: string;
    apiModel?: string;
    riskTolerance: 'conservative' | 'moderate' | 'aggressive';
    investmentStyle: 'value' | 'growth' | 'momentum' | 'mixed';
    preferredSectors: string[];
    theme: 'light' | 'dark' | 'system';
    profileParams?: {
        stopLoss: number;
        takeProfit: number;
        maxPosition: number;
        riskScore: number;
        riskType: string;
        experience: string;
        investPeriod: string;
        style: string;
    };
    notificationPreferences?: {
        enabled: boolean;
        quietHours?: number[];
        maxDaily?: number;
        channels?: string[];
    };
}

// 扩展 Window 类型
declare global {
    interface Window {
        electronAPI: {
            mcp: {
                init: () => Promise<MCPResult>;
                callTool: (name: string, args?: Record<string, unknown>) => Promise<MCPResult>;
                listTools: () => Promise<MCPResult>;
            };
            db: {
                createSession: (title?: string) => Promise<MCPResult<ChatSession>>;
                getSessions: () => Promise<MCPResult<ChatSession[]>>;
                getMessages: (sessionId: string) => Promise<MCPResult<ChatMessage[]>>;
                saveMessage: (sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) => Promise<MCPResult<{ id: string }>>;
                updateSessionTitle: (sessionId: string, title: string) => Promise<MCPResult>;
                deleteSession: (sessionId: string) => Promise<MCPResult>;
                searchMessages: (query: string) => Promise<MCPResult<unknown[]>>;
            };
            config: {
                get: () => Promise<MCPResult<UserConfig>>;
                save: (config: Partial<UserConfig>) => Promise<MCPResult>;
            };
            watchlist: {
                get: () => Promise<MCPResult<string[]>>;
                add: (stockCode: string) => Promise<MCPResult>;
                remove: (stockCode: string) => Promise<MCPResult>;
                getMeta: (stockCode?: string) => Promise<MCPResult<WatchlistMeta[]>>;
                saveMeta: (meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) => Promise<MCPResult>;
                removeMeta: (stockCode: string) => Promise<MCPResult>;
            };
            trading: {
                logDecision: (decision: unknown) => Promise<MCPResult<{ id: string }>>;
                getDecisions: (options?: unknown) => Promise<MCPResult<unknown[]>>;
                verifyDecision: (decisionId: string, result: string, profitPercent?: number) => Promise<MCPResult>;
                getAccuracyStats: (options?: unknown) => Promise<MCPResult<unknown>>;
                generateReport: (options: unknown) => Promise<MCPResult<unknown>>;
                createPlan: (plan: Omit<TradePlan, 'id' | 'createdAt' | 'updatedAt'>) => Promise<MCPResult<{ id: string }>>;
                getPlans: (options?: { stockCode?: string; status?: TradePlanStatus; limit?: number }) => Promise<MCPResult<TradePlan[]>>;
                updatePlan: (planId: string, updates: Partial<TradePlan>) => Promise<MCPResult>;
                removePlan: (planId: string) => Promise<MCPResult>;
                setPlanStatus: (planId: string, status: TradePlanStatus) => Promise<MCPResult>;
            };
            behavior: {
                record: (event: {
                    eventType: 'query' | 'tool_call';
                    toolName?: string;
                    stockCode?: string;
                    query?: string;
                }) => Promise<MCPResult>;
                summary: (days?: number) => Promise<MCPResult<unknown>>;
            };
            ai: {
                stream: (messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>) => Promise<MCPResult<{ streamId: string }>>;
                cancel: (streamId: string) => Promise<MCPResult>;
                planTool: (payload: { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }) => Promise<MCPResult<{ toolName?: string; args?: Record<string, unknown>; reason?: string }>>;
                deepAnalysis: (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) => Promise<MCPResult<{ content: string }>>;
                onChunk: (handler: (payload: { streamId: string; delta: string }) => void) => () => void;
                onDone: (handler: (payload: { streamId: string }) => void) => () => void;
                onError: (handler: (payload: { streamId: string; error: string }) => void) => () => void;
            };
            proxy: {
                request: (url: string, options?: unknown) => Promise<{
                    success: boolean;
                    status: number;
                    statusText: string;
                    data: unknown;
                    headers?: Record<string, string>;
                    error?: string;
                }>;
            };
            platform: string;
        };
    }
}
