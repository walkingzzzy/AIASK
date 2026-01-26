/**
 * 决策记录与复盘面板
 */

import React, { useMemo, useState, useEffect } from 'react';

interface DecisionPanelProps {
    title?: string;
    data: unknown;
}

type TradingDecision = {
    id: string;
    stockCode: string;
    stockName?: string;
    decisionType: 'buy' | 'sell' | 'hold' | 'watch';
    source: 'ai' | 'user';
    reason: string;
    targetPrice?: number;
    createdAt: number;
    actualResult?: 'profit' | 'loss' | 'neutral';
    profitPercent?: number;
    verifiedAt?: number;
};

type DecisionPayload = {
    decisions?: TradingDecision[];
    summary?: {
        totalDecisions?: number;
        verifiedDecisions?: number;
        accuracyRate?: number;
    };
    insights?: string[];
    period?: { start: number; end: number };
};

const formatDate = (timestamp?: number): string => {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
};

const normalizePayload = (data: unknown): DecisionPayload => {
    if (Array.isArray(data)) {
        return { decisions: data as TradingDecision[] };
    }

    if (data && typeof data === 'object') {
        const payload = data as DecisionPayload;
        if (Array.isArray(payload.decisions)) return payload;
        if (Array.isArray((payload as any).data)) {
            return { decisions: (payload as any).data } as DecisionPayload;
        }
    }

    return { decisions: [] };
};

const decisionLabels: Record<TradingDecision['decisionType'], string> = {
    buy: '买入',
    sell: '卖出',
    hold: '持有',
    watch: '观望',
};

const resultLabels: Record<NonNullable<TradingDecision['actualResult']>, string> = {
    profit: '盈利',
    loss: '亏损',
    neutral: '中性',
};

const DecisionPanel: React.FC<DecisionPanelProps> = ({ title, data }) => {
    const payload = useMemo(() => normalizePayload(data), [data]);
    const [decisions, setDecisions] = useState<TradingDecision[]>(payload.decisions || []);
    const [profitInputs, setProfitInputs] = useState<Record<string, string>>({});

    useEffect(() => {
        setDecisions(payload.decisions || []);
    }, [payload.decisions]);

    const now = Date.now();
    const dueDecisions = decisions
        .filter(item => !item.verifiedAt)
        .filter(item => now - item.createdAt > 7 * 24 * 60 * 60 * 1000);

    const summary = useMemo(() => {
        if (payload.summary) return payload.summary;
        const total = decisions.length;
        const verified = decisions.filter(item => item.verifiedAt).length;
        const profit = decisions.filter(item => item.actualResult === 'profit').length;
        return {
            totalDecisions: total,
            verifiedDecisions: verified,
            accuracyRate: verified > 0 ? (profit / verified) * 100 : 0,
        };
    }, [payload.summary, decisions]);

    const handleVerify = async (decisionId: string, result: 'profit' | 'loss' | 'neutral') => {
        const profitRaw = profitInputs[decisionId];
        const parsed = profitRaw ? Number(profitRaw) : undefined;
        const profitPercent = parsed !== undefined && Number.isFinite(parsed) ? parsed : undefined;
        const response = await window.electronAPI.trading.verifyDecision(decisionId, result, profitPercent);
        if (!response.success) return;

        setDecisions(prev => prev.map(item => (
            item.id === decisionId
                ? {
                    ...item,
                    actualResult: result,
                    profitPercent: profitPercent ?? item.profitPercent,
                    verifiedAt: Date.now(),
                }
                : item
        )));
    };

    if (decisions.length === 0) {
        return (
            <div className="visualization decision-panel empty">
                {title && <div className="visualization-title">{title}</div>}
                <div className="data-empty">暂无决策记录</div>
            </div>
        );
    }

    return (
        <div className="visualization decision-panel">
            {title && <div className="visualization-title">{title}</div>}

            <div className="decision-summary">
                <div>
                    <span>决策总数</span>
                    <strong>{summary.totalDecisions ?? decisions.length}</strong>
                </div>
                <div>
                    <span>已复盘</span>
                    <strong>{summary.verifiedDecisions ?? 0}</strong>
                </div>
                <div>
                    <span>准确率</span>
                    <strong>{summary.accuracyRate !== undefined ? summary.accuracyRate.toFixed(1) : '0.0'}%</strong>
                </div>
            </div>

            {dueDecisions.length > 0 && (
                <div className="decision-reminder">
                    ⚠️ 有 {dueDecisions.length} 条决策超过 7 天未复盘
                </div>
            )}

            {payload.insights && payload.insights.length > 0 && (
                <div className="decision-insights">
                    {payload.insights.map(item => (
                        <div key={item}>{item}</div>
                    ))}
                </div>
            )}

            <div className="decision-table">
                <div className="decision-header">
                    <span>日期</span>
                    <span>标的</span>
                    <span>动作</span>
                    <span>理由</span>
                    <span>状态</span>
                    <span>复盘</span>
                </div>
                {decisions.map(item => {
                    const isDue = !item.verifiedAt && now - item.createdAt > 7 * 24 * 60 * 60 * 1000;
                    return (
                        <div key={item.id} className="decision-row">
                            <span>{formatDate(item.createdAt)}</span>
                            <span>{item.stockName ? `${item.stockName} ${item.stockCode}` : item.stockCode}</span>
                            <span className={`decision-tag ${item.decisionType}`}>{decisionLabels[item.decisionType]}</span>
                            <span className="decision-reason">{item.reason}</span>
                            <span>
                                {item.verifiedAt ? (
                                    <span className="decision-tag done">
                                        {item.actualResult ? resultLabels[item.actualResult] : '已复盘'}
                                        {item.profitPercent !== undefined ? ` ${item.profitPercent}%` : ''}
                                    </span>
                                ) : (
                                    <span className={`decision-tag pending ${isDue ? 'warning' : ''}`}>
                                        待复盘
                                    </span>
                                )}
                            </span>
                            <span className="decision-actions">
                                {!item.verifiedAt ? (
                                    <>
                                        <input
                                            className="decision-input"
                                            placeholder="收益%"
                                            value={profitInputs[item.id] || ''}
                                            onChange={event =>
                                                setProfitInputs(prev => ({
                                                    ...prev,
                                                    [item.id]: event.target.value,
                                                }))
                                            }
                                        />
                                        <button onClick={() => handleVerify(item.id, 'profit')}>盈利</button>
                                        <button onClick={() => handleVerify(item.id, 'loss')}>亏损</button>
                                        <button onClick={() => handleVerify(item.id, 'neutral')}>中性</button>
                                    </>
                                ) : (
                                    <span className="decision-done">已复盘</span>
                                )}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default DecisionPanel;
