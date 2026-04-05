'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';

type DiagnosisResult = {
    recommendation: 'buy' | 'hold' | 'sell' | string;
    confidence: number | null;
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

function normalizeDiagnosisPayload(payload: unknown): DiagnosisResult {
    const data = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    const card = data.card && typeof data.card === 'object' ? data.card as Record<string, unknown> : null;
    const raw = data.raw && typeof data.raw === 'object' ? data.raw as Record<string, unknown> : null;
    const rawData = raw?.data && typeof raw.data === 'object' ? raw.data as Record<string, unknown> : raw;
    const summaryInfo = rawData?.summary && typeof rawData.summary === 'object' ? rawData.summary as Record<string, unknown> : null;
    const rawRecommendation = String(
        card?.action ??
        rawData?.recommendation ??
        rawData?.action ??
        rawData?.signal ??
        'hold',
    ).toLowerCase();
    const normalizedRecommendation =
        rawRecommendation.includes('buy') ? 'buy'
            : rawRecommendation.includes('sell') ? 'sell'
                : 'hold';
    const rawConfidence = Number(
        card?.confidence ??
        rawData?.confidence ??
        rawData?.score ??
        NaN,
    );
    const confidence = Number.isFinite(rawConfidence)
        ? rawConfidence <= 1
            ? rawConfidence * 100
            : rawConfidence
        : null;
    const rawFactors = Array.isArray(rawData?.evidence) ? rawData.evidence : Array.isArray(rawData?.factors) ? rawData.factors : [];
    const factors = rawFactors
        .slice(0, 6)
        .map((factor): DiagnosisResult['factors'][number] => {
            const record = factor && typeof factor === 'object' && !Array.isArray(factor)
                ? factor as Record<string, unknown>
                : {};
            const signal = String(record.signal ?? '').toLowerCase();
            return {
                name: String(record.name ?? record.factor ?? record.category ?? record.signal ?? '因子'),
                signal: signal.includes('bull') || signal.includes('buy')
                    ? 'bullish'
                    : signal.includes('bear') || signal.includes('sell')
                        ? 'bearish'
                        : 'neutral',
                detail: String(record.detail ?? record.interpretation ?? record.reason ?? record.description ?? record.value ?? ''),
            };
        })
        .filter((factor) => factor.detail);
    const workflowSteps = Array.isArray(rawData?.steps) ? rawData.steps : [];
    const workflowFactors = workflowSteps
        .slice(0, 6)
        .map((step): DiagnosisResult['factors'][number] | null => {
            const record = step && typeof step === 'object' && !Array.isArray(step)
                ? step as Record<string, unknown>
                : {};
            const stepName = String(record.step ?? '');
            const output = record.output && typeof record.output === 'object'
                ? record.output as Record<string, unknown>
                : {};
            const outputData = output.data && typeof output.data === 'object'
                ? output.data as Record<string, unknown>
                : {};
            const signalText = String(outputData.action ?? outputData.signal ?? '').toLowerCase();
            const label = stepName === 'stock_profile'
                ? '股票画像'
                : stepName === 'daily_kline'
                    ? 'K 线快照'
                    : stepName === 'financials'
                        ? '财务快照'
                        : stepName === 'decision_summary'
                            ? '决策摘要'
                            : stepName || '工作流步骤';
            const detail = stepName === 'stock_profile'
                ? String(outputData.name ?? outputData.code ?? outputData.industry ?? '已拉取股票基础信息')
                : stepName === 'daily_kline'
                    ? `已拉取 ${Array.isArray(outputData.rows) ? outputData.rows.length : 0} 条行情`
                    : stepName === 'financials'
                        ? String(outputData.reportDate ?? outputData.report_date ?? outputData.roe ?? '已拉取财务摘要')
                        : String(outputData.summary ?? outputData.reason ?? outputData.description ?? outputData.action_text ?? '');
            return detail
                ? {
                    name: label,
                    signal: signalText.includes('buy') || signalText.includes('bull')
                        ? 'bullish'
                        : signalText.includes('sell') || signalText.includes('bear')
                            ? 'bearish'
                            : 'neutral',
                    detail,
                }
                : null;
        })
        .filter((factor): factor is DiagnosisResult['factors'][number] => Boolean(factor));
    const rawRisks = Array.isArray(rawData?.risks) ? rawData.risks : [];
    const riskCount = Number(summaryInfo?.risk_count ?? rawRisks.length ?? 0);
    const riskLevel = riskCount >= 5 ? 'high' : riskCount >= 2 ? 'medium' : 'low';

    return {
        recommendation: normalizedRecommendation,
        confidence,
        summary: String(
            rawData?.recommendation_text ??
            card?.summary ??
            rawData?.analysis ??
            rawData?.reason ??
            '暂无详细分析',
        ),
        factors: factors.length > 0 ? factors : workflowFactors,
        riskLevel,
    };
}

export function AIDiagnosisPanel({ code }: { code: string }) {
    const [result, setResult] = useState<DiagnosisResult | null>(null);
    const diagnosisApi = useApiMutation<DiagnosisResult>({
        parse: normalizeDiagnosisPayload,
        successToast: false,
        errorToast: false,
    });

    async function runDiagnosis() {
        try {
            const data = await diagnosisApi.triggerAsync(
                '/assistant/analysis-workflow',
                { method: 'POST' },
                { code },
            );
            setResult(data);
        } catch {
            setResult(null);
        }
    }

    if (!result && !diagnosisApi.isPending && !diagnosisApi.error) {
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

    if (diagnosisApi.isPending) {
        return (
            <div className="text-center py-8">
                <div className="inline-block w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-3" />
                <p className="text-text-secondary text-sm">AI 正在分析 {code}...</p>
            </div>
        );
    }

    if (diagnosisApi.error) {
        return (
            <div className="text-center py-6">
                <p className="text-danger text-sm mb-2">诊断失败: {diagnosisApi.error}</p>
                <button onClick={() => { diagnosisApi.reset(); void runDiagnosis(); }} className="text-xs text-primary cursor-pointer hover:underline">重试</button>
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
                        <p className="text-sm text-text-secondary mt-1">置信度: {result.confidence == null ? '--' : `${result.confidence.toFixed(0)}%`}</p>
                    </div>
                    <div className="text-right">
                        <Badge variant={result.riskLevel === 'high' ? 'danger' : result.riskLevel === 'medium' ? 'warning' : 'success'}>
                            风险:{result.riskLevel === 'high' ? '高' : result.riskLevel === 'medium' ? '中' : '低'}
                        </Badge>
                    </div>
                </div>
            </div>

            {/* Summary */}
            <div className="surface-card rounded-lg p-4">
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
                                <div key={i} className="surface-muted rounded-lg p-3">
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
