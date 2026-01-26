import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { timescaleDB } from '../../storage/timescaledb.js';

export const watchlistManagerTool: ToolDefinition = { name: 'watchlist_manager', description: '自选股管理（分组、增删、行情）', category: 'user', inputSchema: managerSchema, dataSource: 'real' };

export const watchlistManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, name, groupId = 'default', notes } = params;

    // ===== 列出自选股 =====
    if (action === 'list' || action === 'get' || !action) {
        const items = await timescaleDB.getWatchlist(groupId !== 'all' ? groupId : undefined);
        if (items.length === 0) {
            return { success: true, data: { stocks: [], total: 0, groupId } };
        }
        // 获取实时行情
        const codes = items.map((i: any) => i.code);
        const quotesRes = await adapterManager.getBatchQuotes(codes);
        const priceMap = new Map<string, { price: number; changePercent: number; name: string }>();
        if (quotesRes.success && quotesRes.data) {
            quotesRes.data.forEach((q: any) => priceMap.set(q.code, { price: q.price, changePercent: q.changePercent, name: q.name }));
        }
        const enriched = items.map((i: any) => {
            const quote = priceMap.get(i.code);
            return {
                code: i.code,
                name: quote?.name || i.name,
                price: quote?.price || null,
                changePercent: quote?.changePercent || null,
                notes: i.notes,
                addedAt: i.addedAt,
            };
        });
        return { success: true, data: { stocks: enriched, total: enriched.length, groupId } };
    }

    // ===== 添加自选股 =====
    if (action === 'add') {
        if (!code) return { success: false, error: '缺少股票代码' };
        let stockName = name;
        if (!stockName) {
            const quoteRes = await adapterManager.getRealtimeQuote(code);
            stockName = quoteRes.success && quoteRes.data ? quoteRes.data.name : code;
        }
        await timescaleDB.addToWatchlist(code, stockName, groupId);
        return { success: true, data: { message: `${code} ${stockName} 已添加到自选股`, groupId, notes } };
    }

    // ===== 删除自选股 =====
    if (action === 'remove') {
        if (!code) return { success: false, error: '缺少股票代码' };
        const removed = await timescaleDB.removeFromWatchlist(code, groupId);
        return { success: removed, data: { message: removed ? `${code} 已从自选股移除` : '股票不在自选股中' } };
    }

    // ===== 列出分组 =====
    if (action === 'list_groups' || action === 'groups') {
        const groups = await timescaleDB.getWatchlistGroups();
        return { success: true, data: { groups } };
    }

    // ===== 批量添加 =====
    if (action === 'batch_add') {
        const codes = params.codes as string[];
        if (!codes || codes.length === 0) return { success: false, error: '缺少股票代码列表' };
        const quotesRes = await adapterManager.getBatchQuotes(codes);
        const nameMap = new Map<string, string>();
        if (quotesRes.success && quotesRes.data) {
            quotesRes.data.forEach((q: any) => nameMap.set(q.code, q.name));
        }
        let added = 0;
        for (const c of codes) {
            await timescaleDB.addToWatchlist(c, nameMap.get(c) || c, groupId);
            added++;
        }
        return { success: true, data: { message: `已添加 ${added} 只股票到自选股`, groupId } };
    }

    return { success: false, error: `未知操作: ${action}。支持的操作: list, add, remove, list_groups, batch_add` };
};
