import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';

export const sectorManagerTool: ToolDefinition = {
    name: 'sector_manager',
    description: '板块轮动与资金管理（行情、轮动、成分股、景气度）',
    category: 'market_data',
    inputSchema: managerSchema,
    tags: ['sector', 'manager', 'rotation'],
    dataSource: 'real',
};

interface BlockData {
    code: string;
    name: string;
    changePercent?: number;
    change?: number;
    stockCount?: number;
}

export const sectorManagerHandler: ToolHandler = async (params: any) => {
    const { action, topN = 10, type = 'industry', code, name, period = '5d' } = params;

    // ===== 板块资金流向 =====
    if (action === 'get_sector_flow' || action === 'flow') {
        const res = await adapterManager.getSectorFlow(topN);
        return { success: true, data: res };
    }

    // ===== 板块实时行情 =====
    if (action === 'get_sector_realtime' || action === 'realtime') {
        // 通过 akshare-mcp 获取行业/概念板块行情
        const toolName = type === 'concept' ? 'get_concept_fund_flow' : 'get_sector_fund_flow';
        const blocksRes = await callAkshareMcpTool<BlockData[]>(toolName, { top_n: 50 });

        if (!blocksRes.success || !blocksRes.data) {
            // 降级到 getSectorFlow
            const flowRes = await adapterManager.getSectorFlow(topN);
            if (flowRes.success && flowRes.data) {
                return {
                    success: true,
                    data: {
                        type,
                        sectors: flowRes.data.slice(0, topN),
                        source: 'sector_flow',
                    },
                };
            }
            return { success: false, error: '获取板块数据失败' };
        }

        // 排序并返回涨幅榜
        const sorted = blocksRes.data.sort((a: BlockData, b: BlockData) => (b.changePercent || 0) - (a.changePercent || 0));
        return {
            success: true,
            data: {
                type,
                gainers: sorted.slice(0, topN),
                losers: sorted.slice(-topN).reverse(),
                total: sorted.length,
                timestamp: new Date().toISOString(),
            },
        };
    }

    // ===== 板块成分股 =====
    if (action === 'get_sector_stocks' || action === 'stocks') {
        if (!code && !name) return { success: false, error: '需要板块代码(code)或名称(name)' };

        // 暂时返回功能说明
        return {
            success: true,
            data: {
                sector: code || name,
                message: '板块成分股功能需要扩展数据源',
                note: '建议使用 search_stocks 工具按行业搜索',
            },
            degraded: true,
        };
    }

    // ===== 板块轮动分析 =====
    if (action === 'analyze_rotation' || action === 'rotation') {
        // 获取行业板块资金流向
        const blocksRes = await callAkshareMcpTool<BlockData[]>('get_sector_fund_flow', { top_n: 30 });

        if (!blocksRes.success || !blocksRes.data) {
            return { success: false, error: '获取板块数据失败' };
        }

        // 简化的轮动分析
        const blocks = blocksRes.data;
        const strongSectors = blocks.filter((b: BlockData) => (b.changePercent || 0) > 2).slice(0, 5);
        const weakSectors = blocks.filter((b: BlockData) => (b.changePercent || 0) < -2).slice(0, 5);

        // 计算板块强度排名
        const strengthRanking = blocks
            .map((b: BlockData, idx: number) => ({
                name: b.name,
                code: b.code,
                rank: idx + 1,
                change: b.changePercent,
                strength: (b.changePercent || 0) > 0 ? 'strong' : 'weak',
            }))
            .slice(0, topN);

        return {
            success: true,
            data: {
                period,
                strongSectors: strongSectors.map((s: BlockData) => ({ name: s.name, change: s.changePercent })),
                weakSectors: weakSectors.map((s: BlockData) => ({ name: s.name, change: s.changePercent })),
                strengthRanking,
                rotationSignal: strongSectors.length > weakSectors.length ? '资金流入热门板块' : '板块分化明显',
                suggestion: strongSectors.length > 3 ? '市场热度高，关注领涨板块' : '谨慎操作，等待板块企稳',
            },
        };
    }

    // ===== 板块景气度 =====
    if (action === 'sector_prosperity' || action === 'prosperity') {
        // 基于资金流向的景气度评估
        const [flowRes, blocksRes] = await Promise.all([
            adapterManager.getSectorFlow(20),
            callAkshareMcpTool<BlockData[]>('get_sector_fund_flow', { top_n: 20 }),
        ]);

        const blocks = blocksRes.success && blocksRes.data ? blocksRes.data : [];

        // 简化的景气度计算
        const prosperityData = blocks.slice(0, 20).map((b: BlockData) => {
            const change = b.changePercent || 0;
            let prosperityScore = 50; // 基础分
            if (change > 3) prosperityScore = 80;
            else if (change > 1) prosperityScore = 65;
            else if (change > 0) prosperityScore = 55;
            else if (change > -1) prosperityScore = 45;
            else if (change > -3) prosperityScore = 35;
            else prosperityScore = 20;

            return {
                sector: b.name,
                code: b.code,
                change: change,
                prosperityScore,
                level: prosperityScore >= 70 ? '高景气' : prosperityScore >= 50 ? '中性' : '低景气',
            };
        });

        return {
            success: true,
            data: {
                prosperityRanking: prosperityData.sort((a: any, b: any) => b.prosperityScore - a.prosperityScore),
                highProsperity: prosperityData.filter((p: any) => p.level === '高景气').length,
                lowProsperity: prosperityData.filter((p: any) => p.level === '低景气').length,
                marketMood: prosperityData.filter((p: any) => p.prosperityScore > 50).length > 10 ? '乐观' : '谨慎',
            },
        };
    }

    // ===== 宏观到板块映射 =====
    if (action === 'macro_to_sector' || action === 'macro_mapping') {
        // 基于宏观经济指标推荐相关板块
        const macroSectorMapping: Record<string, string[]> = {
            '利率下行': ['房地产', '券商', '银行', '保险'],
            '利率上行': ['银行', '保险'],
            'CPI上涨': ['消费', '农业', '食品饮料'],
            'PPI上涨': ['有色金属', '钢铁', '煤炭', '化工'],
            '基建投资': ['建筑', '水泥', '工程机械', '钢铁'],
            '科技创新': ['半导体', '软件', '人工智能', '新能源'],
            '消费升级': ['白酒', '医药', '旅游', '教育'],
            '碳中和': ['光伏', '风电', '储能', '新能源车'],
        };

        return {
            success: true,
            data: {
                macroSectorMapping,
                usage: '根据宏观经济趋势选择相关板块进行配置',
                note: '具体配置需结合市场情况和个人风险偏好',
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: flow, realtime, stocks, rotation, prosperity, macro_mapping` };
};
