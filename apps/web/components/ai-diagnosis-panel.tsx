'use client';

import { useState, useCallback } from 'react';
import { Badge } from '@/components/ui';
import { BFF_BASE } from '@/lib/api';

type DiagnosisResult = {
    recommendation: 'buy' | 'hold' | 'sell' | string;
    confidence: number;
    summary: string;
    factors: { name: string; signal: 'bullish' | 'bearish' | 'neutral'; detail: string }[];
    riskLevel: 'low' | 'medium' | 'high';
};

const SIGNAL_COLORS = {
    bullish: { badge: 'danger' as const, label: '看多', icon: '📈' },
    bearish: { badge: 'success' as const, label: '看空', icon: '📉' },
    neutral: { badge: 'neutral' as const, label: '中性', icon: '➡️' },
};

const REC_STYLES: Record<string, { bg: string; text: string; label: string }> = {
    buy: { bg: 'bg-red-500/15 border-red-500/30', text: 'text-red-400', label: '🟢 建议买入' },
    hold: { bg: 'bg-amber-500/15 border-amber-500/30', text: 'text-amber-400', label: '🟡 建议持有' },
    sell: { bg: 'bg-green-500/15 border-green-500/30', text: 'text-green-400', label: '🔴 建议卖出' },
};

export function AIDiagnosisPanel({ code }: { code: string }) {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<DiagnosisResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const runDiagnosis = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`${BFF_BASE}/assistant/diagnosis`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            if (!res.ok) throw new Error(`请求失败: ${res.status}`);
            const json = await res.json();
            const data = json?.data ?? json;

            // Normalize AI response
            setResult({
                recommendation: String(data.recommendation ?? data.signal ?? data.action ?? 'hold').toLowerCase(),
                confidence: Number(data.confidence ?? data.score ?? 50),
                summary: String(data.summary ?? data.analysis ?? data.reason ?? '暂无详细分析'),
                factors: Array.isArray(data.factors) ? data.factors.map((f: any) => ({
                    name: String(f.name ?? f.factor ?? ''),
                    signal: String(f.signal ?? f.direction ?? 'neutral') as 'bullish' | 'bearish' | 'neutral',
                    detail: String(f.detail ?? f.reason ?? f.description ?? ''),
                })) : [
                    { name: '技术面', signal: (data.technical_signal ?? 'neutral') as any, detail: String(data.technical_detail ?? '') },
                    { name: '基本面', signal: (data.fundamental_signal ?? 'neutral') as any, detail: String(data.fundamental_detail ?? '') },
                    { name: '资金面', signal: (data.fund_signal ?? 'neutral') as any, detail: String(data.fund_detail ?? '') },
                    { name: '情绪面', signal: (data.sentiment_signal ?? 'neutral') as any, detail: String(data.sentiment_detail ?? '') },
                ].filter(f => f.detail),
                riskLevel: String(data.riskLevel ?? data.risk_level ?? data.risk ?? 'medium') as DiagnosisResult['riskLevel'],
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setLoading(false);
        }
    }, [code]);

    if (!result && !loading && !error) {
        return (
            <div className="text-center py-8">
                <p className="text-text-secondary text-sm mb-3">AI 将综合分析技术面、基本面、资金面和情绪面，给出投资建议</p>
                <button
                    onClick={runDiagnosis}
                    className="px-6 py-2 bg-gradient-to-r from-primary to-purple-500 text-white rounded-lg cursor-pointer text-sm font-medium hover:shadow-lg transition-shadow"
                >
                    🤖 开始 AI 诊断
                </button>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="text-center py-8">
                <div className="inline-block w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-3" />
                <p className="text-text-secondary text-sm">AI 正在分析 {code}...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-center py-6">
                <p className="text-danger text-sm mb-2">诊断失败: {error}</p>
                <button onClick={runDiagnosis} className="text-xs text-primary cursor-pointer hover:underline">重试</button>
            </div>
        );
    }

    if (!result) return null;

    const recStyle = REC_STYLES[result.recommendation] || REC_STYLES.hold;

    return (
        <div className="space-y-4">
            {/* Main Recommendation */}
            <div className={`rounded-lg border p-4 ${recStyle.bg}`}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className={`text-xl font-bold ${recStyle.text}`}>{recStyle.label}</p>
                        <p className="text-sm text-text-secondary mt-1">置信度: {result.confidence}%</p>
                    </div>
                    <div className="text-right">
                        <Badge variant={result.riskLevel === 'high' ? 'danger' : result.riskLevel === 'medium' ? 'warning' : 'success'}>
                            风险:{result.riskLevel === 'high' ? '高' : result.riskLevel === 'medium' ? '中' : '低'}
                        </Badge>
                    </div>
                </div>
            </div>

            {/* Summary */}
            <div className="glass rounded-lg p-4">
                <h4 className="text-sm font-semibold mb-2">📋 综合分析</h4>
                <p className="text-sm text-text-secondary leading-relaxed">{result.summary}</p>
            </div>

            {/* Factor Analysis */}
            {result.factors.length > 0 && (
                <div>
                    <h4 className="text-sm font-semibold mb-2">📊 多维度信号</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {result.factors.map((f, i) => {
                            const cfg = SIGNAL_COLORS[f.signal] || SIGNAL_COLORS.neutral;
                            return (
                                <div key={i} className="glass rounded-lg p-3">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span>{cfg.icon}</span>
                                        <span className="text-sm font-medium">{f.name}</span>
                                        <Badge variant={cfg.badge}>{cfg.label}</Badge>
                                    </div>
                                    <p className="text-xs text-text-secondary">{f.detail}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Refresh button */}
            <div className="text-center">
                <button
                    onClick={runDiagnosis}
                    className="text-xs text-primary cursor-pointer hover:underline"
                >
                    🔄 重新诊断
                </button>
            </div>
        </div>
    );
}
