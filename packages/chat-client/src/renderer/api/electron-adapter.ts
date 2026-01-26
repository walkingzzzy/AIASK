/**
 * Electron 环境适配器
 * 直接包装 window.electronAPI 调用
 */

import type { IApiClient, StreamChunkPayload, StreamDonePayload, StreamErrorPayload, BehaviorEvent } from './api';
import type { MCPResult, ChatMessage, ChatSession, UserConfig, TradePlan, TradePlanStatus } from '../../shared/types';

export const createElectronAdapter = (): IApiClient => {
    const api = window.electronAPI;

    return {
        mcp: {
            init: () => api.mcp.init(),
            callTool: (name: string, args?: Record<string, unknown>) => api.mcp.callTool(name, args),
            listTools: () => api.mcp.listTools(),
        },

        db: {
            createSession: (title?: string) => api.db.createSession(title),
            getSessions: () => api.db.getSessions(),
            getMessages: (sessionId: string) => api.db.getMessages(sessionId),
            saveMessage: (sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) =>
                api.db.saveMessage(sessionId, role, content, toolCalls, metadata),
            updateSessionTitle: (sessionId: string, title: string) => api.db.updateSessionTitle(sessionId, title),
            deleteSession: (sessionId: string) => api.db.deleteSession(sessionId),
            searchMessages: (query: string) => api.db.searchMessages(query),
        },

        config: {
            get: () => api.config.get(),
            save: (config: Partial<UserConfig>) => api.config.save(config),
        },

        watchlist: {
            get: () => api.watchlist.get(),
            add: (stockCode: string) => api.watchlist.add(stockCode),
            remove: (stockCode: string) => api.watchlist.remove(stockCode),
            getMeta: (stockCode?: string) => api.watchlist.getMeta(stockCode),
            saveMeta: (meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) =>
                api.watchlist.saveMeta(meta),
            removeMeta: (stockCode: string) => api.watchlist.removeMeta(stockCode),
        },

        behavior: {
            record: (event: BehaviorEvent) => api.behavior.record(event),
            summary: (days?: number) => api.behavior.summary(days),
        },

        ai: {
            stream: (messages: Array<{ role: string; content: string }>) =>
                api.ai.stream(messages as Array<{ role: 'user' | 'assistant' | 'system'; content: string }>),
            cancel: (streamId: string) => api.ai.cancel(streamId),
            planTool: (payload: { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }) =>
                api.ai.planTool(payload as { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }),
            deepAnalysis: (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) =>
                api.ai.deepAnalysis(payload),
            onChunk: (handler: (payload: StreamChunkPayload) => void) => api.ai.onChunk(handler as (payload: unknown) => void),
            onDone: (handler: (payload: StreamDonePayload) => void) => api.ai.onDone(handler as (payload: unknown) => void),
            onError: (handler: (payload: StreamErrorPayload) => void) => api.ai.onError(handler as (payload: unknown) => void),
        },

        trading: {
            logDecision: (decision: unknown) => api.trading.logDecision(decision),
            getDecisions: (options?: unknown) => api.trading.getDecisions(options),
            verifyDecision: (decisionId: string, result: string, profitPercent?: number) =>
                api.trading.verifyDecision(decisionId, result, profitPercent),
            getAccuracyStats: (options?: unknown) => api.trading.getAccuracyStats(options),
            generateReport: (options: unknown) => api.trading.generateReport(options),
            createPlan: (plan: Omit<TradePlan, 'id' | 'createdAt' | 'updatedAt'>) =>
                api.trading.createPlan(plan),
            getPlans: (options?: { stockCode?: string; status?: TradePlanStatus; limit?: number }) =>
                api.trading.getPlans(options),
            updatePlan: (planId: string, updates: Partial<TradePlan>) =>
                api.trading.updatePlan(planId, updates),
            removePlan: (planId: string) => api.trading.removePlan(planId),
            setPlanStatus: (planId: string, status: TradePlanStatus) =>
                api.trading.setPlanStatus(planId, status),
        },

        proxy: {
            request: (url: string, options?: unknown) => api.proxy.request(url, options),
        },

        platform: api.platform,
    };
};
