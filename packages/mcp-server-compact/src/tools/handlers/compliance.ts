import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';

export const complianceManagerTool: ToolDefinition = { name: 'compliance_manager', description: '合规检查管理', category: 'trading', inputSchema: managerSchema, dataSource: 'real' };

export const complianceManagerHandler: ToolHandler = async (params: any) => {
    const { action, stocks, weights, maxSinglePosition = 0.1, maxSectorWeight = 0.3 } = params;

    if (action === 'check' || !action) {
        if (!stocks || !weights) {
            return { success: false, error: '缺少 stocks 和 weights 参数。Usage: compliance_manager(action="check", stocks=["000001"], weights=[1.0])' };
        }

        const violations: string[] = [];
        const warnings: string[] = [];

        // 检查单一持仓比例
        for (let i = 0; i < stocks.length; i++) {
            if ((weights[i] || 0) > maxSinglePosition) {
                violations.push(`${stocks[i]} 持仓比例 ${(weights[i] * 100).toFixed(1)}% 超过限制 ${(maxSinglePosition * 100).toFixed(1)}%`);
            }
            if ((weights[i] || 0) > maxSinglePosition * 0.8) {
                warnings.push(`${stocks[i]} 持仓比例接近限制`);
            }
        }

        // 检查权重总和
        const totalWeight = weights.reduce((a: number, b: number) => a + (b || 0), 0);
        if (Math.abs(totalWeight - 1) > 0.01) {
            warnings.push(`权重总和为 ${(totalWeight * 100).toFixed(1)}%，应为 100%`);
        }

        return {
            success: true,
            data: {
                compliant: violations.length === 0,
                violations,
                warnings,
                rules: {
                    maxSinglePosition: (maxSinglePosition * 100) + '%',
                    maxSectorWeight: (maxSectorWeight * 100) + '%',
                }
            }
        };
    }

    if (action === 'list_rules') {
        return {
            success: true,
            data: {
                rules: [
                    { name: '单一持仓限制', defaultValue: '10%', description: '单只股票最大持仓比例' },
                    { name: '板块集中度', defaultValue: '30%', description: '单一板块最大权重' },
                    { name: 'ST股禁止', defaultValue: '启用', description: '禁止买入ST股票' },
                ]
            }
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['check', 'monitor', 'report', 'help'] } };
    }

    return { success: false, error: `Unknown action: ${action}` };
};
