import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';

const userPreferences: Map<string, Record<string, any>> = new Map();

export const userManagerTool: ToolDefinition = { name: 'user_manager', description: '用户画像管理', category: 'user', inputSchema: managerSchema, dataSource: 'real' };

export const userManagerHandler: ToolHandler = async (params: any) => {
    const { action, userId = 'default', preferences, key, value } = params;

    if (!userPreferences.has(userId)) {
        userPreferences.set(userId, { riskLevel: 'medium', investmentHorizon: 'medium_term', sectors: [] });
    }
    const prefs = userPreferences.get(userId)!;

    if (action === 'get') {
        return { success: true, data: { userId, preferences: prefs } };
    }

    if (action === 'set' && key && value !== undefined) {
        prefs[key] = value;
        return { success: true, data: { userId, updated: { [key]: value } } };
    }

    if (action === 'update' && preferences) {
        Object.assign(prefs, preferences);
        return { success: true, data: { userId, preferences: prefs } };
    }

    return { success: true, data: { userId, preferences: prefs } };
};
