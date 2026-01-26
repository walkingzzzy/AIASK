/**
 * 工具注册中心
 * 聚合所有工具，提供统一的注册和查找接口
 */

import { ToolRegistryItem } from '../types/tools.js';

import { marketDataTools } from './market-data.js';
import { financialAnalysisTools } from './financial-analysis.js';
import { technicalAnalysisTools } from './technical-analysis.js';
import { marketSentimentTools } from './market-sentiment.js';
import { portfolioManagementTools } from './portfolio-management.js';
import { discoveryTools } from './discovery.js';
import { skillsTools } from './skills.js';
import { semanticTools } from './semantic.js';
import { managerTools } from './managers.js';
import { vectorTools } from './vector-tools.js';
import { researchTools } from './research-tools.js';
import { quantTools } from './quant-tools.js';
import { alertTools } from './alert-tools.js';
import { valuationTools } from './valuation-tools.js';
import { macroTools } from './macro-tools.js';
import { decisionTools } from './decision-tools.js';
import { dataWarmupTools } from './data-warmup-tools.js';
import { setToolRegistry } from './registry.js';

// 聚合所有工具
export const allTools: ToolRegistryItem[] = [
    ...marketDataTools,        // 7 tools
    ...financialAnalysisTools, // 4 tools
    ...technicalAnalysisTools, // 3 tools
    ...marketSentimentTools,   // 3 tools
    ...portfolioManagementTools, // 3 tools
    ...discoveryTools,         // 3 tools
    ...skillsTools,            // 3 tools
    ...semanticTools,          // 4 tools
    ...managerTools,           // 30 managers
    ...vectorTools,            // 3 vector search
    ...researchTools,          // 3 research
    ...quantTools,             // 4 quant factor
    ...alertTools,             // 3 alerts
    ...valuationTools,         // 3 valuation
    ...macroTools,             // 2 macro
    ...decisionTools,          // 2 decision
    ...dataWarmupTools,        // 1 data warmup
];  // Total: 81 tools (51 standalone + 30 managers)

setToolRegistry(allTools);

/**
 * 获取所有工具定义
 */
export function getAllToolDefinitions() {
    return allTools.map(item => item.definition);
}

/**
 * 根据名称查找工具处理器
 */
export function getToolHandler(name: string) {
    const tool = allTools.find(item => item.definition.name === name);
    return tool ? tool.handler : undefined;
}

/**
 * 验证工具名称是否存在
 */
export function hasTool(name: string): boolean {
    return allTools.some(item => item.definition.name === name);
}
