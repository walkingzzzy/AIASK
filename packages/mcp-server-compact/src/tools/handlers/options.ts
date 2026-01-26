import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';
import { buildManagerHelp } from './manager-help.js';

export const optionsManagerTool: ToolDefinition = {
    name: 'options_manager',
    description: '期权分析管理（定价、Greeks、策略分析）',
    category: 'financial_analysis',
    inputSchema: managerSchema,
    tags: ['options', 'manager', 'greeks'],
    dataSource: 'real',
};

// Black-Scholes 定价模型
function blackScholes(
    S: number, // 标的价格
    K: number, // 行权价
    T: number, // 到期时间（年）
    r: number, // 无风险利率
    sigma: number, // 波动率
    type: 'call' | 'put'
): { price: number; delta: number; gamma: number; theta: number; vega: number; rho: number } {
    // 标准正态分布累积函数
    const normCdf = (x: number): number => {
        const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
        const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
        const sign = x < 0 ? -1 : 1;
        x = Math.abs(x) / Math.sqrt(2);
        const t = 1.0 / (1.0 + p * x);
        const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
        return 0.5 * (1.0 + sign * y);
    };

    // 标准正态分布概率密度函数
    const normPdf = (x: number): number => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);

    const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
    const d2 = d1 - sigma * Math.sqrt(T);

    let price: number, delta: number;

    if (type === 'call') {
        price = S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
        delta = normCdf(d1);
    } else {
        price = K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
        delta = normCdf(d1) - 1;
    }

    const gamma = normPdf(d1) / (S * sigma * Math.sqrt(T));
    const theta = (-(S * normPdf(d1) * sigma) / (2 * Math.sqrt(T)) -
        r * K * Math.exp(-r * T) * (type === 'call' ? normCdf(d2) : normCdf(-d2))) / 365;
    const vega = S * normPdf(d1) * Math.sqrt(T) / 100; // 每1%波动率变化
    const rho = (type === 'call' ? 1 : -1) * K * T * Math.exp(-r * T) *
        (type === 'call' ? normCdf(d2) : normCdf(-d2)) / 100;

    return { price, delta, gamma, theta, vega, rho };
}

// 计算隐含波动率（牛顿法）
function impliedVolatility(
    marketPrice: number,
    S: number,
    K: number,
    T: number,
    r: number,
    type: 'call' | 'put'
): number {
    let sigma = 0.3; // 初始猜测
    for (let i = 0; i < 100; i++) {
        const result = blackScholes(S, K, T, r, sigma, type);
        const diff = result.price - marketPrice;
        if (Math.abs(diff) < 0.0001) break;
        const vega = result.vega * 100; // 还原 vega
        if (vega < 0.0001) break;
        sigma -= diff / vega;
        if (sigma <= 0) sigma = 0.01;
        if (sigma > 5) sigma = 5;
    }
    return sigma;
}

export const optionsManagerHandler: ToolHandler = async (params: any) => {
    let {
        action, type = 'call', spotPrice, strikePrice, expiry, volatility = 0.3,
        riskFreeRate = 0.03, marketPrice, strategies,
    } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'calculate_option_price',
            'price',
            'calculate_greeks',
            'greeks',
            'analyze_implied_volatility',
            'iv',
            'analyze_option_strategy',
            'strategy',
            'get_option_chain',
            'chain',
            'help',
        ],
        description: '期权分析入口，action 为空时返回可用动作。',
    });
    if (help && action !== 'help') return help;

    // 参数类型转换 (确保是数字)
    spotPrice = spotPrice ? parseFloat(spotPrice) : undefined;
    strikePrice = strikePrice ? parseFloat(strikePrice) : undefined;
    expiry = expiry ? parseFloat(expiry) : undefined;
    volatility = volatility ? parseFloat(volatility) : 0.3;
    riskFreeRate = riskFreeRate ? parseFloat(riskFreeRate) : 0.03;
    marketPrice = marketPrice ? parseFloat(marketPrice) : undefined;

    // ===== 期权定价 =====
    if (action === 'calculate_option_price' || action === 'price') {
        if (!spotPrice || !strikePrice || !expiry) {
            return { success: false, error: '需要参数: spotPrice(标的价格), strikePrice(行权价), expiry(到期天数)' };
        }

        const T = expiry / 365; // 转换为年
        const result = blackScholes(spotPrice, strikePrice, T, riskFreeRate, volatility, type as 'call' | 'put');

        return {
            success: true,
            data: {
                inputs: {
                    spotPrice,
                    strikePrice,
                    expiryDays: expiry,
                    volatility: `${(volatility * 100).toFixed(1)}%`,
                    riskFreeRate: `${(riskFreeRate * 100).toFixed(1)}%`,
                    type,
                },
                price: Math.round(result.price * 10000) / 10000,
                timeValue: Math.round((result.price - Math.max(0, type === 'call' ? spotPrice - strikePrice : strikePrice - spotPrice)) * 10000) / 10000,
                moneyness: spotPrice > strikePrice ? (type === 'call' ? 'ITM' : 'OTM') : (type === 'call' ? 'OTM' : 'ITM'),
            },
        };
    }

    // ===== Greeks 计算 =====
    if (action === 'calculate_greeks' || action === 'greeks') {
        if (!spotPrice || !strikePrice || !expiry) {
            return { success: false, error: '需要参数: spotPrice, strikePrice, expiry' };
        }

        const T = expiry / 365;
        const result = blackScholes(spotPrice, strikePrice, T, riskFreeRate, volatility, type as 'call' | 'put');

        return {
            success: true,
            data: {
                inputs: { spotPrice, strikePrice, expiryDays: expiry, volatility, type },
                greeks: {
                    delta: Math.round(result.delta * 10000) / 10000,
                    gamma: Math.round(result.gamma * 10000) / 10000,
                    theta: Math.round(result.theta * 10000) / 10000,
                    vega: Math.round(result.vega * 10000) / 10000,
                    rho: Math.round(result.rho * 10000) / 10000,
                },
                interpretation: {
                    delta: `标的每涨1元，期权价格变化约${(result.delta).toFixed(4)}元`,
                    gamma: `Delta的变化速度`,
                    theta: `每天时间价值损耗约${Math.abs(result.theta).toFixed(4)}元`,
                    vega: `波动率每涨1%，期权价格变化约${result.vega.toFixed(4)}元`,
                },
            },
        };
    }

    // ===== 隐含波动率 =====
    if (action === 'analyze_implied_volatility' || action === 'iv') {
        if (!spotPrice || !strikePrice || !expiry || !marketPrice) {
            return { success: false, error: '需要参数: spotPrice, strikePrice, expiry, marketPrice' };
        }

        const T = expiry / 365;
        const iv = impliedVolatility(marketPrice, spotPrice, strikePrice, T, riskFreeRate, type as 'call' | 'put');

        // 计算理论价格进行对比
        const theoretical = blackScholes(spotPrice, strikePrice, T, riskFreeRate, iv, type as 'call' | 'put');

        return {
            success: true,
            data: {
                marketPrice,
                impliedVolatility: `${(iv * 100).toFixed(2)}%`,
                ivDecimal: Math.round(iv * 10000) / 10000,
                theoreticalPrice: Math.round(theoretical.price * 10000) / 10000,
                ivLevel: iv > 0.5 ? '高波动' : iv > 0.3 ? '中等波动' : '低波动',
                analysis: iv > volatility ? '期权价格偏贵（IV高于历史波动率）' : '期权价格偏便宜',
            },
        };
    }

    // ===== 期权策略分析 =====
    if (action === 'analyze_option_strategy' || action === 'strategy') {
        const strategyTemplates: Record<string, { description: string; legs: string[]; risk: string; reward: string }> = {
            'covered_call': {
                description: '备兑开仓：持有标的+卖出看涨期权',
                legs: ['Long Stock', 'Short Call'],
                risk: '标的下跌风险',
                reward: '获得权利金收入，适合温和看涨',
            },
            'protective_put': {
                description: '保护性看跌：持有标的+买入看跌期权',
                legs: ['Long Stock', 'Long Put'],
                risk: '有限（权利金成本）',
                reward: '保护下跌风险，保留上涨收益',
            },
            'bull_call_spread': {
                description: '牛市看涨价差：买低行权价Call+卖高行权价Call',
                legs: ['Long Call (low strike)', 'Short Call (high strike)'],
                risk: '有限（净权利金）',
                reward: '有限（行权价差-净权利金）',
            },
            'bear_put_spread': {
                description: '熊市看跌价差：买高行权价Put+卖低行权价Put',
                legs: ['Long Put (high strike)', 'Short Put (low strike)'],
                risk: '有限',
                reward: '有限',
            },
            'straddle': {
                description: '跨式：同时买入相同行权价的Call和Put',
                legs: ['Long Call', 'Long Put'],
                risk: '有限（两份权利金）',
                reward: '无限（需要大幅波动）',
            },
            'strangle': {
                description: '宽跨式：买入不同行权价的Call和Put',
                legs: ['Long OTM Call', 'Long OTM Put'],
                risk: '有限（较低权利金）',
                reward: '无限（需要更大波动）',
            },
            'iron_condor': {
                description: '铁鹰：卖出宽跨式+买入更宽跨式保护',
                legs: ['Sell OTM Put', 'Buy further OTM Put', 'Sell OTM Call', 'Buy further OTM Call'],
                risk: '有限',
                reward: '有限（收取净权利金）',
            },
        };

        const strategy = strategies || 'covered_call';
        const template = strategyTemplates[strategy];

        if (!template) {
            return {
                success: true,
                data: {
                    availableStrategies: Object.keys(strategyTemplates),
                    message: `请指定策略: ${Object.keys(strategyTemplates).join(', ')}`,
                },
            };
        }

        return {
            success: true,
            data: {
                strategy,
                ...template,
                suitableFor: strategy.includes('bull') || strategy === 'covered_call' ? '看涨市场' :
                    strategy.includes('bear') ? '看跌市场' :
                        strategy === 'straddle' || strategy === 'strangle' ? '预期大幅波动' :
                            strategy === 'iron_condor' ? '预期横盘震荡' : '中性',
            },
        };
    }

    // ===== 期权链（需要数据源）=====
    if (action === 'get_option_chain' || action === 'chain') {
        const underlying = params.underlying || params.code || params.symbol;
        const expiryMonth = params.expiry_month || params.expiryMonth;
        const limit = params.limit ? parseInt(params.limit, 10) : undefined;
        if (!underlying) {
            return { success: false, error: '需要提供 underlying 或 code 参数' };
        }
        const chainRes = await callAkshareMcpTool('get_option_chain', {
            underlying,
            expiry_month: expiryMonth,
            limit,
        });
        if (!chainRes.success || !chainRes.data) {
            return { success: false, error: chainRes.error || '获取期权链失败' };
        }
        return {
            success: true,
            data: {
                underlying,
                expiryMonth: expiryMonth || null,
                contracts: chainRes.data,
            },
            source: 'akshare',
        };
    }

    // ===== 帮助信息 =====
    if (action === 'help' || !action) {
        return {
            success: true,
            data: {
                supportedActions: [
                    { action: 'price', description: '期权定价（Black-Scholes）', params: ['spotPrice', 'strikePrice', 'expiry', 'volatility', 'type'] },
                    { action: 'greeks', description: '计算希腊字母', params: ['spotPrice', 'strikePrice', 'expiry', 'volatility', 'type'] },
                    { action: 'iv', description: '计算隐含波动率', params: ['spotPrice', 'strikePrice', 'expiry', 'marketPrice', 'type'] },
                    { action: 'strategy', description: '期权策略分析', params: ['strategies'] },
                    { action: 'chain', description: '期权链数据（开发中）', params: [] },
                ],
                defaultParams: {
                    volatility: 0.3,
                    riskFreeRate: 0.03,
                    type: 'call',
                },
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: price, greeks, iv, strategy, chain, help, list` };
};
