/**
 * API 配置服务
 * 管理 API URL、Key、模型列表的存储和验证
 */

// 配置存储 key
const CONFIG_STORAGE_KEY = 'aethertrade_api_config';

// API 配置接口
export interface ApiConfig {
    baseUrl: string;
    apiKey: string;
    model: string;
    models: string[];
    lastTested: string | null;
    isValid: boolean;
}

// 默认配置
const DEFAULT_CONFIG: ApiConfig = {
    baseUrl: '',
    apiKey: '',
    model: '',
    models: [],
    lastTested: null,
    isValid: false,
};

/**
 * 获取保存的配置
 */
export function getApiConfig(): ApiConfig {
    try {
        const stored = localStorage.getItem(CONFIG_STORAGE_KEY);
        if (stored) {
            return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
        }
    } catch (e) {
        console.error('[ConfigService] Failed to load config:', e);
    }
    return DEFAULT_CONFIG;
}

/**
 * 保存配置
 */
export function saveApiConfig(config: Partial<ApiConfig>): void {
    try {
        const current = getApiConfig();
        const updated = { ...current, ...config };
        localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(updated));
    } catch (e) {
        console.error('[ConfigService] Failed to save config:', e);
    }
}

/**
 * 检测可用模型（调用 OpenAI 兼容的 /v1/models 接口）
 */
export async function fetchAvailableModels(baseUrl: string, apiKey: string): Promise<string[]> {
    if (!baseUrl || !apiKey) {
        throw new Error('请填写 API URL 和 API Key');
    }

    // 规范化 URL
    const cleanUrl = baseUrl.replace(/\/$/, '');
    // 智能添加 /v1 后缀 (如果是 OpenAI 兼容接口通常需要)
    const url = cleanUrl.endsWith('/v1') ? cleanUrl : `${cleanUrl}/v1`;
    const modelsUrl = `${url}/models`;

    try {
        let data: any;

        // 优先使用 Electron 代理请求以避免 CORS
        if (window.electronAPI?.proxy) {
            const result = await window.electronAPI.proxy.request(modelsUrl, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json',
                },
            });

            if (!result.success) {
                const errorText = typeof result.data === 'string' ? result.data : JSON.stringify(result.data);
                throw new Error(`API 请求失败: ${result.status} - ${errorText}`);
            }
            data = result.data;
        } else {
            // Web 环境回退
            const response = await fetch(modelsUrl, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`API 请求失败: ${response.status} - ${errorText}`);
            }
            data = await response.json();
        }

        // OpenAI 格式: { data: [{ id: 'model-name', ... }] }
        if (data.data && Array.isArray(data.data)) {
            return data.data.map((m: { id: string }) => m.id).sort();
        }

        // 其他格式尝试
        if (Array.isArray(data)) {
            return data.map((m: { id?: string; name?: string }) => m.id || m.name || String(m)).sort();
        }

        throw new Error('无法解析模型列表');
    } catch (e) {
        if (e instanceof Error) {
            throw e;
        }
        throw new Error('网络请求失败');
    }
}

/**
 * 测试 API 连接
 */
export async function testApiConnection(
    baseUrl: string,
    apiKey: string,
    model: string
): Promise<{ success: boolean; message: string; response?: string }> {
    if (!baseUrl || !apiKey || !model) {
        return { success: false, message: '请填写完整的配置信息' };
    }

    const cleanUrl = baseUrl.replace(/\/$/, '');
    const url = cleanUrl.endsWith('/v1') ? cleanUrl : `${cleanUrl}/v1`;
    const chatUrl = `${url}/chat/completions`;

    try {
        let reply = '';
        const body = JSON.stringify({
            model: model,
            messages: [
                { role: 'user', content: 'Hello, please respond with "API connection successful!"' }
            ],
            max_tokens: 50,
        });

        if (window.electronAPI?.proxy) {
            const result = await window.electronAPI.proxy.request(chatUrl, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json',
                },
                body: body,
            });

            if (!result.success) {
                const errorText = typeof result.data === 'string' ? result.data : JSON.stringify(result.data);
                return { success: false, message: `API 错误: ${result.status} - ${errorText}` };
            }

            const data = result.data as any;
            reply = data.choices?.[0]?.message?.content || 'No response';
        } else {
            const response = await fetch(chatUrl, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json',
                },
                body: body,
            });

            if (!response.ok) {
                const errorText = await response.text();
                return { success: false, message: `API 错误: ${response.status} - ${errorText}` };
            }

            const data = await response.json();
            reply = data.choices?.[0]?.message?.content || 'No response';
        }

        return {
            success: true,
            message: '连接成功！',
            response: reply,
        };
    } catch (e) {
        return {
            success: false,
            message: e instanceof Error ? e.message : '网络请求失败',
        };
    }
}

/**
 * 使用配置的 API 进行聊天
 */
export async function chatWithApi(
    messages: Array<{ role: string; content: string }>,
    onChunk?: (text: string) => void
): Promise<string> {
    const config = getApiConfig();

    if (!config.isValid || !config.baseUrl || !config.apiKey || !config.model) {
        throw new Error('请先配置 API 设置');
    }

    const cleanUrl = config.baseUrl.replace(/\/$/, '');
    const url = cleanUrl.endsWith('/v1') ? cleanUrl : `${cleanUrl}/v1`;
    const chatUrl = `${url}/chat/completions`;

    if (window.electronAPI?.proxy) {
        const result = await window.electronAPI.proxy.request(chatUrl, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${config.apiKey}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: config.model,
                messages: messages,
                stream: false, // 代理模式暂不支持 Stream (需要 SSE 代理，这里先用普通请求)
            }),
        });

        if (!result.success) {
            const errorText = typeof result.data === 'string' ? result.data : JSON.stringify(result.data);
            throw new Error(`API 错误: ${result.status} - ${errorText}`);
        }

        const data = result.data as any;
        return data.choices?.[0]?.message?.content || '';
    }

    // Web 环境或非代理模式 (含 Stream 支持逻辑)
    const response = await fetch(chatUrl, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${config.apiKey}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            model: config.model,
            messages: messages,
            stream: !!onChunk,
        }),
    });

    // ... (保持原有的 Stream 处理逻辑)
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API 错误: ${response.status} - ${errorText}`);
    }

    if (onChunk && response.body) {
        // ...流式处理逻辑保持不变...
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(line => line.startsWith('data: '));
            for (const line of lines) {
                const data = line.slice(6);
                if (data === '[DONE]') continue;
                try {
                    const json = JSON.parse(data);
                    const text = json.choices?.[0]?.delta?.content || '';
                    if (text) {
                        fullText += text;
                        onChunk(text);
                    }
                } catch { }
            }
        }
        return fullText;
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content || '';
}
