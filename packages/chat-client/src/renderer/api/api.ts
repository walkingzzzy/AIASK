/**
 * API 接口定义 - 统一的 API 抽象层
 * 让同一套组件代码同时支持 Electron 和 Web 环境
 */

import type { MCPResult, ChatMessage, ChatSession, UserConfig, Visualization } from '../../shared/types';
import type { TradePlan, TradePlanStatus, WatchlistMeta } from '../../shared/types';

// AI 流式响应的 payload 类型
export interface StreamChunkPayload {
    streamId: string;
    delta: string;
}

export interface StreamDonePayload {
    streamId: string;
}

export interface StreamErrorPayload {
    streamId: string;
    error: string;
}

// 行为记录事件类型
export interface BehaviorEvent {
    eventType: 'query' | 'tool_call';
    toolName?: string;
    stockCode?: string;
    query?: string;
}

// API 客户端接口
export interface IApiClient {
    // MCP 相关
    mcp: {
        init: () => Promise<MCPResult>;
        callTool: (name: string, args?: Record<string, unknown>) => Promise<MCPResult>;
        listTools: () => Promise<MCPResult>;
    };

    // 数据库操作
    db: {
        createSession: (title?: string) => Promise<MCPResult<ChatSession>>;
        getSessions: () => Promise<MCPResult<ChatSession[]>>;
        getMessages: (sessionId: string) => Promise<MCPResult<ChatMessage[]>>;
        saveMessage: (sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) => Promise<MCPResult<{ id: string }>>;
        updateSessionTitle: (sessionId: string, title: string) => Promise<MCPResult>;
        deleteSession: (sessionId: string) => Promise<MCPResult>;
        searchMessages: (query: string) => Promise<MCPResult<unknown[]>>;
    };

    // 用户配置
    config: {
        get: () => Promise<MCPResult<UserConfig>>;
        save: (config: Partial<UserConfig>) => Promise<MCPResult>;
    };

    // 自选股
    watchlist: {
        get: () => Promise<MCPResult<string[]>>;
        add: (stockCode: string) => Promise<MCPResult>;
        remove: (stockCode: string) => Promise<MCPResult>;
        getMeta: (stockCode?: string) => Promise<MCPResult<WatchlistMeta[]>>;
        saveMeta: (meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) => Promise<MCPResult>;
        removeMeta: (stockCode: string) => Promise<MCPResult>;
    };

    // 行为追踪
    behavior: {
        record: (event: BehaviorEvent) => Promise<MCPResult>;
        summary: (days?: number) => Promise<MCPResult<unknown>>;
    };

    // AI 流式响应
    ai: {
        stream: (messages: Array<{ role: string; content: string }>) => Promise<MCPResult<{ streamId: string }>>;
        cancel: (streamId: string) => Promise<MCPResult>;
        planTool: (payload: { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }) => Promise<MCPResult<{ toolName?: string; args?: Record<string, unknown>; reason?: string }>>;
        deepAnalysis: (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) => Promise<MCPResult<{ content: string }>>;
        onChunk: (handler: (payload: StreamChunkPayload) => void) => () => void;
        onDone: (handler: (payload: StreamDonePayload) => void) => () => void;
        onError: (handler: (payload: StreamErrorPayload) => void) => () => void;
    };

    // 交易决策
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

    // HTTP 代理请求（用于避免 CORS）
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

    // 平台信息
    platform: string;
}

// 环境检测
export const isElectron = (): boolean => {
    return typeof window !== 'undefined' && 'electronAPI' in window;
};

// 单例 API 客户端
let apiClient: IApiClient | null = null;

// 获取 API 客户端（延迟加载）
export const getApiClient = async (): Promise<IApiClient> => {
    if (apiClient) {
        return apiClient;
    }

    if (isElectron()) {
        const { createElectronAdapter } = await import('./electron-adapter');
        apiClient = createElectronAdapter();
    } else {
        const { createWebAdapter } = await import('./web-adapter');
        apiClient = createWebAdapter();
    }

    return apiClient;
};

// 同步获取（用于已初始化后的调用）
export const getApiClientSync = (): IApiClient => {
    if (!apiClient) {
        throw new Error('API client not initialized. Call getApiClient() first.');
    }
    return apiClient;
};

// 初始化 API 客户端
export const initApiClient = async (): Promise<IApiClient> => {
    return getApiClient();
};
