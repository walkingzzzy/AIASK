import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { buildManagerHelp } from './manager-help.js';

export const liveTradingManagerTool: ToolDefinition = { name: 'live_trading_manager', description: '实盘交易管理', category: 'trading', inputSchema: managerSchema, dataSource: 'real' };

export const liveTradingManagerHandler: ToolHandler = async (params: any) => {
    const help = buildManagerHelp(params.action, {
        actions: ['status', 'connect', 'submit_order', 'cancel_order', 'positions', 'orders', 'trades'],
        description: '实盘交易入口，需接入券商SDK后才能使用。',
    });
    if (help) return help;

    return {
        success: false,
        error: '实盘交易数据源未接入：请配置券商SDK后再调用',
    };
};
