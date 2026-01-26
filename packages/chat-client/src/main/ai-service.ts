/**
 * AI 服务层 - 支持流式响应
 */

import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import { getConfig, getWatchlist, getBehaviorSummary } from './db/user-store';

export type AIMessage = {
    role: 'user' | 'assistant' | 'system';
    content: string;
};

export type AIStream = {
    iterator: AsyncGenerator<string>;
    cancel: () => void;
};

export type ToolCandidate = {
    name: string;
    description?: string;
    inputSchema?: Record<string, unknown>;
};

export type ToolPlan = {
    toolName?: string | null;
    args?: Record<string, unknown>;
    reason?: string;
};

export type DeepAnalysisPayload = {
    query: string;
    planTitle?: string;
    toolResults: Array<{
        name: string;
        args: Record<string, unknown>;
        result: unknown;
    }>;
};

const buildSystemPrompt = (): string => {
    const config = getConfig();
    const watchlist = getWatchlist();
    const summary = getBehaviorSummary(30);

    const lines: string[] = [
        '你是专业的股票AI助手，请用简洁、结构化的中文回答。',
        '回答包含结论、要点、风险提示、下一步建议。',
    ];

    lines.push(`用户风险偏好: ${config.riskTolerance}`);
    lines.push(`投资风格: ${config.investmentStyle}`);
    if (config.preferredSectors.length > 0) {
        lines.push(`关注板块: ${config.preferredSectors.join(', ')}`);
    }
    if (watchlist.length > 0) {
        lines.push(`自选股: ${watchlist.slice(0, 10).join(', ')}`);
    }

    if (summary.topTools.length > 0) {
        const tools = summary.topTools.map(t => `${t.name}(${t.count})`).join(', ');
        lines.push(`常用工具: ${tools}`);
    }

    return lines.join('\n');
};

const normalizeMessages = (messages: AIMessage[]): { role: 'user' | 'assistant'; content: string }[] => {
    return messages
        .filter(message => message.role !== 'system')
        .map(message => ({
            role: message.role === 'assistant' ? 'assistant' : 'user',
            content: message.content,
        }));
};

const getOpenAIClient = (apiKey?: string, baseUrl?: string): OpenAI => {
    const key = apiKey || process.env.OPENAI_API_KEY || '';
    let baseURL = baseUrl || process.env.OPENAI_BASE_URL || undefined;

    // 自动修正 URL：如果不是默认的 OpenAI API 且没有 /v1 后缀，则尝试添加
    if (baseURL && !baseURL.includes('api.openai.com') && !baseURL.endsWith('/v1')) {
        baseURL = baseURL.replace(/\/$/, '') + '/v1';
    }

    return new OpenAI({ apiKey: key, baseURL });
};

const getAnthropicClient = (apiKey?: string): Anthropic => {
    const key = apiKey || process.env.ANTHROPIC_API_KEY || '';
    return new Anthropic({ apiKey: key });
};

const buildMissingKeyStream = (provider: 'OpenAI' | 'Anthropic'): AIStream => ({
    iterator: (async function* () {
        yield `⚠️ 未检测到 ${provider} API Key，请在设置中填写 API Key 或配置环境变量。`;
    })(),
    cancel: () => { },
});

const parseJsonFromText = (text: string): ToolPlan | null => {
    const direct = text.trim();
    try {
        return JSON.parse(direct);
    } catch {
        // fallthrough
    }

    const match = direct.match(/\{[\s\S]*\}/);
    if (match) {
        try {
            return JSON.parse(match[0]);
        } catch {
            return null;
        }
    }

    return null;
};

const buildPlannerPrompt = (query: string, tools: ToolCandidate[]): string => {
    const toolSummaries = tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        inputSchema: tool.inputSchema,
    }));

    return [
        '你是工具规划助手。请根据用户问题选择最合适的工具。',
        '仅输出 JSON，不要包含其他文字。',
        'JSON 结构: {"toolName": string|null, "args": object, "reason": string}',
        '如果没有合适工具，toolName 返回 null。',
        `用户问题: ${query}`,
        `候选工具: ${JSON.stringify(toolSummaries)}`,
    ].join('\n');
};

const truncateText = (text: string, maxChars: number): string => {
    if (text.length <= maxChars) return text;
    return `${text.slice(0, maxChars)}\n...（已截断）`;
};

const buildDeepAnalysisPrompt = (payload: DeepAnalysisPayload): string => {
    const rawResults = JSON.stringify(payload.toolResults, null, 2);
    const limitedResults = truncateText(rawResults, 12000);
    return [
        '你是股票AI深度分析师，请基于工具结果输出专业分析。',
        '必须输出结构化内容，包含：结论、关键数据、风险提示、策略建议、后续行动。',
        '如数据不足请明确说明并给出补充建议。',
        `用户问题: ${payload.query}`,
        `分析主题: ${payload.planTitle || '未命名分析'}`,
        `工具结果(JSON): ${limitedResults}`,
    ].join('\n');
};

export async function planToolCall(query: string, tools: ToolCandidate[]): Promise<ToolPlan> {
    const config = getConfig();
    const model = config.aiModel;

    if (!tools.length) {
        return { toolName: null, reason: '无候选工具' };
    }

    if (model === 'local') {
        return { toolName: null, reason: '本地模型不支持工具规划' };
    }

    if (model === 'claude') {
        const apiKey = config.apiKey || process.env.ANTHROPIC_API_KEY;
        if (!apiKey) {
            return { toolName: null, reason: '缺少 Anthropic API Key' };
        }
        const client = getAnthropicClient(apiKey);
        const anthropicModel = config.apiModel || process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-20241022';
        const prompt = buildPlannerPrompt(query, tools);
        const response = await client.messages.create({
            model: anthropicModel,
            max_tokens: 512,
            system: '你是严格的 JSON 输出助手。',
            messages: [{ role: 'user', content: prompt }],
        });

        const text = response.content
            .map(block => (block.type === 'text' ? block.text : ''))
            .join('\n')
            .trim();
        return parseJsonFromText(text) || { toolName: null, reason: '无法解析模型输出' };
    }

    const apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    if (!apiKey) {
        return { toolName: null, reason: '缺少 OpenAI API Key' };
    }
    const client = getOpenAIClient(apiKey, config.apiBaseUrl);
    const openaiModel = config.apiModel || process.env.OPENAI_MODEL || 'gpt-4o';
    const prompt = buildPlannerPrompt(query, tools);
    const response = await client.chat.completions.create({
        model: openaiModel,
        messages: [
            { role: 'system', content: '你是严格的 JSON 输出助手。' },
            { role: 'user', content: prompt },
        ],
        temperature: 0.2,
    });

    const text = response.choices?.[0]?.message?.content || '';
    return parseJsonFromText(text) || { toolName: null, reason: '无法解析模型输出' };
}

export async function generateDeepAnalysis(payload: DeepAnalysisPayload): Promise<{ content: string }> {
    const config = getConfig();
    const model = config.aiModel;
    const prompt = buildDeepAnalysisPrompt(payload);

    if (model === 'local') {
        return { content: '⚠️ 本地模型尚未配置，无法生成深度分析。' };
    }

    if (model === 'claude') {
        const apiKey = config.apiKey || process.env.ANTHROPIC_API_KEY;
        if (!apiKey) {
            return { content: '⚠️ 未检测到 Anthropic API Key，无法生成深度分析。' };
        }
        const client = getAnthropicClient(apiKey);
        const anthropicModel = config.apiModel || process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-20241022';
        const response = await client.messages.create({
            model: anthropicModel,
            max_tokens: 1200,
            system: '你是严格的中文金融分析助手。',
            messages: [{ role: 'user', content: prompt }],
        });
        const text = response.content
            .map(block => (block.type === 'text' ? block.text : ''))
            .join('\n')
            .trim();
        return { content: text || '（未生成有效分析）' };
    }

    const apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    if (!apiKey) {
        return { content: '⚠️ 未检测到 OpenAI API Key，无法生成深度分析。' };
    }
    const client = getOpenAIClient(apiKey, config.apiBaseUrl);
    const openaiModel = config.apiModel || process.env.OPENAI_MODEL || 'gpt-4o';
    const response = await client.chat.completions.create({
        model: openaiModel,
        messages: [
            { role: 'system', content: '你是严格的中文金融分析助手。' },
            { role: 'user', content: prompt },
        ],
        temperature: 0.2,
        max_tokens: 1200,
    });
    const text = response.choices?.[0]?.message?.content || '';
    return { content: text.trim() || '（未生成有效分析）' };
}

export async function createAIStream(messages: AIMessage[]): Promise<AIStream> {
    const config = getConfig();
    const systemPrompt = buildSystemPrompt();
    const model = config.aiModel;
    let cancelled = false;

    if (model === 'local') {
        return {
            iterator: (async function* () {
                yield '⚠️ 本地模型尚未配置，请在设置中选择 Claude 或 GPT-4 并提供 API Key。';
            })(),
            cancel: () => {
                cancelled = true;
            },
        };
    }

    if (model === 'claude') {
        const apiKey = config.apiKey || process.env.ANTHROPIC_API_KEY;
        if (!apiKey) {
            return buildMissingKeyStream('Anthropic');
        }
        const client = getAnthropicClient(apiKey);
        const anthropicModel = config.apiModel || process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-20241022';
        const stream = await client.messages.create({
            model: anthropicModel,
            max_tokens: 1024,
            system: systemPrompt,
            messages: normalizeMessages(messages),
            stream: true,
        });

        return {
            iterator: (async function* () {
                for await (const event of stream as any) {
                    if (cancelled) break;
                    if (event.type === 'content_block_delta' && event.delta?.text) {
                        yield event.delta.text as string;
                    }
                }
            })(),
            cancel: () => {
                cancelled = true;
            },
        };
    }

    const apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    if (!apiKey) {
        return buildMissingKeyStream('OpenAI');
    }
    const client = getOpenAIClient(apiKey, config.apiBaseUrl);
    const openaiModel = config.apiModel || process.env.OPENAI_MODEL || 'gpt-4o';
    const stream = await client.chat.completions.create({
        model: openaiModel,
        messages: [
            { role: 'system', content: systemPrompt },
            ...messages,
        ],
        stream: true,
    });

    return {
        iterator: (async function* () {
            for await (const chunk of stream) {
                if (cancelled) break;
                // Debug log for empty content
                if (!chunk.choices?.[0]?.delta?.content) {
                    // check for reasoning_content (Deepseek style)
                    const deltaAny = chunk.choices?.[0]?.delta as any;
                    if (deltaAny?.reasoning_content) {
                        yield deltaAny.reasoning_content;
                        continue;
                    }
                    console.log('[AI Stream] Received non-content chunk:', JSON.stringify(chunk));
                }
                const delta = chunk.choices?.[0]?.delta?.content;
                if (delta) {
                    yield delta;
                }
            }
        })(),
        cancel: () => {
            cancelled = true;
        },
    };
}
