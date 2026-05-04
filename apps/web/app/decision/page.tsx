'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import ResultWorkbench from '@/components/result-workbench';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import UnifiedDecisionPanel from '@/components/unified-decision-panel';
import UnifiedDecisionDiffLogList from '@/components/unified-decision-diff-log-list';
import { ErrorState, LoadingState } from '@/components/status-state';
import { PageContainer, SectionCard, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { useStockCode } from '@/hooks/use-stock-code';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

export default function DecisionPage() {
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
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

  useEffect(() => {
    if (!workbenchHydrated) return;
    if (!trimmedCode && workbenchContext.stockCode) {
      setCode(workbenchContext.stockCode);
    }
  }, [setCode, trimmedCode, workbenchContext.stockCode, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({ stockCode: trimmedCode || null });
  }, [trimmedCode, updateWorkbenchContext, workbenchHydrated]);

  const pageActions = [
    {
      id: 'decision.run',
      label: '运行统一决策',
      description: '按当前股票和风格运行 unified decision',
      keywords: ['决策', '运行'],
      scope: 'page' as const,
      pageKey: 'decision',
      run: () => {
        runDecision();
        return { message: '已触发统一决策' };
      },
    },
    {
      id: 'decision.load-details',
      label: '加载决策详情',
      description: '加载统一决策的完整证据链详情',
      keywords: ['详情', '证据链'],
      scope: 'page' as const,
      pageKey: 'decision',
      run: () => {
        loadDetails();
        return { message: '已触发决策详情加载' };
      },
    },
  ];
  usePageActions(pageActions);
  const decisionSummary = `${trimmedCode || '未选择股票'}，风格 ${investmentStyle}，legacy diff ${legacyMode ? '开启' : '关闭'}。`;
  const decisionResult = buildLocalResultContract({
    summary: decisionSummary,
    pageActions,
    preferredActionIds: ['decision.run', 'decision.load-details'],
    recommendedLinks: [
      { id: 'decision-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
      { id: 'decision-open-stock-link', label: '个股详情', href: trimmedCode ? `/stock?code=${encodeURIComponent(trimmedCode)}` : '/stock' },
      { id: 'decision-open-risk-link', label: '风险中心', href: '/risk' },
      { id: 'decision-open-execution-link', label: '执行中心', href: trimmedCode ? `/execution?code=${encodeURIComponent(trimmedCode)}` : '/execution' },
    ],
    evidence: [
      { label: '股票', value: trimmedCode || '未选择' },
      { label: '风格', value: investmentStyle },
      { label: '历史接口对照', value: legacyMode ? '开启' : '关闭' },
      { label: '结果', value: result ? '已生成' : '未生成' },
      { label: '详情', value: details ? '已加载' : '未加载' },
    ],
    riskNotes: [error].filter((item): item is string => Boolean(item)),
    platformMeta: {
      sourceTool: 'unified-decision',
      sourceChain: ['decision', investmentStyle, legacyMode ? 'legacy' : 'modern'],
      degraded: Boolean(error),
      fallbackReason: error ? [error] : undefined,
    },
    workbenchTask: defaultWorkbenchTask('decision', `复查统一决策 ${trimmedCode || ''}`.trim(), trimmedCode ? `/decision?code=${encodeURIComponent(trimmedCode)}` : '/decision', 'decision-review', {
      code: trimmedCode || null,
      investmentStyle,
      legacyMode,
    }),
  });
  usePageContext({
    pageKey: 'decision',
    title: '统一决策工作台',
    summary: decisionSummary,
    stockCode: trimmedCode || undefined,
    objectType: 'stock',
    objectId: trimmedCode || 'unselected',
    resultType: 'unified-decision',
    tags: [investmentStyle, legacyMode ? 'legacy diff' : 'modern decision'],
    suggestions: [
      trimmedCode ? `解释 ${trimmedCode} 当前统一决策结果` : '选择股票后解释统一决策结果',
      '比较当前 unified decision 和 legacy diff 的差异',
      '把当前决策页整理成执行建议',
    ],
    recommendedActions: decisionResult.recommendedActions ?? [],
    recommendedLinks: decisionResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(decisionResult.evidence),
    riskNotes: decisionResult.riskNotes ?? [],
    freshness: decisionResult.freshness ?? null,
    raw: {
      code: trimmedCode || null,
      investmentStyle,
      legacyMode,
      hasResult: Boolean(result),
      hasDetails: Boolean(details),
    },
  });

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      code: trimmedCode,
      investmentStyle,
      legacyMode,
    }),
    [investmentStyle, legacyMode, trimmedCode],
  );

  const applyView = useCallback((snapshot: Record<string, unknown>) => {
    if (typeof snapshot.code === 'string') {
      setCode(snapshot.code);
    }
    if (
      snapshot.investmentStyle === 'aggressive'
      || snapshot.investmentStyle === 'balanced'
      || snapshot.investmentStyle === 'conservative'
    ) {
      setInvestmentStyle(snapshot.investmentStyle);
    }
    if (typeof snapshot.legacyMode === 'boolean') {
      setLegacyMode(snapshot.legacyMode);
    }
  }, [setCode]);

  const primaryContent = (
    <>
      <SectionCard className="p-5">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div>
            <h1 className="mt-0 text-2xl font-bold text-primary">统一决策工作台</h1>
            <p className="mb-0 mt-2 text-sm text-text-secondary">
              将基本面、量化、事件和用户风险偏好合并成一张决策卡片，并支持与历史接口结果对照。
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
            <AskAiButton
              stockCode={trimmedCode || undefined}
              summary={`风格 ${investmentStyle}，legacy diff ${legacyMode ? '开启' : '关闭'}`}
              prompt={trimmedCode ? `请解释 ${trimmedCode} 当前统一决策页` : '请解释当前统一决策页'}
            />
          </div>
        </div>
      </SectionCard>

      <ResultWorkbench pageKey="decision" title="统一决策工作台" result={decisionResult} />

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
    </>
  );

  const secondaryContent = (
    <SectionCard className="p-4">
      <div className="text-sm font-medium text-text-primary">决策工作区摘要</div>
      <div className="mt-3 grid gap-3 text-xs text-text-secondary">
        <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
          <div>股票：{trimmedCode || '-'}</div>
          <div className="mt-1">风格：{investmentStyle}</div>
          <div className="mt-1">历史接口对照：{legacyMode ? '开启' : '关闭'}</div>
          <div className="mt-1">结果：{result ? '已生成' : '未生成'}</div>
          <div className="mt-1">详情：{details ? '已加载' : '未加载'}</div>
        </div>
        <div className="rounded-xl border border-dashed border-glass-border p-3">
          保存视图后，可以把股票、风格和 legacy diff 组合作为工作区快照复用。
        </div>
      </div>
    </SectionCard>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar pageKey="decision" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      <WorkspaceSplitLayout pageKey="decision" primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
