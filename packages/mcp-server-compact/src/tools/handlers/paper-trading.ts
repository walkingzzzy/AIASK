import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { timescaleDB } from '../../storage/timescaledb.js';
import { buildManagerHelp } from './manager-help.js';

export const paperTradingManagerTool: ToolDefinition = {
    name: 'paper_trading_manager',
    description: '模拟交易管理（账户、买卖、持仓、交易记录）',
    category: 'trading',
    inputSchema: managerSchema,
    tags: ['paper', 'trading', 'simulation'],
    dataSource: 'real'
};

export const paperTradingManagerHandler: ToolHandler = async (params: any) => {
    const { action, accountId = 'default', accountName, code, quantity, price, initialCapital = 1000000, reason, limit = 50 } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'create_account',
            'get_account',
            'status',
            'buy',
            'sell',
            'trades',
            'history',
            'positions',
        ],
        description: '模拟交易管理入口，action 为空时返回可用动作。',
    });
    if (help) return help;

    // ===== 创建账户 =====
    if (action === 'create_account') {
        const existing = await timescaleDB.getPaperAccount(accountId);
        if (existing) return { success: false, error: '账户已存在' };
        await timescaleDB.createPaperAccount(accountId, accountName || accountId, initialCapital);
        return { success: true, data: { accountId, initialCapital, message: '模拟账户创建成功' } };
    }

    // 确保账户存在
    let account = await timescaleDB.getPaperAccount(accountId);
    if (!account) {
        await timescaleDB.createPaperAccount(accountId, accountId, initialCapital);
        account = await timescaleDB.getPaperAccount(accountId)!;
    }

    if (action === 'get_account' || action === 'status' || !action) {
        const positions = await timescaleDB.getPaperPositions(accountId);
        // 更新实时价格
        if (positions.length > 0) {
            const codes = positions.map((p: any) => p.stock_code);
            const quotesRes = await adapterManager.getBatchQuotes(codes);
            if (quotesRes.success && quotesRes.data) {
                for (const q of quotesRes.data) {
                    await timescaleDB.updatePaperPositionPrice(accountId, q.code, q.price);
                }
            }
        }
        // 重新获取更新后的持仓
        const updatedPositions = await timescaleDB.getPaperPositions(accountId);
        const positionValue = updatedPositions.reduce((sum: number, p: any) => sum + (p.market_value || p.quantity * p.cost_price), 0);
        const totalValue = account.current_capital + positionValue;
        await timescaleDB.updatePaperAccount(accountId, account.current_capital, totalValue);
        const updatedAccount = await timescaleDB.getPaperAccount(accountId);
        return {
            success: true,
            data: {
                account: updatedAccount,
                positions: updatedPositions,
                summary: {
                    cash: account.current_capital,
                    positionValue,
                    totalValue,
                    positionCount: updatedPositions.length,
                }
            }
        };
    }

    // ===== 买入 =====
    if (action === 'buy') {
        if (!code || !quantity) return { success: false, error: '缺少 code 和 quantity' };
        const quoteRes = await adapterManager.getRealtimeQuote(code);
        if (!quoteRes.success || !quoteRes.data) return { success: false, error: '获取行情失败' };
        const buyPrice = price || quoteRes.data.price;
        const stockName = quoteRes.data.name;
        const amount = buyPrice * quantity;
        const commission = amount * 0.0003; // 万三佣金
        const totalCost = amount + commission;
        if (totalCost > account.current_capital) return { success: false, error: `余额不足。需要 ${totalCost.toFixed(2)}，可用 ${account.current_capital.toFixed(2)}` };

        // 更新账户余额
        const newCapital = account.current_capital - totalCost;
        await timescaleDB.updatePaperAccount(accountId, newCapital, account.total_value - totalCost + amount);

        // 更新持仓
        const existingPositions = await timescaleDB.getPaperPositions(accountId);
        const existing = existingPositions.find((p: any) => p.stock_code === code);
        if (existing) {
            const newQty = existing.quantity + quantity;
            const newCost = (existing.cost_price * existing.quantity + buyPrice * quantity) / newQty;
            await timescaleDB.upsertPaperPosition(accountId, code, stockName, newQty, newCost);
        } else {
            await timescaleDB.upsertPaperPosition(accountId, code, stockName, quantity, buyPrice);
        }

        // 记录交易
        const tradeId = `pt_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        await timescaleDB.addPaperTrade({
            id: tradeId,
            accountId,
            stockCode: code,
            stockName,
            tradeType: 'buy',
            price: buyPrice,
            quantity,
            amount,
            commission,
            tradeTime: new Date().toISOString(),
            reason,
        });

        return { success: true, data: { action: 'buy', code, stockName, quantity, price: buyPrice, amount, commission, newBalance: newCapital } };
    }

    // ===== 卖出 =====
    if (action === 'sell') {
        if (!code || !quantity) return { success: false, error: '缺少 code 和 quantity' };
        const positions = await timescaleDB.getPaperPositions(accountId);
        const position = positions.find((p: any) => p.stock_code === code);
        if (!position || position.quantity < quantity) return { success: false, error: '持仓不足' };

        const quoteRes = await adapterManager.getRealtimeQuote(code);
        const sellPrice = price || (quoteRes.success && quoteRes.data ? quoteRes.data.price : position.cost_price);
        const stockName = position.stock_name;
        const amount = sellPrice * quantity;
        const commission = amount * 0.0003;
        const stampTax = amount * 0.001; // 印花税
        const netAmount = amount - commission - stampTax;

        // 更新账户余额
        const newCapital = account.current_capital + netAmount;
        await timescaleDB.updatePaperAccount(accountId, newCapital, account.total_value);

        // 更新持仓
        const newQty = position.quantity - quantity;
        if (newQty > 0) {
            await timescaleDB.upsertPaperPosition(accountId, code, stockName, newQty, position.cost_price);
        } else {
            await timescaleDB.deletePaperPosition(accountId, code);
        }

        // 计算盈亏
        const profit = (sellPrice - position.cost_price) * quantity - commission - stampTax;

        // 记录交易
        const tradeId = `pt_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        await timescaleDB.addPaperTrade({
            id: tradeId,
            accountId,
            stockCode: code,
            stockName,
            tradeType: 'sell',
            price: sellPrice,
            quantity,
            amount,
            commission: commission + stampTax,
            tradeTime: new Date().toISOString(),
            reason,
        });

        return { success: true, data: { action: 'sell', code, stockName, quantity, price: sellPrice, amount: netAmount, profit, newBalance: newCapital } };
    }

    // ===== 交易记录 =====
    if (action === 'trades' || action === 'history') {
        const trades = await timescaleDB.getPaperTrades(accountId, limit);
        return { success: true, data: { trades, total: trades.length } };
    }

    // ===== 持仓列表 =====
    if (action === 'positions') {
        const positions = await timescaleDB.getPaperPositions(accountId);
        return { success: true, data: { positions, total: positions.length } };
    }

    return { success: false, error: `未知操作: ${action}。支持的操作: create_account, status, buy, sell, trades, positions` };
};
