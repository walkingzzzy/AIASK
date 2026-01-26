/**
 * 预加载脚本 - 安全暴露 API 给渲染进程
 */

const { contextBridge, ipcRenderer, IpcRendererEvent } = require('electron');

// 暴露给渲染进程的 API
const electronAPI = {
    // MCP 相关
    mcp: {
        init: () => ipcRenderer.invoke('mcp:init'),
        callTool: (name: string, args: Record<string, unknown> = {}) => ipcRenderer.invoke('mcp:callTool', name, args),
        listTools: () => ipcRenderer.invoke('mcp:listTools'),
    },

    // 对话历史
    db: {
        createSession: (title?: string) => ipcRenderer.invoke('db:createSession', title),
        getSessions: () => ipcRenderer.invoke('db:getSessions'),
        getMessages: (sessionId: string) => ipcRenderer.invoke('db:getMessages', sessionId),
        saveMessage: (sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) =>
            ipcRenderer.invoke('db:saveMessage', sessionId, role, content, toolCalls, metadata),
        updateSessionTitle: (sessionId: string, title: string) => ipcRenderer.invoke('db:updateSessionTitle', sessionId, title),
        deleteSession: (sessionId: string) => ipcRenderer.invoke('db:deleteSession', sessionId),
        searchMessages: (query: string) => ipcRenderer.invoke('db:searchMessages', query),
    },

    // 用户配置
    config: {
        get: () => ipcRenderer.invoke('config:get'),
        save: (config: unknown) => ipcRenderer.invoke('config:save', config),
    },

    // 自选股
    watchlist: {
        get: () => ipcRenderer.invoke('watchlist:get'),
        add: (stockCode: string) => ipcRenderer.invoke('watchlist:add', stockCode),
        remove: (stockCode: string) => ipcRenderer.invoke('watchlist:remove', stockCode),
        getMeta: (stockCode?: string) => ipcRenderer.invoke('watchlist:meta:get', stockCode),
        saveMeta: (meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) =>
            ipcRenderer.invoke('watchlist:meta:save', meta),
        removeMeta: (stockCode: string) => ipcRenderer.invoke('watchlist:meta:remove', stockCode),
    },

    // 行为追踪
    behavior: {
        record: (event: unknown) => ipcRenderer.invoke('behavior:record', event),
        summary: (days?: number) => ipcRenderer.invoke('behavior:summary', days),
    },

    // AI 流式响应
    ai: {
        stream: (messages: Array<{ role: string; content: string }>) => ipcRenderer.invoke('ai:stream', messages),
        cancel: (streamId: string) => ipcRenderer.invoke('ai:stream:cancel', streamId),
        planTool: (payload: { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }) =>
            ipcRenderer.invoke('ai:planTool', payload),
        deepAnalysis: (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) =>
            ipcRenderer.invoke('ai:deepAnalysis', payload),
        onChunk: (handler: (payload: unknown) => void) => {
            const listener = (_event: typeof IpcRendererEvent, payload: unknown) => handler(payload);
            ipcRenderer.on('ai:stream:chunk', listener);
            return () => ipcRenderer.removeListener('ai:stream:chunk', listener);
        },
        onDone: (handler: (payload: unknown) => void) => {
            const listener = (_event: typeof IpcRendererEvent, payload: unknown) => handler(payload);
            ipcRenderer.on('ai:stream:done', listener);
            return () => ipcRenderer.removeListener('ai:stream:done', listener);
        },
        onError: (handler: (payload: unknown) => void) => {
            const listener = (_event: typeof IpcRendererEvent, payload: unknown) => handler(payload);
            ipcRenderer.on('ai:stream:error', listener);
            return () => ipcRenderer.removeListener('ai:stream:error', listener);
        },
    },

    // 交易决策追踪
    trading: {
        logDecision: (decision: unknown) => ipcRenderer.invoke('trading:logDecision', decision),
        getDecisions: (options?: unknown) => ipcRenderer.invoke('trading:getDecisions', options),
        verifyDecision: (decisionId: string, result: string, profitPercent?: number) =>
            ipcRenderer.invoke('trading:verifyDecision', decisionId, result, profitPercent),
        getAccuracyStats: (options?: unknown) => ipcRenderer.invoke('trading:getAccuracyStats', options),
        generateReport: (options?: unknown) => ipcRenderer.invoke('trading:generateReport', options),
        createPlan: (plan: unknown) => ipcRenderer.invoke('trading:plan:create', plan),
        getPlans: (options?: unknown) => ipcRenderer.invoke('trading:plan:list', options),
        updatePlan: (planId: string, updates: unknown) => ipcRenderer.invoke('trading:plan:update', planId, updates),
        removePlan: (planId: string) => ipcRenderer.invoke('trading:plan:remove', planId),
        setPlanStatus: (planId: string, status: string) => ipcRenderer.invoke('trading:plan:setStatus', planId, status),
    },

    // 网络代理
    proxy: {
        request: (url: string, options: unknown) => ipcRenderer.invoke('proxy:request', url, options),
    },

    // 通用工具
    platform: process.platform,
};

// 安全暴露 API
contextBridge.exposeInMainWorld('electronAPI', electronAPI);
