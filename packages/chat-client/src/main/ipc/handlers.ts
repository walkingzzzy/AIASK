/**
 * IPC 处理器 - 桥接渲染进程和主进程
 */

import { ipcMain, IpcMainInvokeEvent } from 'electron';
import { randomUUID } from 'crypto';
import { callMCPTool, listMCPTools, initMCPClient } from '../mcp-client';
import { createAIStream, planToolCall, generateDeepAnalysis, type ToolCandidate } from '../ai-service';
import {
    initChatStore,
    createSession,
    getSessions,
    saveMessage,
    getMessages,
    updateSessionTitle,
    deleteSession,
    searchMessages
} from '../db/chat-store';
import {
    initUserStore,
    getConfig,
    saveConfig,
    getWatchlist,
    addToWatchlist,
    removeFromWatchlist,
    getWatchlistMeta,
    upsertWatchlistMeta,
    removeWatchlistMeta,
    recordBehaviorEvent,
    getBehaviorSummary
} from '../db/user-store';
import {
    initTradingStore,
    logDecision,
    getDecisions,
    verifyDecision,
    getAIAccuracyStats,
    generateReviewReport,
    createTradePlan,
    getTradePlans,
    updateTradePlan,
    removeTradePlan,
    setTradePlanStatus
} from '../db/trading-store';

const activeStreams = new Map<string, { cancel: () => void }>();

/**
 * 注册所有 IPC 处理器
 */
export function registerIPCHandlers(): void {
    // 初始化数据库
    initChatStore();
    initUserStore();
    initTradingStore();

    // ==================== MCP 相关 ====================

    ipcMain.handle('mcp:callTool', async (_event: IpcMainInvokeEvent, name: string, args: Record<string, unknown>) => {
        try {
            const result = await callMCPTool(name, args);
            return result;
        } catch (error) {
            console.error('[IPC] mcp:callTool error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('mcp:listTools', async () => {
        try {
            const result = await listMCPTools();
            return result;
        } catch (error) {
            console.error('[IPC] mcp:listTools error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('mcp:init', async () => {
        try {
            await initMCPClient();
            return { success: true };
        } catch (error) {
            console.error('[IPC] mcp:init error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== AI 流式响应 ====================

    ipcMain.handle('ai:stream', async (event, messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>) => {
        try {
            const streamId = randomUUID();
            const stream = await createAIStream(messages);
            activeStreams.set(streamId, stream);

            const sender = event.sender;
            (async () => {
                try {
                    for await (const delta of stream.iterator) {
                        if (sender.isDestroyed()) break;
                        sender.send('ai:stream:chunk', { streamId, delta });
                    }
                    if (!sender.isDestroyed()) {
                        sender.send('ai:stream:done', { streamId });
                    }
                } catch (error) {
                    if (!sender.isDestroyed()) {
                        sender.send('ai:stream:error', { streamId, error: (error as Error).message });
                    }
                } finally {
                    activeStreams.delete(streamId);
                }
            })();

            return { success: true, data: { streamId } };
        } catch (error) {
            console.error('[IPC] ai:stream error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('ai:stream:cancel', async (_event, streamId: string) => {
        const stream = activeStreams.get(streamId);
        if (stream) {
            stream.cancel();
            activeStreams.delete(streamId);
        }
        return { success: true };
    });

    ipcMain.handle('ai:planTool', async (_event, payload: { query: string; tools: ToolCandidate[] }) => {
        try {
            const plan = await planToolCall(payload.query, payload.tools || []);
            return { success: true, data: plan };
        } catch (error) {
            console.error('[IPC] ai:planTool error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('ai:deepAnalysis', async (_event, payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) => {
        try {
            const analysis = await generateDeepAnalysis(payload);
            return { success: true, data: analysis };
        } catch (error) {
            console.error('[IPC] ai:deepAnalysis error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== 对话历史 ====================

    ipcMain.handle('db:createSession', async (_event, title?: string) => {
        try {
            const session = createSession(title);
            return { success: true, data: session };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:getSessions', async () => {
        try {
            const sessions = getSessions();
            return { success: true, data: sessions };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:getMessages', async (_event, sessionId: string) => {
        try {
            const messages = getMessages(sessionId);
            return { success: true, data: messages };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:saveMessage', async (_event, sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) => {
        try {
            const id = saveMessage(sessionId, role as any, content, toolCalls, metadata);
            return { success: true, data: { id } };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:updateSessionTitle', async (_event, sessionId: string, title: string) => {
        try {
            updateSessionTitle(sessionId, title);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:deleteSession', async (_event, sessionId: string) => {
        try {
            deleteSession(sessionId);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('db:searchMessages', async (_event, query: string) => {
        try {
            const results = searchMessages(query);
            return { success: true, data: results };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== 用户配置 ====================

    ipcMain.handle('config:get', async () => {
        try {
            const config = getConfig();
            return { success: true, data: config };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('config:save', async (_event, config: unknown) => {
        try {
            saveConfig(config as any);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:get', async () => {
        try {
            const list = getWatchlist();
            return { success: true, data: list };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:add', async (_event, stockCode: string) => {
        try {
            addToWatchlist(stockCode);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:remove', async (_event, stockCode: string) => {
        try {
            removeFromWatchlist(stockCode);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:meta:get', async (_event, stockCode?: string) => {
        try {
            const list = getWatchlistMeta(stockCode);
            return { success: true, data: list };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:meta:save', async (_event, meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) => {
        try {
            upsertWatchlistMeta(meta);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('watchlist:meta:remove', async (_event, stockCode: string) => {
        try {
            removeWatchlistMeta(stockCode);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== 行为追踪 ====================

    ipcMain.handle('behavior:record', async (_event, behavior: { eventType: 'query' | 'tool_call'; toolName?: string; stockCode?: string; query?: string }) => {
        try {
            recordBehaviorEvent(behavior);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('behavior:summary', async (_event, days?: number) => {
        try {
            const summary = getBehaviorSummary(days);
            return { success: true, data: summary };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== 交易决策追踪 ====================

    ipcMain.handle('trading:logDecision', async (_event, decision: unknown) => {
        try {
            const id = logDecision(decision as any);
            return { success: true, data: { id } };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:getDecisions', async (_event, options?: unknown) => {
        try {
            const decisions = getDecisions(options as any);
            return { success: true, data: decisions };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:verifyDecision', async (_event, decisionId: string, result: string, profitPercent?: number) => {
        try {
            verifyDecision(decisionId, result as any, profitPercent);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:getAccuracyStats', async (_event, options?: unknown) => {
        try {
            const stats = getAIAccuracyStats(options as any);
            return { success: true, data: stats };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:generateReport', async (_event, options: unknown) => {
        try {
            const report = generateReviewReport(options as any);
            return { success: true, data: report };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:plan:create', async (_event, plan: unknown) => {
        try {
            const id = createTradePlan(plan as any);
            return { success: true, data: { id } };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:plan:list', async (_event, options?: unknown) => {
        try {
            const plans = getTradePlans(options as any);
            return { success: true, data: plans };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:plan:update', async (_event, planId: string, updates: unknown) => {
        try {
            updateTradePlan(planId, updates as any);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:plan:remove', async (_event, planId: string) => {
        try {
            removeTradePlan(planId);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    ipcMain.handle('trading:plan:setStatus', async (_event, planId: string, status: string) => {
        try {
            setTradePlanStatus(planId, status as any);
            return { success: true };
        } catch (error) {
            return { success: false, error: (error as Error).message };
        }
    });

    // ==================== 网络代理 ====================

    ipcMain.handle('proxy:request', async (_event, url: string, options: any) => {
        try {
            console.log(`[Proxy] Requesting: ${url}`);
            const response = await fetch(url, options);

            // 尝试解析 JSON，失败则返回文本
            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch {
                data = text;
            }

            return {
                success: response.ok,
                status: response.status,
                statusText: response.statusText,
                data: data,
                // headers: Object.fromEntries(response.headers.entries()) // 暂时不需要完整 headers
            };
        } catch (error) {
            console.error('[IPC] proxy:request error:', error);
            return { success: false, error: (error as Error).message };
        }
    });

    console.log('[IPC] All handlers registered');
}
