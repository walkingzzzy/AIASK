import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { timescaleDB } from '../../storage/timescaledb.js';

export const alertsManagerTool: ToolDefinition = {
    name: 'alerts_manager',
    description: '预警管理（价格、指标、涨跌停、资金流向、组合条件）',
    category: 'alerts',
    inputSchema: managerSchema,
    tags: ['alerts', 'manager', 'price', 'indicator'],
    dataSource: 'real',
};

export const alertsManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, name, type = 'price', condition, value, threshold, period, alertId, alertName, conditions, includeTriggered = false } = params;

    const generateId = () => `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // ===== 创建告警 =====
    if (action === 'create') {
        if (!code) return { success: false, error: '缺少股票代码' };
        // 获取股票名称
        let stockName = name;
        if (!stockName) {
            const quoteRes = await adapterManager.getRealtimeQuote(code);
            stockName = quoteRes.success && quoteRes.data ? quoteRes.data.name : code;
        }



        if (type === 'price') {
            if (!condition || value === undefined) return { success: false, error: '价格告警需要 condition 和 value' };
            const id = await timescaleDB.createPriceAlert({ code, targetPrice: value, condition });
            return { success: true, data: { alertId: id, type: 'price', message: `价格告警创建成功: ${code} ${condition} ${value}` } };
        }

        if (type === 'indicator') {
            if (!condition) return { success: false, error: '指标告警需要 condition (如 RSI>70, MACD金叉)' };
            const indName = name || 'indicator';
            const id = await timescaleDB.createIndicatorAlert({ code, indicator: indName, condition, value: typeof value === 'number' ? value : undefined });
            return { success: true, data: { alertId: id, type: 'indicator', message: `指标告警创建成功: ${code} ${condition}` } };
        }

        if (type === 'limit') {
            if (!condition) return { success: false, error: '涨跌停告警需要 condition (如 limit_up, limit_down)' };
            const id = await timescaleDB.createLimitAlert({ code, condition });
            return { success: true, data: { alertId: id, type: 'limit', message: `涨跌停告警创建成功: ${code} ${condition}` } };
        }

        if (type === 'fund_flow') {
            if (!condition || threshold === undefined) return { success: false, error: '资金流向告警需要 condition 和 threshold' };
            const id = await timescaleDB.createFundFlowAlert({ code, condition, threshold });
            return { success: true, data: { alertId: id, type: 'fund_flow', message: `资金流向告警创建成功: ${code} ${condition} ${threshold}` } };
        }

        if (type === 'combo') {
            if (!conditions || !alertName) return { success: false, error: '组合告警需要 alertName 和 conditions (JSON字符串)' };
            // conditions is expected to be array in new signature? 
            // In DB: conditions is JSONB/Text. 
            // In createComboAlert adapter: accepts { name, conditions: any[], logic }
            // Handler receives conditions as maybe string or object.

            let condArray: any[] = [];
            try {
                condArray = typeof conditions === 'string' ? JSON.parse(conditions) : conditions;
            } catch (e) { return { success: false, error: 'Conditions 解析失败' }; }

            const id = await timescaleDB.createComboAlert({ name: alertName, conditions: condArray, logic: 'and' });
            return { success: true, data: { alertId: id, type: 'combo', message: `组合告警创建成功: ${alertName}` } };
        }

        return { success: false, error: `未知告警类型: ${type}。支持: price, indicator, limit, fund_flow, combo` };
    }

    // ===== 列出告警 =====
    if (action === 'list') {
        const result: Record<string, any[]> = {};

        if (!type || type === 'all' || type === 'price') {
            const priceAlerts = await timescaleDB.getPriceAlerts(includeTriggered);
            result.priceAlerts = priceAlerts.filter((a: any) => !code || a.code === code);
        }
        if (!type || type === 'all' || type === 'indicator') {
            const indicatorAlerts = await timescaleDB.getIndicatorAlerts(includeTriggered);
            result.indicatorAlerts = indicatorAlerts.filter((a: any) => !code || a.code === code);
        }
        if (!type || type === 'all' || type === 'limit') {
            const limitAlerts = await timescaleDB.getLimitAlerts(includeTriggered);
            result.limitAlerts = limitAlerts.filter((a: any) => !code || a.code === code);
        }
        if (!type || type === 'all' || type === 'fund_flow') {
            const fundFlowAlerts = await timescaleDB.getFundFlowAlerts(includeTriggered);
            result.fundFlowAlerts = fundFlowAlerts.filter((a: any) => !code || a.code === code);
        }
        if (!type || type === 'all' || type === 'combo') {
            const comboAlerts = await timescaleDB.getComboAlerts(includeTriggered);
            result.comboAlerts = comboAlerts.filter((a: any) => !code || a.code === code); // Adapter returns fields.
        }

        const totalCount = Object.values(result).reduce((sum, arr) => sum + arr.length, 0);
        return { success: true, data: { ...result, totalCount } };
    }

    // ===== 删除告警 =====
    if (action === 'delete') {
        if (!alertId) return { success: false, error: '缺少 alertId' };
        let deleted = false;
        // alertId is likely string from input, but DB uses integer ID (SERIAL).
        // Since input is 'any' (params), we can just pass it. Adapter expects string? 
        // TimescaleDBAdapter methods take string id currently (e.g. deletePriceAlert(id: string)).
        // But the DB column is SERIAL (int). PostgreSQL handles string-to-int cast usually if it looks like int.
        // However, user input might be legacy string ID e.g. "alert_123". This won't cast to int.
        // But we just deployed new schema, so existing alerts are gone or empty. New alerts will have int IDs (as string).

        // We try deleting from all tables blindly? 
        // This is inefficient but compatible with previous design.

        deleted = await timescaleDB.deletePriceAlert(alertId) || deleted;
        deleted = await timescaleDB.deleteIndicatorAlert(alertId) || deleted;
        deleted = await timescaleDB.deleteLimitAlert(alertId) || deleted;
        deleted = await timescaleDB.deleteFundFlowAlert(alertId) || deleted;
        deleted = await timescaleDB.deleteComboAlert(alertId) || deleted;
        return { success: deleted, data: { message: deleted ? '告警已删除' : '告警不存在' } };
    }

    // ===== 检查告警 =====
    if (action === 'check') {
        const triggeredAlerts: any[] = [];

        // 检查价格告警
        const priceAlerts = await timescaleDB.getPriceAlerts(false);
        for (const alert of priceAlerts) {
            try {
                const quote = await adapterManager.getRealtimeQuote(alert.code);
                if (!quote.success || !quote.data) continue;
                const price = quote.data.price;
                let triggered = false;
                if (alert.condition === 'above' && price > alert.targetPrice) triggered = true;
                if (alert.condition === 'below' && price < alert.targetPrice) triggered = true;
                if (alert.condition === 'cross_up' && price >= alert.targetPrice) triggered = true;
                if (alert.condition === 'cross_down' && price <= alert.targetPrice) triggered = true;
                if (triggered) {
                    await timescaleDB.triggerAlert(String(alert.id), 'price');
                    triggeredAlerts.push({ type: 'price', ...alert, currentPrice: price });
                }
            } catch { /* skip */ }
        }

        // 检查涨跌停告警
        const limitAlerts = await timescaleDB.getLimitAlerts(false);
        if (limitAlerts.length > 0) {
            const codes = [...new Set(limitAlerts.map((a: any) => a.code))];
            const quotesRes = await adapterManager.getBatchQuotes(codes);
            if (quotesRes.success && quotesRes.data) {
                const changeMap = new Map<string, number>();
                quotesRes.data.forEach((q: any) => changeMap.set(q.code, q.changePercent));
                for (const alert of limitAlerts) {
                    const change = changeMap.get(alert.code);
                    if (change === undefined) continue;
                    let triggered = false;
                    if (alert.condition === 'limit_up' && change >= 9.9) triggered = true;
                    if (alert.condition === 'limit_down' && change <= -9.9) triggered = true;
                    if (triggered) {
                        await timescaleDB.triggerAlert(String(alert.id), 'limit');
                        triggeredAlerts.push({ type: 'limit', ...alert, changePercent: change });
                    }
                }
            }
        }

        // 检查资金流向告警
        const fundFlowAlerts = await timescaleDB.getFundFlowAlerts(false);
        for (const alert of fundFlowAlerts) {
            try {
                const flowRes = await adapterManager.getFundFlow(alert.code);
                if (!flowRes.success || !flowRes.data) continue;
                const mainInflow = flowRes.data.mainNetInflow;
                let triggered = false;
                if (alert.condition === 'main_inflow_above' && mainInflow > alert.threshold) triggered = true;
                if (alert.condition === 'main_outflow_above' && mainInflow < -alert.threshold) triggered = true;
                if (triggered) {
                    await timescaleDB.triggerAlert(String(alert.id), 'fund_flow');
                    triggeredAlerts.push({ type: 'fund_flow', ...alert, mainNetInflow: mainInflow });
                }
            } catch { /* skip */ }
        }

        return { success: true, data: { triggeredAlerts, checkedCount: priceAlerts.length + limitAlerts.length + fundFlowAlerts.length } };
    }

    // ===== 告警类型说明 =====
    if (action === 'help' || action === 'types') {
        return {
            success: true,
            data: {
                alertTypes: [
                    { type: 'price', description: '价格告警', params: ['code', 'condition (above/below/cross_up/cross_down)', 'value'] },
                    { type: 'indicator', description: '指标告警', params: ['code', 'condition (如 RSI>70)', 'period'] },
                    { type: 'limit', description: '涨跌停告警', params: ['code', 'condition (limit_up/limit_down)'] },
                    { type: 'fund_flow', description: '资金流向告警', params: ['code', 'condition (main_inflow_above/main_outflow_above)', 'threshold'] },
                    { type: 'combo', description: '组合条件告警', params: ['code', 'alertName', 'conditions (JSON)'] },
                ],
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持的操作: create, list, delete, check, help` };
};
