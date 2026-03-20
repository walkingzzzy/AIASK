'use client';

import { useState } from 'react';
import UnifiedDecisionPanel from '@/components/unified-decision-panel';
import UnifiedDecisionDiffLogList from '@/components/unified-decision-diff-log-list';
import { ErrorState, LoadingState } from '@/components/status-state';
import { PageContainer, SectionCard, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';

export default function DecisionPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode();
  const { trigger, data, isPending, error, reset } = useApiMutation<unknown>();
  const {
    trigger: triggerDetails,
    data: rawDetails,
    isPending: isDetailsPending,
  } = useApiMutation<unknown>({ errorToast: true });
  const [investmentStyle, setInvestmentStyle] = useState<'aggressive' | 'balanced' | 'conservative'>('balanced');
  const [legacyMode, setLegacyMode] = useState(false);
  const [lastBody, setLastBody] = useState<Record<string, unknown> | null>(null);

  const envelope = data && typeof data === 'object' ? data as Record<string, unknown> : null;
  const result = envelope?.card ?? envelope ?? null;
  const detailsEnvelope = rawDetails && typeof rawDetails === 'object' ? rawDetails as Record<string, unknown> : null;
  const details = detailsEnvelope?.details ?? detailsEnvelope?.raw ?? null;
  const legacyComparison = detailsEnvelope?.legacyComparison ?? envelope?.legacyComparison ?? null;

  function runDecision() {
    if (!validate()) return;
    reset();
    const body = { code: trimmedCode, investmentStyle, legacyMode };
    setLastBody(body);
    trigger('/assistant/unified-decision', { method: 'POST' }, body);
  }

  function loadDetails() {
    if (!lastBody) return;
    triggerDetails('/assistant/unified-decision/details', { method: 'POST' }, lastBody);
  }

  return (
    <PageContainer>
      <SectionCard className="p-5">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div>
            <h1 className="mt-0 text-2xl font-bold text-primary">统一决策工作台</h1>
            <p className="mb-0 mt-2 text-sm text-text-secondary">
              把 stock / quant / event / user 风险偏好统一收束到一条决策流水线里，并支持旧入口差异对照。
            </p>
          </div>
          <div className="grid gap-3">
            <StockCodeInput
              id="decision-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
              placeholder="输入股票代码 (如 600519)"
            />
            <label className="grid gap-1 text-xs text-text-secondary">
              <span className="font-medium text-text-muted uppercase tracking-wider">统一决策风格</span>
              <select
                value={investmentStyle}
                onChange={(e) => setInvestmentStyle(e.target.value as 'aggressive' | 'balanced' | 'conservative')}
                className="rounded-md border border-glass-border bg-surface px-3 py-2 text-sm"
              >
                <option value="balanced">平衡</option>
                <option value="conservative">保守</option>
                <option value="aggressive">激进</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-text-secondary">
              <input type="checkbox" checked={legacyMode} onChange={(e) => setLegacyMode(e.target.checked)} />
              <span>开启 legacy diff</span>
            </label>
            <button
              type="button"
              onClick={runDecision}
              disabled={isPending}
              className="rounded-xl border border-primary/30 bg-primary px-4 py-3 text-sm font-medium text-white transition hover:bg-primary/90 disabled:opacity-50"
            >
              运行统一决策
            </button>
          </div>
        </div>
      </SectionCard>

      {isPending ? (
        <div className="mt-4 rounded-xl border border-glass-border bg-surface-alt/20 p-8">
          <LoadingState text="统一决策流水线运行中，正在聚合多源证据..." />
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <ErrorState text={error} hint="请检查股票代码与网络状态后重试" />
        </div>
      ) : null}

      {result && typeof result === 'object' ? (
        <>
          <UnifiedDecisionPanel
            card={result as Record<string, unknown>}
            details={details}
            detailsPending={isDetailsPending}
            canLoadDetails
            onLoadDetails={loadDetails}
            legacyComparison={legacyComparison}
          />
          <UnifiedDecisionDiffLogList
            enabled={legacyMode}
            code={String(lastBody?.code ?? trimmedCode ?? '')}
          />
        </>
      ) : null}
    </PageContainer>
  );
}
