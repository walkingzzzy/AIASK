/**
 * 功能工作台 - MCP 能力产品化入口
 */

import React, { useEffect, useMemo, useState } from 'react';
import VisualizationRenderer from '../visualization/VisualizationRenderer';
import type { TradePlan, TradePlanStatus, WatchlistMeta, Visualization } from '../../../shared/types';

const DEFAULT_MCP_SERVER_URL = 'http://localhost:9898';

type WorkbenchTab =
    | 'alerts'
    | 'monitor'
    | 'risk'
    | 'research'
    | 'quant'
    | 'macro'
    | 'live'
    | 'ledger';

type ToolResult = {
    success: boolean;
    data?: unknown;
    error?: string;
    requiresConfirmation?: boolean;
    confirmation?: { toolName: string; arguments?: Record<string, unknown>; message?: string };
};

interface WorkbenchModalProps {
    isOpen: boolean;
    onClose: () => void;
}

const parseNumber = (value?: string): number | undefined => {
    if (!value) return undefined;
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : undefined;
};

const extractList = (result?: ToolResult): unknown[] => {
    if (!result?.success || !result.data) return [];
    if (Array.isArray(result.data)) return result.data;
    const data = result.data as Record<string, unknown>;
    if (Array.isArray(data.alerts)) return data.alerts;
    if (Array.isArray(data.list)) return data.list;
    if (Array.isArray(data.data)) return data.data;
    if (Array.isArray(data.stocks)) return data.stocks;
    return [];
};

const WorkbenchModal: React.FC<WorkbenchModalProps> = ({ isOpen, onClose }) => {
    const isWeb = typeof window !== 'undefined' && window.electronAPI?.platform === 'web';
    const [activeTab, setActiveTab] = useState<WorkbenchTab>('alerts');
    const [mcpUrl, setMcpUrl] = useState(DEFAULT_MCP_SERVER_URL);
    const [notificationPrefs, setNotificationPrefs] = useState({
        enabled: true,
        quietHours: [22, 23, 0, 1, 2, 3, 4, 5, 6],
        maxDaily: 20,
        channels: ['desktop'],
    });

    useEffect(() => {
        if (isOpen && isWeb) {
            setMcpUrl(localStorage.getItem('aethertrade_mcp_url') || DEFAULT_MCP_SERVER_URL);
        }
    }, [isOpen, isWeb]);

    useEffect(() => {
        if (!isOpen) return;
        window.electronAPI.config.get().then(res => {
            if (res.success && res.data?.notificationPreferences) {
                const prefs = res.data.notificationPreferences;
                setNotificationPrefs({
                    enabled: prefs.enabled ?? true,
                    quietHours: prefs.quietHours ?? [22, 23, 0, 1, 2, 3, 4, 5, 6],
                    maxDaily: prefs.maxDaily ?? 20,
                    channels: prefs.channels ?? ['desktop'],
                });
            }
        }).catch(() => { });
    }, [isOpen]);

    const callMcpTool = async (name: string, args: Record<string, unknown> = {}): Promise<ToolResult> => {
        if (isWeb) {
            const res = await fetch(`${mcpUrl}/api/tools/${name}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(args),
            });
            return res.json();
        }
        return window.electronAPI.mcp.callTool(name, args) as Promise<ToolResult>;
    };

    const invokeTool = async (name: string, args: Record<string, unknown> = {}): Promise<ToolResult> => {
        const result = await callMcpTool(name, args);
        if (result?.requiresConfirmation) {
            const ok = window.confirm(result.confirmation?.message || `工具 ${name} 需要确认执行`);
            if (!ok) return result;
            const confirmArgs = {
                ...(result.confirmation?.arguments || args),
                _confirmed: true,
            };
            return callMcpTool(result.confirmation?.toolName || name, confirmArgs);
        }
        return result;
    };

    const pushNotification = (title: string, body: string) => {
        if (!notificationPrefs.enabled || !notificationPrefs.channels.includes('desktop')) return;
        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') {
            new Notification(title, { body });
            return;
        }
        if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body });
                }
            });
        }
    };

    const renderResult = (title: string, data: unknown, type: Visualization['type'] = 'table') => (
        <div className="pc-section">
            {data !== undefined && data !== null ? (
                <VisualizationRenderer visualization={{ type, title, data }} />
            ) : (
                <>
                    <h3>{title}</h3>
                    <div className="pc-empty">暂无数据</div>
                </>
            )}
        </div>
    );

    // ========== 告警中心 ==========
    const [alertLoading, setAlertLoading] = useState(false);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
    const [alertForm, setAlertForm] = useState({
        type: 'price',
        symbol: '',
        condition: 'above',
        price: '',
        threshold: '',
        period: 'daily',
        preset: '',
        custom: '',
        name: '',
    });
    const [alertLists, setAlertLists] = useState({
        price: [] as unknown[],
        indicator: [] as unknown[],
        limit: [] as unknown[],
        fundFlow: [] as unknown[],
        combo: [] as unknown[],
    });
    const [comboPresets, setComboPresets] = useState<Array<{ key: string; name: string; description: string }>>([]);

    const refreshAlerts = async () => {
        setAlertLoading(true);
        setAlertMessage(null);
        try {
            const [priceRes, indicatorRes, limitRes, fundRes, comboRes, presetRes] = await Promise.all([
                invokeTool('get_price_alerts', { include_triggered: true }),
                invokeTool('get_indicator_alerts', { include_triggered: true }),
                invokeTool('get_limit_alerts', { include_triggered: true }),
                invokeTool('get_fund_flow_alerts', { include_triggered: true }),
                invokeTool('get_combo_alerts', { include_triggered: true }),
                invokeTool('get_combo_presets'),
            ]);
            setAlertLists({
                price: extractList(priceRes),
                indicator: extractList(indicatorRes),
                limit: extractList(limitRes),
                fundFlow: extractList(fundRes),
                combo: extractList(comboRes),
            });
            const presetData = presetRes.success && presetRes.data && typeof presetRes.data === 'object'
                ? (presetRes.data as { presets?: Array<{ key: string; name: string; description: string }> }).presets || []
                : [];
            setComboPresets(presetData);
        } catch (error) {
            setAlertMessage(`加载告警失败: ${(error as Error).message}`);
        } finally {
            setAlertLoading(false);
        }
    };

    const handleCreateAlert = async () => {
        setAlertMessage(null);
        const symbol = alertForm.symbol.trim();
        if (!symbol) {
            setAlertMessage('请输入股票代码');
            return;
        }
        let toolName = 'create_price_alert';
        let args: Record<string, unknown> = {};
        if (alertForm.type === 'price') {
            toolName = 'create_price_alert';
            const price = parseNumber(alertForm.price);
            if (!price) {
                setAlertMessage('请输入价格');
                return;
            }
            args = {
                symbol,
                condition: alertForm.condition,
                price,
            };
            const threshold = parseNumber(alertForm.threshold);
            if (threshold !== undefined) {
                args.threshold = threshold;
            }
        } else if (alertForm.type === 'indicator') {
            toolName = 'create_indicator_alert';
            args = {
                symbol,
                condition: alertForm.condition,
                period: alertForm.period || 'daily',
            };
        } else if (alertForm.type === 'limit') {
            toolName = 'create_limit_alert';
            args = { symbol, condition: alertForm.condition };
        } else if (alertForm.type === 'fund_flow') {
            toolName = 'create_fund_flow_alert';
            args = {
                symbol,
                condition: alertForm.condition,
            };
            const threshold = parseNumber(alertForm.threshold);
            if (threshold !== undefined) {
                args.threshold = threshold;
            }
        } else if (alertForm.type === 'combo') {
            toolName = 'create_combo_alert';
            args = {
                symbol,
                preset: alertForm.preset || undefined,
                custom_conditions: alertForm.custom || undefined,
                name: alertForm.name || undefined,
            };
        }

        const result = await invokeTool(toolName, args);
        if (!result.success) {
            setAlertMessage(result.error || '创建告警失败');
            return;
        }
        setAlertMessage('告警已创建');
        refreshAlerts();
    };

    const handleDeleteAlert = async (type: keyof typeof alertLists, id?: string) => {
        if (!id) return;
        const toolMap: Record<typeof type, string> = {
            price: 'delete_price_alert',
            indicator: 'delete_indicator_alert',
            limit: 'delete_limit_alert',
            fundFlow: 'delete_fund_flow_alert',
            combo: 'delete_combo_alert',
        };
        const result = await invokeTool(toolMap[type], { alert_id: id });
        if (!result.success) {
            setAlertMessage(result.error || '删除失败');
            return;
        }
        refreshAlerts();
    };

    const handleCheckAlerts = async () => {
        const [priceRes, indicatorRes, limitRes, fundRes, comboRes] = await Promise.all([
            invokeTool('check_price_alerts'),
            invokeTool('check_indicator_alerts'),
            invokeTool('check_limit_alerts'),
            invokeTool('check_fund_flow_alerts'),
            invokeTool('check_combo_alerts'),
        ]);
        const extractTriggered = (result?: ToolResult): unknown[] => {
            if (!result?.success || !result.data) return [];
            const data = result.data as Record<string, unknown>;
            if (Array.isArray(data.triggered)) return data.triggered;
            return extractList(result);
        };
        const triggered = [
            ...extractTriggered(priceRes),
            ...extractTriggered(indicatorRes),
            ...extractTriggered(limitRes),
            ...extractTriggered(fundRes),
            ...extractTriggered(comboRes),
        ];
        if (triggered.length > 0) {
            pushNotification('告警触发', `本次触发 ${triggered.length} 条告警`);
        }
        setAlertMessage(triggered.length > 0 ? `触发 ${triggered.length} 条告警` : '未检测到触发');
    };

    // ========== 盯盘 ==========
    const [monitorLoading, setMonitorLoading] = useState(false);
    const [monitorData, setMonitorData] = useState({
        overview: null as unknown,
        anomalies: null as unknown,
        realtime: null as unknown,
        limitUp: null as unknown,
        limitStats: null as unknown,
        sectorRotation: null as unknown,
        marketReport: null as unknown,
        hotConcepts: null as unknown,
        sectorRealtime: null as unknown,
    });

    const refreshMonitor = async () => {
        setMonitorLoading(true);
        try {
            const [
                overviewRes,
                anomaliesRes,
                realtimeRes,
                limitRes,
                limitStatRes,
                rotationRes,
                reportRes,
                hotConceptRes,
                sectorRealtimeRes,
            ] = await Promise.all([
                invokeTool('get_market_overview'),
                invokeTool('scan_market_anomalies', { include_history: true }),
                invokeTool('get_realtime_anomalies', { limit: 20 }),
                invokeTool('get_daily_limit_up_basic', {}),
                invokeTool('get_limit_up_statistics_basic', {}),
                invokeTool('analyze_sector_rotation', { days: 10 }),
                invokeTool('get_market_report'),
                invokeTool('get_hot_concepts', { top_n: 10 }),
                invokeTool('get_sector_realtime', { type: 'industry', top_n: 20 }),
            ]);
            setMonitorData({
                overview: overviewRes.success ? overviewRes.data : null,
                anomalies: anomaliesRes.success ? anomaliesRes.data : null,
                realtime: realtimeRes.success ? realtimeRes.data : null,
                limitUp: limitRes.success ? limitRes.data : null,
                limitStats: limitStatRes.success ? limitStatRes.data : null,
                sectorRotation: rotationRes.success ? rotationRes.data : null,
                marketReport: reportRes.success ? reportRes.data : null,
                hotConcepts: hotConceptRes.success ? hotConceptRes.data : null,
                sectorRealtime: sectorRealtimeRes.success ? sectorRealtimeRes.data : null,
            });
        } finally {
            setMonitorLoading(false);
        }
    };

    // ========== 风险与组合 ==========
    const [riskLoading, setRiskLoading] = useState(false);
    const [riskData, setRiskData] = useState({
        summary: null as unknown,
        portfolio: null as unknown,
        analysis: null as unknown,
        varResult: null as unknown,
        drawdown: null as unknown,
    });
    const [riskParams, setRiskParams] = useState({
        confidence: '0.95',
        holdingPeriod: '5',
        drawdown: '0.1',
    });

    const refreshRisk = async () => {
        setRiskLoading(true);
        try {
            const [summaryRes, portfolioRes, analysisRes] = await Promise.all([
                invokeTool('get_portfolio_summary'),
                invokeTool('get_portfolio_risk'),
                invokeTool('analyze_portfolio_risk'),
            ]);
            setRiskData(prev => ({
                ...prev,
                summary: summaryRes.success ? summaryRes.data : null,
                portfolio: portfolioRes.success ? portfolioRes.data : null,
                analysis: analysisRes.success ? analysisRes.data : null,
            }));
        } finally {
            setRiskLoading(false);
        }
    };

    const runVar = async () => {
        const result = await invokeTool('get_var', {
            confidence: parseNumber(riskParams.confidence),
            holding_period: parseNumber(riskParams.holdingPeriod),
        });
        setRiskData(prev => ({ ...prev, varResult: result.success ? result.data : null }));
    };

    const runDrawdown = async () => {
        const threshold = parseNumber(riskParams.drawdown);
        const result = await invokeTool('monitor_drawdown', threshold ? { threshold } : {});
        setRiskData(prev => ({ ...prev, drawdown: result.success ? result.data : null }));
    };

    // FE-004: 组合优化功能
    const [optimizeForm, setOptimizeForm] = useState({
        stockCodes: '',
        targetReturn: '0.15',
        riskFreeRate: '0.03',
        method: 'mean_variance',
    });
    const [optimizeResult, setOptimizeResult] = useState<unknown>(null);

    const runOptimize = async () => {
        const stockCodes = optimizeForm.stockCodes
            .split(/[,，\s]+/)
            .map(code => code.trim())
            .filter(Boolean);
        if (stockCodes.length === 0) {
            setOptimizeResult({ error: '请输入股票代码（逗号分隔）' });
            return;
        }
        const toolName = optimizeForm.method === 'risk_parity'
            ? 'optimize_risk_parity'
            : 'optimize_mean_variance';
        const result = await invokeTool(toolName, {
            stock_codes: stockCodes,
            target_return: parseNumber(optimizeForm.targetReturn),
            risk_free_rate: parseNumber(optimizeForm.riskFreeRate),
        });
        setOptimizeResult(result.success ? result.data : { error: result.error || '组合优化失败' });
    };

    // ========== 研报与情绪 ==========
    const [researchForm, setResearchForm] = useState({
        stockCode: '',
        keyword: '',
        industry: '',
        topics: '',
    });
    const [researchResults, setResearchResults] = useState<Array<{ title: string; data: unknown; type?: Visualization['type'] }>>([]);

    const pushResearchResult = (title: string, data: unknown, type: Visualization['type'] = 'table') => {
        setResearchResults(prev => [{ title, data, type }, ...prev].slice(0, 5));
    };

    const runResearchTool = async (title: string, name: string, args: Record<string, unknown> = {}, type: Visualization['type'] = 'table') => {
        const result = await invokeTool(name, args);
        if (result.success) {
            pushResearchResult(title, result.data, type);
        }
    };

    // ========== 回测与量化 ==========
    const [quantForm, setQuantForm] = useState({
        stockCode: '',
        strategy: 'sma_cross',
        startDate: '',
        endDate: '',
        initialCapital: '100000',
    });
    const [backtestStrategies, setBacktestStrategies] = useState<string[]>([]);
    const [backtestResult, setBacktestResult] = useState<unknown>(null);
    const [backtestHistory, setBacktestHistory] = useState<unknown>(null);
    const [backtestDetail, setBacktestDetail] = useState<unknown>(null);

    const loadBacktestStrategies = async () => {
        const result = await invokeTool('get_backtest_strategies');
        if (result.success && result.data && typeof result.data === 'object') {
            const list = (result.data as { strategies?: string[] }).strategies;
            if (Array.isArray(list)) {
                setBacktestStrategies(list);
            }
        }
    };

    const runBacktest = async () => {
        if (!quantForm.stockCode) return;
        const params: Record<string, unknown> = {};
        if (quantForm.startDate) params.start_date = quantForm.startDate;
        if (quantForm.endDate) params.end_date = quantForm.endDate;
        const initialCapital = parseNumber(quantForm.initialCapital);
        if (initialCapital) params.initial_capital = initialCapital;

        const result = await invokeTool('run_simple_backtest', {
            stock_codes: quantForm.stockCode.trim(),
            strategy: quantForm.strategy,
            params,
        });
        setBacktestResult(result.success ? result.data : null);
    };

    const loadBacktestHistory = async () => {
        const result = await invokeTool('get_backtest_results', { limit: 10 });
        setBacktestHistory(result.success ? result.data : null);
        setBacktestDetail(null); // 清除之前的详情
    };

    // FE-007: 查看回测详情
    const viewBacktestDetail = async (backtestId: string) => {
        const result = await invokeTool('get_backtest_detail', { backtest_id: backtestId });
        if (result.success) {
            setBacktestDetail(result.data);
        }
    };

    // ========== 产业链/宏观/期权/同步 ==========
    const [macroForm, setMacroForm] = useState({
        chainId: '',
        stockCode: '',
        affectedNode: '',
        impactType: 'positive',
        macroIndicator: 'gdp',
        macroPeriods: '6',
        optionType: 'call',
        optionStrike: '',
        optionPrice: '',
        optionDays: '30',
        optionVol: '0.2',
    });
    const [chainOptions, setChainOptions] = useState<Array<{ id: string; name: string }>>([]);
    const [eventForm, setEventForm] = useState({
        stockCode: '',
        startDate: '',
        endDate: '',
        eventTypes: '',
    });
    const [optionChainForm, setOptionChainForm] = useState({
        underlying: '510050',
        expiryMonth: '',
        limit: '200',
    });
    const [macroResults, setMacroResults] = useState<Array<{ title: string; data: unknown; type?: Visualization['type'] }>>([]);

    const pushMacroResult = (title: string, data: unknown, type: Visualization['type'] = 'table') => {
        setMacroResults(prev => [{ title, data, type }, ...prev].slice(0, 5));
    };

    const runMacroTool = async (title: string, name: string, args: Record<string, unknown> = {}, type: Visualization['type'] = 'table') => {
        const result = await invokeTool(name, args);
        if (result.success) {
            pushMacroResult(title, result.data, type);
        }
    };

    const loadIndustryChains = async () => {
        const result = await invokeTool('get_industry_chains');
        if (result.success && result.data && typeof result.data === 'object') {
            const chains = (result.data as { chains?: Array<{ id?: string; name?: string }> }).chains || [];
            const options = chains
                .filter(item => item.id && item.name)
                .map(item => ({ id: String(item.id), name: String(item.name) }));
            setChainOptions(options);
            if (!macroForm.chainId && options.length > 0) {
                setMacroForm(prev => ({ ...prev, chainId: options[0].id }));
            }
        }
    };

    // ========== 实盘交易 ==========
    const [liveLoading, setLiveLoading] = useState(false);
    const [liveMessage, setLiveMessage] = useState<string | null>(null);
    const [liveForm, setLiveForm] = useState({
        accountId: '',
        stockCode: '',
        side: 'buy',
        quantity: '',
        orderType: 'market',
        price: '',
        timeInForce: 'day',
        cancelOrderId: '',
    });
    const [liveData, setLiveData] = useState({
        account: null as unknown,
        positions: null as unknown,
        orders: null as unknown,
    });

    const refreshLive = async () => {
        setLiveLoading(true);
        setLiveMessage(null);
        try {
            const accountArgs = liveForm.accountId ? { account_id: liveForm.accountId } : {};
            const [accountRes, positionsRes, ordersRes] = await Promise.all([
                invokeTool('get_live_account', accountArgs),
                invokeTool('get_live_positions', accountArgs),
                invokeTool('get_live_orders', accountArgs),
            ]);
            setLiveData({
                account: accountRes.success ? accountRes.data : null,
                positions: positionsRes.success ? positionsRes.data : null,
                orders: ordersRes.success ? ordersRes.data : null,
            });
            if (!accountRes.success) {
                setLiveMessage(accountRes.error || '获取账户信息失败');
            }
        } finally {
            setLiveLoading(false);
        }
    };

    const handlePlaceLiveOrder = async () => {
        setLiveMessage(null);
        const stockCode = liveForm.stockCode.trim();
        const quantity = parseNumber(liveForm.quantity);
        const price = parseNumber(liveForm.price);
        if (!stockCode || !quantity) {
            setLiveMessage('请填写股票代码和数量');
            return;
        }
        if (liveForm.orderType === 'limit' && !price) {
            setLiveMessage('限价单需要填写价格');
            return;
        }
        const result = await invokeTool('place_live_order', {
            account_id: liveForm.accountId || undefined,
            stock_code: stockCode,
            side: liveForm.side,
            quantity,
            order_type: liveForm.orderType,
            price: liveForm.orderType === 'limit' ? price : undefined,
            time_in_force: liveForm.timeInForce,
        });
        if (!result.success) {
            setLiveMessage(result.error || '下单失败');
            return;
        }
        setLiveMessage('已提交实盘订单');
        refreshLive();
    };

    const handleCancelLiveOrder = async () => {
        setLiveMessage(null);
        const orderId = liveForm.cancelOrderId.trim();
        if (!orderId) {
            setLiveMessage('请输入订单ID');
            return;
        }
        const result = await invokeTool('cancel_live_order', {
            order_id: orderId,
            account_id: liveForm.accountId || undefined,
        });
        if (!result.success) {
            setLiveMessage(result.error || '撤单失败');
            return;
        }
        setLiveMessage('已提交撤单请求');
        refreshLive();
    };

    // ========== 交易台账 ==========
    const [ledgerLoading, setLedgerLoading] = useState(false);
    const [watchlist, setWatchlist] = useState<string[]>([]);
    const [watchlistMeta, setWatchlistMeta] = useState<Record<string, WatchlistMeta>>({});
    const [positions, setPositions] = useState<unknown[]>([]);
    const [tradePlans, setTradePlans] = useState<TradePlan[]>([]);
    const [newWatchlistCode, setNewWatchlistCode] = useState('');
    const [planForm, setPlanForm] = useState({
        stockCode: '',
        action: 'buy',
        targetPrice: '',
        stopLoss: '',
        takeProfit: '',
        quantity: '',
        note: '',
    });
    const [positionForm, setPositionForm] = useState({
        stockCode: '',
        quantity: '',
        costPrice: '',
    });

    const loadLedger = async () => {
        setLedgerLoading(true);
        try {
            const [watchRes, metaRes, posRes, planRes] = await Promise.all([
                window.electronAPI.watchlist.get(),
                window.electronAPI.watchlist.getMeta(),
                invokeTool('get_positions'),
                window.electronAPI.trading.getPlans({ limit: 50 }),
            ]);
            setWatchlist(watchRes.success ? (watchRes.data || []) : []);
            const metaList = metaRes.success ? (metaRes.data || []) : [];
            const metaMap: Record<string, WatchlistMeta> = {};
            metaList.forEach((meta: WatchlistMeta) => {
                metaMap[meta.stockCode] = meta;
            });
            setWatchlistMeta(metaMap);
            const positionsList = posRes.success && posRes.data && typeof posRes.data === 'object'
                ? (posRes.data as { positions?: unknown[] }).positions || []
                : [];
            setPositions(positionsList);
            setTradePlans(planRes.success ? (planRes.data || []) : []);
        } finally {
            setLedgerLoading(false);
        }
    };

    const handleAddWatchlist = async () => {
        const code = newWatchlistCode.trim();
        if (!code) return;
        const result = await window.electronAPI.watchlist.add(code);
        if (result.success) {
            setNewWatchlistCode('');
            loadLedger();
        }
    };

    const handleSaveMeta = async (stockCode: string, updates: Partial<WatchlistMeta>) => {
        const current = watchlistMeta[stockCode] || { stockCode } as WatchlistMeta;
        const merged = {
            stockCode,
            costPrice: updates.costPrice ?? current.costPrice ?? undefined,
            targetPrice: updates.targetPrice ?? current.targetPrice ?? undefined,
            stopLoss: updates.stopLoss ?? current.stopLoss ?? undefined,
            note: updates.note ?? current.note ?? undefined,
        };
        await window.electronAPI.watchlist.saveMeta(merged);
        loadLedger();
    };

    const handleRemoveWatchlist = async (stockCode: string) => {
        await window.electronAPI.watchlist.remove(stockCode);
        await window.electronAPI.watchlist.removeMeta(stockCode);
        loadLedger();
    };

    const handleCreatePlan = async () => {
        if (!planForm.stockCode) return;
        const plan = {
            stockCode: planForm.stockCode.trim(),
            action: planForm.action as 'buy' | 'sell',
            targetPrice: parseNumber(planForm.targetPrice),
            stopLoss: parseNumber(planForm.stopLoss),
            takeProfit: parseNumber(planForm.takeProfit),
            quantity: parseNumber(planForm.quantity),
            note: planForm.note,
            status: 'planned' as TradePlanStatus,
        };
        const result = await window.electronAPI.trading.createPlan(plan);
        if (result.success) {
            setPlanForm({
                stockCode: '',
                action: 'buy',
                targetPrice: '',
                stopLoss: '',
                takeProfit: '',
                quantity: '',
                note: '',
            });
            loadLedger();
        }
    };

    const handlePlanStatus = async (planId: string, status: TradePlanStatus) => {
        await window.electronAPI.trading.setPlanStatus(planId, status);
        loadLedger();
    };

    const handleRemovePlan = async (planId: string) => {
        await window.electronAPI.trading.removePlan(planId);
        loadLedger();
    };

    const handleLogDecisionFromPlan = async (plan: TradePlan) => {
        await window.electronAPI.trading.logDecision({
            stockCode: plan.stockCode,
            decisionType: plan.action,
            source: 'user',
            reason: plan.note || '交易计划',
            targetPrice: plan.targetPrice,
            stopLoss: plan.stopLoss,
        });
        loadLedger();
    };

    const handleAddPosition = async () => {
        const stockCode = positionForm.stockCode.trim();
        const quantity = parseNumber(positionForm.quantity);
        const costPrice = parseNumber(positionForm.costPrice);
        if (!stockCode || !quantity || costPrice === undefined) return;
        await invokeTool('add_position', { stock_code: stockCode, quantity, cost_price: costPrice });
        setPositionForm({ stockCode: '', quantity: '', costPrice: '' });
        loadLedger();
    };

    const handleRemovePosition = async (stockCode: string) => {
        await invokeTool('remove_position', { stock_code: stockCode });
        loadLedger();
    };

    useEffect(() => {
        if (!isOpen) return;
        if (activeTab === 'alerts') refreshAlerts();
        if (activeTab === 'monitor') refreshMonitor();
        if (activeTab === 'risk') refreshRisk();
        if (activeTab === 'quant') {
            loadBacktestStrategies();
            loadBacktestHistory();
        }
        if (activeTab === 'macro') {
            loadIndustryChains();
        }
        if (activeTab === 'live') {
            refreshLive();
        }
        if (activeTab === 'ledger') loadLedger();
    }, [activeTab, isOpen]);

    const tabs: Array<{ key: WorkbenchTab; label: string; icon: string }> = useMemo(() => ([
        { key: 'alerts', label: '告警', icon: '🔔' },
        { key: 'monitor', label: '盯盘', icon: '🖥️' },
        { key: 'risk', label: '风控', icon: '🛡️' },
        { key: 'research', label: '研报', icon: '📚' },
        { key: 'quant', label: '回测', icon: '📈' },
        { key: 'macro', label: '产业链', icon: '🧭' },
        { key: 'live', label: '实盘', icon: '⚡' },
        { key: 'ledger', label: '台账', icon: '🧾' },
    ]), []);

    if (!isOpen) return null;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content personal-center workbench-center" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>功能工作台</h2>
                    <button className="modal-close" onClick={onClose}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </div>

                <div className="pc-tabs">
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            className={`pc-tab ${activeTab === tab.key ? 'active' : ''}`}
                            onClick={() => setActiveTab(tab.key)}
                        >
                            <span className="pc-tab-icon">{tab.icon}</span>
                            <span className="pc-tab-label">{tab.label}</span>
                        </button>
                    ))}
                </div>

                <div className="modal-body pc-content workbench-content">
                    {activeTab === 'alerts' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>创建告警</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>类型</label>
                                        <select
                                            className="form-select"
                                            value={alertForm.type}
                                            onChange={e => setAlertForm(prev => ({ ...prev, type: e.target.value }))}
                                        >
                                            <option value="price">价格</option>
                                            <option value="indicator">指标</option>
                                            <option value="limit">涨跌停</option>
                                            <option value="fund_flow">资金流</option>
                                            <option value="combo">组合条件</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            placeholder="600519"
                                            value={alertForm.symbol}
                                            onChange={e => setAlertForm(prev => ({ ...prev, symbol: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>条件</label>
                                        <input
                                            className="form-input"
                                            placeholder="above / below / change_above"
                                            value={alertForm.condition}
                                            onChange={e => setAlertForm(prev => ({ ...prev, condition: e.target.value }))}
                                        />
                                    </div>
                                    {(alertForm.type === 'price' || alertForm.type === 'fund_flow') && (
                                        <div className="form-group">
                                            <label>{alertForm.type === 'price' ? '目标价' : '阈值'}</label>
                                            <input
                                                className="form-input"
                                                placeholder="数值"
                                                value={alertForm.type === 'price' ? alertForm.price : alertForm.threshold}
                                                onChange={e => setAlertForm(prev => ({
                                                    ...prev,
                                                    price: alertForm.type === 'price' ? e.target.value : prev.price,
                                                    threshold: alertForm.type === 'fund_flow' ? e.target.value : prev.threshold,
                                                }))}
                                            />
                                        </div>
                                    )}
                                    {alertForm.type === 'indicator' && (
                                        <div className="form-group">
                                            <label>周期</label>
                                            <input
                                                className="form-input"
                                                placeholder="daily/weekly"
                                                value={alertForm.period}
                                                onChange={e => setAlertForm(prev => ({ ...prev, period: e.target.value }))}
                                            />
                                        </div>
                                    )}
                                    {alertForm.type === 'combo' && (
                                        <>
                                            <div className="form-group">
                                                <label>预设策略</label>
                                                <select
                                                    className="form-select"
                                                    value={alertForm.preset}
                                                    onChange={e => setAlertForm(prev => ({ ...prev, preset: e.target.value }))}
                                                >
                                                    <option value="">自定义</option>
                                                    {comboPresets.map(preset => (
                                                        <option key={preset.key} value={preset.key}>{preset.name}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div className="form-group">
                                                <label>名称</label>
                                                <input
                                                    className="form-input"
                                                    value={alertForm.name}
                                                    onChange={e => setAlertForm(prev => ({ ...prev, name: e.target.value }))}
                                                />
                                            </div>
                                            <div className="form-group workbench-span">
                                                <label>自定义条件(JSON)</label>
                                                <input
                                                    className="form-input"
                                                    placeholder='{"logic":"and","conditions":[...]}'
                                                    value={alertForm.custom}
                                                    onChange={e => setAlertForm(prev => ({ ...prev, custom: e.target.value }))}
                                                />
                                            </div>
                                        </>
                                    )}
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-primary" onClick={handleCreateAlert}>创建告警</button>
                                    <button className="btn btn-secondary" onClick={refreshAlerts} disabled={alertLoading}>
                                        {alertLoading ? '刷新中...' : '刷新列表'}
                                    </button>
                                    <button className="btn btn-secondary" onClick={handleCheckAlerts}>检查触发</button>
                                </div>
                                {alertMessage && <div className="pc-empty">{alertMessage}</div>}
                            </div>

                            {renderResult('价格告警', alertLists.price)}
                            {renderResult('指标告警', alertLists.indicator)}
                            {renderResult('涨跌停告警', alertLists.limit)}
                            {renderResult('资金流告警', alertLists.fundFlow)}
                            {renderResult('组合告警', alertLists.combo)}

                            <div className="pc-section">
                                <h3>删除告警</h3>
                                <div className="workbench-grid">
                                    {(['price', 'indicator', 'limit', 'fundFlow', 'combo'] as const).map(type => (
                                        <div key={type} className="workbench-card">
                                            <div className="workbench-card-title">{type}</div>
                                            {alertLists[type].length === 0 ? (
                                                <div className="pc-empty">暂无</div>
                                            ) : (
                                                (alertLists[type] as Array<{ id?: string; name?: string; code?: string }>).map(alert => (
                                                    <div key={alert.id || `${alert.code}-${alert.name}`} className="workbench-list-item">
                                                        <span>{alert.name || alert.code || '告警'}</span>
                                                        <button className="btn btn-secondary" onClick={() => handleDeleteAlert(type, alert.id)}>删除</button>
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'monitor' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>盯盘总览</h3>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={refreshMonitor} disabled={monitorLoading}>
                                        {monitorLoading ? '刷新中...' : '刷新数据'}
                                    </button>
                                </div>
                            </div>
                            {renderResult('市场概览', monitorData.overview)}
                            {renderResult('市场报告', monitorData.marketReport)}
                            {renderResult('市场异常扫描', monitorData.anomalies)}
                            {renderResult('实时异动', monitorData.realtime)}
                            {renderResult('涨停列表', monitorData.limitUp)}
                            {renderResult('涨停统计', monitorData.limitStats)}
                            {renderResult('板块轮动', monitorData.sectorRotation)}
                            {renderResult('热门概念', monitorData.hotConcepts)}
                            {renderResult('板块行情', monitorData.sectorRealtime)}
                        </div>
                    )}

                    {activeTab === 'risk' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>组合风险</h3>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={refreshRisk} disabled={riskLoading}>
                                        {riskLoading ? '刷新中...' : '刷新风险'}
                                    </button>
                                </div>
                            </div>
                            {renderResult('组合摘要', riskData.summary)}
                            {renderResult('集中度风险', riskData.portfolio)}
                            {renderResult('风险评分', riskData.analysis)}

                            <div className="pc-section">
                                <h3>VaR / 回撤监控</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>置信度</label>
                                        <input
                                            className="form-input"
                                            value={riskParams.confidence}
                                            onChange={e => setRiskParams(prev => ({ ...prev, confidence: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>持有期(天)</label>
                                        <input
                                            className="form-input"
                                            value={riskParams.holdingPeriod}
                                            onChange={e => setRiskParams(prev => ({ ...prev, holdingPeriod: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>回撤阈值</label>
                                        <input
                                            className="form-input"
                                            value={riskParams.drawdown}
                                            onChange={e => setRiskParams(prev => ({ ...prev, drawdown: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={runVar}>计算 VaR</button>
                                    <button className="btn btn-secondary" onClick={runDrawdown}>监控回撤</button>
                                </div>
                            </div>
                            {renderResult('VaR 结果', riskData.varResult)}
                            {renderResult('回撤预警', riskData.drawdown)}

                            {/* FE-004: 组合优化子面板 */}
                            <div className="pc-section">
                                <h3>组合优化</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            placeholder="600519, 000001"
                                            value={optimizeForm.stockCodes}
                                            onChange={e => setOptimizeForm(prev => ({ ...prev, stockCodes: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>优化方法</label>
                                        <select
                                            className="form-select"
                                            value={optimizeForm.method}
                                            onChange={e => setOptimizeForm(prev => ({ ...prev, method: e.target.value }))}
                                        >
                                            <option value="mean_variance">均值-方差优化</option>
                                            <option value="risk_parity">风险平价</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>目标收益率</label>
                                        <input
                                            className="form-input"
                                            placeholder="0.15"
                                            value={optimizeForm.targetReturn}
                                            onChange={e => setOptimizeForm(prev => ({ ...prev, targetReturn: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>无风险利率</label>
                                        <input
                                            className="form-input"
                                            placeholder="0.03"
                                            value={optimizeForm.riskFreeRate}
                                            onChange={e => setOptimizeForm(prev => ({ ...prev, riskFreeRate: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-primary" onClick={runOptimize}>运行优化</button>
                                </div>
                            </div>
                            {optimizeResult && renderResult('优化结果', optimizeResult)}
                        </div>
                    )}

                    {activeTab === 'research' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>研报与情绪</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            value={researchForm.stockCode}
                                            onChange={e => setResearchForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>关键词</label>
                                        <input
                                            className="form-input"
                                            value={researchForm.keyword}
                                            onChange={e => setResearchForm(prev => ({ ...prev, keyword: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>行业</label>
                                        <input
                                            className="form-input"
                                            value={researchForm.industry}
                                            onChange={e => setResearchForm(prev => ({ ...prev, industry: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>热点主题</label>
                                        <input
                                            className="form-input"
                                            placeholder="人工智能, 低空经济"
                                            value={researchForm.topics}
                                            onChange={e => setResearchForm(prev => ({ ...prev, topics: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('个股研报', 'get_stock_research', { stock_code: researchForm.stockCode, limit: 10 })}>
                                        个股研报
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('研报摘要', 'summarize_research_report', { stock_code: researchForm.stockCode, summary_type: 'key_points' })}>
                                        研报摘要
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('研报对比', 'compare_reports', { stock_code: researchForm.stockCode })}>
                                        研报对比
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('研报观点', 'extract_report_opinions', { stock_code: researchForm.stockCode, time_range: '3m', opinion_types: ['rating', 'target_price'] })}>
                                        研报观点
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('研报概览', 'get_research_summary')}>
                                        研报概览
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('最新研报', 'get_recent_research', { days: 7, limit: 20 })}>
                                        最新研报
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('研报搜索', 'search_research', { keyword: researchForm.keyword, industry: researchForm.industry })}>
                                        研报搜索
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('行业研报汇总', 'summarize_industry_reports', { industry: researchForm.industry || '科技', time_range: '1m' })}>
                                        行业研报
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('新闻列表', 'get_stock_news', { stock_code: researchForm.stockCode, limit: 10 })}>
                                        新闻列表
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('实时新闻', 'search_stock_news_realtime', { stock_code: researchForm.stockCode, days: 3 })}>
                                        实时新闻
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('个股情绪', 'get_stock_sentiment', { stock_code: researchForm.stockCode })}>
                                        个股情绪
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('新闻情绪', 'get_news_sentiment', { stock_code: researchForm.stockCode, days: 7 })}>
                                        新闻情绪
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runResearchTool('社媒情绪', 'analyze_social_sentiment', { stock_code: researchForm.stockCode, time_filter: '7d' })}>
                                        社媒情绪
                                    </button>
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => {
                                            const topics = researchForm.topics
                                                .split(',')
                                                .map(item => item.trim())
                                                .filter(Boolean);
                                            if (topics.length === 0) return;
                                            runResearchTool('热点报告', 'generate_hot_topic_report', { topics, mode: 'industry', max_sources: 8 });
                                        }}
                                    >
                                        热点报告
                                    </button>
                                </div>
                            </div>

                            {researchResults.length === 0 ? (
                                <div className="pc-empty">暂无研报结果</div>
                            ) : (
                                researchResults.map(item => (
                                    <div key={item.title} className="pc-section">
                                        <h3>{item.title}</h3>
                                        <VisualizationRenderer visualization={{ type: item.type || 'table', data: item.data }} />
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    {activeTab === 'quant' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>策略回测</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            value={quantForm.stockCode}
                                            onChange={e => setQuantForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>策略</label>
                                        <select
                                            className="form-select"
                                            value={quantForm.strategy}
                                            onChange={e => setQuantForm(prev => ({ ...prev, strategy: e.target.value }))}
                                        >
                                            {backtestStrategies.length > 0 ? backtestStrategies.map(item => (
                                                <option key={item} value={item}>{item}</option>
                                            )) : (
                                                <>
                                                    <option value="sma_cross">sma_cross</option>
                                                    <option value="rsi">rsi</option>
                                                    <option value="trend">trend</option>
                                                </>
                                            )}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>开始日期</label>
                                        <input
                                            className="form-input"
                                            placeholder="YYYY-MM-DD"
                                            value={quantForm.startDate}
                                            onChange={e => setQuantForm(prev => ({ ...prev, startDate: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>结束日期</label>
                                        <input
                                            className="form-input"
                                            placeholder="YYYY-MM-DD"
                                            value={quantForm.endDate}
                                            onChange={e => setQuantForm(prev => ({ ...prev, endDate: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>初始资金</label>
                                        <input
                                            className="form-input"
                                            value={quantForm.initialCapital}
                                            onChange={e => setQuantForm(prev => ({ ...prev, initialCapital: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-primary" onClick={runBacktest}>运行回测</button>
                                    <button className="btn btn-secondary" onClick={loadBacktestHistory}>历史回测</button>
                                </div>
                            </div>

                            {backtestResult && (
                                <div className="pc-section">
                                    <h3>回测结果</h3>
                                    <VisualizationRenderer visualization={{ type: 'backtest', data: backtestResult }} />
                                </div>
                            )}

                            {/* FE-007: 回测历史列表 - 可点击查看详情 */}
                            <div className="pc-section">
                                <h3>历史回测记录 {backtestHistory && <span style={{ fontSize: '0.8em', color: '#888' }}>（点击查看详情）</span>}</h3>
                                {backtestHistory && typeof backtestHistory === 'object' ? (
                                    <div className="backtest-history-list">
                                        {(Array.isArray((backtestHistory as any).results) ? (backtestHistory as any).results : []).map((item: any, idx: number) => (
                                            <div
                                                key={item.id || idx}
                                                className="backtest-history-item"
                                                style={{
                                                    padding: '12px',
                                                    marginBottom: '8px',
                                                    background: 'var(--bg-tertiary)',
                                                    borderRadius: '8px',
                                                    cursor: 'pointer',
                                                    border: '1px solid transparent',
                                                    transition: 'border-color 0.2s',
                                                }}
                                                onClick={() => item.id && viewBacktestDetail(item.id)}
                                                onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent-color)')}
                                                onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'transparent')}
                                            >
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                                    <strong>{item.strategy || '策略'}</strong>
                                                    <span style={{ color: item.totalReturn >= 0 ? 'var(--success-color)' : 'var(--danger-color)' }}>
                                                        {item.totalReturn !== undefined ? `${(item.totalReturn * 100).toFixed(2)}%` : '--'}
                                                    </span>
                                                </div>
                                                <div style={{ fontSize: '0.85em', color: '#888' }}>
                                                    {item.stockCodes?.join(', ') || item.stock_codes?.join(', ') || '未知股票'}
                                                    {item.createdAt && ` • ${new Date(item.createdAt).toLocaleDateString()}`}
                                                </div>
                                            </div>
                                        ))}
                                        {(!(backtestHistory as any).results || (backtestHistory as any).results.length === 0) && (
                                            <div className="pc-empty">暂无历史回测记录</div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="pc-empty">点击"历史回测"按钮加载</div>
                                )}
                            </div>

                            {/* FE-007: 回测详情展示 */}
                            {backtestDetail && (
                                <div className="pc-section">
                                    <h3>回测详情 <button className="btn btn-xs" onClick={() => setBacktestDetail(null)} style={{ marginLeft: '8px', fontSize: '0.8em' }}>关闭</button></h3>
                                    <VisualizationRenderer visualization={{ type: 'backtest', title: '回测详情', data: backtestDetail }} />
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'macro' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>产业链与宏观</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>产业链ID</label>
                                        <select
                                            className="form-select"
                                            value={macroForm.chainId}
                                            onChange={e => setMacroForm(prev => ({ ...prev, chainId: e.target.value }))}
                                        >
                                            {chainOptions.length > 0 ? (
                                                chainOptions.map(option => (
                                                    <option key={option.id} value={option.id}>
                                                        {option.name} ({option.id})
                                                    </option>
                                                ))
                                            ) : (
                                                <option value="">暂无可用产业链</option>
                                            )}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.stockCode}
                                            onChange={e => setMacroForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>影响节点</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.affectedNode}
                                            onChange={e => setMacroForm(prev => ({ ...prev, affectedNode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>影响方向</label>
                                        <select
                                            className="form-select"
                                            value={macroForm.impactType}
                                            onChange={e => setMacroForm(prev => ({ ...prev, impactType: e.target.value }))}
                                        >
                                            <option value="positive">利好</option>
                                            <option value="negative">利空</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('产业链列表', 'get_industry_chains')}>产业链列表</button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('产业链结构', 'get_chain_structure', { chain_id: macroForm.chainId })}>产业链结构</button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('链路位置', 'get_stock_chain_position', { stock_code: macroForm.stockCode })}>链路位置</button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('影响传导', 'analyze_chain_impact', { chain_id: macroForm.chainId, affected_node: macroForm.affectedNode, impact_type: macroForm.impactType })}>影响传导</button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>宏观指标</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>指标代码</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.macroIndicator}
                                            onChange={e => setMacroForm(prev => ({ ...prev, macroIndicator: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>期数</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.macroPeriods}
                                            onChange={e => setMacroForm(prev => ({ ...prev, macroPeriods: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('宏观指标', 'get_macro_indicator', { indicator: macroForm.macroIndicator, periods: parseNumber(macroForm.macroPeriods) || 6 })}>
                                        获取指标
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('指标搜索', 'search_macro_indicators', { keyword: macroForm.macroIndicator })}>
                                        搜索指标
                                    </button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>事件日历</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            placeholder="600519（可选）"
                                            value={eventForm.stockCode}
                                            onChange={e => setEventForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>开始日期</label>
                                        <input
                                            className="form-input"
                                            placeholder="YYYY-MM-DD（可选）"
                                            value={eventForm.startDate}
                                            onChange={e => setEventForm(prev => ({ ...prev, startDate: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>结束日期</label>
                                        <input
                                            className="form-input"
                                            placeholder="YYYY-MM-DD（可选）"
                                            value={eventForm.endDate}
                                            onChange={e => setEventForm(prev => ({ ...prev, endDate: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group workbench-span">
                                        <label>事件类型（逗号分隔）</label>
                                        <input
                                            className="form-input"
                                            placeholder="公告, 分红, 业绩"
                                            value={eventForm.eventTypes}
                                            onChange={e => setEventForm(prev => ({ ...prev, eventTypes: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => {
                                            const args: Record<string, unknown> = {};
                                            const stockCode = eventForm.stockCode.trim();
                                            if (stockCode) args.stock_code = stockCode;
                                            const types = eventForm.eventTypes
                                                .split(',')
                                                .map(item => item.trim())
                                                .filter(Boolean);
                                            if (types.length > 0) args.event_types = types;
                                            if (eventForm.startDate && eventForm.endDate) {
                                                args.date_range = { start: eventForm.startDate, end: eventForm.endDate };
                                            }
                                            runMacroTool('事件日历', 'get_event_calendar', args);
                                        }}
                                    >
                                        获取事件
                                    </button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>期权链</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>标的代码</label>
                                        <input
                                            className="form-input"
                                            placeholder="510050"
                                            value={optionChainForm.underlying}
                                            onChange={e => setOptionChainForm(prev => ({ ...prev, underlying: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>到期月份</label>
                                        <input
                                            className="form-input"
                                            placeholder="YYYY-MM（可选）"
                                            value={optionChainForm.expiryMonth}
                                            onChange={e => setOptionChainForm(prev => ({ ...prev, expiryMonth: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>返回数量</label>
                                        <input
                                            className="form-input"
                                            value={optionChainForm.limit}
                                            onChange={e => setOptionChainForm(prev => ({ ...prev, limit: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => runMacroTool('期权链', 'get_option_chain', {
                                            underlying: optionChainForm.underlying,
                                            expiry_month: optionChainForm.expiryMonth || undefined,
                                            limit: parseNumber(optionChainForm.limit) || 200,
                                        })}
                                    >
                                        查询期权链
                                    </button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>期权估值</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>期权类型</label>
                                        <select
                                            className="form-select"
                                            value={macroForm.optionType}
                                            onChange={e => setMacroForm(prev => ({ ...prev, optionType: e.target.value }))}
                                        >
                                            <option value="call">看涨</option>
                                            <option value="put">看跌</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>标的价格</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.optionPrice}
                                            onChange={e => setMacroForm(prev => ({ ...prev, optionPrice: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>行权价</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.optionStrike}
                                            onChange={e => setMacroForm(prev => ({ ...prev, optionStrike: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>到期天数</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.optionDays}
                                            onChange={e => setMacroForm(prev => ({ ...prev, optionDays: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>波动率</label>
                                        <input
                                            className="form-input"
                                            value={macroForm.optionVol}
                                            onChange={e => setMacroForm(prev => ({ ...prev, optionVol: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => runMacroTool('期权定价', 'calculate_option_price', {
                                            option_type: macroForm.optionType,
                                            underlying_price: parseNumber(macroForm.optionPrice),
                                            strike_price: parseNumber(macroForm.optionStrike),
                                            time_to_expiry: parseNumber(macroForm.optionDays),
                                            volatility: parseNumber(macroForm.optionVol),
                                        })}
                                    >
                                        期权定价
                                    </button>
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => runMacroTool('Greeks', 'calculate_greeks', {
                                            underlying_price: parseNumber(macroForm.optionPrice),
                                            strike_price: parseNumber(macroForm.optionStrike),
                                            time_to_expiry: parseNumber(macroForm.optionDays),
                                            volatility: parseNumber(macroForm.optionVol),
                                        })}
                                    >
                                        Greeks
                                    </button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>数据同步</h3>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('同步K线', 'sync_stock_kline', { stock_code: macroForm.stockCode, days: 120 })}>
                                        同步K线
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('同步行情', 'sync_stock_quotes', { stock_codes: macroForm.stockCode ? [macroForm.stockCode] : [] })}>
                                        同步行情
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('同步财务', 'sync_batch_financials', { limit: 50 })}>
                                        同步财务
                                    </button>
                                    <button
                                        className="btn btn-secondary"
                                        onClick={() => {
                                            const indicators = macroForm.macroIndicator
                                                .split(',')
                                                .map(item => item.trim())
                                                .filter(Boolean);
                                            runMacroTool('同步宏观', 'sync_macro_data', indicators.length > 0 ? { indicators } : {});
                                        }}
                                    >
                                        同步宏观
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => runMacroTool('同步情绪', 'sync_market_sentiment', {})}>
                                        同步情绪
                                    </button>
                                </div>
                            </div>

                            {macroResults.length === 0 ? (
                                <div className="pc-empty">暂无结果</div>
                            ) : (
                                macroResults.map(item => (
                                    <div key={item.title} className="pc-section">
                                        <h3>{item.title}</h3>
                                        <VisualizationRenderer visualization={{ type: item.type || 'table', data: item.data }} />
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    {activeTab === 'live' && (
                        <div className="pc-panel">
                            {/* FE-002: 券商配置提示 */}
                            <div className="pc-section" style={{
                                background: 'linear-gradient(135deg, rgba(251, 191, 36, 0.1), rgba(245, 158, 11, 0.05))',
                                border: '1px solid rgba(251, 191, 36, 0.3)',
                                borderRadius: '12px',
                                padding: '16px',
                                marginBottom: '16px'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                    <span style={{ fontSize: '1.5em' }}>⚠️</span>
                                    <div>
                                        <h4 style={{ margin: '0 0 8px 0', color: 'var(--warning-color)' }}>券商接入配置中</h4>
                                        <p style={{ margin: '0', fontSize: '0.9em', color: '#888', lineHeight: 1.5 }}>
                                            实盘交易功能需要配置券商接口才能使用。请设置环境变量：
                                            <br />
                                            <code style={{
                                                background: 'var(--bg-tertiary)',
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                fontSize: '0.85em'
                                            }}>LIVE_TRADING_PROVIDER=http</code>
                                            <br />
                                            并配置对应的<code style={{ background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.85em' }}>LIVE_TRADING_HTTP_URL</code>等参数。
                                        </p>
                                    </div>
                                </div>
                            </div>
                            <div className="pc-section">
                                <h3>实盘账户</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>账户ID（可选）</label>
                                        <input
                                            className="form-input"
                                            placeholder="account_id"
                                            value={liveForm.accountId}
                                            onChange={e => setLiveForm(prev => ({ ...prev, accountId: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={refreshLive} disabled={liveLoading}>
                                        {liveLoading ? '刷新中...' : '刷新账户/持仓/订单'}
                                    </button>
                                </div>
                                {liveMessage && <div className="pc-empty">{liveMessage}</div>}
                            </div>
                            {renderResult('账户信息', liveData.account)}
                            {renderResult('实盘持仓', liveData.positions)}
                            {renderResult('实盘订单', liveData.orders)}

                            <div className="pc-section">
                                <h3>实盘下单</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            placeholder="600519"
                                            value={liveForm.stockCode}
                                            onChange={e => setLiveForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>方向</label>
                                        <select
                                            className="form-select"
                                            value={liveForm.side}
                                            onChange={e => setLiveForm(prev => ({ ...prev, side: e.target.value }))}
                                        >
                                            <option value="buy">买入</option>
                                            <option value="sell">卖出</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>数量</label>
                                        <input
                                            className="form-input"
                                            placeholder="100"
                                            value={liveForm.quantity}
                                            onChange={e => setLiveForm(prev => ({ ...prev, quantity: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>订单类型</label>
                                        <select
                                            className="form-select"
                                            value={liveForm.orderType}
                                            onChange={e => setLiveForm(prev => ({ ...prev, orderType: e.target.value }))}
                                        >
                                            <option value="market">市价</option>
                                            <option value="limit">限价</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>价格（限价）</label>
                                        <input
                                            className="form-input"
                                            placeholder="价格"
                                            value={liveForm.price}
                                            onChange={e => setLiveForm(prev => ({ ...prev, price: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>有效期</label>
                                        <select
                                            className="form-select"
                                            value={liveForm.timeInForce}
                                            onChange={e => setLiveForm(prev => ({ ...prev, timeInForce: e.target.value }))}
                                        >
                                            <option value="day">当日有效</option>
                                            <option value="gtc">长期有效</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-primary" onClick={handlePlaceLiveOrder}>提交订单</button>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>撤单</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>订单ID</label>
                                        <input
                                            className="form-input"
                                            placeholder="order_id"
                                            value={liveForm.cancelOrderId}
                                            onChange={e => setLiveForm(prev => ({ ...prev, cancelOrderId: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={handleCancelLiveOrder}>撤单</button>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'ledger' && (
                        <div className="pc-panel">
                            <div className="pc-section">
                                <h3>提醒与通知</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>启用通知</label>
                                        <select
                                            className="form-select"
                                            value={notificationPrefs.enabled ? 'on' : 'off'}
                                            onChange={e => {
                                                const enabled = e.target.value === 'on';
                                                const next = { ...notificationPrefs, enabled };
                                                setNotificationPrefs(next);
                                                window.electronAPI.config.save({ notificationPreferences: next });
                                            }}
                                        >
                                            <option value="on">开启</option>
                                            <option value="off">关闭</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>每日上限</label>
                                        <input
                                            className="form-input"
                                            value={notificationPrefs.maxDaily?.toString() || ''}
                                            onChange={e => {
                                                const maxDaily = parseNumber(e.target.value) || 0;
                                                const next = { ...notificationPrefs, maxDaily };
                                                setNotificationPrefs(next);
                                                window.electronAPI.config.save({ notificationPreferences: next });
                                            }}
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="pc-section">
                                <h3>自选股台账</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>新增自选</label>
                                        <input
                                            className="form-input"
                                            placeholder="600519"
                                            value={newWatchlistCode}
                                            onChange={e => setNewWatchlistCode(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={handleAddWatchlist}>加入自选</button>
                                    <button className="btn btn-secondary" onClick={loadLedger} disabled={ledgerLoading}>
                                        {ledgerLoading ? '刷新中...' : '刷新台账'}
                                    </button>
                                </div>
                                {watchlist.length === 0 ? (
                                    <div className="pc-empty">暂无自选</div>
                                ) : (
                                    watchlist.map(code => {
                                        const meta = watchlistMeta[code] || { stockCode: code } as WatchlistMeta;
                                        return (
                                            <div key={code} className="workbench-ledger-row">
                                                <div className="workbench-ledger-title">
                                                    <strong>{code}</strong>
                                                </div>
                                                <div className="workbench-ledger-fields">
                                                    <input
                                                        className="form-input"
                                                        placeholder="成本价"
                                                        defaultValue={meta.costPrice ?? ''}
                                                        onBlur={e => handleSaveMeta(code, { costPrice: parseNumber(e.target.value) })}
                                                    />
                                                    <input
                                                        className="form-input"
                                                        placeholder="目标价"
                                                        defaultValue={meta.targetPrice ?? ''}
                                                        onBlur={e => handleSaveMeta(code, { targetPrice: parseNumber(e.target.value) })}
                                                    />
                                                    <input
                                                        className="form-input"
                                                        placeholder="止损"
                                                        defaultValue={meta.stopLoss ?? ''}
                                                        onBlur={e => handleSaveMeta(code, { stopLoss: parseNumber(e.target.value) })}
                                                    />
                                                    <input
                                                        className="form-input"
                                                        placeholder="备注"
                                                        defaultValue={meta.note ?? ''}
                                                        onBlur={e => handleSaveMeta(code, { note: e.target.value })}
                                                    />
                                                </div>
                                                <button className="btn btn-secondary" onClick={() => handleRemoveWatchlist(code)}>移除</button>
                                            </div>
                                        );
                                    })
                                )}
                            </div>

                            <div className="pc-section">
                                <h3>持仓管理</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            value={positionForm.stockCode}
                                            onChange={e => setPositionForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>数量</label>
                                        <input
                                            className="form-input"
                                            value={positionForm.quantity}
                                            onChange={e => setPositionForm(prev => ({ ...prev, quantity: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>成本价</label>
                                        <input
                                            className="form-input"
                                            value={positionForm.costPrice}
                                            onChange={e => setPositionForm(prev => ({ ...prev, costPrice: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-secondary" onClick={handleAddPosition}>添加持仓</button>
                                </div>
                                {positions.length === 0 ? (
                                    <div className="pc-empty">暂无持仓</div>
                                ) : (
                                    positions.map((pos: any) => (
                                        <div key={pos.code} className="workbench-list-item">
                                            <span>{pos.name || pos.code} · {pos.quantity}股</span>
                                            <button className="btn btn-secondary" onClick={() => handleRemovePosition(pos.code)}>移除</button>
                                        </div>
                                    ))
                                )}
                            </div>

                            <div className="pc-section">
                                <h3>交易计划</h3>
                                <div className="workbench-grid">
                                    <div className="form-group">
                                        <label>股票代码</label>
                                        <input
                                            className="form-input"
                                            value={planForm.stockCode}
                                            onChange={e => setPlanForm(prev => ({ ...prev, stockCode: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>动作</label>
                                        <select
                                            className="form-select"
                                            value={planForm.action}
                                            onChange={e => setPlanForm(prev => ({ ...prev, action: e.target.value }))}
                                        >
                                            <option value="buy">买入</option>
                                            <option value="sell">卖出</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>目标价</label>
                                        <input
                                            className="form-input"
                                            value={planForm.targetPrice}
                                            onChange={e => setPlanForm(prev => ({ ...prev, targetPrice: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>止损</label>
                                        <input
                                            className="form-input"
                                            value={planForm.stopLoss}
                                            onChange={e => setPlanForm(prev => ({ ...prev, stopLoss: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>止盈</label>
                                        <input
                                            className="form-input"
                                            value={planForm.takeProfit}
                                            onChange={e => setPlanForm(prev => ({ ...prev, takeProfit: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>数量</label>
                                        <input
                                            className="form-input"
                                            value={planForm.quantity}
                                            onChange={e => setPlanForm(prev => ({ ...prev, quantity: e.target.value }))}
                                        />
                                    </div>
                                    <div className="form-group workbench-span">
                                        <label>备注</label>
                                        <input
                                            className="form-input"
                                            value={planForm.note}
                                            onChange={e => setPlanForm(prev => ({ ...prev, note: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="workbench-actions">
                                    <button className="btn btn-primary" onClick={handleCreatePlan}>保存计划</button>
                                </div>
                                {tradePlans.length === 0 ? (
                                    <div className="pc-empty">暂无计划</div>
                                ) : (
                                    tradePlans.map(plan => (
                                        <div key={plan.id} className="workbench-plan-row">
                                            <div>
                                                <strong>{plan.stockCode}</strong> · {plan.action.toUpperCase()} · {plan.status}
                                            </div>
                                            <div className="workbench-actions">
                                                <button className="btn btn-secondary" onClick={() => handlePlanStatus(plan.id, 'executed')}>已执行</button>
                                                <button className="btn btn-secondary" onClick={() => handlePlanStatus(plan.id, 'cancelled')}>取消</button>
                                                <button className="btn btn-secondary" onClick={() => handleLogDecisionFromPlan(plan)}>记录决策</button>
                                                <button className="btn btn-secondary" onClick={() => handleRemovePlan(plan.id)}>删除</button>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchModal;
