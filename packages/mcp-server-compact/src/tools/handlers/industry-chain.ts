import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';

export const industryChainManagerTool: ToolDefinition = {
    name: 'industry_chain_manager',
    description: '产业链分析管理',
    category: 'semantic',
    inputSchema: managerSchema,
    tags: ['industry', 'manager'],
    dataSource: 'real',
};

export const industryChainManagerHandler: ToolHandler = async (params: any) => {
    // 简单路由到 industry-chain service
    const { action } = params;
    const { getAllChains, searchChainByKeyword } = await import('../../services/industry-chain.js');

    if (action === 'get_chains') return { success: true, data: getAllChains() };
    if (action === 'search' && params.keyword) return { success: true, data: searchChainByKeyword(params.keyword) };

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['get_chains', 'search', 'help'] } };
    }

    return { success: false, error: `Unknown action: ${action}`, degraded: true };
};
