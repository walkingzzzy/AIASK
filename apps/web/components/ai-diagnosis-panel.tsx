'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';

type DiagnosisResult = {
    state: 'ready' | 'unavailable';
    recommendation: 'buy' | 'hold' | 'sell' | string;
    confidence: number | null;
    summary: string;
    factors: { name: string; signal: 'bullish' | 'bearish' | 'neutral'; detail: string }[];
    riskLevel: 'low' | 'medium' | 'high';
    unavailableReason?: string | null;
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

function normalizeConfidence(value: unknown): number | null {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    const percent = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
    return Math.max(0, Math.min(100, percent));
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function toTextArray(value: unknown): string[] {
    if (Array.isArray(value)) return value.map((item) => String(item ?? '').trim()).filter(Boolean);
    if (typeof value === 'string') return value.split(/[;；\n]/).map((item) => item.trim()).filter(Boolean);
    return [];
}

function normalizeDiagnosisPayload(payload: unknown): DiagnosisResult {
    const data = asRecord(payload);
    const card = asRecord(data.card);
    const raw = asRecord(data.raw);
    const rawData = asRecord(raw.data);
    const resultContract = asRecord(data.result_contract);
    const summaryInfo = asRecord(rawData.summary);
    const platformMeta = asRecord(resultContract.platformMeta);
    const availabilityStatus = String(
        rawData.availability_status
        ?? rawData.status
        ?? resultContract.status
        ?? '',
    ).trim().toLowerCase();
    const fallbackReason = [
        ...toTextArray(platformMeta.fallbackReason),
        ...toTextArray(rawData.risks),
        String(rawData.message ?? '').trim(),
    ].find(Boolean) ?? null;
    if (availabilityStatus === 'unavailable') {
        return {
            state: 'unavailable',
            recommendation: 'hold',
            confidence: null,
            summary: String(
                rawData.recommendation_text
                ?? card.summary
                ?? 'AI 诊断暂时不可用，请稍后再试。',
            ),
            factors: [],
            riskLevel: 'medium',
            unavailableReason: fallbackReason,
        };
    }
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
    const rawConfidence =
        card?.confidence ??
        rawData?.confidence ??
        rawData?.score;
    const confidence = normalizeConfidence(rawConfidence);
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
        state: 'ready',
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
        unavailableReason: null,
    };
}

function summarizeDiagnosisError(error: string | null) {
    if (!error) return 'AI 诊断暂时不可用，请稍后再试。';
    if (/timed?\s*out|timeout|request timed out|mcp error -32001/i.test(error)) {
        return 'AI 诊断服务当前响应较慢，请稍后再试。';
    }
    return 'AI 诊断暂时不可用，请稍后再试。';
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
            <div className="surface-card rounded-lg p-4 text-center">
                <p className="text-sm font-medium text-text-primary">{summarizeDiagnosisError(diagnosisApi.error)}</p>
                <p className="mt-2 text-xs text-text-secondary">当前个股页的行情、K 线、资金流和基本面仍可继续查看。</p>
                <button onClick={() => { diagnosisApi.reset(); void runDiagnosis(); }} className="mt-3 text-xs text-primary cursor-pointer hover:underline">重试</button>
            </div>
        );
    }

    if (!result) return null;

    if (result.state === 'unavailable') {
        return (
            <div className="surface-card rounded-lg p-4">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <p className="text-sm font-semibold text-text-primary">AI 诊断暂时不可用</p>
                        <p className="mt-1 text-sm leading-relaxed text-text-secondary">{result.summary}</p>
                    </div>
                    <Badge variant="warning">稍后再试</Badge>
                </div>
                {result.unavailableReason ? (
                    <p className="mt-3 text-xs text-text-muted">{result.unavailableReason}</p>
                ) : null}
                <div className="mt-3 flex items-center justify-between gap-3">
                    <p className="text-xs text-text-secondary">当前个股页的行情、K 线、资金流和基本面仍可继续查看。</p>
                    <button onClick={runDiagnosis} className="text-xs text-primary cursor-pointer hover:underline">
                        重试
                    </button>
                </div>
            </div>
        );
    }

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
