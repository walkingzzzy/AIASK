/**
 * 个人中心组件
 * 包含 5 个 Tab：概览、画像、持仓、统计、设置
 * 采用 AetherTrade 风格的高级视觉设计
 */

import React, { useState, useEffect, useRef } from 'react';
import {
    getApiConfig,
    saveApiConfig,
    fetchAvailableModels,
    testApiConnection,
    type ApiConfig,
} from '../../api/config-service';

// MCP 服务器地址
const DEFAULT_MCP_SERVER_URL = 'http://localhost:9898';

// Tab 类型
type TabType = 'overview' | 'profile' | 'portfolio' | 'stats' | 'settings';

interface PersonalCenterProps {
    isOpen: boolean;
    onClose: () => void;
    onSave?: (config: ApiConfig) => void;
}

// MCP 工具类型
interface MCPToolSchema {
    type?: string;
    description?: string;
    default?: unknown;
    enum?: Array<string | number>;
    properties?: Record<string, MCPToolSchema>;
    required?: string[];
    items?: MCPToolSchema;
    anyOf?: MCPToolSchema[];
    oneOf?: MCPToolSchema[];
    allOf?: MCPToolSchema[];
}

interface MCPTool {
    name: string;
    description: string;
    category?: string;
    requiresConfirmation?: boolean;
    inputSchema?: MCPToolSchema;
}

interface MCPSkill {
    id: string;
    name: string;
    description?: string;
    category?: string;
}

// 概览数据类型
interface OverviewData {
    watchlist: Array<{ code: string; name: string; change: number }>;
    totalValue: number;
    todayPnL: number;
    todayPnLPercent: number;
    aiAccuracy: number;
    totalDecisions: number;
    positionCount: number;
    winRate: number;
}

// 持仓数据类型
interface PositionData {
    code: string;
    name: string;
    quantity: number;
    costPrice: number;
    currentPrice: number;
    profit: number;
    profitPercent: string;
    trend?: number[]; // 最近7天趋势数据
}

// 统计数据类型
interface StatsData {
    winRate: number | null;
    plRatio: number | null;
    avgHoldingDays: number | null;
    totalReturn: number | null;
    maxDrawdown: number | null;
    sharpe: number | null;
    benchmarkReturn: number | null; // 沪深300对比
}

// 用户画像参数
interface ProfileParams {
    stopLoss: number;
    takeProfit: number;
    maxPosition: number;
    riskScore: number;
    riskType: string;
    experience: string;
    investPeriod: string;
    style: string;
}

type MCPFormValue = string;

const unwrapSchema = (schema?: MCPToolSchema): MCPToolSchema | undefined => {
    if (!schema) return undefined;
    if (schema.anyOf && schema.anyOf.length > 0) return unwrapSchema(schema.anyOf[0]);
    if (schema.oneOf && schema.oneOf.length > 0) return unwrapSchema(schema.oneOf[0]);
    if (schema.allOf && schema.allOf.length > 0) return unwrapSchema(schema.allOf[0]);
    return schema;
};

const resolveSchemaType = (schema?: MCPToolSchema): string => {
    const normalized = unwrapSchema(schema);
    if (!normalized) return 'string';
    if (normalized.enum && normalized.enum.length > 0) return 'enum';
    if (normalized.type) return normalized.type;
    if (normalized.items) return 'array';
    if (normalized.properties) return 'object';
    return 'string';
};

const formatDefaultValue = (value: unknown): string => {
    if (value === undefined || value === null) return '';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return String(value);
    if (typeof value === 'string') return value;
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
};

const buildDefaultFormValues = (schema?: MCPToolSchema): Record<string, MCPFormValue> => {
    const values: Record<string, MCPFormValue> = {};
    const normalized = unwrapSchema(schema);
    if (!normalized?.properties) return values;
    Object.entries(normalized.properties).forEach(([key, propSchema]) => {
        const resolved = unwrapSchema(propSchema);
        if (resolved && resolved.default !== undefined) {
            values[key] = formatDefaultValue(resolved.default);
            return;
        }
        values[key] = '';
    });
    return values;
};

const parseEnumValue = (raw: string, schema?: MCPToolSchema): unknown => {
    if (!schema?.enum) return raw;
    const numericEnums = schema.enum.filter((item): item is number => typeof item === 'number');
    if (numericEnums.length > 0) {
        const numeric = Number(raw);
        if (!Number.isNaN(numeric) && numericEnums.includes(numeric)) {
            return numeric;
        }
    }
    return raw;
};

const parsePrimitiveValue = (raw: string, schema?: MCPToolSchema): { value?: unknown; error?: string } => {
    const normalized = unwrapSchema(schema);
    const type = resolveSchemaType(normalized);
    if (type === 'number' || type === 'integer') {
        const num = Number(raw);
        if (!Number.isFinite(num)) {
            return { error: '请输入有效数字' };
        }
        if (type === 'integer' && !Number.isInteger(num)) {
            return { error: '请输入整数' };
        }
        return { value: num };
    }
    if (type === 'boolean') {
        if (raw === 'true') return { value: true };
        if (raw === 'false') return { value: false };
        return { error: '请输入 true 或 false' };
    }
    if (type === 'enum') {
        return { value: parseEnumValue(raw, normalized) };
    }
    return { value: raw };
};

const parseArrayValue = (raw: string, schema?: MCPToolSchema): { value?: unknown; error?: string } => {
    const trimmed = raw.trim();
    if (!trimmed) return { value: undefined };
    if (trimmed.startsWith('[')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (Array.isArray(parsed)) {
                return { value: parsed };
            }
            return { error: '请输入数组 JSON' };
        } catch {
            return { error: '数组 JSON 解析失败' };
        }
    }
    const itemSchema = unwrapSchema(schema?.items);
    const itemType = resolveSchemaType(itemSchema);
    if (itemType === 'object') {
        return { error: '对象数组请使用 JSON 格式' };
    }
    const items = trimmed.split(',').map(item => item.trim()).filter(Boolean);
    const parsedItems: unknown[] = [];
    for (const item of items) {
        const parsed = parsePrimitiveValue(item, itemSchema);
        if (parsed.error) {
            return parsed;
        }
        if (parsed.value !== undefined) {
            parsedItems.push(parsed.value);
        }
    }
    return { value: parsedItems };
};

const parseInputValue = (raw: string, schema?: MCPToolSchema): { value?: unknown; error?: string } => {
    const normalized = unwrapSchema(schema);
    const type = resolveSchemaType(normalized);
    const trimmed = raw.trim();
    if (!trimmed) return { value: undefined };
    if (type === 'array') return parseArrayValue(raw, normalized);
    if (type === 'object') {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                return { value: parsed };
            }
            return { error: '请输入 JSON 对象' };
        } catch {
            return { error: 'JSON 解析失败' };
        }
    }
    if (type === 'enum') {
        return { value: parseEnumValue(trimmed, normalized) };
    }
    return parsePrimitiveValue(trimmed, normalized);
};

const buildArgsFromSchema = (
    schema: MCPToolSchema | undefined,
    values: Record<string, MCPFormValue>,
): { args: Record<string, unknown>; errors: Record<string, string> } => {
    const args: Record<string, unknown> = {};
    const errors: Record<string, string> = {};
    const normalized = unwrapSchema(schema);
    if (!normalized?.properties) return { args, errors };
    const required = normalized.required || [];
    Object.entries(normalized.properties).forEach(([key, propSchema]) => {
        const raw = values[key] ?? '';
        const parsed = parseInputValue(raw, propSchema);
        if (parsed.error) {
            errors[key] = parsed.error;
            return;
        }
        if (parsed.value === undefined) {
            if (required.includes(key)) {
                errors[key] = '必填项不能为空';
            }
            return;
        }
        args[key] = parsed.value;
    });
    return { args, errors };
};

const PersonalCenter: React.FC<PersonalCenterProps> = ({ isOpen, onClose, onSave }) => {
    const isWeb = typeof window !== 'undefined' && window.electronAPI?.platform === 'web';
    // Tab 状态
    const [activeTab, setActiveTab] = useState<TabType>('overview');

    // 设置相关状态
    const [baseUrl, setBaseUrl] = useState('');
    const [apiKey, setApiKey] = useState('');
    const [model, setModel] = useState('');
    const [models, setModels] = useState<string[]>([]);
    const [isLoadingModels, setIsLoadingModels] = useState(false);
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [error, setError] = useState('');
    const [theme, setTheme] = useState<'dark' | 'light' | 'auto'>('dark');

    // MCP 状态
    const [mcpConnected, setMcpConnected] = useState(false);
    const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);
    const [mcpSkills, setMcpSkills] = useState<MCPSkill[]>([]);
    const [mcpLoading, setMcpLoading] = useState(false);
    const [showToolList, setShowToolList] = useState(false);
    const [showSkillList, setShowSkillList] = useState(false);
    const [mcpUrl, setMcpUrl] = useState(DEFAULT_MCP_SERVER_URL);
    const [selectedToolName, setSelectedToolName] = useState('');
    const [toolFormValues, setToolFormValues] = useState<Record<string, MCPFormValue>>({});
    const [toolRawArgs, setToolRawArgs] = useState('');
    const [toolFormErrors, setToolFormErrors] = useState<Record<string, string>>({});
    const [toolResult, setToolResult] = useState<unknown>(null);
    const [toolRunError, setToolRunError] = useState<string | null>(null);
    const [toolRunning, setToolRunning] = useState(false);

    // 数据状态
    const [overviewData, setOverviewData] = useState<OverviewData | null>(null);
    const [positions, setPositions] = useState<PositionData[]>([]);
    const [portfolioSummary, setPortfolioSummary] = useState<{ totalValue: number; totalProfit: number; profitPercent: number } | null>(null);
    const [statsData, setStatsData] = useState<StatsData | null>(null);
    const [dataLoading, setDataLoading] = useState(false);

    // 画像参数状态
    const [profileParams, setProfileParams] = useState<ProfileParams>({
        stopLoss: 8,
        takeProfit: 15,
        maxPosition: 20,
        riskScore: 50,
        riskType: '平衡型',
        experience: '中级',
        investPeriod: '中期',
        style: '平衡'
    });

    // Canvas refs for charts
    const overviewChartRef = useRef<HTMLCanvasElement>(null);
    const statsChartRef = useRef<HTMLCanvasElement>(null);
    const selectedTool = mcpTools.find(tool => tool.name === selectedToolName);

    // 加载配置
    useEffect(() => {
        if (!isOpen) return;
        const loadConfig = async () => {
            if (isWeb) {
                const config = getApiConfig();
                setBaseUrl(config.baseUrl);
                setApiKey(config.apiKey);
                setModel(config.model);
                setModels(config.models);
                const storedProfile = localStorage.getItem('aethertrade_profile_params');
                if (storedProfile) {
                    try {
                        setProfileParams(JSON.parse(storedProfile));
                    } catch {
                        // ignore parse errors
                    }
                }
                setMcpUrl(localStorage.getItem('aethertrade_mcp_url') || DEFAULT_MCP_SERVER_URL);
            } else {
                const result = await window.electronAPI.config.get();
                if (result.success && result.data) {
                    const config = result.data;
                    setBaseUrl(config.apiBaseUrl || '');
                    setApiKey(config.apiKey || '');
                    setModel(config.apiModel || '');
                    setModels([]);
                    if (config.profileParams) {
                        setProfileParams(config.profileParams);
                    }
                }
            }

            setTestResult(null);
            setError('');

            // 检查 MCP 连接
            checkMCPConnection();

            // 加载数据
            loadData();
        };

        loadConfig().catch(err => {
            console.error('[PersonalCenter] Load config error:', err);
        });
    }, [isOpen, isWeb]);

    useEffect(() => {
        if (mcpTools.length === 0) return;
        if (!selectedToolName) {
            setSelectedToolName(mcpTools[0].name);
            return;
        }
        if (!mcpTools.some(tool => tool.name === selectedToolName)) {
            setSelectedToolName('');
        }
    }, [mcpTools, selectedToolName]);

    useEffect(() => {
        if (!selectedTool) {
            setToolFormValues({});
            setToolRawArgs('');
            setToolFormErrors({});
            setToolResult(null);
            setToolRunError(null);
            return;
        }
        setToolFormValues(buildDefaultFormValues(selectedTool.inputSchema));
        setToolRawArgs('');
        setToolFormErrors({});
        setToolResult(null);
        setToolRunError(null);
    }, [selectedTool?.name]);

    useEffect(() => {
        if (!overviewData) return;
        const trend = buildCompositeTrend(positions);
        if (trend.length > 1) {
            drawSparkline(overviewChartRef.current, trend, 'rgba(94, 138, 250, 0.9)');
        }
    }, [overviewData, positions]);

    useEffect(() => {
        if (!statsData) return;
        const trend = buildPriceTrend(0, statsData.totalReturn || 0, 7);
        if (trend.length > 1) {
            drawSparkline(statsChartRef.current, trend, 'rgba(52, 199, 89, 0.9)');
        }
    }, [statsData]);

    // 检查 MCP 连接
    const checkMCPConnection = async () => {
        setMcpLoading(true);
        try {
            if (isWeb) {
                const healthRes = await fetch(`${mcpUrl}/health`);
                if (healthRes.ok) {
                    setMcpConnected(true);
                    // 获取工具列表
                    const toolsRes = await fetch(`${mcpUrl}/api/tools`);
                    if (toolsRes.ok) {
                        const data = await toolsRes.json();
                        setMcpTools(data.tools || []);
                    }
                    const skillsRes = await callMCPTool('list_skills', {});
                    if (skillsRes.success && skillsRes.data && typeof skillsRes.data === 'object' && 'skills' in skillsRes.data) {
                        const skillData = skillsRes.data as { skills?: MCPSkill[] };
                        setMcpSkills(skillData.skills || []);
                    }
                } else {
                    setMcpConnected(false);
                    setMcpTools([]);
                    setMcpSkills([]);
                }
                return;
            }

            const initRes = await window.electronAPI.mcp.init();
            const toolsRes = await window.electronAPI.mcp.listTools();
            if (initRes.success && toolsRes.success && toolsRes.data && typeof toolsRes.data === 'object' && 'tools' in (toolsRes.data as object)) {
                setMcpConnected(true);
                const data = toolsRes.data as { tools: MCPTool[] };
                setMcpTools(data.tools || []);
                const skillsRes = await window.electronAPI.mcp.callTool('list_skills', {});
                if (skillsRes.success && skillsRes.data && typeof skillsRes.data === 'object' && 'skills' in skillsRes.data) {
                    const skillData = skillsRes.data as { skills?: MCPSkill[] };
                    setMcpSkills(skillData.skills || []);
                }
            } else {
                setMcpConnected(false);
                setMcpTools([]);
                setMcpSkills([]);
            }
        } catch {
            setMcpConnected(false);
            setMcpTools([]);
            setMcpSkills([]);
        } finally {
            setMcpLoading(false);
        }
    };

    // 调用 MCP 工具
    const callMCPTool = async (name: string, args: Record<string, unknown> = {}) => {
        try {
            if (isWeb) {
                const res = await fetch(`${mcpUrl}/api/tools/${name}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(args),
                });
                return await res.json();
            }
            return await window.electronAPI.mcp.callTool(name, args);
        } catch {
            return { success: false, error: 'MCP 调用失败' };
        }
    };

    const invokeMCPTool = async (name: string, args: Record<string, unknown> = {}) => {
        const result = await callMCPTool(name, args);
        if (!result?.requiresConfirmation) return result;
        const confirmation = result.confirmation || {
            toolName: (result as { toolName?: string }).toolName,
            arguments: (result as { arguments?: Record<string, unknown> }).arguments,
            message: (result as { message?: string }).message,
        };
        const message = confirmation?.message || `工具 ${name} 需要确认执行`;
        if (!window.confirm(message)) return result;
        const confirmArgs = {
            ...(confirmation?.arguments || args),
            _confirmed: true,
        };
        return callMCPTool(confirmation?.toolName || name, confirmArgs);
    };

    const updateToolFormValue = (key: string, value: MCPFormValue) => {
        setToolFormValues(prev => ({ ...prev, [key]: value }));
    };

    const handleToolRun = async () => {
        if (!selectedTool) return;
        setToolRunError(null);
        setToolResult(null);
        setToolFormErrors({});
        setToolRunning(true);

        let args: Record<string, unknown> = {};
        const schemaProps = selectedTool.inputSchema?.properties;
        const hasSchemaFields = !!(schemaProps && Object.keys(schemaProps).length > 0);
        if (hasSchemaFields) {
            const built = buildArgsFromSchema(selectedTool.inputSchema, toolFormValues);
            if (Object.keys(built.errors).length > 0) {
                setToolFormErrors(built.errors);
                setToolRunning(false);
                return;
            }
            args = built.args;
        } else if (toolRawArgs.trim()) {
            try {
                const parsed = JSON.parse(toolRawArgs);
                if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                    setToolRunError('参数必须是 JSON 对象');
                    setToolRunning(false);
                    return;
                }
                args = parsed as Record<string, unknown>;
            } catch {
                setToolRunError('参数 JSON 解析失败');
                setToolRunning(false);
                return;
            }
        }

        const result = await invokeMCPTool(selectedTool.name, args);
        if (result?.success) {
            setToolResult(result.data ?? result);
        } else if (result?.requiresConfirmation) {
            setToolRunError(result.message || '已取消确认');
            setToolResult(result);
        } else {
            setToolRunError(result?.error || result?.message || '工具执行失败');
            setToolResult(result);
        }
        setToolRunning(false);
    };

    const renderToolField = (key: string, schema: MCPToolSchema) => {
        const resolved = unwrapSchema(schema);
        const fieldType = resolveSchemaType(resolved);
        const requiredFields = selectedTool?.inputSchema?.required || [];
        const isRequired = requiredFields.includes(key);
        const value = toolFormValues[key] ?? '';
        const label = `${key}${isRequired ? ' *' : ''}`;
        const description = resolved?.description;

        if (fieldType === 'enum') {
            const options = resolved?.enum || [];
            return (
                <div key={key} className="form-group">
                    <label>{label}</label>
                    <select
                        className="form-select"
                        value={value}
                        onChange={e => updateToolFormValue(key, e.target.value)}
                    >
                        {!isRequired && <option value="">未设置</option>}
                        {options.map(option => (
                            <option key={String(option)} value={String(option)}>
                                {String(option)}
                            </option>
                        ))}
                    </select>
                    {description && <span className="form-hint">{description}</span>}
                </div>
            );
        }

        if (fieldType === 'boolean') {
            return (
                <div key={key} className="form-group">
                    <label>{label}</label>
                    <select
                        className="form-select"
                        value={value}
                        onChange={e => updateToolFormValue(key, e.target.value)}
                    >
                        {!isRequired && <option value="">未设置</option>}
                        <option value="true">true</option>
                        <option value="false">false</option>
                    </select>
                    {description && <span className="form-hint">{description}</span>}
                </div>
            );
        }

        if (fieldType === 'array' || fieldType === 'object') {
            const placeholder = fieldType === 'array' ? '逗号分隔，或 JSON 数组' : 'JSON 对象';
            return (
                <div key={key} className="form-group workbench-span">
                    <label>{label}</label>
                    <textarea
                        className="form-input"
                        rows={3}
                        placeholder={placeholder}
                        value={value}
                        onChange={e => updateToolFormValue(key, e.target.value)}
                    />
                    {description && <span className="form-hint">{description}</span>}
                </div>
            );
        }

        const inputType = fieldType === 'number' || fieldType === 'integer' ? 'number' : 'text';
        return (
            <div key={key} className="form-group">
                <label>{label}</label>
                <input
                    className="form-input"
                    type={inputType}
                    value={value}
                    onChange={e => updateToolFormValue(key, e.target.value)}
                />
                {description && <span className="form-hint">{description}</span>}
            </div>
        );
    };

    // 基于成本价与现价生成简单趋势曲线
    const buildPriceTrend = (start?: number, end?: number, points: number = 7): number[] => {
        if (!start || !end || points < 2) return [];
        const trend: number[] = [];
        const step = (end - start) / (points - 1);
        for (let i = 0; i < points; i += 1) {
            trend.push(Number((start + step * i).toFixed(2)));
        }
        return trend;
    };

    const drawSparkline = (canvas: HTMLCanvasElement | null, values: number[], color: string) => {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        if (width === 0 || height === 0) return;

        canvas.width = width;
        canvas.height = height;
        ctx.clearRect(0, 0, width, height);

        if (values.length < 2) return;

        const max = Math.max(...values);
        const min = Math.min(...values);
        const range = max - min || 1;

        ctx.beginPath();
        values.forEach((value, index) => {
            const x = (index / (values.length - 1)) * width;
            const y = height - ((value - min) / range) * height;
            if (index === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
    };

    const buildCompositeTrend = (items: PositionData[]): number[] => {
        const series = items
            .map(item => item.trend || [])
            .filter(trend => trend.length > 1);
        if (series.length === 0) return [];

        const length = Math.max(...series.map(trend => trend.length));
        const result: number[] = [];
        for (let i = 0; i < length; i += 1) {
            let sum = 0;
            let count = 0;
            series.forEach(trend => {
                if (typeof trend[i] === 'number') {
                    sum += trend[i] as number;
                    count += 1;
                }
            });
            result.push(count ? sum / count : 0);
        }
        return result;
    };

    const computeDecisionStats = (decisions: Array<{ profitPercent?: number; actualResult?: string; createdAt?: number; verifiedAt?: number }>) => {
        const verified = decisions.filter(item => typeof item.verifiedAt === 'number');
        const returns = verified
            .map(item => typeof item.profitPercent === 'number' ? item.profitPercent / 100 : null)
            .filter((value): value is number => value !== null);

        if (returns.length === 0) {
            return {
                winRate: null,
                plRatio: null,
                avgHoldingDays: null,
                totalReturn: null,
                maxDrawdown: null,
                sharpe: null,
            };
        }

        const wins = verified.filter(item => item.actualResult === 'profit').length;
        const winRate = verified.length > 0 ? (wins / verified.length) * 100 : null;

        const gains = returns.filter(r => r > 0);
        const losses = returns.filter(r => r < 0).map(r => Math.abs(r));
        const avgGain = gains.length ? gains.reduce((sum, v) => sum + v, 0) / gains.length : null;
        const avgLoss = losses.length ? losses.reduce((sum, v) => sum + v, 0) / losses.length : null;
        const plRatio = avgGain !== null && avgLoss !== null && avgLoss > 0 ? avgGain / avgLoss : null;

        const avgHoldingDays = verified.length
            ? verified.reduce((sum, item) => sum + ((item.verifiedAt || 0) - (item.createdAt || 0)), 0) / verified.length / (24 * 60 * 60 * 1000)
            : null;

        const equityCurve: number[] = [];
        let equity = 1;
        returns.forEach(r => {
            equity *= (1 + r);
            equityCurve.push(equity);
        });
        const totalReturn = equityCurve.length ? (equityCurve[equityCurve.length - 1] - 1) * 100 : null;

        let peak = 1;
        let maxDrawdown = 0;
        equityCurve.forEach(value => {
            if (value > peak) peak = value;
            const drawdown = (value - peak) / peak;
            if (drawdown < maxDrawdown) {
                maxDrawdown = drawdown;
            }
        });

        const mean = returns.reduce((sum, v) => sum + v, 0) / returns.length;
        const variance = returns.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / returns.length;
        const std = Math.sqrt(variance);
        const sharpe = std > 0 ? (mean / std) * Math.sqrt(returns.length) : null;

        return {
            winRate,
            plRatio,
            avgHoldingDays,
            totalReturn,
            maxDrawdown: maxDrawdown * 100,
            sharpe,
        };
    };

    // 加载数据
    const loadData = async () => {
        setDataLoading(true);
        try {
            // 尝试获取持仓
            const posRes = await callMCPTool('get_positions');
            let positionsData: PositionData[] = [];
            let totalValue = 0;
            let totalProfit = 0;

            const posPayload = posRes.data && typeof posRes.data === 'object' ? posRes.data as { positions?: PositionData[]; totalMarketValue?: number; totalProfit?: number } : undefined;
            if (posRes.success && posPayload?.positions) {
                positionsData = posPayload.positions.map((p: PositionData) => ({
                    ...p,
                    trend: buildPriceTrend(p.costPrice, p.currentPrice)
                }));
                totalValue = posPayload.totalMarketValue || 0;
                totalProfit = posPayload.totalProfit || 0;
            }

            setPositions(positionsData);
            setPortfolioSummary({
                totalValue,
                totalProfit,
                profitPercent: totalValue > 0 ? (totalProfit / totalValue) * 100 : 0
            });

            // 获取自选股
            const watchlistRes = await window.electronAPI.watchlist.get();
            const watchlistRaw = watchlistRes.success && Array.isArray(watchlistRes.data) ? watchlistRes.data : [];
            const watchlist = watchlistRaw.slice(0, 5).map((code: string) => ({
                code,
                name: getStockName(code),
                change: 0
            }));

            // AI 准确率 / 决策统计
            const statsRes = await window.electronAPI.trading.getAccuracyStats();
            const statsPayload = statsRes.success && statsRes.data && typeof statsRes.data === 'object'
                ? statsRes.data as { accuracyRate?: number; totalDecisions?: number; verifiedDecisions?: number }
                : undefined;
            const decisionsRes = await window.electronAPI.trading.getDecisions({ limit: 200 });
            const decisions = decisionsRes.success && Array.isArray(decisionsRes.data)
                ? decisionsRes.data as Array<{ profitPercent?: number; actualResult?: string; createdAt?: number; verifiedAt?: number }>
                : [];
            const decisionStats = computeDecisionStats(decisions);

            // 组装概览数据
            setOverviewData({
                watchlist,
                totalValue,
                todayPnL: 0,
                todayPnLPercent: 0,
                aiAccuracy: statsPayload?.accuracyRate ?? 0,
                totalDecisions: statsPayload?.totalDecisions ?? 0,
                positionCount: positionsData.length,
                winRate: decisionStats.winRate ?? statsPayload?.accuracyRate ?? 0
            });

            // 统计数据
            setStatsData({
                winRate: decisionStats.winRate,
                plRatio: decisionStats.plRatio,
                avgHoldingDays: decisionStats.avgHoldingDays,
                totalReturn: decisionStats.totalReturn,
                maxDrawdown: decisionStats.maxDrawdown,
                sharpe: decisionStats.sharpe,
                benchmarkReturn: null
            });

        } catch (e) {
            console.error('[PersonalCenter] Load data error:', e);
        } finally {
            setDataLoading(false);
        }
    };

    // 获取股票名称的简单映射
    const getStockName = (code: string): string => {
        const names: Record<string, string> = {
            '600519': '贵州茅台',
            '000001': '平安银行',
            '300750': '宁德时代',
            '002594': '比亚迪',
            '601318': '中国平安'
        };
        return names[code] || code;
    };


    // 获取可用模型
    const handleFetchModels = async () => {
        if (!baseUrl || !apiKey) {
            setError('请填写 API URL 和 API Key');
            return;
        }
        setIsLoadingModels(true);
        setError('');
        try {
            const availableModels = await fetchAvailableModels(baseUrl, apiKey);
            setModels(availableModels);
            if (availableModels.length > 0 && !model) {
                setModel(availableModels[0]);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : '获取模型列表失败');
        } finally {
            setIsLoadingModels(false);
        }
    };

    // 测试连接
    const handleTest = async () => {
        if (!baseUrl || !apiKey || !model) {
            setError('请填写完整的配置信息');
            return;
        }
        setIsTesting(true);
        setTestResult(null);
        setError('');
        try {
            const result = await testApiConnection(baseUrl, apiKey, model);
            setTestResult(result);
        } catch (e) {
            setTestResult({
                success: false,
                message: e instanceof Error ? e.message : '测试失败',
            });
        } finally {
            setIsTesting(false);
        }
    };

    // 保存配置
    const handleSave = async () => {
        if (!baseUrl || !apiKey || !model) {
            setError('请填写完整的配置信息');
            return;
        }
        const config: ApiConfig = {
            baseUrl,
            apiKey,
            model,
            models,
            lastTested: new Date().toISOString(),
            isValid: testResult?.success || false,
        };

        if (isWeb) {
            saveApiConfig(config);
            localStorage.setItem('aethertrade_mcp_url', mcpUrl);
        } else {
            console.log('[Settings] Saving config to Electron...', { baseUrl, model });
            try {
                await window.electronAPI.config.save({
                    aiModel: 'gpt-4',
                    apiKey,
                    apiBaseUrl: baseUrl,
                    apiModel: model,
                });
                console.log('[Settings] Config saved to Electron');
            } catch (err) {
                console.error('[Settings] Save config error:', err);
            }
        }

        onSave?.(config);
        onClose();
    };

    const handleSaveProfile = async () => {
        if (isWeb) {
            localStorage.setItem('aethertrade_profile_params', JSON.stringify(profileParams));
            return;
        }
        try {
            await window.electronAPI.config.save({ profileParams });
        } catch (e) {
            console.error('[PersonalCenter] Save profile error:', e);
        }
    };

    if (!isOpen) return null;

    // Tab 导航
    const tabs: { key: TabType; label: string; icon: string }[] = [
        { key: 'overview', label: '概览', icon: '📊' },
        { key: 'profile', label: '画像', icon: '👤' },
        { key: 'portfolio', label: '持仓', icon: '💼' },
        { key: 'stats', label: '统计', icon: '📈' },
        { key: 'settings', label: '设置', icon: '⚙️' },
    ];

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content personal-center" onClick={e => e.stopPropagation()}>
                {/* 头部 */}
                <div className="modal-header">
                    <h2>个人中心</h2>
                    <button className="modal-close" onClick={onClose}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </div>

                {/* Tab 导航 */}
                <div className="pc-tabs">
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            className={`pc-tab ${activeTab === tab.key ? 'active' : ''}`}
                            onClick={() => setActiveTab(tab.key)}
                        >
                            <span className="pc-tab-icon">{tab.icon}</span>
                            <span className="pc-tab-label">{tab.label}</span>
                        </button>
                    ))}
                </div>

                {/* Tab 内容 */}
                <div className="modal-body pc-content">
                    {/* 概览 Tab */}
                    {activeTab === 'overview' && (
                        <div className="pc-panel">
                            {/* 资产概览卡片 - 使用 stock-card-advanced */}
                            <div className="stock-card-advanced pc-asset-card">
                                <div className="stock-card-header">
                                    <div className="stock-info">
                                        <span className="stock-symbol">
                                            📊 资产概览
                                        </span>
                                        <span className="stock-label">实时更新</span>
                                    </div>
                                </div>
                                <div className="stock-price-large">
                                    <span className="price">¥{(overviewData?.totalValue || 0).toLocaleString()}</span>
                                    <span className={`change ${(overviewData?.todayPnL || 0) >= 0 ? 'positive' : 'negative'}`}>
                                        {(overviewData?.todayPnL || 0) >= 0 ? '+' : ''}
                                        {(overviewData?.todayPnL || 0).toLocaleString()}
                                        <span style={{ marginLeft: '4px', fontSize: '12px' }}>
                                            ({(overviewData?.todayPnLPercent || 0).toFixed(2)}%)
                                        </span>
                                    </span>
                                </div>
                                {/* 迷你收益曲线 */}
                                <div className="stock-mini-chart">
                                    <canvas ref={overviewChartRef}></canvas>
                                </div>
                            </div>

                            {/* 快速指标网格 */}
                            <div className="metrics-grid">
                                <div className="metric-card">
                                    <div className="metric-label">持仓</div>
                                    <div className="metric-value">{overviewData?.positionCount || 0}</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">胜率</div>
                                    <div className="metric-value">{overviewData?.winRate ?? '--'}%</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">AI准确率</div>
                                    <div className="metric-value">{overviewData?.aiAccuracy ?? '--'}%</div>
                                </div>
                            </div>

                            {/* 自选股 - 横向滚动 */}
                            <div className="pc-section">
                                <h3>⭐ 自选股</h3>
                                <div className="quick-actions-compact" style={{ overflowX: 'auto' }}>
                                    {overviewData?.watchlist?.length ? (
                                        overviewData.watchlist.map(stock => (
                                            <span key={stock.code} className="quick-action-pill">
                                                <span>{stock.code}</span>
                                                <span className={stock.change >= 0 ? 'positive' : 'negative'}>
                                                    {stock.change >= 0 ? '+' : ''}{stock.change.toFixed(1)}%
                                                </span>
                                            </span>
                                        ))
                                    ) : (
                                        <span className="pc-empty">暂无自选股</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 画像 Tab */}
                    {activeTab === 'profile' && (
                        <div className="pc-panel">
                            {/* 风险评估 - ai-inline-card */}
                            <div className="ai-inline-card">
                                <div className="card-title">🎯 风险评估</div>
                                <div className="pc-risk-container">
                                    {/* 渐变进度条 */}
                                    <div className="pc-risk-progress">
                                        <div
                                            className="pc-risk-progress-fill"
                                            style={{ width: `${profileParams.riskScore}%` }}
                                        ></div>
                                        <div
                                            className="pc-risk-indicator"
                                            style={{ left: `${profileParams.riskScore}%` }}
                                        ></div>
                                    </div>
                                    <div className="pc-risk-info">
                                        <span className="pc-risk-score">{profileParams.riskScore}分</span>
                                        <span className="pc-risk-type">{profileParams.riskType}</span>
                                    </div>
                                </div>
                            </div>

                            {/* 投资偏好 - metrics grid */}
                            <div className="metrics-grid">
                                <div className="metric-card">
                                    <div className="metric-label">投资经验</div>
                                    <div className="metric-value">{profileParams.experience}</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">投资期限</div>
                                    <div className="metric-value">{profileParams.investPeriod}</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">交易风格</div>
                                    <div className="metric-value">{profileParams.style}</div>
                                </div>
                            </div>

                            {/* 交易参数 - 滑块 */}
                            <div className="pc-section">
                                <h3>⚙️ 交易参数</h3>
                                <div className="pc-slider-group">
                                    <div className="pc-slider-item">
                                        <div className="pc-slider-header">
                                            <span>止损比例</span>
                                            <span className="pc-slider-value">{profileParams.stopLoss}%</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="1"
                                            max="20"
                                            value={profileParams.stopLoss}
                                            onChange={(e) => setProfileParams(p => ({ ...p, stopLoss: Number(e.target.value) }))}
                                            className="pc-range-slider"
                                        />
                                    </div>
                                    <div className="pc-slider-item">
                                        <div className="pc-slider-header">
                                            <span>止盈比例</span>
                                            <span className="pc-slider-value">{profileParams.takeProfit}%</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="5"
                                            max="50"
                                            value={profileParams.takeProfit}
                                            onChange={(e) => setProfileParams(p => ({ ...p, takeProfit: Number(e.target.value) }))}
                                            className="pc-range-slider"
                                        />
                                    </div>
                                    <div className="pc-slider-item">
                                        <div className="pc-slider-header">
                                            <span>最大仓位</span>
                                            <span className="pc-slider-value">{profileParams.maxPosition}%</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="5"
                                            max="50"
                                            value={profileParams.maxPosition}
                                            onChange={(e) => setProfileParams(p => ({ ...p, maxPosition: Number(e.target.value) }))}
                                            className="pc-range-slider"
                                        />
                                    </div>
                                </div>
                                <button className="btn btn-secondary" onClick={handleSaveProfile}>
                                    保存画像参数
                                </button>
                            </div>
                        </div>
                    )}

                    {/* 持仓 Tab */}
                    {activeTab === 'portfolio' && (
                        <div className="pc-panel">
                            {/* 组合总览卡片 - stock-card-advanced */}
                            <div className="stock-card-advanced">
                                <div className="stock-card-header">
                                    <div className="stock-info">
                                        <span className="stock-symbol">💰 组合总览</span>
                                        <span className="stock-label">实时持仓数据</span>
                                    </div>
                                </div>
                                <div className="stock-price-large">
                                    <span className="price">¥{(portfolioSummary?.totalValue || 0).toLocaleString()}</span>
                                    <span className={`change ${(portfolioSummary?.totalProfit || 0) >= 0 ? 'positive' : 'negative'}`}>
                                        {(portfolioSummary?.totalProfit || 0) >= 0 ? '+' : ''}
                                        ¥{(portfolioSummary?.totalProfit || 0).toLocaleString()}
                                        <span style={{ marginLeft: '4px', fontSize: '12px' }}>
                                            ({(portfolioSummary?.profitPercent || 0).toFixed(2)}%)
                                        </span>
                                    </span>
                                </div>
                            </div>

                            {/* 持仓列表 - stock-card 风格 */}
                            <div className="pc-section">
                                <h3>📋 持仓 ({positions.length})</h3>
                                {positions.length > 0 ? (
                                    <div className="pc-position-list-advanced">
                                        {positions.map(pos => (
                                            <div key={pos.code} className="stock-card-advanced pc-position-card">
                                                <div className="stock-card-header">
                                                    <div className="stock-info">
                                                        <span className="stock-symbol">
                                                            {pos.name}
                                                            <span className="company">{pos.code}</span>
                                                        </span>
                                                        <span className="stock-label">
                                                            成本: ¥{pos.costPrice} | 现价: ¥{pos.currentPrice}
                                                        </span>
                                                    </div>
                                                    <span className={`change ${pos.profit >= 0 ? 'positive' : 'negative'}`}>
                                                        {pos.profit >= 0 ? '+' : ''}¥{pos.profit.toLocaleString()}
                                                    </span>
                                                </div>
                                                {/* 迷你趋势图 - SVG */}
                                                <div className="stock-mini-chart">
                                                    <svg width="100%" height="100%" viewBox="0 0 100 40" preserveAspectRatio="none">
                                                        <defs>
                                                            <linearGradient id={`grad-${pos.code}`} x1="0" y1="0" x2="0" y2="1">
                                                                <stop offset="0%" stopColor={pos.profit >= 0 ? 'rgba(52, 199, 89, 0.3)' : 'rgba(255, 59, 48, 0.3)'} />
                                                                <stop offset="100%" stopColor="transparent" />
                                                            </linearGradient>
                                                        </defs>
                                                        {pos.trend && (
                                                            <>
                                                                <path
                                                                    d={`M 0 ${40 - ((pos.trend[0] - 95) * 2)} ${pos.trend.map((v, i) => `L ${(i / 6) * 100} ${40 - ((v - 95) * 2)}`).join(' ')} L 100 40 L 0 40 Z`}
                                                                    fill={`url(#grad-${pos.code})`}
                                                                />
                                                                <path
                                                                    d={`M 0 ${40 - ((pos.trend[0] - 95) * 2)} ${pos.trend.map((v, i) => `L ${(i / 6) * 100} ${40 - ((v - 95) * 2)}`).join(' ')}`}
                                                                    fill="none"
                                                                    stroke={pos.profit >= 0 ? 'var(--success)' : 'var(--danger)'}
                                                                    strokeWidth="2"
                                                                />
                                                            </>
                                                        )}
                                                    </svg>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="pc-empty">暂无持仓</div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* 统计 Tab */}
                    {activeTab === 'stats' && (
                        <div className="pc-panel">
                            {/* 收益趋势图表 */}
                            <div className="stock-card-advanced">
                                <div className="stock-card-header">
                                    <span className="stock-symbol">📈 收益趋势</span>
                                </div>
                                <div className="stock-mini-chart" style={{ height: '100px' }}>
                                    <canvas ref={statsChartRef}></canvas>
                                </div>
                                <div style={{ textAlign: 'center', marginTop: '8px', opacity: 0.7 }}>
                                    区间：近7天
                                </div>
                            </div>

                            {/* 核心指标 - metrics grid */}
                            <div className="metrics-grid">
                                <div className="metric-card">
                                    <div className="metric-label">胜率</div>
                                    <div className="metric-value">{statsData?.winRate ?? '--'}%</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">夏普</div>
                                    <div className="metric-value">{statsData?.sharpe ?? '--'}</div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">回撤</div>
                                    <div className="metric-value negative">{statsData?.maxDrawdown ?? '--'}%</div>
                                </div>
                            </div>

                            {/* vs 沪深300 对比 */}
                            <div className="pc-section">
                                <h3>vs 沪深300</h3>
                                <div className="pc-benchmark-compare">
                                    <div className="pc-benchmark-item">
                                        <span className="pc-benchmark-label">你的收益</span>
                                        <div className="pc-benchmark-bar">
                                            <div
                                                className="pc-benchmark-fill accent"
                                                style={{ width: `${Math.min(((statsData?.totalReturn ?? 0) as number) * 3, 100)}%` }}
                                            ></div>
                                        </div>
                                        <span className="pc-benchmark-value positive">
                                            {statsData?.totalReturn === null || statsData?.totalReturn === undefined
                                                ? '--'
                                                : `+${statsData.totalReturn.toFixed(2)}%`}
                                        </span>
                                    </div>
                                    <div className="pc-benchmark-item">
                                        <span className="pc-benchmark-label">沪深300</span>
                                        <div className="pc-benchmark-bar">
                                            <div
                                                className="pc-benchmark-fill tertiary"
                                                style={{ width: `${Math.min(((statsData?.benchmarkReturn ?? 0) as number) * 3, 100)}%` }}
                                            ></div>
                                        </div>
                                        <span className="pc-benchmark-value">
                                            {statsData?.benchmarkReturn === null || statsData?.benchmarkReturn === undefined
                                                ? '--'
                                                : `+${statsData.benchmarkReturn.toFixed(2)}%`}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 设置 Tab */}
                    {activeTab === 'settings' && (
                        <div className="pc-panel">
                            {/* MCP 状态 */}
                            <div className="pc-section">
                                <h3>MCP 工具状态</h3>
                                <div className="pc-mcp-status">
                                    <div className="pc-mcp-connection">
                                        <span className={`pc-mcp-dot ${mcpConnected ? 'connected' : 'disconnected'}`}></span>
                                        <span>{mcpConnected ? '已连接' : '未连接'}</span>
                                        <span className="pc-mcp-url">{isWeb ? mcpUrl : 'stdio://local'}</span>
                                    </div>
                                    {mcpConnected && (
                                        <>
                                            <div className="pc-mcp-tools-count">
                                                可用工具: <strong>{mcpTools.length}</strong> 个
                                            </div>
                                            <div className="pc-mcp-tools-count">
                                                可用技能: <strong>{mcpSkills.length}</strong> 个
                                            </div>
                                            <button
                                                className="btn btn-secondary pc-mcp-toggle"
                                                onClick={() => setShowToolList(!showToolList)}
                                            >
                                                {showToolList ? '收起列表' : '查看工具列表'}
                                            </button>
                                            <button
                                                className="btn btn-secondary pc-mcp-toggle"
                                                onClick={() => setShowSkillList(!showSkillList)}
                                            >
                                                {showSkillList ? '收起技能' : '查看技能列表'}
                                            </button>
                                            {showToolList && (
                                                <div className="pc-mcp-tool-list">
                                                    {mcpTools.slice(0, 20).map(tool => (
                                                        <div key={tool.name} className="pc-mcp-tool-item">
                                                            <span className="pc-tool-name">{tool.name}</span>
                                                            <span className="pc-tool-desc">{tool.description?.slice(0, 50)}...</span>
                                                        </div>
                                                    ))}
                                                    {mcpTools.length > 20 && (
                                                        <div className="pc-mcp-more">还有 {mcpTools.length - 20} 个工具...</div>
                                                    )}
                                                </div>
                                            )}
                                            {showSkillList && (
                                                <div className="pc-mcp-tool-list">
                                                    {mcpSkills.slice(0, 20).map(skill => (
                                                        <div key={skill.id} className="pc-mcp-tool-item">
                                                            <span className="pc-tool-name">{skill.name}</span>
                                                            <span className="pc-tool-desc">{skill.description?.slice(0, 50)}...</span>
                                                        </div>
                                                    ))}
                                                    {mcpSkills.length > 20 && (
                                                        <div className="pc-mcp-more">还有 {mcpSkills.length - 20} 个技能...</div>
                                                    )}
                                                </div>
                                            )}
                                        </>
                                    )}
                                    {!mcpConnected && !mcpLoading && (
                                        <button className="btn btn-secondary" onClick={checkMCPConnection}>
                                            重新检测
                                        </button>
                                    )}
                                </div>
                            </div>

                            {mcpConnected && (
                                <div className="pc-section">
                                    <h3>MCP 工具执行</h3>
                                    <div className="form-group">
                                        <label htmlFor="mcpToolSelect">选择工具</label>
                                        <select
                                            id="mcpToolSelect"
                                            className="form-select"
                                            value={selectedToolName}
                                            onChange={e => setSelectedToolName(e.target.value)}
                                        >
                                            <option value="">请选择工具</option>
                                            {mcpTools.map(tool => (
                                                <option key={tool.name} value={tool.name}>
                                                    {tool.name}
                                                </option>
                                            ))}
                                        </select>
                                        {selectedTool?.description && <span className="form-hint">{selectedTool.description}</span>}
                                    </div>

                                    {selectedTool ? (
                                        <>
                                            {selectedTool.inputSchema?.properties && Object.keys(selectedTool.inputSchema.properties).length > 0 ? (
                                                <div className="workbench-grid">
                                                    {Object.entries(selectedTool.inputSchema.properties).map(([key, schema]) =>
                                                        renderToolField(key, schema),
                                                    )}
                                                </div>
                                            ) : (
                                                <div className="form-group">
                                                    <label htmlFor="mcpToolRawArgs">参数 JSON（可选）</label>
                                                    <textarea
                                                        id="mcpToolRawArgs"
                                                        className="form-input"
                                                        rows={4}
                                                        value={toolRawArgs}
                                                        onChange={e => setToolRawArgs(e.target.value)}
                                                        placeholder='{"stock_code":"000001"}'
                                                    />
                                                    <span className="form-hint">该工具暂无参数定义，可手动填写 JSON。</span>
                                                </div>
                                            )}

                                            {selectedTool.requiresConfirmation && (
                                                <div className="form-hint">该工具需要确认执行，请谨慎操作。</div>
                                            )}

                                            {(toolRunError || Object.keys(toolFormErrors).length > 0) && (
                                                <div className="form-error">
                                                    {toolRunError ||
                                                        Object.entries(toolFormErrors)
                                                            .map(([field, message]) => `${field}: ${message}`)
                                                            .join('；')}
                                                </div>
                                            )}

                                            <div className="workbench-actions">
                                                <button className="btn btn-secondary" onClick={handleToolRun} disabled={toolRunning}>
                                                    {toolRunning ? '执行中...' : '执行工具'}
                                                </button>
                                                <button
                                                    className="btn btn-secondary"
                                                    onClick={() => {
                                                        setToolFormValues(buildDefaultFormValues(selectedTool.inputSchema));
                                                        setToolRawArgs('');
                                                        setToolFormErrors({});
                                                        setToolRunError(null);
                                                        setToolResult(null);
                                                    }}
                                                >
                                                    重置参数
                                                </button>
                                            </div>

                                            {toolResult !== null && (
                                                <div className="tool-details">
                                                    <div>返回结果</div>
                                                    <pre>{JSON.stringify(toolResult, null, 2)}</pre>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <div className="pc-empty">请选择工具</div>
                                    )}
                                </div>
                            )}

                            {isWeb && (
                                <div className="pc-section">
                                    <h3>MCP 服务地址 (Web)</h3>
                                    <div className="form-group">
                                        <label htmlFor="mcpUrl">MCP URL</label>
                                        <input
                                            id="mcpUrl"
                                            type="text"
                                            value={mcpUrl}
                                            onChange={e => setMcpUrl(e.target.value)}
                                            placeholder={DEFAULT_MCP_SERVER_URL}
                                            className="form-input"
                                        />
                                    </div>
                                </div>
                            )}

                            {/* API 配置 */}
                            <div className="pc-section">
                                <h3>AI API 配置</h3>
                                <div className="form-group">
                                    <label htmlFor="apiUrl">API URL</label>
                                    <input
                                        id="apiUrl"
                                        type="text"
                                        value={baseUrl}
                                        onChange={e => setBaseUrl(e.target.value)}
                                        placeholder="https://api.openai.com/v1"
                                        className="form-input"
                                    />
                                </div>

                                <div className="form-group">
                                    <label htmlFor="apiKey">API Key</label>
                                    <input
                                        id="apiKey"
                                        type="password"
                                        value={apiKey}
                                        onChange={e => setApiKey(e.target.value)}
                                        placeholder="sk-..."
                                        className="form-input"
                                    />
                                </div>

                                <div className="form-group">
                                    <button
                                        className="btn btn-secondary"
                                        onClick={handleFetchModels}
                                        disabled={isLoadingModels || !baseUrl || !apiKey}
                                    >
                                        {isLoadingModels ? '获取中...' : '获取可用模型'}
                                    </button>
                                </div>

                                <div className="form-group">
                                    <label htmlFor="model">选择模型</label>
                                    <select
                                        id="model"
                                        value={model}
                                        onChange={e => setModel(e.target.value)}
                                        className="form-select"
                                        disabled={models.length === 0}
                                    >
                                        {models.length === 0 ? (
                                            <option value="">请先获取模型列表</option>
                                        ) : (
                                            models.map(m => (
                                                <option key={m} value={m}>{m}</option>
                                            ))
                                        )}
                                    </select>
                                </div>

                                {error && <div className="form-error">❌ {error}</div>}
                                {testResult && (
                                    <div className={`form-result ${testResult.success ? 'success' : 'error'}`}>
                                        {testResult.success ? '✅' : '❌'} {testResult.message}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* 底部按钮 */}
                {activeTab === 'settings' && (
                    <div className="modal-footer">
                        <button
                            className="btn btn-secondary"
                            onClick={handleTest}
                            disabled={isTesting || !baseUrl || !apiKey || !model}
                        >
                            {isTesting ? '测试中...' : '测试连接'}
                        </button>
                        <button
                            className="btn btn-primary"
                            onClick={handleSave}
                            disabled={!baseUrl || !apiKey || !model}
                        >
                            保存配置
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PersonalCenter;
