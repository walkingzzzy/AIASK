/**
 * 技能 (Skills) 工具
 * 管理和执行复合技能
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';

// ========== list_skills ==========

const listSkillsSchema = z.object({});

const listSkillsTool: ToolDefinition = {
    name: 'list_skills',
    description: '列出所有可用的高级技能 (Skills)',
    category: 'skills',
    inputSchema: listSkillsSchema,
    tags: ['skills', 'discovery'],
    dataSource: 'static',
};

const listSkillsHandler: ToolHandler<z.infer<typeof listSkillsSchema>> = async () => {
    // 实际实现应该扫描 skills 目录
    // 这里返回示例
    return {
        success: true,
        data: [
            { id: 'daily_market_report', name: '生成日报', description: '自动生成每日市场复盘报告' },
            { id: 'smart_stock_diagnosis', name: '智能诊股', description: '全方位分析个股基本面和技术面' },
        ],
        source: 'static',
    };
};

// ========== run_skill ==========

const runSkillSchema = z.object({
    skillId: z.string().describe('技能ID'),
    params: z.record(z.any()).optional().describe('技能参数'),
});

const runSkillTool: ToolDefinition = {
    name: 'run_skill',
    description: '执行指定的高级技能',
    category: 'skills',
    inputSchema: runSkillSchema,
    tags: ['skills', 'execution'],
    dataSource: 'real', // ?
};

const runSkillHandler: ToolHandler<z.infer<typeof runSkillSchema>> = async (params) => {
    return {
        success: false,
        error: `技能系统暂未完全集成 (Requested: ${params.skillId})`,
        degraded: true,
    };
};

// ========== search_skills ==========

const searchSkillsSchema = z.object({
    keyword: z.string().describe('搜索关键词'),
});

const searchSkillsTool: ToolDefinition = {
    name: 'search_skills',
    description: '搜索可用的技能',
    category: 'skills',
    inputSchema: searchSkillsSchema,
    tags: ['skills', 'discovery'],
    dataSource: 'static',
};

const searchSkillsHandler: ToolHandler<z.infer<typeof searchSkillsSchema>> = async (params) => {
    const allSkills = [
        { id: 'daily_market_report', name: '生成日报', description: '自动生成每日市场复盘报告' },
        { id: 'smart_stock_diagnosis', name: '智能诊股', description: '全方位分析个股基本面和技术面' },
    ];

    const keyword = params.keyword.toLowerCase();
    const filtered = allSkills.filter((s: any) =>
        s.name.toLowerCase().includes(keyword) ||
        s.description.toLowerCase().includes(keyword) ||
        s.id.toLowerCase().includes(keyword)
    );

    return {
        success: true,
        data: filtered,
        source: 'static',
    };
};

// ========== 注册导出 ==========

export const skillsTools: ToolRegistryItem[] = [
    { definition: listSkillsTool, handler: listSkillsHandler },
    { definition: searchSkillsTool, handler: searchSkillsHandler },
    { definition: runSkillTool, handler: runSkillHandler },
];
