/**
 * 投资组合管理工具
 * 包含风险分析、组合优化等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import * as RiskServices from '../services/risk-model.js';
import * as OptimizationServices from '../services/portfolio-optimizer.js';

// ========== analyze_portfolio_risk ==========

const analyzePortfolioRiskSchema = z.object({
    holdings: z.array(z.object({
        code: z.string(),
        weight: z.number().describe('权重 (0-1)'),
        cost: z.number().optional(),
    })).describe('持仓列表'),
    benchmark: z.string().optional().default('000300').describe('基准指数代码'),
});

const analyzePortfolioRiskTool: ToolDefinition = {
    name: 'analyze_portfolio_risk',
    description: '分析投资组合风险（VaR, 波动率, 最大回撤等）',
    category: 'portfolio_management',
    inputSchema: analyzePortfolioRiskSchema,
    tags: ['portfolio', 'risk'],
    dataSource: 'real',
};

const analyzePortfolioRiskHandler: ToolHandler<z.infer<typeof analyzePortfolioRiskSchema>> = async (params) => {
    // 转换为服务层需要的格式
    const holdingsMap: Record<string, number> = {};
    const stocks: string[] = [];
    params.holdings.forEach((h: any) => {
        holdingsMap[h.code] = h.weight;
        stocks.push(h.code);
    });

    const result = RiskServices.generateRiskReport(stocks, holdingsMap);

    return {
        success: true,
        data: result,
        source: 'calculated',
    };
};

// ========== optimize_portfolio ==========

const optimizePortfolioSchema = z.object({
    stocks: z.array(z.string()).describe('待优化股票池'),
    method: z.enum(['mean_variance', 'black_litterman', 'risk_budget', 'equal_weight']).default('mean_variance').describe('优化方法'),
    targetVolatility: z.number().optional().describe('目标波动率 (仅 risk_budget 有效)'),
    riskBudgets: z.array(z.number()).optional().describe('风险预算 (仅 risk_budget 有效)'),
});

const optimizePortfolioTool: ToolDefinition = {
    name: 'optimize_portfolio',
    description: '投资组合权重优化',
    category: 'portfolio_management',
    inputSchema: optimizePortfolioSchema,
    tags: ['portfolio', 'optimization'],
    dataSource: 'real',
};

const optimizePortfolioHandler: ToolHandler<z.infer<typeof optimizePortfolioSchema>> = async (params) => {
    const result = await OptimizationServices.optimizePortfolio({
        stocks: params.stocks,
        method: params.method as any,
        targetVolatility: params.targetVolatility,
        riskBudgets: params.riskBudgets,
    });

    if ('error' in result) {
        return { success: false, error: result.error };
    }

    return {
        success: true,
        data: result,
        source: 'calculated',
    };
};

// ========== stress_test_portfolio ==========

const stressTestPortfolioSchema = z.object({
    holdings: z.array(z.object({
        code: z.string(),
        weight: z.number(),
    })).describe('持仓列表'),
});

const stressTestPortfolioTool: ToolDefinition = {
    name: 'stress_test_portfolio',
    description: '投资组合压力测试',
    category: 'portfolio_management',
    inputSchema: stressTestPortfolioSchema,
    tags: ['portfolio', 'risk'],
    dataSource: 'real',
};

const stressTestPortfolioHandler: ToolHandler<z.infer<typeof stressTestPortfolioSchema>> = async (params) => {
    const holdingsMap: Record<string, number> = {};
    const stocks: string[] = [];
    params.holdings.forEach((h: any) => {
        holdingsMap[h.code] = h.weight;
        stocks.push(h.code);
    });

    const result = RiskServices.runStressTest(stocks, holdingsMap);

    return {
        success: true,
        data: result,
        source: 'calculated',
    };
};


// ========== 注册导出 ==========

export const portfolioManagementTools: ToolRegistryItem[] = [
    { definition: analyzePortfolioRiskTool, handler: analyzePortfolioRiskHandler },
    { definition: optimizePortfolioTool, handler: optimizePortfolioHandler },
    { definition: stressTestPortfolioTool, handler: stressTestPortfolioHandler },
];
