import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';

export const researchManagerTool: ToolDefinition = {
    name: 'research_manager',
    description: '研报管理（研报搜索、盈利预测、评级分析、目标价）',
    category: 'research',
    inputSchema: managerSchema,
    tags: ['research', 'report', 'forecast', 'rating'],
    dataSource: 'real' // Now we use real AKShare-MCP
};

export const researchManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, keyword, limit = 10 } = params;

    // ===== 搜索研报 =====
    if (action === 'search_reports' || action === 'reports') {
        const result = await callAkshareMcpTool('get_research_reports', {
            symbol: code || keyword || "",
            limit
        });

        if (!result.success) {
            return { success: false, error: result.error || 'Failed to fetch reports' };
        }

        // AKShare usually returns columns: "代码","名称","标题","类型","发布日期","机构","评级","预测变动"
        // key mapping might vary, assume raw dict
        return {
            success: true,
            data: {
                total: result.data ? (result.data as any[]).length : 0,
                reports: result.data
            }
        };
    }

    // ===== 个股研报详情 (Simplify to search with code) =====
    if (action === 'get_stock_research') {
        if (!code) return { success: false, error: 'Missing code' };

        const result = await callAkshareMcpTool('get_research_reports', {
            symbol: code,
            limit
        });

        return {
            success: true,
            data: result.success ? result.data : []
        };
    }

    // ===== 获取盈利预测/目标价/评级 =====
    if (action === 'get_profit_forecast' || action === 'get_target_price' || action === 'get_rating_consensus') {
        if (!code) return { success: false, error: 'Missing code' };

        const result = await callAkshareMcpTool('get_profit_forecast', { symbol: code });

        if (!result.success || !result.data) {
            return { success: false, error: result.error || 'No forecast data found' };
        }

        // Handle both Array and Object { items: [] } formats
        const rawData = result.data;
        const forecasts = (Array.isArray(rawData) ? rawData : (rawData as any)?.items || []) as any[];

        // Analyze target price/rating if action specific
        if (action === 'get_target_price') {
            // Try to extract price targets if available in columns (often just EPS forecast, need to check columns)
            // If explicit target price column exists, aggregate it.
            // Otherwise return raw forecast data
            return { success: true, data: forecasts };
        }

        if (action === 'get_rating_consensus') {
            // Aggregate ratings
            const ratings: Record<string, number> = {};
            forecasts.forEach((f: any) => {
                const rating = f['评级'] || f['rating'] || 'Unknown';
                ratings[rating] = (ratings[rating] || 0) + 1;
            });
            return {
                success: true,
                data: {
                    consensus: ratings,
                    details: forecasts.slice(0, limit)
                }
            };
        }

        return { success: true, data: forecasts };
    }

    // ===== 最新研报 =====
    if (action === 'get_latest_reports' || action === 'latest') {
        const result = await callAkshareMcpTool('get_research_reports', {
            limit: limit || 10
        });
        return { success: true, data: result.success ? result.data : [] };
    }

    // ===== 分析师排名 =====
    if (action === 'get_analyst_rank' || action === 'analyst_rank') {
        const result = await callAkshareMcpTool('get_analyst_ranking', {
            year: params.year
        });
        return { success: true, data: result.success ? result.data : [] };
    }

    // ===== 搜索研报 (Alias) =====
    if (action === 'search') {
        const result = await callAkshareMcpTool('search_research', {
            keyword: keyword || "",
            stock_code: code || ""
        });
        return { success: true, data: result.success ? result.data : [] };
    }

    if (action === 'list' || action === 'help') {
        return {
            success: true,
            data: {
                actions: ['search', 'latest', 'analyst_rank', 'help', 'get_stock_research', 'get_profit_forecast'],
                description: '研报管理工具，支持搜索研报、查看最新研报、分析师排名及个股盈利预测'
            }
        };
    }

    return { success: false, error: `Unknown action: ${action}. Supported: search, latest, analyst_rank, get_stock_research, get_profit_forecast` };
};
