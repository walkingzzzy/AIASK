/**
 * Web 环境适配器
 * 使用 localStorage 作为简化存储，HTTP API 调用后端
 */

import type { IApiClient, StreamChunkPayload, StreamDonePayload, StreamErrorPayload, BehaviorEvent } from './api';
import type { MCPResult, ChatMessage, ChatSession, UserConfig, Visualization } from '../../shared/types';

// MCP 服务器地址配置
const DEFAULT_MCP_SERVER_URL = 'http://localhost:9898';

// localStorage Keys
const STORAGE_KEYS = {
    SESSIONS: 'chat_sessions',
    MESSAGES: 'chat_messages',
    CONFIG: 'user_config',
    WATCHLIST: 'watchlist',
    WATCHLIST_META: 'watchlist_meta',
    BEHAVIORS: 'behaviors',
    DECISIONS: 'trading_decisions',
    TRADE_PLANS: 'trade_plans',
};

// 生成唯一 ID
const generateId = (): string => {
    return Date.now().toString(36) + Math.random().toString(36).substring(2);
};

// 从 localStorage 获取数据
const getStorage = <T>(key: string, defaultValue: T): T => {
    try {
        const data = localStorage.getItem(key);
        return data ? JSON.parse(data) : defaultValue;
    } catch {
        return defaultValue;
    }
};

// 保存数据到 localStorage
const setStorage = <T>(key: string, value: T): void => {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.error('[WebAdapter] Storage error:', e);
    }
};

// AI 流式响应事件处理器
type ChunkHandler = (payload: StreamChunkPayload) => void;
type DoneHandler = (payload: StreamDonePayload) => void;
type ErrorHandler = (payload: StreamErrorPayload) => void;

const eventHandlers = {
    chunk: new Set<ChunkHandler>(),
    done: new Set<DoneHandler>(),
    error: new Set<ErrorHandler>(),
};

const getMCPServerUrl = (): string => {
    return localStorage.getItem('aethertrade_mcp_url') || DEFAULT_MCP_SERVER_URL;
};

// 从配置服务获取 API 配置
const getApiConfigFromStorage = (): { baseUrl: string; apiKey: string; model: string } | null => {
    try {
        const stored = localStorage.getItem('aethertrade_api_config');
        if (stored) {
            const config = JSON.parse(stored);
            if (config.baseUrl && config.apiKey && config.model && config.isValid) {
                return config;
            }
        }
    } catch (e) {
        console.error('[WebAdapter] Failed to load API config:', e);
    }
    return null;
};

const buildDeepAnalysisPrompt = (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }): string => {
    const raw = JSON.stringify(payload.toolResults, null, 2);
    const limited = raw.length > 12000 ? `${raw.slice(0, 12000)}\n...（已截断）` : raw;
    return [
        '你是股票AI深度分析师，请基于工具结果输出专业分析。',
        '必须输出结构化内容，包含：结论、关键数据、风险提示、策略建议、后续行动。',
        '如数据不足请明确说明并给出补充建议。',
        `用户问题: ${payload.query}`,
        `分析主题: ${payload.planTitle || '未命名分析'}`,
        `工具结果(JSON): ${limited}`,
    ].join('\n');
};

// 真实 AI 流式响应
const realAIStream = async (messages: Array<{ role: string; content: string }>): Promise<string> => {
    const streamId = generateId();
    const config = getApiConfigFromStorage();

    if (!config) {
        // 配置未设置，返回提示信息
        setTimeout(() => {
            eventHandlers.chunk.forEach(handler => handler({
                streamId,
                delta: '请先在设置中配置 API（点击右上角设置按钮）。\n配置完成后即可进行 AI 对话。'
            }));
            setTimeout(() => {
                eventHandlers.done.forEach(handler => handler({ streamId }));
            }, 100);
        }, 100);
        return streamId;
    }

    // 调用真实 API
    const url = config.baseUrl.replace(/\/$/, '') + '/chat/completions';

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${config.apiKey}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: config.model,
                messages: messages.map(m => ({ role: m.role, content: m.content })),
                stream: true,
            }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            eventHandlers.chunk.forEach(handler => handler({
                streamId,
                delta: `API 错误: ${response.status} - ${errorText}`
            }));
            eventHandlers.done.forEach(handler => handler({ streamId }));
            return streamId;
        }

        // 处理流式响应
        const reader = response.body?.getReader();
        if (!reader) {
            eventHandlers.chunk.forEach(handler => handler({ streamId, delta: '无法读取响应流' }));
            eventHandlers.done.forEach(handler => handler({ streamId }));
            return streamId;
        }

        const decoder = new TextDecoder();
        let buffer = '';

        const processStream = async () => {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6).trim();
                        if (data === '[DONE]') continue;
                        try {
                            const json = JSON.parse(data);
                            const text = json.choices?.[0]?.delta?.content || '';
                            if (text) {
                                eventHandlers.chunk.forEach(handler => handler({ streamId, delta: text }));
                            }
                        } catch {
                            // 忽略解析错误
                        }
                    }
                }
            }
            eventHandlers.done.forEach(handler => handler({ streamId }));
        };

        processStream().catch(err => {
            console.error('[WebAdapter] Stream error:', err);
            eventHandlers.error.forEach(handler => handler({ streamId, error: String(err) }));
        });

    } catch (err) {
        console.error('[WebAdapter] AI request error:', err);
        eventHandlers.chunk.forEach(handler => handler({
            streamId,
            delta: `请求失败: ${err instanceof Error ? err.message : '未知错误'}`
        }));
        eventHandlers.done.forEach(handler => handler({ streamId }));
    }

    return streamId;
};

export const createWebAdapter = (): IApiClient => {
    return {
        mcp: {
            init: async () => {
                // 检查 MCP 服务器是否可用
                try {
                    const response = await fetch(`${getMCPServerUrl()}/health`);
                    if (response.ok) {
                        return { success: true, data: { connected: true, message: 'MCP Server connected' } };
                    }
                    return { success: true, data: { connected: false, message: 'MCP Server not responding' } };
                } catch {
                    return { success: true, data: { connected: false, message: 'MCP Server not available' } };
                }
            },

            callTool: async (name: string, args: Record<string, unknown>) => {
                try {
                    const response = await fetch(`${getMCPServerUrl()}/api/tools/${name}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(args),
                    });
                    const result = await response.json();
                    return result;
                } catch (err) {
                    return { success: false, error: `MCP call failed: ${err instanceof Error ? err.message : 'Unknown error'}` };
                }
            },

            listTools: async () => {
                try {
                    const response = await fetch(`${getMCPServerUrl()}/api/tools`);
                    const data = await response.json();
                    return { success: true, data: { tools: data.tools || [] } };
                } catch {
                    return { success: true, data: { tools: [] } };
                }
            },
        },

        db: {
            createSession: async (title?: string) => {
                const sessions = getStorage<ChatSession[]>(STORAGE_KEYS.SESSIONS, []);
                const newSession: ChatSession = {
                    id: generateId(),
                    title: title || '新对话',
                    createdAt: Date.now(),
                    updatedAt: Date.now(),
                };
                sessions.unshift(newSession);
                setStorage(STORAGE_KEYS.SESSIONS, sessions);
                return { success: true, data: newSession };
            },

            getSessions: async () => {
                const sessions = getStorage<ChatSession[]>(STORAGE_KEYS.SESSIONS, []);
                return { success: true, data: sessions };
            },

            getMessages: async (sessionId: string) => {
                const allMessages = getStorage<Record<string, ChatMessage[]>>(STORAGE_KEYS.MESSAGES, {});
                const messages = allMessages[sessionId] || [];
                return { success: true, data: messages };
            },

            saveMessage: async (sessionId: string, role: string, content: string, toolCalls?: unknown, metadata?: unknown) => {
                const allMessages = getStorage<Record<string, ChatMessage[]>>(STORAGE_KEYS.MESSAGES, {});
                if (!allMessages[sessionId]) {
                    allMessages[sessionId] = [];
                }
                const message = {
                    id: generateId(),
                    role: role as ChatMessage['role'],
                    content,
                    createdAt: new Date(),
                    toolCalls: toolCalls || null,
                    metadata: metadata || null,
                } as ChatMessage & { toolCalls?: unknown; metadata?: unknown };
                allMessages[sessionId].push(message);
                setStorage(STORAGE_KEYS.MESSAGES, allMessages);
                return { success: true, data: { id: message.id } };
            },

            updateSessionTitle: async (sessionId: string, title: string) => {
                const sessions = getStorage<ChatSession[]>(STORAGE_KEYS.SESSIONS, []);
                const session = sessions.find(s => s.id === sessionId);
                if (session) {
                    session.title = title;
                    session.updatedAt = Date.now();
                    setStorage(STORAGE_KEYS.SESSIONS, sessions);
                }
                return { success: true };
            },

            deleteSession: async (sessionId: string) => {
                const sessions = getStorage<ChatSession[]>(STORAGE_KEYS.SESSIONS, []);
                const filtered = sessions.filter(s => s.id !== sessionId);
                setStorage(STORAGE_KEYS.SESSIONS, filtered);

                const allMessages = getStorage<Record<string, ChatMessage[]>>(STORAGE_KEYS.MESSAGES, {});
                delete allMessages[sessionId];
                setStorage(STORAGE_KEYS.MESSAGES, allMessages);

                return { success: true };
            },

            searchMessages: async (query: string) => {
                const allMessages = getStorage<Record<string, ChatMessage[]>>(STORAGE_KEYS.MESSAGES, {});
                const results: ChatMessage[] = [];
                Object.values(allMessages).forEach(messages => {
                    messages.forEach(message => {
                        if (message.content?.includes(query)) {
                            results.push(message);
                        }
                    });
                });
                return { success: true, data: results.slice(0, 50) };
            },
        },

        config: {
            get: async () => {
                const config = getStorage<UserConfig>(STORAGE_KEYS.CONFIG, {
                    aiModel: 'gpt-4',
                    riskTolerance: 'moderate',
                    investmentStyle: 'mixed',
                    preferredSectors: [],
                    theme: 'system',
                    notificationPreferences: {
                        enabled: true,
                        quietHours: [22, 23, 0, 1, 2, 3, 4, 5, 6],
                        maxDaily: 20,
                        channels: ['desktop'],
                    },
                });
                return { success: true, data: config };
            },

            save: async (config: Partial<UserConfig>) => {
                const existingConfig = getStorage<UserConfig>(STORAGE_KEYS.CONFIG, {} as UserConfig);
                const newConfig = { ...existingConfig, ...config };
                setStorage(STORAGE_KEYS.CONFIG, newConfig);
                return { success: true };
            },
        },

        watchlist: {
            get: async () => {
                const watchlist = getStorage<string[]>(STORAGE_KEYS.WATCHLIST, []);
                return { success: true, data: watchlist };
            },

            add: async (stockCode: string) => {
                const watchlist = getStorage<string[]>(STORAGE_KEYS.WATCHLIST, []);
                if (!watchlist.includes(stockCode)) {
                    watchlist.push(stockCode);
                    setStorage(STORAGE_KEYS.WATCHLIST, watchlist);
                }
                return { success: true };
            },

            remove: async (stockCode: string) => {
                const watchlist = getStorage<string[]>(STORAGE_KEYS.WATCHLIST, []);
                const filtered = watchlist.filter(c => c !== stockCode);
                setStorage(STORAGE_KEYS.WATCHLIST, filtered);
                return { success: true };
            },
            getMeta: async (stockCode?: string) => {
                const metaMap = getStorage<Record<string, any>>(STORAGE_KEYS.WATCHLIST_META, {});
                if (stockCode) {
                    const meta = metaMap[stockCode];
                    return { success: true, data: meta ? [meta] : [] };
                }
                return { success: true, data: Object.values(metaMap) };
            },
            saveMeta: async (meta: { stockCode: string; costPrice?: number; targetPrice?: number; stopLoss?: number; note?: string }) => {
                const metaMap = getStorage<Record<string, any>>(STORAGE_KEYS.WATCHLIST_META, {});
                metaMap[meta.stockCode] = {
                    ...metaMap[meta.stockCode],
                    ...meta,
                    updatedAt: Date.now(),
                };
                setStorage(STORAGE_KEYS.WATCHLIST_META, metaMap);
                return { success: true };
            },
            removeMeta: async (stockCode: string) => {
                const metaMap = getStorage<Record<string, any>>(STORAGE_KEYS.WATCHLIST_META, {});
                delete metaMap[stockCode];
                setStorage(STORAGE_KEYS.WATCHLIST_META, metaMap);
                return { success: true };
            },
        },

        behavior: {
            record: async (event: BehaviorEvent) => {
                const events = getStorage<Array<BehaviorEvent & { createdAt: number }>>(STORAGE_KEYS.BEHAVIORS, []);
                events.push({ ...event, createdAt: Date.now() });
                setStorage(STORAGE_KEYS.BEHAVIORS, events);
                return { success: true };
            },
            summary: async (days?: number) => {
                const periodDays = days ?? 30;
                const since = Date.now() - periodDays * 24 * 60 * 60 * 1000;
                const events = getStorage<Array<BehaviorEvent & { createdAt: number }>>(STORAGE_KEYS.BEHAVIORS, [])
                    .filter(event => event.createdAt >= since);

                const toolCounts: Record<string, number> = {};
                const stockCounts: Record<string, number> = {};
                const recentQueries: string[] = [];
                const activeHours = Array.from({ length: 24 }).map(() => 0);

                events.forEach(event => {
                    if (event.eventType === 'tool_call' && event.toolName) {
                        toolCounts[event.toolName] = (toolCounts[event.toolName] || 0) + 1;
                    }
                    if (event.stockCode) {
                        stockCounts[event.stockCode] = (stockCounts[event.stockCode] || 0) + 1;
                    }
                    if (event.eventType === 'query' && event.query) {
                        recentQueries.push(event.query);
                    }
                    const hour = new Date(event.createdAt).getHours();
                    activeHours[hour] += 1;
                });

                const topTools = Object.entries(toolCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([name, count]) => ({ name, count }));
                const topStocks = Object.entries(stockCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([code, count]) => ({ code, count }));

                return {
                    success: true,
                    data: {
                        periodDays,
                        totalEvents: events.length,
                        topTools,
                        topStocks,
                        recentQueries: recentQueries.slice(0, 5),
                        activeHours,
                    },
                };
            },
        },

        ai: {
            stream: async (messages: Array<{ role: string; content: string }>) => {
                const streamId = await realAIStream(messages);
                return { success: true, data: { streamId } };
            },

            cancel: async () => ({ success: true }),

            planTool: async (payload: { query: string; tools: Array<{ name: string; description?: string; inputSchema?: unknown }> }) => {
                const config = getApiConfigFromStorage();
                if (!config) {
                    return { success: false, error: '请先配置 API' };
                }
                const url = config.baseUrl.replace(/\/$/, '') + '/chat/completions';
                const prompt = [
                    '你是工具规划助手，仅输出 JSON。',
                    'JSON 结构: {"toolName": string|null, "args": object, "reason": string}',
                    `用户问题: ${payload.query}`,
                    `候选工具: ${JSON.stringify(payload.tools)}`,
                ].join('\n');

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${config.apiKey}`,
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            model: config.model,
                            messages: [
                                { role: 'system', content: '你是严格的 JSON 输出助手。' },
                                { role: 'user', content: prompt },
                            ],
                            temperature: 0.2,
                        }),
                    });

                    if (!response.ok) {
                        const errorText = await response.text();
                        return { success: false, error: `API 错误: ${response.status} - ${errorText}` };
                    }

                    const data = await response.json();
                    const text = data.choices?.[0]?.message?.content || '';
                    let parsed;
                    try {
                        parsed = JSON.parse(text);
                    } catch {
                        const match = text.match(/\{[\s\S]*\}/);
                        parsed = match ? JSON.parse(match[0]) : null;
                    }
                    return { success: true, data: parsed };
                } catch (err) {
                    return { success: false, error: String(err) };
                }
            },

            deepAnalysis: async (payload: { query: string; planTitle?: string; toolResults: Array<{ name: string; args: Record<string, unknown>; result: unknown }> }) => {
                const config = getApiConfigFromStorage();
                if (!config) {
                    return { success: false, error: '请先配置 API' };
                }
                const url = config.baseUrl.replace(/\/$/, '') + '/chat/completions';
                const prompt = buildDeepAnalysisPrompt(payload);

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${config.apiKey}`,
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            model: config.model,
                            messages: [
                                { role: 'system', content: '你是严格的中文金融分析助手。' },
                                { role: 'user', content: prompt },
                            ],
                            temperature: 0.2,
                            max_tokens: 1200,
                        }),
                    });

                    if (!response.ok) {
                        const errorText = await response.text();
                        return { success: false, error: `API 错误: ${response.status} - ${errorText}` };
                    }

                    const data = await response.json();
                    const text = data.choices?.[0]?.message?.content || '';
                    return { success: true, data: { content: text.trim() || '（未生成有效分析）' } };
                } catch (err) {
                    return { success: false, error: String(err) };
                }
            },

            onChunk: (handler: (payload: StreamChunkPayload) => void) => {
                eventHandlers.chunk.add(handler);
                return () => eventHandlers.chunk.delete(handler);
            },

            onDone: (handler: (payload: StreamDonePayload) => void) => {
                eventHandlers.done.add(handler);
                return () => eventHandlers.done.delete(handler);
            },

            onError: (handler: (payload: StreamErrorPayload) => void) => {
                eventHandlers.error.add(handler);
                return () => eventHandlers.error.delete(handler);
            },
        },

        trading: {
            logDecision: async (decision: any) => {
                const decisions = getStorage<any[]>(STORAGE_KEYS.DECISIONS, []);
                const id = generateId();
                decisions.push({ ...decision, id, createdAt: Date.now() });
                setStorage(STORAGE_KEYS.DECISIONS, decisions);
                return { success: true, data: { id } };
            },
            getDecisions: async (options?: any) => {
                const decisions = getStorage<any[]>(STORAGE_KEYS.DECISIONS, []);
                let filtered = decisions;
                if (options?.stockCode) {
                    filtered = filtered.filter(item => item.stockCode === options.stockCode);
                }
                if (options?.source) {
                    filtered = filtered.filter(item => item.source === options.source);
                }
                if (options?.limit) {
                    filtered = filtered.slice(0, options.limit);
                }
                return { success: true, data: filtered };
            },
            verifyDecision: async (decisionId: string, result: string, profitPercent?: number) => {
                const decisions = getStorage<any[]>(STORAGE_KEYS.DECISIONS, []);
                const updated = decisions.map(item =>
                    item.id === decisionId
                        ? { ...item, actualResult: result, profitPercent, verifiedAt: Date.now() }
                        : item
                );
                setStorage(STORAGE_KEYS.DECISIONS, updated);
                return { success: true };
            },
            getAccuracyStats: async () => {
                const decisions = getStorage<any[]>(STORAGE_KEYS.DECISIONS, []);
                const verified = decisions.filter(item => item.verifiedAt);
                const profit = verified.filter(item => item.actualResult === 'profit').length;
                const loss = verified.filter(item => item.actualResult === 'loss').length;
                const neutral = verified.filter(item => item.actualResult === 'neutral').length;
                const total = decisions.length;
                const verifiedCount = verified.length;
                return {
                    success: true,
                    data: {
                        totalDecisions: total,
                        verifiedDecisions: verifiedCount,
                        profitCount: profit,
                        lossCount: loss,
                        neutralCount: neutral,
                        accuracyRate: verifiedCount > 0 ? (profit / verifiedCount) * 100 : 0,
                        avgProfitPercent: verifiedCount > 0
                            ? verified.reduce((sum, item) => sum + (item.profitPercent || 0), 0) / verifiedCount
                            : 0,
                        byDecisionType: {},
                    },
                };
            },
            generateReport: async (options: any) => {
                const decisions = getStorage<any[]>(STORAGE_KEYS.DECISIONS, []);
                const startDate = options?.startDate || 0;
                const endDate = options?.endDate || Date.now();
                const filtered = decisions.filter(item => item.createdAt >= startDate && item.createdAt <= endDate);
                return {
                    success: true,
                    data: {
                        period: { start: startDate, end: endDate },
                        decisions: filtered,
                        insights: [],
                    },
                };
            },
            createPlan: async (plan: any) => {
                const plans = getStorage<any[]>(STORAGE_KEYS.TRADE_PLANS, []);
                const id = generateId();
                const now = Date.now();
                const newPlan = {
                    id,
                    createdAt: now,
                    updatedAt: now,
                    status: 'planned',
                    ...plan,
                };
                plans.unshift(newPlan);
                setStorage(STORAGE_KEYS.TRADE_PLANS, plans);
                return { success: true, data: { id } };
            },
            getPlans: async (options?: any) => {
                const plans = getStorage<any[]>(STORAGE_KEYS.TRADE_PLANS, []);
                let filtered = plans;
                if (options?.stockCode) {
                    filtered = filtered.filter(item => item.stockCode === options.stockCode);
                }
                if (options?.status) {
                    filtered = filtered.filter(item => item.status === options.status);
                }
                if (options?.limit) {
                    filtered = filtered.slice(0, options.limit);
                }
                return { success: true, data: filtered };
            },
            updatePlan: async (planId: string, updates: any) => {
                const plans = getStorage<any[]>(STORAGE_KEYS.TRADE_PLANS, []);
                const updated = plans.map(item =>
                    item.id === planId
                        ? { ...item, ...updates, updatedAt: Date.now() }
                        : item
                );
                setStorage(STORAGE_KEYS.TRADE_PLANS, updated);
                return { success: true };
            },
            removePlan: async (planId: string) => {
                const plans = getStorage<any[]>(STORAGE_KEYS.TRADE_PLANS, []);
                setStorage(STORAGE_KEYS.TRADE_PLANS, plans.filter(item => item.id !== planId));
                return { success: true };
            },
            setPlanStatus: async (planId: string, status: string) => {
                const plans = getStorage<any[]>(STORAGE_KEYS.TRADE_PLANS, []);
                const updated = plans.map(item =>
                    item.id === planId
                        ? { ...item, status, updatedAt: Date.now() }
                        : item
                );
                setStorage(STORAGE_KEYS.TRADE_PLANS, updated);
                return { success: true };
            },
        },

        proxy: {
            request: async (url: string, options?: unknown) => {
                const opts = options as { method?: string; headers?: Record<string, string>; body?: string } | undefined;
                try {
                    const response = await fetch(url, {
                        method: opts?.method || 'GET',
                        headers: opts?.headers,
                        body: opts?.body,
                    });
                    const text = await response.text();
                    let data: unknown;
                    try {
                        data = JSON.parse(text);
                    } catch {
                        data = text;
                    }
                    return { success: true, data, status: response.status, statusText: response.statusText };
                } catch (err) {
                    return { success: false, error: String(err), status: 0, statusText: 'Error', data: undefined };
                }
            },
        },

        platform: 'web',
    };
};
